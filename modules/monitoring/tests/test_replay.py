"""情境 WebSocket 回放（WMOM-20261021-06，EPIC-DS Phase 3b ② 串流）。

一個固定起點的 2 h 情境（WT001 主軸承磨耗、WT002 超速），檢查：

1. 回放器：讀值 / 10 分鐘統計 / 事件與盲測版資料包逐筆相同、依時間排序、不含任何答案
2. 時鐘與預測檢查（受測端的 ts / pack_id 一律由伺服器決定）
3. WS：練習模式完整播完、預測以收到時的模擬時間蓋章、評分端下載後可直接給 score.py
4. 單次回放（evaluation）：時鐘從第一次連線起算、中途加入不能倒帶、結束後不能再連
5. token：缺 / 無效 / 撤銷 / 到期、連線數上限、撤銷後不收預測、壞訊息
6. REST：權限、參數檢查、列表不含 token、刪除情境連帶刪回放
7. starter kit 的受測端範例對真的 uvicorn 伺服器跑完一次；出題端 CLI
"""

from __future__ import annotations

import asyncio
import json
import secrets
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
KIT_DIR = PROJECT_ROOT / "examples" / "rag_starter_kit"
for _p in (PROJECT_ROOT, MONITORING_ROOT, KIT_DIR, PROJECT_ROOT / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import numpy as np  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import score as kit_score  # noqa: E402
import simulator.engine as engine_mod  # noqa: E402
from modules.auth.tokens import create_access_token  # noqa: E402
from server import replay as rp  # noqa: E402
from server import scenario_pack as sp  # noqa: E402
from server.data_broker import DataBroker  # noqa: E402
from server.routers import config as config_ep  # noqa: E402
from server.routers import replay as replay_ep  # noqa: E402
from server.storage import Storage  # noqa: E402
from simulator.engine import WindFarmSimulator  # noqa: E402
from simulator.physics.fault_engine import FAULT_SCENARIOS  # noqa: E402
from simulator.time_utils import iso_utc, parse_iso  # noqa: E402

T0 = datetime(2026, 1, 15, 3, 0, tzinfo=timezone.utc)
SCENARIO_NAME = "考題：主軸承 + 超速"
FAST = 10_000.0  # 2 h 情境約 0.7 s 播完


class _FakeBroker:
    """情境生成端點與回放端點用到的 broker 表面（批次事件寫入沿用真 DataBroker 的實作）。"""

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
    """生成一次情境並匯出盲測版 / 評分端版資料包（模組共用）。"""
    tmp = tmp_path_factory.mktemp("replay")
    storage = Storage(db_path=str(tmp / "farm.db"))
    sim = WindFarmSimulator(turbine_count=3)
    sim.wind_model.set_override(wind_speed=14.0)
    broker = _FakeBroker(storage, sim)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(engine_mod, "utc_now", lambda: T0)
        mp.setattr(config_ep, "get_broker", lambda: broker)
        result = asyncio.run(config_ep.generate_bulk({
            "duration_hours": 2.0, "time_step": 10.0, "name": SCENARIO_NAME, "wind_profile": "rated",
            "fault_schedule": [
                {"scenario_id": "bearing_wear", "turbine_id": "WT001", "offset_seconds": 0, "severity_rate": 0.002},
                {"scenario_id": "generator_overspeed", "turbine_id": "WT002", "offset_seconds": 1800,
                 "severity_rate": 0.01},
            ],
        }))
    scenario_id = int(result["scenario_id"])
    sp.export_scenario_pack(storage, scenario_id, tmp / "blind")
    sp.export_scenario_pack(storage, scenario_id, tmp / "full", include_ground_truth=True)
    frames = list(rp.ScenarioReplay(storage, scenario_id).iter_frames())
    return {"storage": storage, "scenario_id": scenario_id, "broker": broker, "tmp": tmp, "frames": frames}


def _messages(frames: List[rp.ReplayFrame], kind: str) -> List[dict]:
    return [f.message for f in frames if f.message["type"] == kind]


# ── 1. 回放器與資料包一致 ────────────────────────────────────────────────────


def test_readings_match_the_pack_raw_parquet(generated: Dict[str, object]) -> None:
    raw = pq.read_table(generated["tmp"] / "blind" / sp.FILE_RAW).to_pylist()  # type: ignore[operator]
    readings = _messages(generated["frames"], "reading")  # type: ignore[arg-type]
    assert len(readings) == len(raw) == 2160
    for row, message in zip(raw, readings, strict=True):
        assert message["ts"] == row["timestamp"].strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        assert message["turbine_id"] == row["turbine_id"]
        assert list(message["values"]) == [k for k in row if k not in ("timestamp", "turbine_id")]
        for tag, value in message["values"].items():
            expected = row[tag]
            if isinstance(expected, float):
                # REAL32：JSON 是 float32 的最短表示，讀回 float32 與 Parquet 逐位元相同
                assert value is not None and np.float32(value) == np.float32(expected), tag
            else:
                assert value == expected and type(value) is type(expected), tag


def test_stats_match_the_pack_stats_parquet(generated: Dict[str, object]) -> None:
    rows = pq.read_table(generated["tmp"] / "blind" / sp.FILE_STATS).to_pylist()  # type: ignore[operator]
    stats = sorted(_messages(generated["frames"], "stats"),  # type: ignore[arg-type]
                   key=lambda m: (m["window_start"], m["turbine_id"]))
    assert len(stats) == len(rows) > 0
    for row, message in zip(rows, stats, strict=True):
        for key in ("window_start", "window_end"):
            assert message[key] == row[key].strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        assert (message["turbine_id"], message["n_samples"], message["is_partial"]) == \
            (row["turbine_id"], row["n_samples"], row["is_partial"])
        assert set(message["values"]) == set(row) - {"window_start", "window_end", "turbine_id", "n_samples",
                                                       "is_partial"}
        for key, value in message["values"].items():
            expected = row[key]
            if expected is None or value is None:
                assert expected is None and value is None, key
            elif isinstance(expected, float):
                assert np.float32(value) == np.float32(expected), key
            else:
                assert value == expected, key


def test_events_match_the_pack_events_jsonl(generated: Dict[str, object]) -> None:
    lines = (generated["tmp"] / "blind" / sp.FILE_EVENTS).read_text(encoding="utf-8").splitlines()  # type: ignore[operator]
    events = [{k: v for k, v in m.items() if k != "type"}
              for m in _messages(generated["frames"], "event")]  # type: ignore[arg-type]
    assert events == [json.loads(line) for line in lines]
    assert any(e["event_type"] == "trip" for e in events)


def test_frames_are_time_ordered_and_stats_are_causal(generated: Dict[str, object]) -> None:
    frames: List[rp.ReplayFrame] = generated["frames"]  # type: ignore[assignment]
    keys = [(f.due, f.order) for f in frames]
    assert keys == sorted(keys)
    last_reading: Dict[str, datetime] = {}
    for frame in frames:
        message = frame.message
        if message["type"] == "reading":
            last_reading[message["turbine_id"]] = frame.due
        elif message["type"] == "stats":
            end = parse_iso(message["window_end"])
            # 窗結束才送（最後的殘缺窗在資料結束時送）；送出前該機組窗內的讀值都已送出
            assert frame.due == min(end, frames[-1].due) or frame.due == end
            assert all(t < end for t in last_reading.values() if t <= frame.due)


def test_replay_messages_carry_no_answers(generated: Dict[str, object]) -> None:
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    replay = rp.ScenarioReplay(storage, generated["scenario_id"])  # type: ignore[arg-type]
    frames: List[rp.ReplayFrame] = generated["frames"]  # type: ignore[assignment]
    blob = json.dumps([replay.describe(), replay.tag_dictionary()] + [f.message for f in frames], ensure_ascii=False)
    for leak in [*FAULT_SCENARIOS, SCENARIO_NAME, "fault_schedule", "ground_truth", "maintenance_lock",
                 "severity", "root_cause"]:
        assert leak not in blob, leak
    assert not set(sp.MODEL_INTERNAL_TAGS) & {t["id"] for t in replay.tag_dictionary()}


def test_replay_requires_an_exportable_scenario(generated: Dict[str, object]) -> None:
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    with pytest.raises(sp.ScenarioPackError) as exc:
        rp.ScenarioReplay(storage, 99_999)
    assert exc.value.status_code == 404


# ── 2. 時鐘與預測檢查 ────────────────────────────────────────────────────────


def test_clock_maps_wall_time_to_sim_time() -> None:
    clock = rp.ReplayClock(sim_start=T0, speed=60.0, wall_start=1000.0)
    assert clock.sim_now(1000.0) == T0
    assert clock.sim_now(900.0) == T0, "開始前停在起點"
    assert clock.sim_now(1010.0) == T0 + timedelta(minutes=10)
    assert clock.wall_at(T0 + timedelta(hours=1)) == pytest.approx(1060.0)


def test_validate_prediction_accepts_the_contract_fields_only() -> None:
    fields = rp.validate_prediction({
        "type": "prediction", "id": 7, "turbine_id": "WT001", "category": "real_fault",
        "component": "main_bearing", "manual_refs": [262, 240], "root_cause": "x", "actions": ["a"],
        "confidence": 0.5, "ts": "1999-01-01T00:00:00Z", "pack_id": "other", "extra": 1,
    }, ["WT001"])
    assert fields == {"turbine_id": "WT001", "category": "real_fault", "component": "main_bearing",
                      "manual_refs": [262, 240], "root_cause": "x", "actions": ["a"], "confidence": 0.5}
    record = rp.prediction_record("z72-scenario-00001", T0, fields)
    assert list(record)[:3] == ["pack_id", "turbine_id", "ts"] and record["ts"] == "2026-01-15T03:00:00.000000Z"
    nuisance = rp.validate_prediction({"turbine_id": "WT001", "category": "nuisance"}, ["WT001"])
    assert nuisance["component"] is None and nuisance["manual_refs"] == []


@pytest.mark.parametrize("item, reason", [
    ({"turbine_id": "WT009", "category": "nuisance"}, "turbine_id"),
    ({"turbine_id": "WT001", "category": "broken"}, "category"),
    ({"turbine_id": "WT001", "category": "real_fault"}, "component"),
    ({"turbine_id": "WT001", "category": "real_fault", "component": "main_bearng"}, "vocabulary"),
    ({"turbine_id": "WT001", "category": "nuisance", "component": 3}, "component"),
    ({"turbine_id": "WT001", "category": "nuisance", "manual_refs": [True]}, "manual_refs"),
    ({"turbine_id": "WT001", "category": "nuisance", "manual_refs": ["262"]}, "manual_refs"),
    ({"turbine_id": "WT001", "category": "nuisance", "manual_refs": list(range(51))}, "manual_refs"),
    ({"turbine_id": "WT001", "category": "nuisance", "root_cause": "x" * 4001}, "root_cause"),
    ({"turbine_id": "WT001", "category": "nuisance", "actions": "check"}, "actions"),
    ({"turbine_id": "WT001", "category": "nuisance", "confidence": 1.5}, "confidence"),
    ({"turbine_id": "WT001", "category": "nuisance", "confidence": True}, "confidence"),
])
def test_validate_prediction_rejects_malformed_items(item: dict, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        rp.validate_prediction(item, ["WT001"])


# ── 3–6. 端點 ────────────────────────────────────────────────────────────────


@pytest.fixture
def client(generated: Dict[str, object], monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)
    monkeypatch.setattr(replay_ep, "get_broker", lambda: generated["broker"])
    app = FastAPI()
    app.include_router(replay_ep.router)
    return TestClient(app)


def _bearer(role: str = "supervisor") -> Dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject='teacher', role=role, name='T')}"}


def _create(client: TestClient, scenario_id: int, **body: object) -> dict:
    # 模組共用同一個情境、混用兩種模式：明確允許並存（防呆本身另有測試）
    body.setdefault("allow_overlap", True)
    resp = client.post(f"/api/scenarios/{scenario_id}/replay-runs", json=body, headers=_bearer())
    assert resp.status_code == 201, resp.text
    return resp.json()


def _ws(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _until_finished(ws: object) -> List[dict]:
    messages = []
    while True:
        message = ws.receive_json()  # type: ignore[attr-defined]
        messages.append(message)
        if message["type"] == "control" and message["status"] == "finished":
            return messages


def test_practice_stream_delivers_the_pack_and_stamps_predictions(client: TestClient,
                                                                  generated: Dict[str, object]) -> None:
    sid: int = generated["scenario_id"]  # type: ignore[assignment]
    created = _create(client, sid, mode="practice", speed=FAST)
    assert created["token"].startswith(rp.TOKEN_PREFIX) and created["ws_path"] == "/ws/replay"
    with client.websocket_connect("/ws/replay", headers=_ws(created["token"])) as ws:
        started = ws.receive_json()
        assert (started["type"], started["status"]) == ("control", "started")
        stream = started["stream"]
        assert stream["pack_id"] == sp.pack_id_for(sid) and stream["mode"] == "practice"
        assert stream["speed"] == FAST and stream["connection_no"] == 1 and stream["turbines"] == ["WT001", "WT002",
                                                                                                    "WT003"]
        assert len(started["tag_dictionary"]) == len(sp.pack_columns())
        assert len(started["alarm_catalog"]["events"]) == len(sp.alarm_catalog_snapshot()["events"])
        # 開播就送一筆（10000× 下受測端反應稍慢，蓋章時間就會超過情境結束，對不到 case）
        ws.send_json({"type": "prediction", "id": "early", "turbine_id": "WT001", "category": "real_fault",
                      "component": "main_bearing", "manual_refs": [262]})
        predicted_at: Optional[str] = None
        messages: List[dict] = []
        while True:
            message = ws.receive_json()
            messages.append(message)
            if message["type"] == "event" and message["event_type"] in ("alarm_raised", "trip") \
                    and predicted_at is None and message["turbine_id"] == "WT001":
                predicted_at = message["ts"]
                ws.send_json({"type": "prediction", "id": "p1", "turbine_id": "WT001", "category": "real_fault",
                              "component": "main_bearing", "manual_refs": [message["alarm_code"]],
                              "ts": "1999-01-01T00:00:00Z", "pack_id": "cheat"})
            if message["type"] == "control" and message["status"] == "finished":
                break
        assert messages[-1]["closing_in_s"] == rp.CLOSE_GRACE_S
        # 情境結束後的預測不收（評分時對不到任何 case）
        ws.send_json({"type": "prediction", "id": 2, "turbine_id": "WT002", "category": "nuisance"})
        late = ws.receive_json()
    kinds = [m["type"] for m in messages]
    assert kinds.count("reading") == 2160 and kinds.count("event") == len(_messages(generated["frames"], "event"))  # type: ignore[arg-type]
    acks = [m for m in messages if m["type"] == "ack"]
    assert [a["ref"] for a in acks] == ["early", "p1"]
    assert acks[0]["ts"] >= started["sim_ts"]
    assert predicted_at is not None and acks[1]["ts"] >= predicted_at, "蓋章時間不早於受測端看到的資料"
    assert (late["ref"], late["accepted"], late["errors"]) == (2, False, ["情境已結束（模擬時間超過 sim_end），不再收預測"])
    acks = [a for a in acks if a["accepted"]]

    run_id = created["run"]["id"]
    resp = client.get(f"/api/replay-runs/{run_id}/predictions", headers=_bearer())
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("application/x-ndjson")
    assert f"{sp.pack_id_for(sid)}-run{run_id}.predictions.jsonl" in resp.headers["content-disposition"]
    lines = [json.loads(line) for line in resp.text.splitlines()]
    assert [p["ts"] for p in lines] == [a["ts"] for a in acks]
    assert all(p["pack_id"] == sp.pack_id_for(sid) for p in lines), "受測端填的 pack_id / ts 不採用"

    # 下載的檔案直接給 starter kit 的評分程式
    answers = kit_score.load_answers([generated["tmp"] / "full"])  # type: ignore[operator]
    predictions, invalid = kit_score.read_predictions(resp.text.splitlines(), kit_score.load_vocabulary())
    report = kit_score.score(answers, predictions, kit_score.load_vocabulary(), invalid)
    bearing = next(r for r in report.case_results if r.turbine_id == "WT001")
    assert invalid == [] and bearing.detected and bearing.component_correct


def test_practice_runs_restart_for_every_connection(client: TestClient, generated: Dict[str, object]) -> None:
    created = _create(client, generated["scenario_id"], mode="practice", speed=FAST)  # type: ignore[arg-type]
    firsts = []
    for expected_no in (1, 2):
        with client.websocket_connect("/ws/replay", headers=_ws(created["token"])) as ws:
            started = ws.receive_json()
            assert started["stream"]["connection_no"] == expected_no
            firsts.append(next(m for m in iter(ws.receive_json, None) if m["type"] == "reading")["ts"])
    assert firsts[0] == firsts[1] == generated["frames"][0].message["ts"]  # type: ignore[index]


def _set_started(storage: Storage, run_id: int, started: datetime) -> None:
    conn = storage._get_conn()
    conn.execute("UPDATE replay_runs SET started_at = ? WHERE id = ?", (iso_utc(started), run_id))
    conn.commit()


def test_evaluation_clock_starts_at_first_connection_and_joiners_cannot_rewind(
        client: TestClient, generated: Dict[str, object]) -> None:
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    speed = 60.0
    created = _create(client, generated["scenario_id"], mode="evaluation", speed=speed)  # type: ignore[arg-type]
    run_id = created["run"]["id"]
    assert created["run"]["status"] == "not_started"
    with client.websocket_connect("/ws/replay", headers=_ws(created["token"])) as ws:
        ws.receive_json()
    started_at = storage.get_replay_run(run_id)["started_at"]  # type: ignore[index]
    assert started_at is not None
    # 第一次連線定下的開始時間之後不會再變
    with client.websocket_connect("/ws/replay", headers=_ws(created["token"])) as ws:
        ws.receive_json()
    assert storage.get_replay_run(run_id)["started_at"] == started_at  # type: ignore[index]

    # 模擬「已經開播 1 小時」：不補送就從現在開始，補送則先送過去的資料，但時間不倒回
    _set_started(storage, run_id, datetime.now(timezone.utc) - timedelta(seconds=3600 / speed))
    with client.websocket_connect("/ws/replay?backfill=false", headers=_ws(created["token"])) as ws:
        started = ws.receive_json()
        now = parse_iso(started["sim_ts"])
        assert now >= T0 + timedelta(minutes=59)
        first = next(m for m in iter(ws.receive_json, None) if m["type"] in ("reading", "event", "stats"))
        assert parse_iso(first.get("ts") or first["window_end"]) >= now - timedelta(seconds=10)
    with client.websocket_connect("/ws/replay", headers=_ws(created["token"])) as ws:
        started = ws.receive_json()
        assert started["stream"]["backfill"] is True
        first = next(m for m in iter(ws.receive_json, None) if m["type"] == "reading")
        assert parse_iso(first["ts"]) < T0 + timedelta(minutes=1), "補送從頭開始"
        assert parse_iso(started["sim_ts"]) >= T0 + timedelta(minutes=59), "但時鐘仍是直播的現在"
    listed = client.get(f"/api/scenarios/{generated['scenario_id']}/replay-runs", headers=_bearer()).json()
    view = next(r for r in listed["runs"] if r["id"] == run_id)
    assert view["status"] == "running" and view["ends_at"] is not None and view["connections"] == 4

    # 播完且過了寬限期：不能再連
    _set_started(storage, run_id, datetime.now(timezone.utc) - timedelta(days=1))
    with client.websocket_connect("/ws/replay", headers=_ws(created["token"])) as ws:
        error = ws.receive_json()
    assert error == {"type": "error", "code": 4410, "message": "單次回放已結束"}
    listed = client.get(f"/api/scenarios/{generated['scenario_id']}/replay-runs", headers=_bearer()).json()
    assert next(r for r in listed["runs"] if r["id"] == run_id)["status"] == "finished"


def test_predictions_after_the_scenario_end_are_rejected(generated: Dict[str, object]) -> None:
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    replay = rp.ScenarioReplay(storage, generated["scenario_id"])  # type: ignore[arg-type]
    run = storage.create_replay_run(replay.scenario_id, rp.token_digest(rp.new_token()), "evaluation", 60.0,
                                    None, iso_utc(), None, iso_utc(datetime.now(timezone.utc) + timedelta(days=1)))
    sent: List[dict] = []

    class _Socket:
        async def send_text(self, text: str) -> None:
            sent.append(json.loads(text))

    clock = rp.ReplayClock(replay.sim_start, 60.0, time.time() - 121)  # 60× 下 2 h 情境 120 s 播完
    connection = replay_ep._ReplayConnection(_Socket(), storage, run, replay, clock, 1, None)  # type: ignore[arg-type]
    asyncio.run(connection._prediction({"type": "prediction", "turbine_id": "WT001", "category": "nuisance"}))
    assert sent[-1]["accepted"] is False and sent[-1]["errors"] == ["情境已結束（模擬時間超過 sim_end），不再收預測"]
    assert storage.replay_predictions(int(run["id"])) == []


@pytest.mark.parametrize("token, code", [(None, 4401), ("wmr_not-a-token", 4401)])
def test_missing_or_unknown_tokens_are_rejected(client: TestClient, token: Optional[str], code: int) -> None:
    path = "/ws/replay" if token is None else f"/ws/replay?token={token}"
    with client.websocket_connect(path) as ws:
        error = ws.receive_json()
    assert error["type"] == "error" and error["code"] == code


def test_revoked_and_expired_runs_are_rejected(client: TestClient, generated: Dict[str, object]) -> None:
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    sid: int = generated["scenario_id"]  # type: ignore[assignment]
    revoked = _create(client, sid, mode="practice", speed=FAST)
    resp = client.delete(f"/api/replay-runs/{revoked['run']['id']}", headers=_bearer())
    assert resp.status_code == 200 and resp.json()["run"]["status"] == "revoked"
    with client.websocket_connect(f"/ws/replay?token={revoked['token']}") as ws:
        assert ws.receive_json()["code"] == 4403
    expired = _create(client, sid, mode="practice", speed=FAST)
    conn = storage._get_conn()
    conn.execute("UPDATE replay_runs SET expires_at = ? WHERE id = ?",
                 (iso_utc(datetime.now(timezone.utc) - timedelta(minutes=1)), expired["run"]["id"]))
    conn.commit()
    with client.websocket_connect("/ws/replay", headers=_ws(expired["token"])) as ws:
        assert ws.receive_json() == {"type": "error", "code": 4403, "message": "回放 token 已到期"}
    assert client.delete("/api/replay-runs/99999", headers=_bearer()).status_code == 404


def test_revoking_stops_accepting_predictions_and_bad_messages_get_errors(
        client: TestClient, generated: Dict[str, object]) -> None:
    created = _create(client, generated["scenario_id"], mode="practice", speed=1.0)  # type: ignore[arg-type]
    with client.websocket_connect("/ws/replay", headers=_ws(created["token"])) as ws:
        ws.receive_json()
        replies = []
        for raw in ("not json", "[1, 2]", json.dumps({"type": "hello"}), "x" * (rp.MAX_CLIENT_MESSAGE_BYTES + 1),
                    json.dumps({"type": "ping"})):
            ws.send_text(raw)
            replies.append(next(m for m in iter(ws.receive_json, None) if m["type"] in ("error", "pong")))
        assert [r["type"] for r in replies] == ["error"] * 4 + ["pong"]
        assert client.delete(f"/api/replay-runs/{created['run']['id']}", headers=_bearer()).status_code == 200
        ws.send_json({"type": "prediction", "turbine_id": "WT001", "category": "nuisance"})
        ack = next(m for m in iter(ws.receive_json, None) if m["type"] == "ack")
    assert ack["accepted"] is False and ack["errors"] == ["回放已撤銷"]


def test_connection_limit_per_run(client: TestClient, generated: Dict[str, object],
                                  monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rp, "MAX_CONNECTIONS_PER_RUN", 1)
    created = _create(client, generated["scenario_id"], mode="practice", speed=1.0)  # type: ignore[arg-type]
    with client.websocket_connect("/ws/replay", headers=_ws(created["token"])) as first:
        first.receive_json()
        with client.websocket_connect("/ws/replay", headers=_ws(created["token"])) as second:
            assert second.receive_json()["code"] == 4409
    assert replay_ep._open_connections == {}


def test_stream_closes_after_the_grace_period(client: TestClient, generated: Dict[str, object],
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rp, "CLOSE_GRACE_S", 0.2)
    created = _create(client, generated["scenario_id"], mode="practice", speed=FAST)  # type: ignore[arg-type]
    with client.websocket_connect("/ws/replay", headers=_ws(created["token"])) as ws:
        ws.receive_json()
        finished = _until_finished(ws)[-1]
        assert finished["closing_in_s"] == 0.2
        from starlette.websockets import WebSocketDisconnect
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 1000


# ── REST ─────────────────────────────────────────────────────────────────────


def test_rest_endpoints_need_a_supervisor(client: TestClient, generated: Dict[str, object]) -> None:
    sid = generated["scenario_id"]
    assert client.post(f"/api/scenarios/{sid}/replay-runs", json={}).status_code == 401
    assert client.post(f"/api/scenarios/{sid}/replay-runs", json={},
                       headers=_bearer("employee")).status_code == 403
    assert client.get(f"/api/scenarios/{sid}/replay-runs", headers=_bearer("employee")).status_code == 403
    assert client.get("/api/replay-runs/1/predictions", headers=_bearer("employee")).status_code == 403
    assert client.delete("/api/replay-runs/1", headers=_bearer("employee")).status_code == 403


@pytest.mark.parametrize("body", [{"speed": 0}, {"speed": rp.MAX_SPEED * 2}, {"mode": "exam"},
                                  {"expires_in_hours": 0}, {"label": "x" * 101}])
def test_create_validates_parameters(client: TestClient, generated: Dict[str, object], body: dict) -> None:
    resp = client.post(f"/api/scenarios/{generated['scenario_id']}/replay-runs", json=body, headers=_bearer())
    assert resp.status_code == 422


def test_create_defaults_and_listing_hide_the_token(client: TestClient, generated: Dict[str, object]) -> None:
    sid = generated["scenario_id"]
    assert client.post("/api/scenarios/99999/replay-runs", json={}, headers=_bearer()).status_code == 404
    created = client.post(f"/api/scenarios/{sid}/replay-runs", json={"label": "期末", "allow_overlap": True},
                          headers=_bearer()).json()
    run = created["run"]
    assert (run["mode"], run["speed"], run["label"], run["created_by"]) == ("evaluation", rp.DEFAULT_SPEED, "期末",
                                                                            "teacher")
    assert parse_iso(run["expires_at"]) - parse_iso(run["created_at"]) == timedelta(hours=rp.DEFAULT_EXPIRES_HOURS)
    listed = client.get(f"/api/scenarios/{sid}/replay-runs", headers=_bearer()).text
    assert created["token"] not in listed and rp.token_digest(created["token"]) not in listed
    assert "token" not in json.loads(listed)["runs"][0]


def test_deleting_the_scenario_deletes_its_replays(tmp_path: Path) -> None:
    storage = Storage(db_path=str(tmp_path / "farm.db"))
    sid = storage.create_session("simulation", 1, config={"kind": storage.SCENARIO_KIND, "status": "ok"})
    run = storage.create_replay_run(sid, "digest", "practice", 60.0, None, iso_utc(), None, iso_utc())
    storage.add_replay_prediction(int(run["id"]), 1, iso_utc(), "2026-01-01T00:00:00.000000Z", {"a": 1})
    assert storage.delete_scenario(sid)
    assert storage.list_replay_runs(sid) == [] and storage.replay_predictions(int(run["id"])) == []


# ── starter kit 受測端範例（真的 uvicorn 伺服器）與出題端 CLI ──────────────────────


def test_kit_stream_client_against_a_real_server(generated: Dict[str, object], monkeypatch: pytest.MonkeyPatch,
                                                 tmp_path: Path) -> None:
    import socket
    import threading

    import uvicorn

    import stream_client

    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setattr(replay_ep, "get_broker", lambda: generated["broker"])
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    # 1200×：2 h 情境 6 s 播完；受測端慢個幾十 ms 只差幾十秒模擬時間，預測不會超過情境結束而被退回
    run, token = rp.create_run(storage, generated["scenario_id"], mode="evaluation", speed=1200.0,  # type: ignore[arg-type]
                               allow_overlap=True)
    app = FastAPI()
    app.include_router(replay_ep.router)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 10
        while not server.started and time.time() < deadline:
            time.sleep(0.05)
        assert server.started
        record = tmp_path / "received.jsonl"
        url = f"ws://127.0.0.1:{port}/ws/replay"
        summary = asyncio.run(asyncio.wait_for(stream_client.run(url, token, record=record, verbose=False), 60))
        # 被拒絕：關閉碼與伺服器的說明都拿得到（不是 traceback）；--check 不開始計時
        bad = asyncio.run(asyncio.wait_for(stream_client.run(url, "wmr_bad", verbose=False), 30))
        checked = asyncio.run(asyncio.wait_for(stream_client.run(url, token, check=True, verbose=False), 30))
        exit_code = stream_client.main([url, "--token", "wmr_bad", "-q"])
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    frames: List[rp.ReplayFrame] = generated["frames"]  # type: ignore[assignment]
    assert summary.counts["reading"] == len(_messages(frames, "reading"))
    assert summary.counts["event"] == len(_messages(frames, "event"))
    assert summary.counts["stats"] == len(_messages(frames, "stats"))
    assert summary.rejected == [] and summary.accepted == summary.counts["ack"] > 0
    stored = storage.replay_predictions(int(run["id"]))
    assert len(stored) == summary.accepted
    assert {p["prediction"]["component"] for p in stored} >= {"main_bearing"}
    assert len(record.read_text(encoding="utf-8").splitlines()) == sum(summary.counts.values())
    assert summary.close_code == 1000
    assert bad.close_code == 4401 and bad.errors[0]["message"] == "回放 token 無效" and exit_code == 1
    assert checked.counts == {"control": 1} and checked.close_code == 1000


def test_kit_stream_client_reports_a_close_while_judging(capsys: pytest.CaptureFixture[str]) -> None:
    """判斷送出前連線已被關閉（例：出題端撤銷 4403）：印出關閉碼與統計，不是 traceback；網址錯也一樣。"""
    import socket
    import threading

    from websockets.asyncio.server import ServerConnection, serve

    import stream_client

    started = {"type": "control", "status": "started", "sim_ts": "2026-03-02T01:00:10Z",
               "stream": {"pack_id": "z72-fake", "mode": "evaluation", "speed": 60, "sim_start": "a", "sim_end": "b",
                          "turbines": ["WT001"], "data": True}}
    event = {"type": "event", "ts": "2026-03-02T02:00:10Z", "turbine_id": "WT001", "event_type": "alarm_raised",
             "alarm_code": 262, "alarm_level": "A", "alarm_text": "Main bearing 1 temperature high"}

    async def handler(ws: ServerConnection) -> None:
        await ws.send(json.dumps(started))
        await ws.send(json.dumps(event))
        await ws.close(code=4403)

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    ready, stop = threading.Event(), threading.Event()

    def serve_forever() -> None:
        async def main() -> None:
            async with serve(handler, "127.0.0.1", port):
                ready.set()
                while not stop.is_set():
                    await asyncio.sleep(0.05)
        asyncio.run(main())

    thread = threading.Thread(target=serve_forever, daemon=True)
    thread.start()
    try:
        assert ready.wait(10)
        exit_code = stream_client.main([f"ws://127.0.0.1:{port}/ws/replay", "--token", "x", "-q"])
    finally:
        stop.set()
        thread.join(timeout=10)
    out = capsys.readouterr().out
    assert exit_code == 1 and "連線關閉：4403" in out
    assert stream_client.main(["http://127.0.0.1:1/ws/replay", "--token", "x"]) == 1, "網址錯：訊息，不是 traceback"
    assert "連不上" in capsys.readouterr().err


def test_farm_cannot_be_switched_during_a_running_evaluation(generated: Dict[str, object],
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    """回放與 token 存在目前風場的 DB：正式評測進行中切換風場（409），撤銷 / 播完後才放行。"""
    from fastapi import HTTPException

    from server.routers import farms as farms_ep

    storage: Storage = generated["storage"]  # type: ignore[assignment]
    switched: List[str] = []

    class _Broker:
        active_farm_id = "farm-a"

        def __init__(self) -> None:
            self.storage = storage

        def switch_farm(self, farm_id: str) -> bool:
            switched.append(farm_id)
            return False  # 測試只看守門：之後的 404 表示已放行到切換

    monkeypatch.setattr(farms_ep, "_get_broker", lambda: _Broker())
    run, _ = rp.create_run(storage, int(generated["scenario_id"]), mode="evaluation", speed=60.0,  # type: ignore[call-overload]
                           allow_overlap=True)
    storage.start_replay_run(int(run["id"]), iso_utc())  # type: ignore[arg-type]
    with pytest.raises(HTTPException) as exc:
        asyncio.run(farms_ep.activate_farm("farm-b"))
    assert exc.value.status_code == 409 and f"#{run['id']}" in str(exc.value.detail) and switched == []
    with pytest.raises(HTTPException) as exc:
        asyncio.run(farms_ep.activate_farm("farm-a"))  # 重新啟用同一個風場不受影響
    assert exc.value.status_code == 404 and switched == ["farm-a"]
    storage.revoke_replay_run(int(run["id"]), iso_utc())  # type: ignore[arg-type]
    with pytest.raises(HTTPException) as exc:
        asyncio.run(farms_ep.activate_farm("farm-b"))
    assert exc.value.status_code == 404 and switched == ["farm-a", "farm-b"]


def test_cli_creates_lists_revokes_and_exports(generated: Dict[str, object], tmp_path: Path,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    import replay_runs

    db = str(generated["tmp"] / "farm.db")  # type: ignore[operator]
    sid = str(generated["scenario_id"])
    assert replay_runs.main([db, "create", sid, "--mode", "practice", "--speed", "600", "--label", "第3組",
                             "--allow-overlap"]) == 0
    out = capsys.readouterr().out
    token = next(line.split("：", 1)[1] for line in out.splitlines() if line.startswith("token："))
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    run = storage.find_replay_run(rp.token_digest(token))
    assert run is not None and (run["mode"], run["speed"], run["label"], run["created_by"]) == \
        ("practice", 600.0, "第3組", "cli")
    run_id = int(run["id"])
    record = rp.prediction_record(sp.pack_id_for(int(sid)), T0, rp.validate_prediction(
        {"turbine_id": "WT001", "category": "real_fault", "component": "main_bearing"}, ["WT001"]))
    storage.add_replay_prediction(run_id, 1, iso_utc(), str(record["ts"]), record)
    assert replay_runs.main([db, "list", sid]) == 0 and f"#{run_id}" in capsys.readouterr().out
    out_file = tmp_path / "p.jsonl"
    assert replay_runs.main([db, "predictions", str(run_id), "-o", str(out_file)]) == 0
    assert [json.loads(line) for line in out_file.read_text(encoding="utf-8").splitlines()] == [record]
    assert replay_runs.main([db, "revoke", str(run_id)]) == 0 and "revoked" in capsys.readouterr().out
    assert replay_runs.main([db, "revoke", "99999"]) == 1
    assert replay_runs.main([db, "predictions", "99999"]) == 1
    assert replay_runs.main([db, "create", "99999"]) == 1
    assert replay_runs.main([db, "create", sid, "--speed", "0"]) == 2
    assert replay_runs.main([str(tmp_path / "missing.db"), "list", sid]) == 2


# ── code review 補測：時鐘因果（假時鐘驅動傳送端）、防呆、上限、壞訊息 ─────────────────


def _tiny_scenario(storage: Storage) -> int:
    """2 台 × 30 筆（每 10 s）的最小可回放情境。"""
    sid = storage.create_session("simulation", 2, config={
        "kind": storage.SCENARIO_KIND, "status": "ok", "events_session_isolated": True, "duration_hours": 0.1,
        "time_step": 10.0, "site_timezone": "Asia/Taipei",
    })
    conn = storage._get_conn()
    conn.executemany(
        "INSERT INTO turbine_data (timestamp, turbine_id, session_id, scada_json) VALUES (?, ?, ?, ?)",
        [(iso_utc(T0 + timedelta(seconds=10 * i)), tid, sid, json.dumps({"WTUR_TotPwrAt": 100.0 + i}))
         for i in range(30) for tid in ("WT001", "WT002")],
    )
    conn.commit()
    return sid


class _Socket:
    """假的 WebSocket：記下每則訊息送出時的（假）實際時間。"""

    def __init__(self, now: List[float], on_send: Optional[object] = None) -> None:
        self.now = now
        self.sent: List[tuple] = []
        self.on_send = on_send

    async def send_text(self, text: str) -> None:
        self.sent.append((self.now[0], json.loads(text)))
        if callable(self.on_send):
            self.on_send(self)


def _fake_clock(monkeypatch: pytest.MonkeyPatch, start: float = 1000.0) -> List[float]:
    """把 ``wall_time`` 與 ``asyncio.sleep`` 換成假時鐘：sleep 直接把時間往前推。"""
    now = [start]
    real_sleep = asyncio.sleep

    async def fake_sleep(delay: float, result: object = None) -> object:
        now[0] += max(0.0, delay)
        await real_sleep(0)
        return result

    monkeypatch.setattr(rp, "wall_time", lambda: now[0])
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return now


def _due(message: dict, sim_end: datetime) -> datetime:
    if message["type"] == "stats":
        return min(parse_iso(message["window_end"]), sim_end)
    return parse_iso(message["ts"])


def _connection(storage: Storage, replay: rp.ScenarioReplay, socket: _Socket, speed: float,
                start: float) -> tuple:
    run = storage.create_replay_run(replay.scenario_id, rp.token_digest(rp.new_token()), "practice", speed, None,
                                    iso_utc(), None, iso_utc(datetime.now(timezone.utc) + timedelta(days=1)))
    clock = rp.ReplayClock(replay.sim_start, speed, start)
    return replay_ep._ReplayConnection(socket, storage, run, replay, clock, 1, None), clock, run  # type: ignore[arg-type]


def test_sender_never_sends_before_due_on_a_fake_clock(generated: Dict[str, object],
                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    now = _fake_clock(monkeypatch)
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    replay = rp.ScenarioReplay(storage, generated["scenario_id"])  # type: ignore[arg-type]
    socket = _Socket(now)
    connection, clock, _ = _connection(storage, replay, socket, 60.0, now[0])
    asyncio.run(connection.stream())
    data = [(wall, m) for wall, m in socket.sent if m["type"] in ("reading", "event", "stats")]
    assert len(data) == len(generated["frames"])  # type: ignore[arg-type]
    for wall, message in data:
        assert _due(message, replay.sim_end) <= clock.sim_now(wall), message
    # 真的照時鐘分散送出（不是一次全送），播完才送 finished，之後再等 CLOSE_GRACE_S
    assert len({wall for wall, _ in data}) > 500
    finished_wall, finished = socket.sent[-1]
    assert finished["status"] == "finished" and finished_wall >= clock.wall_at(replay.sim_end)
    assert now[0] >= clock.wall_at(replay.sim_end) + rp.CLOSE_GRACE_S


def test_revoking_mid_stream_disconnects_within_the_recheck_period(generated: Dict[str, object],
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    now = _fake_clock(monkeypatch)
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    replay = rp.ScenarioReplay(storage, generated["scenario_id"])  # type: ignore[arg-type]
    revoked_at: List[float] = []

    def revoke_after_100(socket: _Socket) -> None:
        if len(socket.sent) == 100:
            storage.revoke_replay_run(int(run["id"]), iso_utc())
            revoked_at.append(socket.now[0])

    socket = _Socket(now, revoke_after_100)
    connection, _, run = _connection(storage, replay, socket, 60.0, now[0])
    with pytest.raises(rp.ReplayError) as exc:
        asyncio.run(connection.stream())
    assert exc.value.close_code == 4403
    assert revoked_at and socket.sent[-1][0] <= revoked_at[0] + replay_ep.RUN_RECHECK_S + 1.0


def test_prediction_ts_never_precedes_data_already_sent(generated: Dict[str, object],
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    now = _fake_clock(monkeypatch)
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    replay = rp.ScenarioReplay(storage, generated["scenario_id"])  # type: ignore[arg-type]

    def stop_after_200(socket: _Socket) -> None:
        if len(socket.sent) == 200:
            from starlette.websockets import WebSocketDisconnect
            raise WebSocketDisconnect(code=1000)

    socket = _Socket(now, stop_after_200)
    connection, _, _ = _connection(storage, replay, socket, 60.0, now[0])
    with pytest.raises(Exception):
        asyncio.run(connection.stream())
    last_seen = max(_due(m, replay.sim_end) for _, m in socket.sent if m["type"] in ("reading", "event", "stats"))
    socket.on_send = None
    now[0] = 0.0  # 時鐘被調回（NTP step、VM 暫停還原）
    asyncio.run(connection._prediction({"type": "prediction", "turbine_id": "WT001", "category": "nuisance"}))
    ack = socket.sent[-1][1]
    assert ack["accepted"] is True and parse_iso(ack["ts"]) == last_seen


def test_overlapping_modes_on_one_scenario_are_refused(tmp_path: Path) -> None:
    storage = Storage(db_path=str(tmp_path / "farm.db"))
    sid = _tiny_scenario(storage)
    first, _ = rp.create_run(storage, sid, mode="practice")
    second, _ = rp.create_run(storage, sid, mode="practice")  # 同模式可以多開
    with pytest.raises(rp.ReplayRunConflict, match="練習"):
        rp.create_run(storage, sid, mode="evaluation")
    storage.revoke_replay_run(int(first["id"]), iso_utc())
    with pytest.raises(rp.ReplayRunConflict):
        rp.create_run(storage, sid, mode="evaluation")
    storage.revoke_replay_run(int(second["id"]), iso_utc())
    rp.create_run(storage, sid, mode="evaluation")
    with pytest.raises(rp.ReplayRunConflict, match="正式評測"):
        rp.create_run(storage, sid, mode="practice")
    rp.create_run(storage, sid, mode="practice", allow_overlap=True)


def test_rest_create_refuses_overlap_and_is_not_cached(client: TestClient, generated: Dict[str, object]) -> None:
    sid = generated["scenario_id"]
    _create(client, sid, mode="practice", speed=1.0)  # type: ignore[arg-type]
    resp = client.post(f"/api/scenarios/{sid}/replay-runs", json={"mode": "evaluation"}, headers=_bearer())
    assert resp.status_code == 409 and "練習" in resp.json()["detail"]
    resp = client.post(f"/api/scenarios/{sid}/replay-runs", json={"mode": "evaluation", "allow_overlap": True},
                       headers=_bearer())
    assert resp.status_code == 201 and resp.headers["cache-control"] == "no-store"


def test_evaluation_connection_limit(client: TestClient, generated: Dict[str, object],
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rp, "MAX_CONNECTIONS_PER_RUN", 1)
    created = _create(client, generated["scenario_id"], mode="evaluation", speed=1.0)  # type: ignore[arg-type]
    with client.websocket_connect("/ws/replay", headers=_ws(created["token"])) as first:
        first.receive_json()
        with client.websocket_connect("/ws/replay", headers=_ws(created["token"])) as second:
            assert second.receive_json()["code"] == 4409
    assert replay_ep._open_connections == {}
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    assert storage.get_replay_run(created["run"]["id"])["connections"] == 1  # type: ignore[index]


def test_check_mode_reports_status_without_starting_the_clock(client: TestClient,
                                                              generated: Dict[str, object]) -> None:
    created = _create(client, generated["scenario_id"], mode="evaluation", label="期末（老師備註）")  # type: ignore[arg-type]
    with client.websocket_connect("/ws/replay?check=true", headers=_ws(created["token"])) as ws:
        checked = ws.receive_json()
    assert (checked["type"], checked["status"]) == ("control", "checked")
    assert checked["run"]["status"] == "not_started" and checked["run"]["pack_id"] == created["run"]["pack_id"]
    assert "label" not in checked["run"] and "created_by" not in checked["run"]
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    run = storage.get_replay_run(created["run"]["id"])
    assert run is not None and run["started_at"] is None and run["connections"] == 0


def test_prediction_count_and_size_caps(client: TestClient, generated: Dict[str, object],
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rp, "MAX_PREDICTIONS_PER_RUN", 1)
    created = _create(client, generated["scenario_id"], mode="practice", speed=1.0)  # type: ignore[arg-type]
    prediction = {"type": "prediction", "turbine_id": "WT001", "category": "nuisance"}

    def ack(ws: object) -> dict:
        return next(m for m in iter(ws.receive_json, None) if m["type"] == "ack")  # type: ignore[attr-defined]

    with client.websocket_connect("/ws/replay", headers=_ws(created["token"])) as ws:
        ws.receive_json()
        ws.send_json(prediction)
        assert ack(ws)["accepted"] is True
        ws.send_json(prediction)
        assert ack(ws)["errors"] == ["這個回放的預測已達上限 1 筆"]
        monkeypatch.setattr(rp, "MAX_PREDICTIONS_PER_RUN", 100)
        monkeypatch.setattr(rp, "MAX_PREDICTION_BYTES_PER_RUN", 150)
        ws.send_json(prediction)
        assert "儲存上限" in ack(ws)["errors"][0]


def test_unreplayable_scenario_closes_with_4404(client: TestClient, generated: Dict[str, object],
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    created = _create(client, generated["scenario_id"], mode="practice", speed=1.0)  # type: ignore[arg-type]

    def broken(*_args: object) -> None:
        raise sp.ScenarioPackError("did not finish generating")

    monkeypatch.setattr(rp, "ScenarioReplay", broken)
    with client.websocket_connect("/ws/replay", headers=_ws(created["token"])) as ws:
        error = ws.receive_json()
    assert error["code"] == 4404 and "did not finish generating" in error["message"]
    assert replay_ep._open_connections == {}, "被拒絕也要還回連線名額"


def test_binary_extreme_and_sensor_fault_messages_keep_the_connection(client: TestClient,
                                                                       generated: Dict[str, object]) -> None:
    created = _create(client, generated["scenario_id"], mode="practice", speed=1.0)  # type: ignore[arg-type]
    with client.websocket_connect("/ws/replay", headers=_ws(created["token"])) as ws:
        ws.receive_json()

        def reply(*types: str) -> dict:
            return next(m for m in iter(ws.receive_json, None) if m["type"] in types)

        ws.send_bytes(b"\x00\x01")
        assert reply("error")["message"] == "只接受文字（JSON）訊息"
        ws.send_text('{"type": "ping", "x": ' + "9" * 5000 + "}")  # 超過 Python 整數字串上限 → ValueError
        assert reply("error")["message"] == "不是 JSON"
        ws.send_text('{"type": "prediction", "turbine_id": "WT001", "category": "nuisance", "confidence": 1'
                     + "0" * 400 + "}")
        assert "confidence" in reply("ack")["errors"][0]
        ws.send_text("x" * (rp.MAX_CLIENT_MESSAGE_BYTES + 1))
        assert "超過" in reply("error")["message"]
        ws.send_json({"type": "prediction", "turbine_id": "WT001", "category": "sensor_fault",
                      "component": "wind_vane_1"})
        assert reply("ack")["accepted"] is True
        ws.send_json({"type": "ping"})
        assert reply("pong")["type"] == "pong", "壞訊息之後連線仍在"


def test_replay_index_is_cached_per_scenario(generated: Dict[str, object], monkeypatch: pytest.MonkeyPatch) -> None:
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    monkeypatch.setattr(rp, "_INDEX_CACHE", type(rp._INDEX_CACHE)())
    calls: List[int] = []
    original = storage.session_reading_ids

    def counting(session_id: int) -> object:
        calls.append(session_id)
        return original(session_id)

    monkeypatch.setattr(storage, "session_reading_ids", counting)
    first = rp.ScenarioReplay(storage, generated["scenario_id"])  # type: ignore[arg-type]
    second = rp.ScenarioReplay(storage, generated["scenario_id"])  # type: ignore[arg-type]
    assert len(calls) == 1 and list(first._row_ids) == list(second._row_ids)


def test_missing_vocabulary_fails_loudly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(rp, "VOCABULARY_PATH", tmp_path / "missing.json")
    with pytest.raises(FileNotFoundError):
        rp._load_vocabulary()
    assert {"main_bearing", "wind_vane_1"} <= rp.VOCABULARY_COMPONENTS


def test_deleting_a_scenario_with_graded_predictions_needs_force(tmp_path: Path,
                                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    from server.routers import scenarios as scenarios_ep

    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    storage = Storage(db_path=str(tmp_path / "farm.db"))
    sid = _tiny_scenario(storage)
    run, _ = rp.create_run(storage, sid, mode="practice")
    storage.add_replay_prediction(int(run["id"]), 1, iso_utc(), "2026-01-15T03:00:10.000000Z", {"a": 1})

    class _Broker:
        pass

    broker = _Broker()
    broker.storage = storage  # type: ignore[attr-defined]
    monkeypatch.setattr(scenarios_ep, "get_broker", lambda: broker)
    app = FastAPI()
    app.include_router(scenarios_ep.router)
    client = TestClient(app)
    resp = client.delete(f"/api/scenarios/{sid}", headers=_bearer("admin"))
    assert resp.status_code == 409 and "replay predictions" in resp.json()["detail"]
    assert storage.get_scenario(sid) is not None
    assert client.delete(f"/api/scenarios/{sid}?force=true", headers=_bearer("admin")).status_code == 200
    assert storage.get_scenario(sid) is None and storage.list_replay_runs(sid) == []


def test_evaluation_speed_is_capped_by_what_the_server_can_keep_up_with(client: TestClient,
                                                                        generated: Dict[str, object]) -> None:
    # 3 台、每 10 s 一筆：上限 1000 × 10 / 3 ≈ 3333×；練習回放不受此限（只到 MAX_SPEED）
    sid = generated["scenario_id"]
    resp = client.post(f"/api/scenarios/{sid}/replay-runs", json={"mode": "evaluation", "speed": 5000,
                                                                  "allow_overlap": True}, headers=_bearer())
    assert resp.status_code == 422 and "3333.33×" in resp.json()["detail"]
    assert _create(client, sid, mode="evaluation", speed=3000)["run"]["speed"] == 3000  # type: ignore[arg-type]
    assert _create(client, sid, mode="practice", speed=rp.MAX_SPEED)["run"]["speed"] == rp.MAX_SPEED  # type: ignore[arg-type]
