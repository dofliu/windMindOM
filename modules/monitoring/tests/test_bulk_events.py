"""批次路徑的可觀測事件與事件 session 隔離（WMOM-20261021-04，EPIC-DS Phase 2）。

1. ``generate_bulk(on_events=...)`` 送出 PLC 事件與狀態轉換（模擬時間戳），且收集事件不改變任何讀值
2. ``history_events.session_id``：舊 DB 自動補欄；批次寫入、依 session / 來源查詢、刪情境一併刪除
3. 標準答案表與事件分開存（存取、覆寫、刪除）
4. 可觀測事件的判定（盲測）：情境標記、故障生命週期、帶故障 ID 的事件都不算
5. broker：Live 事件預設記在目前 session；批次事件與 Live 同格式
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
for _p in (PROJECT_ROOT, MONITORING_ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest  # noqa: E402

import simulator.engine as engine_mod  # noqa: E402
from server.data_broker import DataBroker  # noqa: E402
from server.farm_registry import FarmRegistry  # noqa: E402
from server.models import DataSourceConfig, DataSourceMode  # noqa: E402
from server.storage import Storage, is_observable_event  # noqa: E402
from simulator.bulk_events import STATE_CHANGE, BulkEvent  # noqa: E402
from simulator.engine import WindFarmSimulator  # noqa: E402
from simulator.physics.fault_engine import TestPlanStep as PlanStep  # noqa: E402
from simulator.time_utils import iso_utc, parse_iso  # noqa: E402

T0 = datetime(2026, 7, 1, 2, 0, tzinfo=timezone.utc)


@pytest.fixture
def fixed_start(monkeypatch: pytest.MonkeyPatch) -> datetime:
    """批次起點固定（風況依時刻變化；兩次生成要可比較時必須同一起點）。"""
    monkeypatch.setattr(engine_mod, "utc_now", lambda: T0)
    return T0


def _overspeed_run(on_events: bool) -> tuple:
    """WT001 快速超速故障、1 h、dt 10 s：回傳 (每步讀值, 事件)。"""
    sim = WindFarmSimulator(turbine_count=2, base_wind_speed=13.0)
    readings: List[List[Dict]] = []
    events: List[BulkEvent] = []
    sim.generate_bulk(
        1.0, time_step=10.0, callback=readings.append,
        fault_schedule=[PlanStep(600, "generator_overspeed", "WT001", 0.01)],
        on_events=events.extend if on_events else None,
    )
    return readings, events


# ── 1. 引擎：批次事件 ─────────────────────────────────────────────────────────


def test_collecting_events_does_not_change_the_data(fixed_start: datetime) -> None:
    with_events, events = _overspeed_run(on_events=True)
    without_events, _ = _overspeed_run(on_events=False)
    assert events, "應收到事件"
    assert [[r["scada"] for r in step] for step in with_events] == \
        [[r["scada"] for r in step] for step in without_events]


def test_bulk_events_carry_plc_trip_and_state_changes_on_the_sim_timeline(fixed_start: datetime) -> None:
    readings, events = _overspeed_run(on_events=True)
    start, end = parse_iso(readings[0][0]["timestamp"]), parse_iso(readings[-1][0]["timestamp"])
    assert all(start - timedelta(seconds=10) <= e.timestamp <= end for e in events)

    wt1 = [e for e in events if e.turbine_id == "WT001"]
    assert [e.timestamp for e in wt1] == sorted(e.timestamp for e in wt1), "同機組事件依時間排序"
    (trip,) = [e for e in wt1 if e.kind == "trip"]
    assert trip.plc_event is not None and trip.plc_event.code == 351 and trip.plc_event.level == "T1"
    assert trip.timestamp >= T0 + timedelta(seconds=600), "跳機在注入之後"
    stop = next(e for e in wt1 if e.kind == STATE_CHANGE and e.to_state == 7)
    assert stop.shutdown_cause == "overspeed_software" and stop.timestamp >= trip.timestamp

    # 狀態轉換串起來與讀值一致：最後一個 to_state＝最後一筆讀值的 TurSt
    for tid in ("WT001", "WT002"):
        changes = [e for e in events if e.turbine_id == tid and e.kind == STATE_CHANGE]
        assert changes, f"{tid} 起機應有狀態轉換"
        assert all(a.to_state == b.from_state for a, b in zip(changes, changes[1:]))
        last_reading = next(r for r in readings[-1] if r["turbine_id"] == tid)
        assert changes[-1].to_state == int(last_reading["scada"]["WTUR_TurSt"])
    assert not [e for e in events if e.turbine_id == "WT002" and e.plc_event is not None], \
        "健康機組在 13 m/s 不應有 PLC 事件"


def test_events_keep_physics_substep_resolution(fixed_start: datetime) -> None:
    """dt 10 s 拆成兩個 5 s 物理子步：事件每個子步都收，時間戳不被量化到輸出步。"""
    _, events = _overspeed_run(on_events=True)
    startup = [e for e in events if e.turbine_id == "WT002" and e.kind == STATE_CHANGE][:3]
    assert [(e.from_state, e.to_state) for e in startup] == [(2, 4), (4, 5), (5, 6)]
    assert (startup[1].timestamp - startup[0].timestamp).total_seconds() == pytest.approx(5.0)


def test_bulk_without_on_events_leaves_no_queued_events(fixed_start: datetime) -> None:
    sim = WindFarmSimulator(turbine_count=1, base_wind_speed=13.0)
    sim.generate_bulk(0.5, time_step=10.0, fault_schedule=[PlanStep(0, "generator_overspeed", "WT001", 0.02)])
    assert sim.turbines["WT001"].plc.drain_events() == []


def test_live_events_queued_before_the_batch_are_not_attributed_to_it(fixed_start: datetime) -> None:
    sim = WindFarmSimulator(turbine_count=1, base_wind_speed=13.0)
    model = sim.turbines["WT001"]
    model.plc.note_protection_stop("cut_out", 0.0)  # 佇列裡一筆 I201，模擬 Live 尚未取走的事件
    events: List[BulkEvent] = []
    sim.generate_bulk(0.05, time_step=10.0, on_events=events.extend)
    assert events, "前置：起機應有狀態轉換"
    assert not [e for e in events if e.plc_event is not None and e.plc_event.code == 201]


# ── 2. storage：事件 session 隔離 ─────────────────────────────────────────────


def test_legacy_history_events_table_gets_session_id_column(tmp_path: Path) -> None:
    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db))
    conn.execute("""CREATE TABLE history_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, end_timestamp TEXT,
        turbine_id TEXT, event_type TEXT NOT NULL, source TEXT NOT NULL, title TEXT NOT NULL,
        detail TEXT, payload_json TEXT)""")
    conn.execute("INSERT INTO history_events (timestamp, event_type, source, title) "
                 "VALUES ('2026-10-01T00:00:00.000000+00:00', 'state', 'simulator', 'old')")
    conn.commit()
    conn.close()
    storage = Storage(db_path=str(db))
    (old,) = storage.query_events()
    assert old["session_id"] is None
    storage.record_event("state", "simulator", "new", session_id=5)
    assert [e["title"] for e in storage.query_events(session_id=5)] == ["new"]


def test_record_events_batch_and_session_source_filters(tmp_path: Path) -> None:
    storage = Storage(db_path=str(tmp_path / "ev.db"))
    ts = iso_utc(T0)
    written = storage.record_events([
        {"event_type": "fault", "source": "plc", "title": "Trip", "turbine_id": "WT001",
         "timestamp": ts, "session_id": 1, "payload": {"code": 240}},
        {"event_type": "state", "source": "simulator", "title": "Stop", "turbine_id": "WT001",
         "timestamp": ts, "session_id": 1},
        {"event_type": "fault", "source": "scenario", "title": "Inject", "turbine_id": "WT001",
         "timestamp": ts, "session_id": 1, "payload": {"scenarioId": "bearing_wear"}},
        {"event_type": "fault", "source": "plc", "title": "Other session", "turbine_id": "WT001",
         "timestamp": ts, "session_id": 2},
    ])
    assert written == 4 and storage.record_events([]) == 0
    assert len(storage.query_events(session_id=1)) == 3
    assert [e["title"] for e in storage.query_events("WT001", session_id=1, source="scenario")] == ["Inject"]
    assert storage.query_events(session_id=1, source="plc")[0]["payload"] == {"code": 240}
    assert storage.count_scenario_fault_events(session_id=1) == {"WT001": 2}
    assert storage.count_scenario_fault_events(session_id=2) == {"WT001": 1}


def test_delete_scenario_removes_its_events_and_ground_truth(tmp_path: Path) -> None:
    storage = Storage(db_path=str(tmp_path / "del.db"))
    sid = storage.create_session("simulation", 1, config={"kind": storage.SCENARIO_KIND, "name": "x"})
    other = storage.create_session("simulation", 1)
    storage.record_event("fault", "plc", "mine", turbine_id="WT001", session_id=sid)
    storage.record_event("fault", "plc", "live", turbine_id="WT001", session_id=other)
    storage.save_ground_truth(sid, {"contract_version": "0.1", "cases": []})
    assert storage.delete_scenario(sid)
    assert storage.query_events(session_id=sid) == []
    assert storage.get_ground_truth(sid) is None
    assert [e["title"] for e in storage.query_events(session_id=other)] == ["live"]


# ── 3. 標準答案表 ─────────────────────────────────────────────────────────────


def test_ground_truth_roundtrip_and_overwrite(tmp_path: Path) -> None:
    storage = Storage(db_path=str(tmp_path / "gt.db"))
    assert storage.get_ground_truth(1) is None
    storage.save_ground_truth(1, {"contract_version": "0.1", "cases": [{"root_cause": "主軸承潤滑劣化"}]})
    assert storage.get_ground_truth(1)["cases"][0]["root_cause"] == "主軸承潤滑劣化"
    storage.save_ground_truth(1, {"contract_version": "0.1", "cases": []})
    assert storage.get_ground_truth(1) == {"contract_version": "0.1", "cases": []}
    # 標準答案不在事件表裡
    assert storage.query_events(session_id=1) == []


# ── 4. 可觀測事件的判定 ────────────────────────────────────────────────────────


@pytest.mark.parametrize("event, observable", [
    ({"source": "plc", "event_type": "fault", "payload": {"code": 240, "level": "T1"}}, True),
    ({"source": "simulator", "event_type": "state", "payload": {"shutdownCause": "plc:240"}}, True),
    ({"source": "simulator", "event_type": "grid", "payload": None}, True),
    ({"source": "scenario", "event_type": "fault", "payload": {"kind": "trip"}}, False),
    ({"source": "test_plan", "event_type": "fault", "payload": {}}, False),
    ({"source": "simulator", "event_type": "fault_lifecycle", "payload": {}}, False),
    ({"source": "simulator", "event_type": "fault", "payload": {"faults": ["bearing_wear"]}}, False),
    ({"source": "operator", "event_type": "fault", "payload": {"scenarioId": "bearing_wear"}}, False),
])
def test_is_observable_event(event: dict, observable: bool) -> None:
    assert is_observable_event(event) is observable


# ── 5. broker ─────────────────────────────────────────────────────────────────


def test_broker_records_live_events_in_current_session_and_bulk_events_in_given_one(tmp_path: Path) -> None:
    registry = FarmRegistry(data_dir=tmp_path)
    registry.set_active_farm(registry.ensure_default_farm())
    broker = DataBroker(farm_registry=registry)
    broker.start(DataSourceConfig(mode=DataSourceMode.SIMULATION), run_loop=False)
    try:
        live_sid = broker._session_id
        assert live_sid is not None
        broker.record_event(event_type="operator", source="api", title="Live action")
        (live,) = broker.storage.query_events(session_id=live_sid)
        assert live["title"] == "Live action"

        model = broker.simulator.turbines["WT001"]
        model.plc.note_protection_stop("cut_out", model._sim_time)
        (plc_event,) = model.plc.drain_events()
        bulk = [
            BulkEvent(timestamp=T0, turbine_id="WT001", kind=plc_event.kind, plc_event=plc_event),
            BulkEvent(timestamp=T0, turbine_id="WT001", kind=STATE_CHANGE, from_state=6, to_state=9,
                      shutdown_cause="plc:240"),
            BulkEvent(timestamp=T0, turbine_id="WT001", kind=STATE_CHANGE, from_state=9, to_state=42),
        ]
        assert broker.record_bulk_events(bulk, session_id=999) == 2, "未知狀態不記錄"
        rows = broker.storage.query_events(session_id=999)
        assert {r["timestamp"] for r in rows} == {iso_utc(T0)}
        by_source = {r["source"]: r for r in rows}
        # 與 Live 路徑同格式
        assert by_source["plc"]["title"] == "Info: I_201 " + plc_event.text
        assert by_source["plc"]["payload"]["code"] == 201
        assert by_source["simulator"]["title"] == "Automatic fault stop: PLC event 240"
        assert by_source["simulator"]["event_type"] == "fault"
    finally:
        broker.stop()
