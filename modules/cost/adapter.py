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
import logging
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Numeric-coerce 對照（_apply_wind_farm_overrides 用）— 防 JSON 把 int 寫成 string
_NUMERIC_FIELD_CASTS: dict[str, type] = {
    "nr_turbines": int,
    "lifetime_years": int,
    "capacity_kw": float,
    "investment_cost_per_kw": float,
    "kwh_price": float,
    "farm_efficiency": float,
    "tech_hourly_rate": float,
    "tech_yearly_salary": float,
}

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
DEFAULT_FARMS_DIR = Path(__file__).resolve().parent / "data" / "farms"


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


@dataclass
class FarmDatasetMeta:
    """Cost API 回傳給前端的 dataset metadata。

    讓客戶在 dashboard 上看得到「這次計算到底是用哪個 dataset、是否 fallback」。

    source 值：
    - ``k13_baseline``     — 純 K13 demo（dataset == "k13"）
    - ``farm_overlay``     — 找到 ``cost_inputs.json``，套用 farm-specific overrides
    - ``registry_derived`` — 沒有 cost_inputs.json，但 FarmRegistry 有此 farm，僅用其
                             ``turbine_count`` + ``capacity_kw`` 推導 minimal overrides
    - ``k13_fallback``     — 兩者皆無，退回 K13 + warning
    """

    dataset_used: str  # "k13" | "farm:{id}"
    farm_id: str | None  # None when dataset_used == "k13"
    is_fallback: bool  # True 表示「想要 farm-specific 但落到 K13」
    source: str  # k13_baseline | farm_overlay | registry_derived | k13_fallback
    warning: str | None = None


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
# Farm-aware loader（K13 baseline + per-farm overrides）
#
# WMOM-20260504-10：客戶不應該被 hard-code K13（130 × 4 MW 北海離岸）綁住。
# 三層 lookup：
#   1. data/farms/{farm_id}/cost_inputs.json → wind_farm overrides
#   2. FarmRegistry.get_farm(farm_id) → 從 turbine_count / rated_power_kw 推 overrides
#   3. 兩者皆無 → 純 K13 + is_fallback=True
# ─────────────────────────────────────────────────────────────────────────


def _load_cost_inputs_json(
    farm_id: str, farms_dir: Path | None = None
) -> dict[str, Any] | None:
    """讀取 farm 對應的 cost_inputs.json；找不到回 None。"""
    fd = farms_dir or DEFAULT_FARMS_DIR
    p = fd / farm_id / "cost_inputs.json"
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _apply_wind_farm_overrides(
    base: WindFarmParams, overrides: dict[str, Any]
) -> WindFarmParams:
    """以 dataclass.replace 套用覆寫；只認 ``WindFarmParams`` 既有欄位以避免亂填。

    對 numeric 欄位做 type coerce（JSON 常把 int 寫成 string）；無效值 raise ValueError，
    避免帶字串繼續跑、計算到一半才爆 TypeError 不好追。
    """
    valid_field_names = {f.name for f in fields(WindFarmParams)}
    safe: dict[str, Any] = {}
    for key, value in overrides.items():
        if key not in valid_field_names:
            continue
        cast = _NUMERIC_FIELD_CASTS.get(key)
        if cast is not None and value is not None:
            try:
                safe[key] = cast(value)
            except (TypeError, ValueError) as e:
                raise ValueError(
                    f"wind_farm_overrides.{key} 無法轉成 {cast.__name__}: {value!r}"
                ) from e
        else:
            safe[key] = value
    return replace(base, **safe)


def _derive_overrides_from_registry(
    farm_id: str, farm_registry: Any = None
) -> dict[str, Any] | None:
    """從 monitoring 的 FarmRegistry 推 minimum wind_farm overrides。

    Returns ``None`` when registry 無法存取 / 找不到此 farm。

    Exception handling 分兩層：
    - ``ImportError`` — monitoring layer 不存在（合理：cost module 可獨立部署）→ silent
    - 其他 Exception — registry init / get_farm 出狀況（DB 權限、corrupt schema...）→
      log warning，避免「明明設定對 farm-specific 卻 silently 退回 K13」debug 不到根因
    """
    reg = farm_registry
    if reg is None:
        try:
            from modules.monitoring.server.farm_registry import FarmRegistry  # type: ignore

            reg = FarmRegistry()
        except ImportError:
            return None
        except Exception as e:
            logger.warning(
                "FarmRegistry 初始化失敗，cost module 將跳過 registry-derived overrides: %s",
                e,
            )
            return None

    try:
        farm = reg.get_farm(farm_id)
    except Exception as e:
        logger.warning("FarmRegistry.get_farm(%r) 失敗：%s", farm_id, e)
        return None
    if farm is None:
        return None

    overrides: dict[str, Any] = {}
    if getattr(farm, "turbine_count", None):
        overrides["nr_turbines"] = farm.turbine_count
    rated = (getattr(farm, "turbine_spec", None) or {}).get("rated_power_kw")
    if rated:
        overrides["capacity_kw"] = float(rated)
    return overrides if overrides else None


def load_engine_params_from_farm(
    farm_id: str,
    stochastic: bool = False,
    farm_registry: Any = None,
    farms_dir: Path | None = None,
    data_dir: Path | None = None,
) -> tuple[EngineParams, FarmDatasetMeta]:
    """載入 farm-aware engine params（K13 baseline + overlay）。

    K13 component / FTC / equipment / PM / fixed_cost / waiting-time polynomial 全沿用，
    僅 ``WindFarmParams`` 級欄位可被 farm-specific 覆寫。

    Args:
        farm_id: 與 monitoring/farm_registry 一致的 farm 識別符。
        stochastic: 同 ``load_k13_engine_params``，給 monte_carlo 用。
        farm_registry: 可選；測試可注入 mock。預設 lazy-import monitoring 的 singleton。
        farms_dir: 覆寫 cost_inputs.json 根目錄（測試用）。
        data_dir: 覆寫 K13 demo 根目錄（測試用）。

    Returns:
        ``(EngineParams, FarmDatasetMeta)`` — meta 透露實際走哪一層 lookup。
    """
    base = load_k13_engine_params(data_dir=data_dir, stochastic=stochastic)

    # Tier 1: explicit cost_inputs.json
    cost_inputs = _load_cost_inputs_json(farm_id, farms_dir=farms_dir)
    if cost_inputs is not None:
        overrides = cost_inputs.get("wind_farm_overrides", {}) or {}
        new_wind_farm = _apply_wind_farm_overrides(base.wind_farm, overrides)
        # 提醒客戶：M3 第一週 overlay 模式僅 scope wind_farm 級參數；component / FTC /
        # equipment 沿用 K13 (offshore reference)，onshore 場合的 logistics / equipment cost
        # 可能高估。第二客戶上線時延伸到 component-level override 解決。
        meta = FarmDatasetMeta(
            dataset_used=f"farm:{farm_id}",
            farm_id=farm_id,
            is_fallback=False,
            source="farm_overlay",
            warning=(
                "Component / FTC / equipment 沿用 K13 (130×4 MW offshore reference)；"
                "若為 onshore 風場，logistics / equipment cost 可能偏高 — 第二階段帶客戶實際 SCADA "
                "fault history 後做 OEM-specific override。"
            ),
        )
        return _replace_wind_farm(base, new_wind_farm), meta

    # Tier 2: derive from FarmRegistry
    derived = _derive_overrides_from_registry(farm_id, farm_registry)
    if derived is not None:
        new_wind_farm = _apply_wind_farm_overrides(base.wind_farm, derived)
        meta = FarmDatasetMeta(
            dataset_used=f"farm:{farm_id}",
            farm_id=farm_id,
            is_fallback=False,
            source="registry_derived",
            warning=(
                f"farm '{farm_id}' 無 cost_inputs.json，"
                "僅從 farm registry 推導 nr_turbines / capacity_kw；其餘沿用 K13"
            ),
        )
        return _replace_wind_farm(base, new_wind_farm), meta

    # Tier 3: pure K13 fallback
    meta = FarmDatasetMeta(
        dataset_used="k13",
        farm_id=farm_id,
        is_fallback=True,
        source="k13_fallback",
        warning=(
            f"找不到 farm '{farm_id}' 的 cost_inputs.json，FarmRegistry 也無此 farm — "
            "已套用 K13 預設"
        ),
    )
    return base, meta


def _replace_wind_farm(params: EngineParams, new_wind_farm: WindFarmParams) -> EngineParams:
    """共用：用新 wind_farm 重組 EngineParams（其他欄位保持 reference 沿用）。"""
    return EngineParams(
        wind_farm=new_wind_farm,
        components=params.components,
        equipment_list=params.equipment_list,
        pm_schedules=params.pm_schedules,
        fixed_costs=params.fixed_costs,
        poly_lookup=params.poly_lookup,
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
