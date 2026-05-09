"""windMindOM workflow schemas — pydantic request / response（WMOM-20260504-17 / -18 / -20260509-03）。"""

from .signoff_schemas import (
    ApprovalResultResponse,
    ApproveStepRequest,
    PendingSignoffItem,
    PendingSignoffListResponse,
    RejectStepRequest,
    SignoffChainResponse,
    SignoffStepResponse,
)
from .work_order_schemas import (
    CancelRequest,
    CreateWorkOrderRequest,
    DispatchRequest,
    FinishRequest,
    ProgressNoteResponse,
    RejectRequest,
    ReopenRequest,
    StartWorkRequest,
    UpdateProgressRequest,
    WorkOrderListResponse,
    WorkOrderResponse,
)
from .material_request_schemas import (
    CancelMaterialRequest,
    CloseMaterialRequest,
    CreateMaterialRequest,
    CreateMaterialRequestItem,
    CreateMaterialReturn,
    DispatchMaterialRequest,
    MaterialRequestItemResponse,
    MaterialRequestListResponse,
    MaterialRequestResponse,
    MaterialReturnResponse,
    ReceiveMaterialRequest,
    SubmitForApprovalRequest,
)

__all__ = [
    # signoff
    "ApprovalResultResponse",
    "ApproveStepRequest",
    "PendingSignoffItem",
    "PendingSignoffListResponse",
    "RejectStepRequest",
    "SignoffChainResponse",
    "SignoffStepResponse",
    # work order
    "CancelRequest",
    "CreateWorkOrderRequest",
    "DispatchRequest",
    "FinishRequest",
    "ProgressNoteResponse",
    "RejectRequest",
    "ReopenRequest",
    "StartWorkRequest",
    "UpdateProgressRequest",
    "WorkOrderListResponse",
    "WorkOrderResponse",
    # material request (WMOM-20260509-03)
    "CancelMaterialRequest",
    "CloseMaterialRequest",
    "CreateMaterialRequest",
    "CreateMaterialRequestItem",
    "CreateMaterialReturn",
    "DispatchMaterialRequest",
    "MaterialRequestItemResponse",
    "MaterialRequestListResponse",
    "MaterialRequestResponse",
    "MaterialReturnResponse",
    "ReceiveMaterialRequest",
    "SubmitForApprovalRequest",
]
