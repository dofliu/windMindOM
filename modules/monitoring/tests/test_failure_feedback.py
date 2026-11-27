"""換零件與故障率的回饋（WMOM-20261127-07，DEC-20261127-09）。

1. 故障產生器：工單換掉的零件從換新起算耗損，那個零件的發生率跟著降；其他零件照舊；抽樣次數不變。
2. 運維閉環：完工時記下換掉的零件；維修紀錄（由工單修好的故障、運轉機組年）。
3. 成本模組：可信度加權的故障率、三角分布的比例不變、情境對 K13 元件的表涵蓋全部情境。
4. 端點：``/api/operations/failure-rates`` 與 ``/api/cost/monte-carlo/empirical`` 只給永遠強制登入的主管。
"""

from __future__ import annotations

import asyncio
import pickle
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.cost.adapter import load_k13_engine_params
from modules.cost.engine.cost_cal.data_classes import ComponentParams
from modules.cost.routers import cost_router
from modules.cost.schemas.cost_schemas import EmpiricalMonteCarloRequest
from modules.cost.services import failure_rates as fr
from modules.workflow import hooks
from modules.workflow.domain import WorkOrderType
from modules.workflow.repository import work_order_repository as wo_repo
from server.routers import operations as ops
from simulator.fault_generator import FaultGenerator, FaultGeneratorConfig, part_of
from simulator.physics.fault_engine import FAULT_SCENARIOS

from .test_om_loop import FARM, WIRE_BREAK, Farm


@pytest.fixture
def farm(tmp_path) -> Iterator[Farm]:
    f = Farm(tmp_path, turbines=3)
    try:
        yield f
    finally:
        hooks.clear_work_order_listeners()
        wo_repo.clear_engine_cache_for_test()
        fr.set_observation_provider(None)


def _model(damage: float, fouling: float) -> SimpleNamespace:
    fatigue = SimpleNamespace(damage_tower_fa=damage, damage_tower_ss=0.0, damage_blade_flap=0.0,
                              damage_blade_edge=0.0)
    return SimpleNamespace(fatigue=fatigue, cooling=SimpleNamespace(water_loop=SimpleNamespace(fouling=fouling)))


# ── 1. 故障產生器 ─────────────────────────────────────────────────────────


def test_the_part_a_repair_replaces() -> None:
    assert part_of("bearing_wear") == "main_bearing"
    assert part_of("main_bearing_temp_sensor_drift") == "main_bearing:sensor", "換 Pt100 不會讓主軸承變新"
    assert part_of("pitch_motor_fault") == part_of("pitch_imbalance") == "pitch_system_blade_1"
    for nothing in ("blade_icing", "grid_voltage_sag", "main_bearing_temp_loose_contact"):
        assert part_of(nothing) is None, nothing
    assert part_of("no_such_fault") is None


def test_a_replaced_part_starts_its_wear_again_and_lowers_the_hazard() -> None:
    generator = FaultGenerator(FaultGeneratorConfig(enabled=True, wear_gain=4.0))
    worn = _model(damage=0.2, fouling=0.03)          # 兩種耗損都超過參考值（0.1 / 0.02）→ 1
    from simulator.fault_generator import turbine_wear

    wear = turbine_wear(worn, generator.config)
    before = dict(generator.scenario_weights(wear))
    hazard_before = generator.hazard_per_second("WT001", wear)
    assert before["bearing_wear"] == pytest.approx(5.0) and before["converter_cooling_pump_wear"] == pytest.approx(5.0)

    parts = generator.record_replacement("WT001", ["bearing_wear", "converter_cooling_pump_wear"], worn,
                                         at="2026-11-27T06:00:00.000000+00:00")
    assert parts == ["converter_cooling_system", "main_bearing"]
    replaced = generator.part_wear("WT001", worn)
    assert replaced == {"converter_cooling_system": 0.0, "main_bearing": 0.0}
    after = dict(generator.scenario_weights(wear, replaced))
    assert after["bearing_wear"] == pytest.approx(1.0), "換新的主軸承：耗損 0"
    assert after["cooling_water_deionizer_exhausted"] == pytest.approx(1.0), "同一個冷卻系統一起換新"
    assert after["stator_winding_degradation"] == pytest.approx(5.0), "沒換的零件照舊"
    assert after["main_bearing_temp_sensor_drift"] == pytest.approx(5.0), "主軸承的感測器沒換"
    assert generator.hazard_per_second("WT001", wear, replaced) < hazard_before
    assert generator.part_wear("WT002", worn) == {}, "別台機組不受影響"

    # 換新之後又累積：疲勞多了 0.05（參考值 0.1）→ 0.5
    later = _model(damage=0.25, fouling=0.03)
    assert generator.part_wear("WT001", later)["main_bearing"] == pytest.approx(0.5)
    assert generator.replacements()["WT001"]["main_bearing"]["at"] == "2026-11-27T06:00:00.000000+00:00"
    # 沒有換零件的修復不記
    assert generator.record_replacement("WT003", ["blade_icing"], worn) == []
    assert "WT003" not in generator.replacements()


def test_replacements_do_not_change_the_draw_count_and_survive_a_checkpoint() -> None:
    from simulator.physics.fault_engine import FaultEngine

    turbines = {"WT001": _model(0.2, 0.03), "WT002": _model(0.2, 0.03)}
    a = FaultGenerator(FaultGeneratorConfig(enabled=True, mean_days_between_faults=1e9))
    b = FaultGenerator(FaultGeneratorConfig(enabled=True, mean_days_between_faults=1e9))
    b.record_replacement("WT001", ["bearing_wear"], turbines["WT001"])
    a.step(60.0, turbines, FaultEngine())
    b.step(60.0, turbines, FaultEngine())
    assert a._rng.getstate() == b._rng.getstate(), "換零件不改每次檢查抽幾個數"
    restored = pickle.loads(pickle.dumps(b))
    assert restored.part_wear("WT001", turbines["WT001"]) == {"main_bearing": 0.0}


# ── 2. 運維閉環 ───────────────────────────────────────────────────────────


def test_finishing_a_work_order_records_the_replaced_parts_and_the_repairs(farm: Farm) -> None:
    farm.drive_slow(60)
    farm.inject("bearing_wear", "WT002", severity=0.3)
    order = farm.repo.create(farm_id=FARM, turbine_id="WT002", type=WorkOrderType.CORRECTIVE, title="x",
                             description="", source_alarm_code="240")
    farm.start(order)
    farm.drive(5)
    farm.finish(order)
    generator = farm.broker.simulator.fault_generator
    clock = farm.broker.live_clock()
    from simulator.time_utils import iso_utc

    assert generator.replacements()["WT002"]["main_bearing"]["at"] == iso_utc(clock), "時間用風場時鐘"
    assert generator.part_wear("WT002", farm.model("WT002")) == {"main_bearing": pytest.approx(0.0, abs=1e-6)}
    # 出題用的後門清掉的不算維修紀錄
    farm.inject(WIRE_BREAK, "WT003")
    farm.broker.simulator.fault_engine.clear(turbine_id="WT003", scenario_id=WIRE_BREAK)
    farm.broker.fault_records.on_fault_cleared("WT003", WIRE_BREAK, None)
    observations = farm.loop.failure_observations(clock - timedelta(days=1), clock + timedelta(hours=1))
    assert observations.repairs == {"bearing_wear": 1}
    assert observations.turbine_years > 0


def test_the_generator_view_shows_wear_and_replaced_parts(farm: Farm, monkeypatch) -> None:
    monkeypatch.setattr(ops, "get_broker", lambda: farm.broker)
    farm.drive_slow(6)
    model = farm.model("WT001")
    farm.broker.simulator.fault_generator.record_replacement("WT001", ["hydraulic_leak"], model, at="t")
    view = asyncio.run(ops.fault_generator_settings())["wear"]
    assert set(view) == {"WT001", "WT002", "WT003"}
    assert set(view["WT002"]) == {"fatigue", "fouling", "parts"} and view["WT002"]["parts"] == {}
    assert view["WT001"]["parts"]["yaw_brake_hydraulics"]["replaced_at"] == "t"


# ── 3. 成本模組 ───────────────────────────────────────────────────────────


def test_every_fault_scenario_maps_to_a_k13_component_or_to_none() -> None:
    mapping = fr.component_map()
    assert set(mapping) == set(FAULT_SCENARIOS), "新增故障情境要補 z72_repair_classes.json 的 k13_components"
    codes = {comp.component_code for comp in load_k13_engine_params().components}
    assert {code for code in mapping.values() if code} <= codes
    for scenario_id, scenario in FAULT_SCENARIOS.items():
        if part_of(scenario_id) is None:
            assert mapping[scenario_id] is None, f"{scenario_id}：沒有換零件的不算元件故障"
        if scenario.category == "nuisance":
            assert mapping[scenario_id] is None


def _component(code: str, freq: float) -> ComponentParams:
    return ComponentParams(component_name=f"{code} - test", component_code=code, component_type="WT",
                           annual_failure_freq=freq, maintenance_categories=[], freq_min=freq * 0.7, freq_ml=freq,
                           freq_max=freq * 1.3)


def test_credibility_weighted_rates_move_only_the_modelled_components() -> None:
    components = [_component("MDK10", 0.014), _component("UMD", 0.1512)]
    observations = fr.FailureObservations(repairs={"bearing_wear": 3, "main_bearing_temp_sensor_drift": 2,
                                                   "blade_icing": 4}, turbine_years=14.0)
    bearing, tower = fr.empirical_rates(components, observations, prior_turbine_years=14.0)
    assert bearing.modelled and bearing.repairs == 3, "感測器（MDY）與結冰不算主軸承"
    assert bearing.rate == pytest.approx((0.014 * 14 + 3) / 28) and bearing.weight == pytest.approx(0.5)
    assert bearing.observed_rate == pytest.approx(3 / 14)
    assert not tower.modelled and tower.rate == 0.1512 and tower.weight == 0.0, "模擬器不會讓塔架壞：維持 K13"
    assert fr.unmapped_repairs(observations) == {"blade_icing": 4}
    fr.apply_rate_updates(components, [bearing, tower])
    assert components[0].annual_failure_freq == pytest.approx(bearing.rate)
    assert (components[0].freq_min, components[0].freq_max) == pytest.approx((bearing.rate * 0.7, bearing.rate * 1.3))
    assert components[1].freq_ml == 0.1512
    # 沒有運轉紀錄：照 K13
    (same,) = fr.empirical_rates([_component("MDK10", 0.014)], fr.FailureObservations(repairs={}, turbine_years=0))
    assert same.rate == pytest.approx(0.014) and same.observed_rate is None
    # 運轉了但沒修過：證據是「這段時間沒壞」，故障率往下
    (quiet,) = fr.empirical_rates([_component("MDK10", 0.014)], fr.FailureObservations(repairs={}, turbine_years=14))
    assert quiet.rate == pytest.approx(0.007)
    with pytest.raises(ValueError):
        fr.empirical_rates(components, observations, prior_turbine_years=0)


# ── 4. 端點 ───────────────────────────────────────────────────────────────


def test_the_failure_rate_endpoint(farm: Farm, monkeypatch) -> None:
    monkeypatch.setattr(ops, "get_broker", lambda: farm.broker)
    farm.drive_slow(60)
    farm.inject("bearing_wear", "WT002", severity=0.3)
    order = farm.repo.create(farm_id=FARM, turbine_id="WT002", type=WorkOrderType.CORRECTIVE, title="x",
                             description="", source_alarm_code="240")
    farm.start(order)
    farm.drive(5)
    farm.finish(order)
    body = asyncio.run(ops.failure_rates(prior_turbine_years=14.0))
    by_code = {row["code"]: row for row in body["components"]}
    assert by_code["MDK10"]["repairs"] == 1 and by_code["MDK10"]["rate"] > by_code["MDK10"]["k13_rate"]
    assert by_code["MDK10"]["scenarios"] == ["bearing_wear"]
    assert not by_code["UMD"]["modelled"] and by_code["UMD"]["rate"] == by_code["UMD"]["k13_rate"]
    assert body["turbine_years"] > 0 and body["unmapped"] == {}
    # 只給永遠強制登入的主管（修了什麼來自不對外的故障紀錄）
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)
    app = FastAPI()
    app.include_router(ops.router)
    assert TestClient(app).get("/api/operations/failure-rates").status_code in (401, 403)


def test_the_empirical_monte_carlo(monkeypatch) -> None:
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)
    app = FastAPI()
    app.include_router(cost_router.router)
    client = TestClient(app)
    assert client.post("/api/cost/monte-carlo/empirical", json={"dataset": "farm:台中港曲風場"}).status_code \
        in (401, 403), "永遠強制登入"

    def run(dataset: str):
        return asyncio.run(cost_router.cost_monte_carlo_empirical(
            EmpiricalMonteCarloRequest(dataset=dataset, n_simulations=10, seed=7)))

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as no_farm:
        run("k13")
    assert no_farm.value.status_code == 422
    with pytest.raises(HTTPException) as no_records:
        run("farm:台中港曲風場")
    assert no_records.value.status_code == 409, "沒有登記維修紀錄的來源"
    fr.set_observation_provider(lambda farm_id: fr.FailureObservations(
        repairs={"bearing_wear": 20, "stator_winding_degradation": 10}, turbine_years=14.0,
        start="s", end="e") if farm_id == "台中港曲風場" else None)
    try:
        result = run("farm:台中港曲風場")
        plain = asyncio.run(cost_router.cost_monte_carlo(
            cost_router.MonteCarloRequest(dataset="farm:台中港曲風場", n_simulations=10, seed=7)))
    finally:
        fr.set_observation_provider(None)
    rows = {row.code: row for row in result.empirical.components}
    assert rows["MDK10"].repairs == 20 and rows["MKA"].repairs == 10
    assert rows["MDK10"].rate == pytest.approx((rows["MDK10"].k13_rate * 14 + 20) / 28, rel=1e-4)
    assert result.empirical.turbine_years == 14.0 and plain.empirical is None
    assert result.deterministic.total_effort > plain.deterministic.total_effort, "故障變多，運維成本變高"


def test_the_server_provides_failure_observations_for_the_active_farm(farm: Farm, monkeypatch) -> None:
    from server import app as server_app

    monkeypatch.setattr(server_app, "broker", farm.broker)
    assert server_app._failure_observations_for_cost(FARM) is None, "還沒有運轉紀錄"
    farm.drive_slow(60)
    observations = server_app._failure_observations_for_cost(FARM)
    assert observations is not None and observations.turbine_years > 0 and observations.repairs == {}
    assert server_app._failure_observations_for_cost("other-farm") is None
