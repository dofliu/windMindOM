"""復位不清故障（WMOM-20260719-01）。

背景：現場語意上「復位 (reset / Coil[3])」＝確認並解除 latched trip、嘗試重啟，
但「不」等於「修好故障」。先前 `/api/control/command` 的 reset 分支多做了一步
``fault_engine.clear(turbine_id=...)``，等於一按復位就把未解決的故障直接刪掉，
於是帶病機組立刻恢復發電（使用者回報：「按下復位故障自己被清除然後開始發電，照理
說應該不行」）。

修法：reset 分支只呼叫 ``model.cmd_reset()``，不再清 fault_engine。引擎每步
（``engine._run_one_step`` line 196-198）只要發現該機組仍有 tripped 故障，就會再次
``cmd_emergency_stop``——因此復位無法讓帶病機組復電。唯一真正清除故障的路徑是維護中心
``/api/faults/clear``（工單完成）。

本檔以引擎層驗證這條不變量（不需 broker / HTTP / 背景執行緒）：
1. 故障 tripped 後 ``cmd_reset`` → 下一步被重新 emergency-stop，故障仍在、機組不發電。
2. 走維護清除（``fault_engine.clear`` + ``turbine.reset()``）→ 故障永久移除、不再被重壓。
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


def _running_sim(turbine_count: int = 3) -> WindFarmSimulator:
    sim = WindFarmSimulator(turbine_count=turbine_count)
    sim._running = True
    return sim


def _step(sim: WindFarmSimulator, t0: datetime, i: int, dt: float = 10.0) -> List[Dict]:
    return sim._run_one_step(t0 + timedelta(seconds=i * dt), dt)


def _inject_and_trip(sim: WindFarmSimulator, tid: str, t0: datetime) -> None:
    """注入 generator_overspeed（rate 0.05×dt10＝+0.5/step，auto_trip 0.6）→ 兩步跳機。"""
    ok = sim.fault_engine.inject("generator_overspeed", tid, severity_rate=0.05)
    assert ok, "generator_overspeed 應為合法情境"
    for i in range(4):
        _step(sim, t0, i)
    fault = next(f for f in sim.fault_engine.active_faults if f.turbine_id == tid)
    assert fault.tripped, "前置條件：故障應已 tripped"
    # 故障 tripped 後機組在 7↔3 間擺盪（dt=10 一步就過 state 7 的 4s dwell 門檻），
    # 故前置條件只守真正的前提：被故障壓著、沒在發電——不綁死單一 state 碼，
    # 日後調 severity_rate/dt/dwell 常數也不會無端斷裂。
    assert sim.turbines[tid].tur_state != PRODUCING, "前置條件：機組不應在發電"


def test_reset_does_not_remove_fault_or_resume_power():
    """按復位後：故障仍在 active、機組被引擎重壓在跳機／重啟等待迴圈，永不恢復發電。

    帶病機組復位後，引擎每步都因 tripped 故障重新 emergency-stop，機組於
    跳機(7)↔重啟等待(3)間擺盪，永遠到不了併網發電(6)——故意抽樣連續多步守住
    「整段期間都沒發電」，而非拘泥於單一 state 碼。
    """
    sim = _running_sim()
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    _inject_and_trip(sim, "WT002", t0)

    # 復位（僅解除 latched trip；如修好的 control.py，不清 fault_engine）
    sim.turbines["WT002"].cmd_reset()

    # 再跑一段時間：整段期間機組都不得併網發電
    states = []
    for i in range(4, 14):
        _step(sim, t0, i)
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
    _inject_and_trip(sim, "WT002", t0)
    _inject_and_trip(sim, "WT003", t0)

    sim.turbines["WT002"].cmd_reset()
    for i in range(8, 12):
        _step(sim, t0, i)

    ids = {f.turbine_id for f in sim.fault_engine.active_faults}
    assert {"WT002", "WT003"} <= ids, "兩台的故障都應仍在（復位不刪任何一台）"


def test_maintenance_clear_permanently_removes_fault():
    """維護中心路徑（fault_engine.clear + turbine.reset）才是真正清除故障。"""
    sim = _running_sim()
    t0 = datetime(2026, 1, 1, 0, 0, 0)
    _inject_and_trip(sim, "WT002", t0)

    # 模擬 /api/faults/clear 的動作
    sim.fault_engine.clear(turbine_id="WT002")
    sim.turbines["WT002"].reset()

    # 清除後再跑：不應有任何 WT002 故障被重新注入，引擎也不再因故障壓它
    for i in range(4, 10):
        _step(sim, t0, i)

    active = [f for f in sim.fault_engine.active_faults if f.turbine_id == "WT002"]
    assert active == [], "維護清除後故障應永久消失"
