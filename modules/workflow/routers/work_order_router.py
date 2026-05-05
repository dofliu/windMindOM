"""FastAPI router for Work Order CRUD + state transitions（WMOM-20260504-17）。

11 endpoints. State transitions 都走 ``WorkOrderRepository.transition`` 統一入口
（domain state machine + persist + event log + multi-WO constraint）。

依賴：``modules.monitoring.server.farm_registry`` 的 ``FarmRegistry`` 拿 farm DB path。
為了讓 router 可被 unit test，提供 ``set_repository_factory()`` 注入 mock。
"""

from __future__ import annotations

import logging
from typing import Callable
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from modules.workflow.domain import (
    InvalidTransition,
    Priority,
    WorkOrderStatus,
)

# review fix #14：logging 走 top-level，不放函式體內
_logger = logging.getLogger(__name__)
from modules.workflow.repository import (
    BusinessRuleViolation,
    WorkOrderRepository,
    get_repository,
)
from modules.workflow.schemas import (
    CancelRequest,
    CreateWorkOrderRequest,
    DispatchRequest,
    FinishRequest,
    RejectRequest,
    ReopenRequest,
    StartWorkRequest,
    UpdateProgressRequest,
    WorkOrderListResponse,
    WorkOrderResponse,
)


router = APIRouter(prefix="/api/workflow", tags=["workflow"])


# ─────────────────────────────────────────────────────────────────────────
# Repository factory injection point（給 testing / multi-farm 用）
# ─────────────────────────────────────────────────────────────────────────


_repository_factory: Callable[[str], WorkOrderRepository] | None = None


def set_repository_factory(
    factory: Callable[[str], WorkOrderRepository] | None,
) -> None:
    """注入 repository factory：``factory(farm_id) -> WorkOrderRepository``。

    None → 走預設（從 monitoring FarmRegistry 拿 farm DB path），同時清掉
    `_FARM_REGISTRY` lazy singleton 避免 test 間殘留（review fix #1）。
    """
    global _repository_factory, _FARM_REGISTRY
    _repository_factory = factory
    if factory is None:
        _FARM_REGISTRY = None


# fix #3：FarmRegistry singleton（避免每個 API call 重 init + 開新 sqlite connection）
_FARM_REGISTRY = None


def _get_default_farm_registry():
    """Lazy singleton — module 第一次需要時 init 一次。"""
    global _FARM_REGISTRY
    if _FARM_REGISTRY is None:
        from modules.monitoring.server.farm_registry import FarmRegistry  # type: ignore

        _FARM_REGISTRY = FarmRegistry()
    return _FARM_REGISTRY


def _default_repository_factory(farm_id: str) -> WorkOrderRepository:
    """預設工廠：從 monitoring 的 FarmRegistry 取 farm DB path（singleton 共用）。"""
    try:
        reg = _get_default_farm_registry()
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="FarmRegistry not available; call set_repository_factory() to inject",
        )
    db_path = reg.get_farm_db_path(farm_id)
    if db_path is None:
        raise HTTPException(
            status_code=404, detail=f"Farm not found: {farm_id}"
        )
    return get_repository(str(db_path))


def _get_repo(farm_id: str) -> WorkOrderRepository:
    factory = _repository_factory or _default_repository_factory
    return factory(farm_id)


# ─────────────────────────────────────────────────────────────────────────
# Error mapping helper
# ─────────────────────────────────────────────────────────────────────────


def _map_state_error(action: str, exc: InvalidTransition) -> HTTPException:
    """Domain state machine 拒絕 → 422 (validation) 或 409 (conflict)。

    state mismatch (cannot transition) → 409 Conflict（適合 client 看「現在不能做」）
    guard fail（缺欄位）→ 422 Unprocessable Entity
    """
    msg = str(exc)
    status = 409 if "cannot transition" in msg else 422
    return HTTPException(status_code=status, detail=f"{action}: {msg}")


# ─────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────


@router.post(
    "/work-orders",
    response_model=WorkOrderResponse,
    status_code=201,
)
async def create_work_order(req: CreateWorkOrderRequest) -> WorkOrderResponse:
    """建立 DRAFT 工單。

    強制 multi-WO constraint：
    - ≤ 3 OPEN per turbine（超過 → 409）
    - 不同 source_alarm_code 才可多張（重複 → 409）
    """
    repo = _get_repo(req.farm_id)
    try:
        wo = repo.create(
            farm_id=req.farm_id,
            turbine_id=req.turbine_id,
            type=req.type,
            title=req.title,
            description=req.description,
            priority=req.priority,
            source_alarm_id=req.source_alarm_id,
            source_alarm_code=req.source_alarm_code,
            assignee_id=req.assignee_id,
            crew_size=req.crew_size,
            estimated_hours=req.estimated_hours,
            created_by=req.created_by,
        )
    except BusinessRuleViolation as e:
        raise HTTPException(status_code=409, detail=str(e))
    return WorkOrderResponse.model_validate(wo)


@router.get("/work-orders", response_model=WorkOrderListResponse)
async def list_work_orders(
    farm_id: str = Query(..., min_length=1),
    turbine_id: str | None = None,
    status: WorkOrderStatus | None = None,
    only_open: bool = False,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> WorkOrderListResponse:
    """查詢工單列表（必帶 farm_id；其餘為 filter）。

    回傳 ``total`` = 符合 filter 的真實 row 數（不受 ``limit/offset`` 截斷）；
    ``items`` 為 page 後的工單清單。前端分頁用 ``offset`` + ``total`` 做頁碼計算。

    Review fix #11：加 ``offset`` 支援真分頁（之前只有 limit，超過 200 張看不到）。
    """
    repo = _get_repo(farm_id)
    items, total = repo.list(
        farm_id=farm_id,
        turbine_id=turbine_id,
        status=status,
        only_open=only_open,
        limit=limit,
        offset=offset,
    )
    return WorkOrderListResponse(
        total=total,
        items=[WorkOrderResponse.model_validate(wo) for wo in items],
    )


@router.get("/work-orders/{work_order_id}", response_model=WorkOrderResponse)
async def get_work_order(
    work_order_id: UUID, farm_id: str = Query(..., min_length=1)
) -> WorkOrderResponse:
    repo = _get_repo(farm_id)
    wo = repo.get(work_order_id)
    if wo is None:
        raise HTTPException(status_code=404, detail=f"work_order {work_order_id} not found")
    return WorkOrderResponse.model_validate(wo)


# ─────────────────────────────────────────────────────────────────────────
# State transitions
# ─────────────────────────────────────────────────────────────────────────


@router.post("/work-orders/{work_order_id}/dispatch", response_model=WorkOrderResponse)
async def dispatch(
    work_order_id: UUID,
    req: DispatchRequest,
    farm_id: str = Query(..., min_length=1),
) -> WorkOrderResponse:
    """DRAFT → DISPATCHED。"""
    repo = _get_repo(farm_id)
    return _run_transition(repo, work_order_id, "dispatch", actor_id=req.actor_id)


@router.post("/work-orders/{work_order_id}/start-work", response_model=WorkOrderResponse)
async def start_work(
    work_order_id: UUID,
    req: StartWorkRequest,
    farm_id: str = Query(..., min_length=1),
) -> WorkOrderResponse:
    """DISPATCHED | REOPENED → IN_PROGRESS。

    offshore farm 傳 ``require_weather_window=True`` 強制檢 weather_window_id。
    """
    repo = _get_repo(farm_id)
    return _run_transition(
        repo, work_order_id, "start_work",
        require_weather_window=req.require_weather_window,
    )


@router.post("/work-orders/{work_order_id}/update-progress", response_model=WorkOrderResponse)
async def update_progress(
    work_order_id: UUID,
    req: UpdateProgressRequest,
    farm_id: str = Query(..., min_length=1),
) -> WorkOrderResponse:
    """IN_PROGRESS self-loop：append progress note + 更新 updated_at。"""
    repo = _get_repo(farm_id)
    return _run_transition(
        repo, work_order_id, "update_progress",
        actor_id=req.actor_id,
        note=req.note,
    )


@router.post("/work-orders/{work_order_id}/finish", response_model=WorkOrderResponse)
async def finish(
    work_order_id: UUID,
    req: FinishRequest,
    farm_id: str = Query(..., min_length=1),
) -> WorkOrderResponse:
    """IN_PROGRESS → AWAITING_SIGNOFF + 自動建 signoff chain（DN-02 整合）。

    `actual_hours` + `followup_kind` 必填。
    Side-effect (WMOM-20260504-18)：finish 成功後自動建 signoff chain（依 work_order
    類型 + priority），並 backlink 到 ``work_order.signoff_chain_id``。
    chain 建失敗不會 rollback finish（工單已 AWAITING_SIGNOFF 留著，caller 可重試）。
    """
    repo = _get_repo(farm_id)
    response = _run_transition(
        repo, work_order_id, "finish",
        actual_hours=req.actual_hours,
        followup_kind=req.followup_kind,
        work_summary=req.work_summary,
        unfinished_items=req.unfinished_items,
        followup_note=req.followup_note,
    )

    try:
        # circular import guard：approval_router 在 module level import work_order
        # 相關物件，這裡反方向 import 必須是 runtime 而非 top-level（review fix #9）。
        from modules.workflow.routers.approval_router import (
            get_signoff_repo_for_farm,
        )

        signoff_repo = get_signoff_repo_for_farm(farm_id)
        # review fix #7：response.priority 已是 Priority enum（pydantic v2 coerce），
        # 不需 isinstance 多一層 — 直接用即可
        escalate = response.priority is Priority.CRITICAL
        chain = signoff_repo.create_chain_for_work_order(
            work_order_id=response.id,
            farm_id=farm_id,
            escalate_to_supervisor=escalate,
            actor_id=None,
        )
        repo.set_signoff_chain_id(response.id, chain.id)
        wo = repo.get(response.id)
        if wo is not None:
            return WorkOrderResponse.model_validate(wo)
    except (ValueError, LookupError) as e:
        # review fix #8：細分 expected failure（config 錯誤 / wo 不見）vs 未知 error
        # ValueError → build_chain_levels 全 disabled 拒絕 / overlay 型別錯誤
        # LookupError → 工單建好後馬上消失（罕見）
        _logger.warning(
            "Work order %s finished but signoff chain creation failed (config/lookup): %s",
            work_order_id, e,
        )
    except Exception as e:
        # 未預期錯誤（IntegrityError / DB connection 等） — log error 但不 raise，
        # 工單已 AWAITING_SIGNOFF，caller 可走 manual backfill endpoint（M3+ 再加）
        _logger.error(
            "Unexpected error creating signoff chain for work_order %s: %s",
            work_order_id, e, exc_info=True,
        )
    return response


@router.post("/work-orders/{work_order_id}/approve", response_model=WorkOrderResponse)
async def approve(
    work_order_id: UUID,
    farm_id: str = Query(..., min_length=1),
) -> WorkOrderResponse:
    """AWAITING_SIGNOFF → CLOSED — 但只在 signoff chain 全通過後才放行。

    Review fix #4 (security)：阻擋 client 繞過 DN-02 直接 close 工單。先驗工單有
    signoff_chain_id + chain.overall_status == APPROVED；不過 → 409。
    正常流程是透過 ``POST /api/workflow/approvals/{step_id}/approve`` 的最後一階自動
    觸發此 endpoint（由 approval_router 內部呼叫 ``wo_repo.transition('approve_all')``，
    跳過此 router endpoint，所以不影響整合）。
    """
    repo = _get_repo(farm_id)
    wo = repo.get(work_order_id)
    if wo is None:
        raise HTTPException(status_code=404, detail=f"work_order {work_order_id} not found")
    if wo.signoff_chain_id is None:
        raise HTTPException(
            status_code=409,
            detail="cannot approve directly: no signoff chain linked. "
                   "Use POST /approvals/{step_id}/approve workflow instead.",
        )
    # 確認 chain 真的全 approved
    from modules.workflow.routers.approval_router import get_signoff_repo_for_farm
    chain = get_signoff_repo_for_farm(farm_id).get_chain(wo.signoff_chain_id)
    if chain is None:
        raise HTTPException(
            status_code=409,
            detail="cannot approve: linked signoff chain not found",
        )
    from modules.workflow.domain import SignoffStatus
    if chain.overall_status is not SignoffStatus.APPROVED:
        raise HTTPException(
            status_code=409,
            detail=f"cannot approve: signoff chain not completed "
                   f"(current status: {chain.overall_status.value}). "
                   "Process all signoff steps first.",
        )
    return _run_transition(repo, work_order_id, "approve_all")


@router.post("/work-orders/{work_order_id}/reject", response_model=WorkOrderResponse)
async def reject(
    work_order_id: UUID,
    req: RejectRequest,
    farm_id: str = Query(..., min_length=1),
) -> WorkOrderResponse:
    """AWAITING_SIGNOFF → IN_PROGRESS（簽核 reject 退回給機會修正；DN-01 D2-Q3）。"""
    repo = _get_repo(farm_id)
    return _run_transition(
        repo, work_order_id, "reject",
        reject_reason=req.reject_reason,
    )


@router.post("/work-orders/{work_order_id}/cancel", response_model=WorkOrderResponse)
async def cancel(
    work_order_id: UUID,
    req: CancelRequest,
    farm_id: str = Query(..., min_length=1),
) -> WorkOrderResponse:
    """DRAFT | DISPATCHED | IN_PROGRESS → CANCELLED（取代 etech removeFrom；Q1）。"""
    repo = _get_repo(farm_id)
    return _run_transition(
        repo, work_order_id, "cancel",
        cancel_reason=req.cancel_reason,
    )


@router.post("/work-orders/{work_order_id}/reopen", response_model=WorkOrderResponse)
async def reopen(
    work_order_id: UUID,
    req: ReopenRequest,
    farm_id: str = Query(..., min_length=1),
) -> WorkOrderResponse:
    """CLOSED → REOPENED。後續呼叫 start_work 再進 IN_PROGRESS。"""
    repo = _get_repo(farm_id)
    return _run_transition(
        repo, work_order_id, "reopen",
        reopen_reason=req.reopen_reason,
    )


# ─────────────────────────────────────────────────────────────────────────
# Common transition runner
# ─────────────────────────────────────────────────────────────────────────


def _run_transition(
    repo: WorkOrderRepository,
    work_order_id: UUID,
    action: str,
    *,
    actor_id: UUID | None = None,
    **kwargs: object,
) -> WorkOrderResponse:
    """共用 transition 邏輯：state machine error → 422/409，not found → 404。"""
    try:
        wo = repo.transition(work_order_id, action, actor_id=actor_id, **kwargs)
    except LookupError:
        raise HTTPException(status_code=404, detail=f"work_order {work_order_id} not found")
    except InvalidTransition as e:
        raise _map_state_error(action, e)
    return WorkOrderResponse.model_validate(wo)
