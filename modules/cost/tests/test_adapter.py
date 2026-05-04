"""Adapter test — K13 loader + result→response 雙向轉換 + pydantic round-trip。

測試重點：
1. K13 loader 載入正確（counts + key 數字）
2. stochastic=False vs True 的差異（前者無 bound、後者有）
3. cost_result_to_response → CostForecastResponse pydantic 接受
4. mc_result_to_response → MonteCarloResponse pydantic 接受
5. vf_result_to_response → VarFluctResponse pydantic 接受
6. lcoe_result_to_response → LCOEResponse pydantic 接受
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.cost.adapter import (  # noqa: E402
    EngineParams,
    cost_result_to_response,
    lcoe_result_to_response,
    load_k13_engine_params,
    mc_result_to_response,
    vf_result_to_response,
)
from modules.cost.schemas.cost_schemas import (  # noqa: E402
    CostForecastResponse,
    LCOEResponse,
    MonteCarloResponse,
    VarFluctResponse,
)


# ─────────────────────────────────────────────────────────────────────────
# K13 loader tests
# ─────────────────────────────────────────────────────────────────────────


def test_load_k13_returns_engine_params():
    """K13 loader 回傳 EngineParams 容器，6 個欄位都有東西。"""
    p = load_k13_engine_params()
    assert isinstance(p, EngineParams)
    assert p.wind_farm.nr_turbines == 130
    assert p.wind_farm.capacity_kw == 4000  # K13 turbine: 4 MW per unit
    assert p.wind_farm.lifetime_years == 20
    assert len(p.components) == 18
    assert len(p.equipment_list) == 9
    assert len(p.pm_schedules) > 0
    assert len(p.fixed_costs) > 0
    assert len(p.poly_lookup) > 0


def test_load_k13_no_stochastic_bounds_by_default():
    """stochastic=False（預設）不應該有 freq_min / day_rate_min 等 stochastic 欄位。"""
    p = load_k13_engine_params(stochastic=False)
    for comp in p.components:
        assert comp.freq_min is None
        assert comp.freq_max is None
    for eq in p.equipment_list:
        assert eq.day_rate_min is None
        assert eq.mob_cost_min is None


def test_load_k13_with_stochastic_bounds():
    """stochastic=True 應該有 ±20%/±30% bounds。"""
    p = load_k13_engine_params(stochastic=True)
    # 至少有一個 component 帶 freq_min（freq > 0 的）
    has_freq_bound = any(
        c.freq_min is not None and c.freq_min > 0 for c in p.components
    )
    assert has_freq_bound, "Stochastic mode should set freq bounds on components with freq>0"
    # 至少有一個 equipment 帶 day_rate_min（day_rate > 0 的）
    has_dr_bound = any(
        e.day_rate_min is not None and e.day_rate_min > 0 for e in p.equipment_list
    )
    assert has_dr_bound, "Stochastic mode should set day_rate bounds on eq with rate>0"


def test_load_k13_bounds_correctness():
    """Stochastic bound 應符合預設比例（component ±30%、equipment ±20%）。"""
    p = load_k13_engine_params(stochastic=True)
    for comp in p.components:
        if comp.freq_min is not None:
            assert comp.freq_min == pytest.approx(comp.annual_failure_freq * 0.7)
            assert comp.freq_max == pytest.approx(comp.annual_failure_freq * 1.3)
    for eq in p.equipment_list:
        if eq.day_rate_min is not None and eq.day_rate > 0:
            assert eq.day_rate_min == pytest.approx(eq.day_rate * 0.8)
            assert eq.day_rate_max == pytest.approx(eq.day_rate * 1.2)


# ─────────────────────────────────────────────────────────────────────────
# Result → Response 轉換 tests
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def k13_cost_result():
    from modules.cost.engine.cost_cal import run_cost_calculation

    p = load_k13_engine_params(stochastic=False)
    return run_cost_calculation(
        wind_farm=p.wind_farm, components=p.components,
        equipment_list=p.equipment_list, pm_schedules=p.pm_schedules,
        fixed_costs=p.fixed_costs, poly_lookup=p.poly_lookup,
    )


def test_cost_result_to_response_pydantic_roundtrip(k13_cost_result):
    """cost_cal CostCalResult → dict → pydantic CostForecastResponse 全程不報錯。"""
    resp_dict = cost_result_to_response(k13_cost_result)
    resp = CostForecastResponse(**resp_dict)

    # 數字應與 baseline 一致
    assert resp.availability_time == 0.9401732630646628
    assert resp.total_effort == 67964410.8982218
    assert resp.cost_per_kwh == 0.036948752282382154

    # 4 季 breakdown 都在
    assert set(resp.seasonal.keys()) == {"winter", "spring", "summer", "autumn"}
    assert resp.seasonal["winter"].fixed_cost == 5550000.0


def test_lcoe_result_to_response(k13_cost_result):
    """LCOE 計算 → dict → LCOEResponse pydantic 接受 + 數字正確。"""
    from modules.cost.engine.cost_cal.lcoe import calculate_lcoe
    from modules.cost.engine.cost_cal.revenue_loss import annual_energy_production_mwh

    p = load_k13_engine_params()
    annual_energy = annual_energy_production_mwh(p.wind_farm)
    lcoe = calculate_lcoe(
        capex_per_kw=1250.0, capacity_kw=p.wind_farm.capacity_kw,
        nr_turbines=p.wind_farm.nr_turbines, lifetime=p.wind_farm.lifetime_years,
        discount_rate=0.08, annual_opex=k13_cost_result.total_effort,
        annual_energy_mwh=annual_energy,
    )
    resp = LCOEResponse(**lcoe_result_to_response(lcoe))
    assert resp.lcoe == 72.94042482488679  # 黃金數字
    assert resp.capex_total == 650000000.0


def test_mc_result_to_response_pydantic_roundtrip():
    """MC result → dict → MonteCarloResponse pydantic 接受。"""
    from modules.cost.engine.monte_carlo import run_monte_carlo

    p = load_k13_engine_params(stochastic=True)
    mc = run_monte_carlo(
        wind_farm=p.wind_farm, components=p.components,
        equipment_list=p.equipment_list, pm_schedules=p.pm_schedules,
        fixed_costs=p.fixed_costs, poly_lookup=p.poly_lookup,
        n_simulations=50, seed=42,
    )
    resp = MonteCarloResponse(**mc_result_to_response(mc))
    assert resp.n_simulations == 50
    assert resp.seed == 42
    assert resp.deterministic.availability_time == 0.9401732630646628
    # Percentile order
    assert resp.percentiles.cost.p10 < resp.percentiles.cost.p50 < resp.percentiles.cost.p90


def test_vf_result_to_response_pydantic_roundtrip():
    """VarFluct result → dict → VarFluctResponse pydantic 接受。"""
    from modules.cost.engine.var_fluct import run_var_fluct_calculation
    from modules.cost.engine.var_fluct.calculator import VarFluctConfig

    p = load_k13_engine_params()
    vf = run_var_fluct_calculation(
        wind_farm=p.wind_farm, components=p.components,
        equipment_list=p.equipment_list, pm_schedules=p.pm_schedules,
        fixed_costs=p.fixed_costs, poly_lookup=p.poly_lookup,
        config=VarFluctConfig(),
    )
    resp = VarFluctResponse(**vf_result_to_response(vf))
    assert len(resp.yearly) == 20
    assert resp.yearly[0].year == 1
    assert resp.yearly[0].failure_multiplier == 1.5  # early peak
    assert resp.yearly[19].failure_multiplier == 2.0  # late peak
    assert resp.summary.npv_total_effort == 776626181.4
    assert resp.summary.lifetime_availability_time == 0.932024


# ─────────────────────────────────────────────────────────────────────────
# Equivalence vs old build_*_params (regression)
# ─────────────────────────────────────────────────────────────────────────


def test_loader_produces_pinned_baseline():
    """新 loader 跑出來的 K13 cost_cal 結果 == ECN baseline（與 -03 test 同 invariant）。"""
    from modules.cost.engine.cost_cal import run_cost_calculation

    p = load_k13_engine_params(stochastic=False)
    result = run_cost_calculation(
        wind_farm=p.wind_farm, components=p.components,
        equipment_list=p.equipment_list, pm_schedules=p.pm_schedules,
        fixed_costs=p.fixed_costs, poly_lookup=p.poly_lookup,
    )
    # 6 個 top-level metric 全 bit-perfect
    assert result.availability_time == 0.9401732630646628
    assert result.availability_energy == 0.9364235587596128
    assert result.total_revenue_loss == 15202721.720482074
    assert result.total_repair_cost == 52761689.17773973
    assert result.total_effort == 67964410.8982218
    assert result.cost_per_kwh == 0.036948752282382154
