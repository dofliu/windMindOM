"""WMOM-20260509-F1 — ``add_return`` 寫 ledger 沖銷 regression tests。

驗證：

1. 退料寫 **負值 CONFIRMED** ledger entry（amount = -(qty × parent_locked_unit_cost)）
2. ``source_item_id=MaterialReturn.id``（不撞 dispatch parent 的 ``source_item_id=mr_item.id``，
   保護 ``find_for_mr_item.scalar_one_or_none``）
3. ``locked_unit_cost`` 沿用 dispatch parent 鎖定值，**即使 inventory.unit_cost 改動**
4. 多次退料各寫一筆 offset entry
5. ``summary_by_category(CONFIRMED)`` 退料後正確扣減
6. Dispatch 前退料（無 parent entry）→ 不阻塞 stock/return record，僅跳過 ledger（warning）
7. WO finish hook 的 ``find_for_mr_item`` 在多筆退料 entry 並存下仍正確指向 parent
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.cost.repository.cost_ledger import (
    CostLedgerCategory,
    CostLedgerEntryORM,
    CostLedgerSourceType,
    CostLedgerStatus,
)
from modules.cost.repository import get_cost_ledger_repository
from modules.workflow.domain.inventory import (
    MaterialRequestStatus,
    ReturnReason,
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
def db_path(tmp_path) -> str:
    return str(tmp_path / "wind_farm.db")


@pytest.fixture
def repos(db_path):
    clear_engine_cache_for_test()
    inv_repo = get_inventory_repository(db_path)
    mr_repo = get_material_request_repository(db_path)
    yield inv_repo, mr_repo
    clear_engine_cache_for_test()


@pytest.fixture
def ledger_repo(db_path):
    """獨立的 cost ledger repository — 給 summary_by_category / find_for_mr_item 用。"""
    return get_cost_ledger_repository(db_path)


def _setup_dispatched_mr(
    inv_repo: InventoryRepository,
    mr_repo: MaterialRequestRepository,
    *,
    farm_id: str = "f",
    initial_stock: int = 10,
    estimated_qty: int = 5,
    unit_cost: Decimal = Decimal("450.00"),
) -> tuple[UUID, UUID]:
    """建一個 DISPATCHED MR（含 parent ledger entry）。回傳 (mr_id, item_id)。"""
    wh = inv_repo.create_warehouse(farm_id=farm_id, name="W", is_default=True)
    item = inv_repo.create_item(
        sku="X-1", name="x", description="x", unit="piece",
        farm_id=farm_id, warehouse_id=wh.id, unit_cost=unit_cost,
        stock_new=initial_stock,
    )
    mr = mr_repo.create(
        farm_id=farm_id, requester_id=uuid4(),
        items=[(item.id, estimated_qty, StockKind.NEW)],
    )
    mr_repo.transition(mr.id, "submit_for_approval")
    mr_repo.transition(mr.id, "approve_all")
    mr_repo.dispatch_request(mr.id)
    return mr.id, item.id


def _all_ledger_entries(mr_repo: MaterialRequestRepository) -> list[CostLedgerEntryORM]:
    with mr_repo._sessionmaker() as sess:
        return list(sess.execute(select(CostLedgerEntryORM)).scalars().all())


# ─────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_writes_negative_confirmed_ledger_entry(repos):
    """退料同 transaction 內寫 1 筆負值 CONFIRMED ledger entry。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=5,
        unit_cost=Decimal("450.00"),
    )
    # dispatch 後：parent ledger entry 已寫
    before = _all_ledger_entries(mr_repo)
    assert len(before) == 1
    assert before[0].status == CostLedgerStatus.ESTIMATED.value
    assert Decimal(str(before[0].amount)) == Decimal("2250.00")  # 5 × 450

    ret = mr_repo.add_return(
        request_id=mr_id,
        item_id=item_id,
        qty=2,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
        note="退 2 個剩料",
    )

    after = _all_ledger_entries(mr_repo)
    assert len(after) == 2, "退料應該寫一筆新 ledger entry"

    offset_entries = [e for e in after if Decimal(str(e.amount)) < 0]
    assert len(offset_entries) == 1
    offset = offset_entries[0]

    # 沖銷金額：-(2 × 450) = -900
    assert Decimal(str(offset.amount)) == Decimal("-900.00")
    # status = CONFIRMED + confirmed_at 設好
    assert offset.status == CostLedgerStatus.CONFIRMED.value
    assert offset.confirmed_at is not None
    # category / source_type
    assert offset.category == CostLedgerCategory.MATERIAL.value
    assert offset.source_type == CostLedgerSourceType.MATERIAL_REQUEST.value
    # source_event_id 對到 MR
    assert offset.source_event_id == str(mr_id)
    # source_item_id 對到 return.id（不撞 mr_item.id）
    assert offset.source_item_id == str(ret.id)
    # locked_unit_cost 沿用 parent
    assert Decimal(str(offset.locked_unit_cost)) == Decimal("450.0000")


def test_add_return_source_item_id_uses_return_id_not_mr_item_id(repos, ledger_repo):
    """退料 entry 的 source_item_id 必須是 MaterialReturn.id（不是 mr_item.id），
    才不會破壞 ``find_for_mr_item`` 的 ``scalar_one_or_none``。
    """
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(inv_repo, mr_repo)

    # dispatch 後 find_for_mr_item 可唯一指向 parent
    # 先撈 dispatch parent entry 的 mr_item.id
    from modules.workflow.repository.inventory_orm import MaterialRequestItemORM
    with mr_repo._sessionmaker() as sess:
        mr_item = sess.execute(
            select(MaterialRequestItemORM).where(
                MaterialRequestItemORM.request_id == str(mr_id),
            )
        ).scalar_one()
        mr_item_id = UUID(mr_item.id)

    parent_before = ledger_repo.find_for_mr_item(mr_id, mr_item_id)
    assert parent_before is not None

    # 連退 3 次
    for _ in range(3):
        mr_repo.add_return(
            request_id=mr_id,
            item_id=item_id,
            qty=1,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW,
            returned_by=uuid4(),
        )

    # find_for_mr_item 仍應唯一指向 parent，不 raise MultipleResultsFound
    parent_after = ledger_repo.find_for_mr_item(mr_id, mr_item_id)
    assert parent_after is not None
    assert parent_after.id == parent_before.id


def test_add_return_uses_parent_locked_unit_cost_not_current_inventory(repos):
    """dispatch 後 admin 改 inventory.unit_cost，退料沖銷必須用 parent locked_unit_cost，
    不是現行 inventory.unit_cost — 否則 estimated/confirmed 基礎不一致。
    """
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=5,
        unit_cost=Decimal("450.00"),
    )

    # 改 inventory.unit_cost（模擬市場價變動）
    with mr_repo._sessionmaker() as sess:
        from modules.workflow.repository.inventory_orm import InventoryItemORM
        inv_orm = sess.get(InventoryItemORM, str(item_id))
        inv_orm.unit_cost = Decimal("999.00")
        sess.commit()

    # 退 1 個
    mr_repo.add_return(
        request_id=mr_id,
        item_id=item_id,
        qty=1,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )

    entries = _all_ledger_entries(mr_repo)
    offset_entries = [e for e in entries if Decimal(str(e.amount)) < 0]
    assert len(offset_entries) == 1
    # 沖銷金額 = -(1 × 450) = -450，不是 -999
    assert Decimal(str(offset_entries[0].amount)) == Decimal("-450.00")
    assert Decimal(str(offset_entries[0].locked_unit_cost)) == Decimal("450.0000")


def test_add_return_multiple_returns_each_writes_offset(repos):
    """同一 line item 多次退料 → 每次都寫一筆 offset entry（獨立 audit trail）。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=20, estimated_qty=10,
        unit_cost=Decimal("100.00"),
    )

    for qty in (2, 3, 1):
        mr_repo.add_return(
            request_id=mr_id,
            item_id=item_id,
            qty=qty,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW,
            returned_by=uuid4(),
        )

    entries = _all_ledger_entries(mr_repo)
    offset_entries = [e for e in entries if Decimal(str(e.amount)) < 0]
    assert len(offset_entries) == 3
    amounts = sorted(Decimal(str(e.amount)) for e in offset_entries)
    assert amounts == [Decimal("-300.00"), Decimal("-200.00"), Decimal("-100.00")]


def test_summary_by_category_confirmed_net_of_returns(repos, ledger_repo):
    """月報 ``summary_by_category(CONFIRMED)`` 退料後扣減正確（F1 修補目標）。

    Scenario：dispatch 10×100 → finish 拿 actual_qty=10 → ledger CONFIRMED 1000，
    再退料 3×100 → offset -300，total CONFIRMED material = 700。
    """
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=20, estimated_qty=10,
        unit_cost=Decimal("100.00"),
    )

    # 模擬 WO finish hook：把 dispatch parent entry flip 成 CONFIRMED with actual_qty
    # 不走 _confirm_material_ledger_for_finished_wo（要 mock WO 太麻煩），改用 repo API
    from modules.workflow.repository.inventory_orm import MaterialRequestItemORM
    with mr_repo._sessionmaker() as sess:
        mr_item = sess.execute(
            select(MaterialRequestItemORM).where(
                MaterialRequestItemORM.request_id == str(mr_id),
            )
        ).scalar_one()
        mr_item_id = UUID(mr_item.id)

    parent_entry = ledger_repo.find_for_mr_item(mr_id, mr_item_id)
    assert parent_entry is not None
    ledger_repo.confirm_entry(parent_entry.id, new_amount=Decimal("1000.00"))

    # 退料 3 個
    mr_repo.add_return(
        request_id=mr_id,
        item_id=item_id,
        qty=3,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )

    # 月報統計（CONFIRMED 範圍）
    summary = ledger_repo.summary_by_category(
        farm_id="f",
        status=CostLedgerStatus.CONFIRMED,
    )
    # 1000 + (-300) = 700
    assert summary.get(CostLedgerCategory.MATERIAL) == Decimal("700.00"), (
        f"expected MATERIAL=700.00 (1000 - 300 退料), got {summary}"
    )


def test_summary_by_category_confirmed_net_of_returns_within_date_range(repos, ledger_repo):
    """月報邊界：``summary_by_category(from_date, to_date)`` 必須**正確納入**月份內退料 entry，
    **正確排除**月份外退料 entry（review fix should-fix #5）。

    Scenario：dispatch 寫 parent CONFIRMED entry 1000；月內退料 100、月後退料 200；
    月內 summary 應只看到 1000 - 100 = 900；全期 summary 應看到 1000 - 100 - 200 = 700。
    """
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=20, estimated_qty=10,
        unit_cost=Decimal("100.00"),
    )

    # 把 dispatch parent flip 成 CONFIRMED + amount=1000
    from modules.workflow.repository.inventory_orm import MaterialRequestItemORM
    with mr_repo._sessionmaker() as sess:
        mr_item = sess.execute(
            select(MaterialRequestItemORM).where(
                MaterialRequestItemORM.request_id == str(mr_id),
            )
        ).scalar_one()
        mr_item_id = UUID(mr_item.id)
    parent_entry = ledger_repo.find_for_mr_item(mr_id, mr_item_id)
    ledger_repo.confirm_entry(parent_entry.id, new_amount=Decimal("1000.00"))

    # 月內退料 1 個
    mr_repo.add_return(
        request_id=mr_id,
        item_id=item_id,
        qty=1,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )

    # 月後退料 2 個 — 手動把 recorded_at 推到月後
    mr_repo.add_return(
        request_id=mr_id,
        item_id=item_id,
        qty=2,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )
    # 推 recorded_at 到月後
    next_month_dt = datetime(2099, 2, 1, tzinfo=timezone.utc)
    with mr_repo._sessionmaker() as sess:
        late_entry = sess.execute(
            select(CostLedgerEntryORM).where(
                CostLedgerEntryORM.amount == Decimal("-200.00"),
            )
        ).scalar_one()
        late_entry.recorded_at = next_month_dt
        sess.commit()

    # 把 dispatch parent + 月內退料 entry 也推到目標月份內（避免測試現在的時鐘干擾）
    target_month_dt = datetime(2099, 1, 15, tzinfo=timezone.utc)
    with mr_repo._sessionmaker() as sess:
        entries = sess.execute(
            select(CostLedgerEntryORM).where(
                CostLedgerEntryORM.amount.in_([Decimal("1000.00"), Decimal("-100.00")]),
            )
        ).scalars().all()
        for e in entries:
            e.recorded_at = target_month_dt
        sess.commit()

    # 月份內：[2099-01-01, 2099-02-01) → 應只看到 1000 + (-100) = 900
    in_month = ledger_repo.summary_by_category(
        farm_id="f",
        from_date=datetime(2099, 1, 1, tzinfo=timezone.utc),
        to_date=datetime(2099, 2, 1, tzinfo=timezone.utc),
        status=CostLedgerStatus.CONFIRMED,
    )
    assert in_month.get(CostLedgerCategory.MATERIAL) == Decimal("900.00"), (
        f"月份內應該只看到 1000 - 100 = 900；月後 -200 不應計入；實際 {in_month}"
    )

    # 全期：應看到 1000 + (-100) + (-200) = 700
    all_time = ledger_repo.summary_by_category(
        farm_id="f",
        status=CostLedgerStatus.CONFIRMED,
    )
    assert all_time.get(CostLedgerCategory.MATERIAL) == Decimal("700.00"), (
        f"全期應該看到 1000 - 100 - 200 = 700；實際 {all_time}"
    )


def test_add_return_atomic_rollback_after_ledger_insert(repos):
    """退料中途（**ledger 已 add 進 session 後、commit 之前**）raise → stock + return record +
    ledger entry 全 rollback。

    Review fix（must-fix #1）：原版測試在 ``MaterialReturnORM`` 建構時 raise，
    執行序早於 ledger insert，等於只驗證了「ledger 還沒被呼叫」的 trivial path。
    本版改 monkeypatch ``insert_in_session`` 讓它 add 進 session 後再 raise，
    確保「ledger 已在 session 但 commit 前失敗」的真實 partial-flush rollback 路徑
    被驗證。
    """
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=5,
        unit_cost=Decimal("450.00"),
    )

    before_stock = inv_repo.get_item(item_id).stock_new
    before_entries = len(_all_ledger_entries(mr_repo))
    assert before_entries == 1  # dispatch parent ledger entry exists

    # 注入：呼叫真實 insert_in_session（讓 ledger entry add 進 session），然後 raise
    # add_return 透過 ``_cost_ledger.insert_in_session`` attr-access 呼叫，所以
    # patch ``_cost_ledger`` module 上的 attr 才有效
    from modules.cost.repository import cost_ledger as cost_ledger_mod
    original_insert = cost_ledger_mod.insert_in_session

    def exploding_insert(sess, entry):
        # 先真實 add 進 session
        orm = original_insert(sess, entry)
        # session 已有未 flush 的 ledger entry — 在 commit 前 raise 模擬最壞情境
        raise RuntimeError("simulated failure after ledger insert, before commit")

    cost_ledger_mod.insert_in_session = exploding_insert
    try:
        with pytest.raises(RuntimeError, match="after ledger insert"):
            mr_repo.add_return(
                request_id=mr_id,
                item_id=item_id,
                qty=2,
                reason=ReturnReason.SURPLUS,
                return_to_kind=StockKind.NEW,
                returned_by=uuid4(),
            )
    finally:
        cost_ledger_mod.insert_in_session = original_insert

    # Stock 不變（session rollback 把 +stock 也撤）
    assert inv_repo.get_item(item_id).stock_new == before_stock
    # Ledger 不變 — partial-flush 的 ledger entry 必須 rollback，不可留在 DB
    after_entries = _all_ledger_entries(mr_repo)
    assert len(after_entries) == before_entries, (
        "ledger entry partial-flush 應被 rollback；找到 stale offset entry 代表 atomicity 破"
    )
    # MaterialReturn record 也不可寫進 DB
    from modules.workflow.repository.inventory_orm import MaterialReturnORM
    with mr_repo._sessionmaker() as sess:
        returns = sess.execute(select(MaterialReturnORM)).scalars().all()
        assert len(returns) == 0, "MaterialReturn record 也應 rollback"


def test_add_return_no_parent_ledger_entry_succeeds_with_warning(repos, caplog):
    """極罕見：dispatch parent ledger entry 不存在（資料 corruption） → ledger 寫入 skip
    但 stock + MaterialReturn record 仍完成，並 log warning。
    """
    import logging
    inv_repo, mr_repo = repos
    # 不走 dispatch 路徑，直接建一個 MR（無 parent ledger entry）
    wh = inv_repo.create_warehouse(farm_id="f", name="W", is_default=True)
    item = inv_repo.create_item(
        sku="X", name="x", description="x", unit="piece",
        farm_id="f", warehouse_id=wh.id, unit_cost=Decimal("100.00"),
        stock_new=10,
    )
    mr = mr_repo.create(
        farm_id="f", requester_id=uuid4(),
        items=[(item.id, 5, StockKind.NEW)],
    )

    with caplog.at_level(logging.WARNING):
        ret = mr_repo.add_return(
            request_id=mr.id,
            item_id=item.id,
            qty=1,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW,
            returned_by=uuid4(),
        )

    # MaterialReturn record 寫進
    assert ret.qty == 1
    # Stock 加回
    assert inv_repo.get_item(item.id).stock_new == 11
    # Ledger 沒寫（沒 parent → skip）
    entries = _all_ledger_entries(mr_repo)
    assert len(entries) == 0
    # Warning log
    assert any(
        "no parent ledger entry" in r.message for r in caplog.records
    ), "should log warning about missing parent entry"


def test_add_return_negative_entry_includes_audit_metadata(repos):
    """退料 entry 必須帶足 audit metadata：actor_id, note 含 reason + qty + item。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=5,
        unit_cost=Decimal("100.00"),
    )

    returner = uuid4()
    ret = mr_repo.add_return(
        request_id=mr_id,
        item_id=item_id,
        qty=2,
        reason=ReturnReason.WRONG_PART,
        return_to_kind=StockKind.REPAIRING,
        returned_by=returner,
        note="bearing crack",
    )

    entries = _all_ledger_entries(mr_repo)
    offset = next(e for e in entries if Decimal(str(e.amount)) < 0)
    # actor_id 應該是退料人
    assert offset.actor_id == str(returner)
    # note 含 reason / qty / item
    assert offset.note is not None
    assert ReturnReason.WRONG_PART.value in offset.note
    assert "qty=2" in offset.note
    assert str(item_id) in offset.note
