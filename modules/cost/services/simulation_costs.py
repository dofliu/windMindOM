"""仿真風場的收入與運維支出（WMOM-20260504-11，DEC-20261127-02）。

兩件事：

1. **收入與少收的錢不進帳本，由運轉狀態紀錄算**：發電量、計畫 / 非計畫停機少發的電已經記在監控的
   ``availability_hourly``（可用率也是由它算，DEC-20261126-04）。這裡只負責乘上電價——同一份紀錄、
   同一個時間基準（風場時鐘），不會兩邊對不上。
2. **工單完工時把支出寫進帳本**（``cost_ledger_entries``，``source_type=work_order``）：
   - 人工（``labour``）＝實際工時 × 人數 × 每小時人事費。
   - 料件（``material``）＝修掉的故障對應的 K13 修復等級的料件費；那張工單已經有領料單時不另算
     （領料單出庫時已經寫過帳，``MaterialRequestRepository.dispatch_request``）。
   - 每張工單只寫一次（重複完工、簽核退回再完工都不重寫）。

修復等級（``data/z72_repair_classes.json``）是假設值；K13 是 4 MW 離岸參考，Z72 2 MW 陸域的實際成本可能
較低。帳本只給管理端，不對外。

3. **固定成本與吊車（WMOM-20261127-02，DEC-20261127-08）**：駐場技師的年薪與工程車、工具這類設備的年費是
   固定成本（``fixed_costs``），依風場時鐘實際運轉的天數攤（不進帳本，和收入一樣由運轉狀態紀錄的時數算）；
   技師是領年薪的，工單上的工時只記錄、**不另算支出**（``summarize`` 把工單的人工分錄當成已含在人員固定成本，
   K13 的成本引擎也是這樣：時薪 0、技師年薪是固定成本）。要拆大件（主軸承、發電機）的修復等級完工時，另記一筆
   吊車動員（``equipment``）。假設值在 ``data/z72_onshore_costs.json``。
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence
from uuid import UUID

from modules.cost.repository.cost_ledger import (
    CostLedgerCategory,
    CostLedgerEntry,
    CostLedgerSourceType,
    CostLedgerStatus,
)

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPAIR_CLASSES_PATH = _DATA_DIR / "z72_repair_classes.json"
ONSHORE_COSTS_PATH = _DATA_DIR / "z72_onshore_costs.json"
FTC_PATH = _DATA_DIR / "demo" / "k13_fault_types_wt.json"

# 每位技師一年的有效工時（小時）：農場只給年薪（K13 的 tech_hourly_rate 是 0）時，用年薪 ÷ 這個數換算時薪
WORKING_HOURS_PER_YEAR = 1800.0
# 爬塔作業至少兩人：工單沒寫人數、也沒有修復等級可查時的人數
MIN_CREW = 2
_CENT = Decimal("0.01")
# 算進支出的帳本類別
EXPENSE_CATEGORIES = (CostLedgerCategory.MATERIAL, CostLedgerCategory.LABOUR, CostLedgerCategory.EQUIPMENT)


@dataclass(frozen=True)
class FarmRates:
    """一座風場的電價與人事費率。

    Attributes:
        farm_id: 風場 ID。
        currency: 幣別（農場成本設定的 ``currency``，預設 EUR）。
        kwh_price: 電價（每 kWh）。
        hourly_labour_rate: 每位技師每小時的人事費。
        source: 參數從哪裡來（``farm_overlay`` / ``registry_derived`` / ``k13_fallback``）。
    """

    farm_id: str
    currency: str
    kwh_price: float
    hourly_labour_rate: float
    source: str

    def to_dict(self) -> Dict[str, object]:
        """給 API 用的 dict。"""
        return {"farm_id": self.farm_id, "currency": self.currency, "kwh_price": self.kwh_price,
                "hourly_labour_rate": round(self.hourly_labour_rate, 2), "source": self.source}


def farm_rates(farm_id: str, farm_registry: object = None) -> FarmRates:
    """讀一座風場的電價與人事費率（K13 為底、農場的 ``cost_inputs.json`` 覆寫）。

    Args:
        farm_id: 風場 ID（與監控的 farm registry 一致）。
        farm_registry: 測試用；預設由成本模組自己找。

    Returns:
        費率。
    """
    from modules.cost.adapter import _load_cost_inputs_json, load_engine_params_from_farm

    params, meta = load_engine_params_from_farm(farm_id, farm_registry=farm_registry)
    wind_farm = params.wind_farm
    hourly = float(wind_farm.tech_hourly_rate or 0.0)
    if hourly <= 0:
        salary = float(wind_farm.tech_yearly_salary or 0.0)
        if meta.source == "registry_derived":
            # 監控登錄的風場（仿真的 Z72 陸域）沒有自己的成本設定：年薪用陸域的假設值，不用 K13 離岸的
            salary = float(_onshore()["staff"]["yearly_salary"])
        hourly = salary / WORKING_HOURS_PER_YEAR
    # 幣別跟電價同一層：只有用了農場自己的 cost_inputs.json 時才讀它的幣別，其餘是 K13 的 EUR
    inputs = (_load_cost_inputs_json(farm_id) or {}) if meta.source == "farm_overlay" else {}
    currency = str(inputs.get("currency") or "EUR")
    return FarmRates(farm_id=farm_id, currency=currency, kwh_price=float(wind_farm.kwh_price),
                     hourly_labour_rate=hourly, source=meta.source)


@dataclass(frozen=True)
class RepairClass:
    """一個修復等級（K13 FTC）。"""

    ftc: int
    description: str
    material_cost: float
    crew_size: int


@lru_cache(maxsize=1)
def _repair_tables() -> tuple[Dict[int, RepairClass], Dict[str, int], Dict[str, int]]:
    ftc_data = json.loads(FTC_PATH.read_text(encoding="utf-8"))
    classes = {int(row["ftc_nr"]): RepairClass(ftc=int(row["ftc_nr"]), description=str(row["description"]),
                                               material_cost=float(row["material_cost_euro"]),
                                               crew_size=int(row["crew_size"]))
               for row in ftc_data["maintenance_categories"]}
    mapping = json.loads(REPAIR_CLASSES_PATH.read_text(encoding="utf-8"))
    scenarios = {str(k): int(v) for k, v in mapping["scenarios"].items()}
    defaults = {str(k): int(v) for k, v in mapping["default_ftc_by_category"].items()}
    return classes, scenarios, defaults


def repair_class(scenario_id: str, category: Optional[str] = None) -> RepairClass:
    """一個故障情境修掉時的修復等級；沒列在表上的依類別給預設。

    Args:
        scenario_id: 故障情境 ID。
        category: 情境類別（``sensor_fault`` / ``real_fault`` / ``nuisance``），表上沒有時用。

    Returns:
        修復等級。
    """
    classes, scenarios, defaults = _repair_tables()
    ftc = scenarios.get(scenario_id)
    if ftc is None:
        ftc = defaults.get(category or "", defaults["real_fault"])
    return classes[ftc]


def _money(value: float) -> Decimal:
    return Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)


@lru_cache(maxsize=1)
def _onshore() -> Dict[str, object]:
    return json.loads(ONSHORE_COSTS_PATH.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class CraneCost:
    """一次吊車作業的費用（動員＋日租 × 天數），以及哪些修復等級要用。"""

    label: str
    mobilization: float
    day_rate: float
    days_per_job: float
    ftc: frozenset

    def per_job(self) -> float:
        """一次作業的費用。"""
        return self.mobilization + self.day_rate * self.days_per_job


def crane_cost() -> CraneCost:
    """吊車動員費（``data/z72_onshore_costs.json``，假設值）。"""
    data = _onshore()["crane"]
    return CraneCost(label=str(data["label_zh"]), mobilization=float(data["mobilization"]),
                     day_rate=float(data["day_rate"]), days_per_job=float(data["days_per_job"]),
                     ftc=frozenset(int(v) for v in data["ftc"]))


@dataclass(frozen=True)
class FixedCosts:
    """一座風場一年的固定成本。

    Attributes:
        technicians: 駐場技師人數。
        yearly_salary: 每人年薪。
        equipment: 設備年費（名稱, 每年）。
        source: ``farm_overlay``（風場自己的成本設定）或 ``onshore_default``（陸域假設值）。
    """

    technicians: int
    yearly_salary: float
    equipment: tuple
    source: str

    @property
    def staff_per_year(self) -> float:
        """人員一年。"""
        return self.technicians * self.yearly_salary

    @property
    def equipment_per_year(self) -> float:
        """設備一年。"""
        return float(sum(amount for _, amount in self.equipment))

    def for_days(self, days: float) -> Dict[str, object]:
        """攤到 ``days`` 天（給 API 用）。"""
        days = max(0.0, float(days))
        staff = round(self.staff_per_year * days / 365.0, 2)
        equipment = round(self.equipment_per_year * days / 365.0, 2)
        return {"days": round(days, 3), "staff": staff, "equipment": equipment,
                "total": round(staff + equipment, 2), "technicians": self.technicians,
                "yearly_salary": self.yearly_salary, "staff_per_year": round(self.staff_per_year, 2),
                "equipment_per_year": round(self.equipment_per_year, 2),
                "equipment_items": [{"name": name, "per_year": amount} for name, amount in self.equipment],
                "source": self.source}


def fixed_costs(farm_id: str, turbines: int, farm_registry: object = None) -> FixedCosts:
    """一座風場的固定成本：駐場技師（人數 × 年薪）與設備年費。

    風場的 ``cost_inputs.json`` 有 ``tech_yearly_salary`` / ``tech_count.year`` 時用風場的；其餘用陸域假設值
    （每台機組 ``technicians_per_turbine`` 人、至少 ``min_technicians`` 人）。

    Args:
        farm_id: 風場 ID。
        turbines: 機組數。
        farm_registry: 同 ``farm_rates``。

    Returns:
        固定成本。
    """
    from modules.cost.adapter import _load_cost_inputs_json, load_engine_params_from_farm

    staff = _onshore()["staff"]
    salary = float(staff["yearly_salary"])
    count = max(int(staff["min_technicians"]), math.ceil(max(0, turbines) * float(staff["technicians_per_turbine"])))
    source = "onshore_default"
    _params, meta = load_engine_params_from_farm(farm_id, farm_registry=farm_registry)
    if meta.source == "farm_overlay":
        overrides = (_load_cost_inputs_json(farm_id) or {}).get("wind_farm_overrides") or {}
        if overrides.get("tech_yearly_salary"):
            salary, source = float(overrides["tech_yearly_salary"]), "farm_overlay"
        tech_count = overrides.get("tech_count")
        if isinstance(tech_count, dict) and tech_count.get("year"):
            count, source = int(tech_count["year"]), "farm_overlay"
    equipment = tuple((str(item["label_zh"]), float(item["per_year"])) for item in _onshore()["equipment_fixed"])
    return FixedCosts(technicians=count, yearly_salary=salary, equipment=equipment, source=source)


def recorded_farm_days(availability: Mapping[str, object]) -> float:
    """運轉狀態紀錄涵蓋了幾天（全場的紀錄時數 ÷ 有紀錄的機組數 ÷ 24）：固定成本照這個天數攤。"""
    farm = availability.get("farm") or {}
    turbines = availability.get("turbines") or []
    hours = float(farm.get("recorded_hours", 0.0) or 0.0)  # type: ignore[union-attr]
    count = len(turbines)  # type: ignore[arg-type]
    return hours / count / 24.0 if count else 0.0


def work_order_cost_entries(*, farm_id: str, work_order_id: UUID, business_key: str,
                            actual_hours: Optional[float], crew_size: Optional[int],
                            repaired: Sequence[RepairClass], has_material_requests: bool,
                            rates: FarmRates, moment: datetime,
                            crane: Optional[CraneCost] = None) -> List[CostLedgerEntry]:
    """一張完工的工單要寫進帳本的支出。

    Args:
        farm_id: 風場 ID。
        work_order_id: 工單 ID（帳本的 ``source_event_id``）。
        business_key: 工單編號（寫進備註）。
        actual_hours: 實際工時；沒有就不記人工。
        crew_size: 工單上的人數。
        repaired: 這張工單修掉的故障的修復等級。
        has_material_requests: 這張工單有沒有領料單（有的話料件已由領料出庫入帳）。
        rates: 風場的費率。
        moment: 入帳時間（風場時鐘）。
        crane: 吊車動員費；None＝讀 ``data/z72_onshore_costs.json``。

    Returns:
        帳本分錄（都是 confirmed）；沒有東西要記時是空的。人工分錄照樣寫（記錄工時），但技師是領年薪的，
        ``summarize`` 給了固定成本時不把它算進支出。
    """
    entries: List[CostLedgerEntry] = []
    people = max([crew_size or 0, MIN_CREW] + [cls.crew_size for cls in repaired])
    hours = float(actual_hours or 0.0)
    if hours > 0 and rates.hourly_labour_rate > 0:
        entries.append(CostLedgerEntry(
            farm_id=farm_id, category=CostLedgerCategory.LABOUR,
            amount=_money(hours * people * rates.hourly_labour_rate),
            source_event_id=work_order_id, source_type=CostLedgerSourceType.WORK_ORDER,
            locked_unit_cost=_money(rates.hourly_labour_rate),
            status=CostLedgerStatus.CONFIRMED, recorded_at=moment, confirmed_at=moment,
            note=f"{business_key} 人工 {hours:g} 小時 × {people} 人"))
    if not has_material_requests:
        for cls in repaired:
            if cls.material_cost <= 0:
                continue
            entries.append(CostLedgerEntry(
                farm_id=farm_id, category=CostLedgerCategory.MATERIAL, amount=_money(cls.material_cost),
                source_event_id=work_order_id, source_type=CostLedgerSourceType.WORK_ORDER,
                status=CostLedgerStatus.CONFIRMED, recorded_at=moment, confirmed_at=moment,
                note=f"{business_key} 料件（修復等級 {cls.ftc}：{cls.description}）"))
    crane = crane if crane is not None else crane_cost()
    heavy = sorted({cls.ftc for cls in repaired if cls.ftc in crane.ftc})
    if heavy:
        # 要拆大件的修復：一張工單一次吊車作業（不論修了幾個）
        entries.append(CostLedgerEntry(
            farm_id=farm_id, category=CostLedgerCategory.EQUIPMENT, amount=_money(crane.per_job()),
            source_event_id=work_order_id, source_type=CostLedgerSourceType.WORK_ORDER,
            status=CostLedgerStatus.CONFIRMED, recorded_at=moment, confirmed_at=moment,
            note=(f"{business_key} 吊車動員（修復等級 {'、'.join(str(f) for f in heavy)}；動員 "
                  f"{crane.mobilization:g} ＋ 每天 {crane.day_rate:g} × {crane.days_per_job:g} 天）")))
    return entries


def revenue(energy: Mapping[str, object], rates: FarmRates) -> Dict[str, float]:
    """發電收入與停機少收的錢。

    Args:
        energy: 有 ``energy_kwh`` / ``lost_planned_kwh`` / ``lost_unplanned_kwh`` 的 dict（運轉狀態紀錄的
            合計，``OmLoop.availability`` 的格式）。
        rates: 風場的費率。

    Returns:
        ``{"revenue", "lost_planned", "lost_unplanned"}``（幣別同 ``rates.currency``）。
    """
    def amount(key: str) -> float:
        return round(float(energy.get(key, 0.0) or 0.0) * rates.kwh_price, 2)

    return {"revenue": amount("energy_kwh"), "lost_planned": amount("lost_planned_kwh"),
            "lost_unplanned": amount("lost_unplanned_kwh")}


def summarize(availability: Mapping[str, object], expenses: Mapping[str, Decimal],
              rates: FarmRates, fixed: Optional[FixedCosts] = None,
              work_order_labour: Decimal = Decimal("0")) -> Dict[str, object]:
    """一段時間的收支：收入、少收的錢（每台機組與全場）、支出、淨額。

    Args:
        availability: ``OmLoop.availability`` 的結果（``turbines`` 與 ``farm``）。
        expenses: 帳本各類支出合計（類別 → 金額）。
        rates: 風場的費率。
        fixed: 固定成本；給了的話依運轉狀態紀錄涵蓋的天數攤進人工（技師年薪）與設備（年費），而且帳本裡
            工單的人工分錄（``work_order_labour``）不另算——技師領年薪，工時已經含在人員固定成本裡。
        work_order_labour: 帳本裡工單的人工分錄合計（``source_type=work_order``）。

    Returns:
        給 API 用的 dict（``expenses`` 的人工、設備含固定成本；``fixed_costs`` 是攤的明細；
        ``work_order_labour`` 是工單工時的人工，``counted`` 表示有沒有算進支出）。
    """
    farm = availability.get("farm") or {}
    turbines: Iterable[Mapping[str, object]] = availability.get("turbines") or []  # type: ignore[assignment]
    income = revenue(farm, rates)  # type: ignore[arg-type]
    # 少收的錢由運轉狀態紀錄算（上面的 lost_revenue），帳本的 revenue_loss 不算支出，免得算兩次
    spent = {cat.value: float(expenses.get(cat, Decimal("0"))) for cat in EXPENSE_CATEGORIES}
    fixed_part: Optional[Dict[str, object]] = None
    if fixed is not None:
        fixed_part = fixed.for_days(recorded_farm_days(availability))
        labour = CostLedgerCategory.LABOUR.value
        spent[labour] = round(spent[labour] - float(work_order_labour) + float(fixed_part["staff"]), 2)
        equipment = CostLedgerCategory.EQUIPMENT.value
        spent[equipment] = round(spent[equipment] + float(fixed_part["equipment"]), 2)
    total_expense = round(sum(spent.values()), 2)
    return {
        "rates": rates.to_dict(),
        "energy_kwh": round(float(farm.get("energy_kwh", 0.0) or 0.0), 1),  # type: ignore[union-attr]
        "revenue": income["revenue"],
        "lost_revenue": {"planned": income["lost_planned"], "unplanned": income["lost_unplanned"]},
        "expenses": {**spent, "total": total_expense},
        "fixed_costs": fixed_part,
        "work_order_labour": {"amount": round(float(work_order_labour), 2), "counted": fixed is None},
        "net": round(income["revenue"] - total_expense, 2),
        "turbines": [{"turbine_id": row.get("turbine_id"),
                      "energy_kwh": round(float(row.get("energy_kwh", 0.0) or 0.0), 1),
                      **revenue(row, rates)} for row in turbines],
    }
