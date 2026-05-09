"""FastAPI inventory router tests（WMOM-20260509-04）。

涵蓋 8 endpoints（6 inventory + 2 warehouse）。

注入 mock repository factory 避開 monitoring FarmRegistry 依賴。
"""

from __future__ import annotations

import sys
import time
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
    get_inventory_repository,
)
from modules.workflow.repository.work_order_repository import (
    clear_engine_cache_for_test,
)
from modules.workflow.routers import inventory_router
from modules.workflow.routers.inventory_router import set_inventory_factory


@pytest.fixture
def client_and_repo(tmp_path):
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")

    def factory(_farm_id: str) -> InventoryRepository:
        return get_inventory_repository(db_path)

    set_inventory_factory(factory)

    app = FastAPI(title="inventory-test")
    app.include_router(inventory_router)
    client = TestClient(app)
    repo = get_inventory_repository(db_path)

    yield client, repo

    set_inventory_factory(None)
    clear_engine_cache_for_test()


@pytest.fixture
def client(client_and_repo):
    return client_and_repo[0]


@pytest.fixture
def repo(client_and_repo):
    return client_and_repo[1]


@pytest.fixture
def warehouse(repo):
    """Pre-built default warehouse for tests."""
    return repo.create_warehouse(
        farm_id="changhua", name="Changhua base", is_default=True
    )


def _create_item_payload(warehouse_id: UUID, **overrides) -> dict:
    base = {
        "sku": "GBR-001",
        "name": "Gearbox bearing",
        "description": "Z72 main shaft bearing",
        "unit": "piece",
        "farm_id": "changhua",
        "warehouse_id": str(warehouse_id),
        "unit_cost": "450.00",
        "stock_new": 10,
        "safety_stock": 3,
    }
    base.update(overrides)
    return base


# ─────────────────────────────────────────────────────────────────────────
# Warehouses
# ─────────────────────────────────────────────────────────────────────────


def test_create_warehouse_returns_201(client):
    resp = client.post(
        "/api/workflow/warehouses",
        json={
            "farm_id": "changhua",
            "name": "Main warehouse",
            "location_kind": "onshore_base",
            "is_default": True,
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "Main warehouse"
    assert data["is_default"] is True


def test_create_warehouse_invalid_location_kind_422(client):
    resp = client.post(
        "/api/workflow/warehouses",
        json={
            "farm_id": "changhua",
            "name": "x",
            "location_kind": "moon_base",  # not in Literal
        },
    )
    assert resp.status_code == 422


def test_list_warehouses_default_first(client, repo):
    repo.create_warehouse(farm_id="changhua", name="A", is_default=False)
    repo.create_warehouse(farm_id="changhua", name="B", is_default=True)
    repo.create_warehouse(farm_id="changhua", name="C", is_default=False)
    resp = client.get(
        "/api/workflow/warehouses", params={"farm_id": "changhua"}
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    # default 在前，其餘按 name 排
    assert items[0]["name"] == "B"
    assert items[0]["is_default"] is True


def test_list_warehouses_excludes_other_farm(client, repo):
    repo.create_warehouse(farm_id="changhua", name="A")
    repo.create_warehouse(farm_id="other_farm", name="X")
    resp = client.get(
        "/api/workflow/warehouses", params={"farm_id": "changhua"}
    )
    assert len(resp.json()["items"]) == 1


# ─────────────────────────────────────────────────────────────────────────
# Inventory item: create
# ─────────────────────────────────────────────────────────────────────────


def test_create_item_201(client, warehouse):
    resp = client.post(
        "/api/workflow/inventory",
        json=_create_item_payload(warehouse.id),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["sku"] == "GBR-001"
    assert data["stock_new"] == 10
    # SQLAlchemy Numeric(12, 4) → 4 decimal places stored
    assert Decimal(data["unit_cost"]) == Decimal("450.00")
    # computed fields
    assert data["total_available"] == 10
    assert data["below_safety"] is False  # 10 >= 3


def test_create_item_below_safety_flag(client, warehouse):
    resp = client.post(
        "/api/workflow/inventory",
        json=_create_item_payload(
            warehouse.id, stock_new=1, stock_used=0, safety_stock=5
        ),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["total_available"] == 1
    assert data["below_safety"] is True


def test_create_item_duplicate_sku_409(client, warehouse):
    payload = _create_item_payload(warehouse.id, sku="DUP")
    r1 = client.post("/api/workflow/inventory", json=payload)
    assert r1.status_code == 201
    r2 = client.post("/api/workflow/inventory", json=payload)
    assert r2.status_code == 409
    assert "duplicate" in r2.json()["detail"].lower()


def test_create_item_negative_stock_422(client, warehouse):
    resp = client.post(
        "/api/workflow/inventory",
        json=_create_item_payload(warehouse.id, stock_new=-1),
    )
    assert resp.status_code == 422  # pydantic ge=0


def test_create_item_unit_cost_decimal_roundtrip(client, warehouse):
    resp = client.post(
        "/api/workflow/inventory",
        json=_create_item_payload(warehouse.id, sku="DEC", unit_cost="123.4567"),
    )
    assert resp.status_code == 201
    # 4 decimal places preserved
    assert resp.json()["unit_cost"] == "123.4567"


# ─────────────────────────────────────────────────────────────────────────
# Inventory item: list
# ─────────────────────────────────────────────────────────────────────────


def test_list_items_basic(client, warehouse):
    for sku in ("A", "B", "C"):
        client.post(
            "/api/workflow/inventory",
            json=_create_item_payload(warehouse.id, sku=sku),
        )
    resp = client.get(
        "/api/workflow/inventory", params={"farm_id": "changhua"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert sorted([i["sku"] for i in data["items"]]) == ["A", "B", "C"]


def test_list_items_below_safety_filter(client, warehouse):
    client.post(
        "/api/workflow/inventory",
        json=_create_item_payload(warehouse.id, sku="LOW", stock_new=1, safety_stock=5),
    )
    client.post(
        "/api/workflow/inventory",
        json=_create_item_payload(warehouse.id, sku="OK", stock_new=10, safety_stock=5),
    )
    resp = client.get(
        "/api/workflow/inventory",
        params={"farm_id": "changhua", "below_safety_only": "true"},
    )
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["sku"] == "LOW"
    assert items[0]["below_safety"] is True


def test_list_items_pagination(client, warehouse):
    for i in range(5):
        client.post(
            "/api/workflow/inventory",
            json=_create_item_payload(warehouse.id, sku=f"P{i:02d}"),
        )
    resp = client.get(
        "/api/workflow/inventory",
        params={"farm_id": "changhua", "limit": 2, "offset": 1},
    )
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2


def test_list_items_warehouse_filter(client, repo):
    wh_a = repo.create_warehouse(farm_id="changhua", name="A", is_default=True)
    wh_b = repo.create_warehouse(farm_id="changhua", name="B")
    client.post(
        "/api/workflow/inventory",
        json=_create_item_payload(wh_a.id, sku="A1"),
    )
    client.post(
        "/api/workflow/inventory",
        json=_create_item_payload(wh_b.id, sku="B1"),
    )
    resp = client.get(
        "/api/workflow/inventory",
        params={"farm_id": "changhua", "warehouse_id": str(wh_a.id)},
    )
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["sku"] == "A1"


# ─────────────────────────────────────────────────────────────────────────
# Inventory item: get / 404
# ─────────────────────────────────────────────────────────────────────────


def test_get_item_404(client):
    resp = client.get(
        f"/api/workflow/inventory/{uuid4()}",
        params={"farm_id": "changhua"},
    )
    assert resp.status_code == 404


def test_get_item_returns_full(client, warehouse):
    create = client.post(
        "/api/workflow/inventory",
        json=_create_item_payload(warehouse.id),
    )
    item_id = create.json()["id"]
    resp = client.get(
        f"/api/workflow/inventory/{item_id}",
        params={"farm_id": "changhua"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == item_id


# ─────────────────────────────────────────────────────────────────────────
# PATCH metadata
# ─────────────────────────────────────────────────────────────────────────


def test_patch_metadata_changes_safety_stock(client, warehouse):
    create = client.post(
        "/api/workflow/inventory",
        json=_create_item_payload(warehouse.id, safety_stock=3),
    )
    item_id = create.json()["id"]
    resp = client.patch(
        f"/api/workflow/inventory/{item_id}",
        params={"farm_id": "changhua"},
        json={"safety_stock": 10},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["safety_stock"] == 10
    # stock 不變
    assert data["stock_new"] == 10  # 原本是 10


def test_patch_metadata_partial_update(client, warehouse):
    """只改 description，其他不動。"""
    create = client.post(
        "/api/workflow/inventory",
        json=_create_item_payload(warehouse.id),
    )
    item_id = create.json()["id"]
    original_sku = create.json()["sku"]
    resp = client.patch(
        f"/api/workflow/inventory/{item_id}",
        params={"farm_id": "changhua"},
        json={"description": "Updated description"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["description"] == "Updated description"
    assert data["sku"] == original_sku


def test_patch_metadata_negative_safety_422(client, warehouse):
    create = client.post(
        "/api/workflow/inventory",
        json=_create_item_payload(warehouse.id),
    )
    item_id = create.json()["id"]
    resp = client.patch(
        f"/api/workflow/inventory/{item_id}",
        params={"farm_id": "changhua"},
        json={"safety_stock": -1},
    )
    assert resp.status_code == 422  # pydantic ge=0


def test_patch_unknown_404(client):
    resp = client.patch(
        f"/api/workflow/inventory/{uuid4()}",
        params={"farm_id": "changhua"},
        json={"safety_stock": 5},
    )
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────
# Adjust + audit log
# ─────────────────────────────────────────────────────────────────────────


def test_adjust_positive_delta_updates_stock_and_writes_log(client, warehouse):
    create = client.post(
        "/api/workflow/inventory",
        json=_create_item_payload(warehouse.id, stock_new=2),
    )
    item_id = create.json()["id"]
    actor = str(uuid4())
    resp = client.post(
        f"/api/workflow/inventory/{item_id}/adjust",
        params={"farm_id": "changhua"},
        json={
            "delta_kind": "new",
            "delta": 5,
            "reason": "歸還良品",
            "actor_id": actor,
            "note": "維修後回庫",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["item"]["stock_new"] == 7
    assert data["log"]["delta"] == 5
    assert data["log"]["reason"] == "歸還良品"
    assert data["log"]["actor_id"] == actor


def test_adjust_negative_delta(client, warehouse):
    create = client.post(
        "/api/workflow/inventory",
        json=_create_item_payload(warehouse.id, stock_new=10),
    )
    item_id = create.json()["id"]
    resp = client.post(
        f"/api/workflow/inventory/{item_id}/adjust",
        params={"farm_id": "changhua"},
        json={
            "delta_kind": "new",
            "delta": -3,
            "reason": "盤虧",
            "actor_id": str(uuid4()),
        },
    )
    assert resp.status_code == 200
    assert resp.json()["item"]["stock_new"] == 7


def test_adjust_insufficient_stock_409(client, warehouse):
    create = client.post(
        "/api/workflow/inventory",
        json=_create_item_payload(warehouse.id, stock_new=2),
    )
    item_id = create.json()["id"]
    resp = client.post(
        f"/api/workflow/inventory/{item_id}/adjust",
        params={"farm_id": "changhua"},
        json={
            "delta_kind": "new",
            "delta": -5,
            "reason": "bad",
            "actor_id": str(uuid4()),
        },
    )
    assert resp.status_code == 409
    assert "insufficient" in resp.json()["detail"].lower()


def test_adjust_blank_reason_422(client, warehouse):
    create = client.post(
        "/api/workflow/inventory",
        json=_create_item_payload(warehouse.id),
    )
    item_id = create.json()["id"]
    resp = client.post(
        f"/api/workflow/inventory/{item_id}/adjust",
        params={"farm_id": "changhua"},
        json={
            "delta_kind": "new",
            "delta": 1,
            "reason": "",  # empty
            "actor_id": str(uuid4()),
        },
    )
    assert resp.status_code == 422  # pydantic min_length=1


def test_adjust_unknown_item_404(client):
    resp = client.post(
        f"/api/workflow/inventory/{uuid4()}/adjust",
        params={"farm_id": "changhua"},
        json={
            "delta_kind": "new",
            "delta": 1,
            "reason": "x",
            "actor_id": str(uuid4()),
        },
    )
    assert resp.status_code == 404


def test_adjust_invalid_delta_kind_422(client, warehouse):
    create = client.post(
        "/api/workflow/inventory",
        json=_create_item_payload(warehouse.id),
    )
    item_id = create.json()["id"]
    resp = client.post(
        f"/api/workflow/inventory/{item_id}/adjust",
        params={"farm_id": "changhua"},
        json={
            "delta_kind": "weird",
            "delta": 1,
            "reason": "x",
            "actor_id": str(uuid4()),
        },
    )
    assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────
# Adjustment log query
# ─────────────────────────────────────────────────────────────────────────


def test_list_adjustments_returns_history(client, warehouse):
    create = client.post(
        "/api/workflow/inventory",
        json=_create_item_payload(warehouse.id, stock_new=10),
    )
    item_id = create.json()["id"]
    actor = str(uuid4())
    for delta, reason in [(1, "r1"), (2, "r2"), (3, "r3")]:
        client.post(
            f"/api/workflow/inventory/{item_id}/adjust",
            params={"farm_id": "changhua"},
            json={
                "delta_kind": "new",
                "delta": delta,
                "reason": reason,
                "actor_id": actor,
            },
        )
        time.sleep(0.005)
    resp = client.get(
        f"/api/workflow/inventory/{item_id}/adjustments",
        params={"farm_id": "changhua"},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 3
    assert {it["reason"] for it in items} == {"r1", "r2", "r3"}


def test_list_adjustments_empty(client, warehouse):
    create = client.post(
        "/api/workflow/inventory",
        json=_create_item_payload(warehouse.id),
    )
    item_id = create.json()["id"]
    resp = client.get(
        f"/api/workflow/inventory/{item_id}/adjustments",
        params={"farm_id": "changhua"},
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_list_adjustments_pagination(client, warehouse):
    create = client.post(
        "/api/workflow/inventory",
        json=_create_item_payload(warehouse.id, stock_new=20),
    )
    item_id = create.json()["id"]
    actor = str(uuid4())
    for i in range(5):
        client.post(
            f"/api/workflow/inventory/{item_id}/adjust",
            params={"farm_id": "changhua"},
            json={
                "delta_kind": "new",
                "delta": 1,
                "reason": f"r{i}",
                "actor_id": actor,
            },
        )
        time.sleep(0.002)
    resp = client.get(
        f"/api/workflow/inventory/{item_id}/adjustments",
        params={"farm_id": "changhua", "limit": 2, "offset": 0},
    )
    assert len(resp.json()["items"]) == 2
