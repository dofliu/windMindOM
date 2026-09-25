"""inspection_scheduler service tests — 到期 spawn 工單 + 冪等（WMOM-20260505-22）。"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.workflow.domain import WorkOrderType
from modules.workflow.domain.inspection_schedule import Recurrence
from modules.workflow.repository.inspection_repository import get_inspection_repository
from modules.workflow.repository.work_order_repository import (
    clear_engine_cache_for_test,
    get_repository,
)
from modules.workflow.services.inspection_scheduler import run_inspection_scheduler


UTC = timezone.utc


@pytest.fixture
def repos(tmp_path):
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")
    inspection_repo = get_inspection_repository(db_path)
    work_order_repo = get_repository(db_path)
    yield inspection_repo, work_order_repo
    clear_engine_cache_for_test()


def _create_schedule(inspection_repo, **overrides):
    base = dict(
        farm_id="changhua",
        turbine_id="WT-01",
        title="塔筒螺栓檢查",
        description="每月一次塔筒螺栓扭力檢查",
        recurrence=Recurrence.MONTHLY,
        first_due_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    base.update(overrides)
    return inspection_repo.create(**base)


def test_spawns_work_order_for_due_schedule(repos):
    inspection_repo, work_order_repo = repos
    sched = _create_schedule(inspection_repo)
    as_of = datetime(2026, 2, 1, tzinfo=UTC)

    spawned = run_inspection_scheduler(
        inspection_repo, work_order_repo, "changhua", as_of=as_of
    )

    assert len(spawned) == 1
    assert spawned[0].schedule_id == sched.id
    assert spawned[0].turbine_id == "WT-01"

    wo = work_order_repo.get(spawned[0].work_order_id)
    assert wo is not None
    assert wo.type is WorkOrderType.INSPECTION
    assert wo.turbine_id == "WT-01"
    assert "塔筒螺栓檢查" in wo.title


def test_ignores_not_yet_due_schedule(repos):
    inspection_repo, work_order_repo = repos
    _create_schedule(inspection_repo, first_due_at=datetime(2026, 12, 1, tzinfo=UTC))
    as_of = datetime(2026, 2, 1, tzinfo=UTC)

    spawned = run_inspection_scheduler(
        inspection_repo, work_order_repo, "changhua", as_of=as_of
    )
    assert spawned == []


def test_ignores_inactive_schedule(repos):
    inspection_repo, work_order_repo = repos
    sched = _create_schedule(inspection_repo)
    inspection_repo.set_active(sched.id, False)
    as_of = datetime(2026, 2, 1, tzinfo=UTC)

    spawned = run_inspection_scheduler(
        inspection_repo, work_order_repo, "changhua", as_of=as_of
    )
    assert spawned == []


def test_advances_next_due_at_after_spawn(repos):
    inspection_repo, work_order_repo = repos
    sched = _create_schedule(inspection_repo)
    as_of = datetime(2026, 2, 1, tzinfo=UTC)

    run_inspection_scheduler(inspection_repo, work_order_repo, "changhua", as_of=as_of)

    updated = inspection_repo.get(sched.id)
    assert updated.next_due_at == as_of + timedelta(days=30)


def test_idempotent_second_call_same_cycle_does_not_respawn(repos):
    """同一到期週期內重複呼叫不會重複 spawn（next_due_at 已推進到未來）。"""
    inspection_repo, work_order_repo = repos
    _create_schedule(inspection_repo)
    as_of = datetime(2026, 2, 1, tzinfo=UTC)

    first = run_inspection_scheduler(
        inspection_repo, work_order_repo, "changhua", as_of=as_of
    )
    second = run_inspection_scheduler(
        inspection_repo, work_order_repo, "changhua", as_of=as_of
    )

    assert len(first) == 1
    assert second == []


def test_multiple_due_schedules_all_spawn(repos):
    inspection_repo, work_order_repo = repos
    _create_schedule(inspection_repo, turbine_id="WT-01")
    _create_schedule(inspection_repo, turbine_id="WT-02")
    _create_schedule(inspection_repo, turbine_id="WT-03", first_due_at=datetime(2026, 12, 1, tzinfo=UTC))
    as_of = datetime(2026, 2, 1, tzinfo=UTC)

    spawned = run_inspection_scheduler(
        inspection_repo, work_order_repo, "changhua", as_of=as_of
    )
    assert {s.turbine_id for s in spawned} == {"WT-01", "WT-02"}


def test_only_processes_given_farm(repos):
    inspection_repo, work_order_repo = repos
    _create_schedule(inspection_repo, farm_id="changhua")
    _create_schedule(inspection_repo, farm_id="miaoli")
    as_of = datetime(2026, 2, 1, tzinfo=UTC)

    spawned = run_inspection_scheduler(
        inspection_repo, work_order_repo, "changhua", as_of=as_of
    )
    assert len(spawned) == 1


def test_skips_schedule_when_turbine_already_has_max_open_work_orders(repos):
    """撞 multi-WO constraint（該風機已有 3 張 OPEN 工單）時跳過，
    next_due_at **不推進**（下次呼叫會重試，不會悄悄漏掉這次定檢）。"""
    inspection_repo, work_order_repo = repos
    sched = _create_schedule(inspection_repo, turbine_id="WT-01")

    from modules.workflow.domain import Priority

    for i in range(3):
        work_order_repo.create(
            farm_id="changhua",
            turbine_id="WT-01",
            type=WorkOrderType.CORRECTIVE,
            title=f"既有工單 {i}",
            description="佔滿 OPEN 額度",
            priority=Priority.NORMAL,
            source_alarm_code=f"ALM-{i}",
        )

    as_of = datetime(2026, 2, 1, tzinfo=UTC)
    spawned = run_inspection_scheduler(
        inspection_repo, work_order_repo, "changhua", as_of=as_of
    )

    assert spawned == []
    unchanged = inspection_repo.get(sched.id)
    assert unchanged.next_due_at == sched.next_due_at
    assert unchanged.last_spawned_work_order_id is None


def test_skips_schedule_with_invalid_recurrence_config_without_crashing(repos):
    """Review must-fix 第三層防禦：即使有筆排程繞過 repository 的公開 API（例如
    直接改 DB）落入無效狀態（``custom_days`` + ``interval_days=None``），scheduler
    也必須優雅跳過，不能建了工單才在 ``record_spawn`` 炸開 500、留下孤兒工單。

    直接戳 ORM（略過 ``InspectionScheduleRepository.create``/``update_metadata``
    的驗證）模擬這種「非本次修法涵蓋路徑」造成的髒資料，驗證防禦層真的擋得住。
    """
    inspection_repo, work_order_repo = repos
    sched = _create_schedule(inspection_repo, recurrence=Recurrence.MONTHLY)

    from modules.workflow.repository.inspection_orm import InspectionScheduleORM

    with inspection_repo._sessionmaker() as sess:  # noqa: SLF001 — 測試刻意繞過驗證
        orm = sess.get(InspectionScheduleORM, str(sched.id))
        orm.recurrence = Recurrence.CUSTOM_DAYS.value
        orm.interval_days = None
        sess.commit()

    as_of = datetime(2026, 2, 1, tzinfo=UTC)
    spawned = run_inspection_scheduler(
        inspection_repo, work_order_repo, "changhua", as_of=as_of
    )

    assert spawned == []
    # 沒有建立任何孤兒工單。
    items, total = work_order_repo.list(farm_id="changhua")
    assert total == 0
    # next_due_at 沒推進（下次修正排程設定後會自然重試）。
    unchanged = inspection_repo.get(sched.id)
    assert unchanged.next_due_at == sched.next_due_at


def test_default_as_of_uses_now(repos):
    """未帶 as_of 時用現在時間——過去到期的排程仍會被找到。"""
    inspection_repo, work_order_repo = repos
    _create_schedule(
        inspection_repo, first_due_at=datetime.now(tz=UTC) - timedelta(days=1)
    )
    spawned = run_inspection_scheduler(inspection_repo, work_order_repo, "changhua")
    assert len(spawned) == 1
