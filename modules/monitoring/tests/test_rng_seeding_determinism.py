"""RNG 種子化 for #WMOM-20260927-01。

`GridEnvironmentModel`（grid frequency/voltage 噪聲）與 `YawModel`（brake_pressure
噪聲）先前直接呼叫全域未種子化的 `np.random.normal(...)`，跟其餘 codebase（
`turbine_physics.py`/`vibration_model.py`/`fatigue_model.py`/`wind_field.py` 等）
一律用 `np.random.RandomState(seed)` 建立各自種子化 `self._rng` 的慣例不一致——
導致同一組 seed 重跑 `WindFarmSimulator` 兩次，grid 噪聲與 yaw brake_pressure 噪聲
每次進程啟動皆不同，模擬結果無法逐位元重現（WMOM-20260505-24 修復過程中發現：同一
測試計畫重跑，個體差異 spread 數字每次略有浮動）。

修法：`YawModel` 建構子新增 `seed` 參數並建立 `self._rng`，`TurbinePhysicsModel`
比照既有 `VibrationModel(seed=_seed)` 同款把 `_seed` 傳入 `YawModel`；
`GridEnvironmentModel` 建構子新增 `seed` 參數，`WindFarmSimulator.__init__` 傳入
固定 farm-level seed（比照既有 `_turbulence_gen` seed=42 / `_per_turbine_wind`
seed=99 慣例，這是單一 shared farm-level 模型、非逐風機）。
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

from simulator.engine import WindFarmSimulator  # noqa: E402
from simulator.grid_model import GridEnvironmentModel  # noqa: E402
from simulator.physics.yaw_model import YawModel  # noqa: E402


def test_grid_model_seeded_determinism():
    """同一 seed 的兩個 GridEnvironmentModel，對同一序列 timestamp/profile 應逐位元重現。

    只涵蓋 auto（nominal）+ `low_freq` override 兩條分支——`recovery` profile 的
    `elapsed` 是相對 `set_profile()` 呼叫當下 `datetime.now()`（真實牆鐘時間）計算，
    這本身是與本 issue（RNG 種子化）無關的既有非決定性（不同次呼叫的牆鐘時間本就不同），
    不在本次驗收範圍內，故不在此測試中觸發。
    """
    base_time = datetime(2026, 1, 1, 0, 0, 0)
    timestamps = [base_time + timedelta(seconds=i * 5) for i in range(20)]

    def _run(seed: int):
        model = GridEnvironmentModel(seed=seed)
        freqs, volts = [], []
        for i, ts in enumerate(timestamps):
            if i == 5:
                model.set_profile("low_freq")
            freqs.append(model.get_frequency(ts))
            volts.append(model.get_voltage(ts))
        return freqs, volts

    freqs_a, volts_a = _run(seed=123)
    freqs_b, volts_b = _run(seed=123)
    assert freqs_a == freqs_b
    assert volts_a == volts_b


def test_grid_model_different_seed_diverges():
    """不同 seed 應得到不同噪聲序列（避免「回傳常數」這種退化實作誤判過關本測試）。"""
    ts = datetime(2026, 1, 1, 0, 0, 0)
    model_a = GridEnvironmentModel(seed=1)
    model_b = GridEnvironmentModel(seed=2)
    freqs_a = [model_a.get_frequency(ts + timedelta(seconds=i)) for i in range(5)]
    freqs_b = [model_b.get_frequency(ts + timedelta(seconds=i)) for i in range(5)]
    assert freqs_a != freqs_b


def test_yaw_model_seeded_determinism():
    """同一 seed 的兩個 YawModel，對同一序列輸入（含觸發 unwind 分支）應逐位元重現。"""

    def _run(seed: int):
        model = YawModel(seed=seed)
        model.cable_windup = 3.0  # 預先製造大 cable twist，觸發 unwind 分支
        wind_dirs = [270.0, 270.0, 90.0, 90.0, 90.0, 90.0, 90.0, 90.0, 90.0, 90.0]
        return [model.step(wind_direction=wd, is_producing=True, dt=1.0) for wd in wind_dirs]

    out_a = _run(seed=42)
    out_b = _run(seed=42)
    assert out_a == out_b
    # 確認測試真的有觸發一般 yaw 分支（否則以上比對是同義反覆）
    assert any(o["is_yawing"] == 1.0 for o in out_a)


def test_yaw_model_different_seed_diverges():
    """不同 seed 的 brake_pressure 噪聲序列應不同。"""
    model_a = YawModel(seed=1)
    model_b = YawModel(seed=2)
    pressures_a = [model_a.step(270.0, True, 1.0)["brake_pressure"] for _ in range(5)]
    pressures_b = [model_b.step(270.0, True, 1.0)["brake_pressure"] for _ in range(5)]
    assert pressures_a != pressures_b


def test_farm_level_readings_are_byte_reproducible_across_instances():
    """驗收條件：同一組 seed 的兩個獨立 `WindFarmSimulator` 實例，對同一序列
    `sim_time` 跑 `_run_one_step` 應逐欄逐列數值相同——不用真的跑數小時
    `generate_data()`（太慢），`_run_one_step` 是 `_loop`/`generate_bulk` 共用的
    單步核心，足以驗證 grid_model + yaw 兩者種子化後farm-level 整體可重現。"""
    base_time = datetime(2026, 1, 1, 0, 0, 0)

    def _run():
        sim = WindFarmSimulator(turbine_count=2)
        sim_time = base_time
        all_readings = []
        for _ in range(10):
            sim_time += timedelta(seconds=1)
            all_readings.append(sim._run_one_step(sim_time, 1.0))
        return all_readings

    readings_a = _run()
    readings_b = _run()
    assert readings_a == readings_b
