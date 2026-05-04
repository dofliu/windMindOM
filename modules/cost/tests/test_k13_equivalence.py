"""K13 equivalence test for cost_cal engine.

從 ECN/backend/tests/test_cost_cal_engine.py 移植：
- import path 改為 modules.cost.engine.*
- DATA_DIR 改為 modules/cost/data/demo/
- 加 strict pinned equivalence test（windMindOM 必須 bit-perfect == ECN）

驗證策略：
1. **Migration correctness（最重要）** — `test_k13_migration_equivalence_pinned`
   把 ECN engine 在 K13 上的實際輸出（top-level 6 metrics + 4 季 5 cost
   subcategories）hardcode 進來，windMindOM engine 必須 bit-perfect 一致
   （float 直接 ==）
2. **K13 reference 比對（diagnostic）** — `test_k13_cost_calculation` 沿用 ECN 原版
   tolerance check（5-30%），數字接近 ECN V5 reference 即可

Tolerances 與 ECN 原版一致；數字偏差說明見 docs/legacy/ecn_k13_baseline.md §2.1。
"""

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "demo"


# ─────────────────────────────────────────────────────────────────────────
# Constants — 從 ECN test 沿用
# ─────────────────────────────────────────────────────────────────────────

FTC_DEFAULTS = {
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
MC_EQUIPMENT = {1: None, 2: 1, 3: 1, 4: 1, 5: 1, 6: 4}
FTC_EQUIPMENT_OVERRIDE: dict[int, int] = {}


# ─────────────────────────────────────────────────────────────────────────
# Pinned ECN baseline (2026-05-04，用 repr() 取 float64 完整精度)
# 任何 windMindOM drift 都代表 migration 引入了 numerical bug
# ─────────────────────────────────────────────────────────────────────────

ECN_PINNED_K13 = {
    "availability_time": 0.9401732630646628,
    "availability_energy": 0.9364235587596128,
    "total_revenue_loss": 15202721.720482074,
    "total_repair_cost": 52761689.17773973,
    "total_effort": 67964410.8982218,
    "cost_per_kwh": 0.036948752282382154,
}

ECN_PINNED_K13_SEASONAL = {
    "winter": {
        "corrective_wt_material": 3129581.8937500003,
        "corrective_wt_equipment": 3269378.191780823,
        "corrective_wt_revenue_loss": 6367752.467871219,
        "preventive_material": 0.0,
        "fixed_cost": 5550000.0,
    },
    "spring": {
        "corrective_wt_material": 3129581.8937500003,
        "corrective_wt_equipment": 1297513.9726027397,
        "corrective_wt_revenue_loss": 1929932.1324677265,
        "preventive_material": 572075.0,
        "fixed_cost": 5175000.0,
    },
    "summer": {
        "corrective_wt_material": 3129581.8937500003,
        "corrective_wt_equipment": 878499.7534246575,
        "corrective_wt_revenue_loss": 1074113.5352917863,
        "preventive_material": 898975.0,
        "fixed_cost": 5175000.0,
    },
    "autumn": {
        "corrective_wt_material": 3129581.8937500003,
        "corrective_wt_equipment": 2222792.356164384,
        "corrective_wt_revenue_loss": 4015762.8459275244,
        "preventive_material": 163450.0,
        "fixed_cost": 5475000.0,
    },
}


# ─────────────────────────────────────────────────────────────────────────
# Loaders + builders
# ─────────────────────────────────────────────────────────────────────────


def _load(name: str) -> dict | list:
    with open(DATA_DIR / name) as f:
        return json.load(f)


def _ww_nr_to_idx() -> dict[int, int]:
    ww_data = _load("k13_weather_windows.json")
    mapping: dict[int, int] = {}
    for idx, ww_def in enumerate(ww_data["definition_sheet"]):
        nr = ww_def["window_nr"]
        if nr not in mapping:
            mapping[nr] = idx
    return mapping


def build_all_params():
    """Build all parameters needed for run_cost_calculation()."""
    from modules.cost.engine.cost_cal.data_classes import (
        ComponentParams,
        EquipmentParams,
        FixedCostParams,
        FTCParams,
        MCParams,
        PMParams,
        WaitingTimePolynomial,
        WindFarmParams,
    )

    gen_data = _load("k13_general.json")
    ft_data = _load("k13_fault_types_wt.json")
    eq_data = _load("k13_equipment.json")
    fc_data = _load("k13_fixed_costs.json")
    wt_coeffs = _load("k13_waiting_time_coefficients.json")
    nr2idx = _ww_nr_to_idx()

    # Wind farm
    turbine = gen_data["turbine"]
    wind_farm = WindFarmParams(
        nr_turbines=gen_data["number_of_turbines"],
        capacity_kw=turbine["p_rated_kw"],
        investment_cost_per_kw=turbine["investment_costs_euro_per_kw"],
        kwh_price=gen_data["kwh_price"],
        lifetime_years=gen_data["lifetime_years"],
        farm_efficiency=gen_data["wind_farm_efficiency"],
        capacity_factors=gen_data["capacity_factors"],
        season_weights=gen_data["weighing_factors"],
        tech_hourly_rate=0.0,
        tech_yearly_salary=gen_data["technician_costs"]["yearly_salary"],
        tech_count=gen_data["technician_costs"]["employed_technicians"],
    )

    # Components
    ftc_lookup = {mc["ftc_nr"]: mc for mc in ft_data.get("maintenance_categories", [])}
    components: list[ComponentParams] = []
    for comp_data in ft_data["components"]:
        mc_params: list[MCParams] = []
        for sub in comp_data.get("sub_categories", []):
            mc_index = sub["maintenance_category"]
            ftc_nr = sub["ftc"]
            ftc_def = ftc_lookup.get(ftc_nr, {})
            ftc_defaults = FTC_DEFAULTS.get(ftc_nr, {})
            repair_type = "cbm" if ftc_def.get("type_corr_cbm", 0) == 1 else "corrective"
            ftc = FTCParams(
                ftc_number=ftc_nr,
                repair_type=repair_type,
                material_cost_pct=ftc_def.get("material_cost_pct", 0),
                material_cost_euro=ftc_def.get("material_cost_euro", 0),
                crew_size=ftc_def.get("crew_size", 0),
                repair_hours=ftc_defaults.get("repair_hours", 0),
                logistics_hours=0.0,
                organization_hours=0.0,
                long_working_day=ftc_defaults.get("long_working_day", False),
            )
            equip_index = FTC_EQUIPMENT_OVERRIDE.get(ftc_nr, MC_EQUIPMENT.get(mc_index))
            mc_params.append(
                MCParams(
                    category_index=mc_index,
                    probability=sub["probability"],
                    equipment_index=equip_index,
                    nr_additional_inspections=sub.get("additional_inspections") or 0,
                    ftc=ftc,
                )
            )
        name = comp_data["name"]
        code = name.split(" - ")[0].strip() if " - " in name else name[:10]
        components.append(
            ComponentParams(
                component_name=name,
                component_code=code,
                component_type="WT",
                annual_failure_freq=comp_data["annual_failure_freq"],
                maintenance_categories=mc_params,
            )
        )

    # Equipment
    equipment_list: list[EquipmentParams] = []
    for eq in eq_data:
        ww_normal_idx = nr2idx.get(eq.get("weather_window_normal")) if eq.get("weather_window_normal") else None
        ww_long_idx = nr2idx.get(eq.get("weather_window_long")) if eq.get("weather_window_long") else None
        cost_type = "mission" if eq.get("fixed_cost_freq_type") == 1 else "day"
        fixed_cost_year = eq.get("fixed_cost_euro_per_year") or 0
        day_rate = fixed_cost_year / 365.0 if cost_type == "day" and fixed_cost_year > 0 else 0.0
        equipment_list.append(
            EquipmentParams(
                equipment_index=eq["nr"],
                name=eq["description"],
                ww_normal_index=ww_normal_idx,
                ww_long_index=ww_long_idx,
                nr_available=eq.get("availability_nr") or 1,
                logistic_hours=eq.get("logistic_time_hr") or 0.0,
                travel_hours=eq.get("travel_time_hr") or 0.0,
                cost_type=cost_type,
                day_rate=day_rate,
                mob_cost=eq.get("mob_demob_cost_euro") or 0.0,
                mission_rate=0.0,
            )
        )

    # PM schedules
    pm_schedules: list[PMParams] = []
    for pm_data in fc_data.get("preventive_maintenance", []):
        pm_type = "WT" if pm_data.get("type_wt_bop", 0) == 0 else "BOP"
        ww_idx = nr2idx.get(pm_data.get("weather_window")) if pm_data.get("weather_window") else None
        pm_schedules.append(
            PMParams(
                description=pm_data["description"],
                pm_type=pm_type,
                nr_occurrences=pm_data["occurrences_lifetime"],
                duration_hours=pm_data["duration_hrs"],
                crew_size=pm_data.get("crew_size", 0),
                material_cost=pm_data.get("material_costs_euro", 0),
                equipment_index=pm_data.get("equipment_type"),
                ww_index=ww_idx,
                travel_hours=pm_data.get("travel_time_hr", 0),
                long_working_day=bool(pm_data.get("length_working_day", 0)),
                pct_farm_shutdown=pm_data.get("pct_windfarm_shutdown", 1.0),
                season_distribution=pm_data.get("season_distribution", {}),
            )
        )

    # Fixed costs
    fixed_costs: list[FixedCostParams] = []
    for fc in fc_data.get("fixed_yearly_costs", []):
        sd = fc.get("season_distribution", {})
        fixed_costs.append(
            FixedCostParams(
                description=fc["description"],
                annual_cost=fc["total_euro"],
                season_distribution={
                    "winter": sd.get("winter_pct", 0.25),
                    "spring": sd.get("spring_pct", 0.25),
                    "summer": sd.get("summer_pct", 0.25),
                    "autumn": sd.get("autumn_pct", 0.25),
                },
            )
        )

    # Polynomial lookup
    poly_lookup: dict[tuple[int, str], WaitingTimePolynomial] = {}
    for season, coeffs_list in wt_coeffs.get("waiting_time", {}).items():
        for coeff in coeffs_list:
            ww_idx = nr2idx.get(coeff["nr"])
            if ww_idx is None:
                continue
            poly_lookup[(ww_idx, season)] = WaitingTimePolynomial(
                window_index=ww_idx,
                season=season,
                c0=coeff.get("c0", 0.0),
                c1=coeff.get("c1", 0.0),
                c2=coeff.get("c2", 0.0),
                c3=coeff.get("c3", 0.0),
            )

    return wind_farm, components, equipment_list, pm_schedules, fixed_costs, poly_lookup


@pytest.fixture(scope="module")
def k13_result():
    """Run cost calculation once，給多個 test 共用結果。"""
    from modules.cost.engine.cost_cal import run_cost_calculation

    wind_farm, components, equipment_list, pm_schedules, fixed_costs, poly_lookup = build_all_params()
    return run_cost_calculation(
        wind_farm=wind_farm,
        components=components,
        equipment_list=equipment_list,
        pm_schedules=pm_schedules,
        fixed_costs=fixed_costs,
        poly_lookup=poly_lookup,
    )


# ─────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────


def test_k13_migration_equivalence_pinned(k13_result):
    """Migration gate — windMindOM 必須 bit-perfect 等於 ECN 在 K13 上的輸出。"""
    print("\nTOP-LEVEL METRICS (windMindOM vs ECN pinned):")
    failures: list[str] = []
    for metric, expected in ECN_PINNED_K13.items():
        actual = getattr(k13_result, metric)
        status = "OK" if actual == expected else "DRIFT"
        print(f"  {metric:<24} actual={actual!r}  expected={expected!r}  {status}")
        if actual != expected:
            failures.append(f"{metric}: actual={actual!r} != expected={expected!r}")

    assert not failures, f"Top-level metric drift: {failures}"


def test_k13_migration_equivalence_seasonal(k13_result):
    """Seasonal breakdown — 4 季 × 5 cost subcategories 全部 bit-perfect。"""
    print("\nSEASONAL BREAKDOWN (windMindOM vs ECN pinned):")
    failures: list[str] = []
    for season, expected_dict in ECN_PINNED_K13_SEASONAL.items():
        sr = k13_result.seasonal_results[season]
        for field, expected in expected_dict.items():
            actual = getattr(sr, field)
            if actual != expected:
                failures.append(
                    f"{season}.{field}: actual={actual!r} != expected={expected!r}"
                )

    if failures:
        for f in failures:
            print(f"  DRIFT: {f}")
    else:
        print("  All 4 seasons × 5 fields bit-perfect")
    assert not failures, f"Seasonal drift: {failures}"


def test_k13_cost_calculation(k13_result):
    """ECN reference value 比對 — tolerance 與 ECN 原版一致（5-30%）。

    Reference values from ECN O&M Tool V5 OverviewResults。Tolerance 容
    ECN Excel ↔ Python port 之間 methodology 差異（revenue loss weighting、
    seasonal CF averaging、equipment cost calc 細節）。
    """
    failures: list[str] = []

    def check(name: str, actual: float, expected: float, tolerance_pct: float):
        error_pct = abs(actual - expected) / expected * 100 if expected else 0.0
        ok = error_pct <= tolerance_pct
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}: {actual:.2f} vs {expected:.2f} (err {error_pct:.1f}% / tol {tolerance_pct}%)")
        if not ok:
            failures.append(f"{name}: {actual} vs {expected} (err {error_pct:.1f}% > tol {tolerance_pct}%)")

    print("\nECN V5 REFERENCE COMPARISON:")
    check("Availability (time) %",  k13_result.availability_time * 100,  92.6, 5)
    check("Availability (energy) %", k13_result.availability_energy * 100, 92.1, 5)
    check("Revenue losses (M EUR)",  k13_result.total_revenue_loss / 1e6,  21.1, 30)
    check("Repair costs (M EUR)",    k13_result.total_repair_cost / 1e6,   51.1, 15)
    check("Total effort (M EUR)",    k13_result.total_effort / 1e6,        72.2, 15)

    assert not failures, f"ECN reference comparison failures: {failures}"
