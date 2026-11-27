"""故障出勤卡的離線重播與自動評分（WMOM-20261127-08，出發前助理企劃的階段 A，DEC-20261127-11）。

即時風場的故障出勤卡（``briefing.build_fault_card``）在工單建立當下讀風場的事件與讀值。這裡拿盲測版資料包
（EPIC-DS 的題庫，附標準答案）重播同一個流程：

1. 資料包的每一次跳機當成一張故障維修工單（同一台機組 ``DISPATCH_GAP`` 內的跳機算同一次停機，和運維閉環
   「一次停機一張工單」一樣），資料截止點＝跳機後一個取樣週期（即時風場的截止點最多晚一個取樣週期）。
2. 卡片用**同一個** ``build_fault_card``——資料包只是換掉它讀資料的兩個介面（``live_events`` 與
   ``readings``），卡片的規則不因為重播而不同。
3. 用標準答案評分（``briefing.score_card``）：有故障時重點訊號有沒有被標成偏高 / 偏低、沒有故障（干擾、
   電網事件）時有沒有誤判；電網事件另看「同場同時同碼」有沒有列出其他機組。

資料條件（審查紀錄 2026-11-24 列的缺口）：

- ``raw``：原始 10 秒資料。
- ``gaps``：隨機少掉兩成讀值（缺測）。
- ``stale``：讀值晚 15 分鐘才到（過期 / 晚到；警報照常即時）。
- ``duplicates``：一成讀值重複送兩次。
- ``ten_minute``：只有 10 分鐘統計（真實風場多半只匯得出這個）：類比量取平均、狀態取整段不變的值，時間標在
  每段的結束（那時才算得出來）。

標準答案只用來評分，不進卡片；卡片只看資料包本來就給受測端的東西。
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple
from uuid import uuid5, NAMESPACE_URL

import numpy as np
import pandas as pd

from modules.workflow.domain.work_order import WorkOrder, WorkOrderType
from server import briefing
from server import scenario_pack as sp
from server.live_archive import LiveReading
from simulator.time_utils import iso_utc, normalize_iso, parse_iso

# 同一台機組這段時間內的跳機算同一次停機（同一張工單）
DISPATCH_GAP = timedelta(hours=2)
# 讀值晚到多久（stale 模式）
STALE_LAG = timedelta(minutes=15)
GAP_FRACTION = 0.2
DUPLICATE_FRACTION = 0.1
MODES: Tuple[str, ...] = ("raw", "gaps", "stale", "duplicates", "ten_minute")
MODE_LABELS: Dict[str, str] = {
    "raw": "原始 10 秒資料",
    "gaps": "缺測兩成",
    "stale": "讀值晚 15 分鐘",
    "duplicates": "一成讀值重複",
    "ten_minute": "只有 10 分鐘統計",
}
# 電網事件與干擾的答案往前後找這麼久（同批次標準答案的寬限）
_NUISANCE_MATCH = timedelta(minutes=30)
_PLC_KIND = {v: k for k, v in sp._PLC_EVENT_TYPES.items()}   # 資料包的事件種類 → storage 的 PLC 事件種類


@dataclass
class PackData:
    """一個盲測版資料包（只讀受測端拿得到的檔案）。"""

    pack_id: str
    turbines: List[str]
    sample_period_s: float
    raw: pd.DataFrame
    stats: Optional[pd.DataFrame]
    events: List[Dict[str, object]]

    @classmethod
    def load(cls, path: Path) -> "PackData":
        """讀資料包目錄（``manifest.json``、``events.jsonl``、``timeseries_raw.parquet``、``stats_10min.parquet``）。"""
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        raw = pd.read_parquet(path / "timeseries_raw.parquet")
        stats_path = path / "stats_10min.parquet"
        stats = pd.read_parquet(stats_path) if stats_path.exists() else None
        events = [json.loads(line) for line in (path / "events.jsonl").read_text(encoding="utf-8").splitlines()
                  if line.strip()]
        return cls(pack_id=str(manifest["pack_id"]), turbines=[str(t) for t in manifest["turbines"]],
                   sample_period_s=float(manifest.get("sample_period_s", 10.0)), raw=raw, stats=stats,
                   events=events)


class PackEvents:
    """把資料包的事件包成 ``Storage.live_events`` 的樣子（卡片用同一個 ``_alarm_events`` 讀）。"""

    def __init__(self, events: Sequence[Mapping[str, object]]) -> None:
        self._rows: List[Dict[str, object]] = []
        for index, event in enumerate(sorted(events, key=lambda e: str(e["ts"])), start=1):
            row: Dict[str, object] = {"id": index, "timestamp": normalize_iso(str(event["ts"])),
                                      "turbine_id": event.get("turbine_id")}
            if event.get("event_type") == "state_change":
                row.update(source="simulator", payload={"fromState": event.get("from_state"),
                                                        "toState": event.get("to_state")})
            else:
                row.update(source="plc", payload={
                    "kind": _PLC_KIND.get(str(event.get("event_type")), str(event.get("event_type"))),
                    "code": event.get("alarm_code"), "level": event.get("alarm_level"),
                    "text": event.get("alarm_text"), "eventId": event.get("event_id"),
                    "plcTag": event.get("plc_tag")})
            self._rows.append(row)

    def live_events(self, after_id: int = 0, turbine_id: Optional[str] = None, start: Optional[str] = None,
                    end: Optional[str] = None, limit: int = 1000) -> List[Dict[str, object]]:
        """同 ``Storage.live_events``：依寫入順序、``[start, end)``。"""
        lo = normalize_iso(start) if start else None
        hi = normalize_iso(end) if end else None
        out: List[Dict[str, object]] = []
        for row in self._rows:
            if int(str(row["id"])) <= after_id:
                continue
            if turbine_id is not None and row["turbine_id"] != turbine_id:
                continue
            stamp = str(row["timestamp"])
            if (lo is not None and stamp < lo) or (hi is not None and stamp >= hi):
                continue
            out.append(row)
            if len(out) >= limit:
                break
        return out


class PackReadings:
    """把資料包的讀值包成 ``LiveHistory.readings`` 的樣子。

    ``visible_until``：讀值最晚看得到哪個時間（stale 模式在每張卡前設成截止點減 ``STALE_LAG``）。
    """

    def __init__(self, frame: pd.DataFrame) -> None:
        names = {column.tag.id: column.name for column in sp.pack_columns()}
        self._names = names
        self._by_turbine: Dict[str, Tuple[List[str], pd.DataFrame]] = {}
        for turbine_id, part in frame.groupby("turbine_id", sort=False):
            part = part.sort_values("timestamp", kind="stable")
            stamps = [iso_utc(ts.to_pydatetime()) for ts in part["timestamp"]]
            self._by_turbine[str(turbine_id)] = (stamps, part.reset_index(drop=True))
        self.visible_until: Optional[str] = None

    def readings(self, turbine_id: str, tag_ids: Sequence[str], after_id: int = 0, start: Optional[str] = None,
                 end: Optional[str] = None, limit: int = 1000) -> List[LiveReading]:
        """同 ``LiveHistory.readings``：``[start, end)``、依時間順序；資料包沒有的欄位是 NaN。"""
        found = self._by_turbine.get(turbine_id)
        if found is None:
            return []
        stamps, part = found
        lo = normalize_iso(start) if start else None
        hi = normalize_iso(end) if end else None
        if self.visible_until is not None and (hi is None or self.visible_until < hi):
            hi = self.visible_until
        first = 0 if lo is None else _bisect(stamps, lo)
        last = len(stamps) if hi is None else _bisect(stamps, hi)
        first = max(first, after_id)
        last = min(last, first + limit)
        if last <= first:
            return []
        columns = [self._names.get(tag) for tag in tag_ids]
        block = np.full((last - first, len(tag_ids)), np.nan)
        for j, name in enumerate(columns):
            if name is not None and name in part.columns:
                block[:, j] = part[name].iloc[first:last].to_numpy(dtype=float, na_value=np.nan)
        return [LiveReading(id=first + i + 1, timestamp=stamps[first + i], turbine_id=turbine_id, values=block[i])
                for i in range(last - first)]


def _bisect(stamps: Sequence[str], key: str) -> int:
    lo, hi = 0, len(stamps)
    while lo < hi:
        mid = (lo + hi) // 2
        if stamps[mid] < key:
            lo = mid + 1
        else:
            hi = mid
    return lo


def ten_minute_frame(stats: pd.DataFrame) -> pd.DataFrame:
    """10 分鐘統計 → 讀值表（只用完整的段）：類比量取平均，狀態類只在整段不變時取那個值，時間＝每段的結束。"""
    whole = stats[~stats["is_partial"].astype(bool)]
    data: Dict[str, object] = {"timestamp": whole["window_end"].to_numpy(),
                               "turbine_id": whole["turbine_id"].to_numpy()}
    for column in sp.pack_columns():
        if column.is_analog and f"{column.name}_avg" in whole.columns:
            data[column.name] = whole[f"{column.name}_avg"].to_numpy(dtype=float, na_value=np.nan)
        elif f"{column.name}_min" in whole.columns and f"{column.name}_max" in whole.columns:
            lo = whole[f"{column.name}_min"].to_numpy(dtype=float, na_value=np.nan)
            hi = whole[f"{column.name}_max"].to_numpy(dtype=float, na_value=np.nan)
            data[column.name] = np.where(lo == hi, lo, np.nan)
    return pd.DataFrame(data)


def degrade(raw: pd.DataFrame, mode: str, seed: int = 20261127) -> pd.DataFrame:
    """依資料條件改讀值表（``gaps`` / ``duplicates``；其他模式原樣回傳）。亂數固定，結果可重現。"""
    rng = random.Random(seed)
    if mode == "gaps":
        keep = [rng.random() >= GAP_FRACTION for _ in range(len(raw))]
        return raw[keep].reset_index(drop=True)
    if mode == "duplicates":
        picked = [i for i in range(len(raw)) if rng.random() < DUPLICATE_FRACTION]
        return pd.concat([raw, raw.iloc[picked]], ignore_index=True).sort_values(
            ["turbine_id", "timestamp"], kind="stable").reset_index(drop=True)
    return raw


@dataclass(frozen=True)
class Dispatch:
    """一次出勤：哪台機組、哪個跳機碼、什麼時候跳、資料截止點。"""

    turbine_id: str
    code: int
    trip_ts: datetime
    cutoff: datetime


def dispatches(pack: PackData) -> List[Dispatch]:
    """資料包裡的每一次停機（同一台機組 ``DISPATCH_GAP`` 內的跳機算同一次），依時間排序。"""
    trips = sorted((e for e in pack.events if e.get("event_type") == "trip" and e.get("alarm_code") is not None),
                   key=lambda e: str(e["ts"]))
    last: Dict[str, datetime] = {}
    out: List[Dispatch] = []
    for event in trips:
        turbine_id, moment = str(event["turbine_id"]), parse_iso(str(event["ts"]))
        previous = last.get(turbine_id)
        if previous is not None and moment - previous < DISPATCH_GAP:
            continue
        last[turbine_id] = moment
        out.append(Dispatch(turbine_id=turbine_id, code=int(str(event["alarm_code"])), trip_ts=moment,
                            cutoff=moment + timedelta(seconds=pack.sample_period_s)))
    return out


def answer_for(dispatch: Dispatch, truth: Mapping[str, object]) -> Dict[str, object]:
    """這次出勤的評分答案（``briefing.capture_answer`` 的格式）：當時那台機組有哪些故障、是不是干擾或電網事件。

    - 故障：那台機組已經開始（``onset_ts`` ≤ 截止點）的故障 case。
    - 干擾 / 電網事件：那台機組、跳機碼在 case 的預期碼或實際碼裡、時間在跳機前後 30 分鐘內的 nuisance case。
    """
    names = {column.tag.id: column.name for column in sp.pack_columns()}
    faults: List[Dict[str, object]] = []
    farm_events: List[Dict[str, object]] = []
    matched: List[str] = []
    for case in truth.get("cases", []):  # type: ignore[union-attr]
        if not isinstance(case, dict) or case.get("turbine_id") != dispatch.turbine_id:
            continue
        onset = case.get("onset_ts")
        if case.get("category") == "nuisance":
            codes = set(case.get("observed_alarm_codes") or []) | set(case.get("expected_alarm_codes") or [])
            stamps = [parse_iso(str(case[k])) for k in ("trip_ts", "first_alarm_ts", "onset_ts") if case.get(k)]
            if dispatch.code not in codes or not any(abs(s - dispatch.trip_ts) <= _NUISANCE_MATCH for s in stamps):
                continue
            faults.append({"scenario_id": case.get("fault_id"), "category": "nuisance",
                           "component": case.get("component"), "key_signals": [], "tripped": True,
                           "severity": None})
            if case.get("farm_event_id"):
                farm_events.append({"kind": case.get("fault_id"), "nuisance_cause": case.get("nuisance_cause")})
            matched.append(str(case.get("case_id")))
            continue
        if onset is None or parse_iso(str(onset)) > dispatch.cutoff:
            continue
        keys = [names[tag] for tag in case.get("key_signals") or [] if tag in names]
        trip = case.get("trip_ts")
        faults.append({"scenario_id": case.get("fault_id"), "category": case.get("category"),
                       "component": case.get("component"), "key_signals": keys,
                       "tripped": bool(trip) and parse_iso(str(trip)) <= dispatch.cutoff,
                       "severity": case.get("final_severity")})
        matched.append(str(case.get("case_id")))
    real = [f for f in faults if f["category"] != "nuisance"]
    return {"faults": faults, "has_fault": bool(real), "farm_events": farm_events, "cases": matched}


@dataclass
class ReplayResult:
    """一張重播出來的卡和它的分數。"""

    pack_id: str
    mode: str
    dispatch: Dispatch
    card: Dict[str, object]
    answer: Dict[str, object]
    score: Dict[str, object] = field(default_factory=dict)

    def row(self) -> Dict[str, object]:
        """給報告用的一列（不含整張卡）。"""
        quality = self.card.get("data_quality")
        recent = self.card.get("recent_events")
        farm_same = recent.get("farm_same_code", {}).get("turbines", []) if isinstance(recent, dict) else []
        return {"pack_id": self.pack_id, "mode": self.mode, "turbine_id": self.dispatch.turbine_id,
                "code": self.dispatch.code, "trip_ts": iso_utc(self.dispatch.trip_ts),
                "cases": self.answer.get("cases", []),
                "faults": [f["scenario_id"] for f in self.answer.get("faults", [])],  # type: ignore[union-attr]
                "farm_event": bool(self.answer.get("farm_events")),
                "farm_same_code": [t["turbine_id"] for t in farm_same],
                "flags": quality.get("flags", []) if isinstance(quality, dict) else [],
                **self.score}


def replay_pack(pack: PackData, truth: Mapping[str, object], mode: str = "raw") -> List[ReplayResult]:
    """重播一個資料包：每一次出勤產生一張故障出勤卡、評分。

    Args:
        pack: 資料包。
        truth: 它的標準答案（``ground_truth.json``）。
        mode: 資料條件（``MODES``）。

    Returns:
        每次出勤一筆。
    """
    if mode not in MODES:
        raise ValueError(f"不認得的資料條件：{mode}")
    if mode == "ten_minute":
        if pack.stats is None:
            raise ValueError(f"{pack.pack_id} 沒有 10 分鐘統計")
        frame = ten_minute_frame(pack.stats)
    else:
        frame = degrade(pack.raw, mode)
    readings = PackReadings(frame)
    events = PackEvents(pack.events)
    out: List[ReplayResult] = []
    for index, dispatch in enumerate(dispatches(pack), start=1):
        readings.visible_until = iso_utc(dispatch.cutoff - STALE_LAG) if mode == "stale" else None
        order = WorkOrder(
            farm_id=pack.pack_id, turbine_id=dispatch.turbine_id, type=WorkOrderType.CORRECTIVE,
            title="replay", description="", business_key=f"REPLAY-{pack.pack_id}-{index:03d}",
            id=uuid5(NAMESPACE_URL, f"{pack.pack_id}/{mode}/{index}"), source_alarm_code=str(dispatch.code))
        card = briefing.build_fault_card(storage=events, history=readings,  # type: ignore[arg-type]
                                         work_order=order, turbine_id=dispatch.turbine_id,
                                         turbines=pack.turbines, cutoff=dispatch.cutoff)
        answer = answer_for(dispatch, truth)
        score = dict(briefing.score_card(card, answer))
        recent = card.get("recent_events")
        shown = bool(recent.get("farm_same_code", {}).get("turbines")) if isinstance(recent, dict) else False
        score["farm_context_shown"] = shown if answer.get("farm_events") else None
        manual = card.get("manual")
        score["manual_found"] = manual.get("status") == "ok" if isinstance(manual, dict) else None
        out.append(ReplayResult(pack.pack_id, mode, dispatch, card, answer, score))
    return out


def _rate(values: Sequence[object]) -> Optional[float]:
    known = [bool(v) for v in values if v is not None]
    return round(sum(known) / len(known), 3) if known else None


def summarize(results: Sequence[ReplayResult]) -> Dict[str, object]:
    """一個資料條件的彙總：有故障的出勤裡重點訊號被標出的比例、沒有故障的出勤裡誤判的比例……"""
    scores = [r.score for r in results]
    with_fault = [s for s in scores if s.get("has_fault")]
    without = [s for s in scores if not s.get("has_fault")]
    listed = [float(str(s["key_signal_listed"])) for s in with_fault if s.get("key_signal_listed") is not None]
    flags: Dict[str, int] = {}
    for result in results:
        quality = result.card.get("data_quality")
        for flag in (quality.get("flags", []) if isinstance(quality, dict) else []):
            flags[str(flag)] = flags.get(str(flag), 0) + 1
    return {
        "dispatches": len(results),
        "with_fault": len(with_fault),
        "without_fault": len(without),
        "key_signal_flagged": _rate([s.get("key_signal_flagged") for s in with_fault]),
        "key_signal_listed": round(sum(listed) / len(listed), 3) if listed else None,
        "false_escalation": _rate([s.get("false_escalation") for s in without]),
        "farm_context_shown": _rate([s.get("farm_context_shown") for s in scores]),
        "manual_found": _rate([s.get("manual_found") for s in scores]),
        "degraded": _rate([bool(r.card.get("data_quality", {}).get("degraded"))  # type: ignore[union-attr]
                           for r in results]),
        "flags": dict(sorted(flags.items())),
    }


def replay_all(packs_dir: Path, answers_dir: Path, modes: Sequence[str] = MODES) -> Dict[str, object]:
    """重播一個目錄下的所有資料包（答案在 ``answers_dir/<pack_id>.ground_truth.json``）。

    Returns:
        ``{"modes": {模式: {"summary": {...}, "rows": [...]}}, "packs": [...]}``。
    """
    packs = [PackData.load(path) for path in sorted(p for p in packs_dir.iterdir() if (p / "manifest.json").exists())]
    truths = {pack.pack_id: json.loads((answers_dir / f"{pack.pack_id}.ground_truth.json").read_text(encoding="utf-8"))
              for pack in packs}
    out: Dict[str, object] = {"packs": [pack.pack_id for pack in packs], "modes": {}}
    for mode in modes:
        results = [r for pack in packs for r in replay_pack(pack, truths[pack.pack_id], mode)]
        out["modes"][mode] = {"summary": summarize(results), "rows": [r.row() for r in results]}  # type: ignore[index]
    return out


def _pct(value: object) -> str:
    return "—" if value is None else f"{float(str(value)) * 100:.0f}%"


def markdown_report(result: Mapping[str, object]) -> str:
    """``replay_all`` 的結果 → Markdown 報告（各資料條件的彙總，加上原始資料的逐筆結果）。"""
    modes = result.get("modes", {})
    lines = [
        "# 故障出勤卡離線重播（階段 A）",
        "",
        f"資料包：{', '.join(str(p) for p in result.get('packs', []))}",  # type: ignore[union-attr]
        "",
        "| 資料條件 | 出勤 | 有故障 | 重點訊號被標出 | 重點訊號在卡上 | 沒有故障卻標了偏高 / 偏低 | 電網事件列出同場同碼 | 卡片標示資料有問題 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for mode, body in modes.items():  # type: ignore[union-attr]
        s = body["summary"]
        lines.append(f"| {MODE_LABELS.get(mode, mode)} | {s['dispatches']} | {s['with_fault']} | "
                     f"{_pct(s['key_signal_flagged'])} | {_pct(s['key_signal_listed'])} | "
                     f"{_pct(s['false_escalation'])} | {_pct(s['farm_context_shown'])} | {_pct(s['degraded'])} |")
    raw = modes.get("raw") if isinstance(modes, dict) else None
    if raw:
        lines += ["", "## 原始資料的逐筆結果", "",
                  "| 資料包 | 機組 | 跳機碼 | 答案 | 重點訊號被標出 | 誤判 | 卡片的資料品質旗標 |",
                  "|---|---|---|---|---|---|---|"]
        for row in raw["rows"]:
            mark = {True: "是", False: "否", None: "—"}
            lines.append(f"| {row['pack_id']} | {row['turbine_id']} | {row['code']} | "
                         f"{', '.join(row['faults']) or '（沒有 case）'} | {mark[row.get('key_signal_flagged')]} | "
                         f"{mark[row.get('false_escalation')]} | {', '.join(row['flags']) or '—'} |")
    return "\n".join(lines) + "\n"
