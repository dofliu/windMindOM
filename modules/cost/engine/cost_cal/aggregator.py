"""Aggregator — combines corrective, preventive, and fixed costs into final results."""

from dataclasses import dataclass, field

from modules.cost.engine.cost_cal.corrective import calculate_corrective_costs
from modules.cost.engine.cost_cal.data_classes import (
    SEASONS,
    ComponentParams,
    EquipmentParams,
    FixedCostParams,
    PMParams,
    SeasonResult,
    WaitingTimePolynomial,
    WindFarmParams,
)
from modules.cost.engine.cost_cal.fixed import calculate_fixed_costs
from modules.cost.engine.cost_cal.preventive import calculate_preventive_costs
from modules.cost.engine.cost_cal.revenue_loss import annual_energy_production_mwh


@dataclass
class CostCalResult:
    """Final cost calculation result."""

    # Availability
    availability_time: float = 0.0
    availability_energy: float = 0.0

    # Annual totals
    total_revenue_loss: float = 0.0
    total_repair_cost: float = 0.0
    total_effort: float = 0.0
    cost_per_kwh: float = 0.0

    # Per-season breakdowns
    seasonal_results: dict[str, SeasonResult] = field(default_factory=dict)

    # Component-level breakdown (optional detail)
    component_breakdown: dict = field(default_factory=dict)
    equipment_usage: dict = field(default_factory=dict)


def _merge_season_results(
    base: dict[str, SeasonResult],
    overlay: dict[str, SeasonResult],
) -> None:
    """Merge overlay season results into base (in-place addition)."""
    for season in SEASONS:
        if season not in overlay:
            continue
        o = overlay[season]
        b = base[season]

        b.corrective_wt_material += o.corrective_wt_material
        b.corrective_wt_labour += o.corrective_wt_labour
        b.corrective_wt_equipment += o.corrective_wt_equipment
        b.corrective_wt_mob += o.corrective_wt_mob
        b.corrective_wt_revenue_loss += o.corrective_wt_revenue_loss
        b.corrective_wt_downtime += o.corrective_wt_downtime

        b.corrective_bop_material += o.corrective_bop_material
        b.corrective_bop_labour += o.corrective_bop_labour
        b.corrective_bop_equipment += o.corrective_bop_equipment
        b.corrective_bop_mob += o.corrective_bop_mob
        b.corrective_bop_revenue_loss += o.corrective_bop_revenue_loss
        b.corrective_bop_downtime += o.corrective_bop_downtime

        b.preventive_material += o.preventive_material
        b.preventive_labour += o.preventive_labour
        b.preventive_equipment += o.preventive_equipment
        b.preventive_mob += o.preventive_mob
        b.preventive_revenue_loss += o.preventive_revenue_loss
        b.preventive_downtime += o.preventive_downtime

        b.fixed_cost += o.fixed_cost


def run_cost_calculation(
    wind_farm: WindFarmParams,
    components: list[ComponentParams],
    equipment_list: list[EquipmentParams],
    pm_schedules: list[PMParams],
    fixed_costs: list[FixedCostParams],
    poly_lookup: dict[tuple[int, str], WaitingTimePolynomial],
) -> CostCalResult:
    """Run the complete cost calculation.

    Args:
        wind_farm: Wind farm configuration.
        components: All fault type components (WT + BOP).
        equipment_list: Equipment fleet.
        pm_schedules: Preventive maintenance schedules.
        fixed_costs: Fixed yearly cost items.
        poly_lookup: (ww_index, season) -> WaitingTimePolynomial.

    Returns:
        CostCalResult with all computed values.
    """
    # Initialize combined results
    combined = {s: SeasonResult(season=s) for s in SEASONS}

    # 1. Corrective WT costs
    corr_wt = calculate_corrective_costs(
        components, equipment_list, wind_farm, poly_lookup, component_type="WT"
    )
    _merge_season_results(combined, corr_wt)

    # 2. Corrective BOP costs
    corr_bop = calculate_corrective_costs(
        components, equipment_list, wind_farm, poly_lookup, component_type="BOP"
    )
    _merge_season_results(combined, corr_bop)

    # 3. Preventive maintenance costs
    prev = calculate_preventive_costs(
        pm_schedules, equipment_list, wind_farm, poly_lookup
    )
    _merge_season_results(combined, prev)

    # 4. Fixed yearly costs
    fix = calculate_fixed_costs(fixed_costs)
    _merge_season_results(combined, fix)

    # ── Aggregate annual totals ──
    total_revenue_loss = sum(sr.total_revenue_loss for sr in combined.values())
    total_repair_cost = sum(sr.total_repair_cost for sr in combined.values())
    total_effort = total_revenue_loss + total_repair_cost
    total_downtime = sum(sr.total_downtime for sr in combined.values())

    # Availability (time-based)
    # Total possible turbine-hours per year
    total_possible_hours = 8760.0 * wind_farm.nr_turbines
    availability_time = 1.0 - (total_downtime / total_possible_hours) if total_possible_hours > 0 else 1.0

    # Availability (energy-based) — weighted by capacity factor per season
    # Energy lost / potential energy production
    annual_production = annual_energy_production_mwh(wind_farm)
    if annual_production > 0:
        # Total energy lost across all seasons (already in revenue loss calc)
        total_energy_lost = total_revenue_loss / (wind_farm.kwh_price * 1000.0) if wind_farm.kwh_price > 0 else 0.0
        availability_energy = 1.0 - (total_energy_lost / annual_production)
    else:
        availability_energy = 1.0

    # Cost per kWh
    if annual_production > 0:
        cost_per_kwh = total_effort / (annual_production * 1000.0)  # EUR / kWh
    else:
        cost_per_kwh = 0.0

    return CostCalResult(
        availability_time=availability_time,
        availability_energy=availability_energy,
        total_revenue_loss=total_revenue_loss,
        total_repair_cost=total_repair_cost,
        total_effort=total_effort,
        cost_per_kwh=cost_per_kwh,
        seasonal_results=combined,
    )
