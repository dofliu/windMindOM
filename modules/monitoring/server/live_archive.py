"""即時讀值的長期保存（WMOM-20261125-03-c，分層儲存）。

SQLite 的 ``turbine_data`` 每列約 4 KB（整包 SCADA 值存成 JSON），14 台機組一個月約 15 GB，只適合留最近幾天。
較舊的 Live 讀值依 UTC 日期轉成 Parquet 檔（每列約 0.13 KB），SQLite 那邊再刪掉：

```
<風場目錄>/live_archive/
  index.json              每個日檔的日期、列數、id 與時間範圍；歸檔到哪、SQLite 從哪開始
  raw/2026-11-26.parquet  該日全部 Live 讀值；每台機組一個 row group，組內依 id 排序
```

- 欄位：``id``、``timestamp``、``turbine_id``、``session_id``，加上 SCADA 註冊表的全部 tag（欄名＝tag id，
  型別依 PLC 資料型別，見 ``server/plc_types.py``）。模擬器內部量也留著——這是自己的歷史，給出去時由呼叫端
  挑欄位。
- 只歸檔 Live（不含情境 session：那是凍結的出題資料集，留在 SQLite 直到情境被刪）。
- 一天要「過完」才歸檔：資料時鐘已經進到隔天。用資料自己的時間，不用實際時間——時間倍率大於 1 之後模擬時鐘
  跑在實際時間前面。
- 兩個界線都記在索引裡：
  - ``archived_through``：這一刻之前的日子都處理過了（有 Live 讀值的都有日檔）。
  - ``hot_from``：SQLite 已經刪到這一刻。查詢時這之前的歸檔給、之後的 SQLite 給，每一列只給一次。
- SQLite 那邊只刪「確定在日檔裡」的列：每一天只刪 id 不大於該日檔最大 id 的（``delete_ranges``）。
- 循環保存＝刪掉最舊的日檔。
- 索引讀不出來時不當成「沒有歸檔」：寫的一方（``sync``）從日檔重建索引，讀的一方報錯——當成沒有歸檔的話，
  下一次寫索引會把舊日檔丟掉，查詢也會整段漏掉。

已知的限制：時間早於 ``hot_from`` 的列若之後才寫進 Live（把很久以前的資料補進來），不會進歸檔、也查不到，
留在 SQLite 直到超過保留期才刪。刪掉風場 DB 時要一併刪掉 ``live_archive/``（``sync`` 會檢查並拒絕）。
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from server import scenario_pack as sp
from server.plc_types import typed_column
from server.storage import Storage
from simulator.physics.scada_registry import SCADA_REGISTRY
from simulator.time_utils import iso_utc, parse_iso

logger = logging.getLogger(__name__)

ARCHIVE_DIRNAME = "live_archive"
_INDEX_FILE = "index.json"
_RAW_DIR = "raw"
_TS_TYPE = pa.timestamp("us", tz="UTC")
_INDEX_READ_TRIES = 3


class ArchiveIndexError(RuntimeError):
    """歸檔的索引存在但讀不出來，或和風場 DB 對不上。"""


@dataclass(frozen=True)
class ArchivedDay:
    """一個已歸檔的日檔。

    Attributes:
        day: UTC 日期（``YYYY-MM-DD``）。
        rows: 列數。
        min_id: 最小的 ``turbine_data.id``。
        max_id: 最大的 ``turbine_data.id``。
        min_ts: 最早的讀值時間（``iso_utc``）。
        max_ts: 最晚的讀值時間（``iso_utc``）。
        bytes: 檔案大小。
    """

    day: str
    rows: int
    min_id: int
    max_id: int
    min_ts: str
    max_ts: str
    bytes: int


@dataclass(frozen=True)
class ArchiveState:
    """歸檔的索引內容。

    Attributes:
        days: 日檔，依日期排序。
        archived_through: 這一刻（``iso_utc``）之前的日子都處理過了；還沒歸檔過為 None。
        hot_from: SQLite 已經刪到這一刻（``iso_utc``）；還沒刪過為 None。
    """

    days: Tuple[ArchivedDay, ...] = ()
    archived_through: Optional[str] = None
    hot_from: Optional[str] = None


@dataclass(frozen=True)
class LiveReading:
    """一筆 Live 讀值（不論在哪一層）。``values`` 依呼叫端要的 tag id 順序，PLC 資料型別的值（缺值為 NaN）。"""

    id: int
    timestamp: str
    turbine_id: str
    values: np.ndarray


def _schema() -> pa.Schema:
    tags = [pa.field(tag.id, sp._ARROW_TYPES[tag.data_type]) for tag in SCADA_REGISTRY.all_tags]
    return pa.schema([
        pa.field("id", pa.int64()), pa.field("timestamp", _TS_TYPE), pa.field("turbine_id", pa.string()),
        pa.field("session_id", pa.int64()), *tags,
    ])


def day_start(day: date) -> datetime:
    """一個 UTC 日的 00:00（tz-aware）。"""
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def _day_bounds(day: date) -> Tuple[str, str]:
    start = day_start(day)
    return iso_utc(start), iso_utc(start + timedelta(days=1))


class LiveArchive:
    """一座風場的 Live 讀值歸檔。

    寫（``sync`` / ``mark_hot_from`` / ``prune``）同一時間只能有一方：由 ``DataBroker.run_retention`` 的鎖保證。
    讀可以在任何執行緒。
    """

    def __init__(self, root: Path) -> None:
        """建立（不碰磁碟；第一次寫入時才建目錄）。

        Args:
            root: 歸檔目錄（``<風場目錄>/live_archive``）。
        """
        self._root = Path(root)

    @classmethod
    def for_storage(cls, storage: Storage) -> "LiveArchive":
        """風場 DB 旁邊的歸檔。"""
        return cls(Path(storage.db_path).with_name(ARCHIVE_DIRNAME))

    @property
    def root(self) -> Path:
        """歸檔目錄。"""
        return self._root

    # ── 索引 ───────────────────────────────────────────────────────────────

    def _file(self, day: str) -> Path:
        return self._root / _RAW_DIR / f"{day}.parquet"

    def _day_files(self) -> List[Path]:
        raw = self._root / _RAW_DIR
        return sorted(raw.glob("*.parquet")) if raw.is_dir() else []

    def state(self) -> ArchiveState:
        """讀索引。

        Returns:
            索引內容；索引與日檔都不存在＝還沒有歸檔，回空的狀態。

        Raises:
            ArchiveIndexError: 索引存在但讀不出來，或有日檔卻沒有索引。不能當成「沒有歸檔」。
        """
        path = self._root / _INDEX_FILE
        problem: Exception = FileNotFoundError(str(path))
        for attempt in range(_INDEX_READ_TRIES):
            if not path.is_file():
                if self._day_files():
                    raise ArchiveIndexError(f"{self._root} 有日檔但沒有索引")
                return ArchiveState()
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                days = tuple(sorted((ArchivedDay(**item) for item in raw["days"]), key=lambda d: d.day))
                through, hot = raw.get("archived_through"), raw.get("hot_from")
                return ArchiveState(days=days, archived_through=iso_utc(parse_iso(through)) if through else None,
                                    hot_from=iso_utc(parse_iso(hot)) if hot else None)
            except OSError as exc:  # 寫的一方正在換檔（Windows 上讀寫同時會被拒絕）：等一下再試
                problem = exc
                time.sleep(0.02 * (attempt + 1))
            except (ValueError, TypeError, KeyError) as exc:
                problem = exc
                break
        raise ArchiveIndexError(f"Live 歸檔的索引讀不出來：{problem!r}")

    def _write_state(self, state: ArchiveState) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / _INDEX_FILE
        tmp = path.with_name(path.name + ".tmp")
        payload = {"archived_through": state.archived_through, "hot_from": state.hot_from,
                   "days": [asdict(d) for d in sorted(state.days, key=lambda d: d.day)]}
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)

    def rebuild_index(self, storage: Storage) -> ArchiveState:
        """索引讀不出來時，從日檔重建。

        ``archived_through`` 取最後一個日檔的隔日（日檔是依日期由舊到新寫的，中途失敗就停，所以更早的日子
        都處理過）；``hot_from`` 取 SQLite 裡最早的 Live 讀值時間（更早的列已經刪掉，只在日檔裡）。

        Args:
            storage: 風場的 storage。

        Returns:
            重建後的索引內容（已寫回 ``index.json``）。
        """
        days: List[ArchivedDay] = []
        for path in self._day_files():
            try:
                table = pq.read_table(path, columns=["id", "timestamp"])
                date.fromisoformat(path.stem)
            except (OSError, ValueError, pa.ArrowException) as exc:
                logger.error("Live 歸檔：日檔 %s 讀不出來，重建索引時略過：%s", path.name, exc)
                continue
            if table.num_rows == 0:
                continue
            ids, stamps = table.column("id"), table.column("timestamp")
            days.append(ArchivedDay(
                day=path.stem, rows=table.num_rows, min_id=int(pc.min(ids).as_py()), max_id=int(pc.max(ids).as_py()),
                min_ts=iso_utc(pc.min(stamps).as_py()), max_ts=iso_utc(pc.max(stamps).as_py()),
                bytes=path.stat().st_size))
        through: Optional[str] = None
        hot: Optional[str] = None
        if days:
            through = _day_bounds(date.fromisoformat(max(d.day for d in days)))[1]
            earliest = [ts for ts in (storage.earliest_live_reading_timestamp(t)
                                      for t in storage.reading_turbine_ids()) if ts]
            hot = min(min(earliest), through) if earliest else through
        state = ArchiveState(days=tuple(sorted(days, key=lambda d: d.day)), archived_through=through, hot_from=hot)
        self._write_state(state)
        logger.warning("Live 歸檔的索引已從 %d 個日檔重建（歸檔到 %s，SQLite 從 %s 開始）", len(days), through, hot)
        return state

    def days(self) -> List[ArchivedDay]:
        """已歸檔的日檔，依日期排序。"""
        return list(self.state().days)

    def total_bytes(self) -> int:
        """全部日檔的大小。"""
        return sum(d.bytes for d in self.days())

    def summary(self) -> Dict[str, object]:
        """給管理端看的摘要：幾個日檔、幾列、多大、涵蓋哪幾天；索引讀不出來時帶 ``error``。"""
        try:
            state = self.state()
        except ArchiveIndexError as exc:
            return {"days": 0, "rows": 0, "bytes": 0, "first_day": None, "last_day": None,
                    "archived_through": None, "hot_from": None, "error": str(exc)}
        return {
            "days": len(state.days),
            "rows": sum(d.rows for d in state.days),
            "bytes": sum(d.bytes for d in state.days),
            "first_day": state.days[0].day if state.days else None,
            "last_day": state.days[-1].day if state.days else None,
            "archived_through": state.archived_through,
            "hot_from": state.hot_from,
        }

    # ── 寫入 ───────────────────────────────────────────────────────────────

    def _write_day(self, storage: Storage, day: date, turbines: Sequence[str]) -> Optional[ArchivedDay]:
        """把一個 UTC 日的 Live 讀值寫成日檔（已存在就重寫）；那天沒有 Live 讀值時回 None、不建檔。"""
        lower, upper = _day_bounds(day)
        conn = storage._get_conn()
        schema = _schema()
        tags = list(SCADA_REGISTRY.all_tags)
        tag_ids = [tag.id for tag in tags]
        path = self._file(day.isoformat())
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        rows = 0
        ids_min: List[int] = []
        ids_max: List[int] = []
        ts_min: List[str] = []
        ts_max: List[str] = []
        writer = pq.ParquetWriter(tmp, schema, compression="zstd")
        try:
            for turbine_id in turbines:
                # 走 (turbine_id, timestamp) 索引；turbine_data 沒有純時間的索引
                data: List[sqlite3.Row] = conn.execute(
                    "SELECT id, timestamp, turbine_id, session_id, scada_json FROM turbine_data "
                    "INDEXED BY idx_turbine_time "
                    f"WHERE turbine_id = ? AND timestamp >= ? AND timestamp < ? AND {Storage._NOT_SCENARIO_SQL} "
                    "ORDER BY id", (turbine_id, lower, upper, Storage.SCENARIO_KIND)).fetchall()
                if not data:
                    continue
                values = np.vstack([sp.scada_values(row["scada_json"], tag_ids) for row in data])
                stamps = [parse_iso(str(row["timestamp"])) for row in data]
                ids = [int(row["id"]) for row in data]
                columns: Dict[str, pa.Array] = {
                    "id": pa.array(ids, type=pa.int64()),
                    "timestamp": pa.array(stamps, type=_TS_TYPE),
                    "turbine_id": pa.array([turbine_id] * len(data), type=pa.string()),
                    "session_id": pa.array([row["session_id"] for row in data], type=pa.int64()),
                }
                for c, tag in enumerate(tags):
                    # 先轉成 PLC 型別能表示的值（超出範圍＝缺值）：和 SQLite 那一層查詢時的轉換同一套
                    columns[tag.id] = sp._to_arrow(typed_column(values[:, c], tag.data_type),
                                                   sp._ARROW_TYPES[tag.data_type])
                # 每台機組一個 row group：查一台機組時只讀它的那一組
                writer.write_table(pa.table(columns, schema=schema), row_group_size=len(data))
                rows += len(data)
                ids_min.append(ids[0])
                ids_max.append(ids[-1])
                ts_min.append(iso_utc(min(stamps)))
                ts_max.append(iso_utc(max(stamps)))
        except BaseException:
            writer.close()
            tmp.unlink(missing_ok=True)
            raise
        writer.close()
        if rows == 0:
            tmp.unlink(missing_ok=True)
            return None
        os.replace(tmp, path)
        return ArchivedDay(day=day.isoformat(), rows=rows, min_id=min(ids_min), max_id=max(ids_max),
                           min_ts=min(ts_min), max_ts=max(ts_max), bytes=path.stat().st_size)

    def sync(self, storage: Storage, data_clock: datetime) -> List[ArchivedDay]:
        """把已經過完的日子歸檔（還沒歸檔的，或 SQLite 裡又多了列的），並推進 ``archived_through``。

        「過完」＝``data_clock`` 已經進到之後的日子。依日期由舊到新做；中途出錯就停在那一天
        （``archived_through`` 退到那一天，沒有成功歸檔的日子不會被當成歸檔過），例外往上丟，下次再試。
        索引讀不出來時先從日檔重建。

        Args:
            storage: 風場的 storage。
            data_clock: 資料時鐘（tz-aware）。

        Returns:
            這次新寫（或重寫）的日檔。

        Raises:
            ArchiveIndexError: 歸檔和這個風場 DB 對不上（DB 被重建過，歸檔卻是舊的）。
        """
        try:
            state = self.state()
        except ArchiveIndexError as exc:
            logger.error("%s；從日檔重建索引", exc)
            state = self.rebuild_index(storage)
        if state.days and max(d.max_id for d in state.days) > storage.reading_id_sequence():
            raise ArchiveIndexError(
                f"{self._root} 的讀值 id 比風場 DB 發過的還大：DB 被重建過。請把這個目錄移走再重新開始歸檔")
        today = data_clock.astimezone(timezone.utc).date()
        turbines = storage.reading_turbine_ids()
        earliest = [ts for ts in (storage.earliest_live_reading_timestamp(t) for t in turbines) if ts]
        if not earliest:
            return []
        known = {d.day: d for d in state.days}
        hot_from = parse_iso(state.hot_from) if state.hot_from else None
        written: List[ArchivedDay] = []
        day = parse_iso(min(earliest)).date()
        failed = False
        try:
            while day < today:
                # SQLite 已經刪進這一天（或刪過了）：手上不是完整的一天，不能拿來重寫日檔
                if hot_from is None or day_start(day) >= hot_from:
                    lower, upper = _day_bounds(day)
                    spans = [storage.live_span(t, lower, upper) for t in turbines]
                    rows = sum(n for n, _ in spans)
                    max_id = max((m for _, m in spans if m is not None), default=None)
                    entry = known.get(day.isoformat())
                    if rows and (entry is None or entry.rows != rows or entry.max_id != max_id):
                        fresh = self._write_day(storage, day, turbines)
                        if fresh is not None:
                            known[fresh.day] = fresh
                            written.append(fresh)
                day += timedelta(days=1)
        except BaseException:
            failed = True
            raise
        finally:
            # 走到哪記到哪：day 之前的日子都處理完了。正常結束時界線只往前（資料時鐘可能暫時往回）；
            # 出錯時退到出錯的那一天，那天的日檔可能少了後來才寫進來的列
            through = iso_utc(day_start(day))
            if not failed and state.archived_through and state.archived_through > through:
                through = state.archived_through
            if written or through != state.archived_through:
                self._write_state(ArchiveState(days=tuple(known.values()), archived_through=through,
                                               hot_from=state.hot_from))
        return written

    def delete_ranges(self, state: ArchiveState, before: str) -> List[Tuple[str, str, int]]:
        """SQLite 裡可以刪掉的 Live 讀值：每個日檔一段（時間範圍、該日檔最大的 id）。

        只列「確定在日檔裡」的：每一天只到該日檔的最大 id 為止——那天後來才寫進來、還沒進日檔的列不在內。

        Args:
            state: 索引內容。
            before: 只列時間早於這一刻的（``iso_utc``；通常就是即將設定的 ``hot_from``）。

        Returns:
            ``[(時間下限（含）, 時間上限（不含）, 最大 id), ...]``，依日期排序。
        """
        ranges: List[Tuple[str, str, int]] = []
        for entry in state.days:
            lower, upper = _day_bounds(date.fromisoformat(entry.day))
            if lower >= before:
                break
            ranges.append((lower, min(upper, before), entry.max_id))
        return ranges

    def mark_hot_from(self, moment: str) -> None:
        """記下 SQLite 已經刪到哪一刻（只往前）。要在刪除**之前**呼叫：先讓查詢改從歸檔拿這一段，再刪。

        Args:
            moment: ``iso_utc`` 時間；不得晚於 ``archived_through``。

        Raises:
            ValueError: 這一刻之前還有沒歸檔的資料。
            ArchiveIndexError: 索引讀不出來。
        """
        state = self.state()
        moment = iso_utc(parse_iso(moment))
        if state.archived_through is None or moment > state.archived_through:
            raise ValueError("這一刻之前還有沒歸檔的 Live 讀值，不能刪")
        if state.hot_from is None or moment > state.hot_from:
            self._write_state(ArchiveState(days=state.days, archived_through=state.archived_through, hot_from=moment))

    def prune(self, keep_days: int, today: date) -> List[str]:
        """刪掉比 ``keep_days`` 天更舊的日檔（循環保存）。

        Args:
            keep_days: 保留幾天；≤ 0 表示不刪。
            today: 目前的日期（資料的時間）。

        Returns:
            被刪掉的日期。

        Raises:
            ArchiveIndexError: 索引讀不出來。
        """
        if keep_days <= 0:
            return []
        cutoff = (today - timedelta(days=keep_days)).isoformat()
        state = self.state()
        removed = [d.day for d in state.days if d.day < cutoff]
        if not removed:
            return []
        # 先改索引：讀的一方不會去開要刪的檔
        self._write_state(ArchiveState(days=tuple(d for d in state.days if d.day >= cutoff),
                                       archived_through=state.archived_through, hot_from=state.hot_from))
        for day in removed:
            self._file(day).unlink(missing_ok=True)
        return removed

    # ── 讀取 ───────────────────────────────────────────────────────────────

    def _read_day(self, entry: ArchivedDay, turbine_id: str, tag_ids: Sequence[str], after_id: int,
                  start_dt: Optional[datetime], end_dt: Optional[datetime], limit: int) -> List[LiveReading]:
        """一個日檔裡符合條件的讀值，id 最小的 ``limit`` 筆。"""
        path = self._file(entry.day)
        try:
            available = set(pq.read_schema(path).names)
            wanted = [t for t in tag_ids if t in available]
            table = pq.read_table(path, columns=["id", "timestamp", *wanted],
                                  filters=[("turbine_id", "=", turbine_id), ("id", ">", after_id)])
        except (OSError, pa.ArrowException) as exc:
            logger.warning("Live 歸檔的日檔 %s 讀不出來：%s", entry.day, exc)
            return []
        if table.num_rows == 0:
            return []
        ids = table.column("id").to_numpy()
        stamps = table.column("timestamp").to_pylist()
        missing = np.full(table.num_rows, np.nan)
        columns: Dict[str, np.ndarray] = {}
        for name in wanted:
            column = table.column(name)
            if pa.types.is_boolean(column.type):
                column = pc.cast(column, pa.int8())
            columns[name] = pc.cast(column, pa.float64()).to_numpy(zero_copy_only=False)  # 缺值（null）→ NaN
        matrix = (np.column_stack([columns.get(tag_id, missing) for tag_id in tag_ids]) if tag_ids
                  else np.empty((table.num_rows, 0)))
        out: List[LiveReading] = []
        for i in np.argsort(ids, kind="stable"):
            stamp = stamps[i]
            if (start_dt is not None and stamp < start_dt) or (end_dt is not None and stamp >= end_dt):
                continue
            out.append(LiveReading(id=int(ids[i]), timestamp=iso_utc(stamp), turbine_id=turbine_id,
                                   values=matrix[i].copy()))
            if len(out) >= limit:
                break
        return out

    def readings(self, turbine_id: str, tag_ids: Sequence[str], after_id: int = 0, start: Optional[str] = None,
                 end: Optional[str] = None, limit: int = 1000,
                 days: Optional[Sequence[ArchivedDay]] = None) -> List[LiveReading]:
        """一台機組在歸檔裡的讀值，依 id 遞增。

        日檔通常依 id 一個接一個；id 範圍重疊時（同一段時間的列分兩次寫進來）會多讀幾個檔再合併，
        結果仍是全部符合條件的列裡 id 最小的 ``limit`` 筆。

        Args:
            turbine_id: 機組 ID。
            tag_ids: 要哪些 tag（結果的 ``values`` 依此順序）。
            after_id: 只取 id 大於它的列。
            start: 時間下限（含，``iso_utc``）。
            end: 時間上限（不含，``iso_utc``）。
            limit: 最多幾筆。
            days: 要查的日檔（呼叫端已經讀過索引時給，讓同一次查詢從頭到尾用同一份索引）；None＝現在讀。

        Returns:
            讀值。

        Raises:
            ArchiveIndexError: 沒給 ``days``、索引又讀不出來。
        """
        start_dt = parse_iso(start) if start else None
        end_dt = parse_iso(end) if end else None
        start_key = iso_utc(start_dt) if start_dt else None
        end_key = iso_utc(end_dt) if end_dt else None
        entries = [d for d in sorted(days if days is not None else self.state().days,
                                     key=lambda d: (d.min_id, d.day))
                   if d.max_id > after_id
                   and not (start_key and d.max_ts < start_key) and not (end_key and d.min_ts >= end_key)]
        out: List[LiveReading] = []
        for entry in entries:
            if len(out) >= limit:
                out.sort(key=lambda r: r.id)
                if entry.min_id > out[limit - 1].id:
                    break  # 之後的日檔 id 都更大，不會擠進前 limit 筆
            out.extend(self._read_day(entry, turbine_id, tag_ids, after_id, start_dt, end_dt, limit))
        out.sort(key=lambda r: r.id)
        return out[:limit]
