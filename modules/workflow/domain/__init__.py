"""windMindOM workflow domain layer — pure dataclass + Enum + state machine。

不接 SQLAlchemy / FastAPI；給 repository / router 層 import 用。
對應 [DN-01](../../../docs/design-notes/m3/DN-01-work-order-lifecycle.md) +
[DN-02](../../../docs/design-notes/m3/DN-02-approval-multilevel.md) +
[DN-03](../../../docs/design-notes/m3/DN-03-inventory-material-request.md)。
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
from .inventory import (
    InventoryAdjustmentLog,
    InventoryItem,
    MaterialRequest,
    MaterialRequestItem,
    MaterialRequestNotification,
    MaterialRequestStatus,
    MaterialReturn,
    ReturnReason,
    StockKind,
    Warehouse,
)
from .inventory_state_machine import (
    MATERIAL_REQUEST_TRANSITIONS,
    MaterialRequestStateMachine,
    MaterialRequestTransitionRule,
    open_states_mr,
    terminal_states_mr,
)
from .inspection_schedule import (
    InspectionSchedule,
    Recurrence,
    compute_next_due,
    recurrence_interval_days,
)
from .day_work_form import (
    ACTIVITY_REQUIRED_FIELDS,
    ActivityEntry,
    ActivityKind,
    DayWorkForm,
    validate_activity_entry,
)

__all__ = [
    # Work order + signoff (M3)
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
    # Inventory + material request (M4 / WMOM-20260509-01)
    "InventoryAdjustmentLog",
    "InventoryItem",
    "MATERIAL_REQUEST_TRANSITIONS",
    "MaterialRequest",
    "MaterialRequestItem",
    "MaterialRequestNotification",
    "MaterialRequestStateMachine",
    "MaterialRequestStatus",
    "MaterialRequestTransitionRule",
    "MaterialReturn",
    "ReturnReason",
    "StockKind",
    "Warehouse",
    "open_states_mr",
    "terminal_states_mr",
    # Inspection schedule (WMOM-20260505-22)
    "InspectionSchedule",
    "Recurrence",
    "compute_next_due",
    "recurrence_interval_days",
    # Day work form (WMOM-20260505-21)
    "ACTIVITY_REQUIRED_FIELDS",
    "ActivityEntry",
    "ActivityKind",
    "DayWorkForm",
    "validate_activity_entry",
]
