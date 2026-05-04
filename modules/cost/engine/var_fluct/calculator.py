"""VarFluct calculator — runs cost calculation year-by-year with parameter variation."""

import copy
import json
from dataclasses import dataclass, field

from modules.cost.engine.cost_cal.aggregator import CostCalResult, run_cost_calculation
from modules.cost.engine.cost_cal.data_classes import (
    SEASONS,
    ComponentParams,
    EquipmentParams,
    FixedCostParams,
    PMParams,
    WaitingTimePolynomial,
    WindFarmParams,
)
from modules.cost.engine.var_fluct.bathtub import BathtubParams, bathtub_multiplier


@dataclass
class YearResult:
    """Single year's calculation result."""

    year: int
    failure_multiplier: float
    cost_escalation_factor: float
    kwh_price: float
    capacity_factor_multiplier: float

    # Cost categories (annual)
    corrective_wt: float = 0.0
    corrective_bop: float = 0.0
    preventive: float = 0.0
    fixed: float = 0.0
    revenue_loss: float = 0.0
    total_repair_cost: float = 0.0
    total_effort: float = 0.0
    availability_time: float = 0.0
    availability_energy: float = 0.0


@dataclass
class VarFluctSummary:
    """Lifetime summary with NPV."""

    npv_total_effort: float = 0.0
    npv_total_repair: float = 0.0
    npv_total_revenue_loss: float = 0.0
    avg_annual_effort: float = 0.0
    min_year_effort: float = 0.0
    max_year_effort: float = 0.0
    min_year_index: int = 1
    max_year_index: int = 1
    lifetime_availability_time: float = 0.0
    lifetime_availability_energy: float = 0.0


@dataclass
class VarFluctCalcResult:
    """Full VarFluct calculation output."""

    yearly: list[YearResult] = field(default_factory=list)
    summary: VarFluctSummary = field(default_factory=VarFluctSummary)


@dataclass
class VarFluctConfig:
    """Configuration extracted from DB model for the engine."""

    failure_rate_model: str = "bathtub"  # "constant" | "bathtub" | "custom"
    bathtub_params: BathtubParams = field(default_factory=BathtubParams)
    cost_escalation_rate: float = 0.02
    tariff_schedule: dict[int, float] | None = None  # year -> EUR/kWh
    capacity_degradation_rate: float = 0.005
    custom_failure_multipliers: dict[int, float] | None = None  # year -> multiplier
    discount_rate: float = 0.08


def _get_failure_multiplier(year: int, config: VarFluctConfig) -> float:
    """Get failure rate multiplier for a given year based on the configured model."""
    if config.failure_rate_model == "constant":
        return 1.0
    elif config.failure_rate_model == "custom" and config.custom_failure_multipliers:
        return config.custom_failure_multipliers.get(year, 1.0)
    else:  # bathtub
        return bathtub_multiplier(year, config.bathtub_params)


def _adjust_components(
    components: list[ComponentParams], multiplier: float
) -> list[ComponentParams]:
    """Create copies of components with failure rates scaled by multiplier."""
    adjusted = []
    for comp in components:
        c = copy.deepcopy(comp)
        c.annual_failure_freq *= multiplier
        # Also scale stochastic bounds if present
        if c.freq_min is not None:
            c.freq_min *= multiplier
        if c.freq_ml is not None:
            c.freq_ml *= multiplier
        if c.freq_max is not None:
            c.freq_max *= multiplier
        adjusted.append(c)
    return adjusted


def _adjust_equipment_costs(
    equipment: list[EquipmentParams], escalation_factor: float
) -> list[EquipmentParams]:
    """Scale equipment costs by escalation factor."""
    adjusted = []
    for eq in equipment:
        e = copy.deepcopy(eq)
        e.day_rate *= escalation_factor
        e.mob_cost *= escalation_factor
        e.mission_rate *= escalation_factor
        adjusted.append(e)
    return adjusted


def _adjust_wind_farm(
    wind_farm: WindFarmParams,
    year: int,
    config: VarFluctConfig,
) -> WindFarmParams:
    """Adjust wind farm params for a given year (tariff + degradation)."""
    wf = copy.deepcopy(wind_farm)

    # Tariff schedule override
    if config.tariff_schedule and year in config.tariff_schedule:
        wf.kwh_price = config.tariff_schedule[year]

    # Capacity factor degradation: (1 - rate)^(year-1)
    degradation = (1.0 - config.capacity_degradation_rate) ** (year - 1)
    wf.capacity_factors = {
        s: cf * degradation for s, cf in wf.capacity_factors.items()
    }

    return wf


def _extract_costs_from_result(result: CostCalResult) -> dict:
    """Extract cost categories from a CostCalResult."""
    sr = result.seasonal_results
    corrective_wt = sum(s.corrective_wt_total for s in sr.values())
    corrective_bop = sum(s.corrective_bop_total for s in sr.values())
    preventive = sum(s.preventive_total for s in sr.values())
    fixed = sum(s.fixed_cost for s in sr.values())

    return {
        "corrective_wt": corrective_wt,
        "corrective_bop": corrective_bop,
        "preventive": preventive,
        "fixed": fixed,
        "revenue_loss": result.total_revenue_loss,
        "total_repair_cost": result.total_repair_cost,
        "total_effort": result.total_effort,
        "availability_time": result.availability_time,
        "availability_energy": result.availability_energy,
    }


def run_var_fluct_calculation(
    wind_farm: WindFarmParams,
    components: list[ComponentParams],
    equipment_list: list[EquipmentParams],
    pm_schedules: list[PMParams],
    fixed_costs: list[FixedCostParams],
    poly_lookup: dict[tuple[int, str], WaitingTimePolynomial],
    config: VarFluctConfig,
) -> VarFluctCalcResult:
    """Run year-by-year cost calculation with parameter variation.

    For each year in the wind farm lifetime:
      1. Compute failure rate multiplier (bathtub / constant / custom)
      2. Scale component failure rates
      3. Apply cost escalation to equipment costs
      4. Adjust electricity price from tariff schedule
      5. Apply capacity factor degradation
      6. Run standard cost calculation
      7. Collect results

    Finally, compute NPV summary over the lifetime.
    """
    lifetime = wind_farm.lifetime_years
    config.bathtub_params.lifetime = lifetime

    yearly_results: list[YearResult] = []

    for year in range(1, lifetime + 1):
        # 1. Failure rate multiplier
        failure_mult = _get_failure_multiplier(year, config)

        # 2. Cost escalation factor: (1 + rate)^(year - 1)
        # Year 1 = no escalation, year 2 = 1 * rate, etc.
        escalation = (1.0 + config.cost_escalation_rate) ** (year - 1)

        # 3. Adjust parameters
        adj_components = _adjust_components(components, failure_mult)
        adj_equipment = _adjust_equipment_costs(equipment_list, escalation)
        adj_wind_farm = _adjust_wind_farm(wind_farm, year, config)

        # Also escalate fixed costs and PM material costs
        adj_fixed = []
        for fc in fixed_costs:
            fc_copy = copy.deepcopy(fc)
            fc_copy.annual_cost *= escalation
            adj_fixed.append(fc_copy)

        adj_pm = []
        for pm in pm_schedules:
            pm_copy = copy.deepcopy(pm)
            pm_copy.material_cost *= escalation
            adj_pm.append(pm_copy)

        # 4. Run cost calculation
        result = run_cost_calculation(
            adj_wind_farm, adj_components, adj_equipment,
            adj_pm, adj_fixed, poly_lookup,
        )

        # 5. Extract and store
        costs = _extract_costs_from_result(result)
        cap_deg = (1.0 - config.capacity_degradation_rate) ** (year - 1)

        yr = YearResult(
            year=year,
            failure_multiplier=round(failure_mult, 4),
            cost_escalation_factor=round(escalation, 4),
            kwh_price=adj_wind_farm.kwh_price,
            capacity_factor_multiplier=round(cap_deg, 4),
            **costs,
        )
        yearly_results.append(yr)

    # ── Compute summary ──
    efforts = [yr.total_effort for yr in yearly_results]
    repairs = [yr.total_repair_cost for yr in yearly_results]
    rev_losses = [yr.revenue_loss for yr in yearly_results]

    # NPV
    dr = config.discount_rate
    npv_effort = sum(e / (1 + dr) ** y.year for y, e in zip(yearly_results, efforts))
    npv_repair = sum(r / (1 + dr) ** y.year for y, r in zip(yearly_results, repairs))
    npv_rev_loss = sum(
        r / (1 + dr) ** y.year for y, r in zip(yearly_results, rev_losses)
    )

    # Min / max year
    min_idx = efforts.index(min(efforts))
    max_idx = efforts.index(max(efforts))

    # Lifetime availability (weighted average)
    avg_avail_time = (
        sum(yr.availability_time for yr in yearly_results) / len(yearly_results)
        if yearly_results
        else 0.0
    )
    avg_avail_energy = (
        sum(yr.availability_energy for yr in yearly_results) / len(yearly_results)
        if yearly_results
        else 0.0
    )

    summary = VarFluctSummary(
        npv_total_effort=round(npv_effort, 2),
        npv_total_repair=round(npv_repair, 2),
        npv_total_revenue_loss=round(npv_rev_loss, 2),
        avg_annual_effort=round(sum(efforts) / len(efforts), 2) if efforts else 0.0,
        min_year_effort=round(min(efforts), 2) if efforts else 0.0,
        max_year_effort=round(max(efforts), 2) if efforts else 0.0,
        min_year_index=min_idx + 1,
        max_year_index=max_idx + 1,
        lifetime_availability_time=round(avg_avail_time, 6),
        lifetime_availability_energy=round(avg_avail_energy, 6),
    )

    return VarFluctCalcResult(yearly=yearly_results, summary=summary)
