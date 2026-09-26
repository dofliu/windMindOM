"""DayWorkFormRepository tests — get-or-create + append-activity + query（WMOM-20260505-21）。"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.workflow.domain.day_work_form import ActivityEntry, ActivityKind
from modules.workflow.repository.day_work_form_repository import (
    DayWorkFormRepository,
    get_day_work_form_repository,
)
from modules.workflow.repository.work_order_repository import (
    clear_engine_cache_for_test,
)


@pytest.fixture
def repo(tmp_path) -> DayWorkFormRepository:
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")
    yield get_day_work_form_repository(db_path)
    clear_engine_cache_for_test()


WORK_DATE = date(2026, 5, 5)


def _get_or_create(repo, **overrides):
    base = dict(farm_id="changhua", employee_id=uuid4(), work_date=WORK_DATE)
    base.update(overrides)
    return repo.get_or_create_for_date(**base)


# ─────────────────────────────────────────────────────────────────────────
# get_or_create_for_date
# ─────────────────────────────────────────────────────────────────────────


def test_get_or_create_returns_uuid_and_empty_activities(repo):
    form = _get_or_create(repo)
    assert isinstance(form.id, UUID)
    assert form.activities == []
    assert form.notes == ""


def test_get_or_create_idempotent_same_natural_key(repo):
    """同一 (farm_id, employee_id, work_date) 重複呼叫回同一份日誌（不重複建立）。"""
    employee_id = uuid4()
    first = _get_or_create(repo, employee_id=employee_id)
    second = _get_or_create(repo, employee_id=employee_id)
    assert first.id == second.id


def test_get_or_create_different_employee_creates_separate_form(repo):
    a = _get_or_create(repo, employee_id=uuid4())
    b = _get_or_create(repo, employee_id=uuid4())
    assert a.id != b.id


def test_get_or_create_different_date_creates_separate_form(repo):
    employee_id = uuid4()
    a = _get_or_create(repo, employee_id=employee_id, work_date=WORK_DATE)
    b = _get_or_create(
        repo, employee_id=employee_id, work_date=WORK_DATE + timedelta(days=1)
    )
    assert a.id != b.id


def test_get_or_create_stores_created_by(repo):
    created_by = uuid4()
    form = _get_or_create(repo, created_by=created_by)
    assert form.created_by == created_by


# ─────────────────────────────────────────────────────────────────────────
# append_activity
# ─────────────────────────────────────────────────────────────────────────


def test_append_activity_adds_entry(repo):
    form = _get_or_create(repo)
    entry = ActivityEntry(kind=ActivityKind.PATROL, area="機艙")
    updated = repo.append_activity(form.id, entry)
    assert len(updated.activities) == 1
    assert updated.activities[0].kind is ActivityKind.PATROL
    assert updated.activities[0].area == "機艙"


def test_append_activity_preserves_previous_entries(repo):
    """累加語意——第二筆不覆蓋第一筆。"""
    form = _get_or_create(repo)
    repo.append_activity(form.id, ActivityEntry(kind=ActivityKind.PATROL, area="機艙"))
    updated = repo.append_activity(
        form.id, ActivityEntry(kind=ActivityKind.TRAINING, topic="高空作業安全")
    )
    assert len(updated.activities) == 2
    assert updated.activities[0].kind is ActivityKind.PATROL
    assert updated.activities[1].kind is ActivityKind.TRAINING


def test_append_activity_completed_wo_roundtrips_uuid(repo):
    form = _get_or_create(repo)
    wo_id = uuid4()
    updated = repo.append_activity(
        form.id, ActivityEntry(kind=ActivityKind.COMPLETED_WO, wo_id=wo_id)
    )
    assert updated.activities[0].wo_id == wo_id


def test_append_activity_invalid_entry_raises_before_persist(repo):
    """缺必填欄位的 entry 在寫入前就 raise，不留半套資料。"""
    form = _get_or_create(repo)
    bad_entry = ActivityEntry(kind=ActivityKind.PATROL)  # 缺 area
    with pytest.raises(ValueError, match="area"):
        repo.append_activity(form.id, bad_entry)
    reloaded = repo.get(form.id)
    assert reloaded.activities == []


def test_append_activity_not_found_raises_lookup_error(repo):
    with pytest.raises(LookupError):
        repo.append_activity(uuid4(), ActivityEntry(kind=ActivityKind.PATROL, area="機艙"))


def test_append_activity_updates_updated_at(repo):
    form = _get_or_create(repo)
    updated = repo.append_activity(
        form.id, ActivityEntry(kind=ActivityKind.PATROL, area="機艙")
    )
    assert updated.updated_at >= form.updated_at


# ─────────────────────────────────────────────────────────────────────────
# get / get_by_date
# ─────────────────────────────────────────────────────────────────────────


def test_get_returns_none_when_not_found(repo):
    assert repo.get(uuid4()) is None


def test_get_by_date_returns_none_when_not_created(repo):
    """純讀取——尚未 get_or_create 過的日期不會被動生成。"""
    assert (
        repo.get_by_date(farm_id="changhua", employee_id=uuid4(), work_date=WORK_DATE)
        is None
    )


def test_get_by_date_finds_existing(repo):
    employee_id = uuid4()
    created = _get_or_create(repo, employee_id=employee_id)
    found = repo.get_by_date(
        farm_id="changhua", employee_id=employee_id, work_date=WORK_DATE
    )
    assert found.id == created.id


# ─────────────────────────────────────────────────────────────────────────
# list
# ─────────────────────────────────────────────────────────────────────────


def test_list_returns_all_for_farm(repo):
    _get_or_create(repo, employee_id=uuid4())
    _get_or_create(repo, employee_id=uuid4())
    items, total = repo.list(farm_id="changhua")
    assert total == 2
    assert len(items) == 2


def test_list_filters_by_employee(repo):
    employee_id = uuid4()
    _get_or_create(repo, employee_id=employee_id)
    _get_or_create(repo, employee_id=uuid4())
    items, total = repo.list(farm_id="changhua", employee_id=employee_id)
    assert total == 1
    assert items[0].employee_id == employee_id


def test_list_filters_by_date_range(repo):
    employee_id = uuid4()
    _get_or_create(repo, employee_id=employee_id, work_date=date(2026, 5, 1))
    _get_or_create(repo, employee_id=employee_id, work_date=date(2026, 5, 10))
    items, total = repo.list(
        farm_id="changhua",
        date_from=date(2026, 5, 5),
        date_to=date(2026, 5, 31),
    )
    assert total == 1
    assert items[0].work_date == date(2026, 5, 10)


def test_list_orders_by_date_descending(repo):
    employee_id = uuid4()
    _get_or_create(repo, employee_id=employee_id, work_date=date(2026, 5, 1))
    _get_or_create(repo, employee_id=employee_id, work_date=date(2026, 5, 10))
    items, _ = repo.list(farm_id="changhua")
    assert items[0].work_date == date(2026, 5, 10)
    assert items[1].work_date == date(2026, 5, 1)


def test_list_scoped_to_farm(repo):
    _get_or_create(repo, farm_id="changhua")
    _get_or_create(repo, farm_id="other_farm")
    items, total = repo.list(farm_id="changhua")
    assert total == 1
