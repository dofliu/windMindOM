"""monitoring 的時間戳慣例（WMOM-20261021-03-c，EPIC-DS Phase 1b-c）。

慣例：

- **內部一律 tz-aware UTC**（``utc_now()``），不再用 naive 的 ``datetime.now()``。
- **字串格式固定**：``YYYY-MM-DDTHH:MM:SS.ffffff+00:00``（``iso_utc``）。SQLite 以字串字典序比較
  時間（``timestamp >= ?``），長度與後綴一致才保證字典序＝時間序；不用 ``Z`` 後綴（``Z`` 的字元碼大於
  ``.`` 與數字，同一秒內的字典序會顛倒）。SQLite 的 ``strftime('%s', ...)`` 認得 ``+00:00`` 後綴。
- **naive 輸入視為伺服器本地時間**：本次之前 monitoring 一律寫 naive 的 ``datetime.now()``（伺服器
  本地時間），既有 DB 列、API 呼叫端傳入的 naive 字串都依此解讀再轉 UTC（Python ``astimezone()``
  對 naive 值的預設語意）。

本模組放在 ``simulator/``（最底層）：simulator 與 server 都能匯入；server 以
``from simulator.time_utils import ...``（sys.path 注入模式）或相對匯入（套件模式）取得。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

UTC = timezone.utc
# URL query 未編碼的 "+00:00" 會被解成空格（"...05:00:00 00:00"）：視為 "+"
_SPACE_OFFSET = re.compile(r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?) (\d{2}:\d{2})$")


def utc_now() -> datetime:
    """現在時刻（tz-aware UTC）。

    Returns:
        ``datetime``，``tzinfo`` 為 UTC。
    """
    return datetime.now(UTC)


def to_utc(dt: datetime) -> datetime:
    """轉成 tz-aware UTC；naive 值視為伺服器本地時間（既有資料與舊 API 呼叫端的語意）。

    Args:
        dt: 任意 ``datetime``。

    Returns:
        tz-aware UTC ``datetime``。
    """
    return dt.astimezone(UTC)


def to_local_naive(dt: datetime) -> datetime:
    """轉成伺服器本地時間的 naive ``datetime``（需要「當地時刻」的物理輸入用，例：日夜 / 季節循環）。

    Args:
        dt: 任意 ``datetime``；naive 值原樣回傳（已是本地時間）。

    Returns:
        naive 本地時間 ``datetime``。
    """
    if dt.tzinfo is None:
        return dt
    return dt.astimezone().replace(tzinfo=None)


def iso_utc(dt: Optional[datetime] = None) -> str:
    """固定格式的 UTC ISO 字串：``YYYY-MM-DDTHH:MM:SS.ffffff+00:00``。

    Args:
        dt: 要格式化的時刻；None＝現在。

    Returns:
        ISO 字串（長度固定 32）。
    """
    return to_utc(dt if dt is not None else utc_now()).isoformat(timespec="microseconds")


def parse_iso(value: str) -> datetime:
    """解析 ISO 時間字串為 tz-aware UTC；接受 ``Z`` 後綴、任意時區後綴與 naive（視為本地時間）。

    URL query 裡未編碼的 ``+00:00`` 會變成空格（``...05:00:00 00:00``），也視為 ``+``。

    Args:
        value: ISO 8601 字串。

    Returns:
        tz-aware UTC ``datetime``。

    Raises:
        ValueError: 不是可解析的 ISO 時間字串。
    """
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    else:
        text = _SPACE_OFFSET.sub(r"\1+\2", text)
    return to_utc(datetime.fromisoformat(text))


def normalize_iso(value: Optional[str]) -> Optional[str]:
    """把外部傳入的時間字串（API query、事件時間戳）正規化成 ``iso_utc`` 格式。

    無法解析的字串原樣回傳（維持既有「直接拿字串比較」的行為，不在此改變錯誤處理）。

    Args:
        value: ISO 字串或 None。

    Returns:
        正規化後的字串；None / 空字串原樣回傳。
    """
    if not value:
        return value
    try:
        return iso_utc(parse_iso(value))
    except ValueError:
        return value
