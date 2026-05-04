"""Cost module adapter — bridge between engine layer and windMindOM API layer.

職責：

1. **Demo dataset loader** — 載入 K13（與未來其他 demo dataset），把 JSON / CSV
   轉成 engine dataclass。把 4 個 test 內重複的 `build_*_params` 邏輯收斂到此。

2. **Request → engine adapter** — pydantic CostForecastRequest 等 → engine 參數
   tuple。M2 PoC 階段只支援 named demo dataset（"k13"）；未來可接客戶 upload。

3. **Engine result → response adapter** — CostCalResult / MonteCarloResult /
   VarFluctCalcResult → pydantic response model（給 FastAPI router 用）。

設計邊界：
- Engine layer 維持 ECN-compatible（dataclass，不變）
- API layer 用 pydantic（windMindOM canonical schema）
- 翻譯層在這個檔案，**單向依賴**：adapter import engine，engine 不 import adapter

Migration baseline：
- K13 dataset 路徑、欄位 mapping、stochastic bound 預設值 — 都從 4 個 test 沿用，
  保證 bit-perfect 等價（adapter refactor 後 pytest 仍然 20 PASS + 1 XFAIL）
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modules.cost.engine.cost_cal import CostCalResult
from modules.cost.engine.cost_cal.data_classes import (
    SEASONS,
    ComponentParams,
    EquipmentParams,
    FixedCostParams,
    FTCParams,
    MCParams,
    PMParams,
    SeasonResult,
    WaitingTimePolynomial,
    WindFarmParams,
)
from modules.cost.engine.cost_cal.lcoe import LCOEResult
from modules.cost.engine.monte_carlo import compute_percentiles
from modules.cost.engine.monte_carlo.runner import MonteCarloResult
from modules.cost.engine.var_fluct.calculator import VarFluctCalcResult


# ─────────────────────────────────────────────────────────────────────────
# K13 dataset constants（FTC defaults + MC equipment mapping）
# 從 4 個 test 沿用，與 ECN reference 一致
# ─────────────────────────────────────────────────────────────────────────

K13_FTC_DEFAULTS: dict[int, dict[str, Any]] = {
    1: {"repair_hours": 2, "long_working_day": False},
    2: {"repair_hours": 4, "long_working_day": False},
    3: {"repair_hours": 8, "long_working_day": False},
    4: {"repair_hours": 8, "long_working_day": False},
    5: {"repair_hours": 16, "long_working_day": True},
    6: {"repair_hours": 16, "long_working_day": False},
    7: {"repair_hours": 24, "long_working_day": True},
    8: {"repair_hours": 24, "long_working_day": True},
    9: {"repair_hours": 8, "long_working_day": False},
    10: {"repair_hours": 16, "long_working_day": False},
    11: {"repair_hours": 24, "long_working_day": False},
    12: {"repair_hours": 40, "long_working_day": False},
    13: {"repair_hours": 40, "long_working_day": False},
}

K13_MC_EQUIPMENT: dict[int, int | None] = {
    1: None, 2: 1, 3: 1, 4: 1, 5: 1, 6: 4,
}

DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data" / "demo"


# ─────────────────────────────────────────────────────────────────────────
# EngineParams — 6-tuple 結果的命名容器
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class EngineParams:
    """6 個 engine 參數的 bundle。

    透過命名欄位避免「6-tuple 拆解時順序記不住」的 bug。
    """

    wind_farm: WindFarmParams
    components: list[ComponentParams]
    equipment_list: list[EquipmentParams]
    pm_schedules: list[PMParams]
    fixed_costs: list[FixedCostParams]
    poly_lookup: dict[tuple[int, str], WaitingTimePolynomial]


# ─────────────────────────────────────────────────────────────────────────
# Demo dataset loader — K13
# ─────────────────────────────────────────────────────────────────────────

def _load_json(data_dir: Path, name: str) -> Any:
    with open(data_dir / name) as f:
        return json.load(f)


def _ww_nr_to_idx(ww_data: dict) -> dict[int, int]:
    """Build window_nr → 0-based idx mapping (first-occurrence wins)."""
    mapping: dict[int, int] = {}
    for idx, ww_def in enumerate(ww_data["definition_sheet"]):
        nr = ww_def["window_nr"]
        if nr not in mapping:
            mapping[nr] = idx
    return mapping


def load_k13_engine_params(
    data_dir: Path | None = None,
    stochastic: bool = False,
) -> EngineParams:
    """Load K13 demo dataset → engine params bundle。

    Args:
        data_dir: K13 JSON / CSV 所在目錄。預設 modules/cost/data/demo/。
        stochastic: 若 True，加上 EquipmentParams / FTCParams / ComponentParams 的
                    stochastic bound（給 monte_carlo 用，±20%/±30%/±30%）。

    Returns:
        EngineParams — 可直接傳給 engine 的 6 個參數。
    """
    dd = data_dir or DEFAULT_DATA_DIR

    gen = _load_json(dd, "k13_general.json")
    ft = _load_json(dd, "k13_fault_types_wt.json")
    eq = _load_json(dd, "k13_equipment.json")
    fc = _load_json(dd, "k13_fixed_costs.json")
    wt = _load_json(dd, "k13_waiting_time_coefficients.json")
    ww = _load_json(dd, "k13_weather_windows.json")
    nr2idx = _ww_nr_to_idx(ww)

    # 1) WindFarmParams
    turbine = gen["turbine"]
    wind_farm = WindFarmParams(
        nr_turbines=gen["number_of_turbines"],
        capacity_kw=turbine["p_rated_kw"],
        investment_cost_per_kw=turbine["investment_costs_euro_per_kw"],
        kwh_price=gen["kwh_price"],
        lifetime_years=gen["lifetime_years"],
        farm_efficiency=gen["wind_farm_efficiency"],
        capacity_factors=gen["capacity_factors"],
        season_weights=gen["weighing_factors"],
        tech_hourly_rate=0.0,
        tech_yearly_salary=gen["technician_costs"]["yearly_salary"],
        tech_count=gen["technician_costs"]["employed_technicians"],
    )

    # 2) Components（含 stochastic bounds when enabled）
    ftc_lookup = {mc["ftc_nr"]: mc for mc in ft.get("maintenance_categories", [])}
    components: list[ComponentParams] = []
    for comp_data in ft["components"]:
        mc_params: list[MCParams] = []
        for sub in comp_data.get("sub_categories", []):
            mc_index = sub["maintenance_category"]
            ftc_nr = sub["ftc"]
            ftc_def = ftc_lookup.get(ftc_nr, {})
            ftc_defaults = K13_FTC_DEFAULTS.get(ftc_nr, {})
            repair_type = "cbm" if ftc_def.get("type_corr_cbm", 0) == 1 else "corrective"
            base_repair_hours = ftc_defaults.get("repair_hours", 0)
            ftc = FTCParams(
                ftc_number=ftc_nr,
                repair_type=repair_type,
                material_cost_pct=ftc_def.get("material_cost_pct", 0),
                material_cost_euro=ftc_def.get("material_cost_euro", 0),
                crew_size=ftc_def.get("crew_size", 0),
                repair_hours=base_repair_hours,
                logistics_hours=0.0,
                organization_hours=0.0,
                long_working_day=ftc_defaults.get("long_working_day", False),
                repair_hours_min=base_repair_hours * 0.7 if (stochastic and base_repair_hours > 0) else None,
                repair_hours_max=base_repair_hours * 1.3 if (stochastic and base_repair_hours > 0) else None,
            )
            mc_params.append(MCParams(
                category_index=mc_index,
                probability=sub["probability"],
                equipment_index=K13_MC_EQUIPMENT.get(mc_index),
                nr_additional_inspections=sub.get("additional_inspections") or 0,
                ftc=ftc,
            ))
        name = comp_data["name"]
        code = name.split(" - ")[0].strip() if " - " in name else name[:10]
        freq = comp_data["annual_failure_freq"]
        components.append(ComponentParams(
            component_name=name,
            component_code=code,
            component_type="WT",
            annual_failure_freq=freq,
            maintenance_categories=mc_params,
            freq_min=freq * 0.7 if stochastic else None,
            freq_ml=freq if stochastic else None,
            freq_max=freq * 1.3 if stochastic else None,
        ))

    # 3) Equipment（含 stochastic bounds when enabled）
    equipment_list: list[EquipmentParams] = []
    for e in eq:
        nidx = nr2idx.get(e.get("weather_window_normal")) if e.get("weather_window_normal") else None
        lidx = nr2idx.get(e.get("weather_window_long")) if e.get("weather_window_long") else None
        ct = "mission" if e.get("fixed_cost_freq_type") == 1 else "day"
        fy = e.get("fixed_cost_euro_per_year") or 0
        dr = fy / 365.0 if ct == "day" and fy > 0 else 0.0
        mob = e.get("mob_demob_cost_euro") or 0.0
        equipment_list.append(EquipmentParams(
            equipment_index=e["nr"],
            name=e["description"],
            ww_normal_index=nidx,
            ww_long_index=lidx,
            nr_available=e.get("availability_nr") or 1,
            logistic_hours=e.get("logistic_time_hr") or 0.0,
            travel_hours=e.get("travel_time_hr") or 0.0,
            cost_type=ct,
            day_rate=dr,
            mob_cost=mob,
            mission_rate=0.0,
            day_rate_min=dr * 0.8 if (stochastic and dr > 0) else None,
            day_rate_max=dr * 1.2 if (stochastic and dr > 0) else None,
            mob_cost_min=mob * 0.8 if (stochastic and mob > 0) else None,
            mob_cost_max=mob * 1.2 if (stochastic and mob > 0) else None,
        ))

    # 4) PM schedules
    pm_schedules: list[PMParams] = []
    for p in fc.get("preventive_maintenance", []):
        ptype = "WT" if p.get("type_wt_bop", 0) == 0 else "BOP"
        wi = nr2idx.get(p.get("weather_window")) if p.get("weather_window") else None
        pm_schedules.append(PMParams(
            description=p["description"],
            pm_type=ptype,
            nr_occurrences=p["occurrences_lifetime"],
            duration_hours=p["duration_hrs"],
            crew_size=p.get("crew_size", 0),
            material_cost=p.get("material_costs_euro", 0),
            equipment_index=p.get("equipment_type"),
            ww_index=wi,
            travel_hours=p.get("travel_time_hr", 0),
            long_working_day=bool(p.get("length_working_day", 0)),
            pct_farm_shutdown=p.get("pct_windfarm_shutdown", 1.0),
            season_distribution=p.get("season_distribution", {}),
        ))

    # 5) Fixed costs
    fixed_costs: list[FixedCostParams] = []
    for f in fc.get("fixed_yearly_costs", []):
        sd = f.get("season_distribution", {})
        fixed_costs.append(FixedCostParams(
            description=f["description"],
            annual_cost=f["total_euro"],
            season_distribution={
                "winter": sd.get("winter_pct", 0.25),
                "spring": sd.get("spring_pct", 0.25),
                "summer": sd.get("summer_pct", 0.25),
                "autumn": sd.get("autumn_pct", 0.25),
            },
        ))

    # 6) Polynomial lookup
    poly_lookup: dict[tuple[int, str], WaitingTimePolynomial] = {}
    for season, coeffs_list in wt.get("waiting_time", {}).items():
        for coeff in coeffs_list:
            wi = nr2idx.get(coeff["nr"])
            if wi is None:
                continue
            poly_lookup[(wi, season)] = WaitingTimePolynomial(
                window_index=wi,
                season=season,
                c0=coeff.get("c0", 0.0),
                c1=coeff.get("c1", 0.0),
                c2=coeff.get("c2", 0.0),
                c3=coeff.get("c3", 0.0),
            )

    return EngineParams(
        wind_farm=wind_farm,
        components=components,
        equipment_list=equipment_list,
        pm_schedules=pm_schedules,
        fixed_costs=fixed_costs,
        poly_lookup=poly_lookup,
    )


# ─────────────────────────────────────────────────────────────────────────
# Engine result → API response 轉換
# ─────────────────────────────────────────────────────────────────────────

def cost_result_to_response(result: CostCalResult) -> dict:
    """CostCalResult → API-friendly dict（待 cost_schemas 接手 pydantic 化）。

    返回值的 key 直接對應 schemas/cost_schemas.py:CostForecastResponse 欄位。
    """
    return {
        "availability_time": result.availability_time,
        "availability_energy": result.availability_energy,
        "total_revenue_loss": result.total_revenue_loss,
        "total_repair_cost": result.total_repair_cost,
        "total_effort": result.total_effort,
        "cost_per_kwh": result.cost_per_kwh,
        "seasonal": {
            season: _seasonal_to_dict(result.seasonal_results[season])
            for season in SEASONS
            if season in result.seasonal_results
        },
    }


def _seasonal_to_dict(sr: SeasonResult) -> dict:
    return {
        "season": sr.season,
        "corrective_wt_material": sr.corrective_wt_material,
        "corrective_wt_labour": sr.corrective_wt_labour,
        "corrective_wt_equipment": sr.corrective_wt_equipment,
        "corrective_wt_mob": sr.corrective_wt_mob,
        "corrective_wt_revenue_loss": sr.corrective_wt_revenue_loss,
        "corrective_wt_downtime": sr.corrective_wt_downtime,
        "corrective_bop_total": sr.corrective_bop_total,
        "preventive_total": sr.preventive_total,
        "preventive_material": sr.preventive_material,
        "preventive_revenue_loss": sr.preventive_revenue_loss,
        "preventive_downtime": sr.preventive_downtime,
        "fixed_cost": sr.fixed_cost,
        "total_effort": sr.total_effort,
        "total_downtime": sr.total_downtime,
    }


def lcoe_result_to_response(result: LCOEResult) -> dict:
    """LCOEResult → API-friendly dict。"""
    return {
        "lcoe": result.lcoe,
        "capex_total": result.capex_total,
        "opex_total_npv": result.opex_total_npv,
        "energy_total_npv": result.energy_total_npv,
        "total_cost_npv": result.total_cost_npv,
    }


def mc_result_to_response(result: MonteCarloResult) -> dict:
    """MonteCarloResult → API-friendly dict（含 deterministic + percentiles）。"""
    cost = compute_percentiles(result.total_costs)
    avail_t = compute_percentiles(result.availability_time)
    avail_e = compute_percentiles(result.availability_energy)
    return {
        "n_simulations": result.n_simulations,
        "seed": result.seed,
        "deterministic": cost_result_to_response(result.deterministic_result),
        "percentiles": {
            "cost": cost,
            "availability_time": avail_t,
            "availability_energy": avail_e,
        },
    }


def vf_result_to_response(result: VarFluctCalcResult) -> dict:
    """VarFluctCalcResult → API-friendly dict（含 yearly array + summary）。"""
    return {
        "yearly": [
            {
                "year": y.year,
                "failure_multiplier": y.failure_multiplier,
                "cost_escalation_factor": y.cost_escalation_factor,
                "kwh_price": y.kwh_price,
                "capacity_factor_multiplier": y.capacity_factor_multiplier,
                "total_repair_cost": y.total_repair_cost,
                "total_effort": y.total_effort,
                "revenue_loss": y.revenue_loss,
                "fixed": y.fixed,
                "availability_time": y.availability_time,
                "availability_energy": y.availability_energy,
            }
            for y in result.yearly
        ],
        "summary": {
            "npv_total_effort": result.summary.npv_total_effort,
            "npv_total_repair": result.summary.npv_total_repair,
            "npv_total_revenue_loss": result.summary.npv_total_revenue_loss,
            "avg_annual_effort": result.summary.avg_annual_effort,
            "min_year_effort": result.summary.min_year_effort,
            "max_year_effort": result.summary.max_year_effort,
            "min_year_index": result.summary.min_year_index,
            "max_year_index": result.summary.max_year_index,
            "lifetime_availability_time": result.summary.lifetime_availability_time,
            "lifetime_availability_energy": result.summary.lifetime_availability_energy,
        },
    }
