"""monitoring 時間戳改 UTC tz-aware（WMOM-20261021-03-c，EPIC-DS Phase 1b-c）。

1. ``time_utils``：固定格式（字典序＝時間序）、``Z`` / 時區後綴 / naive（本地時間）解析
2. 模擬器輸出的 reading 時間戳是固定格式的 UTC
3. storage：寫入一律 UTC；查詢參數正規化（前端送 ``toISOString()`` 的 ``Z`` 字串）；舊版 naive 本地
   時間的 DB 開檔時一次性轉成 UTC
4. 風況模型的日夜 / 季節循環仍以伺服器本地時間計（換成 UTC 輸入後不位移）

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

import pytest

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
    session_id = storage.create_session(data_source="simulation", turbine_count=1)
    storage.end_session(session_id)
    session = storage.get_sessions(limit=1)[0]
    assert CANONICAL.match(session["started_at"]) and CANONICAL.match(session["ended_at"])


def test_legacy_naive_local_db_is_converted_to_utc_once(tmp_path: Path, taipei_tz: None) -> None:
    db = str(tmp_path / "legacy.db")
    Storage(db_path=db)                      # 建 schema（空 DB 直接標新版本）
    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == TIMESTAMP_SCHEMA_VERSION
    # 模擬 WMOM-20261021-03-c 之前寫入的資料：naive 本地時間（UTC+8）
    conn.execute("INSERT INTO turbine_data (timestamp, turbine_id) VALUES ('2026-10-21T13:00:00.123456', 'WT001')")
    conn.execute("INSERT INTO turbine_data (timestamp, turbine_id) VALUES ('2026-10-21T06:00:00.000000+00:00', 'WT002')")
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
    assert data == {"WT001": "2026-10-21T05:00:00.123000+00:00",   # 轉成 UTC（毫秒精度）
                    "WT002": "2026-10-21T06:00:00.000000+00:00"}   # 已是 UTC：不動
    assert conn.execute("SELECT timestamp FROM turbine_data_10m").fetchone()[0] == "2026-10-21T05:10:00.000000+00:00"
    assert conn.execute("SELECT timestamp, end_timestamp FROM history_events").fetchone() == (
        "2026-10-21T05:00:00.000000+00:00", "2026-10-21T05:05:00.000000+00:00")
    started_at, ended_at = conn.execute("SELECT started_at, ended_at FROM sessions").fetchone()
    assert (started_at, ended_at) == ("2026-10-21T04:00:00.000000+00:00", None)
    assert conn.execute("SELECT created_at FROM work_orders").fetchone()[0] == "2026-10-21T05:00:00.000000+00:00"
    conn.close()
    scenario = storage.get_sessions(limit=1)[0]["config"]
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


# ── 風況模型：日夜循環仍用本地時間 ─────────────────────────────────────────


def test_wind_model_diurnal_cycle_keeps_server_local_time(taipei_tz: None) -> None:
    utc_input = WindEnvironmentModel(seed=3).get_atmospheric_stability(
        datetime(2026, 7, 1, 6, 0, tzinfo=timezone.utc))                # 台北 14:00
    local_input = WindEnvironmentModel(seed=3).get_atmospheric_stability(datetime(2026, 7, 1, 14, 0))
    utc_hour_as_local = WindEnvironmentModel(seed=3).get_atmospheric_stability(datetime(2026, 7, 1, 6, 0))
    assert utc_input == local_input
    assert utc_input != utc_hour_as_local
