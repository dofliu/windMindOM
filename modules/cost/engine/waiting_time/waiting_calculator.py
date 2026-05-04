"""Core waiting time calculation logic.

Implements the ECN O&M Tool's CalcTwaitMission algorithm for computing
mean waiting times due to bad weather as a function of mission time.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from modules.cost.engine.waiting_time.weather_windows import AccessibleInterval


@dataclass
class WaitingTimeStats:
    """Results for a single mission time calculation."""

    mission_time: float
    mean_waiting_time: float
    std_waiting_time: float
    mean_waiting_power: float
    mean_mission_power: float
    sample_count: int


def calc_twait_mission(
    intervals: list[AccessibleInterval],
    season_cumtimes: np.ndarray,
    mission_time_hours: float,
    time_step_hours: float,
    power_values: np.ndarray | None = None,
) -> WaitingTimeStats:
    """Calculate mean waiting time for a single mission duration.

    This replicates the ECN VBA CalcTwaitMission function:
    - Iterate through accessible intervals in order
    - For each interval with sufficient duration, process all season
      failures up to the end of the interval minus mission time
    - Waiting time = interval_start - failure_time (or 0 if failure
      is within the interval)
    - Average over ALL season time steps

    Args:
        intervals: Sorted list of accessible intervals (with workday gating).
        season_cumtimes: Cumulative time (hours from data start) for each
            time step in the target season.
        mission_time_hours: Required mission duration in hours.
        time_step_hours: Time step in hours (L_Block).
        power_values: Optional array of power values per time step in the
            full dataset (indexed by cumtime / time_step_hours).

    Returns:
        WaitingTimeStats with mean/std waiting time and power values.
    """
    T_Mission = max(mission_time_hours, time_step_hours)
    L_Block = time_step_hours
    N_BlockFail = len(season_cumtimes)

    if N_BlockFail == 0:
        return WaitingTimeStats(
            mission_time=mission_time_hours,
            mean_waiting_time=0.0,
            std_waiting_time=0.0,
            mean_waiting_power=0.0,
            mean_mission_power=0.0,
            sample_count=0,
        )

    T_WaitTot = 0.0
    P_WaitTot = 0.0
    P_MissTot = 0.0
    i_bf = 0  # current failure index
    I_BlockWait = 0  # count of blocks with non-zero wait
    T_Fail = season_cumtimes[0]

    waiting_times = []

    for iv in intervals:
        start_t = iv.start_time_hours
        end_t = iv.end_time_hours
        dur = iv.duration_hours

        # Check if this interval is suitable and failure hasn't passed it
        if T_Mission <= dur and T_Fail < end_t + L_Block / 2 - T_Mission:
            T_StartInt = max(start_t, T_Fail)
            T_EndInt = end_t

            # Process all failures up to the point where mission fits
            while T_Fail <= T_EndInt - T_Mission and i_bf < N_BlockFail:
                if T_Fail < T_StartInt:
                    T_Wait = T_StartInt - T_Fail
                    T_WaitTot += T_Wait
                    I_BlockWait += 1

                    # Compute power during waiting and mission periods
                    if power_values is not None:
                        idx_fail = int(round(T_Fail / L_Block))
                        idx_wait_end = int(round((T_Fail + T_Wait) / L_Block))
                        idx_miss_end = int(round((T_Fail + T_Wait + T_Mission) / L_Block))
                        max_idx = len(power_values)

                        if idx_fail < idx_wait_end and idx_wait_end <= max_idx:
                            P_Wait = np.mean(power_values[idx_fail:idx_wait_end])
                        else:
                            P_Wait = 0.0
                        if idx_wait_end < idx_miss_end and idx_miss_end <= max_idx:
                            P_Miss = np.mean(power_values[idx_wait_end:idx_miss_end])
                        else:
                            P_Miss = 0.0

                        P_WaitTot += P_Wait
                        P_MissTot += P_Miss
                else:
                    # Waiting time is zero - failure is within the interval
                    T_Wait = 0.0

                    if power_values is not None:
                        idx_fail = int(round(T_Fail / L_Block))
                        idx_miss_end = int(round((T_Fail + T_Mission) / L_Block))
                        max_idx = len(power_values)
                        if idx_fail < idx_miss_end and idx_miss_end <= max_idx:
                            P_Miss = np.mean(power_values[idx_fail:idx_miss_end])
                        else:
                            P_Miss = 0.0
                        P_MissTot += P_Miss

                waiting_times.append(T_Wait)
                i_bf += 1
                if i_bf < N_BlockFail:
                    T_Fail = season_cumtimes[i_bf]

    total_processed = i_bf
    if total_processed == 0:
        return WaitingTimeStats(
            mission_time=mission_time_hours,
            mean_waiting_time=0.0,
            std_waiting_time=0.0,
            mean_waiting_power=0.0,
            mean_mission_power=0.0,
            sample_count=0,
        )

    # ECN divides by total number of processed failures (including zero waits)
    T_WaitAvg = T_WaitTot / total_processed
    P_WaitAvg = P_WaitTot / I_BlockWait if I_BlockWait > 0 else 0.0
    P_MissAvg = P_MissTot / total_processed

    wt_array = np.array(waiting_times)
    std_wt = float(np.std(wt_array, ddof=0)) if len(wt_array) > 0 else 0.0

    return WaitingTimeStats(
        mission_time=mission_time_hours,
        mean_waiting_time=T_WaitAvg,
        std_waiting_time=std_wt,
        mean_waiting_power=P_WaitAvg,
        mean_mission_power=P_MissAvg,
        sample_count=total_processed,
    )


def calculate_waiting_times(
    accessible_df: pd.DataFrame,
    mission_durations: list[float],
    time_step_hours: float,
) -> list[dict]:
    """Calculate average waiting times for each mission duration.

    Simplified interface using a pre-computed accessible DataFrame.

    Args:
        accessible_df: DataFrame with 'timestamp' and 'accessible' columns.
        mission_durations: List of mission durations in hours.
        time_step_hours: Time step in hours.

    Returns:
        List of dicts with mission_time, avg_waiting_time, count.
    """
    from modules.cost.engine.waiting_time.weather_windows import build_ecn_intervals

    accessible = accessible_df["accessible"].values.astype(np.int8)
    workday = np.ones(len(accessible_df), dtype=np.int8)
    intervals = build_ecn_intervals(accessible, workday, time_step_hours)
    cumtimes = np.arange(len(accessible_df)) * time_step_hours

    results = []
    for mt in mission_durations:
        stats = calc_twait_mission(intervals, cumtimes, mt, time_step_hours)
        results.append({
            "mission_time": mt,
            "avg_waiting_time": stats.mean_waiting_time,
            "count": stats.sample_count,
        })
    return results
