"""**WMOM-20260509-F1 acceptance test** — `add_return` 寫 ledger 負向 entry 沖銷。

驗收（issue spec）：
- happy path：dispatch → ledger +amount；return → ledger -amount；月報加總自動沖銷
- locked_unit_cost 用 dispatch 當時的快照（即使 inventory.unit_cost 後來改動也不受影響）
- 部分退料 / 多次退料 → 各自寫獨立 offset entry
- `summary_by_category(status=CONFIRMED)` 退料後正確反映淨成本
- 無 dispatch entry 時（罕見邊界）log warning + 跳過沖銷，**不阻** stock add-back
- ledger insert 失敗 → 整 transaction rollback（stock / return / ledger 三者皆不留）
"""

from __future__ import annotations

import logging
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

# 預先 import 讓 CostLedgerEntryORM 註冊到 Base.metadata；否則第一次 create_all
# 不會建出 cost_ledger_entries 表。
from modules.cost.repository.cost_ledger import (
    CostLedgerCategory,
    CostLedgerEntryORM,
    CostLedgerSourceType,
    CostLedgerStatus,
)
from modules.cost.repository.cost_ledger_repository import (
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
from modules.workflow.repository.inventory_orm import (
    InventoryItemORM,
    MaterialRequestItemORM,
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


def _setup_dispatched_mr(
    inv_repo: InventoryRepository,
    mr_repo: MaterialRequestRepository,
    *,
    initial_stock: int = 10,
    estimated_qty: int = 2,
    unit_cost: Decimal = Decimal("450.00"),
    farm_id: str = "f",
) -> tuple[UUID, UUID]:
    """Helper：建一個已 DISPATCHED 的 MR（dispatch_request 已寫 ledger）。"""
    wh = inv_repo.create_warehouse(farm_id=farm_id, name="W", is_default=True)
    item = inv_repo.create_item(
        sku="X-1",
        name="x",
        description="x",
        unit="piece",
        farm_id=farm_id,
        warehouse_id=wh.id,
        unit_cost=unit_cost,
        stock_new=initial_stock,
    )
    mr = mr_repo.create(
        farm_id=farm_id,
        requester_id=uuid4(),
        items=[(item.id, estimated_qty, StockKind.NEW)],
    )
    mr_repo.transition(mr.id, "submit_for_approval")
    mr_repo.transition(mr.id, "approve_all")
    mr_repo.dispatch_request(mr.id)
    return mr.id, item.id


def _get_ledger_entries(
    mr_repo: MaterialRequestRepository,
) -> list[CostLedgerEntryORM]:
    with mr_repo._sessionmaker() as sess:
        return list(
            sess.execute(
                select(CostLedgerEntryORM).order_by(CostLedgerEntryORM.recorded_at)
            )
            .scalars()
            .all()
        )


# ─────────────────────────────────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_writes_negative_ledger_offset_entry(repos):
    """dispatch 2 × 450 → return 1 → ledger 出現第二筆 amount=-450 CONFIRMED。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo,
        initial_stock=10, estimated_qty=2, unit_cost=Decimal("450.00"),
    )

    # 退料前：1 筆 dispatch entry
    before = _get_ledger_entries(mr_repo)
    assert len(before) == 1
    assert before[0].status == CostLedgerStatus.ESTIMATED.value
    assert Decimal(str(before[0].amount)) == Decimal("900.00")

    # 退料 1 件
    returned_by = uuid4()
    mr_repo.add_return(
        request_id=mr_id,
        item_id=item_id,
        qty=1,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW,
        returned_by=returned_by,
        note="用剩",
    )

    after = _get_ledger_entries(mr_repo)
    assert len(after) == 2

    offset = after[1]  # 後寫的 — 按 recorded_at 排序
    assert offset.id != before[0].id
    assert offset.status == CostLedgerStatus.CONFIRMED.value
    assert offset.category == CostLedgerCategory.MATERIAL.value
    assert offset.source_type == CostLedgerSourceType.MATERIAL_REQUEST.value
    assert offset.source_event_id == str(mr_id)
    # source_item_id 必須對得上 dispatch entry（同 line item）
    assert offset.source_item_id == before[0].source_item_id
    assert Decimal(str(offset.amount)) == Decimal("-450.00")  # -(1 × 450)
    assert Decimal(str(offset.locked_unit_cost)) == Decimal("450.00")
    assert offset.actor_id == str(returned_by)
    assert "退料" in (offset.note or "")
    assert "surplus" in (offset.note or "")
    assert "用剩" in (offset.note or "")  # note 透傳


def test_add_return_offset_uses_dispatch_locked_unit_cost_not_current(repos):
    """dispatch 後 inventory.unit_cost 改動（如進貨價格變了），退料沖銷仍用 dispatch 鎖價。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo,
        initial_stock=10, estimated_qty=2, unit_cost=Decimal("450.00"),
    )

    # 模擬進貨價格漲到 600；直接改 inventory_item ORM（repo 沒 update API 但 DB 改得到）
    with mr_repo._sessionmaker() as sess:
        item_orm = sess.get(InventoryItemORM, str(item_id))
        assert item_orm is not None
        item_orm.unit_cost = Decimal("600.00")
        sess.commit()

    # 退料 1 件 — 沖銷 amount 應該還是 450（dispatch 當時的鎖價）
    mr_repo.add_return(
        request_id=mr_id,
        item_id=item_id,
        qty=1,
        reason=ReturnReason.SURPLUS,
        return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )

    entries = _get_ledger_entries(mr_repo)
    offset = entries[1]
    assert Decimal(str(offset.amount)) == Decimal("-450.00")
    assert Decimal(str(offset.locked_unit_cost)) == Decimal("450.00")


def test_add_return_partial_return_offsets_partial_amount(repos):
    """dispatch 5 × 100 → return 2 → offset = -200（不是 -500）。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo,
        initial_stock=10, estimated_qty=5, unit_cost=Decimal("100.00"),
    )

    mr_repo.add_return(
        request_id=mr_id,
        item_id=item_id,
        qty=2,
        reason=ReturnReason.FAILED_INSTALL,
        return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )

    entries = _get_ledger_entries(mr_repo)
    assert len(entries) == 2
    assert Decimal(str(entries[1].amount)) == Decimal("-200.00")


def test_add_return_multiple_returns_each_writes_own_offset(repos):
    """同一張 MR 連續退兩次 → 各自寫一筆 offset entry（總計 3 筆 ledger）。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo,
        initial_stock=10, estimated_qty=5, unit_cost=Decimal("100.00"),
    )

    mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=2,
        reason=ReturnReason.SURPLUS, return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )
    mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=1,
        reason=ReturnReason.WRONG_PART, return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )

    entries = _get_ledger_entries(mr_repo)
    assert len(entries) == 3
    assert Decimal(str(entries[0].amount)) == Decimal("500.00")    # dispatch
    assert Decimal(str(entries[1].amount)) == Decimal("-200.00")   # return 1
    assert Decimal(str(entries[2].amount)) == Decimal("-100.00")   # return 2
    # 兩筆 offset 都同一個 source_item_id（同 line item）
    assert entries[1].source_item_id == entries[0].source_item_id
    assert entries[2].source_item_id == entries[0].source_item_id


def test_summary_by_category_confirmed_excludes_returned_amount(repos, db_path):
    """月報 query `status=CONFIRMED` 應反映退料沖銷後的淨成本。

    本 test 的 dispatch entry 仍是 ESTIMATED（沒 WO finish hook），但 offset 是
    CONFIRMED → `summary_by_category(status=CONFIRMED)` 只 sum 到 offset 的 -450，
    呈負金額。在真實 lifecycle（test_lifecycle_ledger_confirmation 已有完整鏈路）
    dispatch entry 會被 WO finish hook flip 成 CONFIRMED，淨值 = +900 + (-450) = +450
    （已退掉 1 件的成本）。本 test 聚焦 add_return 自己的責任。
    """
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo,
        initial_stock=10, estimated_qty=2, unit_cost=Decimal("450.00"),
    )

    mr_repo.add_return(
        request_id=mr_id, item_id=item_id, qty=1,
        reason=ReturnReason.SURPLUS, return_to_kind=StockKind.NEW,
        returned_by=uuid4(),
    )

    ledger_repo = get_cost_ledger_repository(db_path)
    summary_confirmed = ledger_repo.summary_by_category(
        farm_id="f", status=CostLedgerStatus.CONFIRMED,
    )
    # CONFIRMED 部分只有 offset entry
    assert summary_confirmed.get(CostLedgerCategory.MATERIAL) == Decimal("-450.00")

    # 全部加總（estimated + confirmed）— 反映尚未 confirm 的 dispatch + offset 的淨值
    summary_all = ledger_repo.summary_by_category(farm_id="f", status=None)
    assert summary_all.get(CostLedgerCategory.MATERIAL) == Decimal("450.00")  # 900 - 450


# ─────────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────────


def test_add_return_without_dispatch_entry_logs_skip(repos, caplog):
    """無 dispatch ledger entry（罕見邊界）→ log warning + 跳過沖銷；stock 仍加回。"""
    inv_repo, mr_repo = repos
    # 不走 dispatch_request — 直接建 MR 留在 DRAFT，再手動扣 stock 後試退料
    wh = inv_repo.create_warehouse(farm_id="f", name="W", is_default=True)
    item = inv_repo.create_item(
        sku="X-1", name="x", description="x", unit="piece",
        farm_id="f", warehouse_id=wh.id, unit_cost=Decimal("450.00"),
        stock_new=5,
    )
    mr = mr_repo.create(
        farm_id="f", requester_id=uuid4(),
        items=[(item.id, 2, StockKind.NEW)],
    )

    before_count = len(_get_ledger_entries(mr_repo))
    assert before_count == 0

    with caplog.at_level(logging.WARNING):
        mr_repo.add_return(
            request_id=mr.id, item_id=item.id, qty=1,
            reason=ReturnReason.OTHER, return_to_kind=StockKind.NEW,
            returned_by=uuid4(),
        )

    # Stock 應加回（+1 → 6）
    assert inv_repo.get_item(item.id).stock_new == 6
    # Ledger 不應寫任何 entry
    assert _get_ledger_entries(mr_repo) == []
    # 應有 warning log
    assert any("no dispatch ledger entry" in r.message for r in caplog.records)


def test_add_return_with_no_matching_mr_line_item_logs_skip(repos, caplog):
    """退料的 item_id 不在 MR 任何 line item 內（資料不一致情境）→ skip + log。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo,
        initial_stock=10, estimated_qty=2, unit_cost=Decimal("450.00"),
    )

    # 建另一個料件，但**不**塞進 MR 的 items（資料不一致：MR 沒這個 line item）
    wh = inv_repo.get_default_warehouse("f")
    assert wh is not None
    other_item = inv_repo.create_item(
        sku="OTHER", name="y", description="y", unit="piece",
        farm_id="f", warehouse_id=wh.id, unit_cost=Decimal("200.00"),
        stock_new=5,
    )

    with caplog.at_level(logging.WARNING):
        mr_repo.add_return(
            request_id=mr_id, item_id=other_item.id, qty=1,
            reason=ReturnReason.OTHER, return_to_kind=StockKind.NEW,
            returned_by=uuid4(),
        )

    # 沖銷被 skip — ledger 還是 1 筆（dispatch 寫的）
    entries = _get_ledger_entries(mr_repo)
    assert len(entries) == 1
    assert Decimal(str(entries[0].amount)) == Decimal("900.00")
    assert any("no MR line item" in r.message for r in caplog.records)


def test_add_return_atomic_rollback_on_ledger_failure(repos):
    """模擬 `insert_in_session` 失敗 → stock add-back + MaterialReturn + ledger 三者皆 rollback。"""
    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo,
        initial_stock=10, estimated_qty=2, unit_cost=Decimal("450.00"),
    )

    stock_before = inv_repo.get_item(item_id).stock_new
    ledger_before = len(_get_ledger_entries(mr_repo))
    with mr_repo._sessionmaker() as sess:
        return_count_before = len(
            sess.execute(
                select(
                    __import__(
                        "modules.workflow.repository.inventory_orm",
                        fromlist=["MaterialReturnORM"],
                    ).MaterialReturnORM
                )
            )
            .scalars()
            .all()
        )

    target = "modules.cost.repository.cost_ledger.insert_in_session"
    with patch(target, side_effect=RuntimeError("simulated ledger failure")):
        with pytest.raises(RuntimeError, match="simulated ledger failure"):
            mr_repo.add_return(
                request_id=mr_id, item_id=item_id, qty=1,
                reason=ReturnReason.SURPLUS, return_to_kind=StockKind.NEW,
                returned_by=uuid4(),
            )

    # Atomicity：stock 不變、ledger 不變、MaterialReturn 不留
    assert inv_repo.get_item(item_id).stock_new == stock_before
    assert len(_get_ledger_entries(mr_repo)) == ledger_before
    with mr_repo._sessionmaker() as sess:
        return_count_after = len(
            sess.execute(
                select(
                    __import__(
                        "modules.workflow.repository.inventory_orm",
                        fromlist=["MaterialReturnORM"],
                    ).MaterialReturnORM
                )
            )
            .scalars()
            .all()
        )
    assert return_count_after == return_count_before


def test_add_return_qty_zero_or_negative_raises_before_ledger_write(repos):
    """qty <= 0 → MaterialRequestRuleViolation；ledger 不應被觸碰。"""
    from modules.workflow.repository.material_request_repository import (
        MaterialRequestRuleViolation,
    )

    inv_repo, mr_repo = repos
    mr_id, item_id = _setup_dispatched_mr(
        inv_repo, mr_repo,
        initial_stock=10, estimated_qty=2, unit_cost=Decimal("450.00"),
    )

    before = _get_ledger_entries(mr_repo)
    with pytest.raises(MaterialRequestRuleViolation):
        mr_repo.add_return(
            request_id=mr_id, item_id=item_id, qty=0,
            reason=ReturnReason.SURPLUS, return_to_kind=StockKind.NEW,
            returned_by=uuid4(),
        )
    after = _get_ledger_entries(mr_repo)
    assert len(after) == len(before)
