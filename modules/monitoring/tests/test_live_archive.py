"""Live 讀值的分層儲存（WMOM-20261125-03-c）：每日 Parquet 歸檔、兩層查詢、清理。

1. 歸檔一天：只含 Live（不含情境 session）、每台機組一個 row group、值與 SQLite 的相同。
2. 只歸檔過完的日子；重跑不重複；之後才寫進來的列會補進日檔；壞掉的索引或日檔不影響最近幾天的查詢。
3. 兩層查詢：同一個游標從歸檔走到 SQLite，不重複不遺漏；SQLite 清掉已歸檔的列之後結果不變。
4. 清理：還沒歸檔的 Live 讀值不刪；循環保存刪最舊的日檔。
5. broker 的例行工作：歸檔 → 記下界線 → 清 SQLite → 刪最舊的日檔，保留期看資料自己的時間。
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import pyarrow.parquet as pq
import pytest

from server import scenario_pack as sp
from server.data_broker import DataBroker
from server.farm_registry import FarmRegistry
from server.live_archive import ARCHIVE_DIRNAME, LiveArchive
from server.live_history import LiveHistory
from server.storage import Storage
from simulator.engine import WindFarmSimulator
from simulator.time_utils import iso_utc, parse_iso

# 2026-01-01 23:30 起，每 10 分鐘一筆：跨三個 UTC 日（1/1 尾、1/2 整天、1/3 頭）
T0 = datetime(2026, 1, 1, 23, 30, 0, tzinfo=timezone.utc)
STEP = timedelta(minutes=10)
STEPS = 3 + 144 + 4  # 1/1：3 筆；1/2：144 筆；1/3：4 筆


@pytest.fixture(scope="module")
def filled(tmp_path_factory) -> Storage:
    """兩台機組、跨三天的 Live 讀值，外加一個情境 session 的讀值。"""
    root = tmp_path_factory.mktemp("farm")
    storage = Storage(db_path=str(root / "wind_farm.db"))
    live = storage.create_session(data_source="simulation", turbine_count=2)
    sim = WindFarmSimulator(turbine_count=2)
    for i in range(STEPS):
        storage.store_readings(sim._run_one_step(T0 + i * STEP, 600.0), live)
    scenario = storage.create_session(data_source="simulation", turbine_count=2, config={"kind": "scenario"})
    other = WindFarmSimulator(turbine_count=2)
    for i in range(5):  # 情境的讀值落在 1/2，但不該進歸檔
        storage.store_readings(other._run_one_step(datetime(2026, 1, 2, 6, i, tzinfo=timezone.utc), 60.0), scenario)
    return storage


def _fresh(filled: Storage, tmp_path) -> Storage:
    """複製一份 DB 給會改資料的測試。"""
    import shutil

    target = tmp_path / "wind_farm.db"
    filled._get_conn().execute("PRAGMA wal_checkpoint(TRUNCATE)")
    shutil.copy(filled.db_path, target)
    return Storage(db_path=str(target))


def _ids() -> List[str]:
    return [col.tag.id for col in sp.pack_columns()]


def _formatted(values) -> dict:
    return sp.json_values(values, sp.pack_columns())


CLOCK = T0 + (STEPS - 1) * STEP  # 資料時鐘：1/3 00:30
DAY1, DAY2, DAY3 = date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)


def _midnight(day: date) -> str:
    return iso_utc(datetime(day.year, day.month, day.day, tzinfo=timezone.utc))


def _synced(filled: Storage, tmp_path) -> tuple[Storage, LiveArchive]:
    storage = _fresh(filled, tmp_path)
    archive = LiveArchive.for_storage(storage)
    archive.sync(storage, CLOCK)
    return storage, archive


# ── 歸檔 ───────────────────────────────────────────────────────────────────


def test_day_file_holds_only_live_rows_grouped_by_turbine(filled: Storage, tmp_path) -> None:
    storage = _fresh(filled, tmp_path)
    archive = LiveArchive.for_storage(storage)
    assert archive.root == Path(storage.db_path).with_name(ARCHIVE_DIRNAME)
    written = archive.sync(storage, CLOCK)
    # 資料時鐘在 1/3 00:30：1/1、1/2 過完了，1/3 還沒
    assert [(d.day, d.rows) for d in written] == [("2026-01-01", 6), ("2026-01-02", 288)], "情境的 10 筆不算"
    entry = written[1]
    assert parse_iso(entry.min_ts) == datetime(2026, 1, 2, tzinfo=timezone.utc)
    assert parse_iso(entry.max_ts) == datetime(2026, 1, 2, 23, 50, tzinfo=timezone.utc)

    path = archive.root / "raw" / "2026-01-02.parquet"
    assert path.stat().st_size == entry.bytes and not path.with_name(path.name + ".tmp").exists()
    meta = pq.ParquetFile(path)
    assert meta.num_row_groups == 2 and meta.metadata.num_rows == 288
    names = meta.schema_arrow.names
    assert names[:4] == ["id", "timestamp", "turbine_id", "session_id"]
    assert set(sp.MODEL_INTERNAL_TAGS) <= set(names), "自己的歷史留全部 tag，給出去時才挑欄位"
    table = meta.read()
    assert set(table.column("turbine_id").to_pylist()) == {"WT001", "WT002"}
    assert len(set(table.column("session_id").to_pylist())) == 1
    assert not (archive.root / "raw" / "2026-01-03.parquet").exists()


def test_archived_values_match_sqlite(filled: Storage, tmp_path) -> None:
    storage, archive = _synced(filled, tmp_path)
    ids = _ids()
    archived = archive.readings("WT002", ids, start=_midnight(DAY2), limit=1000)
    hot = storage.live_readings("WT002", start=_midnight(DAY2), end=_midnight(DAY3), limit=1000)
    assert [a.id for a in archived] == [int(r["id"]) for r in hot] and len(archived) == 144
    for a, r in zip(archived, hot):
        assert a.timestamp == r["timestamp"]
        assert _formatted(a.values) == _formatted(sp.scada_values(r["scada_json"], ids))


def test_sync_is_idempotent_and_records_how_far_it_got(filled: Storage, tmp_path) -> None:
    storage = _fresh(filled, tmp_path)
    archive = LiveArchive.for_storage(storage)
    assert archive.state().archived_through is None and archive.days() == []
    assert archive.sync(storage, datetime(2026, 1, 1, 23, 50, tzinfo=timezone.utc)) == [], "第一天還沒過完"
    assert archive.state().archived_through == _midnight(DAY1), "走到哪記到哪"
    assert len(archive.sync(storage, CLOCK)) == 2
    assert archive.state().archived_through == _midnight(DAY3)
    stamp = (archive.root / "raw" / "2026-01-02.parquet").stat().st_mtime_ns
    assert archive.sync(storage, CLOCK) == [], "已歸檔、內容沒變的不重做"
    assert (archive.root / "raw" / "2026-01-02.parquet").stat().st_mtime_ns == stamp
    # 資料時鐘往回（例：沒有命名的批次寫了未來的列之後）：界線不往回
    assert archive.sync(storage, datetime(2026, 1, 2, 12, tzinfo=timezone.utc)) == []
    assert archive.state().archived_through == _midnight(DAY3)
    summary = archive.summary()
    assert summary["days"] == 2 and summary["rows"] == 294 and summary["bytes"] == archive.total_bytes() > 0
    assert (summary["first_day"], summary["last_day"]) == ("2026-01-01", "2026-01-02")


def test_rows_written_later_for_an_archived_day_are_added(filled: Storage, tmp_path) -> None:
    storage, archive = _synced(filled, tmp_path)
    live = storage._get_conn().execute("SELECT session_id FROM turbine_data ORDER BY id LIMIT 1").fetchone()[0]
    late = WindFarmSimulator(turbine_count=2)._run_one_step(datetime(2026, 1, 2, 12, 5, tzinfo=timezone.utc), 60.0)
    storage.store_readings(late, live)   # id 比 1/3 的列還大，時間卻在 1/2
    written = archive.sync(storage, CLOCK)
    assert [(d.day, d.rows) for d in written] == [("2026-01-02", 290)], "SQLite 裡還是完整的一天：重寫日檔"
    days = {d.day: d for d in archive.days()}
    assert days["2026-01-02"].max_id > days["2026-01-02"].min_id + 300, "日檔的 id 範圍和之後的日子重疊"

    # SQLite 已經刪進那一天之後：手上不是完整的一天，不能拿來重寫
    archive.mark_hot_from(_midnight(DAY3))
    storage.delete_live_readings_before(_midnight(DAY3))
    storage.store_readings(WindFarmSimulator(turbine_count=2)._run_one_step(
        datetime(2026, 1, 2, 13, 5, tzinfo=timezone.utc), 60.0), live)
    assert archive.sync(storage, CLOCK) == []
    assert {d.day: d.rows for d in archive.days()}["2026-01-02"] == 290


def test_a_failing_day_stops_the_boundary_before_it(filled: Storage, tmp_path, monkeypatch) -> None:
    storage = _fresh(filled, tmp_path)
    archive = LiveArchive.for_storage(storage)
    original = LiveArchive._write_day

    def flaky(self: LiveArchive, store: Storage, day: date, turbines: List[str]):
        if day == DAY2:
            raise OSError("disk full")
        return original(self, store, day, turbines)

    monkeypatch.setattr(LiveArchive, "_write_day", flaky)
    with pytest.raises(OSError):
        archive.sync(storage, CLOCK)
    state = archive.state()
    assert [d.day for d in state.days] == ["2026-01-01"] and state.archived_through == _midnight(DAY2)
    with pytest.raises(ValueError):
        archive.mark_hot_from(_midnight(DAY3))   # 1/2 還沒歸檔：不准把界線推過去
    monkeypatch.undo()
    assert [d.day for d in archive.sync(storage, CLOCK)] == ["2026-01-02"], "下次從失敗的那一天接著做"
    assert archive.state().archived_through == _midnight(DAY3)


def test_prune_drops_the_oldest_days(filled: Storage, tmp_path) -> None:
    _, archive = _synced(filled, tmp_path)
    assert archive.prune(keep_days=0, today=date(2026, 6, 1)) == [], "0＝不刪"
    assert archive.prune(keep_days=5, today=DAY3) == []
    assert archive.prune(keep_days=1, today=DAY3) == ["2026-01-01"]
    assert [d.day for d in archive.days()] == ["2026-01-02"]
    assert not (archive.root / "raw" / "2026-01-01.parquet").exists()
    assert (archive.root / "raw" / "2026-01-02.parquet").exists()
    assert archive.state().archived_through == _midnight(DAY3), "刪舊檔不動界線"


# ── 兩層查詢 ───────────────────────────────────────────────────────────────


def _page_all(history: LiveHistory, turbine_id: str, limit: int, **kwargs) -> List[int]:
    seen: List[int] = []
    cursor = 0
    for _ in range(500):
        page = history.readings(turbine_id, _ids(), after_id=cursor, limit=limit, **kwargs)
        if not page:
            break
        seen += [r.id for r in page]
        cursor = page[-1].id
    return seen


def test_cursor_walks_from_archive_into_sqlite_without_gaps_or_repeats(filled: Storage, tmp_path) -> None:
    storage = _fresh(filled, tmp_path)
    expected = [int(r["id"]) for r in storage.live_readings("WT001", limit=5000)]
    assert len(expected) == STEPS
    snapshot = {r.id: (r.timestamp, _formatted(r.values))
                for r in LiveHistory(storage, None).readings("WT001", _ids(), limit=5000)}

    archive = LiveArchive.for_storage(storage)
    archive.sync(storage, CLOCK)
    history = LiveHistory(storage, archive)
    # 已歸檔、SQLite 還沒刪、界線還沒設：全部由 SQLite 給
    assert _page_all(history, "WT001", limit=7) == expected

    # 界線設在 1/2 12:00（一天的中間）：之前的歸檔給、之後的 SQLite 給，每一列只給一次
    boundary = iso_utc(datetime(2026, 1, 2, 12, tzinfo=timezone.utc))
    ranges = archive.delete_ranges(archive.state(), boundary)
    archive.mark_hot_from(boundary)
    assert _page_all(history, "WT001", limit=7) == expected, "界線設了、SQLite 還沒刪"
    deleted = storage.delete_archived_live_readings(ranges)
    assert deleted == (3 + 72) * 2, "1/1 與 1/2 上半天的 Live 讀值刪掉；之後的與情境的留著"
    assert len(storage.live_readings("WT001", limit=5000)) == 72 + 4
    for limit in (7, 75, 76, 5000):
        assert _page_all(history, "WT001", limit=limit) == expected, f"一頁 {limit} 筆"
    after = {r.id: (r.timestamp, _formatted(r.values)) for r in history.readings("WT001", _ids(), limit=5000)}
    assert after == snapshot, "SQLite 清掉之後：同一個游標、同樣的內容"

    middle = expected[100]
    assert [r.id for r in history.readings("WT001", _ids(), after_id=middle, limit=5000)] == expected[101:]
    assert history.readings("WT001", _ids(), after_id=expected[-1], limit=10) == [], "輪詢最新資料：不必開日檔"


def test_time_range_spans_both_tiers(filled: Storage, tmp_path) -> None:
    storage, archive = _synced(filled, tmp_path)
    archive.mark_hot_from(_midnight(DAY3))
    storage.delete_live_readings_before(_midnight(DAY3))
    history = LiveHistory(storage, archive)
    start = iso_utc(datetime(2026, 1, 2, 23, 30, tzinfo=timezone.utc))
    end = iso_utc(datetime(2026, 1, 3, 0, 20, tzinfo=timezone.utc))
    rows = history.readings("WT002", _ids(), start=start, end=end, limit=100)
    assert [parse_iso(r.timestamp).strftime("%d %H:%M") for r in rows] == [
        "02 23:30", "02 23:40", "02 23:50", "03 00:00", "03 00:10"], "半開區間，跨過歸檔與 SQLite 的分界"
    only_cold = history.readings("WT002", _ids(), start=_midnight(DAY2), end=_midnight(DAY3), limit=1000)
    assert len(only_cold) == 144
    assert history.readings("WT002", _ids(), end=iso_utc(T0), limit=10) == []
    assert history.readings("WT404", _ids(), limit=10) == []
    # 時間可以用任何 ISO 寫法
    zulu = history.readings("WT002", _ids(), start="2026-01-02T23:30:00Z", end="2026-01-03T08:20:00+08:00", limit=100)
    assert [r.id for r in zulu] == [r.id for r in rows]


def test_paging_stays_in_id_order_when_day_files_overlap(tmp_path) -> None:
    """id 的順序不等於時間的順序時（同一段時間的列分兩次寫進來），翻頁仍依 id、不重複不遺漏。"""
    storage = Storage(db_path=str(tmp_path / "wind_farm.db"))
    live = storage.create_session(data_source="simulation", turbine_count=1)
    sim = WindFarmSimulator(turbine_count=1)
    stamps = ([datetime(2026, 1, 2, h, tzinfo=timezone.utc) for h in range(0, 12)]      # 先寫 1/2 上半天
              + [datetime(2026, 1, 1, h, tzinfo=timezone.utc) for h in range(0, 24)]    # 再寫 1/1 整天
              + [datetime(2026, 1, 2, h, tzinfo=timezone.utc) for h in range(12, 24)]   # 再寫 1/2 下半天
              + [datetime(2026, 1, 3, h, tzinfo=timezone.utc) for h in range(0, 3)])
    for stamp in stamps:
        storage.store_readings(sim._run_one_step(stamp, 3600.0), live)
    expected = [int(r["id"]) for r in storage.live_readings("WT001", limit=500)]
    archive = LiveArchive.for_storage(storage)
    archive.sync(storage, stamps[-1])
    days = {d.day: d for d in archive.days()}
    assert days["2026-01-02"].min_id < days["2026-01-01"].min_id < days["2026-01-02"].max_id, "測試前提：id 範圍重疊"
    archive.mark_hot_from(_midnight(DAY3))
    storage.delete_live_readings_before(_midnight(DAY3))
    history = LiveHistory(storage, archive)
    for limit in (1, 5, 12, 13, 36, 500):
        assert _page_all(history, "WT001", limit=limit) == expected, f"一頁 {limit} 筆"


def test_plc_typed_values() -> None:
    import numpy as np

    from server.plc_types import plc_typed, typed_column

    by_type = {}
    for tag in sp.SCADA_REGISTRY.all_tags:
        by_type.setdefault(tag.data_type, tag.id)
    ids = [by_type["REAL32"], by_type["SINT16"], "not_in_registry"]
    typed = plc_typed([17.123456789012345, 5.5, 1.0], ids)
    assert typed[0] == float(np.float32(17.123456789012345)) != 17.123456789012345
    assert typed[1] == 6.0, "整數四捨六入五成雙"
    assert typed[2] != typed[2], "不在註冊表的 tag：缺值（歸檔沒有這個欄位）"
    nan = float("nan")
    assert all(v != v for v in plc_typed([nan] * len(ids), ids)), "缺值仍是缺值"
    assert plc_typed([], []).shape == (0,)

    def column(values: List[float], kind: str) -> List[object]:
        return [None if v != v else v for v in typed_column(np.array(values), kind).tolist()]

    assert column([32767, 32768, -32768, -32769, 2.5, nan], "SINT16") == [32767.0, None, -32768.0, None, 2.0, None]
    assert column([-1, 0, 65535, 65536], "UINT16") == [None, 0.0, 65535.0, None], "超出型別範圍＝缺值"
    assert column([0, 0.3, -2, nan], "BOOL") == [0.0, 1.0, 1.0, None]
    assert column([1e39, -1e39, 1.5], "REAL32") == [None, None, 1.5], "超出 float32 範圍不變成無限大"
    with pytest.raises(ValueError):
        typed_column(np.array([1.0]), "STRING")


def test_out_of_range_values_are_the_same_in_both_tiers(tmp_path) -> None:
    """同一筆讀值不論在 SQLite 還是在日檔裡，給出去的值相同——包含超出 PLC 型別範圍的壞值。"""
    by_type = {}
    for tag in sp.SCADA_REGISTRY.all_tags:
        by_type.setdefault(tag.data_type, tag.id)
    ids = [by_type["SINT16"], by_type["UINT16"], by_type["REAL32"]]
    storage = Storage(db_path=str(tmp_path / "wind_farm.db"))
    live = storage.create_session(data_source="simulation", turbine_count=1)
    sim = WindFarmSimulator(turbine_count=1)
    bad = sim._run_one_step(datetime(2026, 1, 1, 12, tzinfo=timezone.utc), 10.0)
    bad[0]["scada"].update({ids[0]: 70000.0, ids[1]: -1.0, ids[2]: 1e39})
    storage.store_readings(bad, live)
    storage.store_readings(sim._run_one_step(datetime(2026, 1, 2, 12, tzinfo=timezone.utc), 10.0), live)
    archive = LiveArchive.for_storage(storage)
    history = LiveHistory(storage, archive)
    hot = history.readings("WT001", ids, limit=1)[0]
    archive.sync(storage, datetime(2026, 1, 2, 12, tzinfo=timezone.utc))
    archive.mark_hot_from(_midnight(DAY2))
    cold = history.readings("WT001", ids, limit=1)[0]
    assert cold.id == hot.id
    assert all(v != v for v in hot.values) and all(v != v for v in cold.values), "兩層都當成缺值"


def test_out_of_range_integers_do_not_block_the_archive(tmp_path) -> None:
    storage = Storage(db_path=str(tmp_path / "wind_farm.db"))
    live = storage.create_session(data_source="simulation", turbine_count=1)
    sim = WindFarmSimulator(turbine_count=1)
    readings = sim._run_one_step(datetime(2026, 1, 1, 12, tzinfo=timezone.utc), 10.0)
    readings[0]["scada"]["WTUR_TurSt"] = 9_999_999.0   # 超出 PLC 整數型別的範圍
    storage.store_readings(readings, live)
    storage.store_readings(sim._run_one_step(datetime(2026, 1, 2, 12, tzinfo=timezone.utc), 10.0), live)
    archive = LiveArchive.for_storage(storage)
    written = archive.sync(storage, datetime(2026, 1, 2, 12, tzinfo=timezone.utc))
    assert [(d.day, d.rows) for d in written] == [("2026-01-01", 1)], "一筆壞值不卡住整天的歸檔"
    row = archive.readings("WT001", ["WTUR_TurSt", "WGEN_GnSpd"], limit=5)[0]
    assert row.values[0] != row.values[0] and row.values[1] == row.values[1], "壞值存成缺值，其他欄位照常"


def test_history_without_an_archive_reads_sqlite_only(filled: Storage) -> None:
    rows = LiveHistory(filled, None).readings("WT001", _ids(), limit=5)
    assert [r.id for r in rows] == [int(r["id"]) for r in filled.live_readings("WT001", limit=5)]
    assert rows[0].values.shape == (len(_ids()),)


def test_a_broken_day_file_only_loses_its_own_part(filled: Storage, tmp_path) -> None:
    storage, archive = _synced(filled, tmp_path)
    history = LiveHistory(storage, archive)
    expected = [int(r["id"]) for r in storage.live_readings("WT001", limit=5000)]
    archive.mark_hot_from(_midnight(DAY2))
    (archive.root / "raw" / "2026-01-01.parquet").write_bytes(b"not parquet")
    assert _page_all(history, "WT001", limit=5000) == expected[3:], "壞掉的日檔只少它自己那一段，之後的照常"


def test_unreadable_index_is_an_error_and_sync_rebuilds_it_from_the_day_files(filled: Storage, tmp_path) -> None:
    """索引讀不出來不能當成「沒有歸檔」：那樣下一次寫索引會把舊日檔丟掉，查詢也整段漏掉（code review must-fix）。"""
    from server.live_archive import ArchiveIndexError

    storage, archive = _synced(filled, tmp_path)
    history = LiveHistory(storage, archive)
    expected = [int(r["id"]) for r in storage.live_readings("WT001", limit=5000)]
    boundary = iso_utc(datetime(2026, 1, 2, 12, tzinfo=timezone.utc))
    ranges = archive.delete_ranges(archive.state(), boundary)
    archive.mark_hot_from(boundary)
    storage.delete_archived_live_readings(ranges)
    before = archive.state()

    index = archive.root / "index.json"
    index.write_text("{broken", encoding="utf-8")
    with pytest.raises(ArchiveIndexError):
        archive.state()
    with pytest.raises(ArchiveIndexError):
        history.readings("WT001", _ids(), limit=10)     # 不退回只查 SQLite：游標會跳過歸檔那一段
    with pytest.raises(ArchiveIndexError):
        archive.mark_hot_from(boundary)
    with pytest.raises(ArchiveIndexError):
        archive.prune(1, DAY3)
    assert "error" in archive.summary() and archive.summary()["days"] == 0

    assert archive.sync(storage, CLOCK) == [], "從日檔重建索引；日檔本身不用重寫"
    after = archive.state()
    assert after.days == before.days, "舊的日檔都還在索引裡"
    assert after.archived_through == before.archived_through
    assert after.hot_from == boundary, "SQLite 裡最早的 Live 讀值時間"
    assert _page_all(history, "WT001", limit=40) == expected

    index.unlink()   # 有日檔卻沒有索引：一樣是錯誤，一樣重建
    with pytest.raises(ArchiveIndexError):
        archive.state()
    archive.sync(storage, CLOCK)
    assert archive.state() == after


def test_an_archive_from_another_database_is_refused(filled: Storage, tmp_path) -> None:
    """風場 DB 被重建、歸檔卻留著：讀值 id 會撞在一起，拒絕使用。"""
    import shutil

    from server.live_archive import ArchiveIndexError

    _, archive = _synced(filled, tmp_path)
    other_dir = tmp_path / "rebuilt"
    other_dir.mkdir()
    shutil.copytree(archive.root, other_dir / ARCHIVE_DIRNAME)
    rebuilt = Storage(db_path=str(other_dir / "wind_farm.db"))
    live = rebuilt.create_session(data_source="simulation", turbine_count=2)
    rebuilt.store_readings(WindFarmSimulator(turbine_count=2)._run_one_step(CLOCK, 10.0), live)
    assert rebuilt.reading_id_sequence() == 2
    with pytest.raises(ArchiveIndexError, match="DB 被重建過"):
        LiveArchive.for_storage(rebuilt).sync(rebuilt, CLOCK + timedelta(days=2))

    broker = _broker_on(rebuilt, other_dir, hot_days=0, archive_days=183)
    result = broker.run_retention()
    assert "error" in result and result["cleanup"]["deleted_raw"] == 0, "對不上就什麼都不刪"
    assert len(rebuilt.live_readings("WT001", limit=10)) == 1


def test_short_pages_only_happen_at_the_end(filled: Storage, tmp_path) -> None:
    """SQLite 裡還留著界線之前的列時（記了界線、還沒刪）：它們不算數，一頁仍然裝滿。"""
    storage, archive = _synced(filled, tmp_path)
    boundary = iso_utc(datetime(2026, 1, 2, 12, tzinfo=timezone.utc))
    archive.mark_hot_from(boundary)      # 沒有刪：SQLite 裡 1/1 與 1/2 上半天的 75 列還在
    history = LiveHistory(storage, archive)
    page = history._hot("WT001", _ids(), 0, None, None, 5, boundary)
    assert len(page) == 5 and all(r.timestamp >= boundary for r in page)
    assert len(history._hot("WT001", _ids(), 0, None, None, 5000, boundary)) == 72 + 4
    assert history._hot("WT001", (), page[-1].id, None, None, 1, boundary)[0].id == page[-1].id + 2  # 兩台機組交錯


def test_reader_retries_when_the_boundary_moves_mid_query(filled: Storage, tmp_path) -> None:
    """查到一半清理剛好把界線往前推並刪了列：照新的索引重查，中間那一段不會兩邊都沒給。"""
    storage, archive = _synced(filled, tmp_path)
    expected = [int(r["id"]) for r in storage.live_readings("WT001", limit=5000)]
    first = _midnight(DAY2)
    storage.delete_archived_live_readings(archive.delete_ranges(archive.state(), first))
    archive.mark_hot_from(first)
    history = LiveHistory(storage, archive)
    original = history._hot
    moved: List[str] = []

    def racing(*args, **kwargs):
        if not moved:   # 第一次查 SQLite 之前，另一條執行緒把界線推到 1/2 12:00 並刪掉那之前的列
            later = iso_utc(datetime(2026, 1, 2, 12, tzinfo=timezone.utc))
            ranges = archive.delete_ranges(archive.state(), later)
            archive.mark_hot_from(later)
            storage.delete_archived_live_readings(ranges)
            moved.append(later)
        return original(*args, **kwargs)

    history._hot = racing  # type: ignore[method-assign]  測試用的替身
    assert [r.id for r in history.readings("WT001", _ids(), limit=5000)] == expected
    assert moved, "測試前提：界線真的在查詢途中動過"


# ── 清理 ───────────────────────────────────────────────────────────────────


def test_sqlite_only_loses_rows_that_are_in_a_day_file(filled: Storage, tmp_path) -> None:
    storage, archive = _synced(filled, tmp_path)
    before = len(storage.live_readings("WT001", limit=5000))
    # 分層儲存開著：run_cleanup 自己不動 raw（由 broker 依日檔來刪）
    assert storage.run_cleanup(raw_retention_days=0, raw_tiered=True)["deleted_raw"] == 0
    assert len(storage.live_readings("WT001", limit=5000)) == before
    state = archive.state()
    assert archive.delete_ranges(state, _midnight(DAY1)) == []
    ranges = archive.delete_ranges(state, iso_utc(datetime(2026, 1, 2, 12, tzinfo=timezone.utc)))
    assert [(lower[:13], upper[:13]) for lower, upper, _ in ranges] == [
        ("2026-01-01T00", "2026-01-02T00"), ("2026-01-02T00", "2026-01-02T12")]
    assert [m for _, _, m in ranges] == [d.max_id for d in state.days]

    # 1/2 之後又寫進來一列（id 比日檔的最大 id 還大）：不在日檔裡，不能刪
    live = storage._get_conn().execute("SELECT session_id FROM turbine_data ORDER BY id LIMIT 1").fetchone()[0]
    storage.store_readings(WindFarmSimulator(turbine_count=2)._run_one_step(
        datetime(2026, 1, 2, 6, 5, tzinfo=timezone.utc), 60.0), live)
    assert storage.delete_archived_live_readings(ranges) == (3 + 72) * 2
    left = [r["timestamp"][:16] for r in storage.live_readings("WT001", end=_midnight(DAY3), limit=500)]
    assert left[0] == "2026-01-02T06:05" or "2026-01-02T06:05" in left, "還沒進日檔的那一列留著"
    assert len(left) == 72 + 1
    assert storage.delete_archived_live_readings([]) == 0
    # 超過總保留期：不管有沒有歸檔都刪（情境的讀值永遠不刪）
    assert storage.delete_live_readings_before(_midnight(DAY3)) == (72 + 1) * 2
    # 沒開分層儲存：照舊依天數刪
    assert storage.run_cleanup(raw_retention_days=0)["deleted_raw"] == 4 * 2
    assert storage._get_conn().execute("SELECT COUNT(*) FROM turbine_data").fetchone()[0] == 10


def test_index_is_plain_json(filled: Storage, tmp_path) -> None:
    _, archive = _synced(filled, tmp_path)
    raw = json.loads((archive.root / "index.json").read_text(encoding="utf-8"))
    assert set(raw) == {"archived_through", "hot_from", "days"} and raw["hot_from"] is None
    assert [set(item) for item in raw["days"]] == [
        {"day", "rows", "min_id", "max_id", "min_ts", "max_ts", "bytes"}] * 2
    assert raw["days"][0]["max_id"] < raw["days"][1]["min_id"], "平常日檔的 id 範圍一個接一個"


def test_storage_helpers_use_the_turbine_time_index(filled: Storage) -> None:
    """turbine_data 沒有純時間的索引：分層儲存的查詢要帶機組，否則每次都掃整張表（一天約 0.5 GB）。"""
    conn = filled._get_conn()
    assert filled.reading_turbine_ids() == ["WT001", "WT002"]
    assert filled.live_span("WT001", _midnight(DAY2), _midnight(DAY3))[0] == 144, "情境的 5 筆不算"
    assert filled.live_span("WT001", _midnight(date(2025, 1, 1)), _midnight(date(2025, 1, 2))) == (0, None)
    assert filled.earliest_live_reading_timestamp("WT001") == iso_utc(T0) and filled.reading_id_sequence() == 312
    assert filled.earliest_live_reading_timestamp("WT404") is None
    plan = " ".join(str(row[-1]) for row in conn.execute(
        "EXPLAIN QUERY PLAN SELECT COUNT(*), MAX(id) FROM turbine_data INDEXED BY idx_turbine_time "
        f"WHERE turbine_id = ? AND timestamp >= ? AND timestamp < ? AND {Storage._NOT_SCENARIO_SQL}",
        ("WT001", "a", "b", Storage.SCENARIO_KIND)))
    assert "idx_turbine_time (turbine_id=? AND timestamp>? AND timestamp<?)" in plan


# ── broker 的例行工作 ──────────────────────────────────────────────────────


def _broker_on(storage: Storage, tmp_path, hot_days: int, archive_days: int) -> DataBroker:
    broker = DataBroker(farm_registry=FarmRegistry(data_dir=tmp_path / "registry"))
    broker.storage = storage
    broker.raw_hot_days, broker.archive_days = hot_days, archive_days
    return broker


def test_retention_archives_then_trims_sqlite_by_the_data_clock(filled: Storage, tmp_path) -> None:
    storage = _fresh(filled, tmp_path)
    expected = [int(r["id"]) for r in storage.live_readings("WT001", limit=5000)]
    broker = _broker_on(storage, tmp_path, hot_days=1, archive_days=183)
    assert broker.raw_retention_days == 183
    result = broker.run_retention()
    assert result["archived"] == ["2026-01-01", "2026-01-02"] and result["pruned"] == []
    # 資料時鐘 1/3 00:30、熱資料 1 天：SQLite 留 1/2 00:30 之後的；這些資料是 2026 年 1 月的，離「現在」很遠，
    # 但保留期看的是資料自己的時間
    boundary = iso_utc(datetime(2026, 1, 2, 0, 30, tzinfo=timezone.utc))
    assert result["raw_delete_before"] == boundary == broker.live_archive.state().hot_from
    assert result["cleanup"]["deleted_raw"] == (3 + 3) * 2
    assert _page_all(broker.live_history, "WT001", limit=40) == expected, "清掉之後查得到的內容不變"
    again = broker.run_retention()
    assert again["archived"] == [] and again["cleanup"]["deleted_raw"] == 0, "重跑不重做"


def test_retention_keeps_the_archive_only_for_the_configured_days(filled: Storage, tmp_path) -> None:
    storage = _fresh(filled, tmp_path)
    broker = _broker_on(storage, tmp_path, hot_days=1, archive_days=1)
    result = broker.run_retention()
    assert result["pruned"] == ["2026-01-01"], "總共留 1 天：1/1 的日檔刪掉（循環保存）"
    assert [d.day for d in broker.live_archive.days()] == ["2026-01-02"]
    broker.raw_hot_days, broker.archive_days = 5, 2
    assert broker.raw_retention_days == 5, "總天數不會比熱資料天數短"


def test_rows_older_than_the_whole_retention_are_dropped_even_if_never_archived(filled: Storage, tmp_path) -> None:
    """界線之前才補寫進來的列不會進歸檔，留在 SQLite；超過總保留期時一樣要清掉，不能一直累積。"""
    storage = _fresh(filled, tmp_path)
    broker = _broker_on(storage, tmp_path, hot_days=1, archive_days=1)
    broker.run_retention()
    live = storage._get_conn().execute("SELECT session_id FROM turbine_data ORDER BY id LIMIT 1").fetchone()[0]
    late = WindFarmSimulator(turbine_count=2)
    storage.store_readings(late._run_one_step(datetime(2026, 1, 1, 12, tzinfo=timezone.utc), 60.0), live)
    storage.store_readings(late._run_one_step(CLOCK + STEP, 600.0), live)   # 資料時鐘回到 1/3
    assert len(storage.live_readings("WT001", end=_midnight(DAY2), limit=10)) == 1, "測試前提：殘留列在 SQLite 裡"
    result = broker.run_retention()
    assert result["cleanup"]["deleted_raw"] >= 2
    assert storage.live_readings("WT001", end=_midnight(DAY2), limit=10) == [], "總共只留 1 天：1/1 的殘留列清掉"


def test_retention_without_archiving_is_the_old_behaviour(filled: Storage, tmp_path) -> None:
    storage = _fresh(filled, tmp_path)
    broker = _broker_on(storage, tmp_path, hot_days=3, archive_days=0)
    assert broker.raw_retention_days == 3
    result = broker.run_retention()
    assert result["archived"] == [] and result["raw_delete_before"] is None
    assert result["cleanup"]["deleted_raw"] == STEPS * 2, "照舊：依實際時間，超過 3 天的 Live 讀值直接刪"
    assert not broker.live_archive.root.exists()


def test_retention_deletes_nothing_when_archiving_fails(filled: Storage, tmp_path, monkeypatch, capsys) -> None:
    storage = _fresh(filled, tmp_path)
    broker = _broker_on(storage, tmp_path, hot_days=0, archive_days=183)

    def boom(self: LiveArchive, store: Storage, day: date, turbines: List[str]):
        raise OSError("disk full")

    monkeypatch.setattr(LiveArchive, "_write_day", boom)
    result = broker.run_retention()
    assert result["archived"] == [] and result["cleanup"]["deleted_raw"] == 0
    assert len(storage.live_readings("WT001", limit=5000)) == STEPS, "沒歸檔成功的一列都不刪"
    assert "歸檔失敗" in capsys.readouterr().out


def test_retention_runs_one_at_a_time(filled: Storage, tmp_path, monkeypatch) -> None:
    """maintenance 執行緒與手動維護同時跑會互相蓋掉日檔與索引：第二個要等第一個做完。"""
    import threading

    storage = _fresh(filled, tmp_path)
    broker = _broker_on(storage, tmp_path, hot_days=1, archive_days=183)
    entered, release = threading.Event(), threading.Event()
    order: List[str] = []
    original = LiveArchive.sync

    def slow(self: LiveArchive, store: Storage, clock: datetime):
        order.append("start")
        entered.set()
        release.wait(5)
        result = original(self, store, clock)
        order.append("end")
        return result

    monkeypatch.setattr(LiveArchive, "sync", slow)
    first = threading.Thread(target=broker.run_retention)
    first.start()
    assert entered.wait(5)
    second = threading.Thread(target=broker.run_retention)
    second.start()
    second.join(0.3)
    assert second.is_alive() and order == ["start"], "第一個還沒做完，第二個不能進去"
    release.set()
    first.join(10)
    second.join(10)
    assert order == ["start", "end", "start", "end"]


def test_rows_not_yet_in_a_day_file_survive_a_failed_rewrite(filled: Storage, tmp_path, monkeypatch) -> None:
    """日檔寫好之後那一天又多了列、重寫日檔卻失敗：界線退到那一天，新的列不會被刪。"""
    storage = _fresh(filled, tmp_path)
    broker = _broker_on(storage, tmp_path, hot_days=0, archive_days=183)
    archive = broker.live_archive
    archive.sync(storage, CLOCK)
    live = storage._get_conn().execute("SELECT session_id FROM turbine_data ORDER BY id LIMIT 1").fetchone()[0]
    late = WindFarmSimulator(turbine_count=2)
    storage.store_readings(late._run_one_step(datetime(2026, 1, 2, 6, 5, tzinfo=timezone.utc), 60.0), live)
    storage.store_readings(late._run_one_step(CLOCK + STEP, 600.0), live)   # 資料時鐘回到 1/3
    expected = [int(r["id"]) for r in storage.live_readings("WT001", limit=5000)]

    def boom(self: LiveArchive, store: Storage, day: date, turbines: List[str]):
        raise OSError("disk full")

    monkeypatch.setattr(LiveArchive, "_write_day", boom)
    result = broker.run_retention()
    assert "disk full" in str(result["error"]) and result["raw_delete_before"] == _midnight(DAY2)
    assert result["cleanup"]["deleted_raw"] == 3 * 2, "只刪 1/1 的；1/2 的日檔少了一列，整天都先留著"
    monkeypatch.undo()
    again = broker.run_retention()
    assert again["archived"] == ["2026-01-02"] and "error" not in again
    assert sorted(_page_all(broker.live_history, "WT001", limit=50)) == expected, "那一列沒有遺失"


def test_retention_follows_the_live_clock_not_a_stray_future_row(filled: Storage, tmp_path) -> None:
    """即時模擬在跑時，保留期的「現在」是它的模擬時鐘：別的來源寫進未來時間的列不會讓半年的日檔被當成過期。"""
    storage = _fresh(filled, tmp_path)
    broker = _broker_on(storage, tmp_path, hot_days=1, archive_days=30)
    live = storage._get_conn().execute("SELECT session_id FROM turbine_data ORDER BY id LIMIT 1").fetchone()[0]
    stray = WindFarmSimulator(turbine_count=2)._run_one_step(CLOCK + timedelta(days=400), 60.0)
    storage.store_readings(stray, live)      # 最後寫入的一列在 400 天後
    assert broker._storage_data_clock(storage) == CLOCK + timedelta(days=400)
    sim = WindFarmSimulator(turbine_count=2)
    sim._sim_clock, sim._running = CLOCK, True
    broker.simulator, broker._source_kind = sim, "simulation"
    assert broker._retention_clock(storage) == CLOCK
    result = broker.run_retention()
    assert result["archived"] == ["2026-01-01", "2026-01-02"] and result["pruned"] == []
    assert result["raw_delete_before"] == iso_utc(CLOCK - timedelta(days=1))
    assert len(broker.live_archive.days()) == 2, "日檔沒有被當成過期刪掉"
    sim._running = False
    assert broker._retention_clock(storage) == CLOCK + timedelta(days=400), "即時模擬沒在跑：看 storage 裡的資料"


def test_start_clock_after_rounds_up_to_a_whole_second() -> None:
    sim = WindFarmSimulator(turbine_count=1)
    sim.start_clock_after(datetime(2026, 1, 1, 0, 0, 5, 250000, tzinfo=timezone.utc))
    assert sim.sim_clock == datetime(2026, 1, 1, 0, 0, 6, tzinfo=timezone.utc), "下一步一定在已存的資料之後"
    sim.start_clock_after(datetime(2026, 1, 1, 0, 0, 2, tzinfo=timezone.utc))
    assert sim.sim_clock == datetime(2026, 1, 1, 0, 0, 6, tzinfo=timezone.utc), "只往前調"
    sim.start_clock_after(datetime(2026, 1, 1, 8, 0, 9, tzinfo=timezone(timedelta(hours=8))))
    assert sim.sim_clock == datetime(2026, 1, 1, 0, 0, 9, tzinfo=timezone.utc)


def test_fresh_live_run_continues_after_stored_data_that_is_ahead_of_now(tmp_path) -> None:
    """用過時間倍率之後風場狀態重來：新的讀值接在已有的 Live 資料之後，時間不往回。"""
    from server.models import DataSourceConfig, DataSourceMode, SimulationConfig

    def start() -> DataBroker:
        broker = DataBroker(farm_registry=FarmRegistry(data_dir=tmp_path))
        broker.start(DataSourceConfig(mode=DataSourceMode.SIMULATION), SimulationConfig(turbineCount=1, timeStep=1.0))
        return broker

    first = start()
    sim = first.simulator
    assert sim is not None
    sim.stop_live_loop()
    ahead = (datetime.now(timezone.utc) + timedelta(days=40)).replace(microsecond=0, second=5)
    sim._running = True
    for i in range(1, 16):   # 加速跑到 40 天後
        sim._sim_clock = ahead + timedelta(seconds=i)
        first._on_sim_data(sim._run_one_step(sim._sim_clock, 1.0))
    latest = parse_iso(first.storage.last_live_reading_timestamp("WT001"))
    first.stop()

    second = start()   # 沒開續跑：風場從頭開始
    try:
        assert second.live_restored is False and second.live_epoch != first.live_epoch
        restarted = second.simulator
        assert restarted is not None
        import time as _t
        _t.sleep(0.3)
        restarted.stop_live_loop()
        assert restarted.sim_clock is not None and restarted.sim_clock > latest, "時鐘接在已有的資料之後"
        restarted._running = True
        for i in range(1, 25):
            moment = restarted.sim_clock + timedelta(seconds=1)
            restarted._sim_clock = moment
            second._on_sim_data(restarted._run_one_step(moment, 1.0))
        stamps = [parse_iso(str(r["timestamp"])) for r in second.storage.live_readings("WT001", limit=100)]
        assert stamps == sorted(stamps) and len(set(stamps)) == len(stamps), "Live 的歷史在時間上不往回"
        slots = [int(ts.timestamp() // 10) for ts in stamps]
        assert len(set(slots)) == len(slots), "接續的那個 10 秒時段不重複寫"
    finally:
        second.stop()
