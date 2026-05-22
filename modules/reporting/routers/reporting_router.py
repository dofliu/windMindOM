"""FastAPI reporting router（WMOM-20260509-08）— 3 endpoints。

- POST /api/reporting/monthly?farm_id=...&year=...&month=...&format=pdf|html|json
- POST /api/reporting/annual-budget?farm_id=...&year=...&format=pdf|json
- GET  /api/reporting/templates

DI pattern：與 cost_ledger_router 一致，提供 setter 給 test 注入 ledger / wo factory。
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response

from modules.cost.repository.cost_ledger_repository import (
    CostLedgerRepository,
    get_cost_ledger_repository,
)
from modules.workflow.repository.work_order_repository import (
    WorkOrderRepository,
    get_repository as get_work_order_repository,
)

from modules.reporting.schemas.reporting_schemas import (
    AnnualBudgetData,
    MonthlyReportData,
    ReportTemplate,
    ReportTemplateListResponse,
)
from modules.reporting.services.annual_budget import (
    compute_annual_budget,
    render_annual_budget_pdf,
)
from modules.reporting.services.kpi_calculator import (
    AvailabilityProvider,
    compute_monthly_report_data,
)
from modules.reporting.services.monthly_report import render_html, render_pdf
from shared.farm_registry_provider import (
    reset_farm_registry,
    resolve_farm_db_path,
)

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reporting", tags=["reporting"])


# ─────────────────────────────────────────────────────────────────────────
# DI factories
# ─────────────────────────────────────────────────────────────────────────


_ledger_factory: Optional[Callable[[str], CostLedgerRepository]] = None
_wo_factory: Optional[Callable[[str], WorkOrderRepository]] = None
_availability_provider: Optional[AvailabilityProvider] = None


def set_ledger_factory(factory: Optional[Callable[[str], CostLedgerRepository]]) -> None:
    """注入 cost ledger repository factory。

    WMOM-20260522-01：``None`` 同時呼叫 ``reset_farm_registry()`` 清 shared
    singleton，避免 test 間殘留（與 4 個 workflow / cost routers 行為對齊）。
    """
    global _ledger_factory
    _ledger_factory = factory
    if factory is None:
        reset_farm_registry()


def set_work_order_factory(factory: Optional[Callable[[str], WorkOrderRepository]]) -> None:
    """注入 work order repository factory。

    WMOM-20260522-01：``None`` 同時呼叫 ``reset_farm_registry()`` 清 shared singleton。
    """
    global _wo_factory
    _wo_factory = factory
    if factory is None:
        reset_farm_registry()


def set_availability_provider(provider: Optional[AvailabilityProvider]) -> None:
    """注入物理模擬 availability provider（M5+ 用）；None 走 work_order 推算。"""
    global _availability_provider
    _availability_provider = provider


def _get_ledger_repo(farm_id: str) -> CostLedgerRepository:
    if _ledger_factory is not None:
        return _ledger_factory(farm_id)
    return get_cost_ledger_repository(resolve_farm_db_path(farm_id))


def _get_wo_repo(farm_id: str) -> WorkOrderRepository:
    if _wo_factory is not None:
        return _wo_factory(farm_id)
    return get_work_order_repository(resolve_farm_db_path(farm_id))


# Review fix (must-fix #3)：farm_id 被嵌入 Content-Disposition header 之前
# 必須先 sanitize，避免 `farm_id=foo"; filename="evil` 這種 header injection。
_SAFE_FILENAME_CHARS = re.compile(r"[^a-zA-Z0-9_\-]")


def _safe_filename_token(raw: str) -> str:
    """把任意字串轉成可安全嵌入 filename 的 token（只留 alnum + _ -）。"""
    cleaned = _SAFE_FILENAME_CHARS.sub("_", raw)
    return cleaned or "unknown"


# ─────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────


_AVAILABLE_TEMPLATES = [
    ReportTemplate(
        id="monthly_v1",
        name="Monthly Operations Report",
        name_zh="月運維報表",
        description="封面 + KPI + 4 大成本 + 工單統計 + 可用率 + 重大事件 timeline",
        sections=["cover", "kpi", "cost", "work_orders", "availability", "events"],
        formats=["html", "pdf", "json"],
    ),
    ReportTemplate(
        id="annual_budget_v1",
        name="Annual Budget Forecast",
        name_zh="年度預算 forecast",
        description="12 個月 forecast — 過去用實際 confirmed，未來用歷史平均推算",
        sections=["cover", "monthly_table", "annual_total"],
        formats=["pdf", "json"],
    ),
]


@router.get("/templates", response_model=ReportTemplateListResponse)
async def list_templates() -> ReportTemplateListResponse:
    """列出可用 report templates。"""
    return ReportTemplateListResponse(
        total=len(_AVAILABLE_TEMPLATES),
        items=_AVAILABLE_TEMPLATES,
    )


@router.post("/monthly")
async def generate_monthly_report(
    farm_id: str = Query(..., min_length=1),
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    output_format: str = Query(
        default="pdf",
        alias="format",
        pattern="^(pdf|html|json)$",
        description="pdf (default) / html (preview) / json (structured data)",
    ),
    farm_name: Optional[str] = Query(default=None),
) -> Response:
    """產出單月月報。

    - ``format=pdf``  → 回 PDF binary (Content-Type: application/pdf)
    - ``format=html`` → 回 HTML 字串 (preview)
    - ``format=json`` → 回 ``MonthlyReportData`` 結構化資料

    Acceptance：完整內容 4 大區塊（KPI / cost / work orders / availability）
    """
    ledger_repo = _get_ledger_repo(farm_id)
    wo_repo = _get_wo_repo(farm_id)

    try:
        data: MonthlyReportData = compute_monthly_report_data(
            ledger_repo=ledger_repo,
            wo_repo=wo_repo,
            farm_id=farm_id,
            year=year,
            month=month,
            farm_name=farm_name,
            availability_provider=_availability_provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if output_format == "json":
        # Decimal → str (Pydantic default)
        return JSONResponse(content=data.model_dump(mode="json"))

    if output_format == "html":
        html = render_html(data)
        return HTMLResponse(content=html)

    # default pdf
    pdf_bytes = render_pdf(data)
    filename = f"monthly_report_{_safe_filename_token(farm_id)}_{year}{month:02d}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )


@router.post("/annual-budget")
async def generate_annual_budget(
    farm_id: str = Query(..., min_length=1),
    year: int = Query(..., ge=2000, le=2100),
    output_format: str = Query(
        default="pdf",
        alias="format",
        pattern="^(pdf|json)$",
    ),
    method: str = Query(default="historical_average"),
    history_window: int = Query(default=3, ge=1, le=12),
    current_month: Optional[int] = Query(default=None, ge=1, le=12),
    farm_name: Optional[str] = Query(default=None),
) -> Response:
    """產出年度 12 個月 budget forecast。"""
    ledger_repo = _get_ledger_repo(farm_id)

    try:
        data: AnnualBudgetData = compute_annual_budget(
            ledger_repo=ledger_repo,
            farm_id=farm_id,
            year=year,
            farm_name=farm_name,
            method=method,
            history_window=history_window,
            current_month=current_month,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if output_format == "json":
        return JSONResponse(content=data.model_dump(mode="json"))

    pdf_bytes = render_annual_budget_pdf(data)
    filename = f"annual_budget_{_safe_filename_token(farm_id)}_{year}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )
