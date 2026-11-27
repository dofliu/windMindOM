from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict


class TurbineStatus(str, Enum):
    OPERATING = "OPERATING"
    IDLE = "IDLE"
    FAULT = "FAULT"
    OFFLINE = "OFFLINE"


class DataSourceMode(str, Enum):
    SIMULATION = "simulation"
    OPC_DA = "opc_da"


class TurbineReading(BaseModel):
    """
    Full SCADA reading aligned to Z72 Bachmann 39 display tags.
    Backward-compatible: original fields preserved, new fields use Optional.
    """
    turbineId: str
    name: str
    timestamp: datetime
    status: TurbineStatus
    turState: int = 6                # Bachmann TurState 1-9

    # ── Original fields (backward-compatible) ──
    windSpeed: float = 0.0           # m/s  (WMET_WSpeedNac)
    powerOutput: float = 0.0         # MW   (WTUR_TotPwrAt / 1000)
    rotorSpeed: float = 0.0          # RPM  (WROT_RotSpd)
    bladeAngle: float = 0.0          # deg  (WROT_PtAngValBl1)
    temperature: float = 0.0         # °C   (WGEN_GnStaTmp1)
    vibration: float = 0.0           # mm/s (WNAC_VibMsNacXDir)
    voltage: float = 0.0             # V    (WGEN_GnVtgMs)
    current: float = 0.0             # A    (WGEN_GnCurMs)
    yawAngle: float = 0.0            # deg  (derived from yaw system)
    gearboxTemp: float = 0.0         # °C   (WNAC_NacTmp as proxy)
    frequency: Optional[float] = None       # Hz  (WCNV_CnvGnFrq)
    hydraulicPressure: Optional[float] = None  # bar (WYAW_YwBrkHyPrs)
    history: Optional[List[dict]] = None    # [{time, power}] for frontend chart

    # ── WGEN — Generator (expanded) ──
    genPower: Optional[float] = None         # kW  (WGEN_GnPwrMs)
    genSpeed: Optional[float] = None         # RPM (WGEN_GnSpd)
    genStatorTemp1: Optional[float] = None   # °C  (WGEN_GnStaTmp1)
    genAirTemp1: Optional[float] = None      # °C  (WGEN_GnAirTmp1)
    genBearingTemp1: Optional[float] = None  # °C  (WGEN_GnBrgTmp1)

    # ── WROT — Rotor / Pitch (expanded) ──
    bladeAngle1: Optional[float] = None      # deg (WROT_PtAngValBl1)
    bladeAngle2: Optional[float] = None      # deg (WROT_PtAngValBl2)
    bladeAngle3: Optional[float] = None      # deg (WROT_PtAngValBl3)
    rotorTemp: Optional[float] = None        # °C  (WROT_RotTmp)
    hubCabinetTemp: Optional[float] = None   # °C  (WROT_RotCabTmp)
    rotorLocked: Optional[int] = None        # 0/1 (WROT_RotLckd)
    brakeActive: Optional[int] = None        # 0/1 (WROT_SrvcBrkAct)

    # ── WCNV — Converter ──
    cnvCabinetTemp: Optional[float] = None   # °C  (WCNV_CnvCabinTmp)
    cnvDcVoltage: Optional[float] = None     # V   (WCNV_CnvDClVtg)
    cnvGridPower: Optional[float] = None     # kW  (WCNV_CnvGdPwrAt)
    cnvGenFreq: Optional[float] = None       # Hz  (WCNV_CnvGnFrq)
    cnvGenPower: Optional[float] = None      # kW  (WCNV_CnvGnPwr)
    igctWaterCond: Optional[float] = None    # µS/cm (WCNV_IGCTWtrCond，冷卻水導電度)
    igctWaterPres1: Optional[float] = None   # bar (WCNV_IGCTWtrPres1)
    igctWaterPres2: Optional[float] = None   # bar (WCNV_IGCTWtrPres2)
    igctWaterTemp: Optional[float] = None    # °C  (WCNV_IGCTWtrTmp)

    # ── WCNV — Electrical Response ──
    reactivePower: Optional[float] = None    # kvar (WCNV_ReactPwr)
    powerFactor: Optional[float] = None      #      (WCNV_PwrFactor)
    apparentPower: Optional[float] = None    # kVA  (WCNV_AppPwr)
    freqWattDerate: Optional[float] = None   #      (WCNV_FreqWattDerate)
    inertiaPower: Optional[float] = None     # kW   (WCNV_InertiaPwr)
    converterMode: Optional[int] = None      #      (WCNV_CnvMode)
    rideThroughBand: Optional[int] = None    #      (WCNV_RtBand)

    # ── WVIB — Vibration Spectral Bands ──
    vibBand1pX: Optional[float] = None       # mm/s (WVIB_Band1pX)
    vibBand1pY: Optional[float] = None       # mm/s (WVIB_Band1pY)
    vibBand3pX: Optional[float] = None       # mm/s (WVIB_Band3pX)
    vibBand3pY: Optional[float] = None       # mm/s (WVIB_Band3pY)
    vibBandGearX: Optional[float] = None     # mm/s (WVIB_BandGearX)
    vibBandGearY: Optional[float] = None     # mm/s (WVIB_BandGearY)
    vibBandHfX: Optional[float] = None       # mm/s (WVIB_BandHfX)
    vibBandHfY: Optional[float] = None       # mm/s (WVIB_BandHfY)
    vibBandBbX: Optional[float] = None       # mm/s (WVIB_BandBbX)
    vibBandBbY: Optional[float] = None       # mm/s (WVIB_BandBbY)
    vibCrestFactor: Optional[float] = None   #      (WVIB_CrestFactor)
    vibKurtosis: Optional[float] = None      #      (WVIB_Kurtosis)

    # ── WVIB — Vibration Alarm Thresholds ──
    vibAlarm1p: Optional[int] = None         #      (WVIB_Alarm1p) 0/1/2
    vibAlarm3p: Optional[int] = None         #      (WVIB_Alarm3p)
    vibAlarmGear: Optional[int] = None       #      (WVIB_AlarmGear)
    vibAlarmHf: Optional[int] = None         #      (WVIB_AlarmHf)
    vibAlarmBb: Optional[int] = None         #      (WVIB_AlarmBb)
    vibAlarmOverall: Optional[int] = None    #      (WVIB_AlarmOverall)
    vibThresh1pWarn: Optional[float] = None  # mm/s (WVIB_Thresh1pWarn)
    vibThresh1pAlrm: Optional[float] = None  # mm/s (WVIB_Thresh1pAlrm)

    # ── WGDC — Transformer ──
    transformerTemp: Optional[float] = None  # °C  (WGDC_TrfCoreTmp)

    # ── WMET — Meteorological ──
    windDirection: Optional[float] = None    # deg (WMET_WDirAbs)
    outsideTemp: Optional[float] = None      # °C  (WMET_TmpOutside)

    # ── WNAC — Nacelle ──
    nacelleTemp: Optional[float] = None      # °C  (WNAC_NacTmp)
    nacelleCabTemp: Optional[float] = None   # °C  (WNAC_NacCabTmp)
    vibrationX: Optional[float] = None       # mm/s (WNAC_VibMsNacXDir)
    vibrationY: Optional[float] = None       # mm/s (WNAC_VibMsNacYDir)

    # ── WYAW — Yaw ──
    yawError: Optional[float] = None         # deg  (WYAW_YwVn1AlgnAvg5s)
    yawBrakePressure: Optional[float] = None # bar  (WYAW_YwBrkHyPrs)
    cableWindup: Optional[float] = None      # turns (WYAW_CabWup)

    # ── WLOD — Structural Load & Fatigue ──
    towerFaMoment: Optional[float] = None     # kNm (WLOD_TwrFaMom)
    towerSsMoment: Optional[float] = None     # kNm (WLOD_TwrSsMom)
    bladeFlapMoment: Optional[float] = None   # kNm (WLOD_BldFlapMom)
    bladeEdgeMoment: Optional[float] = None   # kNm (WLOD_BldEdgeMom)
    delTowerFa: Optional[float] = None        # kNm (WLOD_DelTwrFa)
    delTowerSs: Optional[float] = None        # kNm (WLOD_DelTwrSs)
    delBladeFlap: Optional[float] = None      # kNm (WLOD_DelBldFlap)
    delBladeEdge: Optional[float] = None      # kNm (WLOD_DelBldEdge)
    damageTowerFa: Optional[float] = None     #     (WLOD_DmgTwrFa)
    damageTowerSs: Optional[float] = None     #     (WLOD_DmgTwrSs)
    damageBladeFlap: Optional[float] = None   #     (WLOD_DmgBldFlap)
    damageBladeEdge: Optional[float] = None   #     (WLOD_DmgBldEdge)
    productionHours: Optional[float] = None   # h   (WLOD_ProdHours)

    # ── Fault info (from FaultEngine) ──
    activeFaults: Optional[List[dict]] = None

    # ── Raw SCADA dict (all 39 tags, for advanced views) ──
    scadaTags: Optional[Dict[str, float]] = None


class FarmStatus(BaseModel):
    totalTurbines: int
    operatingCount: int
    idleCount: int
    faultCount: int
    offlineCount: int
    totalPowerMW: float
    avgWindSpeed: float
    timestamp: datetime


class DataSourceConfig(BaseModel):
    mode: DataSourceMode
    opcServer: Optional[str] = None
    opcProgId: Optional[str] = None
    opcHost: Optional[str] = "localhost"


class SimulationConfig(BaseModel):
    turbineCount: int = 14
    baseWindSpeed: float = 10.0
    turbulenceIntensity: float = 0.1
    # timeStep 是 Live 自由跑迴圈的節奏（秒）。加上界（0, 60]：批次端點會於 finally 阻塞式 join
    # 等 Live thread 退場，其最壞等待≈一個 timeStep；無上界時一個異常大的 timeStep 會讓同步的批次
    # 端點卡住單 worker。UI 從不送此值（見 useSettings），僅直呼 API 可達，故上界不影響正常使用。
    timeStep: float = Field(1.0, gt=0, le=60)


class WindOverrideRequest(BaseModel):
    """Set manual wind conditions. null values keep auto mode."""
    windSpeed: Optional[float] = None       # m/s (None = auto)
    windDirection: Optional[float] = None   # deg (None = auto)
    ambientTemp: Optional[float] = None     # °C (None = auto)
    turbulence: Optional[float] = None      # 0.0-0.5 (None = keep current)
    profile: Optional[str] = None           # 'calm','moderate','rated','strong','storm','gusty','ramp_up','ramp_down','auto'


class WindSeriesImportRequest(BaseModel):
    """匯入一份實測風況序列（WMOM-20261125-07）。CSV 第一列是欄名。"""
    name: str = Field(min_length=1, max_length=100)
    csv: str = Field(min_length=1, max_length=40_000_000)
    columns: Optional[Dict[str, str]] = None        # 欄位對應（time / wind_speed / wind_direction / ...）
    timezone: Optional[str] = Field(default=None, max_length=64)   # 沒有時區的時間視為這個時區；預設風場時區
    heightM: Optional[float] = Field(default=None, gt=0, le=300)    # 風速的量測高度
    hubHeightM: Optional[float] = Field(default=None, gt=0, le=300)  # 預設用機組的輪轂高度
    shearExponent: float = Field(default=0.14, ge=0, le=0.6)
    maxGapMinutes: float = Field(default=180.0, gt=0, le=7 * 24 * 60)


class WindSeriesApplyRequest(BaseModel):
    """套用一份實測風況序列（WMOM-20261125-07）。"""
    alignment: str = "replay"       # replay：從現在開始播；absolute：模擬時間就是序列的時間
    atEnd: str = "loop"             # loop：從頭再播；hold：停在最後一筆；auto：回到模型的風況
    startOffsetHours: float = Field(default=0.0, ge=0)   # replay 時從序列起點之後幾小時開始播


class GridOverrideRequest(BaseModel):
    frequencyHz: Optional[float] = None
    voltageV: Optional[float] = None
    profile: Optional[str] = None  # 'nominal','low_freq','high_freq','undervoltage','overvoltage','weak_grid','recovery','auto'


class FaultInjectionRequest(BaseModel):
    scenarioId: str
    turbineId: str
    severityRate: float = 0.001   # per second
    initialSeverity: float = 0.0


class FaultClearRequest(BaseModel):
    turbineId: Optional[str] = None
    scenarioId: Optional[str] = None


class AppConfig(BaseModel):
    dataSource: DataSourceConfig
    simulation: SimulationConfig
