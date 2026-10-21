"""Z72 PLC 保護層單元測試（WMOM-20261021-03-b）。

以「健康基準輸出 + 覆寫個別訊號」逐步驅動 ``PlcProtection.evaluate``，驗證：

- A 警報：延時才成立（從第一個越限樣本起算的經過時間 ≥ 延時）、遲滯才解除；判定窗關閉不等於解除
- T 跳機：回傳停機要求（T1 / T2）、鎖存到條件解除、手冊每小時上限內自動解除、超過則封鎖需復位
- 操作員復位：解除鎖存；條件仍成立則下一步再跳
- 葉片差異三段延時、風向標 25 s 濾波 + 10 分鐘風速條件、只在發電時判定的靜水壓
- 物理層保護停機（超速 / LVRT / 電網 / 切出）補碼
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import pytest

from shared.alarm_codes import find_alarm
from simulator.physics.plc_protection import PlcEvent, PlcProtection, build_rules
from simulator.physics.turbine_physics import TurbineSpec

SPEC = TurbineSpec()
NOMINAL_LN_KV = SPEC.nominal_voltage / (3 ** 0.5) / 1000.0

HEALTHY: Dict[str, float] = {
    "WROT_PtAngValBl1": -1.0, "WROT_PtAngValBl2": -1.0, "WROT_PtAngValBl3": -1.0,
    "WYAW_YwVn1AlgnAvg5s": 0.0, "WYAW_YwVn2AlgnAvg5s": 0.0, "WMET_WSpeedNac": 10.0,
    "WGEN_GnBrgTmp1": 45.0, "WGEN_GnStaTmp1": 70.0, "WNAC_NacTmp": 30.0, "WNAC_NacCabTmp": 36.0,
    "WGDC_TrfCoreTmp": 40.0, "WCNV_IGCTWtrTmp": 35.0, "WCNV_CnvCabinTmp": 44.0,
    "WCNV_IGCTWtrPres1": 3.5, "WYAW_YwBrkHyPrs": 210.0, "WYAW_YwBrkSealsLeak": 0.0,
    "WNAC_VibMsNacXDir": 1.0, "WNAC_VibMsNacYDir": 1.0, "WCNV_VtgMsCnvGd1": NOMINAL_LN_KV,
}


class Driver:
    """逐秒驅動 PLC 並累積事件。"""

    def __init__(self) -> None:
        self.plc = PlcProtection(SPEC)
        self.t = 0.0
        self.events: List[PlcEvent] = []

    def run(self, seconds: float, producing: bool = True, dt: float = 1.0, yawing: bool = False,
            **signals: float) -> List[tuple]:
        out = dict(HEALTHY)
        out.update(signals)
        trips: List[tuple] = []
        steps = int(round(seconds / dt))
        for _ in range(steps):
            self.t += dt
            trips += self.plc.evaluate(out, self.t, dt, producing, yawing)
            self.events += self.plc.drain_events()
        return trips

    def kinds(self, code: int) -> List[str]:
        return [e.kind for e in self.events if e.code == code]


def test_healthy_signals_raise_nothing() -> None:
    d = Driver()
    assert d.run(600) == []
    assert d.events == []
    assert not d.plc.restart_inhibited


def test_every_rule_code_is_a_real_z72_event_with_matching_meaning() -> None:
    for rule in build_rules(SPEC):
        alarm = find_alarm(rule.code)
        assert alarm is not None, rule.code
        assert alarm.level in ("A", "T1", "T2")


def test_alarm_needs_delay_and_clears_only_past_hysteresis() -> None:
    d = Driver()
    d.run(10, WGEN_GnBrgTmp1=86.0)
    assert d.kinds(262) == []                       # 延時 10 s：須持續超過 10 s
    d.run(1, WGEN_GnBrgTmp1=86.0)
    assert d.kinds(262) == ["alarm_raised"]
    assert d.events[-1].value == 86.0 and d.events[-1].setpoint == SPEC.gen_bearing_alarm
    d.run(5, WGEN_GnBrgTmp1=83.0)                   # 遲滯 3 °C：> 82 仍成立
    assert d.kinds(262) == ["alarm_raised"]
    d.run(1, WGEN_GnBrgTmp1=81.0)
    assert d.kinds(262) == ["alarm_raised", "alarm_cleared"]
    assert not d.plc.restart_inhibited              # 警報不擋重啟


def test_trip_latches_until_condition_clears_then_auto_resets_within_hourly_limit() -> None:
    d = Driver()
    assert d.run(5, WGEN_GnBrgTmp1=96.0) == []      # 跳機延時 5 s：須持續超過 5 s
    trips = d.run(1, WGEN_GnBrgTmp1=96.0)
    assert trips == [(240, "T1")]
    assert d.plc.restart_inhibited
    d.run(60, WGEN_GnBrgTmp1=91.0)                  # 遲滯 5 °C：> 90 仍鎖存
    assert d.kinds(240) == ["trip"]
    assert d.plc.restart_inhibited
    d.run(1, WGEN_GnBrgTmp1=80.0)
    assert d.kinds(240) == ["trip", "trip_cleared"]  # 手冊 240 每小時上限 1：第一次可自動復歸
    assert not d.plc.restart_inhibited


def test_exceeding_hourly_trip_limit_blocks_restart_until_operator_reset() -> None:
    d = Driver()
    d.run(6, WGEN_GnBrgTmp1=96.0)
    d.run(1, WGEN_GnBrgTmp1=80.0)                   # 第 1 次：自動復歸
    d.run(6, WGEN_GnBrgTmp1=96.0)                   # 一小時內第 2 次
    d.run(1, WGEN_GnBrgTmp1=80.0)
    assert d.kinds(240) == ["trip", "trip_cleared", "trip", "restart_blocked"]
    d.run(600, WGEN_GnBrgTmp1=60.0)
    assert d.plc.restart_inhibited                  # 封鎖不會自己解除
    d.plc.operator_reset(d.t)
    d.events += d.plc.drain_events()
    assert not d.plc.restart_inhibited
    assert [e.kind for e in d.events if e.code == 8] == ["operator_reset"]


def test_trip_auto_resets_again_after_the_hour_window() -> None:
    d = Driver()
    d.run(6, WGEN_GnBrgTmp1=96.0)
    d.run(1, WGEN_GnBrgTmp1=80.0)
    d.run(3600, WGEN_GnBrgTmp1=60.0)                # 超過一小時
    d.run(6, WGEN_GnBrgTmp1=96.0)
    d.run(1, WGEN_GnBrgTmp1=80.0)
    assert d.kinds(240) == ["trip", "trip_cleared", "trip", "trip_cleared"]


def test_operator_reset_while_condition_persists_trips_again() -> None:
    d = Driver()
    d.run(6, WGEN_GnBrgTmp1=96.0)
    d.plc.operator_reset(d.t)
    trips = d.run(1, WGEN_GnBrgTmp1=96.0)
    assert trips == [(240, "T1")]
    assert d.plc.restart_inhibited


def test_converter_cooling_trip_also_raises_converter_trip_request() -> None:
    d = Driver()
    trips = d.run(6, WCNV_IGCTWtrTmp=SPEC.cooling_water_trip + 1.0)
    assert sorted(trips) == [(21, "T1"), (437, "T1")]


@pytest.mark.parametrize(("disc", "seconds", "expect_trip"), [
    (1.5, 5, False), (1.5, 6, True),     # > 1° 需持續超過 5 s
    (3.5, 3, False), (3.5, 4, True),     # > 3° 需持續超過 3 s
    (9.0, 1, True),                      # > 8° 瞬間
])
def test_blade_discrepancy_three_stage_delays(disc: float, seconds: int, expect_trip: bool) -> None:
    d = Driver()
    d.run(60)                                       # 穩定發電 60 s 後才判定葉片差異
    trips = d.run(seconds, WROT_PtAngValBl1=-1.0 + disc)
    codes = {c for c, _ in trips}
    assert (335 in codes) is expect_trip
    if expect_trip:
        assert codes == {335, 336}       # 葉片 1 偏 → 1-2、1-3 同時失步
        assert all(level == "T2" for _, level in trips)


@pytest.mark.parametrize("disc", [1.6, 3.5])   # 5 s 規則（> 1°）與 3 s 規則（> 3°）
def test_single_sample_does_not_satisfy_a_delay_at_coarse_time_steps(disc: float) -> None:
    """批次子步 5 s：單一越限樣本的經過時間是 0，不算「持續」；連續兩個樣本才跳。"""
    d = Driver()
    d.run(60, dt=5.0)
    assert d.run(5, dt=5.0, WROT_PtAngValBl1=-1.0 + disc) == []
    assert d.run(5, dt=5.0, WROT_PtAngValBl1=-1.0 + disc) != []


def test_latched_trip_is_not_cleared_when_the_judgement_window_closes() -> None:
    """葉片差異跳機後機組停機（判定窗關閉），差異仍在 → 維持鎖存；差異消失才解除。"""
    d = Driver()
    d.run(60)
    assert d.run(6, WROT_PtAngValBl1=0.5) != []
    d.run(60, producing=False, WROT_PtAngValBl1=0.5)
    assert d.kinds(335) == ["trip"]
    assert d.plc.restart_inhibited
    d.run(1, producing=False)
    assert d.kinds(335) == ["trip", "trip_cleared"]


def test_alarm_stays_raised_while_yawing_releases_the_brake() -> None:
    d = Driver()
    d.run(91)
    d.run(11, WYAW_YwBrkHyPrs=170.0)
    assert d.kinds(260) == ["alarm_raised"]
    d.run(30, yawing=True, WYAW_YwBrkHyPrs=20.0)     # 偏航中煞車鬆開：不是條件解除
    assert d.kinds(260) == ["alarm_raised"]


def test_event_value_and_setpoint_come_from_the_rule_that_fired() -> None:
    d = Driver()
    d.run(60)
    d.run(6, WROT_PtAngValBl1=0.5)                     # 1.5°，由「5 s > 1°」規則成立
    trip = next(e for e in d.events if e.code == 335 and e.kind == "trip")
    assert (trip.value, trip.setpoint) == (1.5, SPEC.blade_discrepancy_5s_deg)

    d2 = Driver()
    d2.run(6, WCNV_CnvCabinTmp=SPEC.converter_cabinet_trip + 1.0)   # 021 由機櫃溫度觸發
    req = next(e for e in d2.events if e.code == 21 and e.kind == "trip")
    assert (req.value, req.setpoint) == (SPEC.converter_cabinet_trip + 1.0, SPEC.converter_cabinet_trip)


def test_blade_discrepancy_ignored_during_startup_transient_and_while_stopped() -> None:
    d = Driver()
    assert d.run(59, WROT_PtAngValBl1=5.0) == []    # 併網後 60 s 內：變槳暫態
    d2 = Driver()
    assert d2.run(120, producing=False, WROT_PtAngValBl1=20.0) == []


def test_vane_discrepancy_uses_25s_filter_and_needs_wind() -> None:
    calm = Driver()
    calm.run(600, WYAW_YwVn1AlgnAvg5s=20.0, WMET_WSpeedNac=3.0)
    assert calm.kinds(233) == []                    # 10 分鐘平均風速 ≤ 4.5 m/s 不判定

    d = Driver()
    d.run(60)                                       # 濾波器先以健康讀值收斂
    d.run(10, WYAW_YwVn1AlgnAvg5s=20.0)
    assert d.kinds(233) == []                       # 25 s 濾波，10 s 內還不到 15°
    trips = d.run(60, WYAW_YwVn1AlgnAvg5s=20.0)
    assert (233, "T1") in trips


def test_static_water_pressure_only_judged_while_producing() -> None:
    d = Driver()
    d.run(60, producing=False, WCNV_IGCTWtrPres1=0.0)
    assert d.kinds(432) == []
    d.run(11, producing=True, WCNV_IGCTWtrPres1=2.0)
    assert d.kinds(432) == ["alarm_raised"]


def test_yaw_brake_pressure_judged_only_after_brakes_applied_90s() -> None:
    d = Driver()
    assert d.run(30, yawing=True, WYAW_YwBrkHyPrs=20.0) == []      # 偏航中煞車鬆開
    assert d.run(80, WYAW_YwBrkHyPrs=120.0) == []                   # 煞車回壓中
    trips = d.run(25, WYAW_YwBrkHyPrs=120.0)                        # 施加滿 90 s 後判定（T 延時 5 s、A 延時 10 s）
    assert (228, "T1") in trips
    assert d.kinds(260) == ["alarm_raised"]


def test_protection_stops_are_coded_but_do_not_inhibit_restart() -> None:
    d = Driver()
    d.run(1)
    assert d.plc.note_protection_stop("overspeed_software", d.t) == [351]
    assert d.plc.note_protection_stop("overspeed_software", d.t) == []   # 同一停機不重複
    assert not d.plc.restart_inhibited
    d.plc.on_restart(d.t)
    events = d.plc.drain_events()
    assert [(e.kind, e.code, e.source) for e in events] == [
        ("trip", 351, "protection"), ("trip_cleared", 351, "protection"),
    ]


def test_protection_stop_is_coded_again_after_each_restart_attempt() -> None:
    """起動中再遇電網擾動（未到發電）也要記事件：以每次起動為一個停機週期。"""
    d = Driver()
    d.run(1, WCNV_VtgMsCnvGd1=0.78 * NOMINAL_LN_KV)
    assert d.plc.note_protection_stop("grid_trip", d.t) == [482, 21]
    d.plc.on_restart(d.t)
    assert d.plc.note_protection_stop("grid_trip", d.t) == [482, 21]


@pytest.mark.parametrize(("cause", "voltage_pu", "codes"), [
    ("ride_through:lvrt_band1", 0.85, [481, 21]),
    ("ride_through:lvrt_band2", 0.70, [482, 21]),   # < 0.80 p.u.，與電網保護 0.81 一致
    ("ride_through:lvrt_band3", 0.40, [482, 21]),
    ("ride_through:hvrt_band1", 1.15, [475, 21]),
    ("grid_protection", 0.85, [481, 21]),
    ("grid_protection", 0.79, [482, 21]),
    ("grid_trip", 0.78, [482, 21]),
    ("grid_trip", 0.88, [481, 21]),
    ("grid_trip", 1.12, [475, 21]),
    ("grid_trip", 1.00, [489, 21]),       # 電壓正常 → 頻率越界
    ("overspeed_hardware", 1.00, [320]),
    ("operator", 1.00, []),
])
def test_protection_cause_to_event_code(cause: str, voltage_pu: float, codes: List[int]) -> None:
    d = Driver()
    d.run(1, WCNV_VtgMsCnvGd1=voltage_pu * NOMINAL_LN_KV)
    assert d.plc.note_protection_stop(cause, d.t) == codes


def test_cut_out_is_an_information_event() -> None:
    d = Driver()
    assert d.plc.note_protection_stop("cut_out", 0.0) == []
    (event,) = d.plc.drain_events()
    assert (event.kind, event.code, event.level) == ("info", 201, "I")


def test_disabled_plc_is_silent() -> None:
    d = Driver()
    d.plc.enabled = False
    assert d.run(30, WGEN_GnBrgTmp1=120.0) == []
    assert d.plc.note_protection_stop("overspeed_software", 1.0) == []
    assert d.events == []


def test_disabling_plc_releases_restart_inhibit() -> None:
    d = Driver()
    d.run(6, WGEN_GnBrgTmp1=120.0)
    assert d.plc.restart_inhibited
    d.plc.enabled = False
    assert not d.plc.restart_inhibited


def test_event_queue_is_bounded_when_nobody_drains() -> None:
    plc = PlcProtection(SPEC)
    out = dict(HEALTHY)
    for i in range(2000):
        out["WGEN_GnBrgTmp1"] = 90.0 if i % 40 < 20 else 70.0   # 警報反覆起落
        plc.evaluate(out, float(i), 1.0, True)
    assert len(plc.drain_events()) <= 512
