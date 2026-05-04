"""Corrective maintenance cost calculation.

For each WT/BOP component, for each maintenance category (MC), for each fault type class (FTC):
1. Calculate annual events per season
2. Calculate time-to-repair (TTR) including waiting time
3. Calculate costs: material, labour, equipment, revenue loss
4. Sum across all components and categories per season

The ECN O&M Tool V5 calculates costs on a per-turbine, per-event basis, then
multiplies by the number of events to get the seasonal total.
"""

import math

import numpy as np

from modules.cost.engine.cost_cal.data_classes import (
    SEASONS,
    ComponentParams,
    EquipmentParams,
    SeasonResult,
    WaitingTimePolynomial,
    WindFarmParams,
)


# Default FTC repair parameters from the ECN O&M Tool V5
# Keyed by FTC number. These define the repair duration, logistics, organization hours.
FTC_REPAIR_PARAMS = {
    1: {"repair_hours": 2, "logistics_hours": 0, "organization_hours": 0, "long_working_day": False},
    2: {"repair_hours": 4, "logistics_hours": 0, "organization_hours": 0, "long_working_day": False},
    3: {"repair_hours": 8, "logistics_hours": 0, "organization_hours": 0, "long_working_day": False},
    4: {"repair_hours": 8, "logistics_hours": 0, "organization_hours": 0, "long_working_day": False},
    5: {"repair_hours": 16, "logistics_hours": 0, "organization_hours": 0, "long_working_day": True},
    6: {"repair_hours": 16, "logistics_hours": 0, "organization_hours": 0, "long_working_day": False},
    7: {"repair_hours": 24, "logistics_hours": 0, "organization_hours": 0, "long_working_day": True},
    8: {"repair_hours": 24, "logistics_hours": 0, "organization_hours": 0, "long_working_day": True},
    9: {"repair_hours": 8, "logistics_hours": 0, "organization_hours": 0, "long_working_day": False},
    10: {"repair_hours": 16, "logistics_hours": 0, "organization_hours": 0, "long_working_day": False},
    11: {"repair_hours": 24, "logistics_hours": 0, "organization_hours": 0, "long_working_day": False},
    12: {"repair_hours": 40, "logistics_hours": 0, "organization_hours": 0, "long_working_day": False},
    13: {"repair_hours": 40, "logistics_hours": 0, "organization_hours": 0, "long_working_day": False},
}

# Default equipment assignment per maintenance category (MC) in K13
# MC# -> equipment index (1-based)
MC_EQUIPMENT_MAP = {
    1: None,  # Remote reset, no equipment
    2: 1,     # Windcat
    3: 1,     # Windcat
    4: 1,     # Windcat (small repairs), but heavy uses jack-up
    5: 1,     # Windcat (CBM)
    6: 4,     # Jack-up barge
}


def _get_working_hours_per_day(long_working_day: bool) -> float:
    """Get working hours per day based on day type."""
    if long_working_day:
        return 24.0
    return 11.0  # 7:00 to 18:00


def _get_ww_poly(
    ww_index: int | None,
    season: str,
    poly_lookup: dict[tuple[int, str], WaitingTimePolynomial],
) -> WaitingTimePolynomial | None:
    """Look up a waiting time polynomial by weather window index and season."""
    if ww_index is None:
        return None
    return poly_lookup.get((ww_index, season))


def calculate_corrective_costs(
    components: list[ComponentParams],
    equipment_list: list[EquipmentParams],
    wind_farm: WindFarmParams,
    poly_lookup: dict[tuple[int, str], WaitingTimePolynomial],
    component_type: str = "WT",
) -> dict[str, SeasonResult]:
    """Calculate corrective maintenance costs for all components of a given type.

    Args:
        components: List of component failure parameters.
        equipment_list: List of equipment parameters.
        wind_farm: Wind farm configuration.
        poly_lookup: Lookup dict (ww_index, season) -> WaitingTimePolynomial.
        component_type: "WT" or "BOP".

    Returns:
        Dictionary season -> SeasonResult with corrective costs filled in.
    """
    # Build equipment lookup by index
    equip_by_idx = {e.equipment_index: e for e in equipment_list}

    season_results = {s: SeasonResult(season=s) for s in SEASONS}

    for component in components:
        if component.component_type != component_type:
            continue

        for mc in component.maintenance_categories:
            ftc = mc.ftc

            # Get equipment for this MC
            equip = equip_by_idx.get(mc.equipment_index) if mc.equipment_index else None

            # Determine weather window to use based on long_working_day
            ww_index = None
            if equip is not None:
                if ftc.long_working_day and equip.ww_long_index is not None:
                    ww_index = equip.ww_long_index
                else:
                    ww_index = equip.ww_normal_index

            # Working hours per day for this FTC
            working_hours = _get_working_hours_per_day(ftc.long_working_day)

            # Material cost per event
            mat_cost_pct = ftc.material_cost_pct * wind_farm.capacity_kw * wind_farm.investment_cost_per_kw
            mat_cost_euro = ftc.material_cost_euro
            material_per_event = max(mat_cost_pct, mat_cost_euro)

            for season in SEASONS:
                sr = season_results[season]
                season_weight = wind_farm.season_weights.get(season, 0.25)
                capacity_factor = wind_farm.capacity_factors.get(season, 0.0)

                # Annual events for this component/MC/season
                annual_events = (
                    wind_farm.nr_turbines
                    * component.annual_failure_freq
                    * mc.probability
                    * season_weight
                )

                if annual_events <= 0:
                    continue

                # ── Time calculations ──
                t_org = ftc.organization_hours

                # Logistics time: max of equipment logistics and spares logistics
                t_log_equip = equip.logistic_hours if equip else 0.0
                t_log_spares = ftc.logistics_hours
                t_log = max(t_log_equip, t_log_spares)

                # Travel time (one-way, for equipment mobilisation)
                t_travel = equip.travel_hours if equip else 0.0

                # Mission time: repair + round trip travel within mission
                t_mission = ftc.repair_hours + 2 * t_travel

                # Waiting time from polynomial
                poly = _get_ww_poly(ww_index, season, poly_lookup)
                if poly is not None:
                    t_wait = poly.evaluate(t_mission)
                else:
                    t_wait = 0.0

                # Total time to repair (downtime per turbine per event)
                ttr = t_org + t_log + t_wait + t_mission

                # ── Cost calculations ──
                # Material cost
                total_material = annual_events * material_per_event

                # Labour cost
                labour_per_event = ftc.crew_size * ftc.repair_hours * wind_farm.tech_hourly_rate
                total_labour = annual_events * labour_per_event

                # Equipment day cost
                if equip is not None and equip.day_rate > 0:
                    # Days needed = ceil of total time / working hours per day
                    equip_time = t_wait + t_mission + t_travel
                    days_needed = math.ceil(equip_time / working_hours) if working_hours > 0 else 0
                    equip_cost_per_event = equip.day_rate * days_needed
                else:
                    equip_cost_per_event = 0.0
                total_equipment = annual_events * equip_cost_per_event

                # Mobilisation cost
                if equip is not None and equip.mob_cost > 0:
                    mob_per_event = equip.mob_cost
                else:
                    mob_per_event = 0.0
                total_mob = annual_events * mob_per_event

                # Revenue loss per event (one turbine down for ttr hours)
                # Energy_loss_kWh = ttr * capacity_kw * CF * efficiency
                # Revenue_loss_EUR = Energy_loss_kWh * kwh_price
                revenue_loss_per_event = (
                    ttr * wind_farm.capacity_kw * capacity_factor
                    * wind_farm.farm_efficiency * wind_farm.kwh_price
                )
                total_revenue_loss = annual_events * revenue_loss_per_event

                # Downtime (turbine-hours across the farm)
                total_downtime = annual_events * ttr

                # ── Additional inspections ──
                if mc.nr_additional_inspections > 0:
                    # Each additional inspection is a separate visit
                    # Using FTC 2 parameters (small crew, 4hr repair) as inspection baseline
                    insp_events = annual_events * mc.nr_additional_inspections

                    # Inspection uses same equipment
                    insp_repair_hours = 4.0  # standard inspection duration
                    insp_mission = insp_repair_hours + 2 * t_travel
                    if poly is not None:
                        insp_t_wait = poly.evaluate(insp_mission)
                    else:
                        insp_t_wait = 0.0

                    insp_ttr = insp_t_wait + insp_mission

                    # Additional inspection costs (no material, minimal crew)
                    insp_labour = insp_events * 2 * insp_repair_hours * wind_farm.tech_hourly_rate
                    total_labour += insp_labour

                    if equip is not None and equip.day_rate > 0:
                        insp_equip_time = insp_t_wait + insp_mission + t_travel
                        insp_days = math.ceil(insp_equip_time / working_hours) if working_hours > 0 else 0
                        total_equipment += insp_events * equip.day_rate * insp_days

                    # Revenue loss from inspections
                    insp_rev_loss = (
                        insp_ttr * wind_farm.capacity_kw * capacity_factor
                        * wind_farm.farm_efficiency * wind_farm.kwh_price
                    )
                    total_revenue_loss += insp_events * insp_rev_loss
                    total_downtime += insp_events * insp_ttr

                # ── Accumulate into season result ──
                if component_type == "WT":
                    sr.corrective_wt_material += total_material
                    sr.corrective_wt_labour += total_labour
                    sr.corrective_wt_equipment += total_equipment
                    sr.corrective_wt_mob += total_mob
                    sr.corrective_wt_revenue_loss += total_revenue_loss
                    sr.corrective_wt_downtime += total_downtime
                else:
                    sr.corrective_bop_material += total_material
                    sr.corrective_bop_labour += total_labour
                    sr.corrective_bop_equipment += total_equipment
                    sr.corrective_bop_mob += total_mob
                    sr.corrective_bop_revenue_loss += total_revenue_loss
                    sr.corrective_bop_downtime += total_downtime

    return season_results
