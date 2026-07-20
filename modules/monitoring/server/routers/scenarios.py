"""情境保存/調閱 API（DEC-20260718-01 #4，WMOM-20260719-02）。

情境＝一個以 ``config_json.kind == "scenario"`` 標記的專屬 session（見 ``storage``）。
批次生成（``/api/config/simulation/generate-bulk`` 帶 ``name``）會把資料寫進該 session、
與 Live/其他歷史隔離；本 router 讓使用者事後把它們列出來、調某一個回來觀察、或刪除。

- ``GET  /api/scenarios``                                     列出已保存情境（新到舊）
- ``GET  /api/scenarios/{id}``                                單一情境詮釋資料
- ``GET  /api/scenarios/{id}/summary``                        情境物理摘要（每台機組 + 風場層）
- ``GET  /api/scenarios/{id}/turbines/{turbine_id}/history``  某情境某機組的資料（隔離調閱）
- ``DELETE /api/scenarios/{id}``                              刪除情境（含資料列）
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from modules.auth.dependencies import require_authenticated, require_role
from modules.auth.roles import Role

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])

# 情境 session 未存 rated_power_kw（generate_bulk 只傳 data_source/turbine_count/config），
# 容量因數的額定功率以第一個客戶機型 Z72-2000-MV（2000 kW）為預設；回傳帶 ratedPowerKw 讓
# 這個假設對前端透明（日後情境若回填自身額定功率則優先採用，見 _scenario_rated_power_kw）。
DEFAULT_RATED_POWER_KW = 2000.0
# 故障事件計數的撈取上限（事件無 session_id，只能靠時間窗；見 summary 端點 eventsByTimeWindow）。
_FAULT_EVENT_QUERY_LIMIT = 5000


def get_broker():
    """Return the shared DataBroker instance from the main app module."""
    from server.app import broker
    return broker


# ── 情境摘要 response models（A0，DEC-20260720-02）─────────────────────────────

class ComponentLoads(BaseModel):
    """四個結構部位的量：塔架前後（fore-aft）/ 塔架左右（side-side）/ 葉片揮舞 / 葉片擺振。

    損傷（末值）、極限負載（瞬時彎矩 MAX）、DEL 三者皆以這四個部位表示，共用此結構。
    缺鍵時該部位為 None（舊資料或該物理量未落地）。
    """
    towerFa: Optional[float] = None
    towerSs: Optional[float] = None
    bladeFlap: Optional[float] = None
    bladeEdge: Optional[float] = None


class ScenarioTurbineSummary(BaseModel):
    """單一機組在該情境的物理摘要。"""
    turbineId: str
    samples: int                       # 樣本步數（COUNT）
    avgPowerKw: float
    maxPowerKw: float
    energyKwh: float                   # avgPowerKw × 總時數（samples × timeStep / 3600）
    capacityFactor: float              # avgPowerKw / ratedPowerKw（0..1）
    availability: float                # 生產步數 / 樣本步數（tur_state==6 佔比，0..1）
    productionHours: Optional[float] = None   # WLOD_ProdHours 末值（物理模型自身的生產時數計數）
    cumulativeDamage: ComponentLoads          # 累積損傷末值（情境結束時）
    worstDamage: Optional[float] = None       # 四部位損傷取最大（最嚴重部位）
    minRulHours: Optional[float] = None       # 最終剩餘壽命（最壞）
    extremeLoad: ComponentLoads               # 瞬時彎矩 MAX（極限負載）
    damageEquivalentLoad: ComponentLoads      # DEL
    faultEvents: int                          # 該機組在情境時間窗內的 fault 事件數


class ScenarioFarmSummary(BaseModel):
    """風場層 rollup（各機組指標加總 / 平均 / 取最嚴重）。"""
    turbineCount: int
    totalEnergyKwh: float
    avgCapacityFactor: float
    avgAvailability: float
    totalFaultEvents: int
    maxTurbinePowerKw: float
    worstDamage: Optional[float] = None
    worstDamageTurbineId: Optional[str] = None
    minRulHours: Optional[float] = None
    minRulTurbineId: Optional[str] = None


class ScenarioSummary(BaseModel):
    """情境物理摘要端點回傳：情境詮釋 + 風場層 rollup + 每台機組明細。"""
    scenarioId: int
    name: Optional[str] = None
    windProfile: Optional[str] = None
    durationHours: Optional[float] = None
    timeStepSeconds: float
    ratedPowerKw: float                # 容量因數分母（透明化預設假設，見 DEFAULT_RATED_POWER_KW）
    faultsInjected: Optional[int] = None
    # 故障事件數走時間窗（history_events 無 session_id）→ 可能混入時間窗重疊的其他情境，
    # 比照 history 端點以此旗標提醒前端（readings/物理聚合走 session_id 隔離，不受影響）。
    eventsByTimeWindow: bool
    farm: ScenarioFarmSummary
    turbines: List[ScenarioTurbineSummary]


# ── 純函式聚合邏輯（可單元測試，不經 HTTP/DB）─────────────────────────────────

def _round(value: Optional[float], digits: int) -> Optional[float]:
    """四捨五入；None 原樣回傳（保留缺值語意）。"""
    return None if value is None else round(value, digits)


def _max_ignore_none(values: List[Optional[float]]) -> Optional[float]:
    present = [v for v in values if v is not None]
    return max(present) if present else None


def _scenario_rated_power_kw(scenario: dict) -> float:
    """情境的額定功率（容量因數分母）：session 若有 rated_power_kw 則採用，否則預設 Z72 2000 kW。"""
    rated = scenario.get("rated_power_kw")
    try:
        rated_f = float(rated) if rated is not None else 0.0
    except (TypeError, ValueError):
        rated_f = 0.0
    return rated_f if rated_f > 0 else DEFAULT_RATED_POWER_KW


def _fault_counts_by_turbine(events: List[dict]) -> Dict[str, int]:
    """從事件清單數出每台機組的 fault 事件數（只計有 turbine_id 的 fault，忽略 farm-wide）。"""
    counts: Dict[str, int] = {}
    for ev in events:
        if ev.get("event_type") == "fault":
            tid = ev.get("turbine_id")
            if tid:
                counts[tid] = counts.get(tid, 0) + 1
    return counts


def _build_turbine_summary(agg: dict, time_step_s: float, rated_power_kw: float,
                           fault_events: int) -> ScenarioTurbineSummary:
    """把 storage 的一列聚合（MW/原始物理量）換算成機組摘要（kW/能量/容量因數/可用率）。

    純函式（不碰 DB/HTTP）便於 mutation-verify 換算數學。功率欄位（avg/max_power_mw）為 MW，
    ×1000 轉 kW；能量＝平均功率 × 總時數（樣本步數 × time_step / 3600）；容量因數＝平均功率 /
    額定功率；可用率＝生產步數（tur_state==6）/ 樣本步數。
    """
    n = int(agg.get("n") or 0)
    avg_power_kw = (agg.get("avg_power_mw") or 0.0) * 1000.0
    max_power_kw = (agg.get("max_power_mw") or 0.0) * 1000.0
    total_hours = n * time_step_s / 3600.0
    energy_kwh = avg_power_kw * total_hours
    capacity_factor = avg_power_kw / rated_power_kw if rated_power_kw > 0 else 0.0
    production_steps = int(agg.get("production_steps") or 0)
    availability = production_steps / n if n > 0 else 0.0

    damage = ComponentLoads(
        towerFa=agg.get("dmg_tower_fa"),
        towerSs=agg.get("dmg_tower_ss"),
        bladeFlap=agg.get("dmg_blade_flap"),
        bladeEdge=agg.get("dmg_blade_edge"),
    )
    worst_damage = _max_ignore_none(
        [damage.towerFa, damage.towerSs, damage.bladeFlap, damage.bladeEdge]
    )
    return ScenarioTurbineSummary(
        turbineId=agg["turbine_id"],
        samples=n,
        avgPowerKw=round(avg_power_kw, 2),
        maxPowerKw=round(max_power_kw, 2),
        energyKwh=round(energy_kwh, 2),
        capacityFactor=round(capacity_factor, 4),
        availability=round(availability, 4),
        productionHours=_round(agg.get("prod_hours"), 3),
        cumulativeDamage=damage,
        worstDamage=worst_damage,
        minRulHours=_round(agg.get("min_rul_hours"), 1),
        extremeLoad=ComponentLoads(
            towerFa=agg.get("max_tower_fa_moment"),
            towerSs=agg.get("max_tower_ss_moment"),
            bladeFlap=agg.get("max_blade_flap_moment"),
            bladeEdge=agg.get("max_blade_edge_moment"),
        ),
        damageEquivalentLoad=ComponentLoads(
            towerFa=agg.get("del_tower_fa"),
            towerSs=agg.get("del_tower_ss"),
            bladeFlap=agg.get("del_blade_flap"),
            bladeEdge=agg.get("del_blade_edge"),
        ),
        faultEvents=fault_events,
    )


def _build_farm_summary(turbines: List[ScenarioTurbineSummary],
                        turbine_count: Optional[int]) -> ScenarioFarmSummary:
    """各機組摘要 → 風場層 rollup（總能量 Σ、平均容量因數/可用率、最嚴重損傷/最小 RUL 取極值）。"""
    if not turbines:
        return ScenarioFarmSummary(
            turbineCount=turbine_count or 0,
            totalEnergyKwh=0.0, avgCapacityFactor=0.0, avgAvailability=0.0,
            totalFaultEvents=0, maxTurbinePowerKw=0.0,
        )
    worst_damage_t = max(
        (t for t in turbines if t.worstDamage is not None),
        key=lambda t: t.worstDamage, default=None,
    )
    min_rul_t = min(
        (t for t in turbines if t.minRulHours is not None),
        key=lambda t: t.minRulHours, default=None,
    )
    count = len(turbines)
    return ScenarioFarmSummary(
        turbineCount=turbine_count or count,
        totalEnergyKwh=round(sum(t.energyKwh for t in turbines), 2),
        avgCapacityFactor=round(sum(t.capacityFactor for t in turbines) / count, 4),
        avgAvailability=round(sum(t.availability for t in turbines) / count, 4),
        totalFaultEvents=sum(t.faultEvents for t in turbines),
        maxTurbinePowerKw=round(max(t.maxPowerKw for t in turbines), 2),
        worstDamage=worst_damage_t.worstDamage if worst_damage_t else None,
        worstDamageTurbineId=worst_damage_t.turbineId if worst_damage_t else None,
        minRulHours=min_rul_t.minRulHours if min_rul_t else None,
        minRulTurbineId=min_rul_t.turbineId if min_rul_t else None,
    )


@router.get(
    "",
    # 檢視＝任何登入者
    dependencies=[Depends(require_authenticated())],
)
async def list_scenarios(limit: int = 50):
    """列出已保存情境（config_json.kind == "scenario"），最新在前。"""
    b = get_broker()
    return {"scenarios": b.storage.list_scenarios(limit=limit)}


@router.get(
    "/{scenario_id}",
    # 檢視＝任何登入者
    dependencies=[Depends(require_authenticated())],
)
async def get_scenario(scenario_id: int):
    """回傳單一情境的詮釋資料（名稱/風況/時長/故障排程/統計/時間窗）。"""
    b = get_broker()
    sc = b.storage.get_scenario(scenario_id)
    if not sc:
        raise HTTPException(404, f"Scenario {scenario_id} not found")
    return sc


@router.get(
    "/{scenario_id}/summary",
    # 檢視＝任何登入者（比照 list/get scenario）
    dependencies=[Depends(require_authenticated())],
)
async def get_scenario_summary(scenario_id: int) -> ScenarioSummary:
    """情境物理摘要：每台機組（發電量/容量因數/可用率/累積損傷/最小 RUL/極限負載/DEL/故障數）
    + 風場層 rollup。純讀取該情境 session 的資料（session 隔離）聚合而成（DEC-20260720-02 A0），
    是 A1（同情境內比較）/A2（跨情境比較）的資料基礎，本身即可獨立支撐前端情境總覽。

    故障事件數走情境 sim 時間窗（``history_events`` 無 session_id）→ 回傳帶 ``eventsByTimeWindow``
    旗標提醒此計數可能混入時間窗重疊的其他情境（物理聚合走 session_id 隔離，不受影響）。
    """
    b = get_broker()
    scenario = b.storage.get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(404, f"Scenario {scenario_id} not found")

    config = scenario.get("config") if isinstance(scenario.get("config"), dict) else {}
    config = config or {}
    time_step = float(config.get("time_step") or 10.0)
    rated_power_kw = _scenario_rated_power_kw(scenario)

    aggregates = b.storage.scenario_turbine_aggregates(scenario_id)

    # 故障事件計數：走情境 sim 時間窗（config.sim_start..sim_end，缺則退回 session started/ended）。
    start = config.get("sim_start") or scenario.get("started_at")
    end = config.get("sim_end") or scenario.get("ended_at")
    events = (
        b.get_history_events(turbine_id=None, start=start, end=end,
                             limit=_FAULT_EVENT_QUERY_LIMIT)
        if start and end else []
    )
    fault_counts = _fault_counts_by_turbine(events)

    turbines = [
        _build_turbine_summary(agg, time_step, rated_power_kw,
                               fault_counts.get(agg["turbine_id"], 0))
        for agg in aggregates
    ]
    farm = _build_farm_summary(turbines, scenario.get("turbine_count"))

    return ScenarioSummary(
        scenarioId=scenario_id,
        name=config.get("name"),
        windProfile=config.get("wind_profile"),
        durationHours=config.get("duration_hours"),
        timeStepSeconds=time_step,
        ratedPowerKw=rated_power_kw,
        faultsInjected=config.get("faults_injected"),
        eventsByTimeWindow=True,
        farm=farm,
        turbines=turbines,
    )


@router.get(
    "/{scenario_id}/turbines/{turbine_id}/history",
    # 檢視＝任何登入者
    dependencies=[Depends(require_authenticated())],
)
async def get_scenario_turbine_history(scenario_id: int, turbine_id: str, limit: int = 2000):
    """調閱某情境某機組的資料——只回該情境 session 的 turbine_data（與 Live/歷史隔離）。

    另附該情境模擬時間窗內的事件（故障注入等），供時間軸標記；窗未知時回空清單。

    ⚠️ 限制：``history_events`` 無 ``session_id`` 欄位，事件只能靠情境的
    ``sim_start..sim_end`` 時間窗撈取。因情境的 sim-time 皆從生成當下的 wall-clock 起算，
    **短時間內連續產生的情境時間窗會大幅重疊**，此時回傳的 ``events`` 可能混入其他情境的
    事件（``readings`` 走 session_id 隔離，不受影響）。徹底解法是為 ``history_events`` 補
    ``session_id``（見 DEC-20260719-01 trade-off）。故回傳帶 ``events_by_time_window`` 旗標
    提醒前端此清單非 session 隔離。
    """
    b = get_broker()
    sc = b.storage.get_scenario(scenario_id)
    if not sc:
        raise HTTPException(404, f"Scenario {scenario_id} not found")

    readings = b.get_history(turbine_id, limit=limit, session_id=scenario_id)

    cfg = sc.get("config", {}) if isinstance(sc.get("config"), dict) else {}
    start, end = cfg.get("sim_start"), cfg.get("sim_end")
    events = (
        b.get_history_events(turbine_id, start=start, end=end, limit=min(limit, 1000))
        if start and end else []
    )
    return {
        "scenario_id": scenario_id,
        "turbine_id": turbine_id,
        "readings": readings,            # 走 session_id 隔離
        "events": events,                # 走時間窗，非 session 隔離（見下旗標）
        "events_by_time_window": True,   # 提醒：events 可能混入時間窗重疊的其他情境
    }


@router.delete(
    "/{scenario_id}",
    # 刪除情境＝系統管理員（不可逆、會清 5 張表的資料列）——對齊 farms/config/modbus
    # 破壞性端點的既定慣例（皆 ADMIN）。
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def delete_scenario(scenario_id: int):
    """刪除情境 session 及其所有資料列；非情境 session 不受影響（回 404）。"""
    b = get_broker()
    deleted = b.storage.delete_scenario(scenario_id)
    if not deleted:
        raise HTTPException(404, f"Scenario {scenario_id} not found")
    return {"status": "deleted", "scenario_id": scenario_id}
