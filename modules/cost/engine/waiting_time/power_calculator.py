"""Power curve interpolation for waiting time and mission time calculations."""

import numpy as np


def interpolate_power(
    wind_speeds: np.ndarray,
    pv_curve: list[tuple[float, float]],
    v_in: float = 4.0,
    v_out: float = 25.0,
) -> np.ndarray:
    """Interpolate turbine power output for given wind speeds using a PV curve.

    Args:
        wind_speeds: Array of wind speed values (m/s).
        pv_curve: List of (wind_speed, power_kw) tuples defining the power curve.
        v_in: Cut-in wind speed (below this, power = 0).
        v_out: Cut-out wind speed (above this, power = 0).

    Returns:
        Array of power values (kW) for each wind speed.
    """
    # Sort PV curve by wind speed
    pv_sorted = sorted(pv_curve, key=lambda x: x[0])
    curve_v = np.array([p[0] for p in pv_sorted])
    curve_p = np.array([p[1] for p in pv_sorted])

    # Interpolate
    power = np.interp(wind_speeds, curve_v, curve_p, left=0.0, right=0.0)

    # Apply cut-in and cut-out constraints
    power = np.where(wind_speeds < v_in, 0.0, power)
    power = np.where(wind_speeds > v_out, 0.0, power)

    return power


def calculate_power_curves(
    poly_coeffs: dict,
    raw_points: list[dict],
    poly_order: int = 3,
) -> dict:
    """Calculate wait-power and mission-power polynomial coefficients.

    Args:
        poly_coeffs: Dict of waiting time polynomial coefficients.
        raw_points: List of raw data points with mission_time, avg_waiting_time,
                    avg_waiting_power, avg_mission_power.
        poly_order: Order of polynomial to fit.

    Returns:
        Dict with wait_power and mission_power polynomial coefficients.
    """
    from modules.cost.engine.waiting_time.polynomial_fitter import fit_polynomial

    mission_times = np.array([p["mission_time"] for p in raw_points])
    wait_powers = np.array([p.get("avg_waiting_power", 0.0) for p in raw_points])
    mission_powers = np.array([p.get("avg_mission_power", 0.0) for p in raw_points])

    # Fit waiting power polynomial
    wp_coeffs, wp_r2 = fit_polynomial(mission_times, wait_powers, poly_order)

    # Fit mission power polynomial
    mp_coeffs, mp_r2 = fit_polynomial(mission_times, mission_powers, poly_order)

    result = {}
    for i in range(poly_order + 1):
        result[f"wait_power_c{i}"] = wp_coeffs[i] if i < len(wp_coeffs) else 0.0
        result[f"mission_power_c{i}"] = mp_coeffs[i] if i < len(mp_coeffs) else 0.0

    result["r_squared_wait_power"] = wp_r2
    result["r_squared_mission_power"] = mp_r2

    return result
