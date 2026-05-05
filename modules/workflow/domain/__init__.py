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
from .signoff import (
    DEFAULT_MATERIAL_REQUEST_CHAIN,
    DEFAULT_WORK_ORDER_CHAIN,
    SignoffChain,
    SignoffHistoryEntry,
    SignoffLevel,
    SignoffStatus,
    SignoffStep,
    SignoffSubjectType,
    build_chain_levels,
    user_group_to_level,
)

__all__ = [
    "DEFAULT_MATERIAL_REQUEST_CHAIN",
    "DEFAULT_WORK_ORDER_CHAIN",
    "FollowupKind",
    "InvalidTransition",
    "Priority",
    "ProgressNote",
    "SignoffChain",
    "SignoffHistoryEntry",
    "SignoffLevel",
    "SignoffStatus",
    "SignoffStep",
    "SignoffSubjectType",
    "TransitionRule",
    "WORK_ORDER_TRANSITIONS",
    "WorkOrder",
    "WorkOrderFollowup",
    "WorkOrderStateMachine",
    "WorkOrderStatus",
    "WorkOrderType",
    "build_chain_levels",
    "open_states",
    "reopenable_states",
    "terminal_states",
    "user_group_to_level",
]
