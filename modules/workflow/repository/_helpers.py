"""Repository-shared helpers — 抽出兩個 repository 共用的 ORM ↔ domain 轉換工具
（review fix #5）。

之前 ``_ensure_utc`` / ``_uuid_to_str`` / ``_str_to_uuid`` / ``_json_safe`` 在
``work_order_repository.py`` 與 ``signoff_repository.py`` 各複製一份，未來改 UTC 邏輯
（如 PostgreSQL tzinfo 處理）容易漏改。本 module 是單一真實來源。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID


def ensure_utc(dt: datetime | None) -> datetime | None:
    """SQLite ``DateTime(timezone=True)`` round-trip 後丟掉 tzinfo（SQLite 沒 native datetime）。
    讀回時補 ``tzinfo=UTC`` 確保下游（cost ledger / API serialization）拿 timezone-aware。

    Returns ``None`` 直接傳入時也 None。
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def assert_utc(name: str, dt: datetime | None) -> None:
    """Write 路徑 guard — datetime 必須 timezone-aware UTC，否則 ``ValueError``。"""
    if dt is None:
        return
    if dt.tzinfo is None:
        raise ValueError(f"{name}: datetime must be timezone-aware (UTC)")
    offset = dt.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError(f"{name}: datetime must be UTC (offset={offset})")


def uuid_to_str(value: UUID | None) -> str | None:
    return str(value) if value is not None else None


def str_to_uuid(value: str | None) -> UUID | None:
    return UUID(value) if value else None


def json_safe(obj: Any) -> Any:
    """``json.dumps(default=...)`` 用 — UUID / datetime / Enum 都序列化為原始型別。"""
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "value"):  # str-Enum
        return obj.value
    return str(obj)
