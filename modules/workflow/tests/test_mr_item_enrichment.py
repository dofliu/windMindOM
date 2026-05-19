"""Regression — MaterialRequest response item enrichment（WMOM-20260518-01）。

驗：detail / list / 任何 state-transition endpoint 的 ``items[].sku/name/unit`` 都帶
自 InventoryItem 主檔的值（給 frontend 顯示用，避免只能讀 truncated UUID）。
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


@pytest.fixture
def client_and_items(tmp_path):
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

    app = FastAPI(title="mr-enrichment-test")
    app.include_router(workflow_router)
    app.include_router(approval_router)
    app.include_router(material_request_router)
    client = TestClient(app)

    inv_repo = get_inventory_repository(db_path)
    wh = inv_repo.create_warehouse(farm_id="changhua", name="W", is_default=True)
    bearing = inv_repo.create_item(
        sku="GBR-001",
        name="Gearbox bearing",
        description="Z72 main bearing",
        unit="個",
        farm_id="changhua",
        warehouse_id=wh.id,
        unit_cost=Decimal("450.00"),
        stock_new=10,
    )
    oil = inv_repo.create_item(
        sku="OIL-002",
        name="齒輪箱潤滑油",
        description="ISO VG320",
        unit="公升",
        farm_id="changhua",
        warehouse_id=wh.id,
        unit_cost=Decimal("12.50"),
        stock_new=50,
    )

    yield client, bearing.id, oil.id

    set_repository_factory(None)
    set_signoff_factories(None, None)
    set_material_request_factories(None, None)
    clear_engine_cache_for_test()


def _create_mr(client: TestClient, items: list[dict]) -> dict:
    payload = {
        "farm_id": "changhua",
        "requester_id": str(uuid4()),
        "items": items,
    }
    resp = client.post("/api/workflow/material-requests", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_response_carries_sku_name_unit(client_and_items):
    client, bearing_id, oil_id = client_and_items
    body = _create_mr(
        client,
        [
            {"item_id": str(bearing_id), "estimated_qty": 2},
            {"item_id": str(oil_id), "estimated_qty": 5},
        ],
    )

    by_sku = {it["sku"]: it for it in body["items"]}
    assert set(by_sku) == {"GBR-001", "OIL-002"}
    assert by_sku["GBR-001"]["name"] == "Gearbox bearing"
    assert by_sku["GBR-001"]["unit"] == "個"
    assert by_sku["OIL-002"]["name"] == "齒輪箱潤滑油"
    assert by_sku["OIL-002"]["unit"] == "公升"


def test_get_detail_response_enriched(client_and_items):
    client, bearing_id, _ = client_and_items
    created = _create_mr(client, [{"item_id": str(bearing_id), "estimated_qty": 3}])

    resp = client.get(
        f"/api/workflow/material-requests/{created['id']}",
        params={"farm_id": "changhua"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["sku"] == "GBR-001"
    assert body["items"][0]["name"] == "Gearbox bearing"
    assert body["items"][0]["unit"] == "個"


def test_list_response_enriched(client_and_items):
    client, bearing_id, oil_id = client_and_items
    _create_mr(client, [{"item_id": str(bearing_id), "estimated_qty": 1}])
    _create_mr(client, [{"item_id": str(oil_id), "estimated_qty": 2}])

    resp = client.get(
        "/api/workflow/material-requests", params={"farm_id": "changhua"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    all_skus = {it["sku"] for mr in body["items"] for it in mr["items"]}
    assert all_skus == {"GBR-001", "OIL-002"}
    for mr in body["items"]:
        for it in mr["items"]:
            assert it["name"] is not None
            assert it["unit"] is not None


def test_missing_inventory_item_falls_back_to_none(client_and_items, tmp_path):
    """如果 MR.items 引用的 InventoryItem 不存在（被刪 / migration 漏）— enrich 不應 500。"""
    client, bearing_id, _ = client_and_items

    created = _create_mr(client, [{"item_id": str(bearing_id), "estimated_qty": 1}])

    # 直接從 DB 刪掉那筆 InventoryItem，模擬 join 失敗
    from modules.workflow.repository import InventoryItemORM
    from sqlalchemy.orm import sessionmaker as _sm
    db_path = str(tmp_path / "wind_farm.db")
    inv_repo = get_inventory_repository(db_path)
    SessionLocal = _sm(inv_repo._engine, future=True)
    with SessionLocal() as sess:
        orm = sess.get(InventoryItemORM, str(bearing_id))
        assert orm is not None
        sess.delete(orm)
        sess.commit()

    resp = client.get(
        f"/api/workflow/material-requests/{created['id']}",
        params={"farm_id": "changhua"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["sku"] is None
    assert body["items"][0]["name"] is None
    assert body["items"][0]["unit"] is None
    assert body["items"][0]["item_id"] == str(bearing_id)


def test_repository_batch_fetch_dedupes(client_and_items, tmp_path):
    """``get_items_by_ids`` 跨 farm DB 多 id 一次查回。"""
    _, bearing_id, oil_id = client_and_items
    db_path = str(tmp_path / "wind_farm.db")
    inv_repo = get_inventory_repository(db_path)

    by_id = inv_repo.get_items_by_ids([bearing_id, oil_id])
    assert set(by_id.keys()) == {bearing_id, oil_id}
    assert by_id[bearing_id].sku == "GBR-001"
    assert by_id[oil_id].sku == "OIL-002"

    # 空 list 不發 query
    assert inv_repo.get_items_by_ids([]) == {}

    # 不存在的 UUID 不會 raise，dict 缺鍵
    missing = uuid4()
    out = inv_repo.get_items_by_ids([missing])
    assert out == {}
