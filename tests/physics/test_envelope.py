"""Layer 3 — Operating Envelope（WMOM-20260505-23）。

驗證控制邏輯與保護動作 — 風機在不同工況下必須遵守設計邊界：

    1. TestCutInBehavior         ──  V < cut_in：power ≈ 0、rotor 漸停
    2. TestCutOutBehavior        ──  10 分鐘平均 > 25 或 3 秒平均 > 35 m/s → 正常停機、power 歸零；
                                    平均 < 20 m/s 才重啟；瞬間陣風不停機（手冊事件 201，WMOM-20261021-10）
    3. TestEmergencyStopDecay    ──  emergency 後 rotor 5 s 內降 ≥ 50%
    4. TestPitchActuatorLimit    ──  正常運轉 pitch rate ≤ 10 °/s
    5. TestYawRateLimit          ──  yaw rate ≤ 0.5 °/s（Z72 OEM）
    6. TestRotorOverspeedMargin  ──  rotor never > rated × 1.2 + software 保護觸發
    7. TestGeneratorSlip         ──  direct-drive slip < 5%

容差來自 Z72 OEM manual（cut_in=3, cut_out=25 / 10 min avg、35 / 3 s avg（手冊 Appendix D SDVwind_hi_3s；Appendix C 寫 5 s，DEC-20261023-01）、cut-back-in 20, overspeed=26.5/28.5 RPM）。
"""

from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np
import pytest

from simulator.physics.drivetrain_model import DrivetrainModel, DrivetrainSpec
from simulator.physics.power_curve import PowerCurveModel
from simulator.physics.turbine_physics import TurbinePhysicsModel, TurbineSpec, _RollingMean
from simulator.physics.yaw_model import YawModel


# Z72 state machine constants（避免 magic number 散落）
STATE_SHUTDOWN = 1
STATE_STANDBY = 2
STATE_RESTART_WAIT = 3
STATE_PRE_PRODUCTION = 4
STATE_START_PRODUCTION = 5
STATE_PRODUCTION = 6
STATE_EMERGENCY_STOP = 7
STATE_HOT_START = 8
STATE_NORMAL_STOP = 9


def _spin_up_to_production(seed: int = 1, V: float = 10.0, settle_steps: int = 200):
    """Helper：將 turbine 帶到穩定 production 狀態。"""
    m = TurbinePhysicsModel(seed=seed)
    for _ in range(settle_steps):
        m.step(wind_speed=V, wind_direction=180.0, ambient_temp=15.0, dt=1.0)
    assert m.tur_state == STATE_PRODUCTION, (
        f"Helper spin-up 失敗：state={m.tur_state} 非 production"
    )
    return m


# ════════════════════════════════════════════════════════════════════════
# 1. Cut-in Behavior  ──  V < cut_in：power ≈ 0、rotor 不啟動
# ════════════════════════════════════════════════════════════════════════

class TestCutInBehavior:
    """V < cut_in：no power, no rotation。"""

    @pytest.mark.parametrize("V", [0.0, 1.0, 2.0, 2.5])
    def test_no_power_below_cut_in(self, V):
        """V ∈ [0, cut_in)：30 s 平均 |P| < 1% rated（量測噪訊容差）、rotor ≈ 0。"""
        m = TurbinePhysicsModel(seed=1)
        powers = []
        for _ in range(60):
            tags = m.step(wind_speed=V, wind_direction=180.0,
                          ambient_temp=15.0, dt=1.0)
            powers.append(tags["WTUR_TotPwrAt"])
        # 取後 30 s 平均，|P̄| 應遠 < 1% rated（噪訊容差，不含 sensor 雜訊 ±10 kW）
        avg_power = float(np.mean(powers[-30:]))
        rated = m.spec.rated_power_kw  # 2000
        assert abs(avg_power) < 0.01 * rated, (
            f"V={V} m/s 30s 平均 P̄={avg_power:.2f} kW > 1% rated"
        )
        assert m.rotor_speed < 0.5, (
            f"V={V} m/s rotor_speed={m.rotor_speed:.3f} (應接近 0)"
        )
        assert m.tur_state != STATE_PRODUCTION

    def test_just_above_cut_in_starts_eventually(self):
        """V 略高於 cut_in（4 m/s）→ 最終進入 production state（spin-up <300 s）。"""
        m = TurbinePhysicsModel(seed=1)
        for _ in range(300):
            m.step(wind_speed=4.0, wind_direction=180.0, ambient_temp=15.0, dt=1.0)
        # 應已啟動或正在啟動
        assert m.tur_state in (STATE_PRODUCTION, STATE_START_PRODUCTION,
                                STATE_PRE_PRODUCTION), (
            f"V=4.0 m/s 跑 300 s 仍在 state={m.tur_state}"
        )


# ════════════════════════════════════════════════════════════════════════
# 2. Cut-out Behavior  ──  手冊事件 201：平均風速判定、正常停機、20 m/s 回切
# ════════════════════════════════════════════════════════════════════════

STOP_FAMILY = (STATE_NORMAL_STOP, STATE_SHUTDOWN)


def _run(m: TurbinePhysicsModel, V: float, seconds: int) -> List[Tuple[int, float]]:
    """以固定風速推進，回傳每秒的 (state, power)。"""
    out = []
    for _ in range(seconds):
        tags = m.step(wind_speed=V, wind_direction=180.0, ambient_temp=15.0, dt=1.0)
        out.append((m.tur_state, tags["WTUR_TotPwrAt"]))
    return out


class TestCutOutBehavior:
    """切出風速依手冊事件 201 / Appendix D：V wind 10 min avg > 25 或 3 s avg > 35 m/s；回切 10 min avg < 20 m/s。"""

    def test_sustained_wind_above_cut_out_stops_on_10min_average(self):
        """從 10 m/s 升到 27 m/s：10 分鐘平均跨過 25 前持續發電，跨過後正常停機（不是緊急停機）。"""
        m = _spin_up_to_production(seed=1, V=10.0, settle_steps=200)
        early = _run(m, 27.0, 400)                     # 平均 = (10·200 + 27·400) / 600 ≈ 21.3
        assert {st for st, _ in early} == {STATE_PRODUCTION}
        assert min(p for _, p in early[-60:]) > 0.5 * m.spec.rated_power_kw
        later = _run(m, 27.0, 200)
        states = [st for st, _ in later]
        assert STATE_NORMAL_STOP in states and STATE_EMERGENCY_STOP not in states
        assert m.get_control_status()["shutdown_cause"] == "cut_out"
        assert m.tur_state in STOP_FAMILY
        assert m.rotor_speed < 1.0

    def test_power_zero_after_storm_stop(self):
        """暴風停機後（30 m/s 持續）30 s 平均 |P| < 1% rated。"""
        m = _spin_up_to_production(seed=1, V=10.0, settle_steps=200)
        run = _run(m, 30.0, 660)
        avg_power = float(np.mean([p for _, p in run[-30:]]))
        assert abs(avg_power) < 0.01 * m.spec.rated_power_kw, (
            f"V=30 m/s 停機後 30s 平均 P̄={avg_power:.2f} kW > 1% rated"
        )

    def test_3s_average_above_gust_limit_stops_quickly(self):
        """3 秒平均 > 35 m/s：不必等 10 分鐘平均，數秒內要求停機。"""
        m = _spin_up_to_production(seed=1, V=10.0, settle_steps=200)
        run = _run(m, 37.0, 10)
        assert STATE_NORMAL_STOP in [st for st, _ in run]

    @pytest.mark.parametrize("rebuilt", [False, True], ids=["init", "update_spec"])
    def test_brief_gusts_above_cut_out_do_not_stop_or_zero_power(self, rebuilt):
        """平均風速 < 25 時，幾秒 28 m/s 的陣風不停機、功率也不因瞬間風速 > 25 歸零。
        update_spec（每次載入風場都走）重建的氣動模型同樣不在 25 m/s 設閘門。"""
        m = _spin_up_to_production(seed=1, V=10.0, settle_steps=200)
        if rebuilt:
            m.update_spec(TurbineSpec())
        _run(m, 20.0, 300)
        samples = []
        for cycle in range(20):
            samples += _run(m, 28.0 if cycle % 2 == 0 else 20.0, 3)
        assert {st for st, _ in samples} == {STATE_PRODUCTION}
        gust_powers = [p for i, (_, p) in enumerate(samples) if (i // 3) % 2 == 0]
        assert min(gust_powers) > 0.5 * m.spec.rated_power_kw

    def test_brief_gusts_above_cut_out_do_not_block_start_up(self):
        """開機後平均風速 < 25：幾秒 28 m/s 的陣風不讓啟動程序中斷（不再看瞬間風速上限），也不會因
        10 分鐘平均尚未累積滿、第一個陣風樣本就被當成平均值而進暴風停機。"""
        m = TurbinePhysicsModel(seed=1)
        states = []
        for cycle in range(100):
            states += [st for st, _ in _run(m, 28.0 if cycle % 2 == 0 else 20.0, 3)]
        assert STATE_PRODUCTION in states

    def test_brief_gust_shorter_than_3s_does_not_trip_gust_rule(self):
        """2 秒 40 m/s 的陣風：3 秒平均 (2·40 + 10) / 3 = 30 < 35，不停機。"""
        m = _spin_up_to_production(seed=1, V=10.0, settle_steps=200)
        run = _run(m, 40.0, 2) + _run(m, 10.0, 10)
        assert {st for st, _ in run} == {STATE_PRODUCTION}

    def test_3s_gust_trips_the_appendix_d_gust_rule(self):
        """3 秒 40 m/s 的陣風：3 秒平均 40 > 35 → 停機（Appendix C 的 5 秒平均是 28，不會停）。"""
        assert TurbineSpec().cut_out_gust_window_s == 3.0
        m = _spin_up_to_production(seed=1, V=10.0, settle_steps=200)
        run = _run(m, 40.0, 3) + _run(m, 10.0, 10)
        assert STATE_NORMAL_STOP in {st for st, _ in run}

    def test_single_gust_sample_at_cold_start_does_not_stop(self):
        """開機第一個樣本就是 40 m/s：3 秒窗未滿不判定，之後 10 m/s 正常啟動發電。"""
        m = TurbinePhysicsModel(seed=1)
        states = [st for st, _ in _run(m, 40.0, 1) + _run(m, 10.0, 300)]
        assert STATE_PRODUCTION in states

    def test_gust_stop_before_10min_window_full_holds_until_valid_average(self):
        """開機後 10 分鐘內被 3 秒平均停機：10 分鐘平均未滿窗前不解除，滿窗且 < 20 m/s 後才重啟。"""
        m = _spin_up_to_production(seed=1, V=10.0, settle_steps=100)
        _run(m, 40.0, 6)
        before_full = _run(m, 10.0, 480)               # 累計 586 s：10 分鐘窗尚未滿
        assert STATE_PRODUCTION not in [st for st, _ in before_full]
        after_full = _run(m, 10.0, 300)
        assert STATE_PRODUCTION in [st for st, _ in after_full]

    def test_storm_does_not_overwrite_operator_stop_cause(self):
        """操作員停機與暴風旗標同一步成立：停機原因維持 operator、不記 I201。"""
        m = _spin_up_to_production(seed=1, V=10.0, settle_steps=200)
        _run(m, 40.0, 4)                               # 5 秒平均 (10 + 4·40) / 5 = 34：旗標尚未成立
        m.plc.drain_events()
        m.cmd_stop()
        _run(m, 40.0, 10)                              # 第一步：5 秒平均 40 → 旗標成立，與操作員停機同步
        assert m.get_control_status()["shutdown_cause"] == "operator"
        assert [e.code for e in m.plc.drain_events() if e.code == 201] == []

    @pytest.mark.parametrize("action", ["update_spec", "reset"])
    def test_storm_stop_survives_update_spec_and_reset(self, action):
        """暴風停機中改設定（update_spec）或 reset（例：維護清除故障）不得清掉暴風旗標而在暴風中重啟。"""
        m = _spin_up_to_production(seed=1, V=10.0, settle_steps=200)
        _run(m, 28.0, 700)
        assert m.tur_state in STOP_FAMILY
        if action == "update_spec":
            m.update_spec(TurbineSpec())
        else:
            m.reset()
        states = [st for st, _ in _run(m, 28.0, 60)]
        assert not set(states) & {STATE_STANDBY, STATE_PRE_PRODUCTION, STATE_START_PRODUCTION,
                                  STATE_PRODUCTION}

    def test_restart_only_after_10min_average_below_cut_back_in(self):
        """暴風停機後：平均風速仍 > 20 m/s 不重啟；降到 15 m/s、平均 < 20 後才重啟發電。"""
        m = _spin_up_to_production(seed=1, V=10.0, settle_steps=200)
        _run(m, 28.0, 700)
        assert m.tur_state in STOP_FAMILY
        held = _run(m, 22.0, 900)                      # 平均最終 ≈ 22 > 20：持續停機
        assert STATE_PRODUCTION not in [st for st, _ in held]
        resumed = _run(m, 15.0, 900)                   # 平均約 7 分鐘後 < 20 → 重啟
        assert STATE_PRODUCTION in [st for st, _ in resumed]


@pytest.mark.parametrize("dt", [1.0, 5.0, 0.5, 3.3, 700.0])
def test_rolling_mean_covers_exactly_the_last_window(dt):
    """_RollingMean 等於最近 window 秒的時間加權平均（暴力計算對照），任何 dt 皆然。"""
    rng = np.random.default_rng(3)
    window = 600.0
    rolling = _RollingMean(window)
    history: List[Tuple[float, float, float]] = []    # (start, end, value)
    t = 0.0
    for _ in range(400):
        value = float(rng.uniform(0.0, 40.0))
        history.append((t, t + dt, value))
        t += dt
        got = rolling.add(value, dt)
        lo = max(0.0, t - window)
        weights = [(max(0.0, min(end, t) - max(start, lo)), v) for start, end, v in history]
        expected = sum(w * v for w, v in weights) / sum(w for w, _ in weights)
        assert got == pytest.approx(expected, rel=1e-9, abs=1e-9)
    assert rolling.is_full is (t >= window)


def test_default_power_curve_table_does_not_drop_to_zero_above_cut_out():
    """預設功率曲線表（起動同步爬升、Cp 模型無輸出時的 fallback）在 > 25 m/s 不歸零：
    切出是控制器依平均風速的決定，不是查表（WMOM-20261021-10 code review）。"""
    curve = PowerCurveModel(rated_power_kw=2000.0, cut_out=math.inf)
    assert [curve.get_power(v) for v in (25.0, 25.5, 30.0, 34.9)] == [2000.0] * 4


# ════════════════════════════════════════════════════════════════════════
# 3. Emergency Stop Decay  ──  rotor 5 s 內降 ≥ 50%
# ════════════════════════════════════════════════════════════════════════

class TestEmergencyStopDecay:
    """Emergency stop 動作後 rotor 速度快速衰減。"""

    def test_rotor_drops_50pct_within_5s(self):
        """trigger emergency stop → 5 s 內 rotor ≤ 50% 原值。"""
        m = _spin_up_to_production(seed=1, V=10.0, settle_steps=200)
        rotor_t0 = m.rotor_speed
        threshold = rotor_t0 * 0.50

        m._request_stop("emergency", "test")  # noqa: SLF001 — 測試用

        for s in range(1, 6):  # 1..5 秒
            m.step(wind_speed=10.0, wind_direction=180.0,
                   ambient_temp=15.0, dt=1.0)
            if m.rotor_speed <= threshold:
                # 提前達標
                assert s <= 5
                return

        pytest.fail(
            f"5 s 後 rotor 仍 {m.rotor_speed:.3f} RPM > 50% × {rotor_t0:.3f}"
        )

    def test_emergency_state_set_immediately(self):
        """request emergency → 下一次 step 後 state == 7。"""
        m = _spin_up_to_production(seed=1, V=10.0, settle_steps=200)
        m._request_stop("emergency", "test")  # noqa: SLF001
        m.step(wind_speed=10.0, wind_direction=180.0, ambient_temp=15.0, dt=1.0)
        assert m.tur_state == STATE_EMERGENCY_STOP


# ════════════════════════════════════════════════════════════════════════
# 4. Pitch Actuator Rate Limit  ──  ≤ 10 °/s 正常運轉
# ════════════════════════════════════════════════════════════════════════
#
# Z72 OEM：normal servo ~8°/s；emergency battery-driven ≥ 5°/s（min spec）。
# Layer 3 envelope 主要驗證「正常 production 不會超過 actuator limit」。
# Emergency state (st=7) 不在此 envelope（電池驅動可較快），另以單獨 test 容許。

class TestPitchActuatorLimit:
    """Production / start 狀態下 pitch rate ≤ 10 °/s（actuator 物理上限）。"""

    def test_production_pitch_rate_within_limit(self):
        """穩定 production：blade pitch step-to-step 變化 ≤ 10°/s。"""
        m = _spin_up_to_production(seed=1, V=10.0, settle_steps=200)
        prev_pitch = list(m._pitch_bl)  # noqa: SLF001
        max_rate = 0.0

        # 跑 60 s 觀察
        for _ in range(60):
            m.step(wind_speed=10.0, wind_direction=180.0,
                   ambient_temp=15.0, dt=1.0)
            if m.tur_state == STATE_PRODUCTION:
                for i in range(3):
                    rate = abs(m._pitch_bl[i] - prev_pitch[i])  # noqa: SLF001
                    max_rate = max(max_rate, rate)
            prev_pitch = list(m._pitch_bl)  # noqa: SLF001

        assert max_rate <= 10.0, (
            f"Production pitch rate {max_rate:.2f} °/s 超過 10 °/s actuator 上限"
        )

    def test_region3_pitch_rate_under_gust(self):
        """Region 3 突發陣風 → pitch 反應 ≤ 10 °/s。"""
        m = _spin_up_to_production(seed=2, V=12.0, settle_steps=200)
        prev_pitch = list(m._pitch_bl)  # noqa: SLF001
        max_rate = 0.0

        # 風速從 12 跳到 17（持續強風 region 3）
        for s in range(40):
            V = 17.0 if s >= 5 else 12.0
            m.step(wind_speed=V, wind_direction=180.0,
                   ambient_temp=15.0, dt=1.0)
            if m.tur_state == STATE_PRODUCTION:
                for i in range(3):
                    rate = abs(m._pitch_bl[i] - prev_pitch[i])  # noqa: SLF001
                    max_rate = max(max_rate, rate)
            prev_pitch = list(m._pitch_bl)  # noqa: SLF001

        assert max_rate <= 10.0, (
            f"Region 3 gust pitch rate {max_rate:.2f} °/s 超過 10 °/s 上限"
        )


# ════════════════════════════════════════════════════════════════════════
# 5. Yaw Rate Limit  ──  ≤ 0.5 °/s
# ════════════════════════════════════════════════════════════════════════
#
# Z72 OEM nominal yaw speed 0.5 °/s，伴隨 rate_gain（最高 1.8）→ 上限 ~0.9 °/s。
# Layer 3 envelope 驗 nominal 路徑（非 unwind / 非極大誤差）。

class TestYawRateLimit:
    """Yaw 馬達轉動速率不超過設計上限。"""

    def test_yaw_rate_default_constant(self):
        """YawModel.yaw_rate default 必為 Z72 OEM 0.5 °/s。"""
        y = YawModel()
        assert y.yaw_rate == pytest.approx(0.5, abs=0.01)

    def test_steady_yaw_rate_within_spec(self):
        """大誤差驅動 yaw → step 變化 ≤ rate_gain × yaw_rate × dt。"""
        y = YawModel()
        y.yaw_angle = 270.0
        y.cable_windup = 0.0
        # 模擬 10°後 wind 維持 285° → yaw error 15° (剛好觸發 dead_band)
        # 設 wind_direction 偏離 dead_band 才會啟動
        target = 290.0  # 20° 偏移，超過 dead_band=15
        # 跑 activation_delay = 60 s 才會啟動 yawing
        for _ in range(70):
            y.step(wind_direction=target, is_producing=True, dt=1.0)
        # 開始 yawing 後 30 s
        max_step = 0.0
        prev = y.yaw_angle
        for _ in range(30):
            out = y.step(wind_direction=target, is_producing=True, dt=1.0)
            if out["is_yawing"] > 0:
                step = abs((y.yaw_angle - prev + 540) % 360 - 180)
                max_step = max(max_step, step)
            prev = y.yaw_angle
        # rate_gain 上限 1.8 → 最快 0.9 °/s × dt=1 = 0.9 ° per step
        assert max_step <= 0.95, (
            f"yaw step 最大 {max_step:.3f}° 超過 spec 上限 ~0.9°"
        )

    def test_no_yaw_when_in_deadband(self):
        """yaw error 在 dead_band 內 → 不啟動 yaw（即使誤差有，本能容忍）。"""
        y = YawModel()
        y.yaw_angle = 270.0
        # error = 5° < dead_band = 15°
        for _ in range(120):
            out = y.step(wind_direction=275.0, is_producing=True, dt=1.0)
        assert out["is_yawing"] == 0.0
        # yaw 角應紋風不動
        assert abs(y.yaw_angle - 270.0) < 0.1


# ════════════════════════════════════════════════════════════════════════
# 6. Rotor Overspeed Margin  ──  ≤ rated × 1.2、software 保護觸發
# ════════════════════════════════════════════════════════════════════════

class TestRotorOverspeedMargin:
    """rotor 永遠 ≤ overspeed_software_rpm；超過則應觸發 emergency stop。"""

    def test_normal_operation_within_margin(self):
        """V ≤ rated 全程 rotor < software limit。"""
        m = TurbinePhysicsModel(seed=3)
        max_rpm = 0.0
        # 跑 600 s 含風變
        for s in range(600):
            V = 10.0 + 2.0 * math.sin(s * 0.05)  # 8-12 m/s 變動
            m.step(wind_speed=V, wind_direction=180.0,
                   ambient_temp=15.0, dt=1.0)
            max_rpm = max(max_rpm, m.rotor_speed)

        assert max_rpm < m.spec.overspeed_software_rpm, (
            f"max rotor={max_rpm:.2f} 超過 software 上限 "
            f"{m.spec.overspeed_software_rpm}"
        )
        # 也應遠低於 rated × 1.2
        margin = max_rpm / m.spec.max_rotor_rpm
        assert margin < 1.20, (
            f"max rotor {max_rpm:.2f} / rated {m.spec.max_rotor_rpm} "
            f"= {margin:.4f} > 1.2"
        )

    def test_overspeed_triggers_emergency(self):
        """rotor 被故意推超過 software 限 → 下一 step 進 emergency state 7。"""
        m = _spin_up_to_production(seed=4, V=11.0, settle_steps=200)
        # 直接強制 rotor 超過 software limit
        m.rotor_speed = m.spec.overspeed_software_rpm + 0.5
        m.step(wind_speed=11.0, wind_direction=180.0, ambient_temp=15.0, dt=1.0)
        # 經過一個 step 應已觸發 emergency
        assert m.tur_state == STATE_EMERGENCY_STOP, (
            f"rotor 強制超 limit 後 state={m.tur_state}，未進 emergency"
        )


# ════════════════════════════════════════════════════════════════════════
# 7. Generator Slip  ──  Z72 direct-drive < 5%
# ════════════════════════════════════════════════════════════════════════

class TestGeneratorSlip:
    """direct-drive Z72：rotor ≈ generator（除了 LSS twist 外應 < 5% slip）。"""

    def test_steady_state_slip_under_5pct(self):
        """穩定 production 取最後 30 s 平均，slip < 5%。"""
        m = _spin_up_to_production(seed=5, V=10.0, settle_steps=200)
        rotor_samples = []
        gen_samples = []
        for _ in range(60):
            m.step(wind_speed=10.0, wind_direction=180.0,
                   ambient_temp=15.0, dt=1.0)
            rotor_samples.append(m.rotor_speed)
            gen_samples.append(m.drivetrain.generator_speed)

        rotor_avg = float(np.mean(rotor_samples))
        gen_avg = float(np.mean(gen_samples))
        slip = abs(rotor_avg - gen_avg) / max(rotor_avg, 0.1)
        assert slip < 0.05, (
            f"slip={slip:.4f}（rotor={rotor_avg:.3f}, gen={gen_avg:.3f}）"
        )

    def test_geared_drivetrain_slip_under_5pct(self):
        """同樣對 geared spec：穩態 slip(gen / (rotor·ratio)) < 5%。"""
        spec = DrivetrainSpec.for_geared(overall_ratio=104.5)
        dt_model = DrivetrainModel(spec=spec)
        target_rotor = 12.0
        for _ in range(2000):
            dt_model.step(
                aero_rotor_speed=target_rotor, current_rotor_speed=target_rotor,
                aero_torque_knm=600.0, aero_load_factor=0.7,
                dt=0.1, is_producing=True, is_starting=False,
                is_normal_stop=False, is_emergency_stop=False,
            )
        expected = target_rotor * spec.total_gear_ratio
        slip = abs(dt_model.generator_speed - expected) / expected
        assert slip < 0.05, (
            f"geared slip={slip:.4f} (gen={dt_model.generator_speed:.2f}, "
            f"expected={expected:.2f})"
        )
