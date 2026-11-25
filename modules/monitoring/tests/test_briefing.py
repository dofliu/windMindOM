"""出發前準備卡（WMOM-20261125-05）：故障出勤卡。

1. 故障維修工單建立當下產生卡片；內容：本次事件、近 7 天事件、相關訊號與同場對照、過往工單、手冊、料件。
2. 只用可觀測資料：卡上沒有故障情境、沒有模擬器內部量、沒有工單的自由文字；以資料截止點為界。
3. 缺資料要標明並降級；不判定根因。
4. 評分用的答案另外存，只給主管端的評分端點。
5. 對外 API：工單清單只有結構化欄位；準備卡原樣給。
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import timedelta
from pathlib import Path
from typing import Dict, Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from modules.auth import api_keys as ak
from modules.workflow import hooks
from modules.workflow.domain import WorkOrderType
from modules.workflow.repository import work_order_repository as wo_repo
from server import briefing
from server import om_loop
from server import scenario_pack as sp
from server.routers import external as ext
from server.routers import operations as ops
from simulator.physics.fault_engine import FAULT_SCENARIOS
from simulator.physics.plc_protection import build_rules
from simulator.physics.scada_registry import SCADA_REGISTRY
from simulator.physics.turbine_physics import TurbineSpec

from .test_om_loop import BOSS, FARM, T0, TECH, WIRE_BREAK, Farm

BEARING = "WGEN_GnBrgTmp1"


@pytest.fixture
def farm(tmp_path) -> Iterator[Farm]:
    f = Farm(tmp_path, turbines=5)
    try:
        yield f
    finally:
        hooks.clear_work_order_listeners()
        wo_repo.clear_engine_cache_for_test()


@pytest.fixture
def worn(farm: Farm) -> Farm:
    """兩小時的健康歷史之後，WT002 軸承磨耗到跳機 240（之前先出現警報 262）。"""
    farm.drive_slow(2 * 360)
    farm.inject("bearing_wear", "WT002", severity=0.55)
    for _ in range(200):
        farm.drive_slow(6)
        if farm.model("WT002").maintenance_lock:
            break
    assert farm.model("WT002").maintenance_lock, "測試前提：軸承磨耗跳機"
    return farm


def _card(farm: Farm, index: int = 0) -> Dict:
    order = farm.orders()[index]
    stored = farm.broker.storage.get_briefing(work_order_id=str(order.id))
    assert stored is not None, f"{order.business_key} 沒有準備卡"
    return stored["card"]


def _name(tag: str) -> str:
    return next(c.name for c in sp.pack_columns() if c.tag.id == tag)


# ── 1. 內容 ────────────────────────────────────────────────────────────────


def test_card_is_made_when_a_corrective_work_order_is_created(worn: Farm) -> None:
    order = worn.orders()[0]
    assert order.source_alarm_code == "240"
    stored = worn.broker.storage.get_briefing(work_order_id=str(order.id))
    assert stored is not None and stored["business_key"] == order.business_key and stored["turbine_id"] == "WT002"
    card = stored["card"]
    assert card["card_version"] == briefing.CARD_VERSION and card["kind"] == "fault_dispatch"
    assert card["work_order"] == {"business_key": order.business_key, "turbine_id": "WT002", "type": "corrective",
                                  "priority": "normal", "source_alarm_code": 240}
    assert card["generated_late"] is False and card["data_quality"] == {"flags": [], "degraded": False}
    event = card["event"]
    assert (event["code"], event["level"], event["event_type"]) == (240, "T1", "trip")
    assert event["ts"] == card["data_cutoff"], "卡片在跳機那一步產生：截止點就是事件時間"
    recent = card["recent_events"]
    assert recent["same_code"]["count"] == 1 and recent["same_code"]["last_ts"] == event["ts"]
    assert [(o["code"], o["level"]) for o in recent["other_codes"]] == [(262, "A")], "跳機前先出現的警報"
    assert recent["farm_same_code"]["turbines"] == [], "只有這一台"


def test_related_signals_are_compared_with_the_rest_of_the_farm(worn: Farm) -> None:
    card = _card(worn)
    items = {item["name"]: item for item in card["signals"]["items"]}
    bearing = items[_name(BEARING)]
    assert bearing["role"] == "primary" and bearing["label_zh"] and bearing["unit"]
    assert bearing["deviation"] == "high" and bearing["peer_count"] == 4
    assert bearing["turbine_mean"] > bearing["farm_max"] > bearing["farm_median"] > 0
    assert bearing["change_from_baseline"] > 5, "也比自己前 6 小時高"
    context = [item for item in card["signals"]["items"] if item["role"] == "context"]
    assert {item["name"] for item in context} == {_name(t) for t in briefing.CONTEXT_TAGS}
    assert all(item["deviation"] == "normal" for item in context), "風速、功率、轉速和別台差不多"
    window = card["signals"]["window"]
    assert window["end"] == card["data_cutoff"] and card["signals"]["samples"] == 360
    assert card["signals"]["last_reading_ts"] <= card["data_cutoff"]


def test_manual_section_quotes_the_catalog_without_judging(worn: Farm) -> None:
    card = _card(worn)
    manual = card["manual"]
    assert manual["status"] == "ok" and manual["code"] == 240 and manual["source"].endswith("Appendix C")
    assert manual["cause"] and manual["rectification"] and manual["manual_page"]
    assert set(manual) == {"status", "code", "level", "text", "cause", "rectification", "max_per_hour",
                           "manual_page", "source"}, "只引警報目錄（Appendix C）"
    assert card["inventory"]["status"] == "no_mapping", "沒有料件對應表就明講，不硬湊"
    assert any("不判定根因" in note for note in card["notes"])


def test_farm_wide_trips_and_past_work_orders_show_up(farm: Farm) -> None:
    """整場同一時間同碼（外部原因的線索）與這台機組以前的工單都列在卡上。"""
    from simulator.physics.plc_protection import PlcEvent

    farm.drive_slow(60)
    old = farm.repo.create(farm_id=FARM, turbine_id="WTG-03", type=WorkOrderType.INSPECTION, title="定檢：半年",
                           description="自由文字不會出現在卡上")
    farm.start(old)
    farm.finish(old)
    farm.drive(30)

    def trip(code: int) -> PlcEvent:
        return PlcEvent(sim_time=1.0, kind="trip", code=code, level="T1", text="Grid voltage too low",
                        plc_tag=None, event_id=f"T_{code}", value=None, setpoint=None, source="protection")

    for turbine_id in ("WT001", "WT002", "WT003"):
        farm.broker._record_plc_event(turbine_id, trip(481))
    order = next(o for o in farm.orders() if o.turbine_id == "WT003" and o.source_alarm_code == "481")
    card = farm.broker.storage.get_briefing(work_order_id=str(order.id))["card"]
    # WT001、WT002 的事件比 WT003 的早記：在 WT003 的卡上看得到
    assert [t["turbine_id"] for t in card["recent_events"]["farm_same_code"]["turbines"]] == ["WT001", "WT002"]
    past = card["past_work_orders"]
    assert [(p["business_key"], p["type"], p["status"]) for p in past] == [
        (old.business_key, "inspection", "awaiting_signoff")]
    assert set(past[0]) == {"business_key", "type", "status", "source_alarm_code", "created_at", "finished_at"}
    assert {i["name"] for i in card["signals"]["items"] if i["role"] != "context"} == {
        _name(t) for t in briefing.CODE_TAGS[481]}


# ── 2. 只用可觀測資料 ──────────────────────────────────────────────────────


def test_card_holds_nothing_but_observable_data(worn: Farm) -> None:
    order = worn.orders()[0]
    stored = worn.broker.storage.get_briefing(work_order_id=str(order.id))
    blob = json.dumps(stored["card"], ensure_ascii=False).lower()
    for leak in ("bearing_wear", "scenario", "severity", "inject", "fault_engine", "ground_truth", "key_signal"):
        assert leak not in blob, leak
    for leak in ("磨耗", "注入", "情境", "故障原因", "模擬", "knowledge", "excerpt"):
        assert leak not in blob, leak
    names = {item["name"] for item in stored["card"]["signals"]["items"]}
    assert names <= {c.name for c in sp.pack_columns()}, "只有給得出去的欄位"
    internal = {t.opc_tag.split(".", 1)[-1] for t in SCADA_REGISTRY.all_tags if t.id in sp.MODEL_INTERNAL_TAGS}
    assert not names & internal
    assert order.title not in blob and "plc 事件自動開單" not in blob, "工單的標題與說明不進卡片"
    # 答案另外存：有、而且不在卡片裡
    assert stored["answer"]["has_fault"] is True
    assert [f["scenario_id"] for f in stored["answer"]["faults"]] == ["bearing_wear"]


def test_card_only_uses_data_before_the_cutoff(worn: Farm) -> None:
    order = worn.orders()[0]
    before = worn.broker.storage.get_briefing(work_order_id=str(order.id))
    worn.drive_slow(120)   # 之後又過了 20 分鐘：卡片不會變
    after = worn.broker.storage.get_briefing(work_order_id=str(order.id))
    assert after == before
    card = before["card"]
    assert card["recent_events"]["window"]["end"] == card["data_cutoff"]
    assert all(ts <= card["data_cutoff"] for ts in card["recent_events"]["same_code"]["recent"])
    # 機組狀態取自最後一筆讀值，卡上連那筆讀值的時間一起給（讀值每 10 秒一筆，可能還是跳機前的狀態）
    assert card["event"]["turbine_state"] is not None
    assert card["event"]["turbine_state_ts"] <= card["data_cutoff"]
    assert card["event"]["turbine_state_ts"] == card["signals"]["last_reading_ts"]


def test_a_card_built_for_an_earlier_moment_sees_nothing_after_it(worn: Farm) -> None:
    """資料截止點之後的事件與讀值一律不用：把截止點設在跳機前 30 分鐘，卡上就沒有那次跳機。"""
    order = worn.orders()[0]
    trip = briefing.parse_iso(_card(worn)["data_cutoff"])
    worn.drive_slow(60)   # 跳機之後又有 10 分鐘的資料
    early = trip - timedelta(minutes=30)
    card = briefing.build_fault_card(
        storage=worn.broker.storage, history=worn.broker.live_history, work_order=order, turbine_id="WT002",
        turbines=["WT001", "WT002", "WT003", "WT004", "WT005"], cutoff=early)
    assert card["data_cutoff"] == sp.iso_z(briefing.iso_utc(early))
    assert "no_event_found" in card["data_quality"]["flags"] and card["recent_events"]["same_code"]["count"] == 0
    assert card["recent_events"]["other_codes"] == [] or all(
        o["last_ts"] <= card["data_cutoff"] for o in card["recent_events"]["other_codes"])
    assert card["signals"]["last_reading_ts"] < card["data_cutoff"] and card["signals"]["samples"] == 360
    assert card["signals"]["window"]["end"] == card["data_cutoff"]
    bearing = next(i for i in card["signals"]["items"] if i["name"] == _name(BEARING))
    late_card = _card(worn)
    late_bearing = next(i for i in late_card["signals"]["items"] if i["name"] == _name(BEARING))
    assert bearing["recent_mean"] < late_bearing["recent_mean"], "早一點看，溫度還沒那麼高"


def test_events_carrying_fault_ids_never_reach_the_card(worn: Farm) -> None:
    """事件一律先過 ``is_observable_event``：來源在白名單、但 payload 帶故障 ID 的事件（雙重保險那一層）
    與其他來源的事件，都不會被卡片算進去。"""
    order = worn.orders()[0]
    cutoff = worn.broker.live_clock()
    assert cutoff is not None

    def build() -> Dict:
        return briefing.build_fault_card(
            storage=worn.broker.storage, history=worn.broker.live_history, work_order=order, turbine_id="WT002",
            turbines=["WT001", "WT002", "WT003", "WT004", "WT005"], cutoff=cutoff)

    before = build()
    stamp = briefing.iso_utc(cutoff - timedelta(minutes=1))
    trip = {"kind": "trip", "code": 240, "level": "T1", "text": "Bearing 1 temperature very high",
            "eventId": "T_240"}
    worn.broker.storage.record_event("alarm", "plc", "x", turbine_id="WT002", timestamp=stamp,
                                     payload={**trip, "scenarioId": "bearing_wear"})
    worn.broker.storage.record_event("alarm", "plc", "x", turbine_id="WT003", timestamp=stamp,
                                     payload={**trip, "faults": ["bearing_wear"]})
    worn.broker.storage.record_event("fault", "fault_engine", "x", turbine_id="WT002", timestamp=stamp,
                                     payload=dict(trip))
    after = build()
    assert before["recent_events"]["same_code"]["count"] == 1
    assert after["recent_events"] == before["recent_events"] and after["event"] == before["event"]
    # 對照：同樣的事件不帶故障 ID 就是一筆正常的 PLC 事件，會被算進去
    worn.broker.storage.record_event("alarm", "plc", "x", turbine_id="WT003", timestamp=stamp, payload=dict(trip))
    assert [t["turbine_id"] for t in build()["recent_events"]["farm_same_code"]["turbines"]] == ["WT003"]


def test_card_never_quotes_the_placeholder_knowledge_corpus() -> None:
    """知識庫目前的語料是對照故障情境寫的佔位內容（鑑別診斷、甚至寫明是模擬），不是手冊原文：卡片只引
    警報目錄。這張卡會原樣給外部（code review must-fix）。"""
    import inspect

    from modules.knowledge.corpus import KnowledgeCorpus

    corpus = KnowledgeCorpus.load()
    texts = " ".join(chunk.chunk_text for chunk in corpus.chunks)
    assert "模擬" in texts, "測試前提：語料裡真的有不該給出去的內容"
    source = inspect.getsource(briefing)
    assert "KnowledgeCorpus" not in source and "by_alarm_code" not in source
    for code in (29, 229, 230, 231, 236, 240, 242):
        manual = briefing._manual(code)
        assert "knowledge_refs" not in manual and "模擬" not in json.dumps(manual, ensure_ascii=False)


def test_related_signals_come_from_plc_logic_not_from_the_answer() -> None:
    """「相關訊號」的對應表是手冊層級的知識（哪個事件碼看哪個量測），每個 tag 都要是給得出去的欄位。"""
    pack = {c.tag.id for c in sp.pack_columns()}
    for signal, tags in briefing.SIGNAL_TAGS.items():
        assert tags and set(tags) <= pack, signal
    for code, tags in briefing.CODE_TAGS.items():
        assert set(tags) <= pack, code
    rule_signals = {rule.signal for rule in build_rules(TurbineSpec())}
    unmapped = sorted(rule_signals - set(briefing.SIGNAL_TAGS))
    assert unmapped == [], f"PLC 判定用的訊號沒有對應的量測：{unmapped}"
    assert briefing.related_tags(240)[0] == BEARING and briefing.related_tags(None) == ()
    assert briefing.related_tags(999999) == ()
    # 手寫的對應只給「PLC 沒有訊號判定規則」的碼（物理層保護停機）：有規則的碼一律從規則來
    rule_codes = {rule.code for rule in build_rules(TurbineSpec())}
    assert not set(briefing.CODE_TAGS) & rule_codes, "有判定規則的碼不要手寫對應"
    assert set(briefing.CODE_TAGS) == {351, 320, 475, 481, 482, 489}
    import inspect

    source = inspect.getsource(briefing.build_fault_card) + inspect.getsource(briefing.related_tags)
    assert "key_signals" not in source and "FAULT_SCENARIOS" not in source, "卡片不能從標準答案挑訊號"


# ── 3. 缺資料要降級 ────────────────────────────────────────────────────────


def test_missing_data_is_flagged_and_degrades_the_card(farm: Farm) -> None:
    farm.drive(20)   # 只有 20 秒的資料
    manual = farm.repo.create(farm_id=FARM, turbine_id="WT001", type=WorkOrderType.CORRECTIVE, title="異音",
                              description="現場回報")
    card = _card(farm)
    assert card["work_order"]["source_alarm_code"] is None and set(card["event"]) == {"turbine_state", "turbine_state_ts"}
    assert card["data_quality"]["degraded"] is True
    assert {"no_alarm_code", "no_baseline"} <= set(card["data_quality"]["flags"])
    assert card["manual"] == {"status": "no_alarm_code"}
    assert [i["role"] for i in card["signals"]["items"]] == ["context"] * 3, "沒有警報碼：只看背景量測"

    coded = farm.repo.create(farm_id=FARM, turbine_id="WT002", type=WorkOrderType.CORRECTIVE, title="x",
                             description="", source_alarm_code="240")
    stored = farm.broker.storage.get_briefing(work_order_id=str(coded.id))
    assert "no_event_found" in stored["card"]["data_quality"]["flags"], "帶了警報碼、卻找不到那筆事件"
    weird = farm.repo.create(farm_id=FARM, turbine_id="WT003", type=WorkOrderType.CORRECTIVE, title="x",
                             description="", source_alarm_code="8")
    flags = farm.broker.storage.get_briefing(work_order_id=str(weird.id))["card"]["data_quality"]["flags"]
    assert "signals_unmapped" in flags, "這個碼沒有對應的量測"
    assert manual.id != coded.id


def test_too_few_peers_and_stale_readings_degrade_the_card(farm: Farm) -> None:
    """可比較的機組不到 3 台就不做同場對照（不拿一兩台當「同場」）；最後一筆讀值太舊要標明。"""
    farm.drive_slow(60)
    for name in ("WT003", "WT004", "WT005"):
        farm.model(name).cmd_stop()
    farm.drive_slow(360)   # 之後的一小時只有 WT001、WT002 在發電
    order = farm.repo.create(farm_id=FARM, turbine_id="WT001", type=WorkOrderType.CORRECTIVE, title="x",
                             description="", source_alarm_code="240")
    card = farm.broker.storage.get_briefing(work_order_id=str(order.id))["card"]
    flags = card["data_quality"]["flags"]
    assert card["signals"]["peers"] == 1 and "too_few_peers" in flags and "stale_data" not in flags
    assert card["signals"]["samples"] == 360
    assert {item["deviation"] for item in card["signals"]["items"]} == {"unknown"}, "只有一台可比：不下判斷"
    assert all(item["turbine_mean"] is not None for item in card["signals"]["items"]), "自己的讀值照樣給"

    clock = farm.broker.live_clock()
    assert clock is not None
    turbines = ["WT001", "WT002", "WT003", "WT004", "WT005"]
    fresh = briefing.build_fault_card(
        storage=farm.broker.storage, history=farm.broker.live_history, work_order=order, turbine_id="WT001",
        turbines=turbines, cutoff=clock + briefing.STALE_AFTER)
    assert "stale_data" not in fresh["data_quality"]["flags"], "剛好在界線上不算太舊"
    stale = briefing.build_fault_card(
        storage=farm.broker.storage, history=farm.broker.live_history, work_order=order, turbine_id="WT001",
        turbines=turbines, cutoff=clock + briefing.STALE_AFTER + timedelta(seconds=30))
    assert "stale_data" in stale["data_quality"]["flags"] and stale["data_quality"]["degraded"] is True
    assert briefing.score_card(stale, {"faults": [], "has_fault": False})["degraded_when_missing"] is True


def test_only_corrective_orders_on_known_turbines_get_a_card(farm: Farm) -> None:
    farm.drive(30)
    inspection = farm.repo.create(farm_id=FARM, turbine_id="WT001", type=WorkOrderType.INSPECTION, title="定檢",
                                  description="")
    elsewhere = farm.repo.create(farm_id="other-farm", turbine_id="WT001", type=WorkOrderType.CORRECTIVE,
                                 title="x", description="")
    unknown = farm.repo.create(farm_id=FARM, turbine_id="葉片倉庫", type=WorkOrderType.CORRECTIVE, title="x",
                               description="")
    for order in (inspection, elsewhere, unknown):
        assert farm.broker.storage.get_briefing(work_order_id=str(order.id)) is None


# ── 4. 評分 ────────────────────────────────────────────────────────────────


def test_scoring_checks_the_card_against_the_hidden_fault_record(worn: Farm) -> None:
    order = worn.orders()[0]
    stored = worn.broker.storage.get_briefing(work_order_id=str(order.id))
    score = briefing.score_card(stored["card"], stored["answer"])
    keys = FAULT_SCENARIOS["bearing_wear"].key_signals
    assert score["has_fault"] is True and score["key_signal_flagged"] is True
    assert _name(BEARING) in score["flagged"] and _name(BEARING) in score["key_signals"]
    assert 0 < score["key_signal_listed"] <= 1 and len(score["key_signals"]) == len(
        [k for k in keys if k in {c.tag.id for c in sp.pack_columns()}])
    assert score["false_escalation"] is None and score["degraded_when_missing"] is None

    healthy = briefing.score_card(stored["card"], {"faults": [], "has_fault": False})
    assert healthy["false_escalation"] is True and healthy["key_signal_flagged"] is None, "沒有故障卻標了偏高"
    # 背景量測（風速、功率、轉速）不算：機組一跳機，功率與轉速本來就和別台不一樣
    only_context = json.loads(json.dumps(stored["card"]))
    for item in only_context["signals"]["items"]:
        item["deviation"] = "low" if item["role"] == "context" else "normal"
    assert briefing.score_card(only_context, {"faults": [], "has_fault": False})["false_escalation"] is False
    nuisance = {"faults": [{"scenario_id": "x", "category": "nuisance", "key_signals": [_name(BEARING)]}]}
    assert briefing.score_card(stored["card"], nuisance)["has_fault"] is False, "nuisance 不算故障"
    degraded = dict(stored["card"], data_quality={"flags": ["signal_data_missing"], "degraded": True})
    assert briefing.score_card(degraded, stored["answer"])["degraded_when_missing"] is True


def test_internal_endpoints_serve_the_card_and_guard_the_score(worn: Farm, monkeypatch) -> None:
    monkeypatch.setattr(ops, "get_broker", lambda: worn.broker)
    order = worn.orders()[0]
    body = asyncio.run(ops.work_order_briefing(str(order.id), farm_id=FARM))
    assert set(body) == {"work_order_id", "business_key", "turbine_id", "created_at", "data_cutoff", "card"}
    assert "answer" not in body and body["card"]["event"]["code"] == 240
    scored = asyncio.run(ops.work_order_briefing_score(str(order.id), farm_id=FARM))
    assert scored["score"]["key_signal_flagged"] is True and scored["answer"]["has_fault"] is True

    def status_of(call) -> int:
        with pytest.raises(HTTPException) as caught:
            asyncio.run(call)
        return caught.value.status_code

    assert status_of(ops.work_order_briefing("not-a-uuid", farm_id=FARM)) == 422
    # 不是目前啟用的風場：409，和「這張工單沒有卡」（404）分開，畫面才分得出來
    assert status_of(ops.work_order_briefing(str(order.id), farm_id="other-farm")) == 409
    assert status_of(ops.work_order_briefing_score(str(order.id), farm_id="other-farm")) == 409

    # 沒有卡片的工單：GET 只讀（404）；還沒完工的可以用 POST 補一張（標 generated_late）
    worn.loop.enabled = False
    late = worn.repo.create(farm_id=FARM, turbine_id="WT003", type=WorkOrderType.CORRECTIVE, title="x",
                            description="")
    done = worn.repo.create(farm_id=FARM, turbine_id="WT004", type=WorkOrderType.CORRECTIVE, title="x",
                            description="")
    worn.start(done)
    worn.finish(done)
    worn.loop.enabled = True
    assert status_of(ops.work_order_briefing(str(late.id), farm_id=FARM)) == 404
    assert worn.broker.storage.get_briefing(work_order_id=str(late.id)) is None, "GET 不會產生卡片"
    built = asyncio.run(ops.build_work_order_briefing(str(late.id), farm_id=FARM))
    assert built["card"]["generated_late"] is True and "answer" not in built
    again = asyncio.run(ops.build_work_order_briefing(str(late.id), farm_id=FARM))
    assert again == built, "已經有卡：不換掉"
    assert status_of(ops.build_work_order_briefing(str(done.id), farm_id=FARM)) == 409, "已經完工的不補"
    inspection = worn.repo.create(farm_id=FARM, turbine_id="WT003", type=WorkOrderType.INSPECTION, title="定檢",
                                  description="")
    assert status_of(ops.build_work_order_briefing(str(inspection.id), farm_id=FARM)) == 409
    assert status_of(ops.build_work_order_briefing(str(BOSS), farm_id=FARM)) == 404, "沒有這張工單"
    # 卡片做不出來是伺服器的問題（500），不要報成「即時模擬沒在跑」
    broken = worn.repo.create(farm_id=FARM, turbine_id="WT005", type=WorkOrderType.CORRECTIVE, title="x",
                              description="", source_alarm_code="262")
    worn.broker.storage._get_conn().execute("DELETE FROM briefing_cards WHERE work_order_id = ?", (str(broken.id),))
    worn.broker.storage._get_conn().commit()
    with monkeypatch.context() as patched:
        patched.setattr(briefing, "build_fault_card", lambda **_: (_ for _ in ()).throw(RuntimeError("boom")))
        assert status_of(ops.build_work_order_briefing(str(broken.id), farm_id=FARM)) == 500
    # 沒有存答案的卡不評分：不能把「沒記到答案」當成「沒有故障」
    worn.broker.storage._get_conn().execute("UPDATE briefing_cards SET answer_json = NULL WHERE work_order_id = ?",
                                            (str(late.id),))
    worn.broker.storage._get_conn().commit()
    assert status_of(ops.work_order_briefing_score(str(late.id), farm_id=FARM)) == 409

    # 評分端點：主管才看得到，而且不管有沒有開強制登入都驗
    app = FastAPI()
    app.include_router(ops.router)
    client = TestClient(app)
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)
    url = f"/api/operations/work-orders/{order.id}/briefing"
    assert client.get(url, params={"farm_id": FARM}).status_code == 200, "卡片：沒開強制登入時放行"
    assert client.get(url + "/score", params={"farm_id": FARM}).status_code in (401, 403), "評分：永遠要主管"


def test_cards_are_immutable_and_missing_ones_are_filled_in(worn: Farm) -> None:
    """卡片存了就不換（建立當下的證據與答案要留著）；還沒完工、沒有卡的故障維修工單會被補上。"""
    order = worn.orders()[0]
    before = worn.broker.storage.get_briefing(work_order_id=str(order.id))
    worn.drive_slow(60)
    assert worn.loop.make_briefing("WT002", order, late=True) is not None
    assert worn.broker.storage.get_briefing(work_order_id=str(order.id)) == before, "不換掉原本那一張"

    # 產生情境的批次期間建立的工單當下沒有風場時鐘、沒有卡：批次結束後補
    worn.loop.pause()
    sim = worn.broker.simulator
    assert sim is not None
    sim._bulk_running = True
    during = worn.repo.create(farm_id=FARM, turbine_id="WT004", type=WorkOrderType.CORRECTIVE, title="x",
                              description="")
    finished = worn.repo.create(farm_id=FARM, turbine_id="WT001", type=WorkOrderType.CORRECTIVE, title="x",
                                description="")
    assert worn.broker.storage.get_briefing(work_order_id=str(during.id)) is None
    sim._bulk_running = False
    worn.loop._batch_paused = False
    worn.start(finished)
    worn.finish(finished)
    worn.loop._batch_paused = True
    worn.loop.resume()            # 補卡排到背景：批次端點的回應不等它
    worn.loop.wait_briefings()
    filled = worn.broker.storage.get_briefing(work_order_id=str(during.id))
    assert filled is not None and filled["card"]["generated_late"] is True
    assert worn.broker.storage.get_briefing(work_order_id=str(finished.id)) is None, "已經完工的不補"
    assert worn.loop.ensure_briefings() == 0, "都補完了"


def test_cards_made_on_the_live_thread_are_built_in_the_background(worn: Farm, monkeypatch) -> None:
    """即時模擬的執行緒開單時（跳機自動開單），卡片排到背景做：整場一起跳機時模擬不會停下來等。"""
    import threading

    monkeypatch.setattr(worn.loop, "_on_live_thread", lambda: True)
    caller = threading.get_ident()
    built_on: list = []
    original = worn.loop._build_briefing

    def spy(job):
        built_on.append(threading.get_ident())
        return original(job)

    monkeypatch.setattr(worn.loop, "_build_briefing", spy)
    order = worn.repo.create(farm_id=FARM, turbine_id="WT003", type=WorkOrderType.CORRECTIVE, title="x",
                             description="", source_alarm_code="240")
    worn.loop.wait_briefings()
    assert built_on and built_on[0] != caller, "不在開單的那條執行緒上做"
    stored = worn.broker.storage.get_briefing(work_order_id=str(order.id))
    assert stored is not None and stored["card"]["work_order"]["turbine_id"] == "WT003"


def test_cards_are_not_built_on_the_event_loop(worn: Farm, monkeypatch) -> None:
    """``async def`` 的建單路由直接呼叫 repository：卡片在事件迴圈上做的話，整個伺服器的請求都要等。"""
    import threading

    built_on: list = []
    original = worn.loop._build_briefing

    def spy(job):
        built_on.append(threading.get_ident())
        return original(job)

    monkeypatch.setattr(worn.loop, "_build_briefing", spy)

    async def create():
        return worn.repo.create(farm_id=FARM, turbine_id="WT003", type=WorkOrderType.CORRECTIVE, title="x",
                                description="", source_alarm_code="240")

    order = asyncio.run(create())
    worn.loop.wait_briefings()
    assert built_on and built_on[0] != threading.get_ident(), "不在事件迴圈的執行緒上做"
    assert worn.broker.storage.get_briefing(work_order_id=str(order.id)) is not None
    # 一般的執行緒（工具、測試）當下做完
    built_on.clear()
    direct = worn.repo.create(farm_id=FARM, turbine_id="WT004", type=WorkOrderType.CORRECTIVE, title="x",
                              description="")
    assert built_on == [threading.get_ident()]
    assert worn.broker.storage.get_briefing(work_order_id=str(direct.id)) is not None


def test_a_queued_card_uses_what_was_captured_and_is_dropped_if_the_farm_changed(worn: Farm, monkeypatch) -> None:
    """卡片排著的時候風場可能已經換了：截止點、答案、要讀寫的風場都在排進去當下記下來；風場換了就不做。"""
    captured: list = []
    with monkeypatch.context() as patched:
        patched.setattr(worn.loop, "_on_live_thread", lambda: True)
        patched.setattr(worn.loop, "_build_briefing", captured.append)
        order = worn.repo.create(farm_id=FARM, turbine_id="WT003", type=WorkOrderType.CORRECTIVE, title="x",
                                 description="", source_alarm_code="240")
        worn.loop.wait_briefings()
    job = captured[0]
    assert job.storage is worn.broker.storage and job.farm_id == FARM and job.turbine_id == "WT003"
    assert job.cutoff == worn.broker.live_clock() and job.late is False
    worn.drive_slow(30)   # 排著的時候風場又跑了 5 分鐘

    with monkeypatch.context() as patched:
        patched.setattr(worn.broker, "_active_farm_id", "other-farm")
        assert worn.loop._build_briefing(job) is None, "風場換了：不做"
    with monkeypatch.context() as patched:
        patched.setattr(worn.broker, "storage", object())
        assert worn.loop._build_briefing(job) is None, "storage 換了：不做"
    assert worn.broker.storage.get_briefing(work_order_id=str(order.id)) is None

    card = worn.loop._build_briefing(job)
    assert card is not None and card["data_cutoff"] == sp.iso_z(briefing.iso_utc(job.cutoff))
    assert card["signals"]["last_reading_ts"] <= card["data_cutoff"], "用排進去當下的截止點，不是現在"
    # 定期檢查會把被丟掉的補回來：這張已經有卡，不必補
    assert worn.loop.ensure_briefings() == 0


def test_missing_cards_are_queued_once_and_given_up_after_repeated_failures(worn: Farm, monkeypatch) -> None:
    """定期檢查（每 10 個模擬分鐘，加速或補跑時只隔幾秒）不會把同一張工單一排再排；連續做不出來就不再排。"""
    import threading

    def without_card(turbine_id: str):
        worn.loop.enabled = False
        made = worn.repo.create(farm_id=FARM, turbine_id=turbine_id, type=WorkOrderType.CORRECTIVE, title="x",
                                description="")
        worn.loop.enabled = True
        return made

    order = without_card("WT003")
    gate = threading.Event()
    original = worn.loop._build_briefing

    def slow(job):
        gate.wait(10)
        return original(job)

    with monkeypatch.context() as patched:
        patched.setattr(worn.loop, "_build_briefing", slow)
        assert worn.loop.ensure_briefings() == 1
        assert worn.loop.ensure_briefings() == 0, "已經在排了"
        # 別的路徑（建單的掛鉤、手動）在它還沒做完時再排一次，也只有一份工作
        assert worn.loop.make_briefing("WT003", order, late=True, wait=False) is None
        assert worn.loop._briefing_jobs.unfinished_tasks == 1
        gate.set()
        worn.loop.wait_briefings()
    stored = worn.broker.storage.get_briefing(work_order_id=str(order.id))
    assert stored is not None and stored["card"]["generated_late"] is True
    assert worn.loop.ensure_briefings() == 0 and worn.loop._briefing_queued == set()

    other = without_card("WT004")
    with monkeypatch.context() as patched:
        patched.setattr(briefing, "build_fault_card", lambda **_: (_ for _ in ()).throw(RuntimeError("boom")))
        for _ in range(om_loop._MAX_BRIEFING_ATTEMPTS):
            assert worn.loop.ensure_briefings() == 1
            worn.loop.wait_briefings()
        assert worn.loop.ensure_briefings() == 0, "連續做不出來就不再排"
        assert worn.loop.backfill_briefing(other.id) == ("failed", None), "手動補還是會試，而且說是失敗"
    result, card = worn.loop.backfill_briefing(other.id)
    assert result == "ok" and card is not None and card["generated_late"] is True
    assert worn.loop.backfill_briefing(BOSS)[0] == "not_found"


def test_past_work_orders_carry_only_structured_fields(farm: Farm) -> None:
    """工單上的警報碼欄位是自由文字（管理端可以手填）：卡上只給純數字的。之後才開的單不算以前的工單。"""
    farm.drive(30)
    typed = farm.repo.create(farm_id=FARM, turbine_id="WT002", type=WorkOrderType.CORRECTIVE, title="x",
                             description="", source_alarm_code="bearing_wear 注入")
    numeric = farm.repo.create(farm_id=FARM, turbine_id="WTG-02", type=WorkOrderType.INSPECTION, title="x",
                               description="", source_alarm_code="262")
    order = farm.repo.create(farm_id=FARM, turbine_id="WT002", type=WorkOrderType.CORRECTIVE, title="x",
                             description="", source_alarm_code="240")
    card = farm.broker.storage.get_briefing(work_order_id=str(order.id))["card"]
    assert [(p["business_key"], p["source_alarm_code"]) for p in card["past_work_orders"]] == [
        (numeric.business_key, 262), (typed.business_key, None)]
    blob = json.dumps(card, ensure_ascii=False)
    assert "bearing_wear" not in blob and "注入" not in blob
    first = farm.broker.storage.get_briefing(work_order_id=str(typed.id))["card"]
    assert first["work_order"]["source_alarm_code"] is None and first["past_work_orders"] == []

    names = farm.loop.turbine_names("WT002")
    assert len(briefing.past_orders(farm.repo, FARM, names, typed)) == 2
    assert briefing.past_orders(farm.repo, FARM, names, typed, before=typed.created_at) == [], "之後才開的不算"
    assert [o.id for o in briefing.past_orders(farm.repo, FARM, names, order, before=order.created_at)] == [
        numeric.id, typed.id]


def test_recent_spike_is_not_diluted_and_stopped_turbines_are_not_peers(farm: Farm) -> None:
    """最後幾分鐘才飆高的訊號在 1 小時平均裡會被稀釋：最近 10 分鐘偏離也算。停機中的機組不拿來比。"""
    farm.drive_slow(360)
    farm.model("WT005").cmd_stop()          # 一台停機：不算同場的比較對象
    farm.drive_slow(330)
    sim = farm.broker.simulator
    assert sim is not None
    name = _name(BEARING)
    # 最後 5 分鐘 WT001 的軸承溫度讀值高 12 °C（直接改寫進歷史的讀值，不經模擬器）：
    # 攤到 1 小時只高 1 °C，和同場比看不出來；最近 10 分鐘高 6 °C，看得出來
    for _ in range(30):
        farm._step += 10
        sim._sim_clock = T0 + timedelta(seconds=farm._step)
        readings = sim._run_one_step(sim._sim_clock, 10.0)
        readings[0]["scada"][BEARING] = float(readings[0]["scada"][BEARING]) + 12.0
        farm.broker._on_sim_data(readings)
    order = farm.repo.create(farm_id=FARM, turbine_id="WT001", type=WorkOrderType.CORRECTIVE, title="x",
                             description="", source_alarm_code="240")
    card = farm.broker.storage.get_briefing(work_order_id=str(order.id))["card"]
    item = next(i for i in card["signals"]["items"] if i["name"] == name)
    assert item["recent_mean"] - item["turbine_mean"] > 4, "最近 10 分鐘比 1 小時平均高得多"
    assert item["deviation"] == "high"
    hourly_only, _ = briefing._deviation(item["turbine_mean"], [item["farm_median"]] * 3, 0.5)
    assert hourly_only == "normal", "測試前提：只看 1 小時平均的話看不出來"
    assert item["peer_count"] == 3 and card["signals"]["peers"] == 3, "5 台裡扣掉自己與停機的那一台"
    assert card["signals"]["recent_window"]["end"] == card["data_cutoff"]


def test_event_scan_is_complete_or_says_so(worn: Farm, monkeypatch) -> None:
    """事件很多時分批取完；超過掃描上限就標明事件不完整，不會悄悄只看到最舊的那一批。"""
    order = worn.orders()[0]
    monkeypatch.setattr(briefing, "_EVENT_SCAN_BATCH", 1)     # 每批一筆：一定要分很多批
    full = briefing.build_fault_card(
        storage=worn.broker.storage, history=worn.broker.live_history, work_order=order, turbine_id="WT002",
        turbines=["WT001", "WT002", "WT003", "WT004", "WT005"], cutoff=worn.broker.live_clock())
    assert full["event"]["code"] == 240 and "events_truncated" not in full["data_quality"]["flags"]
    monkeypatch.setattr(briefing, "_EVENT_SCAN_MAX_BATCHES", 1)
    cut = briefing.build_fault_card(
        storage=worn.broker.storage, history=worn.broker.live_history, work_order=order, turbine_id="WT002",
        turbines=["WT001", "WT002", "WT003", "WT004", "WT005"], cutoff=worn.broker.live_clock())
    assert "events_truncated" in cut["data_quality"]["flags"] and cut["data_quality"]["degraded"] is True
    assert briefing.score_card(cut, {"faults": [], "has_fault": False})["degraded_when_missing"] is True


# ── 5. 對外 API ────────────────────────────────────────────────────────────


@pytest.fixture
def api(worn: Farm, monkeypatch) -> Iterator[TestClient]:
    ak.set_api_key_store(ak.InMemoryApiKeyStore())
    monkeypatch.setattr(ext, "get_broker", lambda: worn.broker)
    app = FastAPI()
    app.include_router(ext.router)
    _, key = ak.issue_api_key(ak.get_api_key_store(), "rag-assistant", created_by="admin-1")
    client = TestClient(app)
    client.headers[ak.API_KEY_HEADER] = key
    try:
        yield client
    finally:
        ak.set_api_key_store(None)


def test_external_api_lists_work_orders_without_free_text(worn: Farm, api: TestClient) -> None:
    manual = worn.repo.create(farm_id=FARM, turbine_id="WTG-04", type=WorkOrderType.INSPECTION,
                              title="定檢：答案是軸承磨耗", description="bearing_wear 注入於 WT002")
    worn.repo.create(farm_id=FARM, turbine_id="倉庫", type=WorkOrderType.CORRECTIVE, title="x", description="")
    worn.repo.create(farm_id="other-farm", turbine_id="WT001", type=WorkOrderType.CORRECTIVE, title="x",
                     description="")
    body = api.get("/api/ext/v1/work-orders").json()
    orders = body["work_orders"]
    assert [(o["turbine_id"], o["type"], o["source_alarm_code"], o["has_briefing"]) for o in orders] == [
        ("WT002", "corrective", 240, True), ("WT004", "inspection", None, False)], "對不到機組、別座風場的不給"
    assert set(orders[0]) == {"business_key", "turbine_id", "type", "status", "priority", "source_alarm_code",
                              "created_at", "dispatched_at", "started_at", "finished_at", "closed_at",
                              "has_briefing"}
    blob = json.dumps(body, ensure_ascii=False)
    assert "軸承磨耗" not in blob and "bearing_wear" not in blob and "title" not in blob and "description" not in blob
    assert body["has_more"] is False and body["next_cursor"]

    worn.start(manual)
    worn.finish(manual)
    only_open = api.get("/api/ext/v1/work-orders", params={"open_only": True}).json()["work_orders"]
    assert {o["status"] for o in only_open} <= {"draft", "dispatched", "in_progress", "awaiting_signoff", "reopened"}
    one = api.get("/api/ext/v1/work-orders", params={"turbine_id": "WT004"}).json()["work_orders"]
    assert [o["business_key"] for o in one] == [manual.business_key] and one[0]["finished_at"] is not None
    for bad in ("nope", "2026-01-01T00:00:00Z", "~WO-1", "2026-01-01T00:00:00~WO-1", "2026-01-01T00:00:00Z|WO-1"):
        assert api.get("/api/ext/v1/work-orders", params={"after": bad}).status_code == 422, bad
    assert api.get("/api/ext/v1/work-orders", params={"after": "2026-01-01T00:00:00Z~WO-1"}).status_code == 200


def test_external_work_order_paging_neither_skips_nor_repeats(worn: Farm, api: TestClient) -> None:
    """游標是（建立時間, 工單編號）：同一時刻建立的多張工單、被濾掉的工單夾在中間，都不漏不重複。"""
    from modules.workflow.repository.orm_models import WorkOrderORM
    from sqlalchemy import update

    made = [worn.repo.create(farm_id=FARM, turbine_id=name, type=WorkOrderType.INSPECTION, title="x",
                             description="")
            for name in ("WT001", "倉庫", "WT003", "WTG-04", "不明", "WT005", "WT001")]
    # 把其中四張改成同一個建立時刻
    with worn.repo._sessionmaker() as session:
        same = made[2].created_at
        session.execute(update(WorkOrderORM).where(WorkOrderORM.id.in_([str(m.id) for m in made[2:6]]))
                        .values(created_at=same))
        session.commit()
    expected = [o["business_key"] for o in api.get("/api/ext/v1/work-orders", params={"limit": 500}).json()[
        "work_orders"]]
    assert len(expected) == 1 + 5, "跳機自動開的一張，加上對得到機組的五張"
    for limit in (1, 2, 3):
        seen, cursor = [], None
        for _ in range(20):
            params = {"limit": limit, **({"after": cursor} if cursor else {})}
            page = api.get("/api/ext/v1/work-orders", params=params).json()
            seen += [o["business_key"] for o in page["work_orders"]]
            cursor = page["next_cursor"]
            if not page["has_more"]:
                break
        assert seen == expected, f"一頁 {limit} 筆"
    # 游標可以直接放進網址，不必編碼（``+`` 沒編碼會變成空白，所以時間用 Z 結尾）
    assert re.fullmatch(r"[A-Za-z0-9:.~-]+", cursor), cursor
    raw = api.get(f"/api/ext/v1/work-orders?after={cursor}")
    assert raw.status_code == 200 and raw.json()["work_orders"] == []
    # 輪詢：帶最後的游標，沒有新工單就是空的；之後建的新工單會出現
    idle = api.get("/api/ext/v1/work-orders", params={"after": cursor}).json()
    assert idle["work_orders"] == [] and idle["next_cursor"] == cursor and idle["has_more"] is False
    newer = worn.repo.create(farm_id=FARM, turbine_id="WT002", type=WorkOrderType.INSPECTION, title="x",
                             description="")
    polled = api.get("/api/ext/v1/work-orders", params={"after": cursor}).json()
    assert [o["business_key"] for o in polled["work_orders"]] == [newer.business_key]


def test_external_api_serves_the_same_card(worn: Farm, api: TestClient) -> None:
    order = worn.orders()[0]
    stored = worn.broker.storage.get_briefing(work_order_id=str(order.id))
    body = api.get(f"/api/ext/v1/work-orders/{order.business_key}/briefing").json()
    assert set(body) == {"business_key", "turbine_id", "data_cutoff", "card"}
    assert body["card"] == json.loads(json.dumps(stored["card"])), "外部拿到的就是那一張，不多不少"
    assert body["data_cutoff"] == body["card"]["data_cutoff"]
    assert "answer" not in json.dumps(body) and "bearing_wear" not in json.dumps(body)
    assert api.get("/api/ext/v1/work-orders/WO-NOPE-000000-001/briefing").status_code == 404
    assert api.get("/api/ext/v1/status").json()["api_version"] == "1.2"
    assert "knowledge" not in json.dumps(body) and "模擬" not in json.dumps(body, ensure_ascii=False)
    # 卡片用到的事件與讀值，外部自己也拿得到（同一批資料）
    events = api.get("/api/ext/v1/events", params={"turbine_id": "WT002"}).json()["events"]
    assert body["card"]["event"]["ts"] in {e["ts"] for e in events if e["alarm_code"] == 240}


def test_wire_break_card_points_at_the_sensor_reading(farm: Farm) -> None:
    """量測回路斷線：讀值跳到量測範圍外。卡上看得到那支感測器的讀值異常，但不說是感測器壞了。"""
    farm.drive_slow(360)
    farm.inject(WIRE_BREAK, "WT001")
    farm.drive(60)
    card = _card(farm)
    assert card["event"]["code"] == 242
    primary = next(i for i in card["signals"]["items"] if i["role"] == "primary")
    assert primary["name"] == _name(BEARING)
    assert card["manual"]["cause"] and "wire" in card["manual"]["cause"].lower(), "手冊列的原因照引"
    blob = json.dumps(card, ensure_ascii=False)
    assert WIRE_BREAK not in blob and "sensor_fault" not in blob
    assert T0 + timedelta(hours=1) <= briefing.parse_iso(card["data_cutoff"]) and TECH != BOSS
