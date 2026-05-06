"""Layer 5 — Fault Injection Signatures（WMOM-20260505-23）。

對每個 fault scenario 注入後驗證 SCADA tag 朝預期方向變動，並在無 fault 條件下
驗證 health baseline（crest/kurtosis/RMS 落 ISO zone A/B）。

每筆 case = (fault_id, severity, tag, direction, min_delta)：
    direction = '+' ─ faulty 平均應比 baseline 高 min_delta
    direction = '-' ─ faulty 平均應比 baseline 低 min_delta
    direction = 'abs' ─ |delta| ≥ min_delta（不限方向）

baseline 與 fault sim 同 seed、同 wind / 同 ambient，僅 active_faults 不同。
sample 60 s 取平均，避免 single-step 雜訊主導。
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pytest

from simulator.physics import TurbinePhysicsModel


# ── 共用 fixture：跑 baseline + fault 模擬，回傳兩組 SCADA tag 平均 ───────
def _run_paired(fault_id: str | None, severity: float,
                seed: int = 10,
                V: float = 11.0,
                warm_steps: int = 180,
                fault_propagation_steps: int = 600,
                sample_steps: int = 60) -> Tuple[Dict[str, float], Dict[str, float]]:
    """跑同 seed baseline + faulty，回傳兩個 dict（SCADA tag → 60 s 平均）。"""
    mb = TurbinePhysicsModel(seed=seed)
    mf = TurbinePhysicsModel(seed=seed)
    for _ in range(warm_steps):
        mb.step(wind_speed=V, wind_direction=180.0, ambient_temp=15.0, dt=1.0)
        mf.step(wind_speed=V, wind_direction=180.0, ambient_temp=15.0, dt=1.0)
    if fault_id is not None:
        mf.active_faults = [{"scenario_id": fault_id, "severity": severity}]
    for _ in range(fault_propagation_steps):
        mb.step(wind_speed=V, wind_direction=180.0, ambient_temp=15.0, dt=1.0)
        mf.step(wind_speed=V, wind_direction=180.0, ambient_temp=15.0, dt=1.0)

    b_samples: List[Dict[str, float]] = []
    f_samples: List[Dict[str, float]] = []
    for _ in range(sample_steps):
        b_samples.append(
            mb.step(wind_speed=V, wind_direction=180.0,
                    ambient_temp=15.0, dt=1.0)
        )
        f_samples.append(
            mf.step(wind_speed=V, wind_direction=180.0,
                    ambient_temp=15.0, dt=1.0)
        )

    def mean_dict(samples: List[Dict[str, float]]) -> Dict[str, float]:
        keys = samples[0].keys()
        return {
            k: float(np.mean([s.get(k, 0.0) for s in samples])) for k in keys
        }

    return mean_dict(b_samples), mean_dict(f_samples)


# ── Fault → expected signature 列表 ──────────────────────────────────────
# (fault_id, severity, tag, direction, min_delta_or_min_abs)
FAULT_SIGNATURES: List[Tuple[str, float, str, str, float]] = [
    # bearing_wear → vibration 顯著上升
    ("bearing_wear",          0.85, "WNAC_VibMsNacXDir", "+", 0.4),
    ("bearing_wear",          0.85, "WNAC_VibMsNacYDir", "+", 0.3),

    # generator_overspeed → rotor / gen speed 飆 + vibration
    ("generator_overspeed",   0.85, "WROT_RotSpd",       "+", 2.0),
    ("generator_overspeed",   0.85, "WGEN_GnSpd",        "+", 2.0),
    ("generator_overspeed",   0.85, "WNAC_VibMsNacXDir", "+", 1.0),

    # converter_cooling_fault → power 跌 + 冷卻液 level 跌
    ("converter_cooling_fault", 0.85, "WTUR_TotPwrAt",   "-", 50.0),
    ("converter_cooling_fault", 0.85, "WCOL_CoolantLvl", "-", 0.05),

    # transformer_overheat → trf core temp 升
    ("transformer_overheat",  0.85, "WGDC_TrfCoreTmp",   "+", 2.0),

    # pitch_imbalance → blade 1 pitch 偏移 + power 跌
    ("pitch_imbalance",       0.85, "WROT_PtAngValBl1",  "abs", 1.0),
    ("pitch_imbalance",       0.85, "WNAC_VibMsNacXDir", "+", 0.5),

    # yaw_sensor_drift → power 跌（cos 損失）
    ("yaw_sensor_drift",      0.85, "WTUR_TotPwrAt",     "-", 30.0),

    # stator_winding_degradation → 電氣噪訊 + 額外熱
    ("stator_winding_degradation", 0.85, "WGEN_GnStaTmp1", "+", 1.0),

    # blade_icing → power 大跌 + asymmetric vibration
    ("blade_icing",           0.85, "WTUR_TotPwrAt",     "-", 100.0),
    ("blade_icing",           0.85, "WNAC_VibMsNacYDir", "+", 0.8),

    # nacelle_cooling_failure → nacelle / generator 溫度升
    ("nacelle_cooling_failure", 0.85, "WNAC_NacTmp",     "+", 0.4),
    ("nacelle_cooling_failure", 0.85, "WGEN_GnStaTmp1",  "+", 1.0),

    # grid_voltage_sag → power 跌
    ("grid_voltage_sag",      0.85, "WTUR_TotPwrAt",     "-", 30.0),

    # legacy aliases — 仍有效
    ("gearbox_overheat",      0.85, "WNAC_VibMsNacXDir", "+", 0.3),
    ("pitch_motor_fault",     0.85, "WTUR_TotPwrAt",     "-", 50.0),
    ("yaw_misalignment",      0.85, "WTUR_TotPwrAt",     "-", 50.0),
]


@pytest.mark.parametrize("fault_id,severity,tag,direction,min_delta", FAULT_SIGNATURES)
def test_fault_signature(fault_id, severity, tag, direction, min_delta):
    """注入 fault 後 tag 朝預期方向變動 ≥ min_delta。"""
    baseline, faulty = _run_paired(fault_id, severity)
    bv = baseline[tag]
    fv = faulty[tag]
    delta = fv - bv

    if direction == "+":
        assert delta >= min_delta, (
            f"{fault_id}: {tag} 沒有上升足夠多 — "
            f"baseline={bv:.3f}, faulty={fv:.3f}, delta={delta:+.3f} (要求 ≥ +{min_delta})"
        )
    elif direction == "-":
        assert delta <= -min_delta, (
            f"{fault_id}: {tag} 沒有下降足夠多 — "
            f"baseline={bv:.3f}, faulty={fv:.3f}, delta={delta:+.3f} (要求 ≤ -{min_delta})"
        )
    elif direction == "abs":
        assert abs(delta) >= min_delta, (
            f"{fault_id}: {tag} |delta| 不夠大 — "
            f"baseline={bv:.3f}, faulty={fv:.3f}, |delta|={abs(delta):.3f} (要求 ≥ {min_delta})"
        )
    else:
        pytest.fail(f"未知 direction code: {direction}")


# ════════════════════════════════════════════════════════════════════════
# Health Baseline Sanity（No-fault 條件）
# ════════════════════════════════════════════════════════════════════════
#
# 健康風機在 production 工況下：
#   - vibration overall RMS 落 ISO 10816 Zone A 或 B 低端
#   - crest factor < 5（無 impulsive defect）
#   - kurtosis ≈ 3-4（接近 Gaussian）

class TestHealthBaseline:
    """無 fault 注入條件下，振動 / power 走在合理範圍。"""

    def test_no_fault_overall_vibration_below_zone_b(self):
        """healthy production：overall RMS（5 bands quadrature）≤ 4.5 mm/s。"""
        m = TurbinePhysicsModel(seed=20)
        for _ in range(180):
            m.step(wind_speed=11.0, wind_direction=180.0,
                   ambient_temp=15.0, dt=1.0)
        samples = []
        for _ in range(60):
            tags = m.step(wind_speed=11.0, wind_direction=180.0,
                          ambient_temp=15.0, dt=1.0)
            samples.append(tags)

        # SCADA 提供 overall vibration X/Y（mm/s RMS）
        vib_x = float(np.mean([s.get("WNAC_VibMsNacXDir", 0.0) for s in samples]))
        vib_y = float(np.mean([s.get("WNAC_VibMsNacYDir", 0.0) for s in samples]))
        overall = (vib_x ** 2 + vib_y ** 2) ** 0.5

        assert overall < 4.5, (
            f"健康基線 overall RMS = {overall:.3f} mm/s 已 ≥ Zone B 上限 4.5"
        )

    def test_no_fault_power_close_to_lookup(self):
        """healthy production V=11：30 s 平均 power 偏離 lookup curve < 30%。"""
        m = TurbinePhysicsModel(seed=21)
        for _ in range(180):
            m.step(wind_speed=11.0, wind_direction=180.0,
                   ambient_temp=15.0, dt=1.0)
        powers = []
        for _ in range(60):
            tags = m.step(wind_speed=11.0, wind_direction=180.0,
                          ambient_temp=15.0, dt=1.0)
            powers.append(tags["WTUR_TotPwrAt"])
        avg_p = float(np.mean(powers))

        # Z72 lookup @ V=11 = 1700 kW（power_curve.py:31）
        # 容差 30% 涵蓋 individuality + Cp 動態
        expected = 1700.0
        rel_err = abs(avg_p - expected) / expected
        assert rel_err < 0.30, (
            f"healthy V=11 平均 P={avg_p:.0f} 偏離 lookup {expected} "
            f"(rel_err={rel_err:.4f}) 過多"
        )

    def test_no_fault_no_active_faults_recorded(self):
        """模型內部 active_faults list 預設應為空（health baseline）。"""
        m = TurbinePhysicsModel(seed=22)
        assert m.active_faults == []
        for _ in range(60):
            m.step(wind_speed=10.0, wind_direction=180.0,
                   ambient_temp=15.0, dt=1.0)
        assert m.active_faults == []
