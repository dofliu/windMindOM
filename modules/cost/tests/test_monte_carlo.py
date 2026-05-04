"""Monte Carlo engine K13 equivalence test.

從 ECN/backend/tests/test_monte_carlo.py 移植：
- import path 改 modules.cost.engine.*
- 用 seed=42 確保 reproducibility
- 加 strict pinned equivalence test：deterministic + percentiles + LCOE 全 bit-perfect
- 沿用 ECN 原版的 sanity checks（P10 < P50 < P90、std > 0、CDF monotonic）

Pin baseline 來自 2026-05-04 量測（seed=42, n=100），用 repr() 取
float64 完整精度。
"""

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "demo"


# ─────────────────────────────────────────────────────────────────────────
# Pinned ECN baseline（seed=42, n=100）— 任何 drift 都代表 migration bug
# ─────────────────────────────────────────────────────────────────────────

ECN_PINNED_MC_DETERMINISTIC = {
    "availability_time": 0.9401732630646628,
    "availability_energy": 0.9364235587596128,
    "total_effort": 67964410.8982218,
    "cost_per_kwh": 0.036948752282382154,
}

ECN_PINNED_MC_PERCENTILES = {
    "cost_p10": 64947395.4665548,
    "cost_p50": 67461289.52520475,
    "cost_p90": 70735646.24196146,
    "cost_mean": 67712871.35442477,
    "cost_std": 2174372.8650350347,
    "avail_t_p10": 0.9377404575195472,
    "avail_t_p50": 0.940545717276561,
    "avail_t_p90": 0.9432768175120486,
    "avail_e_p10": 0.9337314435543518,
    "avail_e_p50": 0.9368569461738283,
    "avail_e_p90": 0.9398414878752231,
}

ECN_PINNED_LCOE = {
    "annual_energy_mwh": 1839423.7071607013,
    "lcoe": 72.94042482488679,
    "capex_total": 650000000.0,
    "opex_total_npv": 667284604.6591944,
    "energy_total_npv": 18059733.101660598,
    "total_cost_npv": 1317284604.6591945,
}


# ─────────────────────────────────────────────────────────────────────────
# Constants & loaders（從 -03 cost_cal test 沿用）
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


def build_mc_params():
    """Build parameters with stochastic bounds for Monte Carlo testing."""
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

    gen = _load("k13_general.json")
    ft = _load("k13_fault_types_wt.json")
    eq = _load("k13_equipment.json")
    fc = _load("k13_fixed_costs.json")
    wt = _load("k13_waiting_time_coefficients.json")
    nr2idx = _ww_nr_to_idx()

    t = gen["turbine"]
    wind_farm = WindFarmParams(
        nr_turbines=gen["number_of_turbines"],
        capacity_kw=t["p_rated_kw"],
        investment_cost_per_kw=t["investment_costs_euro_per_kw"],
        kwh_price=gen["kwh_price"],
        lifetime_years=gen["lifetime_years"],
        farm_efficiency=gen["wind_farm_efficiency"],
        capacity_factors=gen["capacity_factors"],
        season_weights=gen["weighing_factors"],
        tech_hourly_rate=0.0,
        tech_yearly_salary=gen["technician_costs"]["yearly_salary"],
        tech_count=gen["technician_costs"]["employed_technicians"],
    )

    # Equipment with stochastic bounds (±20%)
    equipment_list = []
    for e in eq:
        nidx = nr2idx.get(e.get("weather_window_normal")) if e.get("weather_window_normal") else None
        lidx = nr2idx.get(e.get("weather_window_long")) if e.get("weather_window_long") else None
        ct = "mission" if e.get("fixed_cost_freq_type") == 1 else "day"
        fy = e.get("fixed_cost_euro_per_year") or 0
        dr = fy / 365.0 if ct == "day" and fy > 0 else 0.0
        mob = e.get("mob_demob_cost_euro") or 0.0
        equipment_list.append(EquipmentParams(
            equipment_index=e["nr"], name=e["description"],
            ww_normal_index=nidx, ww_long_index=lidx,
            nr_available=e.get("availability_nr") or 1,
            logistic_hours=e.get("logistic_time_hr") or 0.0,
            travel_hours=e.get("travel_time_hr") or 0.0,
            cost_type=ct, day_rate=dr, mob_cost=mob, mission_rate=0.0,
            day_rate_min=dr * 0.8 if dr > 0 else None,
            day_rate_max=dr * 1.2 if dr > 0 else None,
            mob_cost_min=mob * 0.8 if mob > 0 else None,
            mob_cost_max=mob * 1.2 if mob > 0 else None,
        ))

    # Components with stochastic bounds (±30%)
    ftc_lookup = {mc["ftc_nr"]: mc for mc in ft.get("maintenance_categories", [])}
    components = []
    for c in ft["components"]:
        mcs = []
        for sub in c.get("sub_categories", []):
            mci = sub["maintenance_category"]
            fnr = sub["ftc"]
            fdef = ftc_lookup.get(fnr, {})
            fdefault = FTC_DEFAULTS.get(fnr, {})
            rt = "cbm" if fdef.get("type_corr_cbm", 0) == 1 else "corrective"
            rh = fdefault.get("repair_hours", 0)
            ftc = FTCParams(
                ftc_number=fnr, repair_type=rt,
                material_cost_pct=fdef.get("material_cost_pct", 0),
                material_cost_euro=fdef.get("material_cost_euro", 0),
                crew_size=fdef.get("crew_size", 0), repair_hours=rh,
                logistics_hours=0.0, organization_hours=0.0,
                long_working_day=fdefault.get("long_working_day", False),
                repair_hours_min=rh * 0.7 if rh > 0 else None,
                repair_hours_max=rh * 1.3 if rh > 0 else None,
            )
            mcs.append(MCParams(
                category_index=mci, probability=sub["probability"],
                equipment_index=MC_EQUIPMENT.get(mci),
                nr_additional_inspections=sub.get("additional_inspections") or 0,
                ftc=ftc,
            ))
        name = c["name"]
        code = name.split(" - ")[0].strip() if " - " in name else name[:10]
        freq = c["annual_failure_freq"]
        components.append(ComponentParams(
            component_name=name, component_code=code, component_type="WT",
            annual_failure_freq=freq, maintenance_categories=mcs,
            freq_min=freq * 0.7, freq_ml=freq, freq_max=freq * 1.3,
        ))

    pms = []
    for p in fc.get("preventive_maintenance", []):
        ptype = "WT" if p.get("type_wt_bop", 0) == 0 else "BOP"
        wi = nr2idx.get(p.get("weather_window")) if p.get("weather_window") else None
        pms.append(PMParams(
            description=p["description"], pm_type=ptype,
            nr_occurrences=p["occurrences_lifetime"], duration_hours=p["duration_hrs"],
            crew_size=p.get("crew_size", 0), material_cost=p.get("material_costs_euro", 0),
            equipment_index=p.get("equipment_type"), ww_index=wi,
            travel_hours=p.get("travel_time_hr", 0),
            long_working_day=bool(p.get("length_working_day", 0)),
            pct_farm_shutdown=p.get("pct_windfarm_shutdown", 1.0),
            season_distribution=p.get("season_distribution", {}),
        ))

    fixed_costs = []
    for f in fc.get("fixed_yearly_costs", []):
        sd = f.get("season_distribution", {})
        fixed_costs.append(FixedCostParams(
            description=f["description"], annual_cost=f["total_euro"],
            season_distribution={
                "winter": sd.get("winter_pct", 0.25), "spring": sd.get("spring_pct", 0.25),
                "summer": sd.get("summer_pct", 0.25), "autumn": sd.get("autumn_pct", 0.25),
            },
        ))

    poly_lookup = {}
    for season, cl in wt.get("waiting_time", {}).items():
        for cf in cl:
            wi = nr2idx.get(cf["nr"])
            if wi is None:
                continue
            poly_lookup[(wi, season)] = WaitingTimePolynomial(
                window_index=wi, season=season,
                c0=cf.get("c0", 0.0), c1=cf.get("c1", 0.0),
                c2=cf.get("c2", 0.0), c3=cf.get("c3", 0.0),
            )

    return wind_farm, components, equipment_list, pms, fixed_costs, poly_lookup


@pytest.fixture(scope="module")
def mc_result():
    """Run Monte Carlo once with seed=42, n=100，給多個 test 共用。"""
    from modules.cost.engine.monte_carlo import run_monte_carlo

    wf, comps, eqs, pms, fcs, poly = build_mc_params()
    return run_monte_carlo(
        wind_farm=wf, components=comps, equipment_list=eqs,
        pm_schedules=pms, fixed_costs=fcs, poly_lookup=poly,
        n_simulations=100, seed=42,
    )


@pytest.fixture(scope="module")
def percentiles(mc_result):
    """Compute percentiles from MC result。"""
    from modules.cost.engine.monte_carlo import compute_percentiles

    return {
        "cost": compute_percentiles(mc_result.total_costs),
        "avail_t": compute_percentiles(mc_result.availability_time),
        "avail_e": compute_percentiles(mc_result.availability_energy),
    }


# ─────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────


def test_mc_deterministic_pinned(mc_result):
    """Deterministic result（MC 內 reuse cost_cal）必須 bit-perfect 等於 -03 cost_cal pinned。"""
    det = mc_result.deterministic_result
    failures: list[str] = []
    for metric, expected in ECN_PINNED_MC_DETERMINISTIC.items():
        actual = getattr(det, metric)
        if actual != expected:
            failures.append(f"{metric}: actual={actual!r} != expected={expected!r}")
    assert not failures, f"Deterministic drift: {failures}"


def test_mc_percentiles_pinned(mc_result, percentiles):
    """MC percentiles（seed=42, n=100）必須 bit-perfect。任何 drift =
    sampler / runner / numpy random generator 的 numerical bug。"""
    cost = percentiles["cost"]
    at = percentiles["avail_t"]
    ae = percentiles["avail_e"]

    actuals = {
        "cost_p10": cost["p10"], "cost_p50": cost["p50"], "cost_p90": cost["p90"],
        "cost_mean": cost["mean"], "cost_std": cost["std"],
        "avail_t_p10": at["p10"], "avail_t_p50": at["p50"], "avail_t_p90": at["p90"],
        "avail_e_p10": ae["p10"], "avail_e_p50": ae["p50"], "avail_e_p90": ae["p90"],
    }
    failures: list[str] = []
    for k, expected in ECN_PINNED_MC_PERCENTILES.items():
        actual = actuals[k]
        if actual != expected:
            failures.append(f"{k}: actual={actual!r} != expected={expected!r}")
    assert not failures, f"Percentile drift: {failures}"


def test_mc_lcoe_pinned(mc_result):
    """LCOE 計算必須 bit-perfect == ECN baseline (72.94 EUR/MWh)。"""
    from modules.cost.engine.cost_cal.lcoe import calculate_lcoe
    from modules.cost.engine.cost_cal.revenue_loss import annual_energy_production_mwh

    wf, _, _, _, _, _ = build_mc_params()
    annual_energy = annual_energy_production_mwh(wf)
    lcoe = calculate_lcoe(
        capex_per_kw=1250.0, capacity_kw=wf.capacity_kw,
        nr_turbines=wf.nr_turbines, lifetime=wf.lifetime_years,
        discount_rate=0.08, annual_opex=mc_result.deterministic_result.total_effort,
        annual_energy_mwh=annual_energy,
    )

    actuals = {
        "annual_energy_mwh": annual_energy,
        "lcoe": lcoe.lcoe,
        "capex_total": lcoe.capex_total,
        "opex_total_npv": lcoe.opex_total_npv,
        "energy_total_npv": lcoe.energy_total_npv,
        "total_cost_npv": lcoe.total_cost_npv,
    }
    failures: list[str] = []
    for k, expected in ECN_PINNED_LCOE.items():
        actual = actuals[k]
        if actual != expected:
            failures.append(f"{k}: actual={actual!r} != expected={expected!r}")
    assert not failures, f"LCOE drift: {failures}"


def test_mc_sanity_checks(mc_result, percentiles):
    """ECN 原版 sanity checks — P10 < P50 < P90、std > 0、CDF monotonic。"""
    from modules.cost.engine.monte_carlo import compute_cdf

    cost = percentiles["cost"]
    at = percentiles["avail_t"]
    ae = percentiles["avail_e"]
    det = mc_result.deterministic_result

    # P10 < P50 < P90
    assert cost["p10"] < cost["p50"] < cost["p90"], (
        f"Cost percentile order: {cost['p10']} < {cost['p50']} < {cost['p90']}"
    )
    assert at["p10"] < at["p50"] < at["p90"], "Avail-time percentile order"
    assert ae["p10"] < ae["p50"] < ae["p90"], "Avail-energy percentile order"

    # P50 close to deterministic (< 20% error)
    p50_error = abs(cost["p50"] - det.total_effort) / det.total_effort * 100
    assert p50_error < 20, f"P50 vs deterministic error {p50_error:.1f}% >= 20%"

    # Non-zero std
    assert cost["std"] > 0, "Cost std must be > 0 (stochastic variation present)"

    # CDF monotonic
    cdf_x, cdf_y = compute_cdf(mc_result.total_costs)
    assert all(cdf_y[i] <= cdf_y[i + 1] for i in range(len(cdf_y) - 1)), (
        "CDF must be monotonically non-decreasing"
    )


def test_mc_tornado(mc_result):
    """Tornado sensitivity 有 bars 且按 cost_range 排序。"""
    from modules.cost.engine.monte_carlo import compute_tornado

    wf, comps, eqs, pms, fcs, poly = build_mc_params()
    bars = compute_tornado(
        base_cost=mc_result.deterministic_result.total_effort,
        wind_farm=wf, components=comps, equipment_list=eqs,
        pm_schedules=pms, fixed_costs=fcs, poly_lookup=poly,
    )
    assert len(bars) > 0, "Tornado must produce at least one bar"
    # 排序：cost_range 由大到小
    for i in range(len(bars) - 1):
        assert bars[i].cost_range >= bars[i + 1].cost_range, (
            f"Tornado bars not sorted at index {i}: "
            f"{bars[i].cost_range} < {bars[i + 1].cost_range}"
        )
