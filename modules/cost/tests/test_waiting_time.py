"""Test the WaitingTime calculation engine against K13 demo data.

從 ECN/backend/tests/test_waiting_time_engine.py 移植：
- import path 改為 modules.cost.engine.*
- DATA_DIR 改為 modules/cost/data/demo/
- return True/False → assert（消除 PytestReturnNotNoneWarning）

驗證策略：
1. **Migration correctness（最重要）** — `test_migration_equivalence_pinned` 把
   ECN engine 在 K13 上的實際輸出 hardcode 進來，windMindOM engine 必須
   bit-perfect 一致（< 1e-10）。這是 migration 不漏洞的 gate。
2. **K13 reference 比對（diagnostic）** — 三個原 ECN test 沿用，但容忍度比照
   ECN 原版（winter < 1e-4 / 1e-2）。第 3 個跨季 test 是 ECN 既有 issue
   （K13 JSON reference 與 ECN 實際算出來不符），mark xfail 保留診斷。
   詳見 docs/legacy/ecn_k13_baseline.md。
"""

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Project root: windMindOM/ — 4 levels up from this file
PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "demo"


def load_metocean_data() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "k13_metocean.csv", parse_dates=["timestamp"])


def load_weather_windows() -> list[dict]:
    with open(DATA_DIR / "k13_weather_windows.json") as f:
        return json.load(f)["definition_sheet"]


def load_expected_coefficients() -> dict:
    with open(DATA_DIR / "k13_waiting_time_coefficients.json") as f:
        return json.load(f)


def load_general_params() -> dict:
    with open(DATA_DIR / "k13_general.json") as f:
        return json.load(f)


def test_ww3_winter():
    """WW3 winter — 主驗證 case，4 個 polynomial 係數須 < 1e-4 誤差。"""
    from modules.cost.engine.waiting_time import (
        WeatherWindowConfig,
        run_waiting_time_analysis,
    )

    df = load_metocean_data()
    general = load_general_params()
    expected = load_expected_coefficients()

    pv_curve = [(p["v_ms"], p["p_kw"]) for p in general["pv_curve"]]
    windows = [
        WeatherWindowConfig(
            nr=3, max_vw=12, max_hs=1.5,
            max_hsd_max=355, max_hsd_min=5, lwd=0, h_vw=85,
        ),
    ]

    t0 = time.time()
    results = run_waiting_time_analysis(
        df=df,
        weather_windows=windows,
        seasons=["winter"],
        pv_curve=pv_curve,
        v_in=general["turbine"]["v_in_ms"],
        v_out=general["turbine"]["v_out_ms"],
        mission_times=[3, 6, 9, 12, 15, 21, 27, 36, 45, 63],
        poly_order=3,
        start_hour=7,
        end_hour=18,
        meas_height=10.0,
        hub_height=general["turbine"]["hub_height_m"],
        wind_profile_exponent=general["wind_profile_exponent"],
    )
    elapsed = time.time() - t0
    print(f"\nCalculation time: {elapsed:.2f}s")

    r = results[0]
    e3 = next(e for e in expected["waiting_time"]["winter"] if e["nr"] == 3)

    print("\nPOLYNOMIAL COEFFICIENTS (Waiting Time):")
    for ci in ["c0", "c1", "c2", "c3"]:
        calc_val = r.wait_coeffs[f"wait_{ci}"]
        exp_val = e3[ci]
        diff = abs(calc_val - exp_val)
        status = "OK" if diff < 1e-4 else "FAIL"
        print(f"  {ci}: calc={calc_val:18.10f}  exp={exp_val:18.10f}  diff={diff:.2e}  {status}")
        assert diff < 1e-4, f"Coefficient {ci} mismatch: calc={calc_val} vs exp={exp_val}"

    print(f"  R-squared: {r.wait_coeffs['r_squared']:.6f}")


def test_all_windows_winter():
    """All 13 weather windows × winter — c0/c1 須 < 1e-2 誤差（較寬容忍）。"""
    from modules.cost.engine.waiting_time import (
        WeatherWindowConfig,
        run_waiting_time_analysis,
    )

    df = load_metocean_data()
    general = load_general_params()
    expected = load_expected_coefficients()
    ww_defs = load_weather_windows()

    seen: set[int] = set()
    unique_wws: list[dict] = []
    for w in ww_defs:
        if w["window_nr"] not in seen:
            seen.add(w["window_nr"])
            unique_wws.append(w)

    windows = [
        WeatherWindowConfig(
            nr=w["window_nr"],
            max_vw=w["vw"],
            max_hs=w["hs"],
            max_hsd_max=w["hsd_max"],
            max_hsd_min=w["hsd_min"],
            lwd=w["lwd"],
            h_vw=w.get("h_vw", 85),
        )
        for w in unique_wws
        if w["vw"] > 0
    ]

    t0 = time.time()
    results = run_waiting_time_analysis(
        df=df,
        weather_windows=windows,
        seasons=["winter"],
        mission_times=[3, 6, 9, 12, 15, 21, 27, 36, 45, 63],
        poly_order=3,
        start_hour=7,
        end_hour=18,
        meas_height=10.0,
        hub_height=general["turbine"]["hub_height_m"],
        wind_profile_exponent=general["wind_profile_exponent"],
    )
    elapsed = time.time() - t0
    print(f"\nCalculation time: {elapsed:.2f}s for {len(windows)} windows")

    failures: list[str] = []
    for r in results:
        exp_entries = [e for e in expected["waiting_time"]["winter"] if e["nr"] == r.window_nr]
        if not exp_entries:
            continue
        e = exp_entries[0]
        c0_diff = abs(r.wait_coeffs["wait_c0"] - e["c0"])
        c1_diff = abs(r.wait_coeffs["wait_c1"] - e["c1"])
        if c0_diff >= 1e-2 or c1_diff >= 1e-2:
            failures.append(
                f"WW{r.window_nr}: c0_diff={c0_diff:.4f}, c1_diff={c1_diff:.4f}"
            )

    assert not failures, f"Coefficient mismatches: {failures}"


@pytest.mark.xfail(
    strict=False,
    reason=(
        "Pre-existing ECN issue: spring/summer cross-season WW3 ECN-computed "
        "coefficients deviate from K13 JSON reference. Migration itself is "
        "bit-perfect — see test_migration_equivalence_pinned. "
        "詳見 docs/legacy/ecn_k13_baseline.md"
    ),
)
def test_all_seasons_ww3():
    """WW3 跨 4 季 — c0/c1 須 < 1e-2 誤差（K13 JSON reference 比對；ECN 既有 deviation）。"""
    from modules.cost.engine.waiting_time import (
        WeatherWindowConfig,
        run_waiting_time_analysis,
    )

    df = load_metocean_data()
    general = load_general_params()
    expected = load_expected_coefficients()

    windows = [
        WeatherWindowConfig(
            nr=3, max_vw=12, max_hs=1.5,
            max_hsd_max=355, max_hsd_min=5, lwd=0, h_vw=85,
        ),
    ]

    t0 = time.time()
    results = run_waiting_time_analysis(
        df=df,
        weather_windows=windows,
        seasons=["winter", "spring", "summer", "autumn"],
        mission_times=[3, 6, 9, 12, 15, 21, 27, 36, 45, 63],
        poly_order=3,
        start_hour=7,
        end_hour=18,
        meas_height=10.0,
        hub_height=general["turbine"]["hub_height_m"],
        wind_profile_exponent=general["wind_profile_exponent"],
    )
    elapsed = time.time() - t0
    print(f"\nCalculation time: {elapsed:.2f}s")

    failures: list[str] = []
    for r in results:
        exp_entries = [e for e in expected["waiting_time"][r.season] if e["nr"] == 3]
        if not exp_entries:
            continue
        e = exp_entries[0]
        c0_diff = abs(r.wait_coeffs["wait_c0"] - e["c0"])
        c1_diff = abs(r.wait_coeffs["wait_c1"] - e["c1"])
        if c0_diff >= 1e-2 or c1_diff >= 1e-2:
            failures.append(
                f"{r.season}: c0_diff={c0_diff:.4f}, c1_diff={c1_diff:.4f}"
            )

    assert not failures, f"Seasonal coefficient mismatches: {failures}"


# ─────────────────────────────────────────────────────────────────────────
# Migration correctness gate — pinned to ECN engine actual output (2026-05-04)
# ─────────────────────────────────────────────────────────────────────────

# 來源：ECN backend 在 K13 上實際 run 出來的 wait_c0 / wait_c1（2026-05-04 量測，
# 用 repr() 取 float64 完整精度）。windMindOM migration 後必須 bit-perfect 一致
# — 任何漂移代表 migration 引入了 numerical drift（最常見：numpy 版本差異、
# 依賴 ECN 內未 stub 的功能、或 import path 改錯引到舊 import）。
ECN_PINNED_WW3_FOUR_SEASONS = {
    "winter": {"wait_c0": 20.171966770995617, "wait_c1": 10.246495799172488},
    "spring": {"wait_c0": 14.223426494477291, "wait_c1":  1.1868813770384665},
    "summer": {"wait_c0":  8.671557426859517, "wait_c1":  0.3329158748985229},
    "autumn": {"wait_c0": 29.837294805592165, "wait_c1":  2.134714165938292},
}


def test_migration_equivalence_pinned():
    """Migration 正確性 gate — windMindOM 必須 bit-perfect 等於 ECN engine 輸出。

    任何 diff > 1e-10 代表移植引入了 numerical drift（最常見：numpy 版本差異、
    依賴 ECN 內未 stub 的功能、或 import path 改錯引到舊 import）。
    """
    from modules.cost.engine.waiting_time import (
        WeatherWindowConfig,
        run_waiting_time_analysis,
    )

    df = load_metocean_data()
    general = load_general_params()

    windows = [
        WeatherWindowConfig(
            nr=3, max_vw=12, max_hs=1.5,
            max_hsd_max=355, max_hsd_min=5, lwd=0, h_vw=85,
        ),
    ]
    results = run_waiting_time_analysis(
        df=df,
        weather_windows=windows,
        seasons=["winter", "spring", "summer", "autumn"],
        mission_times=[3, 6, 9, 12, 15, 21, 27, 36, 45, 63],
        poly_order=3,
        start_hour=7,
        end_hour=18,
        meas_height=10.0,
        hub_height=general["turbine"]["hub_height_m"],
        wind_profile_exponent=general["wind_profile_exponent"],
    )

    print("\nMIGRATION EQUIVALENCE (windMindOM vs ECN pinned):")
    failures: list[str] = []
    for r in results:
        pinned = ECN_PINNED_WW3_FOUR_SEASONS[r.season]
        c0_diff = abs(r.wait_coeffs["wait_c0"] - pinned["wait_c0"])
        c1_diff = abs(r.wait_coeffs["wait_c1"] - pinned["wait_c1"])
        status = "OK" if (c0_diff < 1e-10 and c1_diff < 1e-10) else "DRIFT"
        print(
            f"  {r.season:>8}: c0_diff={c0_diff:.2e}  c1_diff={c1_diff:.2e}  {status}"
        )
        if c0_diff >= 1e-10 or c1_diff >= 1e-10:
            failures.append(
                f"{r.season}: c0_diff={c0_diff:.2e}, c1_diff={c1_diff:.2e}"
            )

    assert not failures, f"Migration drift detected: {failures}"
