"""Levelised Cost of Energy (LCOE) calculation.

LCOE = NPV(total costs) / NPV(total energy)

Where NPV discounts future values to present using a discount rate.
"""

from dataclasses import dataclass


@dataclass
class LCOEResult:
    """Result of an LCOE calculation."""

    lcoe: float  # EUR/MWh
    capex_total: float  # Total CAPEX (EUR)
    opex_total_npv: float  # NPV of total OPEX over lifetime (EUR)
    energy_total_npv: float  # NPV of total energy over lifetime (MWh)
    total_cost_npv: float  # NPV of CAPEX + OPEX (EUR)


def calculate_lcoe(
    capex_per_kw: float,
    capacity_kw: float,
    nr_turbines: int,
    lifetime: int,
    discount_rate: float,
    annual_opex: float,
    annual_energy_mwh: float,
) -> LCOEResult:
    """Calculate the Levelised Cost of Energy (LCOE).

    LCOE = NPV(costs) / NPV(energy)
    NPV = sum over years of value / (1+r)^year

    CAPEX is incurred at year 0 (no discounting).
    OPEX and energy are incurred from year 1 to year `lifetime`.

    Args:
        capex_per_kw: Capital expenditure per kW of installed capacity (EUR/kW).
        capacity_kw: Rated capacity per turbine (kW).
        nr_turbines: Number of turbines.
        lifetime: Project lifetime in years.
        discount_rate: Discount rate (e.g. 0.08 for 8%).
        annual_opex: Annual operational expenditure (EUR/year) — total effort.
        annual_energy_mwh: Annual energy production (MWh/year) for the whole farm.

    Returns:
        LCOEResult with LCOE in EUR/MWh and component NPVs.
    """
    # CAPEX at year 0
    capex_total = capex_per_kw * capacity_kw * nr_turbines

    # NPV of OPEX (years 1..lifetime)
    opex_npv = 0.0
    for year in range(1, lifetime + 1):
        opex_npv += annual_opex / (1.0 + discount_rate) ** year

    # NPV of energy production (years 1..lifetime)
    energy_npv = 0.0
    for year in range(1, lifetime + 1):
        energy_npv += annual_energy_mwh / (1.0 + discount_rate) ** year

    # Total cost NPV
    total_cost_npv = capex_total + opex_npv

    # LCOE
    lcoe = total_cost_npv / energy_npv if energy_npv > 0 else 0.0

    return LCOEResult(
        lcoe=lcoe,
        capex_total=capex_total,
        opex_total_npv=opex_npv,
        energy_total_npv=energy_npv,
        total_cost_npv=total_cost_npv,
    )
