"""WMOM-20260519-01：`add_return` 超量退料 domain guard（F1 follow-up）。

Guard 公式：``max_returnable = physical_ceiling - already_returned``，其中
``physical_ceiling`` per-line = ``actual_qty if not None else estimated_qty``
跨 stock_kind 聚合 by (request_id, item_id)。

驗證：
- 退料 qty 超過 ``max_returnable`` → raise ``MaterialRequestRuleViolation``，
  整 transaction rollback（stock / return / ledger 都不變）
- 跨 stock_kind 聚合：dispatch NEW 5 → return USED 5 允許（cross-kind 試裝後歸二手）
- 多 line 同 item 聚合：MR 含 (NEW 3, USED 2) 同一 item → return USED 5 允許
- 累進退料：dispatch 5、退 3、再退 3 → 第二次擋（累積 6 > 5）
- ``actual_qty`` 為 receive 簽收量（**非** mark_used 耗用量）：
  - estimated=2, actual=1（簽收 1）→ 退 2 擋（max=1）；退 1 允許
  - estimated=5, actual=5（簽收全部）→ 退 1 surplus 允許（max=5-0=5）
  - estimated=5, actual=0（簽收 0，全是壞料退）→ 退 5 允許（max=5-0=5，physical
    ceiling 用 estimated 因 actual=0... 等等：actual=0 ≠ None, 用 actual=0，max=0
    擋全退；測試覆蓋此 edge case 並備 follow-up）
- 邊界：dispatched=N → 退 N 允許（剛好用完）
- DRAFT MR（pre-dispatch / pre-receive）也擋超量（用 estimated_qty 作 ceiling）
- item 不在 MR → raise（避免 phantom inventory）
- Atomic：guard 失敗 → already_returned 累計值不變
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.cost.repository.cost_ledger import (  # noqa: E402
    CostLedgerEntryORM,
)
from modules.workflow.domain.inventory import (  # noqa: E402
    ReturnReason,
    StockKind,
)
from modules.workflow.repository import (  # noqa: E402
    InventoryRepository,
    MaterialRequestRepository,
    MaterialRequestRuleViolation,
    get_inventory_repository,
    get_material_request_repository,
)
from modules.workflow.repository.inventory_orm import (  # noqa: E402
    MaterialRequestItemORM,
    MaterialReturnORM,
)
from modules.workflow.repository.work_order_repository import (  # noqa: E402
    clear_engine_cache_for_test,
)


# ─────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "wind_farm.db")


@pytest.fixture
def repos(db_path):
    clear_engine_cache_for_test()
    inv = get_inventory_repository(db_path)
    mr = get_material_request_repository(db_path)
    yield inv, mr
    clear_engine_cache_for_test()


def _setup_dispatched_mr(
    inv_repo: InventoryRepository,
    mr_repo: MaterialRequestRepository,
    *,
    initial_stock: int = 10,
    estimated_qty: int = 5,
    unit_cost: Decimal = Decimal("300.00"),
    farm_id: str = "f",
    stock_kind: StockKind = StockKind.NEW,
) -> tuple[UUID, UUID]:
    """建一個 APPROVED → DISPATCHED 的 MR + 回傳 (mr_id, item_id)。"""
    wh = inv_repo.create_warehouse(farm_id=farm_id, name="W", is_default=True)
    item = inv_repo.create_item(
        sku="X-1", name="x", description="x", unit="piece",
        farm_id=farm_id, warehouse_id=wh.id, unit_cost=unit_cost,
        stock_new=initial_stock if stock_kind == StockKind.NEW else 0,
        stock_used=initial_stock if stock_kind == StockKind.USED else 0,
    )
    mr = mr_repo.create(
        farm_id=farm_id, requester_id=uuid4(),
        items=[(item.id, estimated_qty, stock_kind)],
    )
    mr_repo.transition(mr.id, "submit_for_approval")
    mr_repo.transition(mr.id, "approve_all")
    mr_repo.dispatch_request(mr.id)
    return mr.id, item.id


def _set_actual_qty(
    mr_repo: MaterialRequestRepository,
    mr_id: UUID,
    item_id: UUID,
    actual_qty: int,
) -> None:
    """直接 ORM-level 寫 actual_qty（避開 wo finish lifecycle，guard test 只關心
    actual_qty 的值是否影響 max_returnable 公式）。"""
    with mr_repo._sessionmaker() as sess:
        row = sess.execute(
            select(MaterialRequestItemORM).where(
                MaterialRequestItemORM.request_id == str(mr_id),
                MaterialRequestItemORM.item_id == str(item_id),
            )
        ).scalar_one()
        row.actual_qty = actual_qty
        sess.commit()


# ─────────────────────────────────────────────────────────────────────────
# Negative path：超量擋
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_rejects_over_dispatched_single_shot(repos):
    """dispatched=5，單次退 6 → MaterialRequestRuleViolation。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=5,
    )
    with pytest.raises(MaterialRequestRuleViolation, match="超過可退上限"):
        mr_repo.add_return(
            request_id=mr_id, item_id=item_id, qty=6,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW, returned_by=uuid4(),
        )


def test_add_return_rejects_over_returned_cumulative(repos):
    """dispatched=5，先退 3、再退 3 → 第二次擋（累積 6 > 5）。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=5,
    )
    mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=3,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW, returned_by=uuid4(),
    )
    with pytest.raises(MaterialRequestRuleViolation, match="已退=3"):
        mr_repo.add_return(
            request_id=mr_id, item_id=item_id, qty=3,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW, returned_by=uuid4(),
        )

    # Review SF#3 — 失敗的第二次呼叫不應改變 already_returned 累計
    with mr_repo._sessionmaker() as sess:
        from sqlalchemy import func as sql_func
        actual_returned = sess.execute(
            select(sql_func.coalesce(sql_func.sum(MaterialReturnORM.qty), 0)).where(
                MaterialReturnORM.request_id == str(mr_id),
                MaterialReturnORM.item_id == str(item_id),
            )
        ).scalar_one()
    assert int(actual_returned) == 3, "已退累計仍應為 3，超量第二次不可改寫"


def test_add_return_rejects_over_received_after_receive(repos):
    """estimated=2, actual_qty=1（receive 簽收 1）→ 退 2 擋（max=1-0=1）。

    這是 F1 motivating bug 的正確 semantic（actual_qty 是 receive 簽收量，
    **不是** mark_used 耗用量）。
    """
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=5, estimated_qty=2,
    )
    _set_actual_qty(mr_repo, mr_id, item_id, actual_qty=1)
    with pytest.raises(MaterialRequestRuleViolation, match="簽收量=1"):
        mr_repo.add_return(
            request_id=mr_id, item_id=item_id, qty=2,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW, returned_by=uuid4(),
        )


def test_add_return_rejects_unknown_item_in_mr(repos):
    """item 不在 MR 內 → raise（避免 phantom inventory）。"""
    inv_repo, mr_repo = repos
    mr_id, _real_item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=5, estimated_qty=2,
    )
    phantom_item_id = uuid4()
    with pytest.raises(MaterialRequestRuleViolation, match="不在 MR"):
        mr_repo.add_return(
            request_id=mr_id, item_id=phantom_item_id, qty=1,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW, returned_by=uuid4(),
        )


def test_add_return_draft_mr_rejects_over_estimated(repos):
    """Review MF#3 — DRAFT MR 也擋超量（用 estimated_qty 作 ceiling）。

    F1 既有 fallback test `test_add_return_without_dispatch_entry_uses_inventory_fallback`
    證明 DRAFT 退料可走（ledger fallback）；本 test 明確 document 即使 DRAFT
    狀態也受 guard 約束（estimated_qty=2 → 退 3 擋）。
    """
    inv_repo, mr_repo = repos
    wh = inv_repo.create_warehouse(farm_id="f", name="W", is_default=True)
    item = inv_repo.create_item(
        sku="X-DRAFT", name="x", description="x", unit="piece",
        farm_id="f", warehouse_id=wh.id, unit_cost=Decimal("100.00"),
        stock_new=10,
    )
    mr = mr_repo.create(
        farm_id="f", requester_id=uuid4(),
        items=[(item.id, 2, StockKind.NEW)],
    )
    # 不 dispatch — 留在 DRAFT
    with pytest.raises(MaterialRequestRuleViolation, match="超過可退上限"):
        mr_repo.add_return(
            request_id=mr.id, item_id=item.id, qty=3,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW, returned_by=uuid4(),
        )


# ─────────────────────────────────────────────────────────────────────────
# Happy path：邊界 / 跨 kind / 多 line aggregate
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_allows_full_return_pre_wo_finish(repos):
    """dispatched=2, actual 未設, 退 2 → 允許（max=2-0-0=2）。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=5, estimated_qty=2,
        unit_cost=Decimal("100.00"),
    )
    ret = mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=2,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW, returned_by=uuid4(),
    )
    assert ret.qty == 2
    # stock 加回（dispatch 扣 2 → 3 → 退 2 回 → 5）
    assert inv_repo.get_item(item_id).stock_new == 5


def test_add_return_allows_return_within_received_ceiling(repos):
    """estimated=2, actual=1（簽收 1）, 退 1 → 允許（max=1-0=1）。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=5, estimated_qty=2,
        unit_cost=Decimal("300.00"),
    )
    _set_actual_qty(mr_repo, mr_id, item_id, actual_qty=1)
    ret = mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=1,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW, returned_by=uuid4(),
    )
    assert ret.qty == 1


def test_add_return_allows_surplus_after_full_receive(repos):
    """Review SF#2 — estimated=5, actual=5（全簽收）, 退 1 surplus → 允許（max=5-0=5）。

    這是 F1 motivating scenario 的「正常 surplus」情境：簽收全部後，工地使用 4 件，
    把多的 1 件退回庫存。Guard 不可誤殺此合法 surplus return — 修正前
    `max=estimated-actual=0` 會 false-positive 擋掉。
    """
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=5,
        unit_cost=Decimal("200.00"),
    )
    _set_actual_qty(mr_repo, mr_id, item_id, actual_qty=5)
    ret = mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=1,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW, returned_by=uuid4(),
    )
    assert ret.qty == 1


def test_add_return_guard_cross_stock_kind_aggregates_by_item(repos):
    """dispatch NEW 5 → return USED 5 → 允許（cross-kind 聚合 by item_id）。"""
    inv_repo, mr_repo = repos
    # NEW 出貨 5 → return USED 5（試裝失敗歸二手 stock）
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=5, estimated_qty=5,
        stock_kind=StockKind.NEW, unit_cost=Decimal("200.00"),
    )
    ret = mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=5,
        reason=ReturnReason.FAILED_INSTALL,
        return_to_kind=StockKind.USED, returned_by=uuid4(),
    )
    assert ret.qty == 5
    # NEW dispatch 後 stock_new=0；return USED → stock_used=5
    inv = inv_repo.get_item(item_id)
    assert inv.stock_new == 0
    assert inv.stock_used == 5


def test_add_return_guard_multi_line_same_item_aggregates(repos):
    """MR 含 (NEW 3, USED 2) 同一 item → return USED 5 ≤ 5 允許。"""
    inv_repo, mr_repo = repos
    wh = inv_repo.create_warehouse(farm_id="f", name="W", is_default=True)
    item = inv_repo.create_item(
        sku="MULTI", name="m", description="m", unit="piece",
        farm_id="f", warehouse_id=wh.id, unit_cost=Decimal("100.00"),
        stock_new=10, stock_used=10,
    )
    mr = mr_repo.create(
        farm_id="f", requester_id=uuid4(),
        items=[
            (item.id, 3, StockKind.NEW),
            (item.id, 2, StockKind.USED),
        ],
    )
    mr_repo.transition(mr.id, "submit_for_approval")
    mr_repo.transition(mr.id, "approve_all")
    mr_repo.dispatch_request(mr.id)

    # 5 是 total dispatched（3 NEW + 2 USED 聚合）
    ret = mr_repo.add_return(
        request_id=mr.id, item_id=item.id, qty=5,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.USED, returned_by=uuid4(),
    )
    assert ret.qty == 5

    # 第 6 件超量 → 擋
    with pytest.raises(MaterialRequestRuleViolation, match="超過可退上限"):
        mr_repo.add_return(
            request_id=mr.id, item_id=item.id, qty=1,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW, returned_by=uuid4(),
        )


# ─────────────────────────────────────────────────────────────────────────
# Atomic：guard 失敗 → stock / return / ledger 全不寫
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_over_return_atomic_no_side_effects(repos):
    """超量退料擋 → stock 不變、MaterialReturn 不寫、ledger offset 不寫。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=3,
        unit_cost=Decimal("100.00"),
    )
    stock_before = inv_repo.get_item(item_id).stock_new  # 7 (10-3)

    with mr_repo._sessionmaker() as sess:
        returns_before = len(
            sess.execute(select(MaterialReturnORM)).scalars().all()
        )
        ledger_before = len(
            sess.execute(select(CostLedgerEntryORM)).scalars().all()
        )

    with pytest.raises(MaterialRequestRuleViolation):
        mr_repo.add_return(
            request_id=mr_id, item_id=item_id, qty=99,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW, returned_by=uuid4(),
        )

    # 三邊都不變
    assert inv_repo.get_item(item_id).stock_new == stock_before
    with mr_repo._sessionmaker() as sess:
        returns_after = len(
            sess.execute(select(MaterialReturnORM)).scalars().all()
        )
        ledger_after = len(
            sess.execute(select(CostLedgerEntryORM)).scalars().all()
        )
    assert returns_after == returns_before
    assert ledger_after == ledger_before
