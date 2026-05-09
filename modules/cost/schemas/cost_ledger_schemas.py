"""Pydantic schemas for cost_ledger router（WMOM-20260509-05）。

Read-only API — caller 通常透過 ``/api/cost/ledger`` query 拿月報資料。
Insert / confirm 走 repository 層（不直接 expose POST/PATCH endpoint，避免外部
誤改帳本；ledger 的所有 mutation 必須來自 atomic 業務 transaction，例如
dispatch / wo finish hook）。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from modules.cost.repository.cost_ledger import (
    CostLedgerCategory,
    CostLedgerSourceType,
    CostLedgerStatus,
)


class CostLedgerEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    farm_id: str
    category: CostLedgerCategory
    amount: Decimal
    source_event_id: UUID
    source_item_id: Optional[UUID] = None
    source_type: CostLedgerSourceType
    status: CostLedgerStatus
    actor_id: Optional[UUID] = None
    note: Optional[str] = None
    recorded_at: datetime
    confirmed_at: Optional[datetime] = None


class CostLedgerListResponse(BaseModel):
    total: int
    items: list[CostLedgerEntryResponse]


class CategorySummaryItem(BaseModel):
    category: CostLedgerCategory
    total: Decimal


class CostLedgerSummaryResponse(BaseModel):
    """4 大類加總結果（給 monthly_report A8 用 — 一次拿月度 cost 拼月報）。"""

    farm_id: str
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
    status_filter: Optional[CostLedgerStatus] = None
    by_category: list[CategorySummaryItem] = Field(default_factory=list)
    grand_total: Decimal
