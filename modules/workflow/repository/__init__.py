"""windMindOM workflow repository layer — SQLAlchemy 2.0 ORM + Repository。

對應：
- [WMOM-20260504-17](../../../ISSUES.md)（work_order CRUD + state）
- [WMOM-20260504-18](../../../ISSUES.md)（signoff multi-level）
- [WMOM-20260509-02](../../../ISSUES.md)（inventory + material_request 雙寫）

與 monitoring (raw sqlite3) 並存於同一個 farm DB（``wind_farm.db``），
SQLite WAL mode 已開可並發讀寫。
"""

from .orm_models import (
    Base,
    ProgressNoteORM,
    SignoffChainORM,
    SignoffHistoryORM,
    SignoffStepORM,
    WorkOrderEventLogORM,
    WorkOrderORM,
)
from .signoff_repository import (
    SignoffActionError,
    SignoffRepository,
    get_signoff_repository,
)
from .work_order_repository import (
    BusinessRuleViolation,
    WorkOrderRepository,
    get_repository,
)
from .inventory_orm import (
    InventoryAdjustmentLogORM,
    InventoryItemORM,
    MaterialRequestItemORM,
    MaterialRequestNotificationORM,
    MaterialRequestORM,
    MaterialReturnORM,
    WarehouseORM,
)
from .inventory_repository import (
    InsufficientStock,
    InventoryRepository,
    StockAdjustmentError,
    apply_stock_delta_in_session,
    get_inventory_repository,
)
from .material_request_repository import (
    ItemMetadata,
    MaterialRequestRepository,
    MaterialRequestRuleViolation,
    get_material_request_repository,
)

__all__ = [
    # core
    "Base",
    # work_order + signoff (M3)
    "BusinessRuleViolation",
    "ProgressNoteORM",
    "SignoffActionError",
    "SignoffChainORM",
    "SignoffHistoryORM",
    "SignoffRepository",
    "SignoffStepORM",
    "WorkOrderEventLogORM",
    "WorkOrderORM",
    "WorkOrderRepository",
    "get_repository",
    "get_signoff_repository",
    # inventory + material_request (M4)
    "InsufficientStock",
    "InventoryAdjustmentLogORM",
    "InventoryItemORM",
    "InventoryRepository",
    "ItemMetadata",
    "MaterialRequestItemORM",
    "MaterialRequestNotificationORM",
    "MaterialRequestORM",
    "MaterialRequestRepository",
    "MaterialRequestRuleViolation",
    "MaterialReturnORM",
    "StockAdjustmentError",
    "WarehouseORM",
    "apply_stock_delta_in_session",
    "get_inventory_repository",
    "get_material_request_repository",
]
