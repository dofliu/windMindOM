"""凍結情境回放（WMOM-20261021-06，EPIC-DS Phase 3b ② 串流）。

把一個可匯出資料包的情境依模擬時間重播成訊息流，給 WebSocket 回放（``routers/replay.py``）與之後的
OPC UA server（-07）共用：

- ``ScenarioReplay``：資料來源。依時間排序產生 ``reading`` / ``event`` / ``stats`` 訊息，內容與型別和
  資料包相同（同一套欄位、事件格式、10 分鐘統計算法），不含任何標準答案。
- ``ReplayClock``：模擬時間 = 起點 + 經過的實際秒數 × 速度。
- ``validate_prediction``：受測端經 WS 送來的預測（合約 §6）；``ts`` 一律由伺服器以收到時的模擬時間
  蓋上，受測端不能自己填（時間因果由伺服器保證，DEC-20261022-02）。

回放的兩種模式（DEC-20261022-02）：
- ``evaluation``：單次直播。時鐘從第一次連線起算，之後的連線都看同一個「現在」，不能倒帶或暫停；
  斷線重連可選擇補送已過去的資料（``backfill``），但不會讓時間倒回。
- ``practice``：每次連線各自從頭播，給受測端開發用。

速度由出題端開回放時決定（受測端不能選），每個受測者每模擬秒能用的運算時間相同。
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from array import array
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, FrozenSet, Iterator, List, Optional, Sequence, Tuple

try:
    from ..simulator.ground_truth import CONTRACT_VERSION
    from ..simulator.time_utils import iso_utc, parse_iso
    from . import scenario_pack as sp
    from .storage import Storage, is_observable_event
except ImportError:  # sys.path 注入模式（modules/monitoring 在 sys.path）
    from simulator.ground_truth import CONTRACT_VERSION  # type: ignore[no-redef]
    from simulator.time_utils import iso_utc, parse_iso  # type: ignore[no-redef]
    from server import scenario_pack as sp  # type: ignore[no-redef]
    from server.storage import Storage, is_observable_event  # type: ignore[no-redef]

JsonValue = sp.JsonValue

REPLAY_MODES: Tuple[str, ...] = ("evaluation", "practice")
MIN_SPEED = 0.1
MAX_SPEED = 10_000.0
# 正式評測每秒要送的讀值上限（機組數 × 速度 ÷ 取樣週期）。實測單一連線約 3,800 筆 / 秒（3 機、每筆
# 100 個 tag）；留 4 倍餘裕給多條連線與較慢的機器——伺服器跟不上時落後的時間會算在受測端頭上
EVAL_MAX_READINGS_PER_S = 1000.0
DEFAULT_SPEED = 60.0
DEFAULT_EXPIRES_HOURS = 24.0 * 7
MAX_EXPIRES_HOURS = 24.0 * 90
# 資料播完後連線再開著的實際秒數：讓送出途中的預測拿到 ack、受測端自己關閉連線。情境結束（模擬時間
# 超過 sim_end）後收到的預測一律退回——評分時那些預測對不到任何 case（合約 §8 規則 3）
CLOSE_GRACE_S = 10.0
MAX_CONNECTIONS_PER_RUN = 4
MAX_PREDICTIONS_PER_RUN = 20_000
MAX_PREDICTION_BYTES_PER_RUN = 20 * 1024 * 1024  # 每個回放存進 DB 的預測總量
MAX_CLIENT_MESSAGE_BYTES = 16 * 1024
# 回放的讀值筆數上限（同 HTTP 資料包匯出）：每條連線要載入 id 索引（每筆 8 bytes）
MAX_REPLAY_ROWS = 2_000_000
TOKEN_PREFIX = "wmr_"
PAGE_ROWS = 500

# 訊息在同一時刻的順序：先送結束於此刻的 10 分鐘統計、再送事件、再送讀值；資料結束時才算完的
# 最後幾個窗（含最後一筆讀值）排在最後
_ORDER_STATS, _ORDER_EVENT, _ORDER_READING, _ORDER_FINAL_STATS = 0, 1, 2, 3

PREDICTION_CATEGORIES: Tuple[str, ...] = ("real_fault", "sensor_fault", "nuisance")
FAULT_CATEGORIES: FrozenSet[str] = frozenset({"real_fault", "sensor_fault"})
MAX_MANUAL_REFS = 50
MAX_TEXT_CHARS = 4000
MAX_COMPONENT_CHARS = 64
MAX_ACTIONS = 20
# 元件詞彙（合約 §9）的唯一來源；starter kit 的 vocabulary.json 是它的副本（build_rag_starter_kit 同步，
# 測試比對兩份相同）。放 shared/ 才會進 Docker 映像；找不到就匯入失敗，不會悄悄略過詞彙檢查
VOCABULARY_PATH = Path(__file__).resolve().parents[3] / "shared" / "data" / "rag_assistant_vocabulary.json"


class ReplayRunConflict(ValueError):
    """同一個情境已有另一種模式的回放（練習回放可以先看完正式評測的資料，DEC-20261022-02）。"""


class ReplayError(ValueError):
    """回放不能開始（token 無效、已撤銷、情境不能回放…）。

    Attributes:
        close_code: WebSocket 關閉碼（4401 token 無效、4403 撤銷 / 到期、4404 情境不能回放、
            4409 連線數已滿、4410 單次回放已結束）。
    """

    def __init__(self, message: str, close_code: int) -> None:
        super().__init__(message)
        self.close_code = close_code


def new_token() -> str:
    """產生回放 token（只回給出題端一次，DB 只存 sha256）。

    Returns:
        ``wmr_`` 開頭的隨機字串。
    """
    return TOKEN_PREFIX + secrets.token_urlsafe(24)


def token_digest(token: str) -> str:
    """token 的 sha256（查詢與儲存用）。

    Args:
        token: 回放 token。

    Returns:
        16 進位字串。
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def wall_time() -> float:
    """實際時間（epoch 秒）；測試以 monkeypatch 控制。"""
    return time.time()


def z(ts: datetime) -> str:
    """UTC datetime → 合約時間格式 ``YYYY-MM-DDTHH:MM:SS.ffffffZ``。"""
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass(frozen=True)
class ReplayClock:
    """回放時鐘：模擬時間＝``sim_start`` + （實際時間 − ``wall_start``）× ``speed``。

    Attributes:
        sim_start: 第一筆讀值的時間（tz-aware UTC）。
        speed: 模擬秒 / 實際秒。
        wall_start: 回放開始的實際時間（epoch 秒）。
    """

    sim_start: datetime
    speed: float
    wall_start: float

    def sim_now(self, wall: Optional[float] = None) -> datetime:
        """目前的模擬時間（開始前回 ``sim_start``）。

        Args:
            wall: 實際時間（epoch 秒）；None＝現在。

        Returns:
            tz-aware UTC。
        """
        elapsed = max(0.0, (wall_time() if wall is None else wall) - self.wall_start)
        return self.sim_start + timedelta(seconds=elapsed * self.speed)

    def wall_at(self, sim_ts: datetime) -> float:
        """模擬時間 ``sim_ts`` 對應的實際時間（epoch 秒）。

        Args:
            sim_ts: 模擬時間。

        Returns:
            epoch 秒。
        """
        return self.wall_start + (sim_ts - self.sim_start).total_seconds() / self.speed


@dataclass(frozen=True)
class ReplayFrame:
    """一則要送出的訊息。

    Attributes:
        due: 可以送出的模擬時刻（讀值 / 事件為其時間；10 分鐘統計為窗結束時刻，最後的殘缺窗為資料結束時刻）。
        order: 同一時刻的順序（統計 → 事件 → 讀值 → 資料結束時的最後幾個窗）。
        message: 訊息內容（JSON 物件）。
    """

    due: datetime
    order: int
    message: Dict[str, JsonValue]


# 情境讀值的 id 索引快取：凍結情境不會再變，同一個情境的多條連線、重連不必每次重查（每筆 8 bytes）。
# 鍵含 DB 路徑（各風場一個 DB）、session 的建立時間與筆數
_INDEX_CACHE: "OrderedDict[Tuple[str, int, str, int], array[int]]" = OrderedDict()
_INDEX_CACHE_SIZE = 8
_INDEX_LOCK = threading.Lock()


def _reading_ids(storage: Storage, scenario_id: int, scenario: Dict[str, JsonValue]) -> "array[int]":
    key = (storage.db_path, scenario_id, str(scenario.get("started_at")), storage.count_session_readings(scenario_id))
    with _INDEX_LOCK:
        cached = _INDEX_CACHE.get(key)
        if cached is not None:
            _INDEX_CACHE.move_to_end(key)
            return cached
    ids = storage.session_reading_ids(scenario_id)
    with _INDEX_LOCK:
        _INDEX_CACHE[key] = ids
        while len(_INDEX_CACHE) > _INDEX_CACHE_SIZE:
            _INDEX_CACHE.popitem(last=False)
    return ids


class ScenarioReplay:
    """一個凍結情境的回放資料來源：依時間排序的 ``reading`` / ``event`` / ``stats`` 訊息。

    內容與盲測版資料包相同（欄位＝``scenario_pack.pack_columns()``、事件只取 ``is_observable_event``、
    10 分鐘統計同一套算法），不含任何標準答案。讀值依時間分頁取（每頁一個短查詢，可以在不同執行緒
    呼叫 ``next_frames``，但同一時間只能一個呼叫端）。

    Attributes:
        scenario_id: 情境 session id。
        pack_id: 對應資料包的 ID（受測端的預測以它對到標準答案）。
        columns: 讀值欄位。
        turbines: 機組 ID。
        sim_start: 第一筆讀值的時間。
        sim_end: 最後一筆讀值的時間。
        sample_period_s: 取樣週期（情境設定的 ``time_step``）。
    """

    def __init__(self, storage: Storage, scenario_id: int) -> None:
        """載入情境（只讀索引與事件，讀值依需要分頁取）。

        Args:
            storage: 情境所在的 storage。
            scenario_id: 情境 session id。

        Raises:
            ScenarioPackError: 情境不存在或不能匯出 / 回放（同資料包的條件）。
        """
        self._storage = storage
        self.scenario_id = scenario_id
        self._scenario = sp.load_exportable_scenario(storage, scenario_id, MAX_REPLAY_ROWS)
        config = self._scenario["config"]
        assert isinstance(config, dict)
        self._config = config
        self.pack_id = sp.pack_id_for(scenario_id)
        self.columns = sp.pack_columns()
        self._tag_ids = [col.tag.id for col in self.columns]
        self._row_ids = _reading_ids(storage, scenario_id, self._scenario)
        bounds = storage.session_reading_bounds(scenario_id)
        assert bounds is not None  # load_exportable_scenario 已確認有讀值
        self.sim_start = parse_iso(bounds[0])
        self.sim_end = parse_iso(bounds[1])
        self.turbines = storage.scenario_turbine_ids(scenario_id)
        self.sample_period_s = sp.positive_number(config.get("time_step"))
        self._events: List[Tuple[datetime, Dict[str, JsonValue]]] = []
        for event in storage.session_events(scenario_id):
            if not is_observable_event(event):
                continue
            packed = sp.pack_event(event)
            if packed is not None:
                self._events.append((parse_iso(str(packed["ts"])), packed))
        self._events.sort(key=lambda item: item[0])  # 穩定排序：同一時刻保持發生順序
        self._stats = sp.StatsBuilder(columns=self.columns)
        self._pos = 0
        self._event_pos = 0
        self._done = False

    def describe(self) -> Dict[str, JsonValue]:
        """回放的說明（給 ``started`` 訊息；欄位取自資料包 manifest，不含情境名稱與故障排程）。

        Returns:
            dict。
        """
        wind_profile = self._config.get("wind_profile")
        return {
            "contract_version": CONTRACT_VERSION,
            "pack_id": self.pack_id,
            "turbine_model": sp.TURBINE_MODEL,
            "turbines": list(self.turbines),
            "sim_start": z(self.sim_start),
            "sim_end": z(self.sim_end),
            "sample_period_s": self.sample_period_s,
            "stats_window_s": sp.STATS_WINDOW_S,
            "stats_convention": sp.stats_convention(self.columns),
            "duration_hours": self._config.get("duration_hours"),
            "site_timezone": self._config.get("site_timezone"),
            "wind_profile": wind_profile if wind_profile in sp.KNOWN_WIND_PROFILES else None,
            "rated_power_kw": self._scenario.get("rated_power_kw"),
        }

    def tag_dictionary(self) -> List[Dict[str, JsonValue]]:
        """讀值欄位的 tag 字典（同資料包 ``tag_dictionary.json`` 的 ``tags``）。"""
        return sp.tag_dictionary(self.columns)

    @property
    def done(self) -> bool:
        """訊息是否都產生完了。"""
        return self._done

    def next_frames(self, max_rows: int = PAGE_ROWS) -> List[ReplayFrame]:
        """下一批訊息（依 ``due``、``order`` 排序；最多讀 ``max_rows`` 筆讀值）。

        Args:
            max_rows: 這一批最多讀幾筆讀值。

        Returns:
            訊息；全部產生完後回空 list。
        """
        if self._done:
            return []
        ids = list(self._row_ids[self._pos:self._pos + max_rows])
        frames: List[ReplayFrame] = []
        if not ids:
            pending = [self._event_frame(i) for i in range(self._event_pos, len(self._events))]
            self._event_pos = len(self._events)
            # 最後的窗（多半殘缺）在資料結束時送出
            pending += [ReplayFrame(self.sim_end, _ORDER_FINAL_STATS, self._stats_message(row))
                        for row in self._stats.close_all()]
            pending.sort(key=lambda f: (f.due, f.order))
            self._done = True
            return pending
        for row in self._storage.readings_by_ids(ids):
            ts = parse_iso(str(row["timestamp"]))
            epoch = ts.timestamp()
            pending = [ReplayFrame(datetime.fromtimestamp(r.start_s + sp.STATS_WINDOW_S, tz=timezone.utc),
                                   _ORDER_STATS, self._stats_message(r))
                       for r in self._stats.close_before(epoch)]
            while self._event_pos < len(self._events) and self._events[self._event_pos][0] <= ts:
                pending.append(self._event_frame(self._event_pos))
                self._event_pos += 1
            pending.sort(key=lambda f: (f.due, f.order))
            frames.extend(pending)
            values = sp.scada_values(row["scada_json"], self._tag_ids)
            turbine_id = str(row["turbine_id"])
            frames.append(ReplayFrame(ts, _ORDER_READING, {
                "type": "reading", "ts": z(ts), "turbine_id": turbine_id,
                "values": sp.json_values(values, self.columns),
            }))
            self._stats.add(epoch, turbine_id, values.copy())
        self._pos += len(ids)
        return frames

    def iter_frames(self) -> Iterator[ReplayFrame]:
        """全部訊息（同步迭代；測試與 -07 OPC UA server 用）。

        Yields:
            依時間排序的訊息。
        """
        while True:
            frames = self.next_frames()
            if not frames and self._done:
                return
            yield from frames

    def _event_frame(self, index: int) -> ReplayFrame:
        ts, packed = self._events[index]
        return ReplayFrame(ts, _ORDER_EVENT, {"type": "event", **packed})

    def _stats_message(self, row: sp.StatsRow) -> Dict[str, JsonValue]:
        return sp.stats_message(row, self.columns, self.sample_period_s or self._stats.sample_period_s)


# ── 受測端的預測 ──────────────────────────────────────────────────────────────


def _load_vocabulary() -> FrozenSet[str]:
    data = json.loads(VOCABULARY_PATH.read_text(encoding="utf-8"))
    return frozenset(str(c["id"]) for c in data["components"])


VOCABULARY_COMPONENTS: FrozenSet[str] = _load_vocabulary()


def _optional_text(item: Dict[str, JsonValue], key: str) -> Optional[str]:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > MAX_TEXT_CHARS:
        raise ValueError(f"{key} 必須是字串（最多 {MAX_TEXT_CHARS} 字）")
    return value


def validate_prediction(item: Dict[str, JsonValue], turbines: Sequence[str]) -> Dict[str, JsonValue]:
    """檢查受測端送來的預測，回傳要存的欄位（合約 §6，不含 ``pack_id`` / ``ts``，由伺服器填）。

    受測端送來的 ``ts`` / ``pack_id`` 一律忽略；不認得的欄位不存。

    Args:
        item: ``{"type": "prediction", ...}`` 訊息。
        turbines: 回放的機組。

    Returns:
        ``turbine_id``、``category``、``component``、``manual_refs`` 與有給的 ``root_cause`` /
        ``actions`` / ``confidence``。

    Raises:
        ValueError: 格式不對（訊息說明原因）。
    """
    turbine_id = item.get("turbine_id")
    if not isinstance(turbine_id, str) or turbine_id not in turbines:
        raise ValueError(f"turbine_id 必須是回放的機組之一（收到 {turbine_id!r}）")
    category = item.get("category")
    if category not in PREDICTION_CATEGORIES:
        raise ValueError(f"category 必須是 {' / '.join(PREDICTION_CATEGORIES)}")
    component = item.get("component")
    if category in FAULT_CATEGORIES:
        if not isinstance(component, str) or not component:
            raise ValueError("故障診斷（real_fault / sensor_fault）必須有 component")
        if component not in VOCABULARY_COMPONENTS:
            raise ValueError(f"component 必須是 vocabulary.json 的元件 ID（收到 {component[:MAX_COMPONENT_CHARS]!r}）")
    elif component is not None and (not isinstance(component, str) or len(component) > MAX_COMPONENT_CHARS):
        raise ValueError(f"component 必須是字串（最多 {MAX_COMPONENT_CHARS} 字）或 null")
    refs = item.get("manual_refs", [])
    if (not isinstance(refs, list) or len(refs) > MAX_MANUAL_REFS
            or not all(isinstance(r, int) and not isinstance(r, bool) for r in refs)):
        raise ValueError(f"manual_refs 必須是事件碼（整數）的清單（最多 {MAX_MANUAL_REFS} 個）")
    out: Dict[str, JsonValue] = {
        "turbine_id": turbine_id, "category": category, "component": component, "manual_refs": list(refs),
    }
    root_cause = _optional_text(item, "root_cause")
    if root_cause is not None:
        out["root_cause"] = root_cause
    actions = item.get("actions")
    if actions is not None:
        if (not isinstance(actions, list) or len(actions) > MAX_ACTIONS
                or not all(isinstance(a, str) and len(a) <= MAX_TEXT_CHARS for a in actions)):
            raise ValueError(f"actions 必須是字串清單（最多 {MAX_ACTIONS} 項）")
        out["actions"] = list(actions)
    confidence = item.get("confidence")
    if confidence is not None:
        # 比較而不是 math.isfinite：極大整數的 isfinite 會 OverflowError；nan / inf 比較都不成立
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence 必須是 0–1 的數字")
        out["confidence"] = float(confidence)
    return out


def prediction_record(pack_id: str, sim_ts: datetime, fields: Dict[str, JsonValue]) -> Dict[str, JsonValue]:
    """存檔 / 匯出用的預測（合約 §6 的一行，``ts`` 為伺服器收到時的模擬時間）。

    Args:
        pack_id: 資料包 ID。
        sim_ts: 收到時的模擬時間。
        fields: ``validate_prediction`` 的結果。

    Returns:
        預測 dict（欄位順序同合約）。
    """
    return {"pack_id": pack_id, "turbine_id": fields["turbine_id"], "ts": z(sim_ts),
            **{k: v for k, v in fields.items() if k != "turbine_id"}}


# ── 回放的建立、狀態與預測匯出（REST 端點與 CLI 共用）───────────────────────────


def create_run(storage: Storage, scenario_id: int, *, mode: str = "evaluation", speed: float = DEFAULT_SPEED,
               label: Optional[str] = None, expires_in_hours: float = DEFAULT_EXPIRES_HOURS,
               created_by: Optional[str] = None, allow_overlap: bool = False) -> Tuple[Dict[str, JsonValue], str]:
    """建立回放。

    Args:
        storage: 情境所在的 storage。
        scenario_id: 情境 session id。
        mode: ``evaluation`` / ``practice``。
        speed: 回放速度（``MIN_SPEED``–``MAX_SPEED``）。
        label: 出題者備註（受測端看不到）。
        expires_in_hours: token 有效時數（``MAX_EXPIRES_HOURS`` 以內）。
        created_by: 建立者。
        allow_overlap: 同一個情境已有另一種模式（未撤銷）的回放時仍建立。預設拒絕：練習回放可以先看完
            正式評測的整段資料（DEC-20261022-02）。

    Returns:
        ``(回放 dict, token)``——token 只在這裡出現一次，DB 只存 sha256。

    Raises:
        ScenarioPackError: 情境不存在或不能回放。
        ReplayRunConflict: 同情境已有另一種模式的回放（``allow_overlap`` 為 False 時）。
        ValueError: 參數超出範圍。
    """
    if mode not in REPLAY_MODES:
        raise ValueError(f"mode 必須是 {' / '.join(REPLAY_MODES)}")
    if not MIN_SPEED <= speed <= MAX_SPEED:
        raise ValueError(f"speed 必須在 {MIN_SPEED}–{MAX_SPEED}")
    if not 0 < expires_in_hours <= MAX_EXPIRES_HOURS:
        raise ValueError(f"expires_in_hours 必須在 0–{MAX_EXPIRES_HOURS}")
    scenario = sp.load_exportable_scenario(storage, scenario_id, MAX_REPLAY_ROWS)
    if mode == "evaluation":
        config = scenario["config"]
        period = sp.positive_number(config.get("time_step") if isinstance(config, dict) else None) or 10.0
        turbines = len(storage.scenario_turbine_ids(scenario_id))
        limit = EVAL_MAX_READINGS_PER_S * period / max(1, turbines)
        if speed > limit:
            raise ValueError(f"正式評測的速度上限是 {limit:g}×（{turbines} 台機組、每 {period:g} 秒一筆：伺服器每秒最多穩定送 "
                             f"{EVAL_MAX_READINGS_PER_S:g} 筆讀值，跟不上時落後的時間會算在受測端頭上）")
    if not allow_overlap:
        others = [r for r in storage.list_replay_runs(scenario_id) if r["mode"] != mode and not r["revoked_at"]]
        if others:
            raise ReplayRunConflict(
                f"情境 {scenario_id} 已有{'練習' if mode == 'evaluation' else '正式評測'}回放 "
                f"#{others[0]['id']}：練習回放可以先看完正式評測的資料。請換一個情境，或先撤銷那個回放"
                "（確定要並存才帶 allow_overlap）"
            )
    token = new_token()
    now = datetime.fromtimestamp(wall_time(), tz=timezone.utc)
    run = storage.create_replay_run(scenario_id, token_digest(token), mode, float(speed), label, iso_utc(now),
                                    created_by, iso_utc(now + timedelta(hours=expires_in_hours)))
    return run, token


def run_view(storage: Storage, run: Dict[str, JsonValue]) -> Dict[str, JsonValue]:
    """回放 → 給出題端看的狀態（不含 token；加上資料包 ID、狀態、單次回放的預計結束時間）。

    Args:
        storage: 情境所在的 storage。
        run: ``storage.get_replay_run`` 的結果。

    Returns:
        dict，``status`` ∈ ``ready``（練習）/ ``not_started`` / ``running`` / ``finished`` / ``expired`` /
        ``revoked``。
    """
    now = wall_time()
    view = dict(run)
    view["pack_id"] = sp.pack_id_for(int(str(run["scenario_id"])))
    ends_at: Optional[str] = None
    bounds = storage.session_reading_bounds(int(str(run["scenario_id"])))
    if run["mode"] == "evaluation" and run["started_at"] and bounds is not None:
        span = (parse_iso(bounds[1]) - parse_iso(bounds[0])).total_seconds()
        ends_at = iso_utc(parse_iso(str(run["started_at"])) + timedelta(seconds=span / float(str(run["speed"]))))
    view["ends_at"] = ends_at
    expired = parse_iso(str(run["expires_at"])).timestamp() < now
    if run["revoked_at"]:
        status = "revoked"
    elif run["mode"] == "practice":
        status = "expired" if expired else "ready"
    elif not run["started_at"]:
        status = "expired" if expired else "not_started"
    elif ends_at is not None and parse_iso(ends_at).timestamp() + CLOSE_GRACE_S < now:
        status = "finished"
    else:
        status = "running"
    view["status"] = status
    return view


def predictions_jsonl(storage: Storage, run_id: int, connection_no: Optional[int] = None) -> str:
    """回放收到的預測（``predictions.jsonl`` 內容，可直接給 starter kit 的 ``score.py``）。

    Args:
        storage: 情境所在的 storage。
        run_id: 回放 id。
        connection_no: 只取某次連線的（練習模式每次連線各自從頭播，評分時要分開）；None＝全部。

    Returns:
        JSONL 文字。
    """
    return "".join(json.dumps(row["prediction"], ensure_ascii=False) + "\n"
                   for row in storage.replay_predictions(run_id, connection_no))
