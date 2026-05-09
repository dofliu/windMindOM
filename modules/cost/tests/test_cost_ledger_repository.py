"""CostLedgerRepository tests — query + confirm（WMOM-20260509-05）。"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.cost.repository import (
    CostLedgerCategory,
    CostLedgerEntry,
    CostLedgerRepository,
    CostLedgerSourceType,
    CostLedgerStatus,
    get_cost_ledger_repository,
    insert_in_session,
)
from modules.workflow.repository.work_order_repository import (
    clear_engine_cache_for_test,
)


@pytest.fixture
def repo(tmp_path) -> CostLedgerRepository:
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")
    yield get_cost_ledger_repository(db_path)
    clear_engine_cache_for_test()


def _insert_entry(repo: CostLedgerRepository, **overrides) -> CostLedgerEntry:
    """Helper：用 insert_in_session 寫一筆 ledger entry。"""
    base = dict(
        farm_id="changhua",
        category=CostLedgerCategory.MATERIAL,
        amount=Decimal("450.00"),
        source_event_id=uuid4(),
        source_type=CostLedgerSourceType.MATERIAL_REQUEST,
        status=CostLedgerStatus.ESTIMATED,
    )
    base.update(overrides)
    entry = CostLedgerEntry(**base)
    with repo._sessionmaker() as sess:
        insert_in_session(sess, entry)
        sess.commit()
    return entry


# ─────────────────────────────────────────────────────────────────────────
# Get / List
# ─────────────────────────────────────────────────────────────────────────


def test_get_returns_entry(repo):
    entry = _insert_entry(repo)
    fetched = repo.get(entry.id)
    assert fetched is not None
    assert fetched.id == entry.id
    assert fetched.amount == Decimal("450.00")


def test_get_unknown_returns_none(repo):
    assert repo.get(uuid4()) is None


def test_list_returns_total_and_items(repo):
    for _ in range(3):
        _insert_entry(repo)
    items, total = repo.list(farm_id="changhua")
    assert total == 3
    assert len(items) == 3


def test_list_filter_by_category(repo):
    _insert_entry(repo, category=CostLedgerCategory.MATERIAL)
    _insert_entry(repo, category=CostLedgerCategory.LABOUR)
    _insert_entry(repo, category=CostLedgerCategory.LABOUR)
    items, total = repo.list(farm_id="changhua", category=CostLedgerCategory.LABOUR)
    assert total == 2
    assert all(it.category is CostLedgerCategory.LABOUR for it in items)


def test_list_filter_by_status(repo):
    _insert_entry(repo, status=CostLedgerStatus.ESTIMATED)
    _insert_entry(repo, status=CostLedgerStatus.CONFIRMED)
    items, total = repo.list(
        farm_id="changhua", status=CostLedgerStatus.CONFIRMED
    )
    assert total == 1


def test_list_filter_by_date_range(repo):
    """Test with date filter — relies on recorded_at differences via sleep."""
    e1 = _insert_entry(repo, recorded_at=datetime(2026, 1, 15, tzinfo=timezone.utc))
    e2 = _insert_entry(repo, recorded_at=datetime(2026, 2, 15, tzinfo=timezone.utc))
    items, total = repo.list(
        farm_id="changhua",
        from_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
        to_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
    )
    assert total == 1
    assert items[0].id == e2.id


def test_list_excludes_other_farm(repo):
    _insert_entry(repo, farm_id="changhua")
    _insert_entry(repo, farm_id="other_farm")
    items, total = repo.list(farm_id="changhua")
    assert total == 1


def test_list_pagination(repo):
    for _ in range(5):
        _insert_entry(repo)
    items, total = repo.list(farm_id="changhua", limit=2, offset=1)
    assert total == 5
    assert len(items) == 2


# ─────────────────────────────────────────────────────────────────────────
# find_for_mr_item
# ─────────────────────────────────────────────────────────────────────────


def test_find_for_mr_item_matches_by_event_and_item(repo):
    mr_id = uuid4()
    item_a = uuid4()
    item_b = uuid4()
    _insert_entry(repo, source_event_id=mr_id, source_item_id=item_a, amount=Decimal("100"))
    _insert_entry(repo, source_event_id=mr_id, source_item_id=item_b, amount=Decimal("200"))
    found = repo.find_for_mr_item(mr_id, item_a)
    assert found is not None
    assert found.amount == Decimal("100")


def test_find_for_mr_item_not_found(repo):
    assert repo.find_for_mr_item(uuid4(), uuid4()) is None


# ─────────────────────────────────────────────────────────────────────────
# list_for_subject
# ─────────────────────────────────────────────────────────────────────────


def test_list_for_subject_returns_all_entries(repo):
    mr_id = uuid4()
    _insert_entry(repo, source_event_id=mr_id, source_item_id=uuid4())
    _insert_entry(repo, source_event_id=mr_id, source_item_id=uuid4())
    _insert_entry(repo, source_event_id=uuid4(), source_item_id=uuid4())  # 別張單
    entries = repo.list_for_subject(mr_id, CostLedgerSourceType.MATERIAL_REQUEST)
    assert len(entries) == 2


# ─────────────────────────────────────────────────────────────────────────
# summary_by_category
# ─────────────────────────────────────────────────────────────────────────


def test_summary_groups_and_sums(repo):
    _insert_entry(repo, category=CostLedgerCategory.MATERIAL, amount=Decimal("100.00"))
    _insert_entry(repo, category=CostLedgerCategory.MATERIAL, amount=Decimal("200.00"))
    _insert_entry(repo, category=CostLedgerCategory.LABOUR, amount=Decimal("50.00"))
    summary = repo.summary_by_category(farm_id="changhua")
    assert summary[CostLedgerCategory.MATERIAL] == Decimal("300.00")
    assert summary[CostLedgerCategory.LABOUR] == Decimal("50.00")


def test_summary_status_filter_confirmed_only(repo):
    """status=CONFIRMED 只算 actual cost（給月報結算用）。"""
    _insert_entry(
        repo, category=CostLedgerCategory.MATERIAL, amount=Decimal("100.00"),
        status=CostLedgerStatus.ESTIMATED,
    )
    _insert_entry(
        repo, category=CostLedgerCategory.MATERIAL, amount=Decimal("250.00"),
        status=CostLedgerStatus.CONFIRMED,
    )
    summary = repo.summary_by_category(
        farm_id="changhua", status=CostLedgerStatus.CONFIRMED
    )
    assert summary[CostLedgerCategory.MATERIAL] == Decimal("250.00")


# ─────────────────────────────────────────────────────────────────────────
# confirm_entry
# ─────────────────────────────────────────────────────────────────────────


def test_confirm_entry_flips_status_and_amount(repo):
    entry = _insert_entry(repo, amount=Decimal("450.00"))
    actor = uuid4()
    updated = repo.confirm_entry(
        entry.id, new_amount=Decimal("470.00"), actor_id=actor
    )
    assert updated.status is CostLedgerStatus.CONFIRMED
    assert updated.amount == Decimal("470.00")
    assert updated.confirmed_at is not None
    assert updated.actor_id == actor


def test_confirm_entry_idempotent(repo):
    """Confirm 已 confirmed 的 entry → no-op，amount 不被改回。"""
    entry = _insert_entry(repo, amount=Decimal("100.00"))
    repo.confirm_entry(entry.id, new_amount=Decimal("250.00"))
    # 第二次 confirm with different amount — 應 idempotent，amount 不變
    second = repo.confirm_entry(entry.id, new_amount=Decimal("999.99"))
    assert second.amount == Decimal("250.00")


def test_confirm_entry_unknown_raises(repo):
    with pytest.raises(LookupError):
        repo.confirm_entry(uuid4(), new_amount=Decimal("100"))


def test_confirm_entry_negative_amount_rejected(repo):
    entry = _insert_entry(repo)
    with pytest.raises(ValueError, match="must be >= 0"):
        repo.confirm_entry(entry.id, new_amount=Decimal("-5"))
