"""Fixed yearly cost calculation.

Simple distribution of fixed annual costs across seasons.
"""

from modules.cost.engine.cost_cal.data_classes import (
    SEASONS,
    FixedCostParams,
    SeasonResult,
)


def calculate_fixed_costs(
    fixed_costs: list[FixedCostParams],
) -> dict[str, SeasonResult]:
    """Calculate fixed yearly costs per season.

    Args:
        fixed_costs: List of fixed cost items.

    Returns:
        Dictionary season -> SeasonResult with fixed_cost field populated.
    """
    season_results = {s: SeasonResult(season=s) for s in SEASONS}

    for fc in fixed_costs:
        for season in SEASONS:
            frac = fc.season_distribution.get(season, 0.25)
            season_results[season].fixed_cost += fc.annual_cost * frac

    return season_results
