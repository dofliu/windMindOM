import sqlite3
import json
from array import array
import threading
import time as _time
from datetime import datetime, timedelta
from typing import Dict, Iterator, List, Optional, Tuple
from pathlib import Path

try:
    # Normal package import (when imported via `modules.monitoring.server.storage`)
    from .sqlite_utils import open_sqlite
except ImportError:
    # sys.path-injected import (when imported via `server.storage` per run.py)
    from sqlite_utils import open_sqlite  # type: ignore[no-redef]

try:
    # 套件模式（modules.monitoring.server.storage）
    from ..simulator.time_utils import iso_utc, normalize_iso, parse_iso, utc_now
except ImportError:
    # sys.path 注入模式（server.storage；modules/monitoring 在 sys.path）
    from simulator.time_utils import iso_utc, normalize_iso, parse_iso, utc_now  # type: ignore[no-redef]


import os as _os
DB_PATH = Path(_os.environ.get("DB_PATH", str(Path(__file__).parent.parent / "wind_farm_data.db")))

# 時間戳 schema 版本（``PRAGMA user_version``）：1＝所有時間戳欄位都是 ``iso_utc`` 格式的 UTC
# （WMOM-20261021-03-c）。0＝舊版，時間戳為 naive 伺服器本地時間，開檔時一次性轉換。
TIMESTAMP_SCHEMA_VERSION = 1
# 存時間戳的欄位（表, 欄）
_TIMESTAMP_COLUMNS = (
    ("turbine_data", "timestamp"),
    ("turbine_data_1m", "timestamp"),
    ("turbine_data_10m", "timestamp"),
    ("turbine_snapshots", "timestamp"),
    ("sessions", "started_at"),
    ("sessions", "ended_at"),
    ("history_events", "timestamp"),
    ("history_events", "end_timestamp"),
    ("work_orders", "created_at"),
    ("work_orders", "completed_at"),
)
# sessions.config_json 內的時間戳鍵（情境的模擬時間窗）
_SESSION_CONFIG_TIME_KEYS = ("sim_start", "sim_end")
# 舊 DB 轉換的每批列數（依 rowid 區段）：每批 commit，WAL 峰值約為一批的大小而非整個 DB
_MIGRATION_BATCH_ROWS = 20_000

# ── 可觀測事件的判定（盲測，WMOM-20261021-04）──
# 白名單：真實 SCADA 看得到的只有 PLC 事件與運轉狀態轉換。其餘（情境 / 測試計畫的注入與跳機標記、
# 故障生命週期、Live 的 FaultEngine 跳機 / 解除、操作 / 設定紀錄、疲勞等級）都不是可觀測事件——
# 很多直接反映 FaultEngine 的內部狀態＝答案。新來源預設不可觀測，要明確加進白名單。
OBSERVABLE_EVENT_SOURCES = frozenset({"plc"})
# SQL 預篩用（對外唯讀 API 的 Live 事件，WMOM-20261125-02）：可觀測事件只可能來自這些來源——PLC 事件與
# 模擬器記錄的運轉狀態轉換。它只縮小掃描範圍；是否可觀測仍由 ``is_observable_event`` 判定。
OBSERVABLE_CANDIDATE_SOURCES = OBSERVABLE_EVENT_SOURCES | {"simulator"}
# payload 帶這些鍵＝含故障 ID（雙重保險：即使來源在白名單也排除）
_GROUND_TRUTH_PAYLOAD_KEYS = frozenset({"scenarioId", "faults"})


def is_observable_event(event: dict) -> bool:
    """事件是否為「真實 SCADA 也看得到」的可觀測事件（不含任何故障根因）。

    Args:
        event: ``query_events`` 回傳的事件 dict（``payload`` 已解析）。

    Returns:
        PLC 事件（``source="plc"``）與運轉狀態轉換（``source="simulator"``、payload 有
        ``fromState`` / ``toState``）為 True；其他一律 False。
    """
    payload = event.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    if _GROUND_TRUTH_PAYLOAD_KEYS & payload.keys():
        return False
    if event.get("source") in OBSERVABLE_EVENT_SOURCES:
        return True
    return event.get("source") == "simulator" and "fromState" in payload and "toState" in payload


def _naive_ts_sql(column: str) -> str:
    """SQL 條件：欄位是可解析、但沒有時區後綴的 naive 時間字串（舊版本地時間）。

    Args:
        column: 欄位名稱。

    Returns:
        可放進 ``WHERE`` 的 SQL 條件。
    """
    return (
        f"{column} IS NOT NULL AND {column} != '' "
        f"AND substr({column}, -1) NOT IN ('Z', 'z') "
        f"AND NOT (substr({column}, -6, 1) IN ('+', '-') AND substr({column}, -3, 1) = ':') "
        f"AND strftime('%s', {column}) IS NOT NULL"
    )


def _local_to_utc_sql(column: str) -> str:
    """SQL 運算式：naive 本地時間字串 → ``iso_utc`` 格式。

    整秒部分用 SQLite 'utc' 修飾詞以本機時區換算；小數秒原字串保留並補到 6 位——不用 ``%f``（只到
    毫秒且會四捨五入），否則與 Python ``normalize_iso``（情境 ``sim_start``）的結果差幾百微秒，
    落在情境時間窗邊界的事件會被查詢排除。

    Args:
        column: 欄位名稱。

    Returns:
        SQL 運算式。
    """
    return (
        f"strftime('%Y-%m-%dT%H:%M:%S', substr({column}, 1, 19), 'utc') || "
        f"substr(CASE WHEN substr({column}, 20, 1) = '.' THEN substr({column}, 20) ELSE '.' END "
        f"|| '000000', 1, 7) || '+00:00'"
    )


def reading_timestamp(reading: dict) -> str:
    """reading 寫進 ``turbine_data.timestamp`` 的時間戳（``iso_utc`` 格式）。

    Args:
        reading: 模擬器 / OPC adapter 的 reading。

    Returns:
        與 ``store_readings`` 落庫時相同的字串。
    """
    return _reading_timestamp(reading)


def _reading_timestamp(reading: dict) -> str:
    """reading 的時間戳 → ``iso_utc`` 格式；缺值用現在時刻。

    Args:
        reading: 模擬器 / OPC adapter 的 reading（``timestamp`` 可為字串或 ``datetime``）。

    Returns:
        ``iso_utc`` 格式字串。
    """
    ts = reading.get('timestamp')
    if isinstance(ts, datetime):
        return iso_utc(ts)
    if ts:
        return normalize_iso(str(ts)) or iso_utc()
    return iso_utc()


class Storage:
    """SQLite-based time-series storage for turbine readings and history events.

    Data tiers:
      - turbine_data:        10s writes (configurable), 3-day retention for raw
      - turbine_data_1m:     1-min aggregates, 90-day retention
      - turbine_data_10m:    10-min aggregates, permanent
      - turbine_snapshots:   1s high-freq capture around events, permanent
      - sessions:            tracks simulation/data source configs
      - history_events:      可觀測事件 + 操作 / 注入標記（``session_id`` 隔離，WMOM-20261021-04）
      - scenario_ground_truth: 情境的標準答案（與可觀測事件分開存，盲測，WMOM-20261021-04）
      - replay_runs / replay_predictions: 情境 WebSocket 回放與受測端的預測（WMOM-20261021-06）
    """

    def __init__(self, db_path: str = str(DB_PATH), migrate_timestamps: bool = True):
        """開啟（必要時建立）DB。

        Args:
            db_path: SQLite 檔路徑。
            migrate_timestamps: 開檔時把舊版 naive 本地時間轉成 UTC（WMOM-20261021-03-c）。維護工具
                （例：``tools/vacuum_db.py`` 先清理再壓縮）可傳 False，避免先改寫即將刪掉的列。
        """
        self._db_path = db_path
        self._local = threading.local()
        self._migrate_timestamps = migrate_timestamps
        self._init_db()

    @property
    def db_path(self) -> str:
        """SQLite 檔路徑。"""
        return self._db_path

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            # WAL + busy_timeout=5s — see sqlite_utils.open_sqlite for rationale.
            # 修 #WMOM-20260504-09: 解決 maintenance thread 跑 cleanup 時其它 thread
            # 撞到 "database is locked" 的並發問題。
            self._local.conn = open_sqlite(self._db_path)
        return self._local.conn

    def _init_db(self):
        conn = open_sqlite(self._db_path)

        # ── Main raw data table (10s interval writes) ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS turbine_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                turbine_id TEXT NOT NULL,
                session_id INTEGER,
                status TEXT,
                tur_state INTEGER,
                wind_speed REAL,
                power_output REAL,
                rotor_speed REAL,
                blade_angle REAL,
                temperature REAL,
                vibration REAL,
                voltage REAL,
                current_amp REAL,
                yaw_angle REAL,
                gearbox_temp REAL,
                frequency REAL,
                hydraulic_pressure REAL,
                scada_json TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_turbine_time
            ON turbine_data (turbine_id, timestamp)
        """)

        # ── 1-minute aggregate table ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS turbine_data_1m (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                turbine_id TEXT NOT NULL,
                session_id INTEGER,
                power_output_avg REAL,
                power_output_max REAL,
                power_output_min REAL,
                wind_speed_avg REAL,
                wind_speed_max REAL,
                rotor_speed_avg REAL,
                temperature_avg REAL,
                vibration_avg REAL,
                vibration_max REAL,
                sample_count INTEGER
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_1m_turbine_time
            ON turbine_data_1m (turbine_id, timestamp)
        """)

        # ── 10-minute aggregate table ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS turbine_data_10m (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                turbine_id TEXT NOT NULL,
                session_id INTEGER,
                power_output_avg REAL,
                power_output_max REAL,
                power_output_min REAL,
                wind_speed_avg REAL,
                wind_speed_max REAL,
                rotor_speed_avg REAL,
                temperature_avg REAL,
                vibration_avg REAL,
                vibration_max REAL,
                sample_count INTEGER
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_10m_turbine_time
            ON turbine_data_10m (turbine_id, timestamp)
        """)

        # ── Event snapshots (1s high-freq around events) ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS turbine_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                turbine_id TEXT NOT NULL,
                session_id INTEGER,
                event_ref TEXT,
                wind_speed REAL,
                power_output REAL,
                rotor_speed REAL,
                scada_json TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_turbine_time
            ON turbine_snapshots (turbine_id, timestamp)
        """)

        # session_id 索引（WMOM-20260719-02）：情境保存讓「依 session 過濾/刪除」成為第一手
        # 查詢模式（query_history(session_id=...) / delete_scenario），補索引避免全表掃描。
        for _tbl in ("turbine_data", "turbine_data_1m", "turbine_data_10m", "turbine_snapshots"):
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{_tbl}_session ON {_tbl} (session_id)"
            )

        # ── Sessions table ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                data_source TEXT NOT NULL,
                turbine_count INTEGER,
                rated_power_kw REAL,
                rotor_diameter_m REAL,
                model_name TEXT,
                config_json TEXT
            )
        """)

        # ── History events (existing) ──
        # ── 出發前準備卡（WMOM-20261125-05）：每張工單一張；answer_json 是評分用的答案，不對外 ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS briefing_cards (
                work_order_id TEXT PRIMARY KEY,
                business_key TEXT NOT NULL,
                turbine_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                created_at TEXT NOT NULL,
                data_cutoff TEXT NOT NULL,
                card_json TEXT NOT NULL,
                answer_json TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_briefing_cards_key ON briefing_cards (business_key)")

        # ── 不對外的故障紀錄（WMOM-20261125-06-c）：即時風場每一筆故障的發生、第一次警報、跳機、修復 ──
        # 這是 Live 版的標準答案：只給評分端，不進對外 API、準備卡、可觀測事件
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fault_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                turbine_id TEXT NOT NULL,
                scenario_id TEXT NOT NULL,
                origin TEXT NOT NULL,
                onset_ts TEXT NOT NULL,
                first_alarm_ts TEXT,
                first_alarm_code INTEGER,
                trip_ts TEXT,
                trip_code INTEGER,
                trip_count INTEGER NOT NULL DEFAULT 0,
                observed_json TEXT NOT NULL DEFAULT '[]',
                cleared_ts TEXT,
                cleared_by TEXT,
                severity_rate REAL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fault_records_open ON fault_records (turbine_id, cleared_ts)")

        # ── 風場的設定（WMOM-20261125-06）：故障產生器、模擬維修班；key → JSON ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS farm_settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # ── 匯入的實測風況序列（WMOM-20261125-07）：資料是 numpy npz，摘要是 JSON ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wind_series (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                summary_json TEXT NOT NULL,
                data BLOB NOT NULL
            )
        """)

        # ── 運轉狀態紀錄（WMOM-20261125-04）：每台機組每小時在各種狀態下的秒數與電量 ──
        # 可用率、停機時數、損失發電量由它計算；只記 Live（即時模擬），永久保留（一台機組一年 8,760 列）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS availability_hourly (
                turbine_id TEXT NOT NULL,
                hour TEXT NOT NULL,
                producing_s REAL NOT NULL DEFAULT 0,
                ready_s REAL NOT NULL DEFAULT 0,
                planned_s REAL NOT NULL DEFAULT 0,
                unplanned_s REAL NOT NULL DEFAULT 0,
                energy_kwh REAL NOT NULL DEFAULT 0,
                lost_planned_kwh REAL NOT NULL DEFAULT 0,
                lost_unplanned_kwh REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (turbine_id, hour)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS history_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                end_timestamp TEXT,
                turbine_id TEXT,
                event_type TEXT NOT NULL,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT,
                payload_json TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_events_turbine_time
            ON history_events (turbine_id, timestamp)
        """)

        # ── Work Orders ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS work_orders (
                id TEXT PRIMARY KEY,
                turbine_id INTEGER NOT NULL,
                turbine_name TEXT NOT NULL,
                technician_id INTEGER,
                status TEXT NOT NULL DEFAULT 'OPEN',
                created_at TEXT NOT NULL,
                completed_at TEXT,
                fault_description TEXT NOT NULL,
                notes TEXT DEFAULT '',
                photos_json TEXT DEFAULT '[]'
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_work_orders_status
            ON work_orders (status)
        """)

        # ── Technicians ──
        conn.execute("""
            CREATE TABLE IF NOT EXISTS technicians (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ON_DUTY'
            )
        """)

        # Seed default technicians if empty
        existing = conn.execute("SELECT COUNT(*) FROM technicians").fetchone()[0]
        if existing == 0:
            for name, status in [
                ("Alice Johnson", "ON_DUTY"),
                ("Bob Williams", "ON_DUTY"),
                ("Charlie Brown", "ON_DUTY"),
                ("Diana Miller", "OFF_DUTY"),
            ]:
                conn.execute("INSERT INTO technicians (name, status) VALUES (?, ?)", (name, status))

        # ── Migrations for existing DBs ──
        self._migrate_columns(conn, "turbine_data", [
            ("scada_json", "TEXT"),
            ("tur_state", "INTEGER"),
            ("session_id", "INTEGER"),
        ])
        self._migrate_columns(conn, "history_events", [
            ("end_timestamp", "TEXT"),
            # 事件所屬 session（WMOM-20261021-04）：情境的事件以此隔離，不再靠模擬時間窗比對；
            # 舊列為 NULL（呼叫端依情境 config.events_session_isolated 決定要不要退回時間窗）
            ("session_id", "INTEGER"),
        ])
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_events_session
            ON history_events (session_id, timestamp)
        """)

        # ── 情境標準答案（ground truth，WMOM-20261021-04）──
        # 與 history_events / sessions.config_json 分開存：可觀測資料（讀值、事件、情境詮釋資料）
        # 不含任何故障根因，答案只在這張表（設計文件 §4 盲測原則）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scenario_ground_truth (
                session_id INTEGER PRIMARY KEY,
                contract_version TEXT NOT NULL,
                ground_truth_json TEXT NOT NULL
            )
        """)

        # ── 情境回放（WMOM-20261021-06）──
        # 受測端以回放 token 連線（不開帳號，DEC-20261021-03）；只存 token 的 sha256。
        # evaluation 回放的時鐘從第一次連線（started_at）起算，重啟伺服器也接得上
        conn.execute("""
            CREATE TABLE IF NOT EXISTS replay_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scenario_id INTEGER NOT NULL,
                token_sha256 TEXT NOT NULL UNIQUE,
                mode TEXT NOT NULL,
                speed REAL NOT NULL,
                label TEXT,
                created_at TEXT NOT NULL,
                created_by TEXT,
                expires_at TEXT NOT NULL,
                started_at TEXT,
                connections INTEGER NOT NULL DEFAULT 0,
                revoked_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_replay_runs_scenario ON replay_runs (scenario_id)")
        # 受測端經 WS 送來的預測；sim_ts 是伺服器收到時的回放模擬時間（時間因果由伺服器保證）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS replay_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                connection_no INTEGER NOT NULL,
                received_at TEXT NOT NULL,
                sim_ts TEXT NOT NULL,
                prediction_json TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_replay_predictions_run ON replay_predictions (run_id, id)")

        conn.commit()
        if self._migrate_timestamps:
            self._migrate_timestamps_to_utc(conn)
        conn.close()

    @staticmethod
    def _migrate_timestamps_to_utc(conn: sqlite3.Connection) -> None:
        """舊 DB（naive 本地時間）→ UTC 時間戳，一次性（WMOM-20261021-03-c）。

        只轉換沒有時區後綴的值，依 rowid 區段分批、每批 commit：中斷後下次開檔接著轉剩下的列，
        全部完成才把 ``PRAGMA user_version`` 設成新版本。新建的空 DB 直接標成新版本。換算用本機
        時區（SQLite 'utc' 修飾詞 / Python ``astimezone``），即假設 DB 在寫入它的同一時區被開啟。
        就地改寫、不可逆：大 DB 建議先備份。

        Args:
            conn: 已開啟的連線（本方法會 commit）。
        """
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= TIMESTAMP_SCHEMA_VERSION:
            return
        converted = 0
        announced = False
        for table, column in _TIMESTAMP_COLUMNS:
            naive = _naive_ts_sql(column)
            if conn.execute(f"SELECT 1 FROM {table} WHERE {naive} LIMIT 1").fetchone() is None:
                continue
            if not announced:
                tz_name = datetime.now().astimezone().tzname()
                print(f"[Storage] 舊版時間戳（naive 本地時間，以本機時區 {tz_name} 換算）轉為 UTC，"
                      f"一次性就地改寫（WMOM-20261021-03-c）……")
                announced = True
            max_rowid = conn.execute(f"SELECT MAX(rowid) FROM {table}").fetchone()[0] or 0
            for low in range(0, max_rowid, _MIGRATION_BATCH_ROWS):
                converted += conn.execute(
                    f"UPDATE {table} SET {column} = {_local_to_utc_sql(column)} "
                    f"WHERE rowid > ? AND rowid <= ? AND {naive}",
                    (low, low + _MIGRATION_BATCH_ROWS),
                ).rowcount
                conn.commit()
        for row in conn.execute("SELECT id, config_json FROM sessions WHERE config_json IS NOT NULL").fetchall():
            try:
                cfg = json.loads(row[1])
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(cfg, dict):
                continue
            changed = False
            for key in _SESSION_CONFIG_TIME_KEYS:
                value = cfg.get(key)
                if isinstance(value, str) and value:
                    normalized = normalize_iso(value)
                    if normalized != value:
                        cfg[key] = normalized
                        changed = True
            if changed:
                conn.execute("UPDATE sessions SET config_json = ? WHERE id = ?", (json.dumps(cfg), row[0]))
                converted += 1
        conn.execute(f"PRAGMA user_version = {TIMESTAMP_SCHEMA_VERSION}")
        conn.commit()
        if converted:
            print(f"[Storage] 時間戳轉為 UTC 完成：{converted} 個欄位值")

    def _migrate_columns(self, conn, table: str, columns: list):
        """Add missing columns to existing tables."""
        for col_name, col_type in columns:
            try:
                conn.execute(f"SELECT {col_name} FROM {table} LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")

    # ══════════════════════════════════════════════════════════════════
    #  Session Management
    # ══════════════════════════════════════════════════════════════════

    def create_session(self, data_source: str, turbine_count: int,
                       rated_power_kw: float = None, rotor_diameter_m: float = None,
                       model_name: str = None, config: dict = None) -> int:
        """Create a new session and return its ID."""
        conn = self._get_conn()
        cursor = conn.execute("""
            INSERT INTO sessions (started_at, data_source, turbine_count,
                                  rated_power_kw, rotor_diameter_m, model_name, config_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            iso_utc(),
            data_source,
            turbine_count,
            rated_power_kw,
            rotor_diameter_m,
            model_name,
            json.dumps(config) if config else None,
        ))
        conn.commit()
        return cursor.lastrowid

    def end_session(self, session_id: int):
        """Mark a session as ended."""
        conn = self._get_conn()
        conn.execute("UPDATE sessions SET ended_at = ? WHERE id = ?",
                     (iso_utc(), session_id))
        conn.commit()

    def get_sessions(self, limit: int = 20) -> List[dict]:
        """Return the most recent sessions, newest first."""
        """Return recent sessions ordered by newest first."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            if d.get("config_json"):
                try:
                    d["config"] = json.loads(d["config_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append(d)
        return result

    def get_active_session(self) -> Optional[dict]:
        """Return the most recent non-ended *Live* session, or None.

        主動排除情境 session（config_json.kind == "scenario"）：情境本應在生成後被
        end_session，但即使中途失敗、或未來改多 worker / 背景任務，也不能讓一個尚未
        結束的情境 session 頂替 Live 被當成 active（防禦性，不依賴呼叫時機）。
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM sessions "
            "WHERE ended_at IS NULL "
            "  AND (json_extract(config_json, '$.kind') IS NULL "
            "       OR json_extract(config_json, '$.kind') != ?) "
            "ORDER BY id DESC LIMIT 1",
            (self.SCENARIO_KIND,),
        ).fetchone()
        return self._session_row_to_dict(row) if row else None

    # ── Scenario sessions（DEC-20260718-01 情境保存）──────────────────
    # 情境＝一個以 config_json.kind == "scenario" 標記的專屬 session；批次生成的
    # 資料寫進該 session_id，與 Live/其他歷史隔離，可事後 list / load / delete。
    SCENARIO_KIND = "scenario"

    @staticmethod
    def _session_row_to_dict(row: sqlite3.Row) -> dict:
        """把 sessions 資料列轉 dict，並把 config_json 解析到 ``config``。"""
        d = dict(row)
        if d.get("config_json"):
            try:
                d["config"] = json.loads(d["config_json"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

    def update_session_config(self, session_id: int, updates: dict) -> None:
        """把 ``updates`` 併入指定 session 的 config_json（其餘鍵保留）。

        情境生成前先 ``create_session`` 拿到 id 才能寫資料，故總筆數/注入數/時間窗
        等統計要等生成後才知道——用本方法回填。
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT config_json FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return
        cfg: dict = {}
        if row["config_json"]:
            try:
                cfg = json.loads(row["config_json"])
            except (json.JSONDecodeError, TypeError):
                cfg = {}
        cfg.update(updates)
        conn.execute(
            "UPDATE sessions SET config_json = ? WHERE id = ?",
            (json.dumps(cfg), session_id),
        )
        conn.commit()

    def list_scenarios(self, limit: int = 50) -> List[dict]:
        """列出已保存情境（config_json.kind == "scenario"），最新在前。"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM sessions "
            "WHERE json_extract(config_json, '$.kind') = ? "
            "ORDER BY id DESC LIMIT ?",
            (self.SCENARIO_KIND, limit),
        ).fetchall()
        return [self._session_row_to_dict(r) for r in rows]

    def get_scenario(self, scenario_id: int) -> Optional[dict]:
        """取單一情境；不存在或非情境 session 回 None。"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM sessions "
            "WHERE id = ? AND json_extract(config_json, '$.kind') = ?",
            (scenario_id, self.SCENARIO_KIND),
        ).fetchone()
        return self._session_row_to_dict(row) if row else None

    def delete_scenario(self, scenario_id: int) -> bool:
        """刪除情境 session 及其所有資料列；回傳是否真的刪到一個情境。

        僅作用在情境 session（kind == "scenario"）——避免誤刪 Live session 的資料。
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id FROM sessions "
            "WHERE id = ? AND json_extract(config_json, '$.kind') = ?",
            (scenario_id, self.SCENARIO_KIND),
        ).fetchone()
        if row is None:
            return False
        # history_events 自 WMOM-20261021-04 起帶 session_id：一併刪除本情境的事件與標準答案。
        # 更早生成的情境事件 session_id 為 NULL，仍會成為孤兒（DEC-20260719-01 trade-off）。
        for table in ("turbine_data", "turbine_data_1m",
                      "turbine_data_10m", "turbine_snapshots",
                      "history_events", "scenario_ground_truth"):
            conn.execute(f"DELETE FROM {table} WHERE session_id = ?", (scenario_id,))
        conn.execute("DELETE FROM replay_predictions WHERE run_id IN "
                     "(SELECT id FROM replay_runs WHERE scenario_id = ?)", (scenario_id,))
        conn.execute("DELETE FROM replay_runs WHERE scenario_id = ?", (scenario_id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (scenario_id,))
        conn.commit()
        return True

    def scenario_turbine_aggregates(self, session_id: int) -> List[dict]:
        """情境（session）內每台機組的物理輸出聚合——A0 情境摘要端點用（DEC-20260720-02）。

        以 ``session_id`` 隔離、掃該情境的 raw ``turbine_data``，用 SQLite ``json_extract`` 直接在
        SQL 內取值，避免把整個情境（長情境可達數十萬列/機組）載進 Python 再算。**依物理量本質分兩類、
        各用正確的聚合方式**（這點很關鍵——用錯會得到語意上錯誤的數字）：

        **A. 全情境統計（``GROUP BY``）**
        - 功率：``AVG``/``MAX``（用 ``power_output`` 欄位，MW；呼叫端 ×1000 轉 kW、算能量/容量因數）。
        - 累積損傷 / 生產時數（**單調遞增**的累積計數器）→ ``MAX(json_extract)`` 即末值。
        - 極限負載（瞬時彎矩峰值）→ ``MAX``（情境中經歷過的最大負載）。
        - 各運轉狀態步數：``SUM(CASE tur_state=...)``。

        **B. 情境結束狀態（每台機組最後一列）**
        - RUL、DEL **非單調**，不可用 ``MIN``/``MAX`` 冒充「末值」：
          * ``WLOD_RulHours`` 是外推估計 ``prod_h·(1-dmg)/dmg``（``fatigue_model``），暖機期回 sentinel
            ``-1.0``、之後隨 prod_h 成長可**上升**——``MIN`` 會鎖在 -1.0 sentinel、``MAX`` 也非末值。
          * ``WLOD_Del*`` 每 10 分鐘視窗**重算並覆蓋**（非累積）——``MAX`` 取到的是「最差視窗」而非
            情境結束值。
          故改取該機組 ``timestamp`` 最大那列的真實值（``ROW_NUMBER() OVER (PARTITION BY turbine_id
          ORDER BY timestamp DESC)``）。RUL 的 sentinel（<0，暖機不足無法估計）在此映射為 ``None``。

        不可改用 ``turbine_data_1m``/``_10m`` 聚合表：downsampling 的 ``GROUP BY`` 不含 ``session_id``、
        會跨 session 混算（見 ``run_downsampling`` 註解）。``json_extract`` 對缺鍵/NULL 回 NULL、聚合
        自動略過；末值列缺鍵時該欄回 None。

        Args:
            session_id: 情境 session id。

        Returns:
            每台機組一個 dict（依 ``turbine_id`` 排序），含 ``n``（樣本步數）、A 類聚合、B 類末值；
            該 session 無資料時回空 list。
        """
        conn = self._get_conn()
        # A. 全情境統計（AVG/MAX/SUM）——僅適用單調累積量、峰值與計數。
        agg_rows = conn.execute(
            """
            SELECT
                turbine_id,
                COUNT(*)                                           AS n,
                AVG(power_output)                                  AS avg_power_mw,
                MAX(power_output)                                  AS max_power_mw,
                MAX(json_extract(scada_json, '$.WLOD_ProdHours'))  AS prod_hours,
                MAX(json_extract(scada_json, '$.WLOD_DmgTwrFa'))   AS dmg_tower_fa,
                MAX(json_extract(scada_json, '$.WLOD_DmgTwrSs'))   AS dmg_tower_ss,
                MAX(json_extract(scada_json, '$.WLOD_DmgBldFlap')) AS dmg_blade_flap,
                MAX(json_extract(scada_json, '$.WLOD_DmgBldEdge')) AS dmg_blade_edge,
                MAX(json_extract(scada_json, '$.WLOD_TwrFaMom'))   AS max_tower_fa_moment,
                MAX(json_extract(scada_json, '$.WLOD_TwrSsMom'))   AS max_tower_ss_moment,
                MAX(json_extract(scada_json, '$.WLOD_BldFlapMom')) AS max_blade_flap_moment,
                MAX(json_extract(scada_json, '$.WLOD_BldEdgeMom')) AS max_blade_edge_moment,
                SUM(CASE WHEN tur_state = 6 THEN 1 ELSE 0 END)     AS production_steps,
                SUM(CASE WHEN tur_state = 7 THEN 1 ELSE 0 END)     AS estop_steps
            FROM turbine_data
            WHERE session_id = ?
            GROUP BY turbine_id
            ORDER BY turbine_id
            """,
            (session_id,),
        ).fetchall()

        # B. 情境結束狀態：每台機組最後一列（timestamp 最大，id 為同秒的決勝）的 RUL/DEL 真實值。
        final_rows = conn.execute(
            """
            SELECT
                turbine_id,
                json_extract(scada_json, '$.WLOD_RulHours')   AS rul_hours,
                json_extract(scada_json, '$.WLOD_DelTwrFa')   AS del_tower_fa,
                json_extract(scada_json, '$.WLOD_DelTwrSs')   AS del_tower_ss,
                json_extract(scada_json, '$.WLOD_DelBldFlap') AS del_blade_flap,
                json_extract(scada_json, '$.WLOD_DelBldEdge') AS del_blade_edge
            FROM (
                SELECT turbine_id, scada_json,
                       ROW_NUMBER() OVER (
                           PARTITION BY turbine_id ORDER BY timestamp DESC, id DESC
                       ) AS rn
                FROM turbine_data
                WHERE session_id = ?
            )
            WHERE rn = 1
            """,
            (session_id,),
        ).fetchall()
        final_by_id = {r["turbine_id"]: dict(r) for r in final_rows}

        result = []
        for row in agg_rows:
            d = dict(row)
            final = final_by_id.get(d["turbine_id"], {})
            rul = final.get("rul_hours")
            # RUL sentinel（<0：暖機不足 / 損傷過小，無法估計）→ None
            d["rul_hours"] = rul if (rul is not None and rul >= 0) else None
            for key in ("del_tower_fa", "del_tower_ss", "del_blade_flap", "del_blade_edge"):
                d[key] = final.get(key)
            result.append(d)
        return result

    def count_scenario_fault_events(self, start: Optional[str] = None,
                                    end: Optional[str] = None,
                                    session_id: Optional[int] = None) -> Dict[str, int]:
        """每台機組（有 turbine_id 者）的 ``fault`` 事件數——A0 摘要用。

        用 SQL ``COUNT ... GROUP BY`` 直接計數（**不設 LIMIT**，避免長/密集情境下靜默截斷少算），並排除
        farm-wide（``turbine_id IS NULL``）事件。兩種模式：

        - **session 模式**（給 ``session_id``，WMOM-20261021-04 之後的情境）：只數該 session 的 PLC 警報成立
          與跳機（``source="plc"``、``kind`` 為 ``alarm_raised`` / ``trip``）——同 session 還有解除、資訊
          （切出風速 I201）、狀態轉換等 ``event_type="fault"`` 的事件，全算進去會讓健康機組也「有故障事件」。
        - **時間窗模式**（舊情境，事件沒有 session）：``sim_start..sim_end`` 內所有 ``fault`` 事件；非 session
          隔離，時間窗重疊的其他情境事件可能混入（故摘要回傳帶 ``eventsByTimeWindow`` 旗標）。時間窗邊界
          比照 ``query_events``（``COALESCE(end_timestamp, timestamp) >= start`` / ``timestamp <= end``）。

        Args:
            start: 時間窗下界（含端點，比照 query_events）；None 表不限制下界。
            end: 時間窗上界（含端點）；None 表不限制上界。
            session_id: 只數這個 session 的事件；None＝不限 session（舊情境的時間窗模式）。

        Returns:
            ``{turbine_id: count}``；窗內無 fault 事件的機組不出現在 dict 中（呼叫端取 0）。
        """
        conn = self._get_conn()
        query = ("SELECT turbine_id, COUNT(*) AS cnt FROM history_events "
                 "WHERE event_type = 'fault' AND turbine_id IS NOT NULL")
        params: list = []
        if session_id is not None:
            query += (" AND session_id = ? AND source = 'plc' "
                      "AND json_extract(payload_json, '$.kind') IN ('alarm_raised', 'trip')")
            params.append(session_id)
        start, end = normalize_iso(start), normalize_iso(end)
        if start:
            query += " AND COALESCE(end_timestamp, timestamp) >= ?"
            params.append(start)
        if end:
            query += " AND timestamp <= ?"
            params.append(end)
        query += " GROUP BY turbine_id"
        rows = conn.execute(query, params).fetchall()
        return {r["turbine_id"]: r["cnt"] for r in rows}

    # ══════════════════════════════════════════════════════════════════
    #  Data Writing
    # ══════════════════════════════════════════════════════════════════

    def record_event(
        self,
        event_type: str,
        source: str,
        title: str,
        turbine_id: Optional[str] = None,
        detail: Optional[str] = None,
        payload: Optional[dict] = None,
        timestamp: Optional[str] = None,
        end_timestamp: Optional[str] = None,
        session_id: Optional[int] = None,
    ):
        """Store a history event for chart markers and audit-style review.

        ``timestamp`` / ``end_timestamp`` 正規化成 UTC（``iso_utc``）；``timestamp`` 缺值用現在時刻。
        ``session_id``：事件所屬 session（WMOM-20261021-04）；None＝不屬於特定 session。
        """
        conn = self._get_conn()
        conn.execute(self._INSERT_EVENT_SQL, self._event_row(
            event_type, source, title, turbine_id, detail, payload, timestamp, end_timestamp, session_id,
        ))
        conn.commit()

    _INSERT_EVENT_SQL = """
        INSERT INTO history_events
        (timestamp, end_timestamp, turbine_id, event_type, source, title, detail, payload_json, session_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    @staticmethod
    def _event_row(event_type: str, source: str, title: str, turbine_id: Optional[str],
                   detail: Optional[str], payload: Optional[dict], timestamp: Optional[str],
                   end_timestamp: Optional[str], session_id: Optional[int]) -> tuple:
        """``history_events`` 一列的 INSERT 參數（``record_event`` / ``record_events`` 共用）。"""
        return (
            normalize_iso(timestamp) if timestamp else iso_utc(),
            normalize_iso(end_timestamp),
            turbine_id,
            event_type,
            source,
            title,
            detail,
            json.dumps(payload) if payload is not None else None,
            session_id,
        )

    def record_events(self, events: List[dict]) -> int:
        """批次寫入多筆事件，一次 commit（批次情境一次可能產生數千筆事件，WMOM-20261021-04）。

        Args:
            events: 每筆是 ``record_event`` 的關鍵字參數 dict（``event_type``、``source``、``title``
                必填，其餘選填）。

        Returns:
            寫入筆數。
        """
        if not events:
            return 0
        conn = self._get_conn()
        conn.executemany(self._INSERT_EVENT_SQL, [
            self._event_row(
                e["event_type"], e["source"], e["title"], e.get("turbine_id"), e.get("detail"),
                e.get("payload"), e.get("timestamp"), e.get("end_timestamp"), e.get("session_id"),
            )
            for e in events
        ])
        conn.commit()
        return len(events)

    # ── 情境標準答案（WMOM-20261021-04）──

    def save_ground_truth(self, session_id: int, ground_truth: dict) -> None:
        """存（或覆寫）某情境 session 的標準答案。

        Args:
            session_id: 情境 session id。
            ground_truth: 標準答案 dict（``contract_version`` 必填，見 ``simulator/ground_truth.py``）。
        """
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO scenario_ground_truth (session_id, contract_version, ground_truth_json) "
            "VALUES (?, ?, ?)",
            (session_id, str(ground_truth["contract_version"]), json.dumps(ground_truth, ensure_ascii=False)),
        )
        conn.commit()

    def get_ground_truth(self, session_id: int) -> Optional[dict]:
        """取某情境 session 的標準答案；沒有（舊情境、非情境 session）回 None。

        Args:
            session_id: 情境 session id。

        Returns:
            標準答案 dict 或 None。
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT ground_truth_json FROM scenario_ground_truth WHERE session_id = ?", (session_id,),
        ).fetchone()
        return json.loads(row["ground_truth_json"]) if row else None

    def close_open_events(
        self,
        event_type: str,
        source: Optional[str] = None,
        turbine_id: Optional[str] = None,
        closed_at: Optional[str] = None,
    ):
        """Close open-ended events by setting end_timestamp."""
        conn = self._get_conn()
        query = """
            UPDATE history_events
            SET end_timestamp = ?
            WHERE event_type = ? AND end_timestamp IS NULL
        """
        params: list = [normalize_iso(closed_at) if closed_at else iso_utc(), event_type]
        if source is not None:
            query += " AND source = ?"
            params.append(source)
        if turbine_id is None:
            query += " AND turbine_id IS NULL"
        else:
            query += " AND turbine_id = ?"
            params.append(turbine_id)
        conn.execute(query, params)
        conn.commit()

    @staticmethod
    def _insert_reading(conn: sqlite3.Connection, reading: dict, session_id: Optional[int] = None) -> None:
        """執行單筆 turbine_data INSERT（**不 commit**）。

        供 ``store_reading``（單筆）與 ``store_readings``（批次一次 commit）共用，讓批次能包在
        單一 transaction 內——把逐列 commit 的鎖競爭降到最低（見 ``store_readings``）。
        """
        def to_float(v, default=0.0):
            try:
                return float(v) if v is not None else default
            except (TypeError, ValueError):
                return default

        scada = reading.get('scada', {})
        scada_json = json.dumps(scada) if scada else None
        tur_state = int(scada.get("WTUR_TurSt", 0)) if scada else None

        conn.execute("""
            INSERT INTO turbine_data
            (timestamp, turbine_id, session_id, status, tur_state, wind_speed, power_output,
             rotor_speed, blade_angle, temperature, vibration, voltage,
             current_amp, yaw_angle, gearbox_temp, frequency, hydraulic_pressure,
             scada_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            _reading_timestamp(reading),
            str(reading.get('turbine_id', '')),
            session_id,
            str(reading.get('operational_state', 'IDLE')),
            tur_state,
            to_float(reading.get('wind_speed', 0)),
            to_float(reading.get('total_power', 0)) / 1_000_000,
            to_float(scada.get('WROT_RotSpd', reading.get('rotor', {}).get('rotor_speed', 0))),
            to_float(scada.get('WROT_PtAngValBl1', reading.get('pitch_angle', 0))),
            to_float(scada.get('WGEN_GnStaTmp1', reading.get('generator', {}).get('temperature', 0))),
            to_float(scada.get('WNAC_VibMsNacXDir', reading.get('gearbox', {}).get('vibration', 0))),
            to_float(scada.get('WGEN_GnVtgMs', reading.get('generator', {}).get('voltage', 0))),
            to_float(scada.get('WGEN_GnCurMs', reading.get('generator', {}).get('current', 0))),
            to_float(scada.get('WYAW_YwVn1AlgnAvg5s', reading.get('yaw', {}).get('yaw_angle', 0))),
            to_float(scada.get('WNAC_NacTmp', reading.get('gearbox', {}).get('temperature', 0))),
            to_float(scada.get('WCNV_CnvGnFrq', reading.get('generator', {}).get('frequency')), None),
            to_float(scada.get('WYAW_YwBrkHyPrs', reading.get('hydraulic', {}).get('pressure')), None),
            scada_json,
        ))

    def store_reading(self, reading: dict, session_id: Optional[int] = None):
        """Store a single turbine reading (from simulator output dict)."""
        conn = self._get_conn()
        self._insert_reading(conn, reading, session_id)
        conn.commit()

    def store_readings(self, readings: List[dict], session_id: Optional[int] = None):
        """批次寫入：整批包在**單一 transaction**（一次 commit）。

        逐列 commit 在與 Live 迴圈 / maintenance thread 並行寫同一 SQLite 檔時會累積大量寫鎖
        取得 → Windows 上實測 generate-bulk 撞 ``database is locked``。一次 commit 大幅降低競爭
        且更快。批次失敗則整批 rollback（不留半批）。
        """
        if not readings:
            return
        conn = self._get_conn()
        try:
            for r in readings:
                self._insert_reading(conn, r, session_id)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def store_snapshot(self, reading: dict, event_ref: str, session_id: int = None):
        """Store a 1s snapshot reading linked to an event."""
        conn = self._get_conn()
        scada = reading.get('scada', {})
        scada_json = json.dumps(scada) if scada else None

        def to_float(v, default=0.0):
            try:
                return float(v) if v is not None else default
            except (TypeError, ValueError):
                return default

        conn.execute("""
            INSERT INTO turbine_snapshots
            (timestamp, turbine_id, session_id, event_ref, wind_speed, power_output,
             rotor_speed, scada_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            _reading_timestamp(reading),
            str(reading.get('turbine_id', '')),
            session_id,
            event_ref,
            to_float(reading.get('wind_speed', 0)),
            to_float(reading.get('total_power', 0)) / 1_000_000,
            to_float(scada.get('WROT_RotSpd', reading.get('rotor', {}).get('rotor_speed', 0))),
            scada_json,
        ))
        conn.commit()

    def store_snapshots(self, readings: List[dict], event_ref: str, session_id: int = None):
        """Store a batch of 1s snapshot readings for an event."""
        """Store multiple 1s snapshot readings linked to an event."""
        for r in readings:
            self.store_snapshot(r, event_ref, session_id)

    # ══════════════════════════════════════════════════════════════════
    #  Data Retention & Downsampling
    # ══════════════════════════════════════════════════════════════════

    def run_downsampling(self):
        """Create 1-minute and 10-minute aggregates from raw data.

        Called periodically by the background maintenance task.

        注意（WMOM-20260719-02）：GROUP BY 只含 turbine_id + 分鐘桶，未含 session_id——同一
        turbine 同一實際分鐘桶內若混有多個 session 的列，聚合列的 session_id 由 SQLite 任選、
        不保證。目前無任何查詢以 session_id 讀 1m/10m（query_history 只讀 raw turbine_data），
        故不影響現況；日後若要對 1m/10m 做 session 隔離查詢，GROUP BY 需補 session_id。
        """
        conn = self._get_conn()
        now = utc_now()

        # ── Build 1-minute aggregates from raw data older than 5 minutes ──
        cutoff_1m = iso_utc(now - timedelta(minutes=5))
        # Find the latest 1m aggregate timestamp to avoid re-processing
        latest_1m = conn.execute(
            "SELECT MAX(timestamp) FROM turbine_data_1m"
        ).fetchone()[0]
        from_ts = latest_1m or "2000-01-01T00:00:00"

        conn.execute("""
            INSERT INTO turbine_data_1m
                (timestamp, turbine_id, session_id,
                 power_output_avg, power_output_max, power_output_min,
                 wind_speed_avg, wind_speed_max, rotor_speed_avg,
                 temperature_avg, vibration_avg, vibration_max, sample_count)
            SELECT
                MIN(timestamp),
                turbine_id,
                session_id,
                AVG(power_output), MAX(power_output), MIN(power_output),
                AVG(wind_speed), MAX(wind_speed), AVG(rotor_speed),
                AVG(temperature), AVG(vibration), MAX(vibration),
                COUNT(*)
            FROM turbine_data
            WHERE timestamp > ? AND timestamp <= ?
            GROUP BY turbine_id,
                     CAST(strftime('%s', timestamp) AS INTEGER) / 60
            HAVING COUNT(*) > 0
        """, (from_ts, cutoff_1m))
        conn.commit()

        # ── Build 10-minute aggregates from 1-min data older than 15 minutes ──
        cutoff_10m = iso_utc(now - timedelta(minutes=15))
        latest_10m = conn.execute(
            "SELECT MAX(timestamp) FROM turbine_data_10m"
        ).fetchone()[0]
        from_ts_10m = latest_10m or "2000-01-01T00:00:00"

        conn.execute("""
            INSERT INTO turbine_data_10m
                (timestamp, turbine_id, session_id,
                 power_output_avg, power_output_max, power_output_min,
                 wind_speed_avg, wind_speed_max, rotor_speed_avg,
                 temperature_avg, vibration_avg, vibration_max, sample_count)
            SELECT
                MIN(timestamp),
                turbine_id,
                session_id,
                AVG(power_output_avg), MAX(power_output_max), MIN(power_output_min),
                AVG(wind_speed_avg), MAX(wind_speed_max), AVG(rotor_speed_avg),
                AVG(temperature_avg), AVG(vibration_avg), MAX(vibration_max),
                SUM(sample_count)
            FROM turbine_data_1m
            WHERE timestamp > ? AND timestamp <= ?
            GROUP BY turbine_id,
                     CAST(strftime('%s', timestamp) AS INTEGER) / 600
            HAVING COUNT(*) > 0
        """, (from_ts_10m, cutoff_10m))
        conn.commit()

    def run_cleanup(
        self,
        raw_retention_days: int = 3,
        agg_1m_retention_days: int = 90,
        snapshots_retention_days: int = 7,
        raw_tiered: bool = False,
    ) -> dict:
        """Delete old raw data, old 1-minute aggregates, and old event snapshots.

        - Raw (turbine_data): keep last `raw_retention_days` days (default 3)；情境 session 的 raw 不清
          （刪情境時才刪，WMOM-20261021-04）。``raw_tiered`` 為真時（分層儲存，WMOM-20261125-03-c）這裡
          不動 raw：Live 的 raw 由 ``DataBroker.run_retention`` 依每日歸檔來刪（只刪確定在日檔裡的）
        - 1-minute aggregates: keep last `agg_1m_retention_days` days (default 90)
        - 10-minute aggregates: keep forever
        - Snapshots: keep last `snapshots_retention_days` days (default 7)
          ★ WMOM-20260505-01: 修補 — 原 schema 註解寫 permanent 但實作 bug，
          snapshots 不清會失控膨脹（彰化 farm 17.5 天累積 41.9 GB）。
          設 7 天 retention 給「事件發生後幾天還可調 snapshot」的合理使用情境。
          設 0 = 不清（保留 legacy 行為，不建議）。
        """
        conn = self._get_conn()
        now = utc_now()

        # 情境＝凍結資料集（DEC-20260720-01）：raw 讀值保留到情境被刪除——標準答案的時刻與資料包匯出
        # 都指向它（WMOM-20261021-04 code review）
        if raw_tiered:
            deleted_raw = 0
        else:
            raw_cutoff = iso_utc(now - timedelta(days=raw_retention_days))
            deleted_raw = conn.execute(
                "DELETE FROM turbine_data WHERE timestamp < ? AND (session_id IS NULL OR session_id NOT IN "
                "(SELECT id FROM sessions WHERE json_extract(config_json, '$.kind') = ?))",
                (raw_cutoff, self.SCENARIO_KIND),
            ).rowcount

        agg_cutoff = iso_utc(now - timedelta(days=agg_1m_retention_days))
        deleted_1m = conn.execute(
            "DELETE FROM turbine_data_1m WHERE timestamp < ?", (agg_cutoff,)
        ).rowcount

        deleted_snapshots = 0
        if snapshots_retention_days > 0:
            snap_cutoff = iso_utc(now - timedelta(days=snapshots_retention_days))
            deleted_snapshots = conn.execute(
                "DELETE FROM turbine_snapshots WHERE timestamp < ?", (snap_cutoff,)
            ).rowcount

        conn.commit()

        if deleted_raw > 0 or deleted_1m > 0 or deleted_snapshots > 0:
            print(
                f"[Storage] Cleanup: removed {deleted_raw} raw rows, "
                f"{deleted_1m} 1m-agg rows, {deleted_snapshots} snapshot rows"
            )

        return {
            "deleted_raw": deleted_raw,
            "deleted_1m": deleted_1m,
            "deleted_snapshots": deleted_snapshots,
        }

    def get_db_stats(self) -> dict:
        """Return row counts and estimated sizes for each table."""
        conn = self._get_conn()
        tables = ["turbine_data", "turbine_data_1m", "turbine_data_10m",
                   "turbine_snapshots", "history_events", "sessions"]
        stats = {}
        for table in tables:
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                stats[table] = count
            except sqlite3.OperationalError:
                stats[table] = 0

        # DB file size
        db_path = Path(self._db_path)
        stats["db_size_mb"] = round(db_path.stat().st_size / (1024 * 1024), 1) if db_path.exists() else 0
        return stats

    # ══════════════════════════════════════════════════════════════════
    #  Data Queries
    # ══════════════════════════════════════════════════════════════════

    def query_history(self, turbine_id: str, start: Optional[str] = None,
                      end: Optional[str] = None, limit: int = 1000,
                      session_id: Optional[int] = None) -> List[dict]:
        """Query raw turbine_data rows for a turbine within an optional time range.

        當 ``session_id`` 給定時只回傳該 session 的資料——情境模式用它把某個已保存
        情境（＝一個專屬 session）的資料與其他歷史/Live 資料隔離開來調閱。
        """
        conn = self._get_conn()
        query = "SELECT * FROM turbine_data WHERE turbine_id = ?"
        params: list = [turbine_id]

        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)
        start, end = normalize_iso(start), normalize_iso(end)
        if start:
            query += " AND timestamp >= ?"
            params.append(start)
        if end:
            query += " AND timestamp <= ?"
            params.append(end)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            if d.get('scada_json'):
                try:
                    d['scada'] = json.loads(d['scada_json'])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append(d)
        return result

    def count_session_readings(self, session_id: int) -> int:
        """某 session 的 raw 讀值筆數（走 session 索引，不讀 ``scada_json``）。

        Args:
            session_id: session id。

        Returns:
            筆數。
        """
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) FROM turbine_data WHERE session_id = ?", (session_id,)).fetchone()
        return int(row[0])

    def session_readings_in_id_order(self, session_id: int) -> bool:
        """某 session 的寫入順序（id）是否已經是時間、機組順序。

        批次生成逐步寫入，id 順序就是時間順序；只讀 ``timestamp`` / ``turbine_id``，不碰 ``scada_json``。

        Args:
            session_id: session id。

        Returns:
            True＝依 id 讀出來就已依時間、機組排序。
        """
        conn = self._get_conn()
        # 時間戳固定格式（time_utils.iso_utc），字串比較即時間比較
        row = conn.execute(
            """
            SELECT 1 FROM (
                SELECT timestamp, turbine_id,
                       LAG(timestamp) OVER w AS prev_ts, LAG(turbine_id) OVER w AS prev_tid
                FROM turbine_data WHERE session_id = ?
                WINDOW w AS (ORDER BY id)
            )
            WHERE timestamp < prev_ts OR (timestamp = prev_ts AND turbine_id < prev_tid)
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        return row is None

    def iter_session_readings(self, session_id: int, batch_size: int = 5000) -> Iterator[List[sqlite3.Row]]:
        """依時間、機組排序，分批取某 session 的 raw 讀值（情境資料包匯出用，WMOM-20261021-05）。

        寫入順序已是時間順序時（批次生成都是）依 id 讀：沿 session 索引直接串流，第一批馬上出來；
        否則才 ``ORDER BY timestamp``——SQLite 要先把整個 session 排序（暫存 B-tree）才吐第一列。

        Args:
            session_id: session id。
            batch_size: 每批列數（匯出長情境時不一次載入全部）。

        Yields:
            每批 ``(timestamp, turbine_id, scada_json)`` 列。
        """
        conn = self._get_conn()
        order = "id" if self.session_readings_in_id_order(session_id) else "timestamp, turbine_id, id"
        cursor = conn.execute(
            f"SELECT timestamp, turbine_id, scada_json FROM turbine_data WHERE session_id = ? ORDER BY {order}",
            (session_id,),
        )
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                return
            yield rows

    def session_events(self, session_id: int) -> List[dict]:
        """某 session 的全部事件，依時間由舊到新（同時刻依寫入順序；資料包匯出用，WMOM-20261021-05）。

        Args:
            session_id: session id。

        Returns:
            事件 dict（``payload`` 已解析）。
        """
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM history_events WHERE session_id = ? ORDER BY timestamp, id", (session_id,),
        ).fetchall()
        events = []
        for row in rows:
            event = dict(row)
            if event.get("payload_json"):
                try:
                    event["payload"] = json.loads(event["payload_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            events.append(event)
        return events

    def session_reading_ids(self, session_id: int) -> "array[int]":
        """某 session 全部讀值的 id，依時間、機組排序（回放分頁用，WMOM-20261021-06）。

        寫入順序已是時間順序時（批次生成都是）直接依 id 取，不必排序；否則依時間、機組排序。只讀
        id，不讀 ``scada_json``；以 ``array('q')`` 回傳（每筆 8 bytes，兩百萬筆約 16 MB）。

        Args:
            session_id: session id。

        Returns:
            id 陣列。
        """
        conn = self._get_conn()
        order = "id" if self.session_readings_in_id_order(session_id) else "timestamp, turbine_id, id"
        ids: "array[int]" = array("q")
        cursor = conn.execute(f"SELECT id FROM turbine_data WHERE session_id = ? ORDER BY {order}", (session_id,))
        while True:
            rows = cursor.fetchmany(10_000)
            if not rows:
                return ids
            ids.extend(int(row[0]) for row in rows)

    def session_reading_bounds(self, session_id: int) -> Optional[tuple]:
        """某 session 第一筆 / 最後一筆讀值的時間（回放結束時刻用）。

        Args:
            session_id: session id。

        Returns:
            ``(first, last)`` 時間字串；沒有讀值回 None。
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT MIN(timestamp), MAX(timestamp) FROM turbine_data WHERE session_id = ?", (session_id,),
        ).fetchone()
        return (str(row[0]), str(row[1])) if row and row[0] is not None else None

    def readings_by_ids(self, ids: List[int]) -> List[sqlite3.Row]:
        """依 id 取讀值（順序同 ``ids``；回放分頁用）。

        Args:
            ids: ``turbine_data`` 的 id（一次幾百筆）。

        Returns:
            ``(id, timestamp, turbine_id, scada_json)`` 列；不存在的 id 略過。
        """
        if not ids:
            return []
        conn = self._get_conn()
        found: Dict[int, sqlite3.Row] = {}
        for start in range(0, len(ids), 900):  # SQLite 參數上限
            chunk = ids[start:start + 900]
            placeholders = ",".join("?" * len(chunk))
            for row in conn.execute(
                f"SELECT id, timestamp, turbine_id, scada_json FROM turbine_data WHERE id IN ({placeholders})",
                chunk,
            ):
                found[int(row["id"])] = row
        return [found[i] for i in ids if i in found]

    # ── 情境回放（WMOM-20261021-06）──

    def create_replay_run(self, scenario_id: int, token_sha256: str, mode: str, speed: float,
                          label: Optional[str], created_at: str, created_by: Optional[str],
                          expires_at: str) -> dict:
        """建立一個回放。

        Args:
            scenario_id: 情境 session id。
            token_sha256: 回放 token 的 sha256（token 本身不存）。
            mode: ``evaluation`` / ``practice``。
            speed: 回放速度（模擬秒 / 實際秒）。
            label: 出題者的備註。
            created_at: 建立時間（``iso_utc``）。
            created_by: 建立者（使用者 id）。
            expires_at: token 到期時間（``iso_utc``）。

        Returns:
            回放 dict（同 ``get_replay_run``）。
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO replay_runs (scenario_id, token_sha256, mode, speed, label, created_at, created_by, "
            "expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (scenario_id, token_sha256, mode, speed, label, created_at, created_by, expires_at),
        )
        conn.commit()
        assert cursor.lastrowid is not None
        run = self.get_replay_run(cursor.lastrowid)
        assert run is not None
        return run

    _REPLAY_RUN_COLUMNS = ("id, scenario_id, mode, speed, label, created_at, created_by, expires_at, started_at, "
                           "connections, revoked_at, "
                           "(SELECT COUNT(*) FROM replay_predictions p WHERE p.run_id = replay_runs.id) AS predictions")

    def get_replay_run(self, run_id: int) -> Optional[dict]:
        """取一個回放（不含 token）。

        Args:
            run_id: 回放 id。

        Returns:
            回放 dict（含已收到的預測筆數 ``predictions``）或 None。
        """
        conn = self._get_conn()
        row = conn.execute(f"SELECT {self._REPLAY_RUN_COLUMNS} FROM replay_runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None

    def find_replay_run(self, token_sha256: str) -> Optional[dict]:
        """以 token 的 sha256 找回放。

        Args:
            token_sha256: token 的 sha256。

        Returns:
            回放 dict 或 None。
        """
        conn = self._get_conn()
        row = conn.execute(
            f"SELECT {self._REPLAY_RUN_COLUMNS} FROM replay_runs WHERE token_sha256 = ?", (token_sha256,),
        ).fetchone()
        return dict(row) if row else None

    def list_replay_runs(self, scenario_id: int) -> List[dict]:
        """某情境的回放，新的在前。

        Args:
            scenario_id: 情境 session id。

        Returns:
            回放 dict 清單。
        """
        conn = self._get_conn()
        rows = conn.execute(
            f"SELECT {self._REPLAY_RUN_COLUMNS} FROM replay_runs WHERE scenario_id = ? ORDER BY id DESC",
            (scenario_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def started_evaluation_runs(self) -> List[dict]:
        """已開播、未撤銷的正式評測（可能仍在進行中；是否已播完由 ``replay.run_view`` 依時鐘判斷）。

        Returns:
            回放 dict 清單（新的在前）。
        """
        conn = self._get_conn()
        rows = conn.execute(
            f"SELECT {self._REPLAY_RUN_COLUMNS} FROM replay_runs WHERE mode = 'evaluation' "
            "AND started_at IS NOT NULL AND revoked_at IS NULL ORDER BY id DESC",
        ).fetchall()
        return [dict(row) for row in rows]

    def unrevoked_evaluation_runs(self) -> List[dict]:
        """未撤銷的正式評測（含還沒開播的；是否已播完 / 到期由 ``replay.run_view`` 判斷）。

        Returns:
            回放 dict 清單（新的在前）。
        """
        conn = self._get_conn()
        rows = conn.execute(
            f"SELECT {self._REPLAY_RUN_COLUMNS} FROM replay_runs WHERE mode = 'evaluation' "
            "AND revoked_at IS NULL ORDER BY id DESC",
        ).fetchall()
        return [dict(row) for row in rows]

    def count_scenario_replay_predictions(self, scenario_id: int) -> int:
        """某情境所有回放收到的預測筆數（刪除情境前確認評測結果已匯出用）。

        Args:
            scenario_id: 情境 session id。

        Returns:
            筆數。
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COUNT(*) FROM replay_predictions WHERE run_id IN (SELECT id FROM replay_runs WHERE scenario_id = ?)",
            (scenario_id,),
        ).fetchone()
        return int(row[0])

    def prediction_bytes(self, run_id: int) -> int:
        """某回放已存的預測總位元組數（每個回放的儲存上限用）。

        Args:
            run_id: 回放 id。

        Returns:
            位元組數（JSON 文字長度）。
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COALESCE(SUM(LENGTH(prediction_json)), 0) FROM replay_predictions WHERE run_id = ?", (run_id,),
        ).fetchone()
        return int(row[0])

    def revoke_replay_run(self, run_id: int, revoked_at: str) -> bool:
        """撤銷回放（之後不能再連線、送預測）；已撤銷的不改時間。

        Args:
            run_id: 回放 id。
            revoked_at: 撤銷時間（``iso_utc``）。

        Returns:
            回放是否存在。
        """
        conn = self._get_conn()
        conn.execute("UPDATE replay_runs SET revoked_at = COALESCE(revoked_at, ?) WHERE id = ?", (revoked_at, run_id))
        conn.commit()
        return conn.execute("SELECT 1 FROM replay_runs WHERE id = ?", (run_id,)).fetchone() is not None

    def start_replay_run(self, run_id: int, started_at: str) -> str:
        """回放的開始時間：第一次呼叫時寫入 ``started_at``，之後回傳同一個值（原子操作）。

        Args:
            run_id: 回放 id。
            started_at: 這次連線的時間（``iso_utc``）。

        Returns:
            回放實際的開始時間。
        """
        conn = self._get_conn()
        with conn:  # 同一個交易：UPDATE 取得寫入鎖，其他連線等到 commit 才能改（不用 RETURNING，SQLite < 3.35 也可用）
            conn.execute("UPDATE replay_runs SET started_at = COALESCE(started_at, ?) WHERE id = ?",
                         (started_at, run_id))
            row = conn.execute("SELECT started_at FROM replay_runs WHERE id = ?", (run_id,)).fetchone()
        return str(row[0])

    def anchor_practice_run(self, run_id: int, started_at: str) -> bool:
        """練習回放以 OPC UA 播出時，記下這次播出的起點（每次啟動 OPC UA server 都覆寫）。

        WS 以 ``?stream=false`` 連線時用它當時鐘，預測的模擬時間才會對上 OPC UA 上的資料（WMOM-20261021-07）。
        一般的 WS 練習連線（送資料）不看這一欄，仍各自從頭播。

        Args:
            run_id: 回放 id（只改練習模式的回放）。
            started_at: 播出起點（``iso_utc``）。

        Returns:
            是否有寫入（不是練習回放時 False）。
        """
        conn = self._get_conn()
        with conn:
            cur = conn.execute("UPDATE replay_runs SET started_at = ? WHERE id = ? AND mode = 'practice'",
                               (started_at, run_id))
        return cur.rowcount == 1

    def next_replay_connection(self, run_id: int) -> int:
        """連線序號（1 起算；原子遞增）。

        Args:
            run_id: 回放 id。

        Returns:
            這次連線的序號。
        """
        conn = self._get_conn()
        with conn:  # 同 start_replay_run：遞增與讀回在同一個交易
            conn.execute("UPDATE replay_runs SET connections = connections + 1 WHERE id = ?", (run_id,))
            row = conn.execute("SELECT connections FROM replay_runs WHERE id = ?", (run_id,)).fetchone()
        return int(row[0])

    def add_replay_prediction(self, run_id: int, connection_no: int, received_at: str, sim_ts: str,
                              prediction: dict) -> int:
        """存一筆預測。

        Args:
            run_id: 回放 id。
            connection_no: 連線序號。
            received_at: 收到的實際時間（``iso_utc``）。
            sim_ts: 收到時的回放模擬時間（合約格式 ``...Z``）。
            prediction: 合約 §6 格式的預測（``ts`` 已是 ``sim_ts``）。

        Returns:
            新預測的 id。
        """
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO replay_predictions (run_id, connection_no, received_at, sim_ts, prediction_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, connection_no, received_at, sim_ts, json.dumps(prediction, ensure_ascii=False)),
        )
        conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def replay_predictions(self, run_id: int, connection_no: Optional[int] = None) -> List[dict]:
        """某回放收到的預測，依收到順序。

        Args:
            run_id: 回放 id。
            connection_no: 只取某次連線的（練習模式每次連線各自從頭播）；None＝全部。

        Returns:
            ``{"id", "connection_no", "received_at", "sim_ts", "prediction"}`` 清單。
        """
        conn = self._get_conn()
        sql = "SELECT id, connection_no, received_at, sim_ts, prediction_json FROM replay_predictions WHERE run_id = ?"
        params: list = [run_id]
        if connection_no is not None:
            sql += " AND connection_no = ?"
            params.append(connection_no)
        rows = conn.execute(sql + " ORDER BY id", params).fetchall()
        return [{"id": row["id"], "connection_no": row["connection_no"], "received_at": row["received_at"],
                 "sim_ts": row["sim_ts"], "prediction": json.loads(row["prediction_json"])} for row in rows]

    def scenario_turbine_ids(self, session_id: int) -> List[str]:
        """情境（session）內出現過資料的機組 id 清單，依字母序排序（PR C Phase 1 情境掛載用）。

        供 scenarios router 組裝「該情境每台機組最後一筆讀數」時，先知道要對哪些
        turbine_id 各發一次 ``query_history(limit=1, session_id=...)``。
        """
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT DISTINCT turbine_id FROM turbine_data WHERE session_id = ? "
            "ORDER BY turbine_id",
            (session_id,),
        ).fetchall()
        return [row[0] for row in rows]

    def query_latest(self, turbine_id: str) -> Optional[dict]:
        """Return the most recent reading for a single turbine."""
        """Return the most recent reading for a turbine, or None."""
        rows = self.query_history(turbine_id, limit=1)
        return rows[0] if rows else None

    def query_events(
        self,
        turbine_id: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 500,
        session_id: Optional[int] = None,
        source: Optional[str] = None,
        exclude_scenario_sessions: bool = False,
    ) -> List[dict]:
        """Query history_events with optional turbine, time range, session, source, and limit filters.

        給 ``turbine_id`` 時一併回傳風場層事件（``turbine_id IS NULL``）。給 ``session_id`` / ``source``
        時只回該 session / 該來源的事件（情境調閱用，WMOM-20261021-04）。``exclude_scenario_sessions``：
        排除情境 session 的事件（Live 端查詢用——情境事件以模擬時間寫入，會混進 Live 的時間軸）。
        同一時刻的事件依寫入順序（``id``）排，例：跳機在它造成的停機狀態之前。
        """
        conn = self._get_conn()
        query = """
            SELECT * FROM history_events
            WHERE (turbine_id = ? OR turbine_id IS NULL)
        """
        params: list = [turbine_id]

        if turbine_id is None:
            query = "SELECT * FROM history_events WHERE 1=1"
            params = []
        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)
        if source is not None:
            query += " AND source = ?"
            params.append(source)
        if exclude_scenario_sessions:
            query += (" AND (session_id IS NULL OR session_id NOT IN "
                      "(SELECT id FROM sessions WHERE json_extract(config_json, '$.kind') = ?))")
            params.append(self.SCENARIO_KIND)
        start, end = normalize_iso(start), normalize_iso(end)
        if start:
            query += " AND COALESCE(end_timestamp, timestamp) >= ?"
            params.append(start)
        if end:
            query += " AND timestamp <= ?"
            params.append(end)

        query += " ORDER BY timestamp DESC, id DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            if d.get("payload_json"):
                try:
                    d["payload"] = json.loads(d["payload_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append(d)
        return result

    def query_all_latest(self) -> List[dict]:
        """Return the most recent reading for every turbine."""
        conn = self._get_conn()
        rows = conn.execute("""
            SELECT t1.* FROM turbine_data t1
            INNER JOIN (
                SELECT turbine_id, MAX(timestamp) as max_ts
                FROM turbine_data
                GROUP BY turbine_id
            ) t2 ON t1.turbine_id = t2.turbine_id AND t1.timestamp = t2.max_ts
            ORDER BY t1.turbine_id
        """).fetchall()
        return [dict(row) for row in rows]

    # ── 對外唯讀 API 的 Live 查詢（WMOM-20261125-02）──────────────────
    # 只取 Live 的資料（排除情境 session：情境以模擬時間寫入，且是出題用的凍結資料集），依寫入順序
    # （id）往後翻頁——外部系統以「上次看到的最後一筆」當游標輪詢。
    _NOT_SCENARIO_SQL = ("(session_id IS NULL OR session_id NOT IN "
                         "(SELECT id FROM sessions WHERE json_extract(config_json, '$.kind') = ?))")

    def live_readings(self, turbine_id: str, after_id: int = 0, start: Optional[str] = None,
                      end: Optional[str] = None, limit: int = 1000) -> List[sqlite3.Row]:
        """一台機組的 Live 讀值（不含情境 session），依寫入順序。

        Args:
            turbine_id: 機組 ID。
            after_id: 只取 id 大於它的列（游標；0＝從頭）。
            start: 時間下限（含）；None＝不限。
            end: 時間上限（不含）；None＝不限。
            limit: 最多幾列。

        Returns:
            ``id`` / ``timestamp`` / ``turbine_id`` / ``scada_json`` 的列。
        """
        start, end = normalize_iso(start), normalize_iso(end)
        # 沒有時間下限（輪詢新資料、從頭翻頁）時從游標沿主鍵往後掃：成本只跟這一頁有關。交給 SQLite 選的話
        # 它會用 (turbine_id, timestamp) 索引掃過這台機組的全部列再依 id 排序。有時間下限時才用那個索引
        # 縮小範圍。
        table = "turbine_data" if start else "turbine_data NOT INDEXED"
        query = (f"SELECT id, timestamp, turbine_id, scada_json FROM {table} "
                 "WHERE turbine_id = ? AND id > ? AND " + self._NOT_SCENARIO_SQL)
        params: list = [turbine_id, after_id, self.SCENARIO_KIND]
        if start:
            query += " AND timestamp >= ?"
            params.append(start)
        if end:
            query += " AND timestamp < ?"
            params.append(end)
        query += " ORDER BY id LIMIT ?"
        params.append(limit)
        return self._get_conn().execute(query, params).fetchall()

    def save_briefing(self, work_order_id: str, business_key: str, turbine_id: str, kind: str, data_cutoff: str,
                      card: Dict, answer: Optional[Dict] = None) -> bool:
        """存一張出發前準備卡。卡片不可變：同一張工單已經有卡就不動（建立當下的卡與答案要留著）。

        Args:
            work_order_id: 工單 id。
            business_key: 工單的業務編號。
            turbine_id: 模擬器的機組 ID。
            kind: 卡片種類（``fault_dispatch``）。
            data_cutoff: 資料截止點（風場時鐘，任何 ISO 格式）。
            card: 卡片內容（只含可觀測資料）。
            answer: 評分用的答案（工單建立當下機組實際的故障）；不對外。

        Returns:
            這次有沒有寫入（已經有卡時為 False）。
        """
        conn = self._get_conn()
        written = conn.execute(
            "INSERT INTO briefing_cards (work_order_id, business_key, turbine_id, kind, created_at, "
            "data_cutoff, card_json, answer_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (work_order_id) DO NOTHING",
            (work_order_id, business_key, turbine_id, kind, iso_utc(), normalize_iso(data_cutoff),
             json.dumps(card, ensure_ascii=False),
             json.dumps(answer, ensure_ascii=False) if answer is not None else None)).rowcount
        conn.commit()
        return written > 0

    def briefing_work_order_ids(self, work_order_ids: List[str]) -> set:
        """這些工單裡哪些有出發前準備卡（一次查完，不必逐張讀整張卡）。

        Args:
            work_order_ids: 工單 id。

        Returns:
            有卡的工單 id。
        """
        found: set = set()
        conn = self._get_conn()
        for offset in range(0, len(work_order_ids), 500):
            chunk = work_order_ids[offset:offset + 500]
            marks = ", ".join("?" * len(chunk))
            found.update(str(row[0]) for row in conn.execute(
                f"SELECT work_order_id FROM briefing_cards WHERE work_order_id IN ({marks})", chunk))
        return found

    # ── 風場的設定 ─────────────────────────────────────────────────────────

    def get_setting(self, key: str) -> Optional[Dict]:
        """讀一筆風場設定；沒有或讀不出來為 None。"""
        row = self._get_conn().execute("SELECT value_json FROM farm_settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        try:
            value = json.loads(row[0])
        except (TypeError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def set_setting(self, key: str, value: Dict) -> None:
        """存一筆風場設定（整筆換掉）。"""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO farm_settings (key, value_json, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False), iso_utc()))
        conn.commit()

    # ── 匯入的實測風況序列（WMOM-20261125-07）────────────────────────────

    def add_wind_series(self, name: str, summary: Dict, data: bytes) -> int:
        """存一份實測風況序列，回傳 ID。"""
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO wind_series (name, created_at, summary_json, data) VALUES (?, ?, ?, ?)",
            (name, iso_utc(), json.dumps(summary, ensure_ascii=False), sqlite3.Binary(data)))
        conn.commit()
        return int(cursor.lastrowid)

    def list_wind_series(self) -> List[Dict]:
        """全部序列的 ID、名稱、建立時間、摘要（不含資料）。"""
        rows = self._get_conn().execute(
            "SELECT id, name, created_at, summary_json FROM wind_series ORDER BY id").fetchall()
        return [{"id": int(r[0]), "name": r[1], "created_at": r[2], "summary": json.loads(r[3])} for r in rows]

    def get_wind_series(self, series_id: int) -> Optional[Dict]:
        """一份序列（含資料）；沒有為 None。"""
        row = self._get_conn().execute(
            "SELECT id, name, created_at, summary_json, data FROM wind_series WHERE id = ?", (series_id,)).fetchone()
        if row is None:
            return None
        return {"id": int(row[0]), "name": row[1], "created_at": row[2], "summary": json.loads(row[3]),
                "data": bytes(row[4])}

    def delete_wind_series(self, series_id: int) -> bool:
        """刪掉一份序列；有刪到回 True。"""
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM wind_series WHERE id = ?", (series_id,))
        conn.commit()
        return cursor.rowcount > 0

    # ── 不對外的故障紀錄（WMOM-20261125-06-c）─────────────────────────────

    _FAULT_RECORD_COLUMNS = ("id", "turbine_id", "scenario_id", "origin", "onset_ts", "first_alarm_ts",
                             "first_alarm_code", "trip_ts", "trip_code", "trip_count", "observed_json",
                             "cleared_ts", "cleared_by", "severity_rate")

    def open_fault_record(self, turbine_id: str, scenario_id: str, origin: str, onset_ts: str,
                          severity_rate: Optional[float] = None) -> Optional[int]:
        """開一筆故障紀錄；這台機組的這個情境已經有還沒結束的紀錄時不重複開。

        Returns:
            新紀錄的 id；已經有就是 None。
        """
        conn = self._get_conn()
        exists = conn.execute(
            "SELECT 1 FROM fault_records WHERE turbine_id = ? AND scenario_id = ? AND cleared_ts IS NULL LIMIT 1",
            (turbine_id, scenario_id)).fetchone()
        if exists is not None:
            return None
        cursor = conn.execute(
            "INSERT INTO fault_records (turbine_id, scenario_id, origin, onset_ts, severity_rate) "
            "VALUES (?, ?, ?, ?, ?)", (turbine_id, scenario_id, origin, normalize_iso(onset_ts), severity_rate))
        conn.commit()
        return int(cursor.lastrowid)

    def open_fault_records(self, turbine_id: Optional[str] = None) -> List[Dict]:
        """還沒結束的故障紀錄（依發生順序）。"""
        return self.fault_records(turbine_id=turbine_id, open_only=True, limit=10000)

    def update_fault_record(self, record_id: int, **fields: object) -> None:
        """改一筆故障紀錄的欄位（``observed`` 會存成 JSON）。"""
        if "observed" in fields:
            fields["observed_json"] = json.dumps(fields.pop("observed"), ensure_ascii=False)
        unknown = set(fields) - (set(self._FAULT_RECORD_COLUMNS) - {"id"})
        if unknown or not fields:
            raise ValueError(f"不能改的欄位：{sorted(unknown)}")
        assignments = ", ".join(f"{name} = ?" for name in fields)
        conn = self._get_conn()
        conn.execute(f"UPDATE fault_records SET {assignments} WHERE id = ?", (*fields.values(), record_id))
        conn.commit()

    def repaired_fault_counts(self, start: str, end: str, origin: str = "generator") -> Dict[str, int]:
        """一段時間內由工單修好的故障，依情境計數（WMOM-20261127-07，故障率回饋用）。

        只算 ``cleared_by`` 是工單的（出題用的後門清掉的不算）；時間看修好的時間（``cleared_ts``，風場時鐘）。

        Args:
            start: 時間下限（含，``iso_utc``）。
            end: 時間上限（不含）。
            origin: 故障從哪裡來——``generator``（故障產生器）或 ``manual``（手動注入的題目）。

        Returns:
            情境 ID → 次數。
        """
        rows = self._get_conn().execute(
            "SELECT scenario_id, COUNT(*) FROM fault_records WHERE cleared_by LIKE 'work_order:%' "
            "AND origin = ? AND cleared_ts >= ? AND cleared_ts < ? GROUP BY scenario_id",
            (origin, start, end)).fetchall()
        return {str(row[0]): int(row[1]) for row in rows}

    def fault_records(self, turbine_id: Optional[str] = None, open_only: bool = False,
                      limit: int = 500, newest_first: bool = False) -> List[Dict]:
        """故障紀錄。

        Args:
            turbine_id: 只取這台機組；None＝全部。
            open_only: 只取還沒結束的。
            limit: 最多幾筆。
            newest_first: True＝新的在前。
        """
        where, params = [], []
        if turbine_id:
            where.append("turbine_id = ?")
            params.append(turbine_id)
        if open_only:
            where.append("cleared_ts IS NULL")
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        order = "DESC" if newest_first else "ASC"
        rows = self._get_conn().execute(
            f"SELECT {', '.join(self._FAULT_RECORD_COLUMNS)} FROM fault_records {clause} ORDER BY id {order} LIMIT ?",
            (*params, int(limit))).fetchall()
        out: List[Dict] = []
        for row in rows:
            item = dict(zip(self._FAULT_RECORD_COLUMNS, row))
            try:
                item["observed"] = json.loads(item.pop("observed_json") or "[]")
            except (TypeError, ValueError):
                item["observed"] = []
            out.append(item)
        return out

    def get_briefing(self, work_order_id: Optional[str] = None, business_key: Optional[str] = None) -> Optional[Dict]:
        """讀一張出發前準備卡（以工單 id 或業務編號）。

        Args:
            work_order_id: 工單 id。
            business_key: 工單的業務編號（沒給 id 時用）。

        Returns:
            ``{"work_order_id", "business_key", "turbine_id", "kind", "created_at", "data_cutoff", "card",
            "answer"}``；沒有這張卡時為 None。``answer`` 是評分用的答案，呼叫端要自己決定給不給。
        """
        if work_order_id is not None:
            row = self._get_conn().execute(
                "SELECT * FROM briefing_cards WHERE work_order_id = ?", (work_order_id,)).fetchone()
        elif business_key is not None:
            row = self._get_conn().execute(
                "SELECT * FROM briefing_cards WHERE business_key = ? ORDER BY created_at DESC LIMIT 1",
                (business_key,)).fetchone()
        else:
            return None
        if row is None:
            return None
        return {
            "work_order_id": row["work_order_id"], "business_key": row["business_key"],
            "turbine_id": row["turbine_id"], "kind": row["kind"], "created_at": row["created_at"],
            "data_cutoff": row["data_cutoff"], "card": json.loads(row["card_json"]),
            "answer": json.loads(row["answer_json"]) if row["answer_json"] else None,
        }

    AVAILABILITY_STATES = ("producing", "ready", "planned", "unplanned")

    def add_availability(self, samples: List[Tuple[str, str, str, float, float, float]]) -> None:
        """把一批運轉狀態取樣累加進 ``availability_hourly``（WMOM-20261125-04）。

        Args:
            samples: ``[(機組 ID, 小時起點（iso_utc）, 狀態, 秒數, 發電量 kWh, 損失發電量 kWh), ...]``；
                狀態是 ``AVAILABILITY_STATES`` 之一。損失發電量只在 ``planned`` / ``unplanned`` 時計入。

        Raises:
            ValueError: 不認得的狀態。
        """
        if not samples:
            return
        rows = []
        for turbine_id, hour, state, seconds, energy_kwh, lost_kwh in samples:
            if state not in self.AVAILABILITY_STATES:
                raise ValueError(f"不認得的運轉狀態：{state}")
            rows.append((turbine_id, normalize_iso(hour),
                         seconds if state == "producing" else 0.0, seconds if state == "ready" else 0.0,
                         seconds if state == "planned" else 0.0, seconds if state == "unplanned" else 0.0,
                         energy_kwh, lost_kwh if state == "planned" else 0.0,
                         lost_kwh if state == "unplanned" else 0.0))
        conn = self._get_conn()
        conn.executemany(
            "INSERT INTO availability_hourly (turbine_id, hour, producing_s, ready_s, planned_s, unplanned_s, "
            "energy_kwh, lost_planned_kwh, lost_unplanned_kwh) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (turbine_id, hour) DO UPDATE SET producing_s = producing_s + excluded.producing_s, "
            "ready_s = ready_s + excluded.ready_s, planned_s = planned_s + excluded.planned_s, "
            "unplanned_s = unplanned_s + excluded.unplanned_s, energy_kwh = energy_kwh + excluded.energy_kwh, "
            "lost_planned_kwh = lost_planned_kwh + excluded.lost_planned_kwh, "
            "lost_unplanned_kwh = lost_unplanned_kwh + excluded.lost_unplanned_kwh", rows)
        conn.commit()

    def availability_totals(self, start: str, end: str) -> List[Dict]:
        """``[start, end)`` 之間各機組的運轉狀態合計（以小時為單位：算進小時起點落在範圍內的列）。

        Args:
            start: 時間下限（含，任何 ISO 格式）。
            end: 時間上限（不含）。

        Returns:
            每台機組一筆：``turbine_id``、四種狀態的秒數、``energy_kwh``、``lost_planned_kwh``、
            ``lost_unplanned_kwh``；依機組 ID 排序。
        """
        rows = self._get_conn().execute(
            "SELECT turbine_id, SUM(producing_s) AS producing_s, SUM(ready_s) AS ready_s, "
            "SUM(planned_s) AS planned_s, SUM(unplanned_s) AS unplanned_s, SUM(energy_kwh) AS energy_kwh, "
            "SUM(lost_planned_kwh) AS lost_planned_kwh, SUM(lost_unplanned_kwh) AS lost_unplanned_kwh "
            "FROM availability_hourly WHERE hour >= ? AND hour < ? GROUP BY turbine_id ORDER BY turbine_id",
            (normalize_iso(start), normalize_iso(end))).fetchall()
        return [dict(row) for row in rows]

    def reading_turbine_ids(self) -> List[str]:
        """``turbine_data`` 裡出現過的機組 ID（含情境 session 的；只掃索引）。"""
        rows = self._get_conn().execute(
            "SELECT DISTINCT turbine_id FROM turbine_data INDEXED BY idx_turbine_time ORDER BY turbine_id").fetchall()
        return [str(row[0]) for row in rows]

    def earliest_live_reading_timestamp(self, turbine_id: str) -> Optional[str]:
        """一台機組時間最早的 Live 讀值時間（不含情境 session）；沒有時為 None。

        沿 ``(turbine_id, timestamp)`` 索引由舊到新走到第一筆 Live 列為止。
        """
        row = self._get_conn().execute(
            "SELECT timestamp FROM turbine_data INDEXED BY idx_turbine_time "
            f"WHERE turbine_id = ? AND {self._NOT_SCENARIO_SQL} ORDER BY timestamp LIMIT 1",
            (turbine_id, self.SCENARIO_KIND)).fetchone()
        return str(row[0]) if row is not None else None

    def reading_id_sequence(self) -> int:
        """``turbine_data`` 發過的最大 id（AUTOINCREMENT 的序號；列被刪掉也不會變小）；還沒寫過為 0。

        分層儲存用它確認歸檔屬於這個 DB：歸檔裡的 id 比它大，表示 DB 被重建過。
        """
        row = self._get_conn().execute("SELECT seq FROM sqlite_sequence WHERE name = 'turbine_data'").fetchone()
        return int(row[0]) if row is not None and row[0] is not None else 0

    def live_span(self, turbine_id: str, start: str, end: str) -> Tuple[int, Optional[int]]:
        """一台機組在 ``[start, end)`` 的 Live 讀值列數與最大 id（沒有列時最大 id 為 None）。

        分層儲存用來判斷一個日檔是否和 SQLite 裡的一致（WMOM-20261125-03-c）。走 ``(turbine_id, timestamp)``
        索引：``turbine_data`` 沒有純時間的索引，不帶機組的時間範圍查詢會掃整張表。

        Args:
            turbine_id: 機組 ID。
            start: 時間下限（含，``iso_utc``）。
            end: 時間上限（不含，``iso_utc``）。

        Returns:
            （列數, 最大 id）。
        """
        row = self._get_conn().execute(
            "SELECT COUNT(*), MAX(id) FROM turbine_data INDEXED BY idx_turbine_time "
            f"WHERE turbine_id = ? AND timestamp >= ? AND timestamp < ? AND {self._NOT_SCENARIO_SQL}",
            (turbine_id, start, end, self.SCENARIO_KIND)).fetchone()
        return int(row[0]), (int(row[1]) if row[1] is not None else None)

    def delete_archived_live_readings(self, ranges: List[Tuple[str, str, int]]) -> int:
        """刪掉已經在每日歸檔裡的 Live 讀值（情境 session 的不動）。

        分層儲存的清理用（WMOM-20261125-03-c）。每一段只刪 id 不大於 ``max_id`` 的列——那一天後來才寫進來、
        還沒進日檔的列留著。逐台機組一個交易：走 ``(turbine_id, timestamp)`` 索引，而且每個交易都短，
        不會讓 Live 的寫入等到逾時。

        Args:
            ranges: ``[(時間下限（含）, 時間上限（不含）, 最大 id), ...]``（``LiveArchive.delete_ranges`` 的結果）。

        Returns:
            刪掉的列數。
        """
        if not ranges:
            return 0
        conn = self._get_conn()
        deleted = 0
        for turbine_id in self.reading_turbine_ids():
            for lower, upper, max_id in ranges:
                deleted += conn.execute(
                    "DELETE FROM turbine_data WHERE id IN (SELECT id FROM turbine_data INDEXED BY idx_turbine_time "
                    f"WHERE turbine_id = ? AND timestamp >= ? AND timestamp < ? AND id <= ? "
                    f"AND {self._NOT_SCENARIO_SQL})",
                    (turbine_id, normalize_iso(lower), normalize_iso(upper), int(max_id),
                     self.SCENARIO_KIND)).rowcount
            conn.commit()
        return deleted

    def delete_live_readings_before(self, cutoff: str) -> int:
        """刪掉時間早於 ``cutoff`` 的 Live 讀值（情境 session 的不動），不管有沒有歸檔；逐台機組一個交易。

        分層儲存用它清掉超過總保留期的列（那時對應的日檔也刪了）。

        Args:
            cutoff: 只刪時間早於這一刻的列（任何 ISO 格式）。

        Returns:
            刪掉的列數。
        """
        conn = self._get_conn()
        moment = normalize_iso(cutoff)
        deleted = 0
        for turbine_id in self.reading_turbine_ids():
            deleted += conn.execute(
                "DELETE FROM turbine_data WHERE id IN (SELECT id FROM turbine_data INDEXED BY idx_turbine_time "
                f"WHERE turbine_id = ? AND timestamp < ? AND {self._NOT_SCENARIO_SQL})",
                (turbine_id, moment, self.SCENARIO_KIND)).rowcount
            conn.commit()
        return deleted

    def last_live_reading_timestamp(self, turbine_id: str, max_sessions: int = 20) -> Optional[str]:
        """一台機組**最近一次寫入**的 Live 讀值的時間戳（依寫入順序，不是最大的時間）。

        對外 API 拿它當這台機組的「資料時鐘」：10 分鐘窗結束於它之前，才算已經收齊（WMOM-20261125-02）。
        從最近的 Live session 往回找，每個 session 沿 ``(session_id)`` 索引倒著掃到這台機組的列為止，
        不必掃過情境 session 的列。

        Args:
            turbine_id: 機組 ID。
            max_sessions: 最多往回看幾個 Live session。

        Returns:
            ``iso_utc`` 格式的時間戳；這台機組沒有 Live 讀值時為 None。
        """
        conn = self._get_conn()
        query = ("SELECT timestamp FROM turbine_data INDEXED BY idx_turbine_data_session "
                 "WHERE session_id {match} AND turbine_id = ? ORDER BY id DESC LIMIT 1")
        sessions = conn.execute(
            "SELECT id FROM sessions WHERE json_extract(config_json, '$.kind') IS NULL "
            "OR json_extract(config_json, '$.kind') != ? ORDER BY id DESC LIMIT ?",
            (self.SCENARIO_KIND, max_sessions),
        ).fetchall()
        for (session_id,) in sessions:
            row = conn.execute(query.format(match="= ?"), (session_id, turbine_id)).fetchone()
            if row is not None:
                return str(row[0])
        # 很舊的 Live 列沒有 session_id
        row = conn.execute(query.format(match="IS NULL"), (turbine_id,)).fetchone()
        return str(row[0]) if row is not None else None

    def live_event_exists(self, timestamp: str, turbine_id: Optional[str], source: str, event_type: str,
                          title: str) -> bool:
        """Live（非情境 session）有沒有一筆時間、機組、來源、種類、標題都相同的事件。

        重啟續跑用（WMOM-20261125-03-b）：伺服器被強制關閉前已經記過的事件，重跑同一步時不再記一次。

        Args:
            timestamp: 事件時間（任何 ISO 格式；比對前正規化）。
            turbine_id: 機組 ID；None＝風場層事件。
            source: 事件來源。
            event_type: 事件種類。
            title: 事件標題。

        Returns:
            是否已存在。
        """
        query = ("SELECT 1 FROM history_events WHERE timestamp = ? AND source = ? AND event_type = ? AND title = ? "
                 "AND " + self._NOT_SCENARIO_SQL)
        params: list = [normalize_iso(timestamp), source, event_type, title, self.SCENARIO_KIND]
        if turbine_id is None:
            query += " AND turbine_id IS NULL"
        else:
            query += " AND turbine_id = ?"
            params.append(turbine_id)
        return self._get_conn().execute(query + " LIMIT 1", params).fetchone() is not None

    def live_events(self, after_id: int = 0, turbine_id: Optional[str] = None, start: Optional[str] = None,
                    end: Optional[str] = None, limit: int = 500) -> List[dict]:
        """Live 的事件裡可能可觀測的那些（不含情境 session），依寫入順序。

        只以來源預篩（``OBSERVABLE_CANDIDATE_SOURCES``）；呼叫端仍要逐筆過 ``is_observable_event``。

        Args:
            after_id: 只取 id 大於它的事件（游標；0＝從頭）。
            turbine_id: 只取這台機組的事件；None＝全部。
            start: 時間下限（含）；None＝不限。
            end: 時間上限（不含）；None＝不限。
            limit: 最多幾筆。

        Returns:
            事件 dict（``payload`` 已解析），依 id 遞增。
        """
        sources = sorted(OBSERVABLE_CANDIDATE_SOURCES)
        query = (f"SELECT * FROM history_events WHERE id > ? AND source IN ({', '.join('?' * len(sources))}) "
                 "AND " + self._NOT_SCENARIO_SQL)
        params: list = [after_id, *sources, self.SCENARIO_KIND]
        if turbine_id is not None:
            query += " AND turbine_id = ?"
            params.append(turbine_id)
        start, end = normalize_iso(start), normalize_iso(end)
        if start:
            query += " AND timestamp >= ?"
            params.append(start)
        if end:
            query += " AND timestamp < ?"
            params.append(end)
        query += " ORDER BY id LIMIT ?"
        params.append(limit)
        result = []
        for row in self._get_conn().execute(query, params).fetchall():
            d = dict(row)
            if d.get("payload_json"):
                try:
                    d["payload"] = json.loads(d["payload_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append(d)
        return result

    def query_snapshots(self, turbine_id: str, event_ref: Optional[str] = None,
                        start: Optional[str] = None, end: Optional[str] = None,
                        limit: int = 1000) -> List[dict]:
        """Query high-frequency snapshot readings with optional event and time filter."""
        """Query high-frequency snapshot readings for a turbine, optionally filtered by event."""
        conn = self._get_conn()
        query = "SELECT * FROM turbine_snapshots WHERE turbine_id = ?"
        params: list = [turbine_id]
        if event_ref:
            query += " AND event_ref = ?"
            params.append(event_ref)
        start, end = normalize_iso(start), normalize_iso(end)
        if start:
            query += " AND timestamp >= ?"
            params.append(start)
        if end:
            query += " AND timestamp <= ?"
            params.append(end)
        query += " ORDER BY timestamp ASC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            if d.get('scada_json'):
                try:
                    d['scada'] = json.loads(d['scada_json'])
                except (json.JSONDecodeError, TypeError):
                    pass
            result.append(d)
        return result

    # ══════════════════════════════════════════════════════════════════
    #  Work Orders
    # ══════════════════════════════════════════════════════════════════

    def create_work_order(self, turbine_id: int, turbine_name: str,
                          fault_description: str,
                          technician_id: Optional[int] = None) -> dict:
        """Create a new maintenance work order and return it."""
        """Create a new work order and return it as a dict."""
        conn = self._get_conn()
        wo_id = f"WO-{int(_time.time() * 1000)}"
        now = iso_utc()
        status = "IN_PROGRESS" if technician_id else "OPEN"
        conn.execute("""
            INSERT INTO work_orders
            (id, turbine_id, turbine_name, technician_id, status, created_at,
             fault_description, notes, photos_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, '', '[]')
        """, (wo_id, turbine_id, turbine_name, technician_id, status, now,
              fault_description))
        conn.commit()
        return self.get_work_order(wo_id)

    def get_work_order(self, wo_id: str) -> Optional[dict]:
        """Return a single work order by ID, or None."""
        """Return a single work order by ID, or None if not found."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM work_orders WHERE id = ?", (wo_id,)).fetchone()
        if not row:
            return None
        return self._wo_row_to_dict(row)

    def query_work_orders(self, status: Optional[str] = None,
                          turbine_id: Optional[int] = None,
                          limit: int = 100) -> List[dict]:
        """List work orders filtered by status and/or turbine."""
        """Query work orders with optional status and turbine filters."""
        conn = self._get_conn()
        query = "SELECT * FROM work_orders WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if turbine_id is not None:
            query += " AND turbine_id = ?"
            params.append(turbine_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return [self._wo_row_to_dict(r) for r in rows]

    def update_work_order(self, wo_id: str, **kwargs) -> Optional[dict]:
        """Update work order fields (status, notes, photos) and return it."""
        """Update work order fields (status, notes, photos) and return the updated record."""
        conn = self._get_conn()
        sets = []
        params = []
        if "status" in kwargs:
            sets.append("status = ?")
            params.append(kwargs["status"])
            if kwargs["status"] == "COMPLETED":
                sets.append("completed_at = ?")
                params.append(iso_utc())
        if "notes" in kwargs:
            sets.append("notes = ?")
            params.append(kwargs["notes"])
        if "photos" in kwargs:
            sets.append("photos_json = ?")
            params.append(json.dumps(kwargs["photos"]))
        if not sets:
            return self.get_work_order(wo_id)
        params.append(wo_id)
        conn.execute(f"UPDATE work_orders SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
        return self.get_work_order(wo_id)

    def _wo_row_to_dict(self, row) -> dict:
        d = dict(row)
        # Map to frontend expected format
        photos = []
        if d.get("photos_json"):
            try:
                photos = json.loads(d["photos_json"])
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "id": d["id"],
            "turbineId": d["turbine_id"],
            "turbineName": d["turbine_name"],
            "technicianId": d.get("technician_id"),
            "status": d["status"],
            "createdAt": int(parse_iso(d["created_at"]).timestamp() * 1000)
                if d.get("created_at") else 0,
            "completedAt": d.get("completed_at"),
            "faultDescription": d["fault_description"],
            "notes": d.get("notes", ""),
            "photos": photos,
        }

    # ══════════════════════════════════════════════════════════════════
    #  Technicians
    # ══════════════════════════════════════════════════════════════════

    def create_technician(self, name: str, status: str = "ON_DUTY") -> dict:
        """Add a technician and return the new record."""
        """Create a new technician record and return it."""
        conn = self._get_conn()
        cursor = conn.execute(
            "INSERT INTO technicians (name, status) VALUES (?, ?)", (name, status)
        )
        conn.commit()
        return {"id": cursor.lastrowid, "name": name, "status": status}

    def query_technicians(self) -> List[dict]:
        """Return all technicians ordered by ID."""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM technicians ORDER BY id").fetchall()
        return [{"id": r["id"], "name": r["name"], "status": r["status"]} for r in rows]

    def update_technician(self, tech_id: int, status: str) -> Optional[dict]:
        """Update a technician's duty status and return the record."""
        """Update a technician's status and return the updated record."""
        conn = self._get_conn()
        conn.execute("UPDATE technicians SET status = ? WHERE id = ?", (status, tech_id))
        conn.commit()
        row = conn.execute("SELECT * FROM technicians WHERE id = ?", (tech_id,)).fetchone()
        if not row:
            return None
        return {"id": row["id"], "name": row["name"], "status": row["status"]}
