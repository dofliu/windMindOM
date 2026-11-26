"""重啟續跑（WMOM-20261125-03-b）：即時模擬的狀態存檔與還原。

1. 還原後接著跑，與沒有中斷的那一份逐位元相同（故障、PLC 鎖存、亂數狀態都帶著）。
2. 存檔與目前的程式 / 機組 / 時區對不上時不還原，風場從頭開始；壞檔不會讓伺服器起不來。
3. broker：開了才存檔與還原；停止時存一次、Live 迴圈定期存；重啟後時鐘接著走、連續段編號不變。
4. 產生情境（批次）不動到即時風場的狀態。
"""

from __future__ import annotations

import pickle
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
from server.models import DataSourceConfig, DataSourceMode, SimulationConfig
from simulator import checkpoint as cp
from simulator.engine import WindFarmSimulator

T0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
FAULT_ID = "main_bearing_temp_sensor_wire_break"  # 量測回路斷線：幾秒內就鎖存跳機 242


def _advance(sim: WindFarmSimulator, first: int, steps: int) -> List[Dict]:
    readings: List[Dict] = []
    for i in range(first, first + steps):
        readings = sim._run_one_step(T0 + timedelta(seconds=i), 1.0)
    return readings


def _tripped_sim(turbines: int = 2) -> WindFarmSimulator:
    sim = WindFarmSimulator(turbine_count=turbines)
    _advance(sim, 1, 20)
    assert sim.fault_engine.inject(FAULT_ID, "WT001", severity_rate=0.05, initial_severity=1.0)
    _advance(sim, 21, 60)
    assert sim.turbines["WT001"].plc.active_lists.snapshot()["T1"] == [242], "測試前提：跳機已鎖存"
    return sim


# ── 模擬器：存檔 / 還原 ────────────────────────────────────────────────────


def test_restored_simulator_continues_bit_identically() -> None:
    original = _tripped_sim()
    blob = original.checkpoint_state()
    restored = WindFarmSimulator(turbine_count=2)
    restored.restore_state(blob)

    assert restored.turbines["WT001"].plc.active_lists.snapshot() == {"A": [], "T1": [242], "T2": []}
    assert restored.turbines["WT001"].maintenance_lock is True
    assert [(f.turbine_id, f.scenario_id, f.tripped) for f in restored.fault_engine.active_faults] == [
        ("WT001", FAULT_ID, True)]

    for i in range(81, 201):
        a = original._run_one_step(T0 + timedelta(seconds=i), 1.0)
        b = restored._run_one_step(T0 + timedelta(seconds=i), 1.0)
        assert [r["scada"] for r in a] == [r["scada"] for r in b], f"第 {i} 步開始不同"
    assert original.turbines["WT002"].plc.drain_events() == restored.turbines["WT002"].plc.drain_events()


def test_restore_keeps_runtime_wiring_and_clears_history() -> None:
    source = _tripped_sim()
    blob = source.checkpoint_state()
    target = WindFarmSimulator(turbine_count=2)
    seen: List[int] = []
    target.on_data(lambda readings: seen.append(len(readings)))
    target.bulk_runs = 7
    _advance(target, 1, 3)
    assert len(target.history["WT001"]) == 3
    target.restore_state(blob)
    assert target.bulk_runs == 7 and len(target._callbacks) == 1, "批次計數與 callback 不屬於存檔"
    assert all(len(h) == 0 for h in target.history.values())
    assert target.latest_data["WT001"]["timestamp"] == source.latest_data["WT001"]["timestamp"]


def test_restore_is_refused_while_the_live_loop_runs() -> None:
    sim = WindFarmSimulator(turbine_count=1)
    blob = sim.checkpoint_state()
    sim.start(time_step=5.0)
    try:
        with pytest.raises(RuntimeError):
            sim.restore_state(blob)
    finally:
        sim.stop()
    sim.restore_state(blob)  # 停了就可以


def test_restore_rejects_a_state_from_a_different_farm() -> None:
    blob = WindFarmSimulator(turbine_count=3).checkpoint_state()
    with pytest.raises(ValueError):
        WindFarmSimulator(turbine_count=2).restore_state(blob)
    with pytest.raises(ValueError):
        WindFarmSimulator(turbine_count=2).restore_state(pickle.dumps({"turbines": {}}))


def test_live_loop_hands_state_to_the_checkpoint_sink(monkeypatch) -> None:
    monkeypatch.setattr(WindFarmSimulator, "CHECKPOINT_INTERVAL_S", 0.15)
    sim = WindFarmSimulator(turbine_count=1)
    blobs: List[bytes] = []
    sim.on_checkpoint(blobs.append)
    sim.start(time_step=0.05)
    try:
        time.sleep(0.6)
    finally:
        sim.stop()
    assert 2 <= len(blobs) <= 5
    twin = WindFarmSimulator(turbine_count=1)
    twin.restore_state(blobs[-1])
    assert twin.sim_clock is not None and twin.sim_clock <= sim.sim_clock


def test_a_failing_sink_does_not_stop_the_simulation(monkeypatch) -> None:
    monkeypatch.setattr(WindFarmSimulator, "CHECKPOINT_INTERVAL_S", 0.05)
    sim = WindFarmSimulator(turbine_count=1)

    def broken(_: bytes) -> None:
        raise OSError("disk full")

    sim.on_checkpoint(broken)
    sim.start(time_step=0.05)
    try:
        time.sleep(0.4)
        assert sim.is_running and sim.sim_clock is not None
    finally:
        sim.stop()


# ── 存檔檔案 ───────────────────────────────────────────────────────────────


def _checkpoint(state: bytes = b"state", **overrides: object) -> cp.LiveCheckpoint:
    fields: Dict[str, object] = dict(state=state, sim_clock=T0, turbine_ids=["WT001", "WT002"],
                                     site_timezone="Asia/Taipei", live_epoch=5, saved_at="2026-01-01T00:00:00+00:00")
    fields.update(overrides)
    return cp.LiveCheckpoint(**fields)  # type: ignore[arg-type]  測試用的欄位覆寫


def test_checkpoint_file_roundtrip(tmp_path) -> None:
    path = tmp_path / "farm" / cp.CHECKPOINT_FILENAME
    cp.save_checkpoint(path, _checkpoint())
    assert not path.with_name(path.name + ".tmp").exists(), "暫存檔換名後不留下"
    loaded = cp.load_checkpoint(path, ["WT001", "WT002"], "Asia/Taipei")
    assert loaded == _checkpoint()


def test_checkpoint_is_not_restored_when_anything_differs(tmp_path, monkeypatch) -> None:
    path = tmp_path / cp.CHECKPOINT_FILENAME
    assert cp.load_checkpoint(path, ["WT001"], "Asia/Taipei") is None, "沒有檔案"
    # state 故意放解不開的內容：對不上的時候不能去解它
    cp.save_checkpoint(path, _checkpoint(state=b"\x80\x05not-a-pickle"))
    assert cp.load_checkpoint(path, ["WT001", "WT002", "WT003"], "Asia/Taipei") is None, "機組不同"
    assert cp.load_checkpoint(path, ["WT001", "WT002"], "Europe/Amsterdam") is None, "時區不同"
    assert cp.load_checkpoint(path, ["WT001", "WT002"], "Asia/Taipei") is not None

    monkeypatch.setattr(cp, "code_fingerprint", lambda: "another-build")
    assert cp.load_checkpoint(path, ["WT001", "WT002"], "Asia/Taipei") is None, "模擬器程式改過"
    monkeypatch.undo()
    monkeypatch.setattr(cp, "CHECKPOINT_VERSION", cp.CHECKPOINT_VERSION + 1)
    assert cp.load_checkpoint(path, ["WT001", "WT002"], "Asia/Taipei") is None, "存檔格式版本不同"


def test_corrupt_checkpoint_is_ignored(tmp_path) -> None:
    path = tmp_path / cp.CHECKPOINT_FILENAME
    path.write_bytes(b"\x00\x01 truncated")
    assert cp.load_checkpoint(path, ["WT001"], "Asia/Taipei") is None
    path.write_bytes(pickle.dumps({"version": cp.CHECKPOINT_VERSION, "state": "not-bytes"}))
    assert cp.load_checkpoint(path, ["WT001"], "Asia/Taipei") is None


def test_truncated_or_unreadable_checkpoint_never_raises(tmp_path) -> None:
    """壞檔一律當作沒有存檔：伺服器不能因為存檔起不來。"""
    path = tmp_path / cp.CHECKPOINT_FILENAME
    cp.save_checkpoint(path, _checkpoint(state=b"x" * 500))
    whole = path.read_bytes()
    for cut in (5, len(cp._MAGIC) + 2, len(whole) - 400, len(whole) - 1):
        path.write_bytes(whole[:cut])  # 寫到一半就斷電
        assert cp.load_checkpoint(path, ["WT001", "WT002"], "Asia/Taipei") is None, f"截在 {cut}"
    path.write_bytes(whole + b"extra")
    assert cp.load_checkpoint(path, ["WT001", "WT002"], "Asia/Taipei") is None, "長度與檔頭記的不符"

    def write(header: Dict[str, object], state: bytes = b"state") -> None:
        import json
        encoded = json.dumps(header).encode("utf-8")
        path.write_bytes(cp._MAGIC + len(encoded).to_bytes(4, "big") + encoded + state)

    good: Dict[str, object] = {
        "version": cp.CHECKPOINT_VERSION, "fingerprint": cp.code_fingerprint(), "saved_at": "",
        "sim_clock": "2026-01-01T00:00:00+00:00", "turbine_ids": ["WT001"], "site_timezone": "Asia/Taipei",
        "live_epoch": 3, "state_bytes": 5}
    write(good)
    assert cp.load_checkpoint(path, ["WT001"], "Asia/Taipei") is not None, "測試前提：手寫的檔頭是好的"
    for field, value in (("sim_clock", "not-a-time"), ("live_epoch", "abc"), ("turbine_ids", "WT001"),
                         ("turbine_ids", None), ("state_bytes", "5")):
        write({**good, field: value})
        assert cp.load_checkpoint(path, ["WT001"], "Asia/Taipei") is None, f"{field}={value!r}"
    path.write_bytes(cp._MAGIC + (10).to_bytes(4, "big") + b"[1, 2, 3]!" + b"state")
    assert cp.load_checkpoint(path, ["WT001"], "Asia/Taipei") is None, "檔頭不是物件"


def test_fingerprint_covers_the_simulator_sources() -> None:
    fingerprint = cp.code_fingerprint()
    assert len(fingerprint) == 64 and fingerprint == cp.code_fingerprint()
    sources = {str(p) for p in cp._FINGERPRINT_SOURCES}
    assert any(s.endswith("simulator") for s in sources) and any(s.endswith("wind_model.py") for s in sources)
    assert all(Path(s).exists() for s in sources), "指紋來源不存在的話，改了也偵測不到"


# ── broker：停止時存、啟動時還原 ───────────────────────────────────────────


def _broker(tmp_path, enabled: bool) -> DataBroker:
    b = DataBroker(farm_registry=FarmRegistry(data_dir=tmp_path))
    b.checkpoint_enabled = enabled
    return b


def _start(b: DataBroker, run_loop: bool = True, turbines: int = 2) -> None:
    b.start(DataSourceConfig(mode=DataSourceMode.SIMULATION), SimulationConfig(turbineCount=turbines, timeStep=1.0),
            run_loop=run_loop)


def test_broker_resumes_the_farm_after_a_restart(tmp_path) -> None:
    first = _broker(tmp_path, enabled=True)
    _start(first)
    sim = first.simulator
    assert sim is not None and first.live_restored is False
    epoch = first.live_epoch
    assert epoch == first._session_id
    time.sleep(0.2)
    sim.stop_live_loop()  # 停下迴圈再動模型，避免和 Live 執行緒搶
    assert sim.fault_engine.inject(FAULT_ID, "WT001", severity_rate=0.05, initial_severity=1.0)
    clock = sim.sim_clock
    assert clock is not None
    for i in range(1, 61):
        sim._run_one_step(clock + timedelta(seconds=i), 1.0)
    sim._sim_clock = clock + timedelta(seconds=60)
    sim.restore_live_loop(True)
    time.sleep(0.2)
    first.stop()
    path = first._checkpoint_path()
    assert path.is_file() and path.parent == Path(first.storage.db_path).parent

    second = _broker(tmp_path, enabled=True)  # 伺服器重啟
    _start(second)
    try:
        restored = second.simulator
        assert restored is not None and second.live_restored is True
        assert second.live_epoch == epoch, "連續段編號沿用（風場狀態沒有重來）"
        assert second._session_id != first._session_id, "每次啟動仍是新的 session"
        assert restored.turbines["WT001"].plc.active_lists.snapshot()["T1"] == [242], "重啟前鎖存的跳機還在"
        assert [f.scenario_id for f in restored.fault_engine.active_faults] == [FAULT_ID]
        time.sleep(0.3)
        assert restored.sim_clock is not None and restored.sim_clock >= clock + timedelta(seconds=60), "時鐘不往回"
    finally:
        second.stop()


def test_broker_does_not_touch_checkpoints_unless_enabled(tmp_path) -> None:
    seeded = _broker(tmp_path, enabled=True)
    _start(seeded)
    time.sleep(0.1)
    seeded.stop()
    path = seeded._checkpoint_path()
    stamp = path.stat().st_mtime_ns

    plain = _broker(tmp_path, enabled=False)
    _start(plain)
    time.sleep(0.1)
    assert plain.live_restored is False and plain.simulator is not None
    assert plain.simulator._checkpoint_sink is None
    plain.stop()
    assert path.stat().st_mtime_ns == stamp, "沒開就不讀也不寫"


def test_scenario_mode_neither_restores_nor_saves(tmp_path) -> None:
    seeded = _broker(tmp_path, enabled=True)
    _start(seeded)
    time.sleep(0.1)
    seeded.stop()
    stamp = seeded._checkpoint_path().stat().st_mtime_ns

    scenario = _broker(tmp_path, enabled=True)
    _start(scenario, run_loop=False)  # 產生情境：要乾淨、可重現的模擬器
    assert scenario.live_restored is False and scenario.source_kind == "scenario"
    scenario.stop()
    assert scenario._checkpoint_path().stat().st_mtime_ns == stamp


def test_broker_starts_fresh_when_the_checkpoint_does_not_fit(tmp_path, capsys) -> None:
    seeded = _broker(tmp_path, enabled=True)
    _start(seeded, turbines=2)
    time.sleep(0.1)
    seeded.stop()

    other = _broker(tmp_path, enabled=True)
    _start(other, turbines=3)  # 機組數改了
    try:
        assert other.live_restored is False and other.live_epoch == other._session_id
    finally:
        other.stop()

    # 內層解不開（外層資訊都對）：印出原因、從頭開始，伺服器照常啟動
    path = other._checkpoint_path()
    cp.save_checkpoint(path, cp.LiveCheckpoint(state=b"garbage", sim_clock=T0, turbine_ids=["WT001", "WT002", "WT003"],
                                               site_timezone="Asia/Taipei", live_epoch=1, saved_at=""))
    broken = _broker(tmp_path, enabled=True)
    _start(broken, turbines=3)
    try:
        assert broken.live_restored is False and broken.simulator is not None and broken.simulator.is_running
        assert "還原失敗" in capsys.readouterr().out
    finally:
        broken.stop()


def _take_over(broker: DataBroker) -> datetime:
    """停下 Live 迴圈，改由測試一步一步推；回傳下一個 10 秒整點（之後的秒數都從它起算）。"""
    sim = broker.simulator
    assert sim is not None
    sim.stop_live_loop()
    clock = sim.sim_clock
    assert clock is not None
    clock = clock.replace(microsecond=0)
    return clock + timedelta(seconds=10 - clock.second % 10)


def _drive(broker: DataBroker, base: datetime, seconds: range) -> None:
    """照 Live 迴圈的做法推進：時鐘、物理、交給 broker（事件因此也跟模擬時鐘）。"""
    simulator = broker.simulator
    assert simulator is not None
    simulator._running = True  # 沒有執行緒，但 broker 據此認定即時模擬在跑（live_clock）
    for i in seconds:
        moment = base + timedelta(seconds=i)
        simulator._sim_clock = moment
        broker._on_sim_data(simulator._run_one_step(moment, 1.0))


def _offset(broker: DataBroker, base: datetime) -> int:
    simulator = broker.simulator
    assert simulator is not None and simulator.sim_clock is not None
    return int((simulator.sim_clock - base).total_seconds())


def _kill(broker: DataBroker) -> None:
    """伺服器被強制關閉：沒有停止時的那次存檔。"""
    broker.checkpoint_enabled = False
    broker.stop()


def _stored_offsets(broker: DataBroker, base: datetime) -> List[int]:
    from simulator.time_utils import parse_iso
    return [int((parse_iso(str(r["timestamp"])) - base).total_seconds())
            for r in broker.storage.live_readings("WT001", limit=1000)]


def _trip_times(broker: DataBroker) -> List[str]:
    return [e["timestamp"] for e in broker.storage.query_events("WT001", limit=500)
            if e.get("source") == "plc" and (e.get("payload") or {}).get("kind") == "trip"]


def _event_keys(broker: DataBroker) -> List[tuple]:
    return sorted((e["timestamp"], e.get("turbine_id") or "", e["source"], e["event_type"], e["title"])
                  for e in broker.storage.query_events(limit=2000))


def test_hard_kill_does_not_duplicate_what_was_already_stored(tmp_path) -> None:
    """伺服器被強制關閉：存檔點到關閉之間的讀值與事件已經在 storage 裡，重啟後重跑那一段時不再寫一次。"""
    first = _broker(tmp_path, enabled=True)
    _start(first)
    base = _take_over(first)
    sim = first.simulator
    assert sim is not None
    _drive(first, base, range(0, 16))              # … +15 s
    sim.fault_engine.inject(FAULT_ID, "WT001", severity_rate=0.05, initial_severity=1.0)
    _drive(first, base, range(16, 41))             # 跳機發生在這一段
    first._write_live_checkpoint(sim.checkpoint_state())   # 定期存檔：時鐘在 +40 s
    _drive(first, base, range(41, 76))             # 存檔之後又跑了 35 秒才被強制關閉
    before_rows, before_trips, before_events = _stored_offsets(first, base), _trip_times(first), _event_keys(first)
    _kill(first)
    assert before_rows[-1] == 70 and len(before_trips) == 1

    second = _broker(tmp_path, enabled=True)
    _start(second)
    restored = second.simulator
    assert restored is not None and second.live_restored
    restored.stop_live_loop()
    # 從存檔點（+40 s）接著跑；停下迴圈之前 Live 執行緒可能已經多跑了一兩步
    assert 40 <= _offset(second, base) <= 43
    assert second._replay_until == base + timedelta(seconds=70), "重跑段到上次已寫入的時間為止"
    _drive(second, base, range(_offset(second, base) + 1, 121))
    rows, events = _stored_offsets(second, base), _event_keys(second)
    _kill(second)

    assert rows[:len(before_rows)] == before_rows, "重啟前寫的列原封不動"
    assert rows[len(before_rows):] == [80, 90, 100, 110, 120], "重跑段不重寫，之後接著下一個 10 秒時段"
    assert len(rows) == len(set(rows))
    assert _trip_times(second) == before_trips, "跳機事件不重複"
    assert len(events) == len(set(events)) and set(before_events) <= set(events), "任何事件都不重複、也不少"


def _trip_delay_steps() -> int:
    """注入量測回路斷線之後第幾步鎖存跳機 242（PLC 的延時是固定的步數）。"""
    sim = WindFarmSimulator(turbine_count=2)
    _advance(sim, 1, 20)
    assert sim.fault_engine.inject(FAULT_ID, "WT001", severity_rate=0.05, initial_severity=1.0)
    for step in range(1, 60):
        sim._run_one_step(T0 + timedelta(seconds=20 + step), 1.0)
        if sim.turbines["WT001"].plc.active_lists.snapshot()["T1"] == [242]:
            return step
    raise AssertionError("測試前提：注入後一分鐘內要跳機")


def test_hard_kill_does_not_repeat_events_recorded_after_the_last_stored_reading(tmp_path) -> None:
    """讀值每 10 秒才寫一次，事件是每一步都記：最後一筆讀值之後、被強制關閉之前記下的事件，重啟後重跑
    同一步時不能再記一次（code review must-fix）。"""
    delay = _trip_delay_steps()
    inject_at = 20 + (5 - (20 + delay)) % 10      # 讓跳機落在某個 10 秒時段的第 5 秒
    trip_at = inject_at + delay
    assert trip_at % 10 == 5

    first = _broker(tmp_path, enabled=True)
    _start(first)
    base = _take_over(first)
    sim = first.simulator
    assert sim is not None
    _drive(first, base, range(0, inject_at + 1))
    sim.fault_engine.inject(FAULT_ID, "WT001", severity_rate=0.05, initial_severity=1.0)
    _drive(first, base, range(inject_at + 1, trip_at - 1))
    first._write_live_checkpoint(sim.checkpoint_state())    # 存檔：跳機前 2 秒
    _drive(first, base, range(trip_at - 1, trip_at + 3))    # 跳機，再 2 秒後被強制關閉
    before_rows, before_trips, before_events = _stored_offsets(first, base), _trip_times(first), _event_keys(first)
    _kill(first)
    assert before_rows[-1] == trip_at - 5, "測試前提：最後一筆讀值在跳機之前"
    assert len(before_trips) == 1 and before_trips[0] > first.storage.last_live_reading_timestamp("WT001")
    assert len([e for e in before_events if e[1] == "WT001" and e[0] >= before_trips[0]]) >= 2, \
        "測試前提：跳機那幾步不只一筆事件（PLC 跳機、狀態轉換）"

    second = _broker(tmp_path, enabled=True)
    _start(second)
    restored = second.simulator
    assert restored is not None and second.live_restored
    restored.stop_live_loop()
    assert second._replay_until is None, "存檔點在最後一筆寫入之後：沒有重跑段"
    assert second._dedupe_until == base + timedelta(seconds=trip_at + 5), "去重段到下一個時段開始為止"
    _drive(second, base, range(_offset(second, base) + 1, trip_at + 41))
    rows, events = _stored_offsets(second, base), _event_keys(second)
    assert second._dedupe_until is None, "去重段結束後不再查重"
    _kill(second)

    assert _trip_times(second) == before_trips, "跳機事件只有一筆"
    assert len(events) == len(set(events)), "沒有任何事件重複"
    assert set(before_events) <= set(events)
    assert rows == before_rows + [trip_at + 5, trip_at + 15, trip_at + 25, trip_at + 35]


def test_clean_restart_does_not_repeat_fault_lifecycle_events(tmp_path) -> None:
    """正常重啟時故障還開著：「故障開始」在重啟前記過了，重啟後第一批讀值進來不能再記一次。"""
    first = _broker(tmp_path, enabled=True)
    _start(first)
    base = _take_over(first)
    sim = first.simulator
    assert sim is not None
    _drive(first, base, range(0, 16))
    sim.fault_engine.inject(FAULT_ID, "WT001", severity_rate=0.05, initial_severity=1.0)
    _drive(first, base, range(16, 61))

    def lifecycle(broker: DataBroker) -> List[str]:
        return sorted(e["title"] for e in broker.storage.query_events("WT001", limit=500)
                      if e["event_type"] == "fault_lifecycle")

    before = lifecycle(first)
    assert before.count(f"Fault started: {FAULT_ID}") == 1
    first.stop()  # 正常停止：存檔

    second = _broker(tmp_path, enabled=True)
    _start(second)
    assert second.live_restored
    base2 = _take_over(second)
    _drive(second, base2, range(0, 30))
    after = lifecycle(second)
    second.stop()
    assert after == before, "重啟不產生新的故障生命週期事件"


def test_rows_far_from_the_checkpoint_do_not_open_a_replay_window(tmp_path) -> None:
    """storage 裡最後一筆 Live 讀值離存檔點很遠（例：沒有命名的批次把模擬時間的列寫進 Live session）：
    不拿它當重跑的依據，否則即時資料會有很長一段不寫。"""
    first = _broker(tmp_path, enabled=True)
    _start(first)
    base = _take_over(first)
    sim = first.simulator
    assert sim is not None
    _drive(first, base, range(0, 21))
    first._write_live_checkpoint(sim.checkpoint_state())
    far = dict(sim.latest_data["WT001"])
    far["timestamp"] = (base + timedelta(hours=5)).isoformat()
    first.storage.store_readings([far], first._session_id)
    _kill(first)

    second = _broker(tmp_path, enabled=True)
    _start(second)
    assert second.live_restored
    second.simulator.stop_live_loop()  # type: ignore[union-attr]
    assert second._replay_until is None and second._dedupe_until is None
    _drive(second, base, range(_offset(second, base) + 1, 41))
    rows = _stored_offsets(second, base)
    _kill(second)
    assert [r for r in rows if 20 < r <= 40], "還原後馬上接著寫，沒有被遠處的那一列擋住"


def test_hard_kill_while_accelerated_does_not_rewrite_the_replayed_span(tmp_path) -> None:
    """加速時被強制關閉（WMOM-20261126-01 長跑實測）：存檔每 30 實際秒一次，倍率 200 時存檔點與最後
    一筆寫入可以差好幾分鐘模擬時間。那一段仍是重跑段，讀值不寫第二次、也不在時段中間多寫一筆。"""
    first = _broker(tmp_path, enabled=True)
    _start(first)
    base = _take_over(first)
    sim = first.simulator
    assert sim is not None
    sim.time_scale = 30.0
    _drive(first, base, range(0, 41))
    first._write_live_checkpoint(sim.checkpoint_state())   # 存檔：倍率 30、時鐘在 +40 s
    _drive(first, base, range(41, 601))                     # 存檔之後又跑了 9 分多鐘（> 120 s）
    before = _stored_offsets(first, base)
    _kill(first)
    assert before[-1] == 600

    second = _broker(tmp_path, enabled=True)
    _start(second)
    restored = second.simulator
    assert restored is not None and second.live_restored
    restored.stop_live_loop()
    assert restored.time_scale == 1.0
    assert second._replay_until == base + timedelta(seconds=600), "存檔時的倍率放寬了重跑段的範圍"
    _drive(second, base, range(_offset(second, base) + 1, 631))
    rows = _stored_offsets(second, base)
    _kill(second)
    assert rows[:len(before)] == before
    assert rows[len(before):] == [610, 620, 630]
    assert len(rows) == len(set(rows))


def test_changing_the_time_scale_requests_a_checkpoint() -> None:
    """改倍率之後盡快存檔：存檔裡的倍率才涵蓋存檔點之後跑的那一段。"""
    sim = WindFarmSimulator(turbine_count=1)
    sim._checkpoint_requested = False
    sim.time_scale = 1.0
    assert sim._checkpoint_requested is False, "倍率沒變不要求"
    sim.time_scale = 200.0
    assert sim._checkpoint_requested is True


def test_fresh_start_ignores_the_checkpoint(tmp_path) -> None:
    seeded = _broker(tmp_path, enabled=True)
    _start(seeded)
    base = _take_over(seeded)
    assert seeded.simulator is not None
    seeded.simulator.fault_engine.inject(FAULT_ID, "WT001", severity_rate=0.05, initial_severity=1.0)
    _drive(seeded, base, range(0, 40))
    seeded.stop()

    fresh = _broker(tmp_path, enabled=True)
    fresh.start(DataSourceConfig(mode=DataSourceMode.SIMULATION), SimulationConfig(turbineCount=2, timeStep=1.0),
                run_loop=True, fresh=True)
    try:
        assert fresh.live_restored is False and fresh.live_epoch == fresh._session_id
        assert fresh.simulator is not None and not fresh.simulator.fault_engine.active_faults
        assert fresh.simulator._checkpoint_sink is not None, "從頭開始之後照常存檔"
    finally:
        fresh.stop()


def test_restore_returns_the_time_scale_to_one(tmp_path, capsys) -> None:
    """存檔時正在加速：重啟後回到 1 倍（時鐘維持領先），不會一重啟就自己加速跑。"""
    first = _broker(tmp_path, enabled=True)
    _start(first)
    assert first.simulator is not None
    first.simulator.stop_live_loop()
    first.simulator.time_scale = 30.0
    first.simulator._running = True
    first.stop()

    second = _broker(tmp_path, enabled=True)
    _start(second)
    try:
        assert second.live_restored and second.simulator is not None
        assert second.simulator.time_scale == 1.0
        assert "時間倍率" in capsys.readouterr().out
    finally:
        second.stop()


def test_a_failing_lookup_during_restore_does_not_block_the_start(tmp_path, capsys, monkeypatch) -> None:
    seeded = _broker(tmp_path, enabled=True)
    _start(seeded)
    base = _take_over(seeded)
    assert seeded.simulator is not None
    seeded.simulator.fault_engine.inject(FAULT_ID, "WT001", severity_rate=0.05, initial_severity=1.0)
    _drive(seeded, base, range(0, 40))
    seeded.stop()

    from server.storage import Storage

    def boom(self: Storage, turbine_id: str, max_sessions: int = 20) -> str:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(Storage, "last_live_reading_timestamp", boom)
    broken = _broker(tmp_path, enabled=True)
    _start(broken)
    try:
        assert broken.simulator is not None and broken.simulator.is_running
        assert broken.live_restored is False and broken.live_epoch == broken._session_id
        assert not broken.simulator.fault_engine.active_faults, "沒還原成功就是全新的風場，不是還原到一半"
        assert "還原即時模擬的狀態時出錯" in capsys.readouterr().out
    finally:
        broken.stop()


def test_operator_actions_request_a_prompt_checkpoint(tmp_path) -> None:
    broker = _broker(tmp_path, enabled=True)
    _start(broker)
    try:
        sim = broker.simulator
        assert sim is not None
        time.sleep(0.1)
        sim._checkpoint_requested = False
        broker.record_event(event_type="state", source="simulator", title="state change")
        assert sim._checkpoint_requested is False, "模擬器自己的事件不必急著存"
        saved = broker._checkpoint_path().stat().st_mtime_ns if broker._checkpoint_path().exists() else 0
        broker.record_event(event_type="fault", source="faults", title="Fault injected: x")
        time.sleep(1.6)  # 下一步之後就存，不等 30 秒
        assert broker._checkpoint_path().stat().st_mtime_ns > saved
        assert sim._checkpoint_requested is False
    finally:
        broker.stop()


# ── 產生情境不動到即時風場 ─────────────────────────────────────────────────


def test_batch_leaves_the_live_farm_state_untouched(tmp_path) -> None:
    broker = _broker(tmp_path, enabled=False)  # 不必開存檔：批次前後的狀態留在記憶體
    _start(broker)
    try:
        sim = broker.simulator
        assert sim is not None
        time.sleep(0.2)
        sim.stop_live_loop()
        assert sim.fault_engine.inject(FAULT_ID, "WT001", severity_rate=0.05, initial_severity=1.0)
        clock = sim.sim_clock
        assert clock is not None
        for i in range(1, 61):
            sim._run_one_step(clock + timedelta(seconds=i), 1.0)
        sim._sim_clock = clock + timedelta(seconds=60)
        sim.restore_live_loop(True)
        time.sleep(0.2)
        epoch = broker.live_epoch

        with broker.pause_live_for_batch() as was_running:
            assert was_running is True
            history = [r["timestamp"] for r in sim.history["WT001"]]
            assert len(history) > 60
            # 批次會做的事：清故障、重設機組、把模型推到別的時間
            sim.start_clean_scenario()
            sim.generate_bulk(duration_hours=0.05, time_step=10.0)
            assert not sim.fault_engine.active_faults
            assert [r["timestamp"] for r in sim.history["WT001"]] != history, "測試前提：批次會動到走勢歷史"
        try:
            sim.stop_live_loop()
            assert [f.scenario_id for f in sim.fault_engine.active_faults] == [FAULT_ID], "Live 的故障還在"
            assert sim.turbines["WT001"].plc.active_lists.snapshot()["T1"] == [242]
            assert sim.sim_clock is not None and sim.sim_clock >= clock + timedelta(seconds=60)
            assert sim.bulk_runs == 1, "批次計數照常增加（不屬於還原的狀態）"
            assert broker.live_epoch == epoch, "即時資料仍是同一段"
            # 恢復之後 Live 迴圈可能已經多跑了一兩步，所以只比前面那一段
            assert [r["timestamp"] for r in sim.history["WT001"]][:len(history)] == history, \
                "走勢小圖的歷史不被批次洗掉"
        finally:
            sim.restore_live_loop(True)
    finally:
        broker.stop()


def test_failed_restore_after_a_batch_starts_a_new_epoch(tmp_path, capsys, monkeypatch) -> None:
    """批次後還原不了 Live 的狀態：風場其實被批次改掉了，連續段編號要變，外部才知道資料在這裡不連續。"""
    broker = _broker(tmp_path, enabled=False)
    _start(broker)
    try:
        sim = broker.simulator
        assert sim is not None
        time.sleep(0.1)
        epoch = broker.live_epoch

        def boom(blob: bytes) -> None:
            raise ValueError("cannot restore")

        with broker.pause_live_for_batch():
            monkeypatch.setattr(sim, "restore_state", boom)
            sim.start_clean_scenario()
        assert broker.live_epoch != epoch
        assert sim.is_running, "還原失敗仍恢復即時模擬（從批次留下的狀態接著跑）"
        assert "還原即時模擬的狀態失敗" in capsys.readouterr().out
    finally:
        broker.stop()


def test_batch_endpoints_report_the_batch_fault_status_not_the_live_one(tmp_path, monkeypatch) -> None:
    """批次結束後 Live 的狀態會被還原：端點回報的故障狀態要是批次結束當下的，不是還原之後的。"""
    import asyncio

    from server.routers import config as config_ep
    from server.routers import faults as faults_ep

    broker = _broker(tmp_path, enabled=False)
    _start(broker, turbines=3)
    monkeypatch.setattr(config_ep, "get_broker", lambda: broker)
    monkeypatch.setattr(faults_ep, "get_broker", lambda: broker)
    try:
        time.sleep(0.2)
        generated = asyncio.run(config_ep.generate_bulk({
            "duration_hours": 0.02, "time_step": 10.0, "name": "批次狀態", "wind_profile": "moderate",
            "fault_schedule": [{"scenario_id": "hydraulic_leak", "turbine_id": "WT002", "offset_seconds": 0}],
        }))
        assert [(f["turbine_id"], f["scenario_id"]) for f in generated["final_fault_status"]] == [
            ("WT002", "hydraulic_leak")]
        sim = broker.simulator
        assert sim is not None and sim.fault_engine.get_fault_status() == [], "即時風場沒有被批次留下故障"

        from simulator.physics.fault_engine import TestPlanStep as PlanStep  # 別名：避免 pytest 收集
        monkeypatch.setitem(faults_ep.TEST_PLANS, "tiny", {
            "name_en": "tiny", "name_zh": "tiny", "description_en": "", "description_zh": "", "duration_hours": 0.02,
            "steps": [PlanStep(0, "hydraulic_leak", "WT002", 0.002, 0.0, "tiny plan")]})
        ran = asyncio.run(faults_ep.run_test_plan("tiny", {"time_step": 10.0}))
        assert ran["final_fault_status"], "測試計畫結束當下的故障狀態"
        assert sim.fault_engine.get_fault_status() == []
    finally:
        broker.stop()


def test_batch_without_a_running_live_loop_is_unchanged(tmp_path) -> None:
    """產生情境模式（Live 沒在跑）：不留狀態也不還原，批次留下的狀態照舊。"""
    broker = _broker(tmp_path, enabled=False)
    _start(broker, run_loop=False)
    try:
        sim = broker.simulator
        assert sim is not None
        with broker.pause_live_for_batch() as was_running:
            assert was_running is False
            assert sim.fault_engine.inject("bearing_wear", "WT002", severity_rate=0.01, initial_severity=0.2)
        assert [f.scenario_id for f in sim.fault_engine.active_faults] == ["bearing_wear"]
    finally:
        broker.stop()
