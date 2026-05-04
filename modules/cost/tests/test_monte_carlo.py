"""Monte Carlo engine K13 equivalence test.

從 ECN/backend/tests/test_monte_carlo.py 移植：
- import path 改 modules.cost.engine.*
- 用 seed=42 確保 reproducibility
- 加 strict pinned equivalence test：deterministic + percentiles + LCOE 全 bit-perfect
- 沿用 ECN 原版的 sanity checks（P10 < P50 < P90、std > 0、CDF monotonic）

Pin baseline 來自 2026-05-04 量測（seed=42, n=100），用 repr() 取
float64 完整精度。
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.cost.adapter import load_k13_engine_params  # noqa: E402


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


@pytest.fixture(scope="module")
def mc_params():
    """Load K13 with stochastic bounds (給 monte_carlo 用)。"""
    return load_k13_engine_params(stochastic=True)


@pytest.fixture(scope="module")
def mc_result(mc_params):
    """Run Monte Carlo once with seed=42, n=100，給多個 test 共用。"""
    from modules.cost.engine.monte_carlo import run_monte_carlo

    return run_monte_carlo(
        wind_farm=mc_params.wind_farm, components=mc_params.components,
        equipment_list=mc_params.equipment_list, pm_schedules=mc_params.pm_schedules,
        fixed_costs=mc_params.fixed_costs, poly_lookup=mc_params.poly_lookup,
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


def test_mc_lcoe_pinned(mc_result, mc_params):
    """LCOE 計算必須 bit-perfect == ECN baseline (72.94 EUR/MWh)。"""
    from modules.cost.engine.cost_cal.lcoe import calculate_lcoe
    from modules.cost.engine.cost_cal.revenue_loss import annual_energy_production_mwh

    wf = mc_params.wind_farm
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


def test_mc_tornado(mc_result, mc_params):
    """Tornado sensitivity 有 bars 且按 cost_range 排序。"""
    from modules.cost.engine.monte_carlo import compute_tornado

    bars = compute_tornado(
        base_cost=mc_result.deterministic_result.total_effort,
        wind_farm=mc_params.wind_farm, components=mc_params.components,
        equipment_list=mc_params.equipment_list, pm_schedules=mc_params.pm_schedules,
        fixed_costs=mc_params.fixed_costs, poly_lookup=mc_params.poly_lookup,
    )
    assert len(bars) > 0, "Tornado must produce at least one bar"
    # 排序：cost_range 由大到小
    for i in range(len(bars) - 1):
        assert bars[i].cost_range >= bars[i + 1].cost_range, (
            f"Tornado bars not sorted at index {i}: "
            f"{bars[i].cost_range} < {bars[i + 1].cost_range}"
        )
