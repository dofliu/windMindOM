"""inventory adjust 端點的雙模式授權（WMOM-20260716-05b 示範 pattern）。

驗證：enforce=false 過渡期非破壞（沿用 body actor_id / 可省略）；token 優先；
enforce=true 後 require_role(TREASURY) + resolve 生效（401/403/200）。
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
from modules.workflow.repository import InventoryRepository, get_inventory_repository
from modules.workflow.repository.work_order_repository import clear_engine_cache_for_test
from modules.workflow.routers import inventory_router
from modules.workflow.routers.inventory_router import set_inventory_factory


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch):
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)


@pytest.fixture
def client_item(tmp_path):
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")
    set_inventory_factory(lambda _f: get_inventory_repository(db_path))
    app = FastAPI(title="inventory-auth-test")
    app.include_router(inventory_router)
    client = TestClient(app)
    repo = get_inventory_repository(db_path)
    wh = repo.create_warehouse(farm_id="changhua", name="base", is_default=True)
    create = client.post("/api/workflow/inventory", json={
        "sku": "GBR-001", "name": "Gearbox bearing", "unit": "piece", "farm_id": "changhua",
        "warehouse_id": str(wh.id), "unit_cost": "450.00", "stock_new": 10, "safety_stock": 3,
    })
    item_id = create.json()["id"]
    yield client, item_id
    set_inventory_factory(None)
    clear_engine_cache_for_test()


def _adjust(client, item_id, *, body_actor: str | None, headers: dict | None = None):
    body = {"delta_kind": "new", "delta": 1, "reason": "test"}
    if body_actor is not None:
        body["actor_id"] = body_actor
    return client.post(f"/api/workflow/inventory/{item_id}/adjust",
                       params={"farm_id": "changhua"}, json=body, headers=headers or {})


def _bearer(role: str, subject: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject=subject, role=role, name='U')}"}


# ── enforce=false（過渡期，非破壞）────────────────────────────────────
def test_legacy_body_actor_ok(client_item):
    client, item_id = client_item
    assert _adjust(client, item_id, body_actor=str(uuid4())).status_code == 200


def test_legacy_system_adjust_no_actor_ok(client_item):
    client, item_id = client_item
    resp = _adjust(client, item_id, body_actor=None)  # 系統 adjust，無真人
    assert resp.status_code == 200
    assert resp.json()["log"]["actor_id"] is None


def test_token_wins_over_body(client_item):
    client, item_id = client_item
    tok_id = str(uuid4())
    resp = _adjust(client, item_id, body_actor=str(uuid4()), headers=_bearer("treasury", tok_id))
    assert resp.status_code == 200
    assert resp.json()["log"]["actor_id"] == tok_id  # 記的是 token 身分，非 body


# ── enforce=true（cutover 後）─────────────────────────────────────────
def test_enforced_no_token_401(client_item, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    client, item_id = client_item
    assert _adjust(client, item_id, body_actor=str(uuid4())).status_code == 401


def test_enforced_non_treasury_403(client_item, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    client, item_id = client_item
    assert _adjust(client, item_id, body_actor=None, headers=_bearer("employee", str(uuid4()))).status_code == 403


def test_enforced_treasury_ok(client_item, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    client, item_id = client_item
    assert _adjust(client, item_id, body_actor=None, headers=_bearer("treasury", str(uuid4()))).status_code == 200


def test_enforced_admin_ok(client_item, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    client, item_id = client_item
    assert _adjust(client, item_id, body_actor=None, headers=_bearer("admin", str(uuid4()))).status_code == 200
