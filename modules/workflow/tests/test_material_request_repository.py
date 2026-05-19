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
    mr = mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 1, StockKind.NEW)])
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


# ─────────────────────────────────────────────────────────────────────────
# Returns ledger offset（WMOM-20260509-F1，2026-05-19）
# ─────────────────────────────────────────────────────────────────────────


def _dispatch_mr(mr_repo, item_id, qty: int = 3):
    """Helper：建 MR → submit → approve → dispatch，回傳 (mr_id, line_item_id)。

    locked_unit_cost 由 inventory item 建立時的 unit_cost 決定，**不是**本 helper
    的責任 — caller 若要控制 locked_unit_cost，請在呼叫前透過
    `inv_repo.create_item(..., unit_cost=...)` 或 `inv_repo.update_metadata(...)` 設定。
    """
    mr = mr_repo.create(
        farm_id="changhua", requester_id=uuid4(),
        items=[(item_id, qty, StockKind.NEW)],
    )
    mr_repo.transition(mr.id, "submit_for_approval")
    mr_repo.transition(mr.id, "approve_all")
    mr_repo.dispatch_request(mr.id)
    refreshed = mr_repo.get(mr.id)
    return mr.id, refreshed.items[0].id


def _query_ledger(mr_repo, mr_id: UUID):
    """直接從 mr_repo session query CostLedgerEntryORM by source_event_id。"""
    from sqlalchemy import select

    from modules.cost.repository.cost_ledger import (
        CostLedgerEntryORM,
        CostLedgerSourceType,
    )

    with mr_repo._sessionmaker() as sess:
        return list(
            sess.execute(
                select(CostLedgerEntryORM).where(
                    CostLedgerEntryORM.source_event_id == str(mr_id),
                    CostLedgerEntryORM.source_type
                    == CostLedgerSourceType.MATERIAL_REQUEST.value,
                )
            ).scalars().all()
        )


def test_add_return_writes_negative_ledger_entry(mr_repo, inv_repo, item):
    """退料後 ledger 多一筆 negative entry（amount = -qty × locked_unit_cost）。

    item fixture: unit_cost=450, stock_new=10 → dispatch qty=3 寫 +1350 ESTIMATED。
    """
    mr_id, line_id = _dispatch_mr(mr_repo, item.id, qty=3)
    before = _query_ledger(mr_repo, mr_id)
    assert len(before) == 1  # dispatch 寫的 estimated entry
    dispatch_entry = before[0]
    assert Decimal(str(dispatch_entry.amount)) == Decimal("1350.00")  # 3 × 450

    mr_repo.add_return(
        request_id=mr_id,
        item_id=item.id,
        qty=2,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
        note="退 2 顆",
    )

    after = _query_ledger(mr_repo, mr_id)
    assert len(after) == 2
    offset = next(e for e in after if Decimal(str(e.amount)) < 0)
    assert Decimal(str(offset.amount)) == Decimal("-900.00")  # -(2 × 450)
    # status 鏡像 dispatch entry — dispatch 尚未 confirm，所以 offset 也 ESTIMATED
    assert offset.status == "estimated"
    assert offset.confirmed_at is None
    assert offset.source_item_id == str(line_id)
    assert offset.category == "material"
    assert offset.locked_unit_cost == Decimal("450.0000")
    assert "退料沖銷" in (offset.note or "")
    assert "reason=surplus" in (offset.note or "")


def test_add_return_offset_mirrors_estimated_when_dispatch_not_finished(
    mr_repo, inv_repo, item, db_path
):
    """**會計正確性 regression（must-fix #2）**：dispatch 仍 ESTIMATED 時退料 →
    offset 也 ESTIMATED，`summary_by_category(CONFIRMED)` 不會出現 negative-only entry。
    """
    from modules.cost.repository import get_cost_ledger_repository
    from modules.cost.repository.cost_ledger import (
        CostLedgerCategory,
        CostLedgerStatus,
    )

    mr_id, _ = _dispatch_mr(mr_repo, item.id, qty=3)  # dispatch entry ESTIMATED +1350
    # **不**呼叫 confirm_entry — 工單尚未 finish
    mr_repo.add_return(
        request_id=mr_id, item_id=item.id, qty=2,
        reason=ReturnReason.SURPLUS, return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )

    ledger_repo = get_cost_ledger_repository(db_path)
    confirmed = ledger_repo.summary_by_category(
        farm_id="changhua", status=CostLedgerStatus.CONFIRMED
    )
    estimated = ledger_repo.summary_by_category(
        farm_id="changhua", status=CostLedgerStatus.ESTIMATED
    )
    # CONFIRMED 桶完全空 — 不可出現 -900 negative-only
    assert confirmed.get(CostLedgerCategory.MATERIAL, Decimal("0")) == Decimal("0")
    # ESTIMATED 桶 net out：+1350 + (-900) = 450
    assert estimated.get(CostLedgerCategory.MATERIAL) == Decimal("450.00")


def test_add_return_uses_dispatch_locked_unit_cost_even_if_inventory_changed(
    mr_repo, inv_repo, item
):
    """退料金額用 dispatch 當下的 locked_unit_cost — inventory.unit_cost 改動不影響。

    item fixture unit_cost=450 → dispatch locked=450；之後改 inventory=999.99，
    退料應仍用 450。
    """
    mr_id, _ = _dispatch_mr(mr_repo, item.id, qty=2)
    # dispatch 後改 inventory unit_cost（模擬料件再進貨改價）
    inv_repo.update_metadata(item.id, unit_cost=Decimal("999.99"))

    mr_repo.add_return(
        request_id=mr_id,
        item_id=item.id,
        qty=1,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )

    entries = _query_ledger(mr_repo, mr_id)
    offset = next(e for e in entries if Decimal(str(e.amount)) < 0)
    # -1 × 450（dispatch locked），不是 -1 × 999.99（current inventory）
    assert Decimal(str(offset.amount)) == Decimal("-450.00")
    assert offset.locked_unit_cost == Decimal("450.0000")


def test_add_return_summary_by_category_nets_correctly(mr_repo, inv_repo, item, db_path):
    """退料後 summary_by_category(CONFIRMED) 正確 net out。"""
    from modules.cost.repository import get_cost_ledger_repository
    from modules.cost.repository.cost_ledger import (
        CostLedgerCategory,
        CostLedgerStatus,
    )

    mr_id, _ = _dispatch_mr(mr_repo, item.id, qty=3)
    # 退料前先把 estimated 翻 confirmed（模擬 wo finish hook）
    ledger_repo = get_cost_ledger_repository(db_path)
    entries = _query_ledger(mr_repo, mr_id)
    dispatch_entry_id = UUID(entries[0].id)
    ledger_repo.confirm_entry(dispatch_entry_id, new_amount=Decimal("1350.00"))

    # 退 2
    mr_repo.add_return(
        request_id=mr_id, item_id=item.id, qty=2,
        reason=ReturnReason.SURPLUS, return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )

    summary = ledger_repo.summary_by_category(
        farm_id="changhua", status=CostLedgerStatus.CONFIRMED
    )
    material_total = summary.get(CostLedgerCategory.MATERIAL, Decimal("0"))
    # 1350 (confirmed) + (-900) (offset) = 450（實際消耗 1 顆 × 450）
    assert material_total == Decimal("450.00")


def test_add_return_no_matching_line_item_still_returns_stock(
    mr_repo, inv_repo, warehouse
):
    """退料對應不到 MR line item 時，stock 仍加回但 ledger 不寫（防禦）。"""
    # 建 item A（mr 內），item B（mr 沒收）
    item_a = inv_repo.create_item(
        sku="A-1", name="a", description="a", unit="piece",
        farm_id="changhua", warehouse_id=warehouse.id,
        unit_cost=Decimal("100"), stock_new=10,
    )
    item_b = inv_repo.create_item(
        sku="B-1", name="b", description="b", unit="piece",
        farm_id="changhua", warehouse_id=warehouse.id,
        unit_cost=Decimal("200"), stock_new=10,
    )
    mr_id, _ = _dispatch_mr(mr_repo, item_a.id, qty=1)

    initial_b = inv_repo.get_item(item_b.id).stock_new
    # 退 item B（mr 沒這個 line item）— 應該 stock 加回 + skip ledger
    mr_repo.add_return(
        request_id=mr_id, item_id=item_b.id, qty=1,
        reason=ReturnReason.SURPLUS, return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )

    assert inv_repo.get_item(item_b.id).stock_new == initial_b + 1
    # ledger 只有 item A 的 dispatch entry，沒有 item B 的 offset
    entries = _query_ledger(mr_repo, mr_id)
    assert len(entries) == 1
    assert Decimal(str(entries[0].amount)) > 0  # 只有原 dispatch 正 entry


def test_add_return_atomic_rollback_on_failure(mr_repo, inv_repo, item):
    """退料 atomic：raise 後 stock / ledger / return record 全部不變。"""
    from unittest.mock import patch

    mr_id, _ = _dispatch_mr(mr_repo, item.id, qty=2)
    stock_before = inv_repo.get_item(item.id).stock_new
    assert stock_before == 8  # 10 (fixture) - 2 (dispatch 扣的)
    ledger_before = _query_ledger(mr_repo, mr_id)

    # patch insert_in_session raise → 整個 transaction rollback
    with patch(
        "modules.cost.repository.cost_ledger.insert_in_session",
        side_effect=RuntimeError("injected failure"),
    ):
        with pytest.raises(RuntimeError, match="injected failure"):
            mr_repo.add_return(
                request_id=mr_id, item_id=item.id, qty=1,
                reason=ReturnReason.SURPLUS, return_to_kind=StockKind.NEW,
                returned_by=uuid4(),
            )

    # stock 沒變、ledger 沒新 entry
    assert inv_repo.get_item(item.id).stock_new == stock_before
    assert len(_query_ledger(mr_repo, mr_id)) == len(ledger_before)
