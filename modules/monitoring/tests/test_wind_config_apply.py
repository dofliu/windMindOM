"""風況設定套用 + 風速→發電 驗證（WMOM-20260718-01）。

背景：`POST /api/config/simulation` 的 in-place 分支之前只套 turbulence、把
`baseWindSpeed` 丟掉，導致「Settings 改風速對跑著的 sim 無反應」。修法改用
`wind_model.set_override(wind_speed=..., turbulence=...)` 讓 base wind 真的生效。

本檔驗證修法所依賴的兩段鏈路（不需啟動 broker / HTTP）：
1. `WindEnvironmentModel.set_override` 確實把風速/turbulence 記進 model 狀態。
2. 送進 turbine physics 的風速確實驅動發電（高風→額定附近；靜風→~0）。
兩段接起來即「改風速 → 發電對應」，也就是使用者反映的問題。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
MONITORING_ROOT = REPO_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

from wind_model import WindEnvironmentModel  # noqa: E402
from simulator.physics import TurbinePhysicsModel  # noqa: E402


def test_set_override_records_wind_and_turbulence():
    """set_override 把 base wind + turbulence 寫進 model（修好的端點就是呼叫這個）。"""
    wm = WindEnvironmentModel()
    wm.set_override(wind_speed=18.0, turbulence=0.12)
    st = wm.get_status()
    assert st["override_wind_speed"] == 18.0
    assert st["mode"] == "manual"
    assert abs(st["turbulence_intensity"] - 0.12) < 1e-9


def test_override_can_be_cleared_back_to_auto():
    """clear_override 回自動模式（Wind Control 的 auto profile 走這條）。"""
    wm = WindEnvironmentModel()
    wm.set_override(wind_speed=25.0)
    assert wm.get_status()["mode"] == "manual"
    wm.clear_override()
    st = wm.get_status()
    assert st["mode"] == "auto"
    assert st["override_wind_speed"] is None


def _avg_power_at_wind(wind_speed: float, *, warmup: int = 240, sample: int = 60) -> float:
    """把某風速餵進 turbine physics，回傳穩態平均發電（kW，WTUR_TotPwrAt）。"""
    m = TurbinePhysicsModel(seed=45)
    for _ in range(warmup):
        m.step(wind_speed=wind_speed, wind_direction=180.0, ambient_temp=15.0, dt=1.0)
    powers = [
        m.step(wind_speed=wind_speed, wind_direction=180.0, ambient_temp=15.0, dt=1.0)["WTUR_TotPwrAt"]
        for _ in range(sample)
    ]
    return float(np.mean(powers))


def test_power_responds_to_wind_speed():
    """核心：改風速 → 發電對應。高風(14)≈額定；靜風(2, 低於 cut-in)≈0。"""
    p_rated = _avg_power_at_wind(14.0)
    p_calm = _avg_power_at_wind(2.0)

    rated_kw = TurbinePhysicsModel(seed=45).spec.rated_power_kw  # 2000
    assert p_rated > 0.5 * rated_kw, f"14 m/s 應接近額定，實得 {p_rated:.0f} kW"
    assert p_calm < 50.0, f"2 m/s（低於 cut-in）應幾乎不發電，實得 {p_calm:.0f} kW"
    assert p_rated > p_calm * 10, "高風發電應遠大於靜風"
