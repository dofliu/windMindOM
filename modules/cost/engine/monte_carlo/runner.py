"""Monte Carlo simulation runner.

Runs N iterations of the cost calculation engine with sampled parameters,
collecting distributions of total cost, availability, and other KPIs.
"""

from dataclasses import dataclass, field

import numpy as np

from modules.cost.engine.cost_cal.aggregator import CostCalResult, run_cost_calculation
from modules.cost.engine.cost_cal.data_classes import (
    ComponentParams,
    EquipmentParams,
    FixedCostParams,
    PMParams,
    WaitingTimePolynomial,
    WindFarmParams,
)
from modules.cost.engine.monte_carlo.sampler import sample_all_parameters


@dataclass
class MonteCarloResult:
    """Result of a Monte Carlo simulation run."""

    n_simulations: int
    seed: int

    # Arrays of length n_simulations
    total_costs: np.ndarray = field(default_factory=lambda: np.array([]))
    total_revenue_losses: np.ndarray = field(default_factory=lambda: np.array([]))
    total_repair_costs: np.ndarray = field(default_factory=lambda: np.array([]))
    availability_time: np.ndarray = field(default_factory=lambda: np.array([]))
    availability_energy: np.ndarray = field(default_factory=lambda: np.array([]))
    cost_per_kwh: np.ndarray = field(default_factory=lambda: np.array([]))

    # Deterministic baseline for comparison
    deterministic_result: CostCalResult | None = None


def run_monte_carlo(
    wind_farm: WindFarmParams,
    components: list[ComponentParams],
    equipment_list: list[EquipmentParams],
    pm_schedules: list[PMParams],
    fixed_costs: list[FixedCostParams],
    poly_lookup: dict[tuple[int, str], WaitingTimePolynomial],
    n_simulations: int = 1000,
    seed: int = 42,
) -> MonteCarloResult:
    """Run Monte Carlo simulation of the cost calculation.

    For each iteration, stochastic parameters (failure frequencies, repair hours,
    logistics hours, equipment day rates, mobilisation costs) are sampled from
    their defined distributions. The full cost calculation is run with these
    sampled values.

    Args:
        wind_farm: Wind farm configuration (deterministic).
        components: Component parameters with optional min/ml/max bounds.
        equipment_list: Equipment parameters with optional min/max bounds.
        pm_schedules: Preventive maintenance schedules (deterministic).
        fixed_costs: Fixed yearly costs (deterministic).
        poly_lookup: Waiting time polynomials (deterministic).
        n_simulations: Number of Monte Carlo iterations.
        seed: Random seed for reproducibility.

    Returns:
        MonteCarloResult with arrays of KPIs across all iterations.
    """
    rng = np.random.default_rng(seed)

    # First run deterministic baseline
    det_result = run_cost_calculation(
        wind_farm=wind_farm,
        components=components,
        equipment_list=equipment_list,
        pm_schedules=pm_schedules,
        fixed_costs=fixed_costs,
        poly_lookup=poly_lookup,
    )

    # Sample parameters for all iterations
    iterations = sample_all_parameters(components, equipment_list, n_simulations, rng)

    # Allocate result arrays
    total_costs = np.zeros(n_simulations)
    total_revenue_losses = np.zeros(n_simulations)
    total_repair_costs = np.zeros(n_simulations)
    avail_time = np.zeros(n_simulations)
    avail_energy = np.zeros(n_simulations)
    cpkwh = np.zeros(n_simulations)

    # Run iterations
    for i, iter_params in enumerate(iterations):
        result = run_cost_calculation(
            wind_farm=wind_farm,
            components=iter_params["components"],
            equipment_list=iter_params["equipment"],
            pm_schedules=pm_schedules,
            fixed_costs=fixed_costs,
            poly_lookup=poly_lookup,
        )
        total_costs[i] = result.total_effort
        total_revenue_losses[i] = result.total_revenue_loss
        total_repair_costs[i] = result.total_repair_cost
        avail_time[i] = result.availability_time
        avail_energy[i] = result.availability_energy
        cpkwh[i] = result.cost_per_kwh

    return MonteCarloResult(
        n_simulations=n_simulations,
        seed=seed,
        total_costs=total_costs,
        total_revenue_losses=total_revenue_losses,
        total_repair_costs=total_repair_costs,
        availability_time=avail_time,
        availability_energy=avail_energy,
        cost_per_kwh=cpkwh,
        deterministic_result=det_result,
    )
