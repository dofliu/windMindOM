"""Z72 PLC 保護層單元測試（WMOM-20261021-03-b）。

以「健康基準輸出 + 覆寫個別訊號」逐步驅動 ``PlcProtection.evaluate``，驗證：

- A 警報：延時才成立（從第一個越限樣本起算的經過時間 ≥ 延時）、遲滯才解除；判定窗關閉不等於解除
- Pt100 溫度以手冊 CDTauPT100（10 s）濾波後判定、沒有事件延時；斷線讀值不進濾波器（WMOM-20261022-02）
- T 跳機：回傳停機要求（T1 / T2）、鎖存到條件解除、手冊每小時上限內自動解除、超過則封鎖並送 A039、需復位
- 操作員復位：解除鎖存與 A039；條件仍成立則下一步再跳
- 葉片差異三段延時、風向標 25 s 濾波 + 60 s 平均風速條件 + 60 s 延時、只在發電時判定的靜水壓
- 偏航煞車液壓（Appendix D）：170 / 150 bar、延時 30 s、> 190 bar 才解除
- 物理層保護停機（超速 / LVRT / 電網 / 切出）補碼，跳機次數與訊號跳機同一套每碼計數
- 偏航逾時 223（Appendix D SDYawTmOutFact / Offs）：對風超過 factor × 誤差 ÷ 偏航速度 + offset；解纜不算
  （WMOM-20261021-08-b）
"""

from __future__ import annotations

import math
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
    "WGEN_GnBrgTmp2": 44.0, "WGEN_GnStaTmp2": 70.5,
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
            unwinding: bool = False, **signals: float) -> List[tuple]:
        out = dict(HEALTHY)
        out.update(signals)
        trips: List[tuple] = []
        steps = int(round(seconds / dt))
        for _ in range(steps):
            self.t += dt
            trips += self.plc.evaluate(out, self.t, dt, producing, yawing, unwinding)
            self.events += self.plc.drain_events()
        return trips

    def kinds(self, code: int) -> List[str]:
        return [e.kind for e in self.events if e.code == code]

    def drain(self) -> None:
        self.events += self.plc.drain_events()


def _steps_to_cross(start: float, target: float, setpoint: float, tau: float = SPEC.pt100_filter_tau_s) -> int:
    """1 s 步長的一階濾波從 start 走向 target，第幾步越過 setpoint（手冊 CDTauPT100）。"""
    return math.ceil(tau * math.log((target - start) / (target - setpoint)) + 1e-9)


def _trip_and_clear_240(d: Driver) -> None:
    """主軸承 1 溫度升到跳機（240，濾波值越過 95 °C），再降溫到條件解除。"""
    for _ in range(120):
        if d.run(1, WGEN_GnBrgTmp1=140.0):
            break
    d.run(60, WGEN_GnBrgTmp1=20.0)


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


def test_pt100_temperature_is_judged_after_the_10s_filter_and_clears_past_hysteresis() -> None:
    d = Driver()
    d.run(1)                                        # 濾波器以健康讀值起算
    n = _steps_to_cross(HEALTHY["WGEN_GnBrgTmp1"], 86.0, SPEC.gen_bearing_alarm)
    assert n == 38                                  # 45 → 86 °C、τ 10 s：濾波值第 38 s 才過 85 °C
    d.run(n - 1, WGEN_GnBrgTmp1=86.0)
    assert d.kinds(262) == []
    d.run(1, WGEN_GnBrgTmp1=86.0)
    assert d.kinds(262) == ["alarm_raised"]
    raised = d.events[-1]
    assert SPEC.gen_bearing_alarm < raised.value < 86.0       # 事件帶的是 PLC 看到的濾波值
    assert raised.setpoint == SPEC.gen_bearing_alarm
    d.run(60, WGEN_GnBrgTmp1=83.0)                  # 遲滯 3 °C：> 82 仍成立
    assert d.kinds(262) == ["alarm_raised"]
    d.run(30, WGEN_GnBrgTmp1=60.0)
    assert d.kinds(262) == ["alarm_raised", "alarm_cleared"]
    assert not d.plc.restart_inhibited              # 警報不擋重啟


def test_broken_pt100_reading_does_not_pass_through_the_filter() -> None:
    """斷線讀值（850 °C）只報感測器故障；接回後濾波器從讀值重新起算，不會殘留高溫而跳 240。"""
    d = Driver()
    d.run(1)
    d.run(10, WGEN_GnBrgTmp1=SPEC.pt100_broken_wire_c)
    assert d.kinds(242) == ["trip"] and d.kinds(240) == [] and d.kinds(262) == []
    d.run(10)
    assert d.kinds(242) == ["trip", "trip_cleared"]
    assert d.kinds(240) == [] and d.kinds(262) == []
    assert not d.plc.restart_inhibited


def test_trip_latches_until_condition_clears_then_auto_resets_within_hourly_limit() -> None:
    d = Driver()
    d.run(1)
    n = _steps_to_cross(HEALTHY["WGEN_GnBrgTmp1"], 96.0, SPEC.gen_bearing_trip)
    assert d.run(n - 1, WGEN_GnBrgTmp1=96.0) == []
    trips = d.run(1, WGEN_GnBrgTmp1=96.0)
    assert trips == [(240, "T1")]
    assert d.plc.restart_inhibited
    d.run(60, WGEN_GnBrgTmp1=91.0)                  # 遲滯 5 °C：> 90 仍鎖存
    assert d.kinds(240) == ["trip"]
    assert d.plc.restart_inhibited
    d.run(30, WGEN_GnBrgTmp1=80.0)
    assert d.kinds(240) == ["trip", "trip_cleared"]  # 手冊 240 每小時上限 1：第一次可自動復歸
    assert not d.plc.restart_inhibited
    assert d.kinds(39) == []


def test_exceeding_hourly_trip_limit_raises_a039_until_operator_reset() -> None:
    """手冊 §8.3：同一個跳機碼一小時內超過上限 → 不自動重啟，送 A039「Auto restart blocked」，按 TURBINE RESET 才解除。"""
    d = Driver()
    d.run(1)
    _trip_and_clear_240(d)                          # 第 1 次：自動復歸
    _trip_and_clear_240(d)                          # 一小時內第 2 次：條件解除時封鎖
    assert d.kinds(240) == ["trip", "trip_cleared", "trip"]
    assert d.kinds(39) == ["alarm_raised"]
    a039 = next(e for e in d.events if e.code == 39)
    assert (a039.level, a039.text, a039.plc_tag, a039.source) == (
        "A", "Auto restart blocked", "Z72PLC__ActiveAlarm", "restart")
    assert d.plc.auto_restart_blocked and d.plc.restart_inhibited
    assert d.plc.active_codes() == {240: "T1", 39: "A"}
    assert d.plc.active_lists.snapshot() == {"A": [39], "T1": [240], "T2": []}
    d.run(600, WGEN_GnBrgTmp1=60.0)
    assert d.plc.auto_restart_blocked               # 封鎖不會自己解除
    assert "restart_blocked" not in {e.kind for e in d.events}   # 合約 v1.4 起不再送
    d.plc.operator_reset(d.t)
    d.drain()
    assert not d.plc.restart_inhibited and not d.plc.auto_restart_blocked
    reset_events = [(e.kind, e.code) for e in d.events if e.code in (8, 39, 240)][-3:]
    assert reset_events == [("operator_reset", 8), ("alarm_cleared", 39), ("trip_cleared", 240)]
    assert d.plc.active_codes() == {}
    assert d.plc.active_lists.snapshot() == {"A": [], "T1": [], "T2": []}


def test_a039_is_raised_once_while_several_codes_are_blocked() -> None:
    d = Driver()
    d.run(1)
    for _ in range(2):
        d.plc.note_protection_stop("grid_trip", d.t)   # 電壓正常 → 489 + 021，每小時上限各 1
        d.plc.on_restart(d.t)
    _trip_and_clear_240(d)
    _trip_and_clear_240(d)
    d.drain()
    assert d.kinds(39) == ["alarm_raised"]
    d.plc.operator_reset(d.t)
    d.drain()
    assert d.kinds(39) == ["alarm_raised", "alarm_cleared"]


def test_maintenance_release_clears_a039_and_lets_the_latched_trip_clear() -> None:
    d = Driver()
    d.run(1)
    _trip_and_clear_240(d)
    _trip_and_clear_240(d)
    assert d.plc.auto_restart_blocked
    d.plc.maintenance_release(d.t)
    d.run(1)
    assert [(e.kind, e.code) for e in d.events if e.code in (8, 39, 240)][-3:] == [
        ("operator_reset", 8), ("alarm_cleared", 39), ("trip_cleared", 240)]
    assert not d.plc.restart_inhibited


def test_trip_auto_resets_again_after_the_hour_window() -> None:
    d = Driver()
    d.run(1)
    _trip_and_clear_240(d)
    d.run(3600, WGEN_GnBrgTmp1=60.0)                # 超過一小時
    _trip_and_clear_240(d)
    assert d.kinds(240) == ["trip", "trip_cleared", "trip", "trip_cleared"]
    assert d.kinds(39) == []


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
    d.run(30, WYAW_YwBrkHyPrs=165.0)
    assert d.kinds(260) == []                        # 手冊 SDYwHyBrkTm：延時 30 s
    d.run(1, WYAW_YwBrkHyPrs=165.0)
    assert d.kinds(260) == ["alarm_raised"]
    d.run(30, yawing=True, WYAW_YwBrkHyPrs=20.0)     # 偏航中煞車鬆開：不是條件解除
    assert d.kinds(260) == ["alarm_raised"]


def test_yaw_brake_pressure_low_events_follow_appendix_d() -> None:
    """Appendix D：SDHyPres_L 170 bar → 260、SDHyPres_LL 150 bar → 228，兩者都要回到 > 190 bar 才解除。"""
    assert (SPEC.yaw_pressure_alarm, SPEC.yaw_pressure_trip, SPEC.yaw_pressure_reset_bar) == (170.0, 150.0, 190.0)
    d = Driver()
    d.run(91)
    d.run(60, WYAW_YwBrkHyPrs=175.0)
    assert d.kinds(260) == []                        # 175 bar：Appendix C 的 180 bar 會報，D 的 170 不報
    trips = d.run(31, WYAW_YwBrkHyPrs=140.0)
    assert (228, "T1") in trips and d.kinds(260) == ["alarm_raised"]
    d.run(60, WYAW_YwBrkHyPrs=185.0)                 # 回到 185 bar：仍未過 190
    assert d.kinds(260) == ["alarm_raised"] and d.kinds(228) == ["trip"]
    d.run(1, WYAW_YwBrkHyPrs=195.0)
    assert d.kinds(260) == ["alarm_raised", "alarm_cleared"]
    assert d.kinds(228) == ["trip", "trip_cleared"]


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


def test_vane_discrepancy_uses_25s_filter_and_60s_delay() -> None:
    d = Driver()
    d.run(60)                                       # 濾波器先以健康讀值收斂
    # 25 s 濾波：20° 的差異第 35 s 才過 15°（20 × (1 − e^(−n/25)) > 15），再持續 60 s（SDWndVnDiscrTm）才跳
    assert d.run(94, WYAW_YwVn1AlgnAvg5s=20.0) == []
    assert d.run(1, WYAW_YwVn1AlgnAvg5s=20.0) == [(233, "T1")]


def test_latched_vane_discrepancy_trip_is_not_cleared_by_a_wind_lull() -> None:
    """風速條件是判定窗（Appendix D「enable」）：風速掉下來不等於差異消失，鎖存的 233 不解除、不會風回來再跳一次。"""
    d = Driver()
    d.run(60)
    assert d.run(95, WYAW_YwVn1AlgnAvg5s=20.0) == [(233, "T1")]
    d.run(300, WYAW_YwVn1AlgnAvg5s=20.0, WMET_WSpeedNac=3.0)       # 風速低谷 5 分鐘
    d.run(300, WYAW_YwVn1AlgnAvg5s=20.0)                           # 風回來
    assert d.kinds(233) == ["trip"] and d.plc.restart_inhibited
    d.run(120)                                                     # 風向標修好：差異消失才解除
    assert d.kinds(233) == ["trip", "trip_cleared"]


def test_vane_discrepancy_wind_condition_is_a_60s_average() -> None:
    """Appendix D 的 SDVw60sWndVnDiscr：60 s 平均風速 > 4.5 m/s 才判定（Appendix C 寫 10 分鐘平均）。"""
    d = Driver()
    d.run(600, WYAW_YwVn1AlgnAvg5s=20.0, WMET_WSpeedNac=3.0)
    assert d.kinds(233) == []                       # 平均風速 ≤ 4.5 m/s 不判定
    # 風速升到 10 m/s：60 s 平均第 15 s 過 4.5 m/s（3 + 7 × (1 − e^(−n/60))），再 60 s 延時
    assert d.run(74, WYAW_YwVn1AlgnAvg5s=20.0) == []
    assert d.run(1, WYAW_YwVn1AlgnAvg5s=20.0) == [(233, "T1")]


def test_static_water_pressure_only_judged_while_producing() -> None:
    d = Driver()
    d.run(60, producing=False, WCNV_IGCTWtrPres1=0.0)
    assert d.kinds(432) == []
    d.run(11, producing=True, WCNV_IGCTWtrPres1=2.0)
    assert d.kinds(432) == ["alarm_raised"]


def test_yaw_brake_pressure_judged_only_after_brakes_applied_90s() -> None:
    d = Driver()
    # 偏航中煞車鬆開（從 20° 誤差開始對風：偏航逾時要 200 s，這裡不會到）
    assert d.run(30, yawing=True, WYAW_YwBrkHyPrs=20.0, WYAW_YwVn1AlgnAvg5s=20.0, WYAW_YwVn2AlgnAvg5s=20.0) == []
    assert d.run(80, WYAW_YwBrkHyPrs=120.0) == []                   # 煞車回壓中
    assert d.run(39, WYAW_YwBrkHyPrs=120.0) == []                   # 施加滿 90 s 後判定，再延時 30 s
    trips = d.run(1, WYAW_YwBrkHyPrs=120.0)
    assert (228, "T1") in trips
    assert d.kinds(260) == ["alarm_raised"]


def _yaw_timeout_s(error_deg: float) -> float:
    return SPEC.yaw_timeout_factor * error_deg / SPEC.yaw_rate_deg_s + SPEC.yaw_timeout_offset_s


def test_yaw_timeout_trips_when_aligning_takes_longer_than_allowed() -> None:
    """從 20° 誤差開始對風，允許 5 × 20 / 0.5 = 200 s；誤差在對風途中不變（追不上）就逾時跳機 223。"""
    d = Driver()
    vanes = {"WYAW_YwVn1AlgnAvg5s": 20.0, "WYAW_YwVn2AlgnAvg5s": 20.0}
    assert _yaw_timeout_s(20.0) == 200.0
    assert d.run(200, yawing=True, **vanes) == []
    assert d.run(1, yawing=True, **vanes) == [(223, "T1")]
    assert d.kinds(223) == ["trip"]


def test_yaw_timeout_allowance_is_fixed_at_the_start_of_each_yaw_run() -> None:
    """允許時間在這一段對風開始時決定；偏航停下就重算，下一段重新計時。"""
    d = Driver()
    big = {"WYAW_YwVn1AlgnAvg5s": 30.0, "WYAW_YwVn2AlgnAvg5s": 30.0}
    small = {"WYAW_YwVn1AlgnAvg5s": 1.0, "WYAW_YwVn2AlgnAvg5s": 1.0}
    assert d.run(250, yawing=True, **big) == []               # 300 s 的額度
    assert d.run(40, yawing=True, **small) == []              # 誤差變小不縮短這一段的額度
    d.run(5)                                                  # 停下
    assert d.run(20, yawing=True, **small) == []              # 新的一段：誤差下限 2° → 20 s
    assert d.run(1, yawing=True, **small) == [(223, "T1")]


def test_unwinding_never_times_out() -> None:
    """解纜（纜線扭轉到上限時的長時間偏航）不算對風，不判偏航逾時。"""
    d = Driver()
    assert d.run(1200, yawing=True, unwinding=True) == []
    assert d.kinds(223) == []


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


def test_protection_trips_share_the_per_code_hourly_limit_and_raise_a039() -> None:
    """物理層保護停機（電網）也照目錄每碼計數：481 / 021 每小時上限 1，一小時內第 2 次封鎖、等操作員復位。"""
    d = Driver()
    d.run(1, WCNV_VtgMsCnvGd1=0.85 * NOMINAL_LN_KV)
    assert d.plc.note_protection_stop("grid_protection", d.t) == [481, 21]
    assert not d.plc.restart_inhibited               # 第 1 次：物理層可自動重啟
    d.plc.on_restart(d.t + 60.0)
    assert d.plc.note_protection_stop("grid_protection", d.t + 600.0) == [481, 21]
    d.drain()
    assert d.kinds(39) == ["alarm_raised"]           # 跳機當下判定：不准自動重啟
    assert d.plc.restart_inhibited and d.plc.auto_restart_blocked
    assert d.plc.active_codes() == {481: "T1", 21: "T1", 39: "A"}
    d.plc.operator_reset(d.t + 900.0)
    d.drain()
    assert not d.plc.restart_inhibited
    assert [(e.kind, e.code) for e in d.events][-2:] == [("operator_reset", 8), ("alarm_cleared", 39)]
    d.plc.on_restart(d.t + 960.0)                    # 保護停機的跳機在再起動時解除
    d.drain()
    assert d.plc.active_codes() == {}


def test_software_overspeed_allows_five_restarts_per_hour() -> None:
    """351 Software overspeed 每小時上限 5：第 6 次才封鎖（不再有全域「每小時 3 次啟動」上限）。"""
    plc = PlcProtection(SPEC)
    for i in range(6):
        assert plc.note_protection_stop("overspeed_software", 100.0 * i) == [351]
        assert plc.restart_inhibited is (i == 5)
        if i < 5:
            plc.on_restart(100.0 * i + 50.0)
    assert [e.code for e in plc.drain_events() if e.kind == "alarm_raised"] == [39]


@pytest.mark.parametrize(("angle", "fault"), [(-5.0, False), (95.0, False), (-5.5, True), (95.5, True)])
def test_blade_encoder_range_is_0_to_90_plus_tolerance(angle: float, fault: bool) -> None:
    """手冊：編碼器範圍 0-90° ± SDVaneLimitTolerance 5°，超出才報 326。"""
    d = Driver()
    d.run(5, WROT_PtAngValBl1=angle)
    assert (d.kinds(326) == ["trip"]) is fault


def test_nacelle_temperature_alarm_at_appendix_d_45c() -> None:
    assert SPEC.nacelle_air_alarm == 45.0
    d = Driver()
    d.run(1)
    d.run(120, WNAC_NacTmp=45.5)
    assert d.kinds(273) == ["alarm_raised"]


def test_farm_specs_saved_earlier_do_not_override_plc_setpoints() -> None:
    """風場存的 turbine_spec 是建立當時的 to_dict()：PLC 設定值以程式為準，機型參數照存檔。"""
    old = TurbineSpec().to_dict() | {"yaw_pressure_alarm": 180.0, "rated_power_kw": 3000.0,
                                     "max_restarts_per_hour": 3}
    spec = TurbineSpec.from_farm_dict(old)
    assert spec.yaw_pressure_alarm == SPEC.yaw_pressure_alarm and spec.rated_power_kw == 3000.0
    assert TurbineSpec.from_dict(old).yaw_pressure_alarm == 180.0     # spec 更新 API 仍可明確改


def test_plc_setpoint_fields_are_turbine_spec_fields() -> None:
    """``from_farm_dict`` 忽略的欄位都要是 TurbineSpec 的欄位（新增 PLC 設定值欄位時要一起加進集合）。"""
    from simulator.physics.turbine_physics import Z72_PLC_SETPOINT_FIELDS

    assert Z72_PLC_SETPOINT_FIELDS <= set(TurbineSpec.__dataclass_fields__)
    for name in ("yaw_pressure_alarm", "pt100_filter_tau_s", "vane_discrepancy_delay_s", "cut_out_gust_window_s"):
        assert name in Z72_PLC_SETPOINT_FIELDS


def test_code_states_are_fixed_after_reset() -> None:
    """每個碼的狀態在 reset 時建好：保護停機不新增鍵（API 執行緒的 operator_reset 迭代時不會遇到字典變大）。"""
    plc = PlcProtection(SPEC)
    keys = set(plc._codes)
    plc.note_protection_stop("ride_through:lvrt_band2", 1.0)
    plc.note_protection_stop("overspeed_hardware", 2.0)
    assert set(plc._codes) == keys


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


def test_cut_out_is_noted_once_per_stop_cycle() -> None:
    """同一停機週期只記一次 I201；機組再次起動後的第二次暴風停機（即使 600 s 內）要再記。"""
    d = Driver()
    d.plc.note_protection_stop("cut_out", 100.0)
    d.plc.note_protection_stop("cut_out", 101.0)
    d.plc.on_restart(300.0)
    d.plc.note_protection_stop("cut_out", 400.0)
    assert [(e.code, e.sim_time) for e in d.plc.drain_events() if e.code == 201] == [(201, 100.0), (201, 400.0)]


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
