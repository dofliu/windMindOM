"""FastAPI router for cost_ledger query API（WMOM-20260509-05）。

2 endpoints (read-only)：
- GET   /api/cost/ledger              (list + filter + pagination)
- GET   /api/cost/ledger/summary      (group by category，給月報用)

⚠ 不暴露 POST / PATCH — ledger 所有 mutation 必須走業務 atomic transaction
（dispatch_request / wo finish hook），避免外部誤改帳本。
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Callable

from fastapi import APIRouter, HTTPException, Query

from modules.cost.repository import (
    CostLedgerCategory,
    CostLedgerRepository,
    CostLedgerSourceType,
    CostLedgerStatus,
    get_cost_ledger_repository,
)
from modules.cost.schemas.cost_ledger_schemas import (
    CategorySummaryItem,
    CostLedgerEntryResponse,
    CostLedgerListResponse,
    CostLedgerSummaryResponse,
)
from shared.farm_registry_provider import (
    reset_farm_registry,
    resolve_farm_db_path,
)


_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cost", tags=["cost-ledger"])


# ─────────────────────────────────────────────────────────────────────────
# Repository factory injection（test mock 用）
# ─────────────────────────────────────────────────────────────────────────


_ledger_factory: Callable[[str], CostLedgerRepository] | None = None


def set_cost_ledger_factory(
    factory: Callable[[str], CostLedgerRepository] | None,
) -> None:
    """注入 factory：``factory(farm_id) -> CostLedgerRepository``。

    None → 走預設（從 monitoring FarmRegistry 拿 farm DB path），同時清 lazy
    singleton 避免 test 間殘留。WMOM-20260509-F4 後 singleton 抽到
    ``shared.farm_registry_provider``，所有 routers 共用。
    """
    global _ledger_factory
    _ledger_factory = factory
    if factory is None:
        reset_farm_registry()


def _get_repo(farm_id: str) -> CostLedgerRepository:
    if _ledger_factory is not None:
        return _ledger_factory(farm_id)
    return get_cost_ledger_repository(resolve_farm_db_path(farm_id))


# ─────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────


@router.get("/ledger", response_model=CostLedgerListResponse)
async def list_ledger_entries(
    farm_id: str = Query(..., min_length=1),
    from_date: datetime | None = Query(default=None, alias="from"),
    to_date: datetime | None = Query(default=None, alias="to"),
    category: CostLedgerCategory | None = None,
    status: CostLedgerStatus | None = None,
    source_type: CostLedgerSourceType | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> CostLedgerListResponse:
    """List cost ledger entries（reverse-time order）。

    Filters：
    - ``from`` / ``to`` 日期區間（半開區間：[from, to)）
    - ``category``: material / labour / equipment / revenue_loss
    - ``status``: estimated / confirmed
    - ``source_type``: material_request / work_order / fault / manual
    """
    repo = _get_repo(farm_id)
    items, total = repo.list(
        farm_id=farm_id,
        from_date=from_date,
        to_date=to_date,
        category=category,
        status=status,
        source_type=source_type,
        limit=limit,
        offset=offset,
    )
    return CostLedgerListResponse(
        total=total,
        items=[CostLedgerEntryResponse.model_validate(e) for e in items],
    )


@router.get("/ledger/summary", response_model=CostLedgerSummaryResponse)
async def cost_ledger_summary(
    farm_id: str = Query(..., min_length=1),
    from_date: datetime | None = Query(default=None, alias="from"),
    to_date: datetime | None = Query(default=None, alias="to"),
    status: CostLedgerStatus | None = Query(
        default=None,
        description="None = all, 'confirmed' = actual cost only (給月報結算用)",
    ),
) -> CostLedgerSummaryResponse:
    """4 大類加總（material / labour / equipment / revenue_loss）。

    - ``status=confirmed`` → 只算 confirmed entries（actual cost）
    - ``status=estimated`` → 只算 estimated entries
    - ``status=None`` → 全部加總（給 dashboard 看 in-flight cost）

    給 monthly_report (A8) 用：傳 ``status=confirmed`` 拿當月實際 cost。
    """
    repo = _get_repo(farm_id)
    summary = repo.summary_by_category(
        farm_id=farm_id,
        from_date=from_date,
        to_date=to_date,
        status=status,
    )
    by_category = [
        CategorySummaryItem(category=cat, total=total)
        for cat, total in summary.items()
    ]
    grand_total = sum((it.total for it in by_category), Decimal("0"))
    return CostLedgerSummaryResponse(
        farm_id=farm_id,
        from_date=from_date,
        to_date=to_date,
        status_filter=status,
        by_category=by_category,
        grand_total=grand_total,
    )
