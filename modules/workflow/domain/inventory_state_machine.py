"""Material request state machine — pure domain transitions（WMOM-20260509-01）。

對應 [DN-03](../../../docs/design-notes/m3/DN-03-inventory-material-request.md) §2.2。

設計：
- 7 個 transition action（同 work_order state machine 模式）
- ``MATERIAL_REQUEST_TRANSITIONS`` 表為 source-of-truth；新加 transition 改這邊
- guard 條件 fail → ``raise InvalidTransition``（caller 端擋，不拋到 router）
- ``MaterialRequestStateMachine.transition`` 為唯一 mutation entry point — 同時更新
  status + side-effect 欄位（timestamps / cancel_reason / reject_reason 等）
- ``MaterialRequest`` 物件 in-place mutation（與 work_order 一致）

Transition 矩陣（DN-03 §2.2 lifecycle）：

    DRAFT ─submit_for_approval─→ AWAITING_APPROVAL
                                       │
                                       ├─approve_all────→ APPROVED ─dispatch───→ DISPATCHED
                                       │                                           │
                                       └─reject──→ REJECTED                       receive
                                                                                    ↓
                                                                                  RECEIVED
                                                                                    │
                                                                                  mark_used
                                                                                    ↓
                                                                                  USED
                                                                                    │
                                                                                  close
                                                                                    ↓
                                                                                  CLOSED

旁路 cancel：
    DRAFT / AWAITING_APPROVAL / APPROVED ─cancel─→ CANCELLED
    （DISPATCHED 之後不允許 cancel — 物料已離庫，須走 ``MaterialReturn`` 流程）

也提供 close：RECEIVED → CLOSED（工單若不需走「USED」就直接 close 也合法）。

注意：``dispatch`` 在 domain 層只做 status / timestamp 更新，**真正的 stock 扣帳 + ledger
寫入** 在 ``inventory_repository.dispatch_request()`` 內以 SELECT FOR UPDATE 雙寫
transaction 完成（DN-03 §2.3 + WMOM-20260509-02）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID

from .inventory import (
    MaterialRequest,
    MaterialRequestStatus,
    _utc_now,
)
from .state_machine import InvalidTransition  # 共用 exception


GuardCallable = Callable[[MaterialRequest, "UUID | None", dict[str, Any]], None]


@dataclass(frozen=True)
class MaterialRequestTransitionRule:
    """單一 transition 描述（與 WorkOrder TransitionRule 同型，但分檔避免耦合）。"""

    name: str
    from_states: frozenset[MaterialRequestStatus]
    to_state: MaterialRequestStatus
    guard: GuardCallable | None = None


# ─────────────────────────────────────────────────────────────────────────
# Guard functions（pure，不動 MR state）
# ─────────────────────────────────────────────────────────────────────────


def _guard_submit_for_approval(
    mr: MaterialRequest, actor_id: UUID | None, kwargs: dict[str, Any]
) -> None:
    """submit — items 必須非空 + farm_id / requester_id 已填。"""
    if not mr.items:
        raise InvalidTransition("submit_for_approval requires at least one item")
    if not mr.farm_id:
        raise InvalidTransition("submit_for_approval requires farm_id")


def _guard_dispatch(
    mr: MaterialRequest, actor_id: UUID | None, kwargs: dict[str, Any]
) -> None:
    """dispatch — 此 guard 只擋 domain-level 條件，stock 充足與否由 repository 雙寫
    transaction 內 SELECT FOR UPDATE 後檢查（避免 race）。"""
    if not mr.items:
        raise InvalidTransition("dispatch requires at least one item")


def _guard_receive(
    mr: MaterialRequest, actor_id: UUID | None, kwargs: dict[str, Any]
) -> None:
    """receive — kwargs 必須帶 ``actual_quantities``: dict[item_id, int]，每個 item 都要有對應 actual。"""
    actual = kwargs.get("actual_quantities")
    if not isinstance(actual, dict):
        raise InvalidTransition(
            "receive requires actual_quantities (dict[item_id, int]) in kwargs"
        )
    item_ids = {it.id for it in mr.items}
    missing = item_ids - set(actual.keys())
    if missing:
        raise InvalidTransition(
            f"receive: actual_quantities missing for items {sorted(str(m) for m in missing)}"
        )
    for it_id, qty in actual.items():
        if not isinstance(qty, int) or qty < 0:
            raise InvalidTransition(
                f"receive: actual qty for item {it_id} must be int >= 0 (got {qty!r})"
            )


def _guard_cancel(
    mr: MaterialRequest, actor_id: UUID | None, kwargs: dict[str, Any]
) -> None:
    """cancel 必填 cancel_reason（給 audit）。"""
    if not (kwargs.get("cancel_reason") or "").strip():
        raise InvalidTransition("cancel requires non-empty cancel_reason in kwargs")


def _guard_reject(
    mr: MaterialRequest, actor_id: UUID | None, kwargs: dict[str, Any]
) -> None:
    """reject 來自簽核流程（DN-02）；必填 reject_reason。"""
    if not (kwargs.get("reject_reason") or "").strip():
        raise InvalidTransition("reject requires non-empty reject_reason in kwargs")


# ─────────────────────────────────────────────────────────────────────────
# Source-of-truth transition table
# ─────────────────────────────────────────────────────────────────────────


MATERIAL_REQUEST_TRANSITIONS: dict[str, MaterialRequestTransitionRule] = {
    "submit_for_approval": MaterialRequestTransitionRule(
        name="submit_for_approval",
        from_states=frozenset({MaterialRequestStatus.DRAFT}),
        to_state=MaterialRequestStatus.AWAITING_APPROVAL,
        guard=_guard_submit_for_approval,
    ),
    "approve_all": MaterialRequestTransitionRule(
        name="approve_all",
        from_states=frozenset({MaterialRequestStatus.AWAITING_APPROVAL}),
        to_state=MaterialRequestStatus.APPROVED,
        guard=None,
    ),
    "reject": MaterialRequestTransitionRule(
        name="reject",
        from_states=frozenset({MaterialRequestStatus.AWAITING_APPROVAL}),
        to_state=MaterialRequestStatus.REJECTED,
        guard=_guard_reject,
    ),
    "dispatch": MaterialRequestTransitionRule(
        name="dispatch",
        from_states=frozenset({MaterialRequestStatus.APPROVED}),
        to_state=MaterialRequestStatus.DISPATCHED,
        guard=_guard_dispatch,
    ),
    "receive": MaterialRequestTransitionRule(
        name="receive",
        from_states=frozenset({MaterialRequestStatus.DISPATCHED}),
        to_state=MaterialRequestStatus.RECEIVED,
        guard=_guard_receive,
    ),
    "mark_used": MaterialRequestTransitionRule(
        name="mark_used",
        from_states=frozenset({MaterialRequestStatus.RECEIVED}),
        to_state=MaterialRequestStatus.USED,
        guard=None,
    ),
    "close": MaterialRequestTransitionRule(
        name="close",
        # 兩條 happy path：USED 後 close（用完）/ RECEIVED 後直接 close（無使用）
        from_states=frozenset(
            {MaterialRequestStatus.USED, MaterialRequestStatus.RECEIVED}
        ),
        to_state=MaterialRequestStatus.CLOSED,
        guard=None,
    ),
    "cancel": MaterialRequestTransitionRule(
        name="cancel",
        # 只能在「未出庫」階段 cancel；DISPATCHED 之後須走 MaterialReturn 流程
        from_states=frozenset(
            {
                MaterialRequestStatus.DRAFT,
                MaterialRequestStatus.AWAITING_APPROVAL,
                MaterialRequestStatus.APPROVED,
            }
        ),
        to_state=MaterialRequestStatus.CANCELLED,
        guard=_guard_cancel,
    ),
}


# ─────────────────────────────────────────────────────────────────────────
# State helpers
# ─────────────────────────────────────────────────────────────────────────


def open_states_mr() -> frozenset[MaterialRequestStatus]:
    """領料單視為「OPEN」（尚未進終態）的所有 state。"""
    return frozenset(
        {
            MaterialRequestStatus.DRAFT,
            MaterialRequestStatus.AWAITING_APPROVAL,
            MaterialRequestStatus.APPROVED,
            MaterialRequestStatus.DISPATCHED,
            MaterialRequestStatus.RECEIVED,
            MaterialRequestStatus.USED,
        }
    )


def terminal_states_mr() -> frozenset[MaterialRequestStatus]:
    """終態 — 不接受任何 transition。"""
    return frozenset(
        {
            MaterialRequestStatus.CLOSED,
            MaterialRequestStatus.CANCELLED,
            MaterialRequestStatus.REJECTED,
        }
    )


# ─────────────────────────────────────────────────────────────────────────
# Side-effect application
# ─────────────────────────────────────────────────────────────────────────


def _apply_side_effects(
    mr: MaterialRequest, action: str, *, actor_id: UUID | None, kwargs: dict[str, Any]
) -> None:
    """transition-specific 欄位更新（status + updated_at 在 caller 端統一處理）。"""
    now = _utc_now()
    if action == "submit_for_approval":
        mr.submitted_at = now
    elif action == "approve_all":
        mr.approved_at = now
    elif action == "reject":
        mr.rejected_at = now
        mr.reject_reason = kwargs["reject_reason"].strip()
        # 駁回後 chain pointer 留著當 audit；下次（若再建新 MR）會有自己的 chain
    elif action == "dispatch":
        mr.dispatched_at = now
        # ⚠ stock 扣帳 + ledger 寫入由 repository 雙寫 transaction 完成
    elif action == "receive":
        mr.received_at = now
        # 把 actual_quantities 寫進 items
        actual: dict[UUID, int] = kwargs["actual_quantities"]
        for item in mr.items:
            if item.id in actual:
                item.actual_qty = actual[item.id]
    elif action == "mark_used":
        mr.used_at = now
    elif action == "close":
        mr.closed_at = now
    elif action == "cancel":
        mr.cancelled_at = now
        mr.cancel_reason = kwargs["cancel_reason"].strip()


# ─────────────────────────────────────────────────────────────────────────
# State machine entry point
# ─────────────────────────────────────────────────────────────────────────


class MaterialRequestStateMachine:
    """Material request pure-domain state machine（同 WorkOrderStateMachine 模式）。

    Usage::

        mr = MaterialRequest(...)  # status=DRAFT
        MaterialRequestStateMachine.transition(mr, "submit_for_approval")
        # ... DN-02 chain 全 approve ...
        MaterialRequestStateMachine.transition(mr, "approve_all")
        # repository.dispatch_request() 雙寫成功後：
        MaterialRequestStateMachine.transition(mr, "dispatch")
        MaterialRequestStateMachine.transition(
            mr, "receive",
            actual_quantities={item_id_1: 3, item_id_2: 1},
        )
        MaterialRequestStateMachine.transition(mr, "mark_used")  # 工單 finish hook 觸發
        MaterialRequestStateMachine.transition(mr, "close")

    Caller 自己負責：
    - DN-02 多階簽核累積 → 全 approve 才 ``approve_all``
    - dispatch action 前要 repository 雙寫 transaction 完成（stock 扣帳 + ledger 寫入）
    - DB persistence — 本層只 mutate dataclass instance
    """

    @staticmethod
    def can_transition(mr: MaterialRequest, action: str) -> bool:
        """Pure check — 不執行也不 raise。給 frontend 顯示「可用按鈕」用。"""
        rule = MATERIAL_REQUEST_TRANSITIONS.get(action)
        if rule is None:
            return False
        return mr.status in rule.from_states

    @staticmethod
    def available_actions(mr: MaterialRequest) -> list[str]:
        """列出當前 state 可用的 action 名稱。"""
        return [
            name
            for name, rule in MATERIAL_REQUEST_TRANSITIONS.items()
            if mr.status in rule.from_states
        ]

    @staticmethod
    def transition(
        mr: MaterialRequest,
        action: str,
        *,
        actor_id: UUID | None = None,
        **kwargs: Any,
    ) -> MaterialRequest:
        """Apply transition in-place + return same MR（chainable）。

        Raises:
            InvalidTransition: action 不存在 / source state 不對 / guard 失敗
        """
        rule = MATERIAL_REQUEST_TRANSITIONS.get(action)
        if rule is None:
            raise InvalidTransition(
                f"unknown action: {action!r}", reason="unknown_action"
            )

        if mr.status not in rule.from_states:
            allowed = ", ".join(sorted(s.value for s in rule.from_states))
            raise InvalidTransition(
                f"{action!r}: cannot transition from {mr.status.value!r} "
                f"(allowed: {allowed})",
                reason="state_mismatch",
            )

        if rule.guard is not None:
            try:
                rule.guard(mr, actor_id, kwargs)
            except InvalidTransition as e:
                # 補 reason="guard_failed"（如 guard 沒自帶 reason）
                if e.reason is None:
                    raise InvalidTransition(str(e), reason="guard_failed") from e
                raise

        # 過 guard 後才 mutate（避免半路失敗留 partial state）
        _apply_side_effects(mr, action, actor_id=actor_id, kwargs=kwargs)
        mr.status = rule.to_state
        mr.updated_at = _utc_now()
        return mr
