"""Polynomial curve fitting for waiting time results."""

import numpy as np


def fit_polynomial(
    x: np.ndarray,
    y: np.ndarray,
    degree: int = 3,
) -> tuple[list[float], float]:
    """Fit a polynomial and return coefficients in [c0, c1, c2, ...] order.

    Args:
        x: Independent variable values (e.g., mission times).
        y: Dependent variable values (e.g., mean waiting times).
        degree: Polynomial degree.

    Returns:
        Tuple of (coefficients [c0, c1, ..., cn], r_squared).
        c0 is constant, c1 is linear, etc.
    """
    if len(x) < degree + 1:
        # Not enough points for the requested degree
        degree = max(len(x) - 1, 0)

    # numpy.polyfit returns [cn, ..., c1, c0] (highest to lowest)
    poly_coeffs = np.polyfit(x, y, degree)

    # Reverse to get [c0, c1, c2, ..., cn]
    coeffs = list(reversed(poly_coeffs))

    # Pad with zeros if degree was reduced
    while len(coeffs) < degree + 1:
        coeffs.append(0.0)

    # Compute R-squared
    y_pred = np.polyval(poly_coeffs, x)
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0

    return coeffs, r_squared


def fit_polynomials(
    raw_points: list[dict],
    poly_order: int = 3,
) -> dict:
    """Fit a polynomial to the waiting time vs. mission duration data.

    Args:
        raw_points: List of dicts with 'mission_time' and 'avg_waiting_time'.
        poly_order: Order of the polynomial to fit (default 3).

    Returns:
        Dict with wait_c0..c3, r_squared.
    """
    x = np.array([p["mission_time"] for p in raw_points])
    y = np.array([p["avg_waiting_time"] for p in raw_points])

    coeffs, r_squared = fit_polynomial(x, y, poly_order)

    result = {}
    for i in range(poly_order + 1):
        result[f"wait_c{i}"] = coeffs[i] if i < len(coeffs) else 0.0
    result["r_squared"] = r_squared

    return result
