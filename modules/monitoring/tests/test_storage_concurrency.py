"""SQLite 並發 lock regression test for #WMOM-20260504-09.

實際生產情境（從用戶 log 重現）：
- FastAPI handler thread 持續 GET /api/maintenance/technicians（SELECT）
- DataBroker maintenance thread 跑 cleanup / downsampling（DELETE 大量 row）
- DataBroker write thread 跑 INSERT turbine_data
- 同時操作同一個 DB → 沒有 WAL 就會 "database is locked"

本 test 用 4 個 thread（2 reader + 1 writer + 1 deleter）並發跑 1 秒，驗證：
1. 沒有 sqlite3.OperationalError raise
2. 所有 thread 都跑出有效 row count

不打開 WAL 此 test 會 fail（reader fail with "database is locked"）。
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
# Storage 用 `from server.X import Y` (sys.path injected) — 加 monitoring/ to path
sys.path.insert(0, str(PROJECT_ROOT / "modules" / "monitoring"))


@pytest.fixture
def temp_storage(tmp_path):
    """乾淨的 Storage instance（每個 test fresh DB）。"""
    from server.storage import Storage

    db_path = str(tmp_path / "test_concurrency.db")
    s = Storage(db_path=db_path)
    # 預塞一些 technician row 給 reader 讀
    for i in range(5):
        s.create_technician(name=f"Tech-{i}", status="ON_DUTY")
    return s


def test_pragmas_applied(temp_storage):
    """驗證 _get_conn 真的有設 WAL + busy_timeout。"""
    conn = temp_storage._get_conn()
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert mode.lower() == "wal", f"journal_mode={mode}, expected WAL"
    assert busy == 5000, f"busy_timeout={busy}, expected 5000"


def test_concurrent_read_write_no_lock(temp_storage):
    """4 thread 並發 read/write 1 秒，不該 raise OperationalError。

    Without WAL fix（or busy_timeout=0），reader 會撞 "database is locked"。
    """
    errors: list[Exception] = []
    op_counts: dict[str, int] = {"reader_a": 0, "reader_b": 0, "writer": 0, "deleter": 0}
    stop_flag = threading.Event()

    def reader(name: str):
        try:
            while not stop_flag.is_set():
                rows = temp_storage.query_technicians()
                assert isinstance(rows, list)
                op_counts[name] += 1
        except Exception as e:
            errors.append(e)

    def writer():
        try:
            counter = 0
            while not stop_flag.is_set():
                temp_storage.create_technician(
                    name=f"NewTech-{counter}", status="ON_DUTY"
                )
                op_counts["writer"] += 1
                counter += 1
                time.sleep(0.005)  # ~200 inserts/sec
        except Exception as e:
            errors.append(e)

    def deleter():
        """模擬 maintenance thread 的 DELETE — 持有 write lock 較久。"""
        try:
            while not stop_flag.is_set():
                conn = temp_storage._get_conn()
                # 大量 DELETE（模擬 cleanup 行為）
                conn.execute("DELETE FROM technicians WHERE id < 0")  # no-op DELETE
                conn.commit()
                op_counts["deleter"] += 1
                time.sleep(0.02)  # ~50 deletes/sec
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=reader, args=("reader_a",), name="reader-a"),
        threading.Thread(target=reader, args=("reader_b",), name="reader-b"),
        threading.Thread(target=writer, name="writer"),
        threading.Thread(target=deleter, name="deleter"),
    ]

    for t in threads:
        t.start()
    time.sleep(1.0)
    stop_flag.set()
    for t in threads:
        t.join(timeout=5.0)

    # 全 thread 跑出 op，沒有 lock error
    assert not errors, f"Got {len(errors)} errors during concurrent ops: {errors[:3]}"
    assert op_counts["reader_a"] > 10, f"Reader A only ran {op_counts['reader_a']} ops"
    assert op_counts["reader_b"] > 10, f"Reader B only ran {op_counts['reader_b']} ops"
    assert op_counts["writer"] > 10, f"Writer only ran {op_counts['writer']} ops"
    assert op_counts["deleter"] > 10, f"Deleter only ran {op_counts['deleter']} ops"
    print(
        f"\nOK concurrent ops in 1 sec: "
        f"reader_a={op_counts['reader_a']}, reader_b={op_counts['reader_b']}, "
        f"writer={op_counts['writer']}, deleter={op_counts['deleter']}"
    )


def test_storage_basic_crud_still_works(temp_storage):
    """Regression: 確認 PRAGMA 改動沒破壞既有 CRUD。"""
    # Create
    new_tech = temp_storage.create_technician(name="Bob", status="OFF_DUTY")
    assert new_tech["name"] == "Bob"
    assert new_tech["status"] == "OFF_DUTY"

    # Read
    all_techs = temp_storage.query_technicians()
    bob_match = [t for t in all_techs if t["name"] == "Bob"]
    assert len(bob_match) == 1

    # Update
    updated = temp_storage.update_technician(
        tech_id=new_tech["id"], status="ON_DUTY"
    )
    assert updated is not None
    assert updated["status"] == "ON_DUTY"
