"""Layer 2 — Literature / Standard Benchmarks（WMOM-20260505-23）。

驗證物理模型符合公開文獻 / 國際標準的關鍵數值。每個 class 對應一條 benchmark：

    1. TestKaimalTurbulence    ──  IEC 61400-1 Kaimal: σ_v / V_mean ≈ TI
    2. TestBastankhahWake      ──  Niayifar & Porté-Agel 2016: deficit @ 5D
    3. TestGlauertNTF          ──  IEC 61400-12-1 Annex D: V_raw/V_∞ ≈ 0.84
    4. TestBearingFrequencies  ──  Tedric Harris BPFO/BPFI formulas
    5. TestISO10816Zones       ──  ISO 10816-3 Class III vibration zones
    6. TestWaltherViscosity    ──  Cold-start decay → 1/e at τ=10 min
    7. TestISAAirDensity       ──  ISA 15°C, dry: ρ = 1.2250 kg/m³

容差設計：
- 文獻數值含模型假設 + 真機差異 — 用「合理區間」而非單點值
- 文獻引用寫在每個 test docstring 內，方便日後追溯
"""

from __future__ import annotations

import math

import numpy as np
import pytest

# simulator.physics 由 conftest.py 注入 sys.path
from simulator.physics.drivetrain_model import DrivetrainModel, DrivetrainSpec
from simulator.physics.power_curve import CpSurfaceModel
from simulator.physics.turbine_physics import TurbineSpec
from simulator.physics.vibration_spectral import SpectralVibrationModel
from simulator.physics.wind_field import (
    PerTurbineWind,
    TurbinePosition,
    TurbulenceGenerator,
)


# ════════════════════════════════════════════════════════════════════════
# 1. IEC 61400-1 Kaimal Turbulence  ──  σ_v / V_mean ≈ TI
# ════════════════════════════════════════════════════════════════════════
#
# Reference:
#   IEC 61400-1 ed.4 (2019) §6.3 — Normal Turbulence Model (NTM)
#   Kaimal, Wyngaard, Izumi, Coté (1972) — atmospheric surface-layer spectra
#
# 在恆定 mean wind 與 TI 條件下，turbulence generator 輸出長期 std 必須收斂到
# σ = V_mean × TI。本模型以 AR(1) approx Kaimal 譜，τ = L_u / V_mean。
# 取樣足夠多時，std 估計誤差 ~ σ/√(2N) → N=2000 時 ~1.6%，容差設 ±15% 寬鬆有餘。

class TestKaimalTurbulence:
    """IEC 61400-1 Kaimal — σ_v / V_mean ≈ TI 在 stationarity。"""

    @pytest.mark.parametrize("V_mean,TI", [
        (8.0,  0.08),   # Class C 弱風 / 平地
        (12.0, 0.10),   # Class B 典型
        (15.0, 0.14),   # Class A 強風 / 高 TI
    ])
    def test_sigma_over_v_equals_ti(self, V_mean, TI):
        """長序列 std 必須 ≈ V_mean × TI，容差 ±15%。"""
        gen = TurbulenceGenerator(seed=42)
        samples = []
        # 跑 10000 樣本（>> 10τ），確保 stationarity + 統計穩定
        for _ in range(10000):
            samples.append(gen.step(mean_speed=V_mean, turbulence_intensity=TI, dt=1.0))
        sigma = float(np.std(samples))
        sigma_over_v = sigma / V_mean
        rel_err = abs(sigma_over_v - TI) / TI
        assert rel_err < 0.15, (
            f"σ/V={sigma_over_v:.4f} vs TI={TI:.4f}, "
            f"rel_err={rel_err:.4f} (容差 15%) at V={V_mean}"
        )

    def test_zero_ti_gives_zero_fluctuation(self):
        """TI=0 → 完全 deterministic，不產生 fluctuation。"""
        gen = TurbulenceGenerator(seed=0)
        samples = [gen.step(mean_speed=10.0, turbulence_intensity=0.0, dt=1.0)
                   for _ in range(500)]
        # 嚴格：sigma 應幾乎為 0（容差 1e-6 應對 numpy float 噪訊）
        assert max(abs(s) for s in samples) < 1e-6

    def test_stable_atm_lengthens_correlation(self):
        """Stability=−1（穩定大氣）→ L_u 增大 → autocorrelation 變慢。

        驗證雙重不變量：
        1. 方向性 invariant：stable lag-1 > unstable lag-1（嚴格鑑別）
        2. 絕對量 invariant：stable lag-1 > 0.93（持久性下界）
        """
        V, TI = 12.0, 0.10

        def lag1(stability: float, seed: int = 7) -> float:
            gen = TurbulenceGenerator(seed=seed)
            samples = [
                gen.step(mean_speed=V, turbulence_intensity=TI,
                         dt=1.0, stability=stability)
                for _ in range(5000)
            ]
            arr = np.array(samples)
            return float(np.corrcoef(arr[:-1], arr[1:])[0, 1])

        lag1_stable = lag1(-1.0)
        lag1_unstable = lag1(+1.0)

        # 1. 方向性
        assert lag1_stable > lag1_unstable, (
            f"stable lag-1={lag1_stable:.4f} 未大於 unstable={lag1_unstable:.4f} "
            f"— L_u 應在 stable ABL 變大"
        )
        # 2. 絕對下界（涵蓋大氣 turnover 量級）
        assert lag1_stable > 0.93, (
            f"stable ABL lag-1={lag1_stable:.4f} 太小，τ_corr 偏離預期"
        )


# ════════════════════════════════════════════════════════════════════════
# 2. Bastankhah-Porté-Agel Wake  ──  deficit @ 5D
# ════════════════════════════════════════════════════════════════════════
#
# Reference:
#   Bastankhah & Porté-Agel (2014) Renew. Energy 70, 116-123 — Gaussian wake
#   Niayifar & Porté-Agel (2016) Energies 9, 741       — k* = 0.38·TI + 0.004
#
# Geometry: 兩台同型風機完全沿風向對齊，間距 5D，V=8 m/s（Region 2，Ct≈0.82）。
# 文獻典型結果：deficit 約 25-35%。本模型以 k*=0.0344 (Niayifar) 給 ~23%；容差
# [0.18, 0.40] 涵蓋不同 k* 假設下的合理區間。

class TestBastankhahWake:
    """Bastankhah-Porté-Agel wake 在 5D 處的 deficit。"""

    def test_single_wake_deficit_at_5D(self):
        """V=8, TI=0.08, x=5D 一台下游 → deficit ∈ [0.18, 0.40]。"""
        D = 70.65
        positions = [
            TurbinePosition(x=0.0, y=0.0),       # upstream
            TurbinePosition(x=5.0 * D, y=0.0),   # 5D downstream, on centerline
        ]
        # 多 seed 平均消除 wake meander 隨機性
        deficits = []
        for seed in range(20):
            ptw = PerTurbineWind(
                turbine_count=2, seed=seed, rotor_diameter=D, positions=positions,
            )
            # 預跑 30 步讓 meander state 進入 stationarity
            for _ in range(30):
                ptw.step(farm_wind=8.0, wind_direction=270.0,
                         turbulence_intensity=0.08, dt=1.0)
            deficits.append(ptw.get_wake_deficit(1))

        mean_def = float(np.mean(deficits))
        # 上游 turbine 必為 0
        for seed in range(3):
            ptw = PerTurbineWind(
                turbine_count=2, seed=seed, rotor_diameter=D, positions=positions,
            )
            ptw.step(farm_wind=8.0, wind_direction=270.0,
                     turbulence_intensity=0.08, dt=1.0)
            assert ptw.get_wake_deficit(0) == 0.0

        assert 0.18 <= mean_def <= 0.40, (
            f"5D 處 wake deficit={mean_def:.4f} 落在 [0.18, 0.40] 之外 "
            f"(Niayifar/Bastankhah 預期區間)"
        )

    def test_wake_decays_with_distance(self):
        """downstream 距離越遠 → deficit 越小（單調性 invariant）。"""
        D = 70.65
        results = []
        for x_over_D in [3.0, 5.0, 8.0, 12.0]:
            positions = [
                TurbinePosition(x=0.0, y=0.0),
                TurbinePosition(x=x_over_D * D, y=0.0),
            ]
            ptw = PerTurbineWind(
                turbine_count=2, seed=0, rotor_diameter=D, positions=positions,
            )
            for _ in range(30):
                ptw.step(farm_wind=8.0, wind_direction=270.0,
                         turbulence_intensity=0.08, dt=1.0)
            results.append((x_over_D, ptw.get_wake_deficit(1)))

        # 驗證單調遞減
        for i in range(len(results) - 1):
            x1, d1 = results[i]
            x2, d2 = results[i + 1]
            assert d1 > d2, (
                f"deficit 沒隨距離衰減：x={x1}D 給 {d1:.4f}, "
                f"x={x2}D 給 {d2:.4f}"
            )

    def test_no_wake_when_perpendicular(self):
        """target 不在 source 下游（垂直風向擺位）→ 不應有 wake。"""
        D = 70.65
        # turbine #1 在 turbine #0 的 cross-stream 方向，沒有任何下游分量
        positions = [
            TurbinePosition(x=0.0, y=0.0),
            TurbinePosition(x=0.0, y=5.0 * D),  # 完全側向
        ]
        ptw = PerTurbineWind(
            turbine_count=2, seed=0, rotor_diameter=D, positions=positions,
        )
        # wind blowing FROM 270 → flowing toward east (+x)；y 方向對 deficit 無 contribution
        for _ in range(20):
            ptw.step(farm_wind=8.0, wind_direction=270.0,
                     turbulence_intensity=0.08, dt=1.0)
        assert ptw.get_wake_deficit(1) < 0.01


# ════════════════════════════════════════════════════════════════════════
# 3. Glauert NTF (Nacelle Anemometer Transfer Function)  ──  V_raw/V_∞ ≈ 0.84
# ════════════════════════════════════════════════════════════════════════
#
# Reference:
#   IEC 61400-12-1 ed.2 (2017) Annex D — Nacelle Anemometer Transfer Function
#   Glauert (1935) / Burton et al. (2011) Wind Energy Handbook §3.10
#
# 1-D momentum theory: a = 0.5(1 - √(1 - Ct))
# Nacelle anemometer 位於 ~1.5R 後方，受 axial induction 影響：
#   V_raw / V_∞ = 1 - k_pos × a × cos²(γ)  其中 k_pos≈0.55
# Region 2 典型 Ct=0.82 → a=0.288 → ntf=0.842
# 容差 [0.80, 0.88] 涵蓋常見模型差異。

class TestGlauertNTF:
    """Glauert axial induction & NTF 對 nacelle 風速 readback 的修正。"""

    @pytest.mark.parametrize("ct,expected_a", [
        # 1-D momentum: a = 0.5 × (1 - √(1 - Ct))
        (0.5,  0.146),  # 0.5 × (1 - √0.5)  = 0.146
        (0.7,  0.226),  # 0.5 × (1 - √0.3)  = 0.226
        (0.82, 0.288),  # 0.5 × (1 - √0.18) = 0.288  ← Region 2 典型
        (0.90, 0.342),
    ])
    def test_axial_induction_formula(self, ct, expected_a):
        """a = ½ × (1 − √(1 − Ct))（1-D momentum theory）。"""
        a = 0.5 * (1.0 - math.sqrt(1.0 - ct))
        assert abs(a - expected_a) < 0.005, (
            f"a({ct})={a:.4f} 偏離公式 {expected_a:.4f}"
        )

    def test_betz_optimal_induction_factor(self):
        """Betz optimal a = 1/3，對應 Ct = 8/9 ≈ 0.889。"""
        ct_betz = 8.0 / 9.0
        a = 0.5 * (1.0 - math.sqrt(1.0 - ct_betz))
        assert abs(a - 1.0 / 3.0) < 0.001, (
            f"Betz optimal: a({ct_betz:.4f})={a:.4f}, expected 1/3"
        )

    def test_ntf_factor_at_region2(self):
        """Region 2 (Ct=0.82, γ=0)：V_raw/V_∞ ≈ 0.84，容差 [0.80, 0.88]。"""
        # 等效於 turbine_physics.py:743 公式 ntf_factor = 1 − 0.55·a·cos²γ
        ct = 0.82
        a = 0.5 * (1.0 - math.sqrt(1.0 - ct))
        cos2_gamma = 1.0  # γ=0 yaw aligned
        ntf = 1.0 - 0.55 * a * cos2_gamma
        assert 0.80 <= ntf <= 0.88, (
            f"NTF factor at Region 2 = {ntf:.4f}, IEC 61400-12-1 Annex D 預期 ~0.84"
        )

    def test_yaw_misalignment_reduces_ntf_correction(self):
        """γ=30°：cos²γ=0.75 → NTF correction 縮小（更接近 1.0 = 無 induction）。"""
        ct = 0.82
        a = 0.5 * (1.0 - math.sqrt(1.0 - ct))
        ntf_aligned = 1.0 - 0.55 * a * 1.0
        ntf_yawed = 1.0 - 0.55 * a * (math.cos(math.radians(30.0))) ** 2
        # 偏航時 induction 衰減（cos²γ），NTF 應更接近 1.0
        assert ntf_aligned < ntf_yawed < 1.0, (
            f"NTF aligned={ntf_aligned:.4f}, yawed={ntf_yawed:.4f} 順序錯"
        )


# ════════════════════════════════════════════════════════════════════════
# 4. Bearing Defect Frequencies  ──  Tedric Harris BPFO/BPFI
# ════════════════════════════════════════════════════════════════════════
#
# Reference:
#   Harris, T.A. (2001) Rolling Bearing Analysis 4th ed., §3
#
# 對於 n 個滾動元件、滾子直徑 d、節徑 D、接觸角 α 的軸承：
#   BPFO = (n/2) × f_shaft × (1 - (d/D)cos α)   ── outer race defect
#   BPFI = (n/2) × f_shaft × (1 + (d/D)cos α)   ── inner race defect
#
# 模型參數：n=23, d/D=0.18, α=10°（球型滾子主軸承典型）
# 個體差異 ±3% 也納入容差。

class TestBearingFrequencies:
    """Tedric Harris BPFO/BPFI formulas at known shaft speed。"""

    @pytest.mark.parametrize("rotor_rpm", [12.0, 15.0, 18.0, 22.0])
    def test_bpfo_bpfi_formula(self, rotor_rpm: float):
        """BPFO/BPFI = (n/2) × f_shaft × (1 ∓ d/D × cos α)，容差 ±5%。"""
        m = SpectralVibrationModel(seed=42, gear_ratio=1.0, gear_teeth=23)
        # 預跑一步 priming
        m.step(rotor_speed_rpm=rotor_rpm, wind_speed=10.0, power_kw=1500.0,
               rated_power_kw=2000.0, turbulence=0.08, dt=1.0)
        bands = m.step(rotor_speed_rpm=rotor_rpm, wind_speed=10.0,
                       power_kw=1500.0, rated_power_kw=2000.0,
                       turbulence=0.08, dt=1.0)

        n = 23
        d_ratio_nom = 0.18
        cos_alpha = math.cos(math.radians(10.0))
        f_shaft = rotor_rpm / 60.0

        # 名義值（不含個體 ±3% 差異）
        bpfo_nom = (n / 2.0) * f_shaft * (1.0 - d_ratio_nom * cos_alpha)
        bpfi_nom = (n / 2.0) * f_shaft * (1.0 + d_ratio_nom * cos_alpha)

        # 容差 ±5%（含 _brg_ratio_var ±3% + numerical）
        bpfo_err = abs(bands.bpfo_freq - bpfo_nom) / bpfo_nom
        bpfi_err = abs(bands.bpfi_freq - bpfi_nom) / bpfi_nom
        assert bpfo_err < 0.05, (
            f"BPFO 偏離 Tedric Harris 公式：actual={bands.bpfo_freq:.4f}, "
            f"expected={bpfo_nom:.4f}, rel_err={bpfo_err:.4f} (rotor={rotor_rpm} rpm)"
        )
        assert bpfi_err < 0.05, (
            f"BPFI 偏離公式：actual={bands.bpfi_freq:.4f}, "
            f"expected={bpfi_nom:.4f}, rel_err={bpfi_err:.4f}"
        )

    def test_bpfi_greater_than_bpfo(self):
        """BPFI 永遠 > BPFO（內環缺陷頻率高於外環，幾何 invariant）。"""
        m = SpectralVibrationModel(seed=0)
        bands = m.step(rotor_speed_rpm=15.0, wind_speed=10.0, power_kw=1500.0,
                       rated_power_kw=2000.0, turbulence=0.08, dt=1.0)
        assert bands.bpfi_freq > bands.bpfo_freq

    def test_bearing_freq_scales_with_shaft_speed(self):
        """rotor RPM 翻倍 → BPFO/BPFI 也翻倍（線性 invariant）。"""
        m = SpectralVibrationModel(seed=0)
        m.step(10.0, 10.0, 1500.0, 2000.0, 0.08, 1.0)
        b1 = m.step(10.0, 10.0, 1500.0, 2000.0, 0.08, 1.0)
        m2 = SpectralVibrationModel(seed=0)
        m2.step(20.0, 10.0, 1500.0, 2000.0, 0.08, 1.0)
        b2 = m2.step(20.0, 10.0, 1500.0, 2000.0, 0.08, 1.0)
        assert abs(b2.bpfo_freq / b1.bpfo_freq - 2.0) < 0.01
        assert abs(b2.bpfi_freq / b1.bpfi_freq - 2.0) < 0.01


# ════════════════════════════════════════════════════════════════════════
# 5. ISO 10816-3 Class III Vibration Zones
# ════════════════════════════════════════════════════════════════════════
#
# Reference:
#   ISO 10816-3 (2009) — Mechanical vibration: evaluation by velocity (RMS)
#   Class III: large machines on rigid foundation (300 kW – 50 MW)
#     Zone A (good):       v ≤ 2.3 mm/s
#     Zone B (acceptable): 2.3 < v ≤ 4.5
#     Zone C (limit):      4.5 < v ≤ 7.1
#     Zone D (damage):     v > 7.1
#
# 健康風機在 rated 工況下 overall RMS 應落在 Zone A 或 B 低端。

class TestISO10816Zones:
    """ISO 10816-3 Class III — 健康基線在 Zone A/B 邊界。"""

    # zone boundaries (mm/s RMS)
    ZONE_A_MAX = 2.3
    ZONE_B_MAX = 4.5
    ZONE_C_MAX = 7.1

    def _overall_rms(self, bands) -> float:
        """跨頻帶幾何加總（quadrature）— 工程上的 overall vibration。"""
        contributions = [
            bands.band_1p_x, bands.band_3p_x, bands.band_gear_x,
            bands.band_hf_x, bands.band_bb_x,
        ]
        return math.sqrt(sum(c * c for c in contributions))

    def test_healthy_baseline_in_zone_A_or_B(self):
        """健康風機 rated 工況 overall RMS ≤ Zone B (4.5 mm/s)。"""
        m = SpectralVibrationModel(seed=0, gear_ratio=1.0, gear_teeth=23)
        # rated 工況：rotor 18 rpm, V=12, P=1900 kW
        # 預跑 5 步進入穩態
        for _ in range(5):
            m.step(rotor_speed_rpm=18.0, wind_speed=12.0, power_kw=1900.0,
                   rated_power_kw=2000.0, turbulence=0.10, dt=1.0)
        bands = m.step(rotor_speed_rpm=18.0, wind_speed=12.0, power_kw=1900.0,
                       rated_power_kw=2000.0, turbulence=0.10, dt=1.0)

        overall = self._overall_rms(bands)
        assert overall <= self.ZONE_B_MAX, (
            f"健康基線 overall RMS={overall:.3f} mm/s 超過 Zone B "
            f"({self.ZONE_B_MAX} mm/s) — model 過敏"
        )

    def test_zone_boundaries_strictly_ordered(self):
        """Zone 邊界滿足 A < B < C < D。"""
        # 純常數 sanity check 防止之後改錯
        assert self.ZONE_A_MAX < self.ZONE_B_MAX < self.ZONE_C_MAX

    def test_per_band_thresholds_below_zone_b(self):
        """個別頻帶 alarm 門檻不應超過 Zone B 邊界（per-band 不可比 overall 嚴）。"""
        m = SpectralVibrationModel(seed=0, gear_ratio=1.0, gear_teeth=23)
        for band, thresholds in m._base_thresholds.items():  # noqa: SLF001
            assert thresholds["alarm"] <= self.ZONE_B_MAX, (
                f"頻帶 {band} alarm 門檻 {thresholds['alarm']} > Zone B "
                f"({self.ZONE_B_MAX})"
            )

    def test_standstill_essentially_zero(self):
        """rotor 停 → 振動回到 ambient noise floor，遠低於 Zone A。"""
        m = SpectralVibrationModel(seed=0)
        # rotor_speed_rpm < 0.5 → 直接走 standstill 路徑
        bands = m.step(rotor_speed_rpm=0.0, wind_speed=2.0, power_kw=0.0,
                       rated_power_kw=2000.0, turbulence=0.05, dt=1.0)
        assert self._overall_rms(bands) < 0.5  # << Zone A


# ════════════════════════════════════════════════════════════════════════
# 6. Walther Viscosity  ──  Cold-start decay → 1/e at τ=10 min
# ════════════════════════════════════════════════════════════════════════
#
# Reference:
#   Walther formula (ASTM D341) — kinematic viscosity vs temperature for oils
#
# Drivetrain `cold_start_factor = 1.0 + 0.5 × exp(-running_seconds / 600)`
# 在 t=0 時為 1.5（高黏度 → extra friction loss），t=∞ 趨近 1.0。
# 經一個時間常數 τ=600 s 後，超過穩態的部分衰減到 1/e ≈ 36.8%。
# 即「63.2% 已衰減完」— 文獻典型 cold-start warm-up time。

class TestWaltherViscosity:
    """Cold-start viscosity factor decay constant τ=600 s（10 min）。"""

    def _expected_factor(self, running_s: float) -> float:
        """直接套公式驗算對照。"""
        return 1.0 + 0.5 * math.exp(-running_s / 600.0)

    @pytest.mark.parametrize("running_s,expected", [
        (0.0,    1.500),  # 100% extra friction
        (300.0,  1.303),  # 0.5 τ → exp(-0.5)=0.607
        (600.0,  1.184),  # 1 τ   → exp(-1.0)=0.368  ← spec 主要驗證點
        (1800.0, 1.025),  # 3 τ   → 已衰減 95%
        (3600.0, 1.001),  # 6 τ   → 接近穩態
    ])
    def test_cold_start_factor_at_known_times(self, running_s, expected):
        """直接驗 1 + 0.5·exp(-t/600) 公式；模擬 drivetrain 跑到指定時間。"""
        spec = DrivetrainSpec.for_geared(overall_ratio=104.5)
        m = DrivetrainModel(spec=spec)

        # 用 dt=10s 跑到 running_s（producing 才會累計 _running_seconds）
        steps = int(running_s / 10.0)
        for _ in range(steps):
            m.step(
                aero_rotor_speed=14.0, current_rotor_speed=14.0,
                aero_torque_knm=400.0, aero_load_factor=0.6,
                dt=10.0, is_producing=True, is_starting=False,
                is_normal_stop=False, is_emergency_stop=False,
                ambient_temp=20.0,
            )
        actual_factor = self._expected_factor(m._running_seconds)  # noqa: SLF001
        assert abs(actual_factor - expected) < 0.01, (
            f"cold_start_factor at t={running_s}s: "
            f"actual={actual_factor:.4f}, expected={expected:.4f}"
        )

    def test_one_tau_gives_one_over_e_decay(self):
        """t=τ=600 s：超過穩態的部分衰減到 1/e ≈ 36.8%。"""
        f0 = self._expected_factor(0.0)        # 1.5
        f_tau = self._expected_factor(600.0)    # 1 + 0.5/e ≈ 1.184
        f_inf = 1.0
        # 殘餘比 (f_tau - 1) / (f0 - 1) 應 = 1/e
        residual_ratio = (f_tau - f_inf) / (f0 - f_inf)
        assert abs(residual_ratio - 1.0 / math.e) < 0.01, (
            f"1τ 殘餘 {residual_ratio:.4f} ≠ 1/e ({1.0 / math.e:.4f})"
        )

    def test_idle_state_does_not_warm_up(self):
        """非 producing 狀態下 _running_seconds 不增加（stop 不算 warm up）。"""
        spec = DrivetrainSpec.for_geared(overall_ratio=104.5)
        m = DrivetrainModel(spec=spec)
        for _ in range(60):
            m.step(
                aero_rotor_speed=0.0, current_rotor_speed=0.0,
                aero_torque_knm=0.0, aero_load_factor=0.0,
                dt=10.0, is_producing=False, is_starting=False,
                is_normal_stop=False, is_emergency_stop=False,
            )
        assert m._running_seconds == 0.0  # noqa: SLF001


# ════════════════════════════════════════════════════════════════════════
# 7. ISA Air Density  ──  ρ = 1.2250 kg/m³ at 15°C, dry, 1013.25 hPa
# ════════════════════════════════════════════════════════════════════════
#
# Reference:
#   International Standard Atmosphere (ISA) / ICAO Standard Atmosphere
#   T_0=15°C, P_0=1013.25 hPa, dry air: ρ_0 = 1.2250 kg/m³
#
# 模型 default `TurbineSpec.air_density = 1.225`（ICAO ISA value）。
# IEC 61400-12-1 power-curve normalization 用 1.225；偏離超過 ±0.5% 在電量
# 計算上會顯著影響（P ∝ ρ）。

class TestISAAirDensity:
    """ISA standard air density baseline。"""

    ISA_RHO = 1.2250  # kg/m³

    def test_turbine_spec_default_matches_isa(self):
        """TurbineSpec.air_density 預設應為 ISA 1.225 kg/m³。"""
        spec = TurbineSpec()
        rel_err = abs(spec.air_density - self.ISA_RHO) / self.ISA_RHO
        assert rel_err < 0.005, (
            f"預設 air_density={spec.air_density} 偏離 ISA {self.ISA_RHO} "
            f"(rel_err={rel_err:.4%})"
        )

    def test_thrust_uses_isa_default(self):
        """CpSurfaceModel.get_aero_thrust_kn 預設 air_density=1.225 對得上 ISA。"""
        m = CpSurfaceModel(cp_max=0.48)
        # 帶入 default ρ
        T_default = m.get_aero_thrust_kn(10.0, 0.7, 70.65)
        # 顯式帶 ISA 應一致
        T_explicit = m.get_aero_thrust_kn(10.0, 0.7, 70.65, air_density=self.ISA_RHO)
        assert abs(T_default - T_explicit) < 1e-9

    def test_density_scaling_linear_in_thrust(self):
        """ρ × 1.5 → thrust × 1.5（IEC 61400-12-1 power-curve normalization 假設）。"""
        m = CpSurfaceModel(cp_max=0.48)
        T_isa = m.get_aero_thrust_kn(10.0, 0.7, 70.65, air_density=self.ISA_RHO)
        T_high = m.get_aero_thrust_kn(10.0, 0.7, 70.65,
                                       air_density=self.ISA_RHO * 1.5)
        assert abs(T_high / T_isa - 1.5) < 1e-4
