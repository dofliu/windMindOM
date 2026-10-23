"""情境標準答案（ground truth）紀錄器（WMOM-20261021-04，EPIC-DS Phase 2）。

批次情境生成時，紀錄器同時收三種輸入：

1. 故障注入（``generate_bulk`` 的 ``on_fault_injected``）→ 每次注入一個 case，``onset_ts``＝注入時刻
2. 可觀測事件（``on_events``）→ 該 case 預期碼第一次出現的時刻（``first_alarm_ts``）、實際出現的預期碼、
   同機組出現的其他警報 / 跳機碼；沒有任何 case 的預期碼能解釋的警報 / 跳機 / 資訊事件另列
   ``unattributed_events``（例：健康機組的偶發跳機、切出風速 I201、故障連帶的其他碼）
3. 故障造成的 PLC 跳機（``on_fault_tripped``）→ ``trip_ts`` / ``trip_code``

產出的 dict 即介面合約 v1 的 ``ground_truth.json``（``docs/integration/rag_assistant_data_contract_v1.md``），
存進 ``scenario_ground_truth`` 表，與可觀測的讀值 / 事件分開（盲測）。根因、元件、處置等答案欄位來自 ``FaultScenario`` 的 metadata；
手冊條目來自 Z72 警報目錄（``shared/alarm_codes.py``）——Z72 手冊對變頻器 / 變壓器事件只寫
「See [ABB]」，這類條目標 ``see_abb`` 並在 case 的 ``manual_coverage`` 註明。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

from .bulk_events import BulkEvent
from .physics import plc_protection  # noqa: F401  匯入時把 repo root 補進 sys.path（shared/ 才找得到）
from .physics.fault_engine import FAULT_SCENARIOS, ActiveFault, FaultScenario, TestPlanStep
from .time_utils import iso_utc

from shared.alarm_codes import get_alarm  # noqa: E402

# 介面合約版本：v1 定稿見 docs/integration/rag_assistant_data_contract_v1.md（WMOM-20261021-09）。
# 加欄位升次版本（1.x），改名 / 刪欄位 / 改語意升主版本
CONTRACT_VERSION = "1.4"
MANUAL_DOC = "Z72 User Manual"
MANUAL_SECTION = "Appendix C"
_ABB_MARKER = "See [ABB]"
# 會出現在 first_alarm / observed 的事件種類（警報成立＝A 級、跳機＝T1 / T2）；解除、復位、資訊不算
_ALARM_KINDS = frozenset({"alarm_raised", "trip"})
# 沒被 case 解釋時要列進 unattributed_events 的事件種類（警報、跳機與 I 類資訊，例：切出風速 201）
_UNATTRIBUTED_KINDS = frozenset({"alarm_raised", "trip", "info"})

JsonValue = Union[str, int, float, bool, None, List["JsonValue"], Dict[str, "JsonValue"]]


def manual_refs(codes: Iterable[int]) -> List[Dict[str, JsonValue]]:
    """事件碼 → 手冊 Appendix C 條目（含原因、處置提示、頁碼）。

    Args:
        codes: Z72 事件碼。

    Returns:
        每碼一筆條目；Z72 手冊只寫「See [ABB]」者 ``see_abb`` 為 True（答案要到 ABB 變頻器手冊找）。
    """
    refs: List[Dict[str, JsonValue]] = []
    for code in codes:
        alarm = get_alarm(code)
        refs.append({
            "doc": MANUAL_DOC,
            "section": MANUAL_SECTION,
            "event_code": code,
            "event_id": alarm.event_id,
            "level": alarm.level,
            "text": alarm.text,
            "page": alarm.manual_page,
            "cause": alarm.cause,
            "rectification": alarm.rectification,
            "see_abb": _ABB_MARKER in (alarm.cause or "") or _ABB_MARKER in (alarm.rectification or ""),
        })
    return refs


def manual_coverage(refs: Sequence[Dict[str, JsonValue]]) -> str:
    """Z72 手冊能涵蓋多少答案。

    Args:
        refs: ``manual_refs`` 的結果。

    Returns:
        ``z72_manual``（全部有 Z72 手冊內容）、``abb_manual``（全部只寫 See [ABB]）或 ``mixed``。
    """
    abb = [bool(r["see_abb"]) for r in refs]
    if abb and all(abb):
        return "abb_manual"
    return "mixed" if any(abb) else "z72_manual"


def scenario_answer(scenario: FaultScenario) -> Dict[str, JsonValue]:
    """故障情境的靜態答案欄位（不含時間；與實際發生的事件無關）。

    Args:
        scenario: 故障情境定義。

    Returns:
        ``category``、``fault_id``、``component``、``root_cause``、``expected_alarm_codes``、
        ``manual_refs``、``expected_actions`` 等欄位。
    """
    refs = manual_refs(a["code"] for a in scenario.alarm_codes)
    refs_json: List[JsonValue] = list(refs)
    sequence: List[JsonValue] = [
        {"code": a["code"], "level": a["type"], "text": a["desc"]} for a in scenario.alarm_codes
    ]
    return {
        "category": scenario.category,
        "origin": scenario.origin,
        "difficulty": scenario.difficulty,
        "fault_id": scenario.id,
        "fault_name_en": scenario.name_en,
        "fault_name_zh": scenario.name_zh,
        "component": scenario.component,
        "root_cause": scenario.root_cause_zh,
        "root_cause_en": scenario.root_cause_en,
        "expected_alarm_codes": [a["code"] for a in scenario.alarm_codes],
        "expected_alarm_sequence": sequence,
        "manual_refs": refs_json,
        "manual_coverage": manual_coverage(refs),
        "expected_actions": list(scenario.expected_actions_zh),
        "expected_actions_en": list(scenario.expected_actions_en),
        "key_signals": list(scenario.key_signals),
        "simulation_notes": list(scenario.simulation_notes_zh),
        "simulation_notes_en": list(scenario.simulation_notes_en),
    }


@dataclass
class _Case:
    """紀錄中的一個 case（一次故障注入）。"""

    case_id: str
    turbine_id: str
    scenario: FaultScenario
    onset: datetime
    offset_seconds: float
    severity_rate: float
    initial_severity: float
    first_alarm: Optional[Tuple[datetime, int]] = None
    trip: Optional[Tuple[datetime, int]] = None
    observed_codes: List[int] = field(default_factory=list)
    other_codes: List[int] = field(default_factory=list)
    superseded: bool = False

    @property
    def expected_codes(self) -> Tuple[int, ...]:
        """本 case 的預期事件碼。"""
        return tuple(a["code"] for a in self.scenario.alarm_codes)


class GroundTruthRecorder:
    """批次情境的標準答案紀錄器（純計算，不碰 storage）。

    Args:
        turbine_ids: 情境內全部機組（未注入故障者列為 ``healthy_turbines``）。
    """

    def __init__(self, turbine_ids: Sequence[str]) -> None:
        self._turbine_ids = list(turbine_ids)
        self._cases: List[_Case] = []
        self._unattributed: List[Dict[str, JsonValue]] = []

    def on_fault_injected(self, step: TestPlanStep, sim_time: datetime) -> None:
        """一次故障注入成為一個 case（``generate_bulk`` 的 ``on_fault_injected``）。

        同機組同情境再次注入時，``FaultEngine`` 以新實例取代舊的：舊 case 標 ``superseded``，之後的事件
        只歸給新 case。

        Args:
            step: 排程步驟。
            sim_time: 注入的模擬時刻。
        """
        scenario = FAULT_SCENARIOS.get(step.scenario_id)
        if scenario is None:
            return
        for case in self._active_cases(step.turbine_id):
            if case.scenario.id == step.scenario_id:
                case.superseded = True
        self._cases.append(_Case(
            case_id=f"C{len(self._cases) + 1:03d}",
            turbine_id=step.turbine_id,
            scenario=scenario,
            onset=sim_time,
            offset_seconds=float(step.offset_seconds),
            severity_rate=float(step.severity_rate),
            initial_severity=float(step.initial_severity),
        ))

    def on_fault_tripped(self, turbine_id: str, scenario_id: str, code: int, sim_time: datetime) -> None:
        """故障造成 PLC 跳機（``generate_bulk`` 的 ``on_fault_tripped``）。

        Args:
            turbine_id: 機組 ID。
            scenario_id: 故障情境 ID。
            code: 觸發的跳機碼。
            sim_time: 跳機的模擬時刻。
        """
        for case in self._active_cases(turbine_id):
            if case.scenario.id == scenario_id and case.trip is None:
                case.trip = (sim_time, code)

    def on_events(self, events: Sequence[BulkEvent]) -> None:
        """可觀測事件歸到同機組、已開始的 case（``generate_bulk`` 的 ``on_events``）。

        預期碼 → ``first_alarm`` / ``observed_alarm_codes``；其他 A / T 碼 → ``other_observed_codes``
        （例：定子過熱連帶軸承警報、同時發生的環境性跳機）。沒有任何 case 以預期碼認領的警報 / 跳機 /
        資訊事件列進 ``unattributed_events``：評分端才知道 RAG 面對的每一筆事件有沒有答案。

        Args:
            events: 可觀測事件。
        """
        for event in events:
            plc = event.plc_event
            if plc is None:
                continue
            claimed = False
            if event.kind in _ALARM_KINDS:
                for case in self._active_cases(event.turbine_id):
                    if event.timestamp < case.onset:
                        continue
                    if plc.code in case.expected_codes:
                        claimed = True
                        if case.first_alarm is None:
                            case.first_alarm = (event.timestamp, plc.code)
                        if plc.code not in case.observed_codes:
                            case.observed_codes.append(plc.code)
                    elif plc.code not in case.other_codes:
                        case.other_codes.append(plc.code)
            if not claimed and event.kind in _UNATTRIBUTED_KINDS:
                self._unattributed.append({
                    "ts": iso_utc(event.timestamp),
                    "turbine_id": event.turbine_id,
                    "kind": event.kind,
                    "code": plc.code,
                    "level": plc.level,
                    "text": plc.text,
                })

    def build(self, *, scenario_id: Optional[int], scenario_name: Optional[str],
              site_timezone: Optional[str], sim_start: Optional[str], sim_end: Optional[str],
              final_faults: Sequence[ActiveFault] = ()) -> Dict[str, JsonValue]:
        """組出標準答案 dict（設計文件 §5.1 ``ground_truth.json``）。

        Args:
            scenario_id: 情境 session id。
            scenario_name: 情境名稱。
            site_timezone: 風場時區（日夜 / 季節循環所用）。
            sim_start: 情境模擬時間窗起點（ISO）。
            sim_end: 情境模擬時間窗終點（ISO）。
            final_faults: 生成結束時仍在的故障（取最終嚴重度）。

        Returns:
            可 JSON 序列化的標準答案。
        """
        final_severity = {(f.turbine_id, f.scenario_id): f.severity for f in final_faults}
        recorded = {(c.turbine_id, c.scenario.id) for c in self._cases if not c.superseded}
        # 不是本次注入、卻在結束時仍存在的故障（例：生成前就殘留的故障）：不能靜默略過，列成 onset 未知的 case
        pre_existing = [
            f for f in final_faults
            if (f.turbine_id, f.scenario_id) not in recorded and f.scenario_id in FAULT_SCENARIOS
        ]
        faulty = {c.turbine_id for c in self._cases} | {f.turbine_id for f in pre_existing}
        cases: List[JsonValue] = []
        for case in self._cases:
            answer = scenario_answer(case.scenario)
            cases.append({
                "case_id": case.case_id,
                "turbine_id": case.turbine_id,
                **answer,
                "onset_ts": iso_utc(case.onset),
                "first_alarm_ts": iso_utc(case.first_alarm[0]) if case.first_alarm else None,
                "first_alarm_code": case.first_alarm[1] if case.first_alarm else None,
                "trip_ts": iso_utc(case.trip[0]) if case.trip else None,
                "trip_code": case.trip[1] if case.trip else None,
                "observed_alarm_codes": list(case.observed_codes),
                "other_observed_codes": list(case.other_codes),
                "injection": {
                    "offset_seconds": case.offset_seconds,
                    "severity_rate": case.severity_rate,
                    "initial_severity": case.initial_severity,
                },
                "final_severity": (
                    None if case.superseded
                    else round(final_severity.get((case.turbine_id, case.scenario.id), 0.0), 4)
                ),
                "superseded": case.superseded,
                "pre_existing": False,
            })
        for fault in pre_existing:
            cases.append({
                "case_id": f"C{len(cases) + 1:03d}",
                "turbine_id": fault.turbine_id,
                **scenario_answer(FAULT_SCENARIOS[fault.scenario_id]),
                "onset_ts": None,
                "first_alarm_ts": None,
                "first_alarm_code": None,
                "trip_ts": None,
                "trip_code": fault.trip_code,
                "observed_alarm_codes": [],
                "other_observed_codes": [],
                "injection": None,
                "final_severity": round(fault.severity, 4),
                "superseded": False,
                "pre_existing": True,
            })
        return {
            "contract_version": CONTRACT_VERSION,
            "kind": "scenario_ground_truth",
            "scenario_id": scenario_id,
            "scenario_name": scenario_name,
            "turbine_model": "Z72",
            "site_timezone": site_timezone,
            "sim_start": sim_start,
            "sim_end": sim_end,
            "generated_at": iso_utc(),
            "turbines": list(self._turbine_ids),
            # 未注入故障的機組（仍可能有環境性停機，例：切出風速 I201）
            "healthy_turbines": [t for t in self._turbine_ids if t not in faulty],
            "cases": cases,
            "unattributed_events": list(self._unattributed),
        }

    def _active_cases(self, turbine_id: str) -> List[_Case]:
        """該機組尚未被取代的 case。"""
        return [c for c in self._cases if c.turbine_id == turbine_id and not c.superseded]
