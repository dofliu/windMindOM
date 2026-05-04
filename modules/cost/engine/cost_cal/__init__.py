"""CostCal — Offshore wind farm O&M cost calculation engine.

This module replicates the ECN O&M Tool V5 cost calculation logic:
- Corrective maintenance (WT + BOP components)
- Preventive maintenance
- Fixed yearly costs
- Revenue loss from downtime
- Overall availability metrics
"""

from modules.cost.engine.cost_cal.aggregator import run_cost_calculation, CostCalResult

__all__ = [
    "run_cost_calculation",
    "CostCalResult",
]
