"""windMindOM workflow routers — FastAPI routers（WMOM-20260504-17 / -18）。

Endpoints:

**work-order (WMOM-17)** — exported as ``router``:
- POST  /api/workflow/work-orders
- GET   /api/workflow/work-orders
- GET   /api/workflow/work-orders/{id}
- POST  /api/workflow/work-orders/{id}/{dispatch|start-work|update-progress|finish|approve|reject|cancel|reopen}

**approval (WMOM-18)** — exported as ``approval_router``:
- GET   /api/workflow/approvals/pending
- POST  /api/workflow/approvals/{step_id}/approve
- POST  /api/workflow/approvals/{step_id}/reject
"""

from .approval_router import router as approval_router
from .work_order_router import router

__all__ = ["router", "approval_router"]
