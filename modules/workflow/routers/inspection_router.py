"""FastAPI router for InspectionSchedule CRUD + scheduler trigger（WMOM-20260505-22）。

8 endpoints：

- POST   /api/workflow/inspection-schedules                  （建計畫）
- GET    /api/workflow/inspection-schedules                  （列表，可加 due_only）
- GET    /api/workflow/inspection-schedules/{id}              （detail）
- PATCH  /api/workflow/inspection-schedules/{id}              （改標題/說明/週期）
- POST   /api/workflow/inspection-schedules/{id}/activate     （恢復）
- POST   /api/workflow/inspection-schedules/{id}/deactivate   （暫停，軟刪除慣例）
- POST   /api/workflow/inspection-schedules/run-scheduler     （手動觸發到期 spawn）

``run-scheduler`` 是本次範圍內「排程觸發」的唯一入口（無背景 cron，見
``services/inspection_scheduler.py`` docstring 說明），由 SUPERVISOR 手動呼叫，
或未來由外部排程器（如 OS-level cron 呼叫這支 API）觸發。
"""

from __future__ import annotations

from typing import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from modules.auth.dependencies import require_authenticated, require_role
from modules.auth.roles import Role
from modules.workflow.repository import (
    InspectionScheduleRepository,
    WorkOrderRepository,
    get_inspection_repository,
    get_repository,
)
from modules.workflow.schemas import (
    CreateInspectionScheduleRequest,
    InspectionScheduleListResponse,
    InspectionScheduleResponse,
    RunSchedulerResponse,
    UpdateInspectionScheduleRequest,
)
from modules.workflow.services.inspection_scheduler import run_inspection_scheduler
from shared.farm_registry_provider import reset_farm_registry, resolve_farm_db_path


router = APIRouter(prefix="/api/workflow", tags=["workflow-inspection"])


# ─────────────────────────────────────────────────────────────────────────
# Repository factory injection（test mock 用，沿襲 work_order_router / inventory_router）
# ─────────────────────────────────────────────────────────────────────────


_inspection_factory: Callable[[str], InspectionScheduleRepository] | None = None
_work_order_factory: Callable[[str], WorkOrderRepository] | None = None


def set_inspection_factory(
    factory: Callable[[str], InspectionScheduleRepository] | None,
) -> None:
    """注入 factory：``factory(farm_id) -> InspectionScheduleRepository``。

    None → 走預設（從 monitoring FarmRegistry 拿 farm DB path），同時清 lazy
    singleton（沿襲 inventory_router 慣例）。
    """
    global _inspection_factory
    _inspection_factory = factory
    if factory is None:
        reset_farm_registry()


def set_work_order_factory_for_scheduler(
    factory: Callable[[str], WorkOrderRepository] | None,
) -> None:
    """注入 ``run-scheduler`` 用的 ``WorkOrderRepository`` factory（test mock 用）。

    與 ``work_order_router.set_repository_factory`` 是各自獨立的 module-level 變數
    （兩個 router 各自的注入點），呼叫本函式不影響 ``work_order_router`` 自己的測試。
    """
    global _work_order_factory
    _work_order_factory = factory


def _get_inspection_repo(farm_id: str) -> InspectionScheduleRepository:
    if _inspection_factory is not None:
        return _inspection_factory(farm_id)
    return get_inspection_repository(resolve_farm_db_path(farm_id))


def _get_work_order_repo(farm_id: str) -> WorkOrderRepository:
    if _work_order_factory is not None:
        return _work_order_factory(farm_id)
    return get_repository(resolve_farm_db_path(farm_id))


# ─────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────


@router.post(
    "/inspection-schedules",
    response_model=InspectionScheduleResponse,
    status_code=201,
    # 定檢計畫排定＝組長 / 主管（比照派工權限）。enforce=false 時放行（過渡期）。
    dependencies=[Depends(require_role(Role.LEADER, Role.SUPERVISOR))],
)
async def create_inspection_schedule(
    req: CreateInspectionScheduleRequest,
) -> InspectionScheduleResponse:
    repo = _get_inspection_repo(req.farm_id)
    try:
        sched = repo.create(
            farm_id=req.farm_id,
            turbine_id=req.turbine_id,
            title=req.title,
            description=req.description,
            recurrence=req.recurrence,
            interval_days=req.interval_days,
            first_due_at=req.first_due_at,
            created_by=req.created_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return InspectionScheduleResponse.model_validate(sched)


@router.get(
    "/inspection-schedules",
    response_model=InspectionScheduleListResponse,
    dependencies=[Depends(require_authenticated())],
)
async def list_inspection_schedules(
    farm_id: str = Query(..., min_length=1),
    turbine_id: str | None = None,
    active_only: bool = False,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> InspectionScheduleListResponse:
    """查詢定檢計畫列表（依 ``next_due_at`` 升冪，最快到期的排前面）。"""
    repo = _get_inspection_repo(farm_id)
    items, total = repo.list(
        farm_id=farm_id,
        turbine_id=turbine_id,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )
    return InspectionScheduleListResponse(
        total=total,
        items=[InspectionScheduleResponse.model_validate(s) for s in items],
    )


@router.get(
    "/inspection-schedules/{schedule_id}",
    response_model=InspectionScheduleResponse,
    dependencies=[Depends(require_authenticated())],
)
async def get_inspection_schedule(
    schedule_id: UUID, farm_id: str = Query(..., min_length=1)
) -> InspectionScheduleResponse:
    repo = _get_inspection_repo(farm_id)
    sched = repo.get(schedule_id)
    if sched is None:
        raise HTTPException(
            status_code=404, detail=f"inspection_schedule {schedule_id} not found"
        )
    return InspectionScheduleResponse.model_validate(sched)


@router.patch(
    "/inspection-schedules/{schedule_id}",
    response_model=InspectionScheduleResponse,
    dependencies=[Depends(require_role(Role.LEADER, Role.SUPERVISOR))],
)
async def update_inspection_schedule(
    schedule_id: UUID,
    req: UpdateInspectionScheduleRequest,
    farm_id: str = Query(..., min_length=1),
) -> InspectionScheduleResponse:
    """改計畫內容。``next_due_at`` 不受影響（見 repository docstring 說明）。

    Review must-fix：PATCH 成 ``recurrence=custom_days`` 卻不帶（或原本沒有）
    ``interval_days`` 是無效組合，改完後的最終狀態由 ``update_metadata`` 驗證
    （schema 層看不到資料庫現有狀態，無法單獨判斷），這裡把它的 ``ValueError``
    轉成 422。
    """
    repo = _get_inspection_repo(farm_id)
    payload = req.model_dump(exclude_unset=True)
    try:
        sched = repo.update_metadata(schedule_id, **payload)
    except LookupError:
        raise HTTPException(
            status_code=404, detail=f"inspection_schedule {schedule_id} not found"
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return InspectionScheduleResponse.model_validate(sched)


@router.post(
    "/inspection-schedules/{schedule_id}/activate",
    response_model=InspectionScheduleResponse,
    dependencies=[Depends(require_role(Role.LEADER, Role.SUPERVISOR))],
)
async def activate_inspection_schedule(
    schedule_id: UUID, farm_id: str = Query(..., min_length=1)
) -> InspectionScheduleResponse:
    repo = _get_inspection_repo(farm_id)
    try:
        sched = repo.set_active(schedule_id, True)
    except LookupError:
        raise HTTPException(
            status_code=404, detail=f"inspection_schedule {schedule_id} not found"
        )
    return InspectionScheduleResponse.model_validate(sched)


@router.post(
    "/inspection-schedules/{schedule_id}/deactivate",
    response_model=InspectionScheduleResponse,
    dependencies=[Depends(require_role(Role.LEADER, Role.SUPERVISOR))],
)
async def deactivate_inspection_schedule(
    schedule_id: UUID, farm_id: str = Query(..., min_length=1)
) -> InspectionScheduleResponse:
    """暫停計畫（軟刪除慣例）——``active=False`` 後 scheduler 不會再挑中此排程。"""
    repo = _get_inspection_repo(farm_id)
    try:
        sched = repo.set_active(schedule_id, False)
    except LookupError:
        raise HTTPException(
            status_code=404, detail=f"inspection_schedule {schedule_id} not found"
        )
    return InspectionScheduleResponse.model_validate(sched)


# ─────────────────────────────────────────────────────────────────────────
# Scheduler trigger
# ─────────────────────────────────────────────────────────────────────────


@router.post(
    "/inspection-schedules/run-scheduler",
    response_model=RunSchedulerResponse,
    # 手動觸發 spawn 工單＝主管（會建立真實工單，權限比照查詢/更新更高）。
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def run_scheduler(
    farm_id: str = Query(..., min_length=1),
) -> RunSchedulerResponse:
    """檢查 ``farm_id`` 內所有到期排程並 spawn 對應 INSPECTION 工單。

    冪等：同一到期週期內重複呼叫不會重複 spawn（見 service docstring）。
    """
    inspection_repo = _get_inspection_repo(farm_id)
    work_order_repo = _get_work_order_repo(farm_id)
    spawned = run_inspection_scheduler(inspection_repo, work_order_repo, farm_id)
    return RunSchedulerResponse(
        spawned=[
            {
                "schedule_id": s.schedule_id,
                "work_order_id": s.work_order_id,
                "turbine_id": s.turbine_id,
                "next_due_at": s.next_due_at,
            }
            for s in spawned
        ]
    )
