"""FastAPI router for MaterialRequest CRUD + state transitions（WMOM-20260509-03）。

9 endpoints。State transitions 走 ``MaterialRequestRepository.transition()``，
**dispatch 走 ``dispatch_request()``** 才會做 atomic stock + ledger 雙寫。

依賴：
- ``modules.monitoring.server.farm_registry.FarmRegistry`` 拿 farm DB path（測試可注入 factory）
- ``modules.workflow.repository.signoff_repository`` 在 submit-for-approval 時建 chain
"""

from __future__ import annotations

import logging
from typing import Callable
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from modules.workflow.domain import InvalidTransition
from modules.workflow.domain.inventory import (
    MaterialRequestStatus,
    StockKind,
)
from modules.workflow.domain.inventory import MaterialRequest
from modules.workflow.repository import (
    InsufficientStock,
    InventoryRepository,
    MaterialRequestRepository,
    MaterialRequestRuleViolation,
    SignoffRepository,
    StockAdjustmentError,
    get_material_request_repository,
    get_signoff_repository,
)
from modules.workflow.schemas import (
    CancelMaterialRequest,
    CloseMaterialRequest,
    CreateMaterialRequest,
    CreateMaterialReturn,
    DispatchMaterialRequest,
    MaterialRequestListResponse,
    MaterialRequestResponse,
    MaterialReturnResponse,
    ReceiveMaterialRequest,
    SubmitForApprovalRequest,
)


_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflow", tags=["workflow-material"])


# ─────────────────────────────────────────────────────────────────────────
# Repository factory injection（test mock 用；同 work_order / approval pattern）
# ─────────────────────────────────────────────────────────────────────────


_mr_factory: Callable[[str], MaterialRequestRepository] | None = None
_signoff_factory_for_mr: Callable[[str], SignoffRepository] | None = None


def set_material_request_factories(
    mr: Callable[[str], MaterialRequestRepository] | None,
    signoff: Callable[[str], SignoffRepository] | None,
) -> None:
    """注入兩個 factory：``mr(farm_id)`` + ``signoff(farm_id)``。

    None → 走預設（從 monitoring FarmRegistry 拿 farm DB path），同時清 lazy
    singleton 避免 test 間殘留。
    """
    global _mr_factory, _signoff_factory_for_mr, _FARM_REGISTRY
    _mr_factory = mr
    _signoff_factory_for_mr = signoff
    if mr is None and signoff is None:
        _FARM_REGISTRY = None


_FARM_REGISTRY = None


def _resolve_farm_db_path(farm_id: str) -> str:
    global _FARM_REGISTRY
    if _FARM_REGISTRY is None:
        try:
            from modules.monitoring.server.farm_registry import FarmRegistry  # type: ignore
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="FarmRegistry not available; call set_material_request_factories() to inject",
            )
        _FARM_REGISTRY = FarmRegistry()
    db_path = _FARM_REGISTRY.get_farm_db_path(farm_id)
    if db_path is None:
        raise HTTPException(status_code=404, detail=f"Farm not found: {farm_id}")
    return str(db_path)


def _get_mr_repo(farm_id: str) -> MaterialRequestRepository:
    if _mr_factory is not None:
        return _mr_factory(farm_id)
    return get_material_request_repository(_resolve_farm_db_path(farm_id))


def _get_signoff_repo(farm_id: str) -> SignoffRepository:
    if _signoff_factory_for_mr is not None:
        return _signoff_factory_for_mr(farm_id)
    return get_signoff_repository(_resolve_farm_db_path(farm_id))


# ─────────────────────────────────────────────────────────────────────────
# Error mapping helper
# ─────────────────────────────────────────────────────────────────────────


def _map_state_error(action: str, exc: InvalidTransition) -> HTTPException:
    """Domain state machine 拒絕 → 422 (validation) 或 409 (conflict)。

    Review fix #3：優先用 ``exc.reason`` 屬性精確判斷（取代 fragile 字串匹配）。
    """
    msg = str(exc)
    if exc.reason == "state_mismatch":
        status = 409
    elif exc.reason in ("guard_failed", "unknown_action"):
        status = 422
    else:
        # 向後相容：未設 reason 時 fallback 字串匹配
        status = 409 if "cannot transition" in msg else 422
    return HTTPException(status_code=status, detail=f"{action}: {msg}")


# ─────────────────────────────────────────────────────────────────────────
# Response enrichment（WMOM-20260518-01）
# ─────────────────────────────────────────────────────────────────────────


def _build_mr_response(
    mr_repo: MaterialRequestRepository, mr: MaterialRequest
) -> MaterialRequestResponse:
    """把 ``MaterialRequest`` 轉成帶 SKU / name / unit enriched 的 response。

    用 ``InventoryRepository`` batch-fetch（共用同個 farm DB engine）避 N+1：一張 MR 多筆
    item 仍只發一次 ``WHERE id IN (...)``。找不到對應 InventoryItem 的 row（被刪 / migration
    不完整）→ 該 row 的 SKU/name/unit 保留 None（schema 為 Optional），frontend fallback 顯
    truncated UUID 與既有行為一致。
    """
    base = MaterialRequestResponse.model_validate(mr)
    if not mr.items:
        return base
    inv_repo = InventoryRepository(mr_repo.engine)
    items_by_id = inv_repo.get_items_by_ids([it.item_id for it in mr.items])
    enriched_items = [
        item.model_copy(
            update={
                "sku": inv.sku if (inv := items_by_id.get(item.item_id)) else None,
                "name": inv.name if inv else None,
                "unit": inv.unit if inv else None,
            }
        )
        for item in base.items
    ]
    return base.model_copy(update={"items": enriched_items})


def _build_mr_responses(
    mr_repo: MaterialRequestRepository, mrs: list[MaterialRequest]
) -> list[MaterialRequestResponse]:
    """List 端 batch enrich — 把所有 MR 的 items 一次 ``WHERE id IN (...)`` 撈完。

    比 per-MR 各自呼叫 ``_build_mr_response`` 更省一輪 query；200 MR × 平均 3 items 由 200
    query 壓縮到 1 query。
    """
    if not mrs:
        return []
    base_list = [MaterialRequestResponse.model_validate(mr) for mr in mrs]
    all_item_ids = list({it.item_id for mr in mrs for it in mr.items})
    if not all_item_ids:
        return base_list
    inv_repo = InventoryRepository(mr_repo.engine)
    items_by_id = inv_repo.get_items_by_ids(all_item_ids)
    enriched: list[MaterialRequestResponse] = []
    for resp in base_list:
        new_items = [
            item.model_copy(
                update={
                    "sku": inv.sku if (inv := items_by_id.get(item.item_id)) else None,
                    "name": inv.name if inv else None,
                    "unit": inv.unit if inv else None,
                }
            )
            for item in resp.items
        ]
        enriched.append(resp.model_copy(update={"items": new_items}))
    return enriched


# ─────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────


@router.post(
    "/material-requests",
    response_model=MaterialRequestResponse,
    status_code=201,
)
async def create_material_request(req: CreateMaterialRequest) -> MaterialRequestResponse:
    """建立 DRAFT 領料單（含多筆 items）。"""
    repo = _get_mr_repo(req.farm_id)
    items_tuple = [
        (it.item_id, it.estimated_qty, it.stock_kind) for it in req.items
    ]
    try:
        mr = repo.create(
            farm_id=req.farm_id,
            requester_id=req.requester_id,
            items=items_tuple,
            work_order_id=req.work_order_id,
        )
    except MaterialRequestRuleViolation as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _build_mr_response(repo, mr)


@router.get("/material-requests", response_model=MaterialRequestListResponse)
async def list_material_requests(
    farm_id: str = Query(..., min_length=1),
    work_order_id: UUID | None = None,
    status: MaterialRequestStatus | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> MaterialRequestListResponse:
    repo = _get_mr_repo(farm_id)
    items, total = repo.list(
        farm_id=farm_id,
        work_order_id=work_order_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return MaterialRequestListResponse(
        total=total,
        items=_build_mr_responses(repo, items),
    )


@router.get(
    "/material-requests/{material_request_id}",
    response_model=MaterialRequestResponse,
)
async def get_material_request(
    material_request_id: UUID,
    farm_id: str = Query(..., min_length=1),
) -> MaterialRequestResponse:
    repo = _get_mr_repo(farm_id)
    mr = repo.get(material_request_id)
    if mr is None:
        raise HTTPException(
            status_code=404,
            detail=f"material_request {material_request_id} not found",
        )
    return _build_mr_response(repo, mr)


# ─────────────────────────────────────────────────────────────────────────
# State transitions
# ─────────────────────────────────────────────────────────────────────────


@router.post(
    "/material-requests/{material_request_id}/submit-for-approval",
    response_model=MaterialRequestResponse,
)
async def submit_for_approval(
    material_request_id: UUID,
    req: SubmitForApprovalRequest,
    farm_id: str = Query(..., min_length=1),
) -> MaterialRequestResponse:
    """DRAFT → AWAITING_APPROVAL + 自動建 signoff chain（DN-02 領料 3 階預設）。

    Side-effect：建 chain 後 backlink 進 ``material_request.signoff_chain_id``。
    Chain 建失敗會 rollback 領料單 transition（藉 raise 觸發 caller 端 retry，避免
    領料單跑進 AWAITING_APPROVAL 但無 chain 的 inconsistent state）。
    """
    mr_repo = _get_mr_repo(farm_id)
    signoff_repo = _get_signoff_repo(farm_id)

    # 先建 chain；建好後才動領料單 status，這樣失敗就不會 leave inconsistent state
    try:
        chain = signoff_repo.create_chain_for_material_request(
            material_request_id=material_request_id,
            farm_id=farm_id,
            escalate_to_supervisor=req.escalate_to_supervisor,
            actor_id=req.actor_id,
        )
    except ValueError as e:
        # build_chain_levels 全 disabled → ValueError
        raise HTTPException(status_code=422, detail=f"chain build failed: {e}")

    # transition state
    try:
        mr_repo.transition(
            material_request_id, "submit_for_approval", actor_id=req.actor_id
        )
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail=f"material_request {material_request_id} not found",
        )
    except InvalidTransition as e:
        raise _map_state_error("submit_for_approval", e)

    # backlink chain id
    try:
        mr_repo.set_signoff_chain_id(material_request_id, chain.id)
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail=f"material_request {material_request_id} not found",
        )

    mr = mr_repo.get(material_request_id)
    return _build_mr_response(mr_repo, mr)


@router.post(
    "/material-requests/{material_request_id}/dispatch",
    response_model=MaterialRequestResponse,
)
async def dispatch_material_request(
    material_request_id: UUID,
    req: DispatchMaterialRequest,
    farm_id: str = Query(..., min_length=1),
) -> MaterialRequestResponse:
    """APPROVED → DISPATCHED — **atomic stock + cost ledger 雙寫**。

    Note：在正常流程中此 endpoint 通常不直接被 client 叫 — approval_router 簽核完
    最後一階時自動觸發。但保留為 explicit endpoint，給 ops 手動補 + test 用。
    """
    repo = _get_mr_repo(farm_id)
    try:
        mr = repo.dispatch_request(material_request_id, actor_id=req.actor_id)
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail=f"material_request {material_request_id} not found",
        )
    except InvalidTransition as e:
        raise _map_state_error("dispatch", e)
    except InsufficientStock as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _build_mr_response(repo, mr)


@router.post(
    "/material-requests/{material_request_id}/receive",
    response_model=MaterialRequestResponse,
)
async def receive_material_request(
    material_request_id: UUID,
    req: ReceiveMaterialRequest,
    farm_id: str = Query(..., min_length=1),
) -> MaterialRequestResponse:
    """DISPATCHED → RECEIVED + 寫 actual_quantities 進 items。"""
    repo = _get_mr_repo(farm_id)
    try:
        mr = repo.transition(
            material_request_id, "receive",
            actor_id=req.actor_id,
            actual_quantities=req.actual_quantities,
        )
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail=f"material_request {material_request_id} not found",
        )
    except InvalidTransition as e:
        raise _map_state_error("receive", e)
    return _build_mr_response(repo, mr)


@router.post(
    "/material-requests/{material_request_id}/close",
    response_model=MaterialRequestResponse,
)
async def close_material_request(
    material_request_id: UUID,
    req: CloseMaterialRequest,
    farm_id: str = Query(..., min_length=1),
) -> MaterialRequestResponse:
    """USED / RECEIVED → CLOSED。"""
    repo = _get_mr_repo(farm_id)
    try:
        mr = repo.transition(material_request_id, "close", actor_id=req.actor_id)
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail=f"material_request {material_request_id} not found",
        )
    except InvalidTransition as e:
        raise _map_state_error("close", e)
    return _build_mr_response(repo, mr)


@router.post(
    "/material-requests/{material_request_id}/cancel",
    response_model=MaterialRequestResponse,
)
async def cancel_material_request(
    material_request_id: UUID,
    req: CancelMaterialRequest,
    farm_id: str = Query(..., min_length=1),
) -> MaterialRequestResponse:
    """DRAFT / AWAITING_APPROVAL / APPROVED → CANCELLED。

    DISPATCHED 之後不允許 cancel — 物料已離庫，須走 ``MaterialReturn`` 流程。
    """
    repo = _get_mr_repo(farm_id)
    try:
        mr = repo.transition(
            material_request_id, "cancel",
            actor_id=req.actor_id,
            cancel_reason=req.cancel_reason,
        )
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail=f"material_request {material_request_id} not found",
        )
    except InvalidTransition as e:
        raise _map_state_error("cancel", e)
    return _build_mr_response(repo, mr)


@router.post(
    "/material-requests/{material_request_id}/returns",
    response_model=MaterialReturnResponse,
    status_code=201,
)
async def create_material_return(
    material_request_id: UUID,
    req: CreateMaterialReturn,
    farm_id: str = Query(..., min_length=1),
) -> MaterialReturnResponse:
    """建退料記錄 + atomic 加回 stock（D3-Q4: 4 種分類）。"""
    repo = _get_mr_repo(farm_id)
    try:
        ret = repo.add_return(
            request_id=material_request_id,
            item_id=req.item_id,
            qty=req.qty,
            reason=req.reason,
            return_to_kind=req.return_to_kind,
            returned_by=req.returned_by,
            note=req.note,
        )
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail=f"material_request {material_request_id} not found",
        )
    except MaterialRequestRuleViolation as e:
        raise HTTPException(status_code=422, detail=str(e))
    except StockAdjustmentError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return MaterialReturnResponse.model_validate(ret)
