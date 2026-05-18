"""Work order state machine transition tests（WMOM-20260504-16）。

涵蓋 DN-01 §2.2 的完整 transition table — 每個 transition 都驗：
- 正例：合法 source state + 必要 kwargs → 成功，狀態進 to_state，side effect 欄位填好
- 反例 1：非法 source state → InvalidTransition
- 反例 2：guard 缺失 kwargs → InvalidTransition
- can_transition / available_actions helper 行為

對齊 walkthrough confirmed 設計：
- Q1 cancel 任何 pre-signoff 階段都可（cancel_reason 必填）
- Q2 finish 帶 followup_kind ∈ {NONE, FOLLOWUP_NEEDED}（二元）
- Q5 onshore start_work 不需 weather_window；offshore caller 才傳 require_weather_window=True
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.workflow.domain import (  # noqa: E402
    FollowupKind,
    InvalidTransition,
    Priority,
    WorkOrder,
    WorkOrderStateMachine,
    WorkOrderStatus,
    WorkOrderType,
)


# ─────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────


def _wo(**overrides) -> WorkOrder:
    base = dict(
        farm_id="台中港曲風場",
        turbine_id="WT001",
        type=WorkOrderType.CORRECTIVE,
        title="bearing high temp",
        description="軸溫 75°C",
        business_key="WO-Z72TC-202607-01",
    )
    base.update(overrides)
    return WorkOrder(**base)


# ─────────────────────────────────────────────────────────────────────────
# can_transition / available_actions
# ─────────────────────────────────────────────────────────────────────────


def test_can_transition_for_draft():
    wo = _wo()
    assert WorkOrderStateMachine.can_transition(wo, "dispatch") is True
    assert WorkOrderStateMachine.can_transition(wo, "cancel") is True
    assert WorkOrderStateMachine.can_transition(wo, "start_work") is False
    assert WorkOrderStateMachine.can_transition(wo, "finish") is False


def test_can_transition_unknown_action():
    wo = _wo()
    assert WorkOrderStateMachine.can_transition(wo, "fly_to_moon") is False


def test_available_actions_for_draft():
    wo = _wo()
    assert set(WorkOrderStateMachine.available_actions(wo)) == {"dispatch", "cancel"}


def test_available_actions_for_in_progress():
    wo = _wo(status=WorkOrderStatus.IN_PROGRESS, assignee_id=uuid4())
    actions = set(WorkOrderStateMachine.available_actions(wo))
    assert actions == {"update_progress", "finish", "cancel"}


def test_available_actions_for_closed_terminal():
    wo = _wo(status=WorkOrderStatus.CLOSED)
    # 終態只剩 reopen（cancel 不可在 CLOSED）
    assert set(WorkOrderStateMachine.available_actions(wo)) == {"reopen"}


# ─────────────────────────────────────────────────────────────────────────
# dispatch
# ─────────────────────────────────────────────────────────────────────────


def test_dispatch_success():
    actor = uuid4()
    wo = _wo(assignee_id=uuid4())  # assignee 須先 set
    WorkOrderStateMachine.transition(wo, "dispatch", actor_id=actor)
    assert wo.status == WorkOrderStatus.DISPATCHED
    assert wo.dispatched_at is not None
    assert wo.dispatched_by == actor


def test_dispatch_requires_assignee():
    wo = _wo()  # no assignee
    with pytest.raises(InvalidTransition, match="assignee_id"):
        WorkOrderStateMachine.transition(wo, "dispatch", actor_id=uuid4())


def test_dispatch_requires_actor_id_for_audit():
    """walkthrough audit 需求：dispatch 必填 actor_id（誰派工的）。"""
    wo = _wo(assignee_id=uuid4())  # assignee 有，但沒給 actor_id
    with pytest.raises(InvalidTransition, match="actor_id"):
        WorkOrderStateMachine.transition(wo, "dispatch")  # 沒 actor_id


def test_dispatch_with_assignee_kwarg_when_wo_has_no_assignee():
    """Hotfix-2026-05-10：派工時用 kwargs 補帶 assignee_id（建單時未指派的常見場景）。

    使用情境：建單者（值班主管）建單時還不知道派誰，DRAFT 留空白；
    後續派工時主管才決定 assignee → 透過 dispatch kwargs 補帶。
    """
    actor = uuid4()
    new_assignee = uuid4()
    wo = _wo()  # no assignee on the work order
    WorkOrderStateMachine.transition(
        wo, "dispatch", actor_id=actor, assignee_id=new_assignee,
    )
    assert wo.status == WorkOrderStatus.DISPATCHED
    assert wo.assignee_id == new_assignee  # ← kwarg 寫入工單
    assert wo.dispatched_by == actor


def test_dispatch_kwarg_assignee_overrides_existing_on_wo():
    """若工單已有 assignee 但 dispatch 又帶 kwarg，以 kwarg 為準（重新指派）。"""
    actor = uuid4()
    original = uuid4()
    new_assignee = uuid4()
    wo = _wo(assignee_id=original)
    WorkOrderStateMachine.transition(
        wo, "dispatch", actor_id=actor, assignee_id=new_assignee,
    )
    assert wo.assignee_id == new_assignee  # kwarg 覆寫


@pytest.mark.parametrize("source_status", [
    WorkOrderStatus.DISPATCHED,
    WorkOrderStatus.IN_PROGRESS,
    WorkOrderStatus.AWAITING_SIGNOFF,
    WorkOrderStatus.CLOSED,
    WorkOrderStatus.CANCELLED,
    WorkOrderStatus.REOPENED,
])
def test_dispatch_only_from_draft(source_status):
    """dispatch 只從 DRAFT 出發；其他 source state 全該被擋。"""
    wo = _wo(status=source_status, assignee_id=uuid4())
    with pytest.raises(InvalidTransition, match="cannot transition"):
        WorkOrderStateMachine.transition(wo, "dispatch", actor_id=uuid4())


# ─────────────────────────────────────────────────────────────────────────
# start_work（DISPATCHED → IN_PROGRESS, 也可 REOPENED → IN_PROGRESS）
# ─────────────────────────────────────────────────────────────────────────


def test_start_work_from_dispatched():
    wo = _wo(status=WorkOrderStatus.DISPATCHED, assignee_id=uuid4())
    WorkOrderStateMachine.transition(wo, "start_work")
    assert wo.status == WorkOrderStatus.IN_PROGRESS
    assert wo.started_at is not None


def test_start_work_from_reopened():
    """walkthrough Q1 + DN-01 transition table — REOPENED 也可 start_work。"""
    wo = _wo(status=WorkOrderStatus.REOPENED, assignee_id=uuid4())
    WorkOrderStateMachine.transition(wo, "start_work")
    assert wo.status == WorkOrderStatus.IN_PROGRESS


def test_start_work_requires_assignee():
    wo = _wo(status=WorkOrderStatus.DISPATCHED)
    with pytest.raises(InvalidTransition, match="assignee_id"):
        WorkOrderStateMachine.transition(wo, "start_work")


def test_start_work_offshore_requires_weather_window():
    """walkthrough Q5：offshore farm caller 傳 require_weather_window=True 強制檢查。"""
    wo = _wo(status=WorkOrderStatus.DISPATCHED, assignee_id=uuid4())
    # Without weather_window_id → 拒絕
    with pytest.raises(InvalidTransition, match="weather_window_id"):
        WorkOrderStateMachine.transition(
            wo, "start_work", require_weather_window=True
        )


def test_start_work_offshore_with_weather_window_passes():
    wo = _wo(
        status=WorkOrderStatus.DISPATCHED,
        assignee_id=uuid4(),
        weather_window_id=uuid4(),
    )
    WorkOrderStateMachine.transition(
        wo, "start_work", require_weather_window=True
    )
    assert wo.status == WorkOrderStatus.IN_PROGRESS


def test_start_work_onshore_does_not_check_weather_window():
    """onshore 不傳 require_weather_window，weather_window_id 留 None 也可。"""
    wo = _wo(status=WorkOrderStatus.DISPATCHED, assignee_id=uuid4())
    WorkOrderStateMachine.transition(wo, "start_work")  # 沒 require_*
    assert wo.status == WorkOrderStatus.IN_PROGRESS


# ── WMOM-20260510-01 Part C：start_work request 內帶 weather_window_id ──


def test_start_work_offshore_accepts_weather_window_id_from_kwargs():
    """offshore 路徑：工單尚未綁 ww_id，但 start_work 同時帶 weather_window_id
    （新的 frontend 在 start_work 對話框一次完成綁定）→ guard 通過 +
    apply 階段寫入工單。"""
    ww_id = uuid4()
    wo = _wo(status=WorkOrderStatus.DISPATCHED, assignee_id=uuid4())
    assert wo.weather_window_id is None
    WorkOrderStateMachine.transition(
        wo, "start_work",
        require_weather_window=True,
        weather_window_id=ww_id,
    )
    assert wo.status == WorkOrderStatus.IN_PROGRESS
    assert wo.weather_window_id == ww_id


def test_start_work_offshore_kwargs_ww_id_overrides_existing():
    """若工單已綁 ww_id A、start_work 又帶 ww_id B → apply 以 kwargs 為準。
    （demo orchestrator 換氣象窗的情境）"""
    existing_ww = uuid4()
    new_ww = uuid4()
    wo = _wo(
        status=WorkOrderStatus.DISPATCHED,
        assignee_id=uuid4(),
        weather_window_id=existing_ww,
    )
    WorkOrderStateMachine.transition(
        wo, "start_work",
        require_weather_window=True,
        weather_window_id=new_ww,
    )
    assert wo.weather_window_id == new_ww


def test_start_work_onshore_ignores_weather_window_id_in_kwargs():
    """Regression (review 5/18 must-fix #1)：onshore（require_weather_window 未傳/=False）
    + caller 偷塞 weather_window_id 進來時，apply 不應靜默寫入 wo.weather_window_id。
    保證 guard 與 apply 條件一致，避免陸上工單被污染。"""
    stray_ww = uuid4()
    wo = _wo(status=WorkOrderStatus.DISPATCHED, assignee_id=uuid4())
    assert wo.weather_window_id is None
    # 沒帶 require_weather_window → guard 不檢，但 apply 也不該寫入
    WorkOrderStateMachine.transition(
        wo, "start_work",
        weather_window_id=stray_ww,
    )
    assert wo.status == WorkOrderStatus.IN_PROGRESS
    assert wo.weather_window_id is None, "onshore 路徑不應寫入 weather_window_id"


# ─────────────────────────────────────────────────────────────────────────
# update_progress（self-loop）
# ─────────────────────────────────────────────────────────────────────────


def test_update_progress_appends_note():
    actor = uuid4()
    wo = _wo(status=WorkOrderStatus.IN_PROGRESS, assignee_id=actor)
    WorkOrderStateMachine.transition(
        wo, "update_progress", actor_id=actor, note="拆下軸承"
    )
    assert wo.status == WorkOrderStatus.IN_PROGRESS  # self-loop
    assert len(wo.progress_notes) == 1
    assert wo.progress_notes[0].note == "拆下軸承"
    assert wo.progress_notes[0].actor_id == actor


def test_update_progress_multiple_notes():
    actor = uuid4()
    wo = _wo(status=WorkOrderStatus.IN_PROGRESS, assignee_id=actor)
    WorkOrderStateMachine.transition(wo, "update_progress", actor_id=actor, note="step 1")
    WorkOrderStateMachine.transition(wo, "update_progress", actor_id=actor, note="step 2")
    WorkOrderStateMachine.transition(wo, "update_progress", actor_id=actor, note="step 3")
    assert [n.note for n in wo.progress_notes] == ["step 1", "step 2", "step 3"]


def test_update_progress_only_from_in_progress():
    wo = _wo()  # DRAFT
    with pytest.raises(InvalidTransition, match="cannot transition"):
        WorkOrderStateMachine.transition(
            wo, "update_progress", actor_id=uuid4(), note="..."
        )


@pytest.mark.parametrize("note_value", ["", "   ", None])
def test_update_progress_rejects_empty_or_whitespace_note(note_value):
    """空 / 純空白 / None note 全應拒絕（不靜默跳過）。"""
    actor = uuid4()
    wo = _wo(status=WorkOrderStatus.IN_PROGRESS, assignee_id=actor)
    with pytest.raises(InvalidTransition, match="non-empty note"):
        WorkOrderStateMachine.transition(
            wo, "update_progress", actor_id=actor, note=note_value
        )


def test_update_progress_requires_actor_id():
    """progress note 必有作者（actor_id），給 audit / KPI 用。"""
    wo = _wo(status=WorkOrderStatus.IN_PROGRESS, assignee_id=uuid4())
    with pytest.raises(InvalidTransition, match="actor_id"):
        WorkOrderStateMachine.transition(
            wo, "update_progress", note="拆下軸承"  # 沒 actor_id
        )


def test_update_progress_strips_whitespace_in_note():
    """note 寫入前自動 strip — 避免前端誤帶 trailing spaces。"""
    actor = uuid4()
    wo = _wo(status=WorkOrderStatus.IN_PROGRESS, assignee_id=actor)
    WorkOrderStateMachine.transition(
        wo, "update_progress", actor_id=actor, note="  好了  "
    )
    assert wo.progress_notes[0].note == "好了"


# ─────────────────────────────────────────────────────────────────────────
# finish
# ─────────────────────────────────────────────────────────────────────────


def test_finish_success_no_followup():
    wo = _wo(status=WorkOrderStatus.IN_PROGRESS, assignee_id=uuid4())
    WorkOrderStateMachine.transition(
        wo, "finish",
        actual_hours=3.5,
        followup_kind=FollowupKind.NONE,
        work_summary="換軸承完成",
    )
    assert wo.status == WorkOrderStatus.AWAITING_SIGNOFF
    assert wo.actual_hours == 3.5
    assert wo.followup_kind == FollowupKind.NONE
    assert wo.work_summary == "換軸承完成"
    assert wo.finished_at is not None


def test_finish_success_with_followup_needed():
    """walkthrough Q2：FOLLOWUP_NEEDED 場景，需給 followup_note。"""
    wo = _wo(status=WorkOrderStatus.IN_PROGRESS, assignee_id=uuid4())
    WorkOrderStateMachine.transition(
        wo, "finish",
        actual_hours=2.0,
        followup_kind=FollowupKind.FOLLOWUP_NEEDED,
        unfinished_items="軸承溫度仍偏高，下週再驗",
        followup_note="觀察 7 天",
    )
    assert wo.followup_kind == FollowupKind.FOLLOWUP_NEEDED
    assert wo.unfinished_items == "軸承溫度仍偏高，下週再驗"


def test_finish_requires_actual_hours():
    wo = _wo(status=WorkOrderStatus.IN_PROGRESS, assignee_id=uuid4())
    with pytest.raises(InvalidTransition, match="actual_hours"):
        WorkOrderStateMachine.transition(
            wo, "finish", followup_kind=FollowupKind.NONE
        )


def test_finish_requires_followup_kind():
    wo = _wo(status=WorkOrderStatus.IN_PROGRESS, assignee_id=uuid4())
    with pytest.raises(InvalidTransition, match="followup_kind"):
        WorkOrderStateMachine.transition(wo, "finish", actual_hours=1.0)


def test_finish_followup_kind_must_be_enum():
    """guard：followup_kind 不能傳字串，必須 enum（避免 typo）。"""
    wo = _wo(status=WorkOrderStatus.IN_PROGRESS, assignee_id=uuid4())
    with pytest.raises(InvalidTransition, match="must be a FollowupKind"):
        WorkOrderStateMachine.transition(
            wo, "finish",
            actual_hours=1.0,
            followup_kind="none",  # 字串，不對
        )


# ─────────────────────────────────────────────────────────────────────────
# approve_all → CLOSED
# ─────────────────────────────────────────────────────────────────────────


def test_approve_all_to_closed():
    wo = _wo(status=WorkOrderStatus.AWAITING_SIGNOFF)
    WorkOrderStateMachine.transition(wo, "approve_all")
    assert wo.status == WorkOrderStatus.CLOSED
    assert wo.closed_at is not None


def test_approve_all_only_from_awaiting_signoff():
    wo = _wo(status=WorkOrderStatus.IN_PROGRESS)
    with pytest.raises(InvalidTransition, match="cannot transition"):
        WorkOrderStateMachine.transition(wo, "approve_all")


# ─────────────────────────────────────────────────────────────────────────
# reject → IN_PROGRESS（DN-02 D2-Q3：給機會修正）
# ─────────────────────────────────────────────────────────────────────────


def test_reject_back_to_in_progress():
    wo = _wo(status=WorkOrderStatus.AWAITING_SIGNOFF)
    WorkOrderStateMachine.transition(
        wo, "reject", reject_reason="缺工程師簽名照片"
    )
    assert wo.status == WorkOrderStatus.IN_PROGRESS
    assert wo.reject_reason == "缺工程師簽名照片"
    assert wo.rejected_at is not None


def test_reject_requires_reason():
    wo = _wo(status=WorkOrderStatus.AWAITING_SIGNOFF)
    with pytest.raises(InvalidTransition, match="reject_reason"):
        WorkOrderStateMachine.transition(wo, "reject")


def test_reject_empty_reason_rejected():
    wo = _wo(status=WorkOrderStatus.AWAITING_SIGNOFF)
    with pytest.raises(InvalidTransition, match="reject_reason"):
        WorkOrderStateMachine.transition(wo, "reject", reject_reason="")


# ─────────────────────────────────────────────────────────────────────────
# cancel
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("source", [
    WorkOrderStatus.DRAFT,
    WorkOrderStatus.DISPATCHED,
    WorkOrderStatus.IN_PROGRESS,
])
def test_cancel_from_pre_signoff_states(source):
    """walkthrough Q1：cancel 在所有 pre-signoff 階段都可（替代 etech removeFrom）。"""
    wo = _wo(status=source, assignee_id=uuid4() if source != WorkOrderStatus.DRAFT else None)
    WorkOrderStateMachine.transition(
        wo, "cancel", cancel_reason="客戶要求暫停"
    )
    assert wo.status == WorkOrderStatus.CANCELLED
    assert wo.cancel_reason == "客戶要求暫停"
    assert wo.cancelled_at is not None


def test_cancel_blocked_at_awaiting_signoff():
    """簽核中不可 cancel — 走 reject 退回 IN_PROGRESS 才合理。"""
    wo = _wo(status=WorkOrderStatus.AWAITING_SIGNOFF)
    with pytest.raises(InvalidTransition, match="cannot transition"):
        WorkOrderStateMachine.transition(
            wo, "cancel", cancel_reason="..."
        )


@pytest.mark.parametrize("terminal", [
    WorkOrderStatus.CLOSED,
    WorkOrderStatus.CANCELLED,
])
def test_cancel_blocked_in_terminal_states(terminal):
    wo = _wo(status=terminal)
    with pytest.raises(InvalidTransition, match="cannot transition"):
        WorkOrderStateMachine.transition(wo, "cancel", cancel_reason="...")


def test_cancel_requires_reason():
    wo = _wo(status=WorkOrderStatus.IN_PROGRESS)
    with pytest.raises(InvalidTransition, match="cancel_reason"):
        WorkOrderStateMachine.transition(wo, "cancel")


# ─────────────────────────────────────────────────────────────────────────
# reopen → REOPENED（CLOSED → REOPENED）
# ─────────────────────────────────────────────────────────────────────────


def test_reopen_from_closed():
    wo = _wo(status=WorkOrderStatus.CLOSED)
    WorkOrderStateMachine.transition(
        wo, "reopen", reopen_reason="客戶反映同部件再次故障"
    )
    assert wo.status == WorkOrderStatus.REOPENED
    # walkthrough fix #7：reopen_reason 寫到獨立欄位，不再串接 followup_note
    assert wo.reopen_reason == "客戶反映同部件再次故障"
    assert wo.reopened_at is not None
    # closed_at 應清掉（給「再開→再 close」覆蓋用）
    assert wo.closed_at is None


def test_reopen_does_not_pollute_followup_note():
    """walkthrough fix #7：reopen 不應污染 followup_note 既有內容。"""
    wo = _wo(
        status=WorkOrderStatus.CLOSED,
        followup_note="完工後一週觀察軸承溫度",
    )
    WorkOrderStateMachine.transition(
        wo, "reopen", reopen_reason="同部件再故障"
    )
    # followup_note 不被改動
    assert wo.followup_note == "完工後一週觀察軸承溫度"
    # reopen_reason 在獨立欄位
    assert wo.reopen_reason == "同部件再故障"


def test_reopen_requires_reason():
    wo = _wo(status=WorkOrderStatus.CLOSED)
    with pytest.raises(InvalidTransition, match="reopen_reason"):
        WorkOrderStateMachine.transition(wo, "reopen")


@pytest.mark.parametrize("invalid_source", [
    WorkOrderStatus.DRAFT,
    WorkOrderStatus.DISPATCHED,
    WorkOrderStatus.IN_PROGRESS,
    WorkOrderStatus.AWAITING_SIGNOFF,
    WorkOrderStatus.CANCELLED,
    WorkOrderStatus.REOPENED,
])
def test_reopen_only_from_closed(invalid_source):
    """REOPENED → REOPENED / CANCELLED → REOPENED 等等都該被擋（要新建單）。"""
    wo = _wo(status=invalid_source)
    with pytest.raises(InvalidTransition, match="cannot transition"):
        WorkOrderStateMachine.transition(
            wo, "reopen", reopen_reason="..."
        )


# ─────────────────────────────────────────────────────────────────────────
# 完整 happy-path lifecycle
# ─────────────────────────────────────────────────────────────────────────


def test_full_happy_path_corrective_lifecycle():
    """DRAFT → DISPATCHED → IN_PROGRESS → AWAITING_SIGNOFF → CLOSED."""
    actor = uuid4()
    dispatcher = uuid4()
    wo = _wo(assignee_id=actor)

    # dispatch
    WorkOrderStateMachine.transition(wo, "dispatch", actor_id=dispatcher)
    assert wo.status == WorkOrderStatus.DISPATCHED
    assert wo.dispatched_by == dispatcher

    # start_work
    WorkOrderStateMachine.transition(wo, "start_work")
    assert wo.status == WorkOrderStatus.IN_PROGRESS

    # update_progress 多次
    WorkOrderStateMachine.transition(wo, "update_progress", actor_id=actor, note="拆下舊件")
    WorkOrderStateMachine.transition(wo, "update_progress", actor_id=actor, note="裝新件")

    # finish
    WorkOrderStateMachine.transition(
        wo, "finish",
        actual_hours=4.0,
        followup_kind=FollowupKind.NONE,
        work_summary="完成軸承更換 + 復測 OK",
    )
    assert wo.status == WorkOrderStatus.AWAITING_SIGNOFF

    # approve_all
    WorkOrderStateMachine.transition(wo, "approve_all")
    assert wo.status == WorkOrderStatus.CLOSED
    assert wo.is_terminal()


def test_reject_then_finish_again_lifecycle():
    """簽核 reject 後可以再走一次 finish + approve_all。"""
    actor = uuid4()
    wo = _wo(
        status=WorkOrderStatus.AWAITING_SIGNOFF,
        assignee_id=actor,
        actual_hours=1.0,
        followup_kind=FollowupKind.NONE,
    )
    # 第一次 reject
    WorkOrderStateMachine.transition(
        wo, "reject", reject_reason="工時太短"
    )
    assert wo.status == WorkOrderStatus.IN_PROGRESS

    # 重新 finish（actual_hours 改了）
    WorkOrderStateMachine.transition(
        wo, "finish",
        actual_hours=4.0,
        followup_kind=FollowupKind.NONE,
        work_summary="附完整工序紀錄",
    )
    # 第二次 approve
    WorkOrderStateMachine.transition(wo, "approve_all")
    assert wo.status == WorkOrderStatus.CLOSED
    # reject 痕跡仍在
    assert wo.reject_reason == "工時太短"


def test_reopen_lifecycle_from_closed():
    """CLOSED → REOPENED → IN_PROGRESS → 重新 finish + approve."""
    actor = uuid4()
    wo = _wo(status=WorkOrderStatus.CLOSED, assignee_id=actor)

    WorkOrderStateMachine.transition(
        wo, "reopen", reopen_reason="同部件 3 天內再故障"
    )
    assert wo.status == WorkOrderStatus.REOPENED

    WorkOrderStateMachine.transition(wo, "start_work")
    assert wo.status == WorkOrderStatus.IN_PROGRESS

    WorkOrderStateMachine.transition(
        wo, "finish",
        actual_hours=2.0,
        followup_kind=FollowupKind.NONE,
    )
    WorkOrderStateMachine.transition(wo, "approve_all")
    assert wo.status == WorkOrderStatus.CLOSED


# ─────────────────────────────────────────────────────────────────────────
# Misc: unknown action
# ─────────────────────────────────────────────────────────────────────────


def test_unknown_action_raises():
    wo = _wo()
    with pytest.raises(InvalidTransition, match="unknown action"):
        WorkOrderStateMachine.transition(wo, "fly_to_moon")


def test_guard_failure_does_not_mutate_state():
    """重要不變式：guard fail 時，WO 狀態 / side-effect 欄位都不應被改動。"""
    wo = _wo(status=WorkOrderStatus.IN_PROGRESS, assignee_id=uuid4())
    original_status = wo.status
    original_finished_at = wo.finished_at

    with pytest.raises(InvalidTransition):
        # finish 缺 actual_hours → guard fail
        WorkOrderStateMachine.transition(
            wo, "finish", followup_kind=FollowupKind.NONE
        )

    # 狀態未改
    assert wo.status == original_status
    assert wo.finished_at == original_finished_at
