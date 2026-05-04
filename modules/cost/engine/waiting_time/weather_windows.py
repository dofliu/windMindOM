"""Weather window evaluation logic.

Implements the ECN O&M Tool's weather window accessibility checks,
including wind speed extrapolation to hub height and workday-gated
accessible interval identification.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class AccessibleInterval:
    """A contiguous accessible weather window.

    In the ECN tool, an accessible interval can only START during working
    hours but continues through non-working hours as long as weather
    conditions remain OK.
    """

    start_time_hours: float  # cumulative hours from data start
    end_time_hours: float
    duration_hours: float


def check_weather_accessible(
    vw_hub: np.ndarray,
    hs: np.ndarray,
    hsd_max: np.ndarray,
    hsd_min: np.ndarray,
    max_vw: float,
    max_hs: float,
    max_hsd_max: float,
    max_hsd_min: float,
) -> np.ndarray:
    """Check weather conditions at each time step.

    Args:
        vw_hub: Wind speed at hub height (m/s).
        hs: Significant wave height (m).
        hsd_max: Wave direction max (degrees).
        hsd_min: Wave direction min (degrees).
        max_vw: Maximum allowed wind speed.
        max_hs: Maximum allowed wave height.
        max_hsd_max: Maximum wave direction upper bound.
        max_hsd_min: Minimum wave direction lower bound.

    Returns:
        Integer array: 1 where all conditions met, 0 otherwise.
    """
    K = (vw_hub <= max_vw).astype(np.int8)
    L = (hs <= max_hs).astype(np.int8)

    if max_hsd_max >= 360 and max_hsd_min <= 0:
        M = np.ones(len(vw_hub), dtype=np.int8)
        N = np.ones(len(vw_hub), dtype=np.int8)
    else:
        M = (hsd_max <= max_hsd_max).astype(np.int8)
        N = (hsd_min >= max_hsd_min).astype(np.int8)

    return np.minimum(np.minimum(K, L), np.minimum(M, N))


def build_workday_mask(
    hours: np.ndarray,
    lwd: int,
    start_hour: int = 7,
    end_hour: int = 18,
) -> np.ndarray:
    """Create workday mask for mission start validity.

    When lwd=1 (long working day), all hours are valid.
    When lwd=0, only hours >= start_hour and < end_hour are valid.

    Args:
        hours: Hour-of-day values (0-23) for each time step.
        lwd: Long working day flag (1=24h, 0=normal).
        start_hour: Normal work start hour (default 7).
        end_hour: Normal work end hour (default 18).

    Returns:
        Integer array: 1 for valid start times, 0 otherwise.
    """
    if lwd == 1:
        return np.ones(len(hours), dtype=np.int8)
    return ((hours >= start_hour) & (hours < end_hour)).astype(np.int8)


def build_ecn_intervals(
    weather_ok: np.ndarray,
    workday_mask: np.ndarray,
    time_step_hours: float,
) -> list[AccessibleInterval]:
    """Build accessible intervals using the ECN column O logic.

    An accessible interval can only START during working hours
    (workday_mask=1) but continues through non-working hours as long
    as weather conditions remain OK.

    This replicates the ECN Excel formula:
        O[i] = IF(U[i]=1,
                   IF(weather_ok[i]=0, 0, 1+O[i-1]),
                   IF(O[i-1]=0, 0,
                      IF(weather_ok[i]=0, 0, 1+O[i-1])))

    Args:
        weather_ok: Integer array (0/1) of weather accessibility.
        workday_mask: Integer array (0/1) of valid start times.
        time_step_hours: Duration of each time step in hours.

    Returns:
        List of AccessibleInterval objects.
    """
    n = len(weather_ok)
    O = np.zeros(n, dtype=np.int64)

    for i in range(n):
        if workday_mask[i]:
            O[i] = (1 + O[i - 1]) if (weather_ok[i] and i > 0) else (1 if weather_ok[i] else 0)
        else:
            if i > 0 and O[i - 1] > 0 and weather_ok[i]:
                O[i] = 1 + O[i - 1]
            else:
                O[i] = 0

    # Identify interval endpoints: where O drops to 0 or at end of data
    intervals = []
    for i in range(n - 1):
        if O[i] > 0 and O[i + 1] == 0:
            dur = O[i] * time_step_hours
            end_t = (i + 1) * time_step_hours
            start_t = end_t - dur
            intervals.append(AccessibleInterval(start_t, end_t, dur))
    if O[-1] > 0:
        dur = O[-1] * time_step_hours
        end_t = n * time_step_hours
        start_t = end_t - dur
        intervals.append(AccessibleInterval(start_t, end_t, dur))

    return intervals


def identify_accessible_mask(
    df: pd.DataFrame,
    max_vw: float,
    max_hs: float,
    max_hsd_max: float,
    max_hsd_min: float,
    vw_extrapolation_factor: float = 1.0,
) -> np.ndarray:
    """Create a boolean mask of accessible time steps (simple check).

    This is a simpler version that does NOT incorporate workday gating.
    For the full ECN algorithm, use build_ecn_intervals.

    Args:
        df: Metocean DataFrame with columns vw, hs, hsd_max, hsd_min.
        max_vw: Maximum wind speed threshold.
        max_hs: Maximum significant wave height threshold.
        max_hsd_max: Maximum wave direction upper bound.
        max_hsd_min: Minimum wave direction lower bound.
        vw_extrapolation_factor: Wind speed extrapolation factor.

    Returns:
        Boolean numpy array.
    """
    vw_hub = df["vw"].values * vw_extrapolation_factor
    hs = df["hs"].values
    hsd_max = df["hsd_max"].values
    hsd_min = df["hsd_min"].values

    weather_ok = check_weather_accessible(
        vw_hub, hs, hsd_max, hsd_min,
        max_vw, max_hs, max_hsd_max, max_hsd_min,
    )
    return weather_ok.astype(bool)


def evaluate_weather_windows(
    metocean_df: pd.DataFrame,
    window,
) -> pd.DataFrame:
    """Evaluate which time steps are accessible for a given weather window.

    Args:
        metocean_df: Preprocessed metocean DataFrame.
        window: WeatherWindow model with threshold values.

    Returns:
        DataFrame with an additional boolean column 'accessible'.
    """
    result = metocean_df.copy()
    mask = identify_accessible_mask(
        metocean_df,
        max_vw=window.max_vw,
        max_hs=window.max_hs,
        max_hsd_max=window.max_hsd_max if window.max_hsd_max is not None else 360.0,
        max_hsd_min=window.max_hsd_min if window.max_hsd_min is not None else 0.0,
    )
    result["accessible"] = mask
    return result
