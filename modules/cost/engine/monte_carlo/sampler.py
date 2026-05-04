"""Parameter sampling for Monte Carlo simulation.

Uses triangular distributions for stochastic parameters where min/ml/max
values are defined. Falls back to deterministic values when bounds are missing.
"""

import copy
from dataclasses import replace

import numpy as np

from modules.cost.engine.cost_cal.data_classes import (
    ComponentParams,
    EquipmentParams,
    FTCParams,
    MCParams,
)


def triangular_sample(
    min_val: float, ml_val: float, max_val: float, n: int, rng: np.random.Generator
) -> np.ndarray:
    """Sample n values from a triangular distribution.

    Args:
        min_val: Minimum value (left).
        ml_val: Most-likely value (mode).
        max_val: Maximum value (right).
        n: Number of samples.
        rng: NumPy random generator.

    Returns:
        Array of n sampled values.
    """
    # Clamp mode to [min, max] for safety
    left = min(min_val, max_val)
    right = max(min_val, max_val)
    mode = max(left, min(ml_val, right))
    if left == right:
        return np.full(n, left)
    return rng.triangular(left, mode, right, size=n)


def uniform_sample(
    min_val: float, max_val: float, n: int, rng: np.random.Generator
) -> np.ndarray:
    """Sample n values from a uniform distribution.

    Args:
        min_val: Minimum value.
        max_val: Maximum value.
        n: Number of samples.
        rng: NumPy random generator.

    Returns:
        Array of n sampled values.
    """
    if min_val == max_val:
        return np.full(n, min_val)
    lo = min(min_val, max_val)
    hi = max(min_val, max_val)
    return rng.uniform(lo, hi, size=n)


def sample_all_parameters(
    components: list[ComponentParams],
    equipment: list[EquipmentParams],
    n: int,
    rng: np.random.Generator,
) -> list[dict]:
    """Sample stochastic parameters for n Monte Carlo iterations.

    For each iteration, creates overrides for:
    - Component failure frequencies (triangular: freq_min/ml/max)
    - FTC repair hours (uniform: repair_hours_min/max)
    - FTC logistics hours (uniform: logistics_hours_min/max)
    - Equipment day rates (uniform: day_rate_min/max)
    - Equipment mobilisation costs (uniform: mob_cost_min/max)

    The returned list has one dict per iteration, each containing
    the sampled component list and equipment list ready for the cost engine.

    Args:
        components: Base component parameters (with optional min/ml/max fields).
        equipment: Base equipment parameters (with optional min/max fields).
        n: Number of iterations.
        rng: NumPy random generator.

    Returns:
        List of n dicts, each with keys 'components' and 'equipment'.
    """
    # Pre-sample all stochastic arrays
    # -- Component failure frequencies --
    comp_freq_samples = {}  # (comp_idx,) -> np.ndarray of shape (n,)
    for ci, comp in enumerate(components):
        freq_min = getattr(comp, "freq_min", None)
        freq_ml = getattr(comp, "freq_ml", None)
        freq_max = getattr(comp, "freq_max", None)
        if freq_min is not None and freq_ml is not None and freq_max is not None:
            comp_freq_samples[ci] = triangular_sample(freq_min, freq_ml, freq_max, n, rng)

    # -- FTC repair/logistics hours --
    ftc_repair_samples = {}  # (comp_idx, mc_idx) -> np.ndarray
    ftc_logistics_samples = {}
    for ci, comp in enumerate(components):
        for mi, mc in enumerate(comp.maintenance_categories):
            ftc = mc.ftc
            rh_min = getattr(ftc, "repair_hours_min", None)
            rh_max = getattr(ftc, "repair_hours_max", None)
            if rh_min is not None and rh_max is not None:
                ftc_repair_samples[(ci, mi)] = uniform_sample(rh_min, rh_max, n, rng)

            lh_min = getattr(ftc, "logistics_hours_min", None)
            lh_max = getattr(ftc, "logistics_hours_max", None)
            if lh_min is not None and lh_max is not None:
                ftc_logistics_samples[(ci, mi)] = uniform_sample(lh_min, lh_max, n, rng)

    # -- Equipment day rates and mob costs --
    equip_day_rate_samples = {}  # equip_idx -> np.ndarray
    equip_mob_cost_samples = {}
    for ei, eq in enumerate(equipment):
        dr_min = getattr(eq, "day_rate_min", None)
        dr_max = getattr(eq, "day_rate_max", None)
        if dr_min is not None and dr_max is not None:
            equip_day_rate_samples[ei] = uniform_sample(dr_min, dr_max, n, rng)

        mc_min = getattr(eq, "mob_cost_min", None)
        mc_max = getattr(eq, "mob_cost_max", None)
        if mc_min is not None and mc_max is not None:
            equip_mob_cost_samples[ei] = uniform_sample(mc_min, mc_max, n, rng)

    # Build per-iteration parameter sets
    iterations = []
    for i in range(n):
        # Deep-copy components and apply overrides
        iter_components = []
        for ci, comp in enumerate(components):
            freq = comp_freq_samples[ci][i] if ci in comp_freq_samples else comp.annual_failure_freq

            iter_mcs = []
            for mi, mc in enumerate(comp.maintenance_categories):
                ftc = mc.ftc
                rh = ftc_repair_samples[(ci, mi)][i] if (ci, mi) in ftc_repair_samples else ftc.repair_hours
                lh = ftc_logistics_samples[(ci, mi)][i] if (ci, mi) in ftc_logistics_samples else ftc.logistics_hours

                new_ftc = FTCParams(
                    ftc_number=ftc.ftc_number,
                    repair_type=ftc.repair_type,
                    material_cost_pct=ftc.material_cost_pct,
                    material_cost_euro=ftc.material_cost_euro,
                    crew_size=ftc.crew_size,
                    repair_hours=float(rh),
                    logistics_hours=float(lh),
                    organization_hours=ftc.organization_hours,
                    long_working_day=ftc.long_working_day,
                )
                iter_mcs.append(MCParams(
                    category_index=mc.category_index,
                    probability=mc.probability,
                    equipment_index=mc.equipment_index,
                    nr_additional_inspections=mc.nr_additional_inspections,
                    ftc=new_ftc,
                ))

            iter_components.append(ComponentParams(
                component_name=comp.component_name,
                component_code=comp.component_code,
                component_type=comp.component_type,
                annual_failure_freq=float(freq),
                maintenance_categories=iter_mcs,
            ))

        # Deep-copy equipment and apply overrides
        iter_equipment = []
        for ei, eq in enumerate(equipment):
            dr = equip_day_rate_samples[ei][i] if ei in equip_day_rate_samples else eq.day_rate
            mc = equip_mob_cost_samples[ei][i] if ei in equip_mob_cost_samples else eq.mob_cost

            iter_equipment.append(EquipmentParams(
                equipment_index=eq.equipment_index,
                name=eq.name,
                ww_normal_index=eq.ww_normal_index,
                ww_long_index=eq.ww_long_index,
                nr_available=eq.nr_available,
                logistic_hours=eq.logistic_hours,
                travel_hours=eq.travel_hours,
                cost_type=eq.cost_type,
                day_rate=float(dr),
                mob_cost=float(mc),
                mission_rate=eq.mission_rate,
            ))

        iterations.append({
            "components": iter_components,
            "equipment": iter_equipment,
        })

    return iterations
