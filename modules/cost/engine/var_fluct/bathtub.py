"""Bathtub curve — failure rate multiplier over wind farm lifetime.

The classic bathtub curve has three phases:
  1. Early life (infant mortality): higher failure rate, decreasing over time
  2. Mid-life (useful life): constant baseline failure rate (multiplier = 1.0)
  3. Late life (wear-out): increasing failure rate due to aging

We model this using a piecewise function based on Weibull hazard rate shape:
  - Early phase: multiplier decreases from early_peak to 1.0
  - Mid phase: multiplier = 1.0
  - Late phase: multiplier increases from 1.0 to late_peak
"""

import math
from dataclasses import dataclass


@dataclass
class BathtubParams:
    """Parameters for the bathtub curve."""

    beta_early: float = 0.7   # Weibull β < 1 for decreasing hazard
    beta_late: float = 1.5    # Weibull β > 1 for increasing hazard
    early_life_years: int = 2  # Duration of infant mortality phase
    late_life_start: int = 15  # Year when aging begins
    early_peak: float = 1.5   # Peak multiplier at year 1
    late_peak: float = 2.0    # Peak multiplier at final year
    lifetime: int = 20


def bathtub_multiplier(year: int, params: BathtubParams) -> float:
    """Compute the failure rate multiplier for a given year.

    Args:
        year: Operating year (1-based, 1 = first year).
        params: Bathtub curve parameters.

    Returns:
        Multiplier >= 1.0. Baseline mid-life = 1.0.
    """
    if year < 1:
        return 1.0

    # Early life phase: year 1 .. early_life_years
    if params.early_life_years > 0 and year <= params.early_life_years:
        # Linear decay from early_peak to 1.0 over the early life period
        t = (year - 1) / max(1, params.early_life_years)  # 0 at year 1, ~1 at end
        # Use Weibull-inspired shape: multiplier = 1 + (peak-1) * (1-t)^(1/beta)
        shape = 1.0 / params.beta_early if params.beta_early > 0 else 1.0
        multiplier = 1.0 + (params.early_peak - 1.0) * ((1.0 - t) ** shape)
        return max(1.0, multiplier)

    # Late life phase: late_life_start .. lifetime
    if year >= params.late_life_start and params.lifetime > params.late_life_start:
        # Progress through late life: 0 at start, 1 at final year
        late_duration = params.lifetime - params.late_life_start + 1
        t = (year - params.late_life_start) / max(1, late_duration - 1)
        t = min(1.0, t)
        # Weibull-inspired shape: multiplier = 1 + (peak-1) * t^beta
        multiplier = 1.0 + (params.late_peak - 1.0) * (t ** params.beta_late)
        return max(1.0, multiplier)

    # Mid-life: constant baseline
    return 1.0


def compute_bathtub_curve(params: BathtubParams) -> list[dict]:
    """Compute the full bathtub curve for visualization.

    Returns:
        List of {year, multiplier} for each year in the lifetime.
    """
    return [
        {"year": y, "multiplier": round(bathtub_multiplier(y, params), 4)}
        for y in range(1, params.lifetime + 1)
    ]
