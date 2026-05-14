"""**WMOM-20260509-05 acceptance test** — 完整 lifecycle ledger 確認鏈路。

驗收：
- material_request dispatch → ledger entry created (estimated)
- WO finish → ledger entry updated (confirmed) — 一次測過
- 用 actual_qty × unit_cost 取代 estimated amount

這是 M4 demo flow 的最後一塊拼圖：「告警 → 工單 → 簽核 → 派工 → 領料簽核 →
庫存扣帳 → 完工 → cost actual 寫入 → 月報 PDF」。
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.cost.repository import (
    CostLedgerCategory,
    CostLedgerSourceType,
    CostLedgerStatus,
    get_cost_ledger_repository,
)
from modules.workflow.domain import FollowupKind, Priority, WorkOrderType
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
    set_finish_hook_db_path,
    set_repository_factory,
)


@pytest.fixture
def lifecycle_setup(tmp_path):
    """完整 setup：所有 routers + 共用 db_path + 預建料件 stock=10。"""
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")

    def wo_factory(_):
        return get_repository(db_path)

    def sg_factory(_):
        return get_signoff_repository(db_path)

    def mr_factory(_):
        return get_material_request_repository(db_path)

    def inv_factory(_):
        return get_inventory_repository(db_path)

    set_repository_factory(wo_factory)
    set_signoff_factories(sg_factory, wo_factory, mr_factory)
    set_material_request_factories(mr_factory, sg_factory)
    set_inventory_factory(inv_factory)
    set_finish_hook_db_path(db_path)  # WMOM-20260509-05: tell finish hook the test DB

    app = FastAPI(title="lifecycle-test")
    app.include_router(workflow_router)
    app.include_router(approval_router)
    app.include_router(material_request_router)
    app.include_router(inventory_router)
    client = TestClient(app)

    inv_repo = get_inventory_repository(db_path)
    wh = inv_repo.create_warehouse(
        farm_id="changhua", name="W", is_default=True
    )
    item = inv_repo.create_item(
        sku="GBR-001",
        name="Gearbox bearing",
        description="Z72",
        unit="piece",
        farm_id="changhua",
        warehouse_id=wh.id,
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
    set_finish_hook_db_path(None)
    clear_engine_cache_for_test()


def _approve_chain(client, chain_id: str, levels=("employee", "leader")):
    # WMOM-20260510-01 Part A：separation-of-duties → 每階用不同 actor
    for level in levels:
        actor = str(uuid4())
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


# ─────────────────────────────────────────────────────────────────────────
# Acceptance test：完整 lifecycle MR dispatch → WO finish → confirmed
# ─────────────────────────────────────────────────────────────────────────


def test_full_lifecycle_estimated_to_confirmed(lifecycle_setup):
    """
    Step 1: 建工單 (corrective)
    Step 2: dispatch + start_work
    Step 3: 建 MR linked to WO，submit + 3 階 approve → 自動 dispatch（atomic 雙寫，
            ledger entry created at estimated）
    Step 4: receive MR with actual_qty=2（estimated 也是 2）
    Step 5: finish WO → A5 hook 確認 ledger entry：amount=2*450=900, status=confirmed
    """
    s = lifecycle_setup
    client = s["client"]
    item_id = s["item_id"]
    inv_repo = s["inv_repo"]
    ledger_repo = s["ledger_repo"]
    wo_repo = s["wo_repo"]

    # Step 1: 建工單
    actor = uuid4()
    wo = wo_repo.create(
        farm_id="changhua",
        turbine_id="WT001",
        type=WorkOrderType.CORRECTIVE,
        title="Gearbox bearing replacement",
        description="Z72 main shaft bearing failure",
        priority=Priority.HIGH,
        assignee_id=actor,
        crew_size=2,
        estimated_hours=4.0,
        created_by=actor,
    )

    # Step 2: dispatch + start_work
    wo_repo.transition(wo.id, "dispatch", actor_id=actor)
    wo_repo.transition(wo.id, "start_work")

    # Step 3: 建 MR
    create_resp = client.post(
        "/api/workflow/material-requests",
        json={
            "farm_id": "changhua",
            "requester_id": str(actor),
            "items": [
                {"item_id": str(item_id), "estimated_qty": 2, "stock_kind": "new"},
            ],
            "work_order_id": str(wo.id),
        },
    )
    assert create_resp.status_code == 201
    mr = create_resp.json()

    submit = client.post(
        f"/api/workflow/material-requests/{mr['id']}/submit-for-approval",
        params={"farm_id": "changhua"},
        json={"actor_id": str(actor)},
    ).json()
    chain_id = submit["signoff_chain_id"]

    # 3 階 approve（MR 預設 employee/leader/treasury）
    _approve_chain(client, chain_id, levels=("employee", "leader", "treasury"))

    # Step 3 verify: MR DISPATCHED + ledger entry created (estimated)
    fresh_mr = client.get(
        f"/api/workflow/material-requests/{mr['id']}",
        params={"farm_id": "changhua"},
    ).json()
    assert fresh_mr["status"] == "dispatched"

    ledger_entries, total = ledger_repo.list(farm_id="changhua")
    assert total == 1
    initial_entry = ledger_entries[0]
    assert initial_entry.status is CostLedgerStatus.ESTIMATED
    assert initial_entry.amount == Decimal("900.00")  # 2 × 450
    assert initial_entry.source_type is CostLedgerSourceType.MATERIAL_REQUEST

    # Stock 已扣
    assert inv_repo.get_item(item_id).stock_new == 8

    # Step 4: receive MR with actual_qty=2
    mr_item_id = fresh_mr["items"][0]["id"]
    receive = client.post(
        f"/api/workflow/material-requests/{mr['id']}/receive",
        params={"farm_id": "changhua"},
        json={
            "actor_id": str(actor),
            "actual_quantities": {mr_item_id: 2},
        },
    )
    assert receive.status_code == 200
    assert receive.json()["status"] == "received"

    # Step 5: finish WO → A5 hook flips ledger entry
    finish_resp = client.post(
        f"/api/workflow/work-orders/{wo.id}/finish",
        params={"farm_id": "changhua"},
        json={
            "actual_hours": 3.5,
            "followup_kind": "none",
            "work_summary": "Bearing replaced and tested",
        },
    )
    assert finish_resp.status_code == 200, finish_resp.text

    # ✓ Acceptance: ledger entry 從 estimated → confirmed
    confirmed_entry = ledger_repo.get(initial_entry.id)
    assert confirmed_entry is not None
    assert confirmed_entry.status is CostLedgerStatus.CONFIRMED
    assert confirmed_entry.amount == Decimal("900.00")  # actual = estimated this time
    assert confirmed_entry.confirmed_at is not None


def test_lifecycle_actual_differs_from_estimated(lifecycle_setup):
    """actual_qty=1 (估 2 但只用 1) → ledger amount 從 900 翻成 450 confirmed。"""
    s = lifecycle_setup
    client = s["client"]
    item_id = s["item_id"]
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
    _approve_chain(client, submit["signoff_chain_id"], ("employee", "leader", "treasury"))

    # receive actual=1（用剩 1 個）
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

    # finish WO
    client.post(
        f"/api/workflow/work-orders/{wo.id}/finish",
        params={"farm_id": "changhua"},
        json={"actual_hours": 1.5, "followup_kind": "none"},
    )

    # ✓ ledger entry = 1 × 450 = 450 confirmed
    entries, _ = ledger_repo.list(farm_id="changhua")
    assert len(entries) == 1
    assert entries[0].status is CostLedgerStatus.CONFIRMED
    assert entries[0].amount == Decimal("450.00")  # 1 × 450


def test_lifecycle_finish_without_receive_leaves_estimated(lifecycle_setup):
    """WO finish 但 MR 還沒 receive → ledger 留 estimated（hook 跳過）。

    Edge case：spare parts dispatched 但工單 finish 時還沒簽收（罕見）。
    """
    s = lifecycle_setup
    client = s["client"]
    item_id = s["item_id"]
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
    _approve_chain(client, submit["signoff_chain_id"], ("employee", "leader", "treasury"))

    # 跳過 receive — MR 仍 DISPATCHED
    # finish WO 直接做
    client.post(
        f"/api/workflow/work-orders/{wo.id}/finish",
        params={"farm_id": "changhua"},
        json={"actual_hours": 1.0, "followup_kind": "none"},
    )

    # ledger 仍 estimated（hook 看 actual_qty=None 跳過）
    entries, _ = ledger_repo.list(farm_id="changhua")
    assert len(entries) == 1
    assert entries[0].status is CostLedgerStatus.ESTIMATED


def test_lifecycle_no_linked_mr_finish_works(lifecycle_setup):
    """工單沒 link MR → finish 仍正常（hook 找不到 MR，不爆）。"""
    s = lifecycle_setup
    client = s["client"]
    wo_repo = s["wo_repo"]

    actor = uuid4()
    wo = wo_repo.create(
        farm_id="changhua", turbine_id="WT001",
        type=WorkOrderType.INSPECTION, title="x", description="x",
        priority=Priority.LOW, assignee_id=actor, created_by=actor,
    )
    wo_repo.transition(wo.id, "dispatch", actor_id=actor)
    wo_repo.transition(wo.id, "start_work")

    resp = client.post(
        f"/api/workflow/work-orders/{wo.id}/finish",
        params={"farm_id": "changhua"},
        json={"actual_hours": 0.5, "followup_kind": "none"},
    )
    assert resp.status_code == 200


def test_lifecycle_summary_after_confirm(lifecycle_setup):
    """完整流程後，cost ledger summary 拿到 confirmed material cost。"""
    s = lifecycle_setup
    client = s["client"]
    item_id = s["item_id"]
    ledger_repo = s["ledger_repo"]
    wo_repo = s["wo_repo"]

    actor = uuid4()
    wo = wo_repo.create(
        farm_id="changhua", turbine_id="WT001",
        type=WorkOrderType.CORRECTIVE, title="x", description="x",
        priority=Priority.HIGH, assignee_id=actor, created_by=actor,
    )
    wo_repo.transition(wo.id, "dispatch", actor_id=actor)
    wo_repo.transition(wo.id, "start_work")

    mr = client.post(
        "/api/workflow/material-requests",
        json={
            "farm_id": "changhua",
            "requester_id": str(actor),
            "items": [{"item_id": str(item_id), "estimated_qty": 3, "stock_kind": "new"}],
            "work_order_id": str(wo.id),
        },
    ).json()
    submit = client.post(
        f"/api/workflow/material-requests/{mr['id']}/submit-for-approval",
        params={"farm_id": "changhua"},
        json={"actor_id": str(actor)},
    ).json()
    _approve_chain(client, submit["signoff_chain_id"], ("employee", "leader", "treasury"))

    fresh_mr = client.get(
        f"/api/workflow/material-requests/{mr['id']}",
        params={"farm_id": "changhua"},
    ).json()
    client.post(
        f"/api/workflow/material-requests/{mr['id']}/receive",
        params={"farm_id": "changhua"},
        json={
            "actor_id": str(actor),
            "actual_quantities": {fresh_mr["items"][0]["id"]: 3},
        },
    )
    client.post(
        f"/api/workflow/work-orders/{wo.id}/finish",
        params={"farm_id": "changhua"},
        json={"actual_hours": 5.0, "followup_kind": "none"},
    )

    # Confirmed-only summary（給月報用）
    summary = ledger_repo.summary_by_category(
        farm_id="changhua", status=CostLedgerStatus.CONFIRMED
    )
    assert summary[CostLedgerCategory.MATERIAL] == Decimal("1350.00")  # 3 × 450
