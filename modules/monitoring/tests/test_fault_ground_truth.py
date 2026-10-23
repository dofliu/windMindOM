"""故障情境的標準答案 metadata 與紀錄器（WMOM-20261021-04，EPIC-DS Phase 2）。

1. 每個故障情境都有完整的答案欄位（元件、根因、類別、難度、可觀測訊號、建議處置），值域合法
2. 手冊條目與 Z72 警報目錄一致；Z72 手冊只寫「See [ABB]」的事件要標出來
3. ``GroundTruthRecorder`` 依注入 / 事件 / 跳機組出 case（onset、首次警報、跳機、預期碼歸屬）
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
for _p in (PROJECT_ROOT, MONITORING_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

from shared.alarm_codes import get_alarm  # noqa: E402
from simulator.bulk_events import STATE_CHANGE, BulkEvent  # noqa: E402
from simulator.ground_truth import (  # noqa: E402
    CONTRACT_VERSION,
    GroundTruthRecorder,
    manual_coverage,
    manual_refs,
    scenario_answer,
)
from simulator.physics.fault_engine import FAULT_SCENARIOS, ActiveFault  # noqa: E402
from simulator.physics.fault_engine import TestPlanStep as PlanStep  # noqa: E402  (別名：避免 pytest 當成測試類別收集)
from simulator.physics.plc_protection import PlcEvent  # noqa: E402
from simulator.physics.scada_registry import SCADA_REGISTRY  # noqa: E402

T0 = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
SCENARIO_IDS = sorted(FAULT_SCENARIOS)


# ── 1. 答案欄位完整、值域合法 ─────────────────────────────────────────────────


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_every_scenario_has_complete_answer_metadata(scenario_id: str) -> None:
    sc = FAULT_SCENARIOS[scenario_id]
    assert re.fullmatch(r"[a-z][a-z0-9_]*", sc.component), sc.component
    assert sc.root_cause_zh.strip() and sc.root_cause_en.strip()
    assert sc.category in ("real_fault", "sensor_fault", "nuisance", "healthy")
    assert sc.origin in ("internal", "environmental", "external_grid")
    assert sc.difficulty in ("easy", "medium", "hard")
    assert sc.expected_actions_zh and len(sc.expected_actions_zh) == len(sc.expected_actions_en)
    assert all(a.strip() for a in sc.expected_actions_zh + sc.expected_actions_en)
    assert sc.key_signals, "至少要有一個看得到故障的 SCADA tag"
    unknown = [t for t in sc.key_signals if t not in SCADA_REGISTRY]
    assert not unknown, f"key_signals 不在 SCADA tag 註冊表：{unknown}"
    # 至少一條處置出自手冊 Appendix C（標「（手冊）」/「manual」），中英對齊
    assert [("手冊" in zh) for zh in sc.expected_actions_zh] == [("manual" in en) for en in sc.expected_actions_en]
    assert any("手冊" in zh for zh in sc.expected_actions_zh)
    # 模擬與真實的差異只寫在 simulation_notes，根因不放模擬器說明
    assert len(sc.simulation_notes_zh) == len(sc.simulation_notes_en)
    assert all(n.strip() for n in sc.simulation_notes_zh + sc.simulation_notes_en)
    assert "模擬" not in sc.root_cause_zh and "simulat" not in sc.root_cause_en.lower()


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_expected_alarm_sequence_lists_alarms_before_trips(scenario_id: str) -> None:
    levels = [a["type"] for a in FAULT_SCENARIOS[scenario_id].alarm_codes]
    first_trip = next((i for i, lv in enumerate(levels) if lv in ("T1", "T2")), len(levels))
    assert all(lv == "A" for lv in levels[:first_trip]) and "A" not in levels[first_trip:], levels


def test_sensor_and_external_categories_match_the_physics() -> None:
    assert FAULT_SCENARIOS["yaw_sensor_drift"].category == "sensor_fault"
    assert FAULT_SCENARIOS["blade_icing"].origin == "environmental"
    assert FAULT_SCENARIOS["grid_voltage_sag"].origin == "external_grid"
    sensor = {sid for sid, sc in FAULT_SCENARIOS.items() if sc.category == "sensor_fault"}
    assert sensor == {"yaw_sensor_drift", "main_bearing_temp_sensor_drift", "stator_temp_sensor_drift",
                      "main_bearing_temp_sensor_wire_break", "blade1_pitch_encoder_fault",
                      "yaw_brake_pressure_sensor_fault",
                      "rotor_speed_sensor_fault", "anemometer_fault", "wind_vane1_stuck"}
    # 感測器故障與真故障同元件、不同類別（WMOM-20261021-08-a）：只看警報碼猜不出類別。量測儀器本身就是元件的
    # （風向標、風速計、轉速編碼器，WMOM-20261021-08-c）沒有對應的真故障
    real = {sc.component for sc in FAULT_SCENARIOS.values() if sc.category == "real_fault"}
    assert {"main_bearing", "generator_stator", "pitch_system_blade_1", "yaw_brake_hydraulics"} <= real
    instruments = {"wind_vane_1", "nacelle_anemometer", "rotor_speed_sensor"}
    assert {FAULT_SCENARIOS[s].component for s in sensor} - instruments <= real


# ── 2. 手冊條目 ───────────────────────────────────────────────────────────────


def test_manual_refs_follow_the_alarm_catalog() -> None:
    (ref,) = manual_refs([262])
    alarm = get_alarm(262)
    assert ref == {
        "doc": "Z72 User Manual", "section": "Appendix C", "event_code": 262, "event_id": "A_262",
        "level": "A", "text": alarm.text, "page": alarm.manual_page, "cause": alarm.cause,
        "rectification": alarm.rectification, "see_abb": False,
    }


def test_abb_only_events_are_flagged() -> None:
    by_code = {r["event_code"]: r for r in manual_refs([420, 437, 21, 262])}
    assert by_code[420]["see_abb"] and by_code[437]["see_abb"]
    assert by_code[21]["see_abb"], "021 的處置寫 See [ABB]（要配合 400-700 的變頻器跳機查）"
    assert not by_code[262]["see_abb"]
    assert manual_coverage(manual_refs([420, 437])) == "abb_manual"
    assert manual_coverage(manual_refs([262, 240])) == "z72_manual"
    assert manual_coverage(manual_refs([262, 437])) == "mixed"
    assert scenario_answer(FAULT_SCENARIOS["converter_cooling_fault"])["manual_coverage"] == "abb_manual"
    assert scenario_answer(FAULT_SCENARIOS["bearing_wear"])["manual_coverage"] == "z72_manual"


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_scenario_answer_lists_every_expected_code(scenario_id: str) -> None:
    sc = FAULT_SCENARIOS[scenario_id]
    answer = scenario_answer(sc)
    codes = [a["code"] for a in sc.alarm_codes]
    assert answer["expected_alarm_codes"] == codes
    assert [r["event_code"] for r in answer["manual_refs"]] == codes
    assert [s["level"] for s in answer["expected_alarm_sequence"]] == [a["type"] for a in sc.alarm_codes]
    assert answer["root_cause"] == sc.root_cause_zh and answer["fault_id"] == scenario_id


# ── 3. 紀錄器 ─────────────────────────────────────────────────────────────────


def _plc(turbine: str, at_s: float, kind: str, code: int) -> BulkEvent:
    alarm = get_alarm(code)
    return BulkEvent(
        timestamp=T0 + timedelta(seconds=at_s), turbine_id=turbine, kind=kind,
        plc_event=PlcEvent(sim_time=at_s, kind=kind, code=code, level=alarm.level, text=alarm.text,
                           plc_tag=alarm.plc_tag, event_id=alarm.event_id),
    )


def _inject(rec: GroundTruthRecorder, turbine: str, scenario: str, at_s: float,
            rate: float = 0.001, initial: float = 0.0) -> None:
    rec.on_fault_injected(PlanStep(at_s, scenario, turbine, rate, initial), T0 + timedelta(seconds=at_s))


def _case(gt: dict, case_id: str) -> dict:
    return next(c for c in gt["cases"] if c["case_id"] == case_id)


def _build(rec: GroundTruthRecorder, final: Optional[list] = None) -> dict:
    return rec.build(scenario_id=7, scenario_name="考題", site_timezone="Asia/Taipei",
                     sim_start="2026-03-01T00:00:00.000000+00:00",
                     sim_end="2026-03-01T06:00:00.000000+00:00", final_faults=final or [])


def test_recorder_builds_case_with_onset_first_alarm_and_trip() -> None:
    rec = GroundTruthRecorder(["WT001", "WT002", "WT003"])
    _inject(rec, "WT001", "bearing_wear", 600)
    rec.on_events([
        _plc("WT001", 100, "alarm_raised", 262),        # 注入前：不算
        _plc("WT002", 900, "alarm_raised", 262),        # 別台：不算
        _plc("WT001", 1800, "alarm_raised", 262),
        _plc("WT001", 1900, "alarm_cleared", 262),      # 解除不算首次警報
        _plc("WT001", 2400, "alarm_raised", 264),       # 非預期碼 → other
        _plc("WT001", 3000, "trip", 240),
        BulkEvent(timestamp=T0 + timedelta(seconds=3000), turbine_id="WT001", kind=STATE_CHANGE,
                  from_state=6, to_state=9, shutdown_cause="plc:240"),
    ])
    rec.on_fault_tripped("WT001", "bearing_wear", 240, T0 + timedelta(seconds=3000))
    final = [ActiveFault(scenario_id="bearing_wear", turbine_id="WT001", severity=0.987654)]
    gt = _build(rec, final)

    assert gt["contract_version"] == CONTRACT_VERSION and gt["kind"] == "scenario_ground_truth"
    assert gt["scenario_id"] == 7 and gt["site_timezone"] == "Asia/Taipei"
    assert gt["healthy_turbines"] == ["WT002", "WT003"]
    case = _case(gt, "C001")
    assert case["turbine_id"] == "WT001" and case["fault_id"] == "bearing_wear"
    assert case["component"] == "main_bearing" and case["category"] == "real_fault"
    assert case["onset_ts"] == "2026-03-01T00:10:00.000000+00:00"
    assert (case["first_alarm_ts"], case["first_alarm_code"]) == ("2026-03-01T00:30:00.000000+00:00", 262)
    assert (case["trip_ts"], case["trip_code"]) == ("2026-03-01T00:50:00.000000+00:00", 240)
    assert case["observed_alarm_codes"] == [262, 240]
    assert case["other_observed_codes"] == [264]
    assert case["expected_alarm_codes"] == [262, 240]
    assert case["injection"] == {"offset_seconds": 600.0, "severity_rate": 0.001, "initial_severity": 0.0}
    assert case["final_severity"] == 0.9877 and case["superseded"] is False and case["pre_existing"] is False
    assert case["nuisance_cause"] is None and case["window_end_ts"] is None and case["farm_event_id"] is None
    # 沒有故障時的事件歸成環境性 nuisance case（v1.5）：注入前的 262、別台的 262；故障連帶的 264 不歸
    env = [c for c in gt["cases"] if c["category"] == "nuisance"]
    assert [(c["case_id"], c["turbine_id"], c["observed_alarm_codes"], c["onset_ts"][11:19], c["window_end_ts"][11:19])
            for c in env] == [("C002", "WT001", [262], "00:01:40", "00:10:00"),
                              ("C003", "WT002", [262], "00:15:00", "00:45:00")]
    assert all(c["nuisance_cause"] == "environment" and c["component"] is None for c in env)
    # 沒有任何 case 解釋的事件：只剩連帶的 264（解除不列）
    assert [(e["turbine_id"], e["code"], e["ts"][11:19]) for e in gt["unattributed_events"]] == [
        ("WT001", 264, "00:40:00"),
    ]


def test_fault_without_alarm_before_trip_has_first_alarm_at_trip() -> None:
    """pitch_imbalance 跳機前沒有任何警報（設計文件 §6.1 限制 2）：首次警報＝跳機。"""
    rec = GroundTruthRecorder(["WT001"])
    _inject(rec, "WT001", "pitch_imbalance", 0)
    rec.on_events([_plc("WT001", 5000, "trip", 335), _plc("WT001", 5000, "trip", 336)])
    rec.on_fault_tripped("WT001", "pitch_imbalance", 335, T0 + timedelta(seconds=5000))
    case = _case(_build(rec), "C001")
    assert case["first_alarm_ts"] == case["trip_ts"] and case["first_alarm_code"] == 335
    assert case["observed_alarm_codes"] == [335, 336]


def test_fault_that_never_alarms_keeps_nulls() -> None:
    rec = GroundTruthRecorder(["WT001"])
    _inject(rec, "WT001", "stator_winding_degradation", 0)
    case = _case(_build(rec), "C001")
    assert case["first_alarm_ts"] is None and case["trip_ts"] is None and case["trip_code"] is None
    assert case["observed_alarm_codes"] == [] and case["final_severity"] == 0.0


def test_events_are_attributed_to_every_matching_fault_on_the_turbine() -> None:
    """同機組兩個故障：預期碼歸各自的 case；021 兩者都預期時兩邊都記。"""
    rec = GroundTruthRecorder(["WT001"])
    _inject(rec, "WT001", "converter_cooling_fault", 0)
    _inject(rec, "WT001", "grid_voltage_sag", 0)
    rec.on_events([_plc("WT001", 100, "alarm_raised", 420), _plc("WT001", 200, "trip", 21)])
    gt = _build(rec)
    cooling, grid = _case(gt, "C001"), _case(gt, "C002")
    assert cooling["observed_alarm_codes"] == [420, 21] and cooling["first_alarm_code"] == 420
    assert grid["observed_alarm_codes"] == [21] and grid["other_observed_codes"] == [420]


def test_reinjection_supersedes_the_previous_case() -> None:
    rec = GroundTruthRecorder(["WT001"])
    _inject(rec, "WT001", "bearing_wear", 0)
    _inject(rec, "WT001", "bearing_wear", 3600)
    rec.on_events([_plc("WT001", 4000, "alarm_raised", 262)])
    rec.on_fault_tripped("WT001", "bearing_wear", 240, T0 + timedelta(seconds=5000))
    gt = _build(rec, [ActiveFault(scenario_id="bearing_wear", turbine_id="WT001", severity=0.5)])
    first, second = _case(gt, "C001"), _case(gt, "C002")
    assert first["superseded"] is True and first["final_severity"] is None
    assert first["first_alarm_ts"] is None and first["trip_ts"] is None
    assert second["first_alarm_code"] == 262 and second["trip_code"] == 240
    assert second["final_severity"] == 0.5


def test_unknown_scenario_injection_is_ignored() -> None:
    rec = GroundTruthRecorder(["WT001"])
    _inject(rec, "WT001", "not_a_fault", 0)
    gt = _build(rec)
    assert gt["cases"] == [] and gt["healthy_turbines"] == ["WT001"]


def test_info_events_and_healthy_turbine_trips_become_environment_cases() -> None:
    """健康機組的偶發跳機、切出風速 I201：答案卷要說得出「這筆不是故障」（v1.5：環境性 nuisance case）。"""
    rec = GroundTruthRecorder(["WT001", "WT002"])
    rec.on_events([_plc("WT002", 100, "trip", 336), _plc("WT002", 110, "trip_cleared", 336),
                   _plc("WT001", 200, "info", 201), _plc("WT001", 300, "operator_reset", 8)])
    gt = _build(rec)
    assert gt["unattributed_events"] == []
    assert [(c["turbine_id"], c["category"], c["nuisance_cause"], c["observed_alarm_codes"], c["first_alarm_code"],
             c["trip_code"]) for c in gt["cases"]] == [
        ("WT001", "nuisance", "environment", [201], None, None),     # I 類：沒有警報 / 跳機
        ("WT002", "nuisance", "environment", [336], 336, 336),
    ]
    storm = gt["cases"][0]
    assert "切出風速" in storm["root_cause"] and storm["key_signals"] == ["WMET_WSpeedNac"]
    assert storm["manual_refs"][0]["event_code"] == 201 and storm["origin"] == "environmental"
    assert gt["healthy_turbines"] == ["WT001", "WT002"]


@pytest.mark.parametrize("kind, code", [
    ("alarm_cleared", 262), ("trip_cleared", 240), ("restart_blocked", 240), ("info", 201),
])
def test_only_raised_alarms_and_trips_count_for_a_case(kind: str, code: int) -> None:
    rec = GroundTruthRecorder(["WT001"])
    _inject(rec, "WT001", "bearing_wear", 0)
    rec.on_events([_plc("WT001", 100, kind, code)])
    case = _case(_build(rec), "C001")
    assert case["first_alarm_ts"] is None and case["observed_alarm_codes"] == []
    assert case["other_observed_codes"] == []


def test_event_at_the_onset_instant_belongs_to_the_case() -> None:
    rec = GroundTruthRecorder(["WT001"])
    _inject(rec, "WT001", "bearing_wear", 600)
    rec.on_events([_plc("WT001", 600, "alarm_raised", 262)])
    assert _case(_build(rec), "C001")["first_alarm_code"] == 262


def test_trip_is_credited_to_the_matching_fault_only_once() -> None:
    rec = GroundTruthRecorder(["WT001"])
    _inject(rec, "WT001", "converter_cooling_fault", 0)
    _inject(rec, "WT001", "grid_voltage_sag", 0)
    rec.on_fault_tripped("WT001", "grid_voltage_sag", 481, T0 + timedelta(seconds=100))
    rec.on_fault_tripped("WT001", "grid_voltage_sag", 21, T0 + timedelta(seconds=200))
    gt = _build(rec)
    assert _case(gt, "C001")["trip_ts"] is None
    assert (_case(gt, "C002")["trip_code"], _case(gt, "C002")["trip_ts"]) == (481, "2026-03-01T00:01:40.000000+00:00")


def test_faults_present_at_the_end_without_an_injection_become_pre_existing_cases() -> None:
    """生成前就殘留的故障不能被靜默略過：列成 onset 未知的 case，機組不算健康。"""
    rec = GroundTruthRecorder(["WT001", "WT002"])
    leftover = ActiveFault(scenario_id="bearing_wear", turbine_id="WT001", severity=1.0, tripped=True, trip_code=240)
    gt = _build(rec, [leftover])
    (case,) = gt["cases"]
    assert case["pre_existing"] is True and case["onset_ts"] is None and case["injection"] is None
    assert (case["fault_id"], case["trip_code"], case["final_severity"]) == ("bearing_wear", 240, 1.0)
    assert gt["healthy_turbines"] == ["WT002"]


def test_answer_carries_simulation_notes() -> None:
    answer = scenario_answer(FAULT_SCENARIOS["generator_overspeed"])
    assert answer["simulation_notes"] and answer["simulation_notes_en"]
    assert "320" in answer["simulation_notes"][0]


def test_live_residue_does_not_leak_into_a_clean_scenario() -> None:
    """Live 已跳機鎖存的機組：情境開頭不得出現沒有對應 trip 的 trip_cleared / operator_reset（答案寫健康）。"""
    from simulator.engine import WindFarmSimulator

    sim = WindFarmSimulator(turbine_count=2)
    sim.wind_model.set_override(wind_speed=15.0, wind_direction=180.0, ambient_temp=25.0)
    sim.fault_engine.inject("blade1_pitch_encoder_fault", "WT001", severity_rate=0.002, initial_severity=0.0)
    for i in range(1200):
        sim._run_one_step(T0 + timedelta(seconds=5.0 * i), 5.0)
    model = sim.turbines["WT001"]
    assert model.maintenance_lock and model.plc.active_codes(), "前提：Live 留下鎖存的跳機與維護鎖"
    for m in sim.turbines.values():
        m.plc.drain_events()

    assert sim.start_clean_scenario() == ["WT001"], "只重設帶殘留狀態的機組"
    recorder = GroundTruthRecorder(list(sim.turbines))
    events: list = []

    def on_events(batch: list) -> None:
        events.extend(batch)
        recorder.on_events(batch)

    sim.generate_bulk(1.0, time_step=10.0, on_events=on_events)
    plc = [(e.turbine_id, e.kind) for e in events if e.plc_event is not None and e.kind != "info"]
    assert plc == [], f"乾淨情境不該有 PLC 事件：{plc}"
    answer = recorder.build(scenario_id=1, scenario_name="x", site_timezone="Asia/Taipei", sim_start=None, sim_end=None)
    assert answer["cases"] == [] and answer["healthy_turbines"] == ["WT001", "WT002"]
    assert model.tur_state == 6, "重設後照常起動發電"


def test_clean_scenario_starts_with_empty_hourly_trip_counts() -> None:
    """Live 一小時內自動恢復過的跳機（例：320 硬體超速，每小時上限 1）不能讓情境的第一次同碼跳機就送 A039。"""
    from simulator.engine import WindFarmSimulator

    sim = WindFarmSimulator(turbine_count=1)
    plc = sim.turbines["WT001"].plc
    assert plc.note_protection_stop("overspeed_hardware", 100.0) == [320]
    plc.on_restart(160.0)
    plc.drain_events()
    assert plc.active_codes() == {}, "前提：Live 的跳機已自動恢復，沒有殘留狀態"

    assert sim.start_clean_scenario() == [], "乾淨的機組不重設（不動 RNG）"
    assert plc.note_protection_stop("overspeed_hardware", 400.0) == [320]
    assert [(e.kind, e.code) for e in plc.drain_events()] == [("trip", 320)]
    assert not plc.auto_restart_blocked
