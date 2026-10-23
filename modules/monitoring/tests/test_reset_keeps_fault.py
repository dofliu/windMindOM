"""復位不清故障（WMOM-20260719-01）。

背景：現場語意上「復位 (reset / Coil[3])」＝確認並解除 latched trip、嘗試重啟，
但「不」等於「修好故障」。先前 `/api/control/command` 的 reset 分支多做了一步
``fault_engine.clear(turbine_id=...)``，等於一按復位就把未解決的故障直接刪掉，
於是帶病機組立刻恢復發電（使用者回報：「按下復位故障自己被清除然後開始發電，照理
說應該不行」）。

修法：reset 分支只呼叫 ``model.cmd_reset()``，不再清 fault_engine。唯一真正清除故障的路徑
是維護中心 ``/api/faults/clear``（工單完成）。

WMOM-20261021-03-b 起：故障是在 PLC 以其預期跳機碼使機組跳機時才轉為 tripped（不再是嚴重度
門檻）；tripped 期間引擎每步設 ``model.maintenance_lock`` 阻擋重啟——取代原本每步重下
``cmd_emergency_stop``（那會讓 TurSt 在 7↔3 間擺盪）。

本檔以引擎層驗證這條不變量（不需 broker / HTTP / 背景執行緒）：
0. 故障 tripped 後機組停著，不再 7↔3 擺盪。
1. 故障 tripped 後 ``cmd_reset`` → 故障仍在、機組被維修鎖擋住，不發電（物理層保護與 PLC 訊號判定兩條路徑）。
2. 走維護清除（``fault_engine.clear`` + ``turbine.reset()``）→ 故障永久移除、機組重新併網發電。
3. 只清故障不 reset 機組（``/api/faults/clear`` 不帶機組、情境批次）也必須恢復發電，即使一小時內第二次跳機
   已讓 PLC 封鎖自動重啟。
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

from simulator.engine import WindFarmSimulator  # noqa: E402


PRODUCING = 6  # tur_state：併網發電（守「復位後不得復電」的不變量核心）
EMERGENCY_STOP = 7
DT = 5.0  # 物理子步上限 5 s（engine._MAX_PHYSICS_DT）


def _running_sim(turbine_count: int = 3) -> WindFarmSimulator:
    sim = WindFarmSimulator(turbine_count=turbine_count)
    sim._running = True
    # 高風速：generator_overspeed 才會真的把轉速推過軟體超速設定（26.5 rpm）
    sim.wind_model.set_override(wind_speed=15.0, wind_direction=180.0, ambient_temp=20.0)
    return sim


def _step(sim: WindFarmSimulator, t0: datetime, i: int, dt: float = DT) -> List[Dict]:
    return sim._run_one_step(t0 + timedelta(seconds=i * dt), dt)


def _inject_and_trip(sim: WindFarmSimulator, tid: str, t0: datetime) -> int:
    """暖機到併網發電 → 注入 generator_overspeed（滿嚴重度）→ 物理層超速保護停機、PLC 記
    事件 351 → 故障轉為 tripped（WMOM-20261021-03-b：跳機由 PLC 依量測值判定，不再是嚴重度門檻）。

    Returns:
        下一個可用的步序號。
    """
    i = 0
    while sim.turbines[tid].tur_state != PRODUCING:
        _step(sim, t0, i)
        i += 1
        assert i < 200, "前置條件：機組應在 1000 s 內併網發電"
    ok = sim.fault_engine.inject("generator_overspeed", tid, severity_rate=0.0, initial_severity=1.0)
    assert ok, "generator_overspeed 應為合法情境"
    fault = next(f for f in sim.fault_engine.active_faults if f.turbine_id == tid)
    while not fault.tripped:
        _step(sim, t0, i)
        i += 1
        assert i < 400, "前置條件：故障應因 PLC 超速跳機而 tripped"
    assert fault.trip_code in (351, 320)
    return i


def test_tripped_fault_keeps_turbine_down_without_7_3_oscillation():
    """故障 tripped 後機組停在停機狀態，不再被引擎每步重下 emergency stop 而在 7↔3 間擺盪。"""
    sim = _running_sim()
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    i = _inject_and_trip(sim, "WT002", t0)
    states = []
    for j in range(i, i + 120):  # 10 分鐘
        _step(sim, t0, j)
        states.append(sim.turbines["WT002"].tur_state)
    assert PRODUCING not in states
    reentries = sum(1 for a, b in zip(states, states[1:]) if b == EMERGENCY_STOP and a != EMERGENCY_STOP)
    assert reentries == 0, f"跳機後不應反覆重入 emergency stop，states={states}"


def test_reset_does_not_remove_fault_or_resume_power():
    """按復位後：故障仍在 active、機組被維修鎖擋住重啟，永不恢復發電。

    復位解除 PLC 鎖存，但故障 tripped 期間引擎每步設 ``maintenance_lock``，機組到不了
    併網發電(6)——抽樣連續多步守住「整段期間都沒發電」，而非拘泥於單一 state 碼。
    """
    sim = _running_sim()
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    i = _inject_and_trip(sim, "WT002", t0)

    # 復位（僅解除 latched trip；如修好的 control.py，不清 fault_engine）
    sim.turbines["WT002"].cmd_reset()

    # 再跑一段時間（10 分鐘）：整段期間機組都不得併網發電
    states = []
    for j in range(i, i + 120):
        _step(sim, t0, j)
        states.append(sim.turbines["WT002"].tur_state)

    active = [f for f in sim.fault_engine.active_faults if f.turbine_id == "WT002"]
    assert len(active) == 1, "復位不得移除未解決故障"
    assert active[0].tripped, "故障應維持 tripped"
    assert PRODUCING not in states, f"復位不得讓帶病機組恢復發電，實得 states={states}"
    assert sim.turbines["WT002"].tur_state != PRODUCING, "結束時仍不得在發電"


def test_reset_leaves_other_turbines_untouched():
    """復位只作用在該機組；其他機組的故障不受影響。"""
    sim = _running_sim()
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    i = _inject_and_trip(sim, "WT002", t0)
    i = max(i, _inject_and_trip(sim, "WT003", t0))

    sim.turbines["WT002"].cmd_reset()
    for j in range(i, i + 4):
        _step(sim, t0, j)

    ids = {f.turbine_id for f in sim.fault_engine.active_faults}
    assert {"WT002", "WT003"} <= ids, "兩台的故障都應仍在（復位不刪任何一台）"


def test_maintenance_clear_permanently_removes_fault():
    """維護中心路徑（fault_engine.clear + turbine.reset）才是真正清除故障。"""
    sim = _running_sim()
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    i = _inject_and_trip(sim, "WT002", t0)

    # 模擬 /api/faults/clear 的動作
    sim.fault_engine.clear(turbine_id="WT002")
    sim.turbines["WT002"].reset()

    # 清除後再跑：不應有任何 WT002 故障被重新注入，引擎也不再因故障壓它 → 會重新併網發電
    states = []
    for j in range(i, i + 200):
        _step(sim, t0, j)
        states.append(sim.turbines["WT002"].tur_state)

    active = [f for f in sim.fault_engine.active_faults if f.turbine_id == "WT002"]
    assert active == [], "維護清除後故障應永久消失"
    assert not sim.turbines["WT002"].maintenance_lock
    assert PRODUCING in states, "維護清除後機組應能重新併網發電"


def _warm_up(sim: WindFarmSimulator, tid: str, t0: datetime, i: int = 0) -> int:
    while sim.turbines[tid].tur_state != PRODUCING:
        _step(sim, t0, i)
        i += 1
        assert i < 2000, "前置條件：機組應併網發電"
    return i


def _inject_hydraulic_leak_and_trip(sim: WindFarmSimulator, tid: str, t0: datetime, i: int) -> int:
    """注入 hydraulic_leak（滿嚴重度）→ PLC 依偏航煞車液壓 < 150 bar 以 T1 228 跳機（訊號判定路徑）。"""
    assert sim.fault_engine.inject("hydraulic_leak", tid, severity_rate=0.0, initial_severity=1.0)
    fault = next(f for f in sim.fault_engine.active_faults if f.turbine_id == tid)
    while not fault.tripped:
        _step(sim, t0, i)
        i += 1
        assert i < 2000, "前置條件：液壓洩漏應使 PLC 以 228 跳機"
    assert fault.trip_code == 228
    return i


def test_signal_trip_keeps_plc_cause_and_reset_start_cannot_resume_power():
    """PLC 訊號判定的 T1 跳機：正常停機、停機原因保留 "plc:228"（不被維修鎖蓋掉）；復位 + 啟動也不復電。"""
    sim = _running_sim(turbine_count=1)
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    model = sim.turbines["WT001"]
    i = _inject_hydraulic_leak_and_trip(sim, "WT001", t0, _warm_up(sim, "WT001", t0))
    states, causes = [], set()
    for j in range(i, i + 24):
        _step(sim, t0, j)
        states.append(model.tur_state)
        causes.add(model.get_control_status()["shutdown_cause"])
    assert 9 in states and EMERGENCY_STOP not in states, f"T1 應走正常伺服停機，states={states}"
    assert causes == {"plc:228"}

    model.cmd_reset()
    model.cmd_start()
    states = []
    for j in range(i + 24, i + 144):
        _step(sim, t0, j)
        states.append(model.tur_state)
    assert PRODUCING not in states, f"復位 + 啟動不得讓帶病機組恢復發電，states={states}"


def test_clear_without_model_reset_resumes_power_even_after_restart_block():
    """一小時內第二次 228 跳機（手冊每小時上限 1）會封鎖自動重啟；只清故障、不 reset 機組時，
    引擎在維修鎖解除時代技師清除跳機計數與封鎖，修好的機組仍要能恢復發電。"""
    sim = _running_sim(turbine_count=1)
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    model = sim.turbines["WT001"]
    i = _warm_up(sim, "WT001", t0)
    for _round in range(2):
        i = _inject_hydraulic_leak_and_trip(sim, "WT001", t0, i)
        for _ in range(12):
            _step(sim, t0, i)
            i += 1
        sim.fault_engine.clear()      # 不帶機組：不呼叫 model.reset()
        i = _warm_up(sim, "WT001", t0, i)
    events = [(e.kind, e.code) for e in model.plc.drain_events()]
    assert events.count(("trip", 228)) == 2
    assert not model.plc.restart_inhibited



def test_full_reset_clears_the_hourly_trip_count_and_a039() -> None:
    """reset() 把模擬時間歸零：PLC 的每碼跳機計數與自動重啟封鎖（A039）也要清，否則修好的機組不能重啟。"""
    from simulator.physics.turbine_physics import TurbinePhysicsModel

    model = TurbinePhysicsModel(seed=3)
    for t in (100.0, 700.0):
        model.plc.note_protection_stop("overspeed_hardware", t)   # 320 每小時上限 1
        model.plc.on_restart(t + 60.0)
    assert model.plc.auto_restart_blocked and 39 in model.plc.active_codes()
    model.reset()
    assert not model.plc.auto_restart_blocked and not model.plc.restart_inhibited
    assert model.plc.active_codes() == {}
