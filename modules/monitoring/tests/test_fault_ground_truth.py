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


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_expected_alarm_sequence_lists_alarms_before_trips(scenario_id: str) -> None:
    levels = [a["type"] for a in FAULT_SCENARIOS[scenario_id].alarm_codes]
    first_trip = next((i for i, lv in enumerate(levels) if lv in ("T1", "T2")), len(levels))
    assert all(lv == "A" for lv in levels[:first_trip]) and "A" not in levels[first_trip:], levels


def test_sensor_and_external_categories_match_the_physics() -> None:
    assert FAULT_SCENARIOS["yaw_sensor_drift"].category == "sensor_fault"
    assert FAULT_SCENARIOS["blade_icing"].origin == "environmental"
    assert FAULT_SCENARIOS["grid_voltage_sag"].origin == "external_grid"
    others = {sid for sid, sc in FAULT_SCENARIOS.items() if sc.category == "sensor_fault"}
    assert others == {"yaw_sensor_drift"}


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
    assert case["final_severity"] == 0.9877 and case["superseded"] is False


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
