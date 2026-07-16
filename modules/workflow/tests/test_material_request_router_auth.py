"""material-request 端點的雙模式授權（WMOM-20260716-05c）。

覆蓋兩種 gate：

- ``require_authenticated``（submit-for-approval）：enforce=true 後需登入（任何角色），
  無 token → 401；有效 token（含 employee）→ 放行。
- ``require_role(LEADER, SUPERVISOR)``（cancel）：enforce=true 後非授權角色 → 403、
  授權角色 / ADMIN → 放行。

其餘 stock-touching 端點（dispatch / returns＝TREASURY）與 receive / close 共用同一
``require_role`` / ``_actor_uuid`` 機制——TREASURY gate 已於
``test_inventory_router_auth.py`` 證實，LEADER/SUPERVISOR gate 於本檔 cancel 證實；
各端點的 state machine 由 ``test_material_request_api.py`` 覆蓋。故此處聚焦 auth 機制本身，
不重測狀態流轉（避免 dispatch/receive 需先跑完整 approval flow 的脆弱 setup）。

Token 直接以 ``create_access_token`` 鑄造（不建帳、無密碼字面值）。
"""

from __future__ import annotations

import secrets
import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.auth.tokens import create_access_token
from modules.workflow.repository import (
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


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch):
    """每 test 給 JWT secret；清 dev_mode / enforce（各 test 自行 opt-in enforce）。"""
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)


@pytest.fixture
def client_mr(tmp_path):
    """TestClient + 預建 warehouse / 料件（stock=10）；注入三個 repo factory。"""
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")

    def wo_factory(_f: str) -> WorkOrderRepository:
        return get_repository(db_path)

    def sg_factory(_f: str) -> SignoffRepository:
        return get_signoff_repository(db_path)

    def mr_factory(_f: str) -> MaterialRequestRepository:
        return get_material_request_repository(db_path)

    set_repository_factory(wo_factory)
    set_signoff_factories(sg_factory, wo_factory, mr_factory)
    set_material_request_factories(mr_factory, sg_factory)

    app = FastAPI(title="material-request-auth-test")
    app.include_router(workflow_router)
    app.include_router(approval_router)
    app.include_router(material_request_router)
    client = TestClient(app)

    inv_repo = get_inventory_repository(db_path)
    wh = inv_repo.create_warehouse(farm_id="changhua", name="W", is_default=True)
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

    yield client, item.id

    set_repository_factory(None)
    set_signoff_factories(None, None)
    set_material_request_factories(None, None)
    clear_engine_cache_for_test()


def _bearer(role: str, subject: str) -> dict[str, str]:
    token = create_access_token(subject=subject, role=role, name="U")
    return {"Authorization": f"Bearer {token}"}


def _create_draft(client: TestClient, item_id) -> str:
    resp = client.post(
        "/api/workflow/material-requests",
        json={
            "farm_id": "changhua",
            "requester_id": str(uuid4()),
            "items": [
                {"item_id": str(item_id), "estimated_qty": 2, "stock_kind": "new"}
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _submit(client, mr_id, *, body_actor: str | None, headers: dict | None = None):
    body: dict = {}
    if body_actor is not None:
        body["actor_id"] = body_actor
    return client.post(
        f"/api/workflow/material-requests/{mr_id}/submit-for-approval",
        params={"farm_id": "changhua"},
        json=body,
        headers=headers or {},
    )


def _cancel(client, mr_id, *, body_actor: str | None, headers: dict | None = None):
    body: dict = {"cancel_reason": "auth-test"}
    if body_actor is not None:
        body["actor_id"] = body_actor
    return client.post(
        f"/api/workflow/material-requests/{mr_id}/cancel",
        params={"farm_id": "changhua"},
        json=body,
        headers=headers or {},
    )


# ── submit-for-approval：require_authenticated ────────────────────────────
def test_submit_legacy_body_actor_ok(client_mr):
    """enforce=false：沿用 body actor_id（現有行為，非破壞）。"""
    client, item_id = client_mr
    mr_id = _create_draft(client, item_id)
    resp = _submit(client, mr_id, body_actor=str(uuid4()))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "awaiting_approval"


def test_submit_token_ok(client_mr):
    """enforce=false：帶 token 一樣放行（token 優先於 body）。"""
    client, item_id = client_mr
    mr_id = _create_draft(client, item_id)
    resp = _submit(
        client, mr_id, body_actor=str(uuid4()), headers=_bearer("employee", str(uuid4()))
    )
    assert resp.status_code == 200, resp.text


def test_submit_enforced_no_token_401(client_mr, monkeypatch):
    """enforce=true：無 token → 401（body actor_id 不再被信任）。"""
    client, item_id = client_mr
    mr_id = _create_draft(client, item_id)  # 先在 enforce=false 下建單
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")  # 再翻旗標（is_auth_enforced 每次重讀）
    resp = _submit(client, mr_id, body_actor=str(uuid4()))
    assert resp.status_code == 401


def test_submit_enforced_employee_ok(client_mr, monkeypatch):
    """enforce=true：require_authenticated 不限角色 → employee token 也放行。

    body 仍帶 actor_id（過渡期 schema 尚必填；token 優先於 body）。
    """
    client, item_id = client_mr
    mr_id = _create_draft(client, item_id)
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = _submit(
        client, mr_id, body_actor=str(uuid4()), headers=_bearer("employee", str(uuid4()))
    )
    assert resp.status_code == 200, resp.text


# ── cancel：require_role(LEADER, SUPERVISOR) ──────────────────────────────
def test_cancel_legacy_body_actor_ok(client_mr):
    """enforce=false：role 尚未強制 → 沿用 body actor_id，放行（非破壞）。"""
    client, item_id = client_mr
    mr_id = _create_draft(client, item_id)
    resp = _cancel(client, mr_id, body_actor=str(uuid4()))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"


def test_cancel_enforced_no_token_401(client_mr, monkeypatch):
    """enforce=true：無 token → 401。"""
    client, item_id = client_mr
    mr_id = _create_draft(client, item_id)
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = _cancel(client, mr_id, body_actor=str(uuid4()))
    assert resp.status_code == 401


def test_cancel_enforced_employee_403(client_mr, monkeypatch):
    """enforce=true：employee 無取消權 → 403。"""
    client, item_id = client_mr
    mr_id = _create_draft(client, item_id)
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = _cancel(client, mr_id, body_actor=None, headers=_bearer("employee", str(uuid4())))
    assert resp.status_code == 403


def test_cancel_enforced_leader_ok(client_mr, monkeypatch):
    """enforce=true：leader（組長）可取消 → 200（body 仍帶 actor_id，token 優先）。"""
    client, item_id = client_mr
    mr_id = _create_draft(client, item_id)
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = _cancel(
        client, mr_id, body_actor=str(uuid4()), headers=_bearer("leader", str(uuid4()))
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"


def test_cancel_enforced_admin_ok(client_mr, monkeypatch):
    """enforce=true：admin 全權 → 200（body 仍帶 actor_id，token 優先）。"""
    client, item_id = client_mr
    mr_id = _create_draft(client, item_id)
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = _cancel(
        client, mr_id, body_actor=str(uuid4()), headers=_bearer("admin", str(uuid4()))
    )
    assert resp.status_code == 200, resp.text
