"""Pydantic request / response schemas for inventory router（WMOM-20260509-04）。

設計（沿襲 work_order / material_request schemas 模式）：
- Response 直接從 dataclass 對映；用 ``ConfigDict(from_attributes=True)``
- str-Enum (StockKind) 透明序列化
- UUID / datetime / Decimal 由 pydantic v2 預設處理
- Decimal unit_cost 走 ``Decimal`` 不掉精度
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from modules.workflow.domain.inventory import StockKind


# ─────────────────────────────────────────────────────────────────────────
# Warehouse
# ─────────────────────────────────────────────────────────────────────────


class CreateWarehouseRequest(BaseModel):
    """``POST /api/workflow/warehouses`` body — 建倉。"""

    farm_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    location_kind: Literal[
        "onshore_base", "vessel_storage", "offshore_platform"
    ] = "onshore_base"
    is_default: bool = False


class WarehouseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    farm_id: str
    name: str
    location_kind: str
    is_default: bool


class WarehouseListResponse(BaseModel):
    items: list[WarehouseResponse]


# ─────────────────────────────────────────────────────────────────────────
# Inventory item — Request
# ─────────────────────────────────────────────────────────────────────────


class CreateInventoryItemRequest(BaseModel):
    """``POST /api/workflow/inventory`` body — 建料件主檔。

    Note：``(farm_id, sku)`` unique constraint enforced by DB；重覆 → 409 Conflict。
    """

    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(default="", max_length=4000)
    unit: str = Field(min_length=1, max_length=32)
    farm_id: str = Field(min_length=1, max_length=128)
    warehouse_id: UUID
    unit_cost: Decimal = Field(ge=Decimal("0"))
    stock_new: int = Field(default=0, ge=0)
    stock_used: int = Field(default=0, ge=0)
    stock_repairing: int = Field(default=0, ge=0)
    safety_stock: int = Field(default=0, ge=0)


class UpdateInventoryMetadataRequest(BaseModel):
    """``PATCH /api/workflow/inventory/{item_id}`` body — 改 metadata，不動 stock。

    所有欄位 optional；只更新傳入的欄位（pydantic ``exclude_unset=True``）。
    """

    sku: Optional[str] = Field(default=None, min_length=1, max_length=64)
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    description: Optional[str] = Field(default=None, max_length=4000)
    unit: Optional[str] = Field(default=None, min_length=1, max_length=32)
    safety_stock: Optional[int] = Field(default=None, ge=0)
    unit_cost: Optional[Decimal] = Field(default=None, ge=Decimal("0"))


class AdjustInventoryRequest(BaseModel):
    """``POST /api/workflow/inventory/{item_id}/adjust`` body — 手動 +/- 異動 stock。

    - ``delta_kind``: NEW / USED / REPAIRING — 異動哪個 stock 欄位
    - ``delta``: 正值 = 加、負值 = 扣（不限正負；扣到負數會 422）
    - ``reason``: 必填，給 audit log 用（例「歸還良品」/「盤盈」）
    - ``actor_id``: 庫管員身分；可省略（WMOM-20260509-F5：系統 adjust 不必假裝有人簽）
    """

    delta_kind: StockKind
    delta: int
    reason: str = Field(min_length=1, max_length=256)
    actor_id: Optional[UUID] = None
    note: Optional[str] = Field(default=None, max_length=2000)


# ─────────────────────────────────────────────────────────────────────────
# Inventory item — Response
# ─────────────────────────────────────────────────────────────────────────


class InventoryItemResponse(BaseModel):
    """完整料件視圖 + safety_stock 警示計算欄位。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sku: str
    name: str
    description: str
    unit: str
    farm_id: str
    warehouse_id: UUID

    stock_new: int
    stock_used: int
    stock_repairing: int
    safety_stock: int
    unit_cost: Decimal

    last_received_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_available(self) -> int:
        """``stock_new + stock_used``（不含維修中）。"""
        return self.stock_new + self.stock_used

    @computed_field  # type: ignore[prop-decorator]
    @property
    def below_safety(self) -> bool:
        """``stock_new + stock_used < safety_stock`` 視為警示。"""
        return self.stock_new + self.stock_used < self.safety_stock


class InventoryItemListResponse(BaseModel):
    total: int
    items: list[InventoryItemResponse]


# ─────────────────────────────────────────────────────────────────────────
# Adjustment log
# ─────────────────────────────────────────────────────────────────────────


class AdjustmentLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_id: UUID
    delta_kind: StockKind
    delta: int
    reason: str
    # WMOM-20260509-F5：actor_id 可為 None（系統 adjust，無真人簽）
    actor_id: Optional[UUID] = None
    note: Optional[str] = None
    occurred_at: datetime


class AdjustmentLogListResponse(BaseModel):
    items: list[AdjustmentLogResponse]


# ─────────────────────────────────────────────────────────────────────────
# Adjust 結果（item + log 同一回應，前端可同時更新顯示）
# ─────────────────────────────────────────────────────────────────────────


class AdjustInventoryResult(BaseModel):
    """``POST /adjust`` 成功回應 — 帶異動後的 item + 對應 audit log entry。"""

    item: InventoryItemResponse
    log: AdjustmentLogResponse
