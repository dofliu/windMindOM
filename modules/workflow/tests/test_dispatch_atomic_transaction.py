"""**M4 核心測試** — `dispatch_request()` atomic 雙寫交易（WMOM-20260509-02 / DN-03 §2.3）。

Acceptance（ISSUES.md A2）：
- ``dispatch_request`` 在故障注入（mid-transaction raise）下 庫存 + ledger 同時 rollback
- SELECT FOR UPDATE 在 SQLite WAL 下行為（同寫鎖序）
- insufficient_stock / state mismatch / invalid lifecycle 都正確擋
"""

from __future__ import annotations

import sys
import threading
import time
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.cost.repository.cost_ledger import (
    CostLedgerCategory,
    CostLedgerEntryORM,
    CostLedgerStatus,
)
from modules.workflow.domain import InvalidTransition
from modules.workflow.domain.inventory import (
    MaterialRequestStatus,
    StockKind,
)
from modules.workflow.repository import (
    InsufficientStock,
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
def db_path(tmp_path) -> str:
    return str(tmp_path / "wind_farm.db")


@pytest.fixture
def repos(db_path):
    """為每個 test 開一份新 DB；engine cache 在 yield 後清。"""
    clear_engine_cache_for_test()
    inv = get_inventory_repository(db_path)
    mr = get_material_request_repository(db_path)
    yield inv, mr
    clear_engine_cache_for_test()


def _setup_approved_mr(
    inv_repo: InventoryRepository,
    mr_repo: MaterialRequestRepository,
    *,
    initial_stock: int = 10,
    estimated_qty: int = 2,
    unit_cost: Decimal = Decimal("450.00"),
) -> tuple[UUID, UUID]:
    """Helper：建一個 APPROVED 狀態的 MR + 對應 inventory item。回傳 (mr_id, item_id)。"""
    wh = inv_repo.create_warehouse(farm_id="f", name="W", is_default=True)
    item = inv_repo.create_item(
        sku="X-1", name="x", description="x", unit="piece",
        farm_id="f", warehouse_id=wh.id, unit_cost=unit_cost,
        stock_new=initial_stock,
    )
    mr = mr_repo.create(
        farm_id="f", requester_id=uuid4(),
        items=[(item.id, estimated_qty, StockKind.NEW)],
    )
    mr_repo.transition(mr.id, "submit_for_approval")
    mr_repo.transition(mr.id, "approve_all")
    return mr.id, item.id


def _count_ledger_entries(mr_repo: MaterialRequestRepository) -> int:
    """直接 raw query 算 ledger entry 數量（避開沒有 ledger query API 的限制）。"""
    with mr_repo._sessionmaker() as sess:
        return len(sess.execute(select(CostLedgerEntryORM)).scalars().all())


def _get_ledger_entries(mr_repo: MaterialRequestRepository) -> list[CostLedgerEntryORM]:
    with mr_repo._sessionmaker() as sess:
        return list(sess.execute(select(CostLedgerEntryORM)).scalars().all())


# ─────────────────────────────────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────────────────────────────────


def test_dispatch_happy_path_atomic_stock_and_ledger(repos):
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_approved_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=2,
        unit_cost=Decimal("450.00"),
    )

    # initial state
    assert _count_ledger_entries(mr_repo) == 0

    updated = mr_repo.dispatch_request(mr_id)

    # MR status / timestamps
    assert updated.status is MaterialRequestStatus.DISPATCHED
    assert updated.dispatched_at is not None

    # Stock 扣 2
    item = inv_repo.get_item(item_id)
    assert item.stock_new == 8

    # Ledger 寫一筆 estimated
    entries = _get_ledger_entries(mr_repo)
    assert len(entries) == 1
    e = entries[0]
    assert e.category == CostLedgerCategory.MATERIAL.value
    assert e.status == CostLedgerStatus.ESTIMATED.value
    assert Decimal(str(e.amount)) == Decimal("900.00")  # 2 × 450
    assert e.source_event_id == str(mr_id)
    assert e.source_type == "material_request"


def test_dispatch_happy_path_multiple_items(repos):
    inv_repo, mr_repo = repos
    wh = inv_repo.create_warehouse(farm_id="f", name="W", is_default=True)
    a = inv_repo.create_item(
        sku="A", name="a", description="a", unit="piece",
        farm_id="f", warehouse_id=wh.id, unit_cost=Decimal("100.00"),
        stock_new=5,
    )
    b = inv_repo.create_item(
        sku="B", name="b", description="b", unit="piece",
        farm_id="f", warehouse_id=wh.id, unit_cost=Decimal("250.00"),
        stock_new=3,
    )
    mr = mr_repo.create(
        farm_id="f", requester_id=uuid4(),
        items=[(a.id, 2, StockKind.NEW), (b.id, 1, StockKind.NEW)],
    )
    mr_repo.transition(mr.id, "submit_for_approval")
    mr_repo.transition(mr.id, "approve_all")

    mr_repo.dispatch_request(mr.id)

    assert inv_repo.get_item(a.id).stock_new == 3
    assert inv_repo.get_item(b.id).stock_new == 2
    assert _count_ledger_entries(mr_repo) == 2


# ─────────────────────────────────────────────────────────────────────────
# State mismatch
# ─────────────────────────────────────────────────────────────────────────


def test_dispatch_from_draft_rejected_no_side_effect(repos):
    """DRAFT 不能 dispatch — stock / ledger 全不動。"""
    inv_repo, mr_repo = repos
    wh = inv_repo.create_warehouse(farm_id="f", name="W", is_default=True)
    item = inv_repo.create_item(
        sku="A", name="a", description="a", unit="piece",
        farm_id="f", warehouse_id=wh.id, unit_cost=Decimal("100.00"),
        stock_new=5,
    )
    mr = mr_repo.create(
        farm_id="f", requester_id=uuid4(),
        items=[(item.id, 2, StockKind.NEW)],
    )

    with pytest.raises(InvalidTransition, match="must be APPROVED"):
        mr_repo.dispatch_request(mr.id)

    assert inv_repo.get_item(item.id).stock_new == 5
    assert _count_ledger_entries(mr_repo) == 0
    assert mr_repo.get(mr.id).status is MaterialRequestStatus.DRAFT


def test_dispatch_from_dispatched_rejected(repos):
    """已 DISPATCHED 不能再 dispatch — 防止 double-dispatch。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_approved_mr(inv_repo, mr_repo, initial_stock=10, estimated_qty=2)
    mr_repo.dispatch_request(mr_id)
    # second dispatch attempt
    with pytest.raises(InvalidTransition, match="must be APPROVED"):
        mr_repo.dispatch_request(mr_id)
    # stock 仍只扣一次（10 - 2 = 8）
    assert inv_repo.get_item(item_id).stock_new == 8
    # ledger 仍只一筆
    assert _count_ledger_entries(mr_repo) == 1


def test_dispatch_unknown_id(repos):
    inv_repo, mr_repo = repos
    with pytest.raises(LookupError):
        mr_repo.dispatch_request(uuid4())


# ─────────────────────────────────────────────────────────────────────────
# Insufficient stock — 全 rollback
# ─────────────────────────────────────────────────────────────────────────


def test_dispatch_insufficient_stock_full_rollback(repos):
    """請領量 > stock → InsufficientStock + stock / ledger / status 全不動。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_approved_mr(
        inv_repo, mr_repo, initial_stock=1, estimated_qty=5
    )

    with pytest.raises(InsufficientStock):
        mr_repo.dispatch_request(mr_id)

    assert inv_repo.get_item(item_id).stock_new == 1
    assert _count_ledger_entries(mr_repo) == 0
    assert mr_repo.get(mr_id).status is MaterialRequestStatus.APPROVED


def test_dispatch_insufficient_on_second_item_first_rolled_back(repos):
    """多 item dispatch — 第二個 stock 不足，第一個的扣帳必須 rollback。"""
    inv_repo, mr_repo = repos
    wh = inv_repo.create_warehouse(farm_id="f", name="W", is_default=True)
    a = inv_repo.create_item(
        sku="A", name="a", description="a", unit="piece",
        farm_id="f", warehouse_id=wh.id, unit_cost=Decimal("100.00"),
        stock_new=10,
    )
    b = inv_repo.create_item(
        sku="B", name="b", description="b", unit="piece",
        farm_id="f", warehouse_id=wh.id, unit_cost=Decimal("250.00"),
        stock_new=1,  # 不足
    )
    mr = mr_repo.create(
        farm_id="f", requester_id=uuid4(),
        items=[(a.id, 2, StockKind.NEW), (b.id, 5, StockKind.NEW)],
    )
    mr_repo.transition(mr.id, "submit_for_approval")
    mr_repo.transition(mr.id, "approve_all")

    with pytest.raises(InsufficientStock):
        mr_repo.dispatch_request(mr.id)

    # A 沒被扣（rollback 了），B 也沒動
    assert inv_repo.get_item(a.id).stock_new == 10
    assert inv_repo.get_item(b.id).stock_new == 1
    assert _count_ledger_entries(mr_repo) == 0
    assert mr_repo.get(mr.id).status is MaterialRequestStatus.APPROVED


# ─────────────────────────────────────────────────────────────────────────
# Mid-transaction failure（mock cost_ledger.insert raise）
# ─────────────────────────────────────────────────────────────────────────


def test_dispatch_ledger_insert_fails_full_rollback(repos):
    """mid-transaction 故障：mock cost ledger insert raise → stock 回原值 + 沒 ledger entry。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_approved_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=3
    )

    # patch insert_in_session 讓它在 dispatch transaction 中段 raise
    # Note: A5 改成 lazy import 後要 patch 在原 module（cost_ledger），不在 mr_repo
    target = "modules.cost.repository.cost_ledger.insert_in_session"
    with patch(target, side_effect=RuntimeError("synthetic ledger failure")):
        with pytest.raises(RuntimeError, match="synthetic ledger failure"):
            mr_repo.dispatch_request(mr_id)

    # 全部不變
    assert inv_repo.get_item(item_id).stock_new == 10
    assert _count_ledger_entries(mr_repo) == 0
    assert mr_repo.get(mr_id).status is MaterialRequestStatus.APPROVED


def test_dispatch_apply_stock_fails_full_rollback(repos):
    """mock apply_stock_delta_in_session raise → MR status + ledger 都不動。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_approved_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=2
    )

    target = "modules.workflow.repository.material_request_repository.apply_stock_delta_in_session"
    with patch(target, side_effect=RuntimeError("synthetic stock failure")):
        with pytest.raises(RuntimeError, match="synthetic stock failure"):
            mr_repo.dispatch_request(mr_id)

    assert inv_repo.get_item(item_id).stock_new == 10
    assert _count_ledger_entries(mr_repo) == 0
    assert mr_repo.get(mr_id).status is MaterialRequestStatus.APPROVED


# ─────────────────────────────────────────────────────────────────────────
# Round-trip：dispatch + 讀回
# ─────────────────────────────────────────────────────────────────────────


def test_dispatch_round_trip_get_after_commit(repos):
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_approved_mr(inv_repo, mr_repo, initial_stock=10, estimated_qty=2)
    mr_repo.dispatch_request(mr_id)
    fresh = mr_repo.get(mr_id)
    assert fresh.status is MaterialRequestStatus.DISPATCHED
    assert fresh.dispatched_at is not None
    # items 仍存
    assert len(fresh.items) == 1
    assert fresh.items[0].estimated_qty == 2
    # actual_qty 還沒填（要等 receive transition）
    assert fresh.items[0].actual_qty is None


def test_dispatch_then_receive_writes_actual_qty(repos):
    """完整 dispatch → receive 流程，actual_qty 寫入 items。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_approved_mr(inv_repo, mr_repo, initial_stock=10, estimated_qty=3)
    mr_repo.dispatch_request(mr_id)

    # receive：actual = 2（用了 2 個，1 個之後退）
    mr = mr_repo.get(mr_id)
    actual_quantities = {mr.items[0].id: 2}
    updated = mr_repo.transition(
        mr_id, "receive", actual_quantities=actual_quantities
    )

    assert updated.status is MaterialRequestStatus.RECEIVED
    assert updated.items[0].actual_qty == 2


# ─────────────────────────────────────────────────────────────────────────
# Concurrency（SQLite serialized；確認 SELECT FOR UPDATE 在 multi-thread 下行為）
# ─────────────────────────────────────────────────────────────────────────


def test_two_sequential_dispatches_different_mrs(repos):
    """兩張不同 MR 對同一 item — sequential 完成，最終 stock 正確。"""
    inv_repo, mr_repo = repos
    wh = inv_repo.create_warehouse(farm_id="f", name="W", is_default=True)
    item = inv_repo.create_item(
        sku="A", name="a", description="a", unit="piece",
        farm_id="f", warehouse_id=wh.id, unit_cost=Decimal("100.00"),
        stock_new=10,
    )
    mr1 = mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 3, StockKind.NEW)])
    mr2 = mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 2, StockKind.NEW)])
    for mr in (mr1, mr2):
        mr_repo.transition(mr.id, "submit_for_approval")
        mr_repo.transition(mr.id, "approve_all")

    mr_repo.dispatch_request(mr1.id)
    mr_repo.dispatch_request(mr2.id)

    assert inv_repo.get_item(item.id).stock_new == 5  # 10 - 3 - 2
    assert _count_ledger_entries(mr_repo) == 2


def test_concurrent_dispatch_same_item_serialized_correctly(repos):
    """兩個 thread 同時 dispatch 同 item — SQLite WAL + busy_timeout 序列化執行，
    結果 stock 正確（不會 double-spend）。

    注意：SQLite 的 ``with_for_update()`` 是 no-op（語法支援但不真做 row-lock），
    本 test 主要驗 SQLite 自己的 BEGIN IMMEDIATE 寫入序列化讓我們得到正確答案；
    PostgreSQL 部署時 SELECT FOR UPDATE 才真的 row-lock。
    """
    inv_repo, mr_repo = repos
    wh = inv_repo.create_warehouse(farm_id="f", name="W", is_default=True)
    item = inv_repo.create_item(
        sku="A", name="a", description="a", unit="piece",
        farm_id="f", warehouse_id=wh.id, unit_cost=Decimal("100.00"),
        stock_new=10,
    )
    mr1 = mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 3, StockKind.NEW)])
    mr2 = mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 4, StockKind.NEW)])
    for mr in (mr1, mr2):
        mr_repo.transition(mr.id, "submit_for_approval")
        mr_repo.transition(mr.id, "approve_all")

    errors: list[Exception] = []

    def _do_dispatch(mr_id):
        try:
            mr_repo.dispatch_request(mr_id)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    t1 = threading.Thread(target=_do_dispatch, args=(mr1.id,))
    t2 = threading.Thread(target=_do_dispatch, args=(mr2.id,))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    # 最終結果：兩個 dispatch 都成功（10 足夠扣 3 + 4），stock = 3
    assert errors == [], f"unexpected errors: {errors}"
    assert inv_repo.get_item(item.id).stock_new == 3
    assert _count_ledger_entries(mr_repo) == 2


def test_concurrent_dispatch_one_loses_when_stock_short(repos):
    """兩 thread 同 dispatch，stock 不夠兩個都成功 — 至少一個 InsufficientStock。"""
    inv_repo, mr_repo = repos
    wh = inv_repo.create_warehouse(farm_id="f", name="W", is_default=True)
    item = inv_repo.create_item(
        sku="A", name="a", description="a", unit="piece",
        farm_id="f", warehouse_id=wh.id, unit_cost=Decimal("100.00"),
        stock_new=5,  # 只夠一個
    )
    mr1 = mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 4, StockKind.NEW)])
    mr2 = mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 4, StockKind.NEW)])
    for mr in (mr1, mr2):
        mr_repo.transition(mr.id, "submit_for_approval")
        mr_repo.transition(mr.id, "approve_all")

    results: list[tuple[str, Exception | None]] = []

    def _do_dispatch(label, mr_id):
        try:
            mr_repo.dispatch_request(mr_id)
            results.append((label, None))
        except Exception as e:  # noqa: BLE001
            results.append((label, e))

    t1 = threading.Thread(target=_do_dispatch, args=("mr1", mr1.id))
    t2 = threading.Thread(target=_do_dispatch, args=("mr2", mr2.id))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    success = [r for r in results if r[1] is None]
    failure = [r for r in results if isinstance(r[1], InsufficientStock)]
    # 必有 1 成功 + 1 InsufficientStock（不會兩個都成功）
    assert len(success) == 1, f"results={results}"
    assert len(failure) == 1, f"results={results}"
    # 最終 stock = 5 - 4 = 1
    assert inv_repo.get_item(item.id).stock_new == 1
    assert _count_ledger_entries(mr_repo) == 1


def test_dispatch_no_lost_update_under_forced_interleave(repos):
    """**WMOM-20260525-01 regression**：用 barrier 強制兩 thread 在「各自讀到 stock
    之後、任一方 commit 之前」交會，逼出 lost-update window。

    *舊（deferred）行為*：兩 thread 的 ``BEGIN`` 不取鎖、``SELECT`` 也不取鎖 → 兩邊
    都讀到 stock=10、都抵達 barrier → 放行後各自寫回 → 後寫者覆蓋前者 → 庫存只扣
    一筆但 ledger 兩筆（``stock_new`` 變 7 或 6 而非 3）。本 test 會抓到。

    *新（``BEGIN IMMEDIATE``）行為*：第二個 thread 在交易起手即卡在 RESERVED lock，
    根本到不了 barrier；第一個 thread 的 ``barrier.wait`` 逾時（``BrokenBarrierError``）
    後獨自 commit 放鎖，第二個 thread 才接續、讀到最新 stock=7 再扣 4 → 最終 stock=3。

    故本 test 在修復前必失敗、修復後必過，且不依賴 thread 排程運氣。
    """
    import modules.cost.repository.cost_ledger as _cost_ledger_mod

    inv_repo, mr_repo = repos
    wh = inv_repo.create_warehouse(farm_id="f", name="W", is_default=True)
    item = inv_repo.create_item(
        sku="A", name="a", description="a", unit="piece",
        farm_id="f", warehouse_id=wh.id, unit_cost=Decimal("100.00"),
        stock_new=10,
    )
    mr1 = mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 3, StockKind.NEW)])
    mr2 = mr_repo.create(farm_id="f", requester_id=uuid4(), items=[(item.id, 4, StockKind.NEW)])
    for mr in (mr1, mr2):
        mr_repo.transition(mr.id, "submit_for_approval")
        mr_repo.transition(mr.id, "approve_all")

    # barrier 設在 stock 讀取（apply_stock_delta）之後、commit 之前的 ledger insert，
    # 強制兩 thread 在 lost-update window 內交會。逾時後放行讓修復路徑不會 deadlock。
    barrier = threading.Barrier(2)
    real_insert = _cost_ledger_mod.insert_in_session

    def _insert_with_barrier(sess, entry):
        try:
            barrier.wait(timeout=2.0)
        except threading.BrokenBarrierError:
            pass
        return real_insert(sess, entry)

    errors: list[Exception] = []

    def _do_dispatch(mr_id):
        try:
            mr_repo.dispatch_request(mr_id)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    with patch.object(_cost_ledger_mod, "insert_in_session", _insert_with_barrier):
        t1 = threading.Thread(target=_do_dispatch, args=(mr1.id,))
        t2 = threading.Thread(target=_do_dispatch, args=(mr2.id,))
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

    # join 逾時不丟例外，故先確認兩 thread 確實結束 — 否則後面 assert 讀到的是
    # 部分 commit 的中間值、errors 也可能尚未 append（假性通過）。
    assert not t1.is_alive(), "t1 未在逾時內結束 — 疑似 deadlock"
    assert not t2.is_alive(), "t2 未在逾時內結束 — 疑似 deadlock"
    assert errors == [], f"unexpected errors: {errors}"
    # 無 lost update：10 - 3 - 4 = 3（舊行為會是 6 或 7）
    assert inv_repo.get_item(item.id).stock_new == 3
    assert _count_ledger_entries(mr_repo) == 2


def test_read_transactions_not_serialized(repos):
    """**WMOM-20260525-01 must-fix regression**：純讀交易維持 ``BEGIN DEFERRED``，
    兩個並發讀可同時持有交易、互不阻塞。

    修復的 scope guard：``BEGIN IMMEDIATE`` 只套在 read-modify-write 寫路徑
    （``immediate_transaction()``）；若誤把「全交易」都升級成 ``BEGIN IMMEDIATE``，純讀
    （reporting 長查詢 / list / dashboard）也會取 RESERVED write lock → 互相序列化、
    一個長讀可卡住所有寫。

    本 test 開兩個只讀的 session，各自先觸發一次 SELECT（→ begin）再於 barrier 等對方。
    *正確（deferred 讀）*：兩讀都不取 write lock → 都抵達 barrier → ``reached == 2``。
    *回歸（讀也 IMMEDIATE）*：第二個 begin 卡在 RESERVED lock，busy_timeout(5s) 後 raise
    `OperationalError` → 到不了 barrier → barrier(8s) 逾時 → ``reached < 2`` → 失敗。
    """
    inv_repo, mr_repo = repos
    wh = inv_repo.create_warehouse(farm_id="f", name="W", is_default=True)
    inv_repo.create_item(
        sku="A", name="a", description="a", unit="piece",
        farm_id="f", warehouse_id=wh.id, unit_cost=Decimal("100.00"), stock_new=5,
    )

    barrier = threading.Barrier(2, timeout=8.0)
    reached: list[bool] = []
    errors: list[Exception] = []

    def _read_and_hold():
        try:
            with mr_repo._sessionmaker() as sess:
                # 觸發 begin（純讀）
                sess.execute(select(CostLedgerEntryORM)).scalars().all()
                barrier.wait()  # 交易開著等對方 — deferred 讀不互鎖才能兩邊都到
                reached.append(True)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    t1 = threading.Thread(target=_read_and_hold)
    t2 = threading.Thread(target=_read_and_hold)
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert not t1.is_alive() and not t2.is_alive(), "讀 thread 未結束 — 疑似被序列化卡死"
    assert errors == [], f"並發讀不該出錯（被序列化才會 lock timeout）: {errors}"
    assert len(reached) == 2, "兩個並發讀未能同時持有交易 — 純讀疑似被升級成 BEGIN IMMEDIATE"
