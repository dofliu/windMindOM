"""Z72 PLC 保護層（WMOM-20261021-03-b，EPIC-DS Phase 1b-b）。

依真實 Z72 保護設定值（``TurbineSpec``，WMOM-20261021-03-a）判定**製程值**（感測器模型之前的
物理量），送出 Z72 事件碼（``shared/data/z72_alarm_catalog.json``），並模擬 PLC 的跳機語意。

為何不用感測器模型之後的 SCADA 值：本模擬的感測器模型（雜訊、隨機漂移、卡值）是為 SCADA 趨勢
的視覺真實度調校的資料擷取瑕疵，幅度對 PLC 判定太大（例：葉片角度漂移上限 ±0.8°、卡值每機
每小時約 1.3 次，健康機組約兩天一次葉片同步 T2 誤跳）。感測器故障造成的跳機改由 Phase 4
（WMOM-20261021-08）以有標註的方式建模，避免產生沒有標準答案的誤報。

跳機語意：

- **A（警報）**：條件成立超過延時 → ``alarm_raised``；回到遲滯範圍內 → ``alarm_cleared``。不停機。
- **T1 / T2（跳機）**：條件成立超過延時 → ``trip``，T1 要求正常伺服停機、T2 要求緊急變槳停機。
  跳機鎖存到條件解除；解除時若該碼一小時內的跳機次數未超過手冊每小時上限（``max_per_hour``）
  → ``trip_cleared`` 自動解除、機組可自動重啟；超過則 ``restart_blocked``，需操作員復位
  （``operator_reset``，事件 008）。復位後條件仍成立會立即再跳。
- **物理層既有保護**（超速、LVRT / 電網保護、切出風速）停機時，依停機原因補上對應事件碼
  （``note_protection_stop``）。這類停機的重啟由物理層狀態機處理，不在此鎖存。

所有事件以 ``PlcEvent`` 暫存於有上限的佇列，由即時路徑（broker）或批次路徑以 ``drain_events``
取走；沒人取時舊事件自動丟棄，不會無限成長。
"""

from __future__ import annotations

import math
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Deque, Dict, FrozenSet, List, Mapping, Optional, Tuple

# 模擬器可單獨執行（tools/、examples/ 只把 modules/monitoring 放進 sys.path），補上 repo root
# 讓共用的 Z72 警報目錄可匯入。append 而非 insert，不遮蔽既有模組。
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.append(str(_REPO_ROOT))

from shared.alarm_codes import AlarmDef, get_alarm  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover
    from .turbine_physics import TurbineSpec

# 每碼一小時內跳機次數的統計窗（手冊「Max #/hr」）
_TRIP_WINDOW_S = 3600.0
# 風向標比對用的濾波時間常數（手冊事件 233：Filtered values (T=25s)）
_VANE_FILTER_TAU_S = 25.0
# 風向標比對的風速條件（手冊：10 min. avg. wind speed）
_WIND_AVG_TAU_S = 600.0
# 葉片差異只在穩定發電後判定：本模型各葉片對大幅變槳（啟動 30° → 工作角）的響應差異，
# 併網後 60 s 內暫態差異可達 ~6.6°；穩定發電時健康最大 ~1.3–1.9°、超過 1° 最長連續 2 s
_PITCH_SETTLE_S = 60.0
# 偏航煞車壓力只在煞車施加後判定：偏航時煞車鬆開降到 ~20 bar，結束後以 3 bar/s 回升到 210 bar
#（約 63 s），回升期間低於 180 / 150 bar 是正常行為；手冊 260 / 228 指的是煞車施加時的液壓站壓力
_YAW_BRAKE_SETTLE_S = 90.0
# 佇列上限：即時路徑每步取走；批次路徑（-04 之前）不取，舊事件自動丟棄
_EVENT_QUEUE_MAX = 512
# 物理層停機原因 → 事件碼（I 類只記事件不鎖存）
_OVERSPEED_CODES = {"overspeed_software": 351, "overspeed_hardware": 320}
_CUT_OUT_CODE = 201          # I: Windspeed too high
_CONVERTER_TRIP_REQUEST = 21  # T1: Turbine trip request from converter（伴隨 400-700 碼）
_OPERATOR_RESET_CODE = 8     # I: Operator reset
# 物理層保護停機可能補上的跳機碼（超速、ARU 欠壓 / 過壓、電網頻率、變頻器跳機要求）
PROTECTION_TRIP_CODES: Tuple[int, ...] = (351, 320, 475, 481, 482, 489, _CONVERTER_TRIP_REQUEST)
# I 類事件（切出風速）去重間隔：暴風時物理層會反覆要求停機，避免洗版
_INFO_EVENT_MIN_INTERVAL_S = 600.0


@dataclass(frozen=True)
class ProtectionRule:
    """一條訊號判定規則。同一事件碼可有多條規則（例：葉片差異的三段延時），任一成立即視為成立。

    Attributes:
        code: Z72 事件碼。
        signal: ``PlcProtection.signals`` 的鍵。
        above: True＝訊號高於設定值時成立；False＝低於設定值時成立。
        setpoint: 設定值。
        hysteresis: 解除遲滯：成立後須回到 setpoint ∓ hysteresis 之外才解除。
        delay_s: 條件須持續的秒數（0＝瞬間）。
        producing_only: 只在發電狀態判定（例：停機時冷卻泵停止，靜水壓本來就低）。
        gate: 選填，``signals`` 中的旗標鍵；旗標為 0 時不判定（例：葉片差異只在穩定發電時判定）。
    """

    code: int
    signal: str
    above: bool
    setpoint: float
    hysteresis: float
    delay_s: float = 0.0
    producing_only: bool = False
    gate: Optional[str] = None


@dataclass
class _RuleState:
    timer: float = 0.0
    on: bool = False


@dataclass
class _CodeState:
    active: bool = False
    latched: bool = False
    blocked: bool = False
    trip_times: List[float] = field(default_factory=list)


@dataclass(frozen=True)
class PlcEvent:
    """PLC 事件（給 broker / 資料包使用的可觀測事件，不含故障根因）。

    Attributes:
        sim_time: 機組模擬時間（秒，``TurbinePhysicsModel._sim_time``）。
        kind: ``alarm_raised`` / ``alarm_cleared`` / ``trip`` / ``trip_cleared`` /
            ``restart_blocked`` / ``operator_reset`` / ``info``。
        code: Z72 事件碼。
        level: A / T1 / T2 / I。
        text: PLC 顯示文字（目錄原文）。
        plc_tag: 送出此事件的 PLC tag；I 類為 None。
        event_id: HMI 事件 ID（例 ``A_262``）。
        value: 觸發當下的訊號值（物理層保護停機時為 None）。
        setpoint: 對應設定值（物理層保護停機時為 None）。
        source: ``signal``（本層判定）或 ``protection``（物理層既有保護）或 ``operator``。
    """

    sim_time: float
    kind: str
    code: int
    level: str
    text: str
    plc_tag: Optional[str]
    event_id: str
    value: Optional[float] = None
    setpoint: Optional[float] = None
    source: str = "signal"


def build_rules(spec: "TurbineSpec") -> Tuple[ProtectionRule, ...]:
    """依 ``TurbineSpec`` 建立 Z72 保護規則表。

    Args:
        spec: 機組規格（含 -03-a 的保護設定值）。

    Returns:
        規則 tuple。
    """
    t_delay = 5.0   # 溫度跳機延時（過濾感測器尖峰）
    a_delay = 10.0  # 溫度警報延時
    rules: List[ProtectionRule] = [
        # 主軸承 / 定子 / 機艙（設定值：manual）
        ProtectionRule(262, "bearing_temp", True, spec.gen_bearing_alarm, 3.0, a_delay),
        ProtectionRule(240, "bearing_temp", True, spec.gen_bearing_trip, 5.0, t_delay),
        ProtectionRule(264, "stator_temp", True, spec.gen_stator_alarm, 3.0, a_delay),
        ProtectionRule(244, "stator_temp", True, spec.gen_stator_trip, 5.0, t_delay),
        ProtectionRule(273, "nacelle_temp", True, spec.nacelle_air_alarm, 2.0, a_delay),
        ProtectionRule(256, "nacelle_cab_temp", True, spec.nacelle_cab_trip, 3.0, t_delay),
        # 變壓器 / 變頻器冷卻（設定值：assumed；ABB 跳機同時送出變頻器跳機要求 021）
        ProtectionRule(417, "transformer_temp", True, spec.transformer_alarm, 3.0, a_delay),
        ProtectionRule(444, "transformer_temp", True, spec.transformer_trip, 5.0, t_delay),
        ProtectionRule(420, "cooling_water_temp", True, spec.cooling_water_alarm, 2.0, a_delay),
        ProtectionRule(437, "cooling_water_temp", True, spec.cooling_water_trip, 3.0, t_delay),
        ProtectionRule(_CONVERTER_TRIP_REQUEST, "cooling_water_temp", True, spec.cooling_water_trip, 3.0, t_delay),
        ProtectionRule(421, "converter_cab_temp", True, spec.converter_cabinet_alarm, 2.0, a_delay),
        ProtectionRule(438, "converter_cab_temp", True, spec.converter_cabinet_trip, 3.0, t_delay),
        ProtectionRule(_CONVERTER_TRIP_REQUEST, "converter_cab_temp", True, spec.converter_cabinet_trip, 3.0, t_delay),
        ProtectionRule(432, "static_water_pressure", False, spec.cooling_static_pressure_low_bar, 0.2, a_delay,
                       producing_only=True),
        # 偏航煞車（manual）
        ProtectionRule(260, "yaw_brake_pressure", False, spec.yaw_pressure_alarm, 5.0, a_delay,
                       gate="yaw_brake_settled"),
        ProtectionRule(228, "yaw_brake_pressure", False, spec.yaw_pressure_trip, 5.0, t_delay,
                       gate="yaw_brake_settled"),
        ProtectionRule(261, "seals_leak", True, 0.5, 0.0, a_delay),
        # 風向標 1-2 差異（manual；濾波與風速條件在 signals 內處理）
        ProtectionRule(233, "vane_discrepancy", True, spec.vane_discrepancy_deg, 3.0, 0.0),
        # 塔架加速度（assumed）
        ProtectionRule(236, "vibration", True, spec.tower_vibration_trip_mm_s, 1.0, 10.0),
    ]
    # 葉片同步差異（manual：瞬間 > 8°、3 s > 3°、5 s > 1°），只在穩定發電時判定
    for code, signal in ((335, "blade_disc_12"), (336, "blade_disc_13"), (337, "blade_disc_23")):
        for setpoint, delay in ((spec.blade_discrepancy_instant_deg, 0.0),
                                (spec.blade_discrepancy_3s_deg, 3.0),
                                (spec.blade_discrepancy_5s_deg, 5.0)):
            rules.append(ProtectionRule(code, signal, True, setpoint, 0.3, delay, gate="pitch_settled"))
    return tuple(rules)


def raisable_codes(spec: "TurbineSpec") -> FrozenSet[int]:
    """本保護層可能送出的全部跳機 / 警報碼（訊號規則 + 物理層保護補碼）。

    Args:
        spec: 機組規格。

    Returns:
        事件碼集合。
    """
    return frozenset(r.code for r in build_rules(spec)) | frozenset(PROTECTION_TRIP_CODES)


class PlcProtection:
    """單台機組的 Z72 PLC 保護層。"""

    def __init__(self, spec: "TurbineSpec") -> None:
        self.spec = spec
        self.enabled = True
        self.rules = build_rules(spec)
        self._alarm: Dict[int, AlarmDef] = {}
        codes = raisable_codes(spec) | {_CUT_OUT_CODE, _OPERATOR_RESET_CODE}
        for code in codes:
            self._alarm[code] = get_alarm(code)
        self.reset()

    # ── 狀態 ───────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """清除全部狀態（機組完整 reset 時呼叫）。"""
        self._rule_state: Dict[int, _RuleState] = {i: _RuleState() for i in range(len(self.rules))}
        self._codes: Dict[int, _CodeState] = {}
        self._protection_latched: Dict[int, float] = {}
        self._last_info_time: Dict[int, float] = {}
        self._events: Deque[PlcEvent] = deque(maxlen=_EVENT_QUEUE_MAX)
        self._last_trip_codes: Tuple[int, ...] = ()
        self._pending_trip_codes: List[int] = []
        self._vane1_f: Optional[float] = None
        self._vane2_f: Optional[float] = None
        self._wind_avg: Optional[float] = None
        self._producing_s = 0.0
        self._brake_applied_s = _YAW_BRAKE_SETTLE_S
        self.signals: Dict[str, float] = {}

    @property
    def restart_inhibited(self) -> bool:
        """任一本層判定的跳機仍鎖存（含封鎖）時，機組不可重啟。"""
        return any(st.latched for st in self._codes.values())

    @property
    def last_trip_codes(self) -> Tuple[int, ...]:
        """上一個 ``evaluate`` 期間新產生的跳機碼（含同一步中物理層保護停機補上的碼）。"""
        return self._last_trip_codes

    def active_codes(self) -> Dict[int, str]:
        """目前成立中的警報與鎖存中的跳機（事件碼 → 等級）。"""
        result = {code: self._alarm[code].level for code, st in self._codes.items() if st.active or st.latched}
        for code in self._protection_latched:
            result[code] = self._alarm[code].level
        return result

    def drain_events(self) -> List[PlcEvent]:
        """取走並清空暫存事件。"""
        events = list(self._events)
        self._events.clear()
        return events

    # ── 判定 ───────────────────────────────────────────────────────────────

    def _update_signals(self, output: Mapping[str, float], dt: float, producing: bool, yawing: bool) -> None:
        b1 = output["WROT_PtAngValBl1"]
        b2 = output["WROT_PtAngValBl2"]
        b3 = output["WROT_PtAngValBl3"]
        v1 = output["WYAW_YwVn1AlgnAvg5s"]
        v2 = output["WYAW_YwVn2AlgnAvg5s"]
        wind = output["WMET_WSpeedNac"]
        a_vane = 1.0 - math.exp(-dt / _VANE_FILTER_TAU_S)
        a_wind = 1.0 - math.exp(-dt / _WIND_AVG_TAU_S)
        self._vane1_f = v1 if self._vane1_f is None else self._vane1_f + (v1 - self._vane1_f) * a_vane
        self._vane2_f = v2 if self._vane2_f is None else self._vane2_f + (v2 - self._vane2_f) * a_vane
        self._wind_avg = wind if self._wind_avg is None else self._wind_avg + (wind - self._wind_avg) * a_wind
        self._producing_s = self._producing_s + dt if producing else 0.0
        self._brake_applied_s = 0.0 if yawing else self._brake_applied_s + dt
        vane_disc = abs(self._vane1_f - self._vane2_f)
        if self._wind_avg <= self.spec.vane_discrepancy_min_wind:
            vane_disc = 0.0
        self.signals = {
            "bearing_temp": output["WGEN_GnBrgTmp1"],
            "stator_temp": output["WGEN_GnStaTmp1"],
            "nacelle_temp": output["WNAC_NacTmp"],
            "nacelle_cab_temp": output["WNAC_NacCabTmp"],
            "transformer_temp": output["WGDC_TrfCoreTmp"],
            "cooling_water_temp": output["WCNV_IGCTWtrTmp"],
            "converter_cab_temp": output["WCNV_CnvCabinTmp"],
            "static_water_pressure": output["WCNV_IGCTWtrPres1"],
            "yaw_brake_pressure": output["WYAW_YwBrkHyPrs"],
            "seals_leak": output["WYAW_YwBrkSealsLeak"],
            "vane_discrepancy": vane_disc,
            "blade_disc_12": abs(b1 - b2),
            "blade_disc_13": abs(b1 - b3),
            "blade_disc_23": abs(b2 - b3),
            "vibration": max(output["WNAC_VibMsNacXDir"], output["WNAC_VibMsNacYDir"]),
            "grid_voltage_pu": output["WCNV_VtgMsCnvGd1"]
            / (self.spec.nominal_voltage / math.sqrt(3.0) / 1000.0),
            "pitch_settled": 1.0 if self._producing_s >= _PITCH_SETTLE_S else 0.0,
            "yaw_brake_settled": 1.0 if self._brake_applied_s >= _YAW_BRAKE_SETTLE_S else 0.0,
        }

    def _rule_on(self, idx: int, rule: ProtectionRule, dt: float, producing: bool) -> bool:
        st = self._rule_state[idx]
        if (rule.producing_only and not producing) or (rule.gate and self.signals[rule.gate] < 0.5):
            st.timer = 0.0
            st.on = False
            return False
        value = self.signals[rule.signal]
        crossed = value > rule.setpoint if rule.above else value < rule.setpoint
        st.timer = st.timer + dt if crossed else 0.0
        if st.on:
            still = value > rule.setpoint - rule.hysteresis if rule.above else value < rule.setpoint + rule.hysteresis
            st.on = still
        else:
            # 嚴格大於：步長 ≥ 延時（批次 5 s 子步）時至少要連續兩個樣本，單一樣本不算「持續」
            st.on = crossed and (st.timer > rule.delay_s if rule.delay_s > 0 else True)
        return st.on

    def evaluate(self, output: Mapping[str, float], sim_time: float, dt: float,
                 producing: bool, yawing: bool = False) -> List[Tuple[int, str]]:
        """判定一步，回傳本步新跳機的 ``(code, level)``（呼叫端依等級要求停機）。

        Args:
            output: 感測器模型之前的製程值（鍵同 SCADA tag）。
            sim_time: 機組模擬時間（秒）。
            dt: 時間步長（秒）。
            producing: 機組是否在發電狀態（TurSt 6）。
            yawing: 是否正在偏航（煞車鬆開）。

        Returns:
            新跳機清單。
        """
        pending, self._pending_trip_codes = self._pending_trip_codes, []
        self._last_trip_codes = tuple(pending)
        if not self.enabled:
            return []
        self._update_signals(output, dt, producing, yawing)
        code_on: Dict[int, bool] = {}
        for idx, rule in enumerate(self.rules):
            on = self._rule_on(idx, rule, dt, producing)
            code_on[rule.code] = code_on.get(rule.code, False) or on

        trips: List[Tuple[int, str]] = []
        for code in sorted(code_on):
            active = code_on[code]
            alarm = self._alarm[code]
            st = self._codes.setdefault(code, _CodeState())
            value, setpoint = self._trigger_value(code)
            if alarm.level == "A":
                if active and not st.active:
                    self._emit(sim_time, "alarm_raised", code, value, setpoint)
                elif not active and st.active:
                    self._emit(sim_time, "alarm_cleared", code, value, setpoint)
            elif alarm.is_trip:
                if active and not st.latched:
                    st.latched = True
                    st.trip_times = [t for t in st.trip_times if sim_time - t < _TRIP_WINDOW_S] + [sim_time]
                    self._emit(sim_time, "trip", code, value, setpoint)
                    trips.append((code, alarm.level))
                elif not active and st.latched and not st.blocked:
                    recent = [t for t in st.trip_times if sim_time - t < _TRIP_WINDOW_S]
                    limit = alarm.max_per_hour or 1
                    if len(recent) > limit:
                        st.blocked = True
                        self._emit(sim_time, "restart_blocked", code, value, setpoint)
                    else:
                        st.latched = False
                        self._emit(sim_time, "trip_cleared", code, value, setpoint)
            st.active = active
        self._last_trip_codes = tuple(pending) + tuple(code for code, _ in trips)
        return trips

    def _trigger_value(self, code: int) -> Tuple[Optional[float], Optional[float]]:
        for rule in self.rules:
            if rule.code == code:
                return round(self.signals.get(rule.signal, float("nan")), 3), rule.setpoint
        return None, None

    # ── 物理層保護、操作員 ──────────────────────────────────────────────────

    def note_protection_stop(self, cause: str, sim_time: float) -> List[int]:
        """物理層既有保護要求停機時，補上對應事件碼。

        Args:
            cause: ``TurbinePhysicsModel`` 的停機原因（``overspeed_software`` / ``cut_out`` /
                ``ride_through:lvrt_band1`` / ``grid_protection`` ...）。
            sim_time: 機組模擬時間（秒）。

        Returns:
            新產生的跳機碼（I 類不算）。
        """
        if not self.enabled:
            return []
        if cause == "cut_out":
            last = self._last_info_time.get(_CUT_OUT_CODE)
            if last is None or sim_time - last >= _INFO_EVENT_MIN_INTERVAL_S:
                self._last_info_time[_CUT_OUT_CODE] = sim_time
                self._emit(sim_time, "info", _CUT_OUT_CODE, None, None, source="protection")
            return []
        codes = self._protection_codes(cause)
        new_codes = [c for c in codes if c not in self._protection_latched]
        for code in new_codes:
            self._protection_latched[code] = sim_time
            self._emit(sim_time, "trip", code, None, None, source="protection")
        self._pending_trip_codes.extend(new_codes)
        return new_codes

    def _protection_codes(self, cause: str) -> List[int]:
        if cause in _OVERSPEED_CODES:
            return [_OVERSPEED_CODES[cause]]
        if cause.startswith("ride_through:lvrt_band"):
            band = int(cause.rsplit("band", 1)[1] or 1)
            return [481 if band <= 2 else 482, _CONVERTER_TRIP_REQUEST]
        if cause.startswith("ride_through:hvrt"):
            return [475, _CONVERTER_TRIP_REQUEST]
        if cause in ("grid_protection", "grid_trip"):
            v_pu = self.signals.get("grid_voltage_pu", 1.0)
            if v_pu < 0.87:
                return [481 if cause == "grid_protection" else 482, _CONVERTER_TRIP_REQUEST]
            if v_pu > 1.10:
                return [475, _CONVERTER_TRIP_REQUEST]
            return [489, _CONVERTER_TRIP_REQUEST]
        return []

    def on_production_resumed(self, sim_time: float) -> None:
        """機組回到發電：物理層保護停機的事件視為解除。"""
        for code in list(self._protection_latched):
            del self._protection_latched[code]
            self._emit(sim_time, "trip_cleared", code, None, None, source="protection")

    def operator_reset(self, sim_time: float) -> None:
        """操作員復位：解除全部鎖存 / 封鎖的跳機；條件仍成立者下一步會再跳。

        Args:
            sim_time: 機組模擬時間（秒）。
        """
        if not self.enabled:
            return
        cleared = False
        for st in self._codes.values():
            if st.latched:
                st.latched = False
                st.blocked = False
                cleared = True
        if cleared:
            self._emit(sim_time, "operator_reset", _OPERATOR_RESET_CODE, None, None, source="operator")

    def _emit(self, sim_time: float, kind: str, code: int, value: Optional[float],
              setpoint: Optional[float], source: str = "signal") -> None:
        alarm = self._alarm[code]
        self._events.append(PlcEvent(
            sim_time=round(sim_time, 3), kind=kind, code=code, level=alarm.level, text=alarm.text,
            plc_tag=alarm.plc_tag, event_id=alarm.event_id, value=value, setpoint=setpoint, source=source,
        ))
