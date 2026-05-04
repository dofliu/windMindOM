"""K13 equivalence test for cost_cal engine.

從 ECN/backend/tests/test_cost_cal_engine.py 移植：
- import path 改為 modules.cost.engine.*
- DATA_DIR 改為 modules/cost/data/demo/
- 加 strict pinned equivalence test（windMindOM 必須 bit-perfect == ECN）

驗證策略：
1. **Migration correctness（最重要）** — `test_k13_migration_equivalence_pinned`
   把 ECN engine 在 K13 上的實際輸出（top-level 6 metrics + 4 季 5 cost
   subcategories）hardcode 進來，windMindOM engine 必須 bit-perfect 一致
   （float 直接 ==）
2. **K13 reference 比對（diagnostic）** — `test_k13_cost_calculation` 沿用 ECN 原版
   tolerance check（5-30%），數字接近 ECN V5 reference 即可

Tolerances 與 ECN 原版一致；數字偏差說明見 docs/legacy/ecn_k13_baseline.md §2.1。
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.cost.adapter import load_k13_engine_params  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────
# Pinned ECN baseline (2026-05-04，用 repr() 取 float64 完整精度)
# ─────────────────────────────────────────────────────────────────────────

ECN_PINNED_K13 = {
    "availability_time": 0.9401732630646628,
    "availability_energy": 0.9364235587596128,
    "total_revenue_loss": 15202721.720482074,
    "total_repair_cost": 52761689.17773973,
    "total_effort": 67964410.8982218,
    "cost_per_kwh": 0.036948752282382154,
}

ECN_PINNED_K13_SEASONAL = {
    "winter": {
        "corrective_wt_material": 3129581.8937500003,
        "corrective_wt_equipment": 3269378.191780823,
        "corrective_wt_revenue_loss": 6367752.467871219,
        "preventive_material": 0.0,
        "fixed_cost": 5550000.0,
    },
    "spring": {
        "corrective_wt_material": 3129581.8937500003,
        "corrective_wt_equipment": 1297513.9726027397,
        "corrective_wt_revenue_loss": 1929932.1324677265,
        "preventive_material": 572075.0,
        "fixed_cost": 5175000.0,
    },
    "summer": {
        "corrective_wt_material": 3129581.8937500003,
        "corrective_wt_equipment": 878499.7534246575,
        "corrective_wt_revenue_loss": 1074113.5352917863,
        "preventive_material": 898975.0,
        "fixed_cost": 5175000.0,
    },
    "autumn": {
        "corrective_wt_material": 3129581.8937500003,
        "corrective_wt_equipment": 2222792.356164384,
        "corrective_wt_revenue_loss": 4015762.8459275244,
        "preventive_material": 163450.0,
        "fixed_cost": 5475000.0,
    },
}


@pytest.fixture(scope="module")
def k13_result():
    """Run cost calculation once，給多個 test 共用結果。"""
    from modules.cost.engine.cost_cal import run_cost_calculation

    p = load_k13_engine_params(stochastic=False)
    return run_cost_calculation(
        wind_farm=p.wind_farm,
        components=p.components,
        equipment_list=p.equipment_list,
        pm_schedules=p.pm_schedules,
        fixed_costs=p.fixed_costs,
        poly_lookup=p.poly_lookup,
    )


# ─────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────


def test_k13_migration_equivalence_pinned(k13_result):
    """Migration gate — windMindOM 必須 bit-perfect 等於 ECN 在 K13 上的輸出。"""
    print("\nTOP-LEVEL METRICS (windMindOM vs ECN pinned):")
    failures: list[str] = []
    for metric, expected in ECN_PINNED_K13.items():
        actual = getattr(k13_result, metric)
        status = "OK" if actual == expected else "DRIFT"
        print(f"  {metric:<24} actual={actual!r}  expected={expected!r}  {status}")
        if actual != expected:
            failures.append(f"{metric}: actual={actual!r} != expected={expected!r}")

    assert not failures, f"Top-level metric drift: {failures}"


def test_k13_migration_equivalence_seasonal(k13_result):
    """Seasonal breakdown — 4 季 × 5 cost subcategories 全部 bit-perfect。"""
    print("\nSEASONAL BREAKDOWN (windMindOM vs ECN pinned):")
    failures: list[str] = []
    for season, expected_dict in ECN_PINNED_K13_SEASONAL.items():
        sr = k13_result.seasonal_results[season]
        for field, expected in expected_dict.items():
            actual = getattr(sr, field)
            if actual != expected:
                failures.append(
                    f"{season}.{field}: actual={actual!r} != expected={expected!r}"
                )

    if failures:
        for f in failures:
            print(f"  DRIFT: {f}")
    else:
        print("  All 4 seasons × 5 fields bit-perfect")
    assert not failures, f"Seasonal drift: {failures}"


def test_k13_cost_calculation(k13_result):
    """ECN reference value 比對 — tolerance 與 ECN 原版一致（5-30%）。

    Reference values from ECN O&M Tool V5 OverviewResults。Tolerance 容
    ECN Excel ↔ Python port 之間 methodology 差異（revenue loss weighting、
    seasonal CF averaging、equipment cost calc 細節）。
    """
    failures: list[str] = []

    def check(name: str, actual: float, expected: float, tolerance_pct: float):
        error_pct = abs(actual - expected) / expected * 100 if expected else 0.0
        ok = error_pct <= tolerance_pct
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}: {actual:.2f} vs {expected:.2f} (err {error_pct:.1f}% / tol {tolerance_pct}%)")
        if not ok:
            failures.append(f"{name}: {actual} vs {expected} (err {error_pct:.1f}% > tol {tolerance_pct}%)")

    print("\nECN V5 REFERENCE COMPARISON:")
    check("Availability (time) %",  k13_result.availability_time * 100,  92.6, 5)
    check("Availability (energy) %", k13_result.availability_energy * 100, 92.1, 5)
    check("Revenue losses (M EUR)",  k13_result.total_revenue_loss / 1e6,  21.1, 30)
    check("Repair costs (M EUR)",    k13_result.total_repair_cost / 1e6,   51.1, 15)
    check("Total effort (M EUR)",    k13_result.total_effort / 1e6,        72.2, 15)

    assert not failures, f"ECN reference comparison failures: {failures}"
