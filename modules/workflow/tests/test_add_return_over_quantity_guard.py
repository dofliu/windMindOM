"""WMOM-20260519-01：`add_return` 超量退料 domain guard。

驗證：
- Domain layer `MaterialRequest.compute_returnable_upper_bound` 純函式正確
- Repository `add_return` 在 qty + already_returned > upper_bound 時 raise
  `MaterialRequestRuleViolation`；stock + ledger + MaterialReturn 都不寫
- Boundary：剛好等於 upper bound 仍允許
- 多次退料累計檢查（cumulative）
- Multi-line MR 同 item_id 跨 stock_kind aggregate
- Cross-kind return（dispatch NEW、退 USED）共用同一 upper bound
- F1 邊界場景（dispatched=2 / actual_qty=1 / return 2）被擋下 → 月報 confirmed 視角不可
  能變負值
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
    MaterialRequest,
    MaterialRequestItem,
    ReturnReason,
    StockKind,
)
from modules.workflow.repository import (  # noqa: E402
    InventoryRepository,
    MaterialRequestRepository,
    get_inventory_repository,
    get_material_request_repository,
)
from modules.workflow.repository.material_request_repository import (  # noqa: E402
    MaterialRequestRuleViolation,
)
from modules.workflow.repository.work_order_repository import (  # noqa: E402
    clear_engine_cache_for_test,
)


# ─────────────────────────────────────────────────────────────────────────
# Domain layer — pure-function tests（不碰 DB）
# ─────────────────────────────────────────────────────────────────────────


def _build_mr(items: list[MaterialRequestItem]) -> MaterialRequest:
    return MaterialRequest(
        farm_id="f", requester_id=uuid4(), business_key="MR-TEST", items=items
    )


def test_upper_bound_dispatched_only_no_actual_qty():
    """actual_qty 全 None（未 receive）→ upper bound = dispatched_total。"""
    item_id = uuid4()
    mr = _build_mr([
        MaterialRequestItem(
            request_id=uuid4(), item_id=item_id, estimated_qty=3,
            stock_kind=StockKind.NEW,
        )
    ])
    assert mr.compute_returnable_upper_bound(item_id) == 3


def test_upper_bound_after_receive_subtracts_consumed():
    """actual_qty=1 / estimated=2 → upper bound = 2 − 1 = 1（F1 邊界場景）。"""
    item_id = uuid4()
    mr = _build_mr([
        MaterialRequestItem(
            request_id=uuid4(), item_id=item_id, estimated_qty=2,
            actual_qty=1, stock_kind=StockKind.NEW,
        )
    ])
    assert mr.compute_returnable_upper_bound(item_id) == 1


def test_upper_bound_multi_line_same_item_aggregates_across_stock_kinds():
    """同一 item_id 多 line（不同 stock_kind）→ upper bound aggregate 全部。"""
    item_id = uuid4()
    mr = _build_mr([
        MaterialRequestItem(
            request_id=uuid4(), item_id=item_id, estimated_qty=2,
            actual_qty=1, stock_kind=StockKind.NEW,
        ),
        MaterialRequestItem(
            request_id=uuid4(), item_id=item_id, estimated_qty=3,
            actual_qty=2, stock_kind=StockKind.USED,
        ),
    ])
    # dispatched=5, consumed=3 → upper bound = 2
    assert mr.compute_returnable_upper_bound(item_id) == 2


def test_upper_bound_unknown_item_id_is_zero():
    """item_id 不在 MR.items → upper bound = 0（無法退）。"""
    mr = _build_mr([
        MaterialRequestItem(
            request_id=uuid4(), item_id=uuid4(), estimated_qty=2,
            stock_kind=StockKind.NEW,
        )
    ])
    assert mr.compute_returnable_upper_bound(uuid4()) == 0


def test_upper_bound_consumed_exceeds_dispatched_floors_at_zero():
    """defensive：actual_qty > estimated_qty（不應發生但容忍）→ upper bound = 0。"""
    item_id = uuid4()
    mr = _build_mr([
        MaterialRequestItem(
            request_id=uuid4(), item_id=item_id, estimated_qty=2,
            actual_qty=5, stock_kind=StockKind.NEW,
        )
    ])
    assert mr.compute_returnable_upper_bound(item_id) == 0


# ─────────────────────────────────────────────────────────────────────────
# Repository layer — fixtures
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
    estimated_qty: int = 2,
    unit_cost: Decimal = Decimal("300.00"),
    farm_id: str = "f",
) -> tuple[UUID, UUID]:
    wh = inv_repo.create_warehouse(farm_id=farm_id, name="W", is_default=True)
    item = inv_repo.create_item(
        sku="X-1", name="x", description="x", unit="piece",
        farm_id=farm_id, warehouse_id=wh.id, unit_cost=unit_cost,
        stock_new=initial_stock,
    )
    mr = mr_repo.create(
        farm_id=farm_id, requester_id=uuid4(),
        items=[(item.id, estimated_qty, StockKind.NEW)],
    )
    mr_repo.transition(mr.id, "submit_for_approval")
    mr_repo.transition(mr.id, "approve_all")
    mr_repo.dispatch_request(mr.id)
    return mr.id, item.id


def _ledger_count(mr_repo: MaterialRequestRepository) -> int:
    with mr_repo._sessionmaker() as sess:
        return len(sess.execute(select(CostLedgerEntryORM)).scalars().all())


# ─────────────────────────────────────────────────────────────────────────
# Repository layer — guard tests
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_qty_exceeds_dispatched_raises(repos):
    """dispatched 2 → return 3 → raise MaterialRequestRuleViolation。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=2,
    )
    stock_before = inv_repo.get_item(item_id).stock_new  # 8
    ledger_before = _ledger_count(mr_repo)  # 1 dispatch entry

    with pytest.raises(
        MaterialRequestRuleViolation,
        match="exceeds remaining returnable",
    ):
        mr_repo.add_return(
            request_id=mr_id, item_id=item_id, qty=3,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW, returned_by=uuid4(),
        )

    # Stock / ledger / MR.status 全沒動
    assert inv_repo.get_item(item_id).stock_new == stock_before
    assert _ledger_count(mr_repo) == ledger_before


def test_add_return_qty_equals_upper_bound_allowed(repos):
    """boundary：qty 剛好等於 upper bound（全退）→ 允許，寫一筆 -600 entry。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=5, estimated_qty=2,
        unit_cost=Decimal("300.00"),
    )
    ret = mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=2,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW, returned_by=uuid4(),
    )
    assert ret.qty == 2
    # stock 加回完整 2 件
    assert inv_repo.get_item(item_id).stock_new == 5  # 5 - 2 + 2
    # ledger 多一筆 -600 confirmed entry
    assert _ledger_count(mr_repo) == 2


def test_add_return_after_receive_actual_qty_lowers_upper_bound(repos):
    """F1 邊界場景：dispatched 2 / receive actual_qty=1 → max returnable=1，
    再退 2 必須被擋。
    """
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=2,
        unit_cost=Decimal("300.00"),
    )
    # receive actual_qty=1（worker 說只用 1）
    mr = mr_repo.get(mr_id)
    mr_repo.transition(
        mr_id, "receive", actual_quantities={mr.items[0].id: 1},
    )

    with pytest.raises(
        MaterialRequestRuleViolation,
        match="exceeds remaining returnable",
    ):
        mr_repo.add_return(
            request_id=mr_id, item_id=item_id, qty=2,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW, returned_by=uuid4(),
        )

    # 退 1 件還是允許（剩餘 1）
    ret = mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=1,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW, returned_by=uuid4(),
    )
    assert ret.qty == 1


def test_add_return_cumulative_already_returned_blocks_second_call(repos):
    """連退 2 次 → 第 2 次 cumulative 累加超過 upper bound 被擋。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=3,
        unit_cost=Decimal("200.00"),
    )
    # 1st return：2 件（剩餘 1）
    mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=2,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW, returned_by=uuid4(),
    )
    # 2nd return：再退 2 件 → cumulative 2+2=4 > upper bound 3，被擋
    with pytest.raises(
        MaterialRequestRuleViolation,
        match="exceeds remaining returnable",
    ):
        mr_repo.add_return(
            request_id=mr_id, item_id=item_id, qty=2,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW, returned_by=uuid4(),
        )
    # 但退 1 件還允許
    mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=1,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW, returned_by=uuid4(),
    )


def test_add_return_cross_stock_kind_shares_same_upper_bound(repos):
    """dispatch NEW → 退 USED（cross-kind）仍受同一 upper bound 拘束。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=2,
        unit_cost=Decimal("300.00"),
    )
    # 退 1 USED（cross-kind）
    mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=1,
        reason=ReturnReason.FAILED_INSTALL,
        return_to_kind=StockKind.USED, returned_by=uuid4(),
    )
    # 再退 2 NEW → cumulative 1+2=3 > 2，被擋（跨 kind aggregate）
    with pytest.raises(
        MaterialRequestRuleViolation,
        match="exceeds remaining returnable",
    ):
        mr_repo.add_return(
            request_id=mr_id, item_id=item_id, qty=2,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW, returned_by=uuid4(),
        )
    # 退 1 NEW 還允許
    mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=1,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW, returned_by=uuid4(),
    )


def test_add_return_no_matching_item_raises(repos):
    """item_id 不在 MR.items → upper bound=0 → 任何 qty 都 raise。"""
    inv_repo, mr_repo = repos
    mr_id, _ = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=2,
    )
    # 用 default warehouse 建另一個 item（不在 MR.items 內）
    default_wh = inv_repo.get_default_warehouse("f")
    assert default_wh is not None
    other_item = inv_repo.create_item(
        sku="OTHER", name="other", description="o", unit="piece",
        farm_id="f", warehouse_id=default_wh.id,
        unit_cost=Decimal("100.00"), stock_new=5,
    )
    with pytest.raises(
        MaterialRequestRuleViolation,
        match="exceeds remaining returnable",
    ):
        mr_repo.add_return(
            request_id=mr_id, item_id=other_item.id, qty=1,
            reason=ReturnReason.WRONG_PART,
            return_to_kind=StockKind.NEW, returned_by=uuid4(),
        )


def test_add_return_guard_does_not_affect_confirmed_negative_after_fix(
    db_path, repos
):
    """F1 邊界場景：dispatched 2 / actual=1 / 試圖 return 2 被 guard 擋下 →
    月報 confirmed 視角不會變 −300。

    沒 guard 前：dispatched confirmed=300 + return -600 = -300 ❌
    有 guard 後：return 2 raise → 月報只看到 dispatched confirmed=300（正確）
    """
    from modules.cost.repository import get_cost_ledger_repository
    from modules.cost.repository.cost_ledger import (
        CostLedgerCategory, CostLedgerStatus,
    )
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=2,
        unit_cost=Decimal("300.00"), farm_id="changhua",
    )
    mr = mr_repo.get(mr_id)
    mr_repo.transition(
        mr_id, "receive", actual_quantities={mr.items[0].id: 1},
    )

    # 模擬 wo finish hook：confirm dispatch entry 為 actual_qty × locked_cost = 1 × 300
    ledger_repo = get_cost_ledger_repository(db_path)
    dispatch_entry = next(
        e for e in ledger_repo.list(farm_id="changhua")[0]
    )
    ledger_repo.confirm_entry(
        dispatch_entry.id, new_amount=Decimal("300.00")
    )

    # 嘗試 over-return → 被擋
    with pytest.raises(MaterialRequestRuleViolation):
        mr_repo.add_return(
            request_id=mr_id, item_id=item_id, qty=2,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW, returned_by=uuid4(),
        )

    # 月報 confirmed 視角 = dispatched confirmed 300（不含 -600 offset）
    confirmed_map = ledger_repo.summary_by_category(
        farm_id="changhua", status=CostLedgerStatus.CONFIRMED,
    )
    assert confirmed_map.get(CostLedgerCategory.MATERIAL, Decimal("0")) == \
        Decimal("300.00")


def test_add_return_unknown_mr_raises_lookup_not_guard(repos):
    """MR 不存在 → LookupError（早於 guard）。"""
    _, mr_repo = repos
    with pytest.raises(LookupError):
        mr_repo.add_return(
            request_id=uuid4(), item_id=uuid4(), qty=1,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW, returned_by=uuid4(),
        )


def test_add_return_zero_qty_raises_before_guard(repos):
    """qty <= 0 由 caller-side check 早擋；不會碰到 upper bound 邏輯。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=2,
    )
    with pytest.raises(MaterialRequestRuleViolation, match="qty must be > 0"):
        mr_repo.add_return(
            request_id=mr_id, item_id=item_id, qty=0,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW, returned_by=uuid4(),
        )


def test_add_return_returns_router_422_on_over_quantity(repos, monkeypatch):
    """整合：API layer 收 422（router 已 catch MaterialRequestRuleViolation → 422）。

    Note：``modules.workflow.routers/__init__.py`` 把 submodule 同名 rebind 為 APIRouter
    物件，所以這裡直接從 ``sys.modules`` 拿真正的 submodule 來 monkeypatch
    ``_resolve_farm_db_path``（先 trigger import 確保它在 ``sys.modules``）。
    """
    import sys
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    # 觸發 submodule import → 進 sys.modules（即便 __init__.py rebind 同名 attr）
    from modules.workflow.routers.material_request_router import router  # noqa: F401

    sub_mod = sys.modules["modules.workflow.routers.material_request_router"]

    farm_id = "f"
    inv_repo, mr_repo = repos
    db_path = mr_repo._engine.url.database

    monkeypatch.setattr(sub_mod, "_resolve_farm_db_path", lambda fid: db_path)

    app = FastAPI()
    app.include_router(sub_mod.router)
    client = TestClient(app)

    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=2,
    )
    resp = client.post(
        f"/api/workflow/material-requests/{mr_id}/returns",
        params={"farm_id": farm_id},
        json={
            "item_id": str(item_id), "qty": 3,
            "reason": "surplus", "return_to_kind": "new",
            "returned_by": str(uuid4()),
        },
    )
    assert resp.status_code == 422
    assert "exceeds remaining returnable" in resp.text
