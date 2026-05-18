"""WMOM-20260509-F1：``add_return`` 寫 cost ledger 沖銷 entry 的 regression tests。

Acceptance（ISSUES.md F1）：
- 退料後 cost ledger 多一筆 negative ``amount`` entry（同 source_event_id +
  source_item_id 對應原 dispatch entry）
- offset entry 的 ``locked_unit_cost`` 跟原 dispatch entry **一致**（不重新查
  inventory，避免 dispatch 後 unit_cost 改動導致估計/實際/沖銷三邊不同基礎）
- offset entry 的 ``status`` match 原 entry（dispatched 但未 finish → ESTIMATED；
  已 finish → CONFIRMED）
- ``summary_by_category(status=CONFIRMED)`` 在退料後正確扣回退料金額（demo
  月報不再偏高 — 這正是本 issue 主要修正點）
- 找不到 dispatch entry 時不阻塞退料（warning + skip ledger offset，stock 仍加回）
- Ledger 寫入失敗時 stock 一起 rollback（atomic 不變式）
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.cost.repository.cost_ledger import (
    CostLedgerCategory,
    CostLedgerSourceType,
    CostLedgerStatus,
)
from modules.cost.repository.cost_ledger_repository import (
    CostLedgerRepository,
    get_cost_ledger_repository,
)
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
    inv = get_inventory_repository(db_path)
    mr = get_material_request_repository(db_path)
    ledger = get_cost_ledger_repository(db_path)
    yield inv, mr, ledger
    clear_engine_cache_for_test()


def _setup_dispatched_mr(
    inv_repo: InventoryRepository,
    mr_repo: MaterialRequestRepository,
    *,
    initial_stock: int = 10,
    estimated_qty: int = 5,
    unit_cost: Decimal = Decimal("100.00"),
    farm_id: str = "f1",
) -> tuple[UUID, UUID]:
    """Helper：建 DISPATCHED MR + inventory item，回傳 (mr_id, item_id)。"""
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


def _get_ledger_entries_for_mr(
    ledger_repo: CostLedgerRepository, mr_id: UUID
) -> list:
    """走 public API — 避免 review fix #6 報的「測試直擊 mr_repo._sessionmaker」。

    用 ``list_for_subject`` 拿一個 MR 的全部 entries（含 offset），給斷言判斷
    數量 / amount / status 用。
    """
    return ledger_repo.list_for_subject(
        mr_id, CostLedgerSourceType.MATERIAL_REQUEST
    )


def _count_all_ledger_entries(ledger_repo: CostLedgerRepository, farm_id: str) -> int:
    """全 ledger entries 計數（含跨 MR 的；給 corner case test 驗證 0 個）。"""
    _, total = ledger_repo.list(farm_id=farm_id)
    return total


# ─────────────────────────────────────────────────────────────────────────
# Happy path — 沖銷 entry 在 ESTIMATED state
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_writes_estimated_ledger_offset_when_dispatch_not_yet_confirmed(repos):
    """退料發生在工單 finish 之前 → 原 entry 是 ESTIMATED，offset 也 ESTIMATED。

    這樣 ``summary(status=ESTIMATED)`` 與 ``summary(status=None)`` 都自然扣回，
    日後工單 finish 時 hook 只 confirm 原 dispatch entry，offset 留 ESTIMATED
    （不會被誤 flip）。
    """
    inv_repo, mr_repo, ledger_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, estimated_qty=5, unit_cost=Decimal("100.00"),
    )

    # dispatch 後 1 筆 ESTIMATED entry
    entries = _get_ledger_entries_for_mr(ledger_repo, mr_id)
    assert len(entries) == 1
    assert entries[0].status is CostLedgerStatus.ESTIMATED
    assert entries[0].amount == Decimal("500.00")  # 5 × 100

    # 退料 2 → 寫第 2 筆 entry，amount = -(2 × 100) = -200，status=ESTIMATED
    mr_repo.add_return(
        request_id=mr_id,
        item_id=item_id,
        qty=2,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )

    entries = _get_ledger_entries_for_mr(ledger_repo, mr_id)
    assert len(entries) == 2
    offsets = [e for e in entries if e.amount < 0]
    assert len(offsets) == 1
    off = offsets[0]
    assert off.amount == Decimal("-200.00")
    assert off.status is CostLedgerStatus.ESTIMATED
    assert off.category is CostLedgerCategory.MATERIAL
    assert off.source_event_id == mr_id
    assert off.source_type is CostLedgerSourceType.MATERIAL_REQUEST
    # offset 的 source_item_id 對齊原 dispatch entry（即 MR line item id）
    dispatch = [e for e in entries if e.amount > 0][0]
    assert off.source_item_id == dispatch.source_item_id


# ─────────────────────────────────────────────────────────────────────────
# Happy path — 沖銷 entry 在 CONFIRMED state（issue 主要修正場景）
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_writes_confirmed_ledger_offset_when_dispatch_already_confirmed(repos):
    """退料發生在工單 finish 之後 → 原 entry 是 CONFIRMED，offset 也 CONFIRMED。

    這是 WMOM-20260509-F1 主要修正的場景：月報 ``summary(status=CONFIRMED)`` 在
    退料前已含 dispatch 金額，退料後必須有對應的 negative CONFIRMED entry 才會
    自動扣回；否則月報材料成本偏高。
    """
    inv_repo, mr_repo, ledger_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, estimated_qty=5, unit_cost=Decimal("100.00"),
        farm_id="changhua",
    )

    # 模擬 wo finish hook：把 dispatch entry 翻 ESTIMATED → CONFIRMED
    dispatch_entries = _get_ledger_entries_for_mr(ledger_repo, mr_id)
    assert len(dispatch_entries) == 1
    confirmed = ledger_repo.confirm_entry(
        dispatch_entries[0].id, new_amount=Decimal("500.00")
    )
    assert confirmed.status is CostLedgerStatus.CONFIRMED

    # confirm 前 summary
    summary_before = ledger_repo.summary_by_category(
        farm_id="changhua", status=CostLedgerStatus.CONFIRMED,
    )
    assert summary_before[CostLedgerCategory.MATERIAL] == Decimal("500.00")

    # 退料 2 → 寫 offset CONFIRMED
    mr_repo.add_return(
        request_id=mr_id,
        item_id=item_id,
        qty=2,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )

    # 找到 offset entry，且 CONFIRMED summary 正確扣回
    entries = _get_ledger_entries_for_mr(ledger_repo, mr_id)
    assert len(entries) == 2
    offsets = [e for e in entries if e.amount < 0]
    assert len(offsets) == 1
    off = offsets[0]
    assert off.status is CostLedgerStatus.CONFIRMED
    assert off.confirmed_at is not None
    assert off.amount == Decimal("-200.00")

    summary_after = ledger_repo.summary_by_category(
        farm_id="changhua", status=CostLedgerStatus.CONFIRMED,
    )
    # 500 - 200 = 300（退料正確扣回）
    assert summary_after[CostLedgerCategory.MATERIAL] == Decimal("300.00")


# ─────────────────────────────────────────────────────────────────────────
# find_for_mr_item 在退料後仍能找到 dispatch entry（Must-fix #1 regression）
# ─────────────────────────────────────────────────────────────────────────


def test_find_for_mr_item_returns_dispatch_entry_after_return_not_offset(repos):
    """退料後 ``find_for_mr_item`` 必須回傳原 dispatch entry，**不** raise
    ``MultipleResultsFound``，且**不**錯回傳 offset entry。

    這是本 fix 必須對應的 regression test：dispatch entry 與 offset entry 共用同
    ``(source_event_id, source_item_id, source_type)``，若 `find_for_mr_item` 沒
    加 `amount > 0` filter 會炸 — wo finish hook 在退料後就無法 confirm ledger。
    """
    inv_repo, mr_repo, ledger_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, estimated_qty=5, unit_cost=Decimal("100.00"),
    )
    # 抓 MR line item id（find_for_mr_item 用的 item_id 是 line item id 不是
    # inventory item_id）
    entries_before = _get_ledger_entries_for_mr(ledger_repo, mr_id)
    assert len(entries_before) == 1
    mr_item_id = entries_before[0].source_item_id
    assert mr_item_id is not None

    # 退料寫 offset entry
    mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=2,
        reason=ReturnReason.SURPLUS, return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )
    entries_after = _get_ledger_entries_for_mr(ledger_repo, mr_id)
    assert len(entries_after) == 2

    # find_for_mr_item 不應 raise，且只回傳 dispatch entry（amount > 0）
    found = ledger_repo.find_for_mr_item(mr_id, mr_item_id)
    assert found is not None
    assert found.amount > 0
    assert found.amount == Decimal("500.00")


# ─────────────────────────────────────────────────────────────────────────
# locked_unit_cost 不變式 — 不重新查 inventory
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_offset_uses_original_locked_unit_cost_not_current(repos):
    """退料 offset 用 dispatch 當下的 locked_unit_cost，不重新查 inventory。

    A5 review fix #1 規則：估計 / 實際 / 沖銷必須同基礎（會計做帳要求），否則
    月報差異分析失效。
    """
    inv_repo, mr_repo, ledger_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, estimated_qty=5, unit_cost=Decimal("100.00"),
    )

    # 模擬 dispatch 後 inventory unit_cost 暴漲到 300（M5 採購漲價）
    with mr_repo._sessionmaker() as sess:
        from modules.workflow.repository.inventory_orm import InventoryItemORM
        inv = sess.get(InventoryItemORM, str(item_id))
        inv.unit_cost = Decimal("300.00")
        sess.commit()

    mr_repo.add_return(
        request_id=mr_id,
        item_id=item_id,
        qty=2,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )

    entries = _get_ledger_entries_for_mr(ledger_repo, mr_id)
    offsets = [e for e in entries if e.amount < 0]
    assert len(offsets) == 1
    # 用 dispatch 當下的 100，不是當前 300：-(2 × 100) = -200
    assert offsets[0].amount == Decimal("-200.00")
    assert offsets[0].locked_unit_cost == Decimal("100.00")


# ─────────────────────────────────────────────────────────────────────────
# 多次退料（cumulative）
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_multiple_returns_each_writes_own_offset(repos):
    """同 MR + 同 item 多次退料 → 每次都寫獨立 offset entry（保留 audit trail）。"""
    inv_repo, mr_repo, ledger_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, estimated_qty=5, unit_cost=Decimal("100.00"),
        farm_id="changhua",
    )

    # 第一次退 1
    mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=1,
        reason=ReturnReason.SURPLUS, return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )
    # 第二次退 2
    mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=2,
        reason=ReturnReason.WRONG_PART, return_to_kind=StockKind.USED,
        returned_by=uuid4(),
    )

    entries = _get_ledger_entries_for_mr(ledger_repo, mr_id)
    offsets = sorted(
        (e for e in entries if e.amount < 0),
        key=lambda e: e.amount,  # -200 < -100
    )
    assert len(offsets) == 2
    assert offsets[0].amount == Decimal("-200.00")
    assert offsets[1].amount == Decimal("-100.00")

    # summary 仍能正確算（500 - 100 - 200 = 200，含 estimated）
    summary = ledger_repo.summary_by_category(farm_id="changhua")
    assert summary[CostLedgerCategory.MATERIAL] == Decimal("200.00")


# ─────────────────────────────────────────────────────────────────────────
# 邊界 — 沒有 dispatch entry（罕見 corner case）
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_skips_ledger_offset_when_no_dispatch_entry(repos, caplog):
    """退料時找不到對應 dispatch entry → log warning + 不寫 offset，但 stock 仍加回。

    精確模擬 corner case：「dispatch atomic 半途失敗，status 卻已被外力寫成
    DISPATCHED + stock 已被扣，但 ledger entry 沒寫成」。這是 review fix #2
    指出的精確場景（不是 CREATED 狀態的 bypass — `add_return` 對 status 無守衛
    是真的，但本測試專門驗的是 ledger 缺失而非 status 缺失）。
    """
    import logging

    from modules.workflow.repository.inventory_orm import MaterialRequestORM

    caplog.set_level(logging.WARNING)
    inv_repo, mr_repo, ledger_repo = repos

    # 建 MR + 走 happy path 到 APPROVED，但**不** dispatch_request（不寫 ledger）
    wh = inv_repo.create_warehouse(farm_id="f", name="W", is_default=True)
    item = inv_repo.create_item(
        sku="A", name="a", description="a", unit="piece",
        farm_id="f", warehouse_id=wh.id, unit_cost=Decimal("100.00"),
        stock_new=10,
    )
    mr = mr_repo.create(
        farm_id="f", requester_id=uuid4(),
        items=[(item.id, 5, StockKind.NEW)],
    )
    mr_repo.transition(mr.id, "submit_for_approval")
    mr_repo.transition(mr.id, "approve_all")

    # 模擬 dispatch atomic 半途失敗的 corner case：手動把 status 設 DISPATCHED +
    # stock 扣掉（模擬「stock 扣了但 ledger 沒寫成」），不走 dispatch_request
    with mr_repo._sessionmaker() as sess:
        mr_orm = sess.get(MaterialRequestORM, str(mr.id))
        mr_orm.status = MaterialRequestStatus.DISPATCHED.value
        sess.commit()
    # 直接扣 stock 模擬 dispatch 寫一半（用 atomic helper 確保 stock 正確扣）
    from modules.workflow.repository.inventory_repository import (
        apply_stock_delta_in_session,
    )
    with mr_repo._sessionmaker() as sess:
        apply_stock_delta_in_session(
            sess, item_id=item.id, kind=StockKind.NEW, delta=-5,
        )
        sess.commit()

    stock_before_return = inv_repo.get_item(item.id).stock_new
    assert _count_all_ledger_entries(ledger_repo, "f") == 0  # 沒任何 dispatch entry

    # 退料應 succeed（stock 加回），但不寫 ledger
    mr_repo.add_return(
        request_id=mr.id, item_id=item.id, qty=2,
        reason=ReturnReason.SURPLUS, return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )
    assert inv_repo.get_item(item.id).stock_new == stock_before_return + 2
    assert _count_all_ledger_entries(ledger_repo, "f") == 0

    # 有 log warning
    warnings = [r for r in caplog.records if "ledger offset skipped" in r.message]
    assert len(warnings) == 1


# ─────────────────────────────────────────────────────────────────────────
# Atomic — ledger 寫失敗時 stock 一起 rollback
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_rolls_back_stock_when_ledger_insert_fails(repos):
    """Ledger insert 半路 raise → stock 不應加回（atomic 不變式）。"""
    inv_repo, mr_repo, ledger_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo, estimated_qty=5, unit_cost=Decimal("100.00"),
    )
    stock_before_return = inv_repo.get_item(item_id).stock_new
    ledger_count_before = len(_get_ledger_entries_for_mr(ledger_repo, mr_id))

    # patch insert_in_session 讓它 raise
    with patch(
        "modules.cost.repository.cost_ledger.insert_in_session",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            mr_repo.add_return(
                request_id=mr_id, item_id=item_id, qty=2,
                reason=ReturnReason.SURPLUS, return_to_kind=StockKind.NEW,
                returned_by=uuid4(),
            )

    # Stock 沒變 + ledger 沒新 entry + 沒 MaterialReturn record
    assert inv_repo.get_item(item_id).stock_new == stock_before_return
    assert len(_get_ledger_entries_for_mr(ledger_repo, mr_id)) == ledger_count_before
