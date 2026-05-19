"""MaterialRequestItemResponse SKU/name/unit enrichment 測試（WMOM-20260518-01）。

涵蓋：
- `fetch_item_metadata()` 批次查詢正確（含空集合 / 不存在 id / 多筆）
- `build_material_request_response()` 注入 metadata 後 items 有 sku/name/unit
- 沒 metadata 時 fields 保持 None（向後相容）
- Router 8 個端點回 `MaterialRequestResponse` 都帶 sku/name/unit
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
from modules.workflow.schemas import build_material_request_response


# ─────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def client_and_setup(tmp_path):
    """TestClient + 2 個 inventory item（不同 sku/name/unit）。"""
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

    app = FastAPI(title="mr-meta-test")
    app.include_router(workflow_router)
    app.include_router(approval_router)
    app.include_router(material_request_router)
    client = TestClient(app)

    inv_repo = get_inventory_repository(db_path)
    wh = inv_repo.create_warehouse(
        farm_id="changhua", name="W", is_default=True
    )
    item_a = inv_repo.create_item(
        sku="GBR-001",
        name="主軸承",
        description="Z72 gearbox bearing",
        unit="個",
        farm_id="changhua",
        warehouse_id=wh.id,
        unit_cost=Decimal("450.00"),
        stock_new=10,
    )
    item_b = inv_repo.create_item(
        sku="OIL-203",
        name="齒輪油",
        description="ISO VG320",
        unit="公升",
        farm_id="changhua",
        warehouse_id=wh.id,
        unit_cost=Decimal("80.00"),
        stock_new=20,
    )

    yield client, item_a.id, item_b.id, mr_factory

    set_repository_factory(None)
    set_signoff_factories(None, None)
    set_material_request_factories(None, None)
    clear_engine_cache_for_test()


# ─────────────────────────────────────────────────────────────────────────
# fetch_item_metadata 單元
# ─────────────────────────────────────────────────────────────────────────


def test_fetch_item_metadata_empty_returns_empty_dict(client_and_setup):
    _, _, _, mr_factory = client_and_setup
    repo = mr_factory("changhua")
    assert repo.fetch_item_metadata([]) == {}


def test_fetch_item_metadata_batch_returns_sku_name_unit(client_and_setup):
    _, item_a, item_b, mr_factory = client_and_setup
    repo = mr_factory("changhua")
    out = repo.fetch_item_metadata([item_a, item_b])
    assert out[item_a] == ("GBR-001", "主軸承", "個")
    assert out[item_b] == ("OIL-203", "齒輪油", "公升")


def test_fetch_item_metadata_unknown_id_omitted(client_and_setup):
    _, item_a, _, mr_factory = client_and_setup
    repo = mr_factory("changhua")
    unknown = uuid4()
    out = repo.fetch_item_metadata([item_a, unknown])
    assert item_a in out
    assert unknown not in out  # caller fallbacks to None


def test_fetch_item_metadata_farm_id_filter_scopes_query(client_and_setup):
    """code review should-fix #5：farm_id 過濾 — 給 multi-farm 防禦用。"""
    _, item_a, _, mr_factory = client_and_setup
    repo = mr_factory("changhua")
    # 同 farm 查得到
    assert repo.fetch_item_metadata([item_a], farm_id="changhua") != {}
    # 跨 farm 查 — 同 item_id 應被 filter 掉
    assert repo.fetch_item_metadata([item_a], farm_id="other_farm") == {}


# ─────────────────────────────────────────────────────────────────────────
# build_material_request_response — builder 單元
# ─────────────────────────────────────────────────────────────────────────


def test_builder_without_metadata_keeps_none(client_and_setup):
    _, item_a, _, mr_factory = client_and_setup
    repo = mr_factory("changhua")
    mr = repo.create(
        farm_id="changhua",
        requester_id=uuid4(),
        items=[(item_a, 2, _stock_new())],
    )
    resp = build_material_request_response(mr, item_metadata=None)
    assert resp.items[0].sku is None
    assert resp.items[0].name is None
    assert resp.items[0].unit is None


def test_builder_with_empty_dict_metadata_keeps_none(client_and_setup):
    """code review must-fix #1：``{}`` 與 ``None`` 都應走 enrich path 但全 miss 保 None。

    語意：``None`` = caller 沒查；``{}`` = caller 查了但結果空（仍 enrich loop）。
    """
    _, item_a, _, mr_factory = client_and_setup
    repo = mr_factory("changhua")
    mr = repo.create(
        farm_id="changhua",
        requester_id=uuid4(),
        items=[(item_a, 2, _stock_new())],
    )
    resp = build_material_request_response(mr, item_metadata={})
    assert resp.items[0].sku is None
    assert resp.items[0].name is None
    assert resp.items[0].unit is None


def test_builder_with_metadata_enriches_items(client_and_setup):
    _, item_a, _, mr_factory = client_and_setup
    repo = mr_factory("changhua")
    mr = repo.create(
        farm_id="changhua",
        requester_id=uuid4(),
        items=[(item_a, 2, _stock_new())],
    )
    metadata = repo.fetch_item_metadata([item_a])
    resp = build_material_request_response(mr, metadata)
    assert resp.items[0].sku == "GBR-001"
    assert resp.items[0].name == "主軸承"
    assert resp.items[0].unit == "個"


def test_builder_missing_metadata_for_one_item_keeps_none(client_and_setup):
    """Edge：metadata 對部分 items 缺漏（例如 item 後來被刪除）— 該 item 保持 None。"""
    _, item_a, item_b, mr_factory = client_and_setup
    repo = mr_factory("changhua")
    mr = repo.create(
        farm_id="changhua",
        requester_id=uuid4(),
        items=[(item_a, 2, _stock_new()), (item_b, 5, _stock_new())],
    )
    # 故意只給 item_a 的 metadata
    partial = repo.fetch_item_metadata([item_a])
    resp = build_material_request_response(mr, partial)
    item_a_resp = next(it for it in resp.items if it.item_id == item_a)
    item_b_resp = next(it for it in resp.items if it.item_id == item_b)
    assert item_a_resp.sku == "GBR-001"
    assert item_b_resp.sku is None
    assert item_b_resp.name is None


# ─────────────────────────────────────────────────────────────────────────
# Router 整合 — 確認所有 endpoint 都 enrich
# ─────────────────────────────────────────────────────────────────────────


def test_create_endpoint_returns_enriched_items(client_and_setup):
    client, item_a, _, _ = client_and_setup
    resp = client.post(
        "/api/workflow/material-requests",
        json={
            "farm_id": "changhua",
            "requester_id": str(uuid4()),
            "items": [
                {"item_id": str(item_a), "estimated_qty": 2, "stock_kind": "new"}
            ],
        },
    )
    assert resp.status_code == 201
    item = resp.json()["items"][0]
    assert item["sku"] == "GBR-001"
    assert item["name"] == "主軸承"
    assert item["unit"] == "個"


def test_get_endpoint_returns_enriched_items(client_and_setup):
    client, item_a, _, _ = client_and_setup
    create_resp = client.post(
        "/api/workflow/material-requests",
        json={
            "farm_id": "changhua",
            "requester_id": str(uuid4()),
            "items": [
                {"item_id": str(item_a), "estimated_qty": 2, "stock_kind": "new"}
            ],
        },
    )
    mr_id = create_resp.json()["id"]
    get_resp = client.get(
        f"/api/workflow/material-requests/{mr_id}?farm_id=changhua"
    )
    assert get_resp.status_code == 200
    item = get_resp.json()["items"][0]
    assert item["sku"] == "GBR-001"
    assert item["name"] == "主軸承"
    assert item["unit"] == "個"


def test_list_endpoint_returns_enriched_items_for_all_mrs(client_and_setup):
    """跨多個 MR + 多 item 確保批次 fetch 正確（無 N+1 漏 item）。"""
    client, item_a, item_b, _ = client_and_setup
    for est_qty in (1, 2, 3):
        client.post(
            "/api/workflow/material-requests",
            json={
                "farm_id": "changhua",
                "requester_id": str(uuid4()),
                "items": [
                    {"item_id": str(item_a), "estimated_qty": est_qty, "stock_kind": "new"},
                    {"item_id": str(item_b), "estimated_qty": est_qty + 1, "stock_kind": "new"},
                ],
            },
        )
    list_resp = client.get("/api/workflow/material-requests?farm_id=changhua")
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] == 3
    # 每個 MR 兩個 item 都要有 enrichment
    for mr in data["items"]:
        skus = {it["sku"] for it in mr["items"]}
        names = {it["name"] for it in mr["items"]}
        assert skus == {"GBR-001", "OIL-203"}
        assert names == {"主軸承", "齒輪油"}


def test_cancel_endpoint_still_enriches_items(client_and_setup):
    """state transition 端點也帶 enrichment（覆蓋 _enriched_response 共用 path）。"""
    client, item_a, _, _ = client_and_setup
    mr_id = client.post(
        "/api/workflow/material-requests",
        json={
            "farm_id": "changhua",
            "requester_id": str(uuid4()),
            "items": [
                {"item_id": str(item_a), "estimated_qty": 2, "stock_kind": "new"}
            ],
        },
    ).json()["id"]
    cancel_resp = client.post(
        f"/api/workflow/material-requests/{mr_id}/cancel?farm_id=changhua",
        json={"actor_id": str(uuid4()), "cancel_reason": "test"},
    )
    assert cancel_resp.status_code == 200
    item = cancel_resp.json()["items"][0]
    assert item["sku"] == "GBR-001"
    assert item["name"] == "主軸承"
    assert item["unit"] == "個"


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _stock_new():
    from modules.workflow.domain.inventory import StockKind

    return StockKind.NEW
