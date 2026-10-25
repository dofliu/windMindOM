"""Z72 PLC 保護層（WMOM-20261021-03-b，EPIC-DS Phase 1b-b）。

依真實 Z72 保護設定值（``TurbineSpec``，WMOM-20261021-03-a）判定**製程值**（感測器模型之前的
物理量），送出 Z72 事件碼（``shared/data/z72_alarm_catalog.json``），並模擬 PLC 的跳機語意。

為何不用感測器模型之後的 SCADA 值：本模擬的感測器模型（雜訊、隨機漂移、卡值）是為 SCADA 趨勢
的視覺真實度調校的資料擷取瑕疵，幅度對 PLC 判定太大（例：葉片角度漂移上限 ±0.8°、卡值每機
每小時約 1.3 次，健康機組約兩天一次葉片同步 T2 誤跳）。感測器故障以有標註的故障情境建模
（WMOM-20261021-08-a）：被注入故障的那支感測器，PLC 判定的是它的故障讀值（漂移 → 同真故障的溫度碼；
斷線 / 編碼器超出範圍 → 專屬的感測器故障碼 242/243、250/251、229、326-328，且該讀值不再參與越限判定）。
另一個例外是風向標凍結（231 / 232，WMOM-20261021-08-c）：判的是含量測雜訊的 I/O 讀值——製程值在固定風向下
本來就不變；感測器模型的雜訊遠大於解析度、卡值事件最長 20 s，健康讀值不會凍結 60 s（測試鎖住這兩個條件）。
不是 SCADA tag 的 PLC 輸入（變頻器轉速、ABB 冷卻水流量、風向標 I/O 讀值）由 ``evaluate(..., internal=)`` 傳入。

跳機語意：

- **延時**：從第一個越限樣本起算，連續越限的經過時間 ≥ 延時才成立（批次 5 s 子步下，有延時的規則至少
  要兩個連續樣本；單一樣本不算「持續」）。成立後只依遲滯解除；判定窗（``gate`` / ``producing_only``）
  關閉只禁止新的成立，不等於條件解除（否則鎖存的跳機會在停機減速時立刻被解除）。
- **A（警報）**：條件成立 → ``alarm_raised``；回到遲滯範圍內 → ``alarm_cleared``。不停機。
- **T1 / T2（跳機）**：條件成立超過延時 → ``trip``，T1 要求正常伺服停機、T2 要求緊急變槳停機。
  跳機鎖存到條件解除；解除時若該碼一小時內的跳機次數未超過手冊每小時上限（``max_per_hour``，手冊
  §6.8.1 / §8.3：每個跳機碼各自計數）→ ``trip_cleared`` 自動解除、機組可自動重啟；超過則該碼封鎖、
  送 A039「Auto restart blocked」（手冊獨有碼），機組進 SHUTDOWN，需操作員復位（``operator_reset``，
  事件 008；同時解除 A039）。復位後條件仍成立會立即再跳。（WMOM-20261022-02 之前送自創的
  ``restart_blocked``，合約 v1.4 起不再送出。）
- **物理層既有保護**（超速、LVRT / 電網保護、切出風速）停機時，依停機原因補上對應事件碼
  （``note_protection_stop``）。這類停機的條件由物理層狀態機處理，不在此鎖存；同一停機週期只記一次，
  機組再次起動（``on_restart``）後重新計。跳機次數與訊號判定的跳機同一套每碼計數：超過上限時在跳機
  當下封鎖並送 A039，物理層不得自動重啟（``restart_inhibited``）。
- **設定值**：手冊 Appendix D（控制系統實際設定值）與 Appendix C（事件說明）不一致時以 Appendix D 為準
  （DEC-20261023-01）：液壓壓力低 170 / 150 bar、190 bar 解除、延時 30 s；風向標差異延時 60 s、
  風速條件 60 s 平均；溫度（Pt100）以 10 s 時間常數濾波後比較（``CDTauPT100``）。

所有事件以 ``PlcEvent`` 暫存於有上限的佇列，由即時路徑（broker）或批次路徑以 ``drain_events``
取走；沒人取時舊事件自動丟棄，不會無限成長。
"""

from __future__ import annotations

import math
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Deque, Dict, FrozenSet, List, Mapping, Optional, Set, Tuple

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
# 葉片差異只在穩定發電後判定：本模型各葉片對大幅變槳（啟動 30° → 工作角）的響應差異，
# 併網後 60 s 內暫態差異可達 ~6.6°；穩定發電時健康機組連續 5 s 最大約 0.5°、瞬間峰值約 0.9°
#（陣風 TI 30% 約 1.8°，變槳速率受限時；WMOM-20261021-12）
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
_AUTO_RESTART_BLOCKED_CODE = 39  # A: Auto restart blocked（手冊獨有碼，xlsx 沒列；目錄標 manual_only）
# PLC 自己的溫度輸入（Pt100）：以手冊 CDTauPT100 濾波後判定越限；ABB 變頻器 / 變壓器溫度不在此列
#（signals 鍵, SCADA tag）
_PT100_SIGNALS: Tuple[Tuple[str, str], ...] = (
    ("bearing_temp", "WGEN_GnBrgTmp1"),
    ("bearing2_temp", "WGEN_GnBrgTmp2"),
    ("stator_temp", "WGEN_GnStaTmp1"),
    ("stator2_temp", "WGEN_GnStaTmp2"),
    ("nacelle_temp", "WNAC_NacTmp"),
    ("nacelle_cab_temp", "WNAC_NacCabTmp"),
)
# 物理層保護停機可能補上的跳機碼（超速、ARU 欠壓 / 過壓、電網頻率、變頻器跳機要求）
PROTECTION_TRIP_CODES: Tuple[int, ...] = (351, 320, 475, 481, 482, 489, _CONVERTER_TRIP_REQUEST)
# 變槳馬達電流的平均窗（手冊 Appendix D CDOvrCurr5s / 60s / 10m；以同時間常數的一階濾波近似）
_PITCH_CURRENT_WINDOWS: Tuple[Tuple[str, float], ...] = (("5s", 5.0), ("60s", 60.0), ("10m", 600.0))
# 延時比較的浮點容差（子步 dt 累加誤差）
_DELAY_EPS_S = 1e-6
# 電網保護停機依量測電壓分類（p.u.）：< 0.81 對齊物理層嚴重欠壓限值 → 482；< 0.90 → 481；
# > 1.08（物理層過壓限值 1.10 含個體差 ±0.02）→ 475；其餘視為頻率越界 → 489
_GRID_VERY_LOW_PU = 0.81
_GRID_LOW_PU = 0.90
_GRID_HIGH_PU = 1.08


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
        gate: 選填，``signals`` 中的旗標鍵；旗標為 0 時不判定（例：葉片差異只在穩定發電時判定）。已成立的
            規則不受影響（判定窗關閉不等於條件解除）。
        valid: 選填，``signals`` 中的讀值有效旗標鍵；旗標為 0（斷線 / 超出範圍）時規則立即不成立——
            失效的讀值不能維持溫度過高、壓力過低、葉片差異（WMOM-20261021-08-a）。
    """

    code: int
    signal: str
    above: bool
    setpoint: float
    hysteresis: float
    delay_s: float = 0.0
    producing_only: bool = False
    gate: Optional[str] = None
    valid: Optional[str] = None


@dataclass
class _RuleState:
    # 從第一個越限樣本起算的經過秒數；None＝目前未越限
    elapsed: Optional[float] = None
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
            ``operator_reset`` / ``info``（自動重啟封鎖以 A039 的 ``alarm_raised`` / ``alarm_cleared`` 表示）。
        code: Z72 事件碼。
        level: A / T1 / T2 / I。
        text: PLC 顯示文字（目錄原文）。
        plc_tag: 送出此事件的 PLC tag；I 類為 None。
        event_id: HMI 事件 ID（例 ``A_262``）。
        value: 觸發當下的訊號值（物理層保護停機時為 None）。
        setpoint: 對應設定值（物理層保護停機時為 None）。
        source: ``signal``（本層判定）、``protection``（物理層既有保護）、``restart``（每小時重啟上限，A039）
            或 ``operator``。
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


def _in_range(value: float, valid: Tuple[float, float]) -> bool:
    """讀值是否在有效範圍內（含端點）。

    Args:
        value: 讀值。
        valid: ``(下限, 上限)``。

    Returns:
        是否有效。
    """
    return valid[0] <= value <= valid[1]


def _in_range_flag(valid: Tuple[float, float]) -> Callable[[float], float]:
    """讀值有效旗標的函式（1.0 有效、0.0 斷線 / 超出範圍），給規則的 ``valid`` 用。

    Args:
        valid: ``(下限, 上限)``。

    Returns:
        讀值 → 旗標。
    """
    return lambda value: 1.0 if _in_range(value, valid) else 0.0


def build_rules(spec: "TurbineSpec") -> Tuple[ProtectionRule, ...]:
    """依 ``TurbineSpec`` 建立 Z72 保護規則表。

    Args:
        spec: 機組規格（含 -03-a 的保護設定值）。

    Returns:
        規則 tuple。
    """
    # 手冊沒給延時的規則（ABB 變頻器 / 變壓器溫度、冷卻、振動）沿用的假設值：過濾感測器尖峰
    t_delay = 5.0   # 跳機延時（assumed）
    a_delay = 10.0  # 警報延時（assumed）
    s_delay = 2.0   # 感測器訊號故障（斷線 / 超出範圍）的確認延時（assumed）
    # PLC 自己的溫度（Pt100）：手冊只給濾波時間常數（CDTauPT100 10 s，signals 內處理）、沒有事件延時
    pt_delay = 0.0
    # 偏航煞車液壓：手冊 Appendix D 兩個壓力低事件都在 > SDHyPres_H 才解除
    yaw_alarm_hyst = spec.yaw_pressure_reset_bar - spec.yaw_pressure_alarm
    yaw_trip_hyst = spec.yaw_pressure_reset_bar - spec.yaw_pressure_trip
    rules: List[ProtectionRule] = [
        # 主軸承 1 / 2、定子 1 / 2（設定值：manual）；讀值無效（斷線）時不判定
        ProtectionRule(262, "bearing_temp", True, spec.gen_bearing_alarm, 3.0, pt_delay, valid="bearing_temp_ok"),
        ProtectionRule(240, "bearing_temp", True, spec.gen_bearing_trip, 5.0, pt_delay, valid="bearing_temp_ok"),
        ProtectionRule(263, "bearing2_temp", True, spec.gen_bearing_alarm, 3.0, pt_delay, valid="bearing2_temp_ok"),
        ProtectionRule(241, "bearing2_temp", True, spec.gen_bearing_trip, 5.0, pt_delay, valid="bearing2_temp_ok"),
        ProtectionRule(264, "stator_temp", True, spec.gen_stator_alarm, 3.0, pt_delay, valid="stator_temp_ok"),
        ProtectionRule(244, "stator_temp", True, spec.gen_stator_trip, 5.0, pt_delay, valid="stator_temp_ok"),
        ProtectionRule(265, "stator2_temp", True, spec.gen_stator_alarm, 3.0, pt_delay, valid="stator2_temp_ok"),
        ProtectionRule(245, "stator2_temp", True, spec.gen_stator_trip, 5.0, pt_delay, valid="stator2_temp_ok"),
        ProtectionRule(273, "nacelle_temp", True, spec.nacelle_air_alarm, 2.0, pt_delay),
        ProtectionRule(256, "nacelle_cab_temp", True, spec.nacelle_cab_trip, 3.0, pt_delay),
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
        # 偏航煞車（manual Appendix D：170 / 150 bar、> 190 bar 解除、延時 30 s）
        ProtectionRule(260, "yaw_brake_pressure", False, spec.yaw_pressure_alarm, yaw_alarm_hyst,
                       spec.yaw_pressure_delay_s, gate="yaw_brake_settled", valid="yaw_pressure_ok"),
        ProtectionRule(228, "yaw_brake_pressure", False, spec.yaw_pressure_trip, yaw_trip_hyst,
                       spec.yaw_pressure_delay_s, gate="yaw_brake_settled", valid="yaw_pressure_ok"),
        ProtectionRule(261, "seals_leak", True, 0.5, 0.0, a_delay),
        # 風向標 1-2 差異（manual：15°、延時 60 s；25 s 濾波在 signals 內處理）。風速條件（Appendix D「enable
        # wind vane discrepancy」）是判定窗：只禁止新的成立，已鎖存的跳機不因風速掉下來就解除
        ProtectionRule(233, "vane_discrepancy", True, spec.vane_discrepancy_deg, 3.0, spec.vane_discrepancy_delay_s,
                       gate="vane_wind_ok"),
        # 塔架加速度（assumed）
        ProtectionRule(236, "vibration", True, spec.tower_vibration_trip_mm_s, 1.0, 10.0),
        # 偏航逾時（manual Appendix D SDYawTmOutFact / SDYawTmOutOffs；逾時與否在 signals 內算）
        ProtectionRule(223, "yaw_timeout", True, 0.5, 0.0, 0.0),
        # ── 故障庫擴充（WMOM-20261021-08-c）──
        # 轉速感測器 029：PLC 量的轉子轉速與變頻器的發電機轉速差 > 10 %（manual；轉速下限與延時 assumed）
        ProtectionRule(29, "rotor_speed_deviation", True, spec.rotor_speed_deviation, 0.02,
                       spec.rotor_speed_deviation_delay_s, gate="rotor_speed_check"),
        # 風速計 230：轉子 > 6.5 rpm 時風速讀值 < 0.5 m/s 持續 60 s（manual Appendix D SDWspdMinRange /
        # SDRotSpdMinRange / SDWndMtrFltTm）
        ProtectionRule(230, "anemometer_wind", False, spec.anemometer_min_wind, 0.5, spec.anemometer_fault_delay_s,
                       gate="rotor_turning"),
        # 風向標 231 / 232：I/O 讀值凍結 > 1 分鐘、1 分鐘平均風速 > 4.0 m/s（manual）
        ProtectionRule(231, "vane1_frozen", True, 0.5, 0.0, spec.vane_frozen_delay_s, gate="vane_frozen_wind_ok"),
        ProtectionRule(232, "vane2_frozen", True, 0.5, 0.0, spec.vane_frozen_delay_s, gate="vane_frozen_wind_ok"),
        # ABB 冷卻水流量 422 / 439、導電度 423 / 440（assumed；ABB 跳機同時送出變頻器跳機要求 021）
        ProtectionRule(422, "cooling_flow", False, spec.cooling_flow_alarm_ratio, 0.03, a_delay, producing_only=True),
        ProtectionRule(439, "cooling_flow", False, spec.cooling_flow_trip_ratio, 0.03, t_delay, producing_only=True),
        ProtectionRule(_CONVERTER_TRIP_REQUEST, "cooling_flow", False, spec.cooling_flow_trip_ratio, 0.03, t_delay,
                       producing_only=True),
        ProtectionRule(423, "cooling_conductivity", True, spec.cooling_conductivity_alarm_us_cm, 0.05, a_delay),
        ProtectionRule(440, "cooling_conductivity", True, spec.cooling_conductivity_trip_us_cm, 0.05, t_delay),
        ProtectionRule(_CONVERTER_TRIP_REQUEST, "cooling_conductivity", True, spec.cooling_conductivity_trip_us_cm, 0.05,
                       t_delay),
    ]
    # 變槳馬達過載 367-369（manual Appendix D：5 s 平均 > 22 A、60 s > 20 A、10 分鐘 > 18 A）與伺服驅動 I2t
    # 限流 381-383（驅動器熱狀態 > 1＝RMS 電流超過連續額定；assumed）
    for blade, (overload, i2t) in enumerate(((367, 381), (368, 382), (369, 383)), start=1):
        for window, setpoint in (("5s", spec.pitch_motor_overcurrent_5s_a), ("60s", spec.pitch_motor_overcurrent_60s_a),
                                 ("10m", spec.pitch_motor_overcurrent_10m_a)):
            rules.append(ProtectionRule(overload, f"pitch{blade}_current_{window}", True, setpoint, 1.0))
        rules.append(ProtectionRule(i2t, f"pitch{blade}_i2t", True, 1.0, 0.1))
    # 感測器訊號故障（WMOM-20261021-08-a；手冊：I/O 模組偵測到斷線 / 編碼器角度超出範圍）：讀值超出有效範圍
    pt_lo, pt_hi = spec.pt100_valid_range_c
    yaw_lo, yaw_hi = spec.yaw_pressure_valid_range_bar
    ang_lo, ang_hi = spec.blade_angle_valid_range_deg
    # Pt100 斷線判的是未濾波的讀值（I/O 模組直接偵測），越限規則才用濾波值
    for code, signal, lo, hi in ((242, "bearing_temp_raw", pt_lo, pt_hi), (243, "bearing2_temp_raw", pt_lo, pt_hi),
                                 (250, "stator_temp_raw", pt_lo, pt_hi), (251, "stator2_temp_raw", pt_lo, pt_hi),
                                 (229, "yaw_brake_pressure", yaw_lo, yaw_hi),
                                 (326, "blade1_angle", ang_lo, ang_hi), (327, "blade2_angle", ang_lo, ang_hi),
                                 (328, "blade3_angle", ang_lo, ang_hi)):
        rules.append(ProtectionRule(code, signal, True, hi, 0.0, s_delay))
        rules.append(ProtectionRule(code, signal, False, lo, 0.0, s_delay))
    # 葉片同步差異（manual：瞬間 > 8°、3 s > 3°、5 s > 1°），只在穩定發電、該對葉片的編碼器都有效時判定
    for code, pair in ((335, "12"), (336, "13"), (337, "23")):
        for setpoint, delay in ((spec.blade_discrepancy_instant_deg, 0.0),
                                (spec.blade_discrepancy_3s_deg, 3.0),
                                (spec.blade_discrepancy_5s_deg, 5.0)):
            rules.append(ProtectionRule(code, f"blade_disc_{pair}", True, setpoint, 0.3, delay, gate="pitch_settled",
                                        valid=f"blades_{pair}_ok"))
    return tuple(rules)


def raisable_codes(spec: "TurbineSpec") -> FrozenSet[int]:
    """本保護層可能送出的全部跳機 / 警報碼（訊號規則 + 物理層保護補碼 + 自動重啟封鎖 A039）。

    Args:
        spec: 機組規格。

    Returns:
        事件碼集合。
    """
    return (frozenset(r.code for r in build_rules(spec)) | frozenset(PROTECTION_TRIP_CODES)
            | {_AUTO_RESTART_BLOCKED_CODE})


# 真實 PLC 的 Z72PLC__ActiveAlarm / ActiveTrip1 / ActiveTrip2 陣列長度（tag 清單 xlsx：21 個 SINT16）
ACTIVE_LIST_SLOTS = 21


class ActiveEventLists:
    """依事件維護目前成立的警報 / 跳機碼（OPC 的 ActiveAlarm / ActiveTrip1 / ActiveTrip2 陣列，WMOM-20261021-07）。

    依成立順序排列、同一個碼只出現一次。規則：
    - ``alarm_raised`` 加入 A 清單、``alarm_cleared`` 移除。
    - ``trip`` 依等級加入 T1 / T2 清單、``trip_cleared`` 移除；超過每小時重啟上限時跳機碼仍保留（鎖存），
      另由 A039（Auto restart blocked）的 ``alarm_raised`` / ``alarm_cleared`` 增減 A 清單。舊資料的
      ``restart_blocked``（合約 v1.4 前）不動清單。
    - 操作員復位（``operator_reset``；資料包事件為 ``reset``）本身不動清單：``PlcProtection.operator_reset``
      解除的每個鎖存都另外送 ``trip_cleared``；維護復位（``maintenance_release``）不解除鎖存，跳機清單照舊
      （有 A039 時送 ``alarm_cleared``，A 清單移除 039）。
      物理層保護停機的跳機（例：351）在機組再起動時以 ``trip_cleared`` 解除。
    - 資訊事件（I）不在任何清單。

    即時模擬由 ``PlcProtection`` 在送出事件時更新；回放則由事件流重建，兩邊規則相同，且與
    ``PlcProtection.active_codes()`` 一致（``test_opcua_server.py`` 逐步檢查）。真實 PLC 陣列內的排列方式
    手冊沒有寫，這裡假設依成立順序、空位為 0。
    """

    def __init__(self) -> None:
        self._lists: Dict[str, List[int]] = {"A": [], "T1": [], "T2": []}

    def apply(self, kind: str, code: int, level: Optional[str]) -> bool:
        """套用一個事件。

        Args:
            kind: 事件種類（PLC 事件的 ``kind`` 或資料包事件的 ``event_type``）。
            code: 事件碼。
            level: 等級（``A`` / ``T1`` / ``T2`` / ``I``）。

        Returns:
            清單是否改變。
        """
        if kind == "alarm_raised" and level == "A":
            return self._add("A", code)
        if kind == "alarm_cleared":
            return self._remove(("A",), code)
        if kind == "trip" and level in ("T1", "T2"):
            return self._add(level, code)
        if kind == "trip_cleared":
            return self._remove(("T1", "T2"), code)
        return False

    def snapshot(self) -> Dict[str, List[int]]:
        """目前的清單（複本）。"""
        return {level: list(codes) for level, codes in self._lists.items()}

    def _add(self, level: str, code: int) -> bool:
        if code in self._lists[level]:
            return False
        self._lists[level].append(code)
        return True

    def _remove(self, levels: Tuple[str, ...], code: int) -> bool:
        changed = False
        for level in levels:
            if code in self._lists[level]:
                self._lists[level].remove(code)
                changed = True
        return changed


class PlcProtection:
    """單台機組的 Z72 PLC 保護層。"""

    def __init__(self, spec: "TurbineSpec") -> None:
        """建立規則表並清空狀態。

        Args:
            spec: 機組規格（保護設定值來源）。
        """
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
        # 每個可能跳機 / 警報的碼先建好：執行中不新增鍵（API 執行緒的 operator_reset 迭代時不會遇到字典變大）
        self._codes: Dict[int, _CodeState] = {
            code: _CodeState() for code in sorted({r.code for r in self.rules} | set(PROTECTION_TRIP_CODES))}
        # 每個事件碼最近一次成立的規則（同碼多規則時，事件的 value / setpoint 取實際成立者）
        self._trigger_rule: Dict[int, ProtectionRule] = {}
        self._protection_latched: Dict[int, float] = {}
        # 超過每小時重啟上限的物理層保護跳機碼（跳機當下判定；操作員 / 維護復位才解除）
        self._protection_blocked: Set[int] = set()
        # A039（Auto restart blocked）是否成立中：任一碼封鎖時成立
        self._restart_blocked_alarm = False
        # 本停機週期已記過切出風速事件（I201）；機組再次起動時清除（WMOM-20261021-10）
        self._cut_out_noted = False
        self._events: Deque[PlcEvent] = deque(maxlen=_EVENT_QUEUE_MAX)
        # 目前成立的警報 / 跳機碼（OPC UA server 的 ActiveAlarm / ActiveTrip 陣列，WMOM-20261021-07）
        self.active_lists = ActiveEventLists()
        self._last_trip_codes: Tuple[int, ...] = ()
        self._pending_trip_codes: List[int] = []
        self._vane1_f: Optional[float] = None
        self._vane2_f: Optional[float] = None
        self._wind_avg: Optional[float] = None
        # Pt100 溫度的濾波值（CDTauPT100）；讀值無效（斷線）時清空，恢復後從讀值重新起算
        self._pt100_f: Dict[str, Optional[float]] = {}
        self._producing_s = 0.0
        self._brake_applied_s = _YAW_BRAKE_SETTLE_S
        # 這一段對風偏航已持續的秒數與允許的時間（偏航逾時 223；不在偏航時為 None）
        self._yaw_run_s = 0.0
        self._yaw_timeout_s: Optional[float] = None
        # 變槳馬達電流的各窗平均（葉片 → 窗 → 值）與伺服驅動 I2t 熱狀態（WMOM-20261021-08-c）
        self._pitch_current_avg: List[Dict[str, float]] = [{}, {}, {}]
        self._pitch_i2t = [0.0, 0.0, 0.0]
        # 風向標 1 / 2 上一步的 I/O 讀值（凍結判定 231 / 232）
        self._vane_io_prev: List[Optional[float]] = [None, None]
        # 轉速差（029）最近一次可比對時的值：轉子停下（判定窗關閉）時保持，不等於條件解除
        self._rotor_speed_dev = 0.0
        self.signals: Dict[str, float] = {}

    @property
    def restart_inhibited(self) -> bool:
        """任一本層判定的跳機仍鎖存（含封鎖），或物理層保護跳機超過每小時上限時，機組不可重啟。

        Returns:
            True＝擋住重啟；停用（``enabled=False``）時恆為 False。
        """
        return self.enabled and (any(st.latched for st in self._codes.values()) or bool(self._protection_blocked))

    @property
    def auto_restart_blocked(self) -> bool:
        """A039 成立中（某個跳機碼超過每小時重啟上限）：機組進 SHUTDOWN，只有操作員復位能解除。

        Returns:
            是否封鎖；停用時恆為 False。
        """
        return self.enabled and self._restart_blocked_alarm

    @property
    def last_trip_codes(self) -> Tuple[int, ...]:
        """上一個 ``evaluate`` 期間新產生的跳機碼（含同一步中物理層保護停機補上的碼）。"""
        return self._last_trip_codes

    def active_codes(self) -> Dict[int, str]:
        """目前成立中的警報與鎖存中的跳機。

        Returns:
            事件碼 → 等級（A / T1 / T2）。
        """
        result = {code: self._alarm[code].level for code, st in self._codes.items() if st.active or st.latched}
        for code in self._protection_latched:
            result[code] = self._alarm[code].level
        if self._restart_blocked_alarm:
            result[_AUTO_RESTART_BLOCKED_CODE] = self._alarm[_AUTO_RESTART_BLOCKED_CODE].level
        return result

    def drain_events(self) -> List[PlcEvent]:
        """取走並清空暫存事件。

        Returns:
            自上次取走後的事件（依發生順序）。
        """
        events = list(self._events)
        self._events.clear()
        return events

    # ── 判定 ───────────────────────────────────────────────────────────────

    def _update_signals(self, output: Mapping[str, float], dt: float, producing: bool, yawing: bool,
                        unwinding: bool = False, internal: Optional[Mapping[str, float]] = None) -> None:
        b1 = output["WROT_PtAngValBl1"]
        b2 = output["WROT_PtAngValBl2"]
        b3 = output["WROT_PtAngValBl3"]
        v1 = output["WYAW_YwVn1AlgnAvg5s"]
        v2 = output["WYAW_YwVn2AlgnAvg5s"]
        wind = output["WMET_WSpeedNac"]
        spec = self.spec
        a_vane = 1.0 - math.exp(-dt / _VANE_FILTER_TAU_S)
        # 風速條件：手冊 Appendix D 參數名為 60 s 平均（SDVw60sWndVnDiscr）；以同時間常數的一階濾波近似
        a_wind = 1.0 - math.exp(-dt / spec.vane_discrepancy_wind_avg_s)
        self._vane1_f = v1 if self._vane1_f is None else self._vane1_f + (v1 - self._vane1_f) * a_vane
        self._vane2_f = v2 if self._vane2_f is None else self._vane2_f + (v2 - self._vane2_f) * a_vane
        self._wind_avg = wind if self._wind_avg is None else self._wind_avg + (wind - self._wind_avg) * a_wind
        self._producing_s = self._producing_s + dt if producing else 0.0
        self._brake_applied_s = 0.0 if yawing else self._brake_applied_s + dt
        # 偏航逾時：對風（不含解纜）開始時依當下的偏航誤差算允許時間＝factor × 誤差 ÷ 偏航速度 + offset
        aligning = yawing and not unwinding
        if aligning:
            if self._yaw_timeout_s is None:
                yaw_error = max(abs(v1), 2.0)
                self._yaw_timeout_s = (self.spec.yaw_timeout_factor * yaw_error / self.spec.yaw_rate_deg_s
                                       + self.spec.yaw_timeout_offset_s)
                self._yaw_run_s = 0.0
            self._yaw_run_s += dt
        else:
            self._yaw_timeout_s = None
            self._yaw_run_s = 0.0
        vane_disc = abs(self._vane1_f - self._vane2_f)
        pt_ok = _in_range_flag(spec.pt100_valid_range_c)
        blade_ok = [_in_range(a, spec.blade_angle_valid_range_deg) for a in (b1, b2, b3)]
        yaw_pressure = output["WYAW_YwBrkHyPrs"]
        self.signals = {
            "blade1_angle": b1,
            "blade2_angle": b2,
            "blade3_angle": b3,
            "transformer_temp": output["WGDC_TrfCoreTmp"],
            "cooling_water_temp": output["WCNV_IGCTWtrTmp"],
            "converter_cab_temp": output["WCNV_CnvCabinTmp"],
            "static_water_pressure": output["WCNV_IGCTWtrPres1"],
            "yaw_brake_pressure": yaw_pressure,
            "yaw_pressure_ok": 1.0 if _in_range(yaw_pressure, spec.yaw_pressure_valid_range_bar) else 0.0,
            "seals_leak": output["WYAW_YwBrkSealsLeak"],
            "vane_discrepancy": vane_disc,
            "vane_wind_ok": 1.0 if self._wind_avg > spec.vane_discrepancy_min_wind else 0.0,
            "yaw_timeout": 1.0 if self._yaw_timeout_s is not None and self._yaw_run_s > self._yaw_timeout_s else 0.0,
            "blade_disc_12": abs(b1 - b2),
            "blade_disc_13": abs(b1 - b3),
            "blade_disc_23": abs(b2 - b3),
            "vibration": max(output["WNAC_VibMsNacXDir"], output["WNAC_VibMsNacYDir"]),
            "grid_voltage_pu": output["WCNV_VtgMsCnvGd1"]
            / (self.spec.nominal_voltage / math.sqrt(3.0) / 1000.0),
            # 編碼器讀值無效時不判定含該葉片的差異（由 326-328 報編碼器故障）
            "blades_12_ok": 1.0 if blade_ok[0] and blade_ok[1] else 0.0,
            "blades_13_ok": 1.0 if blade_ok[0] and blade_ok[2] else 0.0,
            "blades_23_ok": 1.0 if blade_ok[1] and blade_ok[2] else 0.0,
            "pitch_settled": 1.0 if self._producing_s >= _PITCH_SETTLE_S else 0.0,
            "yaw_brake_settled": 1.0 if self._brake_applied_s >= _YAW_BRAKE_SETTLE_S else 0.0,
        }
        self._update_expansion_signals(output, dt, internal or {})
        # Pt100：越限判定用濾波值（<鍵>）、斷線判定用讀值（<鍵>_raw）、有效旗標（<鍵>_ok）
        a_pt = 1.0 - math.exp(-dt / spec.pt100_filter_tau_s)
        for key, tag in _PT100_SIGNALS:
            raw = output[tag]
            ok = pt_ok(raw)
            prev = self._pt100_f.get(key)
            if ok < 0.5:
                filtered: Optional[float] = None  # 斷線讀值不進濾波器；修好後從讀值重新起算
            else:
                filtered = raw if prev is None else prev + (raw - prev) * a_pt
            self._pt100_f[key] = filtered
            self.signals[key] = raw if filtered is None else filtered
            self.signals[f"{key}_raw"] = raw
            self.signals[f"{key}_ok"] = ok

    def _update_expansion_signals(self, output: Mapping[str, float], dt: float,
                                  internal: Mapping[str, float]) -> None:
        """故障庫擴充的訊號（WMOM-20261021-08-c）：變槳馬達電流、轉速比對、風速計、風向標凍結、冷卻水。

        Args:
            output: 製程值（注入感測器故障的那支為故障讀值）。
            dt: 時間步長（秒）。
            internal: 不是 SCADA tag 的輸入——``converter_rotor_rpm``（變頻器量到的轉速：直驅 PMSG 由電氣頻率
                算出、等於轉子實際轉速）、``cooling_flow_ratio``（ABB 冷卻單元流量，額定 = 1）、``vane1_io`` /
                ``vane2_io``（風向標 I/O 讀值，含量測雜訊）。沒給的項目不判定（流量視為額定）。
        """
        spec = self.spec
        signals = self.signals
        for blade in range(3):
            current = output[f"WROT_PtMotCurBl{blade + 1}"]
            averages = self._pitch_current_avg[blade]
            for window, tau in _PITCH_CURRENT_WINDOWS:
                prev = averages.get(window)
                averages[window] = current if prev is None else prev + (current - prev) * (1.0 - math.exp(-dt / tau))
                signals[f"pitch{blade + 1}_current_{window}"] = averages[window]
            a_i2t = 1.0 - math.exp(-dt / spec.pitch_drive_i2t_tau_s)
            load = (current / spec.pitch_drive_continuous_a) ** 2
            self._pitch_i2t[blade] += (load - self._pitch_i2t[blade]) * a_i2t
            signals[f"pitch{blade + 1}_i2t"] = self._pitch_i2t[blade]
        rotor_rpm = output["WROT_RotSpd"]
        # 模擬的 WGEN_GnSpd 是傳動鏈模型的發電機轉速，有扭轉暫態（直驅機組實際上剛性連接）：PLC 比對用
        # 變頻器的轉速（WMOM-20261021-08-c），沒給就不判定
        converter_rpm = internal.get("converter_rotor_rpm")
        check = converter_rpm is not None and converter_rpm > spec.rotor_speed_check_min_rpm
        signals["rotor_speed_check"] = 1.0 if check else 0.0
        if converter_rpm is not None and check:
            self._rotor_speed_dev = abs(rotor_rpm - converter_rpm) / converter_rpm
        signals["rotor_speed_deviation"] = self._rotor_speed_dev
        signals["rotor_turning"] = 1.0 if rotor_rpm > spec.anemometer_min_rotor_rpm else 0.0
        signals["anemometer_wind"] = output["WMET_WSpeedNac"]
        # 風速條件沿用 233 的 60 s 平均風速（_wind_avg，_update_signals 已更新）
        signals["vane_frozen_wind_ok"] = 1.0 if (self._wind_avg or 0.0) > spec.vane_frozen_min_wind else 0.0
        for idx, key in enumerate(("vane1_io", "vane2_io")):
            reading = internal.get(key)
            prev = self._vane_io_prev[idx]
            signals[f"vane{idx + 1}_frozen"] = 1.0 if reading is not None and reading == prev else 0.0
            self._vane_io_prev[idx] = reading
        signals["cooling_flow"] = internal.get("cooling_flow_ratio", 1.0)
        signals["cooling_conductivity"] = output["WCNV_IGCTWtrCond"]

    def _rule_on(self, idx: int, rule: ProtectionRule, dt: float, producing: bool) -> bool:
        st = self._rule_state[idx]
        if rule.valid is not None and self.signals[rule.valid] < 0.5:
            st.on = False
            st.elapsed = None
            return False
        value = self.signals[rule.signal]
        if st.on:
            # 已成立：只依遲滯解除。判定窗關閉（停機減速、偏航中）不等於條件解除
            if rule.above:
                st.on = value > rule.setpoint - rule.hysteresis
            else:
                st.on = value < rule.setpoint + rule.hysteresis
            if not st.on:
                st.elapsed = None
            return st.on
        gated = (rule.producing_only and not producing) or (
            rule.gate is not None and self.signals[rule.gate] < 0.5)
        crossed = not gated and (value > rule.setpoint if rule.above else value < rule.setpoint)
        if not crossed:
            st.elapsed = None
            return False
        # 經過時間從第一個越限樣本起算：dt = 5 s 時單一樣本的經過時間是 0，不算「持續」
        st.elapsed = 0.0 if st.elapsed is None else st.elapsed + dt
        st.on = st.elapsed >= rule.delay_s - _DELAY_EPS_S
        return st.on

    def evaluate(self, output: Mapping[str, float], sim_time: float, dt: float,
                 producing: bool, yawing: bool = False, unwinding: bool = False,
                 internal: Optional[Mapping[str, float]] = None) -> List[Tuple[int, str]]:
        """判定一步，回傳本步新跳機的 ``(code, level)``（呼叫端依等級要求停機）。

        Args:
            output: 感測器模型之前的製程值（鍵同 SCADA tag）；被注入感測器故障的那支感測器是它的故障讀值
                （WMOM-20261021-08-a）。
            sim_time: 機組模擬時間（秒）。
            dt: 時間步長（秒）。
            producing: 機組是否在發電狀態（TurSt 6）。
            yawing: 是否正在偏航（煞車鬆開；含解纜）。
            unwinding: 是否正在解纜（偏航逾時不計）。
            internal: 不是 SCADA tag 的 PLC 輸入（冷卻水流量、風向標 I/O 讀值；WMOM-20261021-08-c），
                見 ``_update_expansion_signals``。

        Returns:
            新跳機清單。
        """
        pending, self._pending_trip_codes = self._pending_trip_codes, []
        self._last_trip_codes = tuple(pending)
        if not self.enabled:
            return []
        self._update_signals(output, dt, producing, yawing, unwinding, internal)
        code_on: Dict[int, bool] = {}
        firing: Dict[int, ProtectionRule] = {}
        for idx, rule in enumerate(self.rules):
            on = self._rule_on(idx, rule, dt, producing)
            code_on[rule.code] = code_on.get(rule.code, False) or on
            if on and rule.code not in firing:
                firing[rule.code] = rule
        self._trigger_rule.update(firing)

        trips: List[Tuple[int, str]] = []
        for code in sorted(code_on):
            active = code_on[code]
            alarm = self._alarm[code]
            st = self._codes.setdefault(code, _CodeState())
            value, setpoint = self._trigger_value(code, firing.get(code))
            if alarm.level == "A":
                if active and not st.active:
                    self._emit(sim_time, "alarm_raised", code, value, setpoint)
                elif not active and st.active:
                    self._emit(sim_time, "alarm_cleared", code, value, setpoint)
            elif alarm.is_trip:
                if active and not st.latched:
                    st.latched = True
                    self._record_trip(st, sim_time)
                    self._emit(sim_time, "trip", code, value, setpoint)
                    trips.append((code, alarm.level))
                elif not active and st.latched and not st.blocked:
                    if self._over_restart_limit(st, code, sim_time):
                        st.blocked = True  # 不自動重啟：保持鎖存、送 A039（迴圈後統一）
                    else:
                        st.latched = False
                        self._emit(sim_time, "trip_cleared", code, value, setpoint)
            st.active = active
        self._sync_restart_blocked_alarm(sim_time)
        self._last_trip_codes = tuple(pending) + tuple(code for code, _ in trips)
        return trips

    # ── 每小時重啟上限（手冊 §6.8.1 / §8.3：每個跳機碼各自計數）─────────────────

    @staticmethod
    def _record_trip(st: _CodeState, sim_time: float) -> None:
        """記一次跳機（同時丟掉一小時前的紀錄）。"""
        st.trip_times = [t for t in st.trip_times if sim_time - t < _TRIP_WINDOW_S] + [sim_time]

    def _over_restart_limit(self, st: _CodeState, code: int, sim_time: float) -> bool:
        """該碼一小時內的跳機次數是否超過目錄的每小時上限（``max_per_hour``；未列者視為 1）。

        判定時點：訊號判定的跳機在條件解除（要重啟）時、以解除時刻往前一小時計；物理層保護停機的條件由物理層
        處理，在跳機當下、以跳機時刻往前一小時計。手冊 §8.3 只寫「restarts within the last hour」。同一個碼不分
        成因都算同一種跳機（例：021 伴隨所有變頻器跳機，冷卻與電網的 021 一起計數）。
        """
        recent = [t for t in st.trip_times if sim_time - t < _TRIP_WINDOW_S]
        return len(recent) > (self._alarm[code].max_per_hour or 1)

    def _sync_restart_blocked_alarm(self, sim_time: float) -> None:
        """任一碼封鎖時 A039 成立，全部解除時清除；狀態改變才送事件（多個碼封鎖只送一次）。"""
        blocked = any(st.blocked for st in self._codes.values()) or bool(self._protection_blocked)
        if blocked == self._restart_blocked_alarm:
            return
        self._restart_blocked_alarm = blocked
        kind = "alarm_raised" if blocked else "alarm_cleared"
        self._emit(sim_time, kind, _AUTO_RESTART_BLOCKED_CODE, None, None, source="restart")

    def _trigger_value(self, code: int, rule: Optional[ProtectionRule]) -> Tuple[Optional[float], Optional[float]]:
        """事件的訊號值與設定值：本步成立的規則；解除事件取最近一次成立的規則。"""
        rule = rule or self._trigger_rule.get(code) or next(r for r in self.rules if r.code == code)
        return round(self.signals.get(rule.signal, float("nan")), 3), rule.setpoint

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
            # 每個停機週期記一次（與其他保護停機同一套週期語意），不用時間窗去重——時間窗會把
            # 600 s 內真實的第二次暴風停機吞掉
            if not self._cut_out_noted:
                self._cut_out_noted = True
                self._emit(sim_time, "info", _CUT_OUT_CODE, None, None, source="protection")
            return []
        codes = self._protection_codes(cause)
        new_codes = [c for c in codes if c not in self._protection_latched]
        for code in new_codes:
            self._protection_latched[code] = sim_time
            self._emit(sim_time, "trip", code, None, None, source="protection")
            # 與訊號判定的跳機同一套每碼計數（同一個碼＝同一種跳機）；條件由物理層處理，超過上限在跳機當下封鎖
            st = self._codes[code]
            self._record_trip(st, sim_time)
            if self._over_restart_limit(st, code, sim_time):
                self._protection_blocked.add(code)
        self._sync_restart_blocked_alarm(sim_time)
        self._pending_trip_codes.extend(new_codes)
        return new_codes

    def _protection_codes(self, cause: str) -> List[int]:
        if cause in _OVERSPEED_CODES:
            return [_OVERSPEED_CODES[cause]]
        if cause.startswith("ride_through:lvrt_band"):
            # band 1 = 0.80–0.90 p.u.；band ≥ 2 < 0.80 p.u.（與電網保護的 0.81 嚴重欠壓一致）
            band = int(cause.rsplit("band", 1)[1] or 1)
            return [481 if band <= 1 else 482, _CONVERTER_TRIP_REQUEST]
        if cause.startswith("ride_through:hvrt"):
            return [475, _CONVERTER_TRIP_REQUEST]
        if cause in ("grid_protection", "grid_trip"):
            # 前一步的量測電壓（本步訊號尚未更新）；電網電壓變化慢，差一步不影響分類
            v_pu = self.signals.get("grid_voltage_pu", 1.0)
            if v_pu < _GRID_VERY_LOW_PU:
                return [482, _CONVERTER_TRIP_REQUEST]
            if v_pu < _GRID_LOW_PU:
                return [481, _CONVERTER_TRIP_REQUEST]
            if v_pu > _GRID_HIGH_PU:
                return [475, _CONVERTER_TRIP_REQUEST]
            return [489, _CONVERTER_TRIP_REQUEST]
        return []

    def on_restart(self, sim_time: float) -> None:
        """機組再次起動（進入起動 / 發電）：物理層保護停機的事件視為解除。

        以起動而非停機完成為界：條件持續時物理層會在停止狀態反覆要求停機，以停機完成為界會洗版；
        起動後再遇到同一保護停機則重新記事件。

        Args:
            sim_time: 機組模擬時間（秒）。
        """
        self._cut_out_noted = False
        for code in list(self._protection_latched):
            del self._protection_latched[code]
            self._emit(sim_time, "trip_cleared", code, None, None, source="protection")

    def clear_trip_counts(self) -> None:
        """清掉每小時跳機計數（命名情境開頭的乾淨機組用）：Live 一小時內自動恢復過的跳機不能讓情境的第一次跳機
        就送 A039。不送事件、不動鎖存（呼叫端只對沒有成立中事件的機組呼叫）。"""
        for st in self._codes.values():
            st.trip_times.clear()

    def maintenance_release(self, sim_time: float) -> None:
        """故障被維護清除（修好 + 技師復位）：清除每小時跳機計數與封鎖（含 A039）。

        與 ``operator_reset`` 不同，不解除鎖存：修好後的殘餘條件（例：液壓回壓中）解除時，鎖存的跳機
        以計數 0 自動解除，不會因殘餘條件再跳一次；已封鎖者在下一步即解除。

        Args:
            sim_time: 機組模擬時間（秒）。
        """
        if not self.enabled:
            return
        released = bool(self._protection_blocked)
        for st in list(self._codes.values()):
            released = released or st.latched
            st.trip_times.clear()
            st.blocked = False
        self._protection_blocked.clear()
        self._rotor_speed_dev = 0.0  # 修好了：停機中保持的轉速差不再擋住重啟
        if released:
            self._emit(sim_time, "operator_reset", _OPERATOR_RESET_CODE, None, None, source="operator")
        self._sync_restart_blocked_alarm(sim_time)

    def operator_reset(self, sim_time: float) -> None:
        """操作員復位（TURBINE RESET）：解除全部鎖存 / 封鎖的跳機與 A039；條件仍成立者下一步會再跳。

        送出 ``operator_reset``（事件 008）後清除 A039（``alarm_cleared``），每個被解除的跳機再送
        ``trip_cleared``（OPC 的 ActiveTrip 陣列據此移除）。物理層保護停機的跳機只解除封鎖，跳機本身在
        機組再起動時解除（``on_restart``）。每小時跳機計數不清除：復位後一小時內再跳仍算數。

        Args:
            sim_time: 機組模擬時間（秒）。
        """
        if not self.enabled:
            return
        released: List[int] = []
        for code, st in list(self._codes.items()):
            if st.latched:
                st.latched = False
                st.blocked = False
                released.append(code)
        unblocked = bool(self._protection_blocked)
        self._protection_blocked.clear()
        # 停機中保持的轉速差（029）：復位後重新比對，條件仍成立就在轉子轉起來後再跳
        self._rotor_speed_dev = 0.0
        if released or unblocked:
            self._emit(sim_time, "operator_reset", _OPERATOR_RESET_CODE, None, None, source="operator")
        self._sync_restart_blocked_alarm(sim_time)
        for code in released:
            self._emit(sim_time, "trip_cleared", code, None, None, source="operator")

    def _emit(self, sim_time: float, kind: str, code: int, value: Optional[float],
              setpoint: Optional[float], source: str = "signal") -> None:
        alarm = self._alarm[code]
        self.active_lists.apply(kind, code, alarm.level)
        self._events.append(PlcEvent(
            sim_time=round(sim_time, 3), kind=kind, code=code, level=alarm.level, text=alarm.text,
            plc_tag=alarm.plc_tag, event_id=alarm.event_id, value=value, setpoint=setpoint, source=source,
        ))
