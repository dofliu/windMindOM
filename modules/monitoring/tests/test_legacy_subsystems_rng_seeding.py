"""Legacy `subsystems.py`（`WindTurbine`/`main.py` 路徑）RNG 種子化 for #WMOM-20260927-03。

`GearboxSystem.calculate()`（vibration_level 噪聲）與 `HydraulicSystem.calculate()`
（pressure 噪聲）先前直接呼叫全域未種子化的 `np.random.normal(...)`，跟
WMOM-20260927-01 修復的 `simulator/grid_model.py`/`simulator/physics/yaw_model.py`
是同一類問題，但這是完全獨立的 code path——只被 `modules/monitoring/main.py` 的
legacy `WindFarmSimulator`/`WindTurbine`（非 `simulator/engine.py` 目前主要模擬
路徑）引用。

投產前已確認：`main.py`/`turbine_model.py`/`subsystems.py` 這條 legacy 路徑未被
`run.py`、`api/`、任何 Docker/docker-compose 設定、或既有測試引用（純歷史原型
程式碼，被 `modules/monitoring/simulator/` 取代），故不影響任何 demo/deploy 流程。
修法比照 -01：建構子新增 `seed` 參數，預設 `None` 維持既有（未種子化）行為，呼叫端
可選擇性傳入以取得逐位元可重現的結果。
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

from subsystems import GearboxSystem, HydraulicSystem  # noqa: E402
from turbine_model import WindTurbine  # noqa: E402


def test_gearbox_system_seeded_determinism():
    """同一 seed 的兩個 GearboxSystem，對同一序列輸入應逐位元重現 vibration_level。"""

    def _run(seed: int):
        gearbox = GearboxSystem(seed=seed)
        return [gearbox.calculate(input_speed=1500.0, input_torque=8000.0)["vibration"]
                for _ in range(10)]

    assert _run(seed=42) == _run(seed=42)


def test_gearbox_system_different_seed_diverges():
    """不同 seed 應得到不同的 vibration_level 噪聲序列（避免退化實作誤判過關）。"""
    gearbox_a = GearboxSystem(seed=1)
    gearbox_b = GearboxSystem(seed=2)
    vib_a = [gearbox_a.calculate(1500.0, 8000.0)["vibration"] for _ in range(5)]
    vib_b = [gearbox_b.calculate(1500.0, 8000.0)["vibration"] for _ in range(5)]
    assert vib_a != vib_b


def test_gearbox_system_default_seed_none_still_random():
    """`seed=None`（預設值，既有呼叫端未修改的行為）仍應維持未種子化的隨機性。"""
    gearbox_a = GearboxSystem()
    gearbox_b = GearboxSystem()
    vib_a = [gearbox_a.calculate(1500.0, 8000.0)["vibration"] for _ in range(5)]
    vib_b = [gearbox_b.calculate(1500.0, 8000.0)["vibration"] for _ in range(5)]
    assert vib_a != vib_b


def test_hydraulic_system_seeded_determinism():
    """同一 seed 的兩個 HydraulicSystem，對同一序列呼叫應逐位元重現 pressure。"""

    def _run(seed: int):
        hydraulic = HydraulicSystem(seed=seed)
        return [hydraulic.calculate()["pressure"] for _ in range(10)]

    assert _run(seed=7) == _run(seed=7)


def test_hydraulic_system_different_seed_diverges():
    """不同 seed 應得到不同的 pressure 噪聲序列。"""
    hydraulic_a = HydraulicSystem(seed=1)
    hydraulic_b = HydraulicSystem(seed=2)
    p_a = [hydraulic_a.calculate()["pressure"] for _ in range(5)]
    p_b = [hydraulic_b.calculate()["pressure"] for _ in range(5)]
    assert p_a != p_b


def test_wind_turbine_seeded_determinism_end_to_end():
    """驗收條件：同一 seed 的兩個獨立 `WindTurbine` 實例，對同一序列
    `simulate_step()` 呼叫應逐位元重現（含 gearbox vibration + hydraulic pressure
    兩條噪聲來源）。"""
    from datetime import datetime, timedelta

    base_time = datetime(2026, 1, 1, 0, 0, 0)

    def _run():
        turbine = WindTurbine(turbine_id="WT001", seed=99)
        outputs = []
        for i in range(10):
            ts = base_time + timedelta(seconds=i)
            outputs.append(turbine.simulate_step(wind_speed=10.0, wind_direction=270.0, timestamp=ts))
        return outputs

    outputs_a = _run()
    outputs_b = _run()
    assert outputs_a == outputs_b
    # 確認測試真的有跑進 RUNNING 分支觸發兩條噪聲來源（否則以上比對是同義反覆）
    assert any(o["operational_state"] == "RUNNING" for o in outputs_a)


def test_wind_turbine_different_seeds_diverge_end_to_end():
    """不同 seed 的兩個 `WindTurbine` 應得到不同的完整輸出序列。"""
    from datetime import datetime, timedelta

    base_time = datetime(2026, 1, 1, 0, 0, 0)

    def _run(seed: int):
        turbine = WindTurbine(turbine_id="WT001", seed=seed)
        outputs = []
        for i in range(5):
            ts = base_time + timedelta(seconds=i)
            outputs.append(turbine.simulate_step(wind_speed=10.0, wind_direction=270.0, timestamp=ts))
        return outputs

    assert _run(seed=1) != _run(seed=2)


def test_gearbox_and_hydraulic_noise_are_not_correlated_when_sharing_one_wind_turbine_seed():
    """`WindTurbine(seed=...)` 應對 gearbox/hydraulic 兩條噪聲來源套用不同的實際
    seed（各自偏移，比照 `simulator/physics/wind_field.py` 既有 seed+1000/+2000
    慣例），而非把同一個 seed 原封不動餵給兩個獨立 `RandomState`——後者會造成兩條
    物理上無關的噪聲彼此呈固定比例（sigma 比例 0.5/0.1=5.0）的退化相關性，是比
    「完全不種子化」更糟的合成資料假象。

    用 `input_speed=0`/`input_torque=0` 讓 `GearboxSystem.calculate()` 的
    `output_speed/10000` 項歸零，分離出純噪聲項（`vibration - 0.5`），與
    `HydraulicSystem` 第一次呼叫的純噪聲項（`pressure - 150.0`，初始值扣除）比較。
    若兩者共用同一 seed，這個比例必為固定的 5.0；獨立隨機序列則幾乎必然不是。
    """
    turbine = WindTurbine(turbine_id="WT001", seed=99)
    gearbox_noise = turbine.gearbox.calculate(input_speed=0.0, input_torque=0.0)["vibration"] - 0.5
    hydraulic_noise = turbine.hydraulic_system.calculate()["pressure"] - 150.0
    assert gearbox_noise != 0.0
    assert round(hydraulic_noise / gearbox_noise, 6) != 5.0
