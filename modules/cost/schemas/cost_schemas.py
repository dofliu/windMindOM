"""Cost API pydantic schemas — request / response models for FastAPI router.

對應 -07 將實作的 endpoints：
- POST /api/cost/forecast    → CostForecastRequest → CostForecastResponse
- POST /api/cost/monte-carlo → MonteCarloRequest → MonteCarloResponse
- POST /api/cost/var-fluct   → VarFluctRequest → VarFluctResponse
- GET  /api/cost/lcoe        → LCOERequest → LCOEResponse

M2 PoC 階段只支援 dataset="k13"（demo dataset）；未來可加客戶 upload。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────
# Common
# ─────────────────────────────────────────────────────────────────────────

DatasetName = Literal["k13"]
"""支援的 demo dataset 名稱。M2 PoC 只有 k13；之後加 user-upload mode。"""


# ─────────────────────────────────────────────────────────────────────────
# Cost forecast (cost_cal)
# ─────────────────────────────────────────────────────────────────────────

class CostForecastRequest(BaseModel):
    """POST /api/cost/forecast 的 request body。"""

    dataset: DatasetName = Field(default="k13", description="Demo dataset name")


class SeasonalCostBreakdown(BaseModel):
    """單季成本明細。"""

    season: Literal["winter", "spring", "summer", "autumn"]

    # Corrective WT
    corrective_wt_material: float = 0.0
    corrective_wt_labour: float = 0.0
    corrective_wt_equipment: float = 0.0
    corrective_wt_mob: float = 0.0
    corrective_wt_revenue_loss: float = 0.0
    corrective_wt_downtime: float = 0.0

    # Other categories
    corrective_bop_total: float = 0.0
    preventive_total: float = 0.0
    preventive_material: float = 0.0
    preventive_revenue_loss: float = 0.0
    preventive_downtime: float = 0.0

    fixed_cost: float = 0.0
    total_effort: float = 0.0
    total_downtime: float = 0.0


class CostForecastResponse(BaseModel):
    """POST /api/cost/forecast 的 response body。"""

    availability_time: float = Field(description="Availability based on time (0-1)")
    availability_energy: float = Field(description="Availability based on energy (0-1)")
    total_revenue_loss: float = Field(description="Annual revenue loss (EUR)")
    total_repair_cost: float = Field(description="Annual repair cost (EUR)")
    total_effort: float = Field(description="Total annual cost: repair + revenue loss (EUR)")
    cost_per_kwh: float = Field(description="Cost per kWh produced (EUR/kWh)")
    seasonal: dict[str, SeasonalCostBreakdown] = Field(
        description="4-season breakdown (keys: winter/spring/summer/autumn)"
    )


# ─────────────────────────────────────────────────────────────────────────
# LCOE
# ─────────────────────────────────────────────────────────────────────────

class LCOERequest(BaseModel):
    """GET /api/cost/lcoe（也可 POST 帶參數）的 request。"""

    dataset: DatasetName = Field(default="k13")
    capex_per_kw: float = Field(default=1250.0, description="EUR/kW")
    discount_rate: float = Field(default=0.08, description="0-1")


class LCOEResponse(BaseModel):
    """LCOE 計算結果。"""

    lcoe: float = Field(description="EUR/MWh")
    capex_total: float = Field(description="Total CAPEX (EUR)")
    opex_total_npv: float = Field(description="OPEX NPV over lifetime (EUR)")
    energy_total_npv: float = Field(description="Energy NPV over lifetime (MWh)")
    total_cost_npv: float = Field(description="CAPEX + OPEX NPV (EUR)")


# ─────────────────────────────────────────────────────────────────────────
# Monte Carlo
# ─────────────────────────────────────────────────────────────────────────

class MonteCarloRequest(BaseModel):
    """POST /api/cost/monte-carlo 的 request。"""

    dataset: DatasetName = Field(default="k13")
    n_simulations: int = Field(default=100, ge=10, le=10000)
    seed: int = Field(default=42, description="Random seed for reproducibility")


class PercentileStats(BaseModel):
    """Percentile + mean/std 統計。"""

    p10: float
    p50: float
    p90: float
    mean: float
    std: float


class MonteCarloPercentiles(BaseModel):
    """3 個 metric 的 percentile bundle。"""

    cost: PercentileStats
    availability_time: PercentileStats
    availability_energy: PercentileStats


class MonteCarloResponse(BaseModel):
    """POST /api/cost/monte-carlo response — 含 deterministic + percentiles。"""

    n_simulations: int
    seed: int
    deterministic: CostForecastResponse
    percentiles: MonteCarloPercentiles


# ─────────────────────────────────────────────────────────────────────────
# VarFluct (lifetime year-by-year)
# ─────────────────────────────────────────────────────────────────────────

class BathtubConfig(BaseModel):
    """Bathtub failure rate curve 參數。"""

    beta_early: float = 0.7
    beta_late: float = 1.5
    early_life_years: int = 2
    late_life_start: int = 15
    early_peak: float = 1.5
    late_peak: float = 2.0


class VarFluctRequest(BaseModel):
    """POST /api/cost/var-fluct request。"""

    dataset: DatasetName = Field(default="k13")
    failure_rate_model: Literal["bathtub", "constant", "custom"] = "bathtub"
    bathtub: BathtubConfig | None = None
    cost_escalation_rate: float = 0.02
    capacity_degradation_rate: float = 0.005
    discount_rate: float = 0.08


class YearResultResponse(BaseModel):
    """單年 cost result。"""

    year: int
    failure_multiplier: float
    cost_escalation_factor: float
    kwh_price: float
    capacity_factor_multiplier: float
    total_repair_cost: float
    total_effort: float
    revenue_loss: float
    fixed: float
    availability_time: float
    availability_energy: float


class VarFluctSummaryResponse(BaseModel):
    """VarFluct lifetime summary。"""

    npv_total_effort: float
    npv_total_repair: float
    npv_total_revenue_loss: float
    avg_annual_effort: float
    min_year_effort: float
    max_year_effort: float
    min_year_index: int
    max_year_index: int
    lifetime_availability_time: float
    lifetime_availability_energy: float


class VarFluctResponse(BaseModel):
    """POST /api/cost/var-fluct response。"""

    yearly: list[YearResultResponse]
    summary: VarFluctSummaryResponse
