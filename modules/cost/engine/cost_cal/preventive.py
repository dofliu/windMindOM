"""Preventive maintenance cost calculation.

For each PM schedule:
1. Calculate annual events per season from lifetime occurrences
2. Calculate downtime including waiting time
3. Calculate costs: material, labour, equipment, revenue loss
"""

import math

from modules.cost.engine.cost_cal.data_classes import (
    SEASONS,
    EquipmentParams,
    PMParams,
    SeasonResult,
    WaitingTimePolynomial,
    WindFarmParams,
)


def calculate_preventive_costs(
    pm_schedules: list[PMParams],
    equipment_list: list[EquipmentParams],
    wind_farm: WindFarmParams,
    poly_lookup: dict[tuple[int, str], WaitingTimePolynomial],
) -> dict[str, SeasonResult]:
    """Calculate preventive maintenance costs.

    Args:
        pm_schedules: List of PM schedule parameters.
        equipment_list: List of equipment parameters.
        wind_farm: Wind farm configuration.
        poly_lookup: Lookup dict (ww_index, season) -> WaitingTimePolynomial.

    Returns:
        Dictionary season -> SeasonResult with preventive costs filled in.
    """
    equip_by_idx = {e.equipment_index: e for e in equipment_list}
    season_results = {s: SeasonResult(season=s) for s in SEASONS}

    for pm in pm_schedules:
        # Annual occurrences averaged over lifetime
        annual_occurrences = pm.nr_occurrences / wind_farm.lifetime_years

        # For WT PM, multiply by number of turbines
        if pm.pm_type == "WT":
            farm_multiplier = wind_farm.nr_turbines
        else:
            farm_multiplier = 1  # BOP affects entire farm once

        equip = equip_by_idx.get(pm.equipment_index) if pm.equipment_index else None
        working_hours = 24.0 if pm.long_working_day else 11.0

        for season in SEASONS:
            sr = season_results[season]
            season_frac = pm.season_distribution.get(season, 0.0)

            # Events this season
            events = annual_occurrences * farm_multiplier * season_frac
            if events <= 0:
                continue

            # Travel time
            t_travel = pm.travel_hours

            # Mission time: duration + round trip travel
            t_mission = pm.duration_hours + 2 * t_travel

            # Waiting time
            ww_index = None
            if equip is not None:
                if pm.long_working_day and equip.ww_long_index is not None:
                    ww_index = equip.ww_long_index
                else:
                    ww_index = equip.ww_normal_index

            poly = poly_lookup.get((ww_index, season)) if ww_index is not None else None
            t_wait = poly.evaluate(t_mission) if poly else 0.0

            # Total downtime per occurrence per turbine
            ttr = t_wait + t_mission

            # Material cost
            total_material = events * pm.material_cost

            # Labour cost
            total_labour = events * pm.crew_size * pm.duration_hours * wind_farm.tech_hourly_rate

            # Equipment cost
            if equip is not None and equip.day_rate > 0:
                equip_time = t_wait + t_mission + t_travel
                days_needed = math.ceil(equip_time / working_hours) if working_hours > 0 else 0
                total_equipment = events * equip.day_rate * days_needed
            else:
                total_equipment = 0.0

            # Mobilisation
            if equip is not None and equip.mob_cost > 0:
                total_mob = events * equip.mob_cost
            else:
                total_mob = 0.0

            # Revenue loss
            capacity_factor = wind_farm.capacity_factors.get(season, 0.0)
            if pm.pm_type == "WT":
                # Each event is one turbine PM, revenue loss for one turbine
                rev_loss_per_event = (
                    ttr * wind_farm.capacity_kw * capacity_factor
                    * wind_farm.farm_efficiency * wind_farm.kwh_price
                )
            else:
                # BOP PM: affects pct_farm_shutdown of the farm
                rev_loss_per_event = (
                    ttr * wind_farm.capacity_kw * wind_farm.nr_turbines
                    * pm.pct_farm_shutdown * capacity_factor
                    * wind_farm.farm_efficiency * wind_farm.kwh_price
                )
                # For BOP, events are not multiplied by nr_turbines (farm_multiplier=1)

            total_revenue_loss = events * rev_loss_per_event

            # Downtime (turbine-hours)
            if pm.pm_type == "WT":
                total_downtime = events * ttr
            else:
                total_downtime = events * ttr * wind_farm.nr_turbines * pm.pct_farm_shutdown

            # Accumulate
            sr.preventive_material += total_material
            sr.preventive_labour += total_labour
            sr.preventive_equipment += total_equipment
            sr.preventive_mob += total_mob
            sr.preventive_revenue_loss += total_revenue_loss
            sr.preventive_downtime += total_downtime

    return season_results
