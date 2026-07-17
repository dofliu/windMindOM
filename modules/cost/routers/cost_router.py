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

from fastapi import APIRouter, Depends, HTTPException

from modules.auth.dependencies import require_role
from modules.auth.roles import Role
from modules.cost.adapter import (
    EngineParams,
    FarmDatasetMeta,
    cost_result_to_response,
    lcoe_result_to_response,
    load_engine_params_from_farm,
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
    DatasetMeta,
    LCOERequest,
    LCOEResponse,
    MonteCarloRequest,
    MonteCarloResponse,
    VarFluctRequest,
    VarFluctResponse,
)


router = APIRouter(prefix="/api/cost", tags=["cost"])


def _resolve_dataset(name: str, stochastic: bool = False) -> tuple[EngineParams, DatasetMeta]:
    """把 dataset string 解析為 (EngineParams, DatasetMeta)。

    支援格式：
    - ``"k13"``           → K13 baseline（``source=k13_baseline``）
    - ``"farm:{farm_id}"`` → adapter 三層 lookup（farm_overlay / registry_derived / k13_fallback）
    - 其他                → 404

    WMOM-20260504-10：取代舊的雙路 ``_load_dataset`` / ``_load_dataset_stochastic``。
    """
    if name == "k13":
        params = load_k13_engine_params(stochastic=stochastic)
        meta = DatasetMeta(
            dataset_used="k13",
            farm_id=None,
            is_fallback=False,
            source="k13_baseline",
            warning=None,
        )
        return params, meta

    if name.startswith("farm:"):
        farm_id = name.removeprefix("farm:").strip()
        if not farm_id:
            raise HTTPException(status_code=422, detail="farm dataset 缺 farm_id（'farm:' 後沒帶值）")
        # 阻擋 path traversal / 控制字元 / 內含空白等可疑值（farm_id 本意為 slug）
        if any(c in farm_id for c in ("/", "\\", "\0", "..", " ", "\t", "\n")):
            raise HTTPException(
                status_code=422,
                detail=f"farm_id 含無效字元（不允許 / \\ .. 空白）: {farm_id!r}",
            )
        params, adapter_meta = load_engine_params_from_farm(farm_id, stochastic=stochastic)
        meta = _adapter_meta_to_schema(adapter_meta)
        return params, meta

    raise HTTPException(status_code=404, detail=f"Unknown dataset: {name}")


def _adapter_meta_to_schema(m: FarmDatasetMeta) -> DatasetMeta:
    """adapter dataclass → pydantic schema（避免 router import 兩個同名物件混淆）。"""
    return DatasetMeta(
        dataset_used=m.dataset_used,
        farm_id=m.farm_id,
        is_fallback=m.is_fallback,
        source=m.source,  # type: ignore[arg-type]
        warning=m.warning,
    )


# ─────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────


@router.post(
    "/forecast",
    response_model=CostForecastResponse,
    # WMOM-20260716-05h：成本檢視＝管理層（SUPERVISOR＋，ADMIN 全權）。enforce=false 放行。
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def cost_forecast(req: CostForecastRequest) -> CostForecastResponse:
    """跑 cost calculation，回 6 個 top-level metric + 4 季 breakdown + dataset_meta。

    範例 response 摘要（dataset="k13"）:
      - availability_time = 0.9402
      - total_effort = 67.96 M EUR/yr
      - cost_per_kwh = 0.0369 EUR/kWh
      - seasonal: winter / spring / summer / autumn 各別 cost subcategories
      - dataset_meta.source = k13_baseline
    """
    p, meta = _resolve_dataset(req.dataset)
    result = run_cost_calculation(
        wind_farm=p.wind_farm,
        components=p.components,
        equipment_list=p.equipment_list,
        pm_schedules=p.pm_schedules,
        fixed_costs=p.fixed_costs,
        poly_lookup=p.poly_lookup,
    )
    return CostForecastResponse(**cost_result_to_response(result), dataset_meta=meta)


@router.post(
    "/lcoe",
    response_model=LCOEResponse,
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def cost_lcoe(req: LCOERequest) -> LCOEResponse:
    """跑 K13 cost + LCOE 計算，回 LCOE + CAPEX + OPEX NPV。

    範例（K13 + capex_per_kw=1250 + discount_rate=0.08）:
      - lcoe = 72.94 EUR/MWh
      - capex_total = 650 M EUR
      - opex_total_npv = 667 M EUR
    """
    p, meta = _resolve_dataset(req.dataset)

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
    return LCOEResponse(**lcoe_result_to_response(lcoe), dataset_meta=meta)


@router.post(
    "/monte-carlo",
    response_model=MonteCarloResponse,
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def cost_monte_carlo(req: MonteCarloRequest) -> MonteCarloResponse:
    """跑 Monte Carlo 風險評估，回 deterministic + percentiles (P10/P50/P90)。

    參數限制：n_simulations 10-10000；seed 可指定（預設 42）。

    範例（K13, n=100, seed=42）:
      - deterministic.total_effort = 67.96 M EUR/yr
      - cost.p50 ≈ 67.46 M EUR
      - availability_time.p50 ≈ 0.9405
    """
    p, meta = _resolve_dataset(req.dataset, stochastic=True)
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
    return MonteCarloResponse(**mc_result_to_response(mc), dataset_meta=meta)


@router.post(
    "/var-fluct",
    response_model=VarFluctResponse,
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def cost_var_fluct(req: VarFluctRequest) -> VarFluctResponse:
    """跑 lifetime year-by-year 成本模擬，回 20 年 yearly + summary NPV。

    範例（K13 + bathtub 預設）:
      - yearly[0] = year 1, multiplier=1.5, total_effort=88.4 M EUR (early peak)
      - yearly[19] = year 20, multiplier=2.0, total_effort=131.4 M EUR (late peak)
      - summary.npv_total_effort = 776.6 M EUR
    """
    p, meta = _resolve_dataset(req.dataset)

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
    return VarFluctResponse(**vf_result_to_response(vf), dataset_meta=meta)
