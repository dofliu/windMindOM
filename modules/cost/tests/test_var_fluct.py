"""var_fluct engine K13 test (新建 — ECN 沒有對應 unit test)。

涵蓋：
1. **Bathtub curve** — 20 年完整曲線 + 邊界 case bit-perfect
2. **K13 var_fluct calculation** — Year 1 (early peak)、Year 10 (mid)、Year 20 (late peak)
   完整 YearResult + Summary 全 bit-perfect

Pin baseline 來自 2026-05-04 量測，用 repr() 取 float64 完整精度（engine 內部
有 round 過：multiplier/escalation/cap_deg 4 位、summary 2 位）。
"""

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "demo"


# ─────────────────────────────────────────────────────────────────────────
# Pinned ECN baseline（2026-05-04 量測）
# ─────────────────────────────────────────────────────────────────────────

ECN_PINNED_BATHTUB_DEFAULT_CURVE = [
    (1, 1.5),
    (2, 1.1857492861421186),
    (3, 1.0),
    (4, 1.0),
    (5, 1.0),
    (6, 1.0),
    (7, 1.0),
    (8, 1.0),
    (9, 1.0),
    (10, 1.0),
    (11, 1.0),
    (12, 1.0),
    (13, 1.0),
    (14, 1.0),
    (15, 1.0),
    (16, 1.0894427190999916),
    (17, 1.2529822128134704),
    (18, 1.46475800154489),
    (19, 1.7155417527999328),
    (20, 2.0),
]

ECN_PINNED_BATHTUB_EDGES = {
    "year_0": 1.0,
    "year_1_early_peak": 1.5,
    "year_3_post_early": 1.0,
    "year_10_midlife": 1.0,
    "year_15_late_start": 1.0,
    "year_20_late_peak": 2.0,
}

ECN_PINNED_VARFLUCT_YEAR_1 = {
    "year": 1,
    "failure_multiplier": 1.5,
    "cost_escalation_factor": 1.0,
    "kwh_price": 0.13,
    "capacity_factor_multiplier": 1.0,
    "corrective_wt": 41215465.27345891,
    "corrective_bop": 0.0,
    "preventive": 3909712.328767123,
    "fixed": 21375000.0,
    "revenue_loss": 21896502.2112612,
    "total_repair_cost": 66500177.602226034,
    "total_effort": 88396679.81348723,
    "availability_time": 0.9147734906788411,
    "availability_energy": 0.9084307591890781,
}

ECN_PINNED_VARFLUCT_YEAR_10 = {
    "year": 10,
    "failure_multiplier": 1.0,
    "cost_escalation_factor": 1.1951,
    "kwh_price": 0.13,
    "capacity_factor_multiplier": 0.9559,
    "total_effort": 75144993.21809363,
    "availability_time": 0.9401732630646628,  # mid-life = same as -03 cost_cal baseline
    "availability_energy": 0.9364235587596128,
}

ECN_PINNED_VARFLUCT_YEAR_20 = {
    "year": 20,
    "failure_multiplier": 2.0,
    "cost_escalation_factor": 1.4568,
    "kwh_price": 0.13,
    "capacity_factor_multiplier": 0.9092,
    "total_effort": 131448595.88017026,
    "availability_time": 0.8893737182930194,
    "availability_energy": 0.8804379596185434,
}

ECN_PINNED_VARFLUCT_SUMMARY = {
    "npv_total_effort": 776626181.4,
    "npv_total_repair": 616925753.85,
    "npv_total_revenue_loss": 159700427.55,
    "avg_annual_effort": 83127041.13,
    "min_year_effort": 69438595.56,
    "max_year_effort": 131448595.88,
    "min_year_index": 3,
    "max_year_index": 20,
    "lifetime_availability_time": 0.932024,
    "lifetime_availability_energy": 0.927442,
}


# ─────────────────────────────────────────────────────────────────────────
# K13 builders（從 -03 cost_cal test 沿用）
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


def build_k13_params():
    """Build standard K13 parameters (no stochastic bounds — var_fluct doesn't sample)."""
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
        nr_turbines=gen["number_of_turbines"], capacity_kw=t["p_rated_kw"],
        investment_cost_per_kw=t["investment_costs_euro_per_kw"],
        kwh_price=gen["kwh_price"], lifetime_years=gen["lifetime_years"],
        farm_efficiency=gen["wind_farm_efficiency"],
        capacity_factors=gen["capacity_factors"], season_weights=gen["weighing_factors"],
        tech_hourly_rate=0.0, tech_yearly_salary=gen["technician_costs"]["yearly_salary"],
        tech_count=gen["technician_costs"]["employed_technicians"],
    )

    equipment_list = []
    for e in eq:
        nidx = nr2idx.get(e.get("weather_window_normal")) if e.get("weather_window_normal") else None
        lidx = nr2idx.get(e.get("weather_window_long")) if e.get("weather_window_long") else None
        ct = "mission" if e.get("fixed_cost_freq_type") == 1 else "day"
        fy = e.get("fixed_cost_euro_per_year") or 0
        dr = fy / 365.0 if ct == "day" and fy > 0 else 0.0
        equipment_list.append(EquipmentParams(
            equipment_index=e["nr"], name=e["description"],
            ww_normal_index=nidx, ww_long_index=lidx,
            nr_available=e.get("availability_nr") or 1,
            logistic_hours=e.get("logistic_time_hr") or 0.0,
            travel_hours=e.get("travel_time_hr") or 0.0,
            cost_type=ct, day_rate=dr,
            mob_cost=e.get("mob_demob_cost_euro") or 0.0, mission_rate=0.0,
        ))

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
            ftc = FTCParams(
                ftc_number=fnr, repair_type=rt,
                material_cost_pct=fdef.get("material_cost_pct", 0),
                material_cost_euro=fdef.get("material_cost_euro", 0),
                crew_size=fdef.get("crew_size", 0),
                repair_hours=fdefault.get("repair_hours", 0),
                logistics_hours=0.0, organization_hours=0.0,
                long_working_day=fdefault.get("long_working_day", False),
            )
            mcs.append(MCParams(
                category_index=mci, probability=sub["probability"],
                equipment_index=MC_EQUIPMENT.get(mci),
                nr_additional_inspections=sub.get("additional_inspections") or 0,
                ftc=ftc,
            ))
        name = c["name"]
        code = name.split(" - ")[0].strip() if " - " in name else name[:10]
        components.append(ComponentParams(
            component_name=name, component_code=code, component_type="WT",
            annual_failure_freq=c["annual_failure_freq"],
            maintenance_categories=mcs,
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
def vf_result():
    """Run var_fluct K13 once，給多個 test 共用。"""
    from modules.cost.engine.var_fluct import run_var_fluct_calculation
    from modules.cost.engine.var_fluct.calculator import VarFluctConfig

    wf, comps, eqs, pms, fcs, poly = build_k13_params()
    config = VarFluctConfig()  # all defaults
    return run_var_fluct_calculation(
        wind_farm=wf, components=comps, equipment_list=eqs,
        pm_schedules=pms, fixed_costs=fcs, poly_lookup=poly,
        config=config,
    )


# ─────────────────────────────────────────────────────────────────────────
# Bathtub tests
# ─────────────────────────────────────────────────────────────────────────


def test_bathtub_default_curve():
    """Default bathtub curve (20-year) bit-perfect 等於 ECN baseline。"""
    from modules.cost.engine.var_fluct.bathtub import BathtubParams, bathtub_multiplier

    params = BathtubParams()  # all defaults
    failures: list[str] = []
    for year, expected in ECN_PINNED_BATHTUB_DEFAULT_CURVE:
        actual = bathtub_multiplier(year, params)
        if actual != expected:
            failures.append(f"year {year}: actual={actual!r} != expected={expected!r}")
    assert not failures, f"Bathtub curve drift: {failures}"


def test_bathtub_edges():
    """Bathtub edge cases — year 0 (return 1.0), early peak, late peak。"""
    from modules.cost.engine.var_fluct.bathtub import BathtubParams, bathtub_multiplier

    params = BathtubParams()
    actuals = {
        "year_0": bathtub_multiplier(0, params),
        "year_1_early_peak": bathtub_multiplier(1, params),
        "year_3_post_early": bathtub_multiplier(3, params),
        "year_10_midlife": bathtub_multiplier(10, params),
        "year_15_late_start": bathtub_multiplier(15, params),
        "year_20_late_peak": bathtub_multiplier(20, params),
    }
    failures: list[str] = []
    for k, expected in ECN_PINNED_BATHTUB_EDGES.items():
        actual = actuals[k]
        if actual != expected:
            failures.append(f"{k}: actual={actual!r} != expected={expected!r}")
    assert not failures, f"Bathtub edge drift: {failures}"


def test_bathtub_curve_helper():
    """compute_bathtub_curve() 回傳 list of dicts，與單獨 call multiplier 一致。"""
    from modules.cost.engine.var_fluct.bathtub import (
        BathtubParams,
        bathtub_multiplier,
        compute_bathtub_curve,
    )

    params = BathtubParams()
    curve = compute_bathtub_curve(params)
    assert len(curve) == params.lifetime, f"Curve length {len(curve)} != {params.lifetime}"
    # compute_bathtub_curve rounds to 4 decimals; bathtub_multiplier doesn't
    for entry in curve:
        year = entry["year"]
        rounded = round(bathtub_multiplier(year, params), 4)
        assert entry["multiplier"] == rounded, (
            f"Year {year}: curve {entry['multiplier']} != round(multiplier, 4) {rounded}"
        )


# ─────────────────────────────────────────────────────────────────────────
# K13 var_fluct tests
# ─────────────────────────────────────────────────────────────────────────


def test_varfluct_lifetime_length(vf_result):
    """Lifetime = 20 years，yearly result 必須有 20 個 entry。"""
    assert len(vf_result.yearly) == 20, f"Got {len(vf_result.yearly)} years, expected 20"


def test_varfluct_year_1_pinned(vf_result):
    """Year 1 (early life peak, multiplier=1.5) — 完整 14 個欄位 bit-perfect。"""
    y1 = vf_result.yearly[0]
    failures: list[str] = []
    for field, expected in ECN_PINNED_VARFLUCT_YEAR_1.items():
        actual = getattr(y1, field)
        if actual != expected:
            failures.append(f"{field}: actual={actual!r} != expected={expected!r}")
    assert not failures, f"Year 1 drift: {failures}"


def test_varfluct_year_10_pinned(vf_result):
    """Year 10 (mid-life, multiplier=1.0) — availability 應同 -03 cost_cal baseline。"""
    y10 = vf_result.yearly[9]
    failures: list[str] = []
    for field, expected in ECN_PINNED_VARFLUCT_YEAR_10.items():
        actual = getattr(y10, field)
        if actual != expected:
            failures.append(f"{field}: actual={actual!r} != expected={expected!r}")
    assert not failures, f"Year 10 drift: {failures}"


def test_varfluct_year_20_pinned(vf_result):
    """Year 20 (late life peak, multiplier=2.0) — total_effort 比年 1 高 ~50%。"""
    y20 = vf_result.yearly[19]
    failures: list[str] = []
    for field, expected in ECN_PINNED_VARFLUCT_YEAR_20.items():
        actual = getattr(y20, field)
        if actual != expected:
            failures.append(f"{field}: actual={actual!r} != expected={expected!r}")
    assert not failures, f"Year 20 drift: {failures}"


def test_varfluct_summary_pinned(vf_result):
    """Summary（NPV + min/max + lifetime availability）全 bit-perfect。"""
    failures: list[str] = []
    for field, expected in ECN_PINNED_VARFLUCT_SUMMARY.items():
        actual = getattr(vf_result.summary, field)
        if actual != expected:
            failures.append(f"{field}: actual={actual!r} != expected={expected!r}")
    assert not failures, f"Summary drift: {failures}"


def test_varfluct_year_index_consistency(vf_result):
    """yearly[i].year == i+1 (1-based)。"""
    for i, yr in enumerate(vf_result.yearly):
        assert yr.year == i + 1, f"Index mismatch at position {i}: yr.year={yr.year}"
