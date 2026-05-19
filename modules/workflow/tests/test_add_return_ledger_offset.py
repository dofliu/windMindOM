"""WMOM-20260509-F1：`add_return` 寫 ledger 沖銷 entry。

驗證：
- 退料同 transaction 寫一筆 negative amount + status=confirmed 的 cost_ledger entry
- amount 用 **dispatch entry locked_unit_cost** 算（會計一致性 — 不用當前 inventory unit_cost）
- source_item_id = MaterialReturn.id，不衝突 dispatch entry 的 mr_item.id（wo finish hook 不誤觸）
- 月報 summary_by_category(status=CONFIRMED) 視角 dispatch(confirmed) + return(confirmed) 淨額正確
- 找不到 dispatch ledger entry → log warning + 仍寫 stock + MaterialReturn（不寫 ledger）
- locked_unit_cost is None fallback inventory unit_cost
- multi-item MR：return 其中一個只沖銷該 line
"""

from __future__ import annotations

import logging
import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.cost.repository.cost_ledger import (  # noqa: E402
    CostLedgerCategory,
    CostLedgerEntryORM,
    CostLedgerStatus,
)
from modules.workflow.domain.inventory import (  # noqa: E402
    MaterialRequestStatus,
    ReturnReason,
    StockKind,
)
from modules.workflow.repository import (  # noqa: E402
    InventoryRepository,
    MaterialRequestRepository,
    get_inventory_repository,
    get_material_request_repository,
)
from modules.workflow.repository.work_order_repository import (  # noqa: E402
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
    inv = get_inventory_repository(db_path)
    mr = get_material_request_repository(db_path)
    yield inv, mr
    clear_engine_cache_for_test()


def _setup_dispatched_mr(
    inv_repo: InventoryRepository,
    mr_repo: MaterialRequestRepository,
    *,
    initial_stock: int = 10,
    estimated_qty: int = 2,
    unit_cost: Decimal = Decimal("450.00"),
    farm_id: str = "f",
) -> tuple[UUID, UUID]:
    """建一個 APPROVED → DISPATCHED 的 MR + 回傳 (mr_id, item_id)。"""
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


def _get_ledger_entries(mr_repo: MaterialRequestRepository) -> list[CostLedgerEntryORM]:
    with mr_repo._sessionmaker() as sess:
        return list(sess.execute(select(CostLedgerEntryORM)).scalars().all())


# ─────────────────────────────────────────────────────────────────────────
# Happy path：退料寫 negative confirmed entry
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_writes_negative_confirmed_ledger_entry(repos):
    """退料 → ledger 多一筆 amount<0 + status=confirmed 的 entry。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo,
        initial_stock=10, estimated_qty=3, unit_cost=Decimal("450.00"),
    )
    # dispatch 後 ledger 應該有 1 筆 estimated +1350
    entries_before = _get_ledger_entries(mr_repo)
    assert len(entries_before) == 1
    assert entries_before[0].status == CostLedgerStatus.ESTIMATED.value

    mr_repo.add_return(
        request_id=mr_id,
        item_id=item_id,
        qty=1,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )

    entries_after = _get_ledger_entries(mr_repo)
    assert len(entries_after) == 2

    return_entry = next(
        e for e in entries_after if Decimal(str(e.amount)) < 0
    )
    assert return_entry.category == CostLedgerCategory.MATERIAL.value
    assert return_entry.status == CostLedgerStatus.CONFIRMED.value
    assert return_entry.confirmed_at is not None
    assert Decimal(str(return_entry.amount)) == Decimal("-450.00")  # -(1 × 450)
    assert return_entry.source_event_id == str(mr_id)
    assert return_entry.source_type == "material_request"


def test_add_return_amount_uses_dispatch_locked_unit_cost_not_current(repos):
    """dispatch 後 inventory 漲價 → return entry 用 dispatch 鎖定的 unit_cost 算，不重查。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo,
        initial_stock=10, estimated_qty=2, unit_cost=Decimal("450.00"),
    )
    # dispatch 後人為調漲 unit_cost
    with inv_repo._sessionmaker() as sess:
        from modules.workflow.repository.inventory_orm import InventoryItemORM
        inv = sess.get(InventoryItemORM, str(item_id))
        inv.unit_cost = Decimal("999.00")
        sess.commit()

    mr_repo.add_return(
        request_id=mr_id,
        item_id=item_id,
        qty=1,
        reason=ReturnReason.WRONG_PART,
        return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )

    return_entry = next(
        e for e in _get_ledger_entries(mr_repo) if Decimal(str(e.amount)) < 0
    )
    # 用 dispatch 當下的 450，不是漲後的 999
    assert Decimal(str(return_entry.amount)) == Decimal("-450.00")
    assert Decimal(str(return_entry.locked_unit_cost)) == Decimal("450.00")


def test_add_return_source_item_id_is_return_id_not_mr_item_id(repos):
    """return entry 的 source_item_id 必須是 MaterialReturn.id，不是 mr_item.id。

    這是為了避免 wo finish hook 的 find_for_mr_item(mr_id, mr_item.id) 撈到多筆 entry
    導致 scalar_one_or_none() raise。
    """
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, estimated_qty=2, unit_cost=Decimal("100.00"),
    )

    ret = mr_repo.add_return(
        request_id=mr_id,
        item_id=item_id,
        qty=1,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )

    return_entry = next(
        e for e in _get_ledger_entries(mr_repo) if Decimal(str(e.amount)) < 0
    )
    # source_item_id = MaterialReturn.id
    assert return_entry.source_item_id == str(ret.id)
    # 不等於 mr_item.id
    mr = mr_repo.get(mr_id)
    assert return_entry.source_item_id != str(mr.items[0].id)


# ─────────────────────────────────────────────────────────────────────────
# 月報 confirmed 視角驗證
# ─────────────────────────────────────────────────────────────────────────


def test_summary_by_category_confirmed_includes_negative_offset(db_path, repos):
    """月報 summary_by_category(CONFIRMED) 看到 dispatch confirmed + return confirmed 淨額。

    Scenario：dispatch 2 件 → wo finish confirm 翻 estimated→confirmed +900
    → add_return 1 件 → 寫 -450 confirmed
    → confirmed 視角 = 900 - 450 = 450
    """
    from modules.cost.repository import get_cost_ledger_repository
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo,
        initial_stock=10, estimated_qty=2, unit_cost=Decimal("450.00"),
        farm_id="changhua",
    )

    # 模擬 wo finish confirm 翻 dispatch entry
    ledger_repo = get_cost_ledger_repository(db_path)
    dispatch_entry = next(
        e for e in _get_ledger_entries(mr_repo)
        if e.status == CostLedgerStatus.ESTIMATED.value
    )
    ledger_repo.confirm_entry(
        UUID(dispatch_entry.id), new_amount=Decimal("900.00")
    )

    # 退料 1 件
    mr_repo.add_return(
        request_id=mr_id,
        item_id=item_id,
        qty=1,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )

    confirmed_map = ledger_repo.summary_by_category(
        farm_id="changhua",
        status=CostLedgerStatus.CONFIRMED,
    )
    # 淨額 = +900 + (-450) = +450
    assert confirmed_map[CostLedgerCategory.MATERIAL] == Decimal("450.00")


def test_summary_by_category_confirmed_after_full_return_zero(db_path, repos):
    """全退（return qty == estimated_qty）→ confirmed 視角應為 0。"""
    from modules.cost.repository import get_cost_ledger_repository
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo,
        initial_stock=5, estimated_qty=2, unit_cost=Decimal("300.00"),
        farm_id="changhua",
    )

    ledger_repo = get_cost_ledger_repository(db_path)
    dispatch_entry = next(
        e for e in _get_ledger_entries(mr_repo)
        if e.status == CostLedgerStatus.ESTIMATED.value
    )
    ledger_repo.confirm_entry(
        UUID(dispatch_entry.id), new_amount=Decimal("600.00")
    )

    mr_repo.add_return(
        request_id=mr_id,
        item_id=item_id,
        qty=2,
        reason=ReturnReason.FAILED_INSTALL,
        return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )

    confirmed_map = ledger_repo.summary_by_category(
        farm_id="changhua",
        status=CostLedgerStatus.CONFIRMED,
    )
    assert confirmed_map.get(CostLedgerCategory.MATERIAL, Decimal("0")) == Decimal("0")


# ─────────────────────────────────────────────────────────────────────────
# WO finish hook 互動：dispatch entry 翻 confirmed 不影響 return entry
# ─────────────────────────────────────────────────────────────────────────


def test_wo_finish_hook_only_touches_dispatch_entry_not_return(db_path, repos):
    """confirm hook 的 find_for_mr_item(mr_id, mr_item.id) 只 match dispatch entry。

    退料 entry 的 source_item_id = MaterialReturn.id 不會被誤觸（idempotent 保護）。
    """
    from modules.cost.repository import get_cost_ledger_repository
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo,
        initial_stock=10, estimated_qty=2, unit_cost=Decimal("500.00"),
    )

    # 退料先發生（dispatch 後 / confirm 前）
    mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=1,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW, returned_by=uuid4(),
    )

    ledger_repo = get_cost_ledger_repository(db_path)
    mr = mr_repo.get(mr_id)
    # find_for_mr_item 找 mr_item.id 對應的 dispatch entry — 不會被 return entry 干擾
    found = ledger_repo.find_for_mr_item(mr_id, mr.items[0].id)
    assert found is not None
    assert found.status is CostLedgerStatus.ESTIMATED
    # 確認是 dispatch entry（amount = +1000）
    assert found.amount == Decimal("1000.00")

    # confirm 後 dispatch entry 變 confirmed；return entry 仍是 confirmed 不被誤翻
    ledger_repo.confirm_entry(found.id, new_amount=Decimal("500.00"))  # actual=1
    entries = _get_ledger_entries(mr_repo)
    statuses = sorted(e.status for e in entries)
    assert statuses == ["confirmed", "confirmed"]
    amounts = sorted(Decimal(str(e.amount)) for e in entries)
    assert amounts == [Decimal("-500.00"), Decimal("500.00")]


# ─────────────────────────────────────────────────────────────────────────
# Fallback：找不到 dispatch ledger entry → warning + skip ledger entry
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_without_dispatch_entry_uses_inventory_fallback(repos, caplog):
    """MR 未 dispatch（DRAFT）直接 add_return → 沒對應 dispatch entry，但 inventory
    item 存在 → fallback 用 inventory.unit_cost 算 offset。

    Note：domain rule 沒擋 add_return 在哪個 status，所以 stock + return 仍寫成功。
    本路徑（已找到 fallback）**不應**產生 warning（only `_lookup_offset_unit_cost`
    回 None 才 warn）。
    """
    inv_repo, mr_repo = repos
    wh = inv_repo.create_warehouse(farm_id="f", name="W", is_default=True)
    item = inv_repo.create_item(
        sku="A", name="a", description="a", unit="piece",
        farm_id="f", warehouse_id=wh.id, unit_cost=Decimal("200.00"),
        stock_new=5,
    )
    mr = mr_repo.create(
        farm_id="f", requester_id=uuid4(),
        items=[(item.id, 2, StockKind.NEW)],
    )
    # 未 dispatch — 沒對應 dispatch ledger entry
    assert len(_get_ledger_entries(mr_repo)) == 0

    with caplog.at_level(
        logging.WARNING,
        logger="modules.workflow.repository.material_request_repository",
    ):
        mr_repo.add_return(
            request_id=mr.id, item_id=item.id, qty=1,
            reason=ReturnReason.WRONG_PART,
            return_to_kind=StockKind.NEW, returned_by=uuid4(),
        )

    # Fallback：用 inventory.unit_cost 算 offset → -200
    entries = _get_ledger_entries(mr_repo)
    assert len(entries) == 1
    assert Decimal(str(entries[0].amount)) == Decimal("-200.00")
    assert entries[0].status == CostLedgerStatus.CONFIRMED.value
    # Inventory fallback 是健康路徑，不該觸發 warning
    assert not any(
        "cannot resolve locked_unit_cost" in r.message for r in caplog.records
    )


def test_add_return_lookup_none_skips_ledger_with_warning(repos, caplog, monkeypatch):
    """`_lookup_offset_unit_cost` 回 None（defensive，實務罕見 — 都被 inventory fallback
    擋掉）→ warning + 不寫 ledger entry，但 stock + MaterialReturn 仍寫。

    覆蓋 add_return 對 None unit_cost 的 defensive 處理。實務上 None 場景需要既無
    dispatch entry 也無 inventory item，但後者會讓 apply_stock_delta 先 raise，所以
    這條 None 路徑只可能由人為破壞 ledger entry + inventory 觸發；用 monkeypatch
    直接構造 None 是最乾淨的測法。
    """
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=2,
        unit_cost=Decimal("100.00"),
    )

    monkeypatch.setattr(
        MaterialRequestRepository, "_lookup_offset_unit_cost",
        staticmethod(lambda sess, **kw: None),
    )

    with caplog.at_level(
        logging.WARNING,
        logger="modules.workflow.repository.material_request_repository",
    ):
        ret = mr_repo.add_return(
            request_id=mr_id, item_id=item_id, qty=1,
            reason=ReturnReason.OTHER,
            return_to_kind=StockKind.NEW, returned_by=uuid4(),
        )

    # MaterialReturn + stock 寫成功
    assert ret.qty == 1
    assert inv_repo.get_item(item_id).stock_new == 9  # 10 - 2 + 1
    # 但 ledger 只有 dispatch entry，沒 return entry
    entries = _get_ledger_entries(mr_repo)
    assert len(entries) == 1
    assert entries[0].status == CostLedgerStatus.ESTIMATED.value
    # warning 有記
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("cannot resolve locked_unit_cost" in r.message for r in warnings)


def test_add_return_dispatch_entry_no_locked_cost_uses_inventory(repos):
    """舊 dispatch entry 沒 locked_unit_cost → fallback 用 inventory.unit_cost。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo,
        initial_stock=10, estimated_qty=2, unit_cost=Decimal("450.00"),
    )

    # 人為清除 dispatch entry 的 locked_unit_cost（模擬老 entries）
    with mr_repo._sessionmaker() as sess:
        e = sess.execute(select(CostLedgerEntryORM)).scalar_one()
        e.locked_unit_cost = None
        sess.commit()

    mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=1,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW, returned_by=uuid4(),
    )

    return_entry = next(
        e for e in _get_ledger_entries(mr_repo) if Decimal(str(e.amount)) < 0
    )
    # Fallback 用 inventory.unit_cost = 450（沒漲價場景）
    assert Decimal(str(return_entry.amount)) == Decimal("-450.00")


# ─────────────────────────────────────────────────────────────────────────
# Multi-item MR：只沖銷退的那個 line
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_multi_item_mr_only_offsets_returned_item(repos):
    """MR 有 2 個 item 都 dispatch → 只退其中一個 → ledger 只多一筆對應那 line 的 offset。"""
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
    assert len(_get_ledger_entries(mr_repo)) == 2  # 2 個 dispatch entries

    # 只退 a 一個
    mr_repo.add_return(
        request_id=mr.id, item_id=a.id, qty=1,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW, returned_by=uuid4(),
    )

    entries = _get_ledger_entries(mr_repo)
    assert len(entries) == 3  # 2 dispatch + 1 return
    negative_entries = [e for e in entries if Decimal(str(e.amount)) < 0]
    assert len(negative_entries) == 1
    assert Decimal(str(negative_entries[0].amount)) == Decimal("-100.00")  # a 的 cost
    assert Decimal(str(negative_entries[0].locked_unit_cost)) == Decimal("100.00")


# ─────────────────────────────────────────────────────────────────────────
# 退多筆同 MR 同 item — 每次都寫獨立 offset entry
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_multiple_returns_each_writes_own_entry(repos):
    """同 MR 同 item 連退兩次 → ledger 多兩筆 offset entry。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo,
        initial_stock=10, estimated_qty=3, unit_cost=Decimal("200.00"),
    )

    mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=1,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW, returned_by=uuid4(),
    )
    mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=1,
        reason=ReturnReason.WRONG_PART,
        return_to_kind=StockKind.USED,
        returned_by=uuid4(),
    )

    entries = _get_ledger_entries(mr_repo)
    assert len(entries) == 3  # 1 dispatch + 2 returns
    negatives = sorted(
        Decimal(str(e.amount)) for e in entries if Decimal(str(e.amount)) < 0
    )
    assert negatives == [Decimal("-200.00"), Decimal("-200.00")]


# ─────────────────────────────────────────────────────────────────────────
# Stock + ledger atomic：ledger insert 失敗 → stock 也 rollback
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_atomic_ledger_failure_rolls_back_stock(repos):
    """patch ledger insert raise → stock 不變 + return 紀錄不寫。"""
    from unittest.mock import patch
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=10, estimated_qty=2,
        unit_cost=Decimal("100.00"),
    )
    stock_before = inv_repo.get_item(item_id).stock_new  # 8 (10 - 2)

    target = "modules.cost.repository.cost_ledger.insert_in_session"
    with patch(target, side_effect=RuntimeError("synthetic ledger fail")):
        with pytest.raises(RuntimeError, match="synthetic ledger fail"):
            mr_repo.add_return(
                request_id=mr_id, item_id=item_id, qty=1,
                reason=ReturnReason.SURPLUS,
                return_to_kind=StockKind.NEW, returned_by=uuid4(),
            )

    # Stock 沒被加回（rollback 了）
    assert inv_repo.get_item(item_id).stock_new == stock_before
    # ledger 只有 dispatch entry，沒 return entry
    entries = _get_ledger_entries(mr_repo)
    assert len(entries) == 1
    assert entries[0].status == CostLedgerStatus.ESTIMATED.value


# ─────────────────────────────────────────────────────────────────────────
# MR not found
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_unknown_mr(repos):
    """MR 不存在 → LookupError，stock / ledger 都不動。"""
    inv_repo, mr_repo = repos
    with pytest.raises(LookupError):
        mr_repo.add_return(
            request_id=uuid4(), item_id=uuid4(), qty=1,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW, returned_by=uuid4(),
        )


# ─────────────────────────────────────────────────────────────────────────
# Lifecycle round-trip：MR.status 結束在 DISPATCHED；MaterialReturn record 在
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_does_not_change_mr_status(repos):
    """add_return 不走 state machine — MR.status 不變（仍 DISPATCHED）。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, initial_stock=5, estimated_qty=2,
    )

    mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=1,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW, returned_by=uuid4(),
    )

    assert mr_repo.get(mr_id).status is MaterialRequestStatus.DISPATCHED


# ─────────────────────────────────────────────────────────────────────────
# Cross-kind return（review SF#1）：dispatch NEW → 退 USED
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_cross_stock_kind_uses_dispatch_locked_unit_cost(repos):
    """dispatch StockKind.NEW，退回 StockKind.USED（試裝後歸二手 stock）
    → 仍用 dispatch 那筆 NEW line 的 locked_unit_cost 算 offset。

    會計一致性：沖銷金額反映 dispatch 時的成本，不管退回到哪個 stock_kind。
    """
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo,
        initial_stock=10, estimated_qty=2, unit_cost=Decimal("450.00"),
    )
    # dispatch 後人為調漲 inventory unit_cost 確認 lookup 不會誤用當前值
    with inv_repo._sessionmaker() as sess:
        from modules.workflow.repository.inventory_orm import InventoryItemORM
        inv = sess.get(InventoryItemORM, str(item_id))
        inv.unit_cost = Decimal("888.00")
        sess.commit()

    mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=1,
        reason=ReturnReason.FAILED_INSTALL,
        return_to_kind=StockKind.USED,  # cross-kind: dispatch NEW → return USED
        returned_by=uuid4(),
    )

    return_entry = next(
        e for e in _get_ledger_entries(mr_repo) if Decimal(str(e.amount)) < 0
    )
    # 用 dispatch 鎖定的 450（NEW line），不是漲後 888
    assert Decimal(str(return_entry.amount)) == Decimal("-450.00")
    assert Decimal(str(return_entry.locked_unit_cost)) == Decimal("450.00")


# ─────────────────────────────────────────────────────────────────────────
# 月報 confirmed mid-state（review SF#4）：close 前退料 → confirmed 視角可能為負
# ─────────────────────────────────────────────────────────────────────────


def test_summary_by_category_confirmed_mid_state_before_dispatch_confirm(
    db_path, repos
):
    """dispatch 後 / wo finish confirm 前退料 → confirmed 視角只看到 return entry（負數）。

    這是業務上「月中查月報」的中間狀態：dispatch entry 仍是 estimated（等 wo finish hook
    才翻 confirmed），return entry 一寫就是 confirmed。月報 confirmed 視角單看 return entry
    為 -450，這是預期行為（不是 bug），但 UI 層 / 月報拉取時點需要文件說明。
    """
    from modules.cost.repository import get_cost_ledger_repository
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo,
        initial_stock=10, estimated_qty=2, unit_cost=Decimal("450.00"),
        farm_id="changhua",
    )

    # 退料 in mid-state（dispatch entry 還是 estimated）
    mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=1,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW, returned_by=uuid4(),
    )

    ledger_repo = get_cost_ledger_repository(db_path)
    confirmed_map = ledger_repo.summary_by_category(
        farm_id="changhua",
        status=CostLedgerStatus.CONFIRMED,
    )
    estimated_map = ledger_repo.summary_by_category(
        farm_id="changhua",
        status=CostLedgerStatus.ESTIMATED,
    )
    # confirmed 視角只看到 return entry（-450）
    assert confirmed_map[CostLedgerCategory.MATERIAL] == Decimal("-450.00")
    # estimated 視角仍是 dispatch entry 全額 (2 × 450 = 900)
    assert estimated_map[CostLedgerCategory.MATERIAL] == Decimal("900.00")
    # grand_total = +900 + (-450) = +450（end-state 應有的數字，confirm 後一樣）
    grand = (
        estimated_map[CostLedgerCategory.MATERIAL]
        + confirmed_map[CostLedgerCategory.MATERIAL]
    )
    assert grand == Decimal("450.00")


# ─────────────────────────────────────────────────────────────────────────
# Nice #1：inventory fallback 後月報 confirmed 視角驗證
# ─────────────────────────────────────────────────────────────────────────


def test_summary_by_category_confirmed_with_inventory_fallback(db_path, repos):
    """無 dispatch entry（未 dispatch 就 return）→ fallback inventory.unit_cost
    → 月報 confirmed 視角正確記入 -200。
    """
    from modules.cost.repository import get_cost_ledger_repository
    inv_repo, mr_repo = repos
    wh = inv_repo.create_warehouse(farm_id="changhua", name="W", is_default=True)
    item = inv_repo.create_item(
        sku="A", name="a", description="a", unit="piece",
        farm_id="changhua", warehouse_id=wh.id, unit_cost=Decimal("200.00"),
        stock_new=5,
    )
    mr = mr_repo.create(
        farm_id="changhua", requester_id=uuid4(),
        items=[(item.id, 1, StockKind.NEW)],
    )
    # 不 dispatch，直接 return
    mr_repo.add_return(
        request_id=mr.id, item_id=item.id, qty=1,
        reason=ReturnReason.OTHER,
        return_to_kind=StockKind.NEW, returned_by=uuid4(),
    )

    ledger_repo = get_cost_ledger_repository(db_path)
    confirmed_map = ledger_repo.summary_by_category(
        farm_id="changhua",
        status=CostLedgerStatus.CONFIRMED,
    )
    assert confirmed_map[CostLedgerCategory.MATERIAL] == Decimal("-200.00")
