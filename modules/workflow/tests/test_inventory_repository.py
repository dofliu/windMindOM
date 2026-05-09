"""InventoryRepository tests — CRUD + adjust + audit log + safety stock。

對應 [WMOM-20260509-02](../../../ISSUES.md)。
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.workflow.domain.inventory import StockKind
from modules.workflow.repository import (
    InsufficientStock,
    InventoryRepository,
    StockAdjustmentError,
    get_inventory_repository,
)
from modules.workflow.repository.work_order_repository import (
    clear_engine_cache_for_test,
)


@pytest.fixture
def repo(tmp_path) -> InventoryRepository:
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")
    yield get_inventory_repository(db_path)
    clear_engine_cache_for_test()


@pytest.fixture
def warehouse(repo):
    return repo.create_warehouse(
        farm_id="changhua",
        name="Changhua onshore base",
        location_kind="onshore_base",
        is_default=True,
    )


def _create_item(repo, warehouse, **overrides):
    base = dict(
        sku="GBR-001",
        name="Gearbox bearing 4040",
        description="Main shaft bearing for Z72",
        unit="piece",
        farm_id="changhua",
        warehouse_id=warehouse.id,
        unit_cost=Decimal("450.00"),
    )
    base.update(overrides)
    return repo.create_item(**base)


# ─────────────────────────────────────────────────────────────────────────
# Warehouse CRUD
# ─────────────────────────────────────────────────────────────────────────


def test_create_warehouse_returns_uuid(repo):
    w = repo.create_warehouse(
        farm_id="changhua", name="x", location_kind="onshore_base"
    )
    assert isinstance(w.id, UUID)
    assert w.is_default is False


def test_get_default_warehouse(repo):
    repo.create_warehouse(farm_id="f1", name="A", is_default=False)
    repo.create_warehouse(farm_id="f1", name="B", is_default=True)
    default = repo.get_default_warehouse("f1")
    assert default is not None
    assert default.name == "B"


def test_get_default_warehouse_none_when_no_default(repo):
    repo.create_warehouse(farm_id="f2", name="A")
    assert repo.get_default_warehouse("f2") is None


# ─────────────────────────────────────────────────────────────────────────
# Inventory item CRUD
# ─────────────────────────────────────────────────────────────────────────


def test_create_item_default_zero_stock(repo, warehouse):
    item = _create_item(repo, warehouse)
    assert item.stock_new == 0
    assert item.stock_used == 0
    assert item.stock_repairing == 0
    assert item.unit_cost == Decimal("450.00")
    assert item.farm_id == "changhua"


def test_create_item_with_initial_stock(repo, warehouse):
    item = _create_item(
        repo, warehouse,
        stock_new=10, stock_used=5, safety_stock=3,
    )
    assert item.stock_new == 10
    assert item.stock_used == 5
    assert item.safety_stock == 3
    # round-trip：再讀一次也對
    fetched = repo.get_item(item.id)
    assert fetched is not None
    assert fetched.stock_new == 10
    assert fetched.stock_used == 5


def test_get_item_by_sku(repo, warehouse):
    item = _create_item(repo, warehouse, sku="GBR-XYZ")
    fetched = repo.get_item_by_sku("changhua", "GBR-XYZ")
    assert fetched is not None
    assert fetched.id == item.id


def test_get_item_by_sku_returns_none(repo):
    assert repo.get_item_by_sku("changhua", "DOES_NOT_EXIST") is None


def test_create_item_duplicate_sku_raises(repo, warehouse):
    """同 farm 同 sku unique。"""
    _create_item(repo, warehouse, sku="DUP")
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        _create_item(repo, warehouse, sku="DUP")


def test_create_item_unit_cost_decimal_roundtrip(repo, warehouse):
    """SQLite Numeric → Decimal 不掉精度。"""
    item = _create_item(repo, warehouse, sku="DEC-TEST", unit_cost=Decimal("123.4567"))
    fetched = repo.get_item(item.id)
    assert fetched.unit_cost == Decimal("123.4567")


# ─────────────────────────────────────────────────────────────────────────
# list_items + safety stock filter
# ─────────────────────────────────────────────────────────────────────────


def test_list_items_basic(repo, warehouse):
    _create_item(repo, warehouse, sku="A")
    _create_item(repo, warehouse, sku="B")
    items, total = repo.list_items(farm_id="changhua")
    assert total == 2
    assert sorted([i.sku for i in items]) == ["A", "B"]


def test_list_items_below_safety_filter(repo, warehouse):
    _create_item(repo, warehouse, sku="LOW", stock_new=1, stock_used=0, safety_stock=5)
    _create_item(repo, warehouse, sku="OK", stock_new=10, stock_used=0, safety_stock=5)
    items, total = repo.list_items(farm_id="changhua", below_safety_only=True)
    assert total == 1
    assert items[0].sku == "LOW"


def test_list_items_excludes_other_farm(repo, warehouse):
    _create_item(repo, warehouse, sku="A")
    other_wh = repo.create_warehouse(farm_id="other_farm", name="o")
    _create_item(repo, other_wh, sku="X", farm_id="other_farm")
    items, total = repo.list_items(farm_id="changhua")
    assert total == 1


def test_list_items_pagination(repo, warehouse):
    for i in range(5):
        _create_item(repo, warehouse, sku=f"P{i:02d}")
    items, total = repo.list_items(farm_id="changhua", limit=2, offset=2)
    assert total == 5
    assert [i.sku for i in items] == ["P02", "P03"]


# ─────────────────────────────────────────────────────────────────────────
# update_metadata
# ─────────────────────────────────────────────────────────────────────────


def test_update_metadata_changes_safety_stock(repo, warehouse):
    item = _create_item(repo, warehouse, safety_stock=5)
    updated = repo.update_metadata(item.id, safety_stock=10)
    assert updated.safety_stock == 10
    # stock 不動
    assert updated.stock_new == 0


def test_update_metadata_negative_safety_rejected(repo, warehouse):
    item = _create_item(repo, warehouse)
    with pytest.raises(StockAdjustmentError, match="safety_stock must be >= 0"):
        repo.update_metadata(item.id, safety_stock=-1)


def test_update_metadata_unknown_item_raises(repo):
    with pytest.raises(LookupError):
        repo.update_metadata(uuid4(), safety_stock=5)


# ─────────────────────────────────────────────────────────────────────────
# adjust + audit log
# ─────────────────────────────────────────────────────────────────────────


def test_adjust_positive_delta_writes_log(repo, warehouse):
    item = _create_item(repo, warehouse, stock_new=2)
    actor = uuid4()
    updated, log = repo.adjust(
        item.id,
        delta_kind=StockKind.NEW,
        delta=+5,
        reason="歸還良品",
        actor_id=actor,
    )
    assert updated.stock_new == 7
    assert log.delta == 5
    assert log.reason == "歸還良品"
    assert log.actor_id == actor


def test_adjust_negative_delta(repo, warehouse):
    item = _create_item(repo, warehouse, stock_new=10)
    updated, _ = repo.adjust(
        item.id,
        delta_kind=StockKind.NEW,
        delta=-3,
        reason="盤虧",
        actor_id=uuid4(),
    )
    assert updated.stock_new == 7


def test_adjust_insufficient_stock_raises_and_rolls_back(repo, warehouse):
    item = _create_item(repo, warehouse, stock_new=2)
    with pytest.raises(InsufficientStock, match="insufficient new stock"):
        repo.adjust(
            item.id,
            delta_kind=StockKind.NEW,
            delta=-5,
            reason="bad adjust",
            actor_id=uuid4(),
        )
    # 確認 stock 沒被動 + 沒留 log
    fresh = repo.get_item(item.id)
    assert fresh.stock_new == 2
    assert repo.list_adjustments(item.id) == []


def test_adjust_blank_reason_rejected(repo, warehouse):
    item = _create_item(repo, warehouse)
    with pytest.raises(StockAdjustmentError, match="non-empty reason"):
        repo.adjust(
            item.id,
            delta_kind=StockKind.NEW,
            delta=+1,
            reason="   ",
            actor_id=uuid4(),
        )


def test_adjust_unknown_item_raises(repo):
    with pytest.raises(StockAdjustmentError, match="not found"):
        repo.adjust(
            uuid4(),
            delta_kind=StockKind.NEW,
            delta=+1,
            reason="x",
            actor_id=uuid4(),
        )


def test_list_adjustments_ordered_desc(repo, warehouse):
    """Audit log 依時間反序排（最新在前）。
    用 sleep 隔 ms 級確保 occurred_at 嚴格遞增（生產場景天然秒級以上不會撞）。
    """
    import time

    item = _create_item(repo, warehouse, stock_new=10)
    actor = uuid4()
    repo.adjust(item.id, delta_kind=StockKind.NEW, delta=+1, reason="r1", actor_id=actor)
    time.sleep(0.005)
    repo.adjust(item.id, delta_kind=StockKind.NEW, delta=+2, reason="r2", actor_id=actor)
    time.sleep(0.005)
    repo.adjust(item.id, delta_kind=StockKind.NEW, delta=+3, reason="r3", actor_id=actor)
    logs = repo.list_adjustments(item.id)
    assert [l.reason for l in logs] == ["r3", "r2", "r1"]
    # 全部 3 筆都在
    assert {l.reason for l in logs} == {"r1", "r2", "r3"}


def test_adjust_used_kind(repo, warehouse):
    item = _create_item(repo, warehouse, stock_used=5)
    updated, _ = repo.adjust(
        item.id,
        delta_kind=StockKind.USED,
        delta=-2,
        reason="領出 used",
        actor_id=uuid4(),
    )
    assert updated.stock_used == 3
    assert updated.stock_new == 0


def test_adjust_repairing_kind(repo, warehouse):
    item = _create_item(repo, warehouse, stock_repairing=3)
    updated, _ = repo.adjust(
        item.id,
        delta_kind=StockKind.REPAIRING,
        delta=+2,
        reason="送修進場",
        actor_id=uuid4(),
    )
    assert updated.stock_repairing == 5
