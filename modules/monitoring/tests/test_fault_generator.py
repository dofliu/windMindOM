"""機率式故障產生器（WMOM-20261125-06-b）。

1. 關著的時候不產生、不抽樣；批次情境不呼叫它。
2. 亂數可重現、用自己的 stream；抽樣次數不隨結果或設定改變；狀態存檔之後接著同一條序列。
3. 發生率符合設定；耗損提高發生率，而且偏向和那種耗損有關的故障；權重為 0 的不產生。
4. 設定要檢查。
"""

from __future__ import annotations

import pickle
import sys
from collections import Counter
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import pytest

from simulator.engine import WindFarmSimulator
from simulator.fault_generator import (
    DEFAULT_EXCLUDED,
    FaultGenerator,
    FaultGeneratorConfig,
    is_latent,
    turbine_wear,
)
from simulator.physics.fault_engine import FAULT_SCENARIOS


def _sim(turbines: int = 6) -> WindFarmSimulator:
    return WindFarmSimulator(turbine_count=turbines)


def _run(sim: WindFarmSimulator, generator: FaultGenerator, checks: int,
         keep: bool = False) -> List[Tuple[int, str, str]]:
    """只推進產生器（不跑物理）：每次檢查一分鐘。回傳（第幾次, 機組, 情境）。"""
    out: List[Tuple[int, str, str]] = []
    for index in range(checks):
        for made in generator.step(60.0, sim.turbines, sim.fault_engine):
            out.append((index, made.turbine_id, made.scenario_id))
        if not keep:
            sim.fault_engine.clear()
    return out


def _config(**changes) -> FaultGeneratorConfig:
    return FaultGeneratorConfig.from_dict({"enabled": True, "mean_days_between_faults": 0.05, **changes})


# ── 1. 關著 / 批次 ─────────────────────────────────────────────────────────


def test_disabled_generator_makes_nothing_and_draws_nothing() -> None:
    sim = _sim()
    generator = sim.fault_generator
    assert generator.config.enabled is False, "預設關"
    before = generator._rng.getstate()
    assert _run(sim, generator, 500) == [] and generator._rng.getstate() == before
    assert sim.fault_engine.active_faults == []


def test_engine_calls_the_generator_only_in_live_steps() -> None:
    from simulator.time_utils import utc_now

    sim = _sim(3)
    sim.fault_generator.configure(_config(mean_days_between_faults=0.0005))
    sim._bulk_running = True
    clock = utc_now()
    for _ in range(180):
        sim._run_one_step(clock, 1.0)
    assert sim.fault_engine.active_faults == [] and sim.fault_generator.generated == 0, "批次情境不產生"
    sim._bulk_running = False
    for _ in range(180):
        sim._run_one_step(clock, 1.0)
    assert sim.fault_generator.generated > 0 and sim.fault_engine.active_faults
    assert {f.scenario_id for f in sim.fault_engine.active_faults} <= set(FAULT_SCENARIOS) - DEFAULT_EXCLUDED


# ── 2. 可重現 ─────────────────────────────────────────────────────────────


def test_same_seed_gives_the_same_faults_and_a_new_seed_does_not() -> None:
    first = _run(_sim(), FaultGenerator(_config()), 400)
    again = _run(_sim(), FaultGenerator(_config()), 400)
    other = _run(_sim(), FaultGenerator(_config(seed=7)), 400)
    assert first and first == again and other != first


def test_draw_count_does_not_depend_on_the_outcome_or_the_settings() -> None:
    busy, quiet = FaultGenerator(_config()), FaultGenerator(_config(mean_days_between_faults=3650.0))
    made = _run(_sim(), busy, 300, keep=True)   # 故障留著：有些機組到了上限
    assert made and _run(_sim(), quiet, 300) == []
    assert busy._rng.getstate() == quiet._rng.getstate(), "每次檢查每台機組固定抽三個數"
    # 換設定（不換種子）不重設序列；換種子才重設
    state = busy._rng.getstate()
    busy.configure(_config(wear_gain=0.0))
    assert busy._rng.getstate() == state
    busy.configure(_config(seed=99))
    assert busy._rng.getstate() != state


def test_generator_does_not_touch_the_simulator_rngs() -> None:
    """健康輸出不受影響：開著產生器（發生率低到不會真的發生）跑出來的讀值和關著的逐位元相同。"""
    from datetime import datetime, timedelta, timezone

    def readings(enabled: bool) -> list:
        sim = _sim(3)
        if enabled:
            sim.fault_generator.configure(_config(mean_days_between_faults=1e9))
        clock = datetime(2026, 1, 1, tzinfo=timezone.utc)
        out = []
        for step in range(150):
            data = sim._run_one_step(clock + timedelta(seconds=step), 1.0)
            out.append([sorted(d["scada"].items()) for d in data])
        return out

    assert readings(True) == readings(False)


def test_pickled_generator_continues_the_same_sequence() -> None:
    sim = _sim()
    generator = FaultGenerator(_config())
    head = _run(sim, generator, 150)
    restored = pickle.loads(pickle.dumps(generator))
    assert restored.config == generator.config and restored.generated == generator.generated == len(head)
    assert _run(sim, restored, 150) == _run(_sim(), generator, 150)


def test_simulator_checkpoint_carries_the_generator() -> None:
    sim = _sim(3)
    sim.fault_generator.configure(_config())
    _run(sim, sim.fault_generator, 100)
    blob = sim.checkpoint_state()
    expected = _run(sim, sim.fault_generator, 100)
    other = _sim(3)
    other.restore_state(blob)
    assert other.fault_generator.config.enabled is True
    assert _run(other, other.fault_generator, 100) == expected


# ── 3. 發生率、耗損、權重 ─────────────────────────────────────────────────


def test_rate_matches_the_setting() -> None:
    sim = _sim(6)
    generator = FaultGenerator(_config(mean_days_between_faults=0.5, wear_gain=0.0))
    checks = 6000   # 6000 分鐘 × 6 台 ÷ (0.5 天＝720 分鐘) ≈ 50 次
    made = _run(sim, generator, checks)
    expected = checks * 6 / 720.0
    assert 0.6 * expected < len(made) < 1.4 * expected, (len(made), expected)
    assert {t for _, t, _ in made} == set(sim.turbines), "每台機組都會"


def test_wear_raises_the_rate_and_favours_the_related_faults() -> None:
    sim = _sim(4)
    generator = FaultGenerator(_config())
    worn, clean = sim.turbines["WT001"], sim.turbines["WT002"]
    assert turbine_wear(clean) == {"fatigue": 0.0, "fouling": 0.0}
    base = generator.hazard_per_second("WT002", turbine_wear(clean))
    assert base == pytest.approx(1.0 / (0.05 * 86400.0))
    worn.cooling.water_loop._fouling_factor = 0.02       # 結垢到參考值（預設 0.02，約半年）
    wear = turbine_wear(worn)
    assert wear == {"fatigue": 0.0, "fouling": 1.0}
    assert generator.hazard_per_second("WT001", wear) > base
    weights = dict(generator.scenario_weights(wear))
    assert weights["converter_cooling_fault"] == pytest.approx(5.0) and weights["bearing_wear"] == pytest.approx(1.0)
    worn.cooling.water_loop._fouling_factor = 0.0
    worn.fatigue.damage_blade_flap = 0.05      # 參考值 0.1 的一半
    assert turbine_wear(worn) == {"fatigue": 0.5, "fouling": 0.0}
    # 參考值可以調：同樣的損傷，參考值大一倍，耗損就小一半；超過參考值封頂在 1
    assert turbine_wear(worn, _config(fatigue_reference=0.2))["fatigue"] == pytest.approx(0.25)
    assert turbine_wear(worn, _config(fatigue_reference=0.01))["fatigue"] == 1.0
    weights = dict(generator.scenario_weights(turbine_wear(worn)))
    assert weights["bearing_wear"] == pytest.approx(3.0) and weights["converter_cooling_fault"] == pytest.approx(1.0)
    # 實際抽出來的也是：結垢的機組更常故障，而且多半是冷卻類
    worn.fatigue.damage_blade_flap = 0.0
    worn.cooling.water_loop._fouling_factor = 0.02
    made = _run(sim, FaultGenerator(_config(mean_days_between_faults=0.2)), 4000)
    per_turbine = Counter(t for _, t, _ in made)
    assert per_turbine["WT001"] > 1.3 * per_turbine["WT002"]
    cooling = {s for s in FAULT_SCENARIOS if FAULT_SCENARIOS[s].component in
               ("converter_cooling_system", "nacelle_ventilation", "transformer")}
    share = lambda tid: sum(1 for _, t, s in made if t == tid and s in cooling) / per_turbine[tid]  # noqa: E731
    assert share("WT001") > share("WT002") + 0.2
    # wear_gain 0：耗損不影響
    flat = FaultGenerator(_config(wear_gain=0.0))
    assert flat.hazard_per_second("WT001", turbine_wear(worn)) == pytest.approx(base)


def test_weights_exclude_scenarios_and_turbines() -> None:
    sim = _sim(4)
    made = _run(sim, FaultGenerator(_config(
        scenario_weights={"bearing_wear": 1.0, **{s: 0.0 for s in FAULT_SCENARIOS if s != "bearing_wear"}},
        turbine_weights={"WT003": 0.0, "WT004": 5.0})), 800)
    assert made and {s for _, _, s in made} == {"bearing_wear"}
    per_turbine = Counter(t for _, t, _ in made)
    assert "WT003" not in per_turbine and per_turbine["WT004"] > 2 * per_turbine["WT001"]
    # 預設不產生的三個情境
    default = _run(_sim(4), FaultGenerator(_config()), 3000)
    assert not {s for _, _, s in default} & DEFAULT_EXCLUDED
    assert DEFAULT_EXCLUDED == {"blade_icing", "yaw_misalignment", "grid_voltage_sag",
                                "main_bearing_temp_loose_contact"}, "沒有工單可以修掉它們的，預設不產生"
    assert len({s for _, _, s in default}) >= 15, "其餘情境都抽得到"
    # 全部權重為 0：什麼都不產生
    assert _run(_sim(4), FaultGenerator(_config(scenario_weights={s: 0.0 for s in FAULT_SCENARIOS})), 300) == []


def test_a_turbine_gets_at_most_the_configured_number_of_faults() -> None:
    sim = _sim(3)
    generator = FaultGenerator(_config(mean_days_between_faults=0.001))
    _run(sim, generator, 200, keep=True)
    assert Counter(f.turbine_id for f in sim.fault_engine.active_faults) == {"WT001": 1, "WT002": 1, "WT003": 1}
    sim.fault_generator = generator
    generator.configure(_config(mean_days_between_faults=0.001, max_active_per_turbine=2))
    _run(sim, generator, 200, keep=True)
    per = Counter(f.turbine_id for f in sim.fault_engine.active_faults)
    assert set(per.values()) == {2}
    assert all(len({f.scenario_id for f in sim.fault_engine.active_faults if f.turbine_id == t}) == 2 for t in per)
    rates = [f.severity_rate for f in sim.fault_engine.active_faults]
    assert all(1 / (48 * 3600) <= r <= 1 / (0.5 * 3600) for r in rates) and len(set(rates)) > 1


def test_a_latent_fault_does_not_hold_the_turbine_slot() -> None:
    """WMOM-20261126-09：嚴重度到頂卻沒有警報的故障（例：11 月的變壓器過熱）修不掉，不能讓那台機組從此
    不再發生別的故障。開始報警或跳過機的，照樣佔名額。"""
    sim = _sim(1)
    generator = FaultGenerator(_config(mean_days_between_faults=0.001))
    _run(sim, generator, 50, keep=True)
    [fault] = sim.fault_engine.active_faults
    assert not is_latent(fault), "還在劣化"
    fault.severity = fault.max_severity
    assert is_latent(fault)
    for busy in ({"active_alarms": [{"code": 417}]}, {"tripped": True}):
        for key, value in busy.items():
            setattr(fault, key, value)
        assert not is_latent(fault)
        assert _run(sim, generator, 50, keep=True) == [], f"{busy}：佔著名額"
        fault.active_alarms, fault.tripped = [], False
    made = _run(sim, generator, 50, keep=True)
    assert len(made) == 1 and made[0][2] != fault.scenario_id, "潛伏的不佔名額，另一種故障照樣發生"
    assert len(sim.fault_engine.active_faults) == 2
    assert _run(sim, generator, 50, keep=True) == [], "新的那個佔著名額"


# ── 4. 設定 ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad", [
    {"mean_days_between_faults": 0}, {"mean_days_between_faults": "x"}, {"wear_gain": -1},
    {"min_hours_to_full": 5, "max_hours_to_full": 1}, {"min_hours_to_full": 0}, {"max_active_per_turbine": 0},
    {"max_active_per_turbine": 1.5}, {"seed": "a"}, {"scenario_weights": {"no_such_fault": 1}},
    {"scenario_weights": {"bearing_wear": -1}}, {"turbine_weights": [1, 2]}, {"unknown_field": 1},
    {"mean_days_between_faults": float("nan")}, {"enabled": "false"}, {"enabled": 0},
    {"fatigue_reference": 0}, {"fouling_reference": -1},
])
def test_bad_settings_are_rejected(bad: dict) -> None:
    with pytest.raises(ValueError):
        FaultGeneratorConfig.from_dict({"enabled": True, **bad})


def test_settings_round_trip() -> None:
    config = _config(scenario_weights={"bearing_wear": 2}, turbine_weights={"WT001": 0.5}, seed=5)
    assert FaultGeneratorConfig.from_dict(config.to_dict()) == config
    assert FaultGeneratorConfig.from_dict({}) == FaultGeneratorConfig()
