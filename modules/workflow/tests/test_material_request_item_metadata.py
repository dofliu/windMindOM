"""WMOM-20260518-01 regression — `MaterialRequestItem` sku/name/unit join。

驗證 `_to_domain` 從 `InventoryItemORM` 拉 `sku / name / unit` 三欄 metadata 補進
dataclass + schema response，給 frontend 顯示用。

覆蓋 5 個 path：
1. ``get(mr_id)`` 後 items 含 sku/name/unit
2. ``list()`` 後 items 含 sku/name/unit
3. ``transition('submit_for_approval')`` 後 response 仍含
4. ``dispatch_request()``（atomic stock + ledger 雙寫）後 response 含
5. cross-farm safety：farm A item 不該被 farm B MR 拉到（multi-tenant 防護）
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.workflow.domain.inventory import (
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

# 強制把 cost_ledger ORM 加進 Base.metadata，避免 create_all() 時 cost_ledger_entries 沒建
# （dispatch_request 內 lazy import 太晚 — schema 已 create 完）
from modules.cost.repository import cost_ledger as _cost_ledger  # noqa: F401


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
def item(inv_repo, warehouse):
    return inv_repo.create_item(
        sku="GBR-007",
        name="Gearbox bearing 7mm",
        description="Z72 main shaft bearing",
        unit="piece",
        farm_id="changhua",
        warehouse_id=warehouse.id,
        unit_cost=Decimal("450.00"),
        stock_new=20,
    )


# ─────────────────────────────────────────────────────────────────────────
# 1. get() 後 items 含 sku/name/unit
# ─────────────────────────────────────────────────────────────────────────


def test_get_populates_item_metadata(mr_repo, item):
    """`_to_domain` 透過 viewonly relationship 拉 sku/name/unit 進 dataclass。"""
    requester = uuid4()
    created = mr_repo.create(
        farm_id="changhua",
        requester_id=requester,
        items=[(item.id, 3, StockKind.NEW)],
    )

    fetched = mr_repo.get(created.id)
    assert fetched is not None
    assert len(fetched.items) == 1
    line = fetched.items[0]
    assert line.sku == "GBR-007"
    assert line.name == "Gearbox bearing 7mm"
    assert line.unit == "piece"


# ─────────────────────────────────────────────────────────────────────────
# 2. list() 後 items 含 sku/name/unit
# ─────────────────────────────────────────────────────────────────────────


def test_list_populates_item_metadata(mr_repo, item):
    requester = uuid4()
    mr_repo.create(
        farm_id="changhua",
        requester_id=requester,
        items=[(item.id, 2, StockKind.NEW)],
    )
    items, total = mr_repo.list(farm_id="changhua", limit=10, offset=0)
    assert total == 1
    assert len(items) == 1
    line = items[0].items[0]
    assert line.sku == "GBR-007"
    assert line.name == "Gearbox bearing 7mm"
    assert line.unit == "piece"


# ─────────────────────────────────────────────────────────────────────────
# 3. transition() 後 metadata 仍帶
# ─────────────────────────────────────────────────────────────────────────


def test_metadata_persists_after_submit_transition(mr_repo, item):
    requester = uuid4()
    mr = mr_repo.create(
        farm_id="changhua",
        requester_id=requester,
        items=[(item.id, 4, StockKind.NEW)],
    )
    transitioned = mr_repo.transition(
        mr.id, "submit_for_approval", actor_id=requester
    )
    assert transitioned.status is MaterialRequestStatus.AWAITING_APPROVAL
    line = transitioned.items[0]
    assert line.sku == "GBR-007"
    assert line.name == "Gearbox bearing 7mm"
    assert line.unit == "piece"


# ─────────────────────────────────────────────────────────────────────────
# 4. dispatch_request() 後 metadata 仍帶（atomic 雙寫 path）
# ─────────────────────────────────────────────────────────────────────────


def test_metadata_after_cancel_transition(mr_repo, item):
    """cancel transition 走 _to_domain；metadata 三欄應仍帶（防 partial load regression）。"""
    requester = uuid4()
    mr = mr_repo.create(
        farm_id="changhua",
        requester_id=requester,
        items=[(item.id, 1, StockKind.NEW)],
    )
    cancelled = mr_repo.transition(
        mr.id,
        "cancel",
        actor_id=requester,
        cancel_reason="duplicate request",
    )
    assert cancelled.status is MaterialRequestStatus.CANCELLED
    line = cancelled.items[0]
    assert line.sku == "GBR-007"
    assert line.name == "Gearbox bearing 7mm"
    assert line.unit == "piece"


def test_metadata_after_add_return(mr_repo, inv_repo, item):
    """add_return 不回 MaterialRequest，但後續 get(mr) 仍經 _to_domain，metadata 應帶。"""
    from modules.workflow.domain.inventory import ReturnReason

    requester = uuid4()
    mr = mr_repo.create(
        farm_id="changhua",
        requester_id=requester,
        items=[(item.id, 5, StockKind.NEW)],
    )
    # 走 lifecycle 到 RECEIVED 才有意義建退料記錄
    mr_repo.transition(mr.id, "submit_for_approval", actor_id=requester)
    mr_repo.transition(mr.id, "approve_all")
    mr_repo.dispatch_request(mr.id, actor_id=requester)
    # actual=4 留 1 件可退（WMOM-20260519-01 guard：max=estimated-actual-returned=5-4-0=1）
    received = mr_repo.transition(
        mr.id,
        "receive",
        actor_id=requester,
        actual_quantities={mr.items[0].id: 4},
    )
    assert received.status is MaterialRequestStatus.RECEIVED
    # 建退料記錄（加回 stock）
    mr_repo.add_return(
        request_id=mr.id,
        item_id=item.id,
        qty=1,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW,
        returned_by=requester,
        note="surplus",
    )
    # 後續 get 仍經 _to_domain，metadata 應帶
    refetched = mr_repo.get(mr.id)
    assert refetched is not None
    line = refetched.items[0]
    assert line.sku == "GBR-007"
    assert line.name == "Gearbox bearing 7mm"
    assert line.unit == "piece"


def test_metadata_after_dispatch_request(mr_repo, inv_repo, item):
    """dispatch 走 atomic stock + ledger，response 仍經 `_to_domain`，metadata 不丟。"""
    requester = uuid4()
    mr = mr_repo.create(
        farm_id="changhua",
        requester_id=requester,
        items=[(item.id, 5, StockKind.NEW)],
    )
    # DRAFT → AWAITING_APPROVAL → APPROVED（沿用既有 dispatch test 路徑）
    mr_repo.transition(mr.id, "submit_for_approval", actor_id=requester)
    mr_repo.transition(mr.id, "approve_all")

    dispatched = mr_repo.dispatch_request(mr.id, actor_id=requester)
    assert dispatched.status is MaterialRequestStatus.DISPATCHED
    line = dispatched.items[0]
    assert line.sku == "GBR-007"
    assert line.name == "Gearbox bearing 7mm"
    assert line.unit == "piece"


# ─────────────────────────────────────────────────────────────────────────
# 5. cross-farm safety — farm B MR 不應誤拉到 farm A item metadata
# ─────────────────────────────────────────────────────────────────────────


def test_cross_farm_metadata_isolation(inv_repo, mr_repo, warehouse):
    """同 SQLite 兩 farm — relationship 走 item_id FK，不會混淆 farm。"""
    item_a = inv_repo.create_item(
        sku="ALPHA-1",
        name="Alpha part",
        description="farm A part",
        unit="kg",
        farm_id="changhua",
        warehouse_id=warehouse.id,
        unit_cost=Decimal("100.00"),
        stock_new=5,
    )
    # 另建 farm B + warehouse + 同名 sku
    wh_b = inv_repo.create_warehouse(
        farm_id="yunlin", name="Yunlin base", is_default=True
    )
    item_b = inv_repo.create_item(
        sku="ALPHA-1",  # 同 sku 不同 farm（unique constraint 是 farm_id+sku）
        name="Beta part",
        description="farm B part",
        unit="set",
        farm_id="yunlin",
        warehouse_id=wh_b.id,
        unit_cost=Decimal("200.00"),
        stock_new=3,
    )
    requester = uuid4()
    mr_a = mr_repo.create(
        farm_id="changhua",
        requester_id=requester,
        items=[(item_a.id, 1, StockKind.NEW)],
    )
    mr_b = mr_repo.create(
        farm_id="yunlin",
        requester_id=requester,
        items=[(item_b.id, 1, StockKind.NEW)],
    )
    fetched_a = mr_repo.get(mr_a.id)
    fetched_b = mr_repo.get(mr_b.id)
    assert fetched_a is not None
    assert fetched_b is not None
    assert fetched_a.items[0].name == "Alpha part"
    assert fetched_a.items[0].unit == "kg"
    assert fetched_b.items[0].name == "Beta part"
    assert fetched_b.items[0].unit == "set"
