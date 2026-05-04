"""var_fluct engine K13 test (新建 — ECN 沒有對應 unit test)。

涵蓋：
1. **Bathtub curve** — 20 年完整曲線 + 邊界 case bit-perfect
2. **K13 var_fluct calculation** — Year 1 (early peak)、Year 10 (mid)、Year 20 (late peak)
   完整 YearResult + Summary 全 bit-perfect

Pin baseline 來自 2026-05-04 量測，用 repr() 取 float64 完整精度（engine 內部
有 round 過：multiplier/escalation/cap_deg 4 位、summary 2 位）。
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.cost.adapter import load_k13_engine_params  # noqa: E402


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


@pytest.fixture(scope="module")
def vf_result():
    """Run var_fluct K13 once，給多個 test 共用。"""
    from modules.cost.engine.var_fluct import run_var_fluct_calculation
    from modules.cost.engine.var_fluct.calculator import VarFluctConfig

    p = load_k13_engine_params(stochastic=False)
    config = VarFluctConfig()  # all defaults
    return run_var_fluct_calculation(
        wind_farm=p.wind_farm, components=p.components,
        equipment_list=p.equipment_list, pm_schedules=p.pm_schedules,
        fixed_costs=p.fixed_costs, poly_lookup=p.poly_lookup,
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
