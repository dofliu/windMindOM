"""WMOM-20260518-01 — MaterialRequestItemResponse 加 sku/name/unit join 測試。

涵蓋：
1. repo.resolve_item_metadata batch fetch（含 empty / missing item_id 處理）
2. router /material-requests 系列 endpoint 回傳 items[].sku / name / unit
3. data drift（item 被刪）→ 對應 row 維持 None，不 crash
"""

from __future__ import annotations

import sqlite3  # SQLite-only：本 repo 至 M6 前都是 single-file SQLite per farm
import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

# 預先 import cost_ledger 讓 CostLedgerEntryORM 註冊到 Base.metadata；否則第一次
# Base.metadata.create_all 不會建出 cost_ledger_entries 表（dispatch 雙寫會失敗）。
# 與既有 test_dispatch_atomic_transaction 同 pattern。
from modules.cost.repository.cost_ledger import (  # noqa: F401
    CostLedgerEntryORM,
)
from modules.workflow.repository import (
    ItemMetadata,
    MaterialRequestRepository,
    SignoffRepository,
    get_inventory_repository,
    get_material_request_repository,
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


@pytest.fixture
def setup(tmp_path):
    """TestClient + 3 個料件 + 1 個 MR 用 2 個 items 預先建好。"""
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")

    def mr_factory(_farm_id: str) -> MaterialRequestRepository:
        return get_material_request_repository(db_path)

    def sg_factory(_farm_id: str) -> SignoffRepository:
        return get_signoff_repository(db_path)

    set_signoff_factories(sg_factory, None, mr_factory)
    set_material_request_factories(mr_factory, sg_factory)

    app = FastAPI(title="mr-item-meta-test")
    app.include_router(workflow_router)
    app.include_router(approval_router)
    app.include_router(material_request_router)
    client = TestClient(app)

    inv_repo = get_inventory_repository(db_path)
    wh = inv_repo.create_warehouse(farm_id="changhua", name="W", is_default=True)
    item_a = inv_repo.create_item(
        sku="GBR-001",
        name="齒輪箱軸承",
        description="Z72 主齒輪箱",
        unit="piece",
        farm_id="changhua",
        warehouse_id=wh.id,
        unit_cost=Decimal("450.00"),
        stock_new=10,
    )
    item_b = inv_repo.create_item(
        sku="OIL-100",
        name="齒輪箱潤滑油",
        description="ISO VG 320",
        unit="liter",
        farm_id="changhua",
        warehouse_id=wh.id,
        unit_cost=Decimal("80.00"),
        stock_new=200,
    )
    item_c_orphan_id = uuid4()  # 故意不建 — 模擬 data drift

    yield client, db_path, mr_factory, item_a, item_b, item_c_orphan_id

    set_signoff_factories(None, None, None)
    set_material_request_factories(None, None)
    clear_engine_cache_for_test()


# ─────────────────────────────────────────────────────────────────────
# Repo-level tests
# ─────────────────────────────────────────────────────────────────────


def test_resolve_item_metadata_returns_sku_name_unit(setup):
    _, _, mr_factory, item_a, item_b, _ = setup
    repo = mr_factory("changhua")
    meta = repo.resolve_item_metadata([item_a.id, item_b.id])
    assert set(meta.keys()) == {item_a.id, item_b.id}
    assert isinstance(meta[item_a.id], ItemMetadata)
    assert meta[item_a.id].sku == "GBR-001"
    assert meta[item_a.id].name == "齒輪箱軸承"
    assert meta[item_a.id].unit == "piece"
    assert meta[item_b.id].sku == "OIL-100"
    assert meta[item_b.id].unit == "liter"


def test_resolve_item_metadata_empty_input(setup):
    """空 input → 直接回 `{}`，不打 SQL。"""
    _, _, mr_factory, _, _, _ = setup
    repo = mr_factory("changhua")
    assert repo.resolve_item_metadata([]) == {}
    assert repo.resolve_item_metadata(iter([])) == {}


def test_resolve_item_metadata_missing_item_id_omitted(setup):
    """不存在的 item_id 在回傳 dict 內缺席（不 raise）。"""
    _, _, mr_factory, item_a, _, orphan_id = setup
    repo = mr_factory("changhua")
    meta = repo.resolve_item_metadata([item_a.id, orphan_id])
    assert item_a.id in meta
    assert orphan_id not in meta


# ─────────────────────────────────────────────────────────────────────
# Router-level tests — POST + GET + LIST 都填 sku/name/unit
# ─────────────────────────────────────────────────────────────────────


def _create_mr(client: TestClient, item_ids: list[UUID]) -> dict:
    payload = {
        "farm_id": "changhua",
        "requester_id": str(uuid4()),
        "items": [
            {"item_id": str(iid), "estimated_qty": 2, "stock_kind": "new"}
            for iid in item_ids
        ],
    }
    r = client.post("/api/workflow/material-requests", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_mr_response_items_include_sku_name_unit(setup):
    client, _, _, item_a, item_b, _ = setup
    data = _create_mr(client, [item_a.id, item_b.id])
    by_item_id = {it["item_id"]: it for it in data["items"]}
    a = by_item_id[str(item_a.id)]
    assert a["sku"] == "GBR-001"
    assert a["name"] == "齒輪箱軸承"
    assert a["unit"] == "piece"
    b = by_item_id[str(item_b.id)]
    assert b["sku"] == "OIL-100"
    assert b["unit"] == "liter"


def test_get_mr_response_items_include_sku_name_unit(setup):
    client, _, _, item_a, item_b, _ = setup
    mr = _create_mr(client, [item_a.id, item_b.id])
    r = client.get(
        f"/api/workflow/material-requests/{mr['id']}",
        params={"farm_id": "changhua"},
    )
    assert r.status_code == 200
    items = r.json()["items"]
    skus = {it["sku"] for it in items}
    assert skus == {"GBR-001", "OIL-100"}
    for it in items:
        assert it["name"]
        assert it["unit"]


def test_list_mr_response_items_include_sku_name_unit(setup):
    client, _, _, item_a, item_b, _ = setup
    _create_mr(client, [item_a.id])
    _create_mr(client, [item_b.id])
    r = client.get(
        "/api/workflow/material-requests",
        params={"farm_id": "changhua"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 2
    all_skus: set[str | None] = set()
    for mr in body["items"]:
        for it in mr["items"]:
            all_skus.add(it["sku"])
    assert {"GBR-001", "OIL-100"} <= all_skus


def _approve_all_chain(client: TestClient, chain_id: str) -> None:
    """LEADER → TREASURY 各用不同 actor 簽完整鏈。"""
    for level in ("employee", "leader", "treasury"):
        pending = client.get(
            "/api/workflow/approvals/pending",
            params={"farm_id": "changhua", "level": level},
        ).json()
        step = next(
            (it for it in pending["items"] if it["chain"]["id"] == chain_id),
            None,
        )
        if step is None:
            continue
        r = client.post(
            f"/api/workflow/approvals/{step['step']['id']}/approve",
            params={"farm_id": "changhua"},
            json={"actor_id": str(uuid4()), "comment": f"ok {level}"},
        )
        assert r.status_code == 200, r.text


def test_full_transition_chain_responses_carry_sku_name_unit(setup):
    """smoke：submit_for_approval / 自動 dispatch / receive / close 四個 transition 回傳的 items 都有 sku/name/unit。

    保護 router 端 9 個 call site 任何一個漏接 ``_build_mr_response``。
    """
    client, _, _, item_a, _, _ = setup
    mr = _create_mr(client, [item_a.id])

    # submit-for-approval
    submitted = client.post(
        f"/api/workflow/material-requests/{mr['id']}/submit-for-approval",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4())},
    ).json()
    assert submitted["items"][0]["sku"] == "GBR-001"
    assert submitted["items"][0]["name"] == "齒輪箱軸承"
    assert submitted["items"][0]["unit"] == "piece"

    # approve 3 階 → 自動 dispatch
    _approve_all_chain(client, submitted["signoff_chain_id"])

    # GET 確認 dispatched 後 items 仍帶 metadata
    after_dispatch = client.get(
        f"/api/workflow/material-requests/{mr['id']}",
        params={"farm_id": "changhua"},
    ).json()
    assert after_dispatch["status"] == "dispatched"
    assert after_dispatch["items"][0]["sku"] == "GBR-001"

    # receive
    mr_item_id = after_dispatch["items"][0]["id"]
    received = client.post(
        f"/api/workflow/material-requests/{mr['id']}/receive",
        params={"farm_id": "changhua"},
        json={
            "actor_id": str(uuid4()),
            "actual_quantities": {mr_item_id: 2},
        },
    ).json()
    assert received["items"][0]["sku"] == "GBR-001"
    assert received["items"][0]["actual_qty"] == 2
    assert received["items"][0]["unit"] == "piece"

    # close
    closed = client.post(
        f"/api/workflow/material-requests/{mr['id']}/close",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4())},
    ).json()
    assert closed["status"] == "closed"
    assert closed["items"][0]["sku"] == "GBR-001"


def test_cancel_response_carries_sku_name_unit(setup):
    """cancel transition 與正常 close 不同 path，獨立驗證。"""
    client, _, _, item_a, _, _ = setup
    mr = _create_mr(client, [item_a.id])
    cancelled = client.post(
        f"/api/workflow/material-requests/{mr['id']}/cancel",
        params={"farm_id": "changhua"},
        json={"actor_id": str(uuid4()), "cancel_reason": "test cancel"},
    ).json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["items"][0]["sku"] == "GBR-001"
    assert cancelled["items"][0]["unit"] == "piece"


def test_mr_items_with_deleted_inventory_item_yields_none_meta(setup):
    """模擬 data drift：MR item 的 item_id 在 inventory_items 找不到 → sku/name/unit 為 None。

    InventoryRepository 目前未提供 delete API（不在本 issue scope），改以 SQLite raw
    delete 模擬。M6 切 PostgreSQL 後（WMOM-20260509-F6）需重寫此 fixture。
    """
    client, db_path, _, item_a, _, _ = setup
    mr = _create_mr(client, [item_a.id])
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM inventory_items WHERE id = ?", (str(item_a.id),))
        conn.commit()
    r = client.get(
        f"/api/workflow/material-requests/{mr['id']}",
        params={"farm_id": "changhua"},
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["sku"] is None
    assert items[0]["name"] is None
    assert items[0]["unit"] is None
    # 但 item_id / estimated_qty 不受影響
    assert items[0]["item_id"] == str(item_a.id)
    assert items[0]["estimated_qty"] == 2
