"""FastAPI router for cost module — POST /api/cost/* endpoints。

對應 issue：WMOM-20260504-07

4 個 endpoints：

| Method | Path                         | Request                    | Response               |
|--------|------------------------------|----------------------------|------------------------|
| POST   | /api/cost/forecast           | CostForecastRequest        | CostForecastResponse   |
| POST   | /api/cost/lcoe               | LCOERequest                | LCOEResponse           |
| POST   | /api/cost/monte-carlo        | MonteCarloRequest          | MonteCarloResponse     |
| POST   | /api/cost/var-fluct          | VarFluctRequest            | VarFluctResponse       |

設計：
- Endpoints 都 POST（即使 LCOE 看似只讀）— 統一 request body pattern
- Response 直接 pydantic model（FastAPI 自動序列化）
- 計算邏輯在 adapter / engine，router 只負責 wire-up
- 錯誤處理：dataset 不認得 → 422（pydantic validation）；engine 異常 → 500
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from modules.cost.adapter import (
    cost_result_to_response,
    lcoe_result_to_response,
    load_k13_engine_params,
    mc_result_to_response,
    vf_result_to_response,
)
from modules.cost.engine.cost_cal import run_cost_calculation
from modules.cost.engine.cost_cal.lcoe import calculate_lcoe
from modules.cost.engine.cost_cal.revenue_loss import annual_energy_production_mwh
from modules.cost.engine.monte_carlo import run_monte_carlo
from modules.cost.engine.var_fluct import run_var_fluct_calculation
from modules.cost.engine.var_fluct.bathtub import BathtubParams
from modules.cost.engine.var_fluct.calculator import VarFluctConfig
from modules.cost.schemas.cost_schemas import (
    CostForecastRequest,
    CostForecastResponse,
    LCOERequest,
    LCOEResponse,
    MonteCarloRequest,
    MonteCarloResponse,
    VarFluctRequest,
    VarFluctResponse,
)


router = APIRouter(prefix="/api/cost", tags=["cost"])


def _load_dataset(name: str):
    """Resolve dataset name → EngineParams。M2 PoC 階段只支援 k13。"""
    if name == "k13":
        return load_k13_engine_params(stochastic=False)
    raise HTTPException(status_code=404, detail=f"Unknown dataset: {name}")


def _load_dataset_stochastic(name: str):
    """同 _load_dataset，但開 stochastic bounds（給 monte_carlo 用）。"""
    if name == "k13":
        return load_k13_engine_params(stochastic=True)
    raise HTTPException(status_code=404, detail=f"Unknown dataset: {name}")


# ─────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────


@router.post("/forecast", response_model=CostForecastResponse)
async def cost_forecast(req: CostForecastRequest) -> CostForecastResponse:
    """跑 K13 cost calculation，回 6 個 top-level metric + 4 季 breakdown。

    範例 response 摘要（K13）:
      - availability_time = 0.9402
      - total_effort = 67.96 M EUR/yr
      - cost_per_kwh = 0.0369 EUR/kWh
      - seasonal: winter / spring / summer / autumn 各別 cost subcategories
    """
    p = _load_dataset(req.dataset)
    result = run_cost_calculation(
        wind_farm=p.wind_farm,
        components=p.components,
        equipment_list=p.equipment_list,
        pm_schedules=p.pm_schedules,
        fixed_costs=p.fixed_costs,
        poly_lookup=p.poly_lookup,
    )
    return CostForecastResponse(**cost_result_to_response(result))


@router.post("/lcoe", response_model=LCOEResponse)
async def cost_lcoe(req: LCOERequest) -> LCOEResponse:
    """跑 K13 cost + LCOE 計算，回 LCOE + CAPEX + OPEX NPV。

    範例（K13 + capex_per_kw=1250 + discount_rate=0.08）:
      - lcoe = 72.94 EUR/MWh
      - capex_total = 650 M EUR
      - opex_total_npv = 667 M EUR
    """
    p = _load_dataset(req.dataset)

    # 先跑 cost_cal 取 annual_opex
    cost_result = run_cost_calculation(
        wind_farm=p.wind_farm,
        components=p.components,
        equipment_list=p.equipment_list,
        pm_schedules=p.pm_schedules,
        fixed_costs=p.fixed_costs,
        poly_lookup=p.poly_lookup,
    )

    annual_energy = annual_energy_production_mwh(p.wind_farm)
    lcoe = calculate_lcoe(
        capex_per_kw=req.capex_per_kw,
        capacity_kw=p.wind_farm.capacity_kw,
        nr_turbines=p.wind_farm.nr_turbines,
        lifetime=p.wind_farm.lifetime_years,
        discount_rate=req.discount_rate,
        annual_opex=cost_result.total_effort,
        annual_energy_mwh=annual_energy,
    )
    return LCOEResponse(**lcoe_result_to_response(lcoe))


@router.post("/monte-carlo", response_model=MonteCarloResponse)
async def cost_monte_carlo(req: MonteCarloRequest) -> MonteCarloResponse:
    """跑 Monte Carlo 風險評估，回 deterministic + percentiles (P10/P50/P90)。

    參數限制：n_simulations 10-10000；seed 可指定（預設 42）。

    範例（K13, n=100, seed=42）:
      - deterministic.total_effort = 67.96 M EUR/yr
      - cost.p50 ≈ 67.46 M EUR
      - availability_time.p50 ≈ 0.9405
    """
    p = _load_dataset_stochastic(req.dataset)
    mc = run_monte_carlo(
        wind_farm=p.wind_farm,
        components=p.components,
        equipment_list=p.equipment_list,
        pm_schedules=p.pm_schedules,
        fixed_costs=p.fixed_costs,
        poly_lookup=p.poly_lookup,
        n_simulations=req.n_simulations,
        seed=req.seed,
    )
    return MonteCarloResponse(**mc_result_to_response(mc))


@router.post("/var-fluct", response_model=VarFluctResponse)
async def cost_var_fluct(req: VarFluctRequest) -> VarFluctResponse:
    """跑 lifetime year-by-year 成本模擬，回 20 年 yearly + summary NPV。

    範例（K13 + bathtub 預設）:
      - yearly[0] = year 1, multiplier=1.5, total_effort=88.4 M EUR (early peak)
      - yearly[19] = year 20, multiplier=2.0, total_effort=131.4 M EUR (late peak)
      - summary.npv_total_effort = 776.6 M EUR
    """
    p = _load_dataset(req.dataset)

    # Build VarFluctConfig from request
    config = VarFluctConfig(
        failure_rate_model=req.failure_rate_model,
        cost_escalation_rate=req.cost_escalation_rate,
        capacity_degradation_rate=req.capacity_degradation_rate,
        discount_rate=req.discount_rate,
    )
    if req.bathtub is not None:
        config.bathtub_params = BathtubParams(
            beta_early=req.bathtub.beta_early,
            beta_late=req.bathtub.beta_late,
            early_life_years=req.bathtub.early_life_years,
            late_life_start=req.bathtub.late_life_start,
            early_peak=req.bathtub.early_peak,
            late_peak=req.bathtub.late_peak,
        )

    vf = run_var_fluct_calculation(
        wind_farm=p.wind_farm,
        components=p.components,
        equipment_list=p.equipment_list,
        pm_schedules=p.pm_schedules,
        fixed_costs=p.fixed_costs,
        poly_lookup=p.poly_lookup,
        config=config,
    )
    return VarFluctResponse(**vf_result_to_response(vf))
