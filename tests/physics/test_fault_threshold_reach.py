"""Fault physics reach real Z72 protection setpoints（WMOM-20261021-03a，EPIC-DS Phase 1b）。

外部 RAG 維修助手看到的警報要由「物理訊號越過真實 PLC 判定條件」觸發（Phase 1b 下一步
WMOM-20261021-03b），前提是故障物理真的能把量測值推過 Z72 手冊 / spec 的門檻。校正前多數
故障離門檻很遠（例：bearing_wear 滿嚴重度軸承只到 44 °C，門檻 85 / 95 °C）。

本檔鎖住三件事（3 h 模擬、dt = 5 s，取最後 5 分鐘）：

1. 健康機組在 30 °C 與天氣模型最熱的 37 °C（7-8 月正午）各風速下，所有監控訊號都低於警報
   設定值——不會整天誤報（37 °C 時手冊的機艙控制櫃 50 °C 會被健康機組碰到，真機亦然，不檢查）
2. 每個故障情境在高負載（14 m/s、25 °C）滿嚴重度時，量測值越過該情境跳機事件的真實設定值
3. 中等嚴重度（0.5）時還沒到跳機設定值——跳機發生在故障後期，不是一注入就跳

另有兩組守門測試：新感測器只用 ``_aux_rng``（既有 tag 的健康輸出不受影響）、熱阻倍率的邊界。

設定值來源見 ``TurbineSpec``（manual = 手冊 Appendix C、assumed = 手冊僅寫 See [ABB] 的假設）。
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Callable, Dict, List, Tuple

import numpy as np
import pytest

from simulator.physics import TurbinePhysicsModel
from simulator.physics.thermal_model import ThermalElement, ThermalSystem
from simulator.physics.turbine_physics import TurbineSpec

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
            samples.append(dict(out))
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
    ("264 stator", _tag("WGEN_GnStaTmp1"), "<", SPEC.gen_stator_alarm),
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
    """grid_voltage_sag：端電壓持續低於 LVRT band 1（0.90 p.u.）或電網保護下限而停機（ARU 欠壓，事件 481）。"""
    samples, cause = _run("grid_voltage_sag", severity, 14.0, 25.0)
    assert min(s["WCNV_VtgMsCnvGd1"] for s in samples) < LVRT_BAND1_PU * NOMINAL_LN_KV
    assert samples[-1]["WTUR_TurSt"] != 6
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
