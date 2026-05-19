"""MaterialRequestRepository — CRUD + state transitions + **atomic dispatch 雙寫**。

WMOM-20260509-02 / DN-03 §2.3。

責任：
1. ORM ↔ dataclass round-trip
2. CRUD：create / get / list / get_by_business_key
3. State machine wrapping：``transition`` 走 ``MaterialRequestStateMachine``
4. **``dispatch_request()`` — atomic 雙寫**：同 transaction 內 SELECT FOR UPDATE
   inventory + 扣 stock + 寫 cost_ledger + transition status；半路 raise → 全 rollback
5. ``add_return()``：建 MaterialReturn + 同 transaction 內加回 stock + 寫 ledger 沖銷
6. ``list_for_work_order()``：查工單關聯的所有 MR（取代「``work_order.material_request_ids``
   欄位回填」之 reverse-lookup 設計，不需 work_orders schema migration）

Business key：``MR-{farm_id_short}-{YYYYMM}-{NN}``（與 work_order 同 pattern）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

# Cost ledger imports are lazy (inside dispatch_request) to break the circular
# import chain: cost_ledger.py needs workflow.orm_models.Base, but
# workflow.repository.__init__ loads this material_request_repository which would
# need cost_ledger before it's done loading. Lazy import is the cleanest fix.

from modules.workflow.domain import InvalidTransition
from modules.workflow.domain.inventory import (
    MaterialRequest,
    MaterialRequestItem,
    MaterialRequestStatus,
    MaterialReturn,
    ReturnReason,
    StockKind,
    _utc_now,
)
from modules.workflow.domain.inventory_state_machine import (
    MaterialRequestStateMachine,
)

from ._helpers import ensure_utc, str_to_uuid, uuid_to_str
from .inventory_orm import (
    InventoryItemORM,
    MaterialRequestItemORM,
    MaterialRequestORM,
    MaterialReturnORM,
)
from .inventory_repository import (
    InsufficientStock,
    apply_stock_delta_in_session,
)
from .orm_models import Base
from .work_order_repository import (
    _ENGINE_LOCK,
    _SCHEMA_INITIALIZED,
    _farm_id_short,
    _get_engine,
)

_logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────


class MaterialRequestRuleViolation(Exception):
    """違反 business 規則（如 dispatch state mismatch、business_key 重覆）。"""


# ─────────────────────────────────────────────────────────────────────────
# Repository factory
# ─────────────────────────────────────────────────────────────────────────


def get_material_request_repository(db_path: str) -> "MaterialRequestRepository":
    engine = _get_engine(db_path)
    abs_path = str(Path(db_path).resolve())
    with _ENGINE_LOCK:
        if abs_path not in _SCHEMA_INITIALIZED:
            Base.metadata.create_all(engine)
            _SCHEMA_INITIALIZED.add(abs_path)
    return MaterialRequestRepository(engine)


# ─────────────────────────────────────────────────────────────────────────
# Repository
# ─────────────────────────────────────────────────────────────────────────


class MaterialRequestRepository:
    """SQLAlchemy 2.0 repository for material_requests + items + returns。"""

    def __init__(self, engine: Engine):
        self._engine = engine
        self._sessionmaker = sessionmaker(engine, expire_on_commit=False, future=True)

    # ──────────────────────────────────────────────────────────────────
    # CRUD
    # ──────────────────────────────────────────────────────────────────

    def create(
        self,
        *,
        farm_id: str,
        requester_id: UUID,
        items: list[tuple[UUID, int, StockKind]],
        work_order_id: UUID | None = None,
    ) -> MaterialRequest:
        """建 DRAFT 領料單 + 多筆 items。

        Args:
            items: list of (inventory_item_id, estimated_qty, stock_kind)。

        ``business_key`` 撞 unique 自動 retry 一次取下一個 NN。
        """
        if not items:
            raise MaterialRequestRuleViolation("create requires at least one item")

        last_err: Exception | None = None
        for _attempt in range(2):
            try:
                return self._create_once(
                    farm_id=farm_id,
                    requester_id=requester_id,
                    items=items,
                    work_order_id=work_order_id,
                )
            except IntegrityError as e:
                last_err = e
                if "business_key" not in str(e).lower():
                    raise
                continue
        raise MaterialRequestRuleViolation(
            f"business_key collision after retry, please retry: {last_err}"
        )

    def _create_once(
        self,
        *,
        farm_id: str,
        requester_id: UUID,
        items: list[tuple[UUID, int, StockKind]],
        work_order_id: UUID | None,
    ) -> MaterialRequest:
        with self._sessionmaker() as sess:
            mr_id = uuid4()
            business_key = self._next_business_key(sess, farm_id)
            now = _utc_now()
            orm = MaterialRequestORM(
                id=str(mr_id),
                business_key=business_key,
                farm_id=farm_id,
                requester_id=str(requester_id),
                work_order_id=str(work_order_id) if work_order_id else None,
                status=MaterialRequestStatus.DRAFT.value,
                requested_at=now,
                created_at=now,
                updated_at=now,
            )
            sess.add(orm)
            for (item_id, est_qty, kind) in items:
                if est_qty <= 0:
                    raise MaterialRequestRuleViolation(
                        f"item {item_id} estimated_qty must be > 0 (got {est_qty})"
                    )
                item_orm = MaterialRequestItemORM(
                    id=str(uuid4()),
                    request_id=str(mr_id),
                    item_id=str(item_id),
                    estimated_qty=est_qty,
                    stock_kind=kind.value,
                )
                sess.add(item_orm)
            sess.commit()
            sess.refresh(orm)
            return self._to_domain(orm)

    def get(self, mr_id: UUID) -> MaterialRequest | None:
        with self._sessionmaker() as sess:
            orm = sess.get(MaterialRequestORM, str(mr_id))
            return self._to_domain(orm) if orm else None

    def get_by_business_key(self, business_key: str) -> MaterialRequest | None:
        with self._sessionmaker() as sess:
            stmt = select(MaterialRequestORM).where(
                MaterialRequestORM.business_key == business_key
            )
            orm = sess.execute(stmt).scalar_one_or_none()
            return self._to_domain(orm) if orm else None

    def list(
        self,
        *,
        farm_id: str,
        work_order_id: UUID | None = None,
        status: MaterialRequestStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[MaterialRequest], int]:
        with self._sessionmaker() as sess:
            base = select(MaterialRequestORM).where(MaterialRequestORM.farm_id == farm_id)
            if work_order_id is not None:
                base = base.where(MaterialRequestORM.work_order_id == str(work_order_id))
            if status is not None:
                base = base.where(MaterialRequestORM.status == status.value)

            count_stmt = base.with_only_columns(MaterialRequestORM.id)
            total = len(sess.execute(count_stmt).scalars().all())

            paged = (
                base.order_by(MaterialRequestORM.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return (
                [self._to_domain(orm) for orm in sess.execute(paged).scalars().all()],
                total,
            )

    def list_for_work_order(self, work_order_id: UUID) -> list[MaterialRequest]:
        """查工單關聯的所有 MR（reverse-lookup 取代 work_order schema 內的 list[UUID]）。"""
        with self._sessionmaker() as sess:
            stmt = select(MaterialRequestORM).where(
                MaterialRequestORM.work_order_id == str(work_order_id)
            )
            return [
                self._to_domain(orm) for orm in sess.execute(stmt).scalars().all()
            ]

    def set_signoff_chain_id(self, mr_id: UUID, chain_id: UUID) -> None:
        """Wire signoff chain id 進 MR（給 approval router 在 submit_for_approval 後 backlink 用）。"""
        with self._sessionmaker() as sess:
            orm = sess.get(MaterialRequestORM, str(mr_id))
            if orm is None:
                raise LookupError(f"material_request {mr_id} not found")
            orm.signoff_chain_id = str(chain_id)
            orm.updated_at = _utc_now()
            sess.commit()

    # ──────────────────────────────────────────────────────────────────
    # State transition wrapper
    # ──────────────────────────────────────────────────────────────────

    def transition(
        self,
        mr_id: UUID,
        action: str,
        *,
        actor_id: UUID | None = None,
        **kwargs: Any,
    ) -> MaterialRequest:
        """走 ``MaterialRequestStateMachine`` + persist 變更。

        ⚠ ``dispatch`` action **不要** 透過此 entry — 用 ``dispatch_request()`` 才會做
        atomic 雙寫。直接呼叫 ``transition('dispatch')`` 只更新 status，不扣 stock 不寫
        ledger（domain layer guard 會通過但 caller 違反語意）。Defensive：本 method
        對 ``action == 'dispatch'`` raise 提示 caller 改 entry。
        """
        if action == "dispatch":
            raise MaterialRequestRuleViolation(
                "use MaterialRequestRepository.dispatch_request() for atomic stock + ledger write; "
                "do not call transition('dispatch') directly"
            )

        with self._sessionmaker() as sess:
            orm = sess.get(MaterialRequestORM, str(mr_id))
            if orm is None:
                raise LookupError(f"material_request {mr_id} not found")

            mr = self._to_domain(orm)
            # Domain 層走 state machine（會 raise InvalidTransition）
            MaterialRequestStateMachine.transition(
                mr, action, actor_id=actor_id, **kwargs
            )
            # 把 mutated dataclass 的變更 sync 回 ORM
            self._sync_to_orm(orm, mr)

            # receive: actual_qty 寫 items
            if action == "receive":
                actual_quantities = kwargs["actual_quantities"]
                # 重新 load items（domain 層已 mutate 過 dataclass，要把 dataclass.items
                # 內的 actual_qty 寫回 ORM 對應 item）
                # 逐筆比對 id 寫
                item_orms = sess.execute(
                    select(MaterialRequestItemORM).where(
                        MaterialRequestItemORM.request_id == str(mr_id)
                    )
                ).scalars().all()
                for io in item_orms:
                    if UUID(io.id) in actual_quantities:
                        io.actual_qty = actual_quantities[UUID(io.id)]

            sess.commit()
            sess.refresh(orm)
            return self._to_domain(orm)

    # ──────────────────────────────────────────────────────────────────
    # ATOMIC DISPATCH（M4 雙寫核心 — DN-03 §2.3）
    # ──────────────────────────────────────────────────────────────────

    def dispatch_request(
        self,
        mr_id: UUID,
        *,
        actor_id: UUID | None = None,
    ) -> MaterialRequest:
        """**Atomic dispatch** — 同 transaction 內：

        1. SELECT FOR UPDATE material_request（state must be APPROVED）
        2. 對每個 item：SELECT FOR UPDATE inventory + 扣 stock（不足 → InsufficientStock）
        3. 同 transaction 寫 cost_ledger entry（category=material, status=estimated,
           amount = estimated_qty × unit_cost）
        4. transition status APPROVED → DISPATCHED
        5. commit

        半路 raise → ``sess.rollback()`` → stock / ledger / status 全部不變。

        Raises:
            LookupError: MR 不存在
            InvalidTransition: 不在 APPROVED state
            InsufficientStock: 某 item 庫存不足扣
        """
        # Lazy import to break circular dependency
        from modules.cost.repository.cost_ledger import (
            CostLedgerCategory,
            CostLedgerEntry,
            CostLedgerSourceType,
            CostLedgerStatus,
            insert_in_session,
        )

        with self._sessionmaker() as sess:
            try:
                # ── Step 1: lock + load MR ─────────────────────────────
                stmt = (
                    select(MaterialRequestORM)
                    .where(MaterialRequestORM.id == str(mr_id))
                    .with_for_update()
                )
                mr_orm = sess.execute(stmt).scalar_one_or_none()
                if mr_orm is None:
                    raise LookupError(f"material_request {mr_id} not found")
                if mr_orm.status != MaterialRequestStatus.APPROVED.value:
                    raise InvalidTransition(
                        f"dispatch_request: cannot transition from {mr_orm.status!r} "
                        f"(must be APPROVED)",
                        reason="state_mismatch",
                    )

                # ── Step 2 + 3: per-item stock decrement + ledger ──────
                item_orms = sess.execute(
                    select(MaterialRequestItemORM).where(
                        MaterialRequestItemORM.request_id == str(mr_id)
                    )
                ).scalars().all()
                if not item_orms:
                    raise InvalidTransition(
                        "dispatch_request: MR has no items"
                    )

                for it in item_orms:
                    # lock + decrement stock（會 raise InsufficientStock）
                    inv_orm = apply_stock_delta_in_session(
                        sess,
                        item_id=UUID(it.item_id),
                        kind=StockKind(it.stock_kind),
                        delta=-it.estimated_qty,
                    )
                    # 寫 cost ledger entry（estimated）
                    # review fix #1：locked_unit_cost 鎖定 dispatch 當下的 unit_cost；
                    # confirm 時用此快照算 amount，避免 unit_cost 改動造成
                    # estimated/confirmed 不同基礎（會計做帳要求一致）
                    locked_cost = Decimal(str(inv_orm.unit_cost))
                    amount = Decimal(it.estimated_qty) * locked_cost
                    insert_in_session(
                        sess,
                        CostLedgerEntry(
                            farm_id=mr_orm.farm_id,
                            category=CostLedgerCategory.MATERIAL,
                            amount=amount,
                            source_event_id=UUID(mr_orm.id),
                            source_item_id=UUID(it.id),  # A5
                            locked_unit_cost=locked_cost,  # review fix #1
                            source_type=CostLedgerSourceType.MATERIAL_REQUEST,
                            status=CostLedgerStatus.ESTIMATED,
                            actor_id=actor_id,
                            note=f"item={it.item_id} qty={it.estimated_qty} {it.stock_kind}",
                        ),
                    )

                # ── Step 4: transition status ────────────────────────────
                now = _utc_now()
                mr_orm.status = MaterialRequestStatus.DISPATCHED.value
                mr_orm.dispatched_at = now
                mr_orm.updated_at = now

                # ── Step 5: commit ───────────────────────────────────────
                sess.commit()
                sess.refresh(mr_orm)
                return self._to_domain(mr_orm)
            except (LookupError, InvalidTransition, InsufficientStock):
                sess.rollback()
                raise
            except Exception:
                _logger.exception(
                    "dispatch_request %s failed unexpectedly — rolling back", mr_id
                )
                sess.rollback()
                raise

    # ──────────────────────────────────────────────────────────────────
    # Returns（D3-Q4 — atomic 加回 stock）
    # ──────────────────────────────────────────────────────────────────

    def add_return(
        self,
        *,
        request_id: UUID,
        item_id: UUID,
        qty: int,
        reason: ReturnReason,
        return_to_kind: StockKind,
        returned_by: UUID,
        note: str | None = None,
    ) -> MaterialReturn:
        """建 MaterialReturn 記錄 + 同 transaction 加回 stock。

        ⚠ 不寫 ledger 沖銷（A5 cost ledger 整合再做 — 用 wo_finish hook 算 actual_qty
           差異一次到位較精確）。本 method 只動 stock + log。
        """
        if qty <= 0:
            raise MaterialRequestRuleViolation(f"qty must be > 0 (got {qty})")

        with self._sessionmaker() as sess:
            try:
                mr_orm = sess.get(MaterialRequestORM, str(request_id))
                if mr_orm is None:
                    raise LookupError(f"material_request {request_id} not found")

                # 加回 stock（atomic）
                apply_stock_delta_in_session(
                    sess, item_id=item_id, kind=return_to_kind, delta=+qty
                )

                ret_id = uuid4()
                ret_orm = MaterialReturnORM(
                    id=str(ret_id),
                    request_id=str(request_id),
                    item_id=str(item_id),
                    qty=qty,
                    reason=reason.value,
                    return_to_kind=return_to_kind.value,
                    returned_by=str(returned_by),
                    note=note,
                    returned_at=_utc_now(),
                )
                sess.add(ret_orm)
                sess.commit()
                sess.refresh(ret_orm)
                return MaterialReturn(
                    id=ret_id,
                    request_id=request_id,
                    item_id=item_id,
                    qty=qty,
                    reason=reason,
                    return_to_kind=return_to_kind,
                    returned_by=returned_by,
                    note=note,
                    returned_at=ensure_utc(ret_orm.returned_at) or _utc_now(),
                )
            except Exception:
                sess.rollback()
                raise

    # ──────────────────────────────────────────────────────────────────
    # Item metadata batch fetch（WMOM-20260518-01）
    # ──────────────────────────────────────────────────────────────────

    def fetch_item_metadata(
        self,
        item_ids: list[UUID] | set[UUID] | tuple[UUID, ...],
        *,
        farm_id: str | None = None,
    ) -> dict[UUID, tuple[str | None, str | None, str | None]]:
        """批次取得 ``inventory_items`` 的 ``(sku, name, unit)`` — 給 router 在組裝
        ``MaterialRequestResponse`` 時 enrich items 的 display 欄位。

        Args:
            item_ids: 要查詢的 ``InventoryItem.id`` 清單；空集合直接回空 dict（避免 IN ()）。
            farm_id: 可選 — 限定 farm，給未來 multi-farm single-DB 部署做防禦；
                當前 single-farm-per-DB 架構下省略。

        Returns:
            ``{item_id: (sku, name, unit)}``；不存在 / 跨 farm 的 id 不會出現在回傳 dict
            中（caller 自行 fallback）。tuple 元素標 ``str | None`` 以防未來 schema 允許
            NULL（目前 ORM 為 NOT NULL）。
        """
        ids = [str(i) for i in item_ids]
        if not ids:
            return {}
        with self._sessionmaker() as sess:
            stmt = select(
                InventoryItemORM.id,
                InventoryItemORM.sku,
                InventoryItemORM.name,
                InventoryItemORM.unit,
            ).where(InventoryItemORM.id.in_(ids))
            if farm_id is not None:
                stmt = stmt.where(InventoryItemORM.farm_id == farm_id)
            return {
                UUID(row.id): (row.sku, row.name, row.unit)
                for row in sess.execute(stmt)
            }

    # ──────────────────────────────────────────────────────────────────
    # Business key 自動編號（同 work_order pattern）
    # ──────────────────────────────────────────────────────────────────

    def _next_business_key(self, sess: Session, farm_id: str) -> str:
        """``MR-{farm_id_short}-{YYYYMM}-{NN}``。"""
        now = datetime.now(tz=timezone.utc)
        ym = now.strftime("%Y%m")
        prefix = f"MR-{_farm_id_short(farm_id)}-{ym}-"
        # SQL: SELECT COUNT(*) WHERE business_key LIKE 'MR-...-' + 1
        stmt = select(func.count(MaterialRequestORM.id)).where(
            MaterialRequestORM.business_key.like(f"{prefix}%")
        )
        existing = sess.execute(stmt).scalar_one()
        nn = existing + 1
        return f"{prefix}{nn:02d}"

    # ──────────────────────────────────────────────────────────────────
    # ORM ↔ domain
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _to_domain(orm: MaterialRequestORM) -> MaterialRequest:
        return MaterialRequest(
            id=UUID(orm.id),
            business_key=orm.business_key,
            farm_id=orm.farm_id,
            requester_id=UUID(orm.requester_id),
            work_order_id=str_to_uuid(orm.work_order_id),
            status=MaterialRequestStatus(orm.status),
            items=[
                MaterialRequestItem(
                    id=UUID(it.id),
                    request_id=UUID(it.request_id),
                    item_id=UUID(it.item_id),
                    estimated_qty=it.estimated_qty,
                    actual_qty=it.actual_qty,
                    stock_kind=StockKind(it.stock_kind),
                )
                for it in (orm.items or [])
            ],
            signoff_chain_id=str_to_uuid(orm.signoff_chain_id),
            requested_at=ensure_utc(orm.requested_at) or _utc_now(),
            submitted_at=ensure_utc(orm.submitted_at),
            approved_at=ensure_utc(orm.approved_at),
            dispatched_at=ensure_utc(orm.dispatched_at),
            received_at=ensure_utc(orm.received_at),
            used_at=ensure_utc(orm.used_at),
            closed_at=ensure_utc(orm.closed_at),
            cancelled_at=ensure_utc(orm.cancelled_at),
            rejected_at=ensure_utc(orm.rejected_at),
            cancel_reason=orm.cancel_reason,
            reject_reason=orm.reject_reason,
            created_at=ensure_utc(orm.created_at) or _utc_now(),
            updated_at=ensure_utc(orm.updated_at) or _utc_now(),
        )

    @staticmethod
    def _sync_to_orm(orm: MaterialRequestORM, mr: MaterialRequest) -> None:
        """把 mutated dataclass 的變更回寫 ORM（status / timestamps / reasons）。"""
        orm.status = mr.status.value
        orm.submitted_at = mr.submitted_at
        orm.approved_at = mr.approved_at
        orm.dispatched_at = mr.dispatched_at
        orm.received_at = mr.received_at
        orm.used_at = mr.used_at
        orm.closed_at = mr.closed_at
        orm.cancelled_at = mr.cancelled_at
        orm.rejected_at = mr.rejected_at
        orm.cancel_reason = mr.cancel_reason
        orm.reject_reason = mr.reject_reason
        orm.updated_at = mr.updated_at
