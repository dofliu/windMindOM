"""情境標準答案（ground truth）紀錄器（WMOM-20261021-04，EPIC-DS Phase 2）。

批次情境生成時，紀錄器同時收三種輸入：

1. 故障注入（``generate_bulk`` 的 ``on_fault_injected``）→ 每次注入一個 case，``onset_ts``＝注入時刻
2. 可觀測事件（``on_events``）→ 該 case 預期碼第一次出現的時刻（``first_alarm_ts``）、實際出現的預期碼、
   同機組出現的其他警報 / 跳機碼；沒有任何 case 的預期碼能解釋的警報 / 跳機 / 資訊事件另列
   ``unattributed_events``（例：健康機組的偶發跳機、切出風速 I201、故障連帶的其他碼）
3. 故障造成的 PLC 跳機（``on_fault_tripped``）→ ``trip_ts`` / ``trip_code``
4. 風場層級事件（``on_farm_event``，WMOM-20261021-08-b）：電網擾動、風向快速變化

nuisance case（WMOM-20261021-08-b，DEC-20261023-02）：不是機組故障、卻會讓機組送警報 / 跳機的事件也有答案——

- 注入的 nuisance 情境（``category="nuisance"`` 的 ``FaultScenario``，例：Pt100 接觸不良）同故障一樣每次注入一個 case
- 風場事件期間（含結束後 ``NUISANCE_WINDOW_GRACE_S``）各機組出現、沒被故障 case 認領的該事件碼 → 每台機組
  一個 nuisance case
- 其餘沒被認領的警報 / 跳機 / 資訊事件，發生在沒有故障 case 的機組上（例：暴風切出 I201、極端氣溫）→ 依機組
  以 ``NUISANCE_WINDOW_GRACE_S`` 為間隔分群，每群一個 ``environment`` nuisance case

nuisance case 不算故障：``healthy_turbines``＝沒有故障 case 的機組（可能有 nuisance case）。

產出的 dict 即介面合約 v1 的 ``ground_truth.json``（``docs/integration/rag_assistant_data_contract_v1.md``），
存進 ``scenario_ground_truth`` 表，與可觀測的讀值 / 事件分開（盲測）。根因、元件、處置等答案欄位來自 ``FaultScenario`` 的 metadata；
手冊條目來自 Z72 警報目錄（``shared/alarm_codes.py``）——Z72 手冊對變頻器 / 變壓器事件只寫
「See [ABB]」，這類條目標 ``see_abb`` 並在 case 的 ``manual_coverage`` 註明。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

from .bulk_events import BulkEvent
from .farm_events import FARM_EVENT_KINDS, FarmEvent
from .physics import plc_protection  # noqa: F401  匯入時把 repo root 補進 sys.path（shared/ 才找得到）
from .physics.fault_engine import FAULT_SCENARIOS, ActiveFault, FaultScenario, TestPlanStep
from .time_utils import iso_utc, parse_iso

from shared.alarm_codes import get_alarm  # noqa: E402

# 介面合約版本：v1 定稿見 docs/integration/rag_assistant_data_contract_v1.md（WMOM-20261021-09）。
# 加欄位升次版本（1.x），改名 / 刪欄位 / 改語意升主版本
CONTRACT_VERSION = "1.5"
MANUAL_DOC = "Z72 User Manual"
MANUAL_SECTION = "Appendix C"
_ABB_MARKER = "See [ABB]"
# 會出現在 first_alarm / observed 的事件種類（警報成立＝A 級、跳機＝T1 / T2）；解除、復位、資訊不算
_ALARM_KINDS = frozenset({"alarm_raised", "trip"})
# 沒被 case 解釋時要列進 unattributed_events 的事件種類（警報、跳機與 I 類資訊，例：切出風速 201）
_UNATTRIBUTED_KINDS = frozenset({"alarm_raised", "trip", "info"})
# 故障 case 的類別（其餘是 nuisance）：healthy_turbines 與評分的故障指標只看這兩類
FAULT_CATEGORIES = frozenset({"real_fault", "sensor_fault"})
# nuisance case 的時間窗在最後一個相關事件（風場事件則取事件結束與最後一個事件較晚者）之後多留這麼久：
# 機組自動重啟、助手的判斷可能稍晚；環境性 case 也以此為分群間隔
NUISANCE_WINDOW_GRACE_S = 1800.0
# 自動重啟被封鎖（A039）：跟在 nuisance 跳機之後，歸給同一個 nuisance case
RESTART_BLOCKED_CODE = 39
# 環境性 nuisance case 的成因說明：依出現的事件碼挑（沒列的碼只用通用說明）
_ENVIRONMENT_HINTS: Dict[int, Tuple[str, str]] = {
    201: ("風速超過切出風速（暴風）：正常的保護停機，風速回落後自動回切",
          "wind speed above cut-out (storm): a normal protective stop; the turbine cuts back in once the wind drops"),
    256: ("機艙控制櫃溫度超出範圍（極端氣溫）",
          "nacelle cabinet temperature out of range (extreme ambient temperature)"),
    273: ("機艙溫度超出範圍（極端氣溫）", "nacelle temperature out of range (extreme ambient temperature)"),
    RESTART_BLOCKED_CODE: ("同一種停機一小時內反覆發生，自動重啟被封鎖、要操作員復位",
                           "the same stop repeated within an hour, so auto restart is blocked until an operator reset"),
}
# 環境性 case 依事件碼列的關鍵訊號
_ENVIRONMENT_SIGNALS: Dict[int, Tuple[str, ...]] = {
    201: ("WMET_WSpeedNac",),
    256: ("WNAC_NacCabTmp", "WMET_TmpOutside"),
    273: ("WNAC_NacTmp", "WMET_TmpOutside"),
}

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
        "nuisance_cause": scenario.nuisance_cause,
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


def _nuisance_answer(*, fault_id: str, nuisance_cause: str, origin: str, difficulty: str,
                     name_zh: str, name_en: str, root_cause_zh: str, root_cause_en: str,
                     codes: Sequence[int], actions_zh: Sequence[str], actions_en: Sequence[str],
                     key_signals: Sequence[str], notes_zh: Sequence[str] = (),
                     notes_en: Sequence[str] = ()) -> Dict[str, JsonValue]:
    """風場事件 / 環境性 nuisance case 的答案欄位（欄位與 ``scenario_answer`` 相同）。

    這類 case 沒有預先定好的事件碼：``expected_alarm_codes`` 是該機組實際出現的碼（依出現順序）。

    Returns:
        答案欄位；``component`` 為 None（不是元件問題）。
    """
    refs = manual_refs(codes)
    sequence: List[JsonValue] = []
    for code in codes:
        alarm = get_alarm(code)
        sequence.append({"code": code, "level": alarm.level, "text": alarm.text})
    refs_json: List[JsonValue] = list(refs)
    return {
        "category": "nuisance",
        "nuisance_cause": nuisance_cause,
        "origin": origin,
        "difficulty": difficulty,
        "fault_id": fault_id,
        "fault_name_en": name_en,
        "fault_name_zh": name_zh,
        "component": None,
        "root_cause": root_cause_zh,
        "root_cause_en": root_cause_en,
        "expected_alarm_codes": list(codes),
        "expected_alarm_sequence": sequence,
        "manual_refs": refs_json,
        "manual_coverage": manual_coverage(refs),
        "expected_actions": list(actions_zh),
        "expected_actions_en": list(actions_en),
        "key_signals": list(key_signals),
        "simulation_notes": list(notes_zh),
        "simulation_notes_en": list(notes_en),
    }


def farm_event_answer(kind_id: str, codes: Sequence[int]) -> Dict[str, JsonValue]:
    """風場事件造成的 nuisance case 答案欄位。

    Args:
        kind_id: ``FARM_EVENT_KINDS`` 的 ID。
        codes: 該機組實際出現的事件碼（依出現順序）。

    Returns:
        答案欄位。
    """
    kind = FARM_EVENT_KINDS[kind_id]
    return _nuisance_answer(
        fault_id=kind.id, nuisance_cause=kind.nuisance_cause, origin=kind.origin, difficulty=kind.difficulty,
        name_zh=kind.name_zh, name_en=kind.name_en, root_cause_zh=kind.root_cause_zh,
        root_cause_en=kind.root_cause_en, codes=codes, actions_zh=kind.expected_actions_zh,
        actions_en=kind.expected_actions_en, key_signals=kind.key_signals,
        notes_zh=kind.simulation_notes_zh, notes_en=kind.simulation_notes_en,
    )


def environment_answer(codes: Sequence[int]) -> Dict[str, JsonValue]:
    """環境性停機 / 警報（沒有注入故障的機組、也不是風場事件）的 nuisance case 答案欄位。

    Args:
        codes: 這群事件的事件碼（依出現順序）。

    Returns:
        答案欄位；成因說明依事件碼挑 ``_ENVIRONMENT_HINTS``。
    """
    hints = [_ENVIRONMENT_HINTS[c] for c in codes if c in _ENVIRONMENT_HINTS]
    root_zh = "環境 / 運轉條件造成的停機或警報，不是機組故障（這台機組在這段時間沒有故障）"
    root_en = "A stop or alarm caused by environmental / operating conditions, not a turbine fault (the turbine has no fault during this period)"
    if hints:
        root_zh += "：" + "；".join(h[0] for h in hints)
        root_en += ": " + "; ".join(h[1] for h in hints)
    signals = list(dict.fromkeys(tag for c in codes for tag in _ENVIRONMENT_SIGNALS.get(c, ())))
    return _nuisance_answer(
        fault_id="environment", nuisance_cause="environment", origin="environmental", difficulty="easy",
        name_zh="環境性停機 / 警報", name_en="Environmental stop / alarm",
        root_cause_zh=root_zh + "。", root_cause_en=root_en + ".", codes=codes,
        actions_zh=(
            "比對環境量（風速、氣溫）與事件時間：條件超出設計範圍時的停機 / 警報是正常保護",
            "條件恢復後機組自動重啟；自動重啟被封鎖（A039）時由操作員復位（手冊）",
            "同類停機在這個場址經常發生時，檢查散熱 / 通風等是否足以應付場址氣候",
        ),
        actions_en=(
            "Compare the environmental values (wind speed, temperature) with the event times: a stop / alarm while conditions are outside the design range is normal protection.",
            "The turbine restarts automatically once conditions recover; if auto restart is blocked (A039), reset by an operator (manual).",
            "If such stops are frequent at the site, check that cooling / ventilation can cope with the site climate.",
        ),
        key_signals=signals,
        notes_zh=("模擬器自己產生的環境性事件（沒有注入）；標準答案依「沒有故障 case 的機組、沒被其他 case 認領」歸成這類。",),
        notes_en=("Environmental events arising from the simulation itself (nothing injected); the answer key groups events on turbines without a fault case that no other case claims into this kind.",),
    )


@dataclass
class _Observed:
    """一筆沒被故障 / 注入的 nuisance case 認領的事件（``build`` 時再歸給風場事件或環境性 case）。"""

    ts: datetime
    turbine_id: str
    kind: str
    code: int
    record: Dict[str, JsonValue]
    case_id: Optional[str] = None


@dataclass
class _FarmEventRecord:
    """一個已開始的風場事件。"""

    event: FarmEvent
    start: datetime
    end: datetime


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

    @property
    def is_fault(self) -> bool:
        """是故障（不是注入的 nuisance）。"""
        return self.scenario.category in FAULT_CATEGORIES


class GroundTruthRecorder:
    """批次情境的標準答案紀錄器（純計算，不碰 storage）。

    Args:
        turbine_ids: 情境內全部機組（未注入故障者列為 ``healthy_turbines``）。
    """

    def __init__(self, turbine_ids: Sequence[str]) -> None:
        self._turbine_ids = list(turbine_ids)
        self._cases: List[_Case] = []
        self._unclaimed: List[_Observed] = []
        self._farm_events: List[_FarmEventRecord] = []

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

    def on_farm_event(self, event: FarmEvent, start: datetime, end: datetime) -> None:
        """風場事件開始（``generate_bulk`` 的 ``on_farm_event``）：``build`` 時據此標 nuisance case。

        Args:
            event: 風場事件。
            start: 開始的模擬時刻。
            end: 結束的模擬時刻。
        """
        self._farm_events.append(_FarmEventRecord(event=event, start=start, end=end))

    def on_events(self, events: Sequence[BulkEvent]) -> None:
        """可觀測事件歸到同機組、已開始的 case（``generate_bulk`` 的 ``on_events``）。

        預期碼 → ``first_alarm`` / ``observed_alarm_codes``；其他 A / T 碼 → ``other_observed_codes``
        （例：定子過熱連帶軸承警報、同時發生的環境性跳機）。注入的 nuisance case 另外認領自己跳機之後的
        A039（自動重啟被封鎖），並以第一次跳機為 ``trip``（nuisance 不鎖機組，``on_fault_tripped`` 不會來）。
        沒有任何 case 認領的警報 / 跳機 / 資訊事件留到 ``build``：歸給風場事件或環境性 nuisance case，
        都不是的列進 ``unattributed_events``——評分端才知道 RAG 面對的每一筆事件有沒有答案。

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
                        if not case.is_fault and event.kind == "trip" and case.trip is None:
                            case.trip = (event.timestamp, plc.code)
                    else:
                        if not case.is_fault and plc.code == RESTART_BLOCKED_CODE and case.trip is not None:
                            claimed = True
                        if plc.code not in case.other_codes:
                            case.other_codes.append(plc.code)
            if not claimed and event.kind in _UNATTRIBUTED_KINDS:
                self._unclaimed.append(_Observed(
                    ts=event.timestamp,
                    turbine_id=event.turbine_id,
                    kind=event.kind,
                    code=plc.code,
                    record={
                        "ts": iso_utc(event.timestamp),
                        "turbine_id": event.turbine_id,
                        "kind": event.kind,
                        "code": plc.code,
                        "level": plc.level,
                        "text": plc.text,
                    },
                ))

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
        cases: List[JsonValue] = []
        for case in self._cases:
            answer = scenario_answer(case.scenario)
            cases.append({
                "case_id": case.case_id,
                "turbine_id": case.turbine_id,
                **answer,
                "onset_ts": iso_utc(case.onset),
                "window_end_ts": None,
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
                "farm_event_id": None,
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
                "window_end_ts": None,
                "first_alarm_ts": None,
                "first_alarm_code": None,
                "trip_ts": None,
                "trip_code": fault.trip_code,
                "observed_alarm_codes": [],
                "other_observed_codes": [],
                "injection": None,
                "farm_event_id": None,
                "final_severity": round(fault.severity, 4),
                "superseded": False,
                "pre_existing": True,
            })
        sim_end_dt = parse_iso(sim_end) if sim_end else None
        farm_events = self._farm_event_cases(cases, sim_end_dt)
        # 故障開始時刻（pre_existing 從情境一開始就在）：之後的事件是故障連帶，不歸環境性 case
        fault_onsets: Dict[str, Optional[datetime]] = {}
        for case in self._cases:
            if case.is_fault:
                prev = fault_onsets.get(case.turbine_id, case.onset)
                fault_onsets[case.turbine_id] = None if prev is None else min(prev, case.onset)
        for fault in pre_existing:
            if FAULT_SCENARIOS[fault.scenario_id].category in FAULT_CATEGORIES:
                fault_onsets[fault.turbine_id] = None
        self._environment_cases(cases, fault_onsets, sim_end_dt)
        faulty = set(fault_onsets)
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
            # 沒有故障 case 的機組（可能有 nuisance case，例：暴風切出 I201、電網擾動）
            "healthy_turbines": [t for t in self._turbine_ids if t not in faulty],
            "cases": cases,
            "farm_events": farm_events,
            # 沒有任何 case 解釋的事件（例：故障連帶的其他碼）
            "unattributed_events": [o.record for o in self._unclaimed if o.case_id is None],
        }

    def _farm_event_cases(self, cases: List[JsonValue], sim_end: Optional[datetime]) -> List[JsonValue]:
        """風場事件 → 每台有反應的機組一個 nuisance case（就地加進 ``cases``）。

        事件期間到結束後 ``NUISANCE_WINDOW_GRACE_S``、沒被認領的該事件碼（與跟在後面的 A039）歸給它。

        Returns:
            標準答案的 ``farm_events`` 清單。
        """
        out: List[JsonValue] = []
        grace = timedelta(seconds=NUISANCE_WINDOW_GRACE_S)
        for index, rec in enumerate(self._farm_events, start=1):
            kind = FARM_EVENT_KINDS[rec.event.kind]
            event_id = f"E{index:02d}"
            codes = set(kind.event_codes)
            case_ids: List[JsonValue] = []
            for turbine_id in self._turbine_ids:
                mine = [o for o in self._unclaimed
                        if o.case_id is None and o.turbine_id == turbine_id and rec.start <= o.ts <= rec.end + grace
                        and o.code in codes]
                if not mine:
                    continue
                last = max(o.ts for o in mine)
                blocked = [o for o in self._unclaimed
                           if o.case_id is None and o.turbine_id == turbine_id and o.code == RESTART_BLOCKED_CODE
                           and mine[0].ts <= o.ts <= last + grace]
                case_id = f"C{len(cases) + 1:03d}"
                for o in mine + blocked:
                    o.case_id = case_id
                window_end = max(rec.end, max(o.ts for o in mine + blocked)) + grace
                cases.append(self._nuisance_case(
                    case_id, turbine_id, farm_event_answer(kind.id, _codes_in_order(mine + blocked)),
                    rec.start, window_end, sim_end, mine + blocked, farm_event_id=event_id))
                case_ids.append(case_id)
            out.append({
                "event_id": event_id,
                "kind": kind.id,
                "name_zh": kind.name_zh,
                "name_en": kind.name_en,
                "nuisance_cause": kind.nuisance_cause,
                "start_ts": iso_utc(rec.start),
                "end_ts": iso_utc(rec.end),
                "magnitude": rec.event.magnitude,
                "magnitude_unit": kind.magnitude_unit,
                "case_ids": case_ids,
            })
        return out

    def _environment_cases(self, cases: List[JsonValue], fault_onsets: Dict[str, Optional[datetime]],
                           sim_end: Optional[datetime]) -> None:
        """其餘沒被認領、發生在故障開始前（或沒有故障）的機組事件 → 環境性 nuisance case（就地加進 ``cases``）。

        同機組相隔不超過 ``NUISANCE_WINDOW_GRACE_S`` 的事件算同一群。

        Args:
            cases: 標準答案的 case 清單（就地加入）。
            fault_onsets: 有故障 case 的機組 → 最早的故障開始時刻（None＝從情境一開始就在）。
            sim_end: 情境結束（時間窗不超過它）。
        """
        grace = timedelta(seconds=NUISANCE_WINDOW_GRACE_S)
        for turbine_id in self._turbine_ids:
            limit: Optional[datetime] = None
            if turbine_id in fault_onsets:
                limit = fault_onsets[turbine_id]
                if limit is None:
                    continue  # 故障從情境一開始就在（pre_existing）
            pending = [o for o in self._unclaimed
                       if o.case_id is None and o.turbine_id == turbine_id and (limit is None or o.ts < limit)]
            groups: List[List[_Observed]] = []
            for o in sorted(pending, key=lambda x: x.ts):
                if groups and o.ts - groups[-1][-1].ts <= grace:
                    groups[-1].append(o)
                else:
                    groups.append([o])
            for group in groups:
                case_id = f"C{len(cases) + 1:03d}"
                for o in group:
                    o.case_id = case_id
                window_end = group[-1].ts + grace
                if limit is not None:
                    window_end = min(window_end, limit)
                cases.append(self._nuisance_case(
                    case_id, turbine_id, environment_answer(_codes_in_order(group)),
                    group[0].ts, window_end, sim_end, group))

    @staticmethod
    def _nuisance_case(case_id: str, turbine_id: str, answer: Dict[str, JsonValue], onset: datetime,
                       window_end: datetime, sim_end: Optional[datetime], observed: Sequence[_Observed],
                       farm_event_id: Optional[str] = None) -> Dict[str, JsonValue]:
        """風場事件 / 環境性 nuisance case 的完整欄位。"""
        if sim_end is not None:
            window_end = min(window_end, sim_end)
        ordered = sorted(observed, key=lambda o: o.ts)
        alarms = [o for o in ordered if o.kind in _ALARM_KINDS]
        trips = [o for o in ordered if o.kind == "trip"]
        return {
            "case_id": case_id,
            "turbine_id": turbine_id,
            **answer,
            "onset_ts": iso_utc(onset),
            "window_end_ts": iso_utc(window_end),
            "first_alarm_ts": iso_utc(alarms[0].ts) if alarms else None,
            "first_alarm_code": alarms[0].code if alarms else None,
            "trip_ts": iso_utc(trips[0].ts) if trips else None,
            "trip_code": trips[0].code if trips else None,
            "observed_alarm_codes": _codes_in_order(ordered),
            "other_observed_codes": [],
            "injection": None,
            "farm_event_id": farm_event_id,
            "final_severity": None,
            "superseded": False,
            "pre_existing": False,
        }

    def _active_cases(self, turbine_id: str) -> List[_Case]:
        """該機組尚未被取代的 case。"""
        return [c for c in self._cases if c.turbine_id == turbine_id and not c.superseded]


def _codes_in_order(observed: Sequence[_Observed]) -> List[int]:
    """事件碼依第一次出現的順序、去重。"""
    return list(dict.fromkeys(o.code for o in sorted(observed, key=lambda o: o.ts)))
