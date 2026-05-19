"""MR item SKU/name/unit join regression tests（WMOM-20260518-01）。

驗證 ``MaterialRequestRepository._to_domain`` 透過 ``_fetch_item_info_map``
把 ``InventoryItem.sku / name / unit`` 帶回 ``MaterialRequestItem``：

- create / get / list / list_for_work_order / transition / dispatch_request
  6 條讀回 path 都應 populate 三欄
- 多筆 items 對應不同 inventory item 時，sku/name/unit 各自正確配對
- Schema 層 ``MaterialRequestItemResponse`` 三欄正確序列化

注意：domain ``MaterialRequestItem`` 三欄為 Optional[str]，直接 dataclass 建構
（state machine unit test 等不 hit DB 的場景）允許 None — 是預期行為。
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.workflow.domain.inventory import (
    MaterialRequestItem,
    MaterialRequestStatus,
    StockKind,
)

# 觸發 cost_ledger ORM 註冊（dispatch_request 在 atomic 雙寫時需要
# ``cost_ledger_entries`` 表存在；同 module 一旦 import，
# ``Base.metadata.create_all`` 才能建到此表）。
import modules.cost.repository.cost_ledger  # noqa: F401
from modules.workflow.repository import (
    InventoryRepository,
    MaterialRequestRepository,
    get_inventory_repository,
    get_material_request_repository,
)
from modules.workflow.repository.work_order_repository import (
    clear_engine_cache_for_test,
)
from modules.workflow.schemas import MaterialRequestResponse


# ─────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "wind_farm.db")


@pytest.fixture
def inv_repo(db_path) -> InventoryRepository:
    clear_engine_cache_for_test()
    yield get_inventory_repository(db_path)
    clear_engine_cache_for_test()


@pytest.fixture
def mr_repo(db_path, inv_repo) -> MaterialRequestRepository:
    return get_material_request_repository(db_path)


@pytest.fixture
def warehouse(inv_repo):
    return inv_repo.create_warehouse(
        farm_id="changhua", name="Changhua base", is_default=True
    )


@pytest.fixture
def gearbox_bearing(inv_repo, warehouse):
    return inv_repo.create_item(
        sku="GBR-001",
        name="齒輪箱軸承",
        description="Z72 gearbox bearing",
        unit="piece",
        farm_id="changhua",
        warehouse_id=warehouse.id,
        unit_cost=Decimal("450.00"),
        stock_new=10,
    )


@pytest.fixture
def gear_oil(inv_repo, warehouse):
    return inv_repo.create_item(
        sku="OIL-100",
        name="齒輪油 ISO VG 320",
        description="Mobil SHC 632",
        unit="公升",
        farm_id="changhua",
        warehouse_id=warehouse.id,
        unit_cost=Decimal("120.50"),
        stock_new=200,
    )


# ─────────────────────────────────────────────────────────────────────────
# Domain dataclass — optional fields
# ─────────────────────────────────────────────────────────────────────────


def test_domain_item_sku_name_unit_default_none():
    """Pure domain 建構（不 hit DB）應允許三欄 None。"""
    item = MaterialRequestItem(
        request_id=uuid4(), item_id=uuid4(), estimated_qty=1
    )
    assert item.item_sku is None
    assert item.item_name is None
    assert item.item_unit is None


def test_domain_item_sku_name_unit_explicit():
    """顯式賦值可正確帶入。"""
    item = MaterialRequestItem(
        request_id=uuid4(),
        item_id=uuid4(),
        estimated_qty=1,
        item_sku="GBR-001",
        item_name="軸承",
        item_unit="piece",
    )
    assert item.item_sku == "GBR-001"
    assert item.item_name == "軸承"
    assert item.item_unit == "piece"


# ─────────────────────────────────────────────────────────────────────────
# Repository read paths — 6 條
# ─────────────────────────────────────────────────────────────────────────


def test_create_returns_items_with_sku_name_unit(mr_repo, gearbox_bearing):
    mr = mr_repo.create(
        farm_id="changhua",
        requester_id=uuid4(),
        items=[(gearbox_bearing.id, 2, StockKind.NEW)],
    )
    assert len(mr.items) == 1
    only = mr.items[0]
    assert only.item_sku == "GBR-001"
    assert only.item_name == "齒輪箱軸承"
    assert only.item_unit == "piece"


def test_get_returns_items_with_sku_name_unit(mr_repo, gearbox_bearing):
    created = mr_repo.create(
        farm_id="changhua",
        requester_id=uuid4(),
        items=[(gearbox_bearing.id, 3, StockKind.NEW)],
    )
    fetched = mr_repo.get(created.id)
    assert fetched is not None
    only = fetched.items[0]
    assert only.item_sku == "GBR-001"
    assert only.item_name == "齒輪箱軸承"
    assert only.item_unit == "piece"


def test_get_by_business_key_returns_items_with_sku(mr_repo, gearbox_bearing):
    created = mr_repo.create(
        farm_id="changhua",
        requester_id=uuid4(),
        items=[(gearbox_bearing.id, 1, StockKind.NEW)],
    )
    fetched = mr_repo.get_by_business_key(created.business_key)
    assert fetched is not None
    assert fetched.items[0].item_sku == "GBR-001"


def test_list_returns_items_with_sku(mr_repo, gearbox_bearing):
    mr_repo.create(
        farm_id="changhua",
        requester_id=uuid4(),
        items=[(gearbox_bearing.id, 1, StockKind.NEW)],
    )
    mrs, total = mr_repo.list(farm_id="changhua")
    assert total == 1
    assert mrs[0].items[0].item_sku == "GBR-001"
    assert mrs[0].items[0].item_unit == "piece"


def test_list_for_work_order_returns_items_with_sku(mr_repo, gearbox_bearing):
    wo_id = uuid4()
    mr_repo.create(
        farm_id="changhua",
        requester_id=uuid4(),
        items=[(gearbox_bearing.id, 1, StockKind.NEW)],
        work_order_id=wo_id,
    )
    mrs = mr_repo.list_for_work_order(wo_id)
    assert len(mrs) == 1
    assert mrs[0].items[0].item_name == "齒輪箱軸承"


def test_transition_returns_items_with_sku(mr_repo, gearbox_bearing):
    mr = mr_repo.create(
        farm_id="changhua",
        requester_id=uuid4(),
        items=[(gearbox_bearing.id, 1, StockKind.NEW)],
    )
    actor = uuid4()
    after = mr_repo.transition(mr.id, "submit_for_approval", actor_id=actor)
    assert after.status is MaterialRequestStatus.AWAITING_APPROVAL
    assert after.items[0].item_sku == "GBR-001"


def test_dispatch_request_returns_items_with_sku(mr_repo, gearbox_bearing):
    """dispatch_request 走 atomic stock+ledger 寫；回傳 MR 三欄也應正確 join。"""
    mr = mr_repo.create(
        farm_id="changhua",
        requester_id=uuid4(),
        items=[(gearbox_bearing.id, 1, StockKind.NEW)],
    )
    mr_repo.transition(mr.id, "submit_for_approval", actor_id=uuid4())
    mr_repo.transition(mr.id, "approve_all", actor_id=uuid4())
    dispatched = mr_repo.dispatch_request(mr.id, actor_id=uuid4())
    assert dispatched.status is MaterialRequestStatus.DISPATCHED
    assert len(dispatched.items) == 1
    only = dispatched.items[0]
    assert only.item_sku == "GBR-001"
    assert only.item_name == "齒輪箱軸承"
    assert only.item_unit == "piece"


# ─────────────────────────────────────────────────────────────────────────
# 多 items 配對 — 不同 inventory item 各自帶回對應 sku
# ─────────────────────────────────────────────────────────────────────────


def test_multi_items_each_correctly_joined(
    mr_repo, gearbox_bearing, gear_oil
):
    mr = mr_repo.create(
        farm_id="changhua",
        requester_id=uuid4(),
        items=[
            (gearbox_bearing.id, 1, StockKind.NEW),
            (gear_oil.id, 5, StockKind.NEW),
        ],
    )
    fetched = mr_repo.get(mr.id)
    assert fetched is not None
    sku_map = {it.item_id: (it.item_sku, it.item_name, it.item_unit) for it in fetched.items}
    assert sku_map[gearbox_bearing.id] == (
        "GBR-001", "齒輪箱軸承", "piece",
    )
    assert sku_map[gear_oil.id] == (
        "OIL-100", "齒輪油 ISO VG 320", "公升",
    )


# ─────────────────────────────────────────────────────────────────────────
# Schema response — pydantic 序列化三欄
# ─────────────────────────────────────────────────────────────────────────


def test_response_serializes_sku_name_unit(mr_repo, gearbox_bearing):
    mr = mr_repo.create(
        farm_id="changhua",
        requester_id=uuid4(),
        items=[(gearbox_bearing.id, 2, StockKind.NEW)],
    )
    resp = MaterialRequestResponse.model_validate(mr)
    assert len(resp.items) == 1
    only = resp.items[0]
    assert only.item_sku == "GBR-001"
    assert only.item_name == "齒輪箱軸承"
    assert only.item_unit == "piece"
    # JSON serialization 也正常
    dumped = resp.model_dump(mode="json")
    assert dumped["items"][0]["item_sku"] == "GBR-001"
    assert dumped["items"][0]["item_name"] == "齒輪箱軸承"
    assert dumped["items"][0]["item_unit"] == "piece"


def test_response_serializes_none_when_no_inventory_join():
    """Schema 接受 sku/name/unit=None（純 domain 場景，例如 state machine unit test）。"""
    item = MaterialRequestItem(
        request_id=uuid4(), item_id=uuid4(), estimated_qty=1
    )
    # 直接從 domain dataclass 跨層
    from modules.workflow.schemas import MaterialRequestItemResponse
    resp = MaterialRequestItemResponse.model_validate(item)
    assert resp.item_sku is None
    assert resp.item_name is None
    assert resp.item_unit is None


# ─────────────────────────────────────────────────────────────────────────
# Helper edge cases
# ─────────────────────────────────────────────────────────────────────────


def test_fetch_item_info_map_empty_mrs_returns_empty(mr_repo):
    """空 list / 沒 items 的 MR 不應做 IN 查詢（IN 空集合在某些 DB 會 ill-formed）。"""
    with mr_repo._sessionmaker() as sess:
        assert MaterialRequestRepository._fetch_item_info_map(sess, []) == {}


def test_fetch_item_info_map_mrs_with_no_items_returns_empty(mr_repo, gearbox_bearing):
    """有 MR 但 items 為空 list（理論上 create 已擋）— helper guard 仍應安全。

    這裡用 manual ORM 構造一個 items 為空的 MR（不透過 create），驗證
    ``_fetch_item_info_map`` 不會嘗試做空 IN 查詢。
    """
    from modules.workflow.repository.inventory_orm import MaterialRequestORM

    with mr_repo._sessionmaker() as sess:
        empty_orm = MaterialRequestORM(id=str(uuid4()))  # items 預設 empty list
        empty_orm.items = []
        result = MaterialRequestRepository._fetch_item_info_map(sess, [empty_orm])
        assert result == {}
