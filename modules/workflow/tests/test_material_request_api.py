"""FastAPI material-request router tests（WMOM-20260509-03）。

涵蓋 9 endpoints + approval 整合（簽核完成後自動 dispatch）。

注入 mock repository factory 避開 monitoring FarmRegistry 依賴。
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

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
    material_request_router,
    router as workflow_router,
)
from modules.workflow.routers.approval_router import set_signoff_factories
from modules.workflow.routers.material_request_router import (
    set_material_request_factories,
)
from modules.workflow.routers.work_order_router import set_repository_factory


# ─────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def client_and_setup(tmp_path):
    """TestClient + inventory item + warehouse 預先建好（給 MR test 用）。"""
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")

    def wo_factory(_farm_id: str) -> WorkOrderRepository:
        return get_repository(db_path)

    def sg_factory(_farm_id: str) -> SignoffRepository:
        return get_signoff_repository(db_path)

    def mr_factory(_farm_id: str) -> MaterialRequestRepository:
        return get_material_request_repository(db_path)

    set_repository_factory(wo_factory)
    set_signoff_factories(sg_factory, wo_factory, mr_factory)
    set_material_request_factories(mr_factory, sg_factory)

    app = FastAPI(title="material-request-test")
    app.include_router(workflow_router)
    app.include_router(approval_router)
    app.include_router(material_request_router)
    client = TestClient(app)

    # 預先建 warehouse + 1 個料件 stock=10
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

    yield client, item.id, inv_repo

    set_repository_factory(None)
    set_signoff_factories(None, None)
    set_material_request_factories(None, None)
    clear_engine_cache_for_test()


@pytest.fixture
def client(client_and_setup):
    return client_and_setup[0]


@pytest.fixture
def item_id(client_and_setup):
    return client_and_setup[1]


@pytest.fixture
def inv_repo(client_and_setup):
    return client_and_setup[2]


def _create_payload(item_id: UUID, **overrides) -> dict:
    base = {
        "farm_id": "changhua",
        "requester_id": str(uuid4()),
        "items": [
            {"item_id": str(item_id), "estimated_qty": 2, "stock_kind": "new"}
        ],
    }
    base.update(overrides)
    return base


def _create_mr(client: TestClient, item_id: UUID, **overrides) -> dict:
    """Helper：POST + 拆 response。"""
    resp = client.post(
        "/api/workflow/material-requests",
        json=_create_payload(item_id, **overrides),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ─────────────────────────────────────────────────────────────────────────
# CRUD: create
# ─────────────────────────────────────────────────────────────────────────


def test_create_returns_201(client, item_id):
    resp = client.post(
        "/api/workflow/material-requests",
        json=_create_payload(item_id),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "draft"
    assert data["farm_id"] == "changhua"
    assert len(data["items"]) == 1
    assert data["items"][0]["estimated_qty"] == 2
    assert data["items"][0]["stock_kind"] == "new"
    assert data["business_key"].startswith("MR-CHANG-")


def test_create_with_work_order(client, item_id):
    wo_id = str(uuid4())
    data = _create_mr(client, item_id, work_order_id=wo_id)
    assert data["work_order_id"] == wo_id


def test_create_no_items_rejected_422(client, item_id):
    payload = _create_payload(item_id)
    payload["items"] = []
    resp = client.post("/api/workflow/material-requests", json=payload)
    assert resp.status_code == 422  # pydantic min_length=1


def test_create_zero_qty_rejected_422(client, item_id):
    payload = _create_payload(item_id)
    payload["items"][0]["estimated_qty"] = 0
    resp = client.post("/api/workflow/material-requests", json=payload)
    assert resp.status_code == 422  # pydantic gt=0


# ─────────────────────────────────────────────────────────────────────────
# CRUD: list / get
# ─────────────────────────────────────────────────────────────────────────


def test_list_filter_by_status(client, item_id):
    _create_mr(client, item_id)
    _create_mr(client, item_id)
    resp = client.get("/api/workflow/material-requests", params={"farm_id": "changhua", "status": "draft"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert all(it["status"] == "draft" for it in data["items"])


def test_list_filter_by_work_order(client, item_id):
    wo_a = str(uuid4())
    wo_b = str(uuid4())
    _create_mr(client, item_id, work_order_id=wo_a)
    _create_mr(client, item_id, work_order_id=wo_b)
    _create_mr(client, item_id, work_order_id=wo_a)
    resp = client.get("/api/workflow/material-requests", params={"farm_id": "changhua", "work_order_id": wo_a})
    assert resp.json()["total"] == 2


def test_list_pagination(client, item_id):
    for _ in range(5):
        _create_mr(client, item_id)
    resp = client.get(
        "/api/workflow/material-requests",
        params={"farm_id": "changhua", "limit": 2, "offset": 1},
    )
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2


def test_get_404_when_not_found(client):
    resp = client.get(
        f"/api/workflow/material-requests/{uuid4()}",
        params={"farm_id": "changhua"},
    )
    assert resp.status_code == 404


def test_get_returns_full_detail(client, item_id):
    created = _create_mr(client, item_id)
    resp = client.get(
        f"/api/workflow/material-requests/{created['id']}",
        params={"farm_id": "changhua"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


# ─────────────────────────────────────────────────────────────────────────
# submit-for-approval
# ─────────────────────────────────────────────────────────────────────────


def test_submit_for_approval_transitions_state(client, item_id):
    mr = _create_mr(client, item_id)
    resp = client.post(
        f"/api/workflow/material-requests/{mr['id']}/submit-for-approval",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4())},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "awaiting_approval"
    assert data["submitted_at"] is not None
    # signoff chain wired
    assert data["signoff_chain_id"] is not None


def test_submit_for_approval_404_unknown(client):
    resp = client.post(
        f"/api/workflow/material-requests/{uuid4()}/submit-for-approval",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4())},
    )
    assert resp.status_code == 404


def test_submit_twice_rejects_409(client, item_id):
    """重覆 submit — 第二次因 state 已 AWAITING_APPROVAL 被擋。
    （注意：第二次 submit 之前 chain 已建好，所以 chain layer 不擋；MR transition 擋）。
    """
    mr = _create_mr(client, item_id)
    actor = str(uuid4())
    client.post(
        f"/api/workflow/material-requests/{mr['id']}/submit-for-approval",
        params={"farm_id": "changhua"},
        json={"actor_id": actor},
    )
    resp = client.post(
        f"/api/workflow/material-requests/{mr['id']}/submit-for-approval",
        params={"farm_id": "changhua"},
        json={"actor_id": actor},
    )
    assert resp.status_code == 409


# ─────────────────────────────────────────────────────────────────────────
# dispatch (explicit endpoint — 通常走 approval 自動觸發)
# ─────────────────────────────────────────────────────────────────────────


def _approve_to_approved_status(client, mr_id: str):
    """Helper：透過 transition path（不走 approval router）把 MR 推到 APPROVED 狀態。
    走 mr_repo direct transition：submit + approve_all。
    """
    # submit
    client.post(
        f"/api/workflow/material-requests/{mr_id}/submit-for-approval",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4())},
    )


def test_dispatch_from_draft_returns_409(client, item_id):
    """DRAFT → dispatch 不合法。"""
    mr = _create_mr(client, item_id)
    resp = client.post(
        f"/api/workflow/material-requests/{mr['id']}/dispatch",
        params={"farm_id": "changhua"},
        json={},
    )
    assert resp.status_code == 409
    assert "must be APPROVED" in resp.json()["detail"]


def test_dispatch_404_unknown(client):
    resp = client.post(
        f"/api/workflow/material-requests/{uuid4()}/dispatch",
        params={"farm_id": "changhua"},
        json={},
    )
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────
# Full lifecycle via approval — happy path（含自動 dispatch）
# ─────────────────────────────────────────────────────────────────────────


def _approve_all_chain(client, chain_id: str, farm_id: str = "changhua") -> str:
    """Approve 所有 pending steps（依 LEADER → TREASURY 順序），回傳最後一階的 ApprovalResultResponse。
    回傳 type 是 dict 但取 'subject_status_changed' 等欄位。"""
    last_resp = None
    actor = str(uuid4())
    levels = ["employee", "leader", "treasury"]  # MR 預設 3 階
    for level in levels:
        # 找該 level 的 pending step
        pending = client.get(
            "/api/workflow/approvals/pending",
            params={"farm_id": farm_id, "level": level},
        ).json()
        # 找 chain_id 對應的 step
        step = next(
            (it for it in pending["items"] if it["chain"]["id"] == chain_id), None
        )
        if step is None:
            break
        resp = client.post(
            f"/api/workflow/approvals/{step['step']['id']}/approve",
            params={"farm_id": farm_id},
            json={"actor_id": actor, "comment": f"approve {level}"},
        )
        assert resp.status_code == 200, resp.text
        last_resp = resp.json()
    return last_resp


def test_full_approval_chain_auto_dispatches(client, item_id, inv_repo):
    """完整流程：建 MR → submit → approve 3 階 → 自動 dispatch + stock 扣 + ledger 寫。"""
    initial_stock = inv_repo.get_item(item_id).stock_new

    mr = _create_mr(client, item_id)
    submit = client.post(
        f"/api/workflow/material-requests/{mr['id']}/submit-for-approval",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4())},
    )
    assert submit.status_code == 200

    chain_id = submit.json()["signoff_chain_id"]

    last = _approve_all_chain(client, chain_id)
    assert last is not None
    assert last["chain_completed"] is True
    assert last["subject_status_changed"] is True
    assert last["subject_transition_error"] is None

    # MR 應在 DISPATCHED
    mr_resp = client.get(
        f"/api/workflow/material-requests/{mr['id']}",
        params={"farm_id": "changhua"},
    )
    assert mr_resp.json()["status"] == "dispatched"

    # Stock 扣 2
    assert inv_repo.get_item(item_id).stock_new == initial_stock - 2


def test_chain_reject_transitions_mr_to_rejected(client, item_id):
    """Reject 第一階 → MR 進 REJECTED。"""
    mr = _create_mr(client, item_id)
    submit = client.post(
        f"/api/workflow/material-requests/{mr['id']}/submit-for-approval",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4())},
    )
    chain_id = submit.json()["signoff_chain_id"]

    # 找 employee level 的 pending step（第一階）
    pending = client.get(
        "/api/workflow/approvals/pending",
        params={"farm_id": "changhua", "level": "employee"},
    ).json()
    step = next(it for it in pending["items"] if it["chain"]["id"] == chain_id)

    resp = client.post(
        f"/api/workflow/approvals/{step['step']['id']}/reject",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4()), "reason": "Item not on supplier list"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["chain_completed"] is True
    assert data["subject_status_changed"] is True

    mr_resp = client.get(
        f"/api/workflow/material-requests/{mr['id']}",
        params={"farm_id": "changhua"},
    ).json()
    assert mr_resp["status"] == "rejected"
    assert mr_resp["reject_reason"] == "Item not on supplier list"


def test_dispatch_fails_at_approval_when_stock_drained(client, item_id, inv_repo):
    """簽核期間 stock 被別張單抽走 → 簽核完成時 dispatch 失敗，
    chain 已 APPROVED 但 subject_transition_error 帶回給 caller。"""
    # 建 2 張 MR，各要 6 個（共 12 但 stock 只有 10）
    a = _create_mr(client, item_id, items=[
        {"item_id": str(item_id), "estimated_qty": 6, "stock_kind": "new"}
    ])
    b = _create_mr(client, item_id, items=[
        {"item_id": str(item_id), "estimated_qty": 6, "stock_kind": "new"}
    ])

    # 都 submit
    sub_a = client.post(
        f"/api/workflow/material-requests/{a['id']}/submit-for-approval",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4())},
    ).json()
    sub_b = client.post(
        f"/api/workflow/material-requests/{b['id']}/submit-for-approval",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4())},
    ).json()

    # 先全 approve a → dispatch 成功（stock 10 - 6 = 4）
    last_a = _approve_all_chain(client, sub_a["signoff_chain_id"])
    assert last_a["subject_status_changed"] is True
    assert last_a["subject_transition_error"] is None

    # b 全 approve → 但 dispatch 時 stock 不足（4 < 6）
    last_b = _approve_all_chain(client, sub_b["signoff_chain_id"])
    assert last_b["chain_completed"] is True
    # chain 已 approve 落地，但 subject (MR) dispatch 失敗
    assert last_b["subject_status_changed"] is False
    assert last_b["subject_transition_error"] is not None
    assert "insufficient" in last_b["subject_transition_error"].lower()

    # MR b 應該卡在 APPROVED（因為 chain 完成讓它 approve_all 了，但 dispatch 沒成功）
    mr_b_resp = client.get(
        f"/api/workflow/material-requests/{b['id']}",
        params={"farm_id": "changhua"},
    ).json()
    assert mr_b_resp["status"] == "approved"  # 卡在 APPROVED，等 ops 處理

    # Stock 不變（a 走 6，剩 4）
    assert inv_repo.get_item(item_id).stock_new == 4


# ─────────────────────────────────────────────────────────────────────────
# receive
# ─────────────────────────────────────────────────────────────────────────


def test_receive_writes_actual_qty(client, item_id):
    """完整：建 → submit → approve 3 階（自動 dispatch）→ receive。"""
    mr = _create_mr(client, item_id)
    sub = client.post(
        f"/api/workflow/material-requests/{mr['id']}/submit-for-approval",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4())},
    ).json()
    _approve_all_chain(client, sub["signoff_chain_id"])

    # 取得 MR 後拿 item id
    mr_resp = client.get(
        f"/api/workflow/material-requests/{mr['id']}",
        params={"farm_id": "changhua"},
    ).json()
    mr_item_id = mr_resp["items"][0]["id"]

    resp = client.post(
        f"/api/workflow/material-requests/{mr['id']}/receive",
        params={"farm_id": "changhua"},
        json={
            "actor_id": str(uuid4()),
            "actual_quantities": {mr_item_id: 2},
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "received"
    assert data["items"][0]["actual_qty"] == 2


def test_receive_missing_item_in_dict_returns_422(client, item_id):
    mr = _create_mr(client, item_id)
    sub = client.post(
        f"/api/workflow/material-requests/{mr['id']}/submit-for-approval",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4())},
    ).json()
    _approve_all_chain(client, sub["signoff_chain_id"])

    resp = client.post(
        f"/api/workflow/material-requests/{mr['id']}/receive",
        params={"farm_id": "changhua"},
        json={
            "actor_id": str(uuid4()),
            "actual_quantities": {},  # 缺所有 items
        },
    )
    assert resp.status_code == 422
    assert "missing" in resp.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────
# close
# ─────────────────────────────────────────────────────────────────────────


def test_close_from_received(client, item_id):
    """received → close（跳過 used）。"""
    mr = _create_mr(client, item_id)
    sub = client.post(
        f"/api/workflow/material-requests/{mr['id']}/submit-for-approval",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4())},
    ).json()
    _approve_all_chain(client, sub["signoff_chain_id"])
    mr_resp = client.get(
        f"/api/workflow/material-requests/{mr['id']}",
        params={"farm_id": "changhua"},
    ).json()
    item_uuid = mr_resp["items"][0]["id"]

    client.post(
        f"/api/workflow/material-requests/{mr['id']}/receive",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4()), "actual_quantities": {item_uuid: 2}},
    )

    resp = client.post(
        f"/api/workflow/material-requests/{mr['id']}/close",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4())},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"


def test_close_from_draft_409(client, item_id):
    mr = _create_mr(client, item_id)
    resp = client.post(
        f"/api/workflow/material-requests/{mr['id']}/close",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4())},
    )
    assert resp.status_code == 409


# ─────────────────────────────────────────────────────────────────────────
# cancel
# ─────────────────────────────────────────────────────────────────────────


def test_cancel_from_draft(client, item_id):
    mr = _create_mr(client, item_id)
    resp = client.post(
        f"/api/workflow/material-requests/{mr['id']}/cancel",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4()), "cancel_reason": "Operator changed mind"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "cancelled"
    assert data["cancel_reason"] == "Operator changed mind"


def test_cancel_no_reason_422(client, item_id):
    mr = _create_mr(client, item_id)
    resp = client.post(
        f"/api/workflow/material-requests/{mr['id']}/cancel",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4()), "cancel_reason": ""},
    )
    assert resp.status_code == 422  # pydantic min_length=1


def test_cancel_from_dispatched_returns_409(client, item_id):
    """DISPATCHED → cancel 不允許（須走 returns 流程）。"""
    mr = _create_mr(client, item_id)
    sub = client.post(
        f"/api/workflow/material-requests/{mr['id']}/submit-for-approval",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4())},
    ).json()
    _approve_all_chain(client, sub["signoff_chain_id"])
    # 現在 MR 是 DISPATCHED
    resp = client.post(
        f"/api/workflow/material-requests/{mr['id']}/cancel",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4()), "cancel_reason": "Too late"},
    )
    assert resp.status_code == 409


# ─────────────────────────────────────────────────────────────────────────
# returns（建退料 + 加回 stock）
# ─────────────────────────────────────────────────────────────────────────


def test_create_return_increments_stock(client, item_id, inv_repo):
    mr = _create_mr(client, item_id)
    initial_used = inv_repo.get_item(item_id).stock_used
    resp = client.post(
        f"/api/workflow/material-requests/{mr['id']}/returns",
        params={"farm_id": "changhua"},
        json={
            "item_id": str(item_id),
            "qty": 2,
            "reason": "surplus",
            "return_to_kind": "used",
            "returned_by": str(uuid4()),
            "note": "Field operator returned 2 surplus bearings",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["qty"] == 2
    assert data["reason"] == "surplus"
    assert data["return_to_kind"] == "used"

    # stock_used 加 2
    assert inv_repo.get_item(item_id).stock_used == initial_used + 2


def test_create_return_zero_qty_422(client, item_id):
    mr = _create_mr(client, item_id)
    resp = client.post(
        f"/api/workflow/material-requests/{mr['id']}/returns",
        params={"farm_id": "changhua"},
        json={
            "item_id": str(item_id),
            "qty": 0,
            "reason": "surplus",
            "return_to_kind": "new",
            "returned_by": str(uuid4()),
        },
    )
    assert resp.status_code == 422  # pydantic gt=0


def test_create_return_unknown_request_404(client, item_id):
    resp = client.post(
        f"/api/workflow/material-requests/{uuid4()}/returns",
        params={"farm_id": "changhua"},
        json={
            "item_id": str(item_id),
            "qty": 1,
            "reason": "surplus",
            "return_to_kind": "new",
            "returned_by": str(uuid4()),
        },
    )
    assert resp.status_code == 404
