"""Pydantic request / response schemas for material_request router（WMOM-20260509-03）。

設計（沿襲 work_order_schemas 模式）：
- Response 直接從 dataclass 對映；用 ``ConfigDict(from_attributes=True)``
- str-Enum 透明序列化（pydantic v2 直接支援 ``StockKind`` / ``MaterialRequestStatus`` 等）
- UUID / datetime / Decimal 由 pydantic v2 預設處理
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from modules.workflow.domain.inventory import (
    MaterialRequestStatus,
    ReturnReason,
    StockKind,
)

if TYPE_CHECKING:
    # Type-only import — runtime forward reference 已透過 __future__ annotations 解決，
    # 此處只是讓 mypy / IDE 能解析 ``MaterialRequest`` 型別。
    from modules.workflow.domain.inventory import MaterialRequest


# ─────────────────────────────────────────────────────────────────────────
# Request bodies
# ─────────────────────────────────────────────────────────────────────────


class CreateMaterialRequestItem(BaseModel):
    """單一料件明細（建單時）。"""

    item_id: UUID
    estimated_qty: int = Field(gt=0, le=100_000)
    stock_kind: StockKind = StockKind.NEW


class CreateMaterialRequest(BaseModel):
    """``POST /api/workflow/material-requests`` body — 建立 DRAFT 領料單。"""

    farm_id: str = Field(min_length=1, max_length=128)
    requester_id: UUID
    items: list[CreateMaterialRequestItem] = Field(min_length=1)
    work_order_id: Optional[UUID] = None


class SubmitForApprovalRequest(BaseModel):
    """``/submit-for-approval`` — DRAFT → AWAITING_APPROVAL + 自動建 signoff chain。"""

    actor_id: UUID
    escalate_to_supervisor: bool = False  # critical priority MR 預留


class DispatchMaterialRequest(BaseModel):
    """``/dispatch`` — APPROVED → DISPATCHED + atomic stock + ledger 雙寫。"""

    actor_id: Optional[UUID] = None  # 給 ledger entry actor 寫入


class ReceiveMaterialRequest(BaseModel):
    """``/receive`` — DISPATCHED → RECEIVED + 寫 actual_quantities 到 items。

    ``actual_quantities`` key 為 ``MaterialRequestItem.id`` (UUID str)，必須涵蓋所有 items。
    """

    actor_id: UUID
    actual_quantities: dict[UUID, int]


class CloseMaterialRequest(BaseModel):
    """``/close`` — USED / RECEIVED → CLOSED。"""

    actor_id: UUID


class CancelMaterialRequest(BaseModel):
    """``/cancel`` — DRAFT / AWAITING_APPROVAL / APPROVED → CANCELLED。"""

    actor_id: UUID
    cancel_reason: str = Field(min_length=1, max_length=2000)


class CreateMaterialReturn(BaseModel):
    """``/returns`` — 建退料記錄 + atomic 加回 stock。"""

    item_id: UUID
    qty: int = Field(gt=0, le=100_000)
    reason: ReturnReason
    return_to_kind: StockKind
    returned_by: UUID
    note: Optional[str] = Field(default=None, max_length=2000)


# ─────────────────────────────────────────────────────────────────────────
# Response sub-models
# ─────────────────────────────────────────────────────────────────────────


class MaterialRequestItemResponse(BaseModel):
    """單筆料件明細回應（read-only）。

    ``sku`` / ``name`` / ``unit`` 為 denormalized 顯示欄位 — 由 router 在組裝時透過
    ``MaterialRequestRepository.fetch_item_metadata()`` 批次填入；若未填則保持 ``None``
    （domain dataclass 本身只持 ``item_id`` FK，不含 display metadata）。
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    request_id: UUID
    item_id: UUID
    estimated_qty: int
    actual_qty: Optional[int] = None
    stock_kind: StockKind

    # denormalized display fields（WMOM-20260518-01）
    sku: Optional[str] = None
    name: Optional[str] = None
    unit: Optional[str] = None


class MaterialReturnResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    request_id: UUID
    item_id: UUID
    qty: int
    reason: ReturnReason
    return_to_kind: StockKind
    returned_by: UUID
    note: Optional[str] = None
    returned_at: datetime


# ─────────────────────────────────────────────────────────────────────────
# Main response
# ─────────────────────────────────────────────────────────────────────────


class MaterialRequestResponse(BaseModel):
    """完整領料單視圖（list / detail / 任何 transition 後共用）。"""

    model_config = ConfigDict(from_attributes=True)

    # identity
    id: UUID
    business_key: str

    # core
    farm_id: str
    requester_id: UUID
    work_order_id: Optional[UUID] = None
    status: MaterialRequestStatus

    # items
    items: list[MaterialRequestItemResponse] = Field(default_factory=list)

    # 簽核
    signoff_chain_id: Optional[UUID] = None

    # timeline
    requested_at: datetime
    submitted_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    dispatched_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    used_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None

    # reasons
    cancel_reason: Optional[str] = None
    reject_reason: Optional[str] = None

    # audit
    created_at: datetime
    updated_at: datetime


class MaterialRequestListResponse(BaseModel):
    """``GET /api/workflow/material-requests`` 回應 — 帶 total + items。"""

    total: int
    items: list[MaterialRequestResponse]


# ─────────────────────────────────────────────────────────────────────────
# Response builder（WMOM-20260518-01）
# ─────────────────────────────────────────────────────────────────────────


def build_material_request_response(
    mr: "MaterialRequest",
    item_metadata: dict[UUID, tuple[str | None, str | None, str | None]] | None = None,
) -> "MaterialRequestResponse":
    """組裝 ``MaterialRequestResponse`` 並 enrich items 的 ``sku``/``name``/``unit``。

    Args:
        mr: domain ``MaterialRequest``。
        item_metadata: ``{inventory_item_id: (sku, name, unit)}``；
            - ``None``：保留 v0.8 行為（純 ``model_validate``，不 enrich），給不需 metadata
              的內部 caller（如 test）使用。
            - ``{}``：表示 caller 「主動查過但結果空」（例如 MR 沒任何 item），仍走 enrich loop
              — 每個 item 都 miss 對應 entry 後保留 None display fields。
            - 缺特定 key：該 item 顯示欄位保持 ``None`` — frontend 自行 fallback 顯示
              truncated UUID。

    型別 ``tuple[str | None, str | None, str | None]``：``InventoryItem.sku/name/unit``
    在 ORM 是 NOT NULL，但 nullable 友善以防未來 schema 變更或測試環境插入 NULL。
    """
    base = MaterialRequestResponse.model_validate(mr)
    if item_metadata is None:
        return base

    enriched_items: list[MaterialRequestItemResponse] = []
    for it in base.items:
        meta = item_metadata.get(it.item_id)
        if meta is None:
            enriched_items.append(it)
            continue
        sku, name, unit = meta
        enriched_items.append(
            it.model_copy(update={"sku": sku, "name": name, "unit": unit})
        )
    return base.model_copy(update={"items": enriched_items})
