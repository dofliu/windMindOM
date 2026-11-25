"""對外唯讀 API（WMOM-20261125-02，EPIC-SF 第 1 項，DEC-20261125-01）。

給外部系統（例：RAG 運維助理）像外部監控一樣，向持續運轉的仿真風場取 SCADA 資料與警報：

- ``GET /api/ext/v1/status``        伺服器與即時模擬的狀態
- ``GET /api/ext/v1/farm``          機型、機組、取樣週期、10 分鐘統計的慣例
- ``GET /api/ext/v1/tags``          tag 字典（同資料包 ``tag_dictionary.json``）
- ``GET /api/ext/v1/alarm-catalog`` Z72 警報目錄（同資料包 ``alarm_catalog.json``）
- ``GET /api/ext/v1/readings/latest`` 每台機組最新一筆讀值
- ``GET /api/ext/v1/readings``      一台機組的歷史讀值（游標往後翻頁）
- ``GET /api/ext/v1/stats-10min``   一台機組的 10 分鐘統計（由讀值即時計算）
- ``GET /api/ext/v1/events``        警報、跳機與運轉狀態轉換（游標往後翻頁）
- ``GET /api/ext/v1/alarms/active`` 每台機組目前成立的警報與跳機碼

守則：

- **只收 API 金鑰**（``X-API-Key``，``modules.auth.api_keys``），一律強制、唯讀。金鑰不是角色，碰不到其他端點。
- **給出去的東西與盲測版資料包、回放訊息同一套**：讀值欄位＝``scenario_pack.pack_columns()``（不含
  ``MODEL_INTERNAL_TAGS``）、事件只取 ``storage.is_observable_event``、格式用 ``pack_event`` /
  ``json_values`` / ``stats_message``。不帶故障注入資訊、情境名稱、風場名稱等自訂文字。
- **只取 Live**：排除情境 session（凍結的出題資料集）；最新讀值取自最近一次寫進 storage 的那一批，不讀
  simulator 記憶體（批次期間那裡是情境的值）。
- 盲測要成立，伺服器要開 ``WMOM_AUTH_ENFORCE=true``——否則其他端點本來就不用登入，``/status`` 的
  ``other_endpoints_require_login`` 會是 false。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Annotated, Dict, List, Optional, Tuple

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query

from modules.auth.api_keys import require_api_key
from modules.auth.dependencies import is_auth_enforced
from server import scenario_pack as sp
from server.data_broker import DataBroker
from server.live_archive import ArchiveIndexError, LiveReading
from server.live_history import LiveHistory
from server.storage import is_observable_event
from simulator.ground_truth import CONTRACT_VERSION
from simulator.time_utils import iso_utc, parse_iso

JsonValue = sp.JsonValue

# 對外 API 自己的版本（端點、參數、翻頁方式）。資料格式（讀值欄位、事件、10 分鐘統計）跟著資料介面合約
# （``CONTRACT_VERSION``）：加端點 / 加欄位升次版本，改名 / 刪除升主版本並換路徑前綴。
EXTERNAL_API_VERSION = "1.1"

READINGS_DEFAULT_LIMIT = 500
READINGS_MAX_LIMIT = 2000
EVENTS_DEFAULT_LIMIT = 500
EVENTS_MAX_LIMIT = 2000
# 10 分鐘統計一次最多算多長（由原始讀值即時計算，太長會拖慢伺服器）
STATS_MAX_RANGE = timedelta(hours=24)
# 事件 / 統計在內部一次向 storage 取幾列
_SCAN_BATCH = 1000
# 事件一個請求最多掃幾批（可觀測事件很稀疏時，避免一個請求掃完整張表）
_MAX_SCAN_BATCHES = 20
_SQLITE_INT_MAX = 2**63 - 1

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/ext/v1",
    tags=["external"],
    # 掛在 router 上：之後新增的端點也一定要金鑰
    dependencies=[Depends(require_api_key())],
)

TurbineId = Annotated[str, Query(min_length=1, max_length=64, description="機組 ID，例 WT001")]
Cursor = Annotated[int, Query(ge=0, le=_SQLITE_INT_MAX, description="游標：上一頁回傳的 next_cursor；0＝從頭")]
TimeParam = Annotated[Optional[str], Query(max_length=40, description="ISO 8601，要帶時區，例 2026-11-26T00:00:00Z")]


def get_broker() -> DataBroker:
    """Return the shared DataBroker instance from the main app module."""
    from server.app import broker
    return broker


@lru_cache(maxsize=1)
def _columns() -> Tuple[sp.PackColumn, ...]:
    return tuple(sp.pack_columns())


@lru_cache(maxsize=1)
def _tag_ids() -> Tuple[str, ...]:
    return tuple(col.tag.id for col in _columns())


def _aware_time(name: str, value: Optional[str]) -> Optional[datetime]:
    """解析查詢參數的時間；沒帶時區或格式錯誤回 422。"""
    if value is None or value == "":
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00").replace("z", "+00:00"))
        if parsed.tzinfo is None:
            raise HTTPException(422, f"{name} 要帶時區（例 2026-11-26T00:00:00Z）")
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:  # OverflowError：年份在 1 / 9999 邊界、換算 UTC 後超出範圍
        raise HTTPException(422, f"{name} 不是可用的 ISO 8601 時間：{value}") from exc


def _time_range(start: Optional[str], end: Optional[str]) -> Tuple[Optional[datetime], Optional[datetime]]:
    start_dt, end_dt = _aware_time("start", start), _aware_time("end", end)
    if start_dt is not None and end_dt is not None and end_dt <= start_dt:
        raise HTTPException(422, "end 要晚於 start")
    return start_dt, end_dt


def _reading_message(timestamp: str, turbine_id: str, values: np.ndarray) -> Dict[str, JsonValue]:
    """一筆讀值 → 與回放 ``reading`` 訊息相同的格式。"""
    return {
        "type": "reading",
        "ts": sp.iso_z(timestamp),
        "turbine_id": turbine_id,
        "values": sp.json_values(values, _columns()),
    }


def _history_page(history: LiveHistory, turbine_id: str, after_id: int, start: Optional[str], end: Optional[str],
                  limit: int) -> List[LiveReading]:
    """讀一頁 Live 讀值（歸檔＋SQLite）；歸檔的索引讀不出來時回 503，不回一份缺了舊資料的結果。"""
    try:
        return history.readings(turbine_id, _tag_ids(), after_id=after_id, start=start, end=end, limit=limit)
    except ArchiveIndexError as exc:
        logger.error("對外 API：%s", exc)
        raise HTTPException(503, "歷史讀值暫時讀不到，請稍後再試") from exc


def _data_clock(broker: DataBroker, turbine_id: str) -> Optional[datetime]:
    """一台機組的資料時鐘：最近一次寫進歷史的 Live 讀值的時間；沒有資料為 None。

    不用實際時間：讀值每個取樣週期才寫一次，窗的最後一筆可能還沒進來；時間倍率大於 1 時，讀值的時間也
    跑在實際時間前面。
    """
    for stored_id, ts, _ in broker.latest_stored_readings():
        if stored_id == turbine_id:
            return parse_iso(ts)
    ts = broker.storage.last_live_reading_timestamp(turbine_id)
    return parse_iso(ts) if ts else None


def _live(broker: DataBroker) -> bool:
    """即時模擬是否在跑（不是批次、不是只調閱）。"""
    simulator = broker.simulator
    return (simulator is not None and broker.source_kind == "simulation"
            and simulator.is_running and not simulator.is_bulk_running)


@router.get("/status")
def status() -> Dict[str, JsonValue]:
    """伺服器與即時模擬的狀態。

    Returns:
        版本、即時模擬是否在跑、取樣週期、最新讀值時間，以及其他端點是否需要登入（盲測的前提）。
    """
    broker = get_broker()
    simulator = broker.simulator
    latest = [parse_iso(ts) for _, ts, _ in broker.latest_stored_readings()]
    return {
        "api_version": EXTERNAL_API_VERSION,
        "contract_version": CONTRACT_VERSION,
        "server_time": sp.iso_z(iso_utc()),
        "live": _live(broker),
        # 即時資料的連續段編號：風場狀態從頭開始時才會變（重啟續跑、產生情境都不會），數字變了表示資料
        # 在那裡不連續
        "live_epoch": int(broker.live_epoch),
        "time_scale": float(simulator.time_scale) if simulator is not None else 1.0,
        "sample_period_s": broker.live_sample_period_s,
        # 原始讀值留幾天（依資料自己的時間，循環保存）：比這更早的 /readings、/stats-10min 查不到
        "raw_retention_days": int(broker.raw_retention_days),
        "latest_reading_ts": sp.iso_z(iso_utc(max(latest))) if latest else None,
        "other_endpoints_require_login": is_auth_enforced(),
    }


@router.get("/farm")
def farm() -> Dict[str, JsonValue]:
    """風場的固定資訊：機型、機組、取樣週期、10 分鐘統計的慣例（欄位同資料包 manifest）。

    Returns:
        不含風場名稱、情境名稱等自訂文字。
    """
    broker = get_broker()
    session = broker.storage.get_active_session() or {}
    config = session.get("config")
    config = config if isinstance(config, dict) else {}
    return {
        "contract_version": CONTRACT_VERSION,
        "turbine_model": sp.TURBINE_MODEL,
        "turbines": sorted(broker.turbine_ids),
        "site_timezone": config.get("site_timezone"),
        "rated_power_kw": session.get("rated_power_kw"),
        "sample_period_s": broker.live_sample_period_s,
        "stats_window_s": sp.STATS_WINDOW_S,
        "stats_convention": sp.stats_convention(_columns()),
    }


@router.get("/tags")
def tags() -> Dict[str, JsonValue]:
    """tag 字典：每個讀值欄位的單位、說明、資料型別與真實性（同資料包 ``tag_dictionary.json``）。"""
    return {"turbine_model": sp.TURBINE_MODEL, "tags": sp.tag_dictionary(_columns())}


@router.get("/alarm-catalog")
def alarm_catalog() -> Dict[str, JsonValue]:
    """Z72 警報目錄（同資料包 ``alarm_catalog.json``）。"""
    return sp.alarm_catalog_snapshot()


@router.get("/readings/latest")
def latest_readings() -> Dict[str, JsonValue]:
    """每台機組最新一筆讀值（最近一次寫進歷史的那一批）。

    Returns:
        ``{"readings": [...]}``；即時模擬還沒寫過資料時為空。
    """
    ids = _tag_ids()
    return {
        "readings": [
            _reading_message(ts, turbine_id, sp.scada_dict_values(scada, ids))
            for turbine_id, ts, scada in get_broker().latest_stored_readings()
        ],
    }


@router.get("/readings")
def readings(
    turbine_id: TurbineId,
    start: TimeParam = None,
    end: TimeParam = None,
    after: Cursor = 0,
    limit: Annotated[int, Query(ge=1, le=READINGS_MAX_LIMIT)] = READINGS_DEFAULT_LIMIT,
) -> Dict[str, JsonValue]:
    """一台機組的歷史讀值，依寫入順序；以 ``next_cursor`` 往後翻頁或輪詢新資料。

    Args:
        turbine_id: 機組 ID。
        start: 時間下限（含）。
        end: 時間上限（不含）。
        after: 游標。
        limit: 一頁最多幾筆。

    Returns:
        ``{"readings": [...], "next_cursor": int, "has_more": bool}``。
    """
    start_dt, end_dt = _time_range(start, end)
    # 兩層：較舊的在每日歸檔、最近幾天的在 SQLite，同一個游標往後走（WMOM-20261125-03-c）
    rows = _history_page(
        get_broker().live_history, turbine_id, after_id=after,
        start=iso_utc(start_dt) if start_dt else None,
        end=iso_utc(end_dt) if end_dt else None,
        limit=limit + 1,
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {
        "readings": [_reading_message(row.timestamp, row.turbine_id, row.values) for row in rows],
        "next_cursor": rows[-1].id if rows else after,
        "has_more": has_more,
    }


@router.get("/stats-10min")
def stats_10min(
    turbine_id: TurbineId,
    start: Annotated[str, Query(max_length=40, description="ISO 8601，要帶時區")],
    end: Annotated[str, Query(max_length=40, description="ISO 8601，要帶時區")],
) -> Dict[str, JsonValue]:
    """一台機組的 10 分鐘統計（算法、欄位與資料包 ``stats_10min.parquet`` 相同），由讀值即時計算。

    只回完整落在 ``[start, end)`` 內、而且已經收齊的窗：這台機組最近一次寫進歷史的讀值，時間已經到了窗的
    結束時間或更晚。一次最多 24 小時。

    Args:
        turbine_id: 機組 ID。
        start: 時間下限（含），要帶時區。
        end: 時間上限（不含），要帶時區。

    Returns:
        ``{"stats": [...], "sample_period_s": float | None}``；``sample_period_s`` 是這段資料相鄰讀值
        間隔的中位數（判定 ``is_partial`` 用），資料不足兩筆時為 None、``is_partial`` 也是 None。
    """
    start_dt, end_dt = _time_range(start, end)
    if start_dt is None or end_dt is None:
        raise HTTPException(422, "start 與 end 都要給")
    if end_dt - start_dt > STATS_MAX_RANGE:
        raise HTTPException(422, "一次最多查 24 小時")
    window = sp.STATS_WINDOW_S
    broker = get_broker()
    builder = sp.StatsBuilder(columns=_columns())
    # 只算完整落在 [start, end) 內的窗；還沒收齊的窗不算（之後還會有讀值進來，算出來的值會變）
    clock = _data_clock(broker, turbine_id)
    first = int(-(-start_dt.timestamp() // window) * window)
    last = int(min(end_dt, clock).timestamp() // window * window) if clock is not None else first
    if last > first:
        history = broker.live_history  # 歸檔＋SQLite：超過熱資料天數的窗由每日歸檔算
        lower = iso_utc(datetime.fromtimestamp(first, tz=timezone.utc))
        upper = iso_utc(datetime.fromtimestamp(last, tz=timezone.utc))
        cursor = 0
        while True:
            rows = _history_page(history, turbine_id, after_id=cursor, start=lower, end=upper, limit=_SCAN_BATCH)
            if not rows:
                break
            # 統計依時間分窗：同一批裡先照時間排（Live 列的寫入順序通常就是時間順序）
            for row in sorted(rows, key=lambda r: r.timestamp):
                builder.add(parse_iso(row.timestamp).timestamp(), row.turbine_id, row.values)
            cursor = rows[-1].id
            if len(rows) < _SCAN_BATCH:
                break
    # 即時資料的間隔帶抖動（約 10.1–10.2 秒）：以這段資料相鄰讀值間隔的中位數當取樣週期來判定殘缺窗
    period = builder.median_period_s
    return {
        "stats": [sp.stats_message(row, _columns(), period) for row in builder.close_all()],
        "sample_period_s": period,
    }


@router.get("/events")
def events(
    turbine_id: Annotated[Optional[str], Query(min_length=1, max_length=64)] = None,
    start: TimeParam = None,
    end: TimeParam = None,
    after: Cursor = 0,
    limit: Annotated[int, Query(ge=1, le=EVENTS_MAX_LIMIT)] = EVENTS_DEFAULT_LIMIT,
) -> Dict[str, JsonValue]:
    """警報、跳機與運轉狀態轉換（同資料包 ``events.jsonl``），依寫入順序；以 ``next_cursor`` 輪詢新事件。

    Args:
        turbine_id: 只取這台機組；不給＝全部。
        start: 時間下限（含）。
        end: 時間上限（不含）。
        after: 游標。
        limit: 一頁最多幾筆。

    Returns:
        ``{"events": [...], "next_cursor": int, "has_more": bool}``。
    """
    start_dt, end_dt = _time_range(start, end)
    storage = get_broker().storage
    lower = iso_utc(start_dt) if start_dt else None
    upper = iso_utc(end_dt) if end_dt else None
    out: List[Dict[str, JsonValue]] = []
    cursor = after
    has_more = False
    for _ in range(_MAX_SCAN_BATCHES):
        batch = storage.live_events(after_id=cursor, turbine_id=turbine_id, start=lower, end=upper,
                                    limit=_SCAN_BATCH)
        for event in batch:
            if len(out) >= limit:
                has_more = True  # 這一筆（與之後的）留給下一頁
                break
            cursor = int(event["id"])
            if not is_observable_event(event):
                continue
            packed = sp.pack_event(event)
            if packed is not None:
                out.append({"type": "event", **packed})
        if has_more or len(batch) < _SCAN_BATCH:
            break
    else:
        has_more = True  # 掃描量到上限：還沒看完，請用 next_cursor 接著取
    return {"events": out, "next_cursor": cursor, "has_more": has_more}


@router.get("/alarms/active")
def active_alarms() -> Dict[str, JsonValue]:
    """每台機組目前成立的警報（A）與鎖存中的跳機（T1 / T2）碼，依成立順序。

    與 OPC UA 的 ``ActiveAlarm`` / ``ActiveTrip1`` / ``ActiveTrip2`` 同一份清單。即時模擬沒在跑（未啟動、
    正在產生情境）時 ``live`` 為 false、``turbines`` 為空。

    Returns:
        ``{"live": bool, "turbines": [{"turbine_id", "alarm", "trip1", "trip2"}]}``。
    """
    broker = get_broker()
    if not _live(broker):
        return {"live": False, "turbines": []}
    simulator = broker.simulator
    assert simulator is not None  # _live 已確認
    turbines: List[Dict[str, JsonValue]] = []
    for tid, model in sorted(dict(simulator.turbines).items()):
        # 模擬執行緒同時在改清單；snapshot 只複製三個 list
        lists = model.plc.active_lists.snapshot()
        turbines.append({
            "turbine_id": tid,
            "alarm": list(lists.get("A", [])),
            "trip1": list(lists.get("T1", [])),
            "trip2": list(lists.get("T2", [])),
        })
    return {"live": True, "turbines": turbines}
