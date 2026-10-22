"""模仿 Bachmann Z72 tag 的 OPC UA server（WMOM-20261021-07，EPIC-DS Phase 3c ③）。

同 ``test_replay.py`` 的 2 h 情境（WT001 主軸承磨耗、WT002 超速），一律用 asyncua 的 client 讀回：

1. 事件碼清單規則（``ActiveEventLists``）與 10 分鐘移動平均
2. 節點：真實讀取腳本（``opc_data_reader.py``）的每個 item ID 都讀得到、型別依 PLC、合成 tag 有標示、
   可從 ``Objects/Z72/H01/...`` 瀏覽、client 不能寫
3. 回放：各檢查點的讀值 / 時間戳 / 事件碼陣列 / 狀態節點與 WS 回放的訊息一致
4. 正式評測：server 啟動就開播、WS（``stream=false``）加入同一個時鐘且不送資料；撤銷就停止更新
5. 即時模擬：讀值與 PLC 的事件碼清單、``WMOM_OPCUA_ENABLE`` 開關、埠被占用不擋主程式
6. 出題端 CLI；starter kit 的受測端範例對真的 OPC UA + WS 伺服器跑完一次
"""

from __future__ import annotations

import ast
import asyncio
import logging
import secrets
import socket
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Iterator, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
KIT_DIR = PROJECT_ROOT / "examples" / "rag_starter_kit"
for _p in (PROJECT_ROOT, MONITORING_ROOT, KIT_DIR, PROJECT_ROOT / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from asyncua import Client, ua  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import simulator.engine as engine_mod  # noqa: E402
from server import opcua_config as oc  # noqa: E402
from server import opcua_server as ou  # noqa: E402
from server import replay as rp  # noqa: E402
from server import scenario_pack as sp  # noqa: E402
from server.data_broker import DataBroker  # noqa: E402
from server.routers import config as config_ep  # noqa: E402
from server.routers import replay as replay_ep  # noqa: E402
from server.storage import Storage  # noqa: E402
from shared.alarm_codes import all_alarms  # noqa: E402
from simulator.engine import WindFarmSimulator  # noqa: E402
from simulator.physics.fault_engine import TestPlanStep as PlanStep  # noqa: E402
from simulator.physics.plc_protection import ACTIVE_LIST_SLOTS, ActiveEventLists  # noqa: E402
from simulator.time_utils import iso_utc, parse_iso, utc_now  # noqa: E402

T0 = datetime(2026, 1, 15, 3, 0, tzinfo=timezone.utc)
READER = PROJECT_ROOT / "shared" / "plc_clients" / "bachmann" / "opc_data_reader.py"
EVAL_SPEED = 3000.0  # 正式評測上限：3 台 × 3000 ÷ 10 s ≤ 1000 筆 / 秒；2 h 情境 2.4 s 播完
FAST = 10_000.0


class _FakeBroker:
    """情境生成端點用到的 broker 表面（同 ``test_replay.py``）。"""

    _PLC_EVENT_TITLES = DataBroker._PLC_EVENT_TITLES
    _plc_event_fields = DataBroker._plc_event_fields
    _state_transition_fields = DataBroker._state_transition_fields
    _state_name = DataBroker._state_name
    record_bulk_events = DataBroker.record_bulk_events

    def __init__(self, storage: Storage, simulator: WindFarmSimulator) -> None:
        self.storage = storage
        self.simulator = simulator
        self._session_id = storage.create_session(data_source="simulation", turbine_count=3)

    @contextmanager
    def pause_live_for_batch(self) -> Iterator[bool]:
        yield False

    def record_event(self, session_id: Optional[int] = None, **kwargs: object) -> None:
        self.storage.record_event(session_id=session_id if session_id is not None else self._session_id,
                                  **kwargs)  # type: ignore[arg-type]  # 轉交 record_event 的關鍵字參數


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Dict[str, object]:
    """生成一次情境（模組共用）。"""
    tmp = tmp_path_factory.mktemp("opcua")
    storage = Storage(db_path=str(tmp / "farm.db"))
    sim = WindFarmSimulator(turbine_count=3)
    sim.wind_model.set_override(wind_speed=14.0)
    broker = _FakeBroker(storage, sim)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(engine_mod, "utc_now", lambda: T0)
        mp.setattr(config_ep, "get_broker", lambda: broker)
        result = asyncio.run(config_ep.generate_bulk({
            "duration_hours": 2.0, "time_step": 10.0, "name": "OPC UA 考題", "wind_profile": "rated",
            "fault_schedule": [
                {"scenario_id": "bearing_wear", "turbine_id": "WT001", "offset_seconds": 0, "severity_rate": 0.002},
                {"scenario_id": "generator_overspeed", "turbine_id": "WT002", "offset_seconds": 1800,
                 "severity_rate": 0.01},
            ],
        }))
    scenario_id = int(result["scenario_id"])
    frames = list(rp.ScenarioReplay(storage, scenario_id).iter_frames())
    return {"storage": storage, "scenario_id": scenario_id, "broker": broker, "db": tmp / "farm.db",
            "frames": frames}


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _reader_item_ids(stations: List[str]) -> List[str]:
    """真實讀取腳本的 ``BASE_TAGS``（不 import：它依賴 Windows 的 OpenOPC）。"""
    tree = ast.parse(READER.read_text(encoding="utf-8"))
    base = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "BASE_TAGS" for t in node.targets))
    templates = ast.literal_eval(base)
    assert templates and all(t.startswith("Z72.H{}.") for t in templates)
    return [t.format(station) for station in stations for t in templates]


def _expected_at(frames: List[rp.ReplayFrame], sim_ts: datetime) -> Tuple[Dict[str, dict], Dict[str, dict]]:
    """``sim_ts`` 時各機組最新的讀值（含 10 分鐘平均）與事件碼清單（直接由回放訊息算）。"""
    readings: Dict[str, List[Tuple[datetime, dict]]] = {}
    lists: Dict[str, ActiveEventLists] = {}
    for frame in frames:
        if frame.due > sim_ts:
            break
        message = frame.message
        tid = str(message.get("turbine_id"))
        if message["type"] == "reading":
            readings.setdefault(tid, []).append((frame.due, message))
        elif message["type"] == "event":
            code = message.get("alarm_code")
            lists.setdefault(tid, ActiveEventLists()).apply(
                message["event_type"], code if isinstance(code, int) else 0, message.get("alarm_level"))
    latest: Dict[str, dict] = {}
    for tid, rows in readings.items():
        due, message = rows[-1]
        winds = [m["values"][ou.WSPEED_TAG] for d, m in rows
                 if d > due - timedelta(seconds=ou.AVG_WINDOW_S) and m["values"][ou.WSPEED_TAG] is not None]
        latest[tid] = {"ts": parse_iso(message["ts"]), "values": message["values"],
                       "avg": float(np.mean(winds)) if winds else None}
    return latest, {tid: lst.snapshot() for tid, lst in lists.items()}


async def _read(client: Client, idx: int, item_id: str) -> ua.DataValue:
    return await client.get_node(ua.NodeId(item_id, idx)).read_data_value(raise_on_bad_status=False)


def _same(column_type: str, read: object, expected: object) -> bool:
    if expected is None:
        return read is None
    if column_type == "REAL32":
        return bool(np.float32(read) == np.float32(expected))  # type: ignore[arg-type]
    return read == expected


# ── 1. 規則 ───────────────────────────────────────────────────────────────────


def test_active_event_lists_follow_raise_clear_and_trip() -> None:
    lists = ActiveEventLists()
    assert lists.apply("alarm_raised", 262, "A") and not lists.apply("alarm_raised", 262, "A"), "同一個碼只出現一次"
    assert lists.apply("alarm_raised", 115, "A")
    assert not lists.apply("alarm_raised", 9, "T1"), "等級不符不加入"
    assert lists.apply("trip", 336, "T2") and lists.apply("trip", 100, "T1")
    assert not lists.apply("restart_blocked", 336, "T2") and not lists.apply("info", 5, "I")
    assert lists.snapshot() == {"A": [262, 115], "T1": [100], "T2": [336]}
    assert lists.apply("alarm_cleared", 262, "A") and lists.apply("trip_cleared", 100, None)
    assert lists.snapshot() == {"A": [115], "T1": [], "T2": [336]}
    assert not lists.apply("reset", 8, None) and not lists.apply("operator_reset", 8, None)
    assert lists.snapshot() == {"A": [115], "T1": [], "T2": [336]}, "復位本身不動清單（解除的跳機另有 trip_cleared）"
    snapshot = lists.snapshot()
    snapshot["A"].append(1)
    assert lists.snapshot()["A"] == [115], "snapshot 是複本"


def test_rolling_mean_keeps_ten_minutes_and_skips_missing() -> None:
    mean = ou.RollingMean()
    assert mean.add(0.0, None) is None
    assert mean.add(0.0, 10.0) == 10.0
    assert mean.add(300.0, 20.0) == 15.0
    assert mean.add(400.0, None) == 15.0, "缺值不加入"
    assert mean.add(600.0, 30.0) == 25.0, "左開：剛好 600 s 前的那筆移出"
    assert mean.add(1300.0, 7.3) == 7.3 and repr(mean.add(1300.0, None)) == "7.3", "float32 最短表示"
    assert mean.add(5000.0, None) is None
    later = ou.RollingMean()
    assert later.add(10_000.0, 30.0) == 30.0
    assert later.add(100.0, 5.0) == 5.0, "時間倒退（批次後回到即時）：重新累積，不留未來的樣本"


def test_replay_tick_follows_the_sample_period() -> None:
    assert ou.replay_tick_s(10.0, 60.0) == pytest.approx(10.0 / 60.0)
    assert ou.replay_tick_s(10.0, 1.0) == ou.REPLAY_TICK_MAX_S
    assert ou.replay_tick_s(10.0, 3000.0) == ou.REPLAY_TICK_MIN_S
    assert ou.replay_tick_s(None, 60.0) == ou.REPLAY_TICK_MAX_S


def test_plc_station_and_item_ids() -> None:
    column = next(c for c in sp.pack_columns() if c.name == ou.WSPEED_TAG)
    assert ou.plc_station("WT001") == "H01" and ou.plc_station("WT014") == "H14" and ou.plc_station("T120") == "H120"
    assert ou.value_item_id("WT003", column) == "Z72.H03.WMET.Z72PLC__UI_Loc_WMET_Analogue_WSpeedNac"
    assert ou.list_item_id("WT002", "T2", 20) == "Z72.H02.Z72PLC__ActiveTrip2[20]"
    with pytest.raises(ValueError):
        ou.plc_station("WTX")


# ── 2-3. 回放：節點與讀回 ─────────────────────────────────────────────────────


def test_replay_nodes_match_the_real_reader_and_the_ws_stream(generated: Dict[str, object]) -> None:
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    frames: List[rp.ReplayFrame] = generated["frames"]  # type: ignore[assignment]
    replay = rp.ScenarioReplay(storage, int(generated["scenario_id"]))  # type: ignore[call-overload]
    columns = sp.pack_columns()
    checkpoints = [T0 + timedelta(minutes=m) for m in (5, 20, 45, 70, 95)] + [replay.sim_end]
    observed_lists: List[Dict[str, List[int]]] = []

    async def main() -> None:
        server = ou.Z72OpcUaServer(host="127.0.0.1", port=_free_port())
        await server.start()
        try:
            clock = rp.ReplayClock(replay.sim_start, 60.0, rp.wall_time())
            feeder = ou.ReplayFeeder(server, replay, clock, "practice", 60.0)
            await feeder.setup()
            async with Client(server.endpoint) as client:
                idx = await client.get_namespace_index(ou.NAMESPACE_URI)
                assert idx == server.namespace_index

                # 開播前：節點都在、值還沒有（BadWaitingForInitialData）
                before = await _read(client, idx, ou.value_item_id("WT001", columns[0]))
                assert before.StatusCode.value == ua.StatusCodes.BadWaitingForInitialData

                # 節點的型別、說明（合成 tag 有標示）、瀏覽路徑
                for column in columns:
                    node = client.get_node(ua.NodeId(ou.value_item_id("WT002", column), idx))
                    assert await node.read_data_type_as_variant_type() == ou._VARIANTS[column.tag.data_type]
                    text = (await node.read_description()).Text
                    assert ("synthetic" in text) == (not sp.is_real_plc_tag(column.name)), column.name
                group, tag = columns[0].tag.opc_tag.split(".", 1)
                browsed = await client.nodes.objects.get_child([f"{idx}:Z72", f"{idx}:H01", f"{idx}:{group}",
                                                                f"{idx}:{tag}"])
                assert browsed.nodeid == ua.NodeId(ou.value_item_id("WT001", columns[0]), idx)
                z72 = await client.nodes.objects.get_child([f"{idx}:Z72"])
                assert sorted([(await c.read_browse_name()).Name for c in await z72.get_children()]) == \
                    ["H01", "H02", "H03"]
                avg_node = client.get_node(ua.NodeId(f"Z72.H01.WMET.{ou.WSPEED_AVG10M_TAG}", idx))
                assert "derived" in (await avg_node.read_description()).Text

                for checkpoint in checkpoints:
                    await feeder.advance_to(checkpoint)
                    latest, lists = _expected_at(frames, checkpoint)
                    for tid in replay.turbines:
                        station = ou.plc_station(tid)
                        expected = latest[tid]
                        for column in columns:
                            data = await _read(client, idx, ou.value_item_id(tid, column))
                            wanted = expected["values"][column.name]
                            if wanted is None:
                                assert data.StatusCode.value == ua.StatusCodes.BadNoData
                            else:
                                assert data.StatusCode.is_good(), (tid, column.name)
                                assert _same(column.tag.data_type, data.Value.Value, wanted), (tid, column.name)
                            assert data.SourceTimestamp == expected["ts"]
                        avg = await _read(client, idx, f"Z72.{station}.WMET.{ou.WSPEED_AVG10M_TAG}")
                        assert avg.Value.Value == pytest.approx(expected["avg"], rel=1e-6)
                        assert avg.SourceTimestamp == expected["ts"]
                        snapshot = lists.get(tid, {"A": [], "T1": [], "T2": []})
                        for level in ou.LIST_TAGS:
                            got = [(await _read(client, idx, ou.list_item_id(tid, level, i))).Value.Value
                                   for i in range(ACTIVE_LIST_SLOTS)]
                            assert got == snapshot[level] + [0] * (ACTIVE_LIST_SLOTS - len(snapshot[level])), \
                                (checkpoint, tid, level)
                        observed_lists.append(snapshot)
                    status = {name: (await _read(client, idx, f"WindMindOM.{name}")).Value.Value
                              for name in ("Source", "Status", "SimTime", "PackId", "Mode", "Speed")}
                    assert status["Source"] == "replay" and status["PackId"] == replay.pack_id
                    assert (status["Mode"], status["Speed"]) == ("practice", 60.0)
                    assert status["SimTime"].replace(tzinfo=timezone.utc) == checkpoint
                assert feeder.done and status["Status"] == "finished"

                # 真實讀取腳本的每個 item ID 都讀得到
                for item_id in _reader_item_ids(["01", "02", "03"]):
                    data = await _read(client, idx, item_id)
                    assert data.StatusCode.is_good(), item_id

                # 唯讀
                node = client.get_node(ua.NodeId(ou.value_item_id("WT001", columns[0]), idx))
                with pytest.raises(ua.UaStatusCodeError):
                    await node.write_value(ua.DataValue(ua.Variant(1.0, ua.VariantType.Float)))
                with pytest.raises(ua.UaStatusCodeError):
                    await client.get_node(ua.NodeId("Z72.H01.Z72PLC__ActiveAlarm[0]", idx)).write_value(
                        ua.DataValue(ua.Variant(1, ua.VariantType.Int16)))
        finally:
            await server.stop()

    asyncio.run(main())
    assert any(lst["A"] or lst["T1"] or lst["T2"] for lst in observed_lists), "情境裡要有成立中的警報 / 跳機"


def test_replay_feeder_stops_when_the_run_is_revoked(generated: Dict[str, object],
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ou, "RUN_RECHECK_S", 0.0)
    replay = rp.ScenarioReplay(generated["storage"], int(generated["scenario_id"]))  # type: ignore[arg-type, call-overload]
    calls: List[int] = []

    async def check_run() -> Optional[str]:
        calls.append(1)
        return "revoked" if len(calls) >= 2 else None

    async def main() -> Tuple[Optional[str], bool, str]:
        server = ou.Z72OpcUaServer(host="127.0.0.1", port=_free_port())
        await server.start()
        try:
            clock = rp.ReplayClock(replay.sim_start, 60.0, rp.wall_time())
            feeder = ou.ReplayFeeder(server, replay, clock, "evaluation", 60.0, check_run=check_run)
            await feeder.setup()
            await asyncio.wait_for(feeder.run(tick_s=0.01), 10)
            async with Client(server.endpoint) as client:
                status = (await _read(client, server.namespace_index, "WindMindOM.Status")).Value.Value
            return feeder.stop_reason, feeder.done, status
        finally:
            await server.stop()

    assert asyncio.run(main()) == ("revoked", False, "revoked")


# ── 4. 正式評測：與 WS 共用時鐘 ───────────────────────────────────────────────


def test_evaluation_starts_at_server_start_and_ws_joins_without_data(generated: Dict[str, object],
                                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    import opcua_server as opcua_cli

    storage: Storage = generated["storage"]  # type: ignore[assignment]
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.setattr(replay_ep, "get_broker", lambda: generated["broker"])
    run, token = rp.create_run(storage, int(generated["scenario_id"]), mode="evaluation",  # type: ignore[call-overload]
                               speed=EVAL_SPEED, allow_overlap=True)
    run_id = int(run["id"])  # type: ignore[arg-type]
    run_row, replay = opcua_cli.load_run(storage, run_id)
    assert storage.get_replay_run(run_id)["started_at"] is None, "載入不開播（節點建好、開始監聽才開播）"  # type: ignore[index]
    clock = opcua_cli.start_clock(storage, run_row, replay)
    started_at = storage.get_replay_run(run_id)["started_at"]  # type: ignore[index]
    assert started_at is not None and clock.wall_start == pytest.approx(parse_iso(started_at).timestamp())
    again = opcua_cli.start_clock(storage, *opcua_cli.load_run(storage, run_id))
    assert again.wall_start == clock.wall_start, "server 重啟：接著播、不重來"

    app = FastAPI()
    app.include_router(replay_ep.router)
    with TestClient(app).websocket_connect("/ws/replay?stream=false",
                                           headers={"Authorization": f"Bearer {token}"}) as ws:
        before = clock.sim_now()
        started = ws.receive_json()
        after = clock.sim_now()
        assert started["stream"]["data"] is False and started["stream"]["mode"] == "evaluation"
        assert before <= parse_iso(started["sim_ts"]) <= after, "WS 加入 OPC UA 開播的同一個時鐘"
        ws.send_json({"type": "prediction", "id": "p1", "turbine_id": "WT001", "category": "real_fault",
                      "component": "main_bearing"})
        messages = []
        while True:
            message = ws.receive_json()
            messages.append(message)
            if message["type"] == "control" and message["status"] == "finished":
                break
    assert {m["type"] for m in messages} <= {"ack", "control"}, "stream=false 不送讀值 / 事件 / 統計"
    ack = next(m for m in messages if m["type"] == "ack")
    assert ack["accepted"] and replay.sim_start <= parse_iso(ack["ts"]) <= replay.sim_end
    assert len(storage.replay_predictions(run_id)) == 1

    # 播完（過了寬限期）不能再開；撤銷的不能開
    conn = storage._get_conn()
    conn.execute("UPDATE replay_runs SET started_at = ? WHERE id = ?",
                 (iso_utc(datetime.now(timezone.utc) - timedelta(days=1)), run_id))
    conn.commit()
    with pytest.raises(ValueError, match="單次回放已結束"):
        opcua_cli.load_run(storage, run_id)
    storage.revoke_replay_run(run_id, iso_utc())
    with pytest.raises(ValueError, match="回放已撤銷"):
        opcua_cli.load_run(storage, run_id)
    with pytest.raises(ValueError, match="回放不存在"):
        opcua_cli.load_run(storage, 999_999)


def test_cli_plays_a_practice_run_to_the_end(generated: Dict[str, object], capsys: pytest.CaptureFixture[str],
                                             tmp_path: Path) -> None:
    import opcua_server as opcua_cli

    storage: Storage = generated["storage"]  # type: ignore[assignment]
    run, _ = rp.create_run(storage, int(generated["scenario_id"]), mode="practice", speed=FAST,  # type: ignore[call-overload]
                           allow_overlap=True)
    args = [str(generated["db"]), str(run["id"]), "--host", "127.0.0.1", "--port", str(_free_port())]
    assert opcua_cli.main(args + ["--exit-when-finished"]) == 0
    out = capsys.readouterr().out
    assert "opc.tcp://127.0.0.1:" in out and "資料播完" in out
    row = storage.get_replay_run(int(run["id"]))  # type: ignore[arg-type]
    assert row is not None and row["started_at"] is not None, "練習模式記下這次播出的起點（WS stream=false 對時用）"
    assert rp.run_view(storage, row)["status"] == "ready", "練習回放的狀態不受影響"
    storage.revoke_replay_run(int(run["id"]), iso_utc())  # type: ignore[arg-type]
    assert opcua_cli.main(args) == 1 and "回放已撤銷" in capsys.readouterr().err
    assert opcua_cli.main([str(tmp_path / "missing.db"), "1"]) == 2


# ── 5. 即時模擬 ───────────────────────────────────────────────────────────────


def _live_broker(turbines: int = 2) -> SimpleNamespace:
    sim = WindFarmSimulator(turbine_count=turbines)
    sim.wind_model.set_override(wind_speed=12.0)
    for step in range(3):
        sim._run_one_step(T0 + timedelta(seconds=step), 1.0)
    return SimpleNamespace(simulator=sim, source_kind="simulation")


def test_live_feeder_writes_the_latest_readings_and_plc_lists() -> None:
    broker = _live_broker()
    sim: WindFarmSimulator = broker.simulator
    columns = sp.pack_columns()
    ids = [c.tag.id for c in columns]
    alarm = next(a for a in all_alarms() if a.level == "A")
    trip = next(a for a in all_alarms() if a.level == "T2")

    async def main() -> None:
        server = ou.Z72OpcUaServer(host="127.0.0.1", port=_free_port())
        await server.start()
        try:
            feeder = ou.LiveFeeder(server, broker)
            await feeder.update()
            async with Client(server.endpoint) as client:
                idx = server.namespace_index
                for tid in ("WT001", "WT002"):
                    reading = sim.latest_data[tid]
                    expected = sp.json_values(sp.scada_dict_values(reading["scada"], ids), columns)
                    for column in columns:
                        data = await _read(client, idx, ou.value_item_id(tid, column))
                        if expected[column.name] is None:
                            assert data.StatusCode.value == ua.StatusCodes.BadNoData
                        else:
                            assert _same(column.tag.data_type, data.Value.Value, expected[column.name]), column.name
                        assert data.SourceTimestamp == parse_iso(reading["timestamp"])
                    avg = await _read(client, idx, f"Z72.{ou.plc_station(tid)}.WMET.{ou.WSPEED_AVG10M_TAG}")
                    assert avg.Value.Value == pytest.approx(float(expected[ou.WSPEED_TAG]), rel=1e-6)
                assert (await _read(client, idx, "WindMindOM.Source")).Value.Value == "live"
                assert (await _read(client, idx, "WindMindOM.Status")).Value.Value == "running"

                # PLC 的清單變了就跟著變（不必有新讀值）
                plc = sim.turbines["WT002"].plc
                plc.active_lists.apply("alarm_raised", alarm.code, "A")
                plc.active_lists.apply("trip", trip.code, "T2")
                await feeder.update()
                assert (await _read(client, idx, "Z72.H02.Z72PLC__ActiveAlarm[0]")).Value.Value == alarm.code
                assert (await _read(client, idx, "Z72.H02.Z72PLC__ActiveTrip2[0]")).Value.Value == trip.code
                assert (await _read(client, idx, "Z72.H01.Z72PLC__ActiveAlarm[0]")).Value.Value == 0
                plc.active_lists.apply("trip_cleared", trip.code, None)
                await feeder.update()
                assert (await _read(client, idx, "Z72.H02.Z72PLC__ActiveTrip2[0]")).Value.Value == 0
                assert (await _read(client, idx, "Z72.H02.Z72PLC__ActiveAlarm[0]")).Value.Value == alarm.code

                # 不是即時模擬（例：產生情境 / 真實 OPC）：只標示 idle，節點保留最後的值
                broker.source_kind = "scenario"
                await feeder.update()
                assert (await _read(client, idx, "WindMindOM.Status")).Value.Value == "idle"
        finally:
            await server.stop()

    asyncio.run(main())


def test_live_plc_lists_match_the_lists_rebuilt_from_events(generated: Dict[str, object]) -> None:
    """即時模擬的清單（``PlcProtection`` 送事件時更新）與回放由事件流重建的一致（同一次批次生成）。"""
    sim: WindFarmSimulator = generated["broker"].simulator  # type: ignore[attr-defined]
    frames: List[rp.ReplayFrame] = generated["frames"]  # type: ignore[assignment]
    _, lists = _expected_at(frames, frames[-1].due)
    for tid, model in sim.turbines.items():
        assert model.plc.active_lists.snapshot() == lists.get(tid, {"A": [], "T1": [], "T2": []}), tid
    assert lists["WT002"]["T1"], "情境結束時 WT002 的超速跳機仍成立（鎖存）"


def test_start_live_from_env(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    broker = _live_broker(turbines=1)
    assert oc.live_bind({}) == ("127.0.0.1", 4840), "即時模擬的 OPC UA 預設只聽本機"
    assert oc.opcua_enabled({"WMOM_OPCUA_ENABLE": "on"}) and not oc.opcua_enabled({})
    monkeypatch.delenv("WMOM_OPCUA_ENABLE", raising=False)
    assert asyncio.run(ou.start_live_from_env(broker)) is None, "預設不開"
    port = _free_port()
    monkeypatch.setenv("WMOM_OPCUA_ENABLE", "true")
    monkeypatch.setenv("WMOM_OPCUA_HOST", "127.0.0.1")
    monkeypatch.setenv("WMOM_OPCUA_PORT", str(port))

    async def main() -> Tuple[str, Optional[ou.LiveOpcUa]]:
        live = await ou.start_live_from_env(broker)
        assert live is not None and live.server.endpoint == f"opc.tcp://127.0.0.1:{port}/windmindom/"
        try:
            async with Client(live.server.endpoint) as client:
                idx = await client.get_namespace_index(ou.NAMESPACE_URI)
                source = ""
                for _ in range(50):
                    source = (await _read(client, idx, "WindMindOM.Source")).Value.Value
                    if source == "live":
                        break
                    await asyncio.sleep(0.05)
                # 同一個埠再起一個：起不來只記警告、回傳 None（不擋主程式）
                with caplog.at_level(logging.WARNING, logger=ou.logger.name):
                    second = await ou.start_live_from_env(broker)
            return source, second
        finally:
            await live.stop()

    source, second = asyncio.run(main())
    assert source == "live" and second is None
    assert any("OPC UA server not started" in r.getMessage() for r in caplog.records)


# ── 6. starter kit ────────────────────────────────────────────────────────────


def test_kit_opcua_client_against_real_servers(generated: Dict[str, object], monkeypatch: pytest.MonkeyPatch) -> None:
    import threading
    import time

    import uvicorn

    import opcua_client
    import opcua_server as opcua_cli

    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setattr(replay_ep, "get_broker", lambda: generated["broker"])
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    # 600×：2 h 情境 12 s 播完；客戶端每 0.05 s 讀一次＝模擬時間 30 秒，6 分鐘長的警報（262）在 CI 變慢時也看得到
    run, token = rp.create_run(storage, int(generated["scenario_id"]), mode="evaluation", speed=600.0,  # type: ignore[call-overload]
                               allow_overlap=True)
    app = FastAPI()
    app.include_router(replay_ep.router)
    ws_port = _free_port()
    web = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=ws_port, log_level="warning"))
    thread = threading.Thread(target=web.run, daemon=True)
    thread.start()

    async def main() -> Tuple[opcua_client.Summary, opcua_client.Summary]:
        run_row, replay = opcua_cli.load_run(storage, int(run["id"]))  # type: ignore[arg-type]
        server = ou.Z72OpcUaServer(host="127.0.0.1", port=_free_port())
        await server.start(turbines=replay.turbines)
        clock = opcua_cli.start_clock(storage, run_row, replay)
        feeder = ou.ReplayFeeder(server, replay, clock, "evaluation", 600.0)
        await feeder.setup()
        task = asyncio.create_task(feeder.run(tick_s=0.02))
        try:
            summary = await asyncio.wait_for(opcua_client.run(
                server.endpoint, f"ws://127.0.0.1:{ws_port}/ws/replay", token, poll_s=0.05, verbose=False), 60)
            await asyncio.wait_for(task, 10)
            # 只看模式：回放已播完，讀一次就結束（看到的是最後還成立的碼）
            watched = await asyncio.wait_for(opcua_client.run(server.endpoint, verbose=False), 30)
            return summary, watched
        finally:
            task.cancel()
            await server.stop()

    try:
        deadline = time.time() + 10
        while not web.started and time.time() < deadline:
            time.sleep(0.05)
        assert web.started
        summary, watched = asyncio.run(main())
    finally:
        web.should_exit = True
        thread.join(timeout=10)
    assert summary.close_code == 1000 and summary.rejected == [] and summary.errors == []
    assert summary.counts.get("opcua_event", 0) >= 3 and summary.accepted == summary.counts["ack"] > 0
    assert set(summary.counts) <= {"control", "ack", "opcua_read", "opcua_event"}, "stream=false 不收資料"
    stored = storage.replay_predictions(int(run["id"]))  # type: ignore[arg-type]
    assert {p["prediction"]["turbine_id"] for p in stored} >= {"WT001"}
    assert {p["prediction"]["component"] for p in stored} >= {"main_bearing"}
    assert watched.counts == {"opcua_read": 1, "opcua_event": 1} and watched.close_code is None


def test_kit_list_events_turn_list_changes_into_events() -> None:
    import opcua_client

    catalog = {262: {"text": "Main bearing temperature high"}}
    events = opcua_client.list_events("WT001", {"A": [115], "T1": [], "T2": [336]},
                                      {"A": [262], "T1": [240], "T2": [336]}, catalog, "2026-01-15T03:15:00.000000Z")
    assert [(e["event_type"], e["alarm_code"], e["alarm_level"]) for e in events] == [
        ("alarm_raised", 262, "A"), ("alarm_cleared", 115, "A"), ("trip", 240, "T1")]
    assert events[0]["alarm_text"] == "Main bearing temperature high" and events[2]["alarm_text"] == ""
    assert opcua_client._turbine_for("H02", ["WT001", "WT002"]) == "WT002"
    assert opcua_client._turbine_for("H07", []) == "H07"


# ── code review 補測 ──────────────────────────────────────────────────────────


def test_admin_login_cannot_write_or_change_the_address_space() -> None:
    """asyncua 預設任何帳號名 admin 的 session 都是管理員：這裡只收匿名、admin 也關掉。"""
    outcome: List[str] = []

    async def main() -> None:
        server = ou.Z72OpcUaServer(host="127.0.0.1", port=_free_port())
        await server.start(turbines=["WT001"])
        idx = server.namespace_index
        try:
            client = Client(server.endpoint)
            client.set_user("admin")
            client.set_password("anything")
            try:
                await client.connect()
            except Exception:  # noqa: BLE001  只收匿名：帳號登入在建立 session 時就被拒
                outcome.append("login refused")
            else:
                try:
                    with pytest.raises(ua.UaStatusCodeError):
                        await client.get_node(ua.NodeId("WindMindOM.Source", idx)).write_value(
                            ua.DataValue(ua.Variant("hacked", ua.VariantType.String)))
                    with pytest.raises(ua.UaStatusCodeError):
                        await client.nodes.objects.add_folder(ua.NodeId("Evil", idx), ua.QualifiedName("Evil", idx))
                    outcome.append("writes refused")
                finally:
                    await client.disconnect()
            async with Client(server.endpoint) as anon:
                assert (await _read(anon, idx, "WindMindOM.Source")).Value.Value == "idle"
                with pytest.raises(ua.UaStatusCodeError):
                    await anon.nodes.objects.add_folder(ua.NodeId("Evil", idx), ua.QualifiedName("Evil", idx))
                with pytest.raises(ua.UaStatusCodeError):
                    await anon.get_node(ua.NodeId("Z72.H01.Z72PLC__ActiveTrip1[0]", idx)).write_value(
                        ua.DataValue(ua.Variant(351, ua.VariantType.Int16)))
        finally:
            await server.stop()

    asyncio.run(main())
    assert outcome in (["login refused"], ["writes refused"])


def test_live_feeder_does_not_publish_bulk_generation() -> None:
    """產生情境（批次）跑在同一個 simulator：期間只標 idle，結束後留在 latest_data 的批次讀值也不發布。"""
    broker = _live_broker()
    sim: WindFarmSimulator = broker.simulator
    power = next(c for c in sp.pack_columns() if c.name == "Z72PLC__UI_Loc_WTUR_Analogue_TotPwrAt")

    async def main() -> None:
        server = ou.Z72OpcUaServer(host="127.0.0.1", port=_free_port())
        await server.start()
        idx = server.namespace_index
        try:
            feeder = ou.LiveFeeder(server, broker)  # type: ignore[arg-type]  # SimpleNamespace 當 broker
            await feeder.update()
            async with Client(server.endpoint) as client:
                first = await _read(client, idx, ou.value_item_id("WT002", power))
                sim_time = (await _read(client, idx, "WindMindOM.SimTime")).Value.Value
                sim._bulk_running = True
                await feeder.update()
                assert (await _read(client, idx, "WindMindOM.Status")).Value.Value == "idle"
                sim._bulk_running = False
                sim.generate_bulk(0.5, time_step=10.0, fault_schedule=[
                    PlanStep(offset_seconds=0, scenario_id="generator_overspeed", turbine_id="WT002",
                                 severity_rate=0.05, initial_severity=0.9)])
                await feeder.update()
                after_bulk = await _read(client, idx, ou.value_item_id("WT002", power))
                assert after_bulk.SourceTimestamp == first.SourceTimestamp, "批次最後一步的讀值不發布"
                assert (await _read(client, idx, "WindMindOM.SimTime")).Value.Value == sim_time
                assert (await _read(client, idx, "WindMindOM.Status")).Value.Value == "idle"
                # 即時模擬寫入新的讀值後才恢復發布；10 分鐘平均重新累積（不混入批次的未來時間）
                live_ts = utc_now()
                sim._run_one_step(live_ts, 1.0)
                await feeder.update()
                resumed = await _read(client, idx, ou.value_item_id("WT002", power))
                assert resumed.SourceTimestamp == parse_iso(sim.latest_data["WT002"]["timestamp"])
                wind = sp.json_values(sp.scada_dict_values(sim.latest_data["WT002"]["scada"],
                                                           [c.tag.id for c in sp.pack_columns()]),
                                      sp.pack_columns())[ou.WSPEED_TAG]
                avg = await _read(client, idx, f"Z72.H02.WMET.{ou.WSPEED_AVG10M_TAG}")
                assert avg.Value.Value == pytest.approx(float(wind), rel=1e-6)  # type: ignore[arg-type]
                assert (await _read(client, idx, "WindMindOM.Status")).Value.Value == "running"
        finally:
            await server.stop()

    asyncio.run(main())


def test_live_feeder_clears_turbines_that_disappear() -> None:
    broker = _live_broker(turbines=2)

    async def main() -> None:
        server = ou.Z72OpcUaServer(host="127.0.0.1", port=_free_port())
        await server.start()
        idx = server.namespace_index
        try:
            feeder = ou.LiveFeeder(server, broker)  # type: ignore[arg-type]
            await feeder.update()
            broker.simulator = _live_broker(turbines=1).simulator  # 換了風場：只剩 1 台
            await feeder.update()
            async with Client(server.endpoint) as client:
                gone = await _read(client, idx, f"Z72.H02.WMET.{ou.WSPEED_TAG}")
                kept = await _read(client, idx, f"Z72.H01.WMET.{ou.WSPEED_TAG}")
                trip = await _read(client, idx, "Z72.H02.Z72PLC__ActiveTrip1[0]")
            assert gone.StatusCode.value == ua.StatusCodes.BadNoData and kept.StatusCode.is_good()
            assert trip.StatusCode.value == ua.StatusCodes.BadNoData
        finally:
            await server.stop()

    asyncio.run(main())


def test_station_collisions_are_rejected() -> None:
    async def main() -> None:
        server = ou.Z72OpcUaServer(host="127.0.0.1", port=_free_port())
        await server.start(turbines=["WT001"])
        try:
            with pytest.raises(ValueError, match="H01"):
                await server.ensure_turbine("WT01")
            assert server.turbine_ids == ["WT001"]
        finally:
            await server.stop()

    asyncio.run(main())


def test_plc_lists_match_active_codes_at_every_step(monkeypatch: pytest.MonkeyPatch) -> None:
    """事件碼陣列＝PLC 目前成立的警報與鎖存中的跳機（每一步都對），含操作員復位與維護清除故障。"""
    monkeypatch.setattr(engine_mod, "utc_now", lambda: T0)
    sim = WindFarmSimulator(turbine_count=3)
    sim.wind_model.set_override(wind_speed=14.0)
    mismatches: List[tuple] = []
    seen: Dict[str, int] = {"A": 0, "T1": 0, "T2": 0}
    steps = [0]

    def check(readings: List[dict]) -> None:
        steps[0] += 1
        if steps[0] == 150:
            sim.turbines["WT001"].cmd_reset()  # 操作員復位：鎖存的跳機解除，條件仍成立就再跳
        for tid, model in sim.turbines.items():
            codes = model.plc.active_codes()
            expected = {level: sorted(c for c, lv in codes.items() if lv == level) for level in seen}
            got = {level: sorted(v) for level, v in model.plc.active_lists.snapshot().items()}
            if got != expected:
                mismatches.append((steps[0], tid, got, expected))
            for level in seen:
                seen[level] += bool(got[level])

    sim.generate_bulk(1.0, time_step=10.0, callback=check, fault_schedule=[
        PlanStep(offset_seconds=0, scenario_id="bearing_wear", turbine_id="WT001", severity_rate=0.004,
                     initial_severity=0.5),
        PlanStep(offset_seconds=600, scenario_id="generator_overspeed", turbine_id="WT002", severity_rate=0.02),
    ])
    sim.fault_engine.clear()  # 維護清除故障：PLC maintenance_release（不解除鎖存）
    sim.generate_bulk(0.5, time_step=10.0, callback=check)
    assert mismatches == []
    assert seen["A"] and seen["T1"], seen


def test_practice_stream_false_uses_the_opc_clock(generated: Dict[str, object],
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    """練習回放以 OPC UA 播出時，WS ``stream=false`` 的時鐘＝OPC UA server 開播時記下的起點。"""
    import opcua_server as opcua_cli

    storage: Storage = generated["storage"]  # type: ignore[assignment]
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.setattr(replay_ep, "get_broker", lambda: generated["broker"])
    run, token = rp.create_run(storage, int(generated["scenario_id"]), mode="practice",  # type: ignore[call-overload]
                               speed=600.0, allow_overlap=True)
    run_id = int(run["id"])  # type: ignore[arg-type]
    headers = {"Authorization": f"Bearer {token}"}
    app = FastAPI()
    app.include_router(replay_ep.router)
    client = TestClient(app)
    with client.websocket_connect("/ws/replay?stream=false", headers=headers) as ws:
        error = ws.receive_json()
    assert error["code"] == 4412, "還沒以 OPC UA 播出：不能用 stream=false"

    run_row, replay = opcua_cli.load_run(storage, run_id)
    clock = opcua_cli.start_clock(storage, run_row, replay)
    import time
    time.sleep(0.5)  # OPC UA 已經播了 5 分鐘模擬時間
    with client.websocket_connect("/ws/replay?stream=false", headers=headers) as ws:
        before = clock.sim_now()
        started = ws.receive_json()
        after = clock.sim_now()
        assert before <= parse_iso(started["sim_ts"]) <= after, "與 OPC UA 同一個時鐘，不是從頭"
        assert started["stream"]["data"] is False and started["stream"]["mode"] == "practice"
        ws.send_json({"type": "prediction", "id": 1, "turbine_id": "WT001", "category": "real_fault",
                      "component": "main_bearing"})
        ack = ws.receive_json()
    assert ack["accepted"] and parse_iso(ack["ts"]) >= before
    # 一般的練習連線（送資料）照舊從頭播
    with client.websocket_connect("/ws/replay", headers=headers) as ws:
        started = ws.receive_json()
    assert parse_iso(started["sim_ts"]) < replay.sim_start + timedelta(minutes=2)
    assert rp.run_view(storage, storage.get_replay_run(run_id))["status"] == "ready"  # type: ignore[arg-type]
    # 這次 OPC UA 播出已結束
    storage.anchor_practice_run(run_id, iso_utc(datetime.now(timezone.utc) - timedelta(days=1)))
    with client.websocket_connect("/ws/replay?stream=false", headers=headers) as ws:
        error = ws.receive_json()
    assert error["code"] == 4410
    assert not storage.anchor_practice_run(999_999, iso_utc()), "只改練習回放"


def test_cli_stops_on_revoke_and_reports_a_busy_port(generated: Dict[str, object], monkeypatch: pytest.MonkeyPatch,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    import opcua_server as opcua_cli

    monkeypatch.setattr(ou, "RUN_RECHECK_S", 0.05)
    monkeypatch.setattr(opcua_cli, "STOP_LINGER_S", 0.0)
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    run, _ = rp.create_run(storage, int(generated["scenario_id"]), mode="practice", speed=60.0,  # type: ignore[call-overload]
                           allow_overlap=True)
    run_id = int(run["id"])  # type: ignore[arg-type]

    async def main() -> int:
        task = asyncio.create_task(opcua_cli.serve(storage, run_id, "127.0.0.1", _free_port(), True))
        await asyncio.sleep(1.0)
        await asyncio.to_thread(storage.revoke_replay_run, run_id, iso_utc())
        return await asyncio.wait_for(task, 20)

    assert asyncio.run(main()) == 1
    assert "回放已停止：revoked" in capsys.readouterr().err
    other, _ = rp.create_run(storage, int(generated["scenario_id"]), mode="practice", speed=60.0,  # type: ignore[call-overload]
                             allow_overlap=True)
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        code = opcua_cli.main([str(generated["db"]), str(other["id"]), "--host", "127.0.0.1", "--port", str(port)])
    assert code == 1 and "OPC UA server 起不來" in capsys.readouterr().err
