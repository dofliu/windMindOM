"""Storage cleanup retention test for #WMOM-20260505-01.

驗證 `Storage.run_cleanup` 會清掉超過 retention 的：
- turbine_data（raw, 預設 3 天）
- turbine_data_1m（1 分鐘 aggregate, 預設 90 天）
- turbine_snapshots（預設 7 天 — ★ WMOM-01 修補的主要目標）

回歸：snapshots_retention_days=0 → 不清（保留 legacy 行為，方便特殊調試需求）。
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "modules" / "monitoring"))


@pytest.fixture
def storage(tmp_path):
    """Fresh Storage on temp DB."""
    from server.storage import Storage

    db_path = str(tmp_path / "test_cleanup.db")
    s = Storage(db_path=db_path)
    yield s


def _seed_snapshot(storage, age_days: float, turbine_id: str = "WT001",
                   event_ref: str = "stop:WT001:7:2026-01-01T00:00:00"):
    """直接寫 snapshot row（繞過 store_snapshot 的時間戳簽名）以控制 timestamp。"""
    ts = (datetime.now() - timedelta(days=age_days)).isoformat()
    conn = storage._get_conn()
    conn.execute(
        """INSERT INTO turbine_snapshots
           (timestamp, turbine_id, session_id, event_ref, wind_speed, power_output, rotor_speed, scada_json)
           VALUES (?, ?, NULL, ?, 7.5, 1500.0, 12.5, '{}')""",
        (ts, turbine_id, event_ref),
    )
    conn.commit()


def _seed_raw(storage, age_days: float, turbine_id: str = "WT001"):
    """只塞 cleanup test 所需的最小欄位 — 不適合用於 aggregation test
    （rotor_speed / blade_angle / temperature 等留 NULL 會讓 AVG() 跳過 rows）。"""
    ts = (datetime.now() - timedelta(days=age_days)).isoformat()
    conn = storage._get_conn()
    conn.execute(
        """INSERT INTO turbine_data
           (timestamp, turbine_id, session_id, status, tur_state, wind_speed, power_output)
           VALUES (?, ?, NULL, 'OPERATING', 6, 7.5, 1500.0)""",
        (ts, turbine_id),
    )
    conn.commit()


def _seed_agg_1m(storage, age_days: float, turbine_id: str = "WT001"):
    ts = (datetime.now() - timedelta(days=age_days)).isoformat()
    conn = storage._get_conn()
    conn.execute(
        """INSERT INTO turbine_data_1m
           (timestamp, turbine_id, session_id, power_output_avg, sample_count)
           VALUES (?, ?, NULL, 1500.0, 6)""",
        (ts, turbine_id),
    )
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────


def test_cleanup_removes_old_snapshots(storage):
    """老 snapshot (8 天前) 在 retention=7 應被清，新的 (1 天前) 不動。"""
    _seed_snapshot(storage, age_days=8.0, event_ref="stop:WT001:7:old")
    _seed_snapshot(storage, age_days=1.0, event_ref="stop:WT001:7:recent")

    result = storage.run_cleanup(snapshots_retention_days=7)

    assert result["deleted_snapshots"] == 1
    conn = storage._get_conn()
    rows = conn.execute("SELECT event_ref FROM turbine_snapshots").fetchall()
    refs = [r[0] for r in rows]
    assert "stop:WT001:7:recent" in refs
    assert "stop:WT001:7:old" not in refs


def test_cleanup_snapshots_default_7_days(storage):
    """預設 snapshots_retention_days=7 — 不傳參數行為。"""
    _seed_snapshot(storage, age_days=10.0, event_ref="stop:old")
    _seed_snapshot(storage, age_days=2.0, event_ref="stop:recent")

    result = storage.run_cleanup()  # 全 default

    assert result["deleted_snapshots"] == 1


def test_cleanup_snapshots_zero_retention_keeps_all(storage):
    """snapshots_retention_days=0 → 不清（legacy 行為）。"""
    _seed_snapshot(storage, age_days=100.0, event_ref="stop:ancient")
    _seed_snapshot(storage, age_days=1.0, event_ref="stop:recent")

    result = storage.run_cleanup(snapshots_retention_days=0)

    assert result["deleted_snapshots"] == 0
    count = storage._get_conn().execute(
        "SELECT COUNT(*) FROM turbine_snapshots"
    ).fetchone()[0]
    assert count == 2


def test_cleanup_returns_three_counters(storage):
    """run_cleanup 返回 dict 含 deleted_raw / deleted_1m / deleted_snapshots 三個 key。"""
    _seed_raw(storage, age_days=4.0)              # > 3 day → 清
    _seed_raw(storage, age_days=1.0)              # 留
    _seed_agg_1m(storage, age_days=100.0)         # > 90 day → 清
    _seed_agg_1m(storage, age_days=30.0)          # 留
    _seed_snapshot(storage, age_days=10.0)        # > 7 day → 清
    _seed_snapshot(storage, age_days=2.0)         # 留

    result = storage.run_cleanup()

    assert result == {"deleted_raw": 1, "deleted_1m": 1, "deleted_snapshots": 1}


def test_cleanup_no_op_when_all_recent(storage):
    """全部資料都新 → 0 row 被刪。"""
    _seed_raw(storage, age_days=0.5)
    _seed_agg_1m(storage, age_days=10.0)
    _seed_snapshot(storage, age_days=2.0)

    result = storage.run_cleanup()

    assert result == {"deleted_raw": 0, "deleted_1m": 0, "deleted_snapshots": 0}


def test_cleanup_handles_empty_db(storage):
    """空 DB cleanup 不應 raise，全 0。"""
    result = storage.run_cleanup()
    assert result == {"deleted_raw": 0, "deleted_1m": 0, "deleted_snapshots": 0}
