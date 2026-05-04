"""Season and workday filtering logic.

Implements the ECN O&M Tool's season definition:
    Season 1 (winter): Dec, Jan, Feb
    Season 2 (spring): Mar, Apr, May
    Season 3 (summer): Jun, Jul, Aug
    Season 4 (autumn): Sep, Oct, Nov
    Season 5 (year): All months
"""

import numpy as np
import pandas as pd


# Season name -> ECN season number
SEASON_NR = {
    "winter": 1,
    "spring": 2,
    "summer": 3,
    "autumn": 4,
    "year": 5,
}

# Season definitions: name -> list of months
SEASON_MONTHS = {
    "winter": [12, 1, 2],
    "spring": [3, 4, 5],
    "summer": [6, 7, 8],
    "autumn": [9, 10, 11],
    "year": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
}


def ecn_season_nr(month: int) -> int:
    """Map month number to ECN season number.

    Replicates the Excel formula: =1+TRUNC(IF(F=12,0,F)/3)

    Args:
        month: Month number (1-12).

    Returns:
        Season number (1=winter, 2=spring, 3=summer, 4=autumn).
    """
    m = 0 if month == 12 else month
    return 1 + int(m / 3)


def get_season_mask(months: np.ndarray, season: str) -> np.ndarray:
    """Return boolean mask for time steps in the given season.

    Args:
        months: Array of month numbers (1-12).
        season: One of 'winter', 'spring', 'summer', 'autumn', 'year'.

    Returns:
        Boolean array: True where month belongs to the season.
    """
    season = season.lower()
    if season == "year":
        return np.ones(len(months), dtype=bool)

    if season not in SEASON_NR:
        raise ValueError(f"Unknown season: {season}. Valid: {list(SEASON_NR.keys())}")

    target_nr = SEASON_NR[season]
    season_nrs = np.array([ecn_season_nr(int(m)) for m in months])
    return season_nrs == target_nr


def filter_by_season_mask(
    timestamps: np.ndarray | pd.Series,
    season: str,
) -> np.ndarray:
    """Return a boolean mask for timestamps belonging to the given season.

    Args:
        timestamps: Array of datetime timestamps.
        season: One of 'winter', 'spring', 'summer', 'autumn', 'year'.

    Returns:
        Boolean numpy array.
    """
    if isinstance(timestamps, pd.Series):
        month_values = timestamps.dt.month.values
    else:
        ts_series = pd.DatetimeIndex(timestamps)
        month_values = ts_series.month.values

    return get_season_mask(month_values, season)


def apply_workday_constraint(
    timestamps: np.ndarray | pd.Series,
    lwd: int,
    start_hour: int = 7,
    end_hour: int = 18,
) -> np.ndarray:
    """Return a boolean mask for valid mission start times.

    Note: In the ECN tool, the workday constraint is built into the
    interval identification (column O logic), not applied separately.
    This function is kept for backward compatibility.

    Args:
        timestamps: Array of datetime timestamps.
        lwd: Long working day flag. 1=24h, 0=normal hours.
        start_hour: Start of working hours (default 7).
        end_hour: End of working hours (default 18, exclusive).

    Returns:
        Boolean numpy array.
    """
    if lwd == 1:
        return np.ones(len(timestamps), dtype=bool)

    if isinstance(timestamps, pd.Series):
        hour_values = timestamps.dt.hour.values
    else:
        ts_series = pd.DatetimeIndex(timestamps)
        hour_values = ts_series.hour.values

    return (hour_values >= start_hour) & (hour_values < end_hour)


def filter_by_season(
    metocean_df: pd.DataFrame,
    month_start: int,
    month_end: int,
    workday_def=None,
) -> pd.DataFrame:
    """Filter metocean data by season months and workday hours.

    Args:
        metocean_df: DataFrame with a 'timestamp' column.
        month_start: Starting month of the season (1-12).
        month_end: Ending month of the season (1-12).
        workday_def: Optional WorkDayDefinition model.

    Returns:
        Filtered DataFrame.
    """
    df = metocean_df.copy()
    months = df["timestamp"].dt.month

    if month_start <= month_end:
        mask = (months >= month_start) & (months <= month_end)
    else:
        mask = (months >= month_start) | (months <= month_end)

    df = df[mask]

    if workday_def is not None:
        hours = df["timestamp"].dt.hour
        df = df[(hours >= workday_def.start_hour) & (hours < workday_def.end_hour)]

    return df.reset_index(drop=True)
