"""Reporting Pydantic schemas（WMOM-20260509-08）。

對應 monthly_report 4 大區塊 + annual_budget 12 個月 forecast。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────────
# Monthly report — 4 區塊
# ─────────────────────────────────────────────────────────────────────────


class CostBreakdownItem(BaseModel):
    """4 大成本類別其中一筆。"""

    model_config = ConfigDict(from_attributes=True)

    category: str = Field(description="material / labour / equipment / revenue_loss")
    estimated: Decimal = Field(default=Decimal("0"), description="estimated entries 加總")
    confirmed: Decimal = Field(default=Decimal("0"), description="confirmed entries 加總")
    total: Decimal = Field(default=Decimal("0"), description="estimated + confirmed")


class CostSummary(BaseModel):
    """月報 cost section — 4 大類 + grand total。"""

    by_category: list[CostBreakdownItem]
    estimated_total: Decimal
    confirmed_total: Decimal
    grand_total: Decimal


class WorkOrderTypeStats(BaseModel):
    """工單按 type 分類統計（CORRECTIVE / PREVENTIVE / INSPECTION / COMMISSIONING）。"""

    type: str
    finished: int = Field(default=0, description="當月 finished_at 落在期間 + 已 closed")
    closed: int = Field(default=0, description="當月 closed_at 落在期間")
    in_progress: int = Field(default=0, description="期間結尾仍 in_progress / dispatched")


class WorkOrderSummary(BaseModel):
    """月報 work order section。"""

    by_type: list[WorkOrderTypeStats]
    total_finished: int
    total_closed: int
    total_in_progress: int
    total_actual_hours: float = Field(description="當月 actual_hours 加總（給 availability 推算）")


class AvailabilityMetrics(BaseModel):
    """月報 availability section（time / energy 雙指標）。"""

    time_availability: float = Field(
        ge=0.0, le=1.0,
        description="0.0-1.0：1 = 100% 可用",
    )
    energy_availability: float = Field(
        ge=0.0, le=1.0,
        description="0.0-1.0：能量加權 availability，無物理資料時 = time_availability",
    )
    total_hours_in_period: float
    downtime_hours: float
    source: str = Field(
        description="`work_order_derived` (default) / `physics_simulator` (M5+ 注入後)",
    )


class KpiHighlights(BaseModel):
    """月報摘要 KPI（首頁第二區塊）。"""

    grand_total_cost: Decimal
    confirmed_cost_ratio: float = Field(
        ge=0.0, le=1.0,
        description="confirmed / (estimated + confirmed)；越接近 1 表月報越定案",
    )
    work_orders_finished: int
    average_repair_hours: float = Field(
        description="actual_hours / finished work order 數，0 if no finished WO",
    )
    time_availability: float


class MonthlyReportData(BaseModel):
    """月報完整資料結構（傳進 PDF / HTML render）。"""

    farm_id: str
    farm_name: Optional[str] = None
    year: int
    month: int = Field(ge=1, le=12)
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    kpi: KpiHighlights
    cost: CostSummary
    work_orders: WorkOrderSummary
    availability: AvailabilityMetrics
    notable_events: list["NotableEvent"] = Field(
        default_factory=list,
        description="當月重大事件 timeline（高優先 WO / 簽核 reject 等）",
    )


class NotableEvent(BaseModel):
    """月報重大事件 timeline 一筆。"""

    occurred_at: datetime
    event_type: str = Field(description="work_order_created / signoff_rejected / ...")
    title: str
    detail: Optional[str] = None


# 解 forward ref（NotableEvent 在 MonthlyReportData 後定義）
MonthlyReportData.model_rebuild()


# ─────────────────────────────────────────────────────────────────────────
# Annual budget — 12 個月 forecast
# ─────────────────────────────────────────────────────────────────────────


class MonthlyBudgetEntry(BaseModel):
    """單月 budget forecast。"""

    month: int = Field(ge=1, le=12)
    forecast_total: Decimal
    forecast_by_category: dict[str, Decimal] = Field(
        default_factory=dict,
        description="material / labour / equipment / revenue_loss → 預測 amount",
    )
    actual_total: Optional[Decimal] = Field(
        default=None,
        description="若該月 confirmed 資料已落入 ledger，回填實際值；未來月份 None",
    )
    method: str = Field(
        default="historical_average",
        description="historical_average / linear_trend / 等推算法",
    )


class AnnualBudgetData(BaseModel):
    """年度預算完整 12 個月 + 統計。"""

    farm_id: str
    farm_name: Optional[str] = None
    year: int
    generated_at: datetime
    months: list[MonthlyBudgetEntry]
    annual_forecast_total: Decimal
    annual_actual_total: Decimal
    method: str = Field(default="historical_average")
    notes: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────
# Templates listing
# ─────────────────────────────────────────────────────────────────────────


class ReportTemplate(BaseModel):
    """`GET /api/reporting/templates` 回傳一筆。"""

    id: str
    name: str
    name_zh: str
    description: str
    sections: list[str]
    formats: list[str] = Field(description="支援輸出格式 e.g. ['html', 'pdf']")


class ReportTemplateListResponse(BaseModel):
    """`GET /api/reporting/templates` 回傳。"""

    total: int
    items: list[ReportTemplate]
