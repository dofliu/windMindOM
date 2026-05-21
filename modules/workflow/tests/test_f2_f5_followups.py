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
    """F2：list_items 真的執行 ``SELECT count(*)`` SQL，不再 fetch 所有 row 進 Python。

    review should-fix #2：原版只驗 SQL pattern 等價性，不能擋日後改回 ``len()``。
    這版用 ``event.listen("before_cursor_execute")`` 攔 production code 真實
    送出的 SQL，斷言至少有一句 ``count(``。
    """
    from sqlalchemy import event

    for i in range(5):
        _create_item(inv_repo, warehouse, sku=f"SKU-{i:03d}")

    executed_sql: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        executed_sql.append(statement)

    event.listen(inv_repo._engine, "before_cursor_execute", _record)
    try:
        items, total = inv_repo.list_items(farm_id="changhua")
    finally:
        event.remove(inv_repo._engine, "before_cursor_execute", _record)

    assert total == 5
    assert len(items) == 5

    count_sqls = [s for s in executed_sql if "count(" in s.lower()]
    assert count_sqls, (
        f"expected production code to emit SQL count(*), only saw:\n"
        + "\n".join(executed_sql)
    )


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
    import modules.monitoring.server.farm_registry_provider as provider
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
    """F4：FarmRegistry.get_farm(farm_id) 回 None → HTTPException 404。

    注意：真實 ``FarmRegistry.get_farm_db_path()`` 永遠回 Path，靠 ``get_farm()``
    回 None 判斷 farm 是否存在（review should-fix #1）。
    """
    import modules.monitoring.server.farm_registry_provider as provider
    from fastapi import HTTPException

    provider.reset_farm_registry()

    class FakeRegistry:
        def get_farm(self, farm_id: str):
            return None  # 模擬找不到該 farm

        def get_farm_db_path(self, farm_id: str):
            return Path(f"/tmp/{farm_id}/wind_farm.db")  # 真實 FarmRegistry 一律回 Path

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
    import modules.monitoring.server.farm_registry_provider as provider

    class FakeRegistry:
        def get_farm_db_path(self, farm_id: str):
            return "/tmp/fake.db"

    provider._farm_registry = FakeRegistry()
    provider.reset_farm_registry()
    assert provider._farm_registry is None


def test_f4_resolve_returns_str_path_when_found():
    """F4：query 命中 → 回 str(path)（向後相容既有 caller 的 type 期待）。"""
    import modules.monitoring.server.farm_registry_provider as provider

    class FakeRegistry:
        def get_farm(self, farm_id: str):
            return object()  # 任何 non-None 物件代表 farm 存在

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


def test_f5_migration_converts_old_notnull_db_to_nullable(tmp_path):
    """F5 must-fix #2：既有 DB 帶 ``actor_id NOT NULL`` 的舊 schema，第二次 open
    觸發 idempotent migration，欄位變 nullable + 既有 rows 不丟。
    """
    import sqlite3

    from modules.workflow.repository.work_order_repository import (
        clear_engine_cache_for_test,
    )

    db_path = tmp_path / "legacy.db"
    # 模擬舊 schema（actor_id NOT NULL）
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE inventory_items (
            id VARCHAR(36) PRIMARY KEY,
            sku TEXT, name TEXT, description TEXT, unit TEXT,
            farm_id TEXT, warehouse_id TEXT,
            stock_new INTEGER, stock_used INTEGER, stock_repairing INTEGER,
            safety_stock INTEGER, unit_cost NUMERIC,
            last_received_at DATETIME, last_used_at DATETIME,
            created_at DATETIME, updated_at DATETIME
        );
        CREATE TABLE inventory_adjustment_log (
            id VARCHAR(36) PRIMARY KEY NOT NULL,
            item_id VARCHAR(36) NOT NULL,
            delta_kind VARCHAR(16) NOT NULL,
            delta INTEGER NOT NULL,
            reason VARCHAR(256) NOT NULL,
            actor_id VARCHAR(36) NOT NULL,  -- 舊 schema：NOT NULL
            note TEXT,
            occurred_at DATETIME NOT NULL
        );
        INSERT INTO inventory_adjustment_log
            VALUES ('11111111-1111-1111-1111-111111111111',
                    '22222222-2222-2222-2222-222222222222',
                    'new', 5, '盤盈',
                    '33333333-3333-3333-3333-333333333333',
                    NULL, '2026-05-20T10:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()

    # 驗 pre-migration：actor_id 為 NOT NULL
    conn = sqlite3.connect(db_path)
    info = conn.execute("PRAGMA table_info(inventory_adjustment_log)").fetchall()
    actor_col = next(row for row in info if row[1] == "actor_id")
    assert actor_col[3] == 1, "pre-migration: expected NOT NULL"
    conn.close()

    # Open repo → 應自動跑 migration
    clear_engine_cache_for_test()
    repo = get_inventory_repository(str(db_path))
    assert repo is not None

    # 驗 post-migration：actor_id 已是 nullable + 舊 row 仍在
    conn = sqlite3.connect(db_path)
    info = conn.execute("PRAGMA table_info(inventory_adjustment_log)").fetchall()
    actor_col = next(row for row in info if row[1] == "actor_id")
    assert actor_col[3] == 0, f"post-migration: expected nullable, got notnull={actor_col[3]}"

    # 既有資料完整保留
    rows = conn.execute(
        "SELECT id, actor_id, reason FROM inventory_adjustment_log"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "11111111-1111-1111-1111-111111111111"
    assert rows[0][1] == "33333333-3333-3333-3333-333333333333"
    assert rows[0][2] == "盤盈"

    # 現在可以插入 actor_id=NULL（不會 IntegrityError）
    conn.execute(
        "INSERT INTO inventory_adjustment_log "
        "(id, item_id, delta_kind, delta, reason, actor_id, occurred_at) "
        "VALUES (?, ?, 'new', 1, 'system auto', NULL, ?)",
        (
            "44444444-4444-4444-4444-444444444444",
            "22222222-2222-2222-2222-222222222222",
            "2026-05-21T10:00:00+00:00",
        ),
    )
    conn.commit()
    null_rows = conn.execute(
        "SELECT id FROM inventory_adjustment_log WHERE actor_id IS NULL"
    ).fetchall()
    assert len(null_rows) == 1
    conn.close()
    clear_engine_cache_for_test()


def test_f5_migration_idempotent_on_already_nullable(tmp_path):
    """F5 must-fix #2：對已是 nullable 的 DB（新建 / 第二次 open）migration 是 no-op。"""
    from modules.workflow.repository.work_order_repository import (
        clear_engine_cache_for_test,
    )

    clear_engine_cache_for_test()
    db_path = str(tmp_path / "fresh.db")
    # 第一次 open：create_all 直接建 nullable schema + migration no-op
    repo1 = get_inventory_repository(db_path)
    # 第二次 open（再 trigger 一次 migration）：仍應 no-op，不 raise
    clear_engine_cache_for_test()
    repo2 = get_inventory_repository(db_path)
    assert repo1 is not None and repo2 is not None
    clear_engine_cache_for_test()


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
