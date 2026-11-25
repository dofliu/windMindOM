"""對外唯讀 API（WMOM-20261125-02，EPIC-SF 第 1 項）。

鎖住三件事：

1. **只收 API 金鑰**：沒有 / 無效 / 已撤銷一律 401，不受 ``WMOM_AUTH_ENFORCE`` 與 dev_mode 影響；金鑰在強制
   登入的伺服器上碰不到其他端點；人員的 JWT 也進不了對外端點。
2. **盲測**：讀值欄位＝盲測版資料包的欄位（不含模擬器內部量）；事件只有可觀測的（PLC 事件、運轉狀態轉換），
   故障注入 / 故障生命週期 / 模擬器跳機標記都不出現；情境 session 的資料不出現。
3. **格式與翻頁**：讀值、事件、10 分鐘統計與回放訊息同格式；游標往後翻頁、輪詢不重複不遺漏。
"""

from __future__ import annotations

import json
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterator, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

from modules.auth import api_keys as ak  # noqa: E402
from modules.auth.tokens import create_access_token  # noqa: E402
from server import scenario_pack as sp  # noqa: E402
from server.data_broker import DataBroker  # noqa: E402
from server.farm_registry import FarmRegistry  # noqa: E402
from server.routers import external as ext  # noqa: E402
from server.routers import faults as faults_ep  # noqa: E402
from server.storage import Storage  # noqa: E402
from simulator.engine import WindFarmSimulator  # noqa: E402
from simulator.physics.fault_engine import FAULT_SCENARIOS  # noqa: E402

T0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
DT = 10.0
BASE = "/api/ext/v1"
FAULT_ID = "bearing_wear"


def _z(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture(autouse=True)
def _env(monkeypatch) -> Iterator[None]:
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)
    ak.set_api_key_store(ak.InMemoryApiKeyStore())
    yield
    ak.set_api_key_store(None)


@pytest.fixture
def broker(tmp_path) -> DataBroker:
    b = DataBroker(farm_registry=FarmRegistry(data_dir=tmp_path))
    b.storage = Storage(db_path=str(tmp_path / "ext.db"))
    b.simulator = WindFarmSimulator(turbine_count=2)
    b._session_id = b.storage.create_session(
        data_source="simulation", turbine_count=2, rated_power_kw=2000, model_name="Z72-2000-MV",
        config={"site_timezone": "Asia/Taipei"})
    b._source_active = True
    b._source_kind = "simulation"
    b.simulator._running = True  # 視同即時模擬在跑（測試自己一步一步推）
    return b


@pytest.fixture
def client(broker: DataBroker, monkeypatch) -> TestClient:
    monkeypatch.setattr(ext, "get_broker", lambda: broker)
    monkeypatch.setattr(faults_ep, "get_broker", lambda: broker)
    app = FastAPI(title="external-api-test")
    app.include_router(ext.router)
    app.include_router(faults_ep.router)
    return TestClient(app)


@pytest.fixture
def key() -> str:
    _, value = ak.issue_api_key(ak.get_api_key_store(), "rag-assistant", created_by="admin-1")
    return value


def _h(key: str) -> Dict[str, str]:
    return {ak.API_KEY_HEADER: key}


def _feed(broker: DataBroker, steps: int, start: datetime = T0, first: int = 1) -> None:
    """照 Live 路徑推模擬：偵測事件、寫進 storage、記下最新讀值。"""
    sim = broker.simulator
    assert sim is not None
    for i in range(first, first + steps):
        readings = sim._run_one_step(start + timedelta(seconds=i * DT), DT)
        broker._detect_sim_events(readings)
        broker.storage.store_readings(readings, broker._session_id)
        broker._remember_stored(readings)


def _add_scenario_rows(broker: DataBroker) -> int:
    """另開一個情境 session，寫入讀值與 PLC 事件（對外端點都不該看到）。"""
    sid = broker.storage.create_session(data_source="simulation", turbine_count=2,
                                        config={"kind": "scenario", "name": "secret-exam"})
    sim = WindFarmSimulator(turbine_count=2)
    readings = sim._run_one_step(T0 + timedelta(seconds=5), DT)
    broker.storage.store_readings(readings, sid)
    broker.storage.record_event(
        event_type="fault", source="plc", title="PLC event 262", turbine_id="WT001",
        timestamp=(T0 + timedelta(seconds=5)).isoformat(), session_id=sid,
        payload={"kind": "alarm_raised", "code": 262, "level": "A", "text": "scenario-only"})
    return sid


# ── 1. 金鑰 ────────────────────────────────────────────────────────────────

_ENDPOINTS = ["/status", "/farm", "/tags", "/alarm-catalog", "/readings/latest", "/readings?turbine_id=WT001",
              "/stats-10min?turbine_id=WT001&start=2026-01-01T00:00:00Z&end=2026-01-01T01:00:00Z",
              "/events", "/alarms/active"]


def test_endpoint_list_covers_every_route() -> None:
    """新增端點時要一起進上面的清單（每個端點都驗金鑰）；對外端點只有 GET。"""
    paths = {r.path for r in ext.router.routes}
    assert paths == {BASE + e.split("?")[0] for e in _ENDPOINTS}
    assert {m for r in ext.router.routes for m in r.methods} == {"GET"}


@pytest.mark.parametrize("endpoint", _ENDPOINTS)
def test_every_endpoint_requires_a_key(client: TestClient, key: str, endpoint: str) -> None:
    assert client.get(BASE + endpoint).status_code == 401
    assert client.get(BASE + endpoint, headers=_h(key)).status_code == 200


@pytest.mark.parametrize("endpoint", ["/readings", "/stats-10min"])
def test_missing_key_is_reported_before_parameter_errors(client: TestClient, endpoint: str) -> None:
    """少參數的請求沒帶金鑰時回 401，不是 422（不對沒驗證的人透露參數格式）。"""
    assert client.get(BASE + endpoint).status_code == 401


def test_invalid_and_revoked_keys_are_rejected(client: TestClient, key: str) -> None:
    assert client.get(BASE + "/status", headers=_h("not-a-key")).status_code == 401
    assert client.get(BASE + "/status", headers=_h(ak.new_api_key())).status_code == 401
    store = ak.get_api_key_store()
    (record,) = store.list_keys()
    assert store.revoke(record.id, "2026-01-01T00:00:00+00:00")
    resp = client.get(BASE + "/status", headers=_h(key))
    assert resp.status_code == 401 and resp.headers["WWW-Authenticate"] == "ApiKey"


def test_key_is_required_even_in_dev_mode_and_without_enforcement(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("WMOM_DEV_MODE", "true")
    assert client.get(BASE + "/status").status_code == 401


def test_staff_token_does_not_open_external_endpoints(client: TestClient) -> None:
    token = create_access_token(subject="u1", role="admin", name="Admin")
    assert client.get(BASE + "/status", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_key_opens_nothing_else_when_login_is_enforced(client: TestClient, key: str, monkeypatch) -> None:
    """盲測的前提：強制登入時，金鑰看不到故障狀態，也不能注入 / 清除。"""
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    for headers in (_h(key), {"Authorization": f"Bearer {key}"}):
        assert client.get("/api/faults/active", headers=headers).status_code == 401
        assert client.get("/api/faults/scenarios", headers=headers).status_code == 401
        assert client.post("/api/faults/inject", json={"scenarioId": FAULT_ID, "turbineId": "WT001"},
                           headers=headers).status_code == 401
    status = client.get(BASE + "/status", headers=_h(key)).json()
    assert status["other_endpoints_require_login"] is True


def test_status_reports_when_other_endpoints_are_open(client: TestClient, key: str) -> None:
    assert client.get(BASE + "/status", headers=_h(key)).json()["other_endpoints_require_login"] is False


def test_key_scope_must_match() -> None:
    store = ak.InMemoryApiKeyStore()
    ak.set_api_key_store(store)
    record, value = ak.issue_api_key(store, "x", created_by="a")
    store._by_id[record.id] = ak.ApiKey(**{**record.__dict__, "scope": "other:scope"})
    app = FastAPI()
    app.include_router(ext.router)
    assert TestClient(app).get(BASE + "/tags", headers=_h(value)).status_code == 403


# ── 2. 讀值 ────────────────────────────────────────────────────────────────


def test_readings_have_exactly_the_blind_pack_columns(client: TestClient, broker: DataBroker, key: str) -> None:
    _feed(broker, 3)
    body = client.get(BASE + "/readings", params={"turbine_id": "WT001"}, headers=_h(key)).json()
    assert [r["ts"] for r in body["readings"]] == [
        (T0 + timedelta(seconds=i * DT)).strftime("%Y-%m-%dT%H:%M:%S.%fZ") for i in (1, 2, 3)]
    names = [c.name for c in sp.pack_columns()]
    for reading in body["readings"]:
        assert reading["type"] == "reading" and reading["turbine_id"] == "WT001"
        assert list(reading["values"]) == names
    # 模擬器內部量存在 storage 裡，但不給出去
    stored = json.loads(broker.storage.live_readings("WT001")[0]["scada_json"])
    assert sp.MODEL_INTERNAL_TAGS & stored.keys()
    internal_names = {tag.opc_tag.split(".", 1)[-1] for tag in sp.SCADA_REGISTRY.all_tags
                      if tag.id in sp.MODEL_INTERNAL_TAGS}
    assert internal_names and not internal_names & set(names)


def test_reading_values_match_the_replay_format(client: TestClient, broker: DataBroker, key: str) -> None:
    _feed(broker, 1)
    (reading,) = client.get(BASE + "/readings", params={"turbine_id": "WT002"}, headers=_h(key)).json()["readings"]
    row = broker.storage.live_readings("WT002")[0]
    columns = sp.pack_columns()
    expected = sp.json_values(sp.scada_values(row["scada_json"], [c.tag.id for c in columns]), columns)
    assert reading["values"] == json.loads(json.dumps(expected))
    by_name = {c.name: c for c in columns}
    for name, value in reading["values"].items():
        if value is None:
            continue
        col = by_name[name]
        if col.is_analog:
            assert isinstance(value, float)
        elif col.tag.data_type == "BOOL":
            assert isinstance(value, bool)
        else:
            assert isinstance(value, int) and not isinstance(value, bool)


def test_readings_page_forward_with_cursor(client: TestClient, broker: DataBroker, key: str) -> None:
    _feed(broker, 5)
    seen: List[str] = []
    cursor = 0
    for _ in range(10):
        body = client.get(BASE + "/readings", params={"turbine_id": "WT001", "after": cursor, "limit": 2},
                          headers=_h(key)).json()
        seen += [r["ts"] for r in body["readings"]]
        cursor = body["next_cursor"]
        if not body["has_more"]:
            break
    assert len(seen) == 5 and seen == sorted(seen)
    # 輪詢：沒有新資料時回空、游標不動；有新資料時只回新的
    again = client.get(BASE + "/readings", params={"turbine_id": "WT001", "after": cursor}, headers=_h(key)).json()
    assert again == {"readings": [], "next_cursor": cursor, "has_more": False}
    _feed(broker, 1, first=6)
    new = client.get(BASE + "/readings", params={"turbine_id": "WT001", "after": cursor}, headers=_h(key)).json()
    assert len(new["readings"]) == 1 and new["readings"][0]["ts"] > seen[-1]


def test_readings_time_range_is_half_open(client: TestClient, broker: DataBroker, key: str) -> None:
    _feed(broker, 6)
    body = client.get(BASE + "/readings", headers=_h(key), params={
        "turbine_id": "WT001", "start": _z(T0 + timedelta(seconds=20)), "end": _z(T0 + timedelta(seconds=50))}).json()
    assert [r["ts"][17:19] for r in body["readings"]] == ["20", "30", "40"]
    # 帶其他時區的時間也可以
    plus8 = (T0 + timedelta(seconds=50)).astimezone(timezone(timedelta(hours=8))).isoformat()
    body = client.get(BASE + "/readings", headers=_h(key), params={"turbine_id": "WT001", "start": plus8}).json()
    assert [r["ts"][17:19] for r in body["readings"]] == ["50", "00"]


@pytest.mark.parametrize("params", [
    {"turbine_id": "WT001", "start": "2026-01-01T00:00:00"},           # 沒帶時區
    {"turbine_id": "WT001", "start": "yesterday"},
    {"turbine_id": "WT001", "start": "2026-01-01T01:00:00Z", "end": "2026-01-01T00:00:00Z"},
    {"turbine_id": "WT001", "start": "0001-01-01T00:00:00+05:00"},    # 換算 UTC 後超出範圍
    {"turbine_id": "WT001", "end": "9999-12-31T23:59:59-05:00"},
    {"turbine_id": "WT001", "limit": 0},
    {"turbine_id": "WT001", "limit": ext.READINGS_MAX_LIMIT + 1},
    {"turbine_id": "WT001", "after": -1},
    {},                                                                  # 沒給機組
])
def test_readings_reject_bad_parameters(client: TestClient, key: str, params: Dict[str, object]) -> None:
    assert client.get(BASE + "/readings", params=params, headers=_h(key)).status_code == 422


def test_latest_readings_come_from_what_was_stored(client: TestClient, broker: DataBroker, key: str) -> None:
    assert client.get(BASE + "/readings/latest", headers=_h(key)).json() == {"readings": []}
    _feed(broker, 2)
    latest = client.get(BASE + "/readings/latest", headers=_h(key)).json()["readings"]
    assert [r["turbine_id"] for r in latest] == ["WT001", "WT002"]
    history = client.get(BASE + "/readings", params={"turbine_id": "WT001"}, headers=_h(key)).json()["readings"]
    assert latest[0] == history[-1]
    # simulator 再往前跑但沒寫進 storage（例：產生情境的批次）：最新讀值不變
    assert broker.simulator is not None
    broker.simulator._run_one_step(T0 + timedelta(days=30), DT)
    assert client.get(BASE + "/readings/latest", headers=_h(key)).json()["readings"] == latest
    status = client.get(BASE + "/status", headers=_h(key)).json()
    assert status["latest_reading_ts"] == latest[0]["ts"] and status["sample_period_s"] == 10.0


# ── 3. 事件 ────────────────────────────────────────────────────────────────


def _trip_wt001(broker: DataBroker, step: int) -> None:
    """讓 WT001 的 PLC 送出一筆真實的跳機事件（351，物理層超速停機），再照 Live 路徑記錄。"""
    sim = broker.simulator
    assert sim is not None
    model = sim.turbines["WT001"]
    readings = sim._run_one_step(T0 + timedelta(seconds=step * DT), DT)
    model.plc.note_protection_stop("overspeed_software", model._sim_time)
    broker._detect_sim_events(readings)
    broker.storage.store_readings(readings, broker._session_id)
    broker._remember_stored(readings)


def test_events_contain_only_observable_ones(client: TestClient, broker: DataBroker, key: str) -> None:
    sim = broker.simulator
    assert sim is not None
    _feed(broker, 2)
    # 故障注入：Live 會記下注入紀錄、故障生命週期（都帶故障 ID）
    assert sim.fault_engine.inject(FAULT_ID, "WT001", severity_rate=0.01, initial_severity=0.3)
    broker.record_event(event_type="fault", source="faults", title=f"Fault injected: {FAULT_ID}",
                        turbine_id="WT001", payload={"scenarioId": FAULT_ID, "turbineId": "WT001"})
    _feed(broker, 3, first=3)
    _trip_wt001(broker, 6)
    broker.record_event(event_type="fault", source="simulator", title="Automatic fault trip", turbine_id="WT001",
                        payload={"turbineId": "WT001", "faults": [FAULT_ID], "tripCodes": [351]})
    broker._record_state_transition_event("WT001", 6, 9, "plc:351")
    # 來源在白名單內、格式也對得上，但 payload 帶故障 ID 的事件（雙重保險那一條）：只有
    # is_observable_event 擋得住，SQL 預篩與 pack_event 都會放行
    marker_ts = (T0 + timedelta(seconds=12345)).isoformat()
    broker.record_event(event_type="fault", source="plc", title="PLC event 264", turbine_id="WT001",
                        timestamp=marker_ts,
                        payload={"kind": "alarm_raised", "code": 264, "level": "A", "text": "leak-marker",
                                 "scenarioId": FAULT_ID})
    broker.record_event(event_type="fault", source="simulator", title="state", turbine_id="WT002",
                        timestamp=marker_ts, payload={"fromState": 6, "toState": 7, "faults": [FAULT_ID]})

    stored = broker.storage.query_events(limit=500)
    assert any("scenarioId" in (e.get("payload") or {}) for e in stored), "測試前提：storage 裡有帶故障 ID 的事件"

    body = client.get(BASE + "/events", headers=_h(key)).json()
    events = body["events"]
    assert events and not body["has_more"]
    for event in events:
        assert list(event) == ["type", *sp.EVENT_KEYS] and event["type"] == "event"
    kinds = [(e["event_type"], e["alarm_code"]) for e in events]
    assert ("trip", 351) in kinds
    stop = next(e for e in events if e["event_type"] == "state_change" and e["to_state"] == 9)
    assert stop["stop_reason"] == "plc_trip", "停機原因只給 PLC 看得到的類別"
    text = json.dumps(body, ensure_ascii=False)
    for leaked in (FAULT_ID, "scenarioId", "Fault injected", "severity", "Automatic fault trip", "leak-marker"):
        assert leaked not in text
    assert ("alarm_raised", 264) not in kinds
    assert not [e for e in events if e["ts"].startswith("2026-01-01T03:25:45")], "帶故障 ID 的兩筆都不能出現"
    # 游標已經越過不可觀測的事件：再問一次是空的
    again = client.get(BASE + "/events", params={"after": body["next_cursor"]}, headers=_h(key)).json()
    assert again == {"events": [], "next_cursor": body["next_cursor"], "has_more": False}


def test_events_page_forward_and_filter_by_turbine(client: TestClient, broker: DataBroker, key: str) -> None:
    _feed(broker, 1)
    for i, (turbine, code) in enumerate([("WT001", 262), ("WT002", 240), ("WT001", 264), ("WT002", 244)]):
        broker.storage.record_event(
            event_type="fault", source="plc", title=f"PLC event {code}", turbine_id=turbine,
            timestamp=(T0 + timedelta(seconds=100 + i)).isoformat(), session_id=broker._session_id,
            payload={"kind": "alarm_raised", "code": code, "level": "A", "text": "t", "eventId": "e", "plcTag": "p"})
    codes: List[int] = []
    cursor = 0
    for _ in range(10):
        body = client.get(BASE + "/events", params={"after": cursor, "limit": 1}, headers=_h(key)).json()
        codes += [e["alarm_code"] for e in body["events"]]
        cursor = body["next_cursor"]
        if not body["has_more"]:
            break
    assert codes == [262, 240, 264, 244]
    only = client.get(BASE + "/events", params={"turbine_id": "WT002"}, headers=_h(key)).json()["events"]
    assert [e["alarm_code"] for e in only] == [240, 244] and {e["turbine_id"] for e in only} == {"WT002"}
    window = client.get(BASE + "/events", headers=_h(key), params={
        "start": _z(T0 + timedelta(seconds=101)), "end": _z(T0 + timedelta(seconds=103))}).json()["events"]
    assert [e["alarm_code"] for e in window] == [240, 264]


def test_event_scan_cap_keeps_paging_possible(client: TestClient, broker: DataBroker, key: str, monkeypatch) -> None:
    """可觀測事件很稀疏時，一個請求只掃到上限；用 next_cursor 接著取，不遺漏。"""
    monkeypatch.setattr(ext, "_SCAN_BATCH", 2)
    monkeypatch.setattr(ext, "_MAX_SCAN_BATCHES", 2)
    for i in range(6):  # 不可觀測（模擬器的跳機解除標記）
        broker.storage.record_event(event_type="fault", source="simulator", title="x", turbine_id="WT001",
                                    timestamp=(T0 + timedelta(seconds=i)).isoformat(),
                                    session_id=broker._session_id, payload={"turbineId": "WT001"})
    broker.storage.record_event(
        event_type="fault", source="plc", title="PLC event 262", turbine_id="WT001",
        timestamp=(T0 + timedelta(seconds=10)).isoformat(), session_id=broker._session_id,
        payload={"kind": "alarm_raised", "code": 262, "level": "A", "text": "t"})
    found: List[int] = []
    cursor = 0
    for _ in range(10):
        body = client.get(BASE + "/events", params={"after": cursor}, headers=_h(key)).json()
        found += [e["alarm_code"] for e in body["events"]]
        cursor = body["next_cursor"]
        if not body["has_more"]:
            break
    assert found == [262]


def test_scenario_sessions_are_never_exposed(client: TestClient, broker: DataBroker, key: str) -> None:
    _feed(broker, 2)
    _add_scenario_rows(broker)
    readings = client.get(BASE + "/readings", params={"turbine_id": "WT001"}, headers=_h(key)).json()["readings"]
    assert len(readings) == 2 and all(r["ts"][17:19] in ("10", "20") for r in readings)
    events_text = json.dumps(client.get(BASE + "/events", headers=_h(key)).json(), ensure_ascii=False)
    assert "scenario-only" not in events_text
    farm_text = json.dumps(client.get(BASE + "/farm", headers=_h(key)).json(), ensure_ascii=False)
    assert "secret-exam" not in farm_text


def test_legacy_scenario_markers_without_session_are_not_exposed(client: TestClient, broker: DataBroker,
                                                                 key: str) -> None:
    """``session_id`` 為 NULL 的舊事件視為 Live（WMOM-20261021-04 之前 Live 的事件都沒有 session）。

    那時候產生情境只寫 ``source="scenario"`` 的注入 / 跳機標記，不是可觀測事件，不會被放出去；可觀測的
    情境事件（PLC 事件、狀態轉換）與 session 隔離是同一版加入的，一定帶 session_id。
    """
    storage = broker.storage
    storage.record_event(event_type="fault", source="scenario", title="Scenario fault injected", turbine_id="WT001",
                         timestamp=(T0 + timedelta(seconds=1)).isoformat(), session_id=None,
                         payload={"scenarioId": FAULT_ID, "turbineId": "WT001"})
    storage.record_event(event_type="state", source="simulator", title="Entered production", turbine_id="WT001",
                         timestamp=(T0 + timedelta(seconds=2)).isoformat(), session_id=None,
                         payload={"fromState": 5, "toState": 6})
    body = client.get(BASE + "/events", headers=_h(key)).json()
    assert [(e["event_type"], e["from_state"], e["to_state"]) for e in body["events"]] == [("state_change", 5, 6)]
    assert FAULT_ID not in json.dumps(body)


def test_polling_scans_forward_from_the_cursor(broker: DataBroker) -> None:
    """沒有時間下限的查詢沿主鍵從游標往後掃（成本只跟這一頁有關），不掃整台機組再排序。"""
    statements: List[str] = []
    conn = broker.storage._get_conn()
    conn.set_trace_callback(statements.append)
    try:
        broker.storage.live_readings("WT001", after_id=5)
        broker.storage.live_readings("WT001", after_id=5, start=T0.isoformat())
    finally:
        conn.set_trace_callback(None)
    polling, ranged = statements[-2], statements[-1]
    assert "NOT INDEXED" in polling and "NOT INDEXED" not in ranged
    plan = " ".join(str(row[3]) for row in conn.execute(
        "EXPLAIN QUERY PLAN SELECT id FROM turbine_data NOT INDEXED WHERE turbine_id = ? AND id > ? ORDER BY id LIMIT ?",
        ("WT001", 5, 10)))
    assert "PRIMARY KEY" in plan and "TEMP B-TREE" not in plan


# ── 4. 目前成立的警報 ──────────────────────────────────────────────────────


def test_active_alarms_follow_the_plc(client: TestClient, broker: DataBroker, key: str) -> None:
    sim = broker.simulator
    assert sim is not None
    _feed(broker, 1)
    body = client.get(BASE + "/alarms/active", headers=_h(key)).json()
    assert body == {"live": True, "turbines": [
        {"turbine_id": "WT001", "alarm": [], "trip1": [], "trip2": []},
        {"turbine_id": "WT002", "alarm": [], "trip1": [], "trip2": []}]}
    _trip_wt001(broker, 2)
    wt001 = client.get(BASE + "/alarms/active", headers=_h(key)).json()["turbines"][0]
    assert wt001["trip1"] == [351]
    active = sim.turbines["WT001"].plc.active_codes()
    assert {code: level for level, key_ in (("A", "alarm"), ("T1", "trip1"), ("T2", "trip2"))
            for code in wt001[key_]} == active


def test_active_alarms_are_withheld_while_not_live(client: TestClient, broker: DataBroker, key: str) -> None:
    sim = broker.simulator
    assert sim is not None
    _trip_wt001(broker, 1)
    sim._bulk_running = True  # 正在產生情境：PLC 狀態是批次的
    assert client.get(BASE + "/alarms/active", headers=_h(key)).json() == {"live": False, "turbines": []}
    assert client.get(BASE + "/status", headers=_h(key)).json()["live"] is False
    sim._bulk_running = False
    broker._source_kind = "scenario"  # 產生情境模式：simulator 不自由跑
    assert client.get(BASE + "/alarms/active", headers=_h(key)).json()["live"] is False


# ── 5. 10 分鐘統計 ─────────────────────────────────────────────────────────


def test_stats_use_the_pack_algorithm_and_only_complete_windows(client: TestClient, broker: DataBroker,
                                                                 key: str) -> None:
    _feed(broker, 130)  # 00:00:10 … 00:21:40
    params = {"turbine_id": "WT001", "start": _z(T0), "end": _z(T0 + timedelta(minutes=30))}
    body = client.get(BASE + "/stats-10min", params=params, headers=_h(key)).json()
    stats = body["stats"]
    # 00:20 的窗還沒收齊（最新一筆是 00:21:40）→ 不給；第一個窗少一筆（00:00:00 那筆不存在）→ 殘缺
    assert [(s["window_start"][11:16], s["n_samples"], s["is_partial"]) for s in stats] == [
        ("00:00", 59, True), ("00:10", 60, False)]
    assert body["sample_period_s"] == 10.0

    columns = sp.pack_columns()
    ids = [c.tag.id for c in columns]
    builder = sp.StatsBuilder(columns=columns)
    for row in broker.storage.live_readings("WT001", end=(T0 + timedelta(minutes=20)).isoformat(), limit=1000):
        epoch = datetime.fromisoformat(row["timestamp"]).timestamp()
        builder.add(epoch, "WT001", sp.scada_values(row["scada_json"], ids))
    expected = [sp.stats_message(r, columns, 10.0) for r in builder.close_all()]
    assert stats == json.loads(json.dumps(expected))

    # is_partial 用間隔的中位數判定：即時資料每筆間隔都帶一點抖動，取「最常見的間隔」不穩定
    def median_of(steps: List[float]) -> object:
        builder = sp.StatsBuilder(columns=columns)
        epoch = 1000.0
        builder.add(epoch, "WT001", sp.scada_values(None, ids))
        for step in steps:
            epoch += step
            builder.add(epoch, "WT001", sp.scada_values(None, ids))
        return builder.median_period_s

    assert median_of([]) is None
    assert median_of([10.2]) == pytest.approx(10.2)
    assert median_of([10.1, 3600.0, 10.2]) == pytest.approx(10.2), "停機造成的大間隔不影響"
    assert median_of([10.3, 10.1, 3600.0, 10.2]) == pytest.approx(10.25)
    assert median_of([10.0] * 7) == pytest.approx(10.0)

    inside = client.get(BASE + "/stats-10min", headers=_h(key), params={
        "turbine_id": "WT001", "start": _z(T0 + timedelta(minutes=5)), "end": _z(T0 + timedelta(minutes=25))}).json()
    assert [s["window_start"][11:16] for s in inside["stats"]] == ["00:10"], "只回完整落在範圍內的窗"


def test_stats_wait_until_the_window_is_complete(client: TestClient, broker: DataBroker, key: str) -> None:
    """窗「結束」看的是這台機組已寫進歷史的最新讀值，不是實際時間：最後一筆還沒進來的窗不給（給了之後值會變）。"""
    params = {"turbine_id": "WT001", "start": _z(T0), "end": _z(T0 + timedelta(minutes=30))}
    assert client.get(BASE + "/stats-10min", params=params, headers=_h(key)).json() == {
        "stats": [], "sample_period_s": None}, "沒有資料"
    _feed(broker, 59)  # 最新一筆 00:09:50：第一個窗的資料到齊了，但還不知道（下一筆可能也在窗內）
    assert client.get(BASE + "/stats-10min", params=params, headers=_h(key)).json()["stats"] == []
    _feed(broker, 1, first=60)  # 00:10:00 的讀值進來，第一個窗確定收齊
    stats = client.get(BASE + "/stats-10min", params=params, headers=_h(key)).json()["stats"]
    assert [(s["window_start"][11:16], s["n_samples"]) for s in stats] == [("00:00", 59)]
    # 伺服器剛重啟（記憶體裡沒有最新讀值）：改從歷史找這台機組最近寫入的一筆，結果相同
    broker._last_stored_live = {}
    assert client.get(BASE + "/stats-10min", params=params, headers=_h(key)).json()["stats"] == stats


def test_stats_follow_the_data_clock_when_it_runs_ahead_of_real_time(client: TestClient, broker: DataBroker,
                                                                      key: str) -> None:
    """時間倍率大於 1 時讀值的時間跑在實際時間前面：照資料的時間判定，未來的窗也給。"""
    future = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(days=2)
    _feed(broker, 61, start=future)
    body = client.get(BASE + "/stats-10min", headers=_h(key), params={
        "turbine_id": "WT001", "start": _z(future), "end": _z(future + timedelta(minutes=30))}).json()
    assert [s["n_samples"] for s in body["stats"]] == [59]


def test_data_clock_is_the_last_written_live_row(broker: DataBroker) -> None:
    storage = broker.storage
    assert storage.last_live_reading_timestamp("WT001") is None
    _feed(broker, 3)
    last = (T0 + timedelta(seconds=30)).isoformat(timespec="microseconds")
    assert storage.last_live_reading_timestamp("WT001") == last
    _add_scenario_rows(broker)  # 情境的列寫在後面、時間也不同：不算
    assert storage.last_live_reading_timestamp("WT001") == last
    # 新的 Live session 寫了一筆時間較早的讀值（時間倍率調回 1 時會這樣）：時鐘跟著最後寫入的那筆
    sid = storage.create_session(data_source="simulation", turbine_count=2, config={"site_timezone": "Asia/Taipei"})
    sim = WindFarmSimulator(turbine_count=2)
    storage.store_readings(sim._run_one_step(T0 + timedelta(seconds=5), DT), sid)
    assert storage.last_live_reading_timestamp("WT002") == (T0 + timedelta(seconds=5)).isoformat(
        timespec="microseconds")
    assert storage.last_live_reading_timestamp("WT999") is None


@pytest.mark.parametrize("params", [
    {"turbine_id": "WT001", "start": "2026-01-01T00:00:00Z"},
    {"turbine_id": "WT001", "start": "2026-01-01T00:00:00Z", "end": "2026-01-02T00:00:01Z"},   # 超過 24 小時
    {"turbine_id": "WT001", "start": "2026-01-01T00:00:00", "end": "2026-01-01T01:00:00"},     # 沒帶時區
    {"start": "2026-01-01T00:00:00Z", "end": "2026-01-01T01:00:00Z"},
])
def test_stats_reject_bad_parameters(client: TestClient, key: str, params: Dict[str, object]) -> None:
    assert client.get(BASE + "/stats-10min", params=params, headers=_h(key)).status_code == 422


# ── 6. 固定資訊 ────────────────────────────────────────────────────────────


def test_farm_tags_and_catalog_match_the_pack(client: TestClient, broker: DataBroker, key: str) -> None:
    farm = client.get(BASE + "/farm", headers=_h(key)).json()
    # 欄位是白名單：要多給一個欄位，先確認它不是答案、也不是自訂文字
    assert set(farm) == {"contract_version", "turbine_model", "turbines", "site_timezone", "rated_power_kw",
                         "sample_period_s", "stats_window_s", "stats_convention"}
    status = client.get(BASE + "/status", headers=_h(key)).json()
    assert set(status) == {"api_version", "contract_version", "server_time", "live", "live_epoch", "time_scale",
                           "sample_period_s", "latest_reading_ts", "other_endpoints_require_login"}
    assert status["api_version"] == ext.EXTERNAL_API_VERSION
    assert farm["turbines"] == ["WT001", "WT002"] and farm["turbine_model"] == sp.TURBINE_MODEL
    assert farm["site_timezone"] == "Asia/Taipei" and farm["rated_power_kw"] == 2000
    assert farm["stats_convention"] == json.loads(json.dumps(sp.stats_convention(sp.pack_columns())))
    assert not {"name", "farm_id", "description", "location", "wind_profile"} & farm.keys(), "不給自訂文字與風況設定"
    tags = client.get(BASE + "/tags", headers=_h(key)).json()
    assert tags == json.loads(json.dumps({"turbine_model": sp.TURBINE_MODEL,
                                          "tags": sp.tag_dictionary(sp.pack_columns())}))
    catalog = client.get(BASE + "/alarm-catalog", headers=_h(key)).json()
    assert catalog == json.loads(json.dumps(sp.alarm_catalog_snapshot()))


def test_nothing_reveals_an_injected_fault(client: TestClient, broker: DataBroker, key: str) -> None:
    """注入故障並跑一段時間後，逐一讀過即時端點：回應裡找不到任何故障情境 ID 與注入用的詞。"""
    sim = broker.simulator
    assert sim is not None
    _feed(broker, 2)
    assert sim.fault_engine.inject(FAULT_ID, "WT001", severity_rate=0.02, initial_severity=0.5)
    _feed(broker, 70, first=3)
    assert sim.fault_engine.get_fault_status(), "測試前提：故障仍在進行"
    stats_path = f"/stats-10min?turbine_id=WT001&start={_z(T0)}&end={_z(T0 + timedelta(minutes=20))}"
    stats = client.get(BASE + stats_path, headers=_h(key)).json()
    assert stats["stats"], "測試前提：有算出統計"
    texts = [json.dumps(client.get(BASE + path, headers=_h(key)).json(), ensure_ascii=False)
             for path in ("/status", "/farm", "/readings/latest", "/readings?turbine_id=WT001",
                          "/events", "/alarms/active", stats_path)]
    for text in texts:
        for word in (*FAULT_SCENARIOS, "scenarioId", "scenario_id", "severity", "root_cause", "phase", "injected"):
            assert word not in text, word
    # 固定資訊（tag 字典、警報目錄）不帶故障情境的 ID
    for path in ("/tags", "/alarm-catalog"):
        text = json.dumps(client.get(BASE + path, headers=_h(key)).json(), ensure_ascii=False)
        for word in (*FAULT_SCENARIOS, "scenarioId", "scenario_id"):
            assert word not in text, word


def test_app_registers_the_external_router() -> None:
    from server.app import CORS_ALLOW_HEADERS, app

    paths = app.openapi()["paths"]  # 不直接讀 app.routes：新版 FastAPI 的 include_router 不一定展開成 route
    assert {BASE + e.split("?")[0] for e in _ENDPOINTS} <= paths.keys()
    assert ak.API_KEY_HEADER in CORS_ALLOW_HEADERS
