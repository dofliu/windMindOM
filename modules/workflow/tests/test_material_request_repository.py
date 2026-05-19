"""MaterialRequestRepository tests — CRUD + state transitions + return + business_key。

對應 [WMOM-20260509-02](../../../ISSUES.md)。
Atomic dispatch test 在 ``test_dispatch_atomic_transaction.py`` 獨立測。
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.workflow.domain import InvalidTransition
from modules.workflow.domain.inventory import (
    MaterialRequestStatus,
    ReturnReason,
    StockKind,
)
from modules.workflow.repository import (
    InventoryRepository,
    MaterialRequestRepository,
    MaterialRequestRuleViolation,
    get_inventory_repository,
    get_material_request_repository,
)
from modules.workflow.repository.work_order_repository import (
    clear_engine_cache_for_test,
)


# ─────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "wind_farm.db")


@pytest.fixture
def inv_repo(db_path) -> InventoryRepository:
    clear_engine_cache_for_test()
    yield get_inventory_repository(db_path)
    clear_engine_cache_for_test()


@pytest.fixture
def mr_repo(db_path, inv_repo) -> MaterialRequestRepository:
    return get_material_request_repository(db_path)


@pytest.fixture
def warehouse(inv_repo):
    return inv_repo.create_warehouse(
        farm_id="changhua", name="Changhua base", is_default=True
    )


@pytest.fixture
def item(inv_repo, warehouse):
    return inv_repo.create_item(
        sku="GBR-001",
        name="Gearbox bearing",
        description="Z72 bearing",
        unit="piece",
        farm_id="changhua",
        warehouse_id=warehouse.id,
        unit_cost=Decimal("450.00"),
        stock_new=10,
    )


# ─────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────


def test_create_basic(mr_repo, item):
    requester = uuid4()
    mr = mr_repo.create(
        farm_id="changhua",
        requester_id=requester,
        items=[(item.id, 2, StockKind.NEW)],
    )
    assert mr.farm_id == "changhua"
    assert mr.requester_id == requester
    assert mr.status is MaterialRequestStatus.DRAFT
    assert len(mr.items) == 1
    assert mr.items[0].estimated_qty == 2
    assert mr.items[0].stock_kind is StockKind.NEW
    assert mr.business_key.startswith("MR-CHANG-")


def test_create_with_work_order_link(mr_repo, item):
    wo_id = uuid4()
    mr = mr_repo.create(
        farm_id="changhua",
        requester_id=uuid4(),
        items=[(item.id, 1, StockKind.NEW)],
        work_order_id=wo_id,
    )
    assert mr.work_order_id == wo_id


def test_create_business_key_increments(mr_repo, item):
    """同月建多張，NN 自動 +1。"""
    mr1 = mr_repo.create(
        farm_id="changhua", requester_id=uuid4(),
        items=[(item.id, 1, StockKind.NEW)],
    )
    mr2 = mr_repo.create(
        farm_id="changhua", requester_id=uuid4(),
        items=[(item.id, 1, StockKind.NEW)],
    )
    n1 = int(mr1.business_key.split("-")[-1])
    n2 = int(mr2.business_key.split("-")[-1])
    assert n2 == n1 + 1


def test_create_no_items_rejected(mr_repo):
    with pytest.raises(MaterialRequestRuleViolation, match="at least one item"):
        mr_repo.create(
            farm_id="changhua", requester_id=uuid4(), items=[]
        )


def test_create_zero_qty_rejected(mr_repo, item):
    with pytest.raises(MaterialRequestRuleViolation, match="must be > 0"):
        mr_repo.create(
            farm_id="changhua", requester_id=uuid4(),
            items=[(item.id, 0, StockKind.NEW)],
        )


def test_get_by_business_key(mr_repo, item):
    mr = mr_repo.create(
        farm_id="changhua", requester_id=uuid4(),
        items=[(item.id, 1, StockKind.NEW)],
    )
    fetched = mr_repo.get_by_business_key(mr.business_key)
    assert fetched is not None
    assert fetched.id == mr.id


def test_list_filter_by_status(mr_repo, item):
    mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 1, StockKind.NEW)])
    mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 1, StockKind.NEW)])
    items, total = mr_repo.list(farm_id="f", status=MaterialRequestStatus.DRAFT)
    assert total == 2


def test_list_filter_by_work_order(mr_repo, item):
    wo_a = uuid4()
    wo_b = uuid4()
    mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 1, StockKind.NEW)], work_order_id=wo_a)
    mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 1, StockKind.NEW)], work_order_id=wo_b)
    mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 1, StockKind.NEW)], work_order_id=wo_a)
    items, total = mr_repo.list(farm_id="f", work_order_id=wo_a)
    assert total == 2


def test_list_for_work_order_reverse_lookup(mr_repo, item):
    wo = uuid4()
    mr1 = mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 1, StockKind.NEW)], work_order_id=wo)
    mr2 = mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 1, StockKind.NEW)], work_order_id=wo)
    found = mr_repo.list_for_work_order(wo)
    assert {m.id for m in found} == {mr1.id, mr2.id}


# ─────────────────────────────────────────────────────────────────────────
# State transition (non-dispatch)
# ─────────────────────────────────────────────────────────────────────────


def test_transition_submit_for_approval(mr_repo, item):
    mr = mr_repo.create(
        farm_id="changhua", requester_id=uuid4(),
        items=[(item.id, 1, StockKind.NEW)],
    )
    updated = mr_repo.transition(mr.id, "submit_for_approval")
    assert updated.status is MaterialRequestStatus.AWAITING_APPROVAL
    assert updated.submitted_at is not None


def test_transition_approve_all(mr_repo, item):
    mr = mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 1, StockKind.NEW)])
    mr_repo.transition(mr.id, "submit_for_approval")
    updated = mr_repo.transition(mr.id, "approve_all")
    assert updated.status is MaterialRequestStatus.APPROVED


def test_transition_reject_records_reason(mr_repo, item):
    mr = mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 1, StockKind.NEW)])
    mr_repo.transition(mr.id, "submit_for_approval")
    updated = mr_repo.transition(
        mr.id, "reject", reject_reason="Not on approved supplier list"
    )
    assert updated.status is MaterialRequestStatus.REJECTED
    assert updated.reject_reason == "Not on approved supplier list"


def test_transition_cancel_with_reason(mr_repo, item):
    mr = mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 1, StockKind.NEW)])
    updated = mr_repo.transition(mr.id, "cancel", cancel_reason="Operator changed mind")
    assert updated.status is MaterialRequestStatus.CANCELLED
    assert updated.cancel_reason == "Operator changed mind"


def test_transition_dispatch_via_repo_transition_rejected(mr_repo, item):
    """``transition('dispatch')`` 應提示 caller 改用 dispatch_request()。"""
    mr = mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 1, StockKind.NEW)])
    mr_repo.transition(mr.id, "submit_for_approval")
    mr_repo.transition(mr.id, "approve_all")
    with pytest.raises(MaterialRequestRuleViolation, match="dispatch_request"):
        mr_repo.transition(mr.id, "dispatch")


def test_transition_unknown_id(mr_repo):
    with pytest.raises(LookupError):
        mr_repo.transition(uuid4(), "submit_for_approval")


def test_transition_invalid_state_raises(mr_repo, item):
    mr = mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 1, StockKind.NEW)])
    # DRAFT → approve_all 不合法
    with pytest.raises(InvalidTransition):
        mr_repo.transition(mr.id, "approve_all")


# ─────────────────────────────────────────────────────────────────────────
# signoff_chain_id wiring
# ─────────────────────────────────────────────────────────────────────────


def test_set_signoff_chain_id(mr_repo, item):
    mr = mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 1, StockKind.NEW)])
    chain_id = uuid4()
    mr_repo.set_signoff_chain_id(mr.id, chain_id)
    fetched = mr_repo.get(mr.id)
    assert fetched.signoff_chain_id == chain_id


# ─────────────────────────────────────────────────────────────────────────
# Returns（atomic 加回 stock）
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_increments_stock(mr_repo, inv_repo, item):
    # WMOM-20260519-01：return qty 必須 ≤ dispatched_total − consumed_total；
    # estimated_qty=2 + actual_qty=None（未 receive）→ upper_bound=2，剛好可退 2
    mr = mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 2, StockKind.NEW)])
    initial_stock = inv_repo.get_item(item.id).stock_used
    ret = mr_repo.add_return(
        request_id=mr.id,
        item_id=item.id,
        qty=2,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.USED,  # 用剩退回 used
        returned_by=uuid4(),
        note="Field operator returned 2 surplus bearings",
    )
    assert ret.qty == 2
    assert ret.reason is ReturnReason.SURPLUS
    fresh = inv_repo.get_item(item.id)
    assert fresh.stock_used == initial_stock + 2


def test_add_return_zero_qty_rejected(mr_repo, item):
    mr = mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 1, StockKind.NEW)])
    with pytest.raises(MaterialRequestRuleViolation, match="qty must be > 0"):
        mr_repo.add_return(
            request_id=mr.id,
            item_id=item.id,
            qty=0,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW,
            returned_by=uuid4(),
        )


def test_add_return_unknown_request(mr_repo, item):
    with pytest.raises(LookupError):
        mr_repo.add_return(
            request_id=uuid4(),
            item_id=item.id,
            qty=1,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW,
            returned_by=uuid4(),
        )
