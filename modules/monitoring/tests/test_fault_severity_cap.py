"""故障嚴重度上限 ``max_severity``（WMOM-20261021-08-d，早期徵兆題）。

- ``FaultEngine.inject(max_severity=)``：嚴重度停在上限不再惡化；範圍外或小於起始嚴重度直接拒絕
- 標準答案的 ``injection.max_severity`` 記下上限
- 壓在警報門檻之下的故障整段都不出警報，但訊號已偏離健康機組（早期徵兆）
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import pytest

from simulator.engine import WindFarmSimulator
from simulator.ground_truth import GroundTruthRecorder
from simulator.physics.fault_engine import FaultEngine
from simulator.physics.fault_engine import TestPlanStep as PlanStep  # pytest 會想收集 Test* 類別

T0 = datetime(2026, 1, 1)
DT = 5.0


def test_severity_stops_at_the_cap() -> None:
    engine = FaultEngine()
    assert engine.inject("bearing_wear", "WT001", severity_rate=0.01, initial_severity=0.2, max_severity=0.5)
    for _ in range(100):
        engine.step(dt=1.0)
    assert engine.active_faults[0].severity == pytest.approx(0.5)
    assert engine.active_faults[0].max_severity == 0.5
    engine.inject("hydraulic_leak", "WT002", severity_rate=0.01)
    for _ in range(200):
        engine.step(dt=1.0)
    assert engine.active_faults[1].severity == 1.0, "預設上限 1.0 與原本相同"


@pytest.mark.parametrize("initial, cap", [(0.0, 0.0), (0.0, 1.2), (0.0, -0.1), (0.6, 0.5)])
def test_invalid_cap_is_rejected(initial: float, cap: float) -> None:
    engine = FaultEngine()
    with pytest.raises(ValueError):
        engine.inject("bearing_wear", "WT001", initial_severity=initial, max_severity=cap)
    assert engine.active_faults == []


def test_ground_truth_records_the_cap() -> None:
    rec = GroundTruthRecorder(["WT001"])
    rec.on_fault_injected(PlanStep(0.0, "bearing_wear", "WT001", 0.0002, 0.0, 0.5), T0)
    gt = rec.build(scenario_id=1, scenario_name="x", site_timezone="UTC",
                   sim_start="2026-01-01T00:00:00.000000+00:00", sim_end="2026-01-01T01:00:00.000000+00:00")
    assert gt["cases"][0]["injection"]["max_severity"] == 0.5


def test_capped_bearing_wear_shows_in_the_signal_but_never_alarms() -> None:
    """額定風速 3 h：上限 0.5 的主軸承磨耗（262 約 0.88 才出）整段沒有警報，軸承溫度卻比健康機組高。"""
    sim = WindFarmSimulator(turbine_count=2)
    sim.wind_model.set_override(wind_speed=13.0, wind_direction=180.0, ambient_temp=25.0)
    models = sim.turbines
    i = 0
    while any(m.tur_state != 6 for m in models.values()):
        sim._run_one_step(T0 + timedelta(seconds=i * DT), DT)
        i += 1
        assert i < 400
    for m in models.values():
        m.plc.drain_events()
    assert sim.fault_engine.inject("bearing_wear", "WT001", severity_rate=0.001, max_severity=0.5)
    events = []
    readings = []
    for _ in range(int(3 * 3600 / DT)):
        readings = sim._run_one_step(T0 + timedelta(seconds=i * DT), DT)
        i += 1
        events += [(e.kind, e.code) for e in models["WT001"].plc.drain_events() if e.kind != "info"]
    assert events == [] and models["WT001"].tur_state == 6
    assert sim.fault_engine.active_faults[0].severity == pytest.approx(0.5)
    by_turbine = {r["turbine_id"]: r for r in readings}
    faulty = by_turbine["WT001"]["scada"]["WGEN_GnBrgTmp1"]
    healthy = by_turbine["WT002"]["scada"]["WGEN_GnBrgTmp1"]
    assert faulty > healthy + 3.0, (faulty, healthy)
