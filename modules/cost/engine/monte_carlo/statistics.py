"""Statistical analysis utilities for Monte Carlo results.

Provides percentile computation, CDF generation, and tornado chart
sensitivity analysis.
"""

from dataclasses import dataclass

import numpy as np

from modules.cost.engine.cost_cal.aggregator import run_cost_calculation
from modules.cost.engine.cost_cal.data_classes import (
    ComponentParams,
    EquipmentParams,
    FTCParams,
    FixedCostParams,
    MCParams,
    PMParams,
    WaitingTimePolynomial,
    WindFarmParams,
)


def compute_percentiles(values: np.ndarray) -> dict:
    """Compute common percentiles for a distribution of values.

    Args:
        values: Array of simulated values.

    Returns:
        Dict with keys p5, p10, p25, p50 (median), p75, p90, p95,
        plus mean and std.
    """
    return {
        "p5": float(np.percentile(values, 5)),
        "p10": float(np.percentile(values, 10)),
        "p25": float(np.percentile(values, 25)),
        "p50": float(np.percentile(values, 50)),
        "p75": float(np.percentile(values, 75)),
        "p90": float(np.percentile(values, 90)),
        "p95": float(np.percentile(values, 95)),
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
    }


def compute_cdf(values: np.ndarray, n_bins: int = 100) -> tuple[list[float], list[float]]:
    """Compute the empirical CDF of a distribution.

    Args:
        values: Array of simulated values.
        n_bins: Number of bins for the CDF x-axis.

    Returns:
        Tuple of (x_values, y_values) where y is the cumulative probability [0, 1].
    """
    sorted_vals = np.sort(values)
    n = len(sorted_vals)
    y = np.arange(1, n + 1) / n

    # Downsample to n_bins points for efficient storage
    if n > n_bins:
        indices = np.linspace(0, n - 1, n_bins, dtype=int)
        x_out = sorted_vals[indices].tolist()
        y_out = y[indices].tolist()
    else:
        x_out = sorted_vals.tolist()
        y_out = y.tolist()

    return x_out, y_out


@dataclass
class TornadoBar:
    """One bar in a tornado chart — the cost impact of varying a single parameter."""

    parameter_name: str
    base_value: float
    min_value: float
    max_value: float
    cost_at_min: float
    cost_at_max: float
    cost_range: float  # |cost_at_max - cost_at_min|


def _run_with_override(
    wind_farm: WindFarmParams,
    components: list[ComponentParams],
    equipment_list: list[EquipmentParams],
    pm_schedules: list[PMParams],
    fixed_costs: list[FixedCostParams],
    poly_lookup: dict[tuple[int, str], WaitingTimePolynomial],
) -> float:
    """Run cost calculation and return total effort."""
    result = run_cost_calculation(
        wind_farm=wind_farm,
        components=components,
        equipment_list=equipment_list,
        pm_schedules=pm_schedules,
        fixed_costs=fixed_costs,
        poly_lookup=poly_lookup,
    )
    return result.total_effort


def _deep_copy_components(components: list[ComponentParams]) -> list[ComponentParams]:
    """Create a deep copy of component parameters."""
    result = []
    for comp in components:
        mcs = []
        for mc in comp.maintenance_categories:
            ftc = FTCParams(
                ftc_number=mc.ftc.ftc_number,
                repair_type=mc.ftc.repair_type,
                material_cost_pct=mc.ftc.material_cost_pct,
                material_cost_euro=mc.ftc.material_cost_euro,
                crew_size=mc.ftc.crew_size,
                repair_hours=mc.ftc.repair_hours,
                logistics_hours=mc.ftc.logistics_hours,
                organization_hours=mc.ftc.organization_hours,
                long_working_day=mc.ftc.long_working_day,
            )
            mcs.append(MCParams(
                category_index=mc.category_index,
                probability=mc.probability,
                equipment_index=mc.equipment_index,
                nr_additional_inspections=mc.nr_additional_inspections,
                ftc=ftc,
            ))
        result.append(ComponentParams(
            component_name=comp.component_name,
            component_code=comp.component_code,
            component_type=comp.component_type,
            annual_failure_freq=comp.annual_failure_freq,
            maintenance_categories=mcs,
        ))
    return result


def _deep_copy_equipment(equipment: list[EquipmentParams]) -> list[EquipmentParams]:
    """Create a deep copy of equipment parameters."""
    return [
        EquipmentParams(
            equipment_index=eq.equipment_index,
            name=eq.name,
            ww_normal_index=eq.ww_normal_index,
            ww_long_index=eq.ww_long_index,
            nr_available=eq.nr_available,
            logistic_hours=eq.logistic_hours,
            travel_hours=eq.travel_hours,
            cost_type=eq.cost_type,
            day_rate=eq.day_rate,
            mob_cost=eq.mob_cost,
            mission_rate=eq.mission_rate,
        )
        for eq in equipment
    ]


def compute_tornado(
    base_cost: float,
    wind_farm: WindFarmParams,
    components: list[ComponentParams],
    equipment_list: list[EquipmentParams],
    pm_schedules: list[PMParams],
    fixed_costs: list[FixedCostParams],
    poly_lookup: dict[tuple[int, str], WaitingTimePolynomial],
) -> list[TornadoBar]:
    """Compute tornado chart data by varying each stochastic parameter individually.

    For each parameter that has min/max bounds defined, run the cost calculation
    at the min and max values while holding everything else at deterministic values.
    The resulting cost range indicates sensitivity to that parameter.

    Args:
        base_cost: Deterministic total effort (baseline).
        wind_farm: Wind farm configuration.
        components: Component parameters with optional bounds.
        equipment_list: Equipment parameters with optional bounds.
        pm_schedules: PM schedules.
        fixed_costs: Fixed costs.
        poly_lookup: Waiting time polynomials.

    Returns:
        List of TornadoBar sorted by cost_range descending (most sensitive first).
    """
    bars: list[TornadoBar] = []

    # 1. Component failure frequencies
    for ci, comp in enumerate(components):
        freq_min = getattr(comp, "freq_min", None)
        freq_max = getattr(comp, "freq_max", None)
        if freq_min is None or freq_max is None:
            continue

        # Run at min
        comps_min = _deep_copy_components(components)
        comps_min[ci].annual_failure_freq = freq_min
        cost_min = _run_with_override(
            wind_farm, comps_min, equipment_list, pm_schedules, fixed_costs, poly_lookup
        )

        # Run at max
        comps_max = _deep_copy_components(components)
        comps_max[ci].annual_failure_freq = freq_max
        cost_max = _run_with_override(
            wind_farm, comps_max, equipment_list, pm_schedules, fixed_costs, poly_lookup
        )

        bars.append(TornadoBar(
            parameter_name=f"Failure freq: {comp.component_name}",
            base_value=comp.annual_failure_freq,
            min_value=freq_min,
            max_value=freq_max,
            cost_at_min=cost_min,
            cost_at_max=cost_max,
            cost_range=abs(cost_max - cost_min),
        ))

    # 2. FTC repair hours
    for ci, comp in enumerate(components):
        for mi, mc in enumerate(comp.maintenance_categories):
            ftc = mc.ftc
            rh_min = getattr(ftc, "repair_hours_min", None)
            rh_max = getattr(ftc, "repair_hours_max", None)
            if rh_min is None or rh_max is None:
                continue

            comps_lo = _deep_copy_components(components)
            comps_lo[ci].maintenance_categories[mi].ftc.repair_hours = rh_min
            cost_lo = _run_with_override(
                wind_farm, comps_lo, equipment_list, pm_schedules, fixed_costs, poly_lookup
            )

            comps_hi = _deep_copy_components(components)
            comps_hi[ci].maintenance_categories[mi].ftc.repair_hours = rh_max
            cost_hi = _run_with_override(
                wind_farm, comps_hi, equipment_list, pm_schedules, fixed_costs, poly_lookup
            )

            bars.append(TornadoBar(
                parameter_name=f"Repair hrs: {comp.component_name} MC{mc.category_index}",
                base_value=ftc.repair_hours,
                min_value=rh_min,
                max_value=rh_max,
                cost_at_min=cost_lo,
                cost_at_max=cost_hi,
                cost_range=abs(cost_hi - cost_lo),
            ))

    # 3. FTC logistics hours
    for ci, comp in enumerate(components):
        for mi, mc in enumerate(comp.maintenance_categories):
            ftc = mc.ftc
            lh_min = getattr(ftc, "logistics_hours_min", None)
            lh_max = getattr(ftc, "logistics_hours_max", None)
            if lh_min is None or lh_max is None:
                continue

            comps_lo = _deep_copy_components(components)
            comps_lo[ci].maintenance_categories[mi].ftc.logistics_hours = lh_min
            cost_lo = _run_with_override(
                wind_farm, comps_lo, equipment_list, pm_schedules, fixed_costs, poly_lookup
            )

            comps_hi = _deep_copy_components(components)
            comps_hi[ci].maintenance_categories[mi].ftc.logistics_hours = lh_max
            cost_hi = _run_with_override(
                wind_farm, comps_hi, equipment_list, pm_schedules, fixed_costs, poly_lookup
            )

            bars.append(TornadoBar(
                parameter_name=f"Logistics hrs: {comp.component_name} MC{mc.category_index}",
                base_value=ftc.logistics_hours,
                min_value=lh_min,
                max_value=lh_max,
                cost_at_min=cost_lo,
                cost_at_max=cost_hi,
                cost_range=abs(cost_hi - cost_lo),
            ))

    # 4. Equipment day rates
    for ei, eq in enumerate(equipment_list):
        dr_min = getattr(eq, "day_rate_min", None)
        dr_max = getattr(eq, "day_rate_max", None)
        if dr_min is None or dr_max is None:
            continue

        equip_lo = _deep_copy_equipment(equipment_list)
        equip_lo[ei].day_rate = dr_min
        cost_lo = _run_with_override(
            wind_farm, components, equip_lo, pm_schedules, fixed_costs, poly_lookup
        )

        equip_hi = _deep_copy_equipment(equipment_list)
        equip_hi[ei].day_rate = dr_max
        cost_hi = _run_with_override(
            wind_farm, components, equip_hi, pm_schedules, fixed_costs, poly_lookup
        )

        bars.append(TornadoBar(
            parameter_name=f"Day rate: {eq.name}",
            base_value=eq.day_rate,
            min_value=dr_min,
            max_value=dr_max,
            cost_at_min=cost_lo,
            cost_at_max=cost_hi,
            cost_range=abs(cost_hi - cost_lo),
        ))

    # 5. Equipment mobilisation costs
    for ei, eq in enumerate(equipment_list):
        mc_min = getattr(eq, "mob_cost_min", None)
        mc_max = getattr(eq, "mob_cost_max", None)
        if mc_min is None or mc_max is None:
            continue

        equip_lo = _deep_copy_equipment(equipment_list)
        equip_lo[ei].mob_cost = mc_min
        cost_lo = _run_with_override(
            wind_farm, components, equip_lo, pm_schedules, fixed_costs, poly_lookup
        )

        equip_hi = _deep_copy_equipment(equipment_list)
        equip_hi[ei].mob_cost = mc_max
        cost_hi = _run_with_override(
            wind_farm, components, equip_hi, pm_schedules, fixed_costs, poly_lookup
        )

        bars.append(TornadoBar(
            parameter_name=f"Mob cost: {eq.name}",
            base_value=eq.mob_cost,
            min_value=mc_min,
            max_value=mc_max,
            cost_at_min=cost_lo,
            cost_at_max=cost_hi,
            cost_range=abs(cost_hi - cost_lo),
        ))

    # Sort by cost_range descending
    bars.sort(key=lambda b: b.cost_range, reverse=True)
    return bars
