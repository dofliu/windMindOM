"""RAG 維修助手評分程式（介面合約 v1 §7，WMOM-20261021-09）。

只用 Python 標準函式庫：學生把整個 starter kit 目錄複製走就能用。

用法::

    python score.py --answers answers/ --predictions my_predictions.jsonl
    python score.py --answers answers/z72-starter-01.ground_truth.json --predictions p.jsonl --json report.json

``--answers`` 可給檔案或目錄（讀目錄下所有 ``*.ground_truth.json``）；``--predictions`` 是助手輸出的
JSONL，每行一筆診斷（格式見合約 §6）。只評 ``--answers`` 裡有的資料包，其他 pack_id 的預測忽略。

評分規則（合約 §7）：
- 「故障診斷」＝category 為 ``real_fault`` / ``sensor_fault`` 的預測；依機組與時間對到 case
  （``onset_ts`` ≤ ts ≤ ``sim_end``）；對不到的是誤報。
- 每個 case 以**最後一筆**對到的診斷評元件、元件群組、類別與手冊引用（助手可以邊看邊修正）。
- 時效以**第一筆元件正確**的診斷計：相對 ``first_alarm_ts`` 的延遲；早於第一個預期警報（或整段都沒有
  警報）就是早期預警。
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
    """助手的一筆診斷（合約 §6）。"""

    line: int
    pack_id: str
    turbine_id: str
    ts: datetime
    category: str
    component: Optional[str]
    manual_refs: List[int]


@dataclass
class Case:
    """標準答案的一個 case（只取評分用得到的欄位）。"""

    pack_id: str
    case_id: str
    turbine_id: str
    category: str
    component: str
    expected_codes: List[int]
    window_start: datetime
    window_end: Optional[datetime]
    first_alarm: Optional[datetime]
    fault_id: str


def read_predictions(lines: Iterable[str], components: Dict[str, str]) -> Tuple[List[Prediction], List[Dict[str, object]]]:
    """讀助手輸出的 JSONL。

    Args:
        lines: 檔案的每一行。
        components: ``load_vocabulary`` 的結果。

    Returns:
        ``(有效的預測, 無效的行與原因)``。故障診斷的元件不在詞彙內（多半是拼錯）算無效，報告會列出來。
    """
    valid: List[Prediction] = []
    invalid: List[Dict[str, object]] = []
    for number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
            if not isinstance(item, dict):
                raise ValueError("not a JSON object")
            for key in ("pack_id", "turbine_id", "ts", "category"):
                if not isinstance(item.get(key), str) or not item[key]:
                    raise ValueError(f"missing or non-string {key!r}")
            if item["category"] not in PREDICTION_CATEGORIES:
                raise ValueError(f"category must be one of {PREDICTION_CATEGORIES}")
            component = item.get("component")
            if item["category"] in FAULT_CATEGORIES and component not in components:
                raise ValueError(f"a fault diagnosis needs a 'component' from vocabulary.json (got {component!r})")
            refs = item.get("manual_refs", [])
            if not isinstance(refs, list) or not all(isinstance(r, int) and not isinstance(r, bool) for r in refs):
                raise ValueError("'manual_refs' must be a list of event codes (int)")
            valid.append(Prediction(
                line=number, pack_id=item["pack_id"], turbine_id=item["turbine_id"], ts=parse_ts(item["ts"]),
                category=item["category"], component=component if isinstance(component, str) else None,
                manual_refs=list(dict.fromkeys(refs)),
            ))
        except (ValueError, TypeError) as exc:
            invalid.append({"line": number, "reason": str(exc)})
    return valid, invalid


def read_cases(ground_truth: Dict[str, object]) -> List[Case]:
    """標準答案 → 要評分的 case（被同機組同故障再注入取代的 ``superseded`` case 不評）。

    Args:
        ground_truth: 一個資料包的 ``ground_truth.json``。

    Returns:
        case 清單。
    """
    pack_id = str(ground_truth["pack_id"])
    sim_start = parse_ts(str(ground_truth["sim_start"]))
    sim_end = parse_ts(str(ground_truth["sim_end"])) if ground_truth.get("sim_end") else None
    cases = []
    for item in ground_truth.get("cases") or []:  # type: ignore[union-attr]
        if item.get("superseded"):
            continue
        cases.append(Case(
            pack_id=pack_id,
            case_id=item["case_id"],
            turbine_id=item["turbine_id"],
            category=item["category"],
            component=item["component"],
            expected_codes=list(item.get("expected_alarm_codes") or []),
            window_start=parse_ts(item["onset_ts"]) if item.get("onset_ts") else sim_start,
            window_end=sim_end,
            first_alarm=parse_ts(item["first_alarm_ts"]) if item.get("first_alarm_ts") else None,
            fault_id=item.get("fault_id", ""),
        ))
    return cases


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
    n_predictions: int = 0


@dataclass
class Report:
    """全部資料包的評分結果。"""

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
    latency_median_s: Optional[float]
    latency_mean_s: Optional[float]
    false_alarm_predictions: int
    false_alarm_turbines: int
    nuisance_predictions: int
    nuisance_during_fault: int
    ignored_predictions: int
    invalid_predictions: List[Dict[str, object]] = field(default_factory=list)
    case_results: List[CaseResult] = field(default_factory=list)


def _in_window(case: Case, ts: datetime) -> bool:
    return case.window_start <= ts and (case.window_end is None or ts <= case.window_end)


def _match(prediction: Prediction, cases: Sequence[Case]) -> Optional[Case]:
    """一筆故障診斷對到哪個 case：同機組、時間在窗內；同時有多個時優先元件相同者，否則取最近發生的。"""
    candidates = [c for c in cases if c.turbine_id == prediction.turbine_id and _in_window(c, prediction.ts)]
    if not candidates:
        return None
    same = [c for c in candidates if c.component == prediction.component]
    return max(same or candidates, key=lambda c: c.window_start)


def _rank_of(refs: Sequence[int], relevant: Iterable[int]) -> Optional[int]:
    wanted = set(relevant)
    for rank, code in enumerate(refs, start=1):
        if code in wanted:
            return rank
    return None


def score(ground_truths: Sequence[Dict[str, object]], predictions: Sequence[Prediction],
          components: Dict[str, str], invalid: Sequence[Dict[str, object]] = ()) -> Report:
    """評分。

    Args:
        ground_truths: 各資料包的標準答案。
        predictions: ``read_predictions`` 的有效預測。
        components: 元件 → 群組。
        invalid: ``read_predictions`` 的無效行（原樣放進報告）。

    Returns:
        評分報告。
    """
    packs = [str(gt["pack_id"]) for gt in ground_truths]
    cases_by_pack = {str(gt["pack_id"]): read_cases(gt) for gt in ground_truths}
    matched: Dict[Tuple[str, str], List[Prediction]] = {}
    false_alarms: List[Prediction] = []
    nuisance = nuisance_during_fault = ignored = 0
    for prediction in sorted(predictions, key=lambda p: (p.ts, p.line)):
        cases = cases_by_pack.get(prediction.pack_id)
        if cases is None:
            ignored += 1
            continue
        if prediction.category == "nuisance":
            nuisance += 1
            if any(c.turbine_id == prediction.turbine_id and _in_window(c, prediction.ts) for c in cases):
                nuisance_during_fault += 1  # 把真故障當成干擾
            continue
        case = _match(prediction, cases)
        if case is None:
            false_alarms.append(prediction)
        else:
            matched.setdefault((case.pack_id, case.case_id), []).append(prediction)

    results: List[CaseResult] = []
    for pack_id in packs:
        for case in cases_by_pack[pack_id]:
            result = CaseResult(pack_id=pack_id, case_id=case.case_id, turbine_id=case.turbine_id,
                                expected_component=case.component, expected_category=case.category)
            claims = matched.get((pack_id, case.case_id), [])
            result.n_predictions = len(claims)
            if claims:
                final = claims[-1]  # 已依時間排序：最後一筆＝助手最後的判斷
                result.detected = True
                result.predicted_component = final.component
                result.predicted_category = final.category
                result.component_correct = final.component == case.component
                result.component_group_correct = (
                    final.component is not None and components.get(final.component) == components.get(case.component)
                )
                result.category_correct = final.category == case.category
                rank = _rank_of(final.manual_refs, case.expected_codes)
                result.manual_hit_at_1 = rank == 1
                result.manual_hit_at_3 = rank is not None and rank <= 3
                result.manual_reciprocal_rank = 1.0 / rank if rank else 0.0
                correct = [p for p in claims if p.component == case.component]
                if correct:
                    first = correct[0].ts
                    result.first_correct_ts = first.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                    if case.first_alarm is not None:
                        result.latency_s = (first - case.first_alarm).total_seconds()
                    result.early_warning = case.first_alarm is None or first < case.first_alarm
            results.append(result)

    n = len(results)

    def rate(values: Iterable[bool]) -> float:
        return sum(values) / n if n else 0.0

    latencies = [r.latency_s for r in results if r.latency_s is not None]
    return Report(
        packs=packs,
        cases=n,
        detected=sum(r.detected for r in results),
        detection_rate=rate(r.detected for r in results),
        component_accuracy=rate(r.component_correct for r in results),
        component_group_accuracy=rate(r.component_group_correct for r in results),
        category_accuracy=rate(r.category_correct for r in results),
        manual_hit_at_1=rate(r.manual_hit_at_1 for r in results),
        manual_hit_at_3=rate(r.manual_hit_at_3 for r in results),
        manual_mrr=sum(r.manual_reciprocal_rank for r in results) / n if n else 0.0,
        early_warnings=sum(r.early_warning for r in results),
        latency_median_s=statistics.median(latencies) if latencies else None,
        latency_mean_s=statistics.mean(latencies) if latencies else None,
        false_alarm_predictions=len(false_alarms),
        false_alarm_turbines=len({(p.pack_id, p.turbine_id) for p in false_alarms}),
        nuisance_predictions=nuisance,
        nuisance_during_fault=nuisance_during_fault,
        ignored_predictions=ignored,
        invalid_predictions=list(invalid),
        case_results=results,
    )


# ── CLI ──────────────────────────────────────────────────────────────────────


def load_answers(paths: Sequence[Path]) -> List[Dict[str, object]]:
    """讀標準答案檔（檔案或目錄）。

    Args:
        paths: ``*.ground_truth.json`` 檔或含這些檔的目錄。

    Returns:
        依檔名排序的標準答案。

    Raises:
        FileNotFoundError: 路徑不存在。
    """
    files: List[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.glob("*.ground_truth.json")))
        elif path.exists():
            files.append(path)
        else:
            raise FileNotFoundError(path)
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


def format_report(report: Report) -> str:
    """報告 → 給人看的文字。"""
    def pct(value: float) -> str:
        return f"{value * 100:5.1f} %"

    def secs(value: Optional[float]) -> str:
        return "-" if value is None else f"{value:+.0f} s"

    lines = [
        f"資料包：{', '.join(report.packs)}",
        f"case：{report.cases}　偵測到：{report.detected}（{pct(report.detection_rate).strip()}）",
        "",
        f"  元件正確率          {pct(report.component_accuracy)}",
        f"  元件群組正確率      {pct(report.component_group_accuracy)}",
        f"  類別正確率          {pct(report.category_accuracy)}",
        f"  手冊引用 hit@1      {pct(report.manual_hit_at_1)}",
        f"  手冊引用 hit@3      {pct(report.manual_hit_at_3)}",
        f"  手冊引用 MRR        {report.manual_mrr:7.3f}",
        f"  延遲（中位 / 平均） {secs(report.latency_median_s)} / {secs(report.latency_mean_s)}"
        "（相對第一個預期警報，負值＝提前）",
        f"  早期預警            {report.early_warnings} 個 case",
        f"  誤報                {report.false_alarm_predictions} 筆（{report.false_alarm_turbines} 台機組）",
        f"  干擾判定            {report.nuisance_predictions} 筆，其中 {report.nuisance_during_fault} 筆發生在故障期間",
    ]
    if report.ignored_predictions:
        lines.append(f"  略過（不在答案裡的資料包）{report.ignored_predictions} 筆")
    if report.invalid_predictions:
        lines.append(f"  格式錯誤 {len(report.invalid_predictions)} 行，例：{report.invalid_predictions[0]}")
    lines += ["", "case 明細："]
    for r in report.case_results:
        mark = "✓" if r.component_correct else ("~" if r.component_group_correct else ("✗" if r.detected else "-"))
        lines.append(
            f"  {mark} {r.pack_id} {r.case_id} {r.turbine_id}  答案 {r.expected_component}/{r.expected_category}"
            f"  預測 {r.predicted_component}/{r.predicted_category}  延遲 {secs(r.latency_s)}"
            f"{'  早期預警' if r.early_warning else ''}"
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
    parser.add_argument("--answers", type=Path, nargs="+", required=True, help="ground_truth.json 檔或目錄")
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
        print("找不到標準答案檔（*.ground_truth.json）", file=sys.stderr)
        return 2
    if not args.predictions.exists():
        print(f"找不到：{args.predictions}", file=sys.stderr)
        return 2
    components = load_vocabulary(args.vocabulary)
    predictions, invalid = read_predictions(args.predictions.read_text(encoding="utf-8").splitlines(), components)
    report = score(answers, predictions, components, invalid)
    print(format_report(report))
    if args.json:
        args.json.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
