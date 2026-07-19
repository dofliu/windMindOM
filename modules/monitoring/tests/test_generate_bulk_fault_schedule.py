"""Scenario 模式：generate_bulk 排程故障注入（WMOM-20260718-03, DEC-20260718-01）。

背景：Scenario 模式讓使用者定義「風場 + 風況 + 時長 + 故障排程」→ 一次批次生成
可重現資料集。核心新增能力是 ``WindFarmSimulator.generate_bulk`` 能於指定 sim-time
注入故障，讓資料集包含該故障的發展；`/api/config/simulation/generate-bulk` 端點
以 ``_parse_fault_schedule`` 驗證使用者排程後接上此能力。

本檔驗證兩段（皆不需啟動 broker / HTTP / 背景執行緒）：
1. 引擎層 ``generate_bulk(fault_schedule=...)`` 的排程注入行為（到點才注入、回呼、trip）。
2. 端點層 ``_parse_fault_schedule`` 的解析與驗證（at_hour↔offset、排序、未知情境/機組、負值）。
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "modules" / "monitoring"))

from fastapi import HTTPException  # noqa: E402
from simulator.engine import WindFarmSimulator  # noqa: E402
from simulator.physics.fault_engine import TestPlanStep as PlanStep  # noqa: E402
from server.routers.config import _parse_fault_schedule  # noqa: E402


# ─── 引擎層：generate_bulk 排程注入 ────────────────────────────────────────

def _running_sim(turbine_count: int = 3) -> WindFarmSimulator:
    """建一個可同步跑 generate_bulk 的 simulator（不啟背景 loop 執行緒）。"""
    sim = WindFarmSimulator(turbine_count=turbine_count)
    sim._running = True  # generate_bulk 迴圈以此為續跑條件
    return sim


def test_scheduled_fault_injected_at_offset_zero():
    """offset 0 的故障於批次開始即注入，並隨批次進程累積 severity。"""
    sim = _running_sim()
    schedule = [PlanStep(offset_seconds=0.0, scenario_id="hydraulic_leak",
                         turbine_id="WT002", severity_rate=0.001)]

    sim.generate_bulk(duration_hours=0.05, time_step=10.0, fault_schedule=schedule)  # 18 steps

    active = sim.fault_engine.active_faults
    assert len(active) == 1
    assert active[0].scenario_id == "hydraulic_leak"
    assert active[0].turbine_id == "WT002"
    assert active[0].severity > 0.0, "注入後應隨每步 fault_engine.step 累積 severity"


def test_scheduled_fault_not_injected_before_its_offset():
    """offset 超過本次批次總長 → 從未注入（Scenario 的故障是「稍後才發生」）。"""
    sim = _running_sim()
    # 180s 的批次；offset 1000s 永遠不會到。
    schedule = [PlanStep(offset_seconds=1000.0, scenario_id="bearing_wear",
                         turbine_id="WT001", severity_rate=0.001)]

    sim.generate_bulk(duration_hours=0.05, time_step=10.0, fault_schedule=schedule)

    assert sim.fault_engine.active_faults == []


def test_on_fault_injected_callback_fires_once_with_step_and_simtime():
    """注入當下以 (step, sim_time) 回呼一次；sim_time 為 datetime，端點用它寫模擬時間戳。"""
    sim = _running_sim()
    injected: list[tuple[PlanStep, datetime]] = []
    schedule = [PlanStep(offset_seconds=0.0, scenario_id="yaw_sensor_drift",
                         turbine_id="WT003", severity_rate=0.001)]

    sim.generate_bulk(duration_hours=0.05, time_step=10.0, fault_schedule=schedule,
                      on_fault_injected=lambda step, st: injected.append((step, st)))

    assert len(injected) == 1
    step, sim_time = injected[0]
    assert step.scenario_id == "yaw_sensor_drift"
    assert step.turbine_id == "WT003"
    assert isinstance(sim_time, datetime), "sim_time 應為 datetime，供 record_event 用模擬時間戳"


def test_multiple_faults_at_same_offset_all_injected_in_one_step():
    """同一 offset 的多支故障於同一 step 全部注入（守住 engine 的 while 迴圈，不是 if）。"""
    sim = _running_sim()
    schedule = [
        PlanStep(offset_seconds=0.0, scenario_id="bearing_wear", turbine_id="WT001", severity_rate=0.001),
        PlanStep(offset_seconds=0.0, scenario_id="yaw_sensor_drift", turbine_id="WT002", severity_rate=0.001),
        PlanStep(offset_seconds=0.0, scenario_id="hydraulic_leak", turbine_id="WT003", severity_rate=0.001),
    ]

    sim.generate_bulk(duration_hours=0.02, time_step=10.0, fault_schedule=schedule)

    active = {(f.scenario_id, f.turbine_id) for f in sim.fault_engine.active_faults}
    assert active == {
        ("bearing_wear", "WT001"),
        ("yaw_sensor_drift", "WT002"),
        ("hydraulic_leak", "WT003"),
    }


def test_unknown_scenario_in_schedule_is_skipped_without_callback():
    """引擎層防禦：未知 scenario → inject 回 False → 不注入也不回呼。"""
    sim = _running_sim()
    injected: list[PlanStep] = []
    schedule = [PlanStep(offset_seconds=0.0, scenario_id="does_not_exist",
                         turbine_id="WT001", severity_rate=0.001)]

    sim.generate_bulk(duration_hours=0.02, time_step=10.0, fault_schedule=schedule,
                      on_fault_injected=lambda step, st: injected.append(step))

    assert sim.fault_engine.active_faults == []
    assert injected == []


def test_no_schedule_generates_data_without_faults():
    """回歸：不帶 fault_schedule 時行為不變——照常產資料、零故障。"""
    sim = _running_sim(turbine_count=2)

    total = sim.generate_bulk(duration_hours=0.02, time_step=10.0)  # 7 steps × 2 turbines

    assert total > 0
    assert sim.fault_engine.active_faults == []


def test_scheduled_fault_progresses_to_trip():
    """注入 → severity 進程 → 到 auto_trip 門檻跳機，證明排定故障真的驅動物理。"""
    sim = _running_sim()
    # generator_overspeed auto_trip=0.6；rate 0.05/s × dt 10 = 每步 +0.5 → 兩步內跳機。
    schedule = [PlanStep(offset_seconds=0.0, scenario_id="generator_overspeed",
                         turbine_id="WT002", severity_rate=0.05)]

    sim.generate_bulk(duration_hours=0.05, time_step=10.0, fault_schedule=schedule)

    wt002 = [f for f in sim.fault_engine.active_faults if f.turbine_id == "WT002"]
    assert wt002, "故障應仍在 active 清單"
    assert wt002[0].tripped, "severity 應達 auto_trip_severity 而跳機"


# ─── 端點層：_parse_fault_schedule 解析與驗證 ──────────────────────────────

def _ids() -> set[str]:
    return {"WT001", "WT002", "WT003"}


def test_parse_empty_schedule_returns_empty():
    assert _parse_fault_schedule([], _ids()) == []


def test_parse_at_hour_converts_to_offset_seconds():
    steps = _parse_fault_schedule(
        [{"scenario_id": "hydraulic_leak", "turbine_id": "WT002", "at_hour": 2}], _ids())
    assert len(steps) == 1
    assert steps[0].offset_seconds == 7200.0
    assert steps[0].scenario_id == "hydraulic_leak"
    assert steps[0].turbine_id == "WT002"


def test_parse_offset_seconds_takes_precedence_over_at_hour():
    steps = _parse_fault_schedule(
        [{"scenario_id": "bearing_wear", "turbine_id": "WT001",
          "at_hour": 5, "offset_seconds": 30}], _ids())
    assert steps[0].offset_seconds == 30.0


def test_parse_sorts_by_offset():
    steps = _parse_fault_schedule([
        {"scenario_id": "bearing_wear", "turbine_id": "WT001", "at_hour": 5},
        {"scenario_id": "yaw_sensor_drift", "turbine_id": "WT003", "at_hour": 1},
    ], _ids())
    assert [s.offset_seconds for s in steps] == [3600.0, 18000.0]


def test_parse_defaults_severity_rate_and_initial():
    steps = _parse_fault_schedule(
        [{"scenario_id": "bearing_wear", "turbine_id": "WT001"}], _ids())
    assert steps[0].severity_rate == 0.0002
    assert steps[0].initial_severity == 0.0
    assert steps[0].offset_seconds == 0.0


def test_parse_unknown_scenario_raises_404():
    with pytest.raises(HTTPException) as ei:
        _parse_fault_schedule([{"scenario_id": "nope", "turbine_id": "WT001"}], _ids())
    assert ei.value.status_code == 404


def test_parse_unknown_turbine_raises_404():
    with pytest.raises(HTTPException) as ei:
        _parse_fault_schedule([{"scenario_id": "bearing_wear", "turbine_id": "WT999"}], _ids())
    assert ei.value.status_code == 404


def test_parse_negative_offset_raises_400():
    with pytest.raises(HTTPException) as ei:
        _parse_fault_schedule(
            [{"scenario_id": "bearing_wear", "turbine_id": "WT001", "offset_seconds": -10}], _ids())
    assert ei.value.status_code == 400


def test_parse_non_dict_entry_raises_400():
    with pytest.raises(HTTPException) as ei:
        _parse_fault_schedule(["not-a-dict"], _ids())
    assert ei.value.status_code == 400


def test_parse_raw_not_a_list_raises_400():
    with pytest.raises(HTTPException) as ei:
        _parse_fault_schedule(123, _ids())  # type: ignore[arg-type]
    assert ei.value.status_code == 400


def test_parse_non_numeric_offset_raises_400():
    """畸形數值（字串）→ 乾淨 400，而非未預期 500。"""
    with pytest.raises(HTTPException) as ei:
        _parse_fault_schedule(
            [{"scenario_id": "bearing_wear", "turbine_id": "WT001", "offset_seconds": "soon"}], _ids())
    assert ei.value.status_code == 400


def test_parse_none_severity_rate_raises_400():
    """畸形數值（None）→ 乾淨 400，而非未預期 500。"""
    with pytest.raises(HTTPException) as ei:
        _parse_fault_schedule(
            [{"scenario_id": "bearing_wear", "turbine_id": "WT001", "severity_rate": None}], _ids())
    assert ei.value.status_code == 400


# ─── 大 time_step 數值穩定性（WMOM-20260718-10）──────────────────────────────

def test_generate_bulk_large_timestep_stays_finite():
    """大 time_step（60s）+ moderate 風況不再讓 rotor speed 數值發散→inf。

    根因：物理積分在 dt>~5s 會發散（rotor speed 爆到 ~1e5 rpm → imbalance **2 overflow →
    inf → Modbus/round 崩）。修法＝generate_bulk 把每個輸出步拆成 ≤5s 的子步跑物理。
    本測試用會觸發發散的 moderate profile 跑 30 個 60s 輸出步，守住「輸出全為有限、
    rotor speed 維持物理範圍」。
    """
    import math

    sim = _running_sim(turbine_count=3)
    sim.wind_model.set_profile("moderate")

    seen = {"bad": 0, "max_rotspd": 0.0}

    def cb(readings):
        for r in readings:
            scada = r.get("scada", {})
            for v in scada.values():
                if isinstance(v, (int, float)) and not math.isfinite(v):
                    seen["bad"] += 1
            rs = scada.get("WROT_RotSpd", 0.0)
            if isinstance(rs, (int, float)) and math.isfinite(rs):
                seen["max_rotspd"] = max(seen["max_rotspd"], abs(rs))

    # 0.5h @ 60s = 30 輸出步（每步 12 子步）——遠超原本 <14 步就發散的門檻。
    sim.generate_bulk(duration_hours=0.5, time_step=60.0, callback=cb)

    assert seen["bad"] == 0, "大 time_step 不應產生非有限值（子步穩定化後）"
    assert seen["max_rotspd"] < 100.0, f"rotor speed 應維持物理範圍，實得 {seen['max_rotspd']:.0f} rpm"
