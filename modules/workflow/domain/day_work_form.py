"""DayWorkForm pure-domain entities for windMindOM workflow module。

對應 [DN-01](../../../docs/design-notes/m3/DN-01-work-order-lifecycle.md) §3.3 +
walkthrough Q6（2026-05-05 劉老師確認，見 ``WMOM-20260505-21``）。

實作邊界：
- 純 dataclass + Enum + 純函式；不接 SQLAlchemy / FastAPI
- ``work_order`` 工作對象＝風機；``day_work_form`` 工作對象＝**員工 × 當天**——不同
  entity，一份日誌可包含多筆 activity（完成工單 / 定檢項 / 巡視 / 訓練）
- 本次範圍**不含** work_order 完工自動寫入 day_work_form 的整合 hook（涉及既有簽核
  流程的 ``transition`` 入口，需另評估耦合風險），見 completion summary
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from uuid import UUID, uuid4


def _utc_now() -> datetime:
    """timezone-aware UTC now（windMindOM 一律 UTC 進 DB）。"""
    return datetime.now(tz=timezone.utc)


class ActivityKind(str, Enum):
    """日誌內單筆活動的種類（walkthrough Q6 圖示的 4 種）。"""

    COMPLETED_WO = "completed_wo"      # 完成一張工單 → wo_id
    INSPECTION_ITEM = "inspection_item"  # 完成一個定檢項 → item_id + result
    PATROL = "patrol"                  # 巡視 → area
    TRAINING = "training"              # 訓練 → topic


# 每種 kind 對應的必填欄位（其餘欄位維持 None，不強制清空）。
_REQUIRED_FIELDS: dict[ActivityKind, tuple[str, ...]] = {
    ActivityKind.COMPLETED_WO: ("wo_id",),
    ActivityKind.INSPECTION_ITEM: ("item_id", "result"),
    ActivityKind.PATROL: ("area",),
    ActivityKind.TRAINING: ("topic",),
}


@dataclass
class ActivityEntry:
    """日誌內單筆活動（純資料，必填欄位依 ``kind`` 不同，由 :func:`validate_activity_entry` 驗證）。"""

    kind: ActivityKind
    id: UUID = field(default_factory=uuid4)

    # kind-specific fields（未使用的維持 None）
    wo_id: UUID | None = None
    item_id: UUID | None = None
    result: str | None = None
    area: str | None = None
    topic: str | None = None

    note: str = ""
    logged_at: datetime = field(default_factory=_utc_now)


def validate_activity_entry(entry: ActivityEntry) -> None:
    """驗證 ``entry`` 依 ``kind`` 帶齊必填欄位，否則 ``ValueError``。

    刻意設計成**顯式呼叫**（非 dataclass ``__post_init__``）：與
    ``recurrence_interval_days`` 同一慣例——domain 層提供純驗證函式，由
    repository / schema 邊界呼叫，測試可自由建構部分欄位的 entry 做其他用途
    （如 round-trip 測試）而不被迫先通過驗證。
    """
    missing = [
        name
        for name in _REQUIRED_FIELDS[entry.kind]
        if getattr(entry, name) in (None, "")
    ]
    if missing:
        raise ValueError(
            f"ActivityKind.{entry.kind.value} 缺必填欄位: {', '.join(missing)}"
        )


@dataclass
class DayWorkForm:
    """員工當天工作日誌主實體（walkthrough Q6：員工 × 當天為 natural key）。

    Naming convention 沿用 ``inspection_schedule.py``：``id`` 為系統 FK 用
    surrogate UUID；``(farm_id, employee_id, work_date)`` 三欄組合唯一
    （見 repository ``DayWorkFormORM`` 的 unique index），一天一位員工只有一份日誌。
    """

    # ── primary identity ─────────────────────────────────────────────
    farm_id: str
    employee_id: UUID
    work_date: date
    id: UUID = field(default_factory=uuid4)

    # ── 活動清單 ──────────────────────────────────────────────────────
    activities: list[ActivityEntry] = field(default_factory=list)

    # ── 當天整體備註（選填）───────────────────────────────────────────
    notes: str = ""

    # ── audit ────────────────────────────────────────────────────────
    created_at: datetime = field(default_factory=_utc_now)
    created_by: UUID | None = None
    updated_at: datetime = field(default_factory=_utc_now)
