"""work_order 端點的雙模式授權（WMOM-20260716-05d）。

覆蓋三種 gate：

- ``require_role(EMPLOYEE, LEADER, SUPERVISOR)``（create / finish）：庫管 TREASURY 被排除。
- ``require_role(LEADER, SUPERVISOR)``（dispatch / approve / reject / cancel / reopen）：
  EMPLOYEE 也被排除（派工 / 生命週期管控＝管理層）。
- ``require_authenticated``（start-work / update-progress）：任何登入者（現場 assignee）。

聚焦 auth 機制本身：create 驗 EMPLOYEE/LEADER/SUPERVISOR gate（+TREASURY 403），
dispatch 驗 LEADER/SUPERVISOR gate（+EMPLOYEE 403）且 actor 由 token 解析，
start-work 驗 require_authenticated。各端點 state machine 由 ``test_work_order_api.py`` 覆蓋。
讀取端點（list/get）之授權延後至 -05h（同 material_request 做法）。token 直接鑄造。
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.auth.tokens import create_access_token
from modules.workflow.repository import (
    SignoffRepository,
    WorkOrderRepository,
    get_repository,
    get_signoff_repository,
)
from modules.workflow.repository.work_order_repository import (
    clear_engine_cache_for_test,
)
from modules.workflow.routers import approval_router, router as workflow_router
from modules.workflow.routers.approval_router import set_signoff_factories
from modules.workflow.routers.work_order_router import set_repository_factory


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch):
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)


@pytest.fixture
def client_wo(tmp_path):
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")

    def wo_factory(_f: str) -> WorkOrderRepository:
        return get_repository(db_path)

    def sg_factory(_f: str) -> SignoffRepository:
        return get_signoff_repository(db_path)

    set_repository_factory(wo_factory)
    set_signoff_factories(sg_factory, wo_factory)

    app = FastAPI(title="work-order-auth-test")
    app.include_router(workflow_router)
    app.include_router(approval_router)
    yield TestClient(app)

    set_repository_factory(None)
    set_signoff_factories(None, None)
    clear_engine_cache_for_test()


def _bearer(role: str, subject: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject=subject, role=role, name='U')}"}


def _create(client, *, headers: dict | None = None):
    return client.post(
        "/api/workflow/work-orders",
        json={
            "farm_id": "changhua",
            "turbine_id": "WT001",
            "type": "corrective",
            "title": "軸承過熱",
            "description": "主軸承溫度 75°C",
        },
        headers=headers or {},
    )


def _create_draft_id(client) -> str:
    r = _create(client)  # enforce=false 下建（現場動作 gate 放行）
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _dispatch(client, wo_id, *, body_actor, headers: dict | None = None):
    body: dict = {"assignee_id": str(uuid4())}  # 建單未指派 → 派工時補帶被派者
    if body_actor is not None:
        body["actor_id"] = body_actor
    return client.post(
        f"/api/workflow/work-orders/{wo_id}/dispatch?farm_id=changhua",
        json=body,
        headers=headers or {},
    )


def _start_work(client, wo_id, *, headers: dict | None = None):
    return client.post(
        f"/api/workflow/work-orders/{wo_id}/start-work?farm_id=changhua",
        json={"require_weather_window": False},
        headers=headers or {},
    )


# ── create：require_role(EMPLOYEE, LEADER, SUPERVISOR) ────────────────────
def test_create_legacy_ok(client_wo):
    """enforce=false：放行（非破壞）。"""
    assert _create(client_wo).status_code == 201


def test_create_enforced_no_token_401(client_wo, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert _create(client_wo).status_code == 401


def test_create_enforced_treasury_403(client_wo, monkeypatch):
    """庫管 TREASURY 不建工單 → 403。"""
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert _create(client_wo, headers=_bearer("treasury", str(uuid4()))).status_code == 403


def test_create_enforced_employee_ok(client_wo, monkeypatch):
    """現場工程師可建工單 → 201。"""
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert _create(client_wo, headers=_bearer("employee", str(uuid4()))).status_code == 201


def test_create_enforced_admin_ok(client_wo, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert _create(client_wo, headers=_bearer("admin", str(uuid4()))).status_code == 201


# ── dispatch：require_role(LEADER, SUPERVISOR) + actor 由 token 解析 ───────
def test_dispatch_legacy_ok(client_wo):
    """enforce=false：沿用 body actor_id，放行（非破壞）。"""
    wo_id = _create_draft_id(client_wo)
    r = _dispatch(client_wo, wo_id, body_actor=str(uuid4()))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "dispatched"


def test_dispatch_enforced_no_token_401(client_wo, monkeypatch):
    wo_id = _create_draft_id(client_wo)
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert _dispatch(client_wo, wo_id, body_actor=str(uuid4())).status_code == 401


def test_dispatch_enforced_employee_403(client_wo, monkeypatch):
    """派工＝管理層 → EMPLOYEE 403。"""
    wo_id = _create_draft_id(client_wo)
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    r = _dispatch(client_wo, wo_id, body_actor=str(uuid4()), headers=_bearer("employee", str(uuid4())))
    assert r.status_code == 403


def test_dispatch_enforced_leader_ok(client_wo, monkeypatch):
    """組長可派工 → 200（body 仍帶 actor_id，token 優先）。"""
    wo_id = _create_draft_id(client_wo)
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    r = _dispatch(client_wo, wo_id, body_actor=str(uuid4()), headers=_bearer("leader", str(uuid4())))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "dispatched"


# ── start-work：require_authenticated ─────────────────────────────────────
def test_start_work_enforced_no_token_401(client_wo, monkeypatch):
    wo_id = _create_draft_id(client_wo)
    r = _dispatch(client_wo, wo_id, body_actor=str(uuid4()))  # setup 在 enforce=false
    assert r.status_code == 200, r.text
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert _start_work(client_wo, wo_id).status_code == 401


def test_start_work_enforced_employee_ok(client_wo, monkeypatch):
    """開工＝任何登入者 → employee token 放行。"""
    wo_id = _create_draft_id(client_wo)
    r = _dispatch(client_wo, wo_id, body_actor=str(uuid4()))
    assert r.status_code == 200, r.text
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = _start_work(client_wo, wo_id, headers=_bearer("employee", str(uuid4())))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "in_progress"
