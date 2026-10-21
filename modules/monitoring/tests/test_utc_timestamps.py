"""monitoring 時間戳改 UTC tz-aware（WMOM-20261021-03-c，EPIC-DS Phase 1b-c）。

1. ``time_utils``：固定格式（字典序＝時間序）、``Z`` / 時區後綴 / naive（本地時間）解析
2. 模擬器輸出的 reading 時間戳是固定格式的 UTC
3. storage：寫入一律 UTC；查詢參數正規化（前端送 ``toISOString()`` 的 ``Z`` 字串）；舊版 naive 本地
   時間的 DB 開檔時一次性轉成 UTC
4. 風況模型的日夜 / 季節循環以風場時區計（WMOM-20261021-11；原為伺服器本地時間）

本地時區相關的測試把程序時區設成 Asia/Taipei（UTC+8）——CI 是 UTC，naive 與 UTC 一樣，測不出差異。
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import asyncio

import pytest

import server.storage as storage_module
from server.farm_registry import FarmRegistry
from server.routers import turbines as turbines_ep
from server.storage import TIMESTAMP_SCHEMA_VERSION, Storage
from simulator.engine import WindFarmSimulator
from simulator.time_utils import iso_utc, normalize_iso, parse_iso, utc_now
from wind_model import WindEnvironmentModel

CANONICAL = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00$")


@pytest.fixture
def taipei_tz() -> Iterator[None]:
    """程序時區暫時設為 Asia/Taipei（Python 與 SQLite 的本地時間都跟著變）。"""
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset 不可用（Windows）")
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "Asia/Taipei"
    time.tzset()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()


# ── time_utils ────────────────────────────────────────────────────────────


def test_iso_utc_is_fixed_format_and_sorts_chronologically() -> None:
    base = datetime(2026, 10, 21, 5, 0, 0, tzinfo=timezone.utc)
    times = [base + timedelta(microseconds=us) for us in (0, 5, 500_000, 999_999, 1_000_000, 1_000_001)]
    texts = [iso_utc(t) for t in times]
    assert all(CANONICAL.match(t) for t in texts)
    assert sorted(texts) == texts
    assert iso_utc(base) == "2026-10-21T05:00:00.000000+00:00"


def test_parse_iso_handles_z_offsets_and_naive_local(taipei_tz: None) -> None:
    expected = datetime(2026, 10, 21, 5, 0, 0, tzinfo=timezone.utc)
    assert parse_iso("2026-10-21T05:00:00Z") == expected
    assert parse_iso("2026-10-21T05:00:00.000Z") == expected
    assert parse_iso("2026-10-21T13:00:00+08:00") == expected
    assert parse_iso("2026-10-21T13:00:00") == expected          # naive＝本地時間（UTC+8）
    assert parse_iso("2026-10-21T05:00:00Z").tzinfo is not None


def test_normalize_iso_passes_through_empty_and_unparsable() -> None:
    assert normalize_iso(None) is None
    assert normalize_iso("") == ""
    assert normalize_iso("not-a-time") == "not-a-time"
    assert normalize_iso("2026-10-21T05:00:00.000Z") == "2026-10-21T05:00:00.000000+00:00"
    # URL query 未編碼的 "+" 變成空格
    assert normalize_iso("2026-10-21T05:00:00.000000 00:00") == "2026-10-21T05:00:00.000000+00:00"
    assert normalize_iso("2026-10-21T13:00:00 08:00") == "2026-10-21T05:00:00.000000+00:00"


# ── 模擬器輸出 ──────────────────────────────────────────────────────────────


def test_simulator_readings_carry_canonical_utc_timestamps() -> None:
    sim = WindFarmSimulator(turbine_count=1)
    now = utc_now()
    (reading,) = sim._run_one_step(now, 1.0)
    assert CANONICAL.match(reading["timestamp"])
    assert parse_iso(reading["timestamp"]) == now


# ── storage ───────────────────────────────────────────────────────────────


def _reading(ts: str) -> dict:
    return {"timestamp": ts, "turbine_id": "WT001", "wind_speed": 8.0, "scada": {"WTUR_TurSt": 6}}


def test_storage_writes_utc_and_normalizes_query_bounds(tmp_path: Path, taipei_tz: None) -> None:
    storage = Storage(db_path=str(tmp_path / "s.db"))
    storage.store_reading(_reading("2026-10-21T05:00:00.000000+00:00"))
    storage.record_event(event_type="fault", source="test", title="t", turbine_id="WT001",
                         timestamp="2026-10-21T13:00:00+08:00")
    storage.record_event(event_type="state", source="test", title="now", turbine_id="WT001")

    # 前端以 toISOString()（Z、毫秒）送查詢範圍：落在下界那一秒的列也要撈得到
    rows = storage.query_history("WT001", start="2026-10-21T05:00:00.000Z", end="2026-10-21T05:00:00.000Z")
    assert [r["timestamp"] for r in rows] == ["2026-10-21T05:00:00.000000+00:00"]
    # 舊 API 呼叫端的 naive 字串＝伺服器本地時間
    assert len(storage.query_history("WT001", start="2026-10-21T13:00:00", end="2026-10-21T13:00:01")) == 1

    events = storage.query_events("WT001", limit=10)
    assert all(CANONICAL.match(e["timestamp"]) for e in events)
    assert "2026-10-21T05:00:00.000000+00:00" in {e["timestamp"] for e in events}
    z_bounds = {"start": "2026-10-21T05:00:00.000Z", "end": "2026-10-21T05:00:00.000Z"}
    assert [e["title"] for e in storage.query_events("WT001", **z_bounds)] == ["t"]
    assert storage.count_scenario_fault_events(**z_bounds) == {"WT001": 1}
    storage.store_snapshot(_reading("2026-10-21T05:00:00.000000+00:00"), event_ref="ev")
    assert len(storage.query_snapshots("WT001", **z_bounds)) == 1

    storage.record_event(event_type="grid", source="test", title="open", turbine_id="WT009",
                         timestamp="2026-10-21T05:00:00Z", end_timestamp="2026-10-21T05:00:05Z")
    storage.record_event(event_type="fatigue", source="test", title="closing", turbine_id="WT009",
                         timestamp="2026-10-21T05:00:00Z")
    storage.close_open_events("fatigue", turbine_id="WT009", closed_at="2026-10-21T13:00:10+08:00")
    ends = {e["title"]: e["end_timestamp"] for e in storage.query_events("WT009", limit=10)}
    assert ends == {"open": "2026-10-21T05:00:05.000000+00:00", "closing": "2026-10-21T05:00:10.000000+00:00"}
    session_id = storage.create_session(data_source="simulation", turbine_count=1)
    storage.end_session(session_id)
    session = storage.get_sessions(limit=1)[0]
    assert CANONICAL.match(session["started_at"]) and CANONICAL.match(session["ended_at"])

    wo = storage.create_work_order(turbine_id=1, turbine_name="WTG-01", fault_description="x")
    storage.update_work_order(wo["id"], status="COMPLETED")
    created_at, completed_at = sqlite3.connect(str(tmp_path / "s.db")).execute(
        "SELECT created_at, completed_at FROM work_orders").fetchone()
    assert CANONICAL.match(created_at) and CANONICAL.match(completed_at)


def test_downsampling_buckets_utc_timestamps_by_minute(tmp_path: Path) -> None:
    storage = Storage(db_path=str(tmp_path / "d.db"))
    start = (utc_now() - timedelta(minutes=30)).replace(second=0, microsecond=0)
    storage.store_readings([_reading(iso_utc(start + timedelta(seconds=10 * i))) for i in range(18)])
    storage.run_downsampling()
    rows = sqlite3.connect(str(tmp_path / "d.db")).execute(
        "SELECT timestamp, sample_count FROM turbine_data_1m ORDER BY timestamp").fetchall()
    assert [count for _, count in rows] == [6, 6, 6]
    assert rows[0][0] == iso_utc(start)


def test_legacy_naive_local_db_is_converted_to_utc_once(tmp_path: Path, taipei_tz: None) -> None:
    db = str(tmp_path / "legacy.db")
    Storage(db_path=db)                      # 建 schema（空 DB 直接標新版本）
    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == TIMESTAMP_SCHEMA_VERSION
    # 模擬 WMOM-20261021-03-c 之前寫入的資料：naive 本地時間（UTC+8）
    conn.execute("INSERT INTO turbine_data (timestamp, turbine_id) VALUES ('2026-10-21T13:00:00.123456', 'WT001')")
    conn.execute("INSERT INTO turbine_data (timestamp, turbine_id) VALUES ('2026-10-21T06:00:00.000000+00:00', 'WT002')")
    conn.execute("INSERT INTO turbine_data (timestamp, turbine_id) VALUES ('2026-10-21 14:00:00.5', 'WT003')")
    conn.execute("INSERT INTO turbine_data (timestamp, turbine_id) VALUES ('2026-10-21T07:00:00Z', 'WT004')")
    conn.execute("INSERT INTO turbine_data (timestamp, turbine_id) VALUES ('2026-10-21T15:00:00+08:00', 'WT005')")
    conn.execute("INSERT INTO turbine_data (timestamp, turbine_id) VALUES ('', 'WT006')")
    conn.execute("INSERT INTO sessions (started_at, data_source, config_json) VALUES ('2026-10-21T12:00:00', 'simulation', NULL)")
    conn.execute("INSERT INTO turbine_data_10m (timestamp, turbine_id) VALUES ('2026-10-21T13:10:00', 'WT001')")
    conn.execute("INSERT INTO history_events (timestamp, end_timestamp, event_type, source, title) "
                 "VALUES ('2026-10-21T13:00:00', '2026-10-21T13:05:00', 'fault', 's', 't')")
    conn.execute("INSERT INTO sessions (started_at, ended_at, data_source, config_json) VALUES "
                 "('2026-10-21T12:00:00', NULL, 'simulation', "
                 "'{\"kind\": \"scenario\", \"sim_start\": \"2026-10-21T13:00:00\", \"sim_end\": \"2026-10-21T14:00:00\"}')")
    conn.execute("INSERT INTO work_orders (id, turbine_id, turbine_name, status, created_at, fault_description) "
                 "VALUES ('WO-1', 1, 'WTG-01', 'OPEN', '2026-10-21T13:00:00', 'x')")
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()

    storage = Storage(db_path=db)

    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == TIMESTAMP_SCHEMA_VERSION
    data = dict(conn.execute("SELECT turbine_id, timestamp FROM turbine_data").fetchall())
    assert data == {"WT001": "2026-10-21T05:00:00.123456+00:00",   # 轉成 UTC，微秒保留
                    "WT002": "2026-10-21T06:00:00.000000+00:00",   # 已是 UTC：不動
                    "WT003": "2026-10-21T06:00:00.500000+00:00",   # 空格分隔的 naive 也轉
                    "WT004": "2026-10-21T07:00:00Z",               # 有時區後綴：不動
                    "WT005": "2026-10-21T15:00:00+08:00",
                    "WT006": ""}
    assert conn.execute("SELECT timestamp FROM turbine_data_10m").fetchone()[0] == "2026-10-21T05:10:00.000000+00:00"
    assert conn.execute("SELECT timestamp, end_timestamp FROM history_events").fetchone() == (
        "2026-10-21T05:00:00.000000+00:00", "2026-10-21T05:05:00.000000+00:00")
    started_at, ended_at = conn.execute("SELECT started_at, ended_at FROM sessions ORDER BY id").fetchone()
    assert (started_at, ended_at) == ("2026-10-21T04:00:00.000000+00:00", None)
    assert conn.execute("SELECT created_at FROM work_orders").fetchone()[0] == "2026-10-21T05:00:00.000000+00:00"
    conn.close()
    scenario = next(x["config"] for x in storage.get_sessions(limit=5) if x.get("config"))
    assert (scenario["sim_start"], scenario["sim_end"]) == (
        "2026-10-21T05:00:00.000000+00:00", "2026-10-21T06:00:00.000000+00:00")
    # 工單建立時間（前端用 epoch ms）不變
    wo = storage.get_work_order("WO-1")
    assert wo is not None
    assert wo["createdAt"] == int(datetime(2026, 10, 21, 5, tzinfo=timezone.utc).timestamp() * 1000)

    # 已是新版本：之後寫進來的 naive 值不會被再轉一次（轉換只跑一次）
    conn = sqlite3.connect(db)
    conn.execute("UPDATE turbine_data SET timestamp = '2026-10-21T13:00:00' WHERE turbine_id = 'WT001'")
    conn.commit()
    conn.close()
    Storage(db_path=db)
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT timestamp FROM turbine_data WHERE turbine_id = 'WT001'").fetchone()[0] == \
        "2026-10-21T13:00:00"
    conn.close()


def test_legacy_scenario_window_still_contains_its_boundary_events(tmp_path: Path, taipei_tz: None) -> None:
    """舊情境的 sim_start 與 offset-0 注入事件同一瞬間（同一個微秒）：轉換後事件仍在時間窗內。"""
    db = str(tmp_path / "scenario.db")
    Storage(db_path=db)
    conn = sqlite3.connect(db)
    ts = "2026-10-21T13:00:00.123456"
    conn.execute("INSERT INTO sessions (started_at, data_source, config_json) VALUES (?, 'simulation', ?)",
                 (ts, '{"kind": "scenario", "sim_start": "%s", "sim_end": "2026-10-21T14:00:00.987654"}' % ts))
    conn.execute("INSERT INTO history_events (timestamp, turbine_id, event_type, source, title) "
                 "VALUES (?, 'WT002', 'fault', 'scenario', 'inject')", (ts,))
    conn.execute("INSERT INTO history_events (timestamp, turbine_id, event_type, source, title) "
                 "VALUES ('2026-10-21T14:00:00.987654', 'WT002', 'fault', 'scenario', 'trip')")
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()

    storage = Storage(db_path=db)
    cfg = storage.get_sessions(limit=1)[0]["config"]
    window = {"start": cfg["sim_start"], "end": cfg["sim_end"]}
    assert sorted(e["title"] for e in storage.query_events(**window)) == ["inject", "trip"]
    assert storage.count_scenario_fault_events(**window) == {"WT002": 2}


def test_migration_runs_in_batches_and_can_be_skipped(tmp_path: Path, taipei_tz: None,
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    db = str(tmp_path / "batch.db")
    Storage(db_path=db)
    conn = sqlite3.connect(db)
    conn.executemany("INSERT INTO turbine_data (timestamp, turbine_id) VALUES (?, 'WT001')",
                     [(f"2026-10-21T13:00:{i:02d}",) for i in range(10)])
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()

    Storage(db_path=db, migrate_timestamps=False)               # 維護工具：不轉換
    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    assert conn.execute("SELECT MIN(timestamp) FROM turbine_data").fetchone()[0] == "2026-10-21T13:00:00"
    conn.close()

    monkeypatch.setattr(storage_module, "_MIGRATION_BATCH_ROWS", 3)
    Storage(db_path=db)
    conn = sqlite3.connect(db)
    stamps = [r[0] for r in conn.execute("SELECT timestamp FROM turbine_data ORDER BY rowid")]
    assert stamps == [f"2026-10-21T05:00:{i:02d}.000000+00:00" for i in range(10)]
    assert conn.execute("PRAGMA user_version").fetchone()[0] == TIMESTAMP_SCHEMA_VERSION
    conn.close()


def test_farm_registry_converts_legacy_times_and_sorts_by_utc(tmp_path: Path, taipei_tz: None) -> None:
    registry = FarmRegistry(data_dir=tmp_path)
    registry.create_farm("old_farm", "Old")
    registry.create_farm("new_farm", "New")
    conn = sqlite3.connect(str(tmp_path / "farms.db"))
    # 舊版：本地時間 11:30（UTC 03:30）
    conn.execute("UPDATE farms SET created_at = '2026-10-21T11:30:00', last_active_at = '2026-10-21T11:30:00' "
                 "WHERE farm_id = 'old_farm'")
    conn.execute("UPDATE farms SET last_active_at = '2026-10-21T06:30:00.000000+00:00' WHERE farm_id = 'new_farm'")
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()

    registry = FarmRegistry(data_dir=tmp_path)
    assert registry.get_farm("old_farm").last_active_at == "2026-10-21T03:30:00.000000+00:00"
    assert [f.farm_id for f in registry.list_farms()] == ["new_farm", "old_farm"]
    registry.set_active_farm("old_farm")
    assert CANONICAL.match(registry.get_farm("old_farm").last_active_at)


def test_farm_trend_long_range_groups_rows_into_time_buckets(tmp_path: Path,
                                                            monkeypatch: pytest.MonkeyPatch) -> None:
    """12 h 趨勢：依 strftime('%s') 分桶（原本 '%%s' 不經 % 格式化，回字面 '%s'，全部落同一桶）。"""
    storage = Storage(db_path=str(tmp_path / "trend.db"))
    now = utc_now()
    storage.store_readings([_reading(iso_utc(now - timedelta(hours=h))) for h in (3, 2, 1)])

    class _Broker:
        def __init__(self) -> None:
            self.storage = storage
            self.simulator = None

    monkeypatch.setattr(turbines_ep, "get_broker", lambda: _Broker())
    result = asyncio.run(turbines_ep.farm_trend(time_range="12h", points=150))
    assert result["count"] == 3


# ── 風況模型：日夜循環用風場時區（WMOM-20261021-11）───────────────────────────


@pytest.mark.parametrize("getter", [
    "get_wind_speed", "get_wind_direction", "get_ambient_temp", "get_ambient_humidity",
    "get_atmospheric_stability",
])
def test_wind_model_diurnal_cycle_uses_site_time(getter: str) -> None:
    """日夜循環依風場時區（預設 Asia/Taipei，WMOM-20261021-11）：UTC 06:00Z 與風場牆鐘 naive 14:00
    結果相同；把 06:00 當風場牆鐘則不同。與伺服器時區無關（見 test_farm_timezone.py）。"""
    def value(ts: datetime) -> float:
        return getattr(WindEnvironmentModel(seed=3), getter)(ts)

    utc_input = value(datetime(2026, 7, 1, 6, 0, tzinfo=timezone.utc))
    assert utc_input == value(datetime(2026, 7, 1, 14, 0))
    assert utc_input != value(datetime(2026, 7, 1, 6, 0))


@pytest.mark.parametrize(("profile", "rising"), [("ramp_up", True), ("ramp_down", False)])
def test_wind_ramp_profiles_accept_utc_timestamps(profile: str, rising: bool) -> None:
    model = WindEnvironmentModel(seed=1)
    model.set_profile(profile)
    t0 = utc_now()
    speeds = [model.get_wind_speed(t0 + timedelta(seconds=s)) for s in range(0, 400)]
    assert (speeds[-1] > speeds[0]) is rising
