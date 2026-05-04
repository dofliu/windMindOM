"""Data classes for the CostCal engine — pure Python, no ORM dependency."""

from dataclasses import dataclass, field


SEASONS = ["winter", "spring", "summer", "autumn"]


@dataclass
class WindFarmParams:
    """Wind farm configuration parameters."""
    nr_turbines: int
    capacity_kw: float
    investment_cost_per_kw: float
    kwh_price: float
    lifetime_years: int
    farm_efficiency: float
    capacity_factors: dict[str, float]  # season -> CF
    season_weights: dict[str, float]  # season -> weight (each 0.25 for equal)
    tech_hourly_rate: float
    tech_yearly_salary: float
    tech_count: dict[str, int]  # season -> nr technicians


@dataclass
class FTCParams:
    """Fault type class repair parameters."""
    ftc_number: int
    repair_type: str  # "corrective" or "cbm"
    material_cost_pct: float
    material_cost_euro: float
    crew_size: int
    repair_hours: float
    logistics_hours: float
    organization_hours: float
    long_working_day: bool
    # Optional stochastic bounds for Monte Carlo
    repair_hours_min: float | None = None
    repair_hours_max: float | None = None
    logistics_hours_min: float | None = None
    logistics_hours_max: float | None = None


@dataclass
class MCParams:
    """Maintenance category parameters."""
    category_index: int
    probability: float
    equipment_index: int | None  # index into equipment list (1-based)
    nr_additional_inspections: int
    ftc: FTCParams


@dataclass
class ComponentParams:
    """Component failure parameters."""
    component_name: str
    component_code: str
    component_type: str  # "WT" or "BOP"
    annual_failure_freq: float
    maintenance_categories: list[MCParams]
    # Optional stochastic bounds for Monte Carlo
    freq_min: float | None = None
    freq_ml: float | None = None
    freq_max: float | None = None


@dataclass
class EquipmentParams:
    """Equipment parameters."""
    equipment_index: int  # 1-based
    name: str
    ww_normal_index: int | None  # weather window index for normal day
    ww_long_index: int | None  # weather window index for long day
    nr_available: int
    logistic_hours: float
    travel_hours: float
    cost_type: str  # "day" or "mission"
    day_rate: float
    mob_cost: float
    mission_rate: float
    # Optional stochastic bounds for Monte Carlo
    day_rate_min: float | None = None
    day_rate_max: float | None = None
    mob_cost_min: float | None = None
    mob_cost_max: float | None = None


@dataclass
class WaitingTimePolynomial:
    """Waiting time polynomial coefficients for a weather window + season."""
    window_index: int  # 0-based index in definition_sheet
    season: str
    # T_wait = c0 + c1*T + c2*T^2 + c3*T^3
    c0: float = 0.0
    c1: float = 0.0
    c2: float = 0.0
    c3: float = 0.0

    def evaluate(self, mission_time: float) -> float:
        """Evaluate the waiting time polynomial at a given mission time."""
        t = mission_time
        result = self.c0 + self.c1 * t + self.c2 * t**2 + self.c3 * t**3
        return max(0.0, result)


@dataclass
class PMParams:
    """Preventive maintenance schedule parameters."""
    description: str
    pm_type: str  # "WT" or "BOP"
    nr_occurrences: int  # during lifetime
    duration_hours: float
    crew_size: int
    material_cost: float
    equipment_index: int | None  # 1-based
    ww_index: int | None  # weather window index (0-based)
    travel_hours: float
    long_working_day: bool
    pct_farm_shutdown: float
    season_distribution: dict[str, float]  # season -> fraction


@dataclass
class FixedCostParams:
    """Fixed yearly cost parameters."""
    description: str
    annual_cost: float
    season_distribution: dict[str, float]  # season -> fraction


@dataclass
class SeasonResult:
    """Cost results for a single season."""
    season: str
    corrective_wt_material: float = 0.0
    corrective_wt_labour: float = 0.0
    corrective_wt_equipment: float = 0.0
    corrective_wt_mob: float = 0.0
    corrective_wt_revenue_loss: float = 0.0
    corrective_wt_downtime: float = 0.0  # total turbine-hours

    corrective_bop_material: float = 0.0
    corrective_bop_labour: float = 0.0
    corrective_bop_equipment: float = 0.0
    corrective_bop_mob: float = 0.0
    corrective_bop_revenue_loss: float = 0.0
    corrective_bop_downtime: float = 0.0

    preventive_material: float = 0.0
    preventive_labour: float = 0.0
    preventive_equipment: float = 0.0
    preventive_mob: float = 0.0
    preventive_revenue_loss: float = 0.0
    preventive_downtime: float = 0.0

    fixed_cost: float = 0.0

    @property
    def corrective_wt_total(self) -> float:
        return (
            self.corrective_wt_material
            + self.corrective_wt_labour
            + self.corrective_wt_equipment
            + self.corrective_wt_mob
        )

    @property
    def corrective_bop_total(self) -> float:
        return (
            self.corrective_bop_material
            + self.corrective_bop_labour
            + self.corrective_bop_equipment
            + self.corrective_bop_mob
        )

    @property
    def preventive_total(self) -> float:
        return (
            self.preventive_material
            + self.preventive_labour
            + self.preventive_equipment
            + self.preventive_mob
        )

    @property
    def total_revenue_loss(self) -> float:
        return (
            self.corrective_wt_revenue_loss
            + self.corrective_bop_revenue_loss
            + self.preventive_revenue_loss
        )

    @property
    def total_repair_cost(self) -> float:
        return (
            self.corrective_wt_total
            + self.corrective_bop_total
            + self.preventive_total
            + self.fixed_cost
        )

    @property
    def total_downtime(self) -> float:
        """Total turbine-downtime-hours for this season."""
        return (
            self.corrective_wt_downtime
            + self.corrective_bop_downtime
            + self.preventive_downtime
        )

    @property
    def total_effort(self) -> float:
        return self.total_repair_cost + self.total_revenue_loss
