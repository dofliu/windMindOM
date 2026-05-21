"""InventoryRepository — CRUD + safety_stock + 手動 +/- adjust + audit log（WMOM-20260509-02）。

責任：
1. ORM ↔ dataclass round-trip（``_to_domain`` / ``_to_orm``）
2. CRUD：create_warehouse / create_item / get / list / update_metadata
3. ``adjust(item_id, delta_kind, delta, reason, actor_id, note)``：手動 +/- 異動
   stock + 同 transaction 寫 ``InventoryAdjustmentLog``
4. ``list_below_safety()``：safety_stock 警示查詢（給 Inventory dashboard 用）
5. **不負責** material_request 雙寫 — 那條走 ``MaterialRequestRepository.dispatch_request``
   （atomic stock + ledger，本 repo 提供 helper ``apply_stock_delta_in_session()`` 給
    它在同 session 內呼叫）。
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import Engine, create_engine, event as sa_event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from modules.workflow.domain.inventory import (
    InventoryAdjustmentLog,
    InventoryItem,
    StockKind,
    Warehouse,
    _utc_now,
)

from ._helpers import ensure_utc, str_to_uuid, uuid_to_str
from .inventory_orm import (
    InventoryAdjustmentLogORM,
    InventoryItemORM,
    WarehouseORM,
)
from .orm_models import Base
from .work_order_repository import _get_engine, _ENGINE_LOCK, _SCHEMA_INITIALIZED

_logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────


class InsufficientStock(Exception):
    """目標 stock 欄位數量不足以扣帳（dispatch 時 raise）。"""

    def __init__(self, item_id: UUID, kind: StockKind, requested: int, available: int):
        self.item_id = item_id
        self.kind = kind
        self.requested = requested
        self.available = available
        super().__init__(
            f"insufficient {kind.value} stock for item {item_id}: "
            f"requested {requested}, available {available}"
        )


class StockAdjustmentError(Exception):
    """手動 adjust 失敗 — delta 會讓 stock 變負 / item 不存在。"""


# ─────────────────────────────────────────────────────────────────────────
# Repository factory（沿用 work_order_repository 的 engine cache）
# ─────────────────────────────────────────────────────────────────────────


def get_inventory_repository(db_path: str) -> "InventoryRepository":
    """Factory — 共用 work_order_repository 的 engine cache，
    避免一個 farm DB 開兩條 connection pool。
    """
    engine = _get_engine(db_path)
    abs_path = str(Path(db_path).resolve())
    with _ENGINE_LOCK:
        if abs_path not in _SCHEMA_INITIALIZED:
            Base.metadata.create_all(engine)
            _SCHEMA_INITIALIZED.add(abs_path)
    return InventoryRepository(engine)


# ─────────────────────────────────────────────────────────────────────────
# Stock-mutation helper（給 MaterialRequestRepository.dispatch_request 用）
# ─────────────────────────────────────────────────────────────────────────


def apply_stock_delta_in_session(
    sess: Session,
    *,
    item_id: UUID,
    kind: StockKind,
    delta: int,
    use_for_update: bool = True,
) -> InventoryItemORM:
    """在現有 session 內 lock 該 item + 異動 stock。**不 commit**，caller 控 transaction。

    delta 可正可負；扣帳（負 delta）若 stock 不足 raise ``InsufficientStock``。
    SQLite 上 ``with_for_update()`` 是 no-op（SQLite 沒 row-level lock），但 SQLite
    的 BEGIN IMMEDIATE + WAL + busy_timeout 會把寫入序列化（足夠 atomic）。

    PostgreSQL 部署時 ``with_for_update()`` 會發 SELECT ... FOR UPDATE 真做 row-lock，
    並行 dispatch 時第二個 request 會等第一個 commit/rollback。
    """
    stmt = select(InventoryItemORM).where(InventoryItemORM.id == str(item_id))
    if use_for_update:
        stmt = stmt.with_for_update()
    inv = sess.execute(stmt).scalar_one_or_none()
    if inv is None:
        raise StockAdjustmentError(f"inventory_item {item_id} not found")

    if kind is StockKind.NEW:
        new_value = inv.stock_new + delta
        if new_value < 0:
            raise InsufficientStock(item_id, kind, abs(delta), inv.stock_new)
        inv.stock_new = new_value
    elif kind is StockKind.USED:
        new_value = inv.stock_used + delta
        if new_value < 0:
            raise InsufficientStock(item_id, kind, abs(delta), inv.stock_used)
        inv.stock_used = new_value
    else:  # REPAIRING
        new_value = inv.stock_repairing + delta
        if new_value < 0:
            raise InsufficientStock(item_id, kind, abs(delta), inv.stock_repairing)
        inv.stock_repairing = new_value

    inv.updated_at = _utc_now()
    if delta < 0:
        inv.last_used_at = _utc_now()
    elif delta > 0:
        inv.last_received_at = _utc_now()
    return inv


# ─────────────────────────────────────────────────────────────────────────
# Repository
# ─────────────────────────────────────────────────────────────────────────


class InventoryRepository:
    """SQLAlchemy 2.0 repository for inventory_items + warehouses + adjustment_log。"""

    def __init__(self, engine: Engine):
        self._engine = engine
        self._sessionmaker = sessionmaker(engine, expire_on_commit=False, future=True)

    # ── Warehouse CRUD ──────────────────────────────────────────────────

    def create_warehouse(
        self,
        *,
        farm_id: str,
        name: str,
        location_kind: str = "onshore_base",
        is_default: bool = False,
    ) -> Warehouse:
        with self._sessionmaker() as sess:
            wh_id = uuid4()
            orm = WarehouseORM(
                id=str(wh_id),
                farm_id=farm_id,
                name=name,
                location_kind=location_kind,
                is_default=is_default,
            )
            sess.add(orm)
            sess.commit()
            return Warehouse(
                id=wh_id,
                farm_id=farm_id,
                name=name,
                location_kind=location_kind,  # type: ignore[arg-type]
                is_default=is_default,
            )

    def get_warehouse(self, warehouse_id: UUID) -> Warehouse | None:
        with self._sessionmaker() as sess:
            orm = sess.get(WarehouseORM, str(warehouse_id))
            return self._warehouse_to_domain(orm) if orm else None

    def get_default_warehouse(self, farm_id: str) -> Warehouse | None:
        """取 farm 內 ``is_default=True`` 的倉；M3-M4 預設只會有一個。"""
        with self._sessionmaker() as sess:
            stmt = select(WarehouseORM).where(
                WarehouseORM.farm_id == farm_id,
                WarehouseORM.is_default == True,  # noqa: E712
            )
            orm = sess.execute(stmt).scalar_one_or_none()
            return self._warehouse_to_domain(orm) if orm else None

    def list_warehouses(self, farm_id: str) -> list[Warehouse]:
        """List 該 farm 所有倉，``is_default`` 在前 + name ASC（F3 把 router raw SQL 拉回 repo）。"""
        with self._sessionmaker() as sess:
            stmt = (
                select(WarehouseORM)
                .where(WarehouseORM.farm_id == farm_id)
                .order_by(WarehouseORM.is_default.desc(), WarehouseORM.name)
            )
            return [
                self._warehouse_to_domain(orm)
                for orm in sess.execute(stmt).scalars().all()
            ]

    # ── Inventory item CRUD ─────────────────────────────────────────────

    def create_item(
        self,
        *,
        sku: str,
        name: str,
        description: str,
        unit: str,
        farm_id: str,
        warehouse_id: UUID,
        unit_cost: Decimal,
        stock_new: int = 0,
        stock_used: int = 0,
        stock_repairing: int = 0,
        safety_stock: int = 0,
    ) -> InventoryItem:
        """建料件主檔。``(farm_id, sku)`` unique — 重覆 raise ``IntegrityError``。"""
        with self._sessionmaker() as sess:
            item_id = uuid4()
            now = _utc_now()
            orm = InventoryItemORM(
                id=str(item_id),
                sku=sku,
                name=name,
                description=description,
                unit=unit,
                farm_id=farm_id,
                warehouse_id=str(warehouse_id),
                stock_new=stock_new,
                stock_used=stock_used,
                stock_repairing=stock_repairing,
                safety_stock=safety_stock,
                unit_cost=unit_cost,
                created_at=now,
                updated_at=now,
            )
            sess.add(orm)
            sess.commit()
            sess.refresh(orm)
            return self._item_to_domain(orm)

    def get_item(self, item_id: UUID) -> InventoryItem | None:
        with self._sessionmaker() as sess:
            orm = sess.get(InventoryItemORM, str(item_id))
            return self._item_to_domain(orm) if orm else None

    def get_item_by_sku(self, farm_id: str, sku: str) -> InventoryItem | None:
        with self._sessionmaker() as sess:
            stmt = select(InventoryItemORM).where(
                InventoryItemORM.farm_id == farm_id,
                InventoryItemORM.sku == sku,
            )
            orm = sess.execute(stmt).scalar_one_or_none()
            return self._item_to_domain(orm) if orm else None

    def list_items(
        self,
        *,
        farm_id: str,
        warehouse_id: UUID | None = None,
        below_safety_only: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[InventoryItem], int]:
        """List items — 可選 below_safety_only filter（給 dashboard 警示）。"""
        with self._sessionmaker() as sess:
            base = select(InventoryItemORM).where(InventoryItemORM.farm_id == farm_id)
            if warehouse_id is not None:
                base = base.where(InventoryItemORM.warehouse_id == str(warehouse_id))
            if below_safety_only:
                # SQLite: stock_new + stock_used < safety_stock
                base = base.where(
                    InventoryItemORM.stock_new + InventoryItemORM.stock_used
                    < InventoryItemORM.safety_stock
                )
            # SQL-side count（F2）：避免把所有 id 撈進 Python 再算 len
            count_stmt = select(func.count()).select_from(base.subquery())
            total = sess.execute(count_stmt).scalar_one()
            paged = base.order_by(InventoryItemORM.sku).limit(limit).offset(offset)
            items = [
                self._item_to_domain(orm)
                for orm in sess.execute(paged).scalars().all()
            ]
            return items, total

    def update_metadata(
        self,
        item_id: UUID,
        *,
        sku: str | None = None,
        name: str | None = None,
        description: str | None = None,
        unit: str | None = None,
        safety_stock: int | None = None,
        unit_cost: Decimal | None = None,
    ) -> InventoryItem:
        """改 metadata（不動 stock 數量）；給 ``PATCH /inventory/{id}`` 用。"""
        with self._sessionmaker() as sess:
            orm = sess.get(InventoryItemORM, str(item_id))
            if orm is None:
                raise LookupError(f"inventory_item {item_id} not found")
            if sku is not None:
                orm.sku = sku
            if name is not None:
                orm.name = name
            if description is not None:
                orm.description = description
            if unit is not None:
                orm.unit = unit
            if safety_stock is not None:
                if safety_stock < 0:
                    raise StockAdjustmentError(
                        f"safety_stock must be >= 0 (got {safety_stock})"
                    )
                orm.safety_stock = safety_stock
            if unit_cost is not None:
                orm.unit_cost = unit_cost
            orm.updated_at = _utc_now()
            sess.commit()
            sess.refresh(orm)
            return self._item_to_domain(orm)

    # ── Manual adjustment（D3-Q2 庫管員 +/-） ──────────────────────────

    def adjust(
        self,
        item_id: UUID,
        *,
        delta_kind: StockKind,
        delta: int,
        reason: str,
        actor_id: UUID | None = None,
        note: str | None = None,
    ) -> tuple[InventoryItem, InventoryAdjustmentLog]:
        """手動異動 stock + 同 transaction 寫 audit log。

        - ``delta`` 可正可負；不可使 stock 變負 → ``InsufficientStock``
        - ``reason`` 必填 non-empty
        - ``actor_id`` 改 Optional（WMOM-20260509-F5）：系統 adjust（如 dispatch hook、
          scheduler 自動沖銷）不必塞 fake UUID 假裝有人簽。
        """
        if not (reason or "").strip():
            raise StockAdjustmentError("adjust requires non-empty reason")
        with self._sessionmaker() as sess:
            try:
                # 同 session lock + 異動
                inv_orm = apply_stock_delta_in_session(
                    sess, item_id=item_id, kind=delta_kind, delta=delta
                )
                # audit log
                log_id = uuid4()
                log_orm = InventoryAdjustmentLogORM(
                    id=str(log_id),
                    item_id=str(item_id),
                    delta_kind=delta_kind.value,
                    delta=delta,
                    reason=reason.strip(),
                    actor_id=str(actor_id) if actor_id is not None else None,
                    note=note,
                    occurred_at=_utc_now(),
                )
                sess.add(log_orm)
                sess.commit()
                sess.refresh(inv_orm)
                sess.refresh(log_orm)
                return self._item_to_domain(inv_orm), self._log_to_domain(log_orm)
            except (InsufficientStock, StockAdjustmentError):
                sess.rollback()
                raise

    def list_adjustments(
        self, item_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> list[InventoryAdjustmentLog]:
        """查 audit log（給 inventory drawer 用）。"""
        with self._sessionmaker() as sess:
            stmt = (
                select(InventoryAdjustmentLogORM)
                .where(InventoryAdjustmentLogORM.item_id == str(item_id))
                .order_by(InventoryAdjustmentLogORM.occurred_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return [
                self._log_to_domain(orm)
                for orm in sess.execute(stmt).scalars().all()
            ]

    # ─────────────────────────────────────────────────────────────────
    # ORM → domain
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _warehouse_to_domain(orm: WarehouseORM) -> Warehouse:
        return Warehouse(
            id=UUID(orm.id),
            farm_id=orm.farm_id,
            name=orm.name,
            location_kind=orm.location_kind,  # type: ignore[arg-type]
            is_default=orm.is_default,
        )

    @staticmethod
    def _item_to_domain(orm: InventoryItemORM) -> InventoryItem:
        return InventoryItem(
            id=UUID(orm.id),
            sku=orm.sku,
            name=orm.name,
            description=orm.description,
            unit=orm.unit,
            farm_id=orm.farm_id,
            warehouse_id=UUID(orm.warehouse_id),
            stock_new=orm.stock_new,
            stock_used=orm.stock_used,
            stock_repairing=orm.stock_repairing,
            safety_stock=orm.safety_stock,
            unit_cost=Decimal(str(orm.unit_cost)) if orm.unit_cost is not None else Decimal("0"),
            last_received_at=ensure_utc(orm.last_received_at),
            last_used_at=ensure_utc(orm.last_used_at),
            created_at=ensure_utc(orm.created_at) or _utc_now(),
            updated_at=ensure_utc(orm.updated_at) or _utc_now(),
        )

    @staticmethod
    def _log_to_domain(orm: InventoryAdjustmentLogORM) -> InventoryAdjustmentLog:
        return InventoryAdjustmentLog(
            id=UUID(orm.id),
            item_id=UUID(orm.item_id),
            delta_kind=StockKind(orm.delta_kind),
            delta=orm.delta,
            reason=orm.reason,
            # WMOM-20260509-F5：actor_id 可為 NULL（系統 adjust）。
            # F5-7（review fix）：用 ``is not None`` 而非 truthy；若 DB 出現意外
            # 空字串應 crash-fast（UUID("") raise ValueError）而非 silently 回 None。
            actor_id=UUID(orm.actor_id) if orm.actor_id is not None else None,
            note=orm.note,
            occurred_at=ensure_utc(orm.occurred_at) or _utc_now(),
        )
