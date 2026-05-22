"""FastAPI router for Work Order CRUD + state transitions（WMOM-20260504-17 + -20260509-05）。

11 endpoints. State transitions 都走 ``WorkOrderRepository.transition`` 統一入口
（domain state machine + persist + event log + multi-WO constraint）。

A5（WMOM-20260509-05）擴充：``finish`` endpoint 加 cost ledger 確認 hook —
工單完工後找所有關聯 MR，把 actual_qty 寫過的 line item ledger entry 從 estimated
翻到 confirmed（amount = actual_qty × unit_cost）。

依賴：``modules.monitoring.server.farm_registry`` 的 ``FarmRegistry`` 拿 farm DB path。
為了讓 router 可被 unit test，提供 ``set_repository_factory()`` + ``set_finish_hook_db_path()``
注入 mock。
"""

from __future__ import annotations

import logging
from decimal import Decimal
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
from shared.farm_registry_provider import (
    get_farm_registry,
    reset_farm_registry,
    resolve_farm_db_path,
)


router = APIRouter(prefix="/api/workflow", tags=["workflow"])


# ─────────────────────────────────────────────────────────────────────────
# Repository factory injection point（給 testing / multi-farm 用）
# ─────────────────────────────────────────────────────────────────────────


_repository_factory: Callable[[str], WorkOrderRepository] | None = None

# WMOM-20260509-05 + review fix #2：finish hook 用的 db_path override map
# (farm_id → path)。Multi-farm 部署 safe — 不同 farm 各自路徑分開。
# 特殊 key "*" 為 fallback (給 single-farm test 偷懶用)。
# 生產：dict 為空 → 走 FarmRegistry。
_finish_hook_db_path_overrides: dict[str, str] = {}


def set_repository_factory(
    factory: Callable[[str], WorkOrderRepository] | None,
) -> None:
    """注入 repository factory：``factory(farm_id) -> WorkOrderRepository``。

    None → 走預設（從 monitoring FarmRegistry 拿 farm DB path），同時清共用
    lazy singleton 避免 test 間殘留（WMOM-20260522-01：原本 module-private
    ``_FARM_REGISTRY`` 已抽到 ``shared.farm_registry_provider``）。
    """
    global _repository_factory
    _repository_factory = factory
    if factory is None:
        reset_farm_registry()


def set_finish_hook_db_path(
    path: str | None, *, farm_id: str = "*"
) -> None:
    """Test inject — finish hook 走 ``path`` 而不查 FarmRegistry。

    Multi-farm safe (review fix #2)：傳特定 ``farm_id`` 只覆寫該 farm；不傳走
    fallback ``"*"`` 對所有 farm 生效（single-farm test 用）。

    Examples:
        set_finish_hook_db_path("/tmp/changhua.db", farm_id="changhua")
        set_finish_hook_db_path("/tmp/test.db")  # 等同 farm_id="*"
        set_finish_hook_db_path(None)  # 清掉 "*"
        set_finish_hook_db_path(None, farm_id="changhua")  # 清掉特定 farm
    """
    if path is None:
        _finish_hook_db_path_overrides.pop(farm_id, None)
    else:
        _finish_hook_db_path_overrides[farm_id] = path


def clear_finish_hook_db_paths() -> None:
    """Test cleanup — 清掉所有 override（fixture teardown 用）。"""
    _finish_hook_db_path_overrides.clear()


def _default_repository_factory(farm_id: str) -> WorkOrderRepository:
    """預設工廠：從 monitoring 的 FarmRegistry 取 farm DB path。

    WMOM-20260522-01：lazy singleton + 404/500 error mapping 已抽到
    ``shared.farm_registry_provider.resolve_farm_db_path``，本函式直接 delegate。
    """
    return get_repository(resolve_farm_db_path(farm_id))


def _get_repo(farm_id: str) -> WorkOrderRepository:
    factory = _repository_factory or _default_repository_factory
    return factory(farm_id)


# ─────────────────────────────────────────────────────────────────────────
# A5 finish hook helpers — cost ledger confirmation
# ─────────────────────────────────────────────────────────────────────────


def _resolve_db_path_for_finish_hook(farm_id: str) -> str | None:
    """For A5 finish hook: resolve farm DB path with test override support.

    Lookup order (review fix #2 multi-farm safe)：
    1. Per-farm override `_finish_hook_db_path_overrides[farm_id]`
    2. Fallback override `_finish_hook_db_path_overrides["*"]`（test 用）
    3. FarmRegistry（生產）
    4. None — caller 安靜跳過 hook

    Returns ``None`` when DB path can't be resolved.

    WMOM-20260522-01：FarmRegistry instance 改走 ``shared.farm_registry_provider.
    get_farm_registry()``；hook 路徑需要「失敗安靜跳過」而非 raise，所以不能用
    ``resolve_farm_db_path()``（它失敗會 raise HTTPException）。改用 registry
    instance + 直接 ``get_farm_db_path()`` 接 None 的 pattern；HTTPException
    （registry 載入失敗時 shared helper 會 raise 500）一併 catch 後安靜跳過。
    """
    if farm_id in _finish_hook_db_path_overrides:
        return _finish_hook_db_path_overrides[farm_id]
    if "*" in _finish_hook_db_path_overrides:
        return _finish_hook_db_path_overrides["*"]
    try:
        reg = get_farm_registry()
    except HTTPException:
        # registry 無法 lazy import（如 monitoring 未掛載）— 安靜跳過 hook
        return None
    db_path = reg.get_farm_db_path(farm_id)
    return str(db_path) if db_path is not None else None


def _confirm_material_ledger_for_finished_wo(wo_id: UUID, farm_id: str) -> None:
    """A5 hook：工單完工後，對所有關聯 MR 的 line item ledger entry，
    用 ``actual_qty × locked_unit_cost`` 翻 estimated → confirmed。

    Review fix #1（會計正確性）：用 ledger entry 的 ``locked_unit_cost``（在
    dispatch 那一刻寫入），不重新查 inventory 當前 unit_cost。如此 estimated
    與 confirmed 用同基礎計算，月報差異分析才有意義。

    - 跳過 actual_qty 還是 None 的 item（MR 還沒 receive）— ledger 留 estimated
    - 找不到 entry → log warning（罕見，可能 dispatch 失敗但 status 進 DISPATCHED）
    - locked_unit_cost 為 None → fallback 查 inventory（向後相容老 entries）
    - 已 confirmed → confirm_entry 內部 idempotent
    """
    db_path = _resolve_db_path_for_finish_hook(farm_id)
    if db_path is None:
        # test 環境無 override + 無 FarmRegistry — 安靜跳過
        return

    # runtime imports（避循環 import）
    from modules.cost.repository import get_cost_ledger_repository
    from modules.workflow.repository import (
        get_inventory_repository,
        get_material_request_repository,
    )

    mr_repo = get_material_request_repository(db_path)
    inv_repo = get_inventory_repository(db_path)
    ledger_repo = get_cost_ledger_repository(db_path)

    linked_mrs = mr_repo.list_for_work_order(wo_id)
    for mr in linked_mrs:
        for item in mr.items:
            if item.actual_qty is None:
                continue
            entry = ledger_repo.find_for_mr_item(mr.id, item.id)
            if entry is None:
                _logger.warning(
                    "ledger hook: no ledger entry for MR %s item %s",
                    mr.id, item.id,
                )
                continue
            # review fix #1：用 entry.locked_unit_cost（dispatch 當下的快照）算 amount
            unit_cost = entry.locked_unit_cost
            if unit_cost is None:
                # 老 entries 沒 locked_unit_cost — fallback 查 inventory（向後相容）
                inv = inv_repo.get_item(item.item_id)
                if inv is None:
                    _logger.warning(
                        "ledger hook: inventory item %s not found AND entry %s has no locked_unit_cost",
                        item.item_id, entry.id,
                    )
                    continue
                unit_cost = inv.unit_cost
            new_amount = Decimal(item.actual_qty) * unit_cost
            ledger_repo.confirm_entry(entry.id, new_amount=new_amount)


# ─────────────────────────────────────────────────────────────────────────
# Error mapping helper
# ─────────────────────────────────────────────────────────────────────────


def _map_state_error(action: str, exc: InvalidTransition) -> HTTPException:
    """Domain state machine 拒絕 → 422 (validation) 或 409 (conflict)。

    Review fix #3：用 ``exc.reason`` 屬性精確判斷（不再 fragile 字串匹配）：
    - ``state_mismatch`` → 409 Conflict（caller 改 state 即可恢復）
    - ``guard_failed`` / ``unknown_action`` → 422 Unprocessable Entity
    - reason 為 None（舊 caller，向後相容）→ fallback 字串匹配
    """
    msg = str(exc)
    if exc.reason == "state_mismatch":
        status = 409
    elif exc.reason in ("guard_failed", "unknown_action"):
        status = 422
    else:
        # 向後相容：舊 caller 沒設 reason → 用字串匹配（fallback）
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
    """DRAFT → DISPATCHED。

    若 ``req.assignee_id`` 有值，會在 transition 時一併寫入工單；
    若工單建單時未指派 + 派工時也未帶 → state machine 拒絕。
    """
    repo = _get_repo(farm_id)
    return _run_transition(
        repo, work_order_id, "dispatch",
        actor_id=req.actor_id,
        assignee_id=req.assignee_id,
    )


@router.post("/work-orders/{work_order_id}/start-work", response_model=WorkOrderResponse)
async def start_work(
    work_order_id: UUID,
    req: StartWorkRequest,
    farm_id: str = Query(..., min_length=1),
) -> WorkOrderResponse:
    """DISPATCHED | REOPENED → IN_PROGRESS。

    offshore farm 傳 ``require_weather_window=True`` 強制檢 weather_window_id；
    WMOM-20260510-01 Part D：caller 可直接帶 ``weather_window_id`` 一次完成綁定 + 開工。
    """
    repo = _get_repo(farm_id)
    return _run_transition(
        repo, work_order_id, "start_work",
        require_weather_window=req.require_weather_window,
        weather_window_id=req.weather_window_id,
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
    except (ValueError, LookupError) as e:
        _logger.warning(
            "Work order %s finished but signoff chain creation failed (config/lookup): %s",
            work_order_id, e,
        )
    except Exception as e:
        _logger.error(
            "Unexpected error creating signoff chain for work_order %s: %s",
            work_order_id, e, exc_info=True,
        )

    # WMOM-20260509-05: cost ledger confirmation hook
    # 對所有 actual_qty 已填的 MR line item，把 ledger entry 從 estimated → confirmed
    # 失敗不阻擋 finish（工單已 AWAITING_SIGNOFF；caller 可手動 backfill）
    try:
        _confirm_material_ledger_for_finished_wo(response.id, farm_id)
    except Exception as e:  # noqa: BLE001
        _logger.warning(
            "Work order %s finished but cost ledger confirmation hook failed: %s",
            work_order_id, e,
        )

    wo = repo.get(response.id)
    if wo is not None:
        return WorkOrderResponse.model_validate(wo)
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
