"""windMindOM workflow routers — FastAPI routers（WMOM-20260504-17 起）。

Endpoints:

| Method | Path                                                         |
|--------|--------------------------------------------------------------|
| POST   | /api/workflow/work-orders                                    |
| GET    | /api/workflow/work-orders                                    |
| GET    | /api/workflow/work-orders/{id}                               |
| POST   | /api/workflow/work-orders/{id}/dispatch                      |
| POST   | /api/workflow/work-orders/{id}/start-work                    |
| POST   | /api/workflow/work-orders/{id}/update-progress               |
| POST   | /api/workflow/work-orders/{id}/finish                        |
| POST   | /api/workflow/work-orders/{id}/approve                       |
| POST   | /api/workflow/work-orders/{id}/reject                        |
| POST   | /api/workflow/work-orders/{id}/cancel                        |
| POST   | /api/workflow/work-orders/{id}/reopen                        |
"""

from .work_order_router import router

__all__ = ["router"]
