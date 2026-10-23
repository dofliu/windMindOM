"""感測器故障情境（WMOM-20261021-08-a，EPIC-DS Phase 4 -08-a）。

只改那支感測器的量測值、機器本身正常；PLC 判定的是故障讀值：

1. 讀值像真故障（漂移）：與真故障相同的警報 / 跳機碼，但同元件的第二支感測器、振動都正常
2. 專屬故障碼（斷線 / 編碼器超出範圍）：只送感測器故障碼，失效的讀值不再參與越限判定（不會連帶送出
   溫度過高、壓力過低、葉片差異）
3. 真故障不會送出感測器故障碼（讀值一直在有效範圍內）
4. PLC 規則：有效範圍、gate、斷線修復後解除
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
for _p in (PROJECT_ROOT, MONITORING_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from simulator.engine import WindFarmSimulator  # noqa: E402
from simulator.physics.fault_engine import FAULT_SCENARIOS  # noqa: E402
from simulator.physics.plc_protection import PlcEvent, PlcProtection  # noqa: E402
from simulator.physics.turbine_physics import TurbinePhysicsModel, TurbineSpec  # noqa: E402

DT = 5.0
PRODUCING = 6
T0 = datetime(2026, 1, 1, 0, 0, 0)
SPEC = TurbineSpec()

# 情境 → (預期碼, 不該出現的碼：同元件真故障的碼或失效讀值會連帶觸發的越限碼)
EXPECTED: Dict[str, Tuple[Set[int], Set[int]]] = {
    "main_bearing_temp_sensor_drift": ({262, 240}, {242, 263, 241}),
    "stator_temp_sensor_drift": ({264, 244}, {250, 265, 245}),
    "main_bearing_temp_sensor_wire_break": ({242}, {262, 240, 263, 241}),
    "blade1_pitch_encoder_fault": ({326}, {335, 336, 337}),
    "yaw_brake_pressure_sensor_fault": ({229}, {260, 228, 261}),
}


def _run(scenario_id: str, minutes: float = 40.0, severity_rate: float = 0.0,
         initial_severity: float = 1.0) -> Tuple[List[PlcEvent], Dict[str, float]]:
    """併網發電後注入故障（預設滿嚴重度），跑 ``minutes`` 分鐘；回傳 PLC 事件與最後一筆 SCADA。"""
    sim = WindFarmSimulator(turbine_count=1)
    sim.wind_model.set_override(wind_speed=15.0, wind_direction=180.0, ambient_temp=25.0)
    model = sim.turbines["WT001"]
    i = 0
    while model.tur_state != PRODUCING or i < 60:
        sim._run_one_step(T0 + timedelta(seconds=i * DT), DT)
        i += 1
        assert i < 400, "前置條件：機組應併網發電"
    model.plc.drain_events()
    assert sim.fault_engine.inject(scenario_id, "WT001", severity_rate=severity_rate,
                                   initial_severity=initial_severity)
    events: List[PlcEvent] = []
    for _ in range(int(minutes * 60 / DT)):
        sim._run_one_step(T0 + timedelta(seconds=i * DT), DT)
        events += model.plc.drain_events()
        i += 1
    return events, dict(sim.latest_data["WT001"]["scada"])


@pytest.mark.parametrize("scenario_id", sorted(EXPECTED))
def test_sensor_fault_raises_only_its_own_codes(scenario_id: str) -> None:
    events, _ = _run(scenario_id)
    raised = {e.code for e in events if e.kind in ("alarm_raised", "trip")}
    expected, forbidden = EXPECTED[scenario_id]
    assert expected <= raised, f"{scenario_id}：應出現 {expected}，實際 {raised}"
    assert not raised & forbidden, f"{scenario_id}：不該出現 {raised & forbidden}"
    assert {a["code"] for a in FAULT_SCENARIOS[scenario_id].alarm_codes} == expected
    assert FAULT_SCENARIOS[scenario_id].category == "sensor_fault"


def test_drift_alarm_precedes_trip_like_the_real_fault() -> None:
    # 從嚴重度 0 慢慢漂（約 40 分鐘到滿）：先警報、後跳機，同真故障
    events, scada = _run("main_bearing_temp_sensor_drift", minutes=60.0, severity_rate=0.0004, initial_severity=0.0)
    order = [e.code for e in events if e.kind in ("alarm_raised", "trip")]
    assert order.index(262) < order.index(240)
    # 第二支感測器正常：分辨感測器與真的軸承故障的依據（真故障時軸承溫度 2 也升溫）
    assert scada["WGEN_GnBrgTmp2"] < SPEC.gen_bearing_alarm
    assert scada["WGEN_GnBrgTmp1"] - scada["WGEN_GnBrgTmp2"] > 20.0


def test_second_bearing_sensor_tells_drift_from_real_wear() -> None:
    """同樣在軸承溫度 1 跳機（240）的那一刻：真故障的軸承溫度 2 已明顯升溫，感測器故障的沒有。"""
    def at_trip(scenario_id: str) -> float:
        sim = WindFarmSimulator(turbine_count=1)
        sim.wind_model.set_override(wind_speed=15.0, wind_direction=180.0, ambient_temp=25.0)
        model = sim.turbines["WT001"]
        for i in range(400):
            sim._run_one_step(T0 + timedelta(seconds=i * DT), DT)
        baseline = sim.latest_data["WT001"]["scada"]["WGEN_GnBrgTmp2"]
        model.plc.drain_events()
        assert sim.fault_engine.inject(scenario_id, "WT001", severity_rate=0.0004, initial_severity=0.0)
        for j in range(400, 400 + int(2 * 3600 / DT)):
            sim._run_one_step(T0 + timedelta(seconds=j * DT), DT)
            if any(e.kind == "trip" and e.code == 240 for e in model.plc.drain_events()):
                return float(sim.latest_data["WT001"]["scada"]["WGEN_GnBrgTmp2"]) - baseline
        raise AssertionError(f"{scenario_id} 沒有跳機")

    assert at_trip("bearing_wear") > 8.0
    assert abs(at_trip("main_bearing_temp_sensor_drift")) < 2.0


@pytest.mark.parametrize("scenario_id, codes", [
    ("bearing_wear", {242, 243}),
    ("stator_winding_degradation", {250, 251}),
    ("hydraulic_leak", {229}),
    ("pitch_imbalance", {326, 327, 328}),
])
def test_real_faults_never_raise_sensor_fault_codes(scenario_id: str, codes: Set[int]) -> None:
    events, _ = _run(scenario_id, minutes=60.0)
    assert not {e.code for e in events} & codes


# ── PLC 規則 ──────────────────────────────────────────────────────────────────

HEALTHY: Dict[str, float] = {
    "WROT_PtAngValBl1": -1.0, "WROT_PtAngValBl2": -1.0, "WROT_PtAngValBl3": -1.0,
    "WYAW_YwVn1AlgnAvg5s": 0.0, "WYAW_YwVn2AlgnAvg5s": 0.0, "WMET_WSpeedNac": 10.0,
    "WGEN_GnBrgTmp1": 45.0, "WGEN_GnBrgTmp2": 44.0, "WGEN_GnStaTmp1": 70.0, "WGEN_GnStaTmp2": 70.5,
    "WNAC_NacTmp": 30.0, "WNAC_NacCabTmp": 36.0, "WGDC_TrfCoreTmp": 40.0, "WCNV_IGCTWtrTmp": 35.0,
    "WCNV_CnvCabinTmp": 44.0, "WCNV_IGCTWtrPres1": 3.5, "WYAW_YwBrkHyPrs": 210.0, "WYAW_YwBrkSealsLeak": 0.0,
    "WNAC_VibMsNacXDir": 1.0, "WNAC_VibMsNacYDir": 1.0, "WCNV_VtgMsCnvGd1": 2.02,
    "WROT_PtMotCurBl1": 6.0, "WROT_PtMotCurBl2": 6.0, "WROT_PtMotCurBl3": 6.0,
    "WROT_RotSpd": 20.0, "WGEN_GnSpd": 20.0, "WCNV_IGCTWtrCond": 0.2,
}


def _drive(plc: PlcProtection, seconds: int, t0: float, **values: float) -> Tuple[float, List[PlcEvent]]:
    t = t0
    for _ in range(seconds):
        t += 1.0
        plc.evaluate({**HEALTHY, **values}, t, 1.0, producing=True)
    return t, plc.drain_events()


def test_broken_wire_trips_after_the_confirmation_delay_and_suppresses_over_limit_rules() -> None:
    plc = PlcProtection(SPEC)
    t, events = _drive(plc, 120, 0.0)
    assert events == []
    t, events = _drive(plc, 2, t, WGEN_GnBrgTmp1=SPEC.pt100_broken_wire_c)
    assert [e.code for e in events] == [], "確認延時 2 s：從第一個越限樣本起算，第 3 個樣本才成立"
    t, events = _drive(plc, 30, t, WGEN_GnBrgTmp1=SPEC.pt100_broken_wire_c)
    assert [(e.kind, e.code) for e in events] == [("trip", 242)], "只報感測器故障，不報溫度過高"
    assert events[0].value == SPEC.pt100_broken_wire_c and events[0].setpoint == SPEC.pt100_valid_range_c[1]
    t, events = _drive(plc, 5, t)  # 修好：讀值回到有效範圍
    assert [(e.kind, e.code) for e in events] == [("trip_cleared", 242)]


def test_out_of_range_low_readings_and_gates() -> None:
    plc = PlcProtection(SPEC)
    t, _ = _drive(plc, 120, 0.0)
    _, events = _drive(plc, 30, t, WYAW_YwBrkHyPrs=SPEC.yaw_pressure_broken_wire_bar)
    assert [(e.kind, e.code) for e in events] == [("trip", 229)], "斷線不是壓力低：不報 260 / 228"
    plc = PlcProtection(SPEC)
    t, _ = _drive(plc, 120, 0.0)
    _, events = _drive(plc, 30, t, WROT_PtAngValBl1=SPEC.blade_encoder_fault_deg)
    assert [(e.kind, e.code) for e in events] == [("trip", 326)], "編碼器故障不再判定葉片差異"
    # 讀值在有效範圍內：一般的越限規則照常（Pt100 經 10 s 濾波，96 °C 約 40 s 才越過 95 °C）
    plc = PlcProtection(SPEC)
    t, _ = _drive(plc, 120, 0.0)
    _, events = _drive(plc, 60, t, WGEN_GnBrgTmp2=SPEC.gen_bearing_trip + 1.0)
    assert {(e.kind, e.code) for e in events} == {("alarm_raised", 263), ("trip", 241)}


def test_invalid_reading_releases_rules_that_were_already_on() -> None:
    """已成立的溫度警報：讀值斷線後立即解除（失效的讀值不能維持警報），改報感測器故障。"""
    plc = PlcProtection(SPEC)
    t, _ = _drive(plc, 120, 0.0)
    t, events = _drive(plc, 45, t, WGEN_GnBrgTmp1=SPEC.gen_bearing_alarm + 2.0)   # 10 s 濾波：約 31 s 越過
    assert [(e.kind, e.code) for e in events] == [("alarm_raised", 262)]
    t, events = _drive(plc, 5, t, WGEN_GnBrgTmp1=SPEC.pt100_broken_wire_c)
    assert [(e.kind, e.code) for e in events] == [("alarm_cleared", 262), ("trip", 242)]
    assert set(plc.active_codes()) == {242}


def test_encoder_fault_on_blade_1_still_judges_blades_2_and_3() -> None:
    plc = PlcProtection(SPEC)
    t, _ = _drive(plc, 120, 0.0)
    _, events = _drive(plc, 10, t, WROT_PtAngValBl1=SPEC.blade_encoder_fault_deg, WROT_PtAngValBl3=9.0)
    assert {e.code for e in events if e.kind == "trip"} == {326, 337}, "葉片 2-3 差異只看有效的兩支編碼器"


def test_tripped_sensor_fault_holds_the_turbine_until_repaired() -> None:
    """跳機後維修鎖擋重啟；維護清除故障後讀值恢復、跳機解除、機組重新發電。"""
    sim = WindFarmSimulator(turbine_count=1)
    sim.wind_model.set_override(wind_speed=15.0, wind_direction=180.0, ambient_temp=25.0)
    model = sim.turbines["WT001"]
    i = 0
    for i in range(200):
        sim._run_one_step(T0 + timedelta(seconds=i * DT), DT)
    # 剛好到 SENSOR_BREAK_SEVERITY（>=）就斷線
    assert sim.fault_engine.inject("yaw_brake_pressure_sensor_fault", "WT001", severity_rate=0.0,
                                   initial_severity=0.5)
    events: List[PlcEvent] = []
    for i in range(i + 1, i + 120):
        sim._run_one_step(T0 + timedelta(seconds=i * DT), DT)
        events += model.plc.drain_events()
    fault = sim.fault_engine.active_faults[0]
    assert fault.tripped and fault.trip_code == 229 and model.maintenance_lock
    assert model.tur_state != PRODUCING
    sim.fault_engine.clear()
    for i in range(i + 1, i + 240):
        sim._run_one_step(T0 + timedelta(seconds=i * DT), DT)
        events += model.plc.drain_events()
    assert ("trip_cleared", 229) in [(e.kind, e.code) for e in events]
    assert model.tur_state == PRODUCING and not model.maintenance_lock
    reading = sim.latest_data["WT001"]["scada"]["WYAW_YwBrkHyPrs"]
    lo, hi = SPEC.yaw_pressure_valid_range_bar
    assert lo <= reading <= hi and reading != SPEC.yaw_pressure_broken_wire_bar, "修好後讀值回到正常範圍"


# ── 故障庫擴充的感測器故障（WMOM-20261021-08-c）──────────────────────────────────


def test_stuck_vane_does_not_reach_the_other_turbines_wake() -> None:
    """風場尾流模型的偏航輸入取風向標 1 讀值：卡住的風向標不能透過尾流改變下游機組（逐位元相同）。

    關掉 PLC：開著時 231 讓 WT001 停機，下游少了它的尾流是真的會變（那是跳機的後果，不是讀值外洩）。
    """
    def run(fault: bool) -> Tuple[List[Dict[str, Dict[str, float]]], float]:
        sim = WindFarmSimulator(turbine_count=6)
        for model in sim.turbines.values():
            model.plc.enabled = False
        sim.wind_model.set_override(wind_speed=10.0, wind_direction=270.0, ambient_temp=20.0)
        rows: List[Dict[str, Dict[str, float]]] = []
        for i in range(400):
            if fault and i == 150:
                assert sim.fault_engine.inject("wind_vane1_stuck", "WT001", severity_rate=0.0, initial_severity=0.6)
            sim._run_one_step(T0 + timedelta(seconds=i * DT), DT)
            rows.append({tid: dict(sim.latest_data[tid]["scada"]) for tid in sim.turbines if tid != "WT001"})
        return rows, float(sim.latest_data["WT001"]["scada"]["WYAW_YwVn1AlgnAvg5s"])

    healthy, healthy_vane = run(False)
    faulty, held_vane = run(True)
    assert held_vane != healthy_vane
    assert faulty == healthy


def test_held_vane_reading_follows_each_injection_and_reset() -> None:
    """卡住的讀值屬於那一次注入：修好再卡住、換一次注入、機組 reset 都從新的讀值起算。"""
    model = TurbinePhysicsModel(seed=3)
    model.plc.enabled = False

    def vane(steps: int, direction: float) -> float:
        out: Dict[str, float] = {}
        for _ in range(steps):
            out = model.step(wind_speed=10.0, wind_direction=direction, ambient_temp=20.0, dt=DT)
        return out["WYAW_YwVn1AlgnAvg5s"]

    vane(200, 180.0)
    model.active_faults = [{"scenario_id": "wind_vane1_stuck", "severity": 1.0, "instance_id": 1}]
    held = vane(1, 180.0)
    assert vane(30, 205.0) == held                      # 風向變了，讀值不動
    model.active_faults = []
    assert vane(1, 205.0) != held                       # 修好：讀值又跟著風向
    model.active_faults = [{"scenario_id": "wind_vane1_stuck", "severity": 1.0, "instance_id": 1}]
    again = vane(1, 205.0)
    assert again != held and vane(10, 170.0) == again   # 再卡住：停在新的值
    model.active_faults = [{"scenario_id": "wind_vane1_stuck", "severity": 1.0, "instance_id": 2}]
    assert vane(1, 170.0) != again                      # 換一次注入（同一步）就重取
    model.reset()
    assert model._held_sensor == {} and model._sensor_last_unfaulted == {}


def test_vane_sensor_noise_is_coarser_than_its_resolution_and_stuck_events_are_short() -> None:
    """風向標凍結判定（231 / 232）看 I/O 讀值：健康讀值靠量測雜訊每步都在變、卡值事件到不了 60 s。"""
    from simulator.physics import TurbinePhysicsModel as Model
    from simulator.physics.turbine_physics import _SENSOR_STUCK_S

    cfg = Model(seed=1)._get_sensor_config("WYAW_YwVn1AlgnAvg5s")
    assert cfg["noise"] >= 4 * cfg["resolution"]
    assert _SENSOR_STUCK_S[1] <= SPEC.vane_frozen_delay_s / 2


def test_pump_wear_with_out_of_range_severity_does_not_break_the_step() -> None:
    """API 沒擋嚴重度範圍：負的嚴重度不能讓冷卻水流量變成負數（** 0.8 → 複數）弄垮整個風場的模擬。"""
    model = TurbinePhysicsModel(seed=1)
    for severity in (-2.0, 3.0):
        model.active_faults = [{"scenario_id": "converter_cooling_pump_wear", "severity": severity}]
        out = model.step(wind_speed=12.0, wind_direction=180.0, ambient_temp=20.0, dt=DT)
        assert out["WCNV_IGCTWtrPres1"] >= 0.0
