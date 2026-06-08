"""超量退料 guard 測試（WMOM-20260519-01 / 採 PR #41 review-後 physical_ceiling semantic）。

封堵 F1 會計邊界：退料超過實體可退上限會寫過頭的 negative ledger offset，
使月報 ``summary_by_category(CONFIRMED)`` 出現負值材料成本。guard 從源頭擋。

physical_ceiling = actual_qty if set else estimated_qty；聚合 by (request_id, item_id)。
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

from modules.cost.repository.cost_ledger import CostLedgerEntryORM  # noqa: E402
from modules.workflow.domain.inventory import ReturnReason, StockKind  # noqa: E402
from modules.workflow.repository import (  # noqa: E402
    InventoryRepository,
    MaterialRequestRepository,
    get_inventory_repository,
    get_material_request_repository,
)
from modules.workflow.repository.inventory_orm import MaterialReturnORM  # noqa: E402
from modules.workflow.repository.material_request_repository import (  # noqa: E402
    MaterialRequestRuleViolation,
)
from modules.workflow.repository.work_order_repository import (  # noqa: E402
    clear_engine_cache_for_test,
)


@pytest.fixture
def repos(tmp_path):
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")
    yield get_inventory_repository(db_path), get_material_request_repository(db_path)
    clear_engine_cache_for_test()


def _setup_dispatched_mr(
    inv_repo: InventoryRepository,
    mr_repo: MaterialRequestRepository,
    *,
    estimated_qty: int = 3,
    initial_stock: int = 20,
) -> tuple[UUID, UUID, UUID]:
    """建 DISPATCHED MR，回 (mr_id, inventory_item_id, line_item_id)。"""
    wh = inv_repo.create_warehouse(farm_id="f", name="W", is_default=True)
    item = inv_repo.create_item(
        sku="X-1", name="x", description="x", unit="piece",
        farm_id="f", warehouse_id=wh.id, unit_cost=Decimal("100.00"),
        stock_new=initial_stock,
    )
    mr = mr_repo.create(
        farm_id="f", requester_id=uuid4(),
        items=[(item.id, estimated_qty, StockKind.NEW)],
    )
    mr_repo.transition(mr.id, "submit_for_approval")
    mr_repo.transition(mr.id, "approve_all")
    mr_repo.dispatch_request(mr.id)
    line_id = mr_repo.get(mr.id).items[0].id
    return mr.id, item.id, line_id


def _return(mr_repo, mr_id, item_id, qty):
    return mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=qty,
        reason=ReturnReason.SURPLUS, return_to_kind=StockKind.NEW, returned_by=uuid4(),
    )


# ─────────────────────────────────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────────────────────────────────


def test_return_within_estimated_ceiling_ok(repos):
    """未簽收前以 estimated 為上限：estimated=3，退 3 → OK。"""
    inv, mr = repos
    mr_id, item_id, _ = _setup_dispatched_mr(inv, mr, estimated_qty=3)
    ret = _return(mr, mr_id, item_id, 3)
    assert ret.qty == 3


def test_partial_returns_up_to_ceiling_ok(repos):
    """累進退到剛好上限：estimated=3，退 2 + 退 1 → OK。"""
    inv, mr = repos
    mr_id, item_id, _ = _setup_dispatched_mr(inv, mr, estimated_qty=3)
    _return(mr, mr_id, item_id, 2)
    _return(mr, mr_id, item_id, 1)  # 累計 3 = ceiling，仍 OK


# ─────────────────────────────────────────────────────────────────────────
# Negative path
# ─────────────────────────────────────────────────────────────────────────


def test_return_over_estimated_ceiling_rejected(repos):
    """estimated=3，退 4 → 超量 → MaterialRequestRuleViolation。"""
    inv, mr = repos
    mr_id, item_id, _ = _setup_dispatched_mr(inv, mr, estimated_qty=3)
    with pytest.raises(MaterialRequestRuleViolation, match="超過可退上限"):
        _return(mr, mr_id, item_id, 4)


def test_cumulative_return_over_ceiling_rejected(repos):
    """estimated=3，退 2 後再退 2（累計 4 > 3）→ 第二次超量。"""
    inv, mr = repos
    mr_id, item_id, _ = _setup_dispatched_mr(inv, mr, estimated_qty=3)
    _return(mr, mr_id, item_id, 2)
    with pytest.raises(MaterialRequestRuleViolation, match="超過可退上限"):
        _return(mr, mr_id, item_id, 2)


def test_received_actual_lowers_ceiling(repos):
    """F1 bug 核心：dispatched 3 但簽收 actual=1 → 上限降為 1，退 2 → 422。"""
    inv, mr = repos
    mr_id, item_id, line_id = _setup_dispatched_mr(inv, mr, estimated_qty=3)
    mr.transition(mr_id, "receive", actor_id=uuid4(), actual_quantities={line_id: 1})
    # ceiling 現在是 actual=1，退 2 超量。
    with pytest.raises(MaterialRequestRuleViolation, match="超過可退上限"):
        _return(mr, mr_id, item_id, 2)
    # 退 1 剛好 → OK。
    assert _return(mr, mr_id, item_id, 1).qty == 1


def test_return_item_not_in_mr_rejected(repos):
    """退一個不在 MR 領料清單的料件（ceiling=0）→ 422。"""
    inv, mr = repos
    mr_id, _item_id, _ = _setup_dispatched_mr(inv, mr, estimated_qty=3)
    with pytest.raises(MaterialRequestRuleViolation, match="上限"):
        _return(mr, mr_id, uuid4(), 1)  # 隨機 item_id 不在 MR


def test_guard_failure_is_atomic(repos):
    """guard 擋下時 stock / MaterialReturn / ledger 三邊皆不變（atomic rollback）。"""
    inv, mr = repos
    mr_id, item_id, _ = _setup_dispatched_mr(inv, mr, estimated_qty=3)
    stock_before = inv.get_item(item_id).stock_new
    with mr._sessionmaker() as sess:
        returns_before = len(sess.execute(select(MaterialReturnORM)).scalars().all())
        ledger_before = len(sess.execute(select(CostLedgerEntryORM)).scalars().all())

    with pytest.raises(MaterialRequestRuleViolation):
        _return(mr, mr_id, item_id, 99)

    assert inv.get_item(item_id).stock_new == stock_before
    with mr._sessionmaker() as sess:
        assert len(sess.execute(select(MaterialReturnORM)).scalars().all()) == returns_before
        assert len(sess.execute(select(CostLedgerEntryORM)).scalars().all()) == ledger_before
