import re
import sys
import os
import threading
import time as _time
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator, List, Optional, Dict, Tuple, TYPE_CHECKING

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from server.models import (
    TurbineReading, TurbineStatus, DataSourceMode,
    DataSourceConfig, SimulationConfig, FarmStatus,
)
from server.storage import Storage, reading_timestamp
from server.farm_registry import FarmRegistry
from server.live_archive import ArchiveIndexError, LiveArchive, day_start
from server.live_history import LiveHistory
from simulator import checkpoint as live_checkpoint
from simulator.bulk_events import BulkEvent
from simulator.engine import WindFarmSimulator
from simulator.physics.plc_protection import PlcEvent
from simulator.physics.turbine_physics import TurbinePhysicsModel
from simulator.time_utils import (
    DEFAULT_SITE_TIMEZONE, iso_utc, parse_iso, site_timezone, to_utc, utc_now,
)

if TYPE_CHECKING:
    from server.om_loop import OmLoop
    from server.opc_adapter import OPCDAAdapter


def _map_state(state: str) -> TurbineStatus:
    mapping = {
        "RUNNING": TurbineStatus.OPERATING,
        "STARTING": TurbineStatus.OPERATING,
        "IDLE": TurbineStatus.IDLE,
        "STOPPING": TurbineStatus.IDLE,
        "FAULT": TurbineStatus.FAULT,
    }
    return mapping.get(state, TurbineStatus.OFFLINE)


def _sim_output_to_reading(output: Dict, history_points: Optional[List[Dict]] = None,
                            fault_info: Optional[List[Dict]] = None) -> TurbineReading:
    """Convert simulator output dict to TurbineReading model (39 SCADA tags)."""
    scada = output.get('scada', {})
    rotor = output.get('rotor', {})
    gen = output.get('generator', {})
    gb = output.get('gearbox', {})
    yaw = output.get('yaw', {})
    hyd = output.get('hydraulic', {})

    power_w = output.get('total_power', gen.get('power', 0))
    power_mw = power_w / 1_000_000

    tid = output.get('turbine_id', 'WT001')
    idx = int(tid.replace('WT', '')) if tid.startswith('WT') else 1
    name = f"WTG-{idx:02d}"

    ts = output.get('timestamp')
    if isinstance(ts, str):
        try:
            ts = parse_iso(ts)
        except ValueError:
            ts = utc_now()
    elif isinstance(ts, datetime):
        ts = to_utc(ts)
    else:
        ts = utc_now()

    # Build mini history for frontend chart
    history = None
    if history_points:
        history = []
        for h in history_points[-30:]:
            hp = h.get('total_power', h.get('generator', {}).get('power', 0))
            ht = h.get('timestamp')
            if isinstance(ht, str):
                try:
                    ht_dt = parse_iso(ht)
                    ht_ms = int(ht_dt.timestamp() * 1000)
                except ValueError:
                    ht_ms = 0
            else:
                ht_ms = int(ht.timestamp() * 1000) if isinstance(ht, datetime) else 0
            history.append({"time": ht_ms, "power": round(hp / 1_000_000, 2)})

    # Determine turbine status — check if any fault has tripped
    op_state = output.get('operational_state', 'IDLE')
    status = _map_state(op_state)
    if fault_info:
        for f in fault_info:
            if f.get('tripped'):
                status = TurbineStatus.FAULT

    tur_state = int(scada.get("WTUR_TurSt", 6)) if scada else 6

    return TurbineReading(
        turbineId=tid,
        name=name,
        timestamp=ts,
        status=status,
        turState=tur_state,

        # ── Original fields (backward-compatible) ──
        windSpeed=round(output.get('wind_speed', 0), 2),
        powerOutput=round(power_mw, 2),
        rotorSpeed=round(scada.get("WROT_RotSpd", rotor.get('rotor_speed', 0)), 3),
        bladeAngle=round(scada.get("WROT_PtAngValBl1", output.get('pitch_angle', 0)), 2),
        temperature=round(scada.get("WGEN_GnStaTmp1", gen.get('temperature', 45)), 2),
        vibration=round(scada.get("WNAC_VibMsNacXDir", gb.get('vibration', 0)), 3),
        voltage=round(scada.get("WGEN_GnVtgMs", gen.get('voltage', 690)), 2),
        current=round(scada.get("WGEN_GnCurMs", gen.get('current', 0)), 2),
        yawAngle=round(scada.get("WYAW_YwVn1AlgnAvg5s", yaw.get('yaw_angle', 0)), 2),
        gearboxTemp=round(scada.get("WNAC_NacTmp", gb.get('temperature', 40)), 2),
        frequency=scada.get("WCNV_CnvGnFrq", gen.get('frequency')),
        hydraulicPressure=scada.get("WYAW_YwBrkHyPrs", hyd.get('pressure')),
        history=history,

        # ── WGEN expanded ──
        genPower=scada.get("WGEN_GnPwrMs"),
        genSpeed=scada.get("WGEN_GnSpd"),
        genStatorTemp1=scada.get("WGEN_GnStaTmp1"),
        genAirTemp1=scada.get("WGEN_GnAirTmp1"),
        genBearingTemp1=scada.get("WGEN_GnBrgTmp1"),

        # ── WROT expanded ──
        bladeAngle1=scada.get("WROT_PtAngValBl1"),
        bladeAngle2=scada.get("WROT_PtAngValBl2"),
        bladeAngle3=scada.get("WROT_PtAngValBl3"),
        rotorTemp=scada.get("WROT_RotTmp"),
        hubCabinetTemp=scada.get("WROT_RotCabTmp"),
        rotorLocked=int(scada.get("WROT_RotLckd", 0)) if scada.get("WROT_RotLckd") is not None else None,
        brakeActive=int(scada.get("WROT_SrvcBrkAct", 0)) if scada.get("WROT_SrvcBrkAct") is not None else None,

        # ── WCNV ──
        cnvCabinetTemp=scada.get("WCNV_CnvCabinTmp"),
        cnvDcVoltage=scada.get("WCNV_CnvDClVtg"),
        cnvGridPower=scada.get("WCNV_CnvGdPwrAt"),
        cnvGenFreq=scada.get("WCNV_CnvGnFrq"),
        cnvGenPower=scada.get("WCNV_CnvGnPwr"),
        igctWaterCond=scada.get("WCNV_IGCTWtrCond"),
        igctWaterPres1=scada.get("WCNV_IGCTWtrPres1"),
        igctWaterPres2=scada.get("WCNV_IGCTWtrPres2"),
        igctWaterTemp=scada.get("WCNV_IGCTWtrTmp"),

        # ── WGDC ──
        transformerTemp=scada.get("WGDC_TrfCoreTmp"),

        # ── WMET ──
        windDirection=scada.get("WMET_WDirAbs"),
        outsideTemp=scada.get("WMET_TmpOutside"),

        # ── WNAC ──
        nacelleTemp=scada.get("WNAC_NacTmp"),
        nacelleCabTemp=scada.get("WNAC_NacCabTmp"),
        vibrationX=scada.get("WNAC_VibMsNacXDir"),
        vibrationY=scada.get("WNAC_VibMsNacYDir"),

        # ── WYAW ──
        yawError=scada.get("WYAW_YwVn1AlgnAvg5s"),
        yawBrakePressure=scada.get("WYAW_YwBrkHyPrs"),
        cableWindup=scada.get("WYAW_CabWup"),

        # ── WCNV — Electrical Response ──
        reactivePower=scada.get("WCNV_ReactPwr"),
        powerFactor=scada.get("WCNV_PwrFactor"),
        apparentPower=scada.get("WCNV_AppPwr"),
        freqWattDerate=scada.get("WCNV_FreqWattDerate"),
        inertiaPower=scada.get("WCNV_InertiaPwr"),
        converterMode=int(scada.get("WCNV_CnvMode", 0)) if scada.get("WCNV_CnvMode") is not None else None,
        rideThroughBand=int(scada.get("WCNV_RtBand", 0)) if scada.get("WCNV_RtBand") is not None else None,

        # ── WVIB — Vibration Spectral Bands ──
        vibBand1pX=scada.get("WVIB_Band1pX"),
        vibBand1pY=scada.get("WVIB_Band1pY"),
        vibBand3pX=scada.get("WVIB_Band3pX"),
        vibBand3pY=scada.get("WVIB_Band3pY"),
        vibBandGearX=scada.get("WVIB_BandGearX"),
        vibBandGearY=scada.get("WVIB_BandGearY"),
        vibBandHfX=scada.get("WVIB_BandHfX"),
        vibBandHfY=scada.get("WVIB_BandHfY"),
        vibBandBbX=scada.get("WVIB_BandBbX"),
        vibBandBbY=scada.get("WVIB_BandBbY"),
        vibCrestFactor=scada.get("WVIB_CrestFactor"),
        vibKurtosis=scada.get("WVIB_Kurtosis"),

        # ── WVIB — Vibration Alarm Thresholds ──
        vibAlarm1p=int(scada.get("WVIB_Alarm1p", 0)) if scada.get("WVIB_Alarm1p") is not None else None,
        vibAlarm3p=int(scada.get("WVIB_Alarm3p", 0)) if scada.get("WVIB_Alarm3p") is not None else None,
        vibAlarmGear=int(scada.get("WVIB_AlarmGear", 0)) if scada.get("WVIB_AlarmGear") is not None else None,
        vibAlarmHf=int(scada.get("WVIB_AlarmHf", 0)) if scada.get("WVIB_AlarmHf") is not None else None,
        vibAlarmBb=int(scada.get("WVIB_AlarmBb", 0)) if scada.get("WVIB_AlarmBb") is not None else None,
        vibAlarmOverall=int(scada.get("WVIB_AlarmOverall", 0)) if scada.get("WVIB_AlarmOverall") is not None else None,
        vibThresh1pWarn=scada.get("WVIB_Thresh1pWarn"),
        vibThresh1pAlrm=scada.get("WVIB_Thresh1pAlrm"),

        # ── WLOD — Structural Load & Fatigue (New Standard) ──
        towerFaMoment=scada.get("WLOD_TwrFaMom"),
        towerSsMoment=scada.get("WLOD_TwrSsMom"),
        bladeFlapMoment=scada.get("WLOD_BldFlapMom"),
        bladeEdgeMoment=scada.get("WLOD_BldEdgeMom"),
        delTowerFa=scada.get("WLOD_DelTwrFa"),
        delTowerSs=scada.get("WLOD_DelTwrSs"),
        delBladeFlap=scada.get("WLOD_DelBldFlap"),
        delBladeEdge=scada.get("WLOD_DelBldEdge"),
        damageTowerFa=scada.get("WLOD_DmgTwrFa"),
        damageTowerSs=scada.get("WLOD_DmgTwrSs"),
        damageBladeFlap=scada.get("WLOD_DmgBldFlap"),
        damageBladeEdge=scada.get("WLOD_DmgBldEdge"),
        productionHours=scada.get("WLOD_ProdHours"),

        # ── Fault info ──
        activeFaults=fault_info,

        # ── Raw SCADA dict ──
        scadaTags=scada if scada else None,
    )


class DataBroker:
    """Unified data interface for simulation and real OPC data.

    Storage strategy:
      - Simulator runs at 1Hz, in-memory buffer keeps 1 hour
      - SQLite writes throttled to every 10 seconds (configurable)
      - Events trigger 1s snapshot capture (±10 min around event)
      - Background task does downsampling and cleanup
    """

    # Default: write to SQLite every N seconds
    WRITE_INTERVAL_S = 10
    # 這些來源的 Live 事件代表操作員動過風場（注入 / 清除故障、控制、設定、維修、工單）：要求盡快存檔
    _OPERATOR_EVENT_SOURCES = frozenset({"faults", "control", "config", "maintenance", "workflow", "test_plan"})
    # 還原存檔時，storage 裡最後一筆 Live 讀值離存檔點多遠以內才算「存檔後、關閉前寫的」（模擬秒，
    # 1 倍時）。存檔每 30 實際秒一次，加速時模擬時鐘每實際秒走「倍率」秒，所以上限再乘上存檔時的倍率
    # （WMOM-20261126-01：倍率 200 時存檔點與最後一筆差了 9 分鐘，沒當成重跑段，那段讀值寫了兩次）；
    # 超過這個範圍的列是別的來源寫的，不拿來決定重跑段
    _MAX_REPLAY_S = 120.0
    # Raw data retention (days)：SQLite 裡留最近幾天的原始讀值（每列約 4 KB）
    RAW_RETENTION_DAYS = 3
    # 原始讀值總共留幾天（WMOM-20261125-03-c）：超過 RAW_RETENTION_DAYS 的部分在每日 Parquet 歸檔裡
    # （每列約 0.13 KB），循環保存。0＝不歸檔，照舊只留 RAW_RETENTION_DAYS 天。半年＝DEC-20261125-01
    ARCHIVE_RETENTION_DAYS = 183
    # 找「最近寫入的 Live 讀值」時最多往回看幾個 Live session（連續重啟而沒寫資料的 session 會佔掉名額）
    _CLOCK_LOOKBACK_SESSIONS = 200
    # 1-min aggregate retention (days)
    AGG_1M_RETENTION_DAYS = 90
    # Snapshot window: seconds of 1s data to capture before/after event
    SNAPSHOT_WINDOW_S = 600  # 10 minutes
    # Snapshot retention (days) — WMOM-20260505-01
    SNAPSHOTS_RETENTION_DAYS = 7
    # Snapshot dedupe cooldown — WMOM-20260505-01：同 turbine 同類 event_class 在這秒內
    # 重新 trigger 時，僅延長 active window，不重複 retroactive write 10 分鐘 history。
    # 解決 simulator state machine flapping 把同類 stop 反覆 emit 的放大效應。
    SNAPSHOT_DEDUPE_COOLDOWN_S = 300  # 5 minutes

    def __init__(self, farm_registry: Optional[FarmRegistry] = None):
        self.mode = DataSourceMode.SIMULATION
        self.farm_registry = farm_registry or FarmRegistry()
        self._active_farm_id: Optional[str] = None
        self.storage = Storage()
        # 保留期（伺服器依環境變數設定，見 server/app.py）：SQLite 的熱資料天數、含歸檔的總天數
        self.raw_hot_days: int = self.RAW_RETENTION_DAYS
        self.archive_days: int = self.ARCHIVE_RETENTION_DAYS
        # 保留期的例行工作同一時間只能有一方在跑（maintenance 執行緒每小時一次、管理端可以手動觸發）：
        # 兩邊同時寫日檔與索引會互相蓋掉
        self._retention_lock = threading.Lock()
        # 運維閉環（跳機開單、完工修復、運轉狀態紀錄，WMOM-20261125-04）：第一次取用時才建立——它會載入
        # 工單模組，沒開閉環的 broker（測試、工具）不必載入
        self._om_loop: Optional['OmLoop'] = None
        self.simulator: Optional[WindFarmSimulator] = None
        self._opc_adapter: Optional['OPCDAAdapter'] = None
        self._sim_config = SimulationConfig()
        self._last_tur_state: Dict[str, int] = {}
        self._last_shutdown_cause: Dict[str, Optional[str]] = {}
        self._last_fault_trip: Dict[str, bool] = {}

        # Fault lifecycle tracking: {turbine_id: {scenario_id: phase}}
        self._last_fault_phases: Dict[str, Dict[str, str]] = {}
        # Track active fault scenario keys for lifecycle start/end
        self._active_fault_keys: Dict[str, set] = {}  # {turbine_id: {scenario_id, ...}}
        # Fatigue alarm level tracking: {turbine_id: (tower_level, blade_level)}
        self._last_fatigue_alarm: Dict[str, tuple] = {}
        # Session tracking
        self._session_id: Optional[int] = None
        # 資料來源選擇（WMOM-20260719-04）：開機不自動起模擬，由使用者登入後選定才啟動。
        # source_kind：None（未選）/ "simulation"（即時模擬自由跑）/ "scenario"（產生情境：
        # simulator 供批次、不自由跑，DEC-20260720-01 PR B）/ "live"（實接 OPC）/ "view"
        # （僅調閱過去情境、不起任何來源）。
        self._source_active: bool = False
        self._source_kind: Optional[str] = None
        # Write throttle state
        self._last_write_time: float = 0  # OPC 來源用（依實際時間節流）
        # 重啟續跑（WMOM-20261125-03-b）：開了才定期把即時模擬的狀態存檔、啟動時還原。預設關——由
        # 伺服器依 WMOM_LIVE_RESUME 開啟（見 server/app.py）；測試與一次性的 broker 不讀寫存檔
        self.checkpoint_enabled: bool = False
        # 即時模擬裡跳過機的故障不鎖機組、自動重啟再跳（WMOM-20261125-06-a）；伺服器依 WMOM_LIVE_RETRIP 開
        self.live_retrip: bool = False
        # 這次啟動的即時模擬是不是從存檔還原的
        self.live_restored: bool = False
        # 即時資料的連續段編號：這份風場狀態從頭開始的那個 session 的 id。還原存檔時沿用存檔裡的，
        # 所以重啟續跑、產生情境都不會改變它；只有風場狀態真的重來才會變
        self.live_epoch: int = 0
        # 還原存檔後的重跑段：存檔點到伺服器停掉之間的讀值與事件已經在 storage 裡，模擬時鐘走到這個時間
        # （含）之前，重跑出來的不再寫（避免重複）；None＝沒有重跑段
        self._replay_until: Optional[datetime] = None
        # 重跑段之後、下一個寫入時段開始之前：這些步在伺服器被強制關閉前可能已經處理過（讀值還沒寫、
        # 事件已經記了），重跑時 Live 執行緒送出的事件逐筆對 storage 查重；None＝沒有這一段
        self._dedupe_until: Optional[datetime] = None
        # 重跑段 / 去重段裡由 Live 執行緒設定：只影響這個執行緒送出的 Live 事件（其他執行緒的操作事件照寫）
        self._replay_local = threading.local()
        # 即時模擬上次寫入的時段編號（讀值的模擬時間 // WRITE_INTERVAL_S）。依模擬時間對齊寫入：
        # 每個時段寫第一筆，間隔固定、不受每步計算時間與時間倍率影響（WMOM-20261125-03-a）
        self._last_write_slot: Optional[int] = None
        # 最近一次寫進 storage 的 Live 讀值：機組 ID →（時間戳, SCADA 值）。對外唯讀 API 的「最新讀值」
        # 用它（WMOM-20261125-02）——與歷史查得到的列相同，不讀 simulator 記憶體（批次期間那裡是情境的值）
        self._last_stored_live: Dict[str, Tuple[str, Dict[str, object]]] = {}
        # Snapshot state: when an event occurs, capture 1s data for a window
        self._snapshot_active: Dict[str, float] = {}  # turbine_id -> end_time
        self._snapshot_event_ref: Dict[str, str] = {}
        # WMOM-20260505-01：同類 event 觸發 dedupe cooldown 用
        # turbine_id -> (event_class, last_seen_time) — last_seen 為「上次 trigger 的時間」
        self._snapshot_last_class: Dict[str, tuple[str, float]] = {}
        # Background maintenance thread
        self._maintenance_thread: Optional[threading.Thread] = None
        self._maintenance_running = False
        # 可中斷睡眠旗標：讓 maintenance thread 從 5 分鐘週期睡眠中被 stop() 立刻喚醒。
        # 用 Event.wait(timeout) 取代 time.sleep(300)，否則 _stop_maintenance 的 join(5) 幾乎
        # 必 timeout（thread 還在睡），害每次切換來源的 stop() 固定卡 5 秒（打在「一鍵啟動」體驗上）。
        self._maintenance_wake = threading.Event()
        # 保護 start/stop/switch_mode 的生命週期操作（WMOM-20260720-08 (1)）：真併發呼叫
        # （如使用者連點兩下 /api/source/select）可能在 _start_maintenance 讀到已賦值但尚未
        # .start() 的 thread 時被另一執行緒的 stop() 撞上，拋 RuntimeError: cannot join
        # thread before it is started。用 RLock（而非 Lock）是因為 switch_mode 會在同一
        # 執行緒內呼叫 stop() 再 start()，需可重入。
        self._lifecycle_lock = threading.RLock()

    def _init_farm_storage(self):
        """Point storage at the active farm's database."""
        farm_id = self._active_farm_id or self.farm_registry.get_active_farm_id()
        if not farm_id:
            farm_id = self.farm_registry.ensure_default_farm()
        self._active_farm_id = farm_id
        db_path = str(self.farm_registry.get_farm_db_path(farm_id))
        self.storage = Storage(db_path=db_path)

    def switch_farm(self, farm_id: str) -> bool:
        """Switch the active wind farm. Stops current simulator, swaps DB, restarts."""
        farm = self.farm_registry.get_farm(farm_id)
        if not farm:
            return False
        # 同款理由（WMOM-20260720-08 (1)）：stop() 與 start() 之間有一段修改 farm registry /
        # storage / _sim_config 的空窗，不上鎖的話另一執行緒的 start/stop/switch_mode/
        # select_view_only 可能插進來動到同一組欄位。
        with self._lifecycle_lock:
            self.stop()
            self.farm_registry.set_active_farm(farm_id)
            self._active_farm_id = farm_id
            self._init_farm_storage()

            from simulator.physics.turbine_physics import TurbineSpec
            if farm.turbine_spec:
                spec = TurbineSpec.from_farm_dict(farm.turbine_spec)
            else:
                spec = TurbineSpec()

            self._sim_config = SimulationConfig(turbineCount=farm.turbine_count)
            self.start()

            if self.simulator:
                for model in self.simulator.turbines.values():
                    # 規格相同就不重套：update_spec 會重建 PLC 保護層，從存檔還原的鎖存與計數會被清掉
                    if model.spec != spec:
                        model.update_spec(spec)

        return True

    @property
    def active_farm_id(self) -> Optional[str]:
        return self._active_farm_id

    def _active_farm_timezone(self) -> str:
        """目前風場的時區（模擬的日夜 / 季節循環用，WMOM-20261021-11）；查不到風場時用預設值。

        Returns:
            IANA 時區名稱。
        """
        farm = self.farm_registry.get_farm(self._active_farm_id) if self._active_farm_id else None
        if farm is None:
            return DEFAULT_SITE_TIMEZONE
        try:
            site_timezone(farm.timezone)
        except ValueError:
            # 存的名稱在本機無效（手改 DB、換到缺 tzdata 的機器）：不讓整個模擬起不來
            print(f"[DataBroker] 風場 {farm.farm_id} 的時區 {farm.timezone!r} 無效，"
                  f"改用預設 {DEFAULT_SITE_TIMEZONE}")
            return DEFAULT_SITE_TIMEZONE
        return farm.timezone

    def start(self, config: Optional[DataSourceConfig] = None,
              sim_config: Optional[SimulationConfig] = None,
              run_loop: bool = True, fresh: bool = False) -> None:
        """Start the data broker in simulation or OPC mode and launch background maintenance.

        ``run_loop`` 只在 SIMULATION 有意義：True＝即時模擬（自由跑連續產資料，source_kind
        ``simulation``）；False＝產生情境（simulator 供批次、不自由跑，source_kind ``scenario``，
        DEC-20260720-01 PR B）。``fresh``＝即使開了重啟續跑也不還原存檔，風場從頭開始。
        """
        with self._lifecycle_lock:
            if sim_config:
                self._sim_config = sim_config
            if config:
                self.mode = config.mode

            if self._active_farm_id is None:
                self._init_farm_storage()

            if self.mode == DataSourceMode.SIMULATION:
                # 先設來源種類再起迴圈：Live 執行緒第一步的事件就要用模擬時鐘（live_clock 看這個欄位）
                self._source_kind = "simulation" if run_loop else "scenario"
                self._start_simulator(run_loop=run_loop, fresh=fresh)
            else:
                self._start_opc(config)
                self._source_kind = "live"
            self._source_active = True

            # Start background maintenance (downsampling + cleanup)
            self._start_maintenance()

    def select_view_only(self):
        """僅調閱過去情境：停掉任何在跑的來源、標記已選但**不啟動**任何資料生成。

        情境調閱只讀 storage（session 隔離），不需要跑 simulator——避免又開始產生預設風場
        資料（正是使用者不想要的）。overview/live 視圖在此狀態下自然為空。
        """
        with self._lifecycle_lock:
            # 與 start/stop/switch_mode 共用同一把鎖（WMOM-20260720-08 (1)）：本方法呼叫
            # stop() 後仍會繼續修改 source_active/source_kind/simulator，若不整段上鎖，另一
            # 執行緒的 start()/switch_mode() 仍可能在 stop() 與這裡的賦值之間插入，讓兩者的
            # 狀態變更交錯（實測：source_kind 最終回報 view，但插進來的 start() 真的建了
            # simulator + 起了 maintenance thread，兩者狀態互相矛盾）。
            self.stop()
            # 關鍵：把 storage 指向 active farm 的 DB。DataBroker.__init__ 的 Storage() 綁預設
            # legacy 路徑，只有 start()/_init_farm_storage() 會重指。開機 idle 後若第一個動作就是
            # 「調閱過去情境」（本方法，不經 start），沒重指就會讀到空的預設 DB → 情境清單空掉
            # （正是 #4 要修的「情境調不回來」以新根因重現）。_init_farm_storage 為 idempotent。
            if self._active_farm_id is None:
                self._init_farm_storage()
            self.simulator = None
            self._source_active = True
            self._source_kind = "view"

    @contextmanager
    def pause_live_for_batch(self) -> Iterator[bool]:
        """批次生成期間暫停 Live 自由跑迴圈，結束後恢復——供所有「同步在 request thread 跑
        ``simulator.generate_bulk`` + ``store_readings``」的端點共用。

        任何這類端點（``config.py::generate_bulk``、``faults.py::run_test_plan`` …）都應把
        「清故障 + generate_bulk + downsampling + 收尾寫入」整段包在本 context 內：消掉 Live 迴圈
        這個**高頻 writer**（Live thread 與批次同時 step 物理 / 並寫同一 SQLite 是 Windows 上
        ``database is locked`` 的根因）。集中一處避免各端點各自漏套或寫法分歧。
        註：背景 maintenance thread 的低頻 downsampling/cleanup 寫入不受此暫停影響，但頻率遠低、
        由 WAL + busy_timeout 緩解，非本 bug 的重現路徑。

        Yields:
            批次前 Live thread 是否在跑（少數呼叫端可據此微調行為；一般忽略即可）。
        """
        sim = self.simulator
        if sim is None:
            # 無 simulator（view/idle）：呼叫端自身會處理（如回 400），這裡不介入。
            yield False
            return
        was_running = sim.stop_live_loop()
        # 運維閉環：批次期間收到的工單動作先記著，Live 的狀態還原之後才套用（WMOM-20261125-04）
        paused_loop = self._om_loop_if_enabled() if was_running else None
        if paused_loop is not None:
            paused_loop.pause()
        # 批次會清故障、重設機組、把模型推到情境的時間；Live 的狀態先留一份，批次結束後還原——即時風場
        # 接著原本的狀態跑（暫停的那段時間由 Live 迴圈補跑），不受產生情境影響（WMOM-20261125-03-b）
        live_state = sim.checkpoint_state() if was_running else None
        # 前端走勢小圖用的一小時讀值歷史不在存檔裡：另外留一份，批次後放回去（批次會把自己的讀值塞進去）
        live_history = ({tid: deque(items, maxlen=items.maxlen) for tid, items in sim.history.items()}
                        if was_running else None)
        try:
            yield was_running
        finally:
            if live_state is not None:
                try:
                    sim.restore_state(live_state)
                    if live_history is not None:
                        sim.history = live_history
                except Exception as exc:  # noqa: BLE001  還原失敗就照舊從批次留下的狀態接著跑
                    print(f"[DataBroker] 批次後還原即時模擬的狀態失敗：{exc}")
                    # 風場狀態其實被批次改掉了：換一個連續段編號，讓外部知道資料在這裡不連續
                    self.live_epoch = int(_time.time())
            # time_step 僅在需恢復時取；用 broker 的 sim_config（Live 自由跑的節奏）。
            sim.restore_live_loop(
                was_running,
                self._sim_config.timeStep if was_running else 1.0,
            )
            if was_running:
                self.apply_live_settings()   # 還原的是批次前的產生器：設定以風場 DB 存的為準
            if paused_loop is not None:
                # 批次期間有人開工 / 完工 / 撤單：等 Live 的狀態還原、迴圈恢復之後才套用到機組（WMOM-20261125-04）
                paused_loop.resume()

    @property
    def source_active(self) -> bool:
        """是否已選定資料來源（未選＝開機 idle，前端顯示來源選擇頁）。"""
        return self._source_active

    @property
    def source_kind(self) -> Optional[str]:
        """已選來源種類：simulation（即時模擬）/ scenario（產生情境、不自由跑）/ live / view /
        None（未選）。"""
        return self._source_kind

    def _start_simulator(self, run_loop: bool = True, fresh: bool = False) -> None:
        """建立 simulator。``run_loop=True``＝即時模擬（起自由跑背景 thread、連續產資料）；
        ``run_loop=False``＝**產生情境**（DEC-20260720-01 PR B）：只建 simulator 供批次生成用，
        **不起自由跑迴圈**——情境是可重現的凍結資料集，不該持續產生新資料。"""
        if self.simulator and self.simulator.is_running:
            self.simulator.stop()

        # End previous session if any
        if self._session_id is not None:
            self.storage.end_session(self._session_id)

        self._last_tur_state.clear()
        self._last_shutdown_cause.clear()
        self._last_fault_trip.clear()
        self._last_fault_phases.clear()
        self._active_fault_keys.clear()
        self._last_fatigue_alarm.clear()
        self._last_stored_live = {}
        self._last_write_slot = None
        self._replay_until = None
        self._dedupe_until = None

        self.simulator = WindFarmSimulator(
            turbine_count=self._sim_config.turbineCount,
            base_wind_speed=self._sim_config.baseWindSpeed,
            turbulence_intensity=self._sim_config.turbulenceIntensity,
            site_timezone=self._active_farm_timezone(),
        )

        # Create a new session
        self._session_id = self.storage.create_session(
            data_source="simulation",
            turbine_count=self._sim_config.turbineCount,
            rated_power_kw=2000,  # Z72-2000-MV default
            model_name="Z72-2000-MV",
            config={
                "baseWindSpeed": self._sim_config.baseWindSpeed,
                "turbulenceIntensity": self._sim_config.turbulenceIntensity,
                "timeStep": self._sim_config.timeStep,
                "site_timezone": self.simulator.wind_model.site_timezone_name,
            },
        )
        print(f"[DataBroker] Created session #{self._session_id}")

        self.live_restored = False
        self.live_epoch = int(self._session_id)
        if run_loop and self.checkpoint_enabled:
            live_checkpoint.code_fingerprint()  # 現在就算（讀幾十個檔），不要拖到 Live 迴圈第一次存檔
            if not fresh:
                try:
                    self._restore_live_checkpoint()
                except Exception as exc:  # noqa: BLE001  還原的任何一步出錯都不該讓來源起不來
                    print(f"[DataBroker] 還原即時模擬的狀態時出錯，從頭開始：{exc}")
                    self._reset_resume_state()
            self.simulator.on_checkpoint(self._write_live_checkpoint)
        if run_loop and not self.live_restored:
            # 風場從頭開始（沒開續跑、沒有可用的存檔、選擇從頭開始）：時鐘接在已存的 Live 讀值之後
            self._continue_after_stored_data()
        loop = self._om_loop_if_enabled()
        if run_loop and loop is not None:
            loop.rebuild()  # 進行中的工單 → 哪些機組在維修模式

        # 即時模擬裡跳過機的故障不鎖機組，鎖存解除後自動重啟、再跳（WMOM-20261125-06-a）；批次不受影響
        self.simulator.retrip_after_restart = bool(getattr(self, "live_retrip", False))
        if run_loop:
            self.apply_live_settings()   # 故障產生器、模擬維修班的設定（存在風場 DB）

        # Register data callback (throttled writes)
        self.simulator.on_data(self._on_sim_data)
        if run_loop:
            self.simulator.start(time_step=self._sim_config.timeStep)

    def _checkpoint_path(self) -> Path:
        """即時模擬的存檔位置：與目前風場的 DB 同一個目錄。"""
        return Path(self.storage.db_path).with_name(live_checkpoint.CHECKPOINT_FILENAME)

    def _continue_after_stored_data(self) -> None:
        """即時模擬從頭開始時，模擬時鐘接在已經存下的 Live 讀值之後——Live 的歷史在時間上不往回。

        會往回的情況：之前用過時間倍率（模擬時鐘跑在實際時間前面），之後風場狀態重來（沒開續跑、程式更新、
        選擇從頭開始）。不接著走的話，同一段時間會有兩份讀值，依時間的查詢、10 分鐘統計、每日歸檔都會混在
        一起（WMOM-20261125-03-c）。還原存檔時不需要：存檔自己帶著時鐘。
        """
        simulator = self.simulator
        if simulator is None:
            return
        try:
            stamps = [self.storage.last_live_reading_timestamp(tid, max_sessions=self._CLOCK_LOOKBACK_SESSIONS)
                      for tid in simulator.turbines]
            latest = max((parse_iso(ts) for ts in stamps if ts), default=None)
        except Exception as exc:  # noqa: BLE001  查不到就照實際時間起跑，不擋啟動
            print(f"[DataBroker] 讀不到已存的 Live 讀值時間，時鐘從現在開始：{exc}")
            return
        if latest is not None and latest >= utc_now():
            simulator.start_clock_after(latest)
            self._last_write_slot = int(latest.timestamp() // self.WRITE_INTERVAL_S)  # 那個時段已經有一筆
            print(f"[DataBroker] 已存的 Live 讀值到 {iso_utc(latest)}（在現在之後），模擬時鐘接著走")

    def _reset_resume_state(self) -> None:
        """清掉還原存檔留下的 broker 狀態（還原失敗、重新啟動時用）。"""
        self.live_restored = False
        if self._session_id is not None:
            self.live_epoch = int(self._session_id)
        self._replay_until = None
        self._dedupe_until = None
        self._last_write_slot = None
        self._active_fault_keys.clear()
        self._last_fault_phases.clear()

    def _restore_live_checkpoint(self) -> None:
        """有可用的存檔就還原即時模擬的狀態（剛建好、還沒起迴圈的 simulator）。"""
        simulator = self.simulator
        if simulator is None:
            return
        saved = live_checkpoint.load_checkpoint(
            self._checkpoint_path(), list(simulator.turbines), simulator.wind_model.site_timezone_name)
        if saved is None:
            return
        # 會出錯的查詢放在還原之前：這裡丟例外時模擬器還沒被動過，呼叫端可以直接當成沒有存檔
        last_written = self.storage.last_live_reading_timestamp(next(iter(simulator.turbines), ""))
        try:
            simulator.restore_state(saved.state)
        except Exception as exc:  # noqa: BLE001  存檔解不開就從頭開始，不讓伺服器起不來
            print(f"[DataBroker] 即時模擬的存檔還原失敗，從頭開始：{exc}")
            return
        self.live_restored = True
        self.live_epoch = saved.live_epoch or self.live_epoch
        saved_scale = max(1.0, float(simulator.time_scale))
        if simulator.time_scale > 1.0:
            # 存檔時正在加速：重啟後回到 1 倍（時鐘維持領先的量），要加速請操作員重新設定
            print(f"[DataBroker] 存檔時的時間倍率是 {simulator.time_scale:g}，還原後改回 1")
            simulator.time_scale = 1.0
        # 已經開著的故障生命週期事件在重啟前記過了：把基準補上，第一批讀值進來時不再記一次「故障開始」
        for fault in simulator.fault_engine.get_fault_status():
            turbine_id, scenario_id = str(fault.get("turbine_id") or ""), str(fault.get("scenario_id") or "")
            self._active_fault_keys.setdefault(turbine_id, set()).add(scenario_id)
            self._last_fault_phases.setdefault(turbine_id, {})[scenario_id] = str(fault.get("phase") or "")
        # 上次已寫到哪：之後接著下一個時段寫
        if not last_written or saved.sim_clock is None:
            return
        moment = parse_iso(last_written)
        gap_s = (moment - saved.sim_clock).total_seconds()
        if abs(gap_s) > self._MAX_REPLAY_S * saved_scale:
            # 最後一列離存檔點太遠：不是「存檔後、關閉前」寫的（例：沒有命名的批次把模擬時間的列寫進
            # Live session），不拿它當重跑的依據
            return
        slot = int(moment.timestamp() // self.WRITE_INTERVAL_S)
        self._last_write_slot = slot
        if gap_s > 0:
            # 伺服器被強制關閉：存檔點到最後一筆寫入之間的步已經處理過，重跑時讀值與事件都不再寫
            self._replay_until = moment
        # 最後一筆寫入之後、下一個時段開始之前的步可能也處理過（讀值還沒到寫的時候，事件已經記了）：
        # 這一段重跑時，事件逐筆對 storage 查重
        # （含下一個時段的第一步：事件先記、讀值後寫，關閉可能落在兩者之間）
        slot_end = datetime.fromtimestamp((slot + 1) * self.WRITE_INTERVAL_S, tz=moment.tzinfo)
        if slot_end >= saved.sim_clock:
            self._dedupe_until = slot_end
        print(f"[DataBroker] 已還原即時模擬的狀態（存檔時間 {saved.saved_at}，模擬時鐘 {saved.sim_clock}）")

    def _write_live_checkpoint(self, state: bytes) -> None:
        """把即時模擬的狀態寫進存檔（Live 迴圈定期呼叫；停止來源時再寫一次）。"""
        simulator = self.simulator
        if simulator is None:
            return
        live_checkpoint.save_checkpoint(self._checkpoint_path(), live_checkpoint.LiveCheckpoint(
            state=state,
            sim_clock=simulator.sim_clock,
            turbine_ids=list(simulator.turbines),
            site_timezone=simulator.wind_model.site_timezone_name,
            live_epoch=self.live_epoch,
            saved_at=iso_utc(),
        ))

    def _start_opc(self, config: Optional[DataSourceConfig]):
        # OPC DA adapter - lazy import to avoid dependency issues
        try:
            from server.opc_adapter import OPCDAAdapter
            self._opc_adapter = OPCDAAdapter(config)
            self._opc_adapter.on_data(self._on_opc_data)
            self._opc_adapter.start()
        except ImportError:
            print("[DataBroker] OPC adapter not available, falling back to simulation")
            self.mode = DataSourceMode.SIMULATION
            self._start_simulator()

    def _on_sim_data(self, readings: List[Dict]):
        """Callback from simulator — called on every Live step（加速時也是每一步）.

        - Always checks for events (state changes, faults)
        - Writes to SQLite once per WRITE_INTERVAL_S seconds of **simulated** time (aligned slots)
        - If a snapshot is active for a turbine, writes 1s data to snapshots table
        """
        now = self._snapshot_clock()
        step_time = self._reading_time(readings)
        if self._replay_until is not None:
            if step_time is not None and step_time <= self._replay_until:
                # 還原存檔後重跑到上次寫到的時間之前：事件偵測照跑（建立基準、取走 PLC 事件），但不寫任何東西
                self._replay_local.active = True
                try:
                    self._detect_sim_events(readings)
                finally:
                    self._replay_local.active = False
                return
            self._replay_until = None
        if self._dedupe_until is not None and step_time is not None and step_time <= self._dedupe_until:
            # 上次寫入之後、下一個時段之前：這一步在伺服器被強制關閉前可能已經處理過，事件逐筆查重
            self._replay_local.dedupe = True
            try:
                self._detect_sim_events(readings)
            finally:
                self._replay_local.dedupe = False
        else:
            self._dedupe_until = None
            self._detect_sim_events(readings)

        # Check if any turbine has an active snapshot window
        for reading in readings:
            tid = reading.get('turbine_id', '')
            snap_end = self._snapshot_active.get(tid)
            if snap_end and now < snap_end:
                event_ref = self._snapshot_event_ref.get(tid, '')
                self.storage.store_snapshot(reading, event_ref, self._session_id)
            elif snap_end and now >= snap_end:
                del self._snapshot_active[tid]
                del self._snapshot_event_ref[tid]
                # _snapshot_last_class 刻意保留 — cooldown 機制需在 active window
                # 結束後仍能阻擋同類 event 馬上再 retroactive write（WMOM-20260505-01）。
                # 若內存壓力大，未來可加「last_class 過期清理」(now - last_seen > cooldown*N)。

        # 對齊模擬時間的固定間隔寫入：每個時段（WRITE_INTERVAL_S 秒）寫進入該時段的第一筆
        slot = self._write_slot(readings)
        if slot != self._last_write_slot:
            self._last_write_slot = slot
            self.storage.store_readings(readings, self._session_id)
            self._remember_stored(readings)
            loop = self._om_loop_if_enabled()
            if loop is not None:
                loop.account(readings, float(self.WRITE_INTERVAL_S))  # 運轉狀態紀錄（WMOM-20261125-04）

    def _replaying(self) -> bool:
        """目前的執行緒是否在還原存檔後的重跑段裡（Live 執行緒在重跑段送出的事件與快照不寫）。"""
        local = getattr(self, "_replay_local", None)  # 以 object.__new__ 建的測試替身沒有這個屬性
        return bool(getattr(local, "active", False))

    def _deduping(self) -> bool:
        """目前的執行緒是否在去重段裡（Live 執行緒送出的事件要先查 storage 有沒有同一筆）。"""
        local = getattr(self, "_replay_local", None)
        return bool(getattr(local, "dedupe", False))

    @staticmethod
    def _reading_time(readings: List[Dict]) -> Optional[datetime]:
        """這批讀值的模擬時間（tz-aware UTC）；讀不到為 None。"""
        for reading in readings:
            stamp = reading.get('timestamp')
            if stamp:
                try:
                    return to_utc(stamp if isinstance(stamp, datetime) else parse_iso(str(stamp)))
                except (TypeError, ValueError):
                    return None
        return None

    def _live_stamp(self) -> str:
        """Live 事件參照用的時間字串：即時模擬在跑時是模擬時鐘（重跑同一步會得到同一個字串），否則現在。"""
        try:
            clock = self.live_clock()
        except AttributeError:  # 以 object.__new__ 建的測試替身
            clock = None
        return iso_utc(clock) if clock is not None else iso_utc()

    def _snapshot_clock(self) -> float:
        """快照視窗用的時間（epoch 秒）：即時模擬在跑時用模擬時鐘，否則用實際時間。

        用模擬時鐘是因為 callback 每一步都會被呼叫：補跑或加速時一個實際秒有幾十步，視窗若以實際時間算，
        一次事件會存下幾十萬列快照。
        """
        try:
            clock = self.live_clock()
        except AttributeError:  # 以 object.__new__ 建的測試替身
            clock = None
        return clock.timestamp() if clock is not None else _time.time()

    def _write_slot(self, readings: List[Dict]) -> int:
        """這批讀值屬於哪個寫入時段：讀值的模擬時間 // ``WRITE_INTERVAL_S``（讀不到時間就用實際時間）。"""
        moment = self._reading_time(readings)
        epoch = moment.timestamp() if moment is not None else _time.time()
        return int(epoch // self.WRITE_INTERVAL_S)

    def _remember_stored(self, readings: List[Dict]) -> None:
        """記下剛寫進 storage 的 Live 讀值（每台機組最新一筆）。"""
        latest = dict(self._last_stored_live)
        for reading in readings:
            scada = reading.get('scada')
            turbine_id = str(reading.get('turbine_id', ''))
            if turbine_id and isinstance(scada, dict):
                latest[turbine_id] = (reading_timestamp(reading), dict(scada))
        self._last_stored_live = latest  # 整個換掉：讀的一方拿到的永遠是完整的一份

    def latest_stored_readings(self) -> List[Tuple[str, str, Dict[str, object]]]:
        """最近一次寫進 storage 的 Live 讀值（對外唯讀 API 的「最新讀值」）。

        Returns:
            ``(機組 ID, 時間戳, SCADA 值)``，依機組 ID 排序；還沒寫過為空。
        """
        stored = self._last_stored_live
        return [(turbine_id, stored[turbine_id][0], stored[turbine_id][1]) for turbine_id in sorted(stored)]

    @property
    def live_sample_period_s(self) -> float:
        """Live 讀值寫進 storage 的間隔（模擬時間，秒）。寫入對齊模擬時間，不受時間倍率影響。"""
        return float(self.WRITE_INTERVAL_S)

    def live_clock(self) -> Optional[datetime]:
        """即時模擬的時鐘（最近一步的模擬時間）；即時模擬沒在跑（未啟動、批次中、非模擬來源）為 None。"""
        simulator = self.simulator
        if (simulator is None or self._source_kind != "simulation" or not simulator.is_running
                or simulator.is_bulk_running):
            return None
        return simulator.sim_clock

    @staticmethod
    def _extract_event_class(event_ref: str) -> str:
        """Strip the trailing ISO timestamp from an event_ref to get a dedupe key.

        WMOM-20260505-01：用 event_class 而非 full event_ref 做 dedupe，
        讓 simulator flapping 在 80 秒內 emit 11 個不同 timestamp 的 stop event 不會
        各自觸發新 snapshot capture window。

        Examples
        --------
        >>> _extract_event_class("stop:WT007:7:2026-05-04T18:01:03.553883")
        "stop:WT007:7"
        >>> _extract_event_class("fault_trip:WT003:2026-05-04T18:01:03.553")
        "fault_trip:WT003"
        >>> _extract_event_class("custom_no_timestamp")
        "custom_no_timestamp"
        """
        # 嚴格匹配 `:YYYY-MM-DDTHH:` 結構（含時分），避免 turbine_id 含 4 位數年份
        # 樣字串（如 maint:WT2026:1:...）誤截。
        m = re.search(r":\d{4}-\d{2}-\d{2}T\d{2}:", event_ref)
        return event_ref[:m.start()] if m else event_ref

    def _trigger_snapshot(self, turbine_id: str, event_ref: str):
        """Activate 1s snapshot capture for a turbine around an event.

        Also retroactively saves recent in-memory history as snapshot data.

        WMOM-20260505-01: 加 dedupe + cooldown — 同 turbine 同 event_class 在
        SNAPSHOT_DEDUPE_COOLDOWN_S 秒內重新 trigger 時，僅延長現有 active window 結束時間，
        ★ 不重新 retroactive write 10 分鐘 history（這是失控的主因），
        ★ 沿用既有 event_ref（保持 grouping，避免 distinct event_ref 暴增）。
        """
        if self._replaying():
            return  # 還原存檔後的重跑段：不再擷取快照

        now = self._snapshot_clock()
        event_class = self._extract_event_class(event_ref)

        last = self._snapshot_last_class.get(turbine_id)
        in_cooldown = (
            last is not None
            and last[0] == event_class
            and (now - last[1]) < self.SNAPSHOT_DEDUPE_COOLDOWN_S
        )

        if in_cooldown:
            # 同類事件在 cooldown 內：只延長 active window，不動 event_ref，不 retroactive。
            # ★ 不更新 _snapshot_last_class — cooldown 從「第一次同類 trigger」起算，
            # 而非「最近一次刷新」。否則 flapping 持續超過 cooldown 期間時，
            # cooldown 永遠不會過期，與 design intent（同類 N 分鐘合併）矛盾。
            self._snapshot_active[turbine_id] = now + self.SNAPSHOT_WINDOW_S
            return

        # 新事件 / 不同類 / cooldown 過期：完整啟動 snapshot capture
        self._snapshot_active[turbine_id] = now + self.SNAPSHOT_WINDOW_S
        self._snapshot_event_ref[turbine_id] = event_ref
        self._snapshot_last_class[turbine_id] = (event_class, now)

        # Retroactively save recent history from in-memory buffer（去重段不補存：伺服器被強制關閉前已經存過）
        if self.simulator and not self._deduping():
            recent = self.simulator.get_history(turbine_id, limit=self.SNAPSHOT_WINDOW_S)
            if recent:
                self.storage.store_snapshots(recent, event_ref, self._session_id)

    def _on_opc_data(self, readings: List[Dict]):
        """Callback from OPC adapter — uses same throttled write."""
        now = _time.time()
        if now - self._last_write_time >= self.WRITE_INTERVAL_S:
            self._last_write_time = now
            self.storage.store_readings(readings, self._session_id)
            self._remember_stored(readings)

    def stop(self):
        """Stop the active data source, end the current session, and halt maintenance."""
        with self._lifecycle_lock:
            self._stop_maintenance()
            if self.simulator and self.simulator.is_running:
                self.simulator.stop()
                if self.checkpoint_enabled and self._source_kind == "simulation":
                    # Live 迴圈已停：把最後的狀態存下來，下次啟動從這裡接著跑
                    try:
                        self._write_live_checkpoint(self.simulator.checkpoint_state())
                    except Exception as exc:  # noqa: BLE001  存檔失敗不該擋住停止
                        print(f"[DataBroker] 停止時存檔失敗：{exc}")
            if self._opc_adapter is not None:
                # Must-fix（WMOM-20260720-04 (1)）：切走 live 前若不停 OPC 輪詢 thread，
                # 它會是孤兒繼續跑，且在下一個 session（新 self._session_id）繼續寫入
                # storage——讓 #144 confirm 文案「會中斷現場連線」只成立一半。
                self._opc_adapter.stop()
                self._opc_adapter = None
            if self._session_id is not None:
                self.storage.end_session(self._session_id)
                self._session_id = None
            self._last_stored_live = {}
            self._last_write_slot = None
            self._replay_until = None
            self._dedupe_until = None
            self._source_active = False
            self._source_kind = None

    def switch_mode(self, config: DataSourceConfig,
                    sim_config: Optional[SimulationConfig] = None,
                    run_loop: bool = True, fresh: bool = False) -> None:
        """Switch between simulation and OPC data source modes.

        ``run_loop`` 傳給 ``start``（SIMULATION 時：True＝即時模擬自由跑、False＝產生情境不自由跑）。
        """
        with self._lifecycle_lock:
            self.stop()
            self.mode = config.mode
            self.start(config, sim_config, run_loop=run_loop, fresh=fresh)

    # ── Background maintenance ──

    def _start_maintenance(self) -> None:
        """Start background thread for downsampling and cleanup."""
        if self._maintenance_running:
            return
        self._maintenance_running = True
        self._maintenance_wake.clear()  # 重入啟動：清掉上次 stop 設的喚醒旗標
        self._maintenance_thread = threading.Thread(
            target=self._maintenance_loop, daemon=True, name="storage-maintenance"
        )
        self._maintenance_thread.start()

    def _stop_maintenance(self) -> None:
        self._maintenance_running = False
        self._maintenance_wake.set()  # 立刻喚醒睡眠中的 thread，讓 join 幾乎瞬間完成（非卡滿 5 秒）
        if self._maintenance_thread:
            self._maintenance_thread.join(timeout=5)
            self._maintenance_thread = None

    def _maintenance_loop(self) -> None:
        """Run downsampling every 5 minutes, cleanup every hour."""
        last_cleanup = 0
        while self._maintenance_running:
            # 可中斷睡眠：wait 回傳 True＝被 stop 喚醒（提早結束）；False＝睡滿 300 秒（做維護）。
            # 取代原本的 time.sleep(300)——那會讓 stop() 一律卡到 join timeout（5 秒）才回。
            if self._maintenance_wake.wait(300):
                break
            if not self._maintenance_running:
                break
            try:
                self.storage.run_downsampling()
                now = _time.time()
                if now - last_cleanup > 3600:  # hourly
                    self.run_retention()
                    last_cleanup = now
            except Exception as e:
                print(f"[DataBroker] Maintenance error: {e}")

    @property
    def om_loop(self) -> 'OmLoop':
        """運維閉環（``server/om_loop.py``）；預設關，伺服器依 ``WMOM_OM_LOOP`` 開。"""
        if self._om_loop is None:
            from server.om_loop import OmLoop
            self._om_loop = OmLoop(self)
        return self._om_loop

    @property
    def fault_records(self):  # noqa: ANN201  回傳型別在 server.fault_record，這裡不在模組層 import
        """不對外的故障紀錄（``server/fault_record.py``，WMOM-20261125-06-c）。"""
        recorder = getattr(self, "_fault_recorder", None)
        if recorder is None:
            from server.fault_record import FaultRecorder
            recorder = self._fault_recorder = FaultRecorder(self)
        return recorder

    # ── 故障產生器與模擬維修班的設定（WMOM-20261125-06）──────────────────

    SETTING_FAULT_GENERATOR = "fault_generator"
    SETTING_CREW = "crew"

    def apply_live_settings(self) -> None:
        """把存在風場 DB 的設定套到即時模擬；沒存過就用啟動時的預設（``default_live_settings``）。"""
        from simulator.fault_generator import FaultGeneratorConfig

        defaults = getattr(self, "default_live_settings", {})
        simulator = self.simulator
        if simulator is None:
            return
        try:
            saved = self.storage.get_setting(self.SETTING_FAULT_GENERATOR)
            simulator.fault_generator.configure(
                FaultGeneratorConfig.from_dict(saved if saved is not None else defaults.get("fault_generator", {})))
        except Exception as exc:  # noqa: BLE001  設定壞了就關著，不讓即時模擬起不來
            print(f"[DataBroker] 故障產生器的設定讀不出來，先關著：{exc}")
            simulator.fault_generator.configure(FaultGeneratorConfig())
        loop = self._om_loop_if_enabled()
        if loop is None:
            return
        from server.crew import CrewConfig

        try:
            saved = self.storage.get_setting(self.SETTING_CREW)
            loop.crew.configure(CrewConfig.from_dict(saved if saved is not None else defaults.get("crew", {})))
        except Exception as exc:  # noqa: BLE001
            print(f"[DataBroker] 模擬維修班的設定讀不出來，先關著：{exc}")
            loop.crew.configure(CrewConfig())

    def _recording_faults(self) -> bool:
        """現在要不要記故障紀錄：只記即時模擬，重啟後重跑的那幾步不記。"""
        simulator = self.simulator
        # live_clock() 在批次期間是 None：批次情境不記（那邊的答案是 scenario_ground_truth）
        return (simulator is not None and self.live_clock() is not None
                and not self._replaying() and not self._deduping())

    def _om_loop_if_enabled(self) -> Optional['OmLoop']:
        """閉環有開才回傳（熱路徑用：沒開就不載入工單模組）。"""
        loop = getattr(self, "_om_loop", None)  # 以 object.__new__ 建的測試替身沒有這個屬性
        return loop if loop is not None and loop.enabled else None

    @property
    def live_archive(self) -> LiveArchive:
        """目前這座風場的 Live 讀值歸檔（風場 DB 旁邊的 ``live_archive/``）。"""
        return LiveArchive.for_storage(self.storage)

    @property
    def live_history(self) -> LiveHistory:
        """目前這座風場的 Live 讀值（歸檔＋SQLite），依寫入順序查詢。"""
        return LiveHistory(self.storage, self.live_archive)

    @property
    def raw_retention_days(self) -> int:
        """原始讀值總共留幾天（含歸檔）。"""
        return max(self.archive_days, self.raw_hot_days) if self.archive_days > 0 else self.raw_hot_days

    def _storage_data_clock(self, storage: Storage) -> Optional[datetime]:
        """一座風場的資料時鐘：各機組最近寫入的 Live 讀值時間裡最晚的那個；沒有 Live 讀值時為 None。"""
        stamps = [storage.last_live_reading_timestamp(tid, max_sessions=self._CLOCK_LOOKBACK_SESSIONS)
                  for tid in storage.reading_turbine_ids()]
        return max((parse_iso(ts) for ts in stamps if ts), default=None)

    def _retention_clock(self, storage: Storage) -> Optional[datetime]:
        """保留期用的「現在」：即時模擬在跑時是它的模擬時鐘，否則是 storage 裡的資料時鐘。

        即時模擬在跑時不看 storage 裡最後寫入的那一列：別的來源可能寫進時間在未來的列（例：沒有命名的批次），
        拿它當現在的話，還沒過完的日子會被當成過完、半年的日檔會被當成過期刪掉。
        """
        live = self.live_clock() if storage is self.storage else None
        return live if live is not None else self._storage_data_clock(storage)

    def run_retention(self) -> Dict[str, object]:
        """保留期的例行工作：把過完的日子歸檔、清掉 SQLite 裡已歸檔又超過熱資料天數的讀值、刪最舊的日檔。

        maintenance 執行緒每小時呼叫一次；管理端也可以手動觸發（``POST /api/config/storage/maintenance``）。
        同一時間只會有一方在跑。``archive_days`` ≤ 0 時不歸檔，照舊只留 ``raw_hot_days`` 天。保留期一律看
        資料自己的時間，不看實際時間：時間倍率大於 1 之後模擬時鐘跑在實際時間前面。

        歸檔那一段出任何錯（索引讀不出來、磁碟滿）都只記下來：沒有確定進日檔的讀值一筆都不刪，其他表的清理照做。

        Returns:
            ``{"archived": [...日期], "pruned": [...日期], "raw_delete_before": str | None,
            "cleanup": {...}, "error": str（歸檔出錯時才有）}``。
        """
        with self._retention_lock:
            return self._run_retention()

    def _run_retention(self) -> Dict[str, object]:
        storage = self.storage
        result: Dict[str, object] = {"archived": [], "pruned": [], "raw_delete_before": None}
        if self.archive_days <= 0:
            result["cleanup"] = storage.run_cleanup(
                raw_retention_days=self.raw_hot_days,
                agg_1m_retention_days=self.AGG_1M_RETENTION_DAYS,
                snapshots_retention_days=self.SNAPSHOTS_RETENTION_DAYS,
            )
            return result
        deleted = 0
        try:
            clock = self._retention_clock(storage)
            if clock is not None:
                archive = LiveArchive.for_storage(storage)
                try:
                    result["archived"] = [d.day for d in archive.sync(storage, clock)]
                except ArchiveIndexError:
                    raise
                except Exception as exc:  # noqa: BLE001  這次沒歸檔完：已經確定在日檔裡的照常清，其餘下次再試
                    result["error"] = repr(exc)
                    print(f"[DataBroker] Live 讀值歸檔失敗：{exc!r}")
                state = archive.state()
                if state.archived_through:
                    # 只刪「已經在日檔裡」而且「超過熱資料天數」的；先把界線記進索引（查詢改從歸檔拿這一段）再刪
                    delete_before = min(iso_utc(clock - timedelta(days=self.raw_hot_days)), state.archived_through)
                    ranges = archive.delete_ranges(state, delete_before)
                    archive.mark_hot_from(delete_before)
                    result["raw_delete_before"] = delete_before
                    deleted += storage.delete_archived_live_readings(ranges)
                result["pruned"] = archive.prune(self.raw_retention_days, clock.date())
                # 超過總保留期的 Live 讀值一律刪（對應的日檔也刪了）：含界線之前才補寫進來、沒進歸檔的列
                expired = day_start(clock.date() - timedelta(days=self.raw_retention_days))
                deleted += storage.delete_live_readings_before(iso_utc(expired))
        except Exception as exc:  # noqa: BLE001  歸檔那一段出錯不擋其他表的清理
            result["error"] = repr(exc)
            print(f"[DataBroker] 保留期的例行工作沒有做完：{exc!r}")
        cleanup = storage.run_cleanup(
            agg_1m_retention_days=self.AGG_1M_RETENTION_DAYS,
            snapshots_retention_days=self.SNAPSHOTS_RETENTION_DAYS,
            raw_tiered=True,
        )
        cleanup["deleted_raw"] = deleted
        result["cleanup"] = cleanup
        return result

    def get_all_turbines(self) -> List[TurbineReading]:
        """Return current readings for all turbines, sorted by turbine ID."""
        if self.mode == DataSourceMode.SIMULATION and self.simulator:
            current = self.simulator.get_current_data()
            fault_status = self.simulator.fault_engine.get_fault_status()
            result = []
            for tid, output in current.items():
                # 比照 get_turbine() 的 `if output:` 防線跳過空 output。engine 會替每台機組
                # 先佔位 latest_data[tid]={}；scenario 模式（run_loop=False，DEC-20260720-01
                # PR B）下 simulator 已建但**尚未跑過任何 step**，第一次成功 generate_bulk 前
                # 這些佔位會持續是空 dict。少了這道防線時 `_sim_output_to_reading({})` 會把每台
                # 機組的 turbine_id 都 fallback 成常數 'WT001'，回傳 N 筆重複假資料（餵給
                # /api/turbines、farm-status、WS 廣播）。run_loop=True 下此空窗僅毫秒級、過去無害，
                # scenario 讓它變成長效穩態故必須擋。
                if not output:
                    continue
                hist = self.simulator.get_history(tid, limit=30)
                tid_faults = [f for f in fault_status if f['turbine_id'] == tid]
                result.append(_sim_output_to_reading(output, hist, tid_faults or None))
            return sorted(result, key=lambda r: r.turbineId)
        return []

    def get_turbine(self, turbine_id: str) -> Optional[TurbineReading]:
        """Return the current reading for a single turbine, or None if not found."""
        if self.mode == DataSourceMode.SIMULATION and self.simulator:
            output = self.simulator.get_turbine_data(turbine_id)
            if output:
                hist = self.simulator.get_history(turbine_id, limit=30)
                fault_status = self.simulator.fault_engine.get_fault_status()
                tid_faults = [f for f in fault_status if f['turbine_id'] == turbine_id]
                return _sim_output_to_reading(output, hist, tid_faults or None)
        return None

    def get_history(self, turbine_id: str, start: Optional[str] = None,
                    end: Optional[str] = None, limit: int = 1000,
                    session_id: Optional[int] = None) -> List[dict]:
        """Query stored SCADA history for a turbine within an optional time range.

        給 ``session_id`` 時只回該 session 的資料（情境調閱用）。
        """
        return self.storage.query_history(turbine_id, start, end, limit,
                                          session_id=session_id)

    def get_history_events(self, turbine_id: Optional[str] = None, start: Optional[str] = None,
                           end: Optional[str] = None, limit: int = 500,
                           session_id: Optional[int] = None,
                           source: Optional[str] = None) -> List[dict]:
        """Query stored history events (faults, grid, operator actions) with optional filters.

        ``session_id`` / ``source``：只回該 session / 該來源的事件（情境調閱用，WMOM-20261021-04）。
        不指定 session 的查詢（Live 歷史頁、事件匯出）排除情境 session 的事件：情境以模擬時間寫入，
        不排除的話會混進 Live 的時間軸。
        """
        return self.storage.query_events(turbine_id, start, end, limit,
                                         session_id=session_id, source=source,
                                         exclude_scenario_sessions=session_id is None)

    def record_event(self, event_type: str, source: str, title: str,
                     turbine_id: Optional[str] = None, detail: Optional[str] = None,
                     payload: Optional[Dict] = None, timestamp: Optional[str] = None,
                     end_timestamp: Optional[str] = None, session_id: Optional[int] = None):
        """Persist a history event (fault, grid change, operator action, etc.) to storage.

        Args:
            timestamp: 事件發生時刻（ISO）。批次生成的排定故障須傳「模擬時間」而非
                wall-clock——否則事件標記會落在真實時間、與資料的模擬時間窗對不上
                （WMOM-20260718-03）。預設 None → Live 的事件用即時模擬的時鐘；即時模擬沒在跑時
                由 storage 落地為現在時刻（UTC）。
            session_id: 事件所屬 session；None＝目前的 Live session（WMOM-20261021-04）。情境生成
                要傳情境自己的 session id。
        """
        if session_id is None and self._replaying():
            return  # 還原存檔後的重跑段：這些事件重啟前已經記過
        if session_id is None and source in self._OPERATOR_EVENT_SOURCES and self.simulator is not None:
            # 操作員動過風場：盡快存檔，伺服器被強制關閉時重啟還原的狀態不會少掉這個動作
            self.simulator.request_checkpoint()
        if timestamp is None and session_id is None:
            # Live 的事件跟即時模擬的時鐘：時間倍率大於 1 之後模擬時鐘跑在實際時間前面，用實際時間的話
            # 事件會和讀值的時間對不上（WMOM-20261125-03-a）
            clock = self.live_clock()
            if clock is not None:
                timestamp = iso_utc(clock)
        if (session_id is None and timestamp is not None and self._deduping()
                and self.storage.live_event_exists(timestamp, turbine_id, source, event_type, title)):
            return  # 伺服器被強制關閉前已經記過同一筆
        self.storage.record_event(
            event_type=event_type,
            source=source,
            title=title,
            turbine_id=turbine_id,
            detail=detail,
            payload=payload,
            timestamp=timestamp,
            end_timestamp=end_timestamp,
            session_id=session_id if session_id is not None else self._session_id,
        )

    def record_bulk_events(self, events: List[BulkEvent], session_id: Optional[int]) -> int:
        """把批次生成的可觀測事件寫進 ``history_events``（一次 commit，WMOM-20261021-04）。

        格式與 Live 路徑相同（PLC 事件見 ``_plc_event_fields``、狀態轉換見
        ``_state_transition_fields``），時間戳為事件的模擬時刻；不觸發 1 s 快照（快照是 Live 專用的
        wall-clock 機制）。

        Args:
            events: ``generate_bulk`` 的 ``on_events`` 收到的事件。
            session_id: 事件所屬 session（情境 session 或目前的 Live session）。

        Returns:
            寫入筆數。
        """
        rows: List[Dict] = []
        for event in events:
            if event.plc_event is not None:
                fields = self._plc_event_fields(event.turbine_id, event.plc_event)
            elif event.from_state is not None and event.to_state is not None:
                fields = self._state_transition_fields(
                    event.turbine_id, event.from_state, event.to_state, event.shutdown_cause,
                )
                if fields is None:
                    continue
            else:
                continue
            rows.append({**fields, "timestamp": iso_utc(event.timestamp), "session_id": session_id})
        return self.storage.record_events(rows)

    def close_open_events(self, event_type: str, source: Optional[str] = None,
                          turbine_id: Optional[str] = None, closed_at: Optional[str] = None):
        """Close open-ended events by setting their end timestamp.

        沒給 ``closed_at`` 時用即時模擬的時鐘（與事件的開始時間同一個時鐘）；即時模擬沒在跑時由 storage
        落地為現在時刻。還原存檔後的重跑段不關（重啟前已經關過；現在開著的可能是之後的另一筆）。
        """
        if self._replaying():
            return
        if closed_at is None:
            clock = self.live_clock()
            if clock is not None:
                closed_at = iso_utc(clock)
        self.storage.close_open_events(
            event_type=event_type,
            source=source,
            turbine_id=turbine_id,
            closed_at=closed_at,
        )

    def _detect_sim_events(self, readings: List[Dict]):
        if not self.simulator:
            return

        fault_status = self.simulator.fault_engine.get_fault_status()
        fault_by_turbine = {
            tid: [f for f in fault_status if f.get("turbine_id") == tid]
            for tid in self.simulator.turbines.keys()
        }

        for reading in readings:
            turbine_id = reading.get("turbine_id")
            if not turbine_id:
                continue

            scada = reading.get("scada", {})
            current_state = int(scada.get("WTUR_TurSt", 0) or 0)
            last_state = self._last_tur_state.get(turbine_id)
            model = self.simulator.turbines.get(turbine_id)
            control = model.get_control_status() if model else {}
            shutdown_cause = control.get("shutdown_cause")
            last_cause = self._last_shutdown_cause.get(turbine_id)

            if last_state is None:
                self._last_tur_state[turbine_id] = current_state
                self._last_shutdown_cause[turbine_id] = shutdown_cause
            elif last_state != current_state:
                self._record_state_transition_event(
                    turbine_id=turbine_id,
                    previous_state=last_state,
                    current_state=current_state,
                    shutdown_cause=shutdown_cause,
                )
                self._last_tur_state[turbine_id] = current_state
                self._last_shutdown_cause[turbine_id] = shutdown_cause
            elif shutdown_cause != last_cause:
                self._last_shutdown_cause[turbine_id] = shutdown_cause

            active_faults = fault_by_turbine.get(turbine_id, [])
            current_tripped = any(bool(f.get("tripped")) for f in active_faults)
            last_tripped = self._last_fault_trip.get(turbine_id)
            if last_tripped is None:
                self._last_fault_trip[turbine_id] = current_tripped
            elif last_tripped != current_tripped:
                if current_tripped:
                    tripped = [f for f in active_faults if f.get("tripped")]
                    tripped_faults = [f.get("scenario_id") for f in tripped]
                    trip_codes = [f.get("trip_code") for f in tripped if f.get("trip_code") is not None]
                    event_ref = f"fault_trip:{turbine_id}:{self._live_stamp()}"
                    self.record_event(
                        event_type="fault",
                        source="simulator",
                        title="Automatic fault trip",
                        turbine_id=turbine_id,
                        detail=(
                            f"Trip triggered by {', '.join(tripped_faults) if tripped_faults else 'active fault'}"
                            + (f" (PLC event {', '.join(str(c) for c in trip_codes)})" if trip_codes else "")
                        ),
                        payload={"turbineId": turbine_id, "faults": tripped_faults, "tripCodes": trip_codes},
                    )
                    # Trigger high-frequency snapshot capture
                    self._trigger_snapshot(turbine_id, event_ref)
                else:
                    self.record_event(
                        event_type="fault",
                        source="simulator",
                        title="Fault trip cleared in simulator",
                        turbine_id=turbine_id,
                        detail=f"{turbine_id} no longer has a tripped fault state",
                        payload={"turbineId": turbine_id},
                    )
                self._last_fault_trip[turbine_id] = current_tripped

            # ── PLC events (real Z72 event codes, raised from the measured process
            # values by the turbine's protection layer — WMOM-20261021-03-b). They carry
            # no fault ground truth: observable events only.
            if model is not None:
                for plc_event in model.plc.drain_events():
                    self._record_plc_event(turbine_id, plc_event,
                                           self._plc_event_timestamp(reading, model, plc_event))

            # ── Fault lifecycle: track start/end + phase transitions ──
            current_fault_keys = set()
            current_phases: Dict[str, str] = {}
            for fault in active_faults:
                sid = str(fault.get("scenario_id") or "")
                phase = str(fault.get("phase") or "")
                current_fault_keys.add(sid)
                current_phases[sid] = phase

            prev_keys = self._active_fault_keys.get(turbine_id, set())
            prev_phases = self._last_fault_phases.get(turbine_id, {})

            # New faults → lifecycle start event (open-ended)
            for sid in current_fault_keys - prev_keys:
                if self._recording_faults():   # 不對外的故障紀錄（WMOM-20261125-06-c）
                    made = {(g.turbine_id, g.scenario_id): g for g in self.simulator.last_generated}
                    generated = made.get((turbine_id, sid))
                    self.fault_records.on_fault_started(
                        turbine_id, sid, "generator" if generated is not None else "manual",
                        generated.severity_rate if generated is not None else None)
                phase = current_phases.get(sid, "incipient")
                sev = next((f.get("severity", 0) for f in active_faults
                            if f.get("scenario_id") == sid), 0)
                self.record_event(
                    event_type="fault_lifecycle",
                    source="simulator",
                    title=f"Fault started: {sid}",
                    turbine_id=turbine_id,
                    detail=f"{sid} entered {phase} phase on {turbine_id}",
                    payload={
                        "turbineId": turbine_id,
                        "scenarioId": sid,
                        "phase": phase,
                        "severity": sev,
                        "lifecycle": "start",
                    },
                )

            # Removed faults → close lifecycle event
            for sid in prev_keys - current_fault_keys:
                if self._recording_faults():
                    self.fault_records.on_fault_cleared(turbine_id, sid)
                self.close_open_events(
                    event_type="fault_lifecycle",
                    source="simulator",
                    turbine_id=turbine_id,
                )
                self.record_event(
                    event_type="fault_lifecycle",
                    source="simulator",
                    title=f"Fault ended: {sid}",
                    turbine_id=turbine_id,
                    detail=f"{sid} cleared on {turbine_id}",
                    payload={
                        "turbineId": turbine_id,
                        "scenarioId": sid,
                        "lifecycle": "end",
                    },
                )

            # Phase transitions for ongoing faults
            for sid in current_fault_keys & prev_keys:
                old_phase = prev_phases.get(sid)
                new_phase = current_phases.get(sid)
                if old_phase and new_phase and old_phase != new_phase:
                    sev = next((f.get("severity", 0) for f in active_faults
                                if f.get("scenario_id") == sid), 0)
                    self.record_event(
                        event_type="fault_lifecycle",
                        source="simulator",
                        title=f"Fault phase change: {sid}",
                        turbine_id=turbine_id,
                        detail=f"{sid} transitioned from {old_phase} to {new_phase}",
                        payload={
                            "turbineId": turbine_id,
                            "scenarioId": sid,
                            "fromPhase": old_phase,
                            "toPhase": new_phase,
                            "severity": sev,
                            "lifecycle": "phase_change",
                        },
                    )

            self._active_fault_keys[turbine_id] = current_fault_keys
            self._last_fault_phases[turbine_id] = current_phases

            # ── Fatigue alarm level changes ──
            alm_twr = int(scada.get("WLOD_AlmTwr", 0) or 0)
            alm_bld = int(scada.get("WLOD_AlmBld", 0) or 0)
            prev_alm = self._last_fatigue_alarm.get(turbine_id)
            if prev_alm is None:
                self._last_fatigue_alarm[turbine_id] = (alm_twr, alm_bld)
            else:
                prev_twr, prev_bld = prev_alm
                alarm_names = {0: "正常", 1: "注意", 2: "警告", 3: "危險", 4: "停機"}
                for label, prev_lvl, cur_lvl in [
                    ("塔架", prev_twr, alm_twr),
                    ("葉片", prev_bld, alm_bld),
                ]:
                    if cur_lvl != prev_lvl and cur_lvl > 0:
                        direction = "升級" if cur_lvl > prev_lvl else "降級"
                        rul = scada.get("WLOD_RulHours", -1)
                        self.record_event(
                            event_type="fatigue",
                            source="simulator",
                            title=f"疲勞警報{direction}：{label} Lv{cur_lvl} ({alarm_names.get(cur_lvl, '')})",
                            turbine_id=turbine_id,
                            detail=f"{turbine_id} {label}疲勞警報從 Lv{prev_lvl} {direction}至 Lv{cur_lvl}，RUL={rul}h",
                            payload={
                                "turbineId": turbine_id,
                                "component": label,
                                "fromLevel": prev_lvl,
                                "toLevel": cur_lvl,
                                "levelName": alarm_names.get(cur_lvl, ""),
                                "rulHours": rul,
                            },
                        )
                self._last_fatigue_alarm[turbine_id] = (alm_twr, alm_bld)

    _PLC_EVENT_TITLES = {
        "alarm_raised": "Alarm",
        "alarm_cleared": "Alarm cleared",
        "trip": "Trip",
        "trip_cleared": "Trip cleared",
        "restart_blocked": "Restart blocked",
        "operator_reset": "Operator reset",
        "info": "Info",
    }

    @staticmethod
    def _plc_event_timestamp(reading: Dict, model: TurbinePhysicsModel, event: PlcEvent) -> Optional[str]:
        """PLC 事件的發生時刻＝本筆 reading 的模擬時間往回推（加速模式一個 tick 跑多步）。

        Args:
            reading: 本步該機組的 reading（含 ISO ``timestamp``）。
            model: 該機組物理模型（``_sim_time`` 與事件 ``sim_time`` 同一時間軸）。
            event: PLC 事件。

        Returns:
            ISO 時間字串；reading 沒有時間戳時回 None（storage 以現在時刻落地）。
        """
        ts = reading.get("timestamp")
        if not isinstance(ts, str):
            return None
        try:
            reading_time = parse_iso(ts)
        except ValueError:
            return None
        lag_s = max(0.0, float(model._sim_time) - event.sim_time)
        return iso_utc(reading_time - timedelta(seconds=lag_s))

    def _record_plc_event(self, turbine_id: str, event: PlcEvent, timestamp: Optional[str] = None) -> None:
        """把一筆 PLC 事件寫進 history_events（event_type="fault"，source="plc"）。

        Args:
            turbine_id: 機組 ID。
            event: PLC 事件。
            timestamp: 事件發生時刻（ISO，模擬時間軸）；None＝現在時刻。
        """
        self.record_event(**self._plc_event_fields(turbine_id, event), timestamp=timestamp)
        if self._recording_faults():
            self.fault_records.on_plc_event(turbine_id, event, timestamp)   # 不對外的故障紀錄
        loop = self._om_loop_if_enabled()
        if loop is not None and not self._replaying():
            loop.on_plc_event(turbine_id, event)  # 跳機開單（WMOM-20261125-04）；重跑段不再開

    @classmethod
    def _plc_event_fields(cls, turbine_id: str, event: PlcEvent) -> Dict:
        """PLC 事件 → ``record_event`` 欄位（Live 與批次路徑共用，WMOM-20261021-04）。

        Args:
            turbine_id: 機組 ID。
            event: PLC 事件。

        Returns:
            ``event_type`` / ``source`` / ``title`` / ``turbine_id`` / ``detail`` / ``payload``。
        """
        label = cls._PLC_EVENT_TITLES.get(event.kind, event.kind)
        detail = f"{event.level} {event.code:03d} {event.text}"
        if event.value is not None and event.setpoint is not None:
            detail += f" (value {event.value} / setpoint {event.setpoint})"
        return dict(
            event_type="fault",
            source="plc",
            title=f"{label}: {event.event_id} {event.text}",
            turbine_id=turbine_id,
            detail=detail,
            payload={
                "turbineId": turbine_id,
                "kind": event.kind,
                "code": event.code,
                "level": event.level,
                "text": event.text,
                "plcTag": event.plc_tag,
                "eventId": event.event_id,
                "value": event.value,
                "setpoint": event.setpoint,
                "origin": event.source,
            },
        )

    def _record_state_transition_event(self, turbine_id: str, previous_state: int,
                                       current_state: int, shutdown_cause: Optional[str]):
        fields = self._state_transition_fields(turbine_id, previous_state, current_state, shutdown_cause)
        if fields is None:
            return
        # Trigger snapshot for emergency stops and fault-caused stops（Live 專用的 wall-clock 機制）
        if current_state == 7 or (current_state == 9 and isinstance(shutdown_cause, str) and
                                  ("fault" in shutdown_cause or "plc:" in shutdown_cause
                                   or "grid" in shutdown_cause or "emergency" in shutdown_cause)):
            event_ref = f"stop:{turbine_id}:{current_state}:{self._live_stamp()}"
            self._trigger_snapshot(turbine_id, event_ref)
        self.record_event(**fields)

    @classmethod
    def _state_transition_fields(cls, turbine_id: str, previous_state: int,
                                 current_state: int, shutdown_cause: Optional[str]) -> Optional[Dict]:
        """運轉狀態轉換 → ``record_event`` 欄位（Live 與批次路徑共用，WMOM-20261021-04）。

        Args:
            turbine_id: 機組 ID。
            previous_state: 轉換前 ``WTUR_TurSt``。
            current_state: 轉換後 ``WTUR_TurSt``。
            shutdown_cause: 機組回報的停機原因。

        Returns:
            ``record_event`` 欄位；不記錄的狀態回 None。
        """
        state_name = cls._state_name(current_state)
        detail = f"{turbine_id} moved from {cls._state_name(previous_state)} to {state_name}"
        payload = {
            "turbineId": turbine_id,
            "fromState": previous_state,
            "toState": current_state,
            "shutdownCause": shutdown_cause,
        }

        if current_state == 6:
            return dict(event_type="state", source="simulator", title="Entered production",
                        turbine_id=turbine_id, detail=detail, payload=payload)

        if current_state in (7, 9):
            event_type = "state"
            title = "Turbine stopping"
            if shutdown_cause in ("grid_trip", "grid_protection"):
                event_type = "grid"
                title = "Automatic grid protection stop"
            elif isinstance(shutdown_cause, str) and shutdown_cause.startswith(("fault:", "plc:")):
                # "plc:<碼>"：PLC 保護層依訊號判定的跳機（WMOM-20261021-03-b）
                event_type = "fault"
                prefix, ident = shutdown_cause.split(":", 1)
                title = f"Automatic fault stop: {'PLC event ' if prefix == 'plc' else ''}{ident}"
            elif shutdown_cause in ("operator", "operator_emergency", "service"):
                event_type = "operator"
                title = "Operator-driven stop"
            return dict(event_type=event_type, source="simulator", title=title, turbine_id=turbine_id,
                        detail=f"{detail} ({shutdown_cause or 'unknown cause'})", payload=payload)

        if current_state in (4, 5, 8):
            return dict(event_type="state", source="simulator", title="Startup / restart transition",
                        turbine_id=turbine_id, detail=detail, payload=payload)

        if current_state in (1, 2, 3):
            return dict(event_type="state", source="simulator", title="Returned to idle state",
                        turbine_id=turbine_id, detail=detail, payload=payload)
        return None

    @staticmethod
    def _state_name(state: int) -> str:
        return {
            1: "Shutdown",
            2: "Standby",
            3: "Wait Restart",
            4: "Pre-Production",
            5: "Synchronization",
            6: "Production",
            7: "Emergency Stop",
            8: "Restart",
            9: "Normal Stop",
        }.get(state, f"State {state}")

    def get_farm_status(self) -> FarmStatus:
        """Aggregate current turbine states into a farm-level status summary."""
        turbines = self.get_all_turbines()
        now = utc_now()
        if not turbines:
            return FarmStatus(
                totalTurbines=0, operatingCount=0, idleCount=0,
                faultCount=0, offlineCount=0, totalPowerMW=0,
                avgWindSpeed=0, timestamp=now,
            )
        return FarmStatus(
            totalTurbines=len(turbines),
            operatingCount=sum(1 for t in turbines if t.status == TurbineStatus.OPERATING),
            idleCount=sum(1 for t in turbines if t.status == TurbineStatus.IDLE),
            faultCount=sum(1 for t in turbines if t.status == TurbineStatus.FAULT),
            offlineCount=sum(1 for t in turbines if t.status == TurbineStatus.OFFLINE),
            totalPowerMW=round(sum(t.powerOutput for t in turbines), 2),
            avgWindSpeed=round(sum(t.windSpeed for t in turbines) / len(turbines), 2),
            timestamp=now,
        )

    @property
    def turbine_ids(self) -> List[str]:
        """List of active turbine IDs from the running simulator."""
        if self.simulator:
            return self.simulator.turbine_ids
        return []
