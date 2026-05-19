"""MaterialRequestRepository — CRUD + state transitions + **atomic dispatch 雙寫**。

WMOM-20260509-02 / DN-03 §2.3。

責任：
1. ORM ↔ dataclass round-trip
2. CRUD：create / get / list / get_by_business_key
3. State machine wrapping：``transition`` 走 ``MaterialRequestStateMachine``
4. **``dispatch_request()`` — atomic 雙寫**：同 transaction 內 SELECT FOR UPDATE
   inventory + 扣 stock + 寫 cost_ledger + transition status；半路 raise → 全 rollback
5. ``add_return()``：建 MaterialReturn + 同 transaction 內加回 stock + 寫 ledger 沖銷
   entry（negative amount, confirmed；WMOM-20260509-F1 2026-05-19 補完）
6. ``list_for_work_order()``：查工單關聯的所有 MR（取代「``work_order.material_request_ids``
   欄位回填」之 reverse-lookup 設計，不需 work_orders schema migration）

Business key：``MR-{farm_id_short}-{YYYYMM}-{NN}``（與 work_order 同 pattern）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable
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


@dataclass(frozen=True)
class ItemMetadata:
    """`MaterialRequestItem.item_id` 對應 InventoryItem 的 view-projection metadata。

    給 router response builder 用 — 不放進 domain `MaterialRequestItem`，避免污染
    aggregate 內部（SKU/名稱/單位屬於 InventoryItem 主檔）。
    """

    sku: str
    name: str
    unit: str


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

    def resolve_item_metadata(
        self, item_ids: Iterable[UUID]
    ) -> dict[UUID, ItemMetadata]:
        """Batch fetch (sku, name, unit) 給 router response builder。

        - 走同一 farm DB engine 一次 SQL `SELECT id, sku, name, unit FROM inventory_items WHERE id IN (...)`
        - 缺漏 item_id（data drift / 已刪）→ key 不存在於回傳 dict（不 raise）
        - empty input → 直接 `{}`，避免發 0-row IN 查詢
        - ``item_ids`` 為 ``Iterable`` 但**只消費一次**（先 materialise 成 set）；
          caller 可放 set / list / generator 均可
        """
        ids = {str(i) for i in item_ids}
        if not ids:
            return {}
        with self._sessionmaker() as sess:
            stmt = select(
                InventoryItemORM.id,
                InventoryItemORM.sku,
                InventoryItemORM.name,
                InventoryItemORM.unit,
            ).where(InventoryItemORM.id.in_(ids))
            rows = sess.execute(stmt).all()
            return {
                UUID(row.id): ItemMetadata(sku=row.sku, name=row.name, unit=row.unit)
                for row in rows
            }

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
        """建 MaterialReturn 記錄 + 同 transaction 加回 stock + 寫 ledger 沖銷 entry。

        Atomic 三寫（WMOM-20260509-F1，2026-05-19 補完）：
        1. ``apply_stock_delta_in_session`` 加回 stock
        2. 寫入 ``MaterialReturn`` audit record
        3. 寫入 ``cost_ledger_entries`` 沖銷 entry（**negative amount**, status=confirmed）

        沖銷 entry 設計：
        - ``amount = -(qty × locked_unit_cost from dispatch entry)``，會計一致性
          原則用 dispatch 當下鎖定的 unit_cost，**不**用當前 inventory unit_cost
        - ``status = CONFIRMED + confirmed_at = now``，退料是已發生的 actual cash flow
          （不是估值），月報 confirmed 視角立即看到沖銷
        - ``source_item_id = MaterialReturn.id``（不是 mr_item.id），避免 wo finish
          confirm hook 的 ``find_for_mr_item`` 撈出多筆而拋例外；dispatch entry 仍維持
          原 ``source_item_id = mr_item.id``，hook 只動 dispatch entry

        Fallback：
        - 找不到對應 dispatch ledger entry（罕見：MR 未 dispatch 直接 return / dispatch
          失敗但 status 已推進）→ log warning + **不寫 ledger entry**，仍寫 stock + return
          紀錄（業務需求：退料動作不可被 ledger 寫入失敗阻斷）
        - dispatch entry 的 ``locked_unit_cost`` 為 None（向後相容老 entries）→ fallback
          查當前 inventory ``unit_cost``

        Domain guard（WMOM-20260519-01）：
        - 退料總量不可超過「dispatched − consumed」的物理上限：
          ``existing_returns(item_id) + qty <= MaterialRequest.compute_returnable_upper_bound(item_id)``
        - 超量 raise ``MaterialRequestRuleViolation``（router → 422）；stock / ledger 全
          不動。例如 dispatched 2 / actual_qty=1 / return 2 之 F1 邊界場景，月報 confirmed
          視角不再可能變負值。
        - guard 用 ``item_id`` aggregate 不 group by ``stock_kind`` — cross-kind 退料（如
          dispatch NEW、退 USED）視為同一料件總帳。
        """
        if qty <= 0:
            raise MaterialRequestRuleViolation(f"qty must be > 0 (got {qty})")

        # Lazy import to break circular dependency（同 dispatch_request pattern）；
        # CostLedgerEntryORM 由 `_lookup_offset_unit_cost` 自己的 lazy import 引入，這裡不需要
        from modules.cost.repository.cost_ledger import (
            CostLedgerCategory,
            CostLedgerEntry,
            CostLedgerSourceType,
            CostLedgerStatus,
            insert_in_session,
        )

        with self._sessionmaker() as sess:
            try:
                mr_orm = sess.get(MaterialRequestORM, str(request_id))
                if mr_orm is None:
                    raise LookupError(f"material_request {request_id} not found")

                # ── Domain guard（WMOM-20260519-01）：超量退料擋下 ──────────
                # upper_bound = dispatched − consumed（pure-domain）；caller 加
                # already_returned 比對。等值邊界（剛好把剩餘量退完）也允許。
                #
                # ⚠ MR status 未列為 guard（DRAFT 直接 add_return 仍會 stock += qty）；
                # 由 WMOM-20260519-02 follow-up 評估是否要擋 — 本 PR scope 只解決會計
                # 視角負值漏洞。
                mr = self._to_domain(mr_orm)
                upper_bound = mr.compute_returnable_upper_bound(item_id)
                # SQLAlchemy `coalesce(SUM, 0)` 在 SQLite 回 int、PostgreSQL 可能回 Decimal；
                # 強制 int() 保證 + qty / 比較 upper_bound（int）型別安全
                already_returned = int(sess.execute(
                    select(func.coalesce(func.sum(MaterialReturnORM.qty), 0)).where(
                        MaterialReturnORM.request_id == str(request_id),
                        MaterialReturnORM.item_id == str(item_id),
                    )
                ).scalar_one())
                if already_returned + qty > upper_bound:
                    raise MaterialRequestRuleViolation(
                        f"add_return: qty={qty} exceeds remaining returnable "
                        f"({upper_bound - already_returned}); "
                        f"dispatched − consumed = {upper_bound}, "
                        f"already_returned = {already_returned}, "
                        f"request_id={request_id}, item_id={item_id}"
                    )

                # 加回 stock（atomic）
                apply_stock_delta_in_session(
                    sess, item_id=item_id, kind=return_to_kind, delta=+qty
                )

                ret_id = uuid4()
                now = _utc_now()
                ret_orm = MaterialReturnORM(
                    id=str(ret_id),
                    request_id=str(request_id),
                    item_id=str(item_id),
                    qty=qty,
                    reason=reason.value,
                    return_to_kind=return_to_kind.value,
                    returned_by=str(returned_by),
                    note=note,
                    returned_at=now,
                )
                sess.add(ret_orm)

                # ── 寫 ledger 沖銷 entry（F1）─────────────────────────────
                locked_cost = self._lookup_offset_unit_cost(
                    sess,
                    request_id=request_id,
                    item_id=item_id,
                    return_to_kind=return_to_kind,
                )
                if locked_cost is None:
                    _logger.warning(
                        "add_return: cannot resolve locked_unit_cost for MR %s item %s "
                        "(no dispatch ledger entry AND inventory item missing) — "
                        "ledger offset entry SKIPPED",
                        request_id, item_id,
                    )
                else:
                    offset_amount = -(Decimal(qty) * locked_cost)
                    insert_in_session(
                        sess,
                        CostLedgerEntry(
                            farm_id=mr_orm.farm_id,
                            category=CostLedgerCategory.MATERIAL,
                            amount=offset_amount,
                            source_event_id=request_id,
                            source_item_id=ret_id,  # 區隔 dispatch entry 的 mr_item.id
                            locked_unit_cost=locked_cost,
                            source_type=CostLedgerSourceType.MATERIAL_REQUEST,
                            status=CostLedgerStatus.CONFIRMED,
                            actor_id=returned_by,
                            note=(
                                f"退料 reason={reason.value} qty={qty} "
                                f"return_to={return_to_kind.value} item={item_id}"
                            ),
                            confirmed_at=now,
                        ),
                    )

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

    @staticmethod
    def _lookup_offset_unit_cost(
        sess: Session,
        *,
        request_id: UUID,
        item_id: UUID,
        return_to_kind: StockKind,
    ) -> Decimal | None:
        """找退料沖銷 entry 應該用的 unit_cost（會計一致性原則）。

        策略：
        1. 找 MR 對應的 dispatch ledger entry（source_event_id=request_id,
           source_type=material_request, category=material, status=estimated 或 confirmed
           — confirm 後 status 已翻；不過濾 status，含兩種都 match）
           → 同 inventory item_id 的 line 可能多筆（不同 stock_kind） → 用
           return_to_kind 過濾優先；剩 > 1 取第一個 + 預設足夠
        2. 沒對應 dispatch entry → fallback 查 inventory_items.unit_cost（當前值）
        3. 仍無 → return None（caller log warning + skip ledger entry）

        Cross-kind return 語意（review SF#1 補強）：
        若 dispatch 的 stock_kind 與 return_to_kind 不同（例如派 NEW 退到 USED，因試裝後
        歸回二手 stock），``matched`` 為空，``candidates`` fallback 到全部 mr_item_orms。
        此時取任一 dispatch entry 的 ``locked_unit_cost`` 仍符合會計一致性原則 — 沖銷金額
        反映 **dispatch 時的成本**，與 return_to_kind 對應的 inventory 當前 unit_cost 無關。
        """
        # Lazy import — 避免 module 載入時抓 cost_ledger 觸發 circular
        from modules.cost.repository.cost_ledger import (
            CostLedgerCategory,
            CostLedgerEntryORM,
            CostLedgerSourceType,
        )

        # ── Step 1: dispatch entry locked_unit_cost ─────────────────────
        # 找對應 MaterialRequestItem(s)：(request_id, item_id, stock_kind=return_to_kind)
        # 若無 stock_kind 對應，退而求其次只 by item_id（多 line 取第一）。
        mr_item_orms = sess.execute(
            select(MaterialRequestItemORM).where(
                MaterialRequestItemORM.request_id == str(request_id),
                MaterialRequestItemORM.item_id == str(item_id),
            )
        ).scalars().all()
        # 優先選 stock_kind == return_to_kind 的 line（最常見場景）
        matched = [
            it for it in mr_item_orms if it.stock_kind == return_to_kind.value
        ]
        candidates = matched if matched else mr_item_orms
        for it in candidates:
            ledger_orm = sess.execute(
                select(CostLedgerEntryORM).where(
                    CostLedgerEntryORM.source_event_id == str(request_id),
                    CostLedgerEntryORM.source_item_id == str(it.id),
                    CostLedgerEntryORM.source_type
                    == CostLedgerSourceType.MATERIAL_REQUEST.value,
                    CostLedgerEntryORM.category == CostLedgerCategory.MATERIAL.value,
                )
            ).scalar_one_or_none()
            if ledger_orm is not None and ledger_orm.locked_unit_cost is not None:
                return Decimal(str(ledger_orm.locked_unit_cost))

        # ── Step 2: fallback 查當前 inventory unit_cost ─────────────────
        inv_orm = sess.execute(
            select(InventoryItemORM).where(InventoryItemORM.id == str(item_id))
        ).scalar_one_or_none()
        if inv_orm is not None:
            return Decimal(str(inv_orm.unit_cost))

        return None

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
                    # WMOM-20260518-01：viewonly relationship 拉 InventoryItem metadata；
                    # cross-DB / 缺對映時 inventory_item 為 None，三欄保持 None 不阻斷 lifecycle
                    sku=(it.inventory_item.sku if it.inventory_item else None),
                    name=(it.inventory_item.name if it.inventory_item else None),
                    unit=(it.inventory_item.unit if it.inventory_item else None),
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
