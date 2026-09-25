"""windMindOM workflow routers — FastAPI routers（WMOM-20260504-17 / -18 / -20260509-03 / -04）。

Endpoints:

**work-order (WMOM-17)** — exported as ``router``:
- POST  /api/workflow/work-orders
- GET   /api/workflow/work-orders
- GET   /api/workflow/work-orders/{id}
- POST  /api/workflow/work-orders/{id}/{dispatch|start-work|update-progress|finish|approve|reject|cancel|reopen}

**approval (WMOM-18)** — exported as ``approval_router``:
- GET   /api/workflow/approvals/pending
- POST  /api/workflow/approvals/{step_id}/approve  (含 MATERIAL_REQUEST auto-dispatch hook)
- POST  /api/workflow/approvals/{step_id}/reject

**material-request (WMOM-20260509-03)** — exported as ``material_request_router``:
- POST  /api/workflow/material-requests
- GET   /api/workflow/material-requests
- GET   /api/workflow/material-requests/{id}
- POST  /api/workflow/material-requests/{id}/{submit-for-approval|dispatch|receive|close|cancel|returns}

**inventory (WMOM-20260509-04)** — exported as ``inventory_router``:
- POST  /api/workflow/warehouses
- GET   /api/workflow/warehouses
- POST  /api/workflow/inventory                       (create item)
- GET   /api/workflow/inventory                       (list + safety filter)
- GET   /api/workflow/inventory/{item_id}
- PATCH /api/workflow/inventory/{item_id}             (metadata 不動 stock)
- POST  /api/workflow/inventory/{item_id}/adjust      (手動 +/- + audit log)
- GET   /api/workflow/inventory/{item_id}/adjustments

**inspection-schedule (WMOM-20260505-22)** — exported as ``inspection_router``:
- POST  /api/workflow/inspection-schedules
- GET   /api/workflow/inspection-schedules
- GET   /api/workflow/inspection-schedules/{id}
- PATCH /api/workflow/inspection-schedules/{id}
- POST  /api/workflow/inspection-schedules/{id}/{activate|deactivate}
- POST  /api/workflow/inspection-schedules/run-scheduler
"""

from .approval_router import router as approval_router
from .inspection_router import router as inspection_router
from .inventory_router import router as inventory_router
from .material_request_router import router as material_request_router
from .work_order_router import router

__all__ = [
    "router",
    "approval_router",
    "material_request_router",
    "inventory_router",
    "inspection_router",
]
