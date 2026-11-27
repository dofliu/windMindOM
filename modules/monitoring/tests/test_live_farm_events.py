"""即時模擬的風場事件（WMOM-20261126-07，DEC-20261127-10）。

1. 產生器：關著不抽樣；每次檢查每種事件固定抽三個數；同一種事件進行中不重複；設定要檢查；跟著存檔。
2. 引擎：只在即時模擬套用；沒有事件時讀值逐位元不變；電網 / 風向在事件期間覆寫、結束後復原；批次不帶 Live 的事件。
3. 運維：電壓驟降讓機組跳機；不對外的故障紀錄記成 nuisance、記錄期間過後結束（不算維修）；跳機開的工單
   答案標出風場事件、準備卡的「同場同時同碼」看得到其他機組。
4. 端點：只給永遠強制登入的主管；設定存在風場 DB。
"""

from __future__ import annotations

import asyncio
import pickle
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, List

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from modules.workflow import hooks
from modules.workflow.repository import work_order_repository as wo_repo
from server.routers import operations as ops
from simulator.engine import WindFarmSimulator
from simulator.farm_event_generator import (
    RECORD_GRACE_S,
    FarmEventGenerator,
    FarmEventGeneratorConfig,
    LiveFarmEvent,
)
from simulator.farm_events import FARM_EVENT_KINDS

from .test_om_loop import FARM, Farm

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def farm(tmp_path) -> Iterator[Farm]:
    f = Farm(tmp_path, turbines=3)
    try:
        yield f
    finally:
        hooks.clear_work_order_listeners()
        wo_repo.clear_engine_cache_for_test()


def _config(**kinds: float) -> FarmEventGeneratorConfig:
    """開著；``kinds`` 給各種事件的 mean_days_between（沒給的用預設）。"""
    return FarmEventGeneratorConfig.from_dict(
        {"enabled": True, "kinds": {k: {"mean_days_between": v} for k, v in kinds.items()}})


def _checks(generator: FarmEventGenerator, count: int, start: datetime = T0) -> List[LiveFarmEvent]:
    """只推進產生器：每次檢查一分鐘，事件一開始就算結束（不擋下一次）。"""
    out: List[LiveFarmEvent] = []
    for index in range(count):
        now = start + timedelta(minutes=index)
        out.extend(generator.step(60.0, now))
        generator.events.clear()
    return out


# ── 1. 產生器 ─────────────────────────────────────────────────────────────


def test_disabled_generator_draws_nothing() -> None:
    generator = FarmEventGenerator()
    assert generator.config.enabled is False, "預設關"
    before = generator._rng.getstate()
    assert _checks(generator, 500) == [] and generator._rng.getstate() == before


def test_three_draws_per_kind_per_check_whatever_happens() -> None:
    busy = FarmEventGenerator(_config(grid_voltage_dip=0.01, grid_frequency_excursion=0.01,
                                      rapid_wind_direction_change=0.01))
    quiet = FarmEventGenerator(FarmEventGeneratorConfig.from_dict({"enabled": True, "kinds": {
        k: {"mean_days_between": None} for k in FARM_EVENT_KINDS}}))
    made = _checks(busy, 300)
    assert made and _checks(quiet, 300) == []
    assert busy._rng.getstate() == quiet._rng.getstate(), "每次檢查每種事件固定抽三個數"
    assert {e.kind for e in made} == set(FARM_EVENT_KINDS)
    for event in made:
        cfg = busy.config.kinds[event.kind]
        size = abs(event.magnitude) if event.kind == "grid_frequency_excursion" else event.magnitude
        assert cfg.magnitude_min <= size <= cfg.magnitude_max
        assert cfg.duration_min_s <= event.duration_s <= cfg.duration_max_s
    shifts = [e.magnitude for e in made if e.kind == "grid_frequency_excursion"]
    assert min(shifts) < 0 < max(shifts), "頻率越界有往下也有往上"


def test_the_same_kind_does_not_start_again_while_it_runs_or_is_being_recorded() -> None:
    generator = FarmEventGenerator(_config(grid_voltage_dip=0.0001))
    first = generator.step(60.0, T0)
    dips = [e for e in first if e.kind == "grid_voltage_dip"]
    assert dips, "發生率很高：第一次檢查就有"

    def dips_at(moment: datetime) -> List[LiveFarmEvent]:
        return [e for e in generator.step(60.0, moment) if e.kind == "grid_voltage_dip"]

    state = generator._rng.getstate()
    assert not dips_at(T0 + timedelta(seconds=1)), "進行中不重複"
    assert generator._rng.getstate() != state, "照樣抽樣"
    end = dips[0].end
    assert not dips_at(end + timedelta(minutes=10)), "結束後的記錄期間也不重開：故障紀錄一種事件同時只有一筆"
    assert dips_at(end + timedelta(seconds=RECORD_GRACE_S + 1)), "記錄期間過了才會再有"


def test_events_survive_a_checkpoint_and_expire_after_the_grace_period() -> None:
    sim = WindFarmSimulator(turbine_count=2)
    sim.farm_event_generator.configure(_config(grid_voltage_dip=0.0001))
    made = sim.farm_event_generator.step(60.0, T0)
    assert made
    other = WindFarmSimulator(turbine_count=2)
    other.restore_state(sim.checkpoint_state())
    assert other.farm_event_generator.events == sim.farm_event_generator.events
    assert pickle.loads(pickle.dumps(sim.farm_event_generator)).events == made
    event = made[0]
    assert sim.farm_event_generator.recording(event.end + timedelta(seconds=RECORD_GRACE_S - 1))
    assert sim.farm_event_generator.expire(event.end) == []
    late = event.end + timedelta(seconds=RECORD_GRACE_S)
    assert event in sim.farm_event_generator.expire(late)


@pytest.mark.parametrize("bad", [
    {"enabled": "yes"},
    {"kinds": {"earthquake": {}}},
    {"kinds": {"grid_voltage_dip": {"magnitude_min": 0.5, "magnitude_max": 1.2}}},
    {"kinds": {"grid_voltage_dip": {"mean_days_between": 0}}},
    {"kinds": {"grid_frequency_excursion": {"magnitude_min": -1.0, "magnitude_max": 1.0}}},
    {"kinds": {"rapid_wind_direction_change": {"duration_min_s": 600, "duration_max_s": 300}}},
    {"kinds": {"grid_voltage_dip": {"size": 1}}},
    {"surprise": 1},
])
def test_bad_settings_are_rejected(bad: dict) -> None:
    with pytest.raises(ValueError):
        FarmEventGeneratorConfig.from_dict(bad)


def test_settings_round_trip() -> None:
    config = _config(grid_voltage_dip=30.0)
    assert FarmEventGeneratorConfig.from_dict(config.to_dict()) == config
    assert config.kinds["grid_frequency_excursion"].mean_days_between == 180.0, "沒給的用預設"


# ── 2. 引擎 ───────────────────────────────────────────────────────────────


def _readings(sim: WindFarmSimulator, steps: int) -> list:
    out = []
    for step in range(steps):
        data = sim._run_one_step(T0 + timedelta(seconds=step + 1), 1.0)
        out.append([sorted(d["scada"].items()) for d in data])
    return out


def test_the_engine_rolls_for_farm_events_only_in_live_steps() -> None:
    sim = WindFarmSimulator(turbine_count=2)
    sim.farm_event_generator.configure(_config(grid_voltage_dip=0.001, grid_frequency_excursion=0.001,
                                               rapid_wind_direction_change=0.001))
    sim._bulk_running = True
    for step in range(180):
        sim._run_one_step(T0 + timedelta(seconds=step + 1), 1.0)
    assert sim.farm_event_generator.generated == 0, "批次情境不產生"
    sim._bulk_running = False
    started: List[LiveFarmEvent] = []
    for step in range(180, 360):
        sim._run_one_step(T0 + timedelta(seconds=step + 1), 1.0)
        started.extend(sim.last_farm_events_started)
    assert started and sim.farm_event_generator.generated == len(started)
    assert all(e.start >= T0 + timedelta(seconds=180) for e in started), "從即時模擬的那一步開始"


def test_a_quiet_generator_leaves_the_readings_unchanged() -> None:
    """開著（發生率低到不會發生）跑出來的讀值和關著的逐位元相同：產生器只用自己的亂數。"""
    quiet = WindFarmSimulator(turbine_count=3)
    quiet.farm_event_generator.configure(_config(grid_voltage_dip=1e9, grid_frequency_excursion=1e9,
                                                 rapid_wind_direction_change=1e9))
    assert _readings(quiet, 150) == _readings(WindFarmSimulator(turbine_count=3), 150)


def test_live_events_override_the_grid_and_the_wind_direction_and_then_restore() -> None:
    sim = WindFarmSimulator(turbine_count=2)
    generator = sim.farm_event_generator
    generator.events.append(LiveFarmEvent("grid_voltage_dip", T0 + timedelta(seconds=10), 20.0, 0.7))
    generator.events.append(LiveFarmEvent("rapid_wind_direction_change", T0 + timedelta(seconds=10), 600.0, 60.0))
    sim._run_one_step(T0 + timedelta(seconds=5), 1.0)
    assert not sim.grid_model.event_override_active and sim._direction_offset_deg == 0.0, "還沒開始"
    sim._run_one_step(T0 + timedelta(seconds=20), 1.0)
    assert sim.grid_model.event_override_active
    assert sim.grid_model._event_voltage == pytest.approx(sim.grid_model.base_voltage_v * 0.7)
    assert sim.grid_model._event_frequency is None, "電壓驟降不動頻率"
    sim._run_one_step(T0 + timedelta(seconds=200), 1.0)
    assert not sim.grid_model.event_override_active, "電壓驟降結束：復原"
    assert sim._direction_offset_deg != 0.0, "風向還在擺"
    sim._run_one_step(T0 + timedelta(seconds=700), 1.0)
    assert sim._direction_offset_deg == 0.0 and generator.events, "結束了，還在記錄期間"
    sim._bulk_running = True
    generator.events.append(LiveFarmEvent("grid_voltage_dip", T0 + timedelta(seconds=800), 20.0, 0.7))
    sim._run_one_step(T0 + timedelta(seconds=810), 1.0)
    assert not sim.grid_model.event_override_active, "批次期間不套用即時模擬的事件"


def test_a_batch_does_not_carry_a_live_event() -> None:
    sim = WindFarmSimulator(turbine_count=2)
    sim.farm_event_generator.events.append(LiveFarmEvent("grid_voltage_dip", T0, 600.0, 0.7))
    sim._run_one_step(T0 + timedelta(seconds=1), 1.0)
    assert sim.grid_model.event_override_active
    seen: List[bool] = []
    sim.generate_bulk(duration_hours=0.01, time_step=10.0,
                      callback=lambda _rows: seen.append(sim.grid_model.event_override_active))
    assert seen and not any(seen), "批次開始時拿掉 Live 的覆寫"


# ── 3. 運維：跳機、故障紀錄、工單答案 ─────────────────────────────────────


def _dip(farm: Farm, magnitude: float = 0.6, duration_s: float = 20.0) -> LiveFarmEvent:
    clock = farm.broker.live_clock()
    event = LiveFarmEvent("grid_voltage_dip", clock, duration_s, magnitude)
    sim = farm.broker.simulator
    sim.farm_event_generator.events.append(event)
    sim.last_farm_events_started = [event]   # 產生器擲出來的那一步會這樣通知 broker
    farm.broker._record_farm_events()
    sim.last_farm_events_started = []
    return event


def test_a_live_grid_dip_trips_turbines_and_is_recorded_as_nuisance(farm: Farm) -> None:
    farm.drive_slow(30)
    for tid in ("WT001", "WT002", "WT003"):
        farm.until_producing(tid)
    event = _dip(farm)
    farm.drive(40)
    cases = {c["turbine_id"]: c for c in farm.broker.fault_records.cases() if c["source"] == "farm_event"}
    assert set(cases) == {"WT001", "WT002", "WT003"}, "每台機組一筆"
    tripped = [c for c in cases.values() if c["trip_code"] in (481, 482)]
    assert tripped, "電壓驟降讓發電中的機組以電網保護跳機"
    for case in cases.values():
        assert case["category"] == "nuisance" and case["nuisance_cause"] == "grid_disturbance"
        assert case["cleared_ts"] is None, "記錄期間還沒過"
    # 記錄期間過了：紀錄結束，時間是事件結束的時刻，不是工單修好的、不算進故障率
    farm.drive_slow(int(RECORD_GRACE_S // 10) + 10)
    closed = [c for c in farm.broker.fault_records.cases() if c["source"] == "farm_event"]
    from simulator.time_utils import iso_utc

    assert closed and all(c["cleared_by"] == "farm_event_end" for c in closed)
    assert all(c["cleared_ts"] == iso_utc(event.end) for c in closed)
    clock = farm.broker.live_clock()
    assert farm.broker.storage.repaired_fault_counts("2000-01-01", iso_utc(clock + timedelta(hours=1))) == {}
    assert farm.broker.simulator.farm_event_generator.events == [], "記錄期間過了就拿掉"


def test_records_left_open_are_closed_and_a_new_event_gets_its_own(farm: Farm) -> None:
    """程式更新後存檔不還原、或重啟去重的那幾步漏了結束：沒關掉的紀錄依產生器的狀態對帳關掉（code review）。"""
    from simulator.time_utils import iso_utc

    farm.drive_slow(6)
    storage = farm.broker.storage
    old = farm.broker.live_clock() - timedelta(hours=3)
    for tid in ("WT001", "WT002", "WT003"):
        storage.open_fault_record(tid, "grid_voltage_dip", "farm_event", iso_utc(old))
    farm.drive_slow(7)   # 一分鐘之內會對帳一次
    stale = farm.broker.fault_records.cases(source="farm_event")
    assert len(stale) == 3 and all(c["cleared_by"] == "farm_event_end" for c in stale)
    event = _dip(farm)
    farm.drive(5)
    fresh = farm.broker.fault_records.cases(source="farm_event", open_only=True)
    assert {c["turbine_id"] for c in fresh} == {"WT001", "WT002", "WT003"}
    assert all(c["onset_ts"] == iso_utc(event.start) for c in fresh), "新事件自己一筆，不沿用沒關掉的"
    assert not [c for c in farm.broker.fault_records.cases(source="generator")], "依來源篩選"


def test_trip_work_orders_carry_the_farm_event_in_the_answer(farm: Farm) -> None:
    farm.drive_slow(6 * 60)   # 一小時的歷史：準備卡有同場可比
    for tid in ("WT001", "WT002", "WT003"):
        farm.until_producing(tid)
    _dip(farm)
    farm.drive(40)
    orders = [o for o in farm.orders() if o.source_alarm_code in ("481", "482")]
    assert len(orders) == 3, "三台都以電網保護跳機、各開一張"
    stored = farm.broker.storage.get_briefing(work_order_id=str(orders[0].id))
    assert stored is not None
    answer = stored["answer"]
    assert answer["has_fault"] is False and [e["kind"] for e in answer["farm_events"]] == ["grid_voltage_dip"]
    assert answer["farm_events"][0]["nuisance_cause"] == "grid_disturbance"
    from server.briefing import score_card

    assert score_card(stored["card"], answer)["false_escalation"] in (True, False), "沒有故障：看卡片有沒有誤判"
    card = stored["card"]
    assert "farm_event" not in str(card) and "grid_voltage_dip" not in str(card), "卡片不帶答案"
    others = {t["turbine_id"] for t in card["recent_events"]["farm_same_code"]["turbines"]}
    assert others == {"WT001", "WT002", "WT003"} - {orders[0].turbine_id}, "同場同時同碼看得到另外兩台"


# ── 4. 端點 ───────────────────────────────────────────────────────────────


def test_the_settings_endpoints(farm: Farm, monkeypatch) -> None:
    monkeypatch.setattr(ops, "get_broker", lambda: farm.broker)
    body = asyncio.run(ops.set_farm_event_settings({"enabled": True, "kinds": {
        "grid_voltage_dip": {"mean_days_between": 10, "magnitude_min": 0.6, "magnitude_max": 0.8}}}))
    assert body["config"]["enabled"] is True and body["generated"] == 0 and body["events"] == []
    assert body["config"]["kinds"]["grid_voltage_dip"]["mean_days_between"] == 10.0
    assert set(body["kinds"]) == set(FARM_EVENT_KINDS)
    assert farm.broker.storage.get_setting(farm.broker.SETTING_FARM_EVENTS)["enabled"] is True, "存在風場 DB"
    assert farm.broker.simulator.farm_event_generator.config.enabled is True
    with pytest.raises(HTTPException) as bad:
        asyncio.run(ops.set_farm_event_settings({"kinds": {"earthquake": {}}}))
    assert bad.value.status_code == 422
    # 重新套用存著的設定（例：重啟）
    farm.broker.simulator.farm_event_generator.configure(FarmEventGeneratorConfig())
    farm.broker.apply_live_settings()
    assert farm.broker.simulator.farm_event_generator.config.enabled is True
    # 發生了什麼是答案：只給永遠強制登入的主管
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)
    app = FastAPI()
    app.include_router(ops.router)
    client = TestClient(app)
    assert client.get("/api/operations/farm-events").status_code in (401, 403)
    assert client.put("/api/operations/farm-events", json={"enabled": False}).status_code in (401, 403)
