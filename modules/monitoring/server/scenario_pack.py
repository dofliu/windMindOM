"""情境資料包匯出（WMOM-20261021-05，EPIC-DS Phase 3a ① 檔案）。

把一個凍結情境（命名情境 session）匯出成設計文件 §5.1 的資料包目錄：

```
{pack_id}/
  manifest.json          合約版本、機型、機組、時間窗、取樣週期、各檔 sha256
  tag_dictionary.json    tag → 單位、說明、source: bachmann_real | synthetic
  alarm_catalog.json     Z72 警報目錄快照（全部 314 碼）
  timeseries_raw.parquet timestamp(UTC), turbine_id, <Bachmann tag 名>...
  stats_10min.parquet    window_start(UTC), turbine_id, n_samples, <tag>_avg/_min/_max/_std
  events.jsonl           可觀測事件（PLC 事件 + 運轉狀態轉換），不含答案
  ground_truth.json      標準答案——只有評分端版本才有（include_ground_truth）
```

盲測（設計文件 §4 原則 2）：
- 事件只匯出 ``storage.is_observable_event`` 白名單內的；不帶模擬器內部的訊號值 / 設定值。
- manifest 不帶情境名稱、故障排程、注入數（這些都寫明故障）。
- 狀態轉換的停機原因正規化成 PLC 看得到的類別（``plc_trip`` / ``high_wind`` …），模擬器內部詞彙
  （例：``maintenance_lock``）不輸出。

時間戳一律 UTC、以 ``Z`` 結尾（合約 §5.1）；Parquet 用 ``timestamp[us, tz=UTC]``。長情境以串流方式
處理（分批讀 raw、10 分鐘統計逐窗計算），記憶體與情境長度無關。
"""

from __future__ import annotations

import hashlib
import json
import math
import warnings
from dataclasses import dataclass, field
from datetime import timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

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
FILE_MANIFEST = "manifest.json"
FILE_TAGS = "tag_dictionary.json"
FILE_ALARMS = "alarm_catalog.json"
FILE_RAW = "timeseries_raw.parquet"
FILE_STATS = "stats_10min.parquet"
FILE_EVENTS = "events.jsonl"
FILE_GROUND_TRUTH = "ground_truth.json"

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
_ARROW_TYPES: Dict[str, pa.DataType] = {
    "REAL32": pa.float32(),
    "SINT16": pa.int16(),
    "UINT16": pa.uint16(),
    "BOOL": pa.bool_(),
}
_READ_BATCH_ROWS = 5000

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
    """

    tag: ScadaTag
    name: str
    arrow_type: pa.DataType
    is_analog: bool


def pack_columns() -> List[PackColumn]:
    """資料包的 tag 欄位（依 SCADA 註冊表順序）。

    Returns:
        欄位定義。
    """
    return [
        PackColumn(tag=tag, name=tag.opc_tag.split(".", 1)[-1], arrow_type=_ARROW_TYPES[tag.data_type],
                   is_analog=tag.data_type == "REAL32")
        for tag in SCADA_REGISTRY.all_tags
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
        }
        for col in columns
    ]


def alarm_catalog_snapshot() -> Dict[str, JsonValue]:
    """Z72 警報目錄快照（全部事件碼）。

    Returns:
        ``{"turbine_model", "events": [...]}``。
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
        合約格式的事件；無法對應者回 None。
    """
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    base: Dict[str, JsonValue] = {"ts": iso_z(str(event["timestamp"])), "turbine_id": event.get("turbine_id")}
    if event.get("source") == "plc":
        event_type = _PLC_EVENT_TYPES.get(str(payload.get("kind")))
        if event_type is None:
            return None
        return {
            **base,
            "event_type": event_type,
            "alarm_code": payload.get("code"),
            "alarm_level": payload.get("level"),
            "alarm_text": payload.get("text"),
            "event_id": payload.get("eventId"),
            "plc_tag": payload.get("plcTag"),
        }
    from_state, to_state = payload.get("fromState"), payload.get("toState")
    if not isinstance(from_state, int) or not isinstance(to_state, int):
        return None
    return {
        **base,
        "event_type": "state_change",
        "from_state": from_state,
        "to_state": to_state,
        "from_state_name": STATE_NAMES.get(from_state),
        "to_state_name": STATE_NAMES.get(to_state),
        "stop_reason": stop_reason(payload.get("shutdownCause")) if to_state in _STOP_STATES else None,
    }


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


# ── raw 與 10 分鐘統計 ─────────────────────────────────────────────────────────


@dataclass
class _Window:
    """一台機組目前累積中的 10 分鐘窗。"""

    start_s: int
    rows: List[np.ndarray] = field(default_factory=list)


@dataclass
class _StatsBuilder:
    """逐窗計算 10 分鐘 avg / min / max / std（讀值依時間排序進來，窗滿就算，記憶體與情境長度無關）。"""

    columns: Sequence[PackColumn]
    open_windows: Dict[str, _Window] = field(default_factory=dict)
    out_rows: List[Tuple[int, str, int, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = field(default_factory=list)

    def add(self, epoch_s: float, turbine_id: str, values: np.ndarray) -> None:
        start = int(math.floor(epoch_s / STATS_WINDOW_S) * STATS_WINDOW_S)
        window = self.open_windows.get(turbine_id)
        if window is not None and window.start_s != start:
            self._flush(turbine_id, window)
            window = None
        if window is None:
            window = self.open_windows[turbine_id] = _Window(start_s=start)
        window.rows.append(values)

    def finish(self) -> None:
        for turbine_id, window in list(self.open_windows.items()):
            self._flush(turbine_id, window)
        self.open_windows.clear()
        self.out_rows.sort(key=lambda r: (r[0], r[1]))

    def _flush(self, turbine_id: str, window: _Window) -> None:
        data = np.vstack(window.rows)
        # 整窗都是缺值時 nanmean / nanmin 會警告（結果 NaN → 輸出 null），不洗版
        with np.errstate(invalid="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            avg = np.nanmean(data, axis=0)
            mn = np.nanmin(data, axis=0)
            mx = np.nanmax(data, axis=0)
            std = np.nanstd(data, axis=0, ddof=1) if len(data) > 1 else np.full(data.shape[1], np.nan)
        self.out_rows.append((window.start_s, turbine_id, len(data), avg, mn, mx, std))

    def table(self) -> pa.Table:
        n = len(self.out_rows)
        arrays: List[pa.Array] = [
            pa.array([r[0] * 1_000_000 for r in self.out_rows], type=pa.timestamp("us", tz="UTC")),
            pa.array([r[1] for r in self.out_rows], type=pa.string()),
            pa.array([r[2] for r in self.out_rows], type=pa.int32()),
        ]
        names = ["window_start", "turbine_id", "n_samples"]
        for i, col in enumerate(self.columns):
            stats = (("avg", 3), ("min", 4), ("max", 5), ("std", 6)) if col.is_analog else (("min", 4), ("max", 5))
            for suffix, idx in stats:
                values = [r[idx][i] for r in self.out_rows] if n else []
                if col.is_analog or col.arrow_type == pa.bool_():
                    arr_type = pa.float32() if col.is_analog else pa.bool_()
                else:
                    arr_type = col.arrow_type
                arrays.append(_to_arrow(values, arr_type))
                names.append(f"{col.name}_{suffix}")
        return pa.Table.from_arrays(arrays, names=names)


def _to_arrow(values: Sequence[float], arrow_type: pa.DataType) -> pa.Array:
    """float 值（NaN＝缺值）→ 指定型別的 Arrow 陣列。"""
    if arrow_type == pa.float32():
        return pa.array([None if (v is None or math.isnan(v)) else float(v) for v in values], type=arrow_type)
    if arrow_type == pa.bool_():
        return pa.array([None if (v is None or math.isnan(v)) else bool(v) for v in values], type=arrow_type)
    return pa.array([None if (v is None or math.isnan(v)) else int(round(v)) for v in values], type=arrow_type)


def _raw_schema(columns: Sequence[PackColumn]) -> pa.Schema:
    fields = [pa.field("timestamp", pa.timestamp("us", tz="UTC")), pa.field("turbine_id", pa.string())]
    fields += [pa.field(col.name, col.arrow_type) for col in columns]
    return pa.schema(fields)


def _write_raw_and_stats(storage: Storage, scenario_id: int, columns: Sequence[PackColumn],
                         raw_path: Path, stats_path: Path) -> Tuple[int, int, List[str], Optional[str], Optional[str]]:
    """串流寫出 raw Parquet，同時逐窗算 10 分鐘統計。

    Returns:
        ``(raw 列數, 統計列數, 機組清單, 第一筆時間, 最後一筆時間)``。
    """
    schema = _raw_schema(columns)
    stats = _StatsBuilder(columns=columns)
    turbines: List[str] = []
    first_ts: Optional[str] = None
    last_ts: Optional[str] = None
    rows_written = 0
    ids = [col.tag.id for col in columns]
    with pq.ParquetWriter(str(raw_path), schema) as writer:
        for batch in storage.iter_session_readings(scenario_id, _READ_BATCH_ROWS):
            micros: List[int] = []
            turbine_col: List[str] = []
            matrix = np.full((len(batch), len(columns)), np.nan)
            for r, row in enumerate(batch):
                ts = parse_iso(row["timestamp"])
                epoch = ts.timestamp()
                micros.append(int(round(epoch * 1_000_000)))
                tid = str(row["turbine_id"])
                turbine_col.append(tid)
                if tid not in turbines:
                    turbines.append(tid)
                scada = json.loads(row["scada_json"]) if row["scada_json"] else {}
                for c, tag_id in enumerate(ids):
                    value = scada.get(tag_id)
                    if isinstance(value, (int, float)) and math.isfinite(value):
                        matrix[r, c] = float(value)
                stats.add(epoch, tid, matrix[r].copy())
                if first_ts is None:
                    first_ts = row["timestamp"]
                last_ts = row["timestamp"]
            arrays: List[pa.Array] = [
                pa.array(micros, type=pa.timestamp("us", tz="UTC")),
                pa.array(turbine_col, type=pa.string()),
            ]
            arrays += [_to_arrow(matrix[:, c].tolist(), col.arrow_type) for c, col in enumerate(columns)]
            writer.write_table(pa.Table.from_arrays(arrays, schema=schema))
            rows_written += len(batch)
    stats.finish()
    stats_table = stats.table()
    pq.write_table(stats_table, str(stats_path))
    return rows_written, stats_table.num_rows, sorted(turbines), first_ts, last_ts


# ── 匯出 ─────────────────────────────────────────────────────────────────────


def _write_json(path: Path, data: JsonValue) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _file_digest(path: Path) -> Dict[str, JsonValue]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return {"sha256": digest.hexdigest(), "bytes": path.stat().st_size}


def _load_exportable_scenario(storage: Storage, scenario_id: int) -> Dict[str, JsonValue]:
    """取情境並確認可以匯出。

    Raises:
        ScenarioPackError: 不存在（404）、生成未成功、事件沒有 session 隔離（409）。
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
    return scenario


def export_scenario_pack(storage: Storage, scenario_id: int, out_dir: Path, *,
                         include_ground_truth: bool = False) -> Dict[str, JsonValue]:
    """把情境匯出成資料包目錄。

    Args:
        storage: 情境所在的 storage。
        scenario_id: 情境 session id。
        out_dir: 輸出目錄（不存在會建立；同名檔案會覆寫）。
        include_ground_truth: 是否附 ``ground_truth.json``（評分端版本）；學生 / 受測端的版本不要附。

    Returns:
        manifest（也寫在 ``out_dir/manifest.json``）。

    Raises:
        ScenarioPackError: 情境不能匯出。
    """
    scenario = _load_exportable_scenario(storage, scenario_id)
    config = scenario["config"]
    pack_id = pack_id_for(scenario_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    columns = pack_columns()

    raw_rows, stats_rows, turbines, first_ts, last_ts = _write_raw_and_stats(
        storage, scenario_id, columns, out_dir / FILE_RAW, out_dir / FILE_STATS,
    )
    if raw_rows == 0:
        raise ScenarioPackError(f"Scenario {scenario_id} has no readings")

    events = [
        packed for event in storage.session_events(scenario_id) if is_observable_event(event)
        for packed in (pack_event(event),) if packed is not None
    ]
    (out_dir / FILE_EVENTS).write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events), encoding="utf-8",
    )
    _write_json(out_dir / FILE_TAGS, {"turbine_model": TURBINE_MODEL, "tags": tag_dictionary(columns)})
    _write_json(out_dir / FILE_ALARMS, alarm_catalog_snapshot())

    files = [FILE_TAGS, FILE_ALARMS, FILE_RAW, FILE_STATS, FILE_EVENTS]
    if include_ground_truth:
        ground_truth = storage.get_ground_truth(scenario_id)
        if ground_truth is None:
            raise ScenarioPackError(f"Scenario {scenario_id} has no ground truth")
        _write_json(out_dir / FILE_GROUND_TRUTH, ground_truth_for_pack(ground_truth, pack_id))
        files.append(FILE_GROUND_TRUTH)
    elif (out_dir / FILE_GROUND_TRUTH).exists():
        (out_dir / FILE_GROUND_TRUTH).unlink()  # 重匯出成盲測版時，不留舊的答案檔

    manifest: Dict[str, JsonValue] = {
        "contract_version": CONTRACT_VERSION,
        "pack_id": pack_id,
        "turbine_model": TURBINE_MODEL,
        "turbines": turbines,
        "sim_start": iso_z(str(first_ts)),
        "sim_end": iso_z(str(last_ts)),
        "sample_period_s": config.get("time_step"),
        "stats_window_s": STATS_WINDOW_S,
        "duration_hours": config.get("duration_hours"),
        "site_timezone": config.get("site_timezone"),
        "wind_profile": config.get("wind_profile"),
        "rated_power_kw": scenario.get("rated_power_kw"),
        "ground_truth_included": include_ground_truth,
        "generator": {"name": "windMindOM", "simulator": "modules/monitoring (Z72 physics + PLC protection)"},
        "reproducibility": {
            "seed": None,
            "note": "Generated from the live simulator state at generation time; not reproducible from this "
                    "manifest alone (WMOM-20261021-05 known limitation).",
        },
        "counts": {"raw_rows": raw_rows, "stats_rows": stats_rows, "events": len(events)},
        "files": {name: _file_digest(out_dir / name) for name in files},
        "exported_at": utc_now().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }
    _write_json(out_dir / FILE_MANIFEST, manifest)
    return manifest


def pack_file_names(include_ground_truth: bool) -> Iterable[str]:
    """資料包內的檔案（壓縮成 zip 時的順序）。

    Args:
        include_ground_truth: 是否含標準答案。

    Returns:
        檔名。
    """
    names = [FILE_MANIFEST, FILE_TAGS, FILE_ALARMS, FILE_RAW, FILE_STATS, FILE_EVENTS]
    return names + [FILE_GROUND_TRUTH] if include_ground_truth else names
