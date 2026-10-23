"""
Fault Simulation Engine — gradual degradation patterns for analyst diagnostics.

Design principles:
1. Faults develop GRADUALLY over hours/days (not sudden jumps)
2. Each fault affects MULTIPLE correlated tags (physically realistic)
3. Severity drives physical causes (heat, cooling, pitch, voltage …) in
   TurbinePhysicsModel._get_fault_physics(); the turbine's PLC protection layer
   (plc_protection.py) raises alarms / trips when the measured process values cross
   the real Z72 setpoints — load and ambient dependent, not at a fixed severity
   (WMOM-20261021-03-b)
4. Historical trend data is analyzable for health assessment

``alarm_codes`` lists the real Z72 events (docs/1040610-Z72_PLC_OPC_TAG_1040510.xlsx,
compiled into shared/data/z72_alarm_catalog.json) the PLC is EXPECTED to raise for this
fault's physics — ground-truth metadata, not an emission schedule. ``type`` / ``desc``
must equal the catalog's level / text (enforced by test_fault_alarm_codes.py). Under
low load or mild weather some expected events may never appear (e.g. a stator fault
at 9 m/s stays below its alarm setpoint).

Each scenario also carries its ANSWER-KEY metadata (component, root cause, category,
difficulty, key SCADA signals, expected actions; WMOM-20261021-04). It only goes into a
scenario's ground truth (simulator/ground_truth.py, stored apart from the observable
events) — never into readings or events the external RAG assistant sees.

A fault becomes ``tripped`` when the PLC trips the turbine with one of its expected
T1 / T2 codes (``mark_tripped``, called by the simulator engine); the turbine then
stays down until maintenance clears the fault (reset ≠ repair, WMOM-20260719-01).

Usage:
    engine = FaultEngine()
    engine.inject("bearing_wear", target_turbine="WT003", severity_rate=0.001)
    # Each physics step:
    modifiers = engine.step(dt=1.0)
    turbine_model.fault_modifiers = modifiers.get("WT003", {})
"""

import itertools
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterator, List, Optional, Tuple
from datetime import datetime

from ..time_utils import iso_utc, utc_now


class FaultPhase(str, Enum):
    """Fault lifecycle phases visible in trend data."""
    INCIPIENT = "incipient"      # Early: subtle changes, hard to detect
    DEVELOPING = "developing"     # Growing: detectable by monitoring
    ADVANCED = "advanced"         # Severe: alarm thresholds exceeded
    CRITICAL = "critical"         # Trip imminent or occurred


@dataclass
class FaultScenario:
    """
    Definition of a fault type and how it affects SCADA tags over time.

    Each fault has:
    - affected_tags: dict mapping tag_id → (max_offset, phase_curve_type) — vestigial,
      effects now flow through TurbinePhysicsModel._get_fault_physics()
    - alarm_codes: Z72 events the PLC is expected to raise for this fault (metadata)
    - severity: 0.0 (no fault) → 1.0 (full severity)
    """
    id: str
    name_en: str
    name_zh: str
    description_en: str
    description_zh: str
    affected_tags: Dict[str, Dict]  # tag_id → {max_offset, curve}
    alarm_codes: List[Dict]         # [{type: "T1"|"T2"|"A", code: int, desc: str}]
    # Legacy: before WMOM-20261021-03-b the turbine tripped when severity reached this.
    # Only used now to approximate trips for scenario sessions generated before trip
    # events were recorded (routers/scenarios.py::_tripped_fault_turbine_ids fallback).
    auto_trip_severity: float = 0.85

    # ── 標準答案 metadata（ground truth，WMOM-20261021-04）──
    # 只寫進情境的標準答案（simulator/ground_truth.py），不進可觀測的讀值 / 事件（盲測）。
    # 欄位語意見設計文件 §5.1 ground_truth.json；由 test_fault_ground_truth.py 檢查完整性。
    component: str = ""                          # 故障元件（snake_case）
    root_cause_zh: str = ""                      # 根因（評分端的標準答案）
    root_cause_en: str = ""
    category: str = "real_fault"                 # real_fault / sensor_fault / nuisance / healthy
    # nuisance 的成因（rag_assistant_vocabulary.json 的 nuisance_causes，WMOM-20261021-08-b）；故障為 None
    nuisance_cause: Optional[str] = None
    origin: str = "internal"                     # internal / environmental / external_grid
    difficulty: str = "medium"                   # easy / medium / hard（對 RAG 診斷而言）
    # 故障在 SCADA 上看得到的 tag：高負載滿嚴重度時明顯偏離健康機組（tests/physics 會驗證）
    key_signals: Tuple[str, ...] = ()
    # 建議處置：手冊 Appendix C 的處置提示（標「（手冊）」）＋ 工程實務；手冊原文另見標準答案的 manual_refs
    expected_actions_zh: Tuple[str, ...] = ()
    expected_actions_en: Tuple[str, ...] = ()
    # 模擬與真實的差異（評分端要知道，例：模擬不會出現的後續事件、沒有耦合的環境量）；根因 / 處置只寫真實世界
    simulation_notes_zh: Tuple[str, ...] = ()
    simulation_notes_en: Tuple[str, ...] = ()


# ─── Pre-defined fault scenarios ──────────────────────────────────────────

FAULT_SCENARIOS: Dict[str, FaultScenario] = {

    # ══════════════════════════════════════════════════════════════════
    # 1. OBVIOUS FAULTS — clear threshold violations, easy to detect
    # ══════════════════════════════════════════════════════════════════

    "bearing_wear": FaultScenario(
        id="bearing_wear",
        name_en="Generator Bearing Wear",
        name_zh="發電機軸承磨損",
        description_en="Gradual bearing degradation causing increased temperature and vibration",
        description_zh="軸承逐漸磨損，導致溫度和振動逐步上升",
        affected_tags={
            "WGEN_GnBrgTmp1": {"max_offset": 45.0, "curve": "exponential"},
            "WNAC_VibMsNacXDir": {"max_offset": 8.0, "curve": "exponential"},
            "WNAC_VibMsNacYDir": {"max_offset": 6.0, "curve": "exponential"},
            "WGEN_GnStaTmp1": {"max_offset": 15.0, "curve": "linear"},
            "WGEN_GnAirTmp1": {"max_offset": 10.0, "curve": "linear"},
        },
        alarm_codes=[
            {"type": "A", "code": 262, "desc": "Main bearing 1 temperature high"},
            {"type": "T1", "code": 240, "desc": "Bearing 1 temperature very high"},
        ],
        component="main_bearing",
        root_cause_zh="主軸承 1（PLC 事件 262 / 240 監測的軸承）潤滑劣化、磨耗：摩擦生熱隨轉速增加且散熱變差，軸承溫度與機艙振動、峰度逐步上升，越過 85 °C 警報、95 °C 跳機；共用潤滑與傳熱，軸承溫度 2 也跟著升溫（幅度約三成）。",
        root_cause_en="Main bearing 1 (monitored by PLC events 262 / 240) lubrication degradation and wear: friction heat rises with speed while heat removal worsens, so bearing temperature, nacelle vibration and kurtosis climb past the 85 °C alarm and 95 °C trip setpoints; through shared lubrication and heat conduction bearing temperature 2 rises too (by about a third as much).",
        difficulty="easy",
        key_signals=(
            "WGEN_GnBrgTmp1",
            "WGEN_GnBrgTmp2",
            "WNAC_VibMsNacXDir",
            "WNAC_VibMsNacYDir",
            "WVIB_Kurtosis",
        ),
        expected_actions_zh=(
            "檢查主軸承潤滑（油脂量 / 油質）（手冊）",
            "檢查軸承冷卻風扇（手冊）",
            "比對振動頻譜（峰度、高頻帶）評估軸承損傷，必要時安排更換",
        ),
        expected_actions_en=(
            "Check main bearing lubrication (manual).",
            "Check the cooling fan (manual).",
            "Review vibration spectra (kurtosis, high-frequency band) for bearing damage; plan replacement if needed.",
        ),
        simulation_notes_zh=(
            "模擬的量測 tag 是 WGEN_GnBrgTmp1（發電機軸承溫度），PLC 以它判定事件 262 / 240（Main bearing 1）；情境名稱沿用 Generator Bearing Wear。",
        ),
        simulation_notes_en=(
            "The simulated measurement tag is WGEN_GnBrgTmp1 (generator bearing temperature); the PLC uses it for events 262 / 240 (Main bearing 1). The scenario keeps its legacy name Generator Bearing Wear.",
        ),
    ),

    "generator_overspeed": FaultScenario(
        id="generator_overspeed",
        name_en="Generator Overspeed",
        name_zh="發電機超速",
        description_en="Control system failure allowing rotor/generator overspeed (Z72 Event 351/320)",
        description_zh="控制系統失效導致發電機超速（Z72事件351/320）",
        affected_tags={
            "WROT_RotSpd": {"max_offset": 5.0, "curve": "exponential"},
            "WGEN_GnSpd": {"max_offset": 5.0, "curve": "exponential"},
            "WNAC_VibMsNacXDir": {"max_offset": 12.0, "curve": "exponential"},
            "WNAC_VibMsNacYDir": {"max_offset": 10.0, "curve": "exponential"},
        },
        alarm_codes=[
            # 對齊物理層兩道保護（TurbineSpec.overspeed_software_rpm 26.5 / overspeed_hardware_rpm 28.5）：
            # 351 變槳控制壓不住轉速；控制失效時轉速續升，觸發外部 Jaquet 硬體超速電驛 320（緊急變槳）
            {"type": "T1", "code": 351, "desc": "Software overspeed"},
            {"type": "T2", "code": 320, "desc": "Hardware overspeed or watchdog timeout"},
        ],
        auto_trip_severity=0.6,
        component="pitch_control_system",
        root_cause_zh="變槳控制失效：控制器 / 變槳驅動壓不住轉子轉速，轉速越過軟體超速設定（351，T1）；控制持續失效時再觸發外部硬體超速電驛（320，T2 緊急變槳）。",
        root_cause_en="Pitch control failure: the controller / pitch drives cannot hold rotor speed, which exceeds the software overspeed limit (351, T1); if control keeps failing the external hardware overspeed relay trips (320, T2 emergency pitch).",
        difficulty="easy",
        key_signals=(
            "WROT_RotSpd",
            "WGEN_GnSpd",
        ),
        expected_actions_zh=(
            "從現場操作面板（Zoom/Rotor/Test Overspeed Trip）讀取峰值轉速並重設（手冊）",
            "檢查變槳驅動與變槳控制回路（含轉速量測）；頻繁發生時調整變槳控制參數並聯絡 Harakosan（手冊）",
            "硬體超速（320）後目視檢查輪轂是否受損（手冊）",
            "超速跳機後須確認原因才可重啟",
        ),
        expected_actions_en=(
            "Read the peak speed from the Local Operator Panel (Zoom/Rotor/Test Overspeed Trip) and reset it (manual).",
            "Check the pitch drives and the pitch control loop, including speed measurement; if it trips often, fine-tune the pitch control parameters and contact Harakosan (manual).",
            "After a hardware overspeed (320), visually inspect the hub for damage (manual).",
            "Find the cause of the overspeed trip before restarting.",
        ),
        simulation_notes_zh=(
            "模擬中 351 跳機後故障即凍結（機組停在 T1），不會再出現 320；320 列為真實情況可能的後續事件。",
        ),
        simulation_notes_en=(
            "In the simulation the fault freezes once 351 trips the turbine (it stays stopped on T1), so 320 never follows; 320 is listed as the possible real-world escalation.",
        ),
    ),

    "converter_cooling_fault": FaultScenario(
        id="converter_cooling_fault",
        name_en="Converter Cooling System Fault",
        name_zh="變頻器冷卻系統故障",
        description_en="IGCT water cooling degradation causing converter overheating (Z72 Event 021)",
        description_zh="IGCT水冷系統劣化，變頻器溫度持續上升（Z72事件021）",
        affected_tags={
            "WCNV_IGCTWtrTmp": {"max_offset": 30.0, "curve": "exponential"},
            "WCNV_IGCTWtrPres1": {"max_offset": -2.0, "curve": "linear"},
            "WCNV_IGCTWtrPres2": {"max_offset": -2.0, "curve": "linear"},
            "WCNV_CnvCabinTmp": {"max_offset": 25.0, "curve": "exponential"},
            "WCNV_CnvGnPwr": {"max_offset": -300.0, "curve": "linear"},
            "WTUR_TotPwrAt": {"max_offset": -300.0, "curve": "linear"},
        },
        alarm_codes=[
            # 手冊：021 會與 400-700 範圍的變頻器跳機碼一起出現
            {"type": "A", "code": 420, "desc": "Cooling water temperature high"},
            {"type": "A", "code": 421, "desc": "Converter cabinet temperature high"},
            # 物理層模擬 O-ring 劣化洩漏（coolant_leak_lph）→ 液位過低時泵空蝕、流量與靜水壓下降
            #（流量事件 422 / 439 自 WMOM-20261021-08-c）
            {"type": "A", "code": 422, "desc": "Cooling water flow low"},
            {"type": "A", "code": 432, "desc": "Static water pressure L"},
            {"type": "T1", "code": 437, "desc": "Cooling water temperature very high"},
            {"type": "T1", "code": 439, "desc": "Cooling water flow very low"},
            {"type": "T1", "code": 21, "desc": "Turbine trip request from converter"},
        ],
        component="converter_cooling_system",
        root_cause_zh="變頻器 IGCT 水冷系統劣化：O-ring 劣化洩漏使冷卻液位下降，液位過低時冷卻泵空蝕、流量與靜水壓下降，散熱能力下降，冷卻水與變頻器機櫃溫度上升，最後由變頻器要求跳機——冷卻水溫過高（437）或流量很低（439），都伴隨 021。劣化快時多半先到溫度、慢慢洩漏時多半先到流量。",
        root_cause_en="Converter IGCT water-cooling degradation: O-ring leakage lowers the coolant level; once it is low the cooling pump cavitates, flow and static pressure fall, cooling capacity drops, and cooling-water and cabinet temperatures rise until the converter requests a trip — cooling water temperature very high (437) or flow very low (439), both with 021. A fast degradation usually reaches the temperature first, a slow leak the flow.",
        difficulty="medium",
        key_signals=(
            "WCNV_IGCTWtrTmp",
            "WCNV_IGCTWtrPres1",
            "WCOL_CoolantLvl",
            "WCNV_CnvCabinTmp",
        ),
        expected_actions_zh=(
            "依 ABB 變頻器手冊檢查冷卻水回路（手冊：Z72 手冊此類事件只寫 See [ABB]）",
            "檢查冷卻液位與洩漏點（O-ring、接頭），補液並修漏",
            "確認冷卻泵與靜水壓恢復正常後再復位",
        ),
        expected_actions_en=(
            "Inspect the converter cooling-water circuit per the ABB converter manual (manual: the Z72 manual only says See [ABB]).",
            "Check coolant level and leaks (O-rings, fittings); refill and repair.",
            "Reset only after pump and static pressure are back to normal.",
        ),
        simulation_notes_zh=(
            "流量低 / 很低（422 / 439）的設定值為模擬假設（額定流量的 90 % / 75 %，手冊只寫 See [ABB]）；冷卻水流量沒有 SCADA tag，只看得到冷卻液位、IGCT 水壓與水溫。",
        ),
        simulation_notes_en=(
            "The flow low / very low setpoints (422 / 439) are simulator assumptions (90 % / 75 % of rated flow; the manual only says See [ABB]); the cooling water flow has no SCADA tag — only the coolant level, IGCT water pressures and temperature are visible.",
        ),
    ),

    "transformer_overheat": FaultScenario(
        id="transformer_overheat",
        name_en="Transformer Overheating",
        name_zh="變壓器過熱",
        description_en="Transformer cooling degradation causing gradual temperature rise",
        description_zh="變壓器冷卻效能下降，溫度逐漸升高",
        affected_tags={
            "WGDC_TrfCoreTmp": {"max_offset": 50.0, "curve": "logarithmic"},
            "WNAC_NacTmp": {"max_offset": 5.0, "curve": "linear"},
        },
        alarm_codes=[
            {"type": "A", "code": 417, "desc": "Transformer temperature high"},
            {"type": "T1", "code": 444, "desc": "Transformer temperature very high"},
        ],
        component="transformer",
        root_cause_zh="變壓器冷卻效能下降（熱阻上升）：損耗隨功率平方增加，高負載下鐵心溫度逐漸升高，越過警報（417）與跳機（444）設定。",
        root_cause_en="Transformer cooling degradation (higher thermal resistance): losses grow with the square of power, so under high load the core temperature climbs past the alarm (417) and trip (444) setpoints.",
        difficulty="easy",
        key_signals=(
            "WGDC_TrfCoreTmp",
        ),
        expected_actions_zh=(
            "依 ABB 文件檢查變壓器溫度量測與冷卻（手冊：Z72 手冊此類事件只寫 See [ABB]）",
            "檢查變壓器通風 / 冷卻風扇",
            "高溫期間降載運轉，確認冷卻恢復後再滿載",
        ),
        expected_actions_en=(
            "Check transformer temperature measurement and cooling per the ABB documentation (manual: the Z72 manual only says See [ABB]).",
            "Inspect transformer ventilation / cooling fans.",
            "Derate while hot; return to full load once cooling is restored.",
        ),
    ),

    # ══════════════════════════════════════════════════════════════════
    # 2. SUBTLE FAULTS — gradual, cross-correlated, hard to detect
    #    These test whether a diagnosis system can catch early anomalies
    # ══════════════════════════════════════════════════════════════════

    "pitch_imbalance": FaultScenario(
        id="pitch_imbalance",
        name_en="Blade Pitch Imbalance (Subtle)",
        name_zh="葉片旋角不平衡（細微）",
        description_en="Blade 1 pitch motor has slight calibration drift. Causes 1P vibration increase and small power loss. Hard to detect from individual tags — requires cross-correlation analysis.",
        description_zh="1號葉片變槳馬達校準微小偏移。造成1P振動增加和微量功率損失。單一標籤難以偵測，需要交叉關聯分析。",
        affected_tags={
            "WROT_PtAngValBl1": {"max_offset": 3.0, "curve": "logarithmic"},    # small drift
            "WNAC_VibMsNacXDir": {"max_offset": 1.5, "curve": "quadratic"},     # subtle 1P vib
            "WNAC_VibMsNacYDir": {"max_offset": 0.8, "curve": "quadratic"},
            "WTUR_TotPwrAt": {"max_offset": -80.0, "curve": "quadratic"},       # tiny power loss
            "WGEN_GnBrgTmp1": {"max_offset": 3.0, "curve": "linear"},           # slight bearing heat
        },
        alarm_codes=[
            # Z72 沒有變槳角度偏差的 A 級警報：細微漂移在跳機前沒有任何警報，
            # 只能靠 1P 振動 / 功率交叉分析提早發現；跳機時兩組葉片同步差異同時觸發
            {"type": "T2", "code": 335, "desc": "Discrepancy blade 1-2"},
            {"type": "T2", "code": 336, "desc": "Discrepancy blade 1-3"},
        ],
        auto_trip_severity=0.90,  # takes longer to trip
        component="pitch_system_blade_1",
        root_cause_zh="1 號葉片變槳角度校準漂移：三葉片不同步造成 1P 振動與少量功率損失，跳機前沒有任何警報；葉片角度差超過 1° 持續 5 秒時 PLC 以葉片同步差異跳機（335 / 336）。",
        root_cause_en="Blade 1 pitch-angle calibration drift: the blades lose synchronisation, causing 1P vibration and a small power loss with no alarm before the trip; once the angle difference exceeds 1° for 5 s the PLC trips on blade discrepancy (335 / 336).",
        difficulty="hard",
        key_signals=(
            "WROT_PtAngValBl1",
            "WNAC_VibMsNacXDir",
            "WVIB_Band1pX",
            "WVIB_Band1pY",
        ),
        expected_actions_zh=(
            "檢查 1 號葉片變槳驅動與角度量測（編碼器 / 校準）（手冊：pitch drives OK?）",
            "檢查變槳軸承是否卡滯（手冊）",
            "重新校準葉片角度後確認三葉片同步",
        ),
        expected_actions_en=(
            "Check the blade 1 pitch drive and angle measurement (encoder / calibration) (manual: are the pitch drives OK?).",
            "Check the pitch bearing for stiffness (manual).",
            "Recalibrate the blade angle and verify all three blades are synchronised.",
        ),
    ),

    "yaw_sensor_drift": FaultScenario(
        id="yaw_sensor_drift",
        name_en="Yaw Sensor Drift (Subtle)",
        name_zh="偏航感測器漂移（細微）",
        description_en="Yaw position sensor slowly drifting. Turbine tracks wind with increasing offset. Power drops subtly relative to wind speed — detectable by comparing power curve to neighbors.",
        description_zh="偏航位置感測器緩慢漂移。風機追風角度逐漸偏移。功率相對風速微量下降 — 可透過與鄰近風機功率曲線比較來發現。",
        affected_tags={
            "WYAW_YwVn1AlgnAvg5s": {"max_offset": 12.0, "curve": "logarithmic"},
            "WTUR_TotPwrAt": {"max_offset": -200.0, "curve": "quadratic"},
            "WGEN_GnPwrMs": {"max_offset": -200.0, "curve": "quadratic"},
        },
        alarm_codes=[
            # 漂移的是風向標 1（WYAW_YwVn1AlgnAvg5s）；PLC 以風向標 1-2 差異偵測
            {"type": "T1", "code": 233, "desc": "Wind vane 1-2 discrepancy"},
        ],
        auto_trip_severity=0.95,
        component="wind_vane_1",
        category="sensor_fault",
        root_cause_zh="風向標 1 校準漂移（感測器故障）：偏航依偏移的風向追風，風向標 1 讀值看似正常，真實的偏航誤差出現在風向標 2 讀值；偏航誤差造成功率損失與塔架側向負載上升，兩風向標差異超過 15° 時 PLC 跳機（233）。",
        root_cause_en="Wind vane 1 calibration drift (sensor fault): the turbine yaws to the drifted reading, so vane 1 looks normal while the true misalignment shows on vane 2; the misalignment costs power and raises tower side-side loads, and the PLC trips once the vanes differ by more than 15° (233).",
        difficulty="hard",
        key_signals=(
            "WYAW_YwVn2AlgnAvg5s",
            "WLOD_TwrSsMom",
        ),
        expected_actions_zh=(
            "檢查兩支風向標（是否彎曲、鬆動、校準偏移）（手冊）",
            "比對兩支風向標讀值找出漂移的一支並重新校準",
            "校準後確認偏航誤差與功率曲線恢復",
        ),
        expected_actions_en=(
            "Check both wind vanes (bent, loose, or out of calibration) (manual).",
            "Compare the two vane readings to find the drifting one and recalibrate it.",
            "After calibration, verify the yaw error and power curve recover.",
        ),
    ),

    "stator_winding_degradation": FaultScenario(
        id="stator_winding_degradation",
        name_en="Stator Winding Insulation Degradation (Subtle)",
        name_zh="定子繞組絕緣劣化（細微）",
        description_en="Insulation resistance slowly decreasing. Stator temperature rises slightly faster under load. Only visible by comparing temperature-vs-power slopes over weeks. Air gap temp also affected.",
        description_zh="絕緣電阻緩慢下降。定子溫度在負載下升溫稍快。需要比較數週的溫度-功率斜率才能發現。氣隙溫度也受影響。",
        affected_tags={
            "WGEN_GnStaTmp1": {"max_offset": 20.0, "curve": "exponential"},    # key signal
            "WGEN_GnAirTmp1": {"max_offset": 8.0, "curve": "linear"},          # secondary
            "WGEN_GnCurMs": {"max_offset": 15.0, "curve": "linear"},           # slight current increase
        },
        alarm_codes=[
            # 整個繞組變熱：同一繞組的兩支 Pt100（溫度 1 / 2）都可能先越過設定（WMOM-20261021-08-a）
            {"type": "A", "code": 264, "desc": "Generator stator temperature 1 high"},
            {"type": "A", "code": 265, "desc": "Generator stator temperature 2 high"},
            {"type": "T1", "code": 244, "desc": "Generator stator temperature 1 very high"},
            {"type": "T1", "code": 245, "desc": "Generator stator temperature 2 very high"},
        ],
        auto_trip_severity=0.85,
        component="generator_stator",
        root_cause_zh="發電機定子繞組絕緣劣化：負載下額外 I²R 損耗且散熱變差，整個繞組的溫度（定子溫度 1、2）隨負載升高得比健康機組快（溫度—功率斜率改變），高負載時越過警報（264 / 265）與跳機（244 / 245）設定，低負載時看不出來。",
        root_cause_en="Generator stator winding insulation degradation: extra I²R losses under load and poorer heat conduction make the whole winding (stator temperatures 1 and 2) rise faster with load than on a healthy turbine (changed temperature-vs-power slope), crossing the alarm (264 / 265) and trip (244 / 245) setpoints at high load but not at low load.",
        difficulty="medium",
        key_signals=(
            "WGEN_GnStaTmp1",
            "WGEN_GnStaTmp2",
            "WGEN_GnAirTmp1",
        ),
        expected_actions_zh=(
            "確認是否外氣溫很高且產能很高（手冊）",
            "檢查定子溫度量測與發電機冷卻",
            "比對溫度—功率斜率與鄰機，確認是否為繞組劣化；安排絕緣電阻量測（megger），必要時降載",
            "跳機（244）或持續發生時聯絡 Harakosan（手冊）",
        ),
        expected_actions_en=(
            "Check whether the outside temperature is very high in combination with very high production (manual).",
            "Check stator temperature measurement and generator cooling.",
            "Compare the temperature-vs-power slope with neighbouring turbines to confirm winding degradation; schedule an insulation resistance test (megger) and derate if needed.",
            "After a trip (244) or if it persists, contact Harakosan (manual).",
        ),
    ),

    "hydraulic_leak": FaultScenario(
        id="hydraulic_leak",
        name_en="Yaw Brake Hydraulic Leak (Subtle)",
        name_zh="偏航煞車液壓洩漏（細微）",
        description_en="Slow hydraulic fluid leak in yaw brake system. Pressure drops gradually over days. Causes intermittent yaw slippage under high wind loads — visible as increased yaw error variance.",
        description_zh="偏航煞車系統液壓油緩慢洩漏。壓力在數天內逐漸下降。高風載下偶發偏航滑移 — 表現為偏航誤差變異增大。",
        affected_tags={
            "WYAW_YwBrkHyPrs": {"max_offset": -80.0, "curve": "linear"},       # slow pressure drop
            "WYAW_YwVn1AlgnAvg5s": {"max_offset": 5.0, "curve": "quadratic"},  # increased yaw error
            "WYAW_CabWup": {"max_offset": 0.8, "curve": "linear"},             # slight cable drift
        },
        alarm_codes=[
            # 物理層壓力 = 210 − 80·severity bar；260 手冊門檻 < 170 bar（Appendix D）→ severity ≥ 0.5
            {"type": "A", "code": 260, "desc": "Yaw brake pressure low"},
            {"type": "A", "code": 261, "desc": "Yaw brake oil leakage detected"},
            {"type": "T1", "code": 228, "desc": "Yaw brake pressure very low"},
        ],
        component="yaw_brake_hydraulics",
        root_cause_zh="偏航煞車液壓系統密封洩漏：液壓壓力逐日下降，先觸發壓力低警報（260），洩漏偵測線路壓力隨後上升（261）；高風載下偏航滑移、塔架側向負載波動增加，壓力過低時跳機（228）。",
        root_cause_en="Yaw brake hydraulic seal leakage: system pressure drops day by day, first raising the low-pressure alarm (260), then the leakage-detector line pressurises (261); under high wind load the nacelle slips in yaw, raising tower side-side load fluctuation, and at very low pressure the turbine trips (228).",
        difficulty="medium",
        key_signals=(
            "WYAW_YwBrkHyPrs",
            "WYAW_YwBrkSealsLeak",
            "WLOD_DelTwrSs",
        ),
        expected_actions_zh=(
            "檢查液壓動力單元（手冊）",
            "檢查偏航煞車是否漏油並修漏（手冊）",
            "修復後確認系統壓力回到額定",
        ),
        expected_actions_en=(
            "Check the hydraulic power unit (manual).",
            "Check the yaw brakes for leakage and fix it (manual).",
            "After repair, verify system pressure is back to nominal.",
        ),
    ),

    "blade_icing": FaultScenario(
        id="blade_icing",
        name_en="Blade Icing (Environmental)",
        name_zh="葉片結冰（環境因素）",
        description_en="Ice accumulation on blades. Causes aerodynamic imbalance: power drops, vibration increases asymmetrically, rotor speed fluctuates. Self-resolves with temperature rise.",
        description_zh="葉片上冰層累積。造成空氣動力不平衡：功率下降、振動不對稱增加、轉速波動。溫度升高後自行解除。",
        affected_tags={
            "WTUR_TotPwrAt": {"max_offset": -400.0, "curve": "logarithmic"},
            "WROT_RotSpd": {"max_offset": -3.0, "curve": "logarithmic"},
            "WNAC_VibMsNacXDir": {"max_offset": 4.0, "curve": "linear"},
            "WNAC_VibMsNacYDir": {"max_offset": 6.0, "curve": "linear"},      # asymmetric!
            "WROT_PtAngValBl1": {"max_offset": 2.0, "curve": "linear"},        # pitch compensating
            "WROT_PtAngValBl2": {"max_offset": 0.5, "curve": "linear"},
            "WROT_PtAngValBl3": {"max_offset": 0.3, "curve": "linear"},
        },
        alarm_codes=[
            # Z72 沒有結冰偵測碼：結冰只會以塔架加速度過高跳機呈現
            {"type": "T1", "code": 236, "desc": "Tower acceleration very high"},
        ],
        component="blades",
        origin="environmental",
        root_cause_zh="葉片結冰（環境因素）：冰層造成質量與氣動不平衡，功率下降、機艙振動不對稱增加，塔架加速度過高時跳機（236）；跳機前沒有結冰專用警報，氣溫回升後解除。",
        root_cause_en="Blade icing (environmental): ice causes mass and aerodynamic imbalance, so power drops and nacelle vibration rises asymmetrically until tower acceleration trips the turbine (236); Z72 has no dedicated icing alarm before the trip, and it clears when the temperature rises.",
        difficulty="medium",
        key_signals=(
            "WNAC_VibMsNacYDir",
            "WNAC_VibMsNacXDir",
            "WTUR_TotPwrAt",
        ),
        expected_actions_zh=(
            "比對同風速下功率是否明顯低於功率曲線、機艙振動是否不對稱（結冰特徵），再確認氣溫 / 濕度是否支持結冰",
            "檢查葉片是否有冰層或葉片差異（手冊：Blade discrepancies and/or very gusty wind）",
            "結冰期間停機等待除冰，確認葉片無冰後再啟動",
        ),
        expected_actions_en=(
            "Check whether power at a given wind speed is clearly below the power curve and nacelle vibration is asymmetric (icing signature), then whether temperature / humidity support icing.",
            "Inspect blades for ice or blade discrepancies (manual: Blade discrepancies and/or very gusty wind).",
            "Keep the turbine stopped until the ice is gone, then restart.",
        ),
        simulation_notes_zh=(
            "模擬的環境溫度 / 濕度不隨結冰情境調整（資料裡的氣溫可能不像結冰天氣），判斷以功率與振動特徵為主。",
            "模擬中結冰不會自行解除。",
        ),
        simulation_notes_en=(
            "Simulated ambient temperature / humidity do not follow the icing scenario (the data may not look like icing weather); judge by the power and vibration signature.",
            "Icing does not clear by itself in the simulation.",
        ),
    ),

    "grid_voltage_sag": FaultScenario(
        id="grid_voltage_sag",
        name_en="Grid Voltage Instability (External)",
        name_zh="電網電壓不穩（外部因素）",
        description_en="Grid voltage fluctuations causing converter stress. DC link voltage oscillates, power output limited. Subtle: converter cabinet temp rises due to increased switching losses.",
        description_zh="電網電壓波動造成變頻器壓力。直流電壓振盪，功率輸出受限。細微：變頻器櫃溫因開關損耗增加而升高。",
        affected_tags={
            "WCNV_CnvDClVtg": {"max_offset": -200.0, "curve": "linear"},
            "WCNV_CnvCabinTmp": {"max_offset": 8.0, "curve": "linear"},
            "WTUR_TotPwrAt": {"max_offset": -150.0, "curve": "quadratic"},
            "WCNV_CnvGnFrq": {"max_offset": -0.5, "curve": "linear"},
        },
        alarm_codes=[
            # 欠壓由 ABB 變頻器 ARU 偵測，PLC 同時收到變頻器的跳機要求（021）
            {"type": "T1", "code": 481, "desc": "Undervoltage ARU phase R-S low"},
            {"type": "T1", "code": 21, "desc": "Turbine trip request from converter"},
        ],
        component="grid_connection",
        origin="external_grid",
        root_cause_zh="機組併網端電壓下陷 / 振盪（外部電網或饋線因素，非機組元件故障）：變頻器輸出受限、無效功率支援增加，電壓低於低電壓穿越帶持續過久時變頻器欠壓保護跳機並要求機組跳機（481 + 021）。",
        root_cause_en="Voltage sag / oscillation at the turbine's grid connection (external grid or feeder, not a turbine component fault): converter output is limited and reactive support rises; when voltage stays below the low-voltage ride-through band too long, the converter undervoltage protection trips and requests a turbine trip (481 + 021).",
        difficulty="medium",
        key_signals=(
            "WGEN_GnVtgMs",
            "WCNV_VtgMsCnvGd1",
            "WCNV_ReactPwr",
            "WTUR_TotPwrAt",
        ),
        expected_actions_zh=(
            "比對本機、鄰機與變電站的電壓紀錄：多機同時下陷為電網事件；只有本機下陷時檢查本機的饋線、併網電纜與開關",
            "依 ABB 變頻器手冊檢查欠壓保護事件（手冊：Z72 手冊此類事件只寫 See [ABB]）",
            "電壓恢復後復位，不需更換機組元件",
        ),
        expected_actions_en=(
            "Compare voltage records of this turbine, its neighbours and the substation: a simultaneous sag points to the grid; a sag on this turbine only points to its feeder, grid cable or switchgear.",
            "Check the undervoltage protection event per the ABB converter manual (manual: the Z72 manual only says See [ABB]).",
            "Reset once the voltage recovers; no turbine component replacement needed.",
        ),
        simulation_notes_zh=(
            "模擬只讓被注入的這台機組端子電壓下陷，鄰機電壓正常。",
        ),
        simulation_notes_en=(
            "Only the injected turbine's terminal voltage sags in the simulation; neighbouring turbines see normal voltage.",
        ),
    ),

    # ══════════════════════════════════════════════════════════════════
    # 3. COMPOUND FAULTS — multiple simultaneous issues (hardest to diagnose)
    # ══════════════════════════════════════════════════════════════════

    "nacelle_cooling_failure": FaultScenario(
        id="nacelle_cooling_failure",
        name_en="Nacelle Cooling System Failure (Compound)",
        name_zh="機艙冷卻系統故障（複合型）",
        description_en="Main nacelle ventilation failure. Multiple component temperatures rise together but at different rates. Challenging to isolate root cause from individual component monitoring.",
        description_zh="主要機艙通風失效。多個組件溫度一起上升但速率不同。從個別組件監控難以確定根因。",
        affected_tags={
            "WNAC_NacTmp": {"max_offset": 20.0, "curve": "logarithmic"},
            "WNAC_NacCabTmp": {"max_offset": 18.0, "curve": "logarithmic"},
            "WGEN_GnStaTmp1": {"max_offset": 12.0, "curve": "linear"},
            "WGEN_GnBrgTmp1": {"max_offset": 8.0, "curve": "linear"},
            "WCNV_CnvCabinTmp": {"max_offset": 10.0, "curve": "linear"},
            "WCNV_IGCTWtrTmp": {"max_offset": 5.0, "curve": "linear"},
        },
        alarm_codes=[
            {"type": "A", "code": 273, "desc": "Nacelle temperature range exceeded"},
            {"type": "T1", "code": 256, "desc": "Nacelle cabinet temperature outside range"},
        ],
        component="nacelle_ventilation",
        root_cause_zh="機艙主通風系統失效（複合型）：機艙空氣、控制櫃、變頻器機櫃、發電機等多個溫度同時以不同速率上升，根因是通風而非個別元件；機艙溫度超出範圍警報（273）、控制櫃溫度超出範圍跳機（256）。",
        root_cause_en="Main nacelle ventilation failure (compound): nacelle air, control cabinet, converter cabinet and generator temperatures all rise at different rates; the root cause is ventilation, not any single component; nacelle temperature out of range alarm (273) and cabinet temperature trip (256).",
        difficulty="hard",
        key_signals=(
            "WNAC_NacTmp",
            "WNAC_NacCabTmp",
            "WCNV_CnvCabinTmp",
            "WGEN_GnStaTmp1",
        ),
        expected_actions_zh=(
            "檢查機艙通風風扇與進出風口（濾網堵塞、風扇故障）",
            "確認多個元件同時升溫指向共同原因（通風），不要逐一更換元件",
            "等待溫度回到可運轉範圍後再啟動（手冊）",
        ),
        expected_actions_en=(
            "Check nacelle ventilation fans and air inlets/outlets (clogged filters, failed fans).",
            "Recognise that several components heating together points to a common cause (ventilation); do not replace components one by one.",
            "Restart only once temperatures are back in the operating range (manual).",
        ),
    ),

    # ══════════════════════════════════════════════════════════════════
    # 感測器故障（WMOM-20261021-08-a）：只改那支感測器的量測值，機器本身正常
    # 標準答案的 component 是被量測的元件、category 是 sensor_fault（與真故障同元件、不同類別）
    # ══════════════════════════════════════════════════════════════════

    # 讀值像真故障：與 bearing_wear 同樣的警報 / 跳機碼，要靠其他訊號分辨
    "main_bearing_temp_sensor_drift": FaultScenario(
        id="main_bearing_temp_sensor_drift",
        name_en="Main Bearing 1 Temperature Sensor Drift",
        name_zh="主軸承溫度 1 感測器漂移",
        description_en="The bearing 1 Pt100 reading drifts upward while the bearing itself is healthy. Raises the same alarm and trip as real bearing wear; bearing 2 temperature, vibration and kurtosis stay normal (real wear lifts them).",
        description_zh="軸承溫度 1 的 Pt100 讀值逐漸往上漂，軸承本身正常。觸發與軸承磨耗相同的警報 / 跳機；軸承溫度 2、振動與峰度都正常。",
        affected_tags={
            "WGEN_GnBrgTmp1": {"max_offset": 60.0, "curve": "linear"},
        },
        alarm_codes=[
            {"type": "A", "code": 262, "desc": "Main bearing 1 temperature high"},
            {"type": "T1", "code": 240, "desc": "Bearing 1 temperature very high"},
        ],
        component="main_bearing",
        category="sensor_fault",
        root_cause_zh="主軸承溫度 1 的 Pt100 量測回路接觸電阻逐漸增加（端子鬆動 / 接點氧化，感測器故障）：讀值比實際溫度高，且偏差逐漸變大，PLC 依讀值送出軸承溫度高警報（262）與跳機（240）；軸承本身正常——軸承溫度 2、機艙振動與峰度都沒有變化，讀值與實際溫度的差也不隨轉速 / 負載改變（真的主軸承磨耗會隨轉速增加摩擦熱，軸承溫度 2 跟著升溫、振動與峰度上升）。",
        root_cause_en="Rising contact resistance in the main bearing temperature 1 Pt100 measuring circuit (loose terminal / oxidised contact, sensor fault): the reading is higher than the real temperature by a growing offset, so the PLC raises the bearing temperature alarm (262) and trip (240) from the reading; the bearing itself is fine — bearing temperature 2, nacelle vibration and kurtosis do not change, and the excess does not scale with speed or load (real main bearing wear adds friction heat with speed, lifts bearing temperature 2 too and raises vibration and kurtosis).",
        difficulty="hard",
        key_signals=(
            "WGEN_GnBrgTmp1",
        ),
        expected_actions_zh=(
            "比對軸承溫度 1 與軸承溫度 2、振動與峰度：只有溫度 1 偏高、其他正常時，先懷疑感測器而不是軸承",
            "依手冊檢查主軸承潤滑與冷卻風扇（手冊），排除真的過熱",
            "檢查軸承溫度 1 的 Pt100 端子與配線（量測回路電阻），以參考溫度計比對，必要時更換感測器",
            "讀值恢復正常後再復機，不必更換軸承",
        ),
        expected_actions_en=(
            "Compare bearing temperature 1 with bearing temperature 2, vibration and kurtosis: if only temperature 1 is high and the rest is normal, suspect the sensor before the bearing.",
            "Check main bearing lubrication and the cooling fan per the manual (manual) to rule out real overheating.",
            "Check the bearing temperature 1 Pt100 terminals and wiring (loop resistance), compare against a reference thermometer and replace the sensor if needed.",
            "Restart once the reading is plausible again; the bearing does not need replacing.",
        ),
        simulation_notes_zh=(
            "讀值＝實際溫度＋偏移，偏移隨嚴重度線性增加到 60 °C；機組停機冷卻時讀值一樣下降（偏移不變）。真實的接觸電阻劣化通常歷時數週到數月。",
        ),
        simulation_notes_en=(
            "Reading = real temperature + an offset that grows linearly with severity up to 60 °C; when the turbine stops and cools the reading falls too (the offset stays). Real contact degradation usually takes weeks to months.",
        ),
    ),

    # 讀值像真故障：與 stator_winding_degradation 同樣的警報 / 跳機碼
    "stator_temp_sensor_drift": FaultScenario(
        id="stator_temp_sensor_drift",
        name_en="Generator Stator Temperature 1 Sensor Drift",
        name_zh="發電機定子溫度 1 感測器漂移",
        description_en="The stator temperature 1 Pt100 reading drifts upward while the winding is healthy. Raises the same alarm and trip as winding degradation at high load; stator temperature 2 and air-gap temperature stay normal.",
        description_zh="定子溫度 1 的 Pt100 讀值逐漸往上漂，繞組本身正常。高負載時觸發與繞組劣化相同的警報 / 跳機；定子溫度 2 與氣隙溫度都正常。",
        affected_tags={
            "WGEN_GnStaTmp1": {"max_offset": 100.0, "curve": "linear"},
        },
        alarm_codes=[
            {"type": "A", "code": 264, "desc": "Generator stator temperature 1 high"},
            {"type": "T1", "code": 244, "desc": "Generator stator temperature 1 very high"},
        ],
        component="generator_stator",
        category="sensor_fault",
        root_cause_zh="發電機定子溫度 1 的 Pt100 量測回路接觸電阻逐漸增加（端子鬆動 / 接點氧化，感測器故障）：讀值比實際溫度高、偏差逐漸變大，高負載時越過警報（264）與跳機（244）設定；繞組本身正常——同一繞組另一個槽的定子溫度 2、氣隙溫度都沒有變化（真的絕緣劣化會讓整個繞組變熱，兩支定子溫度與氣隙溫度一起上升）。",
        root_cause_en="Rising contact resistance in the generator stator temperature 1 Pt100 measuring circuit (loose terminal / oxidised contact, sensor fault): the reading is higher than the real temperature by a growing offset and crosses the alarm (264) and trip (244) setpoints at high load; the winding is fine — stator temperature 2 in another slot of the same winding and the air-gap temperature do not change (real insulation degradation heats the whole winding, so both stator temperatures and the air gap rise together).",
        difficulty="hard",
        key_signals=(
            "WGEN_GnStaTmp1",
        ),
        expected_actions_zh=(
            "確認是否外氣溫很高且產能很高（手冊）",
            "比對定子溫度 1 與定子溫度 2、氣隙溫度：只有溫度 1 偏高時，先懷疑感測器而不是繞組",
            "檢查定子溫度 1 的 Pt100 端子與配線（量測回路電阻），必要時改用備用的定子溫度感測器",
            "讀值恢復正常後再復機，不必做繞組維修",
        ),
        expected_actions_en=(
            "Check whether the outside temperature is very high in combination with very high production (manual).",
            "Compare stator temperature 1 with stator temperature 2 and the air-gap temperature: if only temperature 1 is high, suspect the sensor before the winding.",
            "Check the stator temperature 1 Pt100 terminals and wiring (loop resistance), or switch to a spare stator temperature sensor.",
            "Restart once the reading is plausible again; no winding repair is needed.",
        ),
        simulation_notes_zh=(
            "讀值＝實際溫度＋偏移，偏移隨嚴重度線性增加到 100 °C；低負載時實際溫度低，讀值仍可能在警報設定以下。真實的接觸電阻劣化通常歷時數週到數月。",
        ),
        simulation_notes_en=(
            "Reading = real temperature + an offset that grows linearly with severity up to 100 °C; at low load the real temperature is low, so the reading may stay below the alarm setpoint. Real contact degradation usually takes weeks to months.",
        ),
    ),

    # 專屬故障碼：I/O 模組偵測到斷線
    "main_bearing_temp_sensor_wire_break": FaultScenario(
        id="main_bearing_temp_sensor_wire_break",
        name_en="Main Bearing 1 Temperature Sensor Broken Wire",
        name_zh="主軸承溫度 1 感測器斷線",
        description_en="The wiring of the bearing 1 Pt100 breaks: the I/O module flags a broken wire and the reading jumps to full scale. The PLC trips with the dedicated bearing temperature fault event.",
        description_zh="軸承溫度 1 的 Pt100 配線斷開：I/O 模組偵測到斷線，讀值跳到滿刻度。PLC 以專屬的軸承溫度故障事件跳機。",
        affected_tags={
            "WGEN_GnBrgTmp1": {"max_offset": 800.0, "curve": "linear"},
        },
        alarm_codes=[
            {"type": "T1", "code": 242, "desc": "Bearing 1 temperature fault"},
        ],
        auto_trip_severity=0.5,
        component="main_bearing",
        category="sensor_fault",
        root_cause_zh="主軸承溫度 1 的 Pt100 感測器配線斷開（感測器故障）：I/O 模組偵測到斷線，讀值跳到滿刻度，PLC 送出軸承溫度 1 故障（242）跳機；軸承本身正常，軸承溫度 2 與振動都沒有變化。",
        root_cause_en="Broken wiring of the main bearing temperature 1 Pt100 sensor (sensor fault): the I/O module senses a broken wire, the reading jumps to full scale and the PLC trips with bearing 1 temperature fault (242); the bearing itself is fine and bearing temperature 2 and vibration do not change.",
        difficulty="easy",
        key_signals=(
            "WGEN_GnBrgTmp1",
        ),
        expected_actions_zh=(
            "檢查軸承溫度 1 的 Pt100 配線（手冊）",
            "量測感測器電阻確認是配線還是感測器本身開路，修復或更換",
            "確認讀值恢復合理範圍後復機",
        ),
        expected_actions_en=(
            "Check the wiring to the bearing temperature 1 Pt100 sensor (manual).",
            "Measure the sensor resistance to tell a broken wire from an open sensor element; repair or replace.",
            "Restart once the reading is back in a plausible range.",
        ),
        simulation_notes_zh=(
            "斷線在嚴重度到 0.5 時發生，之前讀值正常；斷線後讀值固定為 850 °C（模擬假設的 Pt100 開路滿刻度讀值，實際依 I/O 模組設定）。",
        ),
        simulation_notes_en=(
            "The wire breaks when severity reaches 0.5 and the reading is normal before that; afterwards it is pinned at 850 °C (a simulator assumption for an open Pt100 at full scale; real modules depend on their configuration).",
        ),
    ),

    # nuisance（WMOM-20261021-08-b）：手冊 §11.3 點名的已知無害跳機，與上面的斷線送同一個碼
    "main_bearing_temp_loose_contact": FaultScenario(
        id="main_bearing_temp_loose_contact",
        name_en="Main Bearing 1 Pt100 Loose Contact (Nuisance)",
        name_zh="主軸承溫度 1 Pt100 接觸不良（nuisance）",
        description_en="A loose connection on the bearing 1 Pt100 opens for a few seconds every so often: each time the I/O module flags a broken wire, the PLC trips with the bearing temperature fault and the turbine restarts once the contact closes again. The manual (§11.3) names this as a known harmless nuisance trip.",
        description_zh="軸承溫度 1 的 Pt100 接點鬆動，偶爾斷開幾秒：每次 I/O 模組都偵測到斷線、PLC 以軸承溫度故障跳機，接點接回後自動重啟。手冊 §11.3 點名這是已知無害的 nuisance 跳機。",
        affected_tags={
            "WGEN_GnBrgTmp1": {"max_offset": 800.0, "curve": "linear"},
        },
        alarm_codes=[
            {"type": "T1", "code": 242, "desc": "Bearing 1 temperature fault"},
        ],
        component="main_bearing",
        category="nuisance",
        nuisance_cause="loose_contact",
        root_cause_zh="主軸承溫度 1 的 Pt100 接點鬆動（nuisance 跳機）：每隔一陣子斷開幾秒，PLC 每次都送軸承溫度 1 故障（242）跳機，接回後讀值正常、機組自動重啟；軸承本身與其他訊號都正常。一小時內超過自動重啟上限時會送 A039、要操作員復位。手冊 §11.3 把 Pt100 鬆線列為已知無害、可設定自動重啟的 nuisance 跳機。",
        root_cause_en="A loose contact on the main bearing temperature 1 Pt100 (nuisance trip): every so often it opens for a few seconds, the PLC trips with bearing 1 temperature fault (242) each time, and once it closes again the reading is normal and the turbine restarts; the bearing and all other signals are fine. Exceeding the auto-restart limit within an hour raises A039 and needs an operator reset. The manual (§11.3) lists a loose Pt100 wire as a known harmless nuisance trip that can be given an auto-restart setting.",
        difficulty="hard",
        key_signals=(
            "WGEN_GnBrgTmp1",
        ),
        expected_actions_zh=(
            "檢查軸承溫度 1 的 Pt100 配線與端子是否鬆動（手冊）",
            "看 242 的模式：短暫跳機後讀值立刻正常、反覆出現，且軸承溫度 2 與振動正常，是接觸不良而不是軸承或感測器壞掉",
            "鎖緊接點；修好前可依手冊把這個跳機的自動重啟次數設高（手冊 §11.3），修好後改回 0",
        ),
        expected_actions_en=(
            "Check the bearing temperature 1 Pt100 wiring and terminals for a loose connection (manual).",
            "Look at the 242 pattern: brief trips with a normal reading right after, recurring, while bearing temperature 2 and vibration are normal, point to a loose contact rather than a failed bearing or sensor.",
            "Tighten the connection; until it is fixed, the auto-restart setting for this trip can be raised as the manual describes (§11.3) and set back to 0 afterwards.",
        ),
        simulation_notes_zh=(
            "注入後 5–20 分鐘第一次瞬斷，之後每 15–45 分鐘一次、每次 10–30 秒；瞬斷時讀值同斷線（850 °C），與嚴重度無關。",
            "模擬器假設這個跳機的自動重啟已開啟（上限照手冊 Appendix C 的每小時次數；手冊 §11.3 的出廠設定是 0）。",
        ),
        simulation_notes_en=(
            "The first glitch comes 5–20 min after injection, then every 15–45 min for 10–30 s each; during a glitch the reading is the broken-wire value (850 °C), independent of severity.",
            "The simulator assumes auto restart is enabled for this trip (limited per hour as in the manual's Appendix C; the factory setting in §11.3 is 0).",
        ),
    ),

    # 專屬故障碼：編碼器讀值超出範圍
    "blade1_pitch_encoder_fault": FaultScenario(
        id="blade1_pitch_encoder_fault",
        name_en="Blade 1 Pitch Encoder Fault",
        name_zh="葉片 1 變槳編碼器故障",
        description_en="The blade 1 pitch encoder fails and reports an angle outside its range while the blade itself is positioned normally. The PLC trips with an emergency stop on the encoder fault event.",
        description_zh="葉片 1 的變槳編碼器故障，回報超出範圍的角度，葉片本身位置正常。PLC 以編碼器故障事件緊急停機。",
        affected_tags={
            "WROT_PtAngValBl1": {"max_offset": 135.0, "curve": "linear"},
        },
        alarm_codes=[
            {"type": "T2", "code": 326, "desc": "Encoder blade 1 fault"},
        ],
        auto_trip_severity=0.5,
        component="pitch_system_blade_1",
        category="sensor_fault",
        root_cause_zh="葉片 1 變槳角度編碼器故障（感測器故障）：編碼器回報的角度超出有效範圍，PLC 送出葉片 1 編碼器故障（326）緊急停機；葉片 1 的實際位置與變槳驅動正常，另外兩支葉片的角度一致。",
        root_cause_en="Blade 1 pitch angle encoder fault (sensor fault): the encoder reports an angle outside its valid range and the PLC trips with an emergency stop on encoder blade 1 fault (326); blade 1's actual position and its pitch drive are fine, and the other two blades agree with each other.",
        difficulty="easy",
        key_signals=(
            "WROT_PtAngValBl1",
        ),
        expected_actions_zh=(
            "檢查葉片 1 編碼器的配線（手冊）",
            "檢查葉片 1 編碼器的校正（手冊）",
            "以手動變槳確認葉片 1 實際角度與另外兩支一致後，更換或重新校正編碼器再復機",
        ),
        expected_actions_en=(
            "Check the wiring to the encoder of blade 1 (manual).",
            "Check the calibration of the blade 1 encoder (manual).",
            "Pitch blade 1 by hand to confirm its real angle matches the other two, then replace or recalibrate the encoder before restarting.",
        ),
        simulation_notes_zh=(
            "故障在嚴重度到 0.5 時發生，之前讀值正常；故障後讀值固定為 135°（模擬假設的超出範圍讀值）。變槳控制仍照實際角度運作，只有量測值錯。",
        ),
        simulation_notes_en=(
            "The fault occurs when severity reaches 0.5 and the reading is normal before that; afterwards it is pinned at 135° (a simulator assumption for an out-of-range reading). Pitch control keeps working on the real angle; only the measurement is wrong.",
        ),
    ),

    # 專屬故障碼：壓力感測器斷線；與 hydraulic_leak 同元件
    "yaw_brake_pressure_sensor_fault": FaultScenario(
        id="yaw_brake_pressure_sensor_fault",
        name_en="Yaw Brake Pressure Sensor Broken Wire",
        name_zh="偏航煞車壓力感測器斷線",
        description_en="The wiring of the yaw brake hydraulic pressure transmitter breaks: the reading drops below the 4-20 mA range. The PLC trips with the dedicated pressure sensor fault event instead of the low-pressure events of a real leak.",
        description_zh="偏航煞車液壓壓力傳送器的配線斷開：讀值掉到 4-20 mA 範圍以下。PLC 以專屬的壓力感測器故障事件跳機，而不是真漏油時的壓力低事件。",
        affected_tags={
            "WYAW_YwBrkHyPrs": {"max_offset": -270.0, "curve": "linear"},
        },
        alarm_codes=[
            {"type": "T1", "code": 229, "desc": "Yaw brake pressure sensor fault"},
        ],
        auto_trip_severity=0.5,
        component="yaw_brake_hydraulics",
        category="sensor_fault",
        root_cause_zh="偏航煞車液壓壓力傳送器配線斷開（感測器故障）：I/O 模組偵測到斷線，讀值掉到量測範圍以下，PLC 送出偏航煞車壓力感測器故障（229）跳機；液壓系統本身正常——沒有洩漏偵測（261）、偏航沒有滑移（真漏油是壓力逐日下降，先出 260 再出 228）。",
        root_cause_en="Broken wiring of the yaw brake hydraulic pressure transmitter (sensor fault): the I/O module senses a broken wire, the reading falls below the measuring range and the PLC trips with yaw brake pressure sensor fault (229); the hydraulics are fine — no leakage detection (261) and no yaw slippage (a real leak lowers pressure over days and raises 260 before 228).",
        difficulty="easy",
        key_signals=(
            "WYAW_YwBrkHyPrs",
        ),
        expected_actions_zh=(
            "檢查液壓壓力感測器的配線（手冊）",
            "以液壓動力單元上的壓力錶確認實際系統壓力正常",
            "修復配線或更換壓力傳送器後復機",
        ),
        expected_actions_en=(
            "Check the wiring to the hydraulic pressure sensor (manual).",
            "Confirm the real system pressure on the hydraulic power unit's gauge is normal.",
            "Repair the wiring or replace the pressure transmitter, then restart.",
        ),
        simulation_notes_zh=(
            "斷線在嚴重度到 0.5 時發生，之前讀值正常；斷線後讀值固定為 −62.5 bar（4-20 mA、0-250 bar 傳送器在 0 mA 時的讀值，模擬假設）。",
        ),
        simulation_notes_en=(
            "The wire breaks when severity reaches 0.5 and the reading is normal before that; afterwards it is pinned at −62.5 bar (the reading of a 4-20 mA, 0-250 bar transmitter at 0 mA, a simulator assumption).",
        ),
    ),

    # ══════════════════════════════════════════════════════════════════
    # 故障庫擴充（WMOM-20261021-08-c）：變槳驅動、冷卻水、量測感測器、偏航對風
    # ══════════════════════════════════════════════════════════════════

    "pitch_motor_fault": FaultScenario(
        id="pitch_motor_fault",
        name_en="Blade 1 Pitch Drive Overload (Bearing / Gear Friction)",
        name_zh="葉片 1 變槳驅動過載（軸承 / 齒輪摩擦）",
        description_en="Lubrication of the blade 1 pitch bearing / pitch gear deteriorates: the DC pitch motor needs more current for the same pitch action. Blade 1's motor current climbs above blades 2 and 3, the drive's I2t current limiter warns first, then the PLC trips on pitch motor overload.",
        description_zh="葉片 1 變槳軸承 / 變槳齒輪潤滑劣化，直流變槳馬達做同樣的變槳動作要更大的電流。葉片 1 馬達電流逐漸高於葉片 2、3，先出驅動器 I2t 限流警報，最後 PLC 以變槳馬達過載跳機。",
        affected_tags={
            "WROT_PtMotCurBl1": {"max_offset": 16.0, "curve": "linear"},
        },
        alarm_codes=[
            {"type": "A", "code": 381, "desc": "I2t protection servo drive 1 active"},
            {"type": "T1", "code": 367, "desc": "Pitch motor blade 1 overload"},
        ],
        component="pitch_system_blade_1",
        root_cause_zh="葉片 1 變槳軸承 / 變槳齒輪摩擦增加（潤滑劣化）：直流變槳馬達要用更大的電流才能維持同樣的變槳動作，葉片 1 的馬達電流明顯高於葉片 2、3（多出的電流固定，總電流隨負載增加，所以高負載時先到限值）；RMS 電流超過驅動器連續額定時 I2t 限流警報（381），電流平均值超過手冊限值（10 分鐘 > 18 A、60 秒 > 20 A、5 秒 > 22 A）時 PLC 以葉片 1 變槳馬達過載（367）跳機。葉片角度與同步正常——不是校正漂移。",
        root_cause_en="Increased friction in the blade 1 pitch bearing / pitch gear (deteriorating lubrication): the DC pitch motor needs more current for the same pitch action, so blade 1's motor current is clearly above blades 2 and 3 (a constant excess on top of a total that rises with load, so high load reaches the limits first). When the RMS current exceeds the drive's continuous rating the I2t current limiter warns (381); when the averaged current exceeds the manual's limits (10 min > 18 A, 60 s > 20 A, 5 s > 22 A) the PLC trips on pitch motor blade 1 overload (367). Blade angles and synchronisation are normal — this is not a calibration drift.",
        difficulty="medium",
        key_signals=(
            "WROT_PtMotCurBl1",
        ),
        expected_actions_zh=(
            "檢查葉片 1 的變槳馬達與變槳齒輪（手冊）",
            "I2t 警報太頻繁表示葉片 1 有機械問題（手冊）",
            "比較三支葉片的馬達電流；檢查變槳軸承與齒輪的潤滑（含變槳軸承潤滑系統），修復後確認葉片 1 電流回到與另外兩支相同",
        ),
        expected_actions_en=(
            "Check the blade 1 pitch motor and pitch gear (manual).",
            "Too frequent I2t alarms indicate a mechanical problem of blade 1 (manual).",
            "Compare the three blades' motor currents; check pitch bearing and gear lubrication (including the pitch bearing grease system), and after the repair confirm blade 1's current matches the other two.",
        ),
        simulation_notes_zh=(
            "變槳馬達電流是模擬假設的模型（通電時基本電流＋隨推力的氣動扭矩＋隨變槳速度）；I2t 限流的連續電流 14 A 與時間常數 60 s 為模擬假設（手冊只寫 See [Control Techniques]），過載限值照手冊 Appendix D。",
            "I2t 限流在模擬中不會讓葉片 1 變慢，所以不會連帶出現葉片同步差異（335 / 336）。",
            "跳機後葉片停在順槳、馬達電流歸零，電流平均值下降，367 約一分鐘後解除（trip_cleared）；故障還在，機組由維修鎖擋住、不會自己重啟。",
        ),
        simulation_notes_en=(
            "The pitch motor current is a simulator model (base current when energised + aerodynamic torque with thrust + pitch speed); the I2t limiter's 14 A continuous current and 60 s time constant are simulator assumptions (the manual only says see [Control Techniques]); the overload limits follow the manual's Appendix D.",
            "In the simulator the I2t limiter does not slow blade 1, so no blade discrepancy (335 / 336) follows.",
            "After the trip the blades park in vane and the motor current drops to zero, so the averages fall and 367 clears after about a minute (trip_cleared); the fault is still there and the maintenance lock keeps the turbine from restarting.",
        ),
    ),

    "converter_cooling_pump_wear": FaultScenario(
        id="converter_cooling_pump_wear",
        name_en="Converter Cooling Water Pump Wear",
        name_zh="變頻器冷卻水泵磨耗",
        description_en="The converter cooling water pump's impeller wears: flow and loop pressure fall while the coolant level stays full. The ABB cooling unit warns of low flow, then low static pressure, and trips the converter on very low flow; the IGCT water runs a few degrees warmer.",
        description_zh="變頻器冷卻水泵葉輪磨耗：流量與迴路壓力下降，冷卻液位維持滿。ABB 冷卻單元先出流量低、靜水壓低警報，流量很低時要求變頻器跳機；IGCT 水溫高出幾度。",
        affected_tags={
            "WCNV_IGCTWtrPres1": {"max_offset": -2.6, "curve": "quadratic"},
            "WCNV_IGCTWtrPres2": {"max_offset": -2.5, "curve": "quadratic"},
            "WCNV_IGCTWtrTmp": {"max_offset": 7.0, "curve": "quadratic"},
        },
        alarm_codes=[
            {"type": "A", "code": 422, "desc": "Cooling water flow low"},
            {"type": "A", "code": 432, "desc": "Static water pressure L"},
            {"type": "T1", "code": 439, "desc": "Cooling water flow very low"},
            {"type": "T1", "code": 21, "desc": "Turbine trip request from converter"},
        ],
        auto_trip_severity=0.75,
        component="converter_cooling_system",
        root_cause_zh="變頻器冷卻水泵葉輪磨耗：泵送流量與迴路壓力逐漸下降（壓力約隨流量平方），冷卻液位正常、沒有洩漏；流量低於額定約九成時冷卻水流量低警報（422），壓力再低出靜水壓低（432），流量很低時變頻器要求跳機（439 + 021）。流量不足使 IGCT 冷卻水溫比平常高幾度，但通常在溫度警報之前就先跳機。",
        root_cause_en="Worn converter cooling water pump impeller: pump flow and loop pressure fall gradually (pressure roughly with flow squared) while the coolant level is normal and nothing leaks; below about 90 % of rated flow the cooling water flow low alarm (422) comes, with lower pressure the static water pressure low alarm (432), and at very low flow the converter requests a trip (439 + 021). The reduced flow runs the IGCT cooling water a few degrees warmer, but the trip usually comes before any temperature alarm.",
        difficulty="medium",
        key_signals=(
            "WCNV_IGCTWtrPres1",
            "WCNV_IGCTWtrPres2",
            "WCNV_IGCTWtrTmp",
        ),
        expected_actions_zh=(
            "依 ABB 變頻器手冊檢查冷卻水流量與泵（手冊：Z72 手冊此類事件只寫 See [ABB]）",
            "確認冷卻液位正常、沒有洩漏（與漏水造成的壓力低區分）",
            "檢查冷卻水泵（葉輪磨耗、馬達、過濾器堵塞），修復或更換後確認流量與壓力恢復再復位",
        ),
        expected_actions_en=(
            "Check the cooling water flow and pump per the ABB converter manual (manual: the Z72 manual only says See [ABB]).",
            "Confirm the coolant level is normal and nothing leaks (to tell it apart from a leak-driven pressure drop).",
            "Inspect the cooling water pump (impeller wear, motor, clogged filter); after repair or replacement confirm flow and pressure are back before resetting.",
        ),
        simulation_notes_zh=(
            "流量低 / 很低的設定值（額定的 90 % / 75 %）為模擬假設（手冊只寫 See [ABB]）；冷卻水流量沒有 SCADA tag，只看得到隨流量下降的 IGCT 水壓與水溫。",
            "模擬的靜水壓低（432）判的是迴路壓力 WCNV_IGCTWtrPres1，所以泵磨耗也會觸發。",
        ),
        simulation_notes_en=(
            "The flow low / very low setpoints (90 % / 75 % of rated) are simulator assumptions (the manual only says See [ABB]); the cooling water flow has no SCADA tag — only the IGCT water pressures and temperature that follow it are visible.",
            "The simulator's static water pressure low (432) is judged on the loop pressure WCNV_IGCTWtrPres1, so pump wear triggers it too.",
        ),
    ),

    "cooling_water_deionizer_exhausted": FaultScenario(
        id="cooling_water_deionizer_exhausted",
        name_en="Converter Cooling Water Deionizer Exhausted",
        name_zh="變頻器冷卻水去離子樹脂耗盡",
        description_en="The ion exchange resin of the converter's deionized cooling water loop is used up: the water's conductivity climbs over days. The ABB cooling unit warns of high conductivity and trips the converter when it gets very high; temperatures, pressures and flow stay normal.",
        description_zh="變頻器去離子冷卻水迴路的離子交換樹脂耗盡：冷卻水導電度在幾天內逐漸上升。ABB 冷卻單元先出導電度高警報，很高時要求變頻器跳機；溫度、壓力、流量都正常。",
        affected_tags={
            "WCNV_IGCTWtrCond": {"max_offset": 1.2, "curve": "quadratic"},
        },
        alarm_codes=[
            {"type": "A", "code": 423, "desc": "Cooling water conductivity high"},
            {"type": "T1", "code": 440, "desc": "Cooling water conductivity very high"},
            {"type": "T1", "code": 21, "desc": "Turbine trip request from converter"},
        ],
        component="converter_cooling_system",
        root_cause_zh="變頻器冷卻水的去離子樹脂（離子交換器）耗盡：冷卻水導電度逐漸上升（水溫高時讀值也較高），IGCT 的漏電風險增加；超過警報值出冷卻水導電度高（423），再高時變頻器要求跳機（440 + 021）。冷卻水溫度、壓力與流量正常。",
        root_cause_en="The deionizer (ion exchange resin) of the converter cooling water is exhausted: the water's conductivity climbs gradually (reading higher when the water is warmer), raising the IGCT leakage-current risk; above the alarm value the cooling water conductivity high alarm (423) comes, and higher still the converter requests a trip (440 + 021). Cooling water temperature, pressure and flow are normal.",
        difficulty="easy",
        key_signals=(
            "WCNV_IGCTWtrCond",
        ),
        expected_actions_zh=(
            "依 ABB 變頻器手冊處理冷卻水導電度（手冊：Z72 手冊此類事件只寫 See [ABB]）",
            "更換去離子樹脂（離子交換器濾芯），必要時換冷卻水",
            "確認導電度降回正常值後再復位",
        ),
        expected_actions_en=(
            "Handle the cooling water conductivity per the ABB converter manual (manual: the Z72 manual only says See [ABB]).",
            "Replace the deionizer resin (ion exchange cartridge) and, if needed, the cooling water.",
            "Reset only after the conductivity is back to normal.",
        ),
        simulation_notes_zh=(
            "導電度的健康值（25 °C 時 0.15–0.25 µS/cm、每 °C 約 +2 %）與警報 / 跳機設定值（0.5 / 1.0 µS/cm）為模擬假設（手冊只寫 See [ABB]）。",
        ),
        simulation_notes_en=(
            "The healthy conductivity (0.15–0.25 µS/cm at 25 °C, about +2 % per °C) and the alarm / trip setpoints (0.5 / 1.0 µS/cm) are simulator assumptions (the manual only says See [ABB]).",
        ),
    ),

    # 感測器故障（-08-a 機制）：讀值錯、機器本身正常
    "rotor_speed_sensor_fault": FaultScenario(
        id="rotor_speed_sensor_fault",
        name_en="Rotor Speed Sensor Fault (Loose Encoder Connection)",
        name_zh="轉子轉速感測器故障（編碼器接線鬆動）",
        description_en="The connection of the rotor speed encoder in the hub works loose: the PLC's rotor speed misses pulses and reads progressively low while the converter's generator speed is right. Once the two differ by more than 10 % the PLC trips.",
        description_zh="輪轂內轉子轉速編碼器的接線鬆動：PLC 量到的轉子轉速漏脈波、越讀越低，變頻器量到的發電機轉速正確。兩者差超過 10 % 時 PLC 跳機。",
        affected_tags={
            "WROT_RotSpd": {"max_offset": -7.0, "curve": "quadratic"},
        },
        alarm_codes=[
            {"type": "T1", "code": 29, "desc": "Rotor speed sensor fault"},
        ],
        auto_trip_severity=0.6,
        component="rotor_speed_sensor",
        category="sensor_fault",
        root_cause_zh="輪轂內轉子轉速編碼器接線鬆動（感測器故障）：PLC 量的轉子轉速漏脈波而偏低、偏差越來越大，轉子實際轉速、變頻器量的轉速與發電都正常；兩者差超過 10 % 時 PLC 以轉子轉速感測器故障（029）跳機。",
        root_cause_en="A loose connection of the rotor speed encoder in the hub (sensor fault): the PLC's rotor speed misses pulses and reads low, increasingly so, while the real rotor speed, the converter's speed and the production are normal; once they differ by more than 10 % the PLC trips on rotor speed sensor fault (029).",
        difficulty="medium",
        key_signals=(
            "WROT_RotSpd",
        ),
        expected_actions_zh=(
            "檢查輪轂內轉子轉速編碼器的接線（手冊）",
            "看轉子轉速讀值與發電、風速的關係：讀值越來越低、發電卻和同風速的其他機組一樣，是量測問題而不是轉子真的變慢",
            "修復接線或更換編碼器，確認轉速讀值與發電、風速的關係恢復正常再復機",
        ),
        expected_actions_en=(
            "Check the connections of the rotor speed encoder in the hub (manual).",
            "Look at the rotor speed reading against power and wind: a reading that keeps falling while the turbine produces like its neighbours at the same wind points to the measurement, not a slower rotor.",
            "Repair the wiring or replace the encoder and confirm the speed reading matches power and wind again before restarting.",
        ),
        simulation_notes_zh=(
            "讀值偏低隨嚴重度平方增加（滿嚴重度少 30 %，約 0.58 時超過 10 %）；PLC 比對用變頻器的轉速（直驅機組＝轉子實際轉速），不是 WGEN_GnSpd——模擬的 WGEN_GnSpd 是傳動鏈模型的量，有的健康機組也長期偏離轉子轉速（WMOM-20261023-01），不能拿來比。跳機後轉子停下時保持停機前的轉速差，操作員復位或維護清除後才重新比對。",
            "轉速差判定的最低轉速（6.5 rpm）與延時（5 s）為模擬假設（手冊只寫 > 10 %）。",
        ),
        simulation_notes_en=(
            "The reading falls short with severity squared (30 % at full severity, past 10 % at about 0.58); the PLC compares with the converter's speed (on a direct-drive turbine the real rotor speed), not WGEN_GnSpd — the simulated WGEN_GnSpd comes from the drivetrain model and stays far from the rotor speed on some healthy turbines too (WMOM-20261023-01), so it cannot be used for the comparison. After the trip the stopped rotor keeps the last speed difference until an operator reset or maintenance clears it.",
            "The minimum speed (6.5 rpm) and delay (5 s) of the check are simulator assumptions (the manual only gives > 10 %).",
        ),
    ),

    "anemometer_fault": FaultScenario(
        id="anemometer_fault",
        name_en="Nacelle Anemometer Fault (Bearing Wear → Seized)",
        name_zh="機艙風速計故障（軸承磨耗 → 卡死）",
        description_en="The cup anemometer's bearing wears: it reads progressively low while the turbine keeps producing normally, then seizes and reads zero. With the rotor still turning, the PLC trips on the wind meter fault after a minute.",
        description_zh="杯式風速計軸承磨耗：讀值越來越低、機組發電照常，最後卡死讀 0。轉子還在轉的情況下，PLC 一分鐘後以風速計故障跳機。",
        affected_tags={
            "WMET_WSpeedNac": {"max_offset": -14.0, "curve": "linear"},
            "WMET_WSpeedRaw": {"max_offset": -14.0, "curve": "linear"},
        },
        alarm_codes=[
            {"type": "T1", "code": 230, "desc": "Wind meter fault"},
        ],
        component="nacelle_anemometer",
        category="sensor_fault",
        root_cause_zh="機艙杯式風速計軸承磨耗後卡死（感測器故障）：故障前期讀值偏低（功率、轉速對同樣讀值看起來比功率曲線高），最後杯子停轉、讀值 0；轉子轉速仍高於 6.5 rpm 而風速讀值低於 0.5 m/s 持續 60 秒，PLC 以風速計故障（230）跳機。機組本身與風向標正常。",
        root_cause_en="The nacelle cup anemometer's bearing wears and then seizes (sensor fault): early on it reads low (power and rotor speed look above the power curve for the reading), finally the cups stop and it reads 0; with the rotor still above 6.5 rpm and the wind reading below 0.5 m/s for 60 s the PLC trips on wind meter fault (230). The turbine and the wind vanes are fine.",
        difficulty="medium",
        key_signals=(
            "WMET_WSpeedNac",
            "WMET_WSpeedRaw",
        ),
        expected_actions_zh=(
            "檢查風速計配線（手冊）",
            "目視檢查風速計是否結冰 / 損壞、風杯是否都在（手冊）",
            "看功率與轉子轉速對風速讀值的關係：讀值偏低而功率正常是風速計問題；更換風速計後再復機",
        ),
        expected_actions_en=(
            "Check the wiring to the wind meter (manual).",
            "Visually inspect the wind meter for icing / damage — are all cups still present? (manual)",
            "Look at power and rotor speed against the wind reading: a low reading with normal power points to the anemometer; replace it before restarting.",
        ),
        simulation_notes_zh=(
            "嚴重度 0.8 之前讀值隨嚴重度偏低（滿 0.8 時少 24 %），到 0.8 時卡死讀 0；兩個風速 tag 都來自這支風速計。模擬的控制器（切入 / 切出、變槳）仍依實際風速運作。",
        ),
        simulation_notes_en=(
            "Before severity 0.8 the reading falls short with severity (24 % at 0.8); at 0.8 it seizes and reads 0. Both wind speed tags come from this anemometer. The simulated controller (cut-in / cut-out, pitch) keeps working on the real wind speed.",
        ),
    ),

    "wind_vane1_stuck": FaultScenario(
        id="wind_vane1_stuck",
        name_en="Wind Vane 1 Stuck (Seized / Iced)",
        name_zh="風向標 1 卡住（軸承卡死 / 結冰）",
        description_en="Wind vane 1's bearing seizes (or it ices up): its reading freezes at the value it had. While the 1-minute wind speed is above 4 m/s the PLC trips on the wind vane 1 fault after a minute; wind vane 2 keeps moving.",
        description_zh="風向標 1 軸承卡死（或結冰）：讀值停在卡住當下的值。1 分鐘平均風速高於 4 m/s 時，PLC 一分鐘後以風向標 1 故障跳機；風向標 2 照常變化。",
        affected_tags={
            "WYAW_YwVn1AlgnAvg5s": {"max_offset": 0.0, "curve": "linear"},
        },
        alarm_codes=[
            {"type": "T1", "code": 231, "desc": "Wind vane 1 fault"},
        ],
        auto_trip_severity=0.5,
        component="wind_vane_1",
        category="sensor_fault",
        root_cause_zh="風向標 1 卡住（軸承卡死或結冰，感測器故障）：讀值凍結不動，風向標 2 照常隨風變化；1 分鐘平均風速高於 4.0 m/s、讀值凍結超過 1 分鐘時 PLC 以風向標 1 故障（231）跳機。風向變化大時兩支風向標的差異也可能超過 15°（233）。",
        root_cause_en="Wind vane 1 stuck (seized bearing or icing, sensor fault): its reading freezes while wind vane 2 keeps following the wind; with the 1-minute wind speed above 4.0 m/s and the reading frozen for more than a minute the PLC trips on wind vane 1 fault (231). With large wind direction changes the two vanes can also differ by more than 15° (233).",
        difficulty="easy",
        key_signals=(
            "WYAW_YwVn1AlgnAvg5s",
        ),
        expected_actions_zh=(
            "檢查風向標 1 的配線（手冊）",
            "檢查風向標 1 是否結冰 / 損壞 / 被卡住（手冊）",
            "確認風向標 1 能自由轉動、讀值與風向標 2 一致後再復機；結冰時確認氣象儀器加熱",
        ),
        expected_actions_en=(
            "Check the wiring to wind vane 1 (manual).",
            "Check wind vane 1 for icing / damage / obstruction (manual).",
            "Confirm wind vane 1 turns freely and reads like wind vane 2 before restarting; if iced, check the meteo heating.",
        ),
        simulation_notes_zh=(
            "嚴重度到 0.5 時卡住，之前讀值正常；卡住後讀值固定在當下的值、沒有量測雜訊。模擬的偏航控制仍依實際風向對風，所以不會因為風向標 1 卡住而偏航失準。",
        ),
        simulation_notes_en=(
            "The vane seizes when severity reaches 0.5 and reads normally before that; afterwards the reading stays at its value at that moment, without measurement noise. The simulated yaw control keeps aligning to the real wind direction, so the stuck vane does not misalign the nacelle.",
        ),
    ),

    # 沒有任何警報的劣化：只能從發電表現看出來
    "yaw_misalignment": FaultScenario(
        id="yaw_misalignment",
        name_en="Static Yaw Misalignment (Wind Vane Mounting Offset)",
        name_zh="靜態偏航失準（風向標安裝偏差）",
        description_en="Both wind vanes are mounted off by the same angle (e.g. after a vane replacement): the yaw control aligns the nacelle to them, so the rotor runs permanently misaligned. The two vanes agree, no alarm or trip ever comes — only the power falls short of the power curve and the side-side loads rise.",
        description_zh="兩支風向標安裝時偏了同樣的角度（例：更換風向標後）：偏航控制照風向標對風，轉子長期偏離風向。兩支風向標讀值一致、永遠不會有警報或跳機——只有發電低於功率曲線、側向負載增加。",
        affected_tags={
            "WTUR_TotPwrAt": {"max_offset": -200.0, "curve": "linear"},
        },
        alarm_codes=[],
        auto_trip_severity=1.1,
        component="wind_vane_alignment",
        root_cause_zh="兩支風向標的安裝方向一起偏了一個角度（例：更換或維修風向標後沒有對準）：偏航控制讓風向標讀值歸零，轉子因此長期偏離真實風向，發電隨偏航角約以 cos³ 減少，塔架側向彎矩與 3P 振動增加。兩支風向標讀值一致，PLC 沒有任何警報或跳機，只能從功率曲線（同風速下發電偏低）與負載趨勢發現。",
        root_cause_en="Both wind vanes are mounted off by the same angle (e.g. not aligned after a vane replacement or repair): the yaw control nulls the vane readings, so the rotor runs permanently misaligned with the real wind, power falls roughly with cos³ of the yaw angle, and tower side-side moment and 3P vibration rise. The two vanes agree, the PLC raises no alarm or trip; it only shows in the power curve (low output for the wind speed) and the load trends.",
        difficulty="hard",
        key_signals=(
            "WTUR_TotPwrAt",
            "WLOD_TwrSsMom",
            "WVIB_Band3pX",
        ),
        expected_actions_zh=(
            "依手冊 §6.8.2.2，風向標是讓機艙對風的依據：檢查兩支風向標的安裝方向（對準標記）與校正（手冊）",
            "用功率曲線比對同風場其他機組：同風速下發電持續偏低、沒有警報時，懷疑對風偏差",
            "以 LiDAR / 鄰機風向比對確認偏航角後重新對準風向標",
        ),
        expected_actions_en=(
            "Per manual §6.8.2.2 the wind vanes are what the nacelle aligns to: check both vanes' mounting direction (alignment mark) and calibration (manual).",
            "Compare the power curve with the farm's other turbines: persistently low output for the wind speed with no alarm suggests a yaw misalignment.",
            "Confirm the misalignment with a LiDAR or the neighbours' wind direction and realign the vanes.",
        ),
        simulation_notes_zh=(
            "滿嚴重度偏 16°；發電損失以 cos³ 套在功率上（本模型的全載變槳依風速決定，若改成減少轉子面對的風，全載時反而會少變槳、多發電）。",
            "這個情境沒有任何預期警報碼：標準答案的 first_alarm / trip 為 null，評分不評延遲、偵測到就算早期預警。",
            "「沒有警報」指 PLC 事件：自創的振動頻帶警報 tag（WVIB_Alarm3p）可能亮。風場尾流模型的偏航輸入取風向標讀值，看不到這個偏差，下游機組的尾流不受影響。發電損失在全載也照 cos³ 套用（真機全載時可能還發得到額定）。",
        ),
        simulation_notes_en=(
            "16° at full severity; the power loss is applied as cos³ on the power (this model's full-load pitch follows the wind speed, so reducing the wind the rotor faces would pitch less and produce more at full load).",
            "This scenario has no expected alarm codes: the answer's first_alarm / trip are null, and scoring does not time it — any detection counts as early warning.",
            "\"No alarm\" means no PLC event: the synthetic vibration band alarm tag (WVIB_Alarm3p) may light up. The farm wake model takes its yaw input from the vane reading, so it does not see this offset and downstream wakes are unaffected. The power loss is applied as cos³ at full load too (a real turbine may still reach rated power there).",
        ),
    ),
}


# ActiveFault.instance_id 的來源（每次注入遞增）
_FAULT_INSTANCE_IDS: Iterator[int] = itertools.count(1)


@dataclass
class ActiveFault:
    """An active fault instance on a specific turbine."""
    scenario_id: str
    turbine_id: str
    severity: float = 0.0                # 0.0 → 1.0
    severity_rate: float = 0.0002        # per second (~0.72/hour = ~18 hours to full)
    started_at: Optional[datetime] = None
    tripped: bool = False
    trip_code: Optional[int] = None          # PLC trip code that tripped this fault
    active_alarms: List[Dict] = field(default_factory=list)  # expected codes the PLC has active
    # 每次注入一個新編號：同機組同情境再注入時，物理模型據此重新起算（例：Pt100 接觸不良的瞬斷排程）
    instance_id: int = field(default_factory=lambda: next(_FAULT_INSTANCE_IDS))


class FaultEngine:
    """
    Manages fault injection across all turbines.

    Faults progress gradually:
      severity += severity_rate * dt   (each simulation step)

    Severity curves control how each tag is affected:
      linear:      offset = max_offset * severity
      quadratic:   offset = max_offset * severity²
      exponential: offset = max_offset * (e^(3*severity) - 1) / (e³ - 1)
      logarithmic: offset = max_offset * ln(1 + severity*e) / ln(1+e)
    """

    def __init__(self):
        self._active_faults: List[ActiveFault] = []

    @property
    def active_faults(self) -> List[ActiveFault]:
        """List of currently active fault instances across all turbines."""
        return list(self._active_faults)

    def get_scenarios(self) -> Dict[str, FaultScenario]:
        """Return the full catalog of available fault scenarios."""
        return dict(FAULT_SCENARIOS)

    def inject(self, scenario_id: str, turbine_id: str,
               severity_rate: float = 0.0002,
               initial_severity: float = 0.0) -> bool:
        """
        Inject a fault into a specific turbine.

        Args:
            scenario_id: One of FAULT_SCENARIOS keys
            turbine_id: e.g. "WT003"
            severity_rate: How fast severity grows per second
                          0.0002 = ~18 hours to full (slow, realistic)
                          0.001  = ~3.6 hours to full (fast demo)
                          0.01   = ~20 min to full (very fast demo)
            initial_severity: Start severity (0.0 = beginning, 0.5 = mid-fault)
        """
        if scenario_id not in FAULT_SCENARIOS:
            return False

        # Remove existing fault of same type on same turbine
        self._active_faults = [
            f for f in self._active_faults
            if not (f.scenario_id == scenario_id and f.turbine_id == turbine_id)
        ]

        self._active_faults.append(ActiveFault(
            scenario_id=scenario_id,
            turbine_id=turbine_id,
            severity=initial_severity,
            severity_rate=severity_rate,
            started_at=utc_now(),
        ))
        return True

    def clear(self, turbine_id: Optional[str] = None,
              scenario_id: Optional[str] = None):
        """Remove active faults. If no args, clears all."""
        if turbine_id is None and scenario_id is None:
            self._active_faults.clear()
            return

        self._active_faults = [
            f for f in self._active_faults
            if not ((turbine_id is None or f.turbine_id == turbine_id) and
                    (scenario_id is None or f.scenario_id == scenario_id))
        ]

    def step(self, dt: float = 1.0) -> Dict[str, Dict[str, float]]:
        """
        Advance all active faults by dt seconds.

        Returns:
            {turbine_id: {tag_id: offset_value}} for all affected turbines.
        """
        result: Dict[str, Dict[str, float]] = {}

        for fault in self._active_faults:
            if fault.tripped:
                continue

            # Progress severity. Alarms / trips are no longer derived from severity:
            # the PLC protection layer raises them from the measured signals and the
            # engine reports back via mark_tripped() / active_alarms (WMOM-20261021-03-b).
            fault.severity = min(1.0, fault.severity + fault.severity_rate * dt)

            scenario = FAULT_SCENARIOS.get(fault.scenario_id)
            if not scenario:
                continue

            # Calculate tag offsets
            modifiers = result.setdefault(fault.turbine_id, {})
            for tag_id, params in scenario.affected_tags.items():
                max_offset = params["max_offset"]
                curve = params.get("curve", "linear")
                offset = self._apply_curve(fault.severity, max_offset, curve)

                # Accumulate if multiple faults affect the same tag
                modifiers[tag_id] = modifiers.get(tag_id, 0) + offset

        return result

    def mark_tripped(self, turbine_id: str, scenario_id: str, code: int) -> bool:
        """PLC 以本故障的預期跳機碼跳機時，標記故障為 tripped（鎖存到維護清除）。

        Args:
            turbine_id: 機組 ID。
            scenario_id: 故障情境 ID。
            code: 觸發的 Z72 跳機碼。

        Returns:
            本次是否由未跳機轉為已跳機。
        """
        scenario = FAULT_SCENARIOS.get(scenario_id)
        if scenario is not None and scenario.category == "nuisance":
            # nuisance 跳機自己會好（手冊 §11.3）：不鎖機組、等條件解除就照每小時上限自動重啟（WMOM-20261021-08-b）
            return False
        for fault in self._active_faults:
            if fault.turbine_id == turbine_id and fault.scenario_id == scenario_id and not fault.tripped:
                fault.tripped = True
                fault.trip_code = code
                return True
        return False

    def get_fault_status(self) -> List[Dict]:
        """Return status of all active faults (for API/frontend)."""
        statuses = []
        for fault in self._active_faults:
            scenario = FAULT_SCENARIOS.get(fault.scenario_id)
            phase = self._severity_to_phase(fault.severity)
            statuses.append({
                "scenario_id": fault.scenario_id,
                "turbine_id": fault.turbine_id,
                "name_en": scenario.name_en if scenario else "",
                "name_zh": scenario.name_zh if scenario else "",
                "severity": round(fault.severity, 4),
                "phase": phase.value,
                "tripped": fault.tripped,
                "trip_code": fault.trip_code,
                "active_alarms": fault.active_alarms,
                "started_at": iso_utc(fault.started_at) if fault.started_at else None,
            })
        return statuses

    @staticmethod
    def _apply_curve(severity: float, max_offset: float, curve: str) -> float:
        """Map severity (0→1) to offset using the specified curve shape."""
        s = max(0.0, min(1.0, severity))
        if curve == "linear":
            return max_offset * s
        elif curve == "quadratic":
            return max_offset * s * s
        elif curve == "exponential":
            # Slow start, rapid end — mimics real degradation
            return max_offset * (math.exp(3 * s) - 1) / (math.exp(3) - 1)
        elif curve == "logarithmic":
            # Fast start, plateaus — mimics saturation effects
            e = math.e
            return max_offset * math.log(1 + s * e) / math.log(1 + e)
        return max_offset * s

    @staticmethod
    def _severity_to_phase(severity: float) -> FaultPhase:
        if severity < 0.2:
            return FaultPhase.INCIPIENT
        elif severity < 0.5:
            return FaultPhase.DEVELOPING
        elif severity < 0.8:
            return FaultPhase.ADVANCED
        return FaultPhase.CRITICAL


# ─── Pre-defined Test Plans ──────────────────────────────────────────────
# Each plan is a sequence of fault injections with timing offsets (seconds).
# Used by the API to auto-inject faults during bulk data generation.

@dataclass
class TestPlanStep:
    """One step in a fault injection test plan."""
    offset_seconds: float       # when to inject (relative to plan start)
    scenario_id: str            # which fault
    turbine_id: str             # which turbine
    severity_rate: float        # how fast it develops
    initial_severity: float = 0.0
    description: str = ""


TEST_PLANS: Dict[str, Dict] = {

    "basic_validation": {
        "name_en": "Basic Validation (4 hours)",
        "name_zh": "基本驗證（4小時）",
        "description_en": "One obvious fault per turbine type. Good for quick functional testing.",
        "description_zh": "每種故障各一台。適合快速功能驗證。",
        "duration_hours": 4,
        "steps": [
            TestPlanStep(0,     "bearing_wear",          "WT001", 0.002,  0.0, "Obvious bearing wear on WT001"),
            TestPlanStep(3600,  "converter_cooling_fault","WT003", 0.002,  0.0, "Converter fault on WT003"),
            TestPlanStep(7200,  "generator_overspeed",   "WT005", 0.005,  0.0, "Overspeed on WT005"),
        ],
    },

    "subtle_challenge": {
        "name_en": "Subtle Fault Challenge (24 hours)",
        "name_zh": "細微故障挑戰（24小時）",
        "description_en": "Mix of very slow-developing faults. Tests whether diagnosis can detect incipient failures before alarms trigger.",
        "description_zh": "多種極緩慢發展的故障混合。測試診斷系統能否在警報觸發前偵測初期異常。",
        "duration_hours": 24,
        "steps": [
            TestPlanStep(0,      "stator_winding_degradation", "WT002", 0.00005, 0.0, "Very slow stator degradation"),
            TestPlanStep(7200,   "yaw_sensor_drift",           "WT004", 0.00008, 0.0, "Slow yaw drift"),
            TestPlanStep(14400,  "hydraulic_leak",             "WT006", 0.00006, 0.0, "Very slow hydraulic leak"),
            TestPlanStep(21600,  "pitch_imbalance",            "WT008", 0.00004, 0.0, "Barely detectable pitch drift"),
        ],
    },

    "mixed_difficulty": {
        "name_en": "Mixed Difficulty (48 hours)",
        "name_zh": "混合難度（48小時）",
        "description_en": "Combination of obvious, subtle, and environmental faults across multiple turbines. Realistic scenario for comprehensive diagnosis testing.",
        "description_zh": "明顯、細微和環境故障的組合，分布在多台風機。適合全面性診斷測試的真實場景。",
        "duration_hours": 48,
        "steps": [
            # Hour 0-6: Subtle faults start
            TestPlanStep(0,      "stator_winding_degradation", "WT002", 0.00003, 0.0, "Very slow insulation degradation"),
            TestPlanStep(1800,   "hydraulic_leak",             "WT007", 0.00005, 0.0, "Slow hydraulic leak"),
            # Hour 6-12: Environmental event
            TestPlanStep(21600,  "blade_icing",                "WT001", 0.0004,  0.0, "Icing event (environmental)"),
            TestPlanStep(21600,  "blade_icing",                "WT002", 0.0003,  0.0, "Icing (different rate)"),
            TestPlanStep(21600,  "blade_icing",                "WT003", 0.0005,  0.0, "Icing (worst)"),
            # Hour 12-24: More subtle faults
            TestPlanStep(43200,  "yaw_sensor_drift",           "WT010", 0.00006, 0.0, "Slow yaw drift"),
            TestPlanStep(50400,  "pitch_imbalance",            "WT012", 0.00004, 0.0, "Subtle pitch imbalance"),
            # Hour 24-36: Obvious fault
            TestPlanStep(86400,  "bearing_wear",               "WT005", 0.001,   0.0, "Clear bearing degradation"),
            TestPlanStep(93600,  "converter_cooling_fault",    "WT009", 0.0008,  0.0, "Converter cooling issue"),
            # Hour 36-48: Compound fault
            TestPlanStep(129600, "nacelle_cooling_failure",    "WT003", 0.0006,  0.0, "Nacelle cooling compound"),
            TestPlanStep(136800, "grid_voltage_sag",           "WT011", 0.0005,  0.0, "Grid instability"),
        ],
    },

    "stress_test": {
        "name_en": "Stress Test (72 hours)",
        "name_zh": "壓力測試（72小時）",
        "description_en": "High fault density — multiple simultaneous faults on different turbines with varying speeds. Tests diagnosis system under heavy load.",
        "description_zh": "高故障密度 — 多台風機同時出現不同速率的故障。測試診斷系統在重負載下的表現。",
        "duration_hours": 72,
        "steps": [
            TestPlanStep(0,      "bearing_wear",               "WT001", 0.0003),
            TestPlanStep(0,      "yaw_sensor_drift",           "WT003", 0.0001),
            TestPlanStep(3600,   "pitch_imbalance",            "WT005", 0.00008),
            TestPlanStep(3600,   "stator_winding_degradation", "WT007", 0.00005),
            TestPlanStep(7200,   "hydraulic_leak",             "WT009", 0.0001),
            TestPlanStep(7200,   "converter_cooling_fault",    "WT011", 0.0005),
            TestPlanStep(14400,  "blade_icing",                "WT002", 0.0005),
            TestPlanStep(14400,  "nacelle_cooling_failure",    "WT004", 0.0004),
            TestPlanStep(21600,  "grid_voltage_sag",           "WT006", 0.0003),
            TestPlanStep(21600,  "transformer_overheat",       "WT008", 0.0002),
            TestPlanStep(43200,  "bearing_wear",               "WT010", 0.0005),
            TestPlanStep(43200,  "generator_overspeed",        "WT012", 0.002),
            TestPlanStep(86400,  "converter_cooling_fault",    "WT013", 0.001),
            TestPlanStep(86400,  "nacelle_cooling_failure",    "WT014", 0.0008),
        ],
    },
}
