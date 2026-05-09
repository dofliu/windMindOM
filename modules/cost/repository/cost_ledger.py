"""Cost ledger entry — minimal repository for WMOM-20260509-02 atomic dispatch。

完整 ledger API（query / aggregate / monthly_report 整合）排到 [WMOM-20260509-05](../../../ISSUES.md)
（A5）；本 module 目前只暴露 atomic dispatch 雙寫所需的：

- ``CostLedgerEntryORM``：SQLAlchemy 2.0 mapped class，**共用 workflow Base** 才能在
  同 ``Session.commit()`` 內寫多表 atomic
- ``CostLedgerCategory`` / ``CostLedgerStatus`` / ``CostLedgerSourceType`` Enum
- ``CostLedgerEntry`` pure domain dataclass
- ``insert_in_session(sess, entry) -> CostLedgerEntryORM``：在現有 session 內 insert
  **不 commit**（caller 在外層 transaction 統一 commit / rollback）

Schema 對應 [DN-03 §3.2](../../../docs/design-notes/m3/DN-03-inventory-material-request.md)
+ [WMOM-20260504-11](../../../ISSUES.md) Phase A：

    UUID id / farm_id / category / amount EUR / source_event_id / source_type /
    status / recorded_at / actor / note
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

# 共用 workflow Base — atomic transaction 必須跨 module 共用 metadata
from modules.workflow.repository.orm_models import Base


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


# ─────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────


class CostLedgerCategory(str, Enum):
    """Ledger 4 大分類（cost forecast model 同名概念對齊）。"""

    MATERIAL = "material"
    LABOUR = "labour"
    EQUIPMENT = "equipment"
    REVENUE_LOSS = "revenue_loss"


class CostLedgerStatus(str, Enum):
    """估計 vs 實際區分：``estimated`` 在 dispatch 時寫入，``confirmed`` 在工單
    finish hook 拿到 actual_qty / actual_hours 後翻轉。"""

    ESTIMATED = "estimated"
    CONFIRMED = "confirmed"


class CostLedgerSourceType(str, Enum):
    """Source event 類型（給 reporting 反查）。"""

    MATERIAL_REQUEST = "material_request"
    WORK_ORDER = "work_order"
    FAULT = "fault"
    MANUAL = "manual"


# ─────────────────────────────────────────────────────────────────────────
# Pure dataclass
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class CostLedgerEntry:
    """Pure domain entry（給 caller 建立 + ORM round-trip）。"""

    farm_id: str
    category: CostLedgerCategory
    amount: Decimal
    source_event_id: UUID
    source_type: CostLedgerSourceType
    id: UUID = field(default_factory=uuid4)
    status: CostLedgerStatus = CostLedgerStatus.ESTIMATED
    actor_id: Optional[UUID] = None
    note: Optional[str] = None
    recorded_at: datetime = field(default_factory=_utc_now)


# ─────────────────────────────────────────────────────────────────────────
# ORM
# ─────────────────────────────────────────────────────────────────────────


class CostLedgerEntryORM(Base):
    __tablename__ = "cost_ledger_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    farm_id: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    source_event_id: Mapped[str] = mapped_column(String(36), index=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True, default="estimated")
    actor_id: Mapped[Optional[str]] = mapped_column(String(36))
    note: Mapped[Optional[str]] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "ix_cost_ledger_farm_category_status",
            "farm_id", "category", "status",
        ),
        Index(
            "ix_cost_ledger_source_event",
            "source_type", "source_event_id",
        ),
    )


# ─────────────────────────────────────────────────────────────────────────
# Insert helper（不 commit — caller 在外層 transaction 控）
# ─────────────────────────────────────────────────────────────────────────


def insert_in_session(sess: Session, entry: CostLedgerEntry) -> CostLedgerEntryORM:
    """在現有 session 內加入一筆 ledger entry（``sess.add`` only，不 flush 也不 commit）。

    Caller 是 atomic transaction 的擁有者；半路失敗 caller rollback 即可，本 entry
    也跟著消失（DN-03 §2.3「雙寫交易」）。
    """
    orm = CostLedgerEntryORM(
        id=str(entry.id),
        farm_id=entry.farm_id,
        category=entry.category.value,
        amount=entry.amount,
        source_event_id=str(entry.source_event_id),
        source_type=entry.source_type.value,
        status=entry.status.value,
        actor_id=str(entry.actor_id) if entry.actor_id is not None else None,
        note=entry.note,
        recorded_at=entry.recorded_at,
    )
    sess.add(orm)
    return orm
