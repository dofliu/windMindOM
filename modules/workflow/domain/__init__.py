"""windMindOM workflow domain layer — pure dataclass + Enum + state machine。

不接 SQLAlchemy / FastAPI；給 repository / router 層 import 用。
對應 [DN-01](../../../docs/design-notes/m3/DN-01-work-order-lifecycle.md) +
[DN-02](../../../docs/design-notes/m3/DN-02-approval-multilevel.md)。
"""

from .work_order import (
    FollowupKind,
    Priority,
    ProgressNote,
    WorkOrder,
    WorkOrderFollowup,
    WorkOrderStatus,
    WorkOrderType,
)
from .state_machine import (
    InvalidTransition,
    TransitionRule,
    WORK_ORDER_TRANSITIONS,
    WorkOrderStateMachine,
    open_states,
    reopenable_states,
    terminal_states,
)

__all__ = [
    "FollowupKind",
    "InvalidTransition",
    "Priority",
    "ProgressNote",
    "TransitionRule",
    "WORK_ORDER_TRANSITIONS",
    "WorkOrder",
    "WorkOrderFollowup",
    "WorkOrderStateMachine",
    "WorkOrderStatus",
    "WorkOrderType",
    "open_states",
    "reopenable_states",
    "terminal_states",
]
