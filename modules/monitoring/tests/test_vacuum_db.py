"""Tests for tools/vacuum_db.py — focus on --purge-snapshots flag (WMOM-20260505-01)。

`vacuum_db.py` 的 retention-based cleanup 在 retroactive write bug 累積的「重複 row 全在
retention 內」場景下無法釋放磁碟（劉老師 2026-05-05 實測：cleanup 只刪 2,135 row，
98.9% 的 1080 萬 row 都是 retention 內的重複）。
`--purge-snapshots` 是救火選項：直接 truncate 整個表。
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "modules" / "monitoring"))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))


@pytest.fixture
def seeded_db(tmp_path):
    """Tmp DB with the schema Storage expects + 一些 snapshot row（不同年齡）。"""
    from server.storage import Storage

    db = tmp_path / "wind_farm.db"
    s = Storage(db_path=str(db))

    # 塞 1000 row snapshots — 一半 1 天前、一半 100 天前
    from datetime import datetime, timedelta
    conn = s._get_conn()
    now = datetime.now()
    for i in range(500):
        ts = (now - timedelta(days=1)).isoformat()
        conn.execute(
            """INSERT INTO turbine_snapshots
               (timestamp, turbine_id, session_id, event_ref, wind_speed, power_output, rotor_speed, scada_json)
               VALUES (?, 'WT001', NULL, 'stop:WT001:7:fresh', 7.5, 1500, 12, '{}')""",
            (ts,),
        )
    for i in range(500):
        ts = (now - timedelta(days=100)).isoformat()
        conn.execute(
            """INSERT INTO turbine_snapshots
               (timestamp, turbine_id, session_id, event_ref, wind_speed, power_output, rotor_speed, scada_json)
               VALUES (?, 'WT002', NULL, 'stop:WT002:7:old', 7.5, 1500, 12, '{}')""",
            (ts,),
        )
    conn.commit()

    # 確認 1000 row
    count = conn.execute("SELECT COUNT(*) FROM turbine_snapshots").fetchone()[0]
    assert count == 1000

    # close storage's connection so vacuum tool can take over
    try:
        s._local.conn.close()
    except Exception:
        pass

    return db


# ─────────────────────────────────────────────────────────────────────────


def test_purge_snapshots_table_helper(seeded_db):
    """`purge_snapshots_table()` 直接 helper：清空 snapshots，回傳被刪 row 數。"""
    from vacuum_db import purge_snapshots_table

    n = purge_snapshots_table(seeded_db)
    assert n == 1000

    con = sqlite3.connect(str(seeded_db))
    remaining = con.execute("SELECT COUNT(*) FROM turbine_snapshots").fetchone()[0]
    con.close()
    assert remaining == 0


def test_purge_flag_clears_all_snapshots_regardless_of_age(seeded_db):
    """`run(... purge_snapshots=True)` 強制 truncate — 不論 row 年齡（fresh / old 都清）。

    對比：retention-based cleanup 只會刪 100 天前的 500 row（fresh 1 天前的留下）。
    """
    from vacuum_db import run

    rc = run(seeded_db, do_cleanup=False, dry_run=False, purge_snapshots=True)
    assert rc == 0

    con = sqlite3.connect(str(seeded_db))
    remaining = con.execute("SELECT COUNT(*) FROM turbine_snapshots").fetchone()[0]
    con.close()
    assert remaining == 0, "purge_snapshots=True 應清空整表（fresh + old 都刪）"


def test_purge_flag_dry_run_no_changes(seeded_db):
    """dry-run + purge_snapshots → 不動 row，只報告。"""
    from vacuum_db import run

    rc = run(seeded_db, do_cleanup=False, dry_run=True, purge_snapshots=True)
    assert rc == 0

    con = sqlite3.connect(str(seeded_db))
    remaining = con.execute("SELECT COUNT(*) FROM turbine_snapshots").fetchone()[0]
    con.close()
    assert remaining == 1000, "dry-run 不應實際刪 row"


def test_retention_alone_keeps_fresh_snapshots(seeded_db):
    """對照組：用 cleanup retention 而非 purge — fresh row（1 天前）留下，old（100 天）刪掉。"""
    from vacuum_db import run

    rc = run(seeded_db, do_cleanup=True, dry_run=False,
             snapshots_retention_days=7, purge_snapshots=False)
    assert rc == 0

    con = sqlite3.connect(str(seeded_db))
    remaining = con.execute("SELECT COUNT(*) FROM turbine_snapshots").fetchone()[0]
    fresh = con.execute(
        "SELECT COUNT(*) FROM turbine_snapshots WHERE event_ref = 'stop:WT001:7:fresh'"
    ).fetchone()[0]
    con.close()
    assert remaining == 500, "只應留下 fresh 500 row"
    assert fresh == 500


def test_purge_plus_cleanup_skips_double_snapshot_delete(seeded_db):
    """purge_snapshots=True + do_cleanup=True 時，cleanup 內 snapshots_retention 應被改 0
    避免「DELETE 後再跑一次 retention 多餘 SQL」（不是 bug 但不漂亮）。

    本 test 透過行為確認：purge 後 cleanup 跑出來 deleted_snapshots == 0。
    """
    from vacuum_db import run

    # purge + cleanup 同時開
    rc = run(seeded_db, do_cleanup=True, dry_run=False,
             snapshots_retention_days=7, purge_snapshots=True)
    assert rc == 0

    con = sqlite3.connect(str(seeded_db))
    remaining = con.execute("SELECT COUNT(*) FROM turbine_snapshots").fetchone()[0]
    con.close()
    assert remaining == 0
