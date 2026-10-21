"""情境資料包匯出（WMOM-20261021-05，EPIC-DS Phase 3a ① 檔案）。

把一個凍結情境（命名情境 session）匯出成設計文件 §5.1 的資料包目錄：

```
{pack_id}/
  manifest.json          合約版本、機型、機組、時間窗、取樣週期、統計慣例、各檔 sha256
  tag_dictionary.json    tag → 單位、說明、source: bachmann_real | synthetic
  alarm_catalog.json     Z72 警報目錄快照（全部 314 碼）
  timeseries_raw.parquet timestamp(UTC), turbine_id, <Bachmann tag 名>...
  stats_10min.parquet    window_start / window_end(UTC), turbine_id, n_samples, is_partial,
                         <tag>_avg/_min/_max/_std
  events.jsonl           可觀測事件（PLC 事件 + 運轉狀態轉換），不含答案；每行欄位相同
  ground_truth.json      標準答案——只有評分端版本才有（include_ground_truth）
```

盲測（設計文件 §4 原則 2）：
- 事件只匯出 ``storage.is_observable_event`` 白名單內的；不帶模擬器內部的訊號值 / 設定值。
- manifest 不帶情境名稱、故障排程、注入數（這些都寫明故障）；風況只輸出已知的 profile 名。
- 狀態轉換的停機原因正規化成 PLC 看得到的類別（``plc_trip`` / ``high_wind`` …），模擬器內部詞彙
  （例：``maintenance_lock``）不輸出。
- 模擬器內部量（尾流 / 大氣模型狀態、疲勞累積損傷與壽命、齒面磨耗指數…）不進資料包
  （``MODEL_INTERNAL_TAGS``，DEC-20261021-03）：真實 Z72 沒有，且會直接透露故障嚴重度。

時間戳一律 UTC、以 ``Z`` 結尾（合約 §5.1）；Parquet 用 ``timestamp[us, tz=UTC]``。raw 分批讀、
串流寫出；10 分鐘統計逐窗計算，記憶體與 raw 筆數無關（只與窗數成正比：每窗每 tag 4 個 float32）。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
import warnings
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

try:
    from ..simulator.ground_truth import CONTRACT_VERSION
    from ..simulator.physics.scada_registry import SCADA_REGISTRY, ScadaTag
    from ..simulator.time_utils import parse_iso, utc_now
    from .storage import Storage, is_observable_event
except ImportError:  # sys.path 注入模式（modules/monitoring 在 sys.path）
    from simulator.ground_truth import CONTRACT_VERSION  # type: ignore[no-redef]
    from simulator.physics.scada_registry import SCADA_REGISTRY, ScadaTag  # type: ignore[no-redef]
    from simulator.time_utils import parse_iso, utc_now  # type: ignore[no-redef]
    from server.storage import Storage, is_observable_event  # type: ignore[no-redef]

from shared.alarm_codes import all_alarms  # noqa: E402  （simulator 匯入時已補 repo root 到 sys.path）
from shared.plc_tags import is_real_plc_tag  # noqa: E402

STATS_WINDOW_S = 600
TURBINE_MODEL = "Z72"
# 資料包內容 / 產生方式有變（欄位、統計慣例、物理語意）就遞增，讓評分端分得出不同版的資料
EXPORTER_VERSION = "1"
FILE_MANIFEST = "manifest.json"
FILE_TAGS = "tag_dictionary.json"
FILE_ALARMS = "alarm_catalog.json"
FILE_RAW = "timeseries_raw.parquet"
FILE_STATS = "stats_10min.parquet"
FILE_EVENTS = "events.jsonl"
FILE_GROUND_TRUTH = "ground_truth.json"

# 模擬器內部量：模型狀態或預測輸出，不是 SCADA / CMS 量得到的訊號（DEC-20261021-03）。
# 真實 Z72 沒有這些 tag；其中磨耗 / 損傷 / 壽命等於直接給出劣化程度，盲測不能給。
# 塔架 / 葉片彎矩與 DEL 保留：負載監測系統量得到，且是兩個故障情境的 key signal。
MODEL_INTERNAL_TAGS: FrozenSet[str] = frozenset({
    # 尾流 / 大氣模型狀態
    "WMET_LocalTi", "WMET_WakeDef", "WMET_WakeMndr", "WMET_WakeDefl", "WMET_WakeTi",
    "WMET_ShearAlpha", "WMET_AtmStab",
    # 疲勞累積損傷、剩餘壽命與其警報等級
    "WLOD_DmgTwrFa", "WLOD_DmgTwrSs", "WLOD_DmgBldFlap", "WLOD_DmgBldEdge", "WLOD_RulHours",
    "WLOD_AlmTwr", "WLOD_AlmBld",
    # 由機組個體差異參數算出的不平衡力（現場只看得到 1P 振動）、齒面磨耗累積狀態（齒輪箱過熱會加速）
    "WROT_ImbForce", "WDRV_GbxToothWear",
})
# 0–360° 方位角：10 分鐘 avg 用圓平均、std 用 Yamartino（min / max 仍為線性值）
CIRCULAR_TAGS: FrozenSet[str] = frozenset({"WMET_WDirAbs"})
# 模擬值與真實 Z72 同名 tag 語意不同之處（寫進 tag 字典的 note）
TAG_NOTES: Dict[str, str] = {
    "WMET_WSpeedNac": (
        "Simulated free-stream wind speed at the rotor (wake deficit applied, no nacelle anemometer error). "
        "On a real Z72 this tag is the nacelle anemometer reading; the simulated anemometer reading "
        "(nacelle transfer function applied) is Z72PLC__UI_Loc_WMET_Analogue_WSpeedRaw."
    ),
    "WMET_WDirAbs": (
        "Simulated true wind direction (0-360 deg) from the wind field, not a vane reading combined with "
        "nacelle position. 10-minute avg is a circular mean and std is Yamartino; min/max are linear."
    ),
}
# 風況 profile（routers/config.py::set_wind、wind_model.py）；其他值可能是出題者自訂文字，不輸出
KNOWN_WIND_PROFILES: FrozenSet[str] = frozenset({
    "calm", "moderate", "rated", "strong", "storm", "gusty", "ramp_up", "ramp_down", "auto",
})

# Bachmann TurSt（1-9）的狀態名稱，與 DataBroker._state_name 一致（測試會比對）
STATE_NAMES: Dict[int, str] = {
    1: "Shutdown", 2: "Standby", 3: "Wait Restart", 4: "Pre-Production", 5: "Synchronization",
    6: "Production", 7: "Emergency Stop", 8: "Restart", 9: "Normal Stop",
}
_STOP_STATES = (7, 9)
# PLC 事件種類 → 合約 event_type（v0 的 reset 對應操作員復位；解除 / 封鎖 / 資訊為 v0.1 擴充）
_PLC_EVENT_TYPES: Dict[str, str] = {
    "alarm_raised": "alarm_raised",
    "alarm_cleared": "alarm_cleared",
    "trip": "trip",
    "trip_cleared": "trip_cleared",
    "restart_blocked": "restart_blocked",
    "operator_reset": "reset",
    "info": "info",
}
# events.jsonl 每行都有這些欄位（不適用者為 null）：逐行推斷 schema 的讀取器（polars 等）不會掉欄
EVENT_KEYS: Tuple[str, ...] = (
    "ts", "turbine_id", "event_type",
    "alarm_code", "alarm_level", "alarm_text", "event_id", "plc_tag",
    "from_state", "to_state", "from_state_name", "to_state_name", "stop_reason",
)
_ARROW_TYPES: Dict[str, pa.DataType] = {
    "REAL32": pa.float32(),
    "SINT16": pa.int16(),
    "UINT16": pa.uint16(),
    "BOOL": pa.bool_(),
}
_READ_BATCH_ROWS = 5000
_ROW_GROUP_ROWS = 50_000
_TS_TYPE = pa.timestamp("us", tz="UTC")

JsonValue = object  # JSON 可序列化值（dict / list / str / 數字 / None）


class ScenarioPackError(ValueError):
    """情境不能匯出（不存在、生成未完成、事件沒有 session 隔離、沒有資料）。

    Attributes:
        status_code: 對應的 HTTP 狀態碼（404 不存在、409 狀態不允許）。
    """

    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class PackColumn:
    """資料包的一個 tag 欄位。

    Attributes:
        tag: 模擬器 SCADA tag 定義。
        name: 欄位名稱＝Bachmann PLC tag 名（不含 OPC 分組前綴）。
        arrow_type: Parquet 型別（依 PLC 資料型別）。
        is_analog: REAL32（10 分鐘統計給 avg / min / max / std；其餘只給 min / max）。
        is_circular: 0–360° 方位角（avg / std 用圓統計）。
    """

    tag: ScadaTag
    name: str
    arrow_type: pa.DataType
    is_analog: bool
    is_circular: bool = False


def pack_columns() -> List[PackColumn]:
    """資料包的 tag 欄位（依 SCADA 註冊表順序，排除 ``MODEL_INTERNAL_TAGS``）。

    Returns:
        欄位定義。
    """
    return [
        PackColumn(tag=tag, name=tag.opc_tag.split(".", 1)[-1], arrow_type=_ARROW_TYPES[tag.data_type],
                   is_analog=tag.data_type == "REAL32", is_circular=tag.id in CIRCULAR_TAGS)
        for tag in SCADA_REGISTRY.all_tags
        if tag.id not in MODEL_INTERNAL_TAGS
    ]


def iso_z(value: str) -> str:
    """ISO 時間字串 → 固定格式 ``YYYY-MM-DDTHH:MM:SS.ffffffZ``（UTC）。

    Args:
        value: 任意 ISO 字串（``+00:00`` / ``Z`` / 其他時區）。

    Returns:
        ``Z`` 結尾的 UTC 字串。
    """
    return parse_iso(value).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def pack_id_for(scenario_id: int) -> str:
    """資料包 ID。

    Args:
        scenario_id: 情境 session id。

    Returns:
        例 ``z72-scenario-00012``（不帶情境名稱：名稱是出題者自訂，可能寫明故障）。
    """
    return f"z72-scenario-{scenario_id:05d}"


def pack_file_names(include_ground_truth: bool) -> List[str]:
    """資料包內的檔案（壓縮成 zip 時的順序）。

    Args:
        include_ground_truth: 是否含標準答案。

    Returns:
        檔名。
    """
    names = [FILE_MANIFEST, FILE_TAGS, FILE_ALARMS, FILE_RAW, FILE_STATS, FILE_EVENTS]
    return names + [FILE_GROUND_TRUTH] if include_ground_truth else names


# ── 檔案內容 ─────────────────────────────────────────────────────────────────


def tag_dictionary(columns: Sequence[PackColumn]) -> List[Dict[str, JsonValue]]:
    """tag 字典：每個欄位的單位、說明、資料型別與真實性。

    Args:
        columns: 資料包欄位。

    Returns:
        依欄位順序的 tag 說明。
    """
    return [
        {
            "tag": col.name,
            "opc_path": col.tag.opc_tag,
            "id": col.tag.id,
            "subsystem": col.tag.subsystem,
            "data_type": col.tag.data_type,
            "unit": col.tag.unit,
            "label_en": col.tag.label_en,
            "label_zh": col.tag.label_zh,
            "source": "bachmann_real" if is_real_plc_tag(col.name) else "synthetic",
            "note": TAG_NOTES.get(col.tag.id),
        }
        for col in columns
    ]


def alarm_catalog_snapshot() -> Dict[str, JsonValue]:
    """Z72 警報目錄快照（全部事件碼）。

    Returns:
        ``{"turbine_model", "source", "events": [...]}``。
    """
    return {
        "turbine_model": TURBINE_MODEL,
        "source": "docs/1040610-Z72_PLC_OPC_TAG_1040510.xlsx + Z72 User Manual Appendix C",
        "events": [
            {
                "code": a.code,
                "event_id": a.event_id,
                "level": a.level,
                "text": a.text,
                "plc_tag": a.plc_tag,
                "cause": a.cause,
                "rectification": a.rectification,
                "max_per_hour": a.max_per_hour,
                "manual_page": a.manual_page,
            }
            for a in all_alarms()
        ],
    }


def stop_reason(shutdown_cause: Optional[str]) -> Optional[str]:
    """機組回報的停機原因 → PLC 看得到的停機類別（模擬器內部詞彙不輸出）。

    Args:
        shutdown_cause: ``TurbinePhysicsModel`` 的停機原因（例 ``plc:240``、``cut_out``）。

    Returns:
        ``plc_trip`` / ``high_wind`` / ``low_wind`` / ``grid`` / ``overspeed`` / ``operator``；
        其他（例 ``maintenance_lock``、``idle``）回 None。
    """
    if not shutdown_cause:
        return None
    if shutdown_cause.startswith("plc:"):
        return "plc_trip"
    if shutdown_cause == "cut_out":
        return "high_wind"
    if shutdown_cause in ("low_wind", "below_cut_in"):
        return "low_wind"
    if shutdown_cause in ("grid_trip", "grid_protection") or shutdown_cause.startswith("ride_through:"):
        return "grid"
    if shutdown_cause.startswith("overspeed"):
        return "overspeed"
    if shutdown_cause in ("operator", "operator_emergency", "service"):
        return "operator"
    return None


def pack_event(event: Dict[str, JsonValue]) -> Optional[Dict[str, JsonValue]]:
    """``history_events`` 的一筆可觀測事件 → 資料包 ``events.jsonl`` 的一行。

    Args:
        event: ``storage.session_events`` 的事件（呼叫端已確認 ``is_observable_event``）。

    Returns:
        合約格式的事件（``EVENT_KEYS`` 全部都有，不適用者為 None）；無法對應者回 None。
    """
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    out: Dict[str, JsonValue] = dict.fromkeys(EVENT_KEYS)
    out["ts"] = iso_z(str(event["timestamp"]))
    out["turbine_id"] = event.get("turbine_id")
    if event.get("source") == "plc":
        event_type = _PLC_EVENT_TYPES.get(str(payload.get("kind")))
        if event_type is None:
            return None
        out.update(
            event_type=event_type,
            alarm_code=payload.get("code"),
            alarm_level=payload.get("level"),
            alarm_text=payload.get("text"),
            event_id=payload.get("eventId"),
            plc_tag=payload.get("plcTag"),
        )
        return out
    from_state, to_state = payload.get("fromState"), payload.get("toState")
    if not isinstance(from_state, int) or not isinstance(to_state, int):
        return None
    out.update(
        event_type="state_change",
        from_state=from_state,
        to_state=to_state,
        from_state_name=STATE_NAMES.get(from_state),
        to_state_name=STATE_NAMES.get(to_state),
        stop_reason=stop_reason(payload.get("shutdownCause")) if to_state in _STOP_STATES else None,
    )
    return out


def ground_truth_for_pack(ground_truth: Dict[str, JsonValue], pack_id: str) -> Dict[str, JsonValue]:
    """存好的標準答案 → 資料包版本（加 ``pack_id``、時間戳統一 ``Z``）。

    Args:
        ground_truth: ``storage.get_ground_truth`` 的結果。
        pack_id: 資料包 ID。

    Returns:
        新的 dict（不改動輸入）。
    """
    def z(value: JsonValue) -> JsonValue:
        return iso_z(value) if isinstance(value, str) and value else value

    out = json.loads(json.dumps(ground_truth))
    out["pack_id"] = pack_id
    for key in ("sim_start", "sim_end", "generated_at"):
        out[key] = z(out.get(key))
    for case in out.get("cases") or []:
        for key in ("onset_ts", "first_alarm_ts", "trip_ts"):
            case[key] = z(case.get(key))
    for item in out.get("unattributed_events") or []:
        item["ts"] = z(item.get("ts"))
    return out


def stats_convention(columns: Sequence[PackColumn]) -> Dict[str, JsonValue]:
    """10 分鐘統計的慣例（寫進 manifest，讀者不必猜窗的邊界與算法）。

    Args:
        columns: 資料包欄位。

    Returns:
        慣例說明。
    """
    return {
        "window_s": STATS_WINDOW_S,
        "alignment": "UTC, aligned to whole 10-minute boundaries",
        "interval": "left-closed [window_start, window_end)",
        "label": "window_start",
        "std_ddof": 1,
        "partial_window": "is_partial = n_samples < floor(window_s / sample_period_s); first/last windows and "
                          "gaps are partial",
        "analog_stats": ["avg", "min", "max", "std"],
        "discrete_stats": ["min", "max"],
        "circular_tags": [col.name for col in columns if col.is_circular],
        "circular_method": "avg = circular mean (0-360), std = Yamartino; min/max linear",
        "missing_values": "ignored; a window with no valid value gives null",
    }


# ── raw 與 10 分鐘統計 ─────────────────────────────────────────────────────────


@dataclass
class _Window:
    """一台機組目前累積中的 10 分鐘窗。"""

    start_s: int
    rows: List[np.ndarray] = field(default_factory=list)


@dataclass
class _StatsRow:
    """一個完成的 10 分鐘窗（統計值以 float32 保存，與輸出精度相同）。"""

    start_s: int
    turbine_id: str
    n_samples: int
    avg: np.ndarray
    mn: np.ndarray
    mx: np.ndarray
    std: np.ndarray


def _circular_mean_std(degrees: np.ndarray) -> Tuple[float, float]:
    """方位角（度）的圓平均與 Yamartino 標準差；缺值忽略。"""
    values = degrees[~np.isnan(degrees)]
    if len(values) == 0:
        return math.nan, math.nan
    rad = np.deg2rad(values)
    s, c = float(np.mean(np.sin(rad))), float(np.mean(np.cos(rad)))
    mean = math.degrees(math.atan2(s, c)) % 360.0
    if mean >= 360.0:  # -1e-15 % 360 進位成 360.0
        mean = 0.0
    if len(values) < 2:
        return mean, math.nan
    eps = math.sqrt(max(0.0, 1.0 - (s * s + c * c)))
    std = math.degrees(math.asin(min(1.0, eps)) * (1.0 + (2.0 / math.sqrt(3.0) - 1.0) * eps ** 3))
    return mean, std


@dataclass
class _StatsBuilder:
    """逐窗計算 10 分鐘統計（每台機組的讀值依時間進來，窗滿就算，不保留 raw）。"""

    columns: Sequence[PackColumn]
    open_windows: Dict[str, _Window] = field(default_factory=dict)
    out_rows: List[_StatsRow] = field(default_factory=list)
    _last_epoch: Dict[str, float] = field(default_factory=dict)
    _steps: Counter[float] = field(default_factory=Counter)  # 相鄰讀值間隔（秒，取到 ms）→ 次數

    def add(self, epoch_s: float, turbine_id: str, values: np.ndarray) -> None:
        prev = self._last_epoch.get(turbine_id)
        if prev is not None:
            self._steps[round(epoch_s - prev, 3)] += 1
        self._last_epoch[turbine_id] = epoch_s
        start = int(math.floor(epoch_s / STATS_WINDOW_S) * STATS_WINDOW_S)
        window = self.open_windows.get(turbine_id)
        if window is not None and window.start_s != start:
            self._flush(turbine_id, window)
            window = None
        if window is None:
            window = self.open_windows[turbine_id] = _Window(start_s=start)
        window.rows.append(values)

    @property
    def sample_period_s(self) -> Optional[float]:
        """資料實際的取樣週期（最常見的相鄰讀值間隔）；每台機組都只有一筆時為 None。"""
        if not self._steps:
            return None
        return float(self._steps.most_common(1)[0][0])

    def finish(self) -> None:
        for turbine_id, window in list(self.open_windows.items()):
            self._flush(turbine_id, window)
        self.open_windows.clear()
        self.out_rows.sort(key=lambda r: (r.start_s, r.turbine_id))

    def _flush(self, turbine_id: str, window: _Window) -> None:
        data = np.vstack(window.rows)
        # 整窗都是缺值時 nanmean / nanmin 會警告（結果 NaN → 輸出 null），不洗版
        with np.errstate(invalid="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            avg = np.nanmean(data, axis=0)
            mn = np.nanmin(data, axis=0)
            mx = np.nanmax(data, axis=0)
            std = np.nanstd(data, axis=0, ddof=1) if len(data) > 1 else np.full(data.shape[1], np.nan)
        for c, col in enumerate(self.columns):
            if col.is_circular:
                avg[c], std[c] = _circular_mean_std(data[:, c])
        self.out_rows.append(_StatsRow(
            start_s=window.start_s, turbine_id=turbine_id, n_samples=len(data),
            avg=avg.astype(np.float32), mn=mn.astype(np.float32), mx=mx.astype(np.float32),
            std=std.astype(np.float32),
        ))

    def table(self, sample_period_s: Optional[float]) -> pa.Table:
        """統計表。

        Args:
            sample_period_s: 取樣週期（判定殘缺窗）；None＝無法判定，``is_partial`` 為 null。

        Returns:
            依 (window_start, turbine_id) 排序的統計表。
        """
        rows = self.out_rows
        full = int(math.floor(STATS_WINDOW_S / sample_period_s + 1e-9)) if sample_period_s else None
        starts = np.array([r.start_s for r in rows], dtype=np.int64) * 1_000_000
        arrays: List[pa.Array] = [
            pa.array(starts, type=_TS_TYPE),
            pa.array(starts + STATS_WINDOW_S * 1_000_000, type=_TS_TYPE),
            pa.array([r.turbine_id for r in rows], type=pa.string()),
            pa.array([r.n_samples for r in rows], type=pa.int32()),
            pa.array([None if full is None else r.n_samples < full for r in rows], type=pa.bool_()),
        ]
        names = ["window_start", "window_end", "turbine_id", "n_samples", "is_partial"]
        n_cols = len(self.columns)
        stacked = {
            key: (np.vstack([getattr(r, key) for r in rows]) if rows else np.empty((0, n_cols), dtype=np.float32))
            for key in ("avg", "mn", "mx", "std")
        }
        for c, col in enumerate(self.columns):
            stats = (("avg", "avg"), ("min", "mn"), ("max", "mx"), ("std", "std")) if col.is_analog \
                else (("min", "mn"), ("max", "mx"))
            for suffix, key in stats:
                arrays.append(_to_arrow(stacked[key][:, c], col.arrow_type))
                names.append(f"{col.name}_{suffix}")
        return pa.Table.from_arrays(arrays, names=names)


def _to_arrow(values: np.ndarray, arrow_type: pa.DataType) -> pa.Array:
    """數值陣列（NaN＝缺值）→ 指定型別的 Arrow 陣列（缺值為 null；整數超出範圍會報錯）。"""
    values = np.asarray(values, dtype=np.float64)
    mask = np.isnan(values)
    if arrow_type == pa.float32():
        return pa.array(values.astype(np.float32), mask=mask, type=arrow_type)
    filled = np.where(mask, 0.0, values)
    if arrow_type == pa.bool_():
        return pa.array(filled != 0.0, mask=mask, type=arrow_type)
    return pa.array(np.rint(filled).astype(np.int64), mask=mask, type=pa.int64()).cast(arrow_type)


def _raw_schema(columns: Sequence[PackColumn]) -> pa.Schema:
    fields = [pa.field("timestamp", _TS_TYPE), pa.field("turbine_id", pa.string())]
    fields += [pa.field(col.name, col.arrow_type) for col in columns]
    return pa.schema(fields)


def _scada_values(scada_json: Optional[str], ids: Sequence[str]) -> np.ndarray:
    """一筆讀值的 tag 值（缺、非數值、非有限值 → NaN）。"""
    out = np.full(len(ids), np.nan)
    if not scada_json:
        return out
    try:
        scada = json.loads(scada_json)
    except (json.JSONDecodeError, TypeError):
        return out
    if not isinstance(scada, dict):
        return out
    for c, tag_id in enumerate(ids):
        value = scada.get(tag_id)
        if isinstance(value, (int, float)) and math.isfinite(value):
            out[c] = float(value)
    return out


@dataclass
class _RawResult:
    """raw / 統計寫完後的摘要。"""

    raw_rows: int
    stats_rows: int
    partial_windows: int
    turbines: List[str]
    first_ts: str
    last_ts: str
    sample_period_s: Optional[float]


def _write_raw_and_stats(storage: Storage, scenario_id: int, columns: Sequence[PackColumn], raw_path: Path,
                         stats_path: Path, fallback_period_s: Optional[float]) -> _RawResult:
    """串流寫出 raw Parquet，同時逐窗算 10 分鐘統計。

    Args:
        storage: 情境所在的 storage。
        scenario_id: 情境 session id。
        columns: 資料包欄位。
        raw_path: raw Parquet 路徑。
        stats_path: 統計 Parquet 路徑。
        fallback_period_s: 資料推不出取樣週期時用（情境設定的 ``time_step``）。

    Returns:
        摘要（呼叫端已確認情境有讀值）。
    """
    schema = _raw_schema(columns)
    stats = _StatsBuilder(columns=columns)
    turbines: Set[str] = set()
    first_ts: Optional[str] = None
    last_ts: Optional[str] = None
    rows_written = 0
    ids = [col.tag.id for col in columns]
    pending: List[pa.Table] = []
    pending_rows = 0
    with pq.ParquetWriter(str(raw_path), schema) as writer:
        for batch in storage.iter_session_readings(scenario_id, _READ_BATCH_ROWS):
            micros = np.empty(len(batch), dtype=np.int64)
            turbine_col: List[str] = []
            matrix = np.empty((len(batch), len(columns)))
            for r, row in enumerate(batch):
                epoch = parse_iso(row["timestamp"]).timestamp()
                micros[r] = int(round(epoch * 1_000_000))
                tid = str(row["turbine_id"])
                turbine_col.append(tid)
                turbines.add(tid)
                matrix[r] = _scada_values(row["scada_json"], ids)
                stats.add(epoch, tid, matrix[r].copy())
                if first_ts is None:
                    first_ts = row["timestamp"]
                last_ts = row["timestamp"]
            arrays: List[pa.Array] = [pa.array(micros, type=_TS_TYPE), pa.array(turbine_col, type=pa.string())]
            arrays += [_to_arrow(matrix[:, c], col.arrow_type) for c, col in enumerate(columns)]
            pending.append(pa.Table.from_arrays(arrays, schema=schema))
            pending_rows += len(batch)
            rows_written += len(batch)
            if pending_rows >= _ROW_GROUP_ROWS:
                writer.write_table(pa.concat_tables(pending))
                pending, pending_rows = [], 0
        if pending:
            writer.write_table(pa.concat_tables(pending))
    stats.finish()
    period = stats.sample_period_s or fallback_period_s
    stats_table = stats.table(period)
    pq.write_table(stats_table, str(stats_path))
    partial = sum(1 for v in stats_table.column("is_partial").to_pylist() if v)
    assert first_ts is not None and last_ts is not None  # 呼叫端已確認有讀值
    return _RawResult(raw_rows=rows_written, stats_rows=stats_table.num_rows, partial_windows=partial,
                      turbines=sorted(turbines), first_ts=first_ts, last_ts=last_ts, sample_period_s=period)


# ── 匯出 ─────────────────────────────────────────────────────────────────────


def _write_text(path: Path, text: str) -> None:
    # 固定 LF：Windows 上匯出的資料包與 Linux 的位元相同（sha256 才比得起來）
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _write_json(path: Path, data: JsonValue) -> None:
    _write_text(path, json.dumps(data, ensure_ascii=False, indent=1) + "\n")


def _file_digest(path: Path) -> Dict[str, JsonValue]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return {"sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def _load_exportable_scenario(storage: Storage, scenario_id: int, max_rows: Optional[int]) -> Dict[str, JsonValue]:
    """取情境並確認可以匯出。

    Raises:
        ScenarioPackError: 不存在（404）、生成未成功、事件沒有 session 隔離、沒有讀值（409）、
            raw 超過 ``max_rows``（413）。
    """
    scenario = storage.get_scenario(scenario_id)
    if scenario is None:
        raise ScenarioPackError(f"Scenario {scenario_id} not found", status_code=404)
    config = scenario.get("config") if isinstance(scenario.get("config"), dict) else {}
    if config.get("status") != "ok":
        raise ScenarioPackError(f"Scenario {scenario_id} did not finish generating (status={config.get('status')!r})")
    if config.get("events_session_isolated") is not True:
        # 舊情境的事件沒有 session，靠時間窗撈會混進其他情境的事件，也沒有標準答案：不匯出半套資料
        raise ScenarioPackError(
            f"Scenario {scenario_id} was generated before WMOM-20261021-04 (no session-isolated events / "
            "ground truth); regenerate it to export a pack"
        )
    rows = storage.count_session_readings(scenario_id)
    if rows == 0:
        raise ScenarioPackError(f"Scenario {scenario_id} has no readings")
    if max_rows is not None and rows > max_rows:
        raise ScenarioPackError(
            f"Scenario {scenario_id} has {rows} readings (limit {max_rows}); export it with "
            "tools/export_scenario_pack.py",
            status_code=413,
        )
    return scenario


def _positive_number(value: JsonValue) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else None


def _write_pack_files(storage: Storage, scenario: Dict[str, JsonValue], scenario_id: int, pack_id: str,
                      out_dir: Path, ground_truth: Optional[Dict[str, JsonValue]]) -> Dict[str, JsonValue]:
    """把資料包所有檔案寫進 ``out_dir``（空目錄），回傳 manifest。"""
    config = scenario["config"]
    assert isinstance(config, dict)
    columns = pack_columns()
    raw = _write_raw_and_stats(storage, scenario_id, columns, out_dir / FILE_RAW, out_dir / FILE_STATS,
                               _positive_number(config.get("time_step")))

    events: List[Dict[str, JsonValue]] = []
    dropped = 0
    for event in storage.session_events(scenario_id):
        if not is_observable_event(event):
            continue
        packed = pack_event(event)
        if packed is None:
            dropped += 1  # 白名單內、但合約還沒有對應格式的事件（新 PLC 事件種類等）
        else:
            events.append(packed)
    _write_text(out_dir / FILE_EVENTS, "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events))
    _write_json(out_dir / FILE_TAGS, {"turbine_model": TURBINE_MODEL, "tags": tag_dictionary(columns)})
    _write_json(out_dir / FILE_ALARMS, alarm_catalog_snapshot())

    files = [FILE_TAGS, FILE_ALARMS, FILE_RAW, FILE_STATS, FILE_EVENTS]
    if ground_truth is not None:
        _write_json(out_dir / FILE_GROUND_TRUTH, ground_truth_for_pack(ground_truth, pack_id))
        files.append(FILE_GROUND_TRUTH)

    wind_profile = config.get("wind_profile")
    manifest: Dict[str, JsonValue] = {
        "contract_version": CONTRACT_VERSION,
        "pack_id": pack_id,
        "turbine_model": TURBINE_MODEL,
        "turbines": raw.turbines,
        # 第一 / 最後一筆讀值的時間（每筆讀值是該步結束時的狀態）
        "sim_start": iso_z(raw.first_ts),
        "sim_end": iso_z(raw.last_ts),
        "sample_period_s": raw.sample_period_s,
        "stats_window_s": STATS_WINDOW_S,
        "stats_convention": stats_convention(columns),
        "duration_hours": config.get("duration_hours"),
        "site_timezone": config.get("site_timezone"),
        "wind_profile": wind_profile if wind_profile in KNOWN_WIND_PROFILES else None,
        "rated_power_kw": scenario.get("rated_power_kw"),
        "ground_truth_included": ground_truth is not None,
        "generator": {
            "name": "windMindOM",
            "exporter_version": EXPORTER_VERSION,
            "simulator": "modules/monitoring (Z72 physics + PLC protection)",
        },
        "reproducibility": {
            "seed": None,
            "note": "Generated from the live simulator state at generation time; not reproducible from this "
                    "manifest alone (WMOM-20261021-05 known limitation).",
        },
        "counts": {
            "raw_rows": raw.raw_rows,
            "stats_rows": raw.stats_rows,
            "partial_windows": raw.partial_windows,
            "events": len(events),
            "events_dropped": dropped,
        },
        "files": {name: _file_digest(out_dir / name) for name in files},
        "exported_at": utc_now().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }
    _write_json(out_dir / FILE_MANIFEST, manifest)
    return manifest


def export_scenario_pack(storage: Storage, scenario_id: int, out_dir: Path, *, include_ground_truth: bool = False,
                         max_rows: Optional[int] = None) -> Dict[str, JsonValue]:
    """把情境匯出成資料包目錄。

    先寫到同層的暫存目錄，全部成功才搬進 ``out_dir``（manifest 最後搬）：中途失敗不會留下半套資料包，
    重匯出時也不會出現新資料配舊 manifest。

    Args:
        storage: 情境所在的 storage。
        scenario_id: 情境 session id。
        out_dir: 輸出目錄（不存在會建立；資料包的同名檔案會覆寫）。
        include_ground_truth: 是否附 ``ground_truth.json``（評分端版本）；學生 / 受測端的版本不要附。
            盲測版會刪掉 ``out_dir`` 裡舊的答案檔。
        max_rows: raw 筆數上限（HTTP 端點用；None＝不限）。

    Returns:
        manifest（也寫在 ``out_dir/manifest.json``）。

    Raises:
        ScenarioPackError: 情境不能匯出（``out_dir`` 不受影響）。
    """
    scenario = _load_exportable_scenario(storage, scenario_id, max_rows)
    ground_truth: Optional[Dict[str, JsonValue]] = None
    if include_ground_truth:
        ground_truth = storage.get_ground_truth(scenario_id)
        if ground_truth is None:
            raise ScenarioPackError(f"Scenario {scenario_id} has no ground truth")
    pack_id = pack_id_for(scenario_id)
    out_dir = Path(out_dir)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}.staging-", dir=out_dir.parent))
    try:
        manifest = _write_pack_files(storage, scenario, scenario_id, pack_id, staging, ground_truth)
        out_dir.mkdir(exist_ok=True)
        if ground_truth is None:
            (out_dir / FILE_GROUND_TRUTH).unlink(missing_ok=True)  # 重匯出成盲測版：先拿掉舊的答案檔
        for name in pack_file_names(ground_truth is not None)[1:]:
            os.replace(staging / name, out_dir / name)
        os.replace(staging / FILE_MANIFEST, out_dir / FILE_MANIFEST)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return manifest


def write_pack_zip(pack_dir: Path, zip_path: Path, include_ground_truth: bool) -> None:
    """把資料包目錄壓成 zip（內部路徑 ``{pack_id}/{檔名}``）。

    Parquet 本身已壓縮，直接存（STORED）；JSON / JSONL 用 DEFLATE。

    Args:
        pack_dir: 資料包目錄（目錄名＝pack_id）。
        zip_path: 輸出的 zip。
        include_ground_truth: 是否含 ``ground_truth.json``。
    """
    with zipfile.ZipFile(zip_path, "w") as archive:
        for name in pack_file_names(include_ground_truth):
            compression = zipfile.ZIP_STORED if name.endswith(".parquet") else zipfile.ZIP_DEFLATED
            archive.write(pack_dir / name, arcname=f"{pack_dir.name}/{name}", compress_type=compression)
