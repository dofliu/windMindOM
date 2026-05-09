"""FastAPI router for Inventory query + adjustment（WMOM-20260509-04）。

8 endpoints（6 inventory + 2 warehouse）：

Inventory（A4 主菜）：
- POST   /api/workflow/inventory                          (create item)
- GET    /api/workflow/inventory?farm_id=...              (list + safety filter)
- GET    /api/workflow/inventory/{item_id}                (detail)
- PATCH  /api/workflow/inventory/{item_id}                (update metadata，不動 stock)
- POST   /api/workflow/inventory/{item_id}/adjust         (手動 +/- + audit log)
- GET    /api/workflow/inventory/{item_id}/adjustments    (audit log)

Warehouse（給 frontend 建料件前先建倉用）：
- POST   /api/workflow/warehouses                         (create warehouse)
- GET    /api/workflow/warehouses?farm_id=...             (list + default flag)
"""

from __future__ import annotations

import logging
from typing import Callable
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.exc import IntegrityError

from modules.workflow.repository import (
    InsufficientStock,
    InventoryRepository,
    StockAdjustmentError,
    get_inventory_repository,
)
from modules.workflow.schemas.inventory_schemas import (
    AdjustInventoryRequest,
    AdjustInventoryResult,
    AdjustmentLogListResponse,
    AdjustmentLogResponse,
    CreateInventoryItemRequest,
    CreateWarehouseRequest,
    InventoryItemListResponse,
    InventoryItemResponse,
    UpdateInventoryMetadataRequest,
    WarehouseListResponse,
    WarehouseResponse,
)


_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflow", tags=["workflow-inventory"])


# ─────────────────────────────────────────────────────────────────────────
# Repository factory injection（test mock 用）
# ─────────────────────────────────────────────────────────────────────────


_inventory_factory: Callable[[str], InventoryRepository] | None = None


def set_inventory_factory(
    factory: Callable[[str], InventoryRepository] | None,
) -> None:
    """注入 factory：``factory(farm_id) -> InventoryRepository``。

    None → 走預設（從 monitoring FarmRegistry 拿 farm DB path），同時清 lazy
    singleton。
    """
    global _inventory_factory, _FARM_REGISTRY
    _inventory_factory = factory
    if factory is None:
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
                detail="FarmRegistry not available; call set_inventory_factory() to inject",
            )
        _FARM_REGISTRY = FarmRegistry()
    db_path = _FARM_REGISTRY.get_farm_db_path(farm_id)
    if db_path is None:
        raise HTTPException(status_code=404, detail=f"Farm not found: {farm_id}")
    return str(db_path)


def _get_repo(farm_id: str) -> InventoryRepository:
    if _inventory_factory is not None:
        return _inventory_factory(farm_id)
    return get_inventory_repository(_resolve_farm_db_path(farm_id))


# ─────────────────────────────────────────────────────────────────────────
# Warehouses
# ─────────────────────────────────────────────────────────────────────────


@router.post(
    "/warehouses",
    response_model=WarehouseResponse,
    status_code=201,
)
async def create_warehouse(req: CreateWarehouseRequest) -> WarehouseResponse:
    repo = _get_repo(req.farm_id)
    wh = repo.create_warehouse(
        farm_id=req.farm_id,
        name=req.name,
        location_kind=req.location_kind,
        is_default=req.is_default,
    )
    return WarehouseResponse.model_validate(wh)


@router.get("/warehouses", response_model=WarehouseListResponse)
async def list_warehouses(
    farm_id: str = Query(..., min_length=1),
) -> WarehouseListResponse:
    """List 該 farm 所有倉。
    （走 raw SQL，不另開 list_warehouses repo method 因 caller 用量低）
    """
    from sqlalchemy import select

    from modules.workflow.repository.inventory_orm import WarehouseORM

    repo = _get_repo(farm_id)
    with repo._sessionmaker() as sess:
        stmt = select(WarehouseORM).where(WarehouseORM.farm_id == farm_id).order_by(
            WarehouseORM.is_default.desc(), WarehouseORM.name
        )
        ws = sess.execute(stmt).scalars().all()
        return WarehouseListResponse(
            items=[WarehouseResponse.model_validate(repo._warehouse_to_domain(w)) for w in ws]
        )


# ─────────────────────────────────────────────────────────────────────────
# Inventory items
# ─────────────────────────────────────────────────────────────────────────


@router.post(
    "/inventory",
    response_model=InventoryItemResponse,
    status_code=201,
)
async def create_inventory_item(
    req: CreateInventoryItemRequest,
) -> InventoryItemResponse:
    """建料件主檔。``(farm_id, sku)`` unique；重覆 → 409 Conflict。"""
    repo = _get_repo(req.farm_id)
    try:
        item = repo.create_item(
            sku=req.sku,
            name=req.name,
            description=req.description,
            unit=req.unit,
            farm_id=req.farm_id,
            warehouse_id=req.warehouse_id,
            unit_cost=req.unit_cost,
            stock_new=req.stock_new,
            stock_used=req.stock_used,
            stock_repairing=req.stock_repairing,
            safety_stock=req.safety_stock,
        )
    except IntegrityError as e:
        raise HTTPException(
            status_code=409,
            detail=f"inventory item creation failed (likely duplicate sku): {e}",
        )
    return InventoryItemResponse.model_validate(item)


@router.get("/inventory", response_model=InventoryItemListResponse)
async def list_inventory_items(
    farm_id: str = Query(..., min_length=1),
    warehouse_id: UUID | None = None,
    below_safety_only: bool = False,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> InventoryItemListResponse:
    """List 料件 — 可加 ``below_safety_only`` filter 給 dashboard 警示用。"""
    repo = _get_repo(farm_id)
    items, total = repo.list_items(
        farm_id=farm_id,
        warehouse_id=warehouse_id,
        below_safety_only=below_safety_only,
        limit=limit,
        offset=offset,
    )
    return InventoryItemListResponse(
        total=total,
        items=[InventoryItemResponse.model_validate(i) for i in items],
    )


@router.get(
    "/inventory/{item_id}",
    response_model=InventoryItemResponse,
)
async def get_inventory_item(
    item_id: UUID,
    farm_id: str = Query(..., min_length=1),
) -> InventoryItemResponse:
    repo = _get_repo(farm_id)
    item = repo.get_item(item_id)
    if item is None:
        raise HTTPException(
            status_code=404, detail=f"inventory_item {item_id} not found"
        )
    return InventoryItemResponse.model_validate(item)


@router.patch(
    "/inventory/{item_id}",
    response_model=InventoryItemResponse,
)
async def update_inventory_metadata(
    item_id: UUID,
    req: UpdateInventoryMetadataRequest,
    farm_id: str = Query(..., min_length=1),
) -> InventoryItemResponse:
    """改 metadata（sku / name / description / unit / safety_stock / unit_cost）。

    **不動 stock 數量** — stock 異動走 ``/adjust`` endpoint。
    """
    repo = _get_repo(farm_id)
    payload = req.model_dump(exclude_unset=True)
    try:
        item = repo.update_metadata(item_id, **payload)
    except LookupError:
        raise HTTPException(
            status_code=404, detail=f"inventory_item {item_id} not found"
        )
    except StockAdjustmentError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return InventoryItemResponse.model_validate(item)


@router.post(
    "/inventory/{item_id}/adjust",
    response_model=AdjustInventoryResult,
)
async def adjust_inventory(
    item_id: UUID,
    req: AdjustInventoryRequest,
    farm_id: str = Query(..., min_length=1),
) -> AdjustInventoryResult:
    """手動 +/- 異動 stock + 同 transaction 寫 ``InventoryAdjustmentLog``。

    Errors：
    - 404：item 不存在
    - 422：reason 空 / safety_stock 負（StockAdjustmentError）
    - 409：扣到負數（InsufficientStock）
    """
    repo = _get_repo(farm_id)
    try:
        item, log = repo.adjust(
            item_id,
            delta_kind=req.delta_kind,
            delta=req.delta,
            reason=req.reason,
            actor_id=req.actor_id,
            note=req.note,
        )
    except StockAdjustmentError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    except InsufficientStock as e:
        raise HTTPException(status_code=409, detail=str(e))
    return AdjustInventoryResult(
        item=InventoryItemResponse.model_validate(item),
        log=AdjustmentLogResponse.model_validate(log),
    )


@router.get(
    "/inventory/{item_id}/adjustments",
    response_model=AdjustmentLogListResponse,
)
async def list_inventory_adjustments(
    item_id: UUID,
    farm_id: str = Query(..., min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AdjustmentLogListResponse:
    """查 audit log（時間反序，最新在前）— 給 inventory drawer / KPI 用。"""
    repo = _get_repo(farm_id)
    logs = repo.list_adjustments(item_id, limit=limit, offset=offset)
    return AdjustmentLogListResponse(
        items=[AdjustmentLogResponse.model_validate(l) for l in logs]
    )
