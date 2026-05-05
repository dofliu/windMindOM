"""Work order state machine — pure domain transitions（WMOM-20260504-16）。

對應 [DN-01](../../../docs/design-notes/m3/DN-01-work-order-lifecycle.md) §2.2。

設計：
- 9 個 transition：``dispatch`` / ``start_work`` / ``update_progress`` / ``finish`` /
  ``approve_all`` / ``reject`` / ``cancel`` / ``reopen``（``start_work`` 適用兩個
  source state，所以 transition table 內 9 條 rule but 8 unique action name）
- ``WORK_ORDER_TRANSITIONS`` 表為 source-of-truth；新加 transition 改這邊就好
- guard 條件 fail → ``raise InvalidTransition``（caller 端擋，不拋到 router）
- ``WorkOrderStateMachine.transition`` 為唯一 mutation entry point — 同時更新 status +
  side-effect 欄位（timestamps / actor_id / cancel_reason 等）
- ``WorkOrder`` 物件 in-place mutation（非 immutable copy）— 對 dataclass 較直觀；
  測試上仍可用 ``copy.deepcopy`` 比對
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

from .work_order import (
    FollowupKind,
    Priority,
    ProgressNote,
    WorkOrder,
    WorkOrderStatus,
    _utc_now,
)


# ─────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────


class InvalidTransition(Exception):
    """Transition rejected — 不合法的 source state 或 guard 失敗。

    Caller 通常 catch 之後轉 422 / 400；不要讓這個 bubble 到外層 traceback。
    """


# ─────────────────────────────────────────────────────────────────────────
# Transition rule table
# ─────────────────────────────────────────────────────────────────────────


GuardCallable = Callable[[WorkOrder, "UUID | None", dict[str, Any]], None]


@dataclass(frozen=True)
class TransitionRule:
    """單一 transition 的描述。

    - ``from_states``: 哪些 source state 接受此 action
    - ``to_state``: target state
    - ``guard``: optional callable ``(wo, actor_id, kwargs) -> None``；
      raise ``InvalidTransition`` 表示拒絕。簽名加 ``actor_id`` 是因為某些 transition
      需要驗證「誰執行」（如 dispatch 必填 dispatcher actor_id）。
    """

    name: str
    from_states: frozenset[WorkOrderStatus]
    to_state: WorkOrderStatus
    guard: GuardCallable | None = None


# ─────────────────────────────────────────────────────────────────────────
# Guard functions（pure，不動 WO state）
# ─────────────────────────────────────────────────────────────────────────


def _guard_dispatch(wo: WorkOrder, actor_id: UUID | None, kwargs: dict[str, Any]) -> None:
    """dispatch — assignee_id（被派者）+ actor_id（派工人，給 audit 用）都必填。"""
    if wo.assignee_id is None:
        raise InvalidTransition("dispatch requires assignee_id to be set on the work order")
    if actor_id is None:
        raise InvalidTransition("dispatch requires actor_id (the dispatcher, for audit)")


def _guard_start_work(wo: WorkOrder, actor_id: UUID | None, kwargs: dict[str, Any]) -> None:
    """start_work — onshore 不檢 weather_window；offshore caller 傳
    ``require_weather_window=True`` 時強制檢查 ``wo.weather_window_id``。
    """
    if wo.assignee_id is None:
        raise InvalidTransition("start_work requires assignee_id")
    if kwargs.get("require_weather_window"):
        if wo.weather_window_id is None:
            raise InvalidTransition(
                "start_work requires weather_window_id (offshore farm policy)"
            )


def _guard_update_progress(
    wo: WorkOrder, actor_id: UUID | None, kwargs: dict[str, Any]
) -> None:
    """update_progress 必填 non-empty note + actor_id（progress note 必有作者）。"""
    note_text = (kwargs.get("note") or "").strip()
    if not note_text:
        raise InvalidTransition("update_progress requires non-empty note")
    if actor_id is None:
        raise InvalidTransition("update_progress requires actor_id (note author)")


def _guard_finish(wo: WorkOrder, actor_id: UUID | None, kwargs: dict[str, Any]) -> None:
    """finish 必填 actual_hours + followup_kind（caller 從 frontend form 帶進來）。"""
    if "actual_hours" not in kwargs or kwargs["actual_hours"] is None:
        raise InvalidTransition("finish requires actual_hours in kwargs")
    if "followup_kind" not in kwargs or kwargs["followup_kind"] is None:
        raise InvalidTransition("finish requires followup_kind in kwargs")
    if not isinstance(kwargs["followup_kind"], FollowupKind):
        raise InvalidTransition(
            "finish: followup_kind must be a FollowupKind enum"
        )


def _guard_cancel(wo: WorkOrder, actor_id: UUID | None, kwargs: dict[str, Any]) -> None:
    """cancel 帶 cancel_reason（取代 etech removeFrom 的 audit 需求）。"""
    if "cancel_reason" not in kwargs or not kwargs["cancel_reason"]:
        raise InvalidTransition("cancel requires non-empty cancel_reason in kwargs")


def _guard_reject(wo: WorkOrder, actor_id: UUID | None, kwargs: dict[str, Any]) -> None:
    """reject 來自簽核流程（DN-02）；必填 reject_reason。"""
    if "reject_reason" not in kwargs or not kwargs["reject_reason"]:
        raise InvalidTransition("reject requires non-empty reject_reason in kwargs")


def _guard_reopen(wo: WorkOrder, actor_id: UUID | None, kwargs: dict[str, Any]) -> None:
    """reopen 通常由 ``followup_kind == FOLLOWUP_NEEDED`` 觸發；亦可人工帶 reason。

    本 guard 不強制 followup_kind 條件（人工 reopen 也合理），但要 ``reopen_reason``。
    """
    if "reopen_reason" not in kwargs or not kwargs["reopen_reason"]:
        raise InvalidTransition("reopen requires non-empty reopen_reason in kwargs")


# ─────────────────────────────────────────────────────────────────────────
# Source-of-truth transition table
# ─────────────────────────────────────────────────────────────────────────


# 注意：dict insertion order 不代表 state machine 序列，僅為 alphabetical-by-action 方便閱讀。
# 新增 transition：在此 dict 加一條 + 寫對應 guard + 在 ``_apply_side_effects`` 加 branch。
WORK_ORDER_TRANSITIONS: dict[str, TransitionRule] = {
    "dispatch": TransitionRule(
        name="dispatch",
        from_states=frozenset({WorkOrderStatus.DRAFT}),
        to_state=WorkOrderStatus.DISPATCHED,
        guard=_guard_dispatch,
    ),
    "start_work": TransitionRule(
        name="start_work",
        # 適用兩個 source state（DN-01 §2.2 transition table）
        from_states=frozenset(
            {WorkOrderStatus.DISPATCHED, WorkOrderStatus.REOPENED}
        ),
        to_state=WorkOrderStatus.IN_PROGRESS,
        guard=_guard_start_work,
    ),
    "update_progress": TransitionRule(
        name="update_progress",
        from_states=frozenset({WorkOrderStatus.IN_PROGRESS}),
        to_state=WorkOrderStatus.IN_PROGRESS,  # self-loop（progress note 累加）
        guard=_guard_update_progress,
    ),
    "finish": TransitionRule(
        name="finish",
        from_states=frozenset({WorkOrderStatus.IN_PROGRESS}),
        to_state=WorkOrderStatus.AWAITING_SIGNOFF,
        guard=_guard_finish,
    ),
    "approve_all": TransitionRule(
        name="approve_all",
        from_states=frozenset({WorkOrderStatus.AWAITING_SIGNOFF}),
        to_state=WorkOrderStatus.CLOSED,
        guard=None,
    ),
    "reject": TransitionRule(
        name="reject",
        from_states=frozenset({WorkOrderStatus.AWAITING_SIGNOFF}),
        to_state=WorkOrderStatus.IN_PROGRESS,  # 回去給機會修正（DN-01 D2-Q3）
        guard=_guard_reject,
    ),
    "cancel": TransitionRule(
        name="cancel",
        # 只能在「未進入簽核」階段 cancel；已簽完 closed 才走 reopen
        from_states=frozenset(
            {
                WorkOrderStatus.DRAFT,
                WorkOrderStatus.DISPATCHED,
                WorkOrderStatus.IN_PROGRESS,
            }
        ),
        to_state=WorkOrderStatus.CANCELLED,
        guard=_guard_cancel,
    ),
    "reopen": TransitionRule(
        name="reopen",
        from_states=frozenset({WorkOrderStatus.CLOSED}),
        to_state=WorkOrderStatus.REOPENED,
        guard=_guard_reopen,
    ),
}


# ─────────────────────────────────────────────────────────────────────────
# State helpers
# ─────────────────────────────────────────────────────────────────────────


def open_states() -> frozenset[WorkOrderStatus]:
    """工單視為「OPEN」（尚未進終態）的所有 state — 給 multi-WO constraint 用。"""
    return frozenset(
        {
            WorkOrderStatus.DRAFT,
            WorkOrderStatus.DISPATCHED,
            WorkOrderStatus.IN_PROGRESS,
            WorkOrderStatus.AWAITING_SIGNOFF,
            WorkOrderStatus.REOPENED,
        }
    )


def terminal_states() -> frozenset[WorkOrderStatus]:
    """終態 — 不接受 forward 流動的 transition（dispatch / start_work / finish 等）。

    注意：CLOSED 仍可走 ``reopen`` action 轉回 REOPENED — 這是 state machine 設計上
    對「事後發現需重做」的合法 exit transition，不違反「終態」定義。
    Service 層若要禁止任何操作，要明確排除 reopen。
    """
    return frozenset({WorkOrderStatus.CLOSED, WorkOrderStatus.CANCELLED})


def reopenable_states() -> frozenset[WorkOrderStatus]:
    """可走 ``reopen`` action 轉回 REOPENED 的 state（目前只有 CLOSED）。"""
    return frozenset({WorkOrderStatus.CLOSED})


# ─────────────────────────────────────────────────────────────────────────
# Side-effect application
# ─────────────────────────────────────────────────────────────────────────


def _apply_side_effects(
    wo: WorkOrder, action: str, *, actor_id: UUID | None, kwargs: dict[str, Any]
) -> None:
    """transition-specific 欄位更新（status + updated_at 在 caller 端統一處理）。

    這裡不檢 guard（已在 ``WorkOrderStateMachine.transition`` 跑過），
    純粹依 action 落地對應欄位變化。所有 timestamp 一律 UTC。
    """
    now = _utc_now()
    if action == "dispatch":
        wo.dispatched_at = now
        wo.dispatched_by = actor_id
    elif action == "start_work":
        wo.started_at = now
    elif action == "update_progress":
        # guard 已確保 actor_id 與 note 都非空
        assert actor_id is not None  # type: assertion for static analysis
        wo.progress_notes.append(
            ProgressNote(timestamp=now, actor_id=actor_id, note=kwargs["note"].strip())
        )
    elif action == "finish":
        wo.finished_at = now
        wo.actual_hours = kwargs["actual_hours"]
        wo.followup_kind = kwargs["followup_kind"]
        wo.work_summary = kwargs.get("work_summary")
        wo.unfinished_items = kwargs.get("unfinished_items")
        wo.followup_note = kwargs.get("followup_note")
    elif action == "approve_all":
        wo.closed_at = now
    elif action == "reject":
        wo.rejected_at = now
        wo.reject_reason = kwargs["reject_reason"]
    elif action == "cancel":
        wo.cancelled_at = now
        wo.cancel_reason = kwargs["cancel_reason"]
    elif action == "reopen":
        # 清掉 closed_at 因為要再開；保留 finished_at 給歷史 trace
        wo.closed_at = None
        wo.reopened_at = now
        wo.reopen_reason = kwargs["reopen_reason"]


# ─────────────────────────────────────────────────────────────────────────
# State machine
# ─────────────────────────────────────────────────────────────────────────


class WorkOrderStateMachine:
    """Work order pure-domain state machine。

    Usage::

        wo = WorkOrder(...)  # status=DRAFT
        WorkOrderStateMachine.transition(wo, "dispatch", actor_id=班長.id)
        WorkOrderStateMachine.transition(wo, "start_work")
        WorkOrderStateMachine.transition(
            wo, "finish",
            actual_hours=3.5,
            followup_kind=FollowupKind.NONE,
            work_summary="..."
        )
        WorkOrderStateMachine.transition(wo, "approve_all")  # → CLOSED

    Caller 自己負責：
    - 多階簽核的累積（DN-02 SignoffChain），全簽完才 ``approve_all``
    - 一台風機 ≤ 3 張 OPEN 的 application-level check（多看 DN-01 §2.2）
    - DB persistence — 本層只 mutate dataclass instance
    """

    @staticmethod
    def can_transition(wo: WorkOrder, action: str) -> bool:
        """Pure check — 不執行也不 raise。給 frontend 顯示「可用按鈕」用。"""
        rule = WORK_ORDER_TRANSITIONS.get(action)
        if rule is None:
            return False
        return wo.status in rule.from_states

    @staticmethod
    def available_actions(wo: WorkOrder) -> list[str]:
        """列出當前 state 可用的所有 action 名稱（給 UI / tests 用）。"""
        return [
            name
            for name, rule in WORK_ORDER_TRANSITIONS.items()
            if wo.status in rule.from_states
        ]

    @staticmethod
    def transition(
        wo: WorkOrder,
        action: str,
        *,
        actor_id: UUID | None = None,
        **kwargs: Any,
    ) -> WorkOrder:
        """Apply transition in-place + return same WO（chainable）。

        Raises:
            InvalidTransition: action 不存在 / source state 不對 / guard 失敗
        """
        rule = WORK_ORDER_TRANSITIONS.get(action)
        if rule is None:
            raise InvalidTransition(f"unknown action: {action!r}")

        if wo.status not in rule.from_states:
            allowed = ", ".join(sorted(s.value for s in rule.from_states))
            raise InvalidTransition(
                f"{action!r}: cannot transition from {wo.status.value!r} "
                f"(allowed: {allowed})"
            )

        if rule.guard is not None:
            rule.guard(wo, actor_id, kwargs)

        # 過 guard 後才 mutate（避免半路失敗留 partial state）
        _apply_side_effects(wo, action, actor_id=actor_id, kwargs=kwargs)
        wo.status = rule.to_state
        wo.updated_at = _utc_now()
        return wo
