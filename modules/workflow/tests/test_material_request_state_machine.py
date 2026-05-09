"""WMOM-20260509-01 — MaterialRequest state machine 測試。

涵蓋：
- 8 個 transition action（submit_for_approval / approve_all / reject / dispatch /
  receive / mark_used / close / cancel）的 happy path
- 各 transition 在錯誤 source state 被擋（InvalidTransition）
- guard 條件 fail（empty items / missing actual_qty / missing reason）
- side-effect 欄位正確（timestamps / cancel_reason / reject_reason / actual_qty）
- ``can_transition`` / ``available_actions`` helper 行為
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from modules.workflow.domain import InvalidTransition
from modules.workflow.domain.inventory import (
    MaterialRequest,
    MaterialRequestItem,
    MaterialRequestStatus,
    StockKind,
)
from modules.workflow.domain.inventory_state_machine import (
    MATERIAL_REQUEST_TRANSITIONS,
    MaterialRequestStateMachine,
    open_states_mr,
    terminal_states_mr,
)


# ─────────────────────────────────────────────────────────────────────────
# fixtures
# ─────────────────────────────────────────────────────────────────────────


def _make_mr(with_items: bool = True) -> MaterialRequest:
    mr = MaterialRequest(
        farm_id="changhua",
        requester_id=uuid4(),
        business_key="MR-cha-202608-99",
    )
    if with_items:
        mr.items.append(
            MaterialRequestItem(
                request_id=mr.id,
                item_id=uuid4(),
                estimated_qty=2,
                stock_kind=StockKind.NEW,
            )
        )
    return mr


def _force_status(mr: MaterialRequest, status: MaterialRequestStatus) -> None:
    """繞過 state machine 直接設 status（給 test fixtures 用）。"""
    mr.status = status


# ─────────────────────────────────────────────────────────────────────────
# Transition table sanity
# ─────────────────────────────────────────────────────────────────────────


def test_transition_table_has_8_actions():
    expected = {
        "submit_for_approval",
        "approve_all",
        "reject",
        "dispatch",
        "receive",
        "mark_used",
        "close",
        "cancel",
    }
    assert set(MATERIAL_REQUEST_TRANSITIONS.keys()) == expected


def test_open_and_terminal_states_partition_correctly():
    """Open + terminal 應該不重疊，兩者聯集涵蓋所有 status。"""
    open_set = open_states_mr()
    term_set = terminal_states_mr()
    assert open_set.isdisjoint(term_set)
    all_status = set(MaterialRequestStatus)
    assert open_set | term_set == all_status


# ─────────────────────────────────────────────────────────────────────────
# submit_for_approval
# ─────────────────────────────────────────────────────────────────────────


def test_submit_for_approval_happy_path():
    mr = _make_mr()
    MaterialRequestStateMachine.transition(mr, "submit_for_approval")
    assert mr.status is MaterialRequestStatus.AWAITING_APPROVAL
    assert mr.submitted_at is not None


def test_submit_requires_items():
    mr = _make_mr(with_items=False)
    with pytest.raises(InvalidTransition, match="at least one item"):
        MaterialRequestStateMachine.transition(mr, "submit_for_approval")


def test_submit_only_from_draft():
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.AWAITING_APPROVAL)
    with pytest.raises(InvalidTransition, match="cannot transition"):
        MaterialRequestStateMachine.transition(mr, "submit_for_approval")


# ─────────────────────────────────────────────────────────────────────────
# approve_all
# ─────────────────────────────────────────────────────────────────────────


def test_approve_all_happy_path():
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.AWAITING_APPROVAL)
    MaterialRequestStateMachine.transition(mr, "approve_all")
    assert mr.status is MaterialRequestStatus.APPROVED
    assert mr.approved_at is not None


def test_approve_all_only_from_awaiting():
    mr = _make_mr()
    with pytest.raises(InvalidTransition, match="cannot transition"):
        MaterialRequestStateMachine.transition(mr, "approve_all")


# ─────────────────────────────────────────────────────────────────────────
# reject
# ─────────────────────────────────────────────────────────────────────────


def test_reject_happy_path_records_reason():
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.AWAITING_APPROVAL)
    MaterialRequestStateMachine.transition(
        mr, "reject", reject_reason="Item not on approved supplier list"
    )
    assert mr.status is MaterialRequestStatus.REJECTED
    assert mr.reject_reason == "Item not on approved supplier list"
    assert mr.rejected_at is not None


def test_reject_requires_reason():
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.AWAITING_APPROVAL)
    with pytest.raises(InvalidTransition, match="non-empty reject_reason"):
        MaterialRequestStateMachine.transition(mr, "reject", reject_reason="")


def test_reject_blank_reason_rejected():
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.AWAITING_APPROVAL)
    with pytest.raises(InvalidTransition):
        MaterialRequestStateMachine.transition(mr, "reject", reject_reason="   ")


# ─────────────────────────────────────────────────────────────────────────
# dispatch（domain only — repository 雙寫在 A2）
# ─────────────────────────────────────────────────────────────────────────


def test_dispatch_happy_path_from_approved():
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.APPROVED)
    MaterialRequestStateMachine.transition(mr, "dispatch")
    assert mr.status is MaterialRequestStatus.DISPATCHED
    assert mr.dispatched_at is not None


def test_dispatch_only_from_approved():
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.AWAITING_APPROVAL)
    with pytest.raises(InvalidTransition, match="cannot transition"):
        MaterialRequestStateMachine.transition(mr, "dispatch")


# ─────────────────────────────────────────────────────────────────────────
# receive
# ─────────────────────────────────────────────────────────────────────────


def test_receive_happy_path_writes_actual_qty():
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.DISPATCHED)
    item_id = mr.items[0].id
    MaterialRequestStateMachine.transition(
        mr, "receive", actual_quantities={item_id: 2}
    )
    assert mr.status is MaterialRequestStatus.RECEIVED
    assert mr.items[0].actual_qty == 2
    assert mr.received_at is not None


def test_receive_partial_qty_allowed():
    """實際領用 < 估計（用剩 / 退回部分），合法。"""
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.DISPATCHED)
    item_id = mr.items[0].id
    MaterialRequestStateMachine.transition(
        mr, "receive", actual_quantities={item_id: 1}  # estimated = 2
    )
    assert mr.items[0].actual_qty == 1


def test_receive_zero_actual_allowed():
    """實際領用 = 0（全退回，但仍走 receive 流程記簽收）。"""
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.DISPATCHED)
    item_id = mr.items[0].id
    MaterialRequestStateMachine.transition(
        mr, "receive", actual_quantities={item_id: 0}
    )
    assert mr.items[0].actual_qty == 0


def test_receive_requires_actual_quantities_dict():
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.DISPATCHED)
    with pytest.raises(InvalidTransition, match="actual_quantities"):
        MaterialRequestStateMachine.transition(mr, "receive")


def test_receive_missing_item_in_dict_rejected():
    mr = _make_mr()
    mr.items.append(
        MaterialRequestItem(
            request_id=mr.id, item_id=uuid4(), estimated_qty=1
        )
    )
    _force_status(mr, MaterialRequestStatus.DISPATCHED)
    only_first = {mr.items[0].id: 1}
    with pytest.raises(InvalidTransition, match="missing for items"):
        MaterialRequestStateMachine.transition(
            mr, "receive", actual_quantities=only_first
        )


def test_receive_negative_qty_rejected():
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.DISPATCHED)
    item_id = mr.items[0].id
    with pytest.raises(InvalidTransition, match="must be int >= 0"):
        MaterialRequestStateMachine.transition(
            mr, "receive", actual_quantities={item_id: -1}
        )


# ─────────────────────────────────────────────────────────────────────────
# mark_used
# ─────────────────────────────────────────────────────────────────────────


def test_mark_used_from_received():
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.RECEIVED)
    MaterialRequestStateMachine.transition(mr, "mark_used")
    assert mr.status is MaterialRequestStatus.USED
    assert mr.used_at is not None


def test_mark_used_only_from_received():
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.DISPATCHED)
    with pytest.raises(InvalidTransition):
        MaterialRequestStateMachine.transition(mr, "mark_used")


# ─────────────────────────────────────────────────────────────────────────
# close
# ─────────────────────────────────────────────────────────────────────────


def test_close_from_used():
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.USED)
    MaterialRequestStateMachine.transition(mr, "close")
    assert mr.status is MaterialRequestStatus.CLOSED
    assert mr.closed_at is not None


def test_close_from_received_skips_used():
    """RECEIVED → CLOSED 合法（工單沒有真正用到，直接結案）。"""
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.RECEIVED)
    MaterialRequestStateMachine.transition(mr, "close")
    assert mr.status is MaterialRequestStatus.CLOSED


def test_close_from_draft_rejected():
    """DRAFT → CLOSED 不合法（要走 cancel）。"""
    mr = _make_mr()
    with pytest.raises(InvalidTransition):
        MaterialRequestStateMachine.transition(mr, "close")


# ─────────────────────────────────────────────────────────────────────────
# cancel
# ─────────────────────────────────────────────────────────────────────────


def test_cancel_from_draft():
    mr = _make_mr()
    MaterialRequestStateMachine.transition(
        mr, "cancel", cancel_reason="Operator changed mind before submit"
    )
    assert mr.status is MaterialRequestStatus.CANCELLED
    assert mr.cancel_reason == "Operator changed mind before submit"
    assert mr.cancelled_at is not None


def test_cancel_from_awaiting_approval():
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.AWAITING_APPROVAL)
    MaterialRequestStateMachine.transition(
        mr, "cancel", cancel_reason="Wrong supplier"
    )
    assert mr.status is MaterialRequestStatus.CANCELLED


def test_cancel_from_approved():
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.APPROVED)
    MaterialRequestStateMachine.transition(
        mr, "cancel", cancel_reason="Stock came in from elsewhere"
    )
    assert mr.status is MaterialRequestStatus.CANCELLED


def test_cancel_from_dispatched_rejected():
    """DISPATCHED 之後不允許 cancel — 物料已離庫，須走 MaterialReturn 流程。"""
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.DISPATCHED)
    with pytest.raises(InvalidTransition, match="cannot transition"):
        MaterialRequestStateMachine.transition(
            mr, "cancel", cancel_reason="Too late"
        )


def test_cancel_requires_reason():
    mr = _make_mr()
    with pytest.raises(InvalidTransition, match="non-empty cancel_reason"):
        MaterialRequestStateMachine.transition(mr, "cancel", cancel_reason="")


# ─────────────────────────────────────────────────────────────────────────
# Helper methods
# ─────────────────────────────────────────────────────────────────────────


def test_can_transition_returns_bool():
    mr = _make_mr()
    assert MaterialRequestStateMachine.can_transition(mr, "submit_for_approval") is True
    assert MaterialRequestStateMachine.can_transition(mr, "approve_all") is False


def test_can_transition_unknown_action_returns_false():
    mr = _make_mr()
    assert MaterialRequestStateMachine.can_transition(mr, "fly_to_mars") is False


def test_available_actions_for_draft():
    mr = _make_mr()
    actions = set(MaterialRequestStateMachine.available_actions(mr))
    assert actions == {"submit_for_approval", "cancel"}


def test_available_actions_for_received():
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.RECEIVED)
    actions = set(MaterialRequestStateMachine.available_actions(mr))
    assert actions == {"mark_used", "close"}


def test_available_actions_for_terminal_state_empty():
    mr = _make_mr()
    _force_status(mr, MaterialRequestStatus.CLOSED)
    assert MaterialRequestStateMachine.available_actions(mr) == []


def test_unknown_action_raises():
    mr = _make_mr()
    with pytest.raises(InvalidTransition, match="unknown action"):
        MaterialRequestStateMachine.transition(mr, "do_the_thing")


# ─────────────────────────────────────────────────────────────────────────
# End-to-end happy lifecycle（不接 DB / repo，只走 state machine）
# ─────────────────────────────────────────────────────────────────────────


def test_full_happy_lifecycle_draft_to_closed():
    """
    DRAFT → AWAITING_APPROVAL → APPROVED → DISPATCHED → RECEIVED → USED → CLOSED
    """
    mr = _make_mr()
    item_id = mr.items[0].id

    MaterialRequestStateMachine.transition(mr, "submit_for_approval")
    assert mr.status is MaterialRequestStatus.AWAITING_APPROVAL

    MaterialRequestStateMachine.transition(mr, "approve_all")
    assert mr.status is MaterialRequestStatus.APPROVED

    MaterialRequestStateMachine.transition(mr, "dispatch")
    assert mr.status is MaterialRequestStatus.DISPATCHED

    MaterialRequestStateMachine.transition(
        mr, "receive", actual_quantities={item_id: 2}
    )
    assert mr.status is MaterialRequestStatus.RECEIVED
    assert mr.items[0].actual_qty == 2

    MaterialRequestStateMachine.transition(mr, "mark_used")
    assert mr.status is MaterialRequestStatus.USED

    MaterialRequestStateMachine.transition(mr, "close")
    assert mr.status is MaterialRequestStatus.CLOSED

    # Timestamps 全填上
    for ts in (
        mr.submitted_at,
        mr.approved_at,
        mr.dispatched_at,
        mr.received_at,
        mr.used_at,
        mr.closed_at,
    ):
        assert ts is not None
