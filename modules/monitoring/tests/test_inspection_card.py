"""例行巡檢卡（WMOM-20261126-05，DEC-20261127-04）。

1. 檢查清單：每個 PLC 事件碼都對得到一項（由判定規則推出來）、量測都給得出去、部件都在詞彙裡；清單與做卡的
   程式不讀故障情境。
2. 排序：沒有證據時維持原訂順序；潛伏的故障（沒有警報，只有量測偏離）、有警報的劣化、未結案的故障維修工單都
   會讓那一項往前；健康的機組不標「注意」。
3. 卡片只含可觀測資料（沒有故障情境、工單的自由文字）；定檢工單建立就有卡；評分（只給主管）。
"""

from __future__ import annotations

import asyncio
import inspect
import json
import sys
from pathlib import Path
from typing import Dict, Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import pytest

from modules.workflow import hooks
from modules.workflow.domain import WorkOrderType
from modules.workflow.repository import work_order_repository as wo_repo
from server import briefing
from server import inspection_checklist as ic
from server import scenario_pack as sp
from server.routers import operations as ops
from simulator.physics.fault_engine import FAULT_SCENARIOS

from .test_om_loop import FARM, Farm


@pytest.fixture
def farm(tmp_path) -> Iterator[Farm]:
    f = Farm(tmp_path, turbines=5)
    try:
        yield f
    finally:
        hooks.clear_work_order_listeners()
        wo_repo.clear_engine_cache_for_test()


def _inspect(farm: Farm, turbine_id: str) -> Dict[str, object]:
    order = farm.repo.create(farm_id=FARM, turbine_id=turbine_id, type=WorkOrderType.INSPECTION,
                             title="定檢：答案是變壓器", description="transformer_overheat 在這台")
    farm.drive(10)   # 建單之後下一批讀值寫進歷史才做卡
    stored = farm.broker.storage.get_briefing(work_order_id=str(order.id))
    assert stored is not None and stored["kind"] == "routine_inspection"
    return stored


def _order(card: Dict[str, object]) -> list:
    return [item["id"] for item in card["checklist"]["items"]]  # type: ignore[index]


def _entry(card: Dict[str, object], item_id: str) -> Dict[str, object]:
    return next(item for item in card["checklist"]["items"] if item["id"] == item_id)  # type: ignore[index]


# ── 1. 檢查清單 ───────────────────────────────────────────────────────────


def test_every_plc_event_code_belongs_to_a_checklist_item() -> None:
    codes = set(briefing._rule_signals()) | set(briefing.CODE_TAGS)
    missing = sorted(code for code in codes if ic.item_of_code(code) is None)
    assert missing == [], f"這些事件碼對不到清單的任何一項：{missing}"
    assert ic.item_of_code(240) == "main_bearing" and ic.item_of_code(417) == "transformer"
    assert ic.item_of_code(439) == "converter_cooling" and ic.item_of_code(223) == "yaw"
    assert ic.item_of_code(None) is None and ic.item_of_code(99999) is None


def test_checklist_tags_and_components_are_valid() -> None:
    vocabulary = json.loads((PROJECT_ROOT / "shared" / "data" / "rag_assistant_vocabulary.json").read_text("utf-8"))
    components = {c["id"] for c in vocabulary["components"]}
    pack = {column.tag.id for column in sp.pack_columns()}
    ids = [item.id for item in ic.CHECKLIST]
    assert len(ids) == len(set(ids))
    for item in ic.CHECKLIST:
        assert set(item.tags) <= pack, f"{item.id}：有給不出去的量測 {set(item.tags) - pack}"
        assert set(item.components) <= components, item.id
    covered = {c for item in ic.CHECKLIST for c in item.components}
    scenario_components = {s.component for s in FAULT_SCENARIOS.values()}
    assert scenario_components <= covered, f"這些部件的故障對不到清單：{scenario_components - covered}"


def test_the_card_logic_does_not_read_fault_scenarios() -> None:
    """清單與做卡的程式不讀故障情境（盲測守則）；部件只在評分時用。"""
    source = inspect.getsource(ic)
    assert "FAULT_SCENARIOS" not in source and "key_signals" not in source
    card_source = inspect.getsource(briefing.build_inspection_card)
    assert "FAULT_SCENARIOS" not in card_source and "key_signals" not in card_source
    assert "components" not in card_source, "部件（評分用）不進卡片"


# ── 2. 排序 ───────────────────────────────────────────────────────────────


def test_a_healthy_turbine_keeps_the_planned_order(farm: Farm) -> None:
    farm.drive_slow(360)
    stored = _inspect(farm, "WT002")
    card = stored["card"]
    assert _order(card) == [item.id for item in ic.CHECKLIST], "沒有證據：維持原訂順序"
    assert card["checklist"]["order_changed"] is False
    assert "no_evidence" in card["data_quality"]["flags"] and card["data_quality"]["degraded"] is False
    score = briefing.score_any_card(card, stored["answer"])
    assert score["has_fault"] is False and score["false_attention"] is False


def test_a_latent_fault_moves_its_item_up(farm: Farm) -> None:
    """變壓器過熱嚴重度到頂、還沒到警報門檻：沒有任何事件，只有溫度比同場高——那一項往前、標注意。"""
    farm.drive_slow(360)
    farm.inject("transformer_overheat", "WT003", severity=1.0)
    farm.drive_slow(720)
    assert not any(e["source"] == "plc" for e in farm.broker.storage.query_events("WT003", limit=200)), \
        "測試前提：沒有警報"
    stored = _inspect(farm, "WT003")
    card = stored["card"]
    assert _order(card)[0] == "transformer"
    entry = _entry(card, "transformer")
    assert entry["attention"] is True and entry["default_position"] == 2 and entry["position"] == 1
    assert entry["evidence"][0]["type"] == "signal" and entry["evidence"][0]["deviation"] == "high"
    assert [e["id"] for e in card["checklist"]["items"] if e["attention"]] == ["transformer"], "其他項目不標注意"
    score = briefing.score_any_card(card, stored["answer"])
    assert score["moved_up"] is True and score["flagged"] is True
    assert score["fault_items"][0]["item"] == "transformer"


def test_alarms_and_open_work_orders_count_as_evidence(farm: Farm) -> None:
    """有警報的劣化（定子溫度感測器漂移送 264）與未結案的故障維修工單，都讓那一項往前。"""
    farm.drive_slow(360)
    farm.inject("stator_temp_sensor_drift", "WT004", severity=1.0)
    for _ in range(60):
        farm.drive_slow(10)
        if any(e.get("payload", {}).get("code") == 264 for e in farm.broker.storage.query_events("WT004", limit=200)):
            break
    farm.repo.create(farm_id=FARM, turbine_id="WT004", type=WorkOrderType.CORRECTIVE, title="x", description="",
                     source_alarm_code="240")
    stored = _inspect(farm, "WT004")
    card = stored["card"]
    generator, bearing = _entry(card, "generator"), _entry(card, "main_bearing")
    assert any(e["type"] == "events" and e["code"] == 264 for e in generator["evidence"])
    assert any(e["type"] == "open_work_order" and e["source_alarm_code"] == 240 for e in bearing["evidence"])
    assert generator["position"] < generator["default_position"] or generator["position"] <= 2
    assert {generator["id"], bearing["id"]} <= set(_order(card)[:3])
    assert briefing.score_any_card(card, stored["answer"])["flagged"] is True


# ── 3. 可觀測、建單、評分端點 ─────────────────────────────────────────────


def test_the_card_carries_only_observable_data(farm: Farm) -> None:
    farm.drive_slow(60)
    farm.inject("transformer_overheat", "WT003", severity=1.0)
    farm.drive_slow(60)
    stored = _inspect(farm, "WT003")
    blob = json.dumps(stored["card"], ensure_ascii=False)
    for leak in ("transformer_overheat", "答案", "在這台", "scenario", "severity", "component"):
        assert leak not in blob, leak
    assert stored["card"]["card_version"] == briefing.CARD_VERSION == "1.2"
    names = {column.name for column in sp.pack_columns()}
    assert {item["name"] for item in stored["card"]["signals"]["items"]} <= names


def test_preventive_orders_get_the_same_card_and_the_score_endpoint_dispatches(farm: Farm, monkeypatch) -> None:
    monkeypatch.setattr(ops, "get_broker", lambda: farm.broker)
    farm.drive_slow(60)
    order = farm.repo.create(farm_id=FARM, turbine_id="WT001", type=WorkOrderType.PREVENTIVE, title="保養",
                             description="")
    farm.drive(10)
    body = asyncio.run(ops.work_order_briefing(str(order.id), farm_id=FARM))
    assert body["card"]["kind"] == "routine_inspection" and "answer" not in body
    scored = asyncio.run(ops.work_order_briefing_score(str(order.id), farm_id=FARM))
    assert set(scored["score"]) >= {"moved_up", "flagged", "false_attention", "fault_items"}
