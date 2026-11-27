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
    assert stored["card"]["card_version"] == briefing.CARD_VERSION == "1.3"
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


# ── 4. code review 修正 ──────────────────────────────────────────────────


def test_a_turbine_that_was_mostly_stopped_is_not_compared_with_the_farm(farm: Farm) -> None:
    """停機 / 維修中的機組轉速、溫度本來就和發電中的不一樣：量測不當證據，不會整排都標注意。"""
    farm.drive_slow(120)
    farm.model("WT002").cmd_service(True)
    farm.drive_slow(600)
    stored = _inspect(farm, "WT002")
    card = stored["card"]
    assert card["signals"]["own_producing_fraction"] < 0.5
    assert "own_not_producing" in card["data_quality"]["flags"] and card["data_quality"]["degraded"] is True
    assert not any(e["type"] == "signal" for item in card["checklist"]["items"] for e in item["evidence"])
    assert briefing.score_any_card(card, stored["answer"])["false_attention"] is False


def test_open_corrective_orders_count_even_beyond_the_listed_ten(farm: Farm) -> None:
    from datetime import datetime, timezone

    farm.drive_slow(60)
    old = farm.repo.create(farm_id=FARM, turbine_id="WT001", type=WorkOrderType.CORRECTIVE, title="x",
                           description="", source_alarm_code="417")
    inspection = farm.repo.create(farm_id=FARM, turbine_id="WT001", type=WorkOrderType.INSPECTION, title="定檢",
                                  description="")
    clock = farm.broker.live_clock() or datetime.now(timezone.utc)
    kwargs = dict(storage=farm.broker.storage, history=farm.broker.live_history, work_order=inspection,
                  turbine_id="WT001", turbines=list(farm.broker.simulator.turbines), cutoff=clock)
    without = briefing.build_inspection_card(**kwargs, past_work_orders=[])
    assert not _entry(without, "transformer")["attention"], "只看列出來的工單：漏掉"
    card = briefing.build_inspection_card(**kwargs, past_work_orders=[], open_work_orders=[old, inspection])
    assert _entry(card, "transformer")["evidence"] == [
        {"type": "open_work_order", "business_key": old.business_key, "source_alarm_code": 417,
         "status": old.status.value}]


def test_scoring_uses_the_items_reached_by_the_expected_codes() -> None:
    """超速的部件是變槳，但 351 依量測歸在轉速量測；原訂排第一的項目沒辦法再往前。"""
    def item(item_id: str, position: int, default: int, attention: bool) -> Dict[str, object]:
        return {"id": item_id, "position": position, "default_position": default, "attention": attention}

    card = {"checklist": {"items": [item("rotor_speed", 1, 8, True), item("converter_cooling", 2, 1, False),
                                    item("pitch", 10, 10, False)]}}
    overspeed = {"faults": [{"scenario_id": "generator_overspeed", "component": "pitch_control_system",
                             "category": "real_fault", "severity": 0.4, "tripped": False}], "has_fault": True}
    score = briefing.score_inspection_card(card, overspeed)
    assert score["fault_items"][0]["items"] == ["pitch", "rotor_speed"]
    assert score["fault_items"][0]["item"] == "rotor_speed" and score["flagged"] is True and score["moved_up"] is True
    cooling = {"faults": [{"scenario_id": "converter_cooling_pump_wear", "component": "converter_cooling_system",
                           "category": "real_fault"}], "has_fault": True}
    assert briefing.score_inspection_card(card, cooling)["moved_up"] is None, "原訂第一：不能再往前"


def test_a_truncated_window_is_flagged(farm: Farm, monkeypatch) -> None:
    farm.drive_slow(60)
    monkeypatch.setattr(briefing, "_WINDOW_LIMIT", 20)
    stored = _inspect(farm, "WT001")
    assert stored["card"]["signals"]["truncated"] is True
    assert "signals_truncated" in stored["card"]["data_quality"]["flags"]


# ── 5. 誤報修正（WMOM-20261127-04，卡片 1.3）─────────────────────────────

from datetime import datetime, timedelta, timezone  # noqa: E402

import numpy as np  # noqa: E402

from server.live_archive import LiveReading  # noqa: E402
from simulator.time_utils import iso_utc  # noqa: E402

_CUT = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
_TEMP, _VANE = "WGEN_GnBrgTmp1", "WYAW_YwVn1AlgnAvg5s"


class _FakeHistory:
    """6 小時、每 10 秒一筆的讀值：每台機組給一個函式（距截止點幾秒 → {tag: 值}）。"""

    def __init__(self, turbines: Dict[str, object]) -> None:
        self.turbines = turbines

    def readings(self, turbine_id, tag_ids, after_id=0, start=None, end=None, limit=1000):  # noqa: ANN001, ANN201
        make = self.turbines[turbine_id]
        rows = []
        for back in range(6 * 3600, -1, -10):
            moment = _CUT - timedelta(seconds=back)
            stamp = iso_utc(moment)
            if (start and stamp < start) or (end and stamp >= end):
                continue
            values = make(back)  # type: ignore[operator]
            values.setdefault(briefing._STATE_TAG, 6.0)
            rows.append(LiveReading(id=len(rows) + 1, timestamp=stamp, turbine_id=turbine_id,
                                    values=np.array([values.get(t, np.nan) for t in tag_ids], dtype=float)))
        return rows[:limit]


def _healthy(power: float, offset: float = 0.0, vane: float = 0.0):  # noqa: ANN202
    """軸承溫度隨功率：20 °C ＋ 每 100 kW 1 °C（加上這台機組自己的小差異）。"""
    return lambda back: {briefing.POWER_TAG: power, briefing.WIND_TAG: 4.0 + power / 250.0,
                         _TEMP: 20.0 + power / 100.0 + offset, _VANE: vane}


def _peers() -> Dict[str, object]:
    return {f"P{i}": _healthy(900.0 + 50.0 * i, offset=0.15 * ((i % 3) - 1), vane=0.4 * ((i % 3) - 1))
            for i in range(8)}


def _items(target, normalize: bool = True) -> Dict[str, Dict[str, object]]:  # noqa: ANN001
    turbines = {"T": target, **_peers()}
    tags = [_TEMP, _VANE, briefing.WIND_TAG, briefing.POWER_TAG]
    items, _info = briefing._signal_items(_FakeHistory(turbines), "T", list(turbines), tags, (), _CUT,
                                          window=briefing.INSPECTION_SIGNAL_WINDOW,
                                          recent=briefing.INSPECTION_RECENT_WINDOW,
                                          baseline_lag=briefing.INSPECTION_BASELINE_LAG, normalize=normalize)
    pack = briefing._pack_tags()
    return {tag: next(i for i in items if i["name"] == pack[tag].name) for tag in tags}


def test_an_upwind_turbine_is_compared_at_its_own_operating_point() -> None:
    """上風處的機組功率高、溫度跟著高：扣掉運轉點之後是正常的（故障出勤卡照舊直接比）。"""
    upwind = _healthy(1400.0)   # 同場 900–1250 kW：在範圍外
    items = _items(upwind)
    assert items[_TEMP]["deviation"] == "normal" and items[briefing.WIND_TAG]["deviation"] == "normal"
    assert items[_TEMP]["expected_mean"] == pytest.approx(34.0, abs=0.3)
    assert items[_TEMP]["normalized_by"] == briefing._pack_tags()[briefing.POWER_TAG].name
    further = _healthy(1800.0)
    assert _items(further)[_TEMP]["deviation"] == "normal"
    assert _items(further, normalize=False)[_TEMP]["deviation"] == "high", "對照：直接比是偏高"
    # 真的偏熱：直接比、扣掉之後比都偏高
    hot = lambda back: {**_healthy(1100.0)(back), _TEMP: 20.0 + 11.0 + 8.0}  # noqa: E731
    assert _items(hot)[_TEMP]["deviation"] == "high"


def test_a_fit_that_disagrees_with_the_plain_comparison_is_not_evidence() -> None:
    """扣掉運轉點之後偏低、直接比卻相近（機組少、配適不穩時會這樣）：不算偏離。"""
    odd = lambda back: {**_healthy(1300.0)(back), _TEMP: 20.0 + 10.75}  # noqa: E731  直接比在同場中間
    items = _items(odd)
    assert items[_TEMP]["deviation"] == "normal"


def test_only_a_lasting_deviation_counts() -> None:
    """只有最後一小時偏離的是一時的：6 小時與最後 1 小時都偏同一邊才算。"""
    late = lambda back: {**_healthy(1100.0)(back), _TEMP: 31.0 + (8.0 if back < 3600 else 0.0)}  # noqa: E731
    assert _items(late)[_TEMP]["deviation"] == "normal"
    assert _items(late, normalize=False)[_TEMP]["deviation"] == "high", "對照：故障出勤卡看最近一段"
    lasting = lambda back: {**_healthy(1100.0)(back), _TEMP: 39.0}  # noqa: E731
    assert _items(lasting)[_TEMP]["deviation"] == "high"


def test_wind_vane_alignment_inside_the_yaw_dead_band_is_normal() -> None:
    from simulator.physics.yaw_model import YawModel

    assert briefing.YAW_DEAD_BAND_DEG == YawModel().dead_band, "和偏航控制的死區一致"
    inside = _healthy(1100.0, vane=-9.0)
    assert _items(inside)[_VANE]["deviation"] == "normal"
    assert _items(inside, normalize=False)[_VANE]["deviation"] == "low", "對照：直接比是偏低"
    assert _items(_healthy(1100.0, vane=-20.0))[_VANE]["deviation"] == "low"


def _plc(code: int, kind: str = "alarm_raised"):  # noqa: ANN202
    from simulator.physics.plc_protection import PlcEvent

    level = "T1" if kind == "trip" else "A"
    return PlcEvent(sim_time=1.0, kind=kind, code=code, level=level, text="x", plc_tag=None,
                    event_id=f"{level}_{code:03d}", value=None, setpoint=None, source="signal")


def _events_only(monkeypatch) -> None:  # noqa: ANN001
    """只看事件與工單：測試風場只跑十幾分鐘，各台溫度還在暖機，讀值的比較不穩（讀值的比法由上面的測試涵蓋）。"""
    original = briefing._signal_items
    monkeypatch.setattr(briefing, "_signal_items", lambda *a, **k: ([], original(*a, **k)[1]))


def test_events_before_a_finished_repair_are_listed_but_not_counted(farm: Farm, monkeypatch) -> None:
    _events_only(monkeypatch)
    farm.drive_slow(60)
    farm.broker._record_plc_event("WT004", _plc(264))
    farm.broker._record_plc_event("WT004", _plc(422))
    repair = farm.repo.create(farm_id=FARM, turbine_id="WT004", type=WorkOrderType.CORRECTIVE, title="x",
                              description="", source_alarm_code="264")
    farm.start(repair)
    farm.drive_slow(6)
    farm.finish(repair)
    farm.drive_slow(30)
    card = _inspect(farm, "WT004")["card"]
    generator, cooling = _entry(card, "generator"), _entry(card, "converter_cooling")
    (handled,) = [e for e in generator["evidence"] if e["type"] == "events"]
    assert handled["count"] == 1 and handled["counted"] == 0 and handled["handled_by"] == [repair.business_key]
    assert generator["attention"] is False, "修好之前的事件不算分；完工等簽核的工單也不算未結案的證據"
    assert farm.repo.get(repair.id).status.value == "awaiting_signoff"
    assert cooling["attention"] is True, "別的項目的事件照算（工單修的是 264 那一項）"
    # 修好之後又發生：照算
    farm.broker._record_plc_event("WT004", _plc(264))
    farm.drive_slow(6)
    again = _entry(_inspect(farm, "WT004")["card"], "generator")
    (entry,) = [e for e in again["evidence"] if e["type"] == "events"]
    assert entry["count"] == 2 and entry["counted"] == 1 and again["attention"] is True


def test_a_finished_inspection_handles_every_earlier_event(farm: Farm, monkeypatch) -> None:
    _events_only(monkeypatch)
    farm.drive_slow(60)
    farm.broker._record_plc_event("WT005", _plc(264))
    done = farm.repo.create(farm_id=FARM, turbine_id="WT005", type=WorkOrderType.INSPECTION, title="定檢",
                            description="")
    farm.drive(10)
    farm.start(done)
    farm.drive_slow(6)
    farm.finish(done)
    farm.drive_slow(30)
    card = _inspect(farm, "WT005")["card"]
    assert not any(item["attention"] for item in card["checklist"]["items"])
    assert "no_evidence" in card["data_quality"]["flags"]


def test_no_evidence_means_nothing_was_counted(farm: Farm, monkeypatch) -> None:
    """有證據的項目剛好排第一：順序沒變，但不是「沒有證據」。"""
    _events_only(monkeypatch)
    farm.drive_slow(60)
    farm.broker._record_plc_event("WT003", _plc(423))
    card = _inspect(farm, "WT003")["card"]
    assert _order(card)[0] == "converter_cooling" and _entry(card, "converter_cooling")["attention"] is True
    assert card["checklist"]["order_changed"] is False
    assert "no_evidence" not in card["data_quality"]["flags"]
