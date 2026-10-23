"""RAG 維修助手評分程式（介面合約 v1 §8，WMOM-20261021-09）。

只用 Python 標準函式庫：學生把整個 starter kit 目錄複製走就能用。

用法::

    python score.py --answers answers/ --predictions my_predictions.jsonl
    python score.py --answers answers/z72-starter-01.ground_truth.json --predictions p.jsonl --json report.json
    python score.py --answers z72-scenario-00012/ --predictions p.jsonl     # 評分端版資料包目錄（內含 ground_truth.json）

``--answers`` 可給檔案或目錄：目錄下的 ``*.ground_truth.json``、``ground_truth.json``，以及下一層子目錄的
``ground_truth.json``（評分端版資料包）。``--predictions`` 是助手輸出的 JSONL，每行一筆診斷（格式見合約 §6）。
只評 ``--answers`` 裡有的資料包，其他 pack_id 的預測略過（報告會列出筆數）。

評分規則（合約 §8）：
- 「故障診斷」＝category 為 ``real_fault`` / ``sensor_fault`` 的預測；依機組與時間對到**故障** case，對不到的是誤報。
- 每個故障 case 以**最後一筆**對到的診斷評元件、元件群組、類別與手冊引用（助手可以邊看邊修正）。
- 時效看「**最後一段連續正確**」的起點：最後一筆診斷元件正確時，往前找到連續都正確的第一筆；
  它早於第一個預期警報就是早期預警。中途猜錯的元件另計誤診，狂猜不會換到早期預警。
- 干擾（v1.5，WMOM-20261021-08-b）：``nuisance`` 預測依機組與時間對到 nuisance case（電網擾動、風向快速變化、
  感測器接點鬆動、環境性停機）＝認出干擾；在 nuisance case 時間窗內下故障診斷照樣是誤報（另計「把干擾當故障」）。
  對不到 nuisance case 的 ``nuisance`` 預測另列（落空），報干擾判定的準確率——每台每分鐘都報干擾拿得到辨識率，
  但準確率會很低。``nuisance`` 預測不會撤回之前的故障診斷。誤報率＝誤報次數 ÷ 沒有故障的機組時數（每 100 機組小時）。
- 各項指標分開列，不合成總分。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

KIT_DIR = Path(__file__).resolve().parent
FAULT_CATEGORIES = ("real_fault", "sensor_fault")
PREDICTION_CATEGORIES = ("real_fault", "sensor_fault", "nuisance")
# 手冊引用只看前 10 個（MRR@10）：列一長串事件碼不會換到分數
MAX_MANUAL_REFS = 10
# 同一機組、同一元件的誤報相隔不到 30 分鐘算同一次（輸出頻率不影響誤報次數）
FALSE_ALARM_EPISODE_GAP_S = 1800.0

JsonObject = Dict[str, object]


def parse_ts(value: str) -> datetime:
    """ISO 時間字串（``Z`` 或 ``+00:00``）→ UTC datetime。

    Args:
        value: 時間字串；不帶時區者視為 UTC。

    Returns:
        tz-aware UTC datetime。
    """
    ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)


def load_vocabulary(path: Path = KIT_DIR / "vocabulary.json") -> Dict[str, str]:
    """元件 → 元件群組。

    Args:
        path: ``vocabulary.json``。

    Returns:
        ``{component_id: group_id}``。
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    return {c["id"]: c["group"] for c in data["components"]}


# ── 輸入 ─────────────────────────────────────────────────────────────────────


@dataclass
class Prediction:
    """助手的一筆診斷（合約 §6）。

    Attributes:
        line: 在 predictions.jsonl 的行號（同一時刻的診斷依行號排先後）。
        pack_id: 資料包 ID。
        turbine_id: 機組。
        ts: 做出判斷的模擬時間（UTC）。
        category: ``real_fault`` / ``sensor_fault`` / ``nuisance``。
        component: 元件 ID（``nuisance`` 可為 None）。
        manual_refs: 去重後、依相關程度排序的事件碼。
    """

    line: int
    pack_id: str
    turbine_id: str
    ts: datetime
    category: str
    component: Optional[str]
    manual_refs: List[int]


@dataclass
class Case:
    """標準答案的一個 case（只取評分用得到的欄位）。

    Attributes:
        pack_id: 資料包 ID。
        case_id: case ID。
        turbine_id: 機組。
        category: 答案類別（``real_fault`` / ``sensor_fault`` / ``nuisance``）。
        component: 答案元件（風場事件 / 環境性 nuisance case 為 None）。
        expected_codes: 預期事件碼（手冊引用的正解）。
        window_start: 時間窗起點（故障開始；同機組同故障再注入時取最早那次）。
        window_end: 時間窗終點（``window_end_ts``；沒有時為情境結束）。
        first_alarm: 第一個預期警報（同上，取最早那次）。
        timing_scored: 是否評延遲 / 早期預警（``pre_existing`` case 不知道何時開始，不評）。
        nuisance_cause: nuisance case 的成因（故障為 None）。
    """

    pack_id: str
    case_id: str
    turbine_id: str
    category: str
    component: Optional[str]
    expected_codes: List[int]
    window_start: datetime
    window_end: Optional[datetime]
    first_alarm: Optional[datetime]
    timing_scored: bool = True
    nuisance_cause: Optional[str] = None

    @property
    def is_fault(self) -> bool:
        """是故障 case（不是 nuisance）。"""
        return self.category in FAULT_CATEGORIES


def read_predictions(lines: Iterable[str], components: Dict[str, str]) -> Tuple[List[Prediction], List[JsonObject]]:
    """讀助手輸出的 JSONL。

    Args:
        lines: 檔案的每一行。
        components: ``load_vocabulary`` 的結果。

    Returns:
        ``(有效的預測, 無效的行與原因)``。無效：不是 JSON 物件、缺必填欄位、``ts`` 不是 ISO 時間、
        類別不在清單、故障診斷的元件不在詞彙內（多半是拼錯）、``manual_refs`` 不是整數清單。
    """
    valid: List[Prediction] = []
    invalid: List[JsonObject] = []
    for number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
            if not isinstance(item, dict):
                raise ValueError("不是 JSON 物件")
            for key in ("pack_id", "turbine_id", "ts", "category"):
                if not isinstance(item.get(key), str) or not item[key]:
                    raise ValueError(f"缺少 {key!r} 或不是字串")
            if item["category"] not in PREDICTION_CATEGORIES:
                raise ValueError(f"category 必須是 {' / '.join(PREDICTION_CATEGORIES)}")
            component = item.get("component")
            if item["category"] in FAULT_CATEGORIES and not (isinstance(component, str) and component in components):
                raise ValueError(f"故障診斷的 component 必須是 vocabulary.json 的元件 ID（收到 {component!r}）")
            refs = item.get("manual_refs", [])
            if not isinstance(refs, list) or not all(isinstance(r, int) and not isinstance(r, bool) for r in refs):
                raise ValueError("manual_refs 必須是事件碼（整數）的清單")
            valid.append(Prediction(
                line=number, pack_id=item["pack_id"], turbine_id=item["turbine_id"], ts=parse_ts(item["ts"]),
                category=item["category"], component=component if isinstance(component, str) else None,
                manual_refs=list(dict.fromkeys(refs)),
            ))
        except (ValueError, TypeError, OverflowError, RecursionError) as exc:
            # RecursionError：極深的巢狀 JSON；OverflowError：超出範圍的時間——一行壞掉不能讓整份評分中斷
            invalid.append({"line": number, "reason": str(exc) or type(exc).__name__})
    return valid, invalid


def read_cases(ground_truth: JsonObject) -> List[Case]:
    """標準答案 → 要評分的 case。

    同機組同故障再注入時，舊 case 標 ``superseded``：同一個故障其實從第一次注入就在，所以把舊 case 併進
    取代它的 case——時間窗從最早那次注入起算、第一個預期警報取最早的。``pre_existing`` case 不知道何時
    開始（``onset_ts`` 為 null），時間窗從 ``sim_start`` 起，不評延遲與早期預警。

    Args:
        ground_truth: 一個資料包的 ``ground_truth.json``。

    Returns:
        case 清單（不含 superseded）。
    """
    pack_id = str(ground_truth["pack_id"])
    sim_start = parse_ts(str(ground_truth["sim_start"]))
    sim_end = parse_ts(str(ground_truth["sim_end"])) if ground_truth.get("sim_end") else None
    raw_cases = ground_truth.get("cases") or []
    assert isinstance(raw_cases, list)
    superseded: Dict[Tuple[str, str], List[JsonObject]] = {}
    cases = []
    for item in raw_cases:
        key = (str(item["turbine_id"]), str(item.get("fault_id", "")))
        if item.get("superseded"):
            superseded.setdefault(key, []).append(item)
            continue
        chain = superseded.pop(key, []) + [item]
        onsets = [parse_ts(str(c["onset_ts"])) for c in chain if c.get("onset_ts")]
        alarms = [parse_ts(str(c["first_alarm_ts"])) for c in chain if c.get("first_alarm_ts")]
        cases.append(Case(
            pack_id=pack_id,
            case_id=item["case_id"],
            turbine_id=item["turbine_id"],
            category=item["category"],
            component=item.get("component"),
            expected_codes=list(item.get("expected_alarm_codes") or []),
            window_start=min(onsets) if onsets else sim_start,
            window_end=parse_ts(str(item["window_end_ts"])) if item.get("window_end_ts") else sim_end,
            first_alarm=min(alarms) if alarms else None,
            timing_scored=not item.get("pre_existing") and bool(onsets),
            nuisance_cause=item.get("nuisance_cause"),
        ))
    return cases


def healthy_turbine_hours(ground_truth: JsonObject, cases: Sequence[Case]) -> Optional[float]:
    """沒有故障的機組時數：每台機組的情境長度扣掉故障 case 時間窗（故障開始前的時間也算）。

    誤報只會發生在這段時間（故障時間窗內的故障診斷都對得到 case），所以拿它當誤報率的分母。

    Args:
        ground_truth: 一個資料包的 ``ground_truth.json``。
        cases: ``read_cases`` 的結果。

    Returns:
        小時數；答案沒有 ``sim_end`` 時為 None。
    """
    if not ground_truth.get("sim_end"):
        return None
    sim_start = parse_ts(str(ground_truth["sim_start"]))
    sim_end = parse_ts(str(ground_truth["sim_end"]))
    listed = ground_truth.get("turbines")
    turbines = listed if isinstance(listed, list) and listed else sorted({c.turbine_id for c in cases})
    total = 0.0
    for turbine in turbines:
        spans = sorted((max(c.window_start, sim_start), min(c.window_end or sim_end, sim_end))
                       for c in cases if c.is_fault and c.turbine_id == turbine)
        covered = 0.0
        cursor = sim_start
        for start, end in spans:
            start = max(start, cursor)
            if end > start:
                covered += (end - start).total_seconds()
                cursor = end
        total += (sim_end - sim_start).total_seconds() - covered
    return total / 3600.0


# ── 評分 ─────────────────────────────────────────────────────────────────────


@dataclass
class CaseResult:
    """一個 case 的評分。"""

    pack_id: str
    case_id: str
    turbine_id: str
    expected_component: str
    expected_category: str
    detected: bool = False
    predicted_component: Optional[str] = None
    predicted_category: Optional[str] = None
    component_correct: bool = False
    component_group_correct: bool = False
    category_correct: bool = False
    manual_hit_at_1: bool = False
    manual_hit_at_3: bool = False
    manual_reciprocal_rank: float = 0.0
    first_correct_ts: Optional[str] = None
    latency_s: Optional[float] = None
    early_warning: bool = False
    timing_scored: bool = True
    n_predictions: int = 0
    misdiagnosis_predictions: int = 0
    components_claimed: List[str] = field(default_factory=list)


@dataclass
class NuisanceCaseResult:
    """一個 nuisance case 的評分（v1.5）。

    Attributes:
        recognized: 時間窗內有 ``nuisance`` 預測（認出是干擾）。
        nuisance_predictions: 對到本 case 的 ``nuisance`` 預測筆數。
        fault_predictions: 時間窗內、沒對到故障 case 的故障診斷筆數（把干擾當故障，都算誤報）。
        first_recognized_ts: 第一筆對到的 ``nuisance`` 預測時間。
    """

    pack_id: str
    case_id: str
    turbine_id: str
    nuisance_cause: Optional[str]
    recognized: bool = False
    nuisance_predictions: int = 0
    fault_predictions: int = 0
    first_recognized_ts: Optional[str] = None


@dataclass
class Report:
    """全部資料包的評分結果（``cases`` 以下到 ``misdiagnosis_predictions`` 只算故障 case）。"""

    packs: List[str]
    cases: int
    detected: int
    detection_rate: float
    component_accuracy: float
    component_group_accuracy: float
    category_accuracy: float
    manual_hit_at_1: float
    manual_hit_at_3: float
    manual_mrr: float
    early_warnings: int
    latency_n: int
    latency_median_s: Optional[float]
    latency_mean_s: Optional[float]
    misdiagnosis_predictions: int
    false_alarm_predictions: int
    false_alarm_episodes: int
    false_alarm_turbines: int
    nuisance_predictions: int
    nuisance_during_fault: int
    ignored_predictions: int
    invalid_predictions: List[JsonObject] = field(default_factory=list)
    case_results: List[CaseResult] = field(default_factory=list)
    # v1.5（WMOM-20261021-08-b）：干擾與健康負樣本
    nuisance_cases: int = 0
    nuisance_recognized: int = 0
    nuisance_recognition_rate: float = 0.0
    nuisance_misread_as_fault: int = 0
    false_alarms_during_nuisance: int = 0
    nuisance_unmatched: int = 0
    nuisance_precision: Optional[float] = None
    healthy_turbine_hours: Optional[float] = None
    false_alarm_rate_per_100h: Optional[float] = None
    nuisance_case_results: List[NuisanceCaseResult] = field(default_factory=list)


def _in_window(case: Case, ts: datetime) -> bool:
    return case.window_start <= ts and (case.window_end is None or ts <= case.window_end)


def _match(prediction: Prediction, cases: Sequence[Case]) -> Optional[Case]:
    """一筆故障診斷對到哪個故障 case：同機組、時間在窗內；同時有多個時優先元件相同者，否則取最近發生的。"""
    candidates = [c for c in cases
                  if c.is_fault and c.turbine_id == prediction.turbine_id and _in_window(c, prediction.ts)]
    if not candidates:
        return None
    same = [c for c in candidates if c.component == prediction.component]
    return max(same or candidates, key=lambda c: c.window_start)


def _match_nuisance(prediction: Prediction, cases: Sequence[Case]) -> Optional[Case]:
    """一筆預測落在哪個 nuisance case 的時間窗：同機組、時間在窗內；同時有多個時取最近發生的。"""
    candidates = [c for c in cases
                  if not c.is_fault and c.turbine_id == prediction.turbine_id and _in_window(c, prediction.ts)]
    return max(candidates, key=lambda c: c.window_start) if candidates else None


def _rank_of(refs: Sequence[int], relevant: Iterable[int]) -> Optional[int]:
    wanted = set(relevant)
    for rank, code in enumerate(refs[:MAX_MANUAL_REFS], start=1):
        if code in wanted:
            return rank
    return None


def _episodes(false_alarms: Sequence[Prediction]) -> int:
    """誤報次數：同資料包、同機組、同元件，相隔不到 ``FALSE_ALARM_EPISODE_GAP_S`` 的算同一次。"""
    last: Dict[Tuple[str, str, Optional[str]], datetime] = {}
    episodes = 0
    for p in sorted(false_alarms, key=lambda p: (p.ts, p.line)):
        key = (p.pack_id, p.turbine_id, p.component)
        if key not in last or (p.ts - last[key]).total_seconds() > FALSE_ALARM_EPISODE_GAP_S:
            episodes += 1
        last[key] = p.ts
    return episodes


def _score_case(case: Case, claims: Sequence[Prediction], components: Dict[str, str]) -> CaseResult:
    """一個 case 的評分（``claims`` 已依時間、行號排序）。"""
    result = CaseResult(pack_id=case.pack_id, case_id=case.case_id, turbine_id=case.turbine_id,
                        expected_component=case.component or "", expected_category=case.category,
                        timing_scored=case.timing_scored, n_predictions=len(claims))
    if not claims:
        return result
    final = claims[-1]  # 最後一筆＝助手最後的判斷
    result.detected = True
    result.predicted_component = final.component
    result.predicted_category = final.category
    result.component_correct = final.component == case.component
    result.component_group_correct = (
        final.component is not None and components.get(final.component) == components.get(case.component or "")
    )
    result.category_correct = final.category == case.category
    rank = _rank_of(final.manual_refs, case.expected_codes)
    result.manual_hit_at_1 = rank == 1
    result.manual_hit_at_3 = rank is not None and rank <= 3
    result.manual_reciprocal_rank = 1.0 / rank if rank else 0.0
    result.misdiagnosis_predictions = sum(1 for p in claims if p.component != case.component)
    result.components_claimed = sorted({p.component for p in claims if p.component})
    if result.component_correct:
        # 最後一段連續正確的起點：之後再也沒改口，才算「那時就診斷出來了」
        start = len(claims) - 1
        while start > 0 and claims[start - 1].component == case.component:
            start -= 1
        first = claims[start].ts
        result.first_correct_ts = first.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        if case.timing_scored:
            if case.first_alarm is not None:
                result.latency_s = (first - case.first_alarm).total_seconds()
            result.early_warning = case.first_alarm is None or first < case.first_alarm
    return result


def score(ground_truths: Sequence[JsonObject], predictions: Sequence[Prediction],
          components: Dict[str, str], invalid: Sequence[JsonObject] = ()) -> Report:
    """評分。

    Args:
        ground_truths: 各資料包的標準答案（pack_id 不可重複）。
        predictions: ``read_predictions`` 的有效預測。
        components: 元件 → 群組。
        invalid: ``read_predictions`` 的無效行（原樣放進報告）。

    Returns:
        評分報告。

    Raises:
        ValueError: 同一個資料包的答案給了兩次。
    """
    packs = [str(gt["pack_id"]) for gt in ground_truths]
    if len(set(packs)) != len(packs):
        raise ValueError(f"標準答案的 pack_id 重複：{sorted(p for p in set(packs) if packs.count(p) > 1)}")
    cases_by_pack = {str(gt["pack_id"]): read_cases(gt) for gt in ground_truths}
    matched: Dict[Tuple[str, str], List[Prediction]] = {}
    nuisance_matched: Dict[Tuple[str, str], List[Prediction]] = {}
    faults_on_nuisance: Dict[Tuple[str, str], List[Prediction]] = {}
    false_alarms: List[Prediction] = []
    nuisance = nuisance_during_fault = nuisance_unmatched = ignored = 0
    for prediction in sorted(predictions, key=lambda p: (p.ts, p.line)):
        cases = cases_by_pack.get(prediction.pack_id)
        if cases is None:
            ignored += 1
            continue
        if prediction.category == "nuisance":
            # 對到 nuisance case＝認出干擾；不會撤回之前的故障診斷
            nuisance += 1
            if any(c.is_fault and c.turbine_id == prediction.turbine_id and _in_window(c, prediction.ts)
                   for c in cases):
                nuisance_during_fault += 1
            hit = _match_nuisance(prediction, cases)
            if hit is not None:
                nuisance_matched.setdefault((hit.pack_id, hit.case_id), []).append(prediction)
            else:
                nuisance_unmatched += 1  # 落空：那時那台機組沒有干擾
            continue
        case = _match(prediction, cases)
        if case is None:
            false_alarms.append(prediction)
            hit = _match_nuisance(prediction, cases)
            if hit is not None:
                faults_on_nuisance.setdefault((hit.pack_id, hit.case_id), []).append(prediction)
        else:
            matched.setdefault((case.pack_id, case.case_id), []).append(prediction)

    fault_cases = [case for pack_id in packs for case in cases_by_pack[pack_id] if case.is_fault]
    results = [_score_case(case, matched.get((case.pack_id, case.case_id), []), components) for case in fault_cases]
    n = len(results)
    nuisance_results = []
    for pack_id in packs:
        for case in cases_by_pack[pack_id]:
            if case.is_fault:
                continue
            hits = nuisance_matched.get((pack_id, case.case_id), [])
            nuisance_results.append(NuisanceCaseResult(
                pack_id=pack_id, case_id=case.case_id, turbine_id=case.turbine_id,
                nuisance_cause=case.nuisance_cause, recognized=bool(hits), nuisance_predictions=len(hits),
                fault_predictions=len(faults_on_nuisance.get((pack_id, case.case_id), [])),
                first_recognized_ts=hits[0].ts.strftime("%Y-%m-%dT%H:%M:%S.%fZ") if hits else None,
            ))
    hours = [healthy_turbine_hours(gt, cases_by_pack[str(gt["pack_id"])]) for gt in ground_truths]
    healthy_hours = None if any(h is None for h in hours) else sum(h for h in hours if h is not None)
    episodes = _episodes(false_alarms)
    n_nuisance = len(nuisance_results)
    recognized = sum(r.recognized for r in nuisance_results)

    def rate(values: Iterable[bool]) -> float:
        return sum(values) / n if n else 0.0

    latencies = [r.latency_s for r in results if r.latency_s is not None]
    # 手冊引用只評有預期事件碼的 case：沒有警報的故障（v1.6，例：偏航失準）沒有可引用的正解
    manual_cases = [r for r, c in zip(results, fault_cases) if c.expected_codes]
    n_manual = len(manual_cases)
    return Report(
        packs=packs,
        cases=n,
        detected=sum(r.detected for r in results),
        detection_rate=rate(r.detected for r in results),
        component_accuracy=rate(r.component_correct for r in results),
        component_group_accuracy=rate(r.component_group_correct for r in results),
        category_accuracy=rate(r.category_correct for r in results),
        manual_hit_at_1=sum(r.manual_hit_at_1 for r in manual_cases) / n_manual if n_manual else 0.0,
        manual_hit_at_3=sum(r.manual_hit_at_3 for r in manual_cases) / n_manual if n_manual else 0.0,
        manual_mrr=sum(r.manual_reciprocal_rank for r in manual_cases) / n_manual if n_manual else 0.0,
        early_warnings=sum(r.early_warning for r in results),
        latency_n=len(latencies),
        latency_median_s=statistics.median(latencies) if latencies else None,
        latency_mean_s=statistics.mean(latencies) if latencies else None,
        misdiagnosis_predictions=sum(r.misdiagnosis_predictions for r in results),
        false_alarm_predictions=len(false_alarms),
        false_alarm_episodes=episodes,
        false_alarm_turbines=len({(p.pack_id, p.turbine_id) for p in false_alarms}),
        nuisance_predictions=nuisance,
        nuisance_during_fault=nuisance_during_fault,
        ignored_predictions=ignored,
        invalid_predictions=list(invalid),
        case_results=results,
        nuisance_cases=n_nuisance,
        nuisance_recognized=recognized,
        nuisance_recognition_rate=recognized / n_nuisance if n_nuisance else 0.0,
        nuisance_misread_as_fault=sum(r.fault_predictions > 0 for r in nuisance_results),
        false_alarms_during_nuisance=sum(r.fault_predictions for r in nuisance_results),
        nuisance_unmatched=nuisance_unmatched,
        nuisance_precision=(nuisance - nuisance_unmatched) / nuisance if nuisance else None,
        healthy_turbine_hours=healthy_hours,
        false_alarm_rate_per_100h=(episodes / healthy_hours * 100.0) if healthy_hours else None,
        nuisance_case_results=nuisance_results,
    )


# ── CLI ──────────────────────────────────────────────────────────────────────


def load_answers(paths: Sequence[Path]) -> List[JsonObject]:
    """讀標準答案檔。

    Args:
        paths: 檔案，或目錄（讀其中的 ``*.ground_truth.json``、``ground_truth.json``，以及下一層子目錄的
            ``ground_truth.json``——評分端版資料包）。

    Returns:
        依路徑排序的標準答案。

    Raises:
        FileNotFoundError: 路徑不存在。
    """
    files: List[Path] = []
    for path in paths:
        if path.is_dir():
            found = set(path.glob("*.ground_truth.json")) | set(path.glob("ground_truth.json")) \
                | set(path.glob("*/ground_truth.json"))
            files.extend(sorted(found))
        elif path.exists():
            files.append(path)
        else:
            raise FileNotFoundError(path)
    return [json.loads(f.read_text(encoding="utf-8-sig")) for f in files]


def format_report(report: Report) -> str:
    """報告 → 給人看的文字（只用 ASCII 與中文標點：Windows cp950 主控台導向檔案也不會出錯）。"""
    def pct(value: float) -> str:
        return f"{value * 100:5.1f} %"

    def secs(value: Optional[float]) -> str:
        return "-" if value is None else f"{value:+.0f} s"

    def rate100(value: Optional[float]) -> str:
        return "-" if value is None else f"{value:.2f} 次 / 100 機組小時"

    def hours(value: Optional[float]) -> str:
        return "-" if value is None else f"{value:.1f} h"

    lines = [
        f"資料包：{', '.join(report.packs)}",
        f"case：{report.cases}　偵測到：{report.detected}（{pct(report.detection_rate).strip()}）"
        f"{'　（沒有故障 case：下面的故障比例都是 0）' if not report.cases else ''}",
        "",
        f"  元件正確率          {pct(report.component_accuracy)}",
        f"  元件群組正確率      {pct(report.component_group_accuracy)}",
        f"  類別正確率          {pct(report.category_accuracy)}",
        f"  手冊引用 hit@1      {pct(report.manual_hit_at_1)}",
        f"  手冊引用 hit@3      {pct(report.manual_hit_at_3)}",
        f"  手冊引用 MRR@{MAX_MANUAL_REFS}     {report.manual_mrr:7.3f}",
        f"  延遲（中位 / 平均） {secs(report.latency_median_s)} / {secs(report.latency_mean_s)}"
        f"（{report.latency_n} 個 case；相對第一個預期警報，負值＝提前）",
        f"  早期預警            {report.early_warnings} 個 case",
        f"  誤診（對到 case 但元件錯）{report.misdiagnosis_predictions} 筆",
        f"  誤報                {report.false_alarm_episodes} 次（{report.false_alarm_predictions} 筆、"
        f"{report.false_alarm_turbines} 台機組）",
        f"  誤報率              {rate100(report.false_alarm_rate_per_100h)}"
        f"（沒有故障的機組時數 {hours(report.healthy_turbine_hours)}）",
        "",
        f"干擾 case：{report.nuisance_cases}　認出：{report.nuisance_recognized}"
        f"（{pct(report.nuisance_recognition_rate).strip()}）",
        f"  把干擾當故障        {report.nuisance_misread_as_fault} 個 case"
        f"（{report.false_alarms_during_nuisance} 筆故障診斷，已算進誤報）",
        f"  干擾判定            {report.nuisance_predictions} 筆：落空 {report.nuisance_unmatched} 筆"
        f"（準確率 {'-' if report.nuisance_precision is None else pct(report.nuisance_precision).strip()}），"
        f"{report.nuisance_during_fault} 筆在故障期間（不會撤回故障診斷）",
    ]
    if report.ignored_predictions:
        lines.append(f"  略過（不在答案裡的資料包）{report.ignored_predictions} 筆")
    if report.invalid_predictions:
        lines.append(f"  格式錯誤 {len(report.invalid_predictions)} 行（不計分）：")
        lines += [f"    第 {i['line']} 行：{i['reason']}" for i in report.invalid_predictions[:20]]
        if len(report.invalid_predictions) > 20:
            lines.append(f"    …另 {len(report.invalid_predictions) - 20} 行（完整清單用 --json）")
    lines += ["", "case 明細（OK 元件對、~ 只有群組對、X 元件錯、- 沒偵測到）："]
    for r in report.case_results:
        mark = "OK" if r.component_correct else ("~" if r.component_group_correct else ("X" if r.detected else "-"))
        lines.append(
            f"  {mark:<2} {r.pack_id} {r.case_id} {r.turbine_id}  答案 {r.expected_component}/{r.expected_category}"
            f"  預測 {r.predicted_component}/{r.predicted_category}  延遲 {secs(r.latency_s)}"
            f"{'  早期預警' if r.early_warning else ''}"
            f"{f'  誤診 {r.misdiagnosis_predictions} 筆' if r.misdiagnosis_predictions else ''}"
        )
    if report.nuisance_case_results:
        lines += ["", "干擾 case 明細（OK 認出、X 沒認出；故障診斷＝把干擾當故障的筆數）："]
        for nr in report.nuisance_case_results:
            lines.append(
                f"  {'OK' if nr.recognized else 'X':<2} {nr.pack_id} {nr.case_id} {nr.turbine_id}  成因 {nr.nuisance_cause}"
                f"  干擾判定 {nr.nuisance_predictions} 筆"
                f"{f'  故障診斷 {nr.fault_predictions} 筆' if nr.fault_predictions else ''}"
            )
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 進入點。

    Args:
        argv: 命令列參數（測試用）；None＝``sys.argv``。

    Returns:
        exit code（0 成功、2 輸入錯誤）。
    """
    parser = argparse.ArgumentParser(description="RAG 維修助手評分（介面合約 v1）")
    parser.add_argument("--answers", type=Path, nargs="+", required=True,
                        help="ground_truth.json 檔、答案目錄或評分端版資料包目錄")
    parser.add_argument("--predictions", type=Path, required=True, help="助手輸出的 predictions.jsonl")
    parser.add_argument("--json", type=Path, help="另存完整報告（JSON）")
    parser.add_argument("--vocabulary", type=Path, default=KIT_DIR / "vocabulary.json")
    args = parser.parse_args(argv)

    try:
        answers = load_answers(args.answers)
    except FileNotFoundError as exc:
        print(f"找不到：{exc}", file=sys.stderr)
        return 2
    if not answers:
        print("找不到標準答案檔（*.ground_truth.json 或 ground_truth.json）", file=sys.stderr)
        return 2
    try:
        # utf-8-sig：Windows 記事本存的 UTF-8 帶 BOM，第一行不會因此變成格式錯誤
        text = args.predictions.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        print(f"找不到：{args.predictions}", file=sys.stderr)
        return 2
    except UnicodeDecodeError:
        print(f"{args.predictions} 不是 UTF-8（PowerShell 5 的 > 會存成 UTF-16；請改用 "
              "Out-File -Encoding utf8 或在 Python 裡寫檔）", file=sys.stderr)
        return 2
    components = load_vocabulary(args.vocabulary)
    predictions, invalid = read_predictions(text.split("\n"), components)
    try:
        report = score(answers, predictions, components, invalid)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(format_report(report))
    if args.json:
        args.json.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
