"""FastAPI router for MaterialRequest CRUD + state transitions（WMOM-20260509-03）。

9 endpoints。State transitions 走 ``MaterialRequestRepository.transition()``，
**dispatch 走 ``dispatch_request()``** 才會做 atomic stock + ledger 雙寫。

依賴：
- ``modules.monitoring.server.farm_registry.FarmRegistry`` 拿 farm DB path（測試可注入 factory）
- ``modules.workflow.repository.signoff_repository`` 在 submit-for-approval 時建 chain
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable
from uuid import UUID

if TYPE_CHECKING:
    from modules.workflow.domain.inventory import MaterialRequest
    from modules.workflow.repository import ItemMetadata

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from modules.auth.dependencies import (
    require_authenticated,
    require_role,
    resolve_actor_id,
    resolve_actor_id_optional,
)
from modules.auth.roles import Role
from modules.workflow.domain import InvalidTransition
from modules.workflow.domain.inventory import (
    MaterialRequestStatus,
    StockKind,
)
from modules.workflow.repository import (
    InsufficientStock,
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
    MaterialRequestItemResponse,
    MaterialRequestListResponse,
    MaterialRequestResponse,
    MaterialReturnResponse,
    ReceiveMaterialRequest,
    SubmitForApprovalRequest,
)
from shared.farm_registry_provider import (
    reset_farm_registry,
    resolve_farm_db_path,
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
    singleton 避免 test 間殘留。WMOM-20260509-F4 後 singleton 在
    ``shared.farm_registry_provider`` 統一管理。
    """
    global _mr_factory, _signoff_factory_for_mr
    _mr_factory = mr
    _signoff_factory_for_mr = signoff
    # F4-1（review fix）：任一 factory 改為 None → reset 共用 singleton。
    # 與 inventory_router / cost_ledger_router 對齊「set_*_factory(None) 就 reset」語義；
    # 避免半 reset 造成測試殘留。
    if mr is None or signoff is None:
        reset_farm_registry()


def _get_mr_repo(farm_id: str) -> MaterialRequestRepository:
    if _mr_factory is not None:
        return _mr_factory(farm_id)
    return get_material_request_repository(resolve_farm_db_path(farm_id))


def _get_signoff_repo(farm_id: str) -> SignoffRepository:
    if _signoff_factory_for_mr is not None:
        return _signoff_factory_for_mr(farm_id)
    return get_signoff_repository(resolve_farm_db_path(farm_id))


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
# Response builder — enrich items with inventory metadata (sku/name/unit)
# ─────────────────────────────────────────────────────────────────────────


def _enrich_items(
    items: list[MaterialRequestItemResponse],
    meta: dict[UUID, "ItemMetadata"],
) -> list[MaterialRequestItemResponse]:
    """以 ``model_copy(update=...)`` 不可變方式填回 sku/name/unit。

    不直接 mutate 屬性是為了：未來若 schema 加上 ``frozen=True`` 也不會悄悄失效；
    同時讓 enrichment 變成 pure function。
    """
    enriched: list[MaterialRequestItemResponse] = []
    for it in items:
        m = meta.get(it.item_id)
        if m is None:
            enriched.append(it)
        else:
            enriched.append(
                it.model_copy(update={"sku": m.sku, "name": m.name, "unit": m.unit})
            )
    return enriched


def _build_mr_response(
    mr: "MaterialRequest", repo: MaterialRequestRepository
) -> MaterialRequestResponse:
    """``MaterialRequestResponse.model_validate(mr)`` 後批次填回 items 的 sku/name/unit。

    注意：此 helper 在 ``repo.get / transition`` 完成後額外開一條 read session 取
    inventory metadata，**非 transactional** — 若另一 process 在 mr fetch ↔ metadata
    fetch 中間刪掉 item，回應的 sku/name/unit 會掉成 None（不會 raise / 不會 stale 對
    caller 造成正確性問題，因為此為 view-projection only）。缺漏 item_id 在 schema 已
    宣告 Optional。
    """
    resp = MaterialRequestResponse.model_validate(mr)
    if not resp.items:
        return resp
    meta = repo.resolve_item_metadata([it.item_id for it in mr.items])
    return resp.model_copy(update={"items": _enrich_items(resp.items, meta)})


def _build_mr_list_response(
    mrs: list["MaterialRequest"], total: int, repo: MaterialRequestRepository
) -> MaterialRequestListResponse:
    """List 場景：一次 union 所有 items 的 item_id 集合，單次 SQL 取得全部 metadata。"""
    if not mrs:
        return MaterialRequestListResponse(total=total, items=[])
    all_item_ids: set[UUID] = set()
    for mr in mrs:
        all_item_ids.update(it.item_id for it in mr.items)
    meta = repo.resolve_item_metadata(all_item_ids)
    resp_items: list[MaterialRequestResponse] = []
    for mr in mrs:
        resp = MaterialRequestResponse.model_validate(mr)
        resp_items.append(
            resp.model_copy(update={"items": _enrich_items(resp.items, meta)})
        )
    return MaterialRequestListResponse(total=total, items=resp_items)


# ─────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────


def _actor_uuid(request: Request, body_actor_id: UUID | None, *, optional: bool = False) -> UUID | None:
    """雙模式解析 actor（有 token 用 token、否則沿用 body）並轉 UUID（workflow schema 多為 UUID）。

    ``optional=True`` 允許無 actor（系統動作）。WMOM-20260716-05b pattern。
    """
    fn = resolve_actor_id_optional if optional else resolve_actor_id
    resolved = fn(request, str(body_actor_id) if body_actor_id else None)
    if resolved is None:
        return None
    try:
        return UUID(resolved)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"actor_id 非合法 UUID: {resolved}")


@router.post(
    "/material-requests",
    response_model=MaterialRequestResponse,
    status_code=201,
    # WMOM-20260716-05：建領料單＝任何登入者（enforce=false 放行）。
    dependencies=[Depends(require_authenticated())],
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
    return _build_mr_response(mr, repo)


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
    return _build_mr_list_response(items, total, repo)


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
    return _build_mr_response(mr, repo)


# ─────────────────────────────────────────────────────────────────────────
# State transitions
# ─────────────────────────────────────────────────────────────────────────


@router.post(
    "/material-requests/{material_request_id}/submit-for-approval",
    response_model=MaterialRequestResponse,
    dependencies=[Depends(require_authenticated())],  # 提送簽核＝任何登入者
)
async def submit_for_approval(
    material_request_id: UUID,
    req: SubmitForApprovalRequest,
    request: Request,
    farm_id: str = Query(..., min_length=1),
) -> MaterialRequestResponse:
    """DRAFT → AWAITING_APPROVAL + 自動建 signoff chain（DN-02 領料 3 階預設）。

    Side-effect：建 chain 後 backlink 進 ``material_request.signoff_chain_id``。
    Chain 建失敗會 rollback 領料單 transition（藉 raise 觸發 caller 端 retry，避免
    領料單跑進 AWAITING_APPROVAL 但無 chain 的 inconsistent state）。
    """
    mr_repo = _get_mr_repo(farm_id)
    signoff_repo = _get_signoff_repo(farm_id)
    actor = _actor_uuid(request, req.actor_id)  # 雙模式：token 優先，否則沿用 body actor_id

    # 先建 chain；建好後才動領料單 status，這樣失敗就不會 leave inconsistent state
    try:
        chain = signoff_repo.create_chain_for_material_request(
            material_request_id=material_request_id,
            farm_id=farm_id,
            escalate_to_supervisor=req.escalate_to_supervisor,
            actor_id=actor,
        )
    except ValueError as e:
        # build_chain_levels 全 disabled → ValueError
        raise HTTPException(status_code=422, detail=f"chain build failed: {e}")

    # transition state
    try:
        mr_repo.transition(
            material_request_id, "submit_for_approval", actor_id=actor
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
    return _build_mr_response(mr, mr_repo)


@router.post(
    "/material-requests/{material_request_id}/dispatch",
    response_model=MaterialRequestResponse,
    # WMOM-20260716-05c：發料出庫（atomic stock-out）＝總務庫管（ADMIN 全權）。enforce=false 放行。
    dependencies=[Depends(require_role(Role.TREASURY))],
)
async def dispatch_material_request(
    material_request_id: UUID,
    req: DispatchMaterialRequest,
    request: Request,
    farm_id: str = Query(..., min_length=1),
) -> MaterialRequestResponse:
    """APPROVED → DISPATCHED — **atomic stock + cost ledger 雙寫**。

    Note：在正常流程中此 endpoint 通常不直接被 client 叫 — approval_router 簽核完
    最後一階時自動觸發。但保留為 explicit endpoint，給 ops 手動補 + test 用。
    """
    repo = _get_mr_repo(farm_id)
    actor = _actor_uuid(request, req.actor_id, optional=True)  # 出庫 actor 可省略（系統自動觸發）
    try:
        mr = repo.dispatch_request(material_request_id, actor_id=actor)
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail=f"material_request {material_request_id} not found",
        )
    except InvalidTransition as e:
        raise _map_state_error("dispatch", e)
    except InsufficientStock as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _build_mr_response(mr, repo)


@router.post(
    "/material-requests/{material_request_id}/receive",
    response_model=MaterialRequestResponse,
    # WMOM-20260716-05c：收料確認＝任何登入者（現場工程師收料）。enforce=false 放行。
    dependencies=[Depends(require_authenticated())],
)
async def receive_material_request(
    material_request_id: UUID,
    req: ReceiveMaterialRequest,
    request: Request,
    farm_id: str = Query(..., min_length=1),
) -> MaterialRequestResponse:
    """DISPATCHED → RECEIVED + 寫 actual_quantities 進 items。"""
    repo = _get_mr_repo(farm_id)
    actor = _actor_uuid(request, req.actor_id)  # 雙模式：token 優先，否則沿用 body actor_id
    try:
        mr = repo.transition(
            material_request_id, "receive",
            actor_id=actor,
            actual_quantities=req.actual_quantities,
        )
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail=f"material_request {material_request_id} not found",
        )
    except InvalidTransition as e:
        raise _map_state_error("receive", e)
    return _build_mr_response(mr, repo)


@router.post(
    "/material-requests/{material_request_id}/close",
    response_model=MaterialRequestResponse,
    # WMOM-20260716-05c：結案＝組長 / 主管（ADMIN 全權）。enforce=false 放行。
    dependencies=[Depends(require_role(Role.LEADER, Role.SUPERVISOR))],
)
async def close_material_request(
    material_request_id: UUID,
    req: CloseMaterialRequest,
    request: Request,
    farm_id: str = Query(..., min_length=1),
) -> MaterialRequestResponse:
    """USED / RECEIVED → CLOSED。"""
    repo = _get_mr_repo(farm_id)
    actor = _actor_uuid(request, req.actor_id)  # 雙模式：token 優先，否則沿用 body actor_id
    try:
        mr = repo.transition(material_request_id, "close", actor_id=actor)
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail=f"material_request {material_request_id} not found",
        )
    except InvalidTransition as e:
        raise _map_state_error("close", e)
    return _build_mr_response(mr, repo)


@router.post(
    "/material-requests/{material_request_id}/cancel",
    response_model=MaterialRequestResponse,
    # WMOM-20260716-05c：取消＝組長 / 主管（ADMIN 全權）。enforce=false 放行。
    dependencies=[Depends(require_role(Role.LEADER, Role.SUPERVISOR))],
)
async def cancel_material_request(
    material_request_id: UUID,
    req: CancelMaterialRequest,
    request: Request,
    farm_id: str = Query(..., min_length=1),
) -> MaterialRequestResponse:
    """DRAFT / AWAITING_APPROVAL / APPROVED → CANCELLED。

    DISPATCHED 之後不允許 cancel — 物料已離庫，須走 ``MaterialReturn`` 流程。
    """
    repo = _get_mr_repo(farm_id)
    actor = _actor_uuid(request, req.actor_id)  # 雙模式：token 優先，否則沿用 body actor_id
    try:
        mr = repo.transition(
            material_request_id, "cancel",
            actor_id=actor,
            cancel_reason=req.cancel_reason,
        )
    except LookupError:
        raise HTTPException(
            status_code=404,
            detail=f"material_request {material_request_id} not found",
        )
    except InvalidTransition as e:
        raise _map_state_error("cancel", e)
    return _build_mr_response(mr, repo)


@router.post(
    "/material-requests/{material_request_id}/returns",
    response_model=MaterialReturnResponse,
    status_code=201,
    # WMOM-20260716-05c：退料入庫（atomic stock-in）＝總務庫管（ADMIN 全權）。enforce=false 放行。
    dependencies=[Depends(require_role(Role.TREASURY))],
)
async def create_material_return(
    material_request_id: UUID,
    req: CreateMaterialReturn,
    farm_id: str = Query(..., min_length=1),
) -> MaterialReturnResponse:
    """建退料記錄 + atomic 加回 stock（D3-Q4: 4 種分類）。

    ``returned_by``（誰退的，audit）沿用 body — 庫管 (TREASURY) 可代現場工程師登記退料。
    """
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
