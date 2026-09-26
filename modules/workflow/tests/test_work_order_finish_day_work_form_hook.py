"""``work_order.approve_all`` → day_work_form 自動寫入 hook test（WMOM-20260926-01 item 2）。

對應 [ISSUES.md](../../../ISSUES.md) WMOM-20260926-01 item 2 + work-log
``work-logs/2026-09/2026-09-26-day-work-form-read-ownership.md`` 下次接手指南：
掛點是 ``WorkOrderRepository.transition()`` 內部 ``action == "approve_all"``，同時涵蓋
``approval_router`` 簽核鏈自動觸發與 ``work_order_router`` ``/approve`` 直接入口兩條路徑
（兩者都直接呼叫 ``repo.transition()``，不經過 router 層 ``_run_transition``）。
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.workflow.domain import FollowupKind, WorkOrderStatus, WorkOrderType
from modules.workflow.domain.day_work_form import ActivityKind
from modules.workflow.repository import WorkOrderRepository, get_repository
from modules.workflow.repository.day_work_form_repository import (
    get_day_work_form_repository,
)
from modules.workflow.repository.work_order_repository import (
    _TAIPEI_TZ,
    clear_engine_cache_for_test,
)


@pytest.fixture
def repo(tmp_path) -> WorkOrderRepository:
    """Fresh repository on tmp DB（每個 test 一個全新 schema + clean cache）。"""
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")
    yield get_repository(db_path)
    clear_engine_cache_for_test()


def _make(repo, **overrides):
    base = dict(
        farm_id="台中港曲風場",
        turbine_id="WT001",
        type=WorkOrderType.CORRECTIVE,
        title="軸承過熱",
        description="主軸承溫度 75°C",
    )
    base.update(overrides)
    return repo.create(**base)


def _run_full_lifecycle_to_closed(repo, assignee_id):
    """走完整生命週期到 CLOSED（dispatch → start_work → finish → approve_all）。"""
    wo = _make(repo, assignee_id=assignee_id)
    repo.transition(wo.id, "dispatch", actor_id=assignee_id)
    repo.transition(wo.id, "start_work")
    repo.transition(
        wo.id, "finish", actual_hours=2.0, followup_kind=FollowupKind.NONE,
    )
    return repo.transition(wo.id, "approve_all")


def _today_taipei() -> date:
    from datetime import datetime

    return datetime.now(tz=_TAIPEI_TZ).date()


def test_approve_all_appends_completed_wo_activity(repo, tmp_path):
    assignee = uuid4()
    final = _run_full_lifecycle_to_closed(repo, assignee)
    assert final.status == WorkOrderStatus.CLOSED

    dwf_repo = get_day_work_form_repository(str(tmp_path / "wind_farm.db"))
    form = dwf_repo.get_by_date(
        farm_id="台中港曲風場", employee_id=assignee, work_date=_today_taipei()
    )
    assert form is not None
    assert len(form.activities) == 1
    entry = form.activities[0]
    assert entry.kind == ActivityKind.COMPLETED_WO
    assert entry.wo_id == final.id
    assert entry.note == final.business_key


def test_approve_all_via_work_order_router_approve_endpoint_also_appends(
    repo, tmp_path,
):
    """``/work-orders/{id}/approve`` 直接入口（非簽核鏈）也要覆蓋到——兩者都經
    ``WorkOrderRepository.transition()``，本質上與 approval_router 路徑同一段程式碼，
    這裡直接驗證 repository 層 API（router 層另有 `_run_transition` 包裝，行為一致）。
    """
    assignee = uuid4()
    wo = _make(repo, assignee_id=assignee)
    repo.transition(wo.id, "dispatch", actor_id=assignee)
    repo.transition(wo.id, "start_work")
    repo.transition(wo.id, "finish", actual_hours=1.5, followup_kind=FollowupKind.NONE)
    # 模擬 work_order_router.approve() 內部呼叫（不經 approval_router 簽核鏈）
    final = repo.transition(wo.id, "approve_all")
    assert final.status == WorkOrderStatus.CLOSED

    dwf_repo = get_day_work_form_repository(str(tmp_path / "wind_farm.db"))
    form = dwf_repo.get_by_date(
        farm_id="台中港曲風場", employee_id=assignee, work_date=_today_taipei()
    )
    assert form is not None
    assert len(form.activities) == 1
    assert form.activities[0].kind == ActivityKind.COMPLETED_WO


def test_approve_all_two_work_orders_same_day_accumulates_activities(repo, tmp_path):
    """同一員工同一天完工兩張工單 → 累加成同一份日誌兩筆 activity（natural key idempotent）。"""
    assignee = uuid4()
    first = _run_full_lifecycle_to_closed(repo, assignee)
    second = _run_full_lifecycle_to_closed(repo, assignee)

    dwf_repo = get_day_work_form_repository(str(tmp_path / "wind_farm.db"))
    form = dwf_repo.get_by_date(
        farm_id="台中港曲風場", employee_id=assignee, work_date=_today_taipei()
    )
    assert form is not None
    assert len(form.activities) == 2
    wo_ids = {entry.wo_id for entry in form.activities}
    assert wo_ids == {first.id, second.id}


def test_approve_all_without_assignee_does_not_raise_and_creates_no_form(
    repo, tmp_path,
):
    """理論上 ``start_work`` guard 已強制 assignee_id 非 None，但這裡直接呼叫私有
    hook 方法模擬「萬一」情境（防禦性檢查），確認 no-op 不拋例外、不建日誌。
    """
    wo = _make(repo)  # 未指派
    # 走完整流程會被 start_work guard 擋（assignee_id 必填），這裡繞過去直接測 hook 本身
    repo._record_completed_wo_activity(wo)  # type: ignore[attr-defined]

    dwf_repo = get_day_work_form_repository(str(tmp_path / "wind_farm.db"))
    forms, total = dwf_repo.list(farm_id="台中港曲風場")
    assert total == 0
    assert forms == []


def test_approve_all_day_work_form_failure_does_not_break_transition(
    repo, tmp_path, monkeypatch, caplog,
):
    """day_work_form 寫入失敗（模擬 DB lock / 其他例外）不應讓已 commit 的工單關閉本身失敗。"""
    assignee = uuid4()
    wo = _make(repo, assignee_id=assignee)
    repo.transition(wo.id, "dispatch", actor_id=assignee)
    repo.transition(wo.id, "start_work")
    repo.transition(wo.id, "finish", actual_hours=1.0, followup_kind=FollowupKind.NONE)

    def _boom(self, *args, **kwargs):
        raise RuntimeError("simulated DB lock")

    monkeypatch.setattr(
        "modules.workflow.repository.day_work_form_repository."
        "DayWorkFormRepository.get_or_create_for_date",
        _boom,
    )

    with caplog.at_level(logging.ERROR):
        final = repo.transition(wo.id, "approve_all")

    assert final.status == WorkOrderStatus.CLOSED
    assert final.closed_at is not None
    assert any("day_work_form 自動寫入失敗" in r.message for r in caplog.records)

    # 工單本身狀態確實已 persist（不是靠例外被吞掉才「看起來」成功）
    refetch = repo.get(wo.id)
    assert refetch.status == WorkOrderStatus.CLOSED
