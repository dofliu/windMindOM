"""故障情境警報碼對齊真實 Z72 目錄（WMOM-20261021-02，EPIC-DS Phase 1a）。

RAG 維修助手是拿警報碼去查 Z72 手冊；模擬器送出的碼若與真實清單不符，RAG 答對反而
會被判錯（DEC-20261021-01）。本檔確保 `FAULT_SCENARIOS` 每個警報：

1. 事件碼存在於 `shared/data/z72_alarm_catalog.json`
2. ``type`` 等於目錄等級、``desc`` 等於目錄文字（不另寫自創描述）
3. 不使用 I（資訊）類事件當故障警報
4. 每個情境至少一個跳機碼
5. 每個預期碼都是 PLC 保護層（WMOM-20261021-03-b）真的能送出的碼——``alarm_codes`` 是
   ground truth 的預期碼，若 PLC 送不出來，資料裡就永遠不會出現

（WMOM-20261021-03-b 前的「嚴重度門檻慣例」測試已移除：警報 / 跳機改由 PLC 依量測值判定。）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import pytest

from shared.alarm_codes import find_alarm
from simulator.physics.fault_engine import FAULT_SCENARIOS, FaultScenario
from simulator.physics.plc_protection import raisable_codes
from simulator.physics.turbine_physics import TurbineSpec

SCENARIOS: List[FaultScenario] = list(FAULT_SCENARIOS.values())


ALL_ALARMS = [(s, a) for s in SCENARIOS for a in s.alarm_codes]
ALL_ALARM_IDS = [f"{s.id}:{a['code']}" for s, a in ALL_ALARMS]


@pytest.mark.parametrize(("scenario", "alarm"), ALL_ALARMS, ids=ALL_ALARM_IDS)
def test_alarm_code_exists_in_real_catalog(scenario: FaultScenario, alarm: Dict) -> None:
    assert find_alarm(alarm["code"]) is not None, (
        f"{scenario.id} 用了 Z72 目錄沒有的事件碼 {alarm['code']}"
    )


@pytest.mark.parametrize(("scenario", "alarm"), ALL_ALARMS, ids=ALL_ALARM_IDS)
def test_alarm_level_and_text_match_catalog(scenario: FaultScenario, alarm: Dict) -> None:
    real = find_alarm(alarm["code"])
    assert real is not None
    assert alarm["type"] == real.level
    assert alarm["desc"] == real.text


@pytest.mark.parametrize(("scenario", "alarm"), ALL_ALARMS, ids=ALL_ALARM_IDS)
def test_no_information_events_used_as_fault_alarms(scenario: FaultScenario, alarm: Dict) -> None:
    assert alarm["type"] in ("A", "T1", "T2")


@pytest.mark.parametrize(("scenario", "alarm"), ALL_ALARMS, ids=ALL_ALARM_IDS)
def test_expected_code_can_be_raised_by_plc(scenario: FaultScenario, alarm: Dict) -> None:
    assert alarm["code"] in raisable_codes(TurbineSpec()), (
        f"{scenario.id} 預期碼 {alarm['code']} 沒有 PLC 規則或保護對應，資料裡永遠不會出現"
    )


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_every_scenario_has_a_trip_code(scenario: FaultScenario) -> None:
    assert any(a["type"] in ("T1", "T2") for a in scenario.alarm_codes)


def test_baseline_knowledge_corpus_uses_same_codes_as_scenarios() -> None:
    """knowledge baseline 語料（`_meta` 宣告對齊 FAULT_SCENARIOS）不可與情境碼脫節。"""
    corpus_path = PROJECT_ROOT / "modules" / "knowledge" / "data" / "baseline_corpus_z72.json"
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    corpus_codes = {code for chunk in corpus["chunks"] for code in chunk["alarm_codes"]}
    scenario_codes = {a["code"] for s in SCENARIOS for a in s.alarm_codes}
    assert corpus_codes == scenario_codes
