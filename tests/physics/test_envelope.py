"""Layer 3 — Operating Envelope（WMOM-20260505-23）。

驗證控制邏輯與保護動作 — 風機在不同工況下必須遵守設計邊界：

    1. TestCutInBehavior         ──  V < cut_in：power ≈ 0、rotor 漸停
    2. TestCutOutBehavior        ──  V > cut_out：30 s 內進 stop、power 歸零
    3. TestEmergencyStopDecay    ──  emergency 後 rotor 5 s 內降 ≥ 50%
    4. TestPitchActuatorLimit    ──  正常運轉 pitch rate ≤ 10 °/s
    5. TestYawRateLimit          ──  yaw rate ≤ 0.5 °/s（Z72 OEM）
    6. TestRotorOverspeedMargin  ──  rotor never > rated × 1.2 + software 保護觸發
    7. TestGeneratorSlip         ──  direct-drive slip < 5%

容差來自 Z72 OEM manual（cut_in=3, cut_out=25, overspeed=26.5/28.5 RPM）。
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from simulator.physics.drivetrain_model import DrivetrainModel, DrivetrainSpec
from simulator.physics.turbine_physics import TurbinePhysicsModel, TurbineSpec
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
# 2. Cut-out Behavior  ──  V > cut_out：30 s 內進 stop state
# ════════════════════════════════════════════════════════════════════════

class TestCutOutBehavior:
    """V > cut_out：自動跳閘保護動作。"""

    def test_cut_out_triggers_emergency_stop(self):
        """從 production 狀態升風到 27 m/s（>cut_out=25）→ 30 s 內 rotor 歸零。"""
        m = _spin_up_to_production(seed=1, V=10.0, settle_steps=200)
        rotor_initial = m.rotor_speed
        assert rotor_initial > 5.0  # 確認 spin-up 成功

        # 大風 30 s
        for _ in range(30):
            m.step(wind_speed=27.0, wind_direction=180.0,
                   ambient_temp=15.0, dt=1.0)

        # 必須在 stop / restart 狀態
        assert m.tur_state in (STATE_EMERGENCY_STOP, STATE_NORMAL_STOP,
                                STATE_RESTART_WAIT, STATE_SHUTDOWN), (
            f"30 s 後 state={m.tur_state}，未進入 stop family"
        )
        assert m.rotor_speed < 1.0, (
            f"30 s 後 rotor 仍={m.rotor_speed:.2f} RPM"
        )

    def test_power_zero_above_cut_out(self):
        """穩定後在 30 m/s（極端強風）下 30 s 平均 |P| < 1% rated。"""
        m = _spin_up_to_production(seed=1, V=10.0, settle_steps=200)
        powers = []
        for _ in range(60):
            tags = m.step(wind_speed=30.0, wind_direction=180.0,
                          ambient_temp=15.0, dt=1.0)
            powers.append(tags["WTUR_TotPwrAt"])
        avg_power = float(np.mean(powers[-30:]))
        assert abs(avg_power) < 0.01 * m.spec.rated_power_kw, (
            f"V=30 m/s 30s 平均 P̄={avg_power:.2f} kW > 1% rated"
        )


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
