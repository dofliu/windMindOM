"""故障情境警報碼對齊真實 Z72 目錄（WMOM-20261021-02，EPIC-DS Phase 1a）。

RAG 維修助手是拿警報碼去查 Z72 手冊；模擬器送出的碼若與真實清單不符，RAG 答對反而
會被判錯（DEC-20261021-01）。本檔確保 `FAULT_SCENARIOS` 每個警報：

1. 事件碼存在於 `shared/data/z72_alarm_catalog.json`
2. ``type`` 等於目錄等級、``desc`` 等於目錄文字（不另寫自創描述）
3. 不使用 I（資訊）類事件當故障警報
4. 門檻慣例：A 級在跳機前出現（< auto_trip_severity）；T1 / T2 跳機碼在跳機當下出現
   （== auto_trip_severity）——不會出現「跳機碼已觸發但機組仍在發電」的資料
5. 每個情境至少一個跳機碼（每個情境都會在 auto_trip_severity 跳機）

另以 FaultEngine 驗證門檻慣例在實際推進時成立。
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
from simulator.physics.fault_engine import FAULT_SCENARIOS, FaultEngine, FaultScenario

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
def test_threshold_convention(scenario: FaultScenario, alarm: Dict) -> None:
    if alarm["type"] == "A":
        assert 0.0 < alarm["threshold"] < scenario.auto_trip_severity
    else:
        assert alarm["threshold"] == scenario.auto_trip_severity


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_every_scenario_has_a_trip_code(scenario: FaultScenario) -> None:
    assert any(a["type"] in ("T1", "T2") for a in scenario.alarm_codes)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_trip_codes_raised_exactly_when_turbine_trips(scenario: FaultScenario) -> None:
    """引擎推進：跳機前只有 A 級警報；跳機那一步才出現 T1 / T2。"""
    engine = FaultEngine()
    assert engine.inject(scenario.id, "WT001", severity_rate=0.01)
    seen_trip_before_tripped = False
    for _ in range(200):
        engine.step(dt=1.0)
        fault = engine.active_faults[0]
        trip_alarms = [a for a in fault.active_alarms if a["type"] in ("T1", "T2")]
        if fault.tripped:
            assert trip_alarms, f"{scenario.id} 跳機時沒有任何跳機碼"
            break
        if trip_alarms:
            seen_trip_before_tripped = True
    else:
        pytest.fail(f"{scenario.id} 在 200 步內沒有跳機")
    assert not seen_trip_before_tripped


def test_baseline_knowledge_corpus_uses_same_codes_as_scenarios() -> None:
    """knowledge baseline 語料（`_meta` 宣告對齊 FAULT_SCENARIOS）不可與情境碼脫節。"""
    corpus_path = PROJECT_ROOT / "modules" / "knowledge" / "data" / "baseline_corpus_z72.json"
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    corpus_codes = {code for chunk in corpus["chunks"] for code in chunk["alarm_codes"]}
    scenario_codes = {a["code"] for s in SCENARIOS for a in s.alarm_codes}
    assert corpus_codes == scenario_codes
