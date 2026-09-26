"""FastAPI router for DayWorkForm get-or-create + activities + query（WMOM-20260505-21）。

5 endpoints：

- POST   /api/workflow/day-work-forms                    （取得或建立當天日誌，idempotent）
- GET    /api/workflow/day-work-forms                    （列表，可加 employee_id / 日期範圍篩選）
- GET    /api/workflow/day-work-forms/by-date             （「我今天做了什麼」單日 query）
- GET    /api/workflow/day-work-forms/{form_id}            （detail）
- POST   /api/workflow/day-work-forms/{form_id}/activities （新增一筆活動）

讀取端點 ownership 限制（WMOM-20260926-01 item 3）：``WMOM_AUTH_ENFORCE=true`` 後，
EMPLOYEE / TREASURY 一律只能查自己的日誌（list 強制收窄 employee_id、by-date/detail
非本人 403）；LEADER / SUPERVISOR / ADMIN 維持可查全員。enforce=false（過渡期）不限制，
維持既有全開放行為。

本次範圍**不含** work_order 完工自動寫入 day_work_form 的整合 hook（見 domain 模組
docstring 說明，涉及既有簽核流程耦合風險，另評估，見 `WMOM-20260926-01` item 2）。
"""

from __future__ import annotations

from datetime import date
from typing import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from modules.auth.dependencies import (
    require_authenticated,
    require_role,
    resolve_actor_id,
    resolve_actor_when_enforced,
)
from modules.auth.roles import Role
from modules.workflow.domain.day_work_form import ActivityEntry
from modules.workflow.repository.day_work_form_repository import (
    DayWorkFormRepository,
    get_day_work_form_repository,
)
from modules.workflow.schemas.day_work_form_schemas import (
    AppendActivityRequest,
    CreateDayWorkFormRequest,
    DayWorkFormListResponse,
    DayWorkFormResponse,
)
from shared.farm_registry_provider import reset_farm_registry, resolve_farm_db_path


router = APIRouter(prefix="/api/workflow", tags=["workflow-day-work-form"])


# ─────────────────────────────────────────────────────────────────────────
# Repository factory injection（test mock 用，沿襲 inspection_router 慣例）
# ─────────────────────────────────────────────────────────────────────────


_repo_factory: Callable[[str], DayWorkFormRepository] | None = None


def set_day_work_form_factory(
    factory: Callable[[str], DayWorkFormRepository] | None,
) -> None:
    """注入 factory：``factory(farm_id) -> DayWorkFormRepository``。

    ``None`` → 走預設（從 monitoring FarmRegistry 拿 farm DB path），同時清 lazy
    singleton（沿襲 inspection_router / inventory_router 慣例）。
    """
    global _repo_factory
    _repo_factory = factory
    if factory is None:
        reset_farm_registry()


def _get_repo(farm_id: str) -> DayWorkFormRepository:
    if _repo_factory is not None:
        return _repo_factory(farm_id)
    return get_day_work_form_repository(resolve_farm_db_path(farm_id))


def _employee_uuid(request: Request, body_employee_id: UUID | None) -> UUID:
    """雙模式解析當事員工身分（token 優先，否則沿用 body），同 ``work_order_router._actor_uuid``。

    day_work_form 是自填日誌——``employee_id`` 恆等於呼叫者本人，不支援代填。
    """
    resolved = resolve_actor_id(
        request, str(body_employee_id) if body_employee_id else None
    )
    try:
        return UUID(resolved)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"employee_id 非合法 UUID: {resolved}")


# 讀取端點 ownership 限制（WMOM-20260926-01 item 3）：維持可查全員的角色——
# TREASURY 刻意不列入（issue 原文點名的問題案例，收窄成只能查自己，同 EMPLOYEE）。
_FULL_VISIBILITY_ROLES = frozenset({Role.LEADER, Role.SUPERVISOR, Role.ADMIN})


def _viewer_uuid(actor_id: str) -> UUID:
    """把 :func:`resolve_actor_when_enforced` 回傳的 ``Actor.id`` 轉 UUID（400 同 ``_employee_uuid``）。"""
    try:
        return UUID(actor_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"actor id 非合法 UUID: {actor_id}")


# ─────────────────────────────────────────────────────────────────────────
# get-or-create
# ─────────────────────────────────────────────────────────────────────────


@router.post(
    "/day-work-forms",
    response_model=DayWorkFormResponse,
    # 自填日誌＝現場工程師 + 管理層（比照 work_order 建單權限）。enforce=false 放行。
    dependencies=[Depends(require_role(Role.EMPLOYEE, Role.LEADER, Role.SUPERVISOR))],
)
async def get_or_create_day_work_form(
    req: CreateDayWorkFormRequest, request: Request
) -> DayWorkFormResponse:
    """取得或建立當天日誌（idempotent，一天一位員工僅一份）。"""
    employee_id = _employee_uuid(request, req.employee_id)
    repo = _get_repo(req.farm_id)
    form = repo.get_or_create_for_date(
        farm_id=req.farm_id,
        employee_id=employee_id,
        work_date=req.work_date,
        created_by=employee_id,
    )
    return DayWorkFormResponse.model_validate(form)


# ─────────────────────────────────────────────────────────────────────────
# query
# ─────────────────────────────────────────────────────────────────────────


@router.get(
    "/day-work-forms",
    response_model=DayWorkFormListResponse,
    dependencies=[Depends(require_authenticated())],
)
async def list_day_work_forms(
    request: Request,
    farm_id: str = Query(..., min_length=1),
    employee_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> DayWorkFormListResponse:
    """查詢日誌列表（依 ``work_date`` 降冪，最新在前）。

    Ownership 限制：enforce 生效後，EMPLOYEE/TREASURY 一律強制收窄成查自己
    （忽略帶入的 ``employee_id``）；LEADER/SUPERVISOR/ADMIN 維持可查全員。
    """
    viewer = resolve_actor_when_enforced(request)
    if viewer is not None and viewer.role not in _FULL_VISIBILITY_ROLES:
        employee_id = _viewer_uuid(viewer.id)
    repo = _get_repo(farm_id)
    items, total = repo.list(
        farm_id=farm_id,
        employee_id=employee_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return DayWorkFormListResponse(
        total=total,
        items=[DayWorkFormResponse.model_validate(f) for f in items],
    )


@router.get(
    "/day-work-forms/by-date",
    response_model=DayWorkFormResponse,
    dependencies=[Depends(require_authenticated())],
)
async def get_day_work_form_by_date(
    request: Request,
    farm_id: str = Query(..., min_length=1),
    employee_id: UUID = Query(...),
    work_date: date = Query(...),
) -> DayWorkFormResponse:
    """「我今天做了什麼」單日 query——純讀取，尚未建立過回 404（前端可據此決定要不要呼叫建立）。

    Ownership 限制：enforce 生效後，EMPLOYEE/TREASURY 帶入非本人 ``employee_id`` → 403
    （``employee_id`` 為必填參數，呼叫端明確指定了對象，靜默覆寫比 403 更危險——會讓
    呼叫端誤以為拿到了指定對象的資料）。
    """
    viewer = resolve_actor_when_enforced(request)
    if (
        viewer is not None
        and viewer.role not in _FULL_VISIBILITY_ROLES
        and _viewer_uuid(viewer.id) != employee_id
    ):
        raise HTTPException(status_code=403, detail="只能查詢自己的日誌")
    repo = _get_repo(farm_id)
    form = repo.get_by_date(farm_id=farm_id, employee_id=employee_id, work_date=work_date)
    if form is None:
        raise HTTPException(
            status_code=404,
            detail=f"day_work_form not found: employee={employee_id} date={work_date}",
        )
    return DayWorkFormResponse.model_validate(form)


@router.get(
    "/day-work-forms/{form_id}",
    response_model=DayWorkFormResponse,
    dependencies=[Depends(require_authenticated())],
)
async def get_day_work_form(
    request: Request, form_id: UUID, farm_id: str = Query(..., min_length=1)
) -> DayWorkFormResponse:
    """detail query。Ownership 限制：404 優先於 403（不洩漏「這份日誌存在但不是你的」），
    enforce 生效後 EMPLOYEE/TREASURY 非本人一律 403，比照 ``append_activity`` 既有慣例。
    """
    repo = _get_repo(farm_id)
    form = repo.get(form_id)
    if form is None:
        raise HTTPException(status_code=404, detail=f"day_work_form {form_id} not found")
    viewer = resolve_actor_when_enforced(request)
    if (
        viewer is not None
        and viewer.role not in _FULL_VISIBILITY_ROLES
        and _viewer_uuid(viewer.id) != form.employee_id
    ):
        raise HTTPException(status_code=403, detail="只能查詢自己的日誌")
    return DayWorkFormResponse.model_validate(form)


# ─────────────────────────────────────────────────────────────────────────
# activity
# ─────────────────────────────────────────────────────────────────────────


@router.post(
    "/day-work-forms/{form_id}/activities",
    response_model=DayWorkFormResponse,
    dependencies=[Depends(require_role(Role.EMPLOYEE, Role.LEADER, Role.SUPERVISOR))],
)
async def append_day_work_form_activity(
    form_id: UUID,
    req: AppendActivityRequest,
    request: Request,
    farm_id: str = Query(..., min_length=1),
) -> DayWorkFormResponse:
    """新增一筆活動到日誌。必填欄位依 ``kind`` 不同，schema 層已先擋一次 422。

    Review must-fix：不支援代填（模組 docstring 明文的設計不變量）——先查出日誌本人
    （``form.employee_id``），比對呼叫者 ``_employee_uuid`` 解出的身分，不同者一律
    403，**不分角色**（LEADER/SUPERVISOR 也不能代填，只能查全員，見 querying
    endpoints 的角色差異）。form 不存在時 404 優先於 403（不洩漏「這份日誌存在但
    不是你的」這種資訊，統一表現為「查無此日誌」）。
    """
    repo = _get_repo(farm_id)
    form = repo.get(form_id)
    if form is None:
        raise HTTPException(status_code=404, detail=f"day_work_form {form_id} not found")

    actor_id = _employee_uuid(request, req.employee_id)
    if actor_id != form.employee_id:
        raise HTTPException(status_code=403, detail="只能新增到自己的日誌")

    entry = ActivityEntry(
        kind=req.kind,
        wo_id=req.wo_id,
        item_id=req.item_id,
        result=req.result,
        area=req.area,
        topic=req.topic,
        note=req.note,
    )
    try:
        form = repo.append_activity(form_id, entry)
    except LookupError:
        raise HTTPException(status_code=404, detail=f"day_work_form {form_id} not found")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return DayWorkFormResponse.model_validate(form)
