"""FastAPI router for Approval / Signoff（WMOM-20260504-18 + -20260509-03 MR hook）。

3 endpoints:
- ``GET  /api/workflow/approvals/pending`` — 我的待簽（filter by farm_id + level）
- ``POST /api/workflow/approvals/{step_id}/approve`` — 通過一階；最後一階通過時自動觸發
                                                        work_order.approve_all() / material_request.dispatch
- ``POST /api/workflow/approvals/{step_id}/reject`` — 駁回；自動觸發 work_order.reject() 回 IN_PROGRESS
                                                       (MATERIAL_REQUEST chain reject 在 domain 層終態化)

Integration（DN-02 + DN-03）：
- WORK_ORDER chain：approve last step → ``wo_repo.transition(approve_all)`` → CLOSED
                    reject → ``wo_repo.transition(reject, reject_reason)`` → IN_PROGRESS
- MATERIAL_REQUEST chain（WMOM-20260509-03）：
                    approve last step → ``mr_repo.transition(approve_all)`` → APPROVED
                                       → ``mr_repo.dispatch_request()`` → DISPATCHED + atomic 雙寫
                    reject → MR domain state machine REJECTED 終態（不另觸發 transition；UI
                            提示 operator 建新 MR）
"""

from __future__ import annotations

import logging
from typing import Callable
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

# review fix #14：logging 走 top-level
_logger = logging.getLogger(__name__)

from modules.workflow.domain import (
    InvalidTransition,
    SignoffLevel,
    SignoffStatus,
    SignoffSubjectType,
)
from modules.workflow.repository import (
    InsufficientStock,
    MaterialRequestRepository,
    SignoffActionError,
    SignoffRepository,
    WorkOrderRepository,
    get_material_request_repository,
    get_repository as get_work_order_repo,
    get_signoff_repository,
)
from modules.workflow.schemas import (
    ApprovalResultResponse,
    ApproveStepRequest,
    PendingSignoffItem,
    PendingSignoffListResponse,
    RejectStepRequest,
    SignoffChainResponse,
    SignoffStepResponse,
)


router = APIRouter(prefix="/api/workflow", tags=["workflow-approval"])


# ─────────────────────────────────────────────────────────────────────────
# Repository factory injection point（給 testing / multi-farm 用）
# ─────────────────────────────────────────────────────────────────────────


_signoff_factory: Callable[[str], SignoffRepository] | None = None
_work_order_factory_for_approval: Callable[[str], WorkOrderRepository] | None = None
_material_request_factory_for_approval: (
    Callable[[str], MaterialRequestRepository] | None
) = None


def set_signoff_factories(
    signoff: Callable[[str], SignoffRepository] | None,
    work_order: Callable[[str], WorkOrderRepository] | None,
    material_request: Callable[[str], MaterialRequestRepository] | None = None,
) -> None:
    """注入 factory：``signoff(farm_id)`` + ``work_order(farm_id)`` + ``material_request(farm_id)``。

    None → 走預設（從 monitoring FarmRegistry 拿 farm DB path），同時清 lazy
    singleton 避免 test 間殘留（review fix #1）。

    ``material_request`` 為新加（WMOM-20260509-03），給 MATERIAL_REQUEST chain 簽核
    最後一階完成時自動觸發 dispatch_request 用。預設 None → 走預設 factory。
    """
    global _signoff_factory, _work_order_factory_for_approval
    global _material_request_factory_for_approval, _FARM_REGISTRY
    _signoff_factory = signoff
    _work_order_factory_for_approval = work_order
    _material_request_factory_for_approval = material_request
    if signoff is None and work_order is None and material_request is None:
        _FARM_REGISTRY = None


def _get_signoff_repo(farm_id: str) -> SignoffRepository:
    if _signoff_factory is not None:
        return _signoff_factory(farm_id)
    db_path = _resolve_farm_db_path(farm_id)
    return get_signoff_repository(db_path)


def get_signoff_repo_for_farm(farm_id: str) -> SignoffRepository:
    """Public factory（review fix #4）— 給其他 router 整合用，避開 private 跨 import。

    當前 caller：``work_order_router.finish`` 自動建 chain 時用此 entry。
    Test 環境下也可注入：``set_signoff_factories(...)`` 設定後本函式自動走 factory。
    """
    return _get_signoff_repo(farm_id)


def _get_work_order_repo(farm_id: str) -> WorkOrderRepository:
    if _work_order_factory_for_approval is not None:
        return _work_order_factory_for_approval(farm_id)
    db_path = _resolve_farm_db_path(farm_id)
    return get_work_order_repo(db_path)


def _get_material_request_repo(farm_id: str) -> MaterialRequestRepository:
    if _material_request_factory_for_approval is not None:
        return _material_request_factory_for_approval(farm_id)
    db_path = _resolve_farm_db_path(farm_id)
    return get_material_request_repository(db_path)


_FARM_REGISTRY = None


def _resolve_farm_db_path(farm_id: str) -> str:
    """共用 lazy singleton — 同 work_order_router 但避免循環 import。"""
    global _FARM_REGISTRY
    if _FARM_REGISTRY is None:
        try:
            from modules.monitoring.server.farm_registry import FarmRegistry  # type: ignore
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="FarmRegistry not available; call set_signoff_factories() to inject",
            )
        _FARM_REGISTRY = FarmRegistry()
    db_path = _FARM_REGISTRY.get_farm_db_path(farm_id)
    if db_path is None:
        raise HTTPException(status_code=404, detail=f"Farm not found: {farm_id}")
    return str(db_path)


# ─────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────


@router.get("/approvals/pending", response_model=PendingSignoffListResponse)
async def list_pending_approvals(
    farm_id: str = Query(..., min_length=1),
    level: SignoffLevel = Query(...),
    subject_type: SignoffSubjectType | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> PendingSignoffListResponse:
    """「我這層的待簽」列表 — caller 帶 ``level`` 對應 user group。

    Returns:
        - ``items``：當前 page 的 step + chain
        - ``total``：filter 後的真實 DB count（不受 limit/offset 截斷；review fix #6）

    Review fix #11/#12：``offset`` 分頁 + ``subject_type`` filter
    （M4 領料單上線後 EMPLOYEE 待簽會混工單 / 領料單，預留 filter）。
    """
    repo = _get_signoff_repo(farm_id)
    pairs, total = repo.list_pending_for_level(
        farm_id=farm_id, level=level,
        subject_type=subject_type,
        limit=limit, offset=offset,
    )
    items = [
        PendingSignoffItem(
            step=SignoffStepResponse.model_validate(step),
            chain=SignoffChainResponse.model_validate(chain),
        )
        for (step, chain) in pairs
    ]
    return PendingSignoffListResponse(total=total, items=items)


@router.post(
    "/approvals/{step_id}/approve",
    response_model=ApprovalResultResponse,
)
async def approve_step(
    step_id: UUID,
    req: ApproveStepRequest,
    farm_id: str = Query(..., min_length=1),
) -> ApprovalResultResponse:
    """通過一階。若是最後一階 → 自動 work_order.approve_all() 進 CLOSED。"""
    signoff_repo = _get_signoff_repo(farm_id)
    try:
        chain, is_last = signoff_repo.approve_step(
            step_id, actor_id=req.actor_id, comment=req.comment
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SignoffActionError as e:
        raise HTTPException(status_code=409, detail=str(e))

    subject_changed = False
    transition_error: str | None = None
    if is_last and chain.subject_type == SignoffSubjectType.WORK_ORDER:
        # 自動觸發 work_order.approve_all()
        wo_repo = _get_work_order_repo(farm_id)
        try:
            wo_repo.transition(chain.subject_id, "approve_all")
            subject_changed = True
        except (LookupError, InvalidTransition) as e:
            # review fix #1：chain 已 APPROVED 落地，但工單 transition 失敗（罕見：
            # 工單被外部改過 status / 被刪）。回 200 + ``subject_transition_error``，
            # 讓 caller 看到 chain 已通過但 subject 沒跟上 — 走 backfill / 通報 ops。
            # 不 raise 500 否則 client 完全看不到 chain 已 APPROVED 的事實。
            _logger.error(
                "signoff %s approved but work_order %s transition failed: %s",
                chain.id, chain.subject_id, e,
            )
            transition_error = (
                f"chain approved but work_order transition failed: {e}"
            )

    elif is_last and chain.subject_type == SignoffSubjectType.MATERIAL_REQUEST:
        # WMOM-20260509-03：簽核完成 → 自動 approve_all 進 APPROVED → atomic
        # dispatch_request 進 DISPATCHED + 扣 stock + 寫 ledger。
        # 任一步失敗都把 transition_error 帶回給 caller（chain 已落地不能 retry，
        # 操作員需手動補：去 /material-requests/{id}/dispatch endpoint 重試）。
        mr_repo = _get_material_request_repo(farm_id)
        try:
            mr_repo.transition(chain.subject_id, "approve_all")
            mr_repo.dispatch_request(chain.subject_id, actor_id=req.actor_id)
            subject_changed = True
        except LookupError as e:
            _logger.error(
                "signoff %s approved but material_request %s lookup failed: %s",
                chain.id, chain.subject_id, e,
            )
            transition_error = (
                f"chain approved but material_request lookup failed: {e}"
            )
        except InvalidTransition as e:
            _logger.error(
                "signoff %s approved but material_request %s transition failed: %s",
                chain.id, chain.subject_id, e,
            )
            transition_error = (
                f"chain approved but material_request transition failed: {e}"
            )
        except InsufficientStock as e:
            # 簽核完才發現 stock 不夠（可能批准期間別張單被先 dispatch 走）
            _logger.error(
                "signoff %s approved but dispatch_request failed (insufficient stock): %s",
                chain.id, e,
            )
            transition_error = (
                f"chain approved but dispatch failed: {e}; "
                "operator must adjust stock or cancel MR"
            )
        except Exception as e:  # noqa: BLE001  (review fix: bare except 兜底)
            # 未預期錯誤（DB lock、IntegrityError 等）— 不能 raise 500，否則
            # client 看不到 chain 已 APPROVED 落地，會誤以為要重 approve。
            # 回 200 + transition_error 訊息，operator 走 manual dispatch 補。
            _logger.exception(
                "signoff %s approved but dispatch_request raised unexpectedly: %s",
                chain.id, e,
            )
            transition_error = (
                f"chain approved but dispatch unexpectedly failed: {type(e).__name__}: {e}; "
                "ops must investigate"
            )

    return ApprovalResultResponse(
        chain=SignoffChainResponse.model_validate(chain),
        chain_completed=is_last,
        subject_status_changed=subject_changed,
        subject_transition_error=transition_error,
    )


@router.post(
    "/approvals/{step_id}/reject",
    response_model=ApprovalResultResponse,
)
async def reject_step(
    step_id: UUID,
    req: RejectStepRequest,
    farm_id: str = Query(..., min_length=1),
) -> ApprovalResultResponse:
    """駁回一階 → chain 進 REJECTED + 自動 work_order.reject(reason) 回 IN_PROGRESS。"""
    signoff_repo = _get_signoff_repo(farm_id)
    try:
        chain = signoff_repo.reject_step(
            step_id, actor_id=req.actor_id, reason=req.reason
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SignoffActionError as e:
        raise HTTPException(status_code=409, detail=str(e))

    subject_changed = False
    transition_error: str | None = None
    if chain.subject_type == SignoffSubjectType.WORK_ORDER:
        wo_repo = _get_work_order_repo(farm_id)
        try:
            wo_repo.transition(
                chain.subject_id, "reject", reject_reason=req.reason
            )
            subject_changed = True
        except (LookupError, InvalidTransition) as e:
            # review fix #2：同 approve 處理 — chain 已 REJECTED 落地，回 200 帶錯誤
            # 訊息給 caller，不 raise 500 隱藏 chain 已結束的事實。
            _logger.error(
                "signoff %s rejected but work_order %s transition failed: %s",
                chain.id, chain.subject_id, e,
            )
            transition_error = (
                f"chain rejected but work_order transition failed: {e}"
            )

    elif chain.subject_type == SignoffSubjectType.MATERIAL_REQUEST:
        # WMOM-20260509-03：MR domain state machine reject 進 REJECTED 終態
        # （與 work_order「reject 回 IN_PROGRESS」不同；DN-03 設計上 MR 駁回後
        #  操作員需建新 MR，不就地 resubmit）
        mr_repo = _get_material_request_repo(farm_id)
        try:
            mr_repo.transition(
                chain.subject_id, "reject", reject_reason=req.reason
            )
            subject_changed = True
        except (LookupError, InvalidTransition) as e:
            _logger.error(
                "signoff %s rejected but material_request %s transition failed: %s",
                chain.id, chain.subject_id, e,
            )
            transition_error = (
                f"chain rejected but material_request transition failed: {e}"
            )

    return ApprovalResultResponse(
        chain=SignoffChainResponse.model_validate(chain),
        chain_completed=True,  # reject 等於 chain 結束
        subject_status_changed=subject_changed,
        subject_transition_error=transition_error,
    )
