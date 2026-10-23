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
from simulator.physics.turbine_physics import TurbineSpec  # noqa: E402

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
