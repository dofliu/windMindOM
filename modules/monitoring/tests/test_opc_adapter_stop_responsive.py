"""OPCDAAdapter._poll_loop 的睡眠可中斷性（WMOM-20260720-04 (1) review 殘留）。

背景：`DataBroker.stop()` 這次補上了呼叫 `self._opc_adapter.stop()`，但 `OPCDAAdapter.stop()`
本身的 `join(timeout=10)` 若撞上 `_poll_loop` 不可中斷的 `time.sleep(self._poll_interval)`
（Z72 預設 17 秒），常態性小於 poll_interval 而逾時——輪詢 thread 仍會在背景活著，睡醒後繼續用
（屆時可能已改變的）callback / session 寫入資料，孤兒 thread 續寫新 session 的窗口只是被縮小，
沒有真正關閉。比照 `engine.py` / `DataBroker` 已用過的修法，改用 `threading.Event().wait()`。

本檔只驗證這一段（monkeypatch 掉 `_connect`/`_read_all_turbines`，不需要真的裝 openopc2 或連線）。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

from server.opc_adapter import OPCDAAdapter  # noqa: E402


def _adapter_with_fake_connection(monkeypatch, poll_interval: float) -> OPCDAAdapter:
    """建一個不需要真連線（openopc2）就能跑 `_poll_loop` 的 adapter。"""
    adapter = OPCDAAdapter()
    adapter._poll_interval = poll_interval
    monkeypatch.setattr(adapter, "_connect", lambda: True)
    monkeypatch.setattr(adapter, "_read_all_turbines", lambda: [])
    return adapter


def test_stop_returns_promptly_during_poll_sleep(monkeypatch):
    """實測：用較大 poll_interval（5s）放大症狀。修好前 stop() 得等該次睡眠自然結束（近 5s，
    且 join(timeout=10) 蓋不住更長的真實 Z72 預設 17s）；修好後 Event.wait 被 set() 立刻中斷，
    stop() 應近乎瞬間完成。"""
    adapter = _adapter_with_fake_connection(monkeypatch, poll_interval=5.0)
    adapter.start()
    try:
        time.sleep(0.05)  # 確保背景 thread 已進入本次睡眠
        t0 = time.time()
        adapter.stop()
        elapsed = time.time() - t0
        assert elapsed < 1.0, f"stop() 應近乎瞬間（可中斷睡眠）；實測 {elapsed:.2f}s"
    finally:
        if adapter._running:
            adapter.stop()


def test_restart_after_stop_does_not_wake_immediately(monkeypatch):
    """重入啟動必須清掉上次 stop() 設的喚醒旗標，否則新一輪輪詢第一次睡眠會被舊旗標立刻打斷、
    變成忙迴圈（每次輪詢間隔恆為 0，對真實 OPC server 是連續轟炸）。"""
    adapter = _adapter_with_fake_connection(monkeypatch, poll_interval=0.2)
    adapter.start()
    adapter.stop()

    adapter._poll_interval = 5.0
    adapter.start()
    try:
        time.sleep(0.05)
        assert not adapter._wake.is_set(), "重入啟動應清掉舊的喚醒旗標，否則本輪睡眠會被立刻打斷"
    finally:
        adapter.stop()
