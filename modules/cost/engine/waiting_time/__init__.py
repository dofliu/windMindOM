"""Waiting time calculation engine.

This module implements the ECN O&M Tool's WaitingTime algorithm, computing
mean waiting times due to bad weather as a function of mission time, fitted
as polynomial curves for each weather window and season combination.

Key differences from a naive implementation:
1. Wind speed is extrapolated to hub height before threshold comparison
2. Accessible intervals can only START during working hours but continue
   through non-working hours (ECN column O logic)
3. Working hours default to 7:00-18:00 (hour >= 7 AND hour < 18)
4. Mission times are specific values, not uniform spacing
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from modules.cost.engine.waiting_time.data_processor import (
    process_metocean_data,
    preprocess_metocean_data,
    ProcessedData,
)
from modules.cost.engine.waiting_time.weather_windows import (
    evaluate_weather_windows,
    identify_accessible_mask,
    check_weather_accessible,
    build_ecn_intervals,
    build_workday_mask,
    AccessibleInterval,
)
from modules.cost.engine.waiting_time.season_filter import (
    filter_by_season,
    filter_by_season_mask,
    apply_workday_constraint,
    get_season_mask,
    ecn_season_nr,
    SEASON_MONTHS,
    SEASON_NR,
)
from modules.cost.engine.waiting_time.waiting_calculator import (
    calculate_waiting_times,
    calc_twait_mission,
    WaitingTimeStats,
)
from modules.cost.engine.waiting_time.polynomial_fitter import (
    fit_polynomials,
    fit_polynomial,
)
from modules.cost.engine.waiting_time.power_calculator import (
    calculate_power_curves,
    interpolate_power,
)


__all__ = [
    "preprocess_metocean_data",
    "process_metocean_data",
    "ProcessedData",
    "evaluate_weather_windows",
    "identify_accessible_mask",
    "build_ecn_intervals",
    "build_workday_mask",
    "AccessibleInterval",
    "filter_by_season",
    "filter_by_season_mask",
    "apply_workday_constraint",
    "get_season_mask",
    "calculate_waiting_times",
    "calc_twait_mission",
    "WaitingTimeStats",
    "fit_polynomials",
    "fit_polynomial",
    "calculate_power_curves",
    "interpolate_power",
    "run_waiting_time_analysis",
    "WeatherWindowConfig",
    "WaitingTimeResult",
]


# Default ECN mission times (from Definition sheet C13:C22)
DEFAULT_MISSION_TIMES = [3, 6, 9, 12, 15, 21, 27, 36, 45, 63]


@dataclass
class WeatherWindowConfig:
    """Configuration for a single weather window."""

    nr: int
    max_vw: float
    max_hs: float
    max_hsd_max: float = 360.0
    max_hsd_min: float = 0.0
    lwd: int = 0  # 0=normal workday, 1=long workday (24h)
    h_vw: float = 85.0  # height for wind speed comparison


@dataclass
class WaitingTimeResult:
    """Result for one weather window + season combination."""

    window_nr: int
    season: str
    raw_points: list[dict]
    wait_coeffs: dict
    wait_power_coeffs: dict
    mission_power_coeffs: dict


def run_waiting_time_analysis(
    df: pd.DataFrame,
    weather_windows: list[WeatherWindowConfig],
    seasons: list[str] | None = None,
    pv_curve: list[tuple[float, float]] | None = None,
    v_in: float = 4.0,
    v_out: float = 25.0,
    mission_times: list[float] | None = None,
    poly_order: int = 3,
    start_hour: int = 7,
    end_hour: int = 18,
    meas_height: float = 10.0,
    hub_height: float = 85.0,
    wind_profile_exponent: float = 0.1,
) -> list[WaitingTimeResult]:
    """Run the complete waiting time analysis pipeline.

    Replicates the ECN O&M Tool's WaitingTime calculation:
    1. Process met-ocean data
    2. Extrapolate wind speed to hub height
    3. For each weather window:
       a. Compute weather accessibility mask
       b. Build workday-gated accessible intervals
       c. For each season:
          - Get season-filtered cumulative times
          - For each mission time:
            - Calculate mean waiting time using interval-based algorithm
          - Fit polynomials
    4. Return all results

    Args:
        df: Raw metocean DataFrame with columns
            [timestamp, vw, hs, hsd_max, hsd_min].
        weather_windows: List of weather window configurations.
        seasons: List of seasons to compute.
        pv_curve: Power-velocity curve as list of (v, p) tuples.
        v_in: Cut-in wind speed.
        v_out: Cut-out wind speed.
        mission_times: List of mission durations in hours.
        poly_order: Polynomial degree for fitting.
        start_hour: Normal working day start hour (default 7).
        end_hour: Normal working day end hour (default 18, exclusive).
        meas_height: Wind speed measurement height in meters.
        hub_height: Turbine hub height in meters.
        wind_profile_exponent: Wind profile power law exponent (alpha).

    Returns:
        List of WaitingTimeResult for each window/season combination.
    """
    if seasons is None:
        seasons = ["winter", "spring", "summer", "autumn"]
    if mission_times is None:
        mission_times = DEFAULT_MISSION_TIMES

    # Step 1: Process data
    processed = process_metocean_data(df)
    clean_df = processed.df
    time_step = processed.time_step_hours
    n = len(clean_df)

    # Wind speed extrapolation factor
    vw_factor = (hub_height / meas_height) ** wind_profile_exponent
    vw_hub = clean_df["vw"].values * vw_factor

    # Pre-compute power values if PV curve provided
    power_values = None
    if pv_curve is not None:
        # Power curve uses hub-height wind speed
        power_values = interpolate_power(vw_hub, pv_curve, v_in, v_out)

    # Pre-compute season masks and cumulative times
    timestamps = pd.DatetimeIndex(clean_df["timestamp"])
    months = timestamps.month.values
    hours = timestamps.hour.values
    cumtime = np.arange(n, dtype=np.float64) * time_step

    season_cumtimes = {}
    for season in seasons:
        mask = get_season_mask(months, season)
        season_cumtimes[season] = cumtime[mask]

    # Weather data arrays
    hs = clean_df["hs"].values
    hsd_max = clean_df["hsd_max"].values
    hsd_min = clean_df["hsd_min"].values

    results = []

    for ww in weather_windows:
        # Step 2a: Weather accessibility check (at hub height)
        weather_ok = check_weather_accessible(
            vw_hub, hs, hsd_max, hsd_min,
            ww.max_vw, ww.max_hs, ww.max_hsd_max, ww.max_hsd_min,
        )

        # Step 2b: Build workday mask and accessible intervals
        workday_mask = build_workday_mask(hours, ww.lwd, start_hour, end_hour)
        intervals = build_ecn_intervals(weather_ok, workday_mask, time_step)

        for season in seasons:
            s_cumtimes = season_cumtimes[season]

            raw_points = []
            for mt in mission_times:
                stats = calc_twait_mission(
                    intervals=intervals,
                    season_cumtimes=s_cumtimes,
                    mission_time_hours=float(mt),
                    time_step_hours=time_step,
                    power_values=power_values,
                )
                raw_points.append({
                    "mission_time": stats.mission_time,
                    "avg_waiting_time": stats.mean_waiting_time,
                    "std_waiting_time": stats.std_waiting_time,
                    "avg_waiting_power": stats.mean_waiting_power,
                    "avg_mission_power": stats.mean_mission_power,
                    "count": stats.sample_count,
                })

            # Step 2c: Fit polynomials
            wait_coeffs = fit_polynomials(raw_points, poly_order)

            # Fit waiting power and mission power polynomials
            valid_points = [p for p in raw_points if p["count"] > 0]
            if len(valid_points) >= poly_order + 1:
                x = np.array([p["mission_time"] for p in valid_points])
                y_wp = np.array([p["avg_waiting_power"] for p in valid_points])
                y_mp = np.array([p["avg_mission_power"] for p in valid_points])

                wp_c, wp_r2 = fit_polynomial(x, y_wp, poly_order)
                mp_c, mp_r2 = fit_polynomial(x, y_mp, poly_order)

                wait_power_coeffs = {f"c{i}": wp_c[i] for i in range(len(wp_c))}
                wait_power_coeffs["r_squared"] = wp_r2
                mission_power_coeffs = {f"c{i}": mp_c[i] for i in range(len(mp_c))}
                mission_power_coeffs["r_squared"] = mp_r2
            else:
                wait_power_coeffs = {f"c{i}": 0.0 for i in range(poly_order + 1)}
                wait_power_coeffs["r_squared"] = 0.0
                mission_power_coeffs = {f"c{i}": 0.0 for i in range(poly_order + 1)}
                mission_power_coeffs["r_squared"] = 0.0

            results.append(WaitingTimeResult(
                window_nr=ww.nr,
                season=season,
                raw_points=raw_points,
                wait_coeffs=wait_coeffs,
                wait_power_coeffs=wait_power_coeffs,
                mission_power_coeffs=mission_power_coeffs,
            ))

    return results
