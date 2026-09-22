"""WindFarmSimulator._loop 的睡眠可中斷性（WMOM-20260720-08 (2) + WMOM-20260922-01）。

背景：round-2 review 用壓力測試在既有碼發現 ``_loop`` real-time 分支的
``time.sleep(time_step)`` 與 #147 已修的 maintenance thread 是同一根因——``stop()``
撞上該次睡眠時得等它自然結束才能 ``join()``，讓每次切換來源多卡最多一個 time_step。
修法比照 #147：改用 ``threading.Event().wait(time_step)``，``stop()`` 呼叫 ``set()``
立刻喚醒。

accelerated 分支（``time_scale > 1``）當時同樣留了 ``time.sleep(wall_sleep)``（見
WMOM-20260720-08 work-log §7 open questions），本檔一併補上同款驗證與修法
（WMOM-20260922-01）——``set_time_scale`` API 可在模擬跑著的時候即時調整，wall_sleep
可長達數秒，未修前 ``stop()`` 得等它自然結束。

本檔只驗證這一段（不需 broker / HTTP）。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

from simulator.engine import WindFarmSimulator  # noqa: E402


def test_stop_returns_promptly_during_real_time_sleep():
    """實測：用較大 time_step（5s）放大症狀。修好前 stop() 得等該次睡眠自然結束（近 5s）；
    修好後 Event.wait 被 set() 立刻中斷，stop() 應近乎瞬間完成。"""
    sim = WindFarmSimulator(turbine_count=1)
    sim.start(time_step=5.0)
    try:
        time.sleep(0.05)  # 確保背景 thread 已進入本次睡眠
        t0 = time.time()
        sim.stop()
        elapsed = time.time() - t0
        assert elapsed < 1.0, f"stop() 應近乎瞬間（可中斷睡眠）；實測 {elapsed:.2f}s"
    finally:
        if sim.is_running:
            sim.stop()


def test_restart_after_stop_does_not_wake_immediately():
    """重入啟動必須清掉上次 stop() 設的喚醒旗標，否則新一輪 _loop 第一次睡眠會被舊旗標
    立刻打斷、變成忙迴圈（每步睡眠時長恆為 0）。"""
    sim = WindFarmSimulator(turbine_count=1)
    sim.start(time_step=0.2)
    sim.stop()

    sim.start(time_step=5.0)
    try:
        time.sleep(0.05)
        assert not sim._wake.is_set(), "重入啟動應清掉舊的喚醒旗標，否則本輪睡眠會被立刻打斷"
    finally:
        sim.stop()


def test_stop_returns_promptly_during_accelerated_wall_sleep():
    """accelerated 分支（time_scale > 1）同款驗證：time_step=5s、time_scale=2 讓
    wall_sleep = max(0.1, time_step/ts*steps_per_tick) = 5s，修好前 stop() 得等這次
    wall_sleep 自然結束；修好後應近乎瞬間完成。"""
    sim = WindFarmSimulator(turbine_count=1)
    sim.time_scale = 2.0
    sim.start(time_step=5.0)
    try:
        time.sleep(0.05)  # 確保背景 thread 已進入本次 wall_sleep
        t0 = time.time()
        sim.stop()
        elapsed = time.time() - t0
        assert elapsed < 1.0, f"stop() 應近乎瞬間（可中斷睡眠）；實測 {elapsed:.2f}s"
    finally:
        if sim.is_running:
            sim.stop()
