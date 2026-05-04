"""SQLite connection helpers — WAL + busy_timeout 設定統一。

對應 issue：WMOM-20260504-09（修 storage / farm_registry 並發 lock）

問題背景：
SQLite 預設 ``journal_mode=DELETE`` + ``busy_timeout=0``，遇到鎖立刻 raise
``OperationalError: database is locked``。多個 thread 同時操作（FastAPI handler
+ DataBroker write + maintenance downsampling + simulator）很容易撞鎖。

解法：每個 connection 開時就設好 WAL mode 與 5 秒 busy_timeout。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def open_sqlite(db_path: str | Path, *, timeout: float = 10.0) -> sqlite3.Connection:
    """開啟 SQLite connection 並設定並發友善的 PRAGMA。

    Args:
        db_path: SQLite DB 路徑
        timeout: Python sqlite3 module 層級的 OS 等待秒數（預設 10s）

    Returns:
        Connection with WAL journal mode, NORMAL synchronous, 5000ms busy_timeout
        and ``sqlite3.Row`` factory（可用 ``row["col"]`` 取值）。

    Notes:
        - ``journal_mode=WAL`` 是**持久化在 DB header**，第一個 connection 設定
          後就會一直生效，後續 connection 即使不設也是 WAL。但每次都呼叫一次
          PRAGMA 是 idempotent（無副作用），保險起見保留。
        - ``synchronous=NORMAL`` 是 WAL 模式下的安全折衷（vs FULL），效能好
          且仍然 crash-safe。
        - ``busy_timeout=5000`` 給 SQLite 自己 5 秒重試空間，比 ``timeout``
          參數更早發揮作用。
    """
    conn = sqlite3.connect(str(db_path), timeout=timeout)
    conn.row_factory = sqlite3.Row
    configure_sqlite_pragmas(conn)
    return conn


def configure_sqlite_pragmas(conn: sqlite3.Connection) -> None:
    """套用並發友善的 PRAGMA 設定。

    供已經有 connection 但需要補設定的場景使用（例如 legacy code path）。
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
