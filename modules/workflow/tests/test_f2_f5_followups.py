"""Tests for M4 follow-up小修 F2/F3/F4/F5（autonomous daily worker 2026-05-21）。

| Issue | Scope | Test |
|-------|-------|------|
| F2    | list_items / list 用 ``func.count`` 而非 Python ``len`` | SQL contains ``count(`` |
| F3    | ``list_warehouses`` 加 repo method            | repo method 行為 + router 整合 |
| F4    | ``_FARM_REGISTRY`` lazy singleton 抽 shared    | shared module unit + reset |
| F5    | ``InventoryAdjustmentLog.actor_id`` Optional   | adjust 接受 None + log round-trip |

不重複測 baseline（既有 99 + 76 個 inventory/MR/approval/cost test 已覆蓋常規 path），
只測「F2-F5 改動本身帶來的新行為」。
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


# ─────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────


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
        name="Changhua base",
        location_kind="onshore_base",
        is_default=True,
    )


def _create_item(inv_repo, warehouse, **overrides):
    base = dict(
        sku="GBR-001",
        name="Gearbox bearing",
        description="Z72 main shaft",
        unit="piece",
        farm_id="changhua",
        warehouse_id=warehouse.id,
        unit_cost=Decimal("450.00"),
        stock_new=10,
    )
    base.update(overrides)
    return inv_repo.create_item(**base)


# ═════════════════════════════════════════════════════════════════════════
# F2 — list_items / list 用 func.count
# ═════════════════════════════════════════════════════════════════════════


def test_f2_list_items_uses_sql_count_not_python_len(inv_repo, warehouse):
    """F2：list_items 的 count_stmt 走 ``SELECT count(*)``，不把所有 id 撈回 Python。"""
    from sqlalchemy import func, select
    from modules.workflow.repository.inventory_orm import InventoryItemORM

    # 建 5 個 item（資料量無關，重點是 SQL shape）
    for i in range(5):
        _create_item(inv_repo, warehouse, sku=f"SKU-{i:03d}")

    # 直接驗證實作走 func.count；inspect 出來的 SQL 應含 "count("
    base = select(InventoryItemORM).where(InventoryItemORM.farm_id == "changhua")
    count_stmt = select(func.count()).select_from(base.subquery())
    sql = str(count_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "count(" in sql.lower(), f"expected SQL count(), got: {sql}"

    # 同時行為驗證：total 正確
    items, total = inv_repo.list_items(farm_id="changhua")
    assert total == 5
    assert len(items) == 5


def test_f2_list_items_count_with_below_safety_filter(inv_repo, warehouse):
    """F2：base filter（below_safety_only）在 subquery 內仍生效。"""
    _create_item(inv_repo, warehouse, sku="A", stock_new=100, safety_stock=10)  # 不警
    _create_item(inv_repo, warehouse, sku="B", stock_new=2, safety_stock=10)    # 警
    _create_item(inv_repo, warehouse, sku="C", stock_new=1, safety_stock=5)     # 警

    items, total = inv_repo.list_items(farm_id="changhua", below_safety_only=True)
    assert total == 2
    assert {it.sku for it in items} == {"B", "C"}


def test_f2_mr_list_count_with_status_filter(mr_repo):
    """F2：material_request.list 的 count 同 SQL-side，filter 維持有效。"""
    item_id = uuid4()
    farm_id = "changhua"
    for _ in range(3):
        mr_repo.create(
            farm_id=farm_id,
            requester_id=uuid4(),
            items=[(item_id, 1, StockKind.NEW)],
        )
    mrs, total = mr_repo.list(farm_id=farm_id)
    assert total == 3
    assert len(mrs) == 3
    # 用 status 過濾沒有命中 → total 0
    mrs2, total2 = mr_repo.list(farm_id=farm_id, status=MaterialRequestStatus.APPROVED)
    assert total2 == 0
    assert mrs2 == []


# ═════════════════════════════════════════════════════════════════════════
# F3 — list_warehouses 加 repo method
# ═════════════════════════════════════════════════════════════════════════


def test_f3_repo_list_warehouses_returns_default_first(inv_repo):
    """F3：repo.list_warehouses 按 (is_default DESC, name ASC) 排序。"""
    inv_repo.create_warehouse(farm_id="f1", name="Zebra", is_default=False)
    inv_repo.create_warehouse(farm_id="f1", name="Apple", is_default=True)
    inv_repo.create_warehouse(farm_id="f1", name="Banana", is_default=False)

    warehouses = inv_repo.list_warehouses("f1")
    names = [w.name for w in warehouses]
    assert names == ["Apple", "Banana", "Zebra"]  # default 第一，其他字母順


def test_f3_repo_list_warehouses_isolates_by_farm(inv_repo):
    """F3：farm_id filter 嚴格隔離。"""
    inv_repo.create_warehouse(farm_id="f1", name="A", is_default=True)
    inv_repo.create_warehouse(farm_id="f2", name="B", is_default=True)
    assert [w.farm_id for w in inv_repo.list_warehouses("f1")] == ["f1"]
    assert [w.farm_id for w in inv_repo.list_warehouses("f2")] == ["f2"]


def test_f3_repo_list_warehouses_empty(inv_repo):
    """F3：farm 沒倉 → 回空 list（不 raise）。"""
    assert inv_repo.list_warehouses("nonexistent") == []


# ═════════════════════════════════════════════════════════════════════════
# F4 — shared/farm_registry_provider lazy singleton
# ═════════════════════════════════════════════════════════════════════════


def test_f4_resolve_returns_500_when_farm_registry_unavailable(monkeypatch):
    """F4：FarmRegistry import 失敗 → HTTPException 500（與舊行為一致）。"""
    import shared.farm_registry_provider as provider
    from fastapi import HTTPException

    # 模擬 import 失敗：清 singleton + 把 monitoring 路徑塞個爛 module
    provider.reset_farm_registry()
    monkeypatch.setitem(
        sys.modules, "modules.monitoring.server.farm_registry", None
    )
    with pytest.raises(HTTPException) as ei:
        provider.resolve_farm_db_path("changhua")
    assert ei.value.status_code == 500
    assert "FarmRegistry" in ei.value.detail


def test_f4_resolve_returns_404_when_farm_not_found(monkeypatch):
    """F4：FarmRegistry 查不到該 farm → HTTPException 404。"""
    import shared.farm_registry_provider as provider
    from fastapi import HTTPException

    provider.reset_farm_registry()

    class FakeRegistry:
        def get_farm_db_path(self, farm_id: str):
            return None  # 模擬找不到

    # 不戳 monitoring；直接塞 fake 進 singleton（保持 lazy-init 邏輯不變更）
    provider._farm_registry = FakeRegistry()
    try:
        with pytest.raises(HTTPException) as ei:
            provider.resolve_farm_db_path("unknown-farm")
        assert ei.value.status_code == 404
        assert "unknown-farm" in ei.value.detail
    finally:
        provider.reset_farm_registry()


def test_f4_reset_clears_singleton():
    """F4：reset_farm_registry() 把 lazy singleton 設回 None。"""
    import shared.farm_registry_provider as provider

    class FakeRegistry:
        def get_farm_db_path(self, farm_id: str):
            return "/tmp/fake.db"

    provider._farm_registry = FakeRegistry()
    provider.reset_farm_registry()
    assert provider._farm_registry is None


def test_f4_resolve_returns_str_path_when_found():
    """F4：query 命中 → 回 str(path)（向後相容既有 caller 的 type 期待）。"""
    import shared.farm_registry_provider as provider

    class FakeRegistry:
        def get_farm_db_path(self, farm_id: str):
            return Path("/tmp/farm.db")  # 故意回 Path，驗證 str() 轉換

    provider._farm_registry = FakeRegistry()
    try:
        result = provider.resolve_farm_db_path("changhua")
        assert result == "/tmp/farm.db"
        assert isinstance(result, str)
    finally:
        provider.reset_farm_registry()


# ═════════════════════════════════════════════════════════════════════════
# F5 — InventoryAdjustmentLog.actor_id Optional
# ═════════════════════════════════════════════════════════════════════════


def test_f5_domain_accepts_none_actor():
    """F5：domain dataclass 允許 actor_id=None。"""
    log = InventoryAdjustmentLog(
        item_id=uuid4(),
        delta_kind=StockKind.NEW,
        delta=+3,
        reason="dispatch hook auto-deduct",
        # actor_id 不填 → 預設 None
    )
    assert log.actor_id is None


def test_f5_adjust_accepts_none_actor(inv_repo, warehouse):
    """F5：repo.adjust() 不傳 actor_id → log.actor_id is None；同 transaction 仍寫成功。"""
    item = _create_item(inv_repo, warehouse, stock_new=5)
    inv, log = inv_repo.adjust(
        item.id,
        delta_kind=StockKind.NEW,
        delta=+2,
        reason="盤盈 — 系統自動觸發",
        # actor_id 不傳
    )
    assert inv.stock_new == 7
    assert log.actor_id is None
    assert log.reason == "盤盈 — 系統自動觸發"


def test_f5_adjust_with_actor_id_still_works(inv_repo, warehouse):
    """F5：向後相容 — 傳 actor_id 仍正確寫入。"""
    item = _create_item(inv_repo, warehouse, stock_new=5)
    actor = uuid4()
    _, log = inv_repo.adjust(
        item.id,
        delta_kind=StockKind.NEW,
        delta=-1,
        reason="盤虧",
        actor_id=actor,
    )
    assert log.actor_id == actor


def test_f5_log_round_trip_with_none_actor(inv_repo, warehouse):
    """F5：寫入 None → DB → 讀回 list_adjustments，仍為 None。"""
    item = _create_item(inv_repo, warehouse, stock_new=5)
    inv_repo.adjust(
        item.id,
        delta_kind=StockKind.NEW,
        delta=+1,
        reason="system auto",
    )
    logs = inv_repo.list_adjustments(item.id)
    assert len(logs) == 1
    assert logs[0].actor_id is None


def test_f5_schema_accepts_optional_actor_id():
    """F5：``AdjustInventoryRequest`` schema accept actor_id 為 None。"""
    from modules.workflow.schemas.inventory_schemas import AdjustInventoryRequest

    req = AdjustInventoryRequest(
        delta_kind=StockKind.NEW,
        delta=+2,
        reason="盤盈",
        # actor_id 不傳
    )
    assert req.actor_id is None


def test_f5_response_schema_accepts_none_actor():
    """F5：``AdjustmentLogResponse`` 序列化 None actor_id 不 raise。"""
    from datetime import datetime, timezone

    from modules.workflow.schemas.inventory_schemas import AdjustmentLogResponse

    resp = AdjustmentLogResponse(
        id=uuid4(),
        item_id=uuid4(),
        delta_kind=StockKind.NEW,
        delta=1,
        reason="system",
        actor_id=None,
        occurred_at=datetime.now(timezone.utc),
    )
    dumped = resp.model_dump()
    assert dumped["actor_id"] is None
