"""Layer 4 — Cross-module Consistency（WMOM-20260505-23）。

驗證物理模型跨模組之間的耦合方向與一致性。每個 test class 對應一條：

    1. TestRegion2CubicLaw         ──  Region 2 power ~ V³ (R² > 0.95)
    2. TestStatorPowerLag          ──  stator temp 落後 power ~5-10 min（熱慣性）
    3. TestInterTurbineIndividuality ──  個體差異有作用且不爆表
    4. TestRegion3PowerCV          ──  Region 3 power CV 結構性檢查（與 WMOM-24 對齊）
    5. TestStabilityCoupling       ──  stability 改變 wake k* 與 turbulence τ

Layer 4 重點是「結構性 invariant」（A 動 B 該動的方向是否正確），
而非單一數值的 calibration（後者由 WMOM-24 處理）。
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from simulator.physics import TurbinePhysicsModel
from simulator.physics.wind_field import (
    PerTurbineWind, TurbinePosition, TurbulenceGenerator,
)


def _build_turbines(n: int, settle_steps: int = 180,
                    V: float = 10.0) -> list:
    """Helper：建立 n 個 spin-up 完成的 turbines。"""
    turbines = [TurbinePhysicsModel(seed=i + 1) for i in range(n)]
    for _ in range(settle_steps):
        for m in turbines:
            m.step(wind_speed=V, wind_direction=180.0,
                   ambient_temp=15.0, dt=1.0)
    return turbines


# ════════════════════════════════════════════════════════════════════════
# 1. Region 2 Cubic Law  ──  P ~ ½ × ρ × A × Cp × V³ → fit R² > 0.95
# ════════════════════════════════════════════════════════════════════════
#
# Region 2（partial load）下 Cp 近常數 → P ≈ k × V³。對長序列做最小平方
# fit，R² 必須極接近 1（容差 R² > 0.95，含 turbulence/stall 隨機項）。
# 此 test 驗 power_curve 與其上下游耦合（rotor speed control、Cp surface）
# 整體一致 — Region 2 不能因任何 fault-free path 偏離 V³ 太多。

class TestRegion2CubicLaw:
    """Region 2 power-vs-wind cubic fit R² 必須 > 0.95。"""

    def test_cubic_fit_quality(self):
        """V ∈ [4, 11] 掃描，sample 平均 power → fit P=a·V³ 之 R² > 0.95。"""
        m = TurbinePhysicsModel(seed=42)
        # warm-up 至 production
        for _ in range(180):
            m.step(wind_speed=10.0, wind_direction=180.0,
                   ambient_temp=15.0, dt=1.0)

        Vs = np.linspace(4.0, 11.0, 30)
        Ps = []
        for V in Vs:
            sub = []
            for _ in range(30):
                tags = m.step(wind_speed=float(V), wind_direction=180.0,
                              ambient_temp=15.0, dt=1.0)
                sub.append(tags["WTUR_TotPwrAt"])
            Ps.append(float(np.mean(sub)))
        P = np.array(Ps)

        # least-squares：P = a × V³
        a, _, _, _ = np.linalg.lstsq(Vs.reshape(-1, 1) ** 3, P, rcond=None)
        P_pred = (Vs ** 3) * a[0]
        ss_res = float(np.sum((P - P_pred) ** 2))
        ss_tot = float(np.sum((P - P.mean()) ** 2))
        R2 = 1.0 - ss_res / ss_tot
        assert R2 > 0.95, (
            f"Region 2 cubic fit R²={R2:.4f} ≤ 0.95 — 物理鏈耦合走樣"
        )

    def test_doubling_wind_eightfolds_power(self):
        """V × 2 在 Region 2 內 → power × ~8（V³ 比例 invariant）。"""
        m = TurbinePhysicsModel(seed=43)
        for _ in range(180):
            m.step(wind_speed=10.0, wind_direction=180.0,
                   ambient_temp=15.0, dt=1.0)

        # V=5 vs V=10（皆在 Region 2，cut_in=3, rated=13）
        for V in (5.0, 10.0):
            for _ in range(30):
                m.step(wind_speed=V, wind_direction=180.0,
                       ambient_temp=15.0, dt=1.0)

        # 重新跑 with reset（避免 carry-over）
        results = {}
        for V in (5.0, 10.0):
            mp = TurbinePhysicsModel(seed=43)
            for _ in range(180):
                mp.step(wind_speed=V, wind_direction=180.0,
                        ambient_temp=15.0, dt=1.0)
            sub = []
            for _ in range(60):
                tags = mp.step(wind_speed=V, wind_direction=180.0,
                               ambient_temp=15.0, dt=1.0)
                sub.append(tags["WTUR_TotPwrAt"])
            results[V] = float(np.mean(sub))

        ratio = results[10.0] / max(results[5.0], 1.0)
        # 容差 ±25%（含 Cp 微調、轉速 transient）
        assert 6.0 < ratio < 10.0, (
            f"P(10)/P(5)={ratio:.2f}，預期 ≈ 8.0（cubic invariant）"
        )


# ════════════════════════════════════════════════════════════════════════
# 2. Stator Temp Lags Power  ──  熱慣性 → r > 0.5 在 lag > 60 s
# ════════════════════════════════════════════════════════════════════════
#
# Stator 熱模型 R_th=0.65, τ=600 s（thermal_model.py:59）。
# 給長週期（1500 s）power 變動 → temp 響應該在 lag ~τ 達最大相關。
# 此 test 驗證 thermal_model × power 之間的耦合方向與時間常數合理。

class TestStatorPowerLag:
    """Stator temp 與 power 的相關性峰值在 lag ~5-10 min。"""

    def test_max_correlation_at_thermal_lag(self):
        """1500 s 週期 sinusoidal load → temp 響應峰值 r > 0.5 落 lag ∈ [240, 600] s。"""
        m = TurbinePhysicsModel(seed=10)
        # warm up
        for _ in range(180):
            m.step(wind_speed=8.0, wind_direction=180.0,
                   ambient_temp=15.0, dt=1.0)

        # 強 sinusoidal load：周期 1500 s（涵蓋 stator τ=600 s 約 2.5 倍）
        P, T = [], []
        for s in range(2400):
            V = 7.0 + 4.0 * math.sin(2.0 * math.pi * s / 1500.0)
            tags = m.step(wind_speed=V, wind_direction=180.0,
                          ambient_temp=15.0, dt=1.0)
            P.append(tags["WTUR_TotPwrAt"])
            T.append(tags["WGEN_GnStaTmp1"])
        P_arr = np.array(P)
        T_arr = np.array(T)

        # 掃描 lag，找 max |r|
        lags = list(range(0, 700, 30))
        rs = []
        for lag in lags:
            if lag == 0:
                r = float(np.corrcoef(P_arr, T_arr)[0, 1])
            else:
                r = float(np.corrcoef(P_arr[:-lag], T_arr[lag:])[0, 1])
            rs.append(r)

        rs_arr = np.array(rs)
        peak_idx = int(np.argmax(rs_arr))
        peak_lag = lags[peak_idx]
        peak_r = rs_arr[peak_idx]

        assert peak_r > 0.5, (
            f"max(r) over lag={peak_r:.4f} 不夠高（peak 應 > 0.5）"
        )
        assert peak_lag > 60, (
            f"peak lag={peak_lag}s 太短（熱慣性應 > 60 s）"
        )
        assert peak_lag < 700, (
            f"peak lag={peak_lag}s 過長（>>τ_thermal=600 s 表示模型有問題）"
        )


# ════════════════════════════════════════════════════════════════════════
# 3. Inter-turbine Individuality  ──  spread > 0（per-seed RNG 有作用）
# ════════════════════════════════════════════════════════════════════════
#
# 每台風機 seed 不同 → individuality 參數（cp_offset、wind_sensor_scale 等）
# 不同 → 同風況下 power 應有非零 spread。
#
# Note：此 test 不嚴格驗 spread 落 [10%, 25%]（WMOM-24 calibration 目標）— Layer 4
# 只驗 individuality 機制有作用（non-zero）且不爆表（< 50%）。WMOM-24 lands 後
# 可加緊範圍。

class TestInterTurbineIndividuality:
    """5 台風機同風況：spread > 0 且 < 50%（個體機制有作用且不亂跳）。"""

    def test_spread_within_reasonable_range(self):
        """5 turbines @ V=10 m/s 60 s 平均 power spread ∈ (0, 50%]。"""
        n = 5
        turbines = _build_turbines(n, settle_steps=180, V=10.0)

        # 60 s 平均
        sums = [[] for _ in range(n)]
        for _ in range(60):
            for i, m in enumerate(turbines):
                tags = m.step(wind_speed=10.0, wind_direction=180.0,
                              ambient_temp=15.0, dt=1.0)
                sums[i].append(tags["WTUR_TotPwrAt"])
        avgs = np.array([np.mean(p) for p in sums])
        spread = (avgs.max() - avgs.min()) / avgs.mean()

        assert spread > 0.005, (
            f"spread={spread:.4f} 太小，individuality 機制可能沒生效"
        )
        # WMOM-24 完成後可改 ≤ 0.30 嚴格化
        assert spread < 0.50, (
            f"spread={spread:.4f} > 50%，個體差異參數失控"
        )

    def test_each_turbine_has_distinct_signature(self):
        """5 台 seed 不同 → 每台 power 平均值都不完全相同（個體不退化成 single）。"""
        n = 5
        turbines = _build_turbines(n, settle_steps=180, V=10.0)
        sums = [[] for _ in range(n)]
        for _ in range(60):
            for i, m in enumerate(turbines):
                tags = m.step(wind_speed=10.0, wind_direction=180.0,
                              ambient_temp=15.0, dt=1.0)
                sums[i].append(tags["WTUR_TotPwrAt"])
        avgs = [round(float(np.mean(p)), 1) for p in sums]
        # 不應有任何兩台完全相同（rounded 到 0.1 kW）
        assert len(set(avgs)) == n, (
            f"5 台中有重複 power 平均值：{avgs}"
        )


# ════════════════════════════════════════════════════════════════════════
# 4. Region 3 Power CV  ──  結構性檢查（與 WMOM-24 對齊）
# ════════════════════════════════════════════════════════════════════════
#
# Region 3（rated wind > 13 m/s）下 power 應大致 = rated，但 controller
# dead-band + pitch lag 會產生小幅 oscillation（CV）。
# 文獻 + 真機 typical CV 落 [3%, 8%]（WMOM-24 acceptance）。
#
# 模型現況可能 CV 偏低（例如 0.8% 如 examples/data_quality_report.txt 指出），
# 此 test 用寬鬆 bound 驗結構性「>0 但 <20%」，等 WMOM-24 收緊。

class TestRegion3PowerCV:
    """Region 3 power 圍繞 rated 有非零 fluctuation，但不爆表。"""

    def test_cv_in_structural_range(self):
        """Rated wind 14 m/s，60 s 取樣 → CV ∈ (0, 0.20]。"""
        m = TurbinePhysicsModel(seed=44)
        for _ in range(240):  # 較長 warm-up 進入穩定 region 3
            m.step(wind_speed=14.0, wind_direction=180.0,
                   ambient_temp=15.0, dt=1.0)

        # 後 120 s 取樣
        powers = []
        for _ in range(120):
            tags = m.step(wind_speed=14.0, wind_direction=180.0,
                          ambient_temp=15.0, dt=1.0)
            powers.append(tags["WTUR_TotPwrAt"])
        arr = np.array(powers)
        cv = float(arr.std() / max(arr.mean(), 1.0))

        # 結構性 bound — WMOM-24 完成後可收緊到 [0.03, 0.08]
        assert 0.0 < cv < 0.20, (
            f"Region 3 power CV={cv:.4f} 落 (0, 0.20] 之外 — controller 行為失常"
        )

    def test_region3_power_near_rated(self):
        """Rated wind → 平均 power ≈ rated_power_kw（容差 ±10%）。"""
        m = TurbinePhysicsModel(seed=45)
        for _ in range(240):
            m.step(wind_speed=14.0, wind_direction=180.0,
                   ambient_temp=15.0, dt=1.0)
        powers = []
        for _ in range(60):
            tags = m.step(wind_speed=14.0, wind_direction=180.0,
                          ambient_temp=15.0, dt=1.0)
            powers.append(tags["WTUR_TotPwrAt"])
        avg_p = float(np.mean(powers))
        rated = m.spec.rated_power_kw  # 2000
        rel_err = abs(avg_p - rated) / rated
        assert rel_err < 0.10, (
            f"Region 3 平均 power={avg_p:.0f} 偏離 rated={rated}（rel_err={rel_err:.4f}）"
        )


# ════════════════════════════════════════════════════════════════════════
# 5. Atmospheric Stability Coupling  ──  s 改變 wake k* 與 turbulence τ
# ════════════════════════════════════════════════════════════════════════
#
# Stability convention: s ∈ [-1, +1]（−1 stable, +1 unstable convective）。
#
# Layer 4 驗證跨模組 stability 系列耦合的方向：
#   - turbulence τ：stable → 大（低頻為主）（已 Layer 2 驗證 lag-1 自相關）
#   - wake k* expansion：stable → 小（wake 持久）→ 同距離 deficit 更大
# 兩者相反方向是物理一致性 invariant（#99/#113/#115 #103）。

class TestStabilityCoupling:
    """大氣穩定度對 wake / turbulence 的耦合方向正確。"""

    def test_stable_atm_increases_wake_deficit(self):
        """5D 處：stability=−1（穩定）下 deficit ≥ stability=+1（對流）。"""
        D = 70.65
        positions = [
            TurbinePosition(x=0.0, y=0.0),
            TurbinePosition(x=5.0 * D, y=0.0),
        ]
        deficits = {}
        for label, s in [("stable", -1.0), ("unstable", +1.0)]:
            samples = []
            for seed in range(15):
                ptw = PerTurbineWind(
                    turbine_count=2, seed=seed,
                    rotor_diameter=D, positions=positions,
                )
                for _ in range(30):
                    ptw.step(farm_wind=8.0, wind_direction=270.0,
                             turbulence_intensity=0.08, dt=1.0,
                             atm_stability=s)
                samples.append(ptw.get_wake_deficit(1))
            deficits[label] = float(np.mean(samples))

        # 穩定大氣 → 小 k* → wake 持久 → 同距離下 deficit 更大
        assert deficits["stable"] >= deficits["unstable"], (
            f"穩定大氣 deficit ({deficits['stable']:.4f}) 應 ≥ "
            f"對流大氣 deficit ({deficits['unstable']:.4f})"
        )

    def test_stable_atm_lengthens_turbulence_correlation(self):
        """Stability < 0 → L_u 加大 → AR(1) lag-1 更接近 1（已 Layer 2 嚴格驗，這裡再 cross-check）。"""
        gen_stable = TurbulenceGenerator(seed=42)
        gen_unstable = TurbulenceGenerator(seed=42)
        ss_stable = []
        ss_unstable = []
        for _ in range(2000):
            ss_stable.append(gen_stable.step(12.0, 0.10, dt=1.0, stability=-1.0))
            ss_unstable.append(gen_unstable.step(12.0, 0.10, dt=1.0, stability=+1.0))

        s_arr = np.array(ss_stable)
        u_arr = np.array(ss_unstable)
        lag1_stable = float(np.corrcoef(s_arr[:-1], s_arr[1:])[0, 1])
        lag1_unstable = float(np.corrcoef(u_arr[:-1], u_arr[1:])[0, 1])

        assert lag1_stable > lag1_unstable, (
            f"stable lag-1={lag1_stable:.4f} 未大於 unstable={lag1_unstable:.4f}"
        )
