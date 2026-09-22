"""DataBroker 生命週期硬化（WMOM-20260720-04 (1)(2)(3) + WMOM-20260720-08 (1)）。

四個獨立子問題（M6 live/OPC 後端硬化，排 M6 實接前）：
1. ``stop()`` 未呼叫 ``_opc_adapter.stop()`` → 切走 live 後孤兒輪詢 thread 續寫新 session。
2. 切走 live（``/api/source/select``）無角色檢查，但起 live 需 SUPERVISOR——不對稱。
3. ``config.py::set_simulation`` 在非即時模擬來源時靜默 ``switch_mode`` 回 simulation。
4. ``start/stop/switch_mode`` 全程無鎖 → 真併發呼叫可能撞出
   ``RuntimeError: cannot join thread before it is started``。

本檔只涵蓋 (1) 與 (4)（純 broker 層、不需 HTTP）；(2)(3) 見
``test_source_selection.py`` / ``test_config_set_simulation_gate.py``。
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

from server.data_broker import DataBroker  # noqa: E402
from server.farm_registry import FarmRegistry  # noqa: E402


@pytest.fixture
def broker(tmp_path):
    return DataBroker(farm_registry=FarmRegistry(data_dir=tmp_path))


class _FakeOPCAdapter:
    """`stop()` 語意驗證用的最小替身：只記錄有沒有被呼叫。"""

    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


def test_stop_stops_opc_adapter_and_clears_reference(broker):
    """Must-fix（(1)）：stop() 之前只停 simulator/maintenance，漏了 _opc_adapter，
    切走 live 後孤兒輪詢 thread 續跑（且續寫入下一個 session）。"""
    fake = _FakeOPCAdapter()
    broker._opc_adapter = fake
    broker._source_active = True
    broker._source_kind = "live"

    broker.stop()

    assert fake.stopped is True, "stop() 必須呼叫 _opc_adapter.stop()"
    assert broker._opc_adapter is None, "停掉後應清空參照，避免下次 stop() 重複操作已停的 adapter"


def test_stop_without_opc_adapter_is_noop(broker):
    """從未啟用過 OPC（simulation-only session）時 stop() 不該因 _opc_adapter 是 None 而炸。"""
    assert broker._opc_adapter is None
    broker.stop()  # 不應拋
    assert broker._opc_adapter is None


def test_concurrent_start_stop_does_not_race(broker, monkeypatch):
    """Must-fix（(4)）：round-2 reviewer 用壓力測試在既有碼發現 start/stop/switch_mode 全程
    無鎖——_start_maintenance 讀到已賦值但尚未 .start() 的 thread，若同時被另一執行緒的
    stop() 呼叫 join()，會拋 RuntimeError: cannot join thread before it is started。
    用高頻併發 start/stop 壓測（4 threads × 30 輪 scenario 模式、單機組、mock 掉
    session 的 SQLite 寫入，只留 maintenance thread 建立/停止這條被壓測的路徑本身）：
    加鎖後應完全不拋例外。
    """
    from server.models import DataSourceConfig, DataSourceMode, SimulationConfig

    # Session 的 SQLite create/end 不是本次壓測目標（且真併發寫同一檔案另有 WMOM-20260720-01
    # 那套 pause_live_for_batch 機制處理），mock 掉讓迴圈只壓 maintenance thread 生命週期本身，
    # 避免無關的 I/O 競爭拖慢或干擾這個測試。
    # Should-fix（code review）：只 monkeypatch broker.storage 上的方法沒用——start() 第一次呼叫
    # 時（_active_farm_id 尚為 None）會跑 _init_farm_storage()，把 self.storage 整個換成新
    # instance，換掉後被 patch 的是舊物件。改成先設定 _active_farm_id，讓 start() 內
    # `if self._active_farm_id is None` 這個分支全程不成立，self.storage 就不會被換掉。
    broker._active_farm_id = "test-farm"
    monkeypatch.setattr(broker.storage, "create_session", lambda *a, **k: 1)
    monkeypatch.setattr(broker.storage, "end_session", lambda *a, **k: None)

    errors: list[Exception] = []
    errors_lock = threading.Lock()

    def hammer():
        for _ in range(30):
            try:
                broker.start(
                    DataSourceConfig(mode=DataSourceMode.SIMULATION),
                    SimulationConfig(turbineCount=1),
                    run_loop=False,
                )
                broker.stop()
            except Exception as e:  # noqa: BLE001 — 壓力測試刻意攔截任何例外以斷言
                with errors_lock:
                    errors.append(e)

    threads = [threading.Thread(target=hammer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"併發 start/stop 不應拋例外，實際：{errors[:3]}"


def test_select_view_only_is_atomic_with_concurrent_start(broker, monkeypatch):
    """`select_view_only()` 呼叫 stop() 後仍會繼續修改 source_active/source_kind/simulator，
    這段空窗如果不與 start/stop/switch_mode 共用同一把鎖，另一執行緒的 start() 可能完整插進來
    跑完（真的建了 simulator + 起了 maintenance thread），select_view_only 卻在那之後才把
    source_kind 覆寫回 'view'——回報「無來源」但背景其實仍有 maintenance thread 在跑，狀態與
    實際不一致（且 simulator 參照被 select_view_only 設回 None，洩漏剛建好的那個 simulator）。

    用受控延遲（monkeypatch `_init_farm_storage`，在 select_view_only 呼叫的那次真正工作完成後
    睡 0.3s）取代隨機壓測——純靠執行緒排程賭運氣重現機率太低（實測 hammer 版本 5 次全過，
    抓不到問題），改成確定性建構交錯視窗。
    """
    import time as _t

    from server.models import DataSourceConfig, DataSourceMode, SimulationConfig

    monkeypatch.setattr(broker.storage, "create_session", lambda *a, **k: 1)
    monkeypatch.setattr(broker.storage, "end_session", lambda *a, **k: None)

    orig_init_farm_storage = broker._init_farm_storage

    def delayed_init_farm_storage():
        orig_init_farm_storage()  # 真正建好 storage、設定 _active_farm_id 之後才睡
        _t.sleep(0.3)

    monkeypatch.setattr(broker, "_init_farm_storage", delayed_init_farm_storage)

    def do_start():
        _t.sleep(0.05)  # 讓 select_view_only 先進入 stop() 之後的 _init_farm_storage 延遲窗
        broker.start(
            DataSourceConfig(mode=DataSourceMode.SIMULATION),
            SimulationConfig(turbineCount=1),
            run_loop=False,
        )

    t = threading.Thread(target=do_start)
    t.start()
    broker.select_view_only()
    t.join(timeout=5)

    assert not (broker.source_kind == "view" and broker._maintenance_running), (
        "回報 source_kind=view（宣稱無來源）但背景其實有 maintenance thread 在跑——"
        f"狀態與實際不一致（source_kind={broker.source_kind!r}, "
        f"_maintenance_running={broker._maintenance_running!r}）"
    )
