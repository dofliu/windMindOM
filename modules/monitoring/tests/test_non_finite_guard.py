"""非有限值防呆（WMOM-20260718-09）。

背景：某些風機規格（如缺欄位/為 0）會讓上游物理發散成 inf/nan，導致
`[Simulator] Error: cannot convert float infinity to integer`（Modbus int() 轉換崩）+
fatigue rainflow numpy warning + 前端 recharts path 畫壞。修法：
1. `RainflowCounter.add_sample` 忽略非有限輸入（不污染 buffer）。
2. `engine._zero_non_finite` 於每步把 SCADA 的 inf/nan 就地歸零（單一 choke point，
   讓一顆壞 tag 不弄垮整個模擬迴圈）。

本檔驗證兩個防呆點（純邏輯，不需 broker/HTTP/Modbus）。
"""

from __future__ import annotations

import math
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

from simulator.engine import WindFarmSimulator, _zero_non_finite  # noqa: E402
from simulator.physics.fatigue_model import RainflowCounter  # noqa: E402


# ─── _zero_non_finite ─────────────────────────────────────────────────────

def test_zero_non_finite_replaces_inf_and_nan():
    scada = {
        "WLOD_DelTwrFa": float("inf"),
        "WLOD_DmgBldFlap": float("nan"),
        "WTUR_TotPwrAt": 1500.0,
        "op_state": "PRODUCING",  # 字串 tag 不可被動
    }
    hit = _zero_non_finite(scada)
    assert set(hit) == {"WLOD_DelTwrFa", "WLOD_DmgBldFlap"}
    assert scada["WLOD_DelTwrFa"] == 0.0
    assert scada["WLOD_DmgBldFlap"] == 0.0
    assert scada["WTUR_TotPwrAt"] == 1500.0  # 有限值不動
    assert scada["op_state"] == "PRODUCING"  # 非數值不動


def test_zero_non_finite_clean_dict_is_noop():
    scada = {"a": 1.0, "b": 2.5, "c": -3.0}
    assert _zero_non_finite(scada) == []
    assert scada == {"a": 1.0, "b": 2.5, "c": -3.0}


# ─── RainflowCounter.add_sample ────────────────────────────────────────────

def test_rainflow_ignores_non_finite_samples():
    rc = RainflowCounter()
    rc.add_sample(1.0)
    rc.add_sample(float("inf"))  # 應被忽略
    rc.add_sample(float("nan"))  # 應被忽略
    rc.add_sample(2.0)
    rc.add_sample(1.0)
    rc.add_sample(3.0)

    assert math.isfinite(rc._last_value), "last_value 不可被 inf/nan 污染"
    assert all(math.isfinite(p) for p in rc._peaks)
    assert all(math.isfinite(c) for c in rc._cycle_ranges)


# ─── 整合：_run_one_step 把非有限 tag 歸零 ─────────────────────────────────

def test_run_one_step_sanitizes_non_finite_from_physics():
    """讓某台 physics 吐 inf tag，_run_one_step 後該 reading 的 scada 應全為有限值。"""
    sim = WindFarmSimulator(turbine_count=2)
    sim._running = True

    orig_step = sim.turbines["WT001"].step

    def bad_step(*args, **kwargs):
        out = orig_step(*args, **kwargs)
        out["WLOD_DelTwrFa"] = float("inf")
        out["WGEN_GnStaTmp1"] = float("nan")
        return out

    sim.turbines["WT001"].step = bad_step  # type: ignore[method-assign]

    readings = sim._run_one_step(datetime(2026, 1, 1, 0, 0, 0), 1.0)
    wt001 = next(r for r in readings if r["turbine_id"] == "WT001")
    numeric = [v for v in wt001["scada"].values() if isinstance(v, (int, float))]
    assert all(math.isfinite(v) for v in numeric), "sanitize 後 scada 不應有 inf/nan"
    assert wt001["scada"]["WLOD_DelTwrFa"] == 0.0
    assert wt001["scada"]["WGEN_GnStaTmp1"] == 0.0
