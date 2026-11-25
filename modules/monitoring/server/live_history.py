"""Live 讀值的兩層查詢（WMOM-20261125-03-c）：較舊的在歸檔（每日 Parquet），最近幾天的在 SQLite。

呼叫端（對外唯讀 API、出發前準備卡）不必知道資料在哪一層：同一個游標（``turbine_data.id``）依寫入順序
往後走。兩層以歸檔索引的 ``hot_from`` 分界——那一刻之前的讀值由歸檔給、之後的由 SQLite 給，所以已歸檔但
SQLite 還沒刪的列只會給一次。

兩層給的值一樣：歸檔照 PLC 資料型別存，SQLite 那一層的值（JSON 裡的 float64）在這裡先轉成同樣的型別
（``server/plc_types.py``）。同一個 10 分鐘窗的統計因此不會因為資料搬進歸檔而改變。

歸檔的索引讀不出來時這裡會丟 ``ArchiveIndexError``，不退回「只查 SQLite」：那樣游標會直接跳過歸檔的那一段，
呼叫端以為沒有資料。
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from server import scenario_pack as sp
from server.live_archive import ArchiveState, LiveArchive, LiveReading
from server.plc_types import plc_typed
from server.storage import Storage
from simulator.time_utils import normalize_iso

__all__ = ["LiveHistory", "LiveReading", "plc_typed"]

_RETRIES = 3


class LiveHistory:
    """一座風場的 Live 讀值（歸檔＋SQLite）。"""

    def __init__(self, storage: Storage, archive: Optional[LiveArchive]) -> None:
        """建立。

        Args:
            storage: 風場的 storage（最近幾天的讀值）。
            archive: 歸檔；None＝沒有歸檔，只查 SQLite。
        """
        self.storage = storage
        self.archive = archive

    def _hot(self, turbine_id: str, tag_ids: Sequence[str], after_id: int, start: Optional[str], end: Optional[str],
             limit: int, hot_from: Optional[str]) -> List[LiveReading]:
        """SQLite 那一層的讀值（時間不早於 ``hot_from``），id 最小的 ``limit`` 筆。

        界線之前的列在查完之後才濾掉（不放進 SQL 的時間條件：那會改走時間索引，翻舊資料時每一頁都要把
        之後所有的列排序一遍）。被濾掉的列不算數：不夠一頁就接著往後拿，所以只有真的沒有更多列時才會少於
        ``limit``。
        """
        out: List[LiveReading] = []
        cursor = after_id
        while len(out) < limit:
            want = limit - len(out)
            rows = self.storage.live_readings(turbine_id, after_id=cursor, start=start, end=end, limit=want)
            for row in rows:
                cursor = int(row["id"])
                timestamp = str(row["timestamp"])
                if hot_from is not None and timestamp < hot_from:
                    continue  # 這一段歸檔給（界線之前才補寫進來的列：不給，否則和歸檔重複或順序錯亂）
                out.append(LiveReading(id=cursor, timestamp=timestamp, turbine_id=str(row["turbine_id"]),
                                       values=plc_typed(sp.scada_values(row["scada_json"], tag_ids), tag_ids)))
            if len(rows) < want:
                break
        return out

    def _once(self, state: ArchiveState, turbine_id: str, tag_ids: Sequence[str], after_id: int,
              start: Optional[str], end: Optional[str], limit: int) -> List[LiveReading]:
        """照一份索引查一次。"""
        hot_from = state.hot_from
        cold: List[LiveReading] = []
        if self.archive is not None and hot_from is not None and (start is None or start < hot_from):
            cold = self.archive.readings(turbine_id, tag_ids, after_id=after_id, start=start,
                                         end=min(end, hot_from) if end else hot_from, limit=limit, days=state.days)
        if end is not None and hot_from is not None and end <= hot_from:
            return cold  # 整段都在歸檔那一層
        if len(cold) >= limit:
            # 歸檔那一層已經裝滿一頁。SQLite 的 id 通常都比較大：先只看它的第一列，確定沒有更小的 id 才省掉整頁查詢
            first = self._hot(turbine_id, (), after_id, start, end, 1, hot_from)
            if not first or first[0].id > cold[-1].id:
                return cold
        hot = self._hot(turbine_id, tag_ids, after_id, start, end, limit, hot_from)
        if not cold:
            return hot
        return sorted(cold + hot, key=lambda r: r.id)[:limit]

    def readings(self, turbine_id: str, tag_ids: Sequence[str], after_id: int = 0, start: Optional[str] = None,
                 end: Optional[str] = None, limit: int = 1000) -> List[LiveReading]:
        """一台機組的 Live 讀值，依寫入順序（id 遞增）。少於 ``limit`` 筆表示沒有更多了。

        Args:
            turbine_id: 機組 ID。
            tag_ids: 要哪些 tag（結果的 ``values`` 依此順序）。
            after_id: 游標：只取 id 大於它的列（0＝從頭）。
            start: 時間下限（含，任何 ISO 格式）；None＝不限。
            end: 時間上限（不含）；None＝不限。
            limit: 最多幾筆。

        Returns:
            讀值。

        Raises:
            ArchiveIndexError: 歸檔的索引讀不出來。
        """
        start = normalize_iso(start) if start else None
        end = normalize_iso(end) if end else None
        if self.archive is None:
            return self._hot(turbine_id, tag_ids, after_id, start, end, limit, None)
        state = self.archive.state()
        out: List[LiveReading] = []
        for _ in range(_RETRIES):
            out = self._once(state, turbine_id, tag_ids, after_id, start, end, limit)
            # 查到一半界線被往前推（清理剛好在跑）：兩層之間那一段可能兩邊都沒給，照新的索引重查
            latest = self.archive.state()
            if latest.hot_from == state.hot_from:
                break
            state = latest
        return out
