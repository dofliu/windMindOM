"""Inventory + MaterialRequest SQLAlchemy 2.0 ORM models（WMOM-20260509-02 / DN-03）。

設計準則（沿襲 work_order ORM 模式）：
- 與 ``modules/workflow/domain/inventory.py`` dataclass **欄位一一對應**
- UUID 存成 string（SQLite 沒 native UUID）
- Enum 存成 string value
- Timestamps DateTime(timezone=True)；SQLite roundtrip 後在 _helpers.ensure_utc 補回 tzinfo
- Decimal 用 Numeric(precision, scale) — SQLite 走 TEXT，SQLAlchemy roundtrip 自動還原 Decimal
- 與 monitoring (raw sqlite3) + work_order ORM 共用 Base（同一個 wind_farm.db）；
  cost_ledger 也用同一個 Base 是為了 atomic transaction 同 connection 寫多表
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .orm_models import Base


# ─────────────────────────────────────────────────────────────────────────
# warehouses
# ─────────────────────────────────────────────────────────────────────────


class WarehouseORM(Base):
    """≡ DN-03 Warehouse — 多倉預留，M3-M4 預設 single default warehouse。"""

    __tablename__ = "warehouses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    farm_id: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(128))
    location_kind: Mapped[str] = mapped_column(String(32))  # onshore_base / vessel_storage / offshore_platform
    is_default: Mapped[bool] = mapped_column(default=False)


# ─────────────────────────────────────────────────────────────────────────
# inventory items
# ─────────────────────────────────────────────────────────────────────────


class InventoryItemORM(Base):
    """≡ DN-03 InventoryItem — 料件主檔（3 stockKind + safety_stock + unit_cost）。"""

    __tablename__ = "inventory_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(32))
    farm_id: Mapped[str] = mapped_column(String(128), index=True)
    warehouse_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("warehouses.id"), index=True
    )

    stock_new: Mapped[int] = mapped_column(Integer, default=0)
    stock_used: Mapped[int] = mapped_column(Integer, default=0)
    stock_repairing: Mapped[int] = mapped_column(Integer, default=0)
    safety_stock: Mapped[int] = mapped_column(Integer, default=0)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 4))

    last_received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_inventory_items_farm_sku", "farm_id", "sku", unique=True),
    )


# ─────────────────────────────────────────────────────────────────────────
# inventory adjustment log（D3-Q2：庫管員手動 +/- audit）
# ─────────────────────────────────────────────────────────────────────────


class InventoryAdjustmentLogORM(Base):
    """每次 ``POST /inventory/{id}/adjust`` 必寫一筆（給 audit / KPI）。"""

    __tablename__ = "inventory_adjustment_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inventory_items.id"), index=True
    )
    delta_kind: Mapped[str] = mapped_column(String(16))           # new / used / repairing
    delta: Mapped[int] = mapped_column(Integer)                   # signed
    reason: Mapped[str] = mapped_column(String(256))
    actor_id: Mapped[str] = mapped_column(String(36))
    note: Mapped[Optional[str]] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# ─────────────────────────────────────────────────────────────────────────
# material requests
# ─────────────────────────────────────────────────────────────────────────


class MaterialRequestORM(Base):
    """≡ DN-03 MaterialRequest — 領料申請單主實體。"""

    __tablename__ = "material_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    business_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    farm_id: Mapped[str] = mapped_column(String(128), index=True)
    requester_id: Mapped[str] = mapped_column(String(36), index=True)
    work_order_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)

    status: Mapped[str] = mapped_column(String(32), index=True, default="draft")

    signoff_chain_id: Mapped[Optional[str]] = mapped_column(String(36))

    # timeline
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    cancel_reason: Mapped[Optional[str]] = mapped_column(Text)
    reject_reason: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    items: Mapped[list["MaterialRequestItemORM"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="MaterialRequestItemORM.id",
    )
    returns: Mapped[list["MaterialReturnORM"]] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        order_by="MaterialReturnORM.returned_at",
    )

    __table_args__ = (
        Index(
            "ix_material_requests_farm_status_wo",
            "farm_id", "status", "work_order_id",
        ),
    )


class MaterialRequestItemORM(Base):
    """≡ DN-03 MaterialRequestItem — 一張 MR 多筆料件明細。"""

    __tablename__ = "material_request_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("material_requests.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inventory_items.id"), index=True
    )
    estimated_qty: Mapped[int] = mapped_column(Integer)
    actual_qty: Mapped[Optional[int]] = mapped_column(Integer)
    stock_kind: Mapped[str] = mapped_column(String(16), default="new")  # new/used/repairing

    request: Mapped["MaterialRequestORM"] = relationship(back_populates="items")
    # 純讀向 join — 給 _to_domain 拉 sku/name/unit metadata（WMOM-20260518-01）；
    # item_id 已有 ForeignKey 宣告，SQLAlchemy 自動推算 primaryjoin，無須顯式設定。
    inventory_item: Mapped[Optional["InventoryItemORM"]] = relationship(
        "InventoryItemORM",
        viewonly=True,
        lazy="joined",
    )


class MaterialReturnORM(Base):
    """≡ DN-03 MaterialReturn — 退料記錄（D3-Q4: 4 種分類）。"""

    __tablename__ = "material_returns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("material_requests.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inventory_items.id"), index=True
    )
    qty: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(32))           # surplus / wrong_part / failed_install / other
    return_to_kind: Mapped[str] = mapped_column(String(16))   # new / used / repairing
    returned_by: Mapped[str] = mapped_column(String(36))
    note: Mapped[Optional[str]] = mapped_column(Text)
    returned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    request: Mapped["MaterialRequestORM"] = relationship(back_populates="returns")


class MaterialRequestNotificationORM(Base):
    """≡ DN-03 MaterialRequestNotification — 統合 etech 兩個 notic collection。"""

    __tablename__ = "material_request_notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("material_requests.id", ondelete="CASCADE"), index=True
    )
    recipient_role: Mapped[str] = mapped_column(String(32), index=True)
    notification_type: Mapped[str] = mapped_column(String(32))   # awaiting_signoff / stock_low / received_pending / dispatched_to_field
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
