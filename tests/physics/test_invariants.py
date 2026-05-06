"""Layer 1 — Conservation Laws / Physical Bounds（WMOM-20260505-23）。

驗證物理模型不違反基本守恆律與物理上限。每個 test class 對應一條守恆：

    1. TestBetzLimit            ──  Cp ≤ 0.593 across (V, λ, β) grid
    2. TestEnergyConservation   ──  P_aero formula + 損耗方向性（P_elec ≤ P_aero）
    3. TestMomentumBalance      ──  thrust 公式 T = ½ρACtV² 一致性
    4. TestAngularMomentum      ──  rotor_speed × gear_ratio ≈ gen_speed（direct + geared）
    5. TestThermalBalance       ──  ThermalElement 穩態 ΔT = Q × R_th
    6. TestMassConservation     ──  冷卻液 level decay 與 leak rate 對得上

容差設計原則：
- 物理模型有隨機項（turbulence、stall、AR(1)）— 用統計量 + 容差，不硬 ==
- 容差來源：物理近似階數 + 實作離散化誤差，盡量寫進 docstring
"""

from __future__ import annotations

import math

import numpy as np
import pytest

# simulator.physics 由 conftest.py 注入 sys.path
from simulator.physics.cooling_model import CoolingSpec, WaterCoolingLoop
from simulator.physics.drivetrain_model import DrivetrainModel, DrivetrainSpec
from simulator.physics.power_curve import CpSurfaceModel, PowerCurveModel
from simulator.physics.thermal_model import ThermalElement
from simulator.physics.turbine_physics import TurbinePhysicsModel, TurbineSpec


# ════════════════════════════════════════════════════════════════════════
# 1. Betz Limit  ──  C_p ≤ 0.593 across all (V, λ, β)
# ════════════════════════════════════════════════════════════════════════
#
# 理論：Lanchester-Betz limit (1919/1926) — 任何 axial-flow rotor 從風中提取
# 動能的最大效率為 16/27 ≈ 0.593。模型若違反，要嘛是 cp_max 設錯，要嘛是
# Cp 公式有 bug。
#
# 注：本模型故意把 cp_max 設為 0.48 ~ 0.50（現代 3-blade HAWT 真實值），
# 比 Betz 還保守。本 test 同時驗 hard ceiling (0.593) 與 soft ceiling (cp_max)。

BETZ_LIMIT = 16.0 / 27.0  # ≈ 0.5926


class TestBetzLimit:
    """Cp 不可超過 Betz 限 16/27 ≈ 0.593。"""

    def test_betz_limit_across_lambda_beta_grid(self):
        """跨 (λ, β) grid 所有條件下 Cp ≤ 16/27。"""
        m = CpSurfaceModel(cp_max=0.48)
        # 涵蓋 Region 2 → Region 3 + 不合理大 β（emergency feather）
        lambdas = np.linspace(0.5, 15.0, 30)
        betas = np.linspace(-2.0, 90.0, 25)

        max_cp = 0.0
        for lam in lambdas:
            for beta in betas:
                cp = m.get_cp(lam, beta)
                assert cp <= BETZ_LIMIT + 1e-9, (
                    f"Betz violation: Cp={cp:.4f} at λ={lam:.2f}, β={beta:.2f}"
                )
                max_cp = max(max_cp, cp)

        # 此模型 cp_max=0.48，所以 max_cp 應該落在 [0.45, 0.50]
        assert 0.40 <= max_cp <= 0.50, (
            f"Cp_peak={max_cp:.4f} 偏離設計值（cp_max=0.48）"
        )

    @pytest.mark.parametrize("cp_max_setting", [0.40, 0.45, 0.48, 0.50, 0.55])
    def test_cp_max_ceiling_respected(self, cp_max_setting: float):
        """無論 cp_max 設多少，Cp 都不可超過該設定值（且不可超過 Betz）。"""
        # 給予一個寬容差（離散搜尋未必命中精確 peak）
        # 模型內部以 raw_peak scaling 推回 cp_max，理論上能精準碰到 ceiling
        m = CpSurfaceModel(cp_max=cp_max_setting)
        lambdas = np.linspace(1.0, 12.0, 25)
        betas = np.linspace(0.0, 30.0, 15)
        cps = [m.get_cp(lam, beta) for lam in lambdas for beta in betas]
        cp_peak = max(cps)
        assert cp_peak <= cp_max_setting + 1e-9, (
            f"cp_max ceiling 失效：peak={cp_peak:.4f} > {cp_max_setting:.4f}"
        )
        assert cp_peak <= BETZ_LIMIT + 1e-9

    def test_full_simulator_cp_under_betz(self):
        """跑全 TurbinePhysicsModel 在多個風速下也不違反 Betz。"""
        m = TurbinePhysicsModel(seed=42)
        wind_speeds = [4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 18.0, 22.0]
        max_cp = 0.0
        for v in wind_speeds:
            for _ in range(60):
                m.step(wind_speed=v, wind_direction=180.0, ambient_temp=15.0, dt=1.0)
            cp = m.power_curve.last_aero.cp
            assert cp <= BETZ_LIMIT, (
                f"全模擬違反 Betz：V={v} m/s 時 Cp={cp:.4f}"
            )
            max_cp = max(max_cp, cp)
        # 至少在 partial-load region 應該真的接近設計 cp_max
        assert max_cp > 0.30, (
            f"全模擬下 max Cp={max_cp:.4f} 太低，模型可能根本沒在 region 2 工作"
        )


# ════════════════════════════════════════════════════════════════════════
# 2. Energy Conservation  ──  P_aero formula + P_elec ≤ P_aero
# ════════════════════════════════════════════════════════════════════════
#
# (a) P_aero = Cp × ½ × ρ × A × V³  ── 公式一致性（驗實作沒寫錯）
# (b) P_elec ≤ P_aero  ── 任何耗損鏈（drivetrain × generator × converter）
#     都只會減少能量，不會增加。違反此方向性 = 模型有 bug。
#
# 不直接測 η_drv × η_conv 的精確比例，因為 controller / dead-band / dynamic stall
# 會讓瞬時 ratio 飄動；只驗能量單向流動是穩定不變量。

class TestEnergyConservation:
    """能量守恆 — aero power 公式一致 + 損耗方向性。"""

    @pytest.mark.parametrize("wind_speed,rotor_rpm,pitch", [
        (8.0, 12.0, 0.0),
        (10.0, 15.0, 0.0),
        (11.0, 16.0, 1.0),
    ])
    def test_aero_power_matches_formula(self, wind_speed, rotor_rpm, pitch):
        """P_aero ≈ Cp × ½ × ρ × A × V³（容差 ±2%，含 stall_factor 衰減）。"""
        rho = 1.225
        diameter = 70.65
        m = PowerCurveModel(
            rated_power_kw=2000.0, rotor_diameter=diameter,
            rated_speed=12.0, cp_max=0.48, air_density=rho,
        )
        # 預跑一步避免 dynamic stall transient 的初始衝擊
        m.get_power_cp(wind_speed, rotor_rpm, pitch, dt=1.0)
        out = m.get_power_cp(wind_speed, rotor_rpm, pitch, dt=1.0)

        area = math.pi * (diameter / 2.0) ** 2
        # 公式還原：P = Cp × 0.5 × ρ × A × V³（kW），不含 region blending
        expected_kw = out.cp * 0.5 * rho * area * wind_speed ** 3 / 1000.0

        # PowerCurveModel 在 region 2 會 max(p_aero_kw, p_lookup×0.85) 作為 floor
        # 所以實際輸出 ≥ formula。我們只驗 formula 不會被違反到 < 0.95 倍
        assert out.power_kw >= expected_kw * 0.95 - 0.5, (
            f"P_aero={out.power_kw:.1f} 低於公式預期 {expected_kw:.1f} kW"
        )

    def test_electrical_output_never_exceeds_aero(self):
        """全模擬：P_elec（converter 出口）絕不超過 P_aero（aero disk）。"""
        m = TurbinePhysicsModel(seed=7)
        # 跑長一點讓 controller 完全穩定
        for _ in range(180):
            m.step(wind_speed=10.0, wind_direction=180.0, ambient_temp=15.0, dt=1.0)

        violations = []
        for _ in range(60):
            tags = m.step(
                wind_speed=10.0, wind_direction=180.0, ambient_temp=15.0, dt=1.0
            )
            p_aero = m.power_curve.last_aero.power_kw
            p_grid = tags.get("WTUR_TotPwrAt", 0.0)  # converter / grid 出口
            # 容差 +2%：可能因 synthetic inertia / freq response 短暫 boost；
            # 真正 bug（如 efficiency > 1）會穩定超出此容差
            if p_grid > p_aero * 1.02 + 5.0:
                violations.append((p_aero, p_grid))

        assert not violations, (
            f"P_elec > P_aero × 1.02 出現 {len(violations)} 次："
            f"first violation P_aero={violations[0][0]:.1f}, "
            f"P_grid={violations[0][1]:.1f}"
        )

    def test_no_power_below_cut_in(self):
        """V < cut_in → power 為 0（守恆無能量輸入應無能量輸出）。"""
        m = PowerCurveModel(rated_power_kw=2000.0, cut_in=3.0, rated_speed=12.0)
        for v in [0.0, 1.0, 2.0, 2.9]:
            assert m.get_power(v) == 0.0, f"V={v} 仍有 power 輸出"

    def test_no_power_above_cut_out(self):
        """V > cut_out → power 為 0（保護動作，不再從風中取能）。"""
        m = PowerCurveModel(rated_power_kw=2000.0, cut_in=3.0, rated_speed=12.0,
                            cut_out=25.0)
        for v in [25.5, 27.0, 30.0]:
            assert m.get_power(v) == 0.0


# ════════════════════════════════════════════════════════════════════════
# 3. Momentum Balance  ──  Thrust 公式 T = ½ × ρ × A × Ct × V²
# ════════════════════════════════════════════════════════════════════════
#
# Actuator-disk theory 下，rotor 對流體施的軸向力（thrust）
#     T = ½ × ρ × A × Ct(λ, β) × V²    [N]
# 這是動量守恆的直接結果（force = d/dt 動量通量）。實作若把任何因子寫錯，
# 此 test 會 catch。

class TestMomentumBalance:
    """動量守恆 — thrust 公式 T = ½ρACtV²。"""

    @pytest.mark.parametrize("wind_speed,ct,diameter,rho", [
        (8.0,  0.7,  70.65, 1.225),
        (12.0, 0.8,  70.65, 1.225),
        (15.0, 0.65, 80.0,  1.20),
        (10.0, 0.5,  126.0, 1.225),  # 大型機
    ])
    def test_aero_thrust_formula(self, wind_speed, ct, diameter, rho):
        """get_aero_thrust_kn 必須完全符合 ½ρACtV² 公式。"""
        m = CpSurfaceModel(cp_max=0.48)
        actual_kn = m.get_aero_thrust_kn(wind_speed, ct, diameter, rho)

        area = math.pi * (diameter / 2.0) ** 2
        expected_n = 0.5 * rho * area * ct * wind_speed ** 2
        expected_kn = expected_n / 1000.0

        # tight 容差：純公式還原，理論上應 bit-perfect
        assert abs(actual_kn - expected_kn) < 1e-6, (
            f"Thrust 公式偏離：actual={actual_kn:.4f} kN, expected={expected_kn:.4f} kN"
        )

    def test_thrust_scales_with_v_squared(self):
        """V 翻倍 → thrust 4 倍（V² 比例的 invariant）。"""
        m = CpSurfaceModel(cp_max=0.48)
        diameter = 70.65
        ct = 0.7
        t1 = m.get_aero_thrust_kn(5.0, ct, diameter)
        t2 = m.get_aero_thrust_kn(10.0, ct, diameter)
        assert abs(t2 / t1 - 4.0) < 1e-4, f"thrust 比例 {t2 / t1:.4f} ≠ 4.0"

    def test_thrust_scales_with_density(self):
        """ρ 翻倍 → thrust 2 倍（線性 invariant）。"""
        m = CpSurfaceModel(cp_max=0.48)
        t1 = m.get_aero_thrust_kn(10.0, 0.7, 70.65, air_density=1.0)
        t2 = m.get_aero_thrust_kn(10.0, 0.7, 70.65, air_density=2.0)
        assert abs(t2 / t1 - 2.0) < 1e-4

    def test_thrust_zero_when_ct_zero(self):
        """Ct=0 → thrust=0（park / 完全 feather 狀態）。"""
        m = CpSurfaceModel(cp_max=0.48)
        assert m.get_aero_thrust_kn(15.0, 0.0, 70.65) == 0.0


# ════════════════════════════════════════════════════════════════════════
# 4. Angular Momentum  ──  rotor_speed × gear_ratio ≈ gen_speed
# ════════════════════════════════════════════════════════════════════════
#
# 任何 rigid drivetrain：generator_speed = rotor_speed × overall_gear_ratio
# 加上 LSS/HSS 扭轉 + slip 容差 ±5%。
#
# Z72 預設是 direct-drive (ratio=1.0)，所以 rotor 與 gen 速度應幾乎完全相等；
# 為了驗證 ratio relation，我們也另起一個 geared spec (ratio=104.5) 直接測
# DrivetrainModel。

class TestAngularMomentum:
    """角動量 — rotor × gear_ratio ≈ gen_speed。"""

    def test_direct_drive_rotor_equals_generator(self):
        """Direct-drive (ratio=1) → rotor_speed ≈ gen_speed。"""
        m = TurbinePhysicsModel(seed=11)
        for _ in range(180):
            m.step(wind_speed=10.0, wind_direction=180.0, ambient_temp=15.0, dt=1.0)
        # 取最後 30 秒平均，避免瞬間 transient
        rotor_samples = []
        gen_samples = []
        for _ in range(30):
            m.step(wind_speed=10.0, wind_direction=180.0, ambient_temp=15.0, dt=1.0)
            rotor_samples.append(m.rotor_speed)
            gen_samples.append(m.drivetrain.generator_speed)

        rotor_avg = sum(rotor_samples) / len(rotor_samples)
        gen_avg = sum(gen_samples) / len(gen_samples)

        assert m.spec.gear_ratio == pytest.approx(1.0)
        # direct-drive：兩者誤差 < 5%
        rel_err = abs(rotor_avg - gen_avg) / max(rotor_avg, 0.1)
        assert rel_err < 0.05, (
            f"direct-drive rotor/gen mismatch: "
            f"rotor={rotor_avg:.3f}, gen={gen_avg:.3f}, rel_err={rel_err:.4f}"
        )

    def test_geared_drivetrain_ratio_relation(self):
        """Geared (ratio≈104.5) → gen_speed ≈ rotor × 104.5（slip ±5%）。"""
        spec = DrivetrainSpec.for_geared(overall_ratio=104.5)
        dt_model = DrivetrainModel(spec=spec)
        gear_ratio = spec.total_gear_ratio
        assert 90.0 < gear_ratio < 120.0, "spec 設計應在 104.5 附近"

        # 給定固定 rotor 速度（producing 模式），模擬到 gen_speed 收斂
        target_rotor = 12.0  # rpm
        aero_torque = 800.0  # kNm（rated 附近）
        for _ in range(2000):  # 足夠收斂
            dt_model.step(
                aero_rotor_speed=target_rotor,
                current_rotor_speed=target_rotor,
                aero_torque_knm=aero_torque,
                aero_load_factor=0.8,
                dt=0.1,
                is_producing=True,
                is_starting=False,
                is_normal_stop=False,
                is_emergency_stop=False,
                ambient_temp=20.0,
            )

        gen_speed = dt_model.generator_speed
        expected = target_rotor * gear_ratio
        rel_err = abs(gen_speed - expected) / expected
        # ±5% 涵蓋 LSS/HSS 扭轉 + slip
        assert rel_err < 0.05, (
            f"geared ratio violation: gen={gen_speed:.2f}, "
            f"expected={expected:.2f} (ratio={gear_ratio:.2f}), rel_err={rel_err:.4f}"
        )

    def test_idle_no_rotation_means_no_generator(self):
        """rotor 停 → gen_speed 也應收斂到 0。"""
        spec = DrivetrainSpec.for_geared(overall_ratio=100.0)
        dt_model = DrivetrainModel(spec=spec)
        # 先讓 gen_speed 達到正常工作值
        for _ in range(1500):
            dt_model.step(
                aero_rotor_speed=12.0, current_rotor_speed=12.0,
                aero_torque_knm=600.0, aero_load_factor=0.7,
                dt=0.1, is_producing=True, is_starting=False,
                is_normal_stop=False, is_emergency_stop=False,
            )
        assert dt_model.generator_speed > 50.0  # 確認真的有轉

        # 然後緊急停機
        for _ in range(800):
            dt_model.step(
                aero_rotor_speed=0.0, current_rotor_speed=0.0,
                aero_torque_knm=0.0, aero_load_factor=0.0,
                dt=0.1, is_producing=False, is_starting=False,
                is_normal_stop=False, is_emergency_stop=True,
            )

        assert dt_model.generator_speed < 0.5, (
            f"emergency stop 後 gen_speed={dt_model.generator_speed:.3f} 沒歸零"
        )


# ════════════════════════════════════════════════════════════════════════
# 5. Thermal Balance  ──  穩態 ΔT = Q × R_th
# ════════════════════════════════════════════════════════════════════════
#
# 一階 thermal node：C × dT/dt = Q − (T − T_amb) / R_th
# 穩態 (dT/dt = 0)：T_steady − T_amb = Q × R_th
#
# 此守恆是熱力第一定律在 lumped-mass model 下的縮影。R_th 設計值不對 = 此 test fail。

class TestThermalBalance:
    """熱平衡 — 穩態 ΔT = Q × R_th。"""

    @pytest.mark.parametrize("R_th,tau,Q,T_amb", [
        (0.65, 600.0, 100.0, 20.0),  # 類似 gen_stator 在 rated
        (0.35, 900.0, 33.0, 25.0),   # 類似 gen_bearing
        (0.22, 300.0, 50.0, 15.0),   # 類似 cnv_water
    ])
    def test_steady_state_temperature(self, R_th, tau, Q, T_amb):
        """跑足夠長的時間（>> 5τ）後，T 應收斂到 T_amb + Q × R_th。"""
        node = ThermalElement(thermal_resistance=R_th, time_constant=tau, initial_temp=T_amb)
        dt = tau / 30.0  # 30 步/τ
        steps = int(8 * tau / dt)  # 跑 8τ，達 99.97% 穩態
        for _ in range(steps):
            node.step(heat_input_kw=Q, ambient_temp=T_amb, dt=dt)

        expected = T_amb + Q * R_th
        actual = node.temperature
        # 8τ 後仍會差 e^-8 ≈ 0.034%，加上離散化誤差，給 ±0.1°C 容差
        assert abs(actual - expected) < 0.1, (
            f"穩態 ΔT 偏離公式：actual={actual:.3f}, "
            f"expected={expected:.3f} (Q={Q}, R={R_th}, T_amb={T_amb})"
        )

    def test_first_order_lag_at_one_tau(self):
        """1 τ 之後溫度應到達 (1 − 1/e) ≈ 63.2% 終值。"""
        R_th = 0.5
        tau = 600.0
        Q = 100.0
        T_amb = 20.0
        node = ThermalElement(R_th, tau, T_amb)
        dt = tau / 100.0
        # 跑剛好 1τ
        for _ in range(100):
            node.step(heat_input_kw=Q, ambient_temp=T_amb, dt=dt)

        T_final_expected = T_amb + Q * R_th
        rise_fraction = (node.temperature - T_amb) / (T_final_expected - T_amb)
        # 理論值 1 - e^-1 = 0.6321；給 ±2% 容差（離散化誤差 + 步距 100 不算密）
        assert 0.60 < rise_fraction < 0.66, (
            f"1τ 後升溫比例 {rise_fraction:.4f} 偏離 (1-1/e)≈0.632"
        )

    def test_no_heat_no_temperature_rise(self):
        """Q=0 → 溫度應穩定停留在 T_amb（純熱平衡 baseline）。"""
        node = ThermalElement(thermal_resistance=0.5, time_constant=300.0,
                              initial_temp=20.0)
        for _ in range(200):
            node.step(heat_input_kw=0.0, ambient_temp=20.0, dt=5.0)
        assert abs(node.temperature - 20.0) < 0.01

    def test_higher_resistance_higher_steady_temp(self):
        """同樣 Q 下，R_th 大者穩態 T 高（單調性 invariant）。"""
        Q = 50.0
        T_amb = 20.0
        temps = []
        for R in [0.1, 0.3, 0.5, 0.8]:
            node = ThermalElement(R, 300.0, T_amb)
            for _ in range(2000):
                node.step(Q, T_amb, dt=1.0)
            temps.append(node.temperature)
        # 嚴格單調遞增
        for i in range(len(temps) - 1):
            assert temps[i] < temps[i + 1], (
                f"單調性失效：R 增大但 T 沒升 ({temps})"
            )


# ════════════════════════════════════════════════════════════════════════
# 6. Mass Conservation  ──  冷卻液 level decay = leak_rate × t / volume
# ════════════════════════════════════════════════════════════════════════
#
# WaterCoolingLoop 用 _coolant_level_pct (0-100) 表示液位百分比。
# Leak rate 為 L/hr，總體積 V_0 (L)。經過 t 秒後流失：
#     ΔLevel% = (rate × t / 3600) / V_0 × 100
# 質量守恆 = 流失量必須與漏率成正比，且不依賴模型其他狀態。

class TestMassConservation:
    """質量守恆 — 冷卻液 level decay 與 leak rate 對得上。"""

    def test_no_leak_no_level_change(self):
        """leak_rate=0 → level 永遠 100%（不可憑空消失）。"""
        loop = WaterCoolingLoop(CoolingSpec())
        # 預設 level = 100%
        assert abs(loop.coolant_level_pct - 100.0) < 0.01
        for _ in range(3600):
            loop.step(heat_load_kw=50.0, ambient_temp=20.0, wind_speed=8.0,
                      dt=1.0, turbine_running=True)
        assert abs(loop.coolant_level_pct - 100.0) < 0.01

    @pytest.mark.parametrize("leak_lph,duration_s", [
        (1.0,  3600.0),   # 1 L/hr × 1hr = 1 L → 1.25% drop（80L total）
        (5.0,  1800.0),   # 5 L/hr × 0.5hr = 2.5 L → 3.125%
        (10.0, 720.0),    # 10 L/hr × 0.2hr = 2 L → 2.5%
    ])
    def test_leak_drains_at_expected_rate(self, leak_lph, duration_s):
        """level decay = leak_lph × duration / volume × 100，容差 ±0.1 個百分點。"""
        spec = CoolingSpec(coolant_volume_liters=80.0)
        loop = WaterCoolingLoop(spec)
        loop.set_leak_rate(leak_lph)

        dt = 1.0
        steps = int(duration_s / dt)
        for _ in range(steps):
            loop.step(heat_load_kw=50.0, ambient_temp=20.0, wind_speed=8.0,
                      dt=dt, turbine_running=True)

        lost_liters = leak_lph * (duration_s / 3600.0)
        expected_drop_pct = lost_liters / spec.coolant_volume_liters * 100.0
        actual_drop = 100.0 - loop.coolant_level_pct

        assert abs(actual_drop - expected_drop_pct) < 0.1, (
            f"level decay 偏離公式：actual_drop={actual_drop:.4f}%, "
            f"expected={expected_drop_pct:.4f}% "
            f"(leak={leak_lph} L/hr × {duration_s}s / 80L)"
        )

    def test_level_never_below_zero(self):
        """嚴重漏液跑久了 level clip 在 0%（不可變負）。"""
        spec = CoolingSpec(coolant_volume_liters=80.0)
        loop = WaterCoolingLoop(spec)
        loop.set_leak_rate(200.0)  # 大漏率
        # 200 L/hr × 1hr = 200L > 80L → 早就漏光
        for _ in range(3600):
            loop.step(heat_load_kw=50.0, ambient_temp=20.0, wind_speed=8.0,
                      dt=1.0, turbine_running=True)
        assert loop.coolant_level_pct == 0.0
        assert loop.coolant_level_pct >= 0.0  # 沒有變負

    def test_refill_restores_level(self):
        """refill 後立刻回 100%（補充質量守恆完整性檢查）。"""
        loop = WaterCoolingLoop(CoolingSpec())
        loop.set_leak_rate(20.0)
        for _ in range(7200):
            loop.step(heat_load_kw=30.0, ambient_temp=20.0, wind_speed=5.0,
                      dt=1.0, turbine_running=True)
        assert loop.coolant_level_pct < 100.0
        loop.refill()
        assert abs(loop.coolant_level_pct - 100.0) < 0.01


# ════════════════════════════════════════════════════════════════════════
# Negative-test sentinel
# ════════════════════════════════════════════════════════════════════════
#
# 確認此 framework 真的有抓 bug 的能力 —
# 給 CpSurfaceModel 一個違反 Betz 的 cp_max，要保證 get_cp 會超過 16/27，
# 進而能讓 Layer 1 真實 fail（避免「test 永遠 pass」的假陽性）。

class TestNegativeSentinel:
    """負向測試 — 故意違反守恆，驗證 framework 能抓到。"""

    def test_betz_violation_is_detected(self):
        """如果 cp_max 設超過 Betz，model 真的會吐 Cp > 0.593。

        這是 framework 的『自我檢查』：若這個負向 test 被 pass（也就是
        model 怎樣都不會違反 Betz），代表 Betz test 抓不到 bug。
        """
        bad = CpSurfaceModel(cp_max=0.70)  # 違反 Betz
        # 找出 peak Cp
        peak = 0.0
        for lam in np.linspace(1.0, 12.0, 40):
            for beta in np.linspace(0.0, 5.0, 20):
                peak = max(peak, bad.get_cp(lam, beta))
        # peak 必須能達 > Betz 才證明 framework 真的會 catch
        # （正常 Layer 1 此情況會 fail，此 test 反向確認）
        assert peak > BETZ_LIMIT, (
            f"Negative-test sentinel 失效：cp_max=0.70 但 model 還是限在 "
            f"{peak:.4f} ≤ Betz；表示 Betz test 在此情況下抓不到 bug"
        )
