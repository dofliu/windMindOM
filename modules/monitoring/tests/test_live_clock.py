"""Live 的模擬時鐘與固定取樣間隔（WMOM-20261125-03-a）。

1. 時鐘每一步往前推剛好 ``time_step`` 秒、起點對齊整秒；不會因為每步的計算時間慢慢落後實際時間。
2. 落後時全速補跑（歷史連續）；落後太多就跳到現在（資料缺口）。
3. 時間倍率大於 1 之後調回 1：時鐘繼續往前，不跳回實際時間。
4. 寫進 storage 的讀值對齊模擬時間的 10 秒時段：一個 10 分鐘窗剛好 60 筆，與時間倍率無關。
5. Live 的事件時間跟模擬時鐘。
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import pytest

from server.data_broker import DataBroker
from server.farm_registry import FarmRegistry
from server.storage import Storage
from simulator.engine import WindFarmSimulator
from simulator.time_utils import parse_iso

T0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def _collect(sim: WindFarmSimulator) -> List[datetime]:
    stamps: List[datetime] = []
    sim.on_data(lambda readings: stamps.append(parse_iso(str(readings[0]["timestamp"]))))
    return stamps


def _run(sim: WindFarmSimulator, seconds: float, time_step: float) -> None:
    sim.start(time_step=time_step)
    try:
        time.sleep(seconds)
    finally:
        sim.stop()


def _steps(stamps: List[datetime]) -> List[float]:
    return [round((b - a).total_seconds(), 6) for a, b in zip(stamps, stamps[1:])]


# ── 時鐘 ───────────────────────────────────────────────────────────────────


def test_clock_advances_by_exactly_one_step_and_starts_on_a_whole_second() -> None:
    sim = WindFarmSimulator(turbine_count=1)
    stamps = _collect(sim)
    started = datetime.now(timezone.utc)
    _run(sim, 0.6, time_step=0.1)
    assert len(stamps) >= 4
    assert set(_steps(stamps)) == {0.1}, "每一步剛好 time_step 秒，不帶計算時間的漂移"
    assert stamps[0].microsecond == 0 and abs((stamps[0] - started).total_seconds()) <= 1.0
    assert sim.sim_clock == stamps[-1]
    # 不超前實際時間：時間到了才算那一步
    assert stamps[-1] <= datetime.now(timezone.utc)


def test_clock_catches_up_when_behind() -> None:
    """落後 40 秒（例：產生情境的批次剛結束、重啟還原）：不等待，連續補跑到現在，中間沒有缺口。"""
    sim = WindFarmSimulator(turbine_count=1)
    stamps = _collect(sim)
    behind = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=40)
    sim._sim_clock = behind
    _run(sim, 1.5, time_step=1.0)
    assert stamps[0] == behind + timedelta(seconds=1)
    assert len(stamps) >= 40, "1.5 秒內要補完 40 步"
    assert set(_steps(stamps)) == {1.0}
    assert (datetime.now(timezone.utc) - stamps[-1]).total_seconds() < 3.0


def test_clock_jumps_when_too_far_behind(monkeypatch) -> None:
    monkeypatch.setattr(WindFarmSimulator, "MAX_CATCH_UP_S", 30.0)
    sim = WindFarmSimulator(turbine_count=1)
    stamps = _collect(sim)
    now = datetime.now(timezone.utc)
    sim._sim_clock = now.replace(microsecond=0) - timedelta(seconds=300)
    _run(sim, 0.3, time_step=1.0)
    assert stamps and abs((stamps[0] - now).total_seconds()) <= 1.5, "直接跳到現在，留下缺口"
    assert stamps[0].microsecond == 0


def test_clock_never_goes_back_after_acceleration() -> None:
    """時間倍率大於 1 時時鐘跑在實際時間前面；調回 1 之後維持領先的量繼續走，不跳回實際時間。"""
    sim = WindFarmSimulator(turbine_count=1)
    stamps = _collect(sim)
    sim.time_scale = 40.0
    sim.start(time_step=1.0)
    try:
        time.sleep(0.3)   # 第一個 tick：連跑 40 步
        sim.time_scale = 1.0
        time.sleep(2.4)   # 回到 1 倍：每個實際秒一步
    finally:
        sim.stop()
    assert len(stamps) >= 41
    assert all(step == 1.0 for step in _steps(stamps)), "每一步仍是 1 秒，時間沒有往回或跳躍"
    assert (stamps[-1] - datetime.now(timezone.utc)).total_seconds() > 30, "領先的量保留下來"
    assert len(stamps) <= 40 + 4, "調回 1 倍之後不再連跑"


def test_restart_continues_from_the_clock(monkeypatch) -> None:
    """stop_live_loop → restore_live_loop（批次前後）之間的時間，恢復後補跑，時鐘不重設。"""
    sim = WindFarmSimulator(turbine_count=1)
    stamps = _collect(sim)
    _run(sim, 0.25, time_step=0.1)
    first = list(stamps)
    time.sleep(0.5)
    _run(sim, 0.25, time_step=0.1)
    assert stamps[len(first)] == first[-1] + timedelta(seconds=0.1)
    assert set(_steps(stamps)) == {0.1}


# ── 寫入間隔 ───────────────────────────────────────────────────────────────


@pytest.fixture
def broker(tmp_path) -> DataBroker:
    b = DataBroker(farm_registry=FarmRegistry(data_dir=tmp_path))
    b.storage = Storage(db_path=str(tmp_path / "clock.db"))
    b.simulator = WindFarmSimulator(turbine_count=1)
    b._session_id = b.storage.create_session(data_source="simulation", turbine_count=1)
    b._source_active = True
    b._source_kind = "simulation"
    return b


def _stored(broker: DataBroker) -> List[datetime]:
    return [parse_iso(str(row["timestamp"])) for row in broker.storage.live_readings("WT001", limit=5000)]


def test_storage_writes_are_aligned_to_ten_second_slots(broker: DataBroker) -> None:
    sim = broker.simulator
    assert sim is not None
    for i in range(7, 7 + 1300):  # 00:00:07 起，每步 1 秒，跑 21 分多鐘
        broker._on_sim_data(sim._run_one_step(T0 + timedelta(seconds=i), 1.0))
    stored = _stored(broker)
    assert stored[0] == T0 + timedelta(seconds=7), "啟動後的第一筆立刻寫"
    assert all(ts.second % 10 == 0 and ts.microsecond == 0 for ts in stored[1:])
    assert set(_steps(stored[1:])) == {10.0}
    window = [ts for ts in stored if T0 + timedelta(minutes=10) <= ts < T0 + timedelta(minutes=20)]
    assert len(window) == 60, "一個完整的 10 分鐘窗剛好 60 筆"
    assert broker.live_sample_period_s == 10.0


def test_storage_interval_follows_simulated_time_not_wall_time(broker: DataBroker) -> None:
    """加速時 callback 連續被呼叫（實際時間幾乎沒走）：照模擬時間每 10 秒寫一筆，不變稀疏。"""
    sim = broker.simulator
    assert sim is not None
    sim.time_scale = 600.0
    started = time.time()
    for i in range(1, 121):
        broker._on_sim_data(sim._run_one_step(T0 + timedelta(seconds=i), 1.0))
    assert time.time() - started < 5.0
    stored = _stored(broker)
    assert [ts.second for ts in stored[:4]] == [1, 10, 20, 30] and len(stored) == 13
    assert broker.live_sample_period_s == 10.0, "取樣週期不隨時間倍率改變"


def test_steps_that_do_not_divide_the_slot_still_write_once_per_slot(broker: DataBroker) -> None:
    sim = broker.simulator
    assert sim is not None
    for i in range(1, 41):  # 每步 3 秒
        broker._on_sim_data(sim._run_one_step(T0 + timedelta(seconds=3 * i), 3.0))
    slots = [int(ts.timestamp() // 10) for ts in _stored(broker)]
    assert slots == sorted(set(slots)), "每個 10 秒時段只寫一筆"
    assert len(slots) == 13  # 00:00:03 … 00:02:00 跨 13 個時段


# ── 事件時間 ───────────────────────────────────────────────────────────────


def _event_times(broker: DataBroker) -> Dict[str, str]:
    return {e["title"]: e["timestamp"] for e in broker.storage.query_events(limit=50)}


def test_live_events_use_the_simulation_clock(broker: DataBroker) -> None:
    sim = broker.simulator
    assert sim is not None
    ahead = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0)
    sim._sim_clock = ahead
    sim._running = True
    assert broker.live_clock() == ahead
    broker.record_event(event_type="operator", source="maintenance", title="live-event")
    broker.record_event(event_type="operator", source="maintenance", title="explicit",
                        timestamp=T0.isoformat())
    scenario = broker.storage.create_session(data_source="simulation", turbine_count=1, config={"kind": "scenario"})
    broker.record_event(event_type="operator", source="scenario", title="scenario-event", session_id=scenario)
    times = _event_times(broker)
    assert parse_iso(times["live-event"]) == ahead, "Live 的事件與讀值同一個時鐘"
    assert parse_iso(times["explicit"]) == T0
    scenario_gap = (parse_iso(times["scenario-event"]) - datetime.now(timezone.utc)).total_seconds()
    assert abs(scenario_gap) < 5, "指定 session 的事件（情境）不套 Live 的時鐘"


def test_events_fall_back_to_wall_time_when_not_live(broker: DataBroker) -> None:
    sim = broker.simulator
    assert sim is not None
    sim._sim_clock = datetime.now(timezone.utc) + timedelta(days=3)
    for running, bulk, kind in ((False, False, "simulation"), (True, True, "simulation"), (True, False, "scenario")):
        sim._running, sim._bulk_running, broker._source_kind = running, bulk, kind
        assert broker.live_clock() is None
    broker.record_event(event_type="operator", source="maintenance", title="not-live")
    stamp = parse_iso(_event_times(broker)["not-live"])
    assert abs((stamp - datetime.now(timezone.utc)).total_seconds()) < 5


def test_source_kind_is_known_before_the_live_loop_starts(tmp_path, monkeypatch) -> None:
    """Live 執行緒一起來就會送事件：那時 broker 必須已經知道來源是即時模擬，事件才拿得到模擬時鐘。"""
    from server.models import DataSourceConfig, DataSourceMode, SimulationConfig

    seen: Dict[str, object] = {}
    original = DataBroker._start_simulator

    def spy(self: DataBroker, run_loop: bool = True, fresh: bool = False) -> None:
        seen["kind"] = self._source_kind
        original(self, run_loop=run_loop, fresh=fresh)

    monkeypatch.setattr(DataBroker, "_start_simulator", spy)
    for run_loop, kind in ((True, "simulation"), (False, "scenario")):
        b = DataBroker(farm_registry=FarmRegistry(data_dir=tmp_path / kind))
        b.start(DataSourceConfig(mode=DataSourceMode.SIMULATION), SimulationConfig(turbineCount=1, timeStep=1.0),
                run_loop=run_loop)
        try:
            assert seen["kind"] == kind
        finally:
            b.stop()


def test_closing_events_uses_the_simulation_clock(broker: DataBroker) -> None:
    """事件的結束時間與開始時間同一個時鐘：加速之後不會出現「結束早於開始」。"""
    sim = broker.simulator
    assert sim is not None
    ahead = (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0)
    sim._sim_clock, sim._running = ahead, True
    broker.record_event(event_type="fault_lifecycle", source="simulator", title="open-one", turbine_id="WT001")
    sim._sim_clock = ahead + timedelta(seconds=90)
    broker.close_open_events(event_type="fault_lifecycle", source="simulator", turbine_id="WT001")
    event = next(e for e in broker.storage.query_events("WT001", limit=10) if e["title"] == "open-one")
    assert parse_iso(event["timestamp"]) == ahead
    assert parse_iso(event["end_timestamp"]) == ahead + timedelta(seconds=90)


def test_snapshot_window_is_measured_in_simulated_time(broker: DataBroker) -> None:
    """補跑或加速時一個實際秒有幾十步：快照視窗若用實際時間算，一次事件會存下幾十萬列。"""
    sim = broker.simulator
    assert sim is not None
    sim._running = True
    for i in range(1, 6):
        sim._sim_clock = T0 + timedelta(seconds=i)
        broker._on_sim_data(sim._run_one_step(sim._sim_clock, 1.0))
    broker._trigger_snapshot("WT001", f"stop:WT001:7:{broker._live_stamp()}")
    assert broker._snapshot_active["WT001"] == (T0 + timedelta(seconds=5)).timestamp() + broker.SNAPSHOT_WINDOW_S
    assert broker._snapshot_event_ref["WT001"].endswith("2026-01-01T00:00:05.000000+00:00"), "事件參照也跟模擬時鐘"
    started = time.time()
    for i in range(6, broker.SNAPSHOT_WINDOW_S + 60):   # 幾秒內跑完超過一個視窗的模擬時間
        sim._sim_clock = T0 + timedelta(seconds=i)
        broker._on_sim_data(sim._run_one_step(sim._sim_clock, 1.0))
    assert time.time() - started < 60
    assert "WT001" not in broker._snapshot_active, "模擬時間過了視窗就停，不看實際時間"
    conn = broker.storage._get_conn()
    count = conn.execute("SELECT COUNT(*) FROM turbine_snapshots").fetchone()[0]
    assert count <= broker.SNAPSHOT_WINDOW_S + 5, f"視窗內每秒一列，最多 {broker.SNAPSHOT_WINDOW_S} 列上下（實得 {count}）"


def test_callback_failures_are_reported_once_not_swallowed(capsys) -> None:
    sim = WindFarmSimulator(turbine_count=1)

    def broken(_: List[Dict]) -> None:
        raise RuntimeError("storage is gone")

    sim.on_data(broken)
    for i in range(1, 4):
        sim._emit(sim._run_one_step(T0 + timedelta(seconds=i), 1.0))
    out = capsys.readouterr().out
    assert out.count("callback 出錯") == 1 and "storage is gone" in out, "看得到，但不逐次洗版"
    assert sim._emit_failures == 3
