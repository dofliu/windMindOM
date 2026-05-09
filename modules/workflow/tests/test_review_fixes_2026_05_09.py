"""Tests for the 3 Must-fix items from 2026-05-09 code review on M4 backend (A1-A5)。

Review fixes:
1. **locked_unit_cost snapshot** — confirm 用 dispatch 當下的快照，不重新查 inventory
   （會計正確性：dispatch 後 unit_cost 改動不影響 confirmed amount）
2. **multi-farm db_path override** — _finish_hook_db_path_overrides 改成 dict，
   不同 farm 不會踩到彼此
3. **InvalidTransition.reason attribute** — _map_state_error 用 exc.reason 精確
   判斷，不依賴 fragile 字串匹配

外加 Should-fix 3: approval_router 加 bare except 兜底（chain approve 後 dispatch
拋未預期 error 時回 200 + transition_error，不 raise 500）。
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.cost.repository import (
    CostLedgerCategory,
    CostLedgerEntry,
    CostLedgerSourceType,
    CostLedgerStatus,
    get_cost_ledger_repository,
    insert_in_session,
)
from modules.workflow.domain import (
    FollowupKind,
    InvalidTransition,
    Priority,
    WorkOrderStatus,
    WorkOrderType,
)
from modules.workflow.domain.inventory import StockKind
from modules.workflow.repository import (
    InventoryRepository,
    MaterialRequestRepository,
    SignoffRepository,
    WorkOrderRepository,
    get_inventory_repository,
    get_material_request_repository,
    get_repository,
    get_signoff_repository,
)
from modules.workflow.repository.work_order_repository import (
    clear_engine_cache_for_test,
)
from modules.workflow.routers import (
    approval_router,
    inventory_router,
    material_request_router,
    router as workflow_router,
)
from modules.workflow.routers.approval_router import set_signoff_factories
from modules.workflow.routers.inventory_router import set_inventory_factory
from modules.workflow.routers.material_request_router import (
    set_material_request_factories,
)
from modules.workflow.routers.work_order_router import (
    clear_finish_hook_db_paths,
    set_finish_hook_db_path,
    set_repository_factory,
)


# ─────────────────────────────────────────────────────────────────────────
# Review fix #1：locked_unit_cost snapshot — 會計正確性
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def lifecycle_setup(tmp_path):
    """共用 fixture（同 test_lifecycle_ledger_confirmation）+ 開放修改 unit_cost。"""
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")

    set_repository_factory(lambda _: get_repository(db_path))
    set_signoff_factories(
        lambda _: get_signoff_repository(db_path),
        lambda _: get_repository(db_path),
        lambda _: get_material_request_repository(db_path),
    )
    set_material_request_factories(
        lambda _: get_material_request_repository(db_path),
        lambda _: get_signoff_repository(db_path),
    )
    set_inventory_factory(lambda _: get_inventory_repository(db_path))
    set_finish_hook_db_path(db_path)

    app = FastAPI(title="review-fixes-test")
    app.include_router(workflow_router)
    app.include_router(approval_router)
    app.include_router(material_request_router)
    app.include_router(inventory_router)
    client = TestClient(app)

    inv_repo = get_inventory_repository(db_path)
    wh = inv_repo.create_warehouse(farm_id="changhua", name="W", is_default=True)
    item = inv_repo.create_item(
        sku="GBR-001", name="Gearbox bearing", description="Z72",
        unit="piece", farm_id="changhua", warehouse_id=wh.id,
        unit_cost=Decimal("450.00"),
        stock_new=10,
    )

    yield {
        "client": client,
        "db_path": db_path,
        "item_id": item.id,
        "inv_repo": inv_repo,
        "ledger_repo": get_cost_ledger_repository(db_path),
        "wo_repo": get_repository(db_path),
        "mr_repo": get_material_request_repository(db_path),
    }

    set_repository_factory(None)
    set_signoff_factories(None, None)
    set_material_request_factories(None, None)
    set_inventory_factory(None)
    clear_finish_hook_db_paths()
    clear_engine_cache_for_test()


def _approve_chain(client, chain_id: str, levels=("employee", "leader", "treasury")):
    actor = str(uuid4())
    for level in levels:
        pending = client.get(
            "/api/workflow/approvals/pending",
            params={"farm_id": "changhua", "level": level},
        ).json()
        step = next(
            (it for it in pending["items"] if it["chain"]["id"] == chain_id), None
        )
        if step is None:
            continue
        client.post(
            f"/api/workflow/approvals/{step['step']['id']}/approve",
            params={"farm_id": "changhua"},
            json={"actor_id": actor, "comment": f"approve {level}"},
        )


def test_locked_unit_cost_snapshot_at_dispatch(lifecycle_setup):
    """**Must-fix #1 acceptance**：dispatch 後改 unit_cost，confirmed amount 仍用
    dispatch 當下的價，不用 confirm 時的當前價。會計做帳要求 estimated/confirmed
    用同基礎。"""
    s = lifecycle_setup
    client = s["client"]
    item_id = s["item_id"]
    inv_repo = s["inv_repo"]
    ledger_repo = s["ledger_repo"]
    wo_repo = s["wo_repo"]

    actor = uuid4()
    wo = wo_repo.create(
        farm_id="changhua", turbine_id="WT001",
        type=WorkOrderType.CORRECTIVE, title="x", description="x",
        priority=Priority.NORMAL, assignee_id=actor, created_by=actor,
    )
    wo_repo.transition(wo.id, "dispatch", actor_id=actor)
    wo_repo.transition(wo.id, "start_work")

    mr = client.post(
        "/api/workflow/material-requests",
        json={
            "farm_id": "changhua",
            "requester_id": str(actor),
            "items": [{"item_id": str(item_id), "estimated_qty": 2, "stock_kind": "new"}],
            "work_order_id": str(wo.id),
        },
    ).json()
    submit = client.post(
        f"/api/workflow/material-requests/{mr['id']}/submit-for-approval",
        params={"farm_id": "changhua"},
        json={"actor_id": str(actor)},
    ).json()
    _approve_chain(client, submit["signoff_chain_id"])

    # Dispatch 完成 — ledger entry estimated, amount=900=2×450
    entries, _ = ledger_repo.list(farm_id="changhua")
    assert len(entries) == 1
    entry = entries[0]
    assert entry.amount == Decimal("900.00")
    assert entry.locked_unit_cost == Decimal("450.0000")  # SQLAlchemy Numeric(12,4)

    # ⚠ Dispatch 後 unit_cost 漲到 600 (供應商漲價、手動更新)
    inv_repo.update_metadata(item_id, unit_cost=Decimal("600.00"))

    # Receive actual_qty = 2
    fresh_mr = client.get(
        f"/api/workflow/material-requests/{mr['id']}",
        params={"farm_id": "changhua"},
    ).json()
    client.post(
        f"/api/workflow/material-requests/{mr['id']}/receive",
        params={"farm_id": "changhua"},
        json={
            "actor_id": str(actor),
            "actual_quantities": {fresh_mr["items"][0]["id"]: 2},
        },
    )

    # Finish WO → trigger ledger confirm
    client.post(
        f"/api/workflow/work-orders/{wo.id}/finish",
        params={"farm_id": "changhua"},
        json={"actual_hours": 1.0, "followup_kind": "none"},
    )

    # ✅ Confirmed amount 仍是 900（用 locked_unit_cost=450），不是 1200（actual_qty × 600）
    confirmed = ledger_repo.get(entry.id)
    assert confirmed.status is CostLedgerStatus.CONFIRMED
    assert confirmed.amount == Decimal("900.00")  # locked_unit_cost × actual_qty


def test_locked_unit_cost_actual_differs_uses_locked_price(lifecycle_setup):
    """actual_qty=1 + dispatch 後漲價 → confirmed = 1 × 450 (locked), 不是 1 × 600."""
    s = lifecycle_setup
    client = s["client"]
    item_id = s["item_id"]
    inv_repo = s["inv_repo"]
    ledger_repo = s["ledger_repo"]
    wo_repo = s["wo_repo"]

    actor = uuid4()
    wo = wo_repo.create(
        farm_id="changhua", turbine_id="WT001",
        type=WorkOrderType.CORRECTIVE, title="x", description="x",
        priority=Priority.NORMAL, assignee_id=actor, created_by=actor,
    )
    wo_repo.transition(wo.id, "dispatch", actor_id=actor)
    wo_repo.transition(wo.id, "start_work")
    mr = client.post(
        "/api/workflow/material-requests",
        json={
            "farm_id": "changhua", "requester_id": str(actor),
            "items": [{"item_id": str(item_id), "estimated_qty": 2, "stock_kind": "new"}],
            "work_order_id": str(wo.id),
        },
    ).json()
    submit = client.post(
        f"/api/workflow/material-requests/{mr['id']}/submit-for-approval",
        params={"farm_id": "changhua"},
        json={"actor_id": str(actor)},
    ).json()
    _approve_chain(client, submit["signoff_chain_id"])

    inv_repo.update_metadata(item_id, unit_cost=Decimal("600.00"))  # 改價

    fresh_mr = client.get(
        f"/api/workflow/material-requests/{mr['id']}",
        params={"farm_id": "changhua"},
    ).json()
    client.post(
        f"/api/workflow/material-requests/{mr['id']}/receive",
        params={"farm_id": "changhua"},
        json={
            "actor_id": str(actor),
            "actual_quantities": {fresh_mr["items"][0]["id"]: 1},
        },
    )
    client.post(
        f"/api/workflow/work-orders/{wo.id}/finish",
        params={"farm_id": "changhua"},
        json={"actual_hours": 1.0, "followup_kind": "none"},
    )

    entries, _ = ledger_repo.list(farm_id="changhua")
    assert entries[0].status is CostLedgerStatus.CONFIRMED
    # 1 × 450 (locked) = 450，不是 1 × 600 = 600
    assert entries[0].amount == Decimal("450.00")


# ─────────────────────────────────────────────────────────────────────────
# Review fix #2：multi-farm db_path override (dict)
# ─────────────────────────────────────────────────────────────────────────


def test_set_finish_hook_db_path_per_farm(tmp_path):
    """不同 farm 各自 path，不互相覆蓋。"""
    path_a = str(tmp_path / "farm_a.db")
    path_b = str(tmp_path / "farm_b.db")
    set_finish_hook_db_path(path_a, farm_id="changhua")
    set_finish_hook_db_path(path_b, farm_id="formosa")

    from modules.workflow.routers.work_order_router import (
        _resolve_db_path_for_finish_hook,
    )
    assert _resolve_db_path_for_finish_hook("changhua") == path_a
    assert _resolve_db_path_for_finish_hook("formosa") == path_b
    clear_finish_hook_db_paths()


def test_set_finish_hook_db_path_wildcard_fallback(tmp_path):
    """fallback 用 farm_id='*' 給 single-farm test 偷懶用。"""
    path = str(tmp_path / "shared.db")
    set_finish_hook_db_path(path)  # default farm_id="*"

    from modules.workflow.routers.work_order_router import (
        _resolve_db_path_for_finish_hook,
    )
    assert _resolve_db_path_for_finish_hook("any_farm") == path
    assert _resolve_db_path_for_finish_hook("another_farm") == path
    clear_finish_hook_db_paths()


def test_set_finish_hook_db_path_specific_overrides_wildcard(tmp_path):
    """特定 farm_id 比 '*' fallback 優先。"""
    wildcard = str(tmp_path / "wildcard.db")
    specific = str(tmp_path / "specific.db")
    set_finish_hook_db_path(wildcard)
    set_finish_hook_db_path(specific, farm_id="changhua")

    from modules.workflow.routers.work_order_router import (
        _resolve_db_path_for_finish_hook,
    )
    assert _resolve_db_path_for_finish_hook("changhua") == specific
    assert _resolve_db_path_for_finish_hook("formosa") == wildcard
    clear_finish_hook_db_paths()


def test_clear_finish_hook_db_paths(tmp_path):
    set_finish_hook_db_path(str(tmp_path / "a"), farm_id="a")
    set_finish_hook_db_path(str(tmp_path / "b"), farm_id="b")
    clear_finish_hook_db_paths()

    from modules.workflow.routers.work_order_router import (
        _finish_hook_db_path_overrides,
    )
    assert _finish_hook_db_path_overrides == {}


# ─────────────────────────────────────────────────────────────────────────
# Review fix #3：InvalidTransition.reason attribute
# ─────────────────────────────────────────────────────────────────────────


def test_invalid_transition_reason_state_mismatch():
    """state machine 拒絕（source state 不對）→ reason='state_mismatch'。"""
    from modules.workflow.domain import (
        WorkOrderStateMachine,
    )
    from modules.workflow.domain.work_order import WorkOrder

    wo = WorkOrder(
        farm_id="f", turbine_id="t", type=WorkOrderType.CORRECTIVE,
        title="x", description="x", business_key="WO-x",
    )
    # status=DRAFT；approve_all 不合法
    with pytest.raises(InvalidTransition) as ex:
        WorkOrderStateMachine.transition(wo, "approve_all")
    assert ex.value.reason == "state_mismatch"


def test_invalid_transition_reason_guard_failed():
    """guard 拒絕（缺欄位）→ reason='guard_failed'。"""
    from modules.workflow.domain import WorkOrderStateMachine
    from modules.workflow.domain.work_order import WorkOrder, WorkOrderStatus

    wo = WorkOrder(
        farm_id="f", turbine_id="t", type=WorkOrderType.CORRECTIVE,
        title="x", description="x", business_key="WO-y",
    )
    wo.status = WorkOrderStatus.DRAFT
    # dispatch 缺 assignee_id → guard fail
    with pytest.raises(InvalidTransition) as ex:
        WorkOrderStateMachine.transition(wo, "dispatch", actor_id=uuid4())
    assert ex.value.reason == "guard_failed"


def test_invalid_transition_reason_unknown_action():
    from modules.workflow.domain import WorkOrderStateMachine
    from modules.workflow.domain.work_order import WorkOrder

    wo = WorkOrder(
        farm_id="f", turbine_id="t", type=WorkOrderType.CORRECTIVE,
        title="x", description="x", business_key="WO-z",
    )
    with pytest.raises(InvalidTransition) as ex:
        WorkOrderStateMachine.transition(wo, "fly_to_mars")
    assert ex.value.reason == "unknown_action"


def test_invalid_transition_reason_works_for_material_request():
    from modules.workflow.domain.inventory import (
        MaterialRequest, MaterialRequestStatus,
    )
    from modules.workflow.domain.inventory_state_machine import (
        MaterialRequestStateMachine,
    )

    mr = MaterialRequest(
        farm_id="f", requester_id=uuid4(), business_key="MR-x",
    )
    # DRAFT → approve_all 不合法
    with pytest.raises(InvalidTransition) as ex:
        MaterialRequestStateMachine.transition(mr, "approve_all")
    assert ex.value.reason == "state_mismatch"


def test_invalid_transition_reason_backward_compat():
    """直接 raise InvalidTransition without reason — reason=None。"""
    exc = InvalidTransition("some legacy error")
    assert exc.reason is None
    assert str(exc) == "some legacy error"
