"""健康機組葉片同步與長時間無誤跳防護（WMOM-20261021-12）。

背景：健康風場在 2026-04-10T09:00Z 起跑約 7 h 後，WT002 偶發 T2 336（葉片 1–3 差異 5 s > 1°）。
PLC 規則與手冊一致（瞬間 > 8°、3 s > 3°、5 s > 1°），根因在物理：各葉片零點校正誤差 σ 0.12°
加上伺服死區 0.18° / 雜訊 0.08° 的追蹤誤差，尾端會碰到 1°。修正後葉片誤差縮到真實試車水準，
本檔防止回歸：

1. 機制：14 支機組種子（預設風場大小）在紊流強、橫跨 Region 2/3 的風速下各跑 12 h，
   以 PLC 的判定方式（延遲從第一個越限樣本起算）量葉片差異，要離設定值留足餘裕
2. 整合：健康風場以批次路徑（5 s 物理子步）從原始重現點跑 12 h，另從冬季夜間、夏季清晨各跑 6 h，
   不得有任何訊號判定的 PLC 事件。葉片誤差是各機組種子的隨機漫步，與起點、風況幾乎無關（修正前三個起點
   都在 +7:04:45 由 WT002 跳同一次 336），所以葉片同步的覆蓋靠 1. 的 14 支種子；其他起點看的是季節 /
   日夜風況與氣溫下其他規則（溫度、偏航煞車、風向標）也不誤跳
"""

from __future__ import annotations

import math
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Deque, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import numpy as np
import pytest

import simulator.engine as engine_mod
from simulator.bulk_events import BulkEvent
from simulator.engine import WindFarmSimulator
from simulator.physics.turbine_physics import TurbinePhysicsModel

PRODUCING = 6
DEFAULT_FARM_TURBINES = 14

# 判定餘裕：5 s 規則看「連續 5 s 都越限」，健康機組這個量要明顯低於 1°（修正前 1.02°、修正後 0.49°，
# 與紊流強度幾乎無關——由零點誤差與死區決定）；3 s / 瞬間規則的設定值 3° / 8° 遠高於健康機組的瞬間峰值
#（本測試 TI 12% 修正後 0.86°；陣風 TI 30% 約 1.2–1.8°，發生在變槳速率受限時，各葉片伺服速率差 0.92–0.98 倍）
SUSTAINED_5S_LIMIT_DEG = 0.7
SUSTAINED_3S_LIMIT_DEG = 1.5
PEAK_LIMIT_DEG = 2.0


class _SustainedTracker:
    """量「連續 delay 秒都越過某值」的最大值：視窗內最小差異的最大值。

    PLC 的延遲從第一個越限樣本起算、經過 ``delay`` 秒（含）才成立，所以一個視窗是
    ``ceil(delay / dt) + 1`` 個連續樣本。

    Attributes:
        worst: 目前為止所有完整視窗中，視窗內最小值的最大值。
    """

    def __init__(self, delay_s: float, dt: float) -> None:
        """建立追蹤器。

        Args:
            delay_s: 規則的延時（秒）。
            dt: 樣本間隔（秒）。
        """
        self._window: Deque[float] = deque(maxlen=math.ceil(delay_s / dt - 1e-9) + 1)
        self.worst = 0.0

    def push(self, value: float) -> None:
        """加入一個樣本並更新 ``worst``。

        Args:
            value: 本樣本的葉片差異（度）。
        """
        self._window.append(value)
        if len(self._window) == self._window.maxlen:
            self.worst = max(self.worst, min(self._window))


def _drive_pitch(seed: int, dt: float, hours: float) -> Tuple[float, float, float]:
    """穩定發電中的機組只跑變槳伺服，風速 6 → 24 → 6 m/s 加強紊流（TI 12%、τ 20 s）。

    Args:
        seed: 機組種子（與 ``WindFarmSimulator`` 的 WT00N 相同）。
        dt: 物理步長（秒）。
        hours: 模擬時數。

    Returns:
        （5 s 持續差異最大值, 3 s 持續差異最大值, 瞬間峰值），單位度，三對葉片取最大。
    """
    model = TurbinePhysicsModel(seed=seed)
    model.tur_state = PRODUCING
    model.pitch_angle = model.spec.pitch_work
    model._pitch_bl = [model.pitch_angle + offset for offset in model._pitch_offset_bl]
    wind_rng = np.random.default_rng(10_000 + seed)
    alpha = math.exp(-dt / 20.0)
    turbulence = 0.0
    sustained_5s = _SustainedTracker(5.0, dt)
    sustained_3s = _SustainedTracker(3.0, dt)
    peak = 0.0
    steps = int(hours * 3600 / dt)
    for k in range(steps):
        mean_wind = 6.0 + 18.0 * (1.0 - abs(2.0 * k / steps - 1.0))
        turbulence = (alpha * turbulence
                      + math.sqrt(1.0 - alpha * alpha) * 0.12 * mean_wind * wind_rng.standard_normal())
        model._calc_pitch(max(0.0, mean_wind + turbulence), True, dt)
        b1, b2, b3 = (round(angle, 2) for angle in model._pitch_bl)  # PLC 讀的是 2 位小數的 tag
        diff = max(abs(b1 - b2), abs(b1 - b3), abs(b2 - b3))
        sustained_5s.push(diff)
        sustained_3s.push(diff)
        peak = max(peak, diff)
    return sustained_5s.worst, sustained_3s.worst, peak


@pytest.mark.parametrize("dt", [1.0, 5.0], ids=["live-1s", "bulk-5s"])
def test_healthy_blade_discrepancy_stays_well_below_setpoints(dt: float) -> None:
    """14 支機組 × 12 h：葉片差異離手冊設定值留足餘裕（Live 1 s 步長與批次 5 s 子步都要成立）。"""
    worst: List[Tuple[int, float, float, float]] = []
    for seed in range(1, DEFAULT_FARM_TURBINES + 1):
        worst.append((seed, *_drive_pitch(seed, dt, hours=12.0)))
    assert max(w[1] for w in worst) < SUSTAINED_5S_LIMIT_DEG, worst
    assert max(w[2] for w in worst) < SUSTAINED_3S_LIMIT_DEG, worst
    assert max(w[3] for w in worst) < PEAK_LIMIT_DEG, worst


def test_blade_calibration_offsets_are_small() -> None:
    """葉片零點校正誤差（靜態）要在真實試車水準：任兩片相差 < 0.4°（含較大風場的種子）。"""
    for seed in range(1, 51):
        offsets = TurbinePhysicsModel(seed=seed)._pitch_offset_bl
        spread = max(offsets) - min(offsets)
        assert spread < 0.4, (seed, offsets)


@pytest.mark.parametrize(("start", "hours"), [
    ("2026-04-10T09:00:00+00:00", 12.0),  # 原始重現點：修正前 16:04:45 WT002 跳 T2 336
    ("2026-01-15T18:00:00+00:00", 6.0),   # 冬季夜間起跑
    ("2026-07-20T04:00:00+00:00", 6.0),   # 夏季清晨起跑
])
def test_healthy_farm_long_run_has_no_signal_judged_events(start: str, hours: float,
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    """健康風場批次產生（time_step 60 → 5 s 物理子步）不得有任何訊號判定的 PLC 事件。

    釘住引擎的起始時刻（``generate_bulk`` 以 ``utc_now()`` 為起點）；自動風況依模擬時刻計算，
    不讀 ``wind_model.utc_now``（只有 ``set_override`` / ``set_profile`` 會讀），本測試不需另外釘。
    """
    t0 = datetime.fromisoformat(start).astimezone(timezone.utc)
    monkeypatch.setattr(engine_mod, "utc_now", lambda: t0)
    sim = WindFarmSimulator(turbine_count=3)
    events: List[BulkEvent] = []
    producing_minutes = 0

    def count_producing(readings: list) -> None:
        nonlocal producing_minutes
        producing_minutes += sum(1 for r in readings if r["scada"].get("WTUR_TurSt") == PRODUCING)

    sim.generate_bulk(duration_hours=hours, time_step=60.0, callback=count_producing, on_events=events.extend)
    signal_events = [(e.timestamp.isoformat(), e.turbine_id, e.kind, e.plc_event.code)
                     for e in events if e.plc_event is not None and e.plc_event.source == "signal"]
    assert signal_events == []
    # 前置條件：大部分時間在穩定發電（葉片差異規則有在判定），而不是整段停機
    assert producing_minutes >= 0.5 * 3 * hours * 60, producing_minutes
