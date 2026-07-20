"""情境保存/調閱：orchestration / endpoint 層（WMOM-20260719-02，code review 補強）。

storage 層由 ``test_scenario_persistence.py`` 覆蓋；本檔補 `config.generate-bulk` 的情境收尾
與 `scenarios` router 的實際程式路徑——兩個 code review Must-fix 都活在這層：
1. offset=0 的排定故障事件必須落在情境時間窗內（可被調閱撈到）。
2. 生成中途失敗，情境 session 必須被收尾（不得卡未結束、被 get_active_session 誤認成 Live）。

以最小 fake broker 直呼 async endpoint（繞過 HTTP/auth——Must-fix 在 business logic、不在 gate）。
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

from server.storage import Storage  # noqa: E402
from simulator.engine import WindFarmSimulator  # noqa: E402
from server.routers import config as config_ep  # noqa: E402
from server.routers import faults as faults_ep  # noqa: E402
from server.routers import scenarios as scenarios_ep  # noqa: E402


class _FakeBroker:
    """只實作 endpoint 用到的表面（storage / simulator / session / 事件與歷史委派）。"""

    def __init__(self, storage: Storage, simulator: WindFarmSimulator, session_id: int):
        self.storage = storage
        self.simulator = simulator
        self._session_id = session_id

    @contextmanager
    def pause_live_for_batch(self) -> Iterator[bool]:
        """對齊真 DataBroker：批次期間暫停 Live（實呼引擎的 stop/restore）。本 fake 的 sim 從未
        start() 故無 thread → 等同 no-op pass-through，但仍走過真正的退場/恢復程式路徑。"""
        was_running = self.simulator.stop_live_loop()
        try:
            yield was_running
        finally:
            self.simulator.restore_live_loop(was_running, 1.0)

    def record_event(self, **kwargs) -> None:
        self.storage.record_event(**kwargs)

    def get_history(self, turbine_id: str, start: Optional[str] = None,
                    end: Optional[str] = None, limit: int = 1000,
                    session_id: Optional[int] = None) -> List[dict]:
        return self.storage.query_history(turbine_id, start, end, limit, session_id=session_id)

    def get_history_events(self, turbine_id: Optional[str] = None, start: Optional[str] = None,
                           end: Optional[str] = None, limit: int = 500) -> List[dict]:
        return self.storage.query_events(turbine_id, start, end, limit)


@pytest.fixture
def broker(tmp_path, monkeypatch):
    storage = Storage(db_path=str(tmp_path / "ep.db"))
    sim = WindFarmSimulator(turbine_count=3)
    sim._running = True
    live_sid = storage.create_session(data_source="simulation", turbine_count=3)
    b = _FakeBroker(storage, sim, live_sid)
    monkeypatch.setattr(config_ep, "get_broker", lambda: b)
    monkeypatch.setattr(scenarios_ep, "get_broker", lambda: b)
    return b


def test_generate_bulk_saves_scenario_with_offset0_event_in_window(broker):
    """Must-fix #2：offset=0 注入的故障事件應落在情境時間窗內、可被調閱撈到。"""
    res = asyncio.run(config_ep.generate_bulk({
        "duration_hours": 0.02, "time_step": 10.0, "name": "情境A", "wind_profile": "moderate",
        "fault_schedule": [{"scenario_id": "hydraulic_leak", "turbine_id": "WT002",
                            "offset_seconds": 0}],
    }))
    sid = res["scenario_id"]
    assert sid is not None and res["faults_injected"] == 1

    hist = asyncio.run(scenarios_ep.get_scenario_turbine_history(sid, "WT002", 2000))
    assert len(hist["readings"]) > 0, "情境資料應可調閱"
    assert hist["events_by_time_window"] is True, "應標明 events 走時間窗、非 session 隔離"
    fault_events = [e for e in hist["events"] if e.get("event_type") == "fault"]
    assert fault_events, "offset=0 的故障事件應落在情境時間窗內、被調閱撈到（Must-fix #2）"


def test_generate_bulk_isolates_scenario_from_live_and_ends_it(broker):
    """情境資料寫專屬 session、不融進 Live；情境結束後 active 仍是 Live。"""
    res = asyncio.run(config_ep.generate_bulk({
        "duration_hours": 0.02, "time_step": 10.0, "name": "情境B"}))
    sid = res["scenario_id"]

    assert len(broker.storage.query_history("WT001", session_id=sid)) > 0
    assert broker.storage.query_history("WT001", session_id=broker._session_id) == [], \
        "情境資料不得寫進 Live session"

    active = broker.storage.get_active_session()
    assert active is not None and active["id"] == broker._session_id, "情境已 end → active 仍是 Live"


def test_generate_bulk_failure_finalizes_scenario_session(broker, monkeypatch):
    """Must-fix #1：生成中途失敗，情境 session 必須被收尾（ended + status=error），
    不得卡未結束、被 get_active_session 誤認成 Live。"""
    def boom(*args, **kwargs):
        raise RuntimeError("physics diverged mid-scenario")

    monkeypatch.setattr(broker.simulator, "generate_bulk", boom)

    with pytest.raises(RuntimeError):
        asyncio.run(config_ep.generate_bulk({
            "duration_hours": 0.02, "time_step": 10.0, "name": "壞情境"}))

    failed = [s for s in broker.storage.list_scenarios() if s["config"]["name"] == "壞情境"]
    assert failed, "失敗的情境 session 仍應存在（可追溯）"
    assert failed[0]["ended_at"] is not None, "失敗情境必須被 end_session（Must-fix #1）"
    assert failed[0]["config"].get("status") == "error", "失敗情境應標記 status=error"

    # 防禦：get_active_session 不得回情境（Should-fix #1）
    active = broker.storage.get_active_session()
    assert active is not None and active["id"] == broker._session_id
    assert active.get("config", {}).get("kind") != "scenario"


def test_generate_bulk_without_name_writes_to_live(broker):
    """回歸：不帶 name 沿用舊行為（寫 Live session、不建情境）。"""
    res = asyncio.run(config_ep.generate_bulk({"duration_hours": 0.02, "time_step": 10.0}))
    assert res["scenario_id"] is None
    assert broker.storage.list_scenarios() == []
    assert len(broker.storage.query_history("WT001", session_id=broker._session_id)) > 0


def test_run_test_plan_stops_live_thread_during_batch_and_restores(tmp_path, monkeypatch):
    """Must-fix（姊妹端點）：faults.py::run_test_plan 與 generate-bulk 同模式，也必須在批次期間
    停 Live thread（避免併發 writer 撞 DB-lock）、事後恢復。用**真 thread** 守住——若哪天 run_test_plan
    的 pause_live_for_batch 包裹被拿掉，此測試會轉紅（mutation test 已證原本無任何測試會抓到）。"""
    from server.routers.faults import TEST_PLANS

    storage = Storage(db_path=str(tmp_path / "rtp.db"))
    sim = WindFarmSimulator(turbine_count=3)
    sim.start(time_step=0.02)  # 真的起 Live 背景 thread
    sid = storage.create_session(data_source="simulation", turbine_count=3)
    b = _FakeBroker(storage, sim, sid)
    monkeypatch.setattr(faults_ep, "get_broker", lambda: b)

    seen: dict = {}
    # spy：於 generate_bulk 被呼叫的當下（即 pause context 內）記錄 Live thread 是否已停。
    # 回傳 0 不真的生成，加速（本測試只驗證 pause 包裹，非生成內容）。
    def spy(*args, **kwargs):
        seen["alive_inside"] = sim._thread.is_alive()
        return 0

    monkeypatch.setattr(sim, "generate_bulk", spy)

    try:
        plan_id = next(iter(TEST_PLANS))  # 任一內建 plan
        asyncio.run(faults_ep.run_test_plan(plan_id, {"time_step": 60.0}))
        assert seen.get("alive_inside") is False, "批次進行時 Live thread 必須已停（無並行 writer）"
        assert sim.is_running and sim._thread.is_alive(), "run_test_plan 後 Live 應恢復（新 thread）"
    finally:
        sim.stop()
