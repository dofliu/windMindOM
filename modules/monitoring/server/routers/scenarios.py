"""情境保存/調閱 API（DEC-20260718-01 #4，WMOM-20260719-02）。

情境＝一個以 ``config_json.kind == "scenario"`` 標記的專屬 session（見 ``storage``）。
批次生成（``/api/config/simulation/generate-bulk`` 帶 ``name``）會把資料寫進該 session、
與 Live/其他歷史隔離；本 router 讓使用者事後把它們列出來、調某一個回來觀察、或刪除。

- ``GET  /api/scenarios``                                     列出已保存情境（新到舊）
- ``GET  /api/scenarios/compare``                             跨情境摘要並排比較（A2 Part 1）
- ``GET  /api/scenarios/{id}``                                單一情境詮釋資料
- ``GET  /api/scenarios/{id}/summary``                        情境物理摘要（每台機組 + 風場層）
- ``GET  /api/scenarios/{id}/turbines``                       該情境每台機組最後一筆讀數（PR C Phase 1 掛載用）
- ``GET  /api/scenarios/{id}/farm-status``                    該情境風場層 KPI（PR C Phase 1 掛載用）
- ``GET  /api/scenarios/{id}/turbines/{turbine_id}/history``  某情境某機組的資料（隔離調閱）
- ``DELETE /api/scenarios/{id}``                              刪除情境（含資料列）
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from modules.auth.dependencies import require_authenticated, require_role
from modules.auth.roles import Role
from server.data_broker import _map_state
from server.models import FarmStatus, TurbineReading, TurbineStatus
from simulator.physics.fault_engine import FAULT_SCENARIOS

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])
logger = logging.getLogger(__name__)

# 容量因數的額定功率預設值。generate_bulk 現於建情境時就把 simulator 機型的 rated_power_kw 存進
# session（見 config.py），故正常情況會採用 session 值；此預設只在舊情境（未回填）/取值失敗時兜底，
# 取第一個客戶機型 Z72-2000-MV（2000 kW）。回傳帶 ratedPowerKw 讓實際採用值對前端透明。
DEFAULT_RATED_POWER_KW = 2000.0


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
    # 生產步數（tur_state==6）/ 樣本步數。刻意不叫 availability——與 reporting 模組
    # kpi_calculator.time_availability（1 − downtime/total）定義不同（本值把低風速正常待機也算成
    # 非生產），避免同 repo 一詞兩義。
    productionRate: float              # 0..1
    estopSteps: int                    # 緊急停機步數（tur_state==7；跳機訊號，DEC-20260720-02 指標）
    productionHours: Optional[float] = None   # WLOD_ProdHours 末值（物理模型自身的生產時數計數）
    cumulativeDamage: ComponentLoads          # 累積損傷末值（情境結束時，單調累積 → MAX）
    worstDamage: Optional[float] = None       # 四部位損傷取最大（最嚴重部位）
    rulHours: Optional[float] = None          # 情境結束時的剩餘壽命估計（最後一列；暖機不足 → None）
    extremeLoad: ComponentLoads               # 瞬時彎矩 MAX（情境中經歷的極限負載）
    damageEquivalentLoad: ComponentLoads      # DEL（情境結束時的最後一個 10 分鐘視窗值，非累積）
    faultEvents: int                          # 該機組在情境時間窗內的 fault 事件數


class ScenarioFarmSummary(BaseModel):
    """風場層 rollup（各機組指標加總 / 平均 / 取最嚴重）。"""
    turbineCount: int
    totalEnergyKwh: float
    avgCapacityFactor: float
    avgProductionRate: float
    totalFaultEvents: int
    maxTurbinePowerKw: float
    worstDamage: Optional[float] = None       # 各機組 worstDamage 取最大（最嚴重機組）
    worstDamageTurbineId: Optional[str] = None
    minRulHours: Optional[float] = None        # 各機組 rulHours 取最小（剩餘壽命最短＝最耗損機組）
    minRulTurbineId: Optional[str] = None


class ScenarioSummary(BaseModel):
    """情境物理摘要端點回傳：情境詮釋 + 風場層 rollup + 每台機組明細。"""
    scenarioId: int
    name: Optional[str] = None
    status: Optional[str] = None       # 情境生成狀態（config.status：ok / error）——error 時摘要僅涵蓋已寫入的部分資料
    windProfile: Optional[str] = None
    durationHours: Optional[float] = None
    timeStepSeconds: float
    ratedPowerKw: float                # 容量因數分母（實際採用值，見 DEFAULT_RATED_POWER_KW）
    faultsInjected: Optional[int] = None
    # 故障事件數走時間窗（history_events 無 session_id）→ 可能混入時間窗重疊的其他情境，
    # 比照 history 端點以此旗標提醒前端（readings/物理聚合走 session_id 隔離，不受影響）。
    eventsByTimeWindow: bool
    farm: ScenarioFarmSummary
    turbines: List[ScenarioTurbineSummary]


class ScenarioCompareResponse(BaseModel):
    """跨情境比較（A2 Part 1，DEC-20260720-02）：並排回傳多個情境的摘要。

    重用 A0（單情境摘要）的建構邏輯，依請求 ``ids`` 的順序回傳、不重複。是「摘要並排（長條/雷達）」
    的資料地基；相對時間對齊的時序疊圖與差異圖屬後續子任務，不在本端點範圍內。
    """
    scenarios: List[ScenarioSummary]


# ── 純函式聚合邏輯（可單元測試，不經 HTTP/DB）─────────────────────────────────

def _round(value: Optional[float], digits: int) -> Optional[float]:
    """四捨五入；None 原樣回傳（保留缺值語意）。"""
    return None if value is None else round(value, digits)


def _max_ignore_none(values: List[Optional[float]]) -> Optional[float]:
    """忽略 None 取最大值；全為 None（或空清單）回 None。"""
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


def _build_turbine_summary(agg: dict, time_step_s: float, rated_power_kw: float,
                           fault_events: int) -> ScenarioTurbineSummary:
    """把 storage 的一列聚合（MW/原始物理量）換算成機組摘要（kW/能量/容量因數/生產佔比）。

    純函式（不碰 DB/HTTP）便於 mutation-verify 換算數學。功率欄位（avg/max_power_mw）為 MW，
    ×1000 轉 kW；能量＝平均功率 × 總時數（樣本步數 × time_step / 3600）；容量因數＝平均功率 /
    額定功率；生產佔比＝生產步數（tur_state==6）/ 樣本步數。RUL/DEL 由 storage 取自末列（含
    sentinel 過濾），此處原樣帶出。
    """
    n = int(agg.get("n") or 0)
    avg_power_kw = (agg.get("avg_power_mw") or 0.0) * 1000.0
    max_power_kw = (agg.get("max_power_mw") or 0.0) * 1000.0
    total_hours = n * time_step_s / 3600.0
    energy_kwh = avg_power_kw * total_hours
    capacity_factor = avg_power_kw / rated_power_kw if rated_power_kw > 0 else 0.0
    production_steps = int(agg.get("production_steps") or 0)
    production_rate = production_steps / n if n > 0 else 0.0

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
        productionRate=round(production_rate, 4),
        estopSteps=int(agg.get("estop_steps") or 0),
        productionHours=_round(agg.get("prod_hours"), 3),
        cumulativeDamage=damage,
        worstDamage=worst_damage,
        rulHours=_round(agg.get("rul_hours"), 1),
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
            totalEnergyKwh=0.0, avgCapacityFactor=0.0, avgProductionRate=0.0,
            totalFaultEvents=0, maxTurbinePowerKw=0.0,
        )
    worst_damage_t = max(
        (t for t in turbines if t.worstDamage is not None),
        key=lambda t: t.worstDamage, default=None,
    )
    min_rul_t = min(
        (t for t in turbines if t.rulHours is not None),
        key=lambda t: t.rulHours, default=None,
    )
    count = len(turbines)
    return ScenarioFarmSummary(
        turbineCount=turbine_count or count,
        totalEnergyKwh=round(sum(t.energyKwh for t in turbines), 2),
        avgCapacityFactor=round(sum(t.capacityFactor for t in turbines) / count, 4),
        avgProductionRate=round(sum(t.productionRate for t in turbines) / count, 4),
        totalFaultEvents=sum(t.faultEvents for t in turbines),
        maxTurbinePowerKw=round(max(t.maxPowerKw for t in turbines), 2),
        worstDamage=worst_damage_t.worstDamage if worst_damage_t else None,
        worstDamageTurbineId=worst_damage_t.turbineId if worst_damage_t else None,
        minRulHours=min_rul_t.rulHours if min_rul_t else None,
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


# 跨情境比較的情境數量界線：DEC-20260720-02 設計決策載明「挑 2–3 情境」比較；下限 2（少於 2 談不上
# 比較），上限 5（留一點餘裕給更多情境並排，同時避免單次請求疊加過多長情境聚合掃描拖垮回應時間——
# 見 get_scenario_summary docstring 提及的「長情境可達分鐘級」）。
MIN_COMPARE_SCENARIOS = 2
MAX_COMPARE_SCENARIOS = 5


def _parse_compare_ids(ids: str) -> List[int]:
    """解析並驗證 `/compare` 端點的 ``ids`` query 參數：逗號分隔整數、去重保留首次出現順序、
    數量介於 [MIN_COMPARE_SCENARIOS, MAX_COMPARE_SCENARIOS]。純函式（不碰 DB/HTTP）便於單元測試。

    Args:
        ids: 逗號分隔的情境 id 字串，例如 ``"3,7,12"``。前後空白與空段落會被忽略。

    Returns:
        去重、保序的情境 id 清單。

    Raises:
        HTTPException: 400 — 含非整數段落 / 數量不足 2 個 / 超過 5 個。
    """
    raw_parts = [part.strip() for part in ids.split(",") if part.strip()]
    try:
        parsed = [int(part) for part in raw_parts]
    except ValueError:
        raise HTTPException(400, "ids 必須是以逗號分隔的整數情境 id，例如 ids=3,7,12")

    deduped: List[int] = []
    seen = set()
    for scenario_id in parsed:
        if scenario_id not in seen:
            seen.add(scenario_id)
            deduped.append(scenario_id)

    if len(deduped) < MIN_COMPARE_SCENARIOS:
        raise HTTPException(400, f"至少需選 {MIN_COMPARE_SCENARIOS} 個情境才能比較")
    if len(deduped) > MAX_COMPARE_SCENARIOS:
        raise HTTPException(400, f"最多同時比較 {MAX_COMPARE_SCENARIOS} 個情境")
    return deduped


@router.get(
    "/compare",
    # 檢視＝任何登入者（比照單情境摘要）
    dependencies=[Depends(require_authenticated())],
)
async def compare_scenarios(ids: str) -> ScenarioCompareResponse:
    """跨情境比較摘要並排（A2 Part 1，DEC-20260720-02）：依請求 ``ids`` 的順序並排回傳多個情境的
    摘要（重用 A0 的單情境摘要邏輯，見 ``_load_scenario_summary``），供前端「摘要並排（長條/雷達）」
    比較第一步。

    相對時間對齊的時序疊圖與差異圖（決策記錄裡的 A2 完整範圍）屬後續子任務，本端點只涵蓋摘要並排。

    路由順序注意：本路由必須註冊在 ``/{scenario_id}`` 之前（見本檔案內宣告順序），否則
    ``GET /api/scenarios/compare`` 會先被單情境路由攔截、因 ``scenario_id`` 無法解析成 int 而 422。

    並發抓取：每個情境的摘要各自把阻塞 SQLite 工作丟 ``asyncio.to_thread``（見
    ``_load_scenario_summary``），彼此不互相阻塞事件迴圈，改用 ``asyncio.gather`` 平行取多個情境的
    摘要（而非逐一 await），呼應 ``MAX_COMPARE_SCENARIOS`` 上限註解裡「避免疊加過多長情境聚合掃描
    拖垮回應時間」的設計意圖——序列化 await 會讓最長情境的延遲乘上情境數，並發後只吃最長那一個。
    ``asyncio.gather`` 保留輸入順序，不影響「依請求 ids 順序並排回傳」的回傳契約。
    """
    scenario_ids = _parse_compare_ids(ids)
    summaries = await asyncio.gather(
        *(_load_scenario_summary(sid) for sid in scenario_ids)
    )
    return ScenarioCompareResponse(scenarios=list(summaries))


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


async def _load_scenario_summary(scenario_id: int) -> ScenarioSummary:
    """情境物理摘要的實際建構：每台機組（發電量/容量因數/可用率/累積損傷/最小 RUL/極限負載/DEL/
    故障數）+ 風場層 rollup。純讀取該情境 session 的資料（session 隔離）聚合而成（DEC-20260720-02
    A0），是 A1（同情境內比較）/A2（跨情境比較）的資料基礎。

    供單情境端點 ``get_scenario_summary`` 與跨情境端點 ``compare_scenarios`` 共用，避免重複組裝
    邏輯——後者對每個請求的 id 依序呼叫本函式。

    故障事件數走情境 sim 時間窗（``history_events`` 無 session_id）→ 回傳帶 ``eventsByTimeWindow``
    旗標提醒此計數可能混入時間窗重疊的其他情境（物理聚合走 session_id 隔離，不受影響）。
    """
    b = get_broker()
    # get_scenario 也是同步 SQLite；與後續重查詢一致丟到 thread（見下 to_thread 說明）。
    scenario = await asyncio.to_thread(b.storage.get_scenario, scenario_id)
    if not scenario:
        raise HTTPException(404, f"Scenario {scenario_id} not found")

    config = scenario.get("config") if isinstance(scenario.get("config"), dict) else {}
    config = config or {}
    time_step = float(config.get("time_step") or 10.0)
    rated_power_kw = _scenario_rated_power_kw(scenario)

    # 聚合與事件計數皆為同步阻塞 SQLite，且長情境（duration 上限 8760h × 多機組）掃描量可達數千萬列、
    # 實測外插達分鐘級——若直接在此 async 端點內同步執行會卡住整個 event loop（含 Live WS 推播與其他
    # 請求）。丟到 worker thread 執行，讓 event loop 期間仍可服務其他協程。
    aggregates = await asyncio.to_thread(b.storage.scenario_turbine_aggregates, scenario_id)

    # 故障事件計數：走情境 sim 時間窗（config.sim_start..sim_end，缺則退回 session started/ended）；
    # 用 storage 的 SQL COUNT（不設 LIMIT，避免長/密集情境靜默截斷），非 session 隔離（見 eventsByTimeWindow）。
    start = config.get("sim_start") or scenario.get("started_at")
    end = config.get("sim_end") or scenario.get("ended_at")
    fault_counts = (
        await asyncio.to_thread(b.storage.count_scenario_fault_events, start, end)
        if start and end else {}
    )

    turbines = [
        _build_turbine_summary(agg, time_step, rated_power_kw,
                               fault_counts.get(agg["turbine_id"], 0))
        for agg in aggregates
    ]
    farm = _build_farm_summary(turbines, scenario.get("turbine_count"))

    return ScenarioSummary(
        scenarioId=scenario_id,
        name=config.get("name"),
        status=config.get("status"),
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
    "/{scenario_id}/summary",
    # 檢視＝任何登入者（比照 list/get scenario）
    dependencies=[Depends(require_authenticated())],
)
async def get_scenario_summary(scenario_id: int) -> ScenarioSummary:
    """情境物理摘要（單一情境）。實作見 ``_load_scenario_summary``（與 ``compare_scenarios`` 共用）。"""
    return await _load_scenario_summary(scenario_id)


# ── 情境掛載唯讀端點（PR C Phase 1，DEC-20260926-01）──────────────────────────
# 與 data_broker 的單一 active source 狀態機完全正交：純附加查詢，不改 data_broker.py/source.py
# 一行。格式對齊既有 /api/turbines、/api/turbines/farm-status（見 routers/turbines.py），讓前端
# ScenarioMountContext 掛載時可重用同一套 TurbineReading/FarmStatus 型別與畫面元件。

def _parse_scenario_timestamp(ts_raw: object) -> datetime:
    """情境 DB row / 事件的 ISO timestamp 字串 → ``datetime``；缺值/格式錯誤回退 ``now()``
    （比照既有 ``data_broker._sim_output_to_reading`` 的防禦寫法）。"""
    if isinstance(ts_raw, str):
        try:
            return datetime.fromisoformat(ts_raw)
        except ValueError:
            return datetime.now()
    return ts_raw if isinstance(ts_raw, datetime) else datetime.now()


def _tripped_fault_turbine_ids(fault_events: List[dict], as_of: datetime) -> Set[str]:
    """依故障注入事件的 payload 重算「哪些機組在 ``as_of`` 時刻已 trip」（DEC-20260926-01
    must-fix：情境掛載端點原本完全無法回報 FAULT 狀態）。

    情境資料由 ``generate_bulk`` 一次性批次生成，DB 沒有為每筆 reading 存下即時 tripped
    旗標——即時路徑的 FAULT 覆寫（``data_broker._sim_output_to_reading``）靠的是記憶體內
    ``FaultEngine`` 當下狀態，情境是歷史批次，該記憶體狀態生成完就消失了。改用與
    ``FaultEngine.step()``（``simulator/physics/fault_engine.py``）完全相同的公式
    （``severity = min(1, initial_severity + severity_rate * elapsed_seconds)``、
    ``tripped = severity >= FAULT_SCENARIOS[id].auto_trip_severity``）對已持久化的故障注入
    事件（``history_events``，``event_type == "fault"``，見 ``routers/config.py::on_inject``）
    離線重算，不需要新 schema/欄位。

    簡化：``FaultEngine.inject()`` 對同一機組同一 scenario_id 的重複注入會先移除舊實例、只留
    最新一次；這裡比照只取每個 ``(turbine_id, scenario_id)`` 組合時間最晚的注入事件。

    ⚠️ 繼承既有限制（見 ``get_scenario_turbine_history`` docstring）：``history_events`` 無
    ``session_id``，事件靠情境模擬時間窗（時間字串比較）撈取，短時間內連續產生的情境時間窗
    可能重疊、混入其他情境的事件——與 ``eventsByTimeWindow`` 旗標標示的既有限制一致，非本次
    新引入的風險。

    Args:
        fault_events: ``history_events`` 查詢結果（含已解析的 ``payload`` dict）。
        as_of: 評估時刻（通常是該機組最後一筆 reading 的 timestamp）。

    Returns:
        已 trip 的 turbine_id 集合。
    """
    latest_injection: Dict[tuple, Dict[str, object]] = {}
    for event in fault_events:
        if event.get("event_type") != "fault":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        turbine_id = event.get("turbine_id") or payload.get("turbineId")
        scenario_id = payload.get("scenarioId")
        ts_raw = event.get("timestamp")
        if not turbine_id or not scenario_id or not ts_raw:
            continue
        injected_at = _parse_scenario_timestamp(ts_raw)
        key = (turbine_id, scenario_id)
        prior = latest_injection.get(key)
        if prior is None or injected_at > prior["injected_at"]:
            latest_injection[key] = {"injected_at": injected_at, "payload": payload}

    tripped: Set[str] = set()
    for (turbine_id, scenario_id), info in latest_injection.items():
        injected_at = info["injected_at"]
        if injected_at > as_of:
            continue  # 尚未注入（不應發生於末筆讀數之後，防禦性檢查）
        scenario = FAULT_SCENARIOS.get(scenario_id)
        if not scenario:
            continue
        payload = info["payload"]
        rate = payload.get("severityRate")
        rate = rate if isinstance(rate, (int, float)) and rate > 0 else 0.0002
        initial = payload.get("initialSeverity")
        initial = initial if isinstance(initial, (int, float)) else 0.0
        elapsed_seconds = max((as_of - injected_at).total_seconds(), 0.0)
        severity = min(1.0, initial + rate * elapsed_seconds)
        if severity >= scenario.auto_trip_severity:
            tripped.add(turbine_id)
    return tripped


def _scenario_row_to_reading(row: dict, force_fault: bool = False) -> TurbineReading:
    """情境 session 內某機組最後一筆原始列（``storage.query_history`` 回傳的扁平 DB row）→
    ``TurbineReading``。

    row['status'] 存的是寫入當下的原始 ``operational_state`` 字串（RUNNING/STARTING/STOPPING/
    IDLE，見 ``storage._insert_reading``；注意此欄位結構上永遠不會是 "FAULT"——
    ``simulator.engine._tur_state_to_str`` 的映射表沒有 FAULT 分支，FAULT 狀態一律靠
    ``force_fault`` 由呼叫端另外算出後覆蓋，比照 ``data_broker._sim_output_to_reading`` 的
    「先映射運轉狀態、再視故障是否 tripped 覆寫」兩段式邏輯），需重新套用與即時路徑
    （``data_broker._map_state``）相同的映射，否則會塞進只接受 4 種列舉值的
    ``TurbineReading.status`` 而炸 pydantic ``ValidationError``。tid→name 慣例比照
    ``data_broker._sim_output_to_reading``。

    Args:
        force_fault: 該機組依 ``_tripped_fault_turbine_ids`` 重算已 trip 時傳 ``True``，
            覆蓋掉 operational_state 映射出的狀態（與即時路徑的覆寫順序一致）。
    """
    tid = str(row.get("turbine_id") or "WT001")
    if tid.startswith("WT") and tid[2:].isdigit():
        idx = int(tid.replace("WT", ""))
    else:
        # 不應發生（DB turbine_id 皆由 simulator 以 f"WT{i:03d}" 產生）——記警告而非默默
        # fallback 成 idx=1（會與真正的 WT001 撞名 "WTG-01"），供異常資料排查。
        logger.warning("Scenario row 的 turbine_id 格式異常（非 WT{n}）：%r，name fallback 為 WTG-01", tid)
        idx = 1
    name = f"WTG-{idx:02d}"

    timestamp = _parse_scenario_timestamp(row.get("timestamp"))

    scada = row.get("scada") if isinstance(row.get("scada"), dict) else None

    status = _map_state(str(row.get("status") or "IDLE"))
    if force_fault:
        status = TurbineStatus.FAULT

    return TurbineReading(
        turbineId=tid,
        name=name,
        timestamp=timestamp,
        status=status,
        # `or 6` 會誤把真實存的 0（見 storage._insert_reading 的 int(scada.get("WTUR_TurSt", 0))）
        # 當成缺值、silently 捏造成 6（正常發電），故明確判斷 None 才 fallback（code review
        # should-fix）。
        turState=int(row["tur_state"]) if row.get("tur_state") is not None else 6,
        windSpeed=row.get("wind_speed") or 0.0,
        powerOutput=row.get("power_output") or 0.0,
        rotorSpeed=row.get("rotor_speed") or 0.0,
        bladeAngle=row.get("blade_angle") or 0.0,
        temperature=row.get("temperature") or 0.0,
        vibration=row.get("vibration") or 0.0,
        voltage=row.get("voltage") or 0.0,
        current=row.get("current_amp") or 0.0,
        yawAngle=row.get("yaw_angle") or 0.0,
        gearboxTemp=row.get("gearbox_temp") or 0.0,
        frequency=row.get("frequency"),
        hydraulicPressure=row.get("hydraulic_pressure"),
        scadaTags=scada,
    )


def _scenario_latest_readings(scenario: dict) -> List[TurbineReading]:
    """該情境每台機組的最後一筆讀數（依 turbine_id 排序），FAULT 狀態依故障注入事件離線重算
    （見 ``_tripped_fault_turbine_ids``，DEC-20260926-01 must-fix）。

    先取該情境出現過的機組 id 清單（``scenario_turbine_ids``），逐一
    ``get_history(limit=1, session_id=scenario_id)`` 取末筆——N 次查詢，若日後實測有感效能問題
    可比照 ``scenario_turbine_aggregates`` 改用 ``ROW_NUMBER() OVER (PARTITION BY turbine_id ...)``
    一次查完（非本次強制範圍，見 WMOM-20260926-03 issue nice-to-have）。

    Args:
        scenario: ``storage.get_scenario()`` 回傳的情境 dict（呼叫端已為 404 檢查取過，這裡
            重用避免多查一次）。
    """
    b = get_broker()
    scenario_id = scenario["id"]
    turbine_ids = b.storage.scenario_turbine_ids(scenario_id)

    rows_by_turbine: Dict[str, dict] = {}
    for tid in turbine_ids:
        rows = b.get_history(tid, limit=1, session_id=scenario_id)
        if rows:
            rows_by_turbine[tid] = rows[0]
    if not rows_by_turbine:
        return []

    config = scenario.get("config") if isinstance(scenario.get("config"), dict) else {}
    config = config or {}
    start = config.get("sim_start") or scenario.get("started_at")
    end = config.get("sim_end") or scenario.get("ended_at")
    fault_events = (
        b.get_history_events(start=start, end=end, limit=1000) if start and end else []
    )

    readings = []
    for tid in turbine_ids:
        row = rows_by_turbine.get(tid)
        if not row:
            continue
        as_of = _parse_scenario_timestamp(row.get("timestamp"))
        tripped_ids = _tripped_fault_turbine_ids(fault_events, as_of)
        readings.append(_scenario_row_to_reading(row, force_fault=tid in tripped_ids))
    return readings


def _aggregate_scenario_farm_status(turbines: List[TurbineReading]) -> FarmStatus:
    """風場層 KPI 彙整——與 ``data_broker.DataBroker.get_farm_status`` 相同的彙整邏輯（按 status
    計數 + sum powerOutput + avg windSpeed），套用在情境的「每機組最後一筆讀數」清單之上。"""
    now = datetime.now()
    if not turbines:
        return FarmStatus(
            totalTurbines=0, operatingCount=0, idleCount=0,
            faultCount=0, offlineCount=0, totalPowerMW=0,
            avgWindSpeed=0, timestamp=now,
        )
    return FarmStatus(
        totalTurbines=len(turbines),
        operatingCount=sum(1 for t in turbines if t.status == TurbineStatus.OPERATING),
        idleCount=sum(1 for t in turbines if t.status == TurbineStatus.IDLE),
        faultCount=sum(1 for t in turbines if t.status == TurbineStatus.FAULT),
        offlineCount=sum(1 for t in turbines if t.status == TurbineStatus.OFFLINE),
        totalPowerMW=round(sum(t.powerOutput for t in turbines), 2),
        avgWindSpeed=round(sum(t.windSpeed for t in turbines) / len(turbines), 2),
        timestamp=now,
    )


@router.get(
    "/{scenario_id}/turbines",
    response_model=List[TurbineReading],
    # 檢視＝任何登入者（比照 /api/turbines 與其餘情境檢視端點）
    dependencies=[Depends(require_authenticated())],
)
async def get_scenario_turbines(scenario_id: int) -> List[TurbineReading]:
    """該情境每台機組的最後一筆讀數（PR C Phase 1 情境掛載：FarmOverview/TurbineDetail 唯讀顯示用）。

    格式對齊即時 ``GET /api/turbines``，讓前端掛載模式下可重用同一批畫面元件；資料本身是凍結快照
    （情境不會變），故省略即時路徑才有的 ``history``（前 30 筆折線）欄位。
    """
    b = get_broker()
    scenario = await asyncio.to_thread(b.storage.get_scenario, scenario_id)
    if not scenario:
        raise HTTPException(404, f"Scenario {scenario_id} not found")
    return await asyncio.to_thread(_scenario_latest_readings, scenario)


@router.get(
    "/{scenario_id}/farm-status",
    response_model=FarmStatus,
    # 檢視＝任何登入者（比照 /api/turbines/farm-status 與其餘情境檢視端點）
    dependencies=[Depends(require_authenticated())],
)
async def get_scenario_farm_status(scenario_id: int) -> FarmStatus:
    """該情境的風場層 KPI（PR C Phase 1 情境掛載：FarmOverview 唯讀顯示用）。格式對齊即時
    ``GET /api/turbines/farm-status``。"""
    b = get_broker()
    scenario = await asyncio.to_thread(b.storage.get_scenario, scenario_id)
    if not scenario:
        raise HTTPException(404, f"Scenario {scenario_id} not found")
    readings = await asyncio.to_thread(_scenario_latest_readings, scenario)
    return _aggregate_scenario_farm_status(readings)


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
