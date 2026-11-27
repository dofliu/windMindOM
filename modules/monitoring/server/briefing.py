"""出發前準備卡（WMOM-20261125-05）：工單建立時，把出發前該看的證據整理成一張卡。

第一版是**故障出勤卡**（故障維修工單）。卡上有六塊：

1. 本次事件：事件碼、等級、PLC 文字、時間、機組目前的運轉狀態。
2. 近 7 天的事件：這台機組同碼出現過幾次、還有哪些別的碼；同一時間同場其他機組有沒有同碼
   （整場一起跳多半是外部原因）。
3. 相關訊號：這個事件碼看的量測，加上風速 / 功率 / 轉速；事件前 1 小時與最後 10 分鐘的平均，和同場
   其他發電中機組的中位數、以及自己前 6 小時比。
4. 過往工單：這台機組最近的工單。
5. 手冊：警報目錄（Z72 手冊 Appendix C）列的原因與處置。知識庫（``modules/knowledge``）目前的語料是
   對照故障情境寫的佔位內容，不是手冊原文，**不引用**——引了等於把鑑別診斷給出去。
6. 料件：目前沒有「警報碼 → 料件」的對應表，卡上明講沒有。

原則（企劃 v0.1）：

- **只用可觀測資料**，和對外唯讀 API 同一條邊界：讀值只取 ``pack_columns()`` 的欄位，事件逐筆過
  ``is_observable_event``。卡上不寫故障情境，也不寫工單的標題與說明（手動開的工單是自由文字）。所以
  同一張卡可以原樣給外部。
- **以資料截止點為界**：只用截止點（工單建立當下的風場時鐘）之前的資料。
- **每一條可回查**：帶機組、時間範圍、來源。
- **缺資料要標明並降級**（``data_quality``）。
- **不判定根因**：「相關訊號」來自 PLC 的判定邏輯（哪個事件碼看哪個量測，手冊層級的知識），不是來自
  故障情境的標準答案；引用手冊列的原因不算判定。

評分（``score_card``）用的答案（工單建立當下這台機組實際有哪些故障）另外存，只給主管端的評分端點，
不在卡片裡。
"""

from __future__ import annotations

import logging
import statistics
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple

import numpy as np

from modules.workflow.domain.work_order import WorkOrder
from server import scenario_pack as sp
from server.live_history import LiveHistory
from server.storage import Storage, is_observable_event
from shared.alarm_codes import find_alarm
from simulator.physics.fault_engine import FAULT_SCENARIOS
from simulator.physics.plc_protection import build_rules
from simulator.physics.turbine_physics import TurbineSpec
from simulator.time_utils import iso_utc, parse_iso

if TYPE_CHECKING:
    from modules.workflow.repository.work_order_repository import WorkOrderRepository
    from simulator.engine import WindFarmSimulator

logger = logging.getLogger(__name__)

# 1.2：加例行巡檢卡（kind=routine_inspection，WMOM-20261126-05）；故障出勤卡的欄位不變
CARD_VERSION = "1.2"
KIND_FAULT_DISPATCH = "fault_dispatch"
KIND_ROUTINE_INSPECTION = "routine_inspection"
# 例行巡檢卡：事件看最近 30 天；訊號看最近 6 小時（最後 1 小時另算），和 7 天前同樣長的一段比
INSPECTION_EVENT_WINDOW = timedelta(days=30)
INSPECTION_SIGNAL_WINDOW = timedelta(hours=6)
INSPECTION_RECENT_WINDOW = timedelta(hours=1)
INSPECTION_BASELINE_LAG = timedelta(days=7)
# 排序用的權重：跳機、未結案的故障維修工單最重，量測偏離其次，警報再其次（同一碼多次只算到上限）
_WEIGHT_TRIP = 3
_WEIGHT_OPEN_ORDER = 3
_WEIGHT_SIGNAL = 2
_WEIGHT_ALARM = 1
_MAX_COUNT_PER_CODE = 3
EVENT_WINDOW = timedelta(days=7)
SIGNAL_WINDOW = timedelta(hours=1)
RECENT_WINDOW = timedelta(minutes=10)
BASELINE_WINDOW = timedelta(hours=6)
FARM_SAME_CODE_WINDOW = timedelta(minutes=10)
STALE_AFTER = timedelta(minutes=5)
# 和同場其他機組比：至少要有幾台有資料才比；偏離幾個「穩健標準差」算偏高 / 偏低
MIN_PEERS = 3
DEVIATION_SIGMAS = 3.0
# 同場的機組至少這麼大比例的時間在發電才拿來比（停機中的機組溫度、轉速本來就不一樣）
PEER_PRODUCING_FRACTION = 0.5
# 「穩健標準差」的下限：量測範圍的這個比例（同場的值幾乎一樣時，不讓很小的差異被放大成偏高 / 偏低）
SPREAD_FLOOR_OF_RANGE = 0.005
_STATE_TAG = "WTUR_TurSt"
_PRODUCTION_STATE = 6.0
_EVENT_SCAN_BATCH = 2000
_EVENT_SCAN_MAX_BATCHES = 25
_MAX_RELATED_TAGS = 8
_MAX_LISTED = 10

# 每張卡都看的背景量測：風速、併網功率、轉子轉速
CONTEXT_TAGS: Tuple[str, ...] = ("WMET_WSpeedNac", "WTUR_TotPwrAt", "WROT_RotSpd")
# PLC 判定用的訊號 → 看得到的量測（手冊層級的知識：哪個事件碼看哪個量測；第一個是主要的那個）
SIGNAL_TAGS: Dict[str, Tuple[str, ...]] = {
    "bearing_temp": ("WGEN_GnBrgTmp1", "WGEN_GnBrgTmp2"),
    "bearing_temp_raw": ("WGEN_GnBrgTmp1", "WGEN_GnBrgTmp2"),
    "bearing2_temp": ("WGEN_GnBrgTmp2", "WGEN_GnBrgTmp1"),
    "bearing2_temp_raw": ("WGEN_GnBrgTmp2", "WGEN_GnBrgTmp1"),
    "stator_temp": ("WGEN_GnStaTmp1", "WGEN_GnStaTmp2", "WGEN_GnAirTmp1"),
    "stator_temp_raw": ("WGEN_GnStaTmp1", "WGEN_GnStaTmp2"),
    "stator2_temp": ("WGEN_GnStaTmp2", "WGEN_GnStaTmp1", "WGEN_GnAirTmp1"),
    "stator2_temp_raw": ("WGEN_GnStaTmp2", "WGEN_GnStaTmp1"),
    "nacelle_temp": ("WNAC_NacTmp", "WMET_TmpOutside"),
    "nacelle_cab_temp": ("WNAC_NacCabTmp", "WNAC_NacTmp"),
    "transformer_temp": ("WGDC_TrfCoreTmp",),
    "cooling_water_temp": ("WCNV_IGCTWtrTmp", "WCNV_IGCTWtrPres1", "WCNV_CnvCabinTmp"),
    "converter_cab_temp": ("WCNV_CnvCabinTmp", "WCNV_IGCTWtrTmp"),
    "static_water_pressure": ("WCNV_IGCTWtrPres1", "WCNV_IGCTWtrPres2", "WCNV_IGCTWtrTmp"),
    "cooling_flow": ("WCNV_IGCTWtrPres1", "WCNV_IGCTWtrPres2", "WCNV_IGCTWtrTmp"),
    "cooling_conductivity": ("WCNV_IGCTWtrCond", "WCNV_IGCTWtrTmp"),
    "yaw_brake_pressure": ("WYAW_YwBrkHyPrs",),
    "seals_leak": ("WYAW_YwBrkHyPrs",),
    "vane_discrepancy": ("WYAW_YwVn1AlgnAvg5s", "WYAW_YwVn2AlgnAvg5s", "WMET_WDirAbs"),
    "vane1_frozen": ("WYAW_YwVn1AlgnAvg5s", "WYAW_YwVn2AlgnAvg5s"),
    "vane2_frozen": ("WYAW_YwVn2AlgnAvg5s", "WYAW_YwVn1AlgnAvg5s"),
    "yaw_timeout": ("WYAW_YwVn1AlgnAvg5s", "WYAW_YwBrkHyPrs", "WMET_WDirAbs"),
    "vibration": ("WNAC_VibMsNacXDir", "WNAC_VibMsNacYDir"),
    "rotor_speed_deviation": ("WROT_RotSpd", "WGEN_GnSpd"),
    "anemometer_wind": ("WMET_WSpeedNac", "WMET_WSpeedRaw"),
    "blade1_angle": ("WROT_PtAngValBl1", "WROT_PtAngValBl2", "WROT_PtAngValBl3"),
    "blade2_angle": ("WROT_PtAngValBl2", "WROT_PtAngValBl1", "WROT_PtAngValBl3"),
    "blade3_angle": ("WROT_PtAngValBl3", "WROT_PtAngValBl1", "WROT_PtAngValBl2"),
    "blade_disc_12": ("WROT_PtAngValBl1", "WROT_PtAngValBl2", "WROT_PtAngValBl3"),
    "blade_disc_13": ("WROT_PtAngValBl1", "WROT_PtAngValBl3", "WROT_PtAngValBl2"),
    "blade_disc_23": ("WROT_PtAngValBl2", "WROT_PtAngValBl3", "WROT_PtAngValBl1"),
}
for _blade in (1, 2, 3):
    for _suffix in ("current_5s", "current_60s", "current_10m", "i2t"):
        SIGNAL_TAGS[f"pitch{_blade}_{_suffix}"] = (f"WROT_PtMotCurBl{_blade}", f"WROT_PtAngValBl{_blade}")
# 物理層保護停機補上的碼——PLC 沒有訊號判定規則，量測依警報目錄的事件文字：351 / 320 是超速，
# 475 / 481 / 482 / 489 是電網電壓與頻率。有判定規則的碼不要寫在這裡（從規則來），測試會擋
CODE_TAGS: Dict[int, Tuple[str, ...]] = {
    351: ("WROT_RotSpd", "WGEN_GnSpd"),
    320: ("WROT_RotSpd", "WGEN_GnSpd"),
    475: ("WCNV_VtgMsCnvGd1", "WCNV_VtgMsCnvGd2", "WCNV_VtgMsCnvGd3", "WCNV_CnvGnFrq"),
    481: ("WCNV_VtgMsCnvGd1", "WCNV_VtgMsCnvGd2", "WCNV_VtgMsCnvGd3", "WCNV_CnvGnFrq"),
    482: ("WCNV_VtgMsCnvGd1", "WCNV_VtgMsCnvGd2", "WCNV_VtgMsCnvGd3", "WCNV_CnvGnFrq"),
    489: ("WCNV_CnvGnFrq", "WCNV_VtgMsCnvGd1"),
}


@lru_cache(maxsize=1)
def _pack_tags() -> Dict[str, sp.PackColumn]:
    return {column.tag.id: column for column in sp.pack_columns()}


@lru_cache(maxsize=1)
def _rule_signals() -> Dict[int, Tuple[str, ...]]:
    """事件碼 → PLC 判定用的訊號（依規則出現的順序）。"""
    signals: Dict[int, List[str]] = {}
    for rule in build_rules(TurbineSpec()):
        bucket = signals.setdefault(rule.code, [])
        if rule.signal not in bucket:
            bucket.append(rule.signal)
    return {code: tuple(names) for code, names in signals.items()}


def related_tags(code: Optional[int]) -> Tuple[str, ...]:
    """一個事件碼相關的量測（tag id，只含給得出去的欄位）；對不到時為空。

    Args:
        code: Z72 事件碼；None＝工單沒帶警報碼。

    Returns:
        tag id，主要的量測在前，最多 ``_MAX_RELATED_TAGS`` 個。
    """
    if code is None:
        return ()
    pack = _pack_tags()
    out: List[str] = []
    for signal in _rule_signals().get(code, ()):
        for tag in SIGNAL_TAGS.get(signal, ()):
            if tag in pack and tag not in out:
                out.append(tag)
    for tag in CODE_TAGS.get(code, ()):
        if tag in pack and tag not in out:
            out.append(tag)
    return tuple(out[:_MAX_RELATED_TAGS])


def alarm_code_of(work_order: WorkOrder) -> Optional[int]:
    """工單帶的警報碼（整數）；沒帶或不是數字為 None。"""
    code = (work_order.source_alarm_code or "").strip()
    return int(code) if code.isdigit() else None


def _alarm_events(storage: Storage, start: datetime, end: datetime,
                  turbine_id: Optional[str]) -> Tuple[List[Dict[str, object]], bool]:
    """``[start, end]`` 之間看得到的 PLC 警報 / 跳機事件（合約格式），依時間排序。

    依寫入順序分批取完；事件多到超過掃描上限時回傳的第二個值為 True（卡片要標明事件不完整）。
    """
    lower, upper = iso_utc(start), iso_utc(end + timedelta(microseconds=1))
    out: List[Dict[str, object]] = []
    cursor = 0
    truncated = True
    for _ in range(_EVENT_SCAN_MAX_BATCHES):
        batch = storage.live_events(after_id=cursor, turbine_id=turbine_id, start=lower, end=upper,
                                    limit=_EVENT_SCAN_BATCH)
        for event in batch:
            if not is_observable_event(event):
                continue
            packed = sp.pack_event(event)
            if packed is None or packed.get("alarm_code") is None:
                continue
            if packed.get("event_type") in ("alarm_raised", "trip"):
                out.append(dict(packed))
        if len(batch) < _EVENT_SCAN_BATCH:
            truncated = False
            break
        cursor = int(batch[-1]["id"])
    return sorted(out, key=lambda e: str(e["ts"])), truncated


class _Window:
    """一台機組在一段時間的讀值：各量測的平均、最近一段的平均、發電中的時間比例。"""

    def __init__(self, history: LiveHistory, turbine_id: str, tags: Sequence[str], start: datetime, end: datetime,
                 recent_from: Optional[datetime] = None) -> None:
        columns = list(tags) + [_STATE_TAG]
        rows = history.readings(turbine_id, columns, start=iso_utc(start), end=iso_utc(end), limit=3000)
        self.samples = len(rows)
        self.last_ts: Optional[str] = rows[-1].timestamp if rows else None
        self.means = np.full(len(tags), np.nan)
        self.recent = np.full(len(tags), np.nan)
        self.last = np.full(len(tags), np.nan)
        self.producing = 0.0
        if not rows:
            return
        matrix = np.vstack([row.values for row in rows])
        self.means = self._mean(matrix[:, :-1])
        self.last = matrix[-1, :-1]
        state = matrix[:, -1]
        known = ~np.isnan(state)
        self.producing = float(np.mean(state[known] == _PRODUCTION_STATE)) if known.any() else 0.0
        if recent_from is not None:
            key = iso_utc(recent_from)
            picked = np.array([row.timestamp >= key for row in rows])
            if picked.any():
                self.recent = self._mean(matrix[picked, :-1])

    @staticmethod
    def _mean(matrix: np.ndarray) -> np.ndarray:
        with np.errstate(all="ignore"):
            counts = np.sum(~np.isnan(matrix), axis=0)
            return np.where(counts > 0, np.nansum(matrix, axis=0) / np.maximum(counts, 1), np.nan)


def _deviation(value: Optional[float], peers: Sequence[float], floor: float) -> Tuple[str, Optional[float]]:
    """和同場比：回傳（偏高 / 偏低 / 相近 / 無法比較, 同場中位數）。"""
    if not peers:
        return "unknown", None
    median = float(statistics.median(peers))
    if value is None or len(peers) < MIN_PEERS:
        return "unknown", median
    mad = float(statistics.median(abs(v - median) for v in peers))
    spread = max(1.4826 * mad, 0.02 * abs(median), floor)
    score = (value - median) / spread
    return ("high" if score >= DEVIATION_SIGMAS else "low" if score <= -DEVIATION_SIGMAS else "normal"), median


def _number(value: float) -> Optional[float]:
    return None if np.isnan(value) else float(value)


def _signal_items(history: LiveHistory, turbine_id: str, turbines: Sequence[str], tags: Sequence[str],
                  primary: Sequence[str], cutoff: datetime, window: timedelta = SIGNAL_WINDOW,
                  recent: timedelta = RECENT_WINDOW, baseline_lag: Optional[timedelta] = None,
                  ) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    """相關訊號的比較：這台機組截止點前的平均、同場其他發電中的機組、自己稍早的基準。

    Args:
        window: 比較的時間長度（截止點往前）。
        recent: 「最近一段」的長度。
        baseline_lag: 基準往前推多久（基準和 ``window`` 一樣長）；None＝緊接在 ``window`` 之前、長
            ``BASELINE_WINDOW``（故障出勤卡）。
    """
    start = cutoff - window
    recent_from = cutoff - recent
    if baseline_lag is None:
        baseline_start, baseline_end = start - BASELINE_WINDOW, start
    else:
        baseline_start, baseline_end = start - baseline_lag, cutoff - baseline_lag
    pack = _pack_tags()
    # 截止點那一筆讀值要算進來（讀值的查詢是左閉右開）：它就是建單之後第一批寫進歷史的那一筆
    upto = cutoff + timedelta(microseconds=1)
    mine = _Window(history, turbine_id, tags, start, upto, recent_from)
    baseline = _Window(history, turbine_id, tags, baseline_start, baseline_end)
    peers: List[_Window] = []
    for other in turbines:
        if other == turbine_id:
            continue
        window = _Window(history, other, tags, start, upto, recent_from)
        # 停機中的機組不拿來比：溫度、轉速、功率本來就和發電中的不一樣
        if window.samples and window.producing >= PEER_PRODUCING_FRACTION:
            peers.append(window)
    items: List[Dict[str, object]] = []
    for index, tag in enumerate(tags):
        column = pack[tag]
        floor = SPREAD_FLOOR_OF_RANGE * abs(float(column.tag.sim_max) - float(column.tag.sim_min)) or 1e-6
        value, recent = _number(mine.means[index]), _number(mine.recent[index])
        hourly = [v for v in (_number(p.means[index]) for p in peers) if v is not None]
        latest = [v for v in (_number(p.recent[index]) for p in peers) if v is not None]
        deviation, median = _deviation(value, hourly, floor) if column.is_analog else ("unknown", None)
        recent_deviation, recent_median = (_deviation(recent, latest, floor) if column.is_analog
                                           else ("unknown", None))
        before = _number(baseline.means[index])
        items.append({
            "name": column.name,
            "label_zh": column.tag.label_zh,
            "label_en": column.tag.label_en,
            "unit": column.tag.unit,
            "role": "primary" if tag in primary else "context" if tag in CONTEXT_TAGS else "related",
            "turbine_mean": value,
            "farm_median": median if column.is_analog else None,
            "farm_min": min(hourly) if hourly else None,
            "farm_max": max(hourly) if hourly else None,
            "peer_count": len(hourly),
            # 最近 10 分鐘偏離就算偏離：最後才飆高的訊號在 1 小時平均裡會被稀釋
            "deviation": recent_deviation if recent_deviation in ("high", "low") else deviation,
            "recent_mean": recent,
            # 最後一筆讀值：斷線、卡住這類突然的變化在平均裡看不出來，原值要給
            "last_value": _number(mine.last[index]),
            "recent_farm_median": recent_median if column.is_analog else None,
            "baseline_mean": before,
            "change_from_baseline": (value - before) if value is not None and before is not None else None,
        })
    info: Dict[str, object] = {
        "window": {"start": sp.iso_z(iso_utc(start)), "end": sp.iso_z(iso_utc(cutoff))},
        "recent_window": {"start": sp.iso_z(iso_utc(recent_from)), "end": sp.iso_z(iso_utc(cutoff))},
        "baseline_window": {"start": sp.iso_z(iso_utc(baseline_start)), "end": sp.iso_z(iso_utc(baseline_end))},
        "samples": mine.samples,
        "baseline_samples": baseline.samples,
        "peers": len(peers),
        "last_reading_ts": sp.iso_z(mine.last_ts) if mine.last_ts else None,
        "source": "live readings（與對外 API 的 /readings 相同）",
    }
    return items, info


def _manual(code: Optional[int]) -> Dict[str, object]:
    """手冊對這個事件碼的說明：警報目錄（Z72 手冊 Appendix C）列的原因與處置，照引、不加判斷。"""
    if code is None:
        return {"status": "no_alarm_code"}
    alarm = find_alarm(code)
    if alarm is None:
        return {"status": "not_in_catalog", "code": code}
    return {
        "status": "ok",
        "code": code,
        "level": alarm.level,
        "text": alarm.text,
        "cause": alarm.cause or None,
        "rectification": alarm.rectification or None,
        "max_per_hour": alarm.max_per_hour or None,
        "manual_page": alarm.manual_page or None,
        "source": "Z72 User Manual Appendix C",
    }


def build_fault_card(*, storage: Storage, history: LiveHistory, work_order: WorkOrder, turbine_id: str,
                     turbines: Sequence[str], cutoff: datetime, past_work_orders: Sequence[WorkOrder] = (),
                     generated_late: bool = False) -> Dict[str, object]:
    """產生一張故障出勤卡。只讀資料，不改任何東西。

    Args:
        storage: 風場的 storage（事件）。
        history: 風場的 Live 讀值（歸檔＋SQLite）。
        work_order: 這張卡所屬的工單。
        turbine_id: 模擬器的機組 ID。
        turbines: 同場的機組 ID（含自己）。
        cutoff: 資料截止點（風場時鐘）。
        past_work_orders: 這台機組的其他工單（新的在前）。
        generated_late: 不是在工單建立當下產生的（之後補產生）。

    Returns:
        卡片（可直接轉成 JSON；只含可觀測資料）。
    """
    cutoff = cutoff.astimezone(timezone.utc)
    flags: List[str] = []
    code = alarm_code_of(work_order)

    # 1、2. 事件
    mine, truncated = _alarm_events(storage, cutoff - EVENT_WINDOW, cutoff, turbine_id)
    if truncated:
        flags.append("events_truncated")
    same = [e for e in mine if e["alarm_code"] == code] if code is not None else []
    event = same[-1] if same else None
    if code is None:
        flags.append("no_alarm_code")
    elif event is None:
        flags.append("no_event_found")
    counts: Dict[int, int] = {}
    latest: Dict[int, Dict[str, object]] = {}
    for item in mine:
        other_code = int(str(item["alarm_code"]))
        if other_code == code:
            continue
        counts[other_code] = counts.get(other_code, 0) + 1
        latest[other_code] = item
    others = [{"code": c, "level": latest[c]["alarm_level"], "text": latest[c]["alarm_text"], "count": n,
               "last_ts": latest[c]["ts"]}
              for c, n in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))][:_MAX_LISTED]
    farm_same: List[Dict[str, object]] = []
    if event is not None:
        moment = parse_iso(str(event["ts"]))
        nearby, _ = _alarm_events(storage, moment - FARM_SAME_CODE_WINDOW,
                                  min(moment + FARM_SAME_CODE_WINDOW, cutoff), None)
        seen: Dict[str, str] = {}
        for item in nearby:
            other = str(item["turbine_id"])
            if item["alarm_code"] == code and other != turbine_id and other not in seen:
                seen[other] = str(item["ts"])
        farm_same = [{"turbine_id": other, "ts": ts} for other, ts in sorted(seen.items())]

    # 3. 相關訊號
    primary = related_tags(code)
    tags = list(primary) + [tag for tag in CONTEXT_TAGS if tag not in primary and tag in _pack_tags()]
    if code is not None and not primary:
        flags.append("signals_unmapped")
    items, info = _signal_items(history, turbine_id, turbines, tags, primary[:1], cutoff)
    samples, baseline_samples, peer_count = int(str(info["samples"])), int(str(info["baseline_samples"])), int(
        str(info["peers"]))
    if samples == 0:
        flags.append("signal_data_missing")
    else:
        last = info["last_reading_ts"]
        if last is not None and cutoff - parse_iso(str(last)) > STALE_AFTER:
            flags.append("stale_data")
        if peer_count < MIN_PEERS:
            flags.append("too_few_peers")
    if baseline_samples == 0:
        flags.append("no_baseline")

    state_tag = _pack_tags().get("WTUR_TurSt")
    state: Optional[int] = None
    state_ts: Optional[str] = None
    if state_tag is not None:
        state_rows = history.readings(turbine_id, ["WTUR_TurSt"], start=iso_utc(cutoff - SIGNAL_WINDOW),
                                      end=iso_utc(cutoff + timedelta(microseconds=1)), limit=3000)
        if state_rows and not np.isnan(state_rows[-1].values[0]):
            # 讀值每 10 秒存一筆：跳機當下產生的卡，最後一筆讀值可能還是跳機前的狀態，所以連時間一起給
            state = int(state_rows[-1].values[0])
            state_ts = sp.iso_z(state_rows[-1].timestamp)

    return {
        "card_version": CARD_VERSION,
        "kind": KIND_FAULT_DISPATCH,
        "work_order": {
            "business_key": work_order.business_key,
            "turbine_id": turbine_id,
            "type": work_order.type.value,
            "priority": work_order.priority.value,
            "source_alarm_code": code,
        },
        "data_cutoff": sp.iso_z(iso_utc(cutoff)),
        "generated_late": generated_late,
        "event": {
            "ts": event["ts"], "code": event["alarm_code"], "level": event["alarm_level"],
            "text": event["alarm_text"], "event_id": event["event_id"], "event_type": event["event_type"],
            "turbine_state": state, "turbine_state_ts": state_ts,
        } if event is not None else {"turbine_state": state, "turbine_state_ts": state_ts},
        "recent_events": {
            "window": {"start": sp.iso_z(iso_utc(cutoff - EVENT_WINDOW)), "end": sp.iso_z(iso_utc(cutoff))},
            "same_code": {
                "count": len(same),
                "first_ts": same[0]["ts"] if same else None,
                "last_ts": same[-1]["ts"] if same else None,
                "recent": [e["ts"] for e in same[-_MAX_LISTED:]],
            },
            "other_codes": others,
            "farm_same_code": {"window_minutes": int(FARM_SAME_CODE_WINDOW.total_seconds() // 60),
                               "turbines": farm_same},
            "source": "PLC 事件（與對外 API 的 /events 相同）",
        },
        "signals": {**info, "items": items},
        "past_work_orders": [{
            "business_key": order.business_key,
            "type": order.type.value,
            "status": order.status.value,
            # 工單上的警報碼欄位是自由文字：只給純數字的（同 public_work_order）
            "source_alarm_code": alarm_code_of(order),
            "created_at": iso_utc(order.created_at) if order.created_at else None,
            "finished_at": iso_utc(order.finished_at) if order.finished_at else None,
        } for order in list(past_work_orders)[:_MAX_LISTED]],
        "manual": _manual(code),
        "inventory": {"status": "no_mapping", "note": "目前沒有「警報碼 → 料件」的對應表，卡上不列料件"},
        "data_quality": {"flags": flags, "degraded": bool(flags)},
        "notes": [
            "本卡只整理看得到的資料（讀值、PLC 事件、工單、手冊），不判定根因。",
            "「相關訊號」依 PLC 的判定邏輯挑選；偏高 / 偏低是和同場其他發電中的機組同一時段的平均比"
            "（事件前 1 小時，或最後 10 分鐘）。",
            "工單的時間是實際時間；卡上的資料截止點、事件與讀值的時間是風場時鐘。",
        ],
    }


def capture_answer(simulator: Optional["WindFarmSimulator"], turbine_id: str) -> Dict[str, object]:
    """工單建立當下這台機組實際有哪些故障（評分用的答案，不進卡片、不對外）。

    Args:
        simulator: 即時模擬的模擬器；None＝沒有。
        turbine_id: 機組 ID。

    Returns:
        ``{"faults": [...], "has_fault": bool}``；nuisance 情境不算故障。
    """
    faults: List[Dict[str, object]] = []
    if simulator is not None:
        pack = _pack_tags()
        for fault in simulator.fault_engine.active_faults:
            if fault.turbine_id != turbine_id:
                continue
            scenario = FAULT_SCENARIOS.get(fault.scenario_id)
            keys = [pack[tag].name for tag in (scenario.key_signals if scenario else ()) if tag in pack]
            faults.append({
                "scenario_id": fault.scenario_id,
                "category": scenario.category if scenario else None,
                "component": scenario.component if scenario else None,
                "key_signals": keys,
                "tripped": bool(fault.tripped),
                "severity": float(fault.severity),
            })
    real = [f for f in faults if f["category"] != "nuisance"]
    return {"faults": faults, "has_fault": bool(real)}


def score_card(card: Dict[str, object], answer: Dict[str, object]) -> Dict[str, object]:
    """用答案核對一張卡（規則版的自動評分）。

    - ``key_signal_flagged``：卡上標成偏高 / 偏低的主要 / 相關訊號裡，有沒有故障的重點訊號。這是主要的指標。
    - ``false_escalation``：這台機組其實沒有故障（誤報、外部原因），卡上卻把主要 / 相關訊號標成偏高 / 偏低。
    - ``key_signal_listed``：故障的重點訊號被列在卡上的比例。只當作檢查用：卡上的訊號來自 PLC 的判定
      邏輯，故障的重點訊號多半就是 PLC 看的那個量測，這個比例本來就高，區辨不出好壞。
    - ``degraded_when_missing``：資料有缺時卡片有沒有降級（沒缺時為 None）。

    背景量測（風速、功率、轉速）不算：機組一跳機，功率與轉速本來就和別台不一樣。準備時間能省多少，要等
    真人或真實風場才量得到；這裡只核對證據有沒有指對地方。

    Args:
        card: ``build_fault_card`` 的結果。
        answer: ``capture_answer`` 的結果。

    Returns:
        各項分數。
    """
    signals = card.get("signals")
    raw_items = signals.get("items", []) if isinstance(signals, dict) else []
    items = [item for item in raw_items if isinstance(item, dict)]
    listed = {str(item["name"]) for item in items}
    flagged = {str(item["name"]) for item in items
               if item.get("deviation") in ("high", "low") and item.get("role") in ("primary", "related")}
    raw_faults = answer.get("faults", [])
    faults = [f for f in (raw_faults if isinstance(raw_faults, list) else []) if isinstance(f, dict)]
    real = [f for f in faults if f.get("category") != "nuisance"]
    keys = {str(name) for fault in real for name in fault.get("key_signals", [])}
    quality = card.get("data_quality")
    flags = set(quality.get("flags", [])) if isinstance(quality, dict) else set()
    missing = bool({"signal_data_missing", "stale_data", "no_event_found", "events_truncated"} & flags)
    return {
        "has_fault": bool(real),
        "key_signals": sorted(keys),
        "key_signal_listed": (len(keys & listed) / len(keys)) if keys else None,
        "key_signal_flagged": bool(keys & flagged) if keys else None,
        "flagged": sorted(flagged),
        "false_escalation": bool(flagged) if not real else None,
        "degraded_when_missing": bool(quality.get("degraded")) if missing and isinstance(quality, dict) else None,
    }


# ── 例行巡檢卡（WMOM-20261126-05，DEC-20261127-04）──────────────────────────


def card_kind_for(work_order: WorkOrder) -> Optional[str]:
    """這張工單要哪一種準備卡：故障維修→故障出勤卡；定檢 / 預防保養→例行巡檢卡；試運轉沒有卡。"""
    from modules.workflow.domain import WorkOrderType

    if work_order.type is WorkOrderType.CORRECTIVE:
        return KIND_FAULT_DISPATCH
    if work_order.type in (WorkOrderType.INSPECTION, WorkOrderType.PREVENTIVE):
        return KIND_ROUTINE_INSPECTION
    return None


def build_inspection_card(*, storage: Storage, history: LiveHistory, work_order: WorkOrder, turbine_id: str,
                          turbines: Sequence[str], cutoff: datetime, past_work_orders: Sequence[WorkOrder] = (),
                          generated_late: bool = False) -> Dict[str, object]:
    """產生一張例行巡檢卡：原訂的檢查清單，依證據排順序。只讀資料，不改任何東西。

    證據（都只用看得到的資料，和故障出勤卡同一條邊界）：

    - 最近 30 天這台機組的警報 / 跳機：事件碼屬於清單的哪一項由 PLC 的判定規則推出來；
    - 量測和同場其他發電中的機組比偏高 / 偏低（最近 6 小時，或最後 1 小時）；
    - 這台機組未結案的故障維修工單（帶事件碼的）。

    有證據的項目往前（證據越多越前面），沒有證據的維持原訂順序；整張都沒有證據時順序完全不動。不判定根因、
    不刪項目——排在後面的照樣要檢查。

    Args:
        storage: 風場的 storage（事件）。
        history: 風場的 Live 讀值（歸檔＋SQLite）。
        work_order: 這張卡所屬的工單（定檢或預防保養）。
        turbine_id: 模擬器的機組 ID。
        turbines: 同場的機組 ID（含自己）。
        cutoff: 資料截止點（風場時鐘）。
        past_work_orders: 這台機組的其他工單（新的在前）。
        generated_late: 不是在工單建立當下產生的。

    Returns:
        卡片（可直接轉成 JSON；只含可觀測資料）。
    """
    from server.inspection_checklist import CHECKLIST, item_of_code

    cutoff = cutoff.astimezone(timezone.utc)
    flags: List[str] = []
    pack = _pack_tags()
    evidence: Dict[str, List[Dict[str, object]]] = {item.id: [] for item in CHECKLIST}
    score: Dict[str, int] = {item.id: 0 for item in CHECKLIST}

    # 1. 事件
    events, truncated = _alarm_events(storage, cutoff - INSPECTION_EVENT_WINDOW, cutoff, turbine_id)
    if truncated:
        flags.append("events_truncated")
    by_code: Dict[Tuple[int, str], Dict[str, object]] = {}
    for event in events:
        code = int(str(event["alarm_code"]))
        kind = str(event["event_type"])
        entry = by_code.setdefault((code, kind), {
            "code": code, "level": event["alarm_level"], "text": event["alarm_text"], "event_type": kind,
            "count": 0, "first_ts": event["ts"], "last_ts": event["ts"], "checklist_item": item_of_code(code)})
        entry["count"] = int(str(entry["count"])) + 1
        entry["last_ts"] = event["ts"]
    for entry in by_code.values():
        item_id = entry["checklist_item"]
        if item_id is None:
            continue
        count = int(str(entry["count"]))
        weight = _WEIGHT_TRIP if entry["event_type"] == "trip" else _WEIGHT_ALARM
        score[str(item_id)] += weight * min(count, _MAX_COUNT_PER_CODE)
        evidence[str(item_id)].append({"type": "events", "code": entry["code"], "level": entry["level"],
                                       "text": entry["text"], "event_type": entry["event_type"], "count": count,
                                       "last_ts": entry["last_ts"]})

    # 2. 量測
    tags: List[str] = []
    owner: Dict[str, str] = {}
    for item in CHECKLIST:
        for tag in item.tags:
            if tag in pack and tag not in owner:
                owner[tag] = item.id
                tags.append(tag)
    context = [tag for tag in CONTEXT_TAGS if tag in pack and tag not in owner]
    items, info = _signal_items(history, turbine_id, turbines, tags + context, (), cutoff,
                                window=INSPECTION_SIGNAL_WINDOW, recent=INSPECTION_RECENT_WINDOW,
                                baseline_lag=INSPECTION_BASELINE_LAG)
    names = {pack[tag].name: tag for tag in tags + context}
    for signal in items:
        tag = names.get(str(signal["name"]))
        item_id = owner.get(tag or "")
        signal["checklist_item"] = item_id
        if item_id is None:
            signal["role"] = "context"
            continue
        signal["role"] = "related"
        if signal.get("deviation") in ("high", "low"):
            score[item_id] += _WEIGHT_SIGNAL
            evidence[item_id].append({"type": "signal", "name": signal["name"], "label_zh": signal["label_zh"],
                                      "label_en": signal["label_en"], "unit": signal["unit"],
                                      "deviation": signal["deviation"], "turbine_mean": signal["turbine_mean"],
                                      "recent_mean": signal["recent_mean"], "farm_median": signal["farm_median"]})
    samples, peer_count = int(str(info["samples"])), int(str(info["peers"]))
    if samples == 0:
        flags.append("signal_data_missing")
    else:
        last = info["last_reading_ts"]
        if last is not None and cutoff - parse_iso(str(last)) > STALE_AFTER:
            flags.append("stale_data")
        if peer_count < MIN_PEERS:
            flags.append("too_few_peers")
    if int(str(info["baseline_samples"])) == 0:
        flags.append("no_baseline")

    # 3. 未結案的故障維修工單
    from modules.workflow.domain import WorkOrderType, open_states

    open_statuses = {status.value for status in open_states()}
    for order in past_work_orders:
        if order.type is not WorkOrderType.CORRECTIVE or order.status.value not in open_statuses:
            continue
        item_id = item_of_code(alarm_code_of(order))
        if item_id is None:
            continue
        score[item_id] += _WEIGHT_OPEN_ORDER
        evidence[item_id].append({"type": "open_work_order", "business_key": order.business_key,
                                  "source_alarm_code": alarm_code_of(order), "status": order.status.value})

    # 4. 排順序：有證據的往前（分數高的先），其餘照原訂順序
    defaults = {item.id: index + 1 for index, item in enumerate(CHECKLIST)}
    ordered = sorted(CHECKLIST, key=lambda item: (-score[item.id], defaults[item.id]))
    checklist = [{
        "id": item.id,
        "label_zh": item.label_zh,
        "label_en": item.label_en,
        "default_position": defaults[item.id],
        "position": position + 1,
        "attention": score[item.id] > 0,
        "score": score[item.id],
        "evidence": evidence[item.id],
        "signals": [pack[tag].name for tag in item.tags if tag in pack],
    } for position, item in enumerate(ordered)]
    changed = any(entry["position"] != entry["default_position"] for entry in checklist)
    if not changed:
        flags.append("no_evidence")

    return {
        "card_version": CARD_VERSION,
        "kind": KIND_ROUTINE_INSPECTION,
        "work_order": {
            "business_key": work_order.business_key,
            "turbine_id": turbine_id,
            "type": work_order.type.value,
            "priority": work_order.priority.value,
            "source_alarm_code": alarm_code_of(work_order),
        },
        "data_cutoff": sp.iso_z(iso_utc(cutoff)),
        "generated_late": generated_late,
        "checklist": {"order_changed": changed, "items": checklist},
        "recent_events": {
            "window": {"start": sp.iso_z(iso_utc(cutoff - INSPECTION_EVENT_WINDOW)),
                       "end": sp.iso_z(iso_utc(cutoff))},
            "by_code": sorted(by_code.values(), key=lambda e: (-int(str(e["count"])), int(str(e["code"]))))[
                :_MAX_LISTED * 2],
            "source": "PLC 事件（與對外 API 的 /events 相同）",
        },
        "signals": {**info, "items": items},
        "past_work_orders": [{
            "business_key": order.business_key,
            "type": order.type.value,
            "status": order.status.value,
            "source_alarm_code": alarm_code_of(order),
            "created_at": iso_utc(order.created_at) if order.created_at else None,
            "finished_at": iso_utc(order.finished_at) if order.finished_at else None,
        } for order in list(past_work_orders)[:_MAX_LISTED]],
        # 沒有證據、沒有 7 天前的基準（風場剛開始跑）都不算降級：排序不靠基準
        "data_quality": {"flags": flags, "degraded": bool(set(flags) - {"no_evidence", "no_baseline"})},
        "notes": [
            "本卡只整理看得到的資料（讀值、PLC 事件、工單），不判定根因；排在後面的項目照樣要檢查。",
            "有證據的項目往前：最近 30 天的警報 / 跳機、量測和同場其他發電中的機組比偏高 / 偏低"
            "（最近 6 小時，或最後 1 小時）、未結案的故障維修工單。都沒有證據時維持原訂順序。",
            "事件屬於清單的哪一項，依 PLC 的判定邏輯（事件碼看哪個量測）。",
            "工單的時間是實際時間；卡上的資料截止點、事件與讀值的時間是風場時鐘。",
        ],
    }


def score_inspection_card(card: Dict[str, object], answer: Dict[str, object]) -> Dict[str, object]:
    """用答案核對一張例行巡檢卡（規則版）。

    答案是建單當下這台機組實際有哪些故障——包括還沒到警報門檻的劣化、潛伏的故障。巡檢卡要做的，是在這些故障
    還沒跳機之前，把相關的項目往前排。

    - ``fault_items``：每個故障對到清單的哪一項、原訂第幾、卡上排第幾、有沒有標「注意」。
    - ``moved_up``：至少一個故障的項目比原訂順序前面。
    - ``flagged``：至少一個故障的項目標了「注意」。
    - ``false_attention``：這台機組沒有故障，卡上卻有項目標了「注意」（沒有故障時才有值）。

    Args:
        card: ``build_inspection_card`` 的結果。
        answer: ``capture_answer`` 的結果。

    Returns:
        各項分數。
    """
    from server.inspection_checklist import item_of_component

    checklist = card.get("checklist")
    raw = checklist.get("items", []) if isinstance(checklist, dict) else []
    entries = {str(e["id"]): e for e in raw if isinstance(e, dict)}
    raw_faults = answer.get("faults", [])
    faults = [f for f in (raw_faults if isinstance(raw_faults, list) else [])
              if isinstance(f, dict) and f.get("category") != "nuisance"]
    results: List[Dict[str, object]] = []
    for fault in faults:
        item_id = item_of_component(str(fault.get("component") or ""))
        entry = entries.get(item_id or "")
        results.append({
            "component": fault.get("component"),
            "severity": fault.get("severity"),
            "tripped": fault.get("tripped"),
            "item": item_id,
            "default_position": entry.get("default_position") if entry else None,
            "position": entry.get("position") if entry else None,
            "attention": bool(entry.get("attention")) if entry else None,
        })
    attention = [e for e in entries.values() if e.get("attention")]
    placed = [r for r in results if r["position"] is not None]
    return {
        "has_fault": bool(faults),
        "fault_items": results,
        "moved_up": any(int(str(r["position"])) < int(str(r["default_position"])) for r in placed) if placed else None,
        "flagged": any(r["attention"] for r in placed) if placed else None,
        "attention_items": sorted(str(e["id"]) for e in attention),
        "false_attention": bool(attention) if not faults else None,
    }


def score_any_card(card: Dict[str, object], answer: Dict[str, object]) -> Dict[str, object]:
    """依卡片種類核對。"""
    if card.get("kind") == KIND_ROUTINE_INSPECTION:
        return score_inspection_card(card, answer)
    return score_card(card, answer)


def public_work_order(order: WorkOrder, turbine_id: Optional[str] = None) -> Dict[str, object]:
    """工單給外部看的樣子：只有結構化欄位，沒有標題、說明、施工摘要這些自由文字。

    Args:
        order: 工單。
        turbine_id: 模擬器的機組 ID（工單上是畫面名稱時換成這個）；None＝照工單上的。

    Returns:
        可直接轉成 JSON 的 dict。
    """
    def stamp(value: Optional[datetime]) -> Optional[str]:
        return sp.iso_z(iso_utc(value)) if value is not None else None

    return {
        "business_key": order.business_key,
        "turbine_id": turbine_id or order.turbine_id,
        "type": order.type.value,
        "status": order.status.value,
        "priority": order.priority.value,
        "source_alarm_code": alarm_code_of(order),
        "created_at": stamp(order.created_at),
        "dispatched_at": stamp(order.dispatched_at),
        "started_at": stamp(order.started_at),
        "finished_at": stamp(order.finished_at),
        "closed_at": stamp(order.closed_at),
    }


def _utc(moment: datetime) -> datetime:
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)


def past_orders(repository: "WorkOrderRepository", farm_id: str, names: Sequence[str],
                exclude: WorkOrder, before: Optional[datetime] = None) -> List[WorkOrder]:
    """這台機組的其他工單，新的在前。

    Args:
        repository: 工單 repository。
        farm_id: 風場 ID。
        names: 這台機組在工單上可能用的名稱（模擬器 ID 與畫面名稱）。
        exclude: 這張卡所屬的工單。
        before: 只取這個時間（實際時間）以前建立的；None＝不限。卡片在背景做的時候，這張工單之後才開的
            單不算「以前的工單」。

    Returns:
        工單（最多 ``_MAX_LISTED`` 張）。
    """
    limit = _utc(before) if before is not None else None
    found: Dict[str, WorkOrder] = {}
    for name in names:
        orders, _total = repository.list(farm_id=farm_id, turbine_id=name, limit=50)
        for order in orders:
            if order.id == exclude.id:
                continue
            if limit is not None and order.created_at is not None and _utc(order.created_at) > limit:
                continue
            found[str(order.id)] = order
    ordered = sorted(found.values(), key=lambda o: _utc(o.created_at), reverse=True)
    return ordered[:_MAX_LISTED]
