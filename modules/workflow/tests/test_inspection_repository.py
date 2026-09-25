"""InspectionScheduleRepository tests — CRUD + due 查詢 + record_spawn（WMOM-20260505-22）。"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.workflow.domain.inspection_schedule import Recurrence
from modules.workflow.repository.inspection_repository import (
    InspectionScheduleRepository,
    get_inspection_repository,
)
from modules.workflow.repository.work_order_repository import (
    clear_engine_cache_for_test,
)


UTC = timezone.utc


@pytest.fixture
def repo(tmp_path) -> InspectionScheduleRepository:
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")
    yield get_inspection_repository(db_path)
    clear_engine_cache_for_test()


def _create(repo, **overrides):
    base = dict(
        farm_id="changhua",
        turbine_id="WT-01",
        title="塔筒螺栓檢查",
        description="每月一次塔筒螺栓扭力檢查",
        recurrence=Recurrence.MONTHLY,
    )
    base.update(overrides)
    return repo.create(**base)


# ─────────────────────────────────────────────────────────────────────────
# create
# ─────────────────────────────────────────────────────────────────────────


def test_create_returns_uuid_and_defaults(repo):
    sched = _create(repo)
    assert isinstance(sched.id, UUID)
    assert sched.active is True
    assert sched.last_spawned_at is None
    assert sched.last_spawned_work_order_id is None


def test_create_without_first_due_at_defaults_one_cycle_ahead(repo):
    """未帶 first_due_at → next_due_at 約在「現在 + 一個週期」，不會立刻到期。"""
    before = datetime.now(tz=UTC)
    sched = _create(repo, recurrence=Recurrence.MONTHLY)
    after = datetime.now(tz=UTC)
    assert before + timedelta(days=29, hours=23) <= sched.next_due_at
    assert sched.next_due_at <= after + timedelta(days=30, minutes=1)


def test_create_with_explicit_first_due_at(repo):
    due = datetime(2026, 6, 1, tzinfo=UTC)
    sched = _create(repo, first_due_at=due)
    assert sched.next_due_at == due


def test_create_custom_days_requires_interval(repo):
    with pytest.raises(ValueError, match="interval_days"):
        _create(repo, recurrence=Recurrence.CUSTOM_DAYS)


def test_create_custom_days_ok_with_interval(repo):
    due = datetime(2026, 6, 1, tzinfo=UTC)
    sched = _create(
        repo, recurrence=Recurrence.CUSTOM_DAYS, interval_days=45, first_due_at=due
    )
    assert sched.interval_days == 45


def test_create_custom_days_requires_interval_even_with_explicit_first_due_at(repo):
    """Review must-fix：舊版驗證只在算 ``compute_next_due`` 分支（未帶
    ``first_due_at``）才會跑，帶了明確 ``first_due_at`` 會繞過驗證靜默寫入無效
    組合。改成無條件驗證後兩條路徑都要擋。"""
    with pytest.raises(ValueError, match="interval_days"):
        _create(
            repo,
            recurrence=Recurrence.CUSTOM_DAYS,
            first_due_at=datetime(2026, 6, 1, tzinfo=UTC),
        )


def test_create_naive_first_due_at_raises(repo):
    naive = datetime(2026, 6, 1)  # 無 tzinfo
    with pytest.raises(ValueError, match="timezone-aware"):
        _create(repo, first_due_at=naive)


# ─────────────────────────────────────────────────────────────────────────
# get / list
# ─────────────────────────────────────────────────────────────────────────


def test_get_roundtrip(repo):
    created = _create(repo, title="機艙潤滑油檢查")
    fetched = repo.get(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.title == "機艙潤滑油檢查"
    assert fetched.next_due_at == created.next_due_at
    assert fetched.next_due_at.tzinfo is not None


def test_get_not_found_returns_none(repo):
    assert repo.get(uuid4()) is None


def test_list_filters_by_farm(repo):
    _create(repo, farm_id="changhua")
    _create(repo, farm_id="miaoli")
    items, total = repo.list(farm_id="changhua")
    assert total == 1
    assert items[0].farm_id == "changhua"


def test_list_filters_by_turbine(repo):
    _create(repo, turbine_id="WT-01")
    _create(repo, turbine_id="WT-02")
    items, total = repo.list(farm_id="changhua", turbine_id="WT-02")
    assert total == 1
    assert items[0].turbine_id == "WT-02"


def test_list_active_only_excludes_deactivated(repo):
    active = _create(repo)
    inactive = _create(repo)
    repo.set_active(inactive.id, False)
    items, total = repo.list(farm_id="changhua", active_only=True)
    assert total == 1
    assert items[0].id == active.id


def test_list_orders_by_next_due_at_ascending(repo):
    later = _create(repo, first_due_at=datetime(2026, 6, 1, tzinfo=UTC))
    sooner = _create(repo, first_due_at=datetime(2026, 3, 1, tzinfo=UTC))
    items, _total = repo.list(farm_id="changhua")
    assert [i.id for i in items] == [sooner.id, later.id]


def test_list_due_only_requires_as_of(repo):
    with pytest.raises(ValueError, match="as_of"):
        repo.list(farm_id="changhua", due_only=True)


def test_list_due_only_filters_past_due(repo):
    due = _create(repo, first_due_at=datetime(2026, 1, 1, tzinfo=UTC))
    not_due = _create(repo, first_due_at=datetime(2026, 12, 1, tzinfo=UTC))
    as_of = datetime(2026, 6, 1, tzinfo=UTC)
    items, total = repo.list(farm_id="changhua", due_only=True, as_of=as_of)
    assert total == 1
    assert items[0].id == due.id
    assert not_due.id not in [i.id for i in items]


def test_list_due_only_excludes_inactive(repo):
    sched = _create(repo, first_due_at=datetime(2026, 1, 1, tzinfo=UTC))
    repo.set_active(sched.id, False)
    as_of = datetime(2026, 6, 1, tzinfo=UTC)
    items, total = repo.list(farm_id="changhua", due_only=True, as_of=as_of)
    assert total == 0


def test_list_pagination(repo):
    for i in range(5):
        _create(repo, first_due_at=datetime(2026, 1, 1 + i, tzinfo=UTC))
    items, total = repo.list(farm_id="changhua", limit=2, offset=2)
    assert total == 5
    assert len(items) == 2


# ─────────────────────────────────────────────────────────────────────────
# update_metadata
# ─────────────────────────────────────────────────────────────────────────


def test_update_metadata_title(repo):
    sched = _create(repo)
    updated = repo.update_metadata(sched.id, title="新標題")
    assert updated.title == "新標題"
    assert updated.description == sched.description  # 未帶欄位不變


def test_update_metadata_does_not_change_next_due_at(repo):
    """改 recurrence 不會馬上重算到期時間（見 repository docstring 的刻意設計）。"""
    sched = _create(repo, first_due_at=datetime(2026, 6, 1, tzinfo=UTC))
    updated = repo.update_metadata(sched.id, recurrence=Recurrence.ANNUAL)
    assert updated.recurrence is Recurrence.ANNUAL
    assert updated.next_due_at == sched.next_due_at


def test_update_metadata_not_found_raises(repo):
    with pytest.raises(LookupError):
        repo.update_metadata(uuid4(), title="x")


def test_update_metadata_custom_days_without_interval_raises(repo):
    """Review must-fix repro：把一個 MONTHLY（``interval_days=None``）排程 PATCH
    成 ``recurrence=custom_days`` 卻不帶 ``interval_days``，commit 前必須擋下，
    否則排程到期時 ``record_spawn`` 才會炸開（工單已建、``next_due_at`` 沒推進，
    每次呼叫都重複 spawn——見 review 報告實測）。"""
    sched = _create(repo, recurrence=Recurrence.MONTHLY)
    with pytest.raises(ValueError, match="interval_days"):
        repo.update_metadata(sched.id, recurrence=Recurrence.CUSTOM_DAYS)

    # raise 前不 commit：確認 DB 內狀態完全沒被改動（非半套髒資料）。
    unchanged = repo.get(sched.id)
    assert unchanged.recurrence is Recurrence.MONTHLY
    assert unchanged.interval_days is None


def test_update_metadata_custom_days_interval_only_patch_ok(repo):
    """合法組合：排程已是 ``custom_days``，PATCH 只帶 ``interval_days``（沿用既有
    ``recurrence``）——不該被上面新增的驗證誤擋。"""
    sched = _create(
        repo,
        recurrence=Recurrence.CUSTOM_DAYS,
        interval_days=30,
        first_due_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    updated = repo.update_metadata(sched.id, interval_days=60)
    assert updated.interval_days == 60
    assert updated.recurrence is Recurrence.CUSTOM_DAYS


def test_update_metadata_custom_days_with_interval_same_call_ok(repo):
    """合法組合：同一次 PATCH 把 ``recurrence`` 改成 ``custom_days`` 並一併帶
    ``interval_days``。"""
    sched = _create(repo, recurrence=Recurrence.MONTHLY)
    updated = repo.update_metadata(
        sched.id, recurrence=Recurrence.CUSTOM_DAYS, interval_days=45
    )
    assert updated.recurrence is Recurrence.CUSTOM_DAYS
    assert updated.interval_days == 45


# ─────────────────────────────────────────────────────────────────────────
# set_active
# ─────────────────────────────────────────────────────────────────────────


def test_set_active_false_then_true(repo):
    sched = _create(repo)
    off = repo.set_active(sched.id, False)
    assert off.active is False
    on = repo.set_active(sched.id, True)
    assert on.active is True


def test_set_active_not_found_raises(repo):
    with pytest.raises(LookupError):
        repo.set_active(uuid4(), False)


# ─────────────────────────────────────────────────────────────────────────
# record_spawn
# ─────────────────────────────────────────────────────────────────────────


def test_record_spawn_advances_next_due_at(repo):
    sched = _create(
        repo, recurrence=Recurrence.MONTHLY, first_due_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    wo_id = uuid4()
    spawned_at = datetime(2026, 1, 5, tzinfo=UTC)  # 晚了 4 天才被 scheduler 撿到
    updated = repo.record_spawn(sched.id, work_order_id=wo_id, spawned_at=spawned_at)
    assert updated.next_due_at == spawned_at + timedelta(days=30)
    assert updated.last_spawned_at == spawned_at
    assert updated.last_spawned_work_order_id == wo_id


def test_record_spawn_uses_spawned_at_not_old_due_date(repo):
    """推進基準是 spawned_at（呼叫當下），不是舊 next_due_at——避免長期暫停後
    重啟時從舊到期日累加仍然過期（見 repository docstring）。"""
    sched = _create(
        repo, recurrence=Recurrence.MONTHLY, first_due_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    spawned_at = datetime(2026, 6, 1, tzinfo=UTC)  # 遠晚於原本到期日
    updated = repo.record_spawn(
        sched.id, work_order_id=uuid4(), spawned_at=spawned_at
    )
    assert updated.next_due_at == datetime(2026, 7, 1, tzinfo=UTC)


def test_record_spawn_not_found_raises(repo):
    with pytest.raises(LookupError):
        repo.record_spawn(uuid4(), work_order_id=uuid4(), spawned_at=datetime.now(tz=UTC))


def test_record_spawn_naive_datetime_raises(repo):
    sched = _create(repo)
    naive = datetime(2026, 1, 1)
    with pytest.raises(ValueError, match="timezone-aware"):
        repo.record_spawn(sched.id, work_order_id=uuid4(), spawned_at=naive)
