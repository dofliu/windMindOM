"""Follow-up tests — WMOM-20260509-F2 / -F3 / -F5（cleanup batch 2026-05-21）。

涵蓋：
- **F2** ``InventoryRepository.list_items`` / ``MaterialRequestRepository.list``
  改用 SQL ``func.count()`` — total 結果不變、performance smoke。
- **F3** ``InventoryRepository.list_warehouses`` 新 method — ``is_default`` 排在前 + 名稱 ASC。
- **F5** ``InventoryAdjustmentLog.actor_id`` 改 ``Optional[UUID]`` — 系統 adjust 走 None
  路徑不再被迫塞 fake UUID。
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
    InventoryAdjustmentLog,
    MaterialRequestStatus,
    StockKind,
)
from modules.workflow.repository import (
    InventoryRepository,
    MaterialRequestRepository,
    get_inventory_repository,
    get_material_request_repository,
)
from modules.workflow.repository.work_order_repository import (
    clear_engine_cache_for_test,
)


@pytest.fixture
def inv_repo(tmp_path) -> InventoryRepository:
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")
    yield get_inventory_repository(db_path)
    clear_engine_cache_for_test()


@pytest.fixture
def mr_repo(tmp_path) -> MaterialRequestRepository:
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")
    yield get_material_request_repository(db_path)
    clear_engine_cache_for_test()


@pytest.fixture
def warehouse(inv_repo):
    return inv_repo.create_warehouse(
        farm_id="changhua",
        name="Default Warehouse",
        location_kind="onshore_base",
        is_default=True,
    )


def _seed_items(repo: InventoryRepository, warehouse, count: int) -> list:
    items = []
    for i in range(count):
        items.append(
            repo.create_item(
                sku=f"SKU-{i:03d}",
                name=f"Item {i}",
                description=f"Test item {i}",
                unit="piece",
                farm_id="changhua",
                warehouse_id=warehouse.id,
                unit_cost=Decimal("100.00"),
            )
        )
    return items


# ─────────────────────────────────────────────────────────────────────────
# F2 — SQL func.count() instead of Python len()
# ─────────────────────────────────────────────────────────────────────────


def test_f2_list_items_total_matches_sql_count(inv_repo, warehouse):
    """F2：建 7 個料件 + 分頁查 limit=3 → total 應為 7（不是 limit 後筆數）。"""
    _seed_items(inv_repo, warehouse, count=7)

    items, total = inv_repo.list_items(farm_id="changhua", limit=3, offset=0)

    assert total == 7
    assert len(items) == 3


def test_f2_list_items_total_empty(inv_repo, warehouse):
    """F2：空表 → total=0，不丟 exception。"""
    items, total = inv_repo.list_items(farm_id="changhua")

    assert total == 0
    assert items == []


def test_f2_mr_list_total_matches_sql_count(mr_repo, inv_repo, warehouse):
    """F2 對 MaterialRequest list — 建 5 個 MR + limit=2 → total=5。"""
    item = inv_repo.create_item(
        sku="X1",
        name="X1",
        description="",
        unit="piece",
        farm_id="changhua",
        warehouse_id=warehouse.id,
        unit_cost=Decimal("100.00"),
        stock_new=99,
    )
    actor = uuid4()
    for _ in range(5):
        mr_repo.create(
            farm_id="changhua",
            requester_id=actor,
            work_order_id=uuid4(),
            items=[(item.id, 1, StockKind.NEW)],
        )

    mrs, total = mr_repo.list(farm_id="changhua", limit=2, offset=0)

    assert total == 5
    assert len(mrs) == 2


# ─────────────────────────────────────────────────────────────────────────
# F3 — InventoryRepository.list_warehouses repo method
# ─────────────────────────────────────────────────────────────────────────


def test_f3_list_warehouses_default_first(inv_repo):
    """F3：``is_default=True`` 排在前；其餘照 name ASC。"""
    inv_repo.create_warehouse(farm_id="f1", name="Zeta", is_default=False)
    inv_repo.create_warehouse(farm_id="f1", name="Alpha", is_default=False)
    inv_repo.create_warehouse(farm_id="f1", name="Main", is_default=True)

    ws = inv_repo.list_warehouses("f1")

    assert [w.name for w in ws] == ["Main", "Alpha", "Zeta"]


def test_f3_list_warehouses_other_farm_excluded(inv_repo):
    """F3：filter farm_id — 不串到別 farm 的倉。"""
    inv_repo.create_warehouse(farm_id="f1", name="A", is_default=True)
    inv_repo.create_warehouse(farm_id="f2", name="B", is_default=True)

    f1 = inv_repo.list_warehouses("f1")
    f2 = inv_repo.list_warehouses("f2")

    assert len(f1) == 1
    assert f1[0].name == "A"
    assert len(f2) == 1
    assert f2[0].name == "B"


def test_f3_list_warehouses_empty(inv_repo):
    """F3：farm 沒倉 → 空 list 而非 raise。"""
    assert inv_repo.list_warehouses("nonexistent") == []


# ─────────────────────────────────────────────────────────────────────────
# F5 — actor_id Optional
# ─────────────────────────────────────────────────────────────────────────


def test_f5_domain_adjustment_log_accepts_none_actor():
    """F5：dataclass 直接 instantiate 不傳 actor_id，預設 None。"""
    log = InventoryAdjustmentLog(
        item_id=uuid4(),
        delta_kind=StockKind.NEW,
        delta=+3,
        reason="系統自動沖銷",
    )

    assert log.actor_id is None


def test_f5_repository_adjust_with_actor(inv_repo, warehouse):
    """F5：傳 actor_id → 一律以該 UUID 寫 audit log（既有行為不變）。"""
    item = _seed_items(inv_repo, warehouse, count=1)[0]
    # 先進 5 piece 才能 adjust
    inv_repo.adjust(
        item.id,
        delta_kind=StockKind.NEW,
        delta=+5,
        reason="initial",
        actor_id=uuid4(),
    )
    actor = uuid4()

    _item, log = inv_repo.adjust(
        item.id,
        delta_kind=StockKind.NEW,
        delta=+1,
        reason="盤盈",
        actor_id=actor,
    )

    assert log.actor_id == actor


def test_f5_repository_adjust_without_actor(inv_repo, warehouse):
    """F5：不傳 actor_id（系統 adjust path）→ ORM 寫 NULL；round-trip 回 None。"""
    item = _seed_items(inv_repo, warehouse, count=1)[0]

    _item, log = inv_repo.adjust(
        item.id,
        delta_kind=StockKind.NEW,
        delta=+1,
        reason="system auto-correct",
        # actor_id 省略
    )

    assert log.actor_id is None

    # round-trip 讀回也是 None（驗 ORM column nullable + _log_to_domain 分支）
    logs = inv_repo.list_adjustments(item.id)
    assert len(logs) == 1
    assert logs[0].actor_id is None
    assert logs[0].reason == "system auto-correct"


def test_f5_mixed_actor_none_and_uuid(inv_repo, warehouse):
    """F5：混合 actor_id（有人簽 + 系統 adjust）→ list 正確分辨。"""
    item = _seed_items(inv_repo, warehouse, count=1)[0]
    human_actor = uuid4()

    inv_repo.adjust(
        item.id, delta_kind=StockKind.NEW, delta=+10,
        reason="dispatch", actor_id=human_actor,
    )
    inv_repo.adjust(
        item.id, delta_kind=StockKind.NEW, delta=-2,
        reason="system rollback",
    )

    logs = inv_repo.list_adjustments(item.id)
    by_reason = {lg.reason: lg.actor_id for lg in logs}

    assert by_reason["dispatch"] == human_actor
    assert by_reason["system rollback"] is None
