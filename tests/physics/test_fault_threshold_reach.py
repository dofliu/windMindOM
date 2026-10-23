"""Fault physics reach real Z72 protection setpoints（WMOM-20261021-03a，EPIC-DS Phase 1b）。

外部 RAG 維修助手看到的警報要由「物理訊號越過真實 PLC 判定條件」觸發（Phase 1b 下一步
WMOM-20261021-03b），前提是故障物理真的能把量測值推過 Z72 手冊 / spec 的門檻。校正前多數
故障離門檻很遠（例：bearing_wear 滿嚴重度軸承只到 44 °C，門檻 85 / 95 °C）。

本檔鎖住四件事（3 h 模擬、dt = 5 s，取最後 5 分鐘）：

1. 健康機組在 30 °C 與天氣模型最熱的 37 °C（7-8 月正午）各風速下，所有監控訊號都低於警報
   設定值——不會整天誤報（37 °C 時手冊的機艙控制櫃 50 °C 會被健康機組碰到，真機亦然，不檢查）
2. 每個故障情境在高負載（14 m/s、25 °C）滿嚴重度時，量測值越過該情境跳機事件的真實設定值
3. 中等嚴重度（0.5）時還沒到跳機設定值——跳機發生在故障後期，不是一注入就跳
4. 標準答案列的 ``key_signals`` 在高負載下確實偏離健康機組（WMOM-20261021-04）

另有兩組守門測試：新感測器只用 ``_aux_rng``（既有 tag 的健康輸出不受影響）、熱阻倍率的邊界；
以及 ``yaw_sensor_drift`` 的多種子守門（WMOM-20261022-02：PLC 看到的是漂移 + 兩支風向標的安裝偏差差，
只測 seed 7 時漏掉了偏差差 < −3° 的機組永遠不跳 233）。

設定值來源見 ``TurbineSpec``（manual = 手冊 Appendix D / C、assumed = 手冊僅寫 See [ABB] 的假設）。
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Callable, Dict, List, Tuple

import numpy as np
import pytest

from simulator.physics import TurbinePhysicsModel
from simulator.physics.fault_engine import FAULT_SCENARIOS
from simulator.physics.thermal_model import ThermalElement, ThermalSystem
from simulator.physics.turbine_physics import YAW_SENSOR_DRIFT_MAX_DEG, TurbineSpec

SPEC = TurbineSpec()
NOMINAL_LN_KV = SPEC.nominal_voltage / math.sqrt(3.0) / 1000.0  # WCNV_VtgMsCnvGd* 為 kV 相電壓
LVRT_BAND1_PU = 0.90  # ElectricalModel：< 0.90 p.u. 進入 LVRT band 1，持續過久即跳機
DT = 5.0
HOURS = 3.0
SAMPLE_STEPS = 60  # 最後 5 分鐘

Sample = Dict[str, float]


def _blade_disc(o: Sample) -> float:
    b = (o["WROT_PtAngValBl1"], o["WROT_PtAngValBl2"], o["WROT_PtAngValBl3"])
    return max(abs(b[0] - b[1]), abs(b[0] - b[2]), abs(b[1] - b[2]))


def _vane_disc(o: Sample) -> float:
    return abs(o["WYAW_YwVn1AlgnAvg5s"] - o["WYAW_YwVn2AlgnAvg5s"])


def _vib(o: Sample) -> float:
    return max(o["WNAC_VibMsNacXDir"], o["WNAC_VibMsNacYDir"])


# 不是 SCADA tag 的 PLC 輸入，_run 另外記在 sample 裡（WMOM-20261021-08-c）：ABB 冷卻單元的流量（額定 = 1）、
# 變頻器轉速（直驅＝轉子實際轉速；029 比的是它，不是模擬的 WGEN_GnSpd）
_FLOW = "_cooling_flow_ratio"
_ROTOR = "_rotor_rpm"


def _rotor_speed_dev(o: Sample) -> float:
    return abs(o["WROT_RotSpd"] - o[_ROTOR]) / o[_ROTOR]


def _pitch_current(o: Sample) -> float:
    return max(o["WROT_PtMotCurBl1"], o["WROT_PtMotCurBl2"], o["WROT_PtMotCurBl3"])


@lru_cache(maxsize=None)
def _run(fault_id: str | None, severity: float, wind: float, ambient: float) -> Tuple[Tuple[Sample, ...], str]:
    """跑 3 h，回傳最後 5 分鐘的 samples 與結束時的 shutdown cause。"""
    model = TurbinePhysicsModel(seed=7)
    # 量測物理訊號能否到達設定值：關閉 PLC 保護，否則一越過就跳機（PLC 行為另見
    # modules/monitoring/tests/test_plc_integration.py，WMOM-20261021-03-b）
    model.plc.enabled = False
    if fault_id is not None:
        model.active_faults = [{"scenario_id": fault_id, "severity": severity}]
    steps = int(HOURS * 3600 / DT)
    samples: List[Sample] = []
    for i in range(steps):
        out = model.step(wind_speed=wind, wind_direction=180.0, ambient_temp=ambient, dt=DT)
        if i >= steps - SAMPLE_STEPS:
            sample = dict(out)
            sample[_FLOW] = model.cooling.water_loop.flow_lpm / model.cooling.spec.pump_flow_rated_lpm
            sample[_ROTOR] = model.rotor_speed
            samples.append(sample)
    return tuple(samples), str(model.get_control_status()["shutdown_cause"])


def _mean(samples: Tuple[Sample, ...], fn: Callable[[Sample], float]) -> float:
    return float(np.mean([fn(s) for s in samples]))


def _tag(name: str) -> Callable[[Sample], float]:
    return lambda s: s[name]


# ─────────────────────────────────────────────────────────────────────────
# 1. 健康機組：炎熱天不誤報
# ─────────────────────────────────────────────────────────────────────────

# (說明, 訊號, 比較, 設定值) — 比較 "<" 表示健康值必須低於設定值
HEALTHY_LIMITS: List[Tuple[str, Callable[[Sample], float], str, float]] = [
    ("262 main bearing", _tag("WGEN_GnBrgTmp1"), "<", SPEC.gen_bearing_alarm),
    ("263 main bearing 2", _tag("WGEN_GnBrgTmp2"), "<", SPEC.gen_bearing_alarm),
    ("264 stator", _tag("WGEN_GnStaTmp1"), "<", SPEC.gen_stator_alarm),
    ("265 stator 2", _tag("WGEN_GnStaTmp2"), "<", SPEC.gen_stator_alarm),
    ("273 nacelle air", _tag("WNAC_NacTmp"), "<", SPEC.nacelle_air_alarm),
    ("256 nacelle cabinet", _tag("WNAC_NacCabTmp"), "<", SPEC.nacelle_cab_trip),
    ("417 transformer", _tag("WGDC_TrfCoreTmp"), "<", SPEC.transformer_alarm),
    ("420 cooling water", _tag("WCNV_IGCTWtrTmp"), "<", SPEC.cooling_water_alarm),
    ("421 converter cabinet", _tag("WCNV_CnvCabinTmp"), "<", SPEC.converter_cabinet_alarm),
    ("432 static water pressure", _tag("WCNV_IGCTWtrPres1"), ">", SPEC.cooling_static_pressure_low_bar),
    ("260 yaw brake pressure", _tag("WYAW_YwBrkHyPrs"), ">", SPEC.yaw_pressure_alarm),
    ("261 seals leak", _tag("WYAW_YwBrkSealsLeak"), "<", 0.5),
    ("233 vane discrepancy", _vane_disc, "<", SPEC.vane_discrepancy_deg),
    ("335 blade discrepancy", _blade_disc, "<", SPEC.blade_discrepancy_5s_deg),
    ("236 tower vibration", _vib, "<", SPEC.tower_vibration_trip_mm_s),
    ("481 grid voltage", _tag("WCNV_VtgMsCnvGd1"), ">", LVRT_BAND1_PU * NOMINAL_LN_KV),
    # WMOM-20261021-08-c：健康機組的變槳馬達電流連 I2t 的連續額定都不到（手冊過載限值 18 A 以下）
    ("381 pitch drive I2t", _pitch_current, "<", SPEC.pitch_drive_continuous_a),
    ("423 conductivity", _tag("WCNV_IGCTWtrCond"), "<", SPEC.cooling_conductivity_alarm_us_cm),
    ("422 cooling flow", _tag(_FLOW), ">", SPEC.cooling_flow_alarm_ratio),
    ("029 rotor speed", _rotor_speed_dev, "<", SPEC.rotor_speed_deviation),
    ("230 wind meter", _tag("WMET_WSpeedNac"), ">", SPEC.anemometer_min_wind),
]

# 37 °C 時健康機組會碰到、且真機也會碰到的手冊設定值（不是模擬器假設值，不調）
MANUAL_LIMITS_REACHED_ON_HOTTEST_DAY = {"256 nacelle cabinet"}


@pytest.mark.parametrize("ambient", [30.0, 37.0])
@pytest.mark.parametrize("wind", [9.0, 14.0, 20.0])
def test_healthy_turbine_on_hot_day_stays_inside_all_setpoints(wind: float, ambient: float) -> None:
    samples, cause = _run(None, 0.0, wind, ambient)
    assert samples[-1]["WTUR_TurSt"] == 6, f"健康機組在 {wind} m/s、{ambient} °C 停機（cause={cause}）"
    violations = []
    for label, fn, op, setpoint in HEALTHY_LIMITS:
        if ambient > 35.0 and label in MANUAL_LIMITS_REACHED_ON_HOTTEST_DAY:
            continue
        worst = max(fn(s) for s in samples) if op == "<" else min(fn(s) for s in samples)
        ok = worst < setpoint if op == "<" else worst > setpoint
        if not ok:
            violations.append(f"{label}: worst={worst:.2f} vs {op}{setpoint}")
    assert violations == []


# ─────────────────────────────────────────────────────────────────────────
# 2. 故障滿嚴重度：越過跳機事件的真實設定值
# ─────────────────────────────────────────────────────────────────────────

# (fault_id, 跳機事件, 訊號, 比較, 設定值) — 比較 ">" 表示故障值必須高於設定值
TRIP_REACH: List[Tuple[str, str, Callable[[Sample], float], str, float]] = [
    ("bearing_wear", "240", _tag("WGEN_GnBrgTmp1"), ">", SPEC.gen_bearing_trip),
    ("stator_winding_degradation", "244", _tag("WGEN_GnStaTmp1"), ">", SPEC.gen_stator_trip),
    # 感測器漂移（WMOM-20261021-08-a）：讀值越過同樣的設定值，機器本身正常
    ("main_bearing_temp_sensor_drift", "240", _tag("WGEN_GnBrgTmp1"), ">", SPEC.gen_bearing_trip),
    ("stator_temp_sensor_drift", "244", _tag("WGEN_GnStaTmp1"), ">", SPEC.gen_stator_trip),
    ("nacelle_cooling_failure", "256", _tag("WNAC_NacCabTmp"), ">", SPEC.nacelle_cab_trip),
    ("nacelle_cooling_failure", "273", _tag("WNAC_NacTmp"), ">", SPEC.nacelle_air_alarm),
    ("transformer_overheat", "444", _tag("WGDC_TrfCoreTmp"), ">", SPEC.transformer_trip),
    ("converter_cooling_fault", "437", _tag("WCNV_IGCTWtrTmp"), ">", SPEC.cooling_water_trip),
    ("converter_cooling_fault", "432", _tag("WCNV_IGCTWtrPres1"), "<", SPEC.cooling_static_pressure_low_bar),
    ("hydraulic_leak", "228", _tag("WYAW_YwBrkHyPrs"), "<", SPEC.yaw_pressure_trip),
    ("hydraulic_leak", "261", _tag("WYAW_YwBrkSealsLeak"), ">", 0.5),
    ("yaw_sensor_drift", "233", _vane_disc, ">", SPEC.vane_discrepancy_deg),
    ("pitch_imbalance", "335", _blade_disc, ">", SPEC.blade_discrepancy_5s_deg),
    ("blade_icing", "236", _vib, ">", SPEC.tower_vibration_trip_mm_s),
    # 故障庫擴充（WMOM-20261021-08-c）
    ("pitch_motor_fault", "367", _tag("WROT_PtMotCurBl1"), ">", SPEC.pitch_motor_overcurrent_10m_a),
    ("converter_cooling_pump_wear", "439", _tag(_FLOW), "<", SPEC.cooling_flow_trip_ratio),
    ("converter_cooling_pump_wear", "432", _tag("WCNV_IGCTWtrPres1"), "<", SPEC.cooling_static_pressure_low_bar),
    ("cooling_water_deionizer_exhausted", "440", _tag("WCNV_IGCTWtrCond"), ">",
     SPEC.cooling_conductivity_trip_us_cm),
    ("rotor_speed_sensor_fault", "029", _rotor_speed_dev, ">", SPEC.rotor_speed_deviation),
    ("anemometer_fault", "230", _tag("WMET_WSpeedNac"), "<", SPEC.anemometer_min_wind),
]


@pytest.mark.parametrize(
    ("fault_id", "event", "fn", "op", "setpoint"),
    TRIP_REACH,
    ids=[f"{f}:{e}" for f, e, *_ in TRIP_REACH],
)
def test_full_severity_fault_crosses_real_setpoint(
    fault_id: str, event: str, fn: Callable[[Sample], float], op: str, setpoint: float,
) -> None:
    samples, _ = _run(fault_id, 1.0, 14.0, 25.0)
    value = _mean(samples, fn)
    if op == ">":
        assert value > setpoint, f"{fault_id} 事件 {event}：{value:.2f} 未超過 {setpoint}"
    else:
        assert value < setpoint, f"{fault_id} 事件 {event}：{value:.2f} 未低於 {setpoint}"


def test_full_severity_overspeed_trips_on_software_overspeed() -> None:
    """generator_overspeed：轉速越過軟體超速設定（26.5 rpm，事件 351）由物理保護停機。"""
    samples, cause = _run("generator_overspeed", 1.0, 14.0, 25.0)
    assert samples[-1]["WTUR_TurSt"] != 6
    assert cause.startswith("overspeed")


@pytest.mark.parametrize("severity", [0.8, 1.0])
def test_grid_sag_trips_on_undervoltage(severity: float) -> None:
    """grid_voltage_sag：端電壓持續低於 LVRT band 1（0.90 p.u.）或電網保護下限而停機（ARU 欠壓，事件 481）。

    本檔關閉 PLC 量物理（沒有每碼重啟上限），機組會反覆停機 / 重啟：看取樣窗內有沒有停機，不看最後一筆。
    """
    samples, cause = _run("grid_voltage_sag", severity, 14.0, 25.0)
    assert min(s["WCNV_VtgMsCnvGd1"] for s in samples) < LVRT_BAND1_PU * NOMINAL_LN_KV
    assert any(s["WTUR_TurSt"] != 6 for s in samples)
    assert cause.startswith("ride_through:lvrt") or cause in ("grid_protection", "grid_trip"), cause


# ─────────────────────────────────────────────────────────────────────────
# 3. 中等嚴重度：還不到跳機設定值
# ─────────────────────────────────────────────────────────────────────────

MID_SEVERITY_BELOW_TRIP = [
    (f, e, fn, op, sp) for f, e, fn, op, sp in TRIP_REACH
    if e not in ("273", "432", "261")  # 警報級或隨時間累積的訊號，不檢查
]


@pytest.mark.parametrize(
    ("fault_id", "event", "fn", "op", "setpoint"),
    MID_SEVERITY_BELOW_TRIP,
    ids=[f"{f}:{e}" for f, e, *_ in MID_SEVERITY_BELOW_TRIP],
)
def test_mid_severity_fault_has_not_reached_trip(
    fault_id: str, event: str, fn: Callable[[Sample], float], op: str, setpoint: float,
) -> None:
    samples, _ = _run(fault_id, 0.5, 14.0, 25.0)
    assert samples[-1]["WTUR_TurSt"] == 6
    value = _mean(samples, fn)
    if op == ">":
        assert value < setpoint, f"{fault_id} 事件 {event}：嚴重度 0.5 就到 {value:.2f}（≥ {setpoint}）"
    else:
        assert value > setpoint, f"{fault_id} 事件 {event}：嚴重度 0.5 就到 {value:.2f}（≤ {setpoint}）"


@pytest.mark.parametrize("fault_id", ["generator_overspeed", "grid_voltage_sag"])
def test_mid_severity_protection_faults_keep_producing(fault_id: str) -> None:
    samples, cause = _run(fault_id, 0.3, 14.0, 25.0)
    assert samples[-1]["WTUR_TurSt"] == 6, f"{fault_id} 嚴重度 0.3 就停機（cause={cause}）"


def test_stator_fault_stays_below_alarm_at_low_load() -> None:
    """負載相依：同樣滿嚴重度的定子劣化，低風速（9 m/s）時不會到警報設定值。"""
    samples, _ = _run("stator_winding_degradation", 1.0, 9.0, 25.0)
    assert _mean(samples, _tag("WGEN_GnStaTmp1")) < SPEC.gen_stator_alarm


# ── 標準答案的 key_signals 確實看得到故障（WMOM-20261021-04）──
# 高負載（14 m/s、25 °C）滿嚴重度時，每個 key signal 的平均值都明顯偏離健康機組。會在取樣窗前跳機的
# 保護類故障改用還在發電的嚴重度：grid_voltage_sag 0.5、generator_overspeed 0.3（轉速 25.1 vs 22.5 rpm）。
_KEY_SIGNAL_SEVERITY = {"grid_voltage_sag": 0.5, "generator_overspeed": 0.3}


# nuisance 的 key signal 只在瞬間偏離（Pt100 接觸不良的瞬斷），取樣窗不一定碰到：另見下面的專屬測試
@pytest.mark.parametrize("fault_id", sorted(sid for sid, sc in FAULT_SCENARIOS.items() if sc.category != "nuisance"))
def test_ground_truth_key_signals_deviate_from_healthy(fault_id: str) -> None:
    healthy, _ = _run(None, 0.0, 14.0, 25.0)
    faulty, cause = _run(fault_id, _KEY_SIGNAL_SEVERITY.get(fault_id, 1.0), 14.0, 25.0)
    for tag in FAULT_SCENARIOS[fault_id].key_signals:
        h = np.array([s[tag] for s in healthy])
        f = np.array([s[tag] for s in faulty])
        deviation = abs(float(f.mean() - h.mean()))
        floor = max(3.0 * float(h.std()), 0.02 * max(abs(float(h.mean())), 1.0))
        assert deviation > floor, (
            f"{fault_id}: key signal {tag} 只偏離 {deviation:.3g}（門檻 {floor:.3g}，結束時 {cause}）"
        )


# ── 感測器故障只改那支感測器的讀值（WMOM-20261021-08-a）──
# 同一個種子：故障機組除了故障的那支感測器，每個 tag 每一步都與健康機組逐位元相同（製程、控制、其他感測器
# 的雜訊都不受影響）；故障讀值確實不同。
_SENSOR_FAULT_TAGS: Dict[str, Tuple[str, ...]] = {
    "main_bearing_temp_sensor_drift": ("WGEN_GnBrgTmp1",),
    "stator_temp_sensor_drift": ("WGEN_GnStaTmp1",),
    "main_bearing_temp_sensor_wire_break": ("WGEN_GnBrgTmp1",),
    "blade1_pitch_encoder_fault": ("WROT_PtAngValBl1",),
    "yaw_brake_pressure_sensor_fault": ("WYAW_YwBrkHyPrs",),
    # WMOM-20261021-08-c；風速計的兩個風速 tag 都來自同一支風速計
    "rotor_speed_sensor_fault": ("WROT_RotSpd",),
    "anemometer_fault": ("WMET_WSpeedNac", "WMET_WSpeedRaw"),
    "wind_vane1_stuck": ("WYAW_YwVn1AlgnAvg5s",),
}


def test_every_sensor_fault_is_covered() -> None:
    assert set(_SENSOR_FAULT_TAGS) == {sid for sid, sc in FAULT_SCENARIOS.items() if sc.category == "sensor_fault"
                                       and sid != "yaw_sensor_drift"}  # 漂移的風向標會讓控制器轉錯方向（製程跟著變）


@pytest.mark.parametrize("fault_id", sorted(_SENSOR_FAULT_TAGS))
def test_sensor_faults_change_only_the_faulty_reading(fault_id: str) -> None:
    healthy, _ = _run(None, 0.0, 14.0, 25.0)
    faulty, _ = _run(fault_id, 1.0, 14.0, 25.0)
    tags = _SENSOR_FAULT_TAGS[fault_id]
    for h, f in zip(healthy, faulty, strict=True):
        assert {k: v for k, v in h.items() if k not in tags} == {k: v for k, v in f.items() if k not in tags}
        assert all(f[tag] != h[tag] for tag in tags)


def test_loose_contact_glitches_only_the_bearing_reading_now_and_then() -> None:
    """Pt100 接觸不良（nuisance，WMOM-20261021-08-b）：關掉 PLC 時只有軸承溫度 1 偶爾讀成斷線值，其餘逐位元同健康。

    瞬斷時讀值＝斷線值（key signal 看得到），其他時間與健康機組相同；瞬斷只佔一小段時間。
    """
    def series(fault: bool) -> List[Sample]:
        model = TurbinePhysicsModel(seed=7)
        model.plc.enabled = False
        if fault:
            model.active_faults = [{"scenario_id": "main_bearing_temp_loose_contact", "severity": 1.0}]
        return [dict(model.step(wind_speed=14.0, wind_direction=180.0, ambient_temp=25.0, dt=DT))
                for _ in range(int(1.5 * 3600 / DT))]

    healthy, loose = series(False), series(True)
    tag = "WGEN_GnBrgTmp1"
    glitches = 0
    for h, f in zip(healthy, loose, strict=True):
        assert {k: v for k, v in h.items() if k != tag} == {k: v for k, v in f.items() if k != tag}
        if f[tag] != h[tag]:
            assert f[tag] == SPEC.pt100_broken_wire_c
            glitches += 1
    assert 0 < glitches < 0.05 * len(loose)


def test_broken_sensors_read_a_constant_out_of_range_value() -> None:
    wire, _ = _run("main_bearing_temp_sensor_wire_break", 1.0, 14.0, 25.0)
    assert {s["WGEN_GnBrgTmp1"] for s in wire} == {SPEC.pt100_broken_wire_c}
    encoder, _ = _run("blade1_pitch_encoder_fault", 1.0, 14.0, 25.0)
    assert {s["WROT_PtAngValBl1"] for s in encoder} == {SPEC.blade_encoder_fault_deg}
    pressure, _ = _run("yaw_brake_pressure_sensor_fault", 1.0, 14.0, 25.0)
    assert {s["WYAW_YwBrkHyPrs"] for s in pressure} == {SPEC.yaw_pressure_broken_wire_bar}
    # WMOM-20261021-08-c：卡死的風速計讀 0、卡住的風向標停在一個值（沒有雜訊）
    anemometer, _ = _run("anemometer_fault", 1.0, 14.0, 25.0)
    assert {s["WMET_WSpeedNac"] for s in anemometer} == {s["WMET_WSpeedRaw"] for s in anemometer} == {0.0}
    vane, _ = _run("wind_vane1_stuck", 1.0, 14.0, 25.0)
    assert len({s["WYAW_YwVn1AlgnAvg5s"] for s in vane}) == 1
    # 嚴重度還沒到 SENSOR_BREAK_SEVERITY：讀值正常
    healthy, _ = _run(None, 0.0, 14.0, 25.0)
    early, _ = _run("main_bearing_temp_sensor_wire_break", 0.4, 14.0, 25.0)
    assert early == healthy
    assert _run("wind_vane1_stuck", 0.4, 14.0, 25.0)[0] == healthy


def test_second_sensors_follow_the_same_component() -> None:
    """軸承溫度 2 / 定子溫度 2：健康時貼近溫度 1；真故障時一起變化（軸承 2 升約三成，定子 2 一起升）。"""
    healthy, _ = _run(None, 0.0, 14.0, 25.0)
    assert abs(_mean(healthy, _tag("WGEN_GnBrgTmp2")) - _mean(healthy, _tag("WGEN_GnBrgTmp1"))) < 3.0
    assert abs(_mean(healthy, _tag("WGEN_GnStaTmp2")) - _mean(healthy, _tag("WGEN_GnStaTmp1"))) < 3.0
    stator, _ = _run("stator_winding_degradation", 1.0, 14.0, 25.0)
    rise_1 = _mean(stator, _tag("WGEN_GnStaTmp1")) - _mean(healthy, _tag("WGEN_GnStaTmp1"))
    rise_2 = _mean(stator, _tag("WGEN_GnStaTmp2")) - _mean(healthy, _tag("WGEN_GnStaTmp2"))
    assert rise_2 == pytest.approx(rise_1, abs=1.0), "同一個繞組的兩支 Pt100 一起升溫"
    bearing, _ = _run("bearing_wear", 1.0, 14.0, 25.0)
    rise_b1 = _mean(bearing, _tag("WGEN_GnBrgTmp1")) - _mean(healthy, _tag("WGEN_GnBrgTmp1"))
    rise_b2 = _mean(bearing, _tag("WGEN_GnBrgTmp2")) - _mean(healthy, _tag("WGEN_GnBrgTmp2"))
    assert 0.2 * rise_b1 < rise_b2 < 0.5 * rise_b1, "軸承 1 磨耗，軸承 2 也跟著升（約三成）——與感測器故障分得出來"
    assert _mean(bearing, _tag("WGEN_GnBrgTmp2")) < SPEC.gen_bearing_alarm


# ─────────────────────────────────────────────────────────────────────────
# 4. 守門：新感測器不動主 RNG、熱阻倍率邊界
# ─────────────────────────────────────────────────────────────────────────


def test_new_sensors_draw_only_from_aux_rng() -> None:
    """替換 ``_aux_rng`` 只改變新感測器，既有 tag 逐位元不變（保護既有校準的健康輸出）。"""
    a = TurbinePhysicsModel(seed=5)
    b = TurbinePhysicsModel(seed=5)
    b._aux_rng = np.random.RandomState(999)
    aux = TurbinePhysicsModel._AUX_SENSOR_TAGS
    aux_differs = False
    for i in range(300):
        wind = 11.0 + (i % 40) * 0.05
        oa = a.step(wind_speed=wind, wind_direction=180.0, ambient_temp=20.0, dt=1.0)
        ob = b.step(wind_speed=wind, wind_direction=180.0, ambient_temp=20.0, dt=1.0)
        assert {k: v for k, v in oa.items() if k not in aux} == {k: v for k, v in ob.items() if k not in aux}
        aux_differs = aux_differs or any(oa[k] != ob[k] for k in aux)
    assert aux_differs


def test_second_pt100s_have_their_own_rng_stream() -> None:
    """軸承 / 定子溫度 2 的雜訊走 ``_rtd_rng``：換掉它只改變這兩個 tag，主 RNG 與既有 aux 感測器都不受影響。"""
    a = TurbinePhysicsModel(seed=5)
    b = TurbinePhysicsModel(seed=5)
    b._rtd_rng = np.random.RandomState(999)
    rtd = TurbinePhysicsModel._RTD_SENSOR_TAGS
    assert not rtd & TurbinePhysicsModel._AUX_SENSOR_TAGS
    differs = False
    for i in range(300):
        wind = 11.0 + (i % 40) * 0.05
        oa = a.step(wind_speed=wind, wind_direction=180.0, ambient_temp=20.0, dt=1.0)
        ob = b.step(wind_speed=wind, wind_direction=180.0, ambient_temp=20.0, dt=1.0)
        assert {k: v for k, v in oa.items() if k not in rtd} == {k: v for k, v in ob.items() if k not in rtd}
        differs = differs or any(oa[k] != ob[k] for k in rtd)
    assert differs


def test_pitch_motor_currents_have_their_own_rng_stream() -> None:
    """變槳馬達電流的雜訊走 ``_ext_rng``（WMOM-20261021-08-c）：換掉它只改變這三個 tag。"""
    a = TurbinePhysicsModel(seed=5)
    b = TurbinePhysicsModel(seed=5)
    b._ext_rng = np.random.RandomState(999)
    ext = TurbinePhysicsModel._EXT_SENSOR_TAGS
    assert not ext & (TurbinePhysicsModel._AUX_SENSOR_TAGS | TurbinePhysicsModel._RTD_SENSOR_TAGS)
    differs = False
    for i in range(300):
        wind = 11.0 + (i % 40) * 0.05
        oa = a.step(wind_speed=wind, wind_direction=180.0, ambient_temp=20.0, dt=1.0)
        ob = b.step(wind_speed=wind, wind_direction=180.0, ambient_temp=20.0, dt=1.0)
        assert {k: v for k, v in oa.items() if k not in ext} == {k: v for k, v in ob.items() if k not in ext}
        differs = differs or any(oa[k] != ob[k] for k in ext)
    assert differs


def test_pitch_motor_fault_raises_only_blade_1_current_and_total_current_follows_load() -> None:
    """變槳驅動劣化只抬高葉片 1 的電流（固定多出一段），葉片角度與另外兩支不變；負載高時總電流較高。"""
    healthy, _ = _run(None, 0.0, 14.0, 25.0)
    faulty, _ = _run("pitch_motor_fault", 1.0, 14.0, 25.0)
    for tag in ("WROT_PtMotCurBl2", "WROT_PtMotCurBl3", "WROT_PtAngValBl1", "WROT_PtAngValBl2"):
        assert _mean(faulty, _tag(tag)) == pytest.approx(_mean(healthy, _tag(tag)))
    low, _ = _run("pitch_motor_fault", 1.0, 9.0, 25.0)
    assert _mean(low, _tag("WROT_PtMotCurBl1")) < _mean(faulty, _tag("WROT_PtMotCurBl1"))


def test_yaw_misalignment_loses_power_with_no_vane_disagreement() -> None:
    """靜態偏航失準：兩支風向標一致（不會 233）、發電低於健康機組約 cos³、側向彎矩增加。"""
    healthy, _ = _run(None, 0.0, 14.0, 25.0)
    misaligned, _ = _run("yaw_misalignment", 1.0, 14.0, 25.0)
    assert _mean(misaligned, _vane_disc) == pytest.approx(_mean(healthy, _vane_disc), abs=0.5)
    ratio = _mean(misaligned, _tag("WTUR_TotPwrAt")) / _mean(healthy, _tag("WTUR_TotPwrAt"))
    assert ratio == pytest.approx(math.cos(math.radians(16.0)) ** 3, abs=0.02)
    assert _mean(misaligned, _tag("WLOD_TwrSsMom")) > 2.0 * _mean(healthy, _tag("WLOD_TwrSsMom"))


def test_resistance_scale_raises_steady_state_and_never_lowers_it() -> None:
    def steady(scale: float) -> float:
        el = ThermalElement(thermal_resistance=0.5, time_constant=10.0, initial_temp=20.0)
        for _ in range(500):
            el.step(heat_input_kw=40.0, ambient_temp=20.0, dt=1.0, resistance_scale=scale)
        return el.temperature

    assert steady(1.0) == pytest.approx(40.0, abs=0.01)
    assert steady(2.0) == pytest.approx(60.0, abs=0.01)
    assert steady(0.3) == pytest.approx(steady(1.0))  # < 1 夾到 1：劣化參數不會讓元件變涼


def test_cooling_degradation_is_floored_at_five_times_resistance() -> None:
    def water_after(degradation: float) -> float:
        ts = ThermalSystem()
        out: Dict[str, float] = {}
        for _ in range(3000):
            out = ts.step(gen_power_kw=2000.0, grid_power_kw=1950.0, rotor_speed=20.0, ambient_temp=25.0,
                          gen_efficiency=0.95, dt=5.0, wind_speed=12.0, tur_state=6,
                          cooling_degradation={"water": degradation})
        return out["cnv_water"]

    assert water_after(0.05) == pytest.approx(water_after(0.2))
    assert water_after(0.2) > water_after(0.5) > water_after(1.0)


# ─────────────────────────────────────────────────────────────────────────
# yaw_sensor_drift：每台機組都在滿嚴重度跳 233、半嚴重度不跳（WMOM-20261022-02）
# ─────────────────────────────────────────────────────────────────────────

# 風向標 1 / 2 安裝偏差的範圍（TurbinePhysicsModel：yaw_sensor_bias ±2.5°、_vane2_bias ±2°）
VANE_BIAS_DIFF_MAX = 2.5 + 2.0
# 每台機組的 PLC 濾波差異＝漂移 + (風向標 1 − 風向標 2 的偏差)；留 3° 餘裕（＝233 的解除遲滯）
VANE_MARGIN_DEG = 3.0


def _vane_bias_diff(seed: int) -> float:
    model = TurbinePhysicsModel(seed=seed)
    return float(model._individuality["yaw_sensor_bias"] - model._vane2_bias)


def test_yaw_drift_reaches_233_for_every_vane_bias_but_not_at_half_severity() -> None:
    """機制：偏差差在理論範圍內任何值，滿嚴重度都越過 15° + 餘裕、0.5 都還差餘裕。"""
    full = YAW_SENSOR_DRIFT_MAX_DEG
    half = YAW_SENSOR_DRIFT_MAX_DEG * 0.5 ** 2
    assert full - VANE_BIAS_DIFF_MAX >= SPEC.vane_discrepancy_deg + VANE_MARGIN_DEG
    assert half + VANE_BIAS_DIFF_MAX <= SPEC.vane_discrepancy_deg - VANE_MARGIN_DEG
    diffs = [_vane_bias_diff(seed) for seed in range(1, 301)]
    assert max(abs(d) for d in diffs) <= VANE_BIAS_DIFF_MAX


def _extreme_vane_bias_seeds() -> List[int]:
    diffs = sorted((_vane_bias_diff(seed), seed) for seed in range(1, 301))
    # 偏差差最負 / 最正的機組，加上 review 找到的原始重現種子（33 / 34 / 119 修正前永遠不跳）
    return sorted({diffs[0][1], diffs[-1][1], 33, 34, 119})


@pytest.mark.parametrize("seed", _extreme_vane_bias_seeds())
def test_yaw_drift_trips_233_on_extreme_vane_bias_turbines(seed: int) -> None:
    """端到端（PLC 開啟）：滿嚴重度一小時內跳 233，嚴重度 0.5 不跳。"""
    for severity, expect in ((1.0, True), (0.5, False)):
        model = TurbinePhysicsModel(seed=seed)
        model.active_faults = [{"scenario_id": "yaw_sensor_drift", "severity": severity}]
        codes = set()
        for _ in range(int(3600 / DT)):
            model.step(wind_speed=12.0, wind_direction=180.0, ambient_temp=20.0, dt=DT)
            codes |= {e.code for e in model.plc.drain_events() if e.kind == "trip"}
        assert (233 in codes) is expect, f"seed {seed} severity {severity}: {codes}"
