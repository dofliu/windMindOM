"""誤報 / 健康負樣本（WMOM-20261021-08-b，EPIC-DS Phase 4-b）。

不是機組故障、卻會讓機組送警報 / 跳機的事件：

1. 風場事件（``simulator/farm_events.py``）：電網電壓驟降 → 全場 482 / 481 + 021；頻率越界 → 489 + 021；
   風向快速變化 → 偏航追不上而逾時 223。事件前的資料與沒有事件時逐位元相同，批次結束後電網 / 風向復原
2. 主軸承 Pt100 接觸不良（nuisance 情境）：偶爾瞬斷 → 242 跳機、接回後自動重啟，不鎖機組
3. 標準答案（``simulator/ground_truth.py``）把它們標成 nuisance case：風場事件每台有反應的機組一個、注入的
   nuisance 情境一個、其餘沒有故障的機組事件歸成環境性 case；``healthy_turbines`` 只看故障 case
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import pytest

import simulator.engine as engine_mod
from shared.alarm_codes import get_alarm
from simulator.bulk_events import BulkEvent
from simulator.engine import WindFarmSimulator
from simulator.farm_events import FARM_EVENT_KINDS, WIND_SWING_RAMP_S, FarmEvent
from simulator.ground_truth import NUISANCE_WINDOW_GRACE_S, GroundTruthRecorder
from simulator.physics.fault_engine import FAULT_SCENARIOS, ActiveFault
from simulator.physics.fault_engine import TestPlanStep as PlanStep  # 別名：避免 pytest 收集
from simulator.physics.plc_protection import PlcEvent

T0 = datetime(2026, 3, 1, tzinfo=timezone.utc)
LOOSE = "main_bearing_temp_loose_contact"


# ── 1. 風場事件 ───────────────────────────────────────────────────────────────


def test_wind_swing_ramps_in_and_out_and_stays_within_amplitude() -> None:
    swing = FarmEvent("rapid_wind_direction_change", offset_seconds=100.0, duration_s=900.0, magnitude=40.0)
    assert swing.wind_direction_offset(99.0) == 0.0 and swing.wind_direction_offset(1000.0) == 0.0
    assert swing.wind_direction_offset(100.0) == 0.0                     # 漸強從 0 開始
    offsets = [swing.wind_direction_offset(100.0 + t) for t in range(900)]
    assert max(abs(o) for o in offsets) <= 40.0 + 1e-9
    assert max(abs(o) for o in offsets) > 39.0
    assert abs(swing.wind_direction_offset(100.0 + 900.0 - 1.0)) < 40.0 / WIND_SWING_RAMP_S + 1e-9
    assert FarmEvent("grid_voltage_dip", 0.0, 10.0, 0.7).wind_direction_offset(5.0) == 0.0


def test_every_farm_event_kind_has_answer_texts_and_real_codes() -> None:
    for kind in FARM_EVENT_KINDS.values():
        assert kind.root_cause_zh and kind.root_cause_en and kind.expected_actions_zh and kind.expected_actions_en
        assert len(kind.expected_actions_zh) == len(kind.expected_actions_en)
        assert kind.origin in ("external_grid", "environmental")
        for code in kind.event_codes:
            get_alarm(code)  # 不在 Z72 警報目錄會 raise
        assert kind.magnitude_range[0] < kind.magnitude_range[1]


def _farm(monkeypatch: pytest.MonkeyPatch, turbines: int = 2) -> WindFarmSimulator:
    monkeypatch.setattr(engine_mod, "utc_now", lambda: T0)
    sim = WindFarmSimulator(turbine_count=turbines)
    sim.wind_model.set_override(wind_speed=13.0, wind_direction=250.0, ambient_temp=25.0)
    return sim


def _bulk(sim: WindFarmSimulator, hours: float, events: Optional[List[FarmEvent]] = None
          ) -> Tuple[List[dict], List[BulkEvent], List[Tuple[str, datetime, datetime]]]:
    rows: List[dict] = []
    observed: List[BulkEvent] = []
    started: List[Tuple[str, datetime, datetime]] = []
    sim.generate_bulk(hours, time_step=10.0, callback=rows.extend, on_events=observed.extend,
                      farm_events=events, on_farm_event=lambda e, s, en: started.append((e.kind, s, en)))
    return rows, observed, started


def _plc(observed: List[BulkEvent], kind: str = "trip") -> List[Tuple[str, int, float]]:
    return [(e.turbine_id, e.plc_event.code, (e.timestamp - T0).total_seconds())
            for e in observed if e.plc_event is not None and e.kind == kind]


def test_grid_voltage_dip_trips_every_producing_turbine_then_grid_is_restored(monkeypatch: pytest.MonkeyPatch) -> None:
    sim = _farm(monkeypatch)
    dip = FarmEvent("grid_voltage_dip", offset_seconds=1500.0, duration_s=20.0, magnitude=0.70)
    _, observed, started = _bulk(sim, 0.6, [dip])
    assert started == [("grid_voltage_dip", T0 + timedelta(seconds=1500), T0 + timedelta(seconds=1520))]
    trips = _plc(observed)
    for turbine in ("WT001", "WT002"):
        codes = {code for t, code, at in trips if t == turbine and 1500 <= at <= 1530}
        assert codes == {482, 21}, f"{turbine}: {trips}"
    assert {code for _, code, at in trips if at < 1500} == set()
    assert sim.grid_model.get_status()["mode"] == "auto" and sim._direction_offset_deg == 0.0


def test_grid_frequency_excursion_trips_on_frequency_out_of_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    sim = _farm(monkeypatch)
    _, observed, _ = _bulk(sim, 0.6, [FarmEvent("grid_frequency_excursion", 1500.0, 40.0, -1.8)])
    for turbine in ("WT001", "WT002"):
        assert {code for t, code, at in _plc(observed) if t == turbine} == {489, 21}


def _at(rows: List[dict], tag: str, start_s: float, end_s: float) -> List[float]:
    return [r["scada"][tag] for r in rows
            if start_s <= (datetime.fromisoformat(r["timestamp"]) - T0).total_seconds() < end_s]


def test_frequency_excursion_below_the_trip_only_derates(monkeypatch: pytest.MonkeyPatch) -> None:
    """+1 Hz（未達 489 的 1.4 Hz）：下垂降載、不跳機；降載少送的功率不算變頻器發熱（不再誤送 420，review S2）。"""
    sim = _farm(monkeypatch, turbines=1)
    rows, observed, _ = _bulk(sim, 0.6, [FarmEvent("grid_frequency_excursion", 1500.0, 60.0, 1.0)])
    assert [(e.kind, e.plc_event.code) for e in observed if e.plc_event is not None] == []
    assert min(_at(rows, "WCNV_FreqWattDerate", 1500, 1560)) < 0.8
    before = max(_at(rows, "WCNV_IGCTWtrTmp", 1200, 1500))
    assert max(_at(rows, "WCNV_IGCTWtrTmp", 1500, 2100)) < before + 2.0


@pytest.mark.parametrize("kind, magnitude", [
    ("grid_voltage_dip", 0.7), ("grid_frequency_excursion", 1.0), ("rapid_wind_direction_change", 60.0),
])
def test_farm_event_key_signals_deviate_during_the_event(monkeypatch: pytest.MonkeyPatch, kind: str,
                                                          magnitude: float) -> None:
    """標準答案列的 key signal 在事件期間明顯偏離事件前（風場事件版的 key signal 守門）。"""
    sim = _farm(monkeypatch, turbines=1)
    rows, _, _ = _bulk(sim, 0.6, [FarmEvent(kind, 1500.0, 300.0, magnitude)])
    for tag in FARM_EVENT_KINDS[kind].key_signals:
        before = _at(rows, tag, 900, 1500)
        during = _at(rows, tag, 1500, 1800)
        mean = sum(before) / len(before)
        spread = max(abs(v - mean) for v in before)
        assert max(abs(v - mean) for v in during) > max(3.0 * spread, 0.005 * max(abs(mean), 1.0)), tag


def test_data_before_a_farm_event_is_identical_to_a_run_without_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """事件只在進行中改變電網 / 風向；之前的資料逐位元相同（電網雜訊的亂數抽樣次數不變）。"""
    plain, _, _ = _bulk(_farm(monkeypatch), 0.5)
    with_event, _, _ = _bulk(_farm(monkeypatch), 0.5, [FarmEvent("grid_voltage_dip", 1200.0, 20.0, 0.70)])
    before = [r for r in plain if r["timestamp"] <= (T0 + timedelta(seconds=1200)).isoformat()]
    assert before and before == with_event[:len(before)]
    assert plain != with_event


def test_rapid_wind_direction_change_times_out_the_yaw(monkeypatch: pytest.MonkeyPatch) -> None:
    sim = _farm(monkeypatch)
    swing = FarmEvent("rapid_wind_direction_change", offset_seconds=1200.0, duration_s=1500.0, magnitude=60.0)
    _, observed, _ = _bulk(sim, 1.0, [swing])
    yaw_timeouts = [(t, at) for t, code, at in _plc(observed) if code == 223]
    assert yaw_timeouts and all(1200 <= at <= 2700 for _, at in yaw_timeouts), yaw_timeouts
    assert {code for _, code, _ in _plc(observed)} == {223}
    assert sim._direction_offset_deg == 0.0


def test_overlapping_dip_and_frequency_events_combine_and_restore_the_manual_override(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """電壓驟降與頻率越界重疊：兩個量各自覆寫；事件都結束後回到批次前的手動覆寫。"""
    sim = _farm(monkeypatch, turbines=1)
    sim.grid_model.set_override(voltage_v=sim.grid_model.base_voltage_v * 0.98)
    before = sim.grid_model.snapshot()
    events = [FarmEvent("grid_voltage_dip", 100.0, 100.0, 0.8), FarmEvent("grid_frequency_excursion", 150.0, 100.0, 0.5)]
    state = sim.grid_model.snapshot()
    overridden = sim._apply_farm_events(events, 175.0, T0, set(), state, False, None)
    status = sim.grid_model.get_status()
    assert overridden and status["profile"] == "farm_event"
    assert status["override_voltage_v"] == pytest.approx(sim.grid_model.base_voltage_v * 0.8)
    assert status["override_frequency_hz"] == pytest.approx(sim.grid_model.base_frequency_hz + 0.5)
    sim._apply_farm_events(events, 225.0, T0, set(), state, True, None)     # 只剩頻率：電壓回到批次前的值
    assert sim.grid_model.get_status()["override_voltage_v"] == before[1]
    assert not sim._apply_farm_events(events, 300.0, T0, set(), state, True, None)
    assert sim.grid_model.snapshot() == before


def test_farm_event_state_is_restored_when_the_batch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    sim = _farm(monkeypatch, turbines=1)
    before = sim.grid_model.snapshot()

    def boom(_rows: List[dict]) -> None:
        raise RuntimeError("store failed")

    with pytest.raises(RuntimeError):
        sim.generate_bulk(0.2, time_step=10.0, callback=boom, farm_events=[
            FarmEvent("grid_voltage_dip", 0.0, 600.0, 0.7), FarmEvent("rapid_wind_direction_change", 0.0, 600.0, 60.0)])
    assert sim.grid_model.snapshot() == before and sim._direction_offset_deg == 0.0


# ── 2. Pt100 接觸不良 ─────────────────────────────────────────────────────────


def _producing_sim(monkeypatch: pytest.MonkeyPatch) -> Tuple[WindFarmSimulator, int]:
    sim = _farm(monkeypatch, turbines=1)
    i = 0
    while sim.turbines["WT001"].tur_state != 6:
        sim._run_one_step(T0 + timedelta(seconds=i * 5.0), 5.0)
        i += 1
        assert i < 200
    return sim, i


def test_loose_contact_trips_242_and_restarts_without_maintenance_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    sim, i = _producing_sim(monkeypatch)
    model = sim.turbines["WT001"]
    model.plc.drain_events()
    assert sim.fault_engine.inject(LOOSE, "WT001", severity_rate=0.0, initial_severity=1.0)
    events: List[PlcEvent] = []
    states: List[int] = []
    for _ in range(int(1.5 * 3600 / 5.0)):
        sim._run_one_step(T0 + timedelta(seconds=i * 5.0), 5.0)
        events += model.plc.drain_events()
        states.append(model.tur_state)
        assert not model.maintenance_lock
        i += 1
    kinds = [(e.kind, e.code) for e in events]
    assert ("trip", 242) in kinds and ("trip_cleared", 242) in kinds
    first_trip = kinds.index(("trip", 242))
    assert 6 in states[first_trip + 1:], "接回後自動重啟回到發電"
    assert not sim.fault_engine.active_faults[0].tripped


def test_loose_contact_schedule_restarts_after_the_fault_is_cleared(monkeypatch: pytest.MonkeyPatch) -> None:
    """修好（清掉故障）再注入：第一次瞬斷照樣在注入後 5–20 分鐘，不沿用舊排程。"""
    sim, i = _producing_sim(monkeypatch)
    model = sim.turbines["WT001"]
    sim.fault_engine.inject(LOOSE, "WT001", severity_rate=0.0, initial_severity=1.0)
    for _ in range(int(3600 / 5.0)):
        sim._run_one_step(T0 + timedelta(seconds=i * 5.0), 5.0)
        i += 1
    sim.fault_engine.clear()
    sim._run_one_step(T0 + timedelta(seconds=i * 5.0), 5.0)
    i += 1
    assert model._contact_next_glitch is None
    model.cmd_reset()  # 一小時內反覆跳機可能已封鎖自動重啟（A039）：操作員復位
    for _ in range(300):
        sim._run_one_step(T0 + timedelta(seconds=i * 5.0), 5.0)
        i += 1
        if model.tur_state == 6:
            break
    assert model.tur_state == 6
    model.plc.drain_events()
    sim.fault_engine.inject(LOOSE, "WT001", severity_rate=0.0, initial_severity=1.0)
    for _ in range(int(290 / 5.0)):
        sim._run_one_step(T0 + timedelta(seconds=i * 5.0), 5.0)
        i += 1
    assert [(e.kind, e.code) for e in model.plc.drain_events() if e.code == 242] == []


# ── 3. 標準答案的 nuisance case ───────────────────────────────────────────────


def _ev(turbine: str, at_s: float, kind: str, code: int) -> BulkEvent:
    alarm = get_alarm(code)
    return BulkEvent(
        timestamp=T0 + timedelta(seconds=at_s), turbine_id=turbine, kind=kind,
        plc_event=PlcEvent(sim_time=at_s, kind=kind, code=code, level=alarm.level, text=alarm.text,
                           plc_tag=alarm.plc_tag, event_id=alarm.event_id),
    )


def _build(rec: GroundTruthRecorder, hours: float = 6.0, final: Optional[list] = None) -> Dict:
    return rec.build(scenario_id=1, scenario_name="負樣本", site_timezone="Asia/Taipei",
                     sim_start=T0.isoformat(), sim_end=(T0 + timedelta(hours=hours)).isoformat(),
                     final_faults=final or [])


def _farm_event(rec: GroundTruthRecorder, event: FarmEvent) -> None:
    start = T0 + timedelta(seconds=event.offset_seconds)
    rec.on_farm_event(event, start, start + timedelta(seconds=event.duration_s))


def _brief(gt: Dict) -> List[Tuple]:
    return [(c["case_id"], c["turbine_id"], c["category"], c["nuisance_cause"], c["observed_alarm_codes"],
             c["farm_event_id"]) for c in gt["cases"]]


def test_farm_event_gives_one_nuisance_case_per_reacting_turbine() -> None:
    rec = GroundTruthRecorder(["WT001", "WT002", "WT003"])
    _farm_event(rec, FarmEvent("grid_voltage_dip", 3600.0, 20.0, 0.7))
    rec.on_events([
        _ev("WT001", 3605, "trip", 482), _ev("WT001", 3605, "trip", 21),
        _ev("WT002", 3606, "trip", 482), _ev("WT002", 3606, "trip", 21),
        _ev("WT001", 3650, "trip_cleared", 482),
        _ev("WT002", 3700, "alarm_raised", 39),            # 跟在後面的自動重啟封鎖
        _ev("WT003", 3610, "alarm_raised", 420),           # 不是事件的碼，但在事件進行中：連帶
        _ev("WT003", 3620 + 900, "alarm_raised", 273),     # 事件結束 15 分鐘後、不是事件的碼：環境性
        _ev("WT001", 9000, "trip", 482),                   # 事件 + 寬限之後
    ])
    gt = _build(rec)
    assert _brief(gt) == [
        ("C001", "WT001", "nuisance", "grid_disturbance", [482, 21], "E01"),
        ("C002", "WT002", "nuisance", "grid_disturbance", [482, 21, 39], "E01"),
        ("C003", "WT003", "nuisance", "grid_disturbance", [420], "E01"),
        ("C004", "WT001", "nuisance", "environment", [482], None),
        ("C005", "WT003", "nuisance", "environment", [273], None),
    ]
    dip = gt["cases"][1]
    assert dip["fault_id"] == "grid_voltage_dip" and dip["component"] is None and dip["origin"] == "external_grid"
    assert (dip["first_alarm_code"], dip["trip_code"]) == (482, 482)
    assert dip["key_signals"] == list(FARM_EVENT_KINDS["grid_voltage_dip"].key_signals)
    assert [r["event_code"] for r in dip["manual_refs"]] == [482, 21, 39]
    end = T0 + timedelta(seconds=3700 + NUISANCE_WINDOW_GRACE_S)
    assert dip["window_end_ts"] == end.strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
    assert gt["farm_events"] == [{
        "event_id": "E01", "kind": "grid_voltage_dip", "name_zh": "電網電壓驟降", "name_en": "Grid voltage dip",
        "nuisance_cause": "grid_disturbance", "start_ts": "2026-03-01T01:00:00.000000+00:00",
        "end_ts": "2026-03-01T01:00:20.000000+00:00", "magnitude": 0.7,
        "magnitude_unit": FARM_EVENT_KINDS["grid_voltage_dip"].magnitude_unit, "case_ids": ["C001", "C002", "C003"],
    }]
    assert gt["unattributed_events"] == [] and gt["healthy_turbines"] == ["WT001", "WT002", "WT003"]


def test_farm_event_codes_on_a_faulty_turbine_go_to_the_farm_event_not_the_fault() -> None:
    """故障機組上的電網碼歸風場事件；故障開始後其他沒被認領的碼留在 unattributed（不當環境性）。"""
    rec = GroundTruthRecorder(["WT001", "WT002"])
    rec.on_fault_injected(PlanStep(600, "bearing_wear", "WT001", 0.001, 0.0), T0 + timedelta(seconds=600))
    _farm_event(rec, FarmEvent("grid_frequency_excursion", 3600.0, 40.0, -1.8))
    rec.on_events([
        _ev("WT001", 300, "trip", 223),                    # 故障前：環境性
        _ev("WT001", 1800, "alarm_raised", 264),           # 故障後、非預期碼：留在 unattributed
        _ev("WT001", 3610, "trip", 489), _ev("WT001", 3610, "trip", 21),
    ])
    gt = _build(rec, final=[ActiveFault(scenario_id="bearing_wear", turbine_id="WT001", severity=0.5)])
    assert _brief(gt) == [
        ("C001", "WT001", "real_fault", None, [], None),
        ("C002", "WT001", "nuisance", "grid_disturbance", [489, 21], "E01"),
        ("C003", "WT001", "nuisance", "environment", [223], None),
    ]
    env = gt["cases"][2]
    assert env["window_end_ts"] == "2026-03-01T00:10:00.000000+00:00", "環境性 case 的時間窗不跨進故障"
    assert [(e["code"]) for e in gt["unattributed_events"]] == [264]
    assert gt["healthy_turbines"] == ["WT002"]


def test_injected_nuisance_scenario_is_a_nuisance_case_and_claims_its_restart_block() -> None:
    rec = GroundTruthRecorder(["WT001", "WT002"])
    rec.on_fault_injected(PlanStep(600, LOOSE, "WT002", 0.001, 0.0), T0 + timedelta(seconds=600))
    rec.on_events([
        _ev("WT002", 1500, "trip", 242), _ev("WT002", 1525, "trip_cleared", 242),
        _ev("WT002", 3000, "trip", 242), _ev("WT002", 3020, "alarm_raised", 39),
    ])
    gt = _build(rec, final=[ActiveFault(scenario_id=LOOSE, turbine_id="WT002", severity=1.0)])
    case = gt["cases"][0]
    assert (case["category"], case["nuisance_cause"], case["component"]) == ("nuisance", "loose_contact", "main_bearing")
    assert (case["trip_code"], case["trip_ts"]) == (242, "2026-03-01T00:25:00.000000+00:00")
    assert case["observed_alarm_codes"] == [242] and case["other_observed_codes"] == [39]
    assert case["window_end_ts"] is None and len(gt["cases"]) == 1
    assert gt["unattributed_events"] == []
    assert gt["healthy_turbines"] == ["WT001", "WT002"], "nuisance 不算故障"


def test_nuisance_windows_never_extend_past_the_scenario_end() -> None:
    rec = GroundTruthRecorder(["WT001"])
    _farm_event(rec, FarmEvent("rapid_wind_direction_change", 5.2 * 3600, 1500.0, 60.0))
    rec.on_events([_ev("WT001", 5.6 * 3600, "trip", 223), _ev("WT001", 5.9 * 3600, "info", 201)])
    gt = _build(rec, hours=6.0)
    assert [(c["nuisance_cause"], c["window_end_ts"]) for c in gt["cases"]] == [
        ("wind_direction_change", "2026-03-01T06:00:00.000000+00:00"),
        ("environment", "2026-03-01T06:00:00.000000+00:00"),
    ]


def test_each_of_two_dips_within_an_hour_gets_its_own_cases() -> None:
    """同種風場事件相隔不到寬限：後面的事件碼歸給後開始的事件，A039 跟著它前一次跳機（review S1 / S6）。"""
    rec = GroundTruthRecorder(["WT001"])
    _farm_event(rec, FarmEvent("grid_voltage_dip", 1200.0, 30.0, 0.7))
    rec.on_events([_ev("WT001", 1205, "trip", 482), _ev("WT001", 1205, "trip", 21)])
    _farm_event(rec, FarmEvent("grid_voltage_dip", 2400.0, 30.0, 0.7))
    rec.on_events([_ev("WT001", 2405, "trip", 482), _ev("WT001", 2405, "trip", 21),
                   _ev("WT001", 2425, "alarm_raised", 39)])
    gt = _build(rec)
    assert _brief(gt) == [
        ("C001", "WT001", "nuisance", "grid_disturbance", [482, 21], "E01"),
        ("C002", "WT001", "nuisance", "grid_disturbance", [482, 21, 39], "E02"),
    ]
    assert [e["case_ids"] for e in gt["farm_events"]] == [["C001"], ["C002"]]


def test_restart_block_follows_the_trip_right_before_it() -> None:
    """Pt100 鬆線的機組遇到電壓驟降：電網跳機之後的 A039 歸電網事件，不歸鬆線（review S6）。"""
    rec = GroundTruthRecorder(["WT001"])
    rec.on_fault_injected(PlanStep(0, LOOSE, "WT001", 0.001, 0.0), T0)
    rec.on_events([_ev("WT001", 600, "trip", 242), _ev("WT001", 625, "trip_cleared", 242)])
    _farm_event(rec, FarmEvent("grid_voltage_dip", 1800.0, 30.0, 0.7))
    rec.on_events([_ev("WT001", 1805, "trip", 482), _ev("WT001", 1805, "trip", 21),
                   _ev("WT001", 1830, "alarm_raised", 39)])
    gt = _build(rec, final=[ActiveFault(scenario_id=LOOSE, turbine_id="WT001", severity=1.0)])
    loose, dip = gt["cases"]
    assert loose["nuisance_cause"] == "loose_contact" and loose["observed_alarm_codes"] == [242]
    assert dip["observed_alarm_codes"] == [482, 21, 39]


def test_farm_event_codes_are_not_claimed_by_a_fault_expecting_them() -> None:
    """converter_cooling_fault 預期 021：電壓驟降時的 021 歸風場事件，不當成故障的第一個警報（review S2）。"""
    rec = GroundTruthRecorder(["WT001"])
    rec.on_fault_injected(PlanStep(0, "converter_cooling_fault", "WT001", 0.001, 0.0), T0)
    _farm_event(rec, FarmEvent("grid_voltage_dip", 1800.0, 30.0, 0.7))
    rec.on_events([_ev("WT001", 1805, "trip", 482), _ev("WT001", 1805, "trip", 21)])
    fault, dip = _build(rec, final=[ActiveFault(scenario_id="converter_cooling_fault", turbine_id="WT001",
                                                severity=0.5)])["cases"]
    assert 21 in [a["code"] for a in FAULT_SCENARIOS["converter_cooling_fault"].alarm_codes]
    assert fault["first_alarm_ts"] is None and fault["observed_alarm_codes"] == []
    assert dip["observed_alarm_codes"] == [482, 21]


def test_build_can_be_called_twice() -> None:
    rec = GroundTruthRecorder(["WT001"])
    _farm_event(rec, FarmEvent("grid_voltage_dip", 600.0, 20.0, 0.7))
    rec.on_events([_ev("WT001", 605, "trip", 482), _ev("WT001", 3 * 3600, "info", 201)])
    first, second = _build(rec), _build(rec)
    assert _brief(first) == _brief(second) and len(first["cases"]) == 2


def test_vocabulary_lists_every_nuisance_cause() -> None:
    import json
    vocab = json.loads((PROJECT_ROOT / "shared" / "data" / "rag_assistant_vocabulary.json").read_text(encoding="utf-8"))
    causes = {c["id"] for c in vocab["nuisance_causes"]}
    used = {k.nuisance_cause for k in FARM_EVENT_KINDS.values()} | {"environment"}
    used |= {sc.nuisance_cause for sc in FAULT_SCENARIOS.values() if sc.category == "nuisance"}
    assert used <= causes and None not in used
    for sc in FAULT_SCENARIOS.values():
        assert (sc.nuisance_cause is None) == (sc.category != "nuisance"), sc.id


def test_pack_answer_key_uses_z_timestamps_for_nuisance_windows_and_farm_events() -> None:
    from server import scenario_pack as sp

    rec = GroundTruthRecorder(["WT001"])
    _farm_event(rec, FarmEvent("grid_voltage_dip", 600.0, 20.0, 0.7))
    rec.on_events([_ev("WT001", 605, "trip", 482)])
    out = sp.ground_truth_for_pack(_build(rec), "z72-test")
    assert out["cases"][0]["window_end_ts"] == "2026-03-01T00:40:20.000000Z"  # 事件結束 + 30 分鐘
    assert (out["farm_events"][0]["start_ts"], out["farm_events"][0]["end_ts"]) == (
        "2026-03-01T00:10:00.000000Z", "2026-03-01T00:10:20.000000Z")
    # 1.5 以前存的答案沒有 window_end_ts：不補欄位
    legacy = sp.ground_truth_for_pack({"contract_version": "1.4", "cases": [{"onset_ts": None}]}, "z72-old")
    assert "window_end_ts" not in legacy["cases"][0]
