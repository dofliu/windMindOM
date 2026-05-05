"""DataBroker snapshot dedupe + cooldown test for #WMOM-20260505-01.

驗證 simulator state machine flapping 場景下，broker `_trigger_snapshot` 不會：
1. 對同一 turbine 同類 event_class 在 cooldown 內重複呼叫 storage.store_snapshots（retroactive write 是 amplifier 主因）
2. 多次更新 _snapshot_event_ref（保持 grouping，不 distinct event_ref 暴增）

但仍會：
- 延長 active window（讓「事件持續中」的 1Hz 收集繼續）
- 不同 event_class 來時走完整重啟流程

實際生產情境（從 41.9 GB DB 樣本重現）：
彰化 farm 17.5 天累積 19,594 個 distinct event_ref，top 都是
`stop:WT007:7:...` 在 80 秒內 trigger 11 次新 event。
本 test 重現該 80 秒並驗證 dedupe 後只 store 1 次 retroactive。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "modules" / "monitoring"))


@pytest.fixture
def broker():
    """Bare DataBroker — bypass __init__ 避開 FarmRegistry / Storage 初始化。

    只填 _trigger_snapshot 用到的欄位 + class consts。
    """
    from server.data_broker import DataBroker

    b = object.__new__(DataBroker)
    # 從 class 抓常數（不重複定義）
    b.SNAPSHOT_WINDOW_S = DataBroker.SNAPSHOT_WINDOW_S
    b.SNAPSHOT_DEDUPE_COOLDOWN_S = DataBroker.SNAPSHOT_DEDUPE_COOLDOWN_S

    b._snapshot_active = {}
    b._snapshot_event_ref = {}
    b._snapshot_last_class = {}
    b._session_id = None

    # Mock simulator 永遠回固定 history（用 sentinel list）
    b.simulator = MagicMock()
    b.simulator.get_history.return_value = [{"turbine_id": "WT007", "_marker": "history_row"}]

    # Mock storage 紀錄被呼叫的次數
    b.storage = MagicMock()
    return b


# ─────────────────────────────────────────────────────────────────────────
# _extract_event_class 純函式
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ref,expected", [
    ("stop:WT007:7:2026-05-04T18:01:03.553883", "stop:WT007:7"),
    ("stop:WT001:9:2026-04-17T23:43:06.223977", "stop:WT001:9"),
    ("fault_trip:WT003:2026-05-04T18:01:03.553", "fault_trip:WT003"),
    ("custom_no_timestamp", "custom_no_timestamp"),
    ("stop:WT007:7:invalid_not_iso", "stop:WT007:7:invalid_not_iso"),  # 無 ISO suffix → 全留
])
def test_extract_event_class(ref, expected):
    from server.data_broker import DataBroker

    assert DataBroker._extract_event_class(ref) == expected


# ─────────────────────────────────────────────────────────────────────────
# _trigger_snapshot dedupe 行為
# ─────────────────────────────────────────────────────────────────────────


def test_first_trigger_does_full_capture(broker):
    """乾淨 broker 第一次 trigger → store_snapshots 被呼叫 1 次（retroactive）。"""
    broker._trigger_snapshot("WT007", "stop:WT007:7:2026-05-04T18:00:00")

    assert broker.storage.store_snapshots.call_count == 1
    # event_ref 紀錄
    assert broker._snapshot_event_ref["WT007"] == "stop:WT007:7:2026-05-04T18:00:00"
    # event_class 紀錄
    cls, _ts = broker._snapshot_last_class["WT007"]
    assert cls == "stop:WT007:7"


def test_same_class_in_cooldown_skips_retroactive(broker):
    """同一 turbine 同 event_class 在 cooldown 內重複 trigger → store_snapshots 不再被呼叫。"""
    # 模擬 80 秒內 11 次 trigger（從真實 DB 觀察到的彰化 farm 場景）
    timestamps = [f"2026-05-04T18:00:{i:02d}.000000" for i in range(0, 80, 7)]  # 12 個

    for ts in timestamps:
        broker._trigger_snapshot("WT007", f"stop:WT007:7:{ts}")

    # ★ 關鍵：retroactive write 只在第一次 — 後 11 次都 skip
    assert broker.storage.store_snapshots.call_count == 1, (
        f"預期 1 次 retroactive，實得 {broker.storage.store_snapshots.call_count} 次 — "
        "dedupe 失靈，會放大成原本 41.9 GB 的問題"
    )

    # event_ref 沿用第一次的（保持 grouping）
    assert broker._snapshot_event_ref["WT007"] == f"stop:WT007:7:{timestamps[0]}"


def test_different_event_class_triggers_full_capture(broker):
    """不同 event_class 來 → 即使 turbine 相同，仍走完整重啟流程。"""
    broker._trigger_snapshot("WT007", "stop:WT007:7:2026-05-04T18:00:00")
    broker._trigger_snapshot("WT007", "fault_trip:WT007:2026-05-04T18:00:30")
    broker._trigger_snapshot("WT007", "stop:WT007:9:2026-05-04T18:01:00")

    # 三個不同 class → 三次 retroactive
    assert broker.storage.store_snapshots.call_count == 3
    # 最終 event_ref 是最後一個
    assert broker._snapshot_event_ref["WT007"].startswith("stop:WT007:9")


def test_different_turbines_independent(broker):
    """不同 turbine 同類 event 互不影響 dedupe（每台獨立 cooldown 軌跡）。"""
    broker._trigger_snapshot("WT007", "stop:WT007:7:2026-05-04T18:00:00")
    broker._trigger_snapshot("WT003", "stop:WT003:7:2026-05-04T18:00:01")
    broker._trigger_snapshot("WT001", "stop:WT001:7:2026-05-04T18:00:02")

    # 三台各走 1 次
    assert broker.storage.store_snapshots.call_count == 3


def test_cooldown_extends_active_window(broker):
    """cooldown 內 dedupe 即使 skip retroactive，仍要延長 active window 給「事件持續」中的 1Hz 收集。"""
    broker._trigger_snapshot("WT007", "stop:WT007:7:2026-05-04T18:00:00")
    first_end = broker._snapshot_active["WT007"]

    # 等一下下（用 monkeypatched time 也行，但 simple test 用 sleep 風險小）
    import time as _time
    _time.sleep(0.05)

    broker._trigger_snapshot("WT007", "stop:WT007:7:2026-05-04T18:00:07")
    second_end = broker._snapshot_active["WT007"]

    # active 結束時間應該被延長
    assert second_end > first_end


def test_cooldown_expired_resumes_full_capture(broker, monkeypatch):
    """cooldown 過期後同類 event → 重新走 retroactive write。"""
    import server.data_broker as dbm

    # 第一次 trigger
    broker._trigger_snapshot("WT007", "stop:WT007:7:t0")
    assert broker.storage.store_snapshots.call_count == 1

    # 把記憶體裡的 last_class timestamp 改成「很久以前」模擬 cooldown 過期
    cls, _ts = broker._snapshot_last_class["WT007"]
    broker._snapshot_last_class["WT007"] = (cls, 0.0)  # 1970 年

    broker._trigger_snapshot("WT007", "stop:WT007:7:t_after_cooldown")

    # 應該重新 retroactive
    assert broker.storage.store_snapshots.call_count == 2


def test_dedupe_drops_load_within_single_cooldown_window(broker):
    """壓力測試：simulator state flapping 在「單一 cooldown window 內」emit 1000 個同類事件。

    Without dedupe: 1000 次 retroactive write × 600 row history = 60 萬 row write
    With dedupe (cooldown 5 min): 第一次走 retro，其餘 999 次都 skip → 1 次

    本 test 跑迴圈幾乎瞬間完成，所有 trigger 都在單一 cooldown window 內，
    驗證「同 cooldown window 內 dedupe 嚴格只觸發 1 次 retro」。
    跨 cooldown 的多次 retro 由 ``test_cooldown_expired_resumes_full_capture`` 覆蓋。
    """
    for i in range(1000):
        # 每次 timestamp 不同，但 event_class 都是 stop:WT007:7
        broker._trigger_snapshot("WT007", f"stop:WT007:7:2026-05-04T18:{i:04d}.000")

    assert broker.storage.store_snapshots.call_count == 1, (
        f"1000 次 flapping（單一 cooldown window 內）→ 應該 1 次 retro write，實得 "
        f"{broker.storage.store_snapshots.call_count}"
    )


def test_cooldown_starts_from_first_trigger_not_latest(broker, monkeypatch):
    """Finding #1 regression：cooldown 必須從「第一次 trigger」起算，不能被刷新。

    持續 flapping 模擬：每隔短時間 trigger 同類 event。若 cooldown 被刷新，
    `_snapshot_last_class.timestamp` 會永遠保持「最近一次」→ cooldown 永不過期。
    本 test 透過 monkey-patch time 模擬「持續 trigger 跨越原 cooldown 時長」，
    驗證最終仍會重新 trigger retro（因為從第一次起算的 cooldown 已過）。
    """
    import time as time_module

    # 起始時間
    fake_time = [1000.0]

    def fake_clock():
        return fake_time[0]

    monkeypatch.setattr(time_module, "time", fake_clock)

    # 第一次 trigger
    broker._trigger_snapshot("WT007", "stop:WT007:7:2026-05-04T18:00:00")
    assert broker.storage.store_snapshots.call_count == 1
    initial_class_ts = broker._snapshot_last_class["WT007"][1]

    # 持續 flapping — 每 30 秒一次，跨越 cooldown (300s)
    for offset in (30, 60, 90, 120, 150, 180, 210, 240, 270):
        fake_time[0] = 1000.0 + offset
        broker._trigger_snapshot("WT007", f"stop:WT007:7:2026-05-04T18:00:{offset:02d}")

    # 還在 cooldown 內：last_class.timestamp 不應被刷新
    assert broker._snapshot_last_class["WT007"][1] == initial_class_ts, (
        "last_class timestamp 不應被 cooldown 路徑刷新（finding #1）"
    )

    # 跨過 cooldown 邊界：第一次 trigger 後 350 秒 → 應重新走 retro
    fake_time[0] = 1000.0 + 350
    broker._trigger_snapshot("WT007", "stop:WT007:7:2026-05-04T18:05:50")

    assert broker.storage.store_snapshots.call_count == 2, (
        "跨過 cooldown 邊界後第一次同類 trigger 應重新 retro write"
    )
