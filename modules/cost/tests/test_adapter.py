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
    FarmDatasetMeta,
    _apply_wind_farm_overrides,
    cost_result_to_response,
    lcoe_result_to_response,
    load_engine_params_from_farm,
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
from modules.cost.tests.pin_tolerance import pin_approx  # noqa: E402


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
    assert resp.availability_time == pin_approx(0.9401732630646628)
    assert resp.total_effort == pin_approx(67964410.8982218)
    assert resp.cost_per_kwh == pin_approx(0.036948752282382154)

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
    assert resp.lcoe == pin_approx(72.94042482488679)  # 黃金數字
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
    assert resp.deterministic.availability_time == pin_approx(0.9401732630646628)
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
    assert result.availability_time == pin_approx(0.9401732630646628)
    assert result.availability_energy == pin_approx(0.9364235587596128)
    assert result.total_revenue_loss == pin_approx(15202721.720482074)
    assert result.total_repair_cost == pin_approx(52761689.17773973)
    assert result.total_effort == pin_approx(67964410.8982218)
    assert result.cost_per_kwh == pin_approx(0.036948752282382154)


# ─────────────────────────────────────────────────────────────────────────
# Farm-aware loader（WMOM-20260504-10）
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def farm_overrides_dir(tmp_path):
    """臨時目錄 + 一個合法的 cost_inputs.json（test_farm / 14 × 2 MW）。"""
    farms_root = tmp_path / "farms"
    farm_dir = farms_root / "test_farm"
    farm_dir.mkdir(parents=True)
    (farm_dir / "cost_inputs.json").write_text(
        '{\n'
        '  "schema_version": "1.0",\n'
        '  "farm_id": "test_farm",\n'
        '  "base_dataset": "k13",\n'
        '  "wind_farm_overrides": {\n'
        '    "nr_turbines": 14,\n'
        '    "capacity_kw": 2000,\n'
        '    "kwh_price": 0.10,\n'
        '    "investment_cost_per_kw": 1100\n'
        '  }\n'
        '}\n',
        encoding="utf-8",
    )
    return farms_root


def test_load_from_farm_with_cost_inputs_overlay(farm_overrides_dir):
    """有 cost_inputs.json → 套用 overrides，meta.source == farm_overlay。"""
    params, meta = load_engine_params_from_farm(
        "test_farm", farms_dir=farm_overrides_dir
    )
    assert isinstance(meta, FarmDatasetMeta)
    assert meta.dataset_used == "farm:test_farm"
    assert meta.farm_id == "test_farm"
    assert meta.is_fallback is False
    assert meta.source == "farm_overlay"
    # farm_overlay 仍有 K13 onshore-mismatch 警語
    assert meta.warning is not None and "K13" in meta.warning

    # wind_farm 級 overrides 套上
    assert params.wind_farm.nr_turbines == 14
    assert params.wind_farm.capacity_kw == 2000
    assert params.wind_farm.kwh_price == 0.10
    assert params.wind_farm.investment_cost_per_kw == 1100

    # 未覆寫的 K13 預設保留（K13 efficiency = 0.9）
    assert params.wind_farm.farm_efficiency == 0.9
    # Components 等沿用 K13
    assert len(params.components) == 18


def test_load_from_farm_with_cost_inputs_changes_revenue_loss(farm_overrides_dir):
    """套用 14×2MW overrides 後跑 cost_cal → revenue_loss 應顯著小於 K13（130×4MW）。"""
    from modules.cost.engine.cost_cal import run_cost_calculation

    params, _ = load_engine_params_from_farm("test_farm", farms_dir=farm_overrides_dir)
    result = run_cost_calculation(
        wind_farm=params.wind_farm,
        components=params.components,
        equipment_list=params.equipment_list,
        pm_schedules=params.pm_schedules,
        fixed_costs=params.fixed_costs,
        poly_lookup=params.poly_lookup,
    )
    # K13 baseline total_revenue_loss == 1.52e7；14 × 2 MW（規模 ~14/130 × 2/4 ≈ 5.4%）
    # 不需 bit-perfect，只要明顯縮小
    assert result.total_revenue_loss < 5e6, (
        f"farm overlay 應大幅縮小 revenue loss，實得 {result.total_revenue_loss}"
    )


class _StubFarmRegistry:
    """測試用 mock — 模擬 monitoring 的 FarmRegistry。"""

    def __init__(self, farm_id, turbine_count, rated_power_kw):
        from types import SimpleNamespace

        self._farm = SimpleNamespace(
            farm_id=farm_id,
            turbine_count=turbine_count,
            turbine_spec={"rated_power_kw": rated_power_kw},
        )
        self._farm_id = farm_id

    def get_farm(self, farm_id):
        return self._farm if farm_id == self._farm_id else None


def test_load_from_farm_registry_derived_when_no_cost_inputs(tmp_path):
    """沒有 cost_inputs.json 但 registry 有此 farm → derive minimal overrides + 帶 warning。"""
    empty_farms = tmp_path / "farms"
    empty_farms.mkdir()
    reg = _StubFarmRegistry("z72_taichung", turbine_count=14, rated_power_kw=2000)

    params, meta = load_engine_params_from_farm(
        "z72_taichung", farm_registry=reg, farms_dir=empty_farms
    )
    # 驗 source（authoritative）— warning 文字之後 i18n 微調不應 break test
    assert meta.source == "registry_derived"
    assert meta.is_fallback is False
    assert meta.warning  # 該層必發 warning（具體文字由 source 蘊含，不重 assert wording）
    assert params.wind_farm.nr_turbines == 14
    assert params.wind_farm.capacity_kw == 2000.0
    # 其餘沿用 K13
    assert params.wind_farm.kwh_price == 0.13  # K13 default
    assert params.wind_farm.investment_cost_per_kw == 1250  # K13 default


def test_load_from_farm_falls_back_to_k13_when_unknown(tmp_path):
    """cost_inputs.json 沒有、registry 也沒有 → fallback K13 + is_fallback=True。"""
    empty_farms = tmp_path / "farms"
    empty_farms.mkdir()
    reg = _StubFarmRegistry("other_farm", turbine_count=10, rated_power_kw=3000)

    params, meta = load_engine_params_from_farm(
        "ghost_farm", farm_registry=reg, farms_dir=empty_farms
    )
    assert meta.source == "k13_fallback"
    assert meta.is_fallback is True
    assert meta.dataset_used == "k13"
    assert meta.farm_id == "ghost_farm"
    assert meta.warning is not None
    # Wind farm 必須是純 K13
    assert params.wind_farm.nr_turbines == 130
    assert params.wind_farm.capacity_kw == 4000


def test_apply_overrides_ignores_unknown_fields():
    """_apply_wind_farm_overrides 只接受 WindFarmParams 既有欄位，未知 key 安靜略過。"""
    base = load_k13_engine_params().wind_farm
    new_wf = _apply_wind_farm_overrides(
        base,
        {
            "nr_turbines": 7,
            "kwh_price": 0.20,
            "rogue_field": "should_be_ignored",
            "another_unknown": 42,
        },
    )
    assert new_wf.nr_turbines == 7
    assert new_wf.kwh_price == 0.20
    # 沒有亂加 attr（非 WindFarmParams field）
    assert not hasattr(new_wf, "rogue_field")


def test_apply_overrides_coerces_string_numbers():
    """JSON 寫成 string 的 int / float 應被 coerce — 不會帶字串繼續跑。"""
    base = load_k13_engine_params().wind_farm
    new_wf = _apply_wind_farm_overrides(
        base,
        {"nr_turbines": "14", "capacity_kw": "2000.0", "kwh_price": "0.1"},
    )
    assert new_wf.nr_turbines == 14
    assert isinstance(new_wf.nr_turbines, int)
    assert new_wf.capacity_kw == 2000.0
    assert isinstance(new_wf.capacity_kw, float)
    assert new_wf.kwh_price == 0.1


def test_apply_overrides_rejects_invalid_numeric():
    """無法 cast 成數字的值應 raise ValueError，避免 TypeError 在計算半路爆。"""
    base = load_k13_engine_params().wind_farm
    with pytest.raises(ValueError, match="nr_turbines"):
        _apply_wind_farm_overrides(base, {"nr_turbines": "fourteen"})
