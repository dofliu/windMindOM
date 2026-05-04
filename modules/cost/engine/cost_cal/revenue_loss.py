"""Revenue loss utility functions.

Energy production and revenue loss calculations using capacity factors
and optionally the waiting/mission power polynomials from the WaitingTime module.
"""

from modules.cost.engine.cost_cal.data_classes import WindFarmParams


def energy_loss_mwh(
    downtime_hours: float,
    capacity_kw: float,
    capacity_factor: float,
    farm_efficiency: float,
) -> float:
    """Calculate energy loss in MWh.

    Args:
        downtime_hours: Total downtime hours for one turbine.
        capacity_kw: Rated power per turbine in kW.
        capacity_factor: Capacity factor for the season (0-1).
        farm_efficiency: Farm efficiency factor (0-1).

    Returns:
        Energy loss in MWh.
    """
    return downtime_hours * capacity_kw * capacity_factor * farm_efficiency / 1000.0


def revenue_loss_eur(
    energy_loss_mwh_val: float,
    kwh_price: float,
) -> float:
    """Calculate revenue loss in EUR from energy loss.

    Args:
        energy_loss_mwh_val: Energy loss in MWh.
        kwh_price: Electricity price in EUR/kWh.

    Returns:
        Revenue loss in EUR.
    """
    return energy_loss_mwh_val * kwh_price * 1000.0


def annual_energy_production_mwh(
    wind_farm: WindFarmParams,
) -> float:
    """Calculate annual energy production in MWh.

    Uses the yearly capacity factor (average of seasonal factors
    weighted by season weights).

    Args:
        wind_farm: Wind farm parameters.

    Returns:
        Annual energy production in MWh for the entire farm.
    """
    # Weighted average capacity factor
    avg_cf = sum(
        wind_farm.capacity_factors.get(s, 0.0) * wind_farm.season_weights.get(s, 0.25)
        for s in ["winter", "spring", "summer", "autumn"]
    )

    # Annual energy = nr_turbines * capacity_kw * 8760 * CF * efficiency / 1000
    return (
        wind_farm.nr_turbines
        * wind_farm.capacity_kw
        * 8760
        * avg_cf
        * wind_farm.farm_efficiency
        / 1000.0
    )
