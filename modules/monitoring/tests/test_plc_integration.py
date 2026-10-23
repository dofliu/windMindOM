"""PLC 保護層整合測試（WMOM-20261021-03-b，EPIC-DS Phase 1b-b）。

引擎層驗證「故障物理 → 量測訊號越過真實設定值 → PLC 送出真實事件碼並跳機 → 故障轉為
tripped」整條鏈，以及健康風場不會被訊號判定誤跳：

1. 11 個故障情境在高負載（15 m/s、25 °C）滿嚴重度下，PLC 都以該情境的預期跳機碼跳機
2. 跳機後的停機模式依手冊等級：T1 正常伺服停機（9）、T2 緊急變槳（7）
3. 健康風場（自動風況，含紊流、偏航）2 h 內沒有任何訊號判定的事件
4. 重複的保護停機照目錄每碼計數，超過每小時上限送 A039、機組進 SHUTDOWN，操作員復位才重啟；
   低風速反覆起停不受限（手冊沒有全域啟動次數上限，WMOM-20261022-02）
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import pytest

import simulator.engine as engine_mod
from simulator.engine import WindFarmSimulator
from simulator.physics.fault_engine import FAULT_SCENARIOS
from simulator.physics.plc_protection import PlcEvent

DT = 5.0
PRODUCING = 6
T0 = datetime(2026, 1, 1, 0, 0, 0)


def _sim(wind: float = 15.0) -> WindFarmSimulator:
    sim = WindFarmSimulator(turbine_count=1)
    sim.wind_model.set_override(wind_speed=wind, wind_direction=180.0, ambient_temp=25.0)
    return sim


def _run_until_tripped(scenario_id: str) -> Tuple[WindFarmSimulator, List[PlcEvent], List[int]]:
    sim = _sim()
    model = sim.turbines["WT001"]
    events: List[PlcEvent] = []
    states: List[int] = []
    i = 0
    while model.tur_state != PRODUCING:
        sim._run_one_step(T0 + timedelta(seconds=i * DT), DT)
        events += model.plc.drain_events()
        i += 1
        assert i < 200, "前置條件：機組應在 1000 s 內併網發電"
    # 再穩定發電 2 分鐘（葉片差異在併網 60 s 後才判定）
    for _ in range(24):
        sim._run_one_step(T0 + timedelta(seconds=i * DT), DT)
        events += model.plc.drain_events()
        i += 1
    assert sim.fault_engine.inject(scenario_id, "WT001", severity_rate=0.0, initial_severity=1.0)
    fault = sim.fault_engine.active_faults[0]
    for _ in range(int(3 * 3600 / DT)):
        sim._run_one_step(T0 + timedelta(seconds=i * DT), DT)
        events += model.plc.drain_events()
        states.append(model.tur_state)
        i += 1
        if fault.tripped:
            for _ in range(6):  # 再跑 30 s 看停機模式
                sim._run_one_step(T0 + timedelta(seconds=i * DT), DT)
                events += model.plc.drain_events()
                states.append(model.tur_state)
                i += 1
            break
    return sim, events, states


# nuisance 情境不鎖機組、不轉 tripped（Pt100 接觸不良另見 test_nuisance_events.py）
FAULT_IDS = sorted(sid for sid, sc in FAULT_SCENARIOS.items() if sc.category != "nuisance")


@pytest.mark.parametrize("scenario_id", FAULT_IDS)
def test_full_severity_fault_trips_turbine_with_expected_code(scenario_id: str) -> None:
    sim, events, states = _run_until_tripped(scenario_id)
    fault = sim.fault_engine.active_faults[0]
    scenario = FAULT_SCENARIOS[scenario_id]
    expected_trips = {a["code"]: a["type"] for a in scenario.alarm_codes if a["type"] in ("T1", "T2")}

    assert fault.tripped, f"{scenario_id} 3 h 內沒有跳機；PLC 事件={[(e.kind, e.code) for e in events]}"
    assert fault.trip_code in expected_trips
    trip_events = [e for e in events if e.kind == "trip" and e.code == fault.trip_code]
    assert trip_events, "跳機必須有對應的 PLC trip 事件"
    assert PRODUCING != states[-1]

    # 本層判定的跳機依手冊等級選停機模式（物理層保護停機——超速、電網——由物理層自己決定）
    if trip_events[0].source == "signal":
        stop_state = 7 if expected_trips[fault.trip_code] == "T2" else 9
        assert stop_state in states, f"{scenario_id} 跳機後應進入 {stop_state}，states={states[-8:]}"


def test_alarm_precedes_trip_for_bearing_wear_ramp() -> None:
    """嚴重度逐漸升高時，主軸承先出 A262 警報、之後才 T240 跳機。"""
    sim = _sim()
    model = sim.turbines["WT001"]
    events: List[PlcEvent] = []
    i = 0
    while model.tur_state != PRODUCING:
        sim._run_one_step(T0 + timedelta(seconds=i * DT), DT)
        i += 1
    sim.fault_engine.inject("bearing_wear", "WT001", severity_rate=1.0 / 7200.0)
    fault = sim.fault_engine.active_faults[0]
    for _ in range(int(3 * 3600 / DT)):
        sim._run_one_step(T0 + timedelta(seconds=i * DT), DT)
        events += model.plc.drain_events()
        i += 1
        if fault.tripped:
            break
    kinds = [(e.kind, e.code) for e in events]
    assert ("alarm_raised", 262) in kinds and ("trip", 240) in kinds
    assert kinds.index(("alarm_raised", 262)) < kinds.index(("trip", 240))


def test_healthy_farm_has_no_signal_judged_events(monkeypatch: pytest.MonkeyPatch) -> None:
    # 釘住起點：日夜 / 季節循環依模擬時刻，否則每次跑的風況不同（12 h 多起點見 test_healthy_blade_sync.py）
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(engine_mod, "utc_now", lambda: t0)
    sim = WindFarmSimulator(turbine_count=3)
    events: List[PlcEvent] = []

    def collect(_readings: list) -> None:
        for model in sim.turbines.values():
            events.extend(model.plc.drain_events())

    sim.generate_bulk(duration_hours=2.0, time_step=5.0, callback=collect)
    signal_events = [(e.kind, e.code) for e in events if e.source == "signal"]
    assert signal_events == []


@pytest.mark.parametrize("preset", ["vestas_v90_3mw", "sg_8mw", "goldwind_2.5mw"])
def test_other_presets_run_healthy_without_plc_events(preset: str) -> None:
    """非 Z72 機型（前端可選）共用 Z72 的 PLC 設定值：熱模型以額定功率正規化，健康機組不得被溫度保護跳機。

    修正前 8 MW 機型在 12 m/s、30 °C 約 3 分鐘就 A420 → T437 / T021，之後自動重啟被封鎖。
    """
    from simulator.physics.turbine_physics import TURBINE_PRESETS, TurbinePhysicsModel

    model = TurbinePhysicsModel(spec=TURBINE_PRESETS[preset], seed=3)
    events = []
    for _ in range(int(1.5 * 3600 / 5)):
        model.step(wind_speed=12.0, wind_direction=180.0, ambient_temp=30.0, dt=5.0)
        events += [(e.kind, e.code) for e in model.plc.drain_events() if e.kind != "info"]
    assert events == [] and model.tur_state == 6


@pytest.mark.parametrize(("fault", "code"), [
    ("generator_overspeed", 351),       # 351 每小時上限 5：第 6 次封鎖
    ("grid_voltage_sag", 481),          # 481 / 021 每小時上限 1：第 2 次封鎖
])
def test_repeated_protection_trips_block_with_a039_until_operator_reset(fault: str, code: int) -> None:
    from shared.alarm_codes import get_alarm
    from simulator.physics.turbine_physics import TurbinePhysicsModel

    limit = get_alarm(code).max_per_hour
    assert limit is not None
    trips_before_block = limit + 1        # 一小時內第 (上限 + 1) 次跳機時封鎖
    model = TurbinePhysicsModel(seed=7)
    model.active_faults = [{"scenario_id": fault, "severity": 1.0}]
    events: List[Tuple[str, int]] = []
    for _ in range(int(3600 / DT)):
        model.step(wind_speed=14.0, wind_direction=180.0, ambient_temp=20.0, dt=DT)
        events += [(e.kind, e.code) for e in model.plc.drain_events()]
    assert events.count(("trip", code)) == trips_before_block
    assert events.count(("alarm_raised", 39)) == 1
    assert model.plc.auto_restart_blocked and model.tur_state == 1      # SHUTDOWN
    model.active_faults = []
    model.cmd_reset()
    for _ in range(int(600 / DT)):
        model.step(wind_speed=14.0, wind_direction=180.0, ambient_temp=20.0, dt=DT)
    events = [(e.kind, e.code) for e in model.plc.drain_events()]
    assert events[:2] == [("operator_reset", 8), ("alarm_cleared", 39)]
    assert model.tur_state == PRODUCING


def test_low_wind_start_stop_cycling_is_not_limited() -> None:
    """風速在切入風速附近擺動：正常起停不算跳機，不受每小時次數限制、也不送事件（舊版全域 3 次上限會卡住待機）。"""
    import math

    from simulator.physics.turbine_physics import TurbinePhysicsModel

    model = TurbinePhysicsModel(seed=7)
    starts = 0
    prev = model.tur_state
    for i in range(int(3 * 3600)):
        wind = 3.3 + 0.9 * math.sin(2 * math.pi * i / 600.0)
        model.step(wind_speed=wind, wind_direction=180.0, ambient_temp=20.0, dt=1.0)
        starts += model.tur_state == 4 and prev != 4
        prev = model.tur_state
    assert starts >= 15                              # 每 10 分鐘一個風速週期都能起動
    assert not model.plc.auto_restart_blocked
    assert [e for e in model.plc.drain_events() if e.kind != "info"] == []
