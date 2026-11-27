"""運維閉環的查詢端點：可用率（WMOM-20261125-04）、出發前準備卡（WMOM-20261125-05）。

可用率由運轉狀態紀錄計算（``server/om_loop.py``），不是由工單工時推估。它是管理端的內部指標：分類用到
「這台機組是不是故障跳機後在等維修」，不對外（對外唯讀 API 沒有這個端點）。

準備卡只含可觀測資料，登入的人都看得到；評分（卡片有沒有指到故障的重點訊號）要對答案，只給主管，而且
不管伺服器有沒有開強制登入都要驗（同標準答案的端點）。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Dict, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from modules.auth.dependencies import require_authenticated, require_role, require_roles
from modules.auth.roles import Role
from modules.workflow.domain import WorkOrderType
from server.batch_state import reject_during_batch
from server.data_broker import DataBroker
from simulator.time_utils import iso_utc, parse_iso, utc_now

router = APIRouter(prefix="/api/operations", tags=["operations"])

MAX_RANGE = timedelta(days=400)


def get_broker() -> DataBroker:
    """Return the shared DataBroker instance from the main app module."""
    from server.app import broker
    return broker


def _moment(name: str, value: str) -> datetime:
    try:
        moment = parse_iso(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, f"{name} 不是 ISO 8601 時間") from exc
    return moment.astimezone(timezone.utc)


@router.get(
    "/availability",
    # 檢視＝任何登入者（enforce 關時放行，同其他檢視端點）
    dependencies=[Depends(require_authenticated())],
)
async def availability(
    start: Annotated[Optional[str], Query(max_length=40, description="ISO 8601；預設 end 往前 24 小時")] = None,
    end: Annotated[Optional[str], Query(max_length=40, description="ISO 8601；預設風場時鐘的現在")] = None,
) -> Dict[str, object]:
    """一段時間的可用率、計畫 / 非計畫停機時數、發電量與停機少發的電（每台機組與全場）。

    以小時為單位：算進小時起點落在 ``[start, end)`` 的紀錄。時間看風場時鐘（即時模擬的模擬時鐘）。

    Args:
        start: 時間下限（含）。
        end: 時間上限（不含）。

    Returns:
        ``{"start", "end", "enabled", "turbines": [...], "farm": {...}}``；閉環沒開時 ``enabled`` 為 False、
        沒有紀錄。
    """
    broker = get_broker()
    end_dt = _moment("end", end) if end else (broker.live_clock() or utc_now()) + timedelta(hours=1)
    start_dt = _moment("start", start) if start else end_dt - timedelta(hours=24)
    if end_dt <= start_dt:
        raise HTTPException(422, "end 要晚於 start")
    if end_dt - start_dt > MAX_RANGE:
        raise HTTPException(422, "一次最多查 400 天")
    loop = broker.om_loop
    result = loop.availability(start_dt, end_dt)
    return {"start": iso_utc(start_dt), "end": iso_utc(end_dt), "enabled": loop.enabled, **result}


@router.get(
    "/finance",
    # 收支是管理端的資料：用永遠強制的主管權限（同故障紀錄）
    dependencies=[Depends(require_roles(Role.SUPERVISOR))],
)
async def finance(
    start: Annotated[Optional[str], Query(max_length=40, description="ISO 8601；預設 end 往前 30 天")] = None,
    end: Annotated[Optional[str], Query(max_length=40, description="ISO 8601；預設風場時鐘的現在")] = None,
) -> Dict[str, object]:
    """一段時間的收支（WMOM-20260504-11）：發電收入、停機少收的錢、支出、淨額。

    收入與少收的錢由運轉狀態紀錄（同可用率）乘上電價；支出是成本帳本裡這段時間的料件、設備（含吊車動員），
    加上固定成本（駐場技師年薪、設備年費，依運轉狀態紀錄涵蓋的天數攤，WMOM-20261127-02）。技師領年薪，工單
    上的工時不另算（``work_order_labour``）。時間看風場時鐘。運轉狀態紀錄以小時為單位，所以 start / end 都往下
    取整到整點，兩邊用同一個時間窗。

    Args:
        start: 時間下限（含）。
        end: 時間上限（不含）。

    Returns:
        ``{"start", "end", "enabled", "rates", "energy_kwh", "revenue", "lost_revenue", "expenses",
        "fixed_costs", "work_order_labour", "net", "turbines"}``。
    """
    broker = get_broker()
    end_dt = _moment("end", end) if end else (broker.live_clock() or utc_now()) + timedelta(hours=1)
    start_dt = _moment("start", start) if start else end_dt - timedelta(days=30)
    start_dt = start_dt.replace(minute=0, second=0, microsecond=0)
    end_dt = end_dt.replace(minute=0, second=0, microsecond=0)
    if end_dt <= start_dt:
        raise HTTPException(422, "end 要晚於 start（取整到整點之後）")
    if end_dt - start_dt > MAX_RANGE:
        raise HTTPException(422, "一次最多查 400 天")
    farm_id = broker._active_farm_id
    if not farm_id:
        raise HTTPException(409, "目前沒有啟用的風場")
    from modules.cost.repository.cost_ledger import CostLedgerCategory, CostLedgerSourceType
    from modules.cost.repository.cost_ledger_repository import get_cost_ledger_repository
    from modules.cost.services.simulation_costs import farm_rates, summarize

    def compute() -> Dict[str, object]:
        loop = broker.om_loop
        ledger = get_cost_ledger_repository(str(broker.storage.db_path))
        expenses = ledger.summary_by_category(farm_id=farm_id, from_date=start_dt, to_date=end_dt)
        # 工單的人工分錄：技師領年薪，已含在人員固定成本裡（WMOM-20261127-02）
        work_order_labour = ledger.summary_by_category(
            farm_id=farm_id, from_date=start_dt, to_date=end_dt,
            source_type=CostLedgerSourceType.WORK_ORDER).get(CostLedgerCategory.LABOUR, Decimal("0"))
        availability = loop.availability(start_dt, end_dt)
        return {"enabled": loop.enabled,
                **summarize(availability, expenses, farm_rates(farm_id, broker.farm_registry),
                            fixed=loop.fixed_costs(farm_id, availability),
                            work_order_labour=work_order_labour)}

    result = await asyncio.to_thread(compute)
    return {"start": iso_utc(start_dt), "end": iso_utc(end_dt), **result}


_CARD_FIELDS = ("work_order_id", "business_key", "turbine_id", "created_at", "data_cutoff", "card")


def _stored_briefing(work_order_id: str, farm_id: str) -> Optional[Dict[str, object]]:
    """讀一張準備卡（含不對外的答案）；先驗工單 id 與風場。沒有卡片回 None。"""
    try:
        UUID(work_order_id)
    except ValueError as exc:
        raise HTTPException(422, "work_order_id 不是 UUID") from exc
    broker = get_broker()
    if farm_id != broker._active_farm_id:
        # 409，不是 404：404 留給「這張工單沒有卡」，畫面才分得出「沒有卡」和「讀不到」
        raise HTTPException(409, "這座風場目前沒有啟用，讀不到它的出發前準備卡")
    return broker.storage.get_briefing(work_order_id=work_order_id)


@router.get(
    "/work-orders/{work_order_id}/briefing",
    dependencies=[Depends(require_authenticated())],
)
async def work_order_briefing(
    work_order_id: str,
    farm_id: Annotated[str, Query(min_length=1)],
) -> Dict[str, object]:
    """一張工單的出發前準備卡（故障出勤卡）。只讀，不會產生卡片。

    卡片在故障維修工單建立當下產生。沒有卡片（定檢工單、對不到機組、工單建立時閉環沒開）回 404；
    還沒完工的工單可以用 ``POST`` 補一張。

    Args:
        work_order_id: 工單 id。
        farm_id: 風場 ID（要是目前啟用的風場）。

    Returns:
        ``{"work_order_id", "business_key", "turbine_id", "created_at", "data_cutoff", "card"}``。
    """
    stored = _stored_briefing(work_order_id, farm_id)
    if stored is None:
        raise HTTPException(404, "這張工單沒有出發前準備卡")
    return {key: stored[key] for key in _CARD_FIELDS}   # 白名單：評分用的答案不在裡面


# ``OmLoop.backfill_briefing`` 的結果 → HTTP 狀態碼與說明
_BACKFILL_ERRORS: Dict[str, Tuple[int, str]] = {
    "not_found": (404, "找不到這張工單"),
    "not_corrective": (409, "只有對得到機組的故障維修、定檢、預防保養工單有出發前準備卡"),
    "finished": (409, "工單已經完工：補出來的不是出發前的樣子，不補"),
    "not_live": (409, "即時模擬沒在跑，現在不能產生出發前準備卡"),
    "failed": (500, "出發前準備卡產生失敗，請看伺服器的 log"),
}


def _build_briefing(work_order_id: str) -> None:
    """替還沒完工的故障維修工單補一張卡（在背景執行緒跑：要讀同場每台機組幾小時的讀值）。"""
    loop = get_broker()._om_loop_if_enabled()
    if loop is None:
        raise HTTPException(409, "運維閉環沒有開，不能產生出發前準備卡")
    result, _card = loop.backfill_briefing(UUID(work_order_id))
    if result != "ok":
        status, message = _BACKFILL_ERRORS[result]
        raise HTTPException(status, message)


@router.post(
    "/work-orders/{work_order_id}/briefing",
    # 補產生會寫資料庫：組長 / 主管（enforce 關時放行，同派工）
    dependencies=[Depends(require_role(Role.LEADER, Role.SUPERVISOR))],
)
async def build_work_order_briefing(
    work_order_id: str,
    farm_id: Annotated[str, Query(min_length=1)],
) -> Dict[str, object]:
    """替一張還沒完工、也還沒有卡片的故障維修工單補產生出發前準備卡。

    補出來的卡以現在的風場時鐘為資料截止點，卡上標 ``generated_late``。已經有卡的工單不會被換掉
    （卡片不可變），直接回原本那一張。

    Args:
        work_order_id: 工單 id。
        farm_id: 風場 ID（要是目前啟用的風場）。

    Returns:
        同 ``GET``。
    """
    stored = _stored_briefing(work_order_id, farm_id)
    if stored is None:
        await asyncio.to_thread(_build_briefing, work_order_id)
        stored = _stored_briefing(work_order_id, farm_id)
    if stored is None:
        raise HTTPException(409, "出發前準備卡沒有產生出來")
    return {key: stored[key] for key in _CARD_FIELDS}


@router.get(
    "/work-orders/{work_order_id}/briefing/score",
    # 評分要對答案（這台機組當下實際的故障）：只給主管，永遠強制（同 /api/scenarios/{id}/ground-truth）
    dependencies=[Depends(require_roles(Role.SUPERVISOR))],
)
async def work_order_briefing_score(
    work_order_id: str,
    farm_id: Annotated[str, Query(min_length=1)],
) -> Dict[str, object]:
    """用不對外的故障紀錄核對一張準備卡：有沒有指到故障的重點訊號、沒有故障時有沒有亂標。

    Args:
        work_order_id: 工單 id。
        farm_id: 風場 ID（要是目前啟用的風場）。

    Returns:
        ``{"business_key", "score": {...}, "answer": {...}}``。
    """
    from server import briefing

    stored = _stored_briefing(work_order_id, farm_id)
    if stored is None:
        raise HTTPException(404, "這張工單沒有出發前準備卡")
    answer = stored["answer"]
    if answer is None:
        # 沒有答案就不評分：把「沒記到答案」當成「沒有故障」會算出假的誤報
        raise HTTPException(409, "這張卡沒有存評分用的答案，不能評分")
    return {"business_key": stored["business_key"], "score": briefing.score_any_card(stored["card"], answer),
            "answer": answer}


# ── 機率式故障產生器、模擬維修班、不對外的故障紀錄（WMOM-20261125-06）────────
# 這三組端點都只給主管，而且永遠強制（不看 WMOM_AUTH_ENFORCE）：故障紀錄是答案，產生器的設定透露
# 風場會出什麼題。外部的 API 金鑰打不到這裡。


def _live_simulator():  # noqa: ANN202  回傳型別在 simulator.engine，這裡不在模組層 import
    simulator = get_broker().simulator
    if simulator is None:
        raise HTTPException(409, "即時模擬沒在跑")
    return simulator


@router.get("/fault-generator", dependencies=[Depends(require_roles(Role.SUPERVISOR))])
async def fault_generator_settings() -> Dict[str, object]:
    """機率式故障產生器的設定與現況。

    Returns:
        ``{"config": {...}, "generated": 開始以來產生了幾個, "scenarios": 各情境的預設權重}``。
    """
    from simulator.fault_generator import default_weight
    from simulator.physics.fault_engine import FAULT_SCENARIOS

    simulator = _live_simulator()
    generator = simulator.fault_generator
    return {"config": generator.config.to_dict(), "generated": generator.generated,
            "scenarios": {sid: default_weight(sid) for sid in sorted(FAULT_SCENARIOS)},
            "wear": _wear_view(simulator)}


def _wear_view(simulator: object) -> Dict[str, object]:
    """各機組的耗損（0–1）與換過的零件從換新以來的耗損（WMOM-20261127-07）。模型內部量，只給主管。"""
    from simulator.fault_generator import turbine_wear

    generator = simulator.fault_generator  # type: ignore[attr-defined]
    replaced = generator.replacements()
    out: Dict[str, object] = {}
    for turbine_id, model in sorted(simulator.turbines.items()):  # type: ignore[attr-defined]
        wear = turbine_wear(model, generator.config)
        parts = generator.part_wear(turbine_id, model)
        out[turbine_id] = {
            **{key: round(value, 4) for key, value in wear.items()},
            "parts": {part: {"wear": round(value, 4), "replaced_at": replaced[turbine_id][part].get("at")}
                      for part, value in sorted(parts.items())}}
    return out


@router.put("/fault-generator",
            dependencies=[Depends(reject_during_batch), Depends(require_roles(Role.SUPERVISOR))])
async def set_fault_generator_settings(body: Dict[str, object]) -> Dict[str, object]:
    """設定機率式故障產生器。設定存在風場 DB，重啟後照舊；沒給的欄位用預設值。

    Args:
        body: ``enabled``、``mean_days_between_faults``、``scenario_weights``、``turbine_weights``、
            ``wear_gain``、``min_hours_to_full``、``max_hours_to_full``、``max_active_per_turbine``、``seed``。

    Returns:
        同 ``GET``。
    """
    from simulator.fault_generator import FaultGeneratorConfig

    simulator = _live_simulator()
    try:
        config = FaultGeneratorConfig.from_dict(body)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    unknown = sorted(set(config.turbine_weights) - set(simulator.turbines))
    if unknown:
        raise HTTPException(422, f"沒有這些機組：{unknown}")
    broker = get_broker()
    broker.storage.set_setting(broker.SETTING_FAULT_GENERATOR, config.to_dict())
    simulator.fault_generator.configure(config)
    return await fault_generator_settings()


def _crew():  # noqa: ANN202  回傳型別在 server.crew
    loop = get_broker()._om_loop_if_enabled()
    if loop is None:
        raise HTTPException(409, "運維閉環沒有開，沒有模擬維修班")
    return loop.crew


@router.get("/crew", dependencies=[Depends(require_roles(Role.SUPERVISOR))])
async def crew_settings() -> Dict[str, object]:
    """模擬維修班的設定。

    Returns:
        ``{"config": {...}}``。
    """
    return {"config": _crew().config.to_dict()}


@router.put("/crew", dependencies=[Depends(reject_during_batch), Depends(require_roles(Role.SUPERVISOR))])
async def set_crew_settings(body: Dict[str, object]) -> Dict[str, object]:
    """設定模擬維修班。設定存在風場 DB，重啟後照舊；沒給的欄位用預設值。

    Args:
        body: ``enabled``、``response_minutes``、``repair_minutes``、``inspection_minutes``、``crews``、
            ``close_after_finish``。時間是風場時鐘的分鐘數。

    Returns:
        同 ``GET``。
    """
    from server.crew import CrewConfig

    crew = _crew()
    try:
        config = CrewConfig.from_dict(body)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    broker = get_broker()
    broker.storage.set_setting(broker.SETTING_CREW, config.to_dict())
    crew.configure(config)
    return {"config": config.to_dict()}


def _inspection_plan_view(plan) -> Dict[str, object]:  # noqa: ANN001  型別在 server.inspection_plan
    clock = get_broker().live_clock()
    schedules = [{
        "turbine_id": schedule.turbine_id,
        "active": schedule.active,
        "next_due_at": iso_utc(schedule.next_due_at),
        "last_spawned_at": iso_utc(schedule.last_spawned_at) if schedule.last_spawned_at else None,
        "last_work_order_id": str(schedule.last_spawned_work_order_id)
        if schedule.last_spawned_work_order_id else None,
        # 到期了還沒開單：即時模擬每 15 分鐘（風場時鐘）看一次，超過就是那台機組的未結案工單滿了
        "overdue": bool(schedule.active and clock is not None and schedule.next_due_at <= clock),
    } for schedule in plan.schedules()]
    schedules.sort(key=lambda item: (not item["active"], item["next_due_at"], item["turbine_id"]))
    return {"config": plan.config.to_dict(), "clock": iso_utc(clock) if clock else None, "schedules": schedules}


@router.get("/inspection-plan", dependencies=[Depends(require_roles(Role.SUPERVISOR))])
async def inspection_plan_settings() -> Dict[str, object]:
    """自動定檢計畫的設定與各機組的排程（WMOM-20261127-03）。

    Returns:
        ``{"config": {...}, "clock": 風場時鐘或 null, "schedules": [{"turbine_id", "active", "next_due_at",
        "last_spawned_at", "last_work_order_id", "overdue"}]}``。時間是風場時鐘；``overdue``＝到期了還沒開單
        （每 15 分鐘看一次，超過就是那台機組的未結案工單滿了）。
    """
    loop = get_broker()._om_loop_if_enabled()
    if loop is None:
        raise HTTPException(409, "運維閉環沒有開，沒有自動定檢計畫")
    return await asyncio.to_thread(_inspection_plan_view, loop.inspection_plan)


@router.put("/inspection-plan",
            dependencies=[Depends(reject_during_batch), Depends(require_roles(Role.SUPERVISOR))])
async def set_inspection_plan_settings(body: Dict[str, object]) -> Dict[str, object]:
    """設定自動定檢計畫。設定存在風場 DB，重啟後照舊；沒給的欄位用預設值。

    排程由即時模擬在下一批讀值寫進歷史時整理（開了就每台機組建 / 啟用一個、錯開到期；關了就全部暫停；週期變了
    就重新錯開；存了同樣的設定不動既有的排程），所以回應裡的排程可能還是改之前的。

    Args:
        body: ``enabled``、``interval_days``（風場時鐘的天數）。

    Returns:
        同 ``GET``。
    """
    from server.inspection_plan import InspectionPlanConfig

    loop = get_broker()._om_loop_if_enabled()
    if loop is None:
        raise HTTPException(409, "運維閉環沒有開，沒有自動定檢計畫")
    try:
        config = InspectionPlanConfig.from_dict(body)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    broker = get_broker()
    broker.storage.set_setting(broker.SETTING_INSPECTION_PLAN, config.to_dict())
    loop.inspection_plan.configure(config)
    return await asyncio.to_thread(_inspection_plan_view, loop.inspection_plan)


# 故障率回饋的預設起點：從有紀錄開始全部算
_HISTORY_START = datetime(2000, 1, 1, tzinfo=timezone.utc)


@router.get("/failure-rates", dependencies=[Depends(require_roles(Role.SUPERVISOR))])
async def failure_rates(
    start: Annotated[Optional[str], Query(max_length=40, description="ISO 8601；預設從有紀錄開始")] = None,
    end: Annotated[Optional[str], Query(max_length=40, description="ISO 8601；預設風場時鐘的現在")] = None,
    prior_turbine_years: Annotated[float, Query(gt=0, le=10000)] = 14.0,
) -> Dict[str, object]:
    """本風場的維修紀錄回饋到 K13 故障率（WMOM-20261127-07，DEC-20261127-09）。

    故障率＝（K13 × 先驗機組年＋修過的次數）÷（先驗機組年＋運轉機組年）。修過的次數來自不對外的故障紀錄
    （由工單修好的），所以只給永遠強制登入的主管。要拿回饋後的故障率跑 Monte Carlo 用
    ``POST /api/cost/monte-carlo/empirical``。

    Args:
        start: 時間下限（含，取整到整點）。
        end: 時間上限（不含）。
        prior_turbine_years: K13 的故障率算幾個機組年的經驗。

    Returns:
        ``{"start", "end", "turbine_years", "prior_turbine_years", "components": [...], "unmapped": {...}}``。
    """
    from modules.cost.adapter import load_engine_params_from_farm
    from modules.cost.services.failure_rates import empirical_rates, unmapped_repairs

    broker = get_broker()
    end_dt = _moment("end", end) if end else (broker.live_clock() or utc_now()) + timedelta(hours=1)
    start_dt = _moment("start", start) if start else _HISTORY_START
    start_dt = start_dt.replace(minute=0, second=0, microsecond=0)
    end_dt = end_dt.replace(minute=0, second=0, microsecond=0)
    if end_dt <= start_dt:
        raise HTTPException(422, "end 要晚於 start（取整到整點之後）")
    farm_id = broker._active_farm_id
    if not farm_id:
        raise HTTPException(409, "目前沒有啟用的風場")

    def compute() -> Dict[str, object]:
        observations = broker.om_loop.failure_observations(start_dt, end_dt)
        params, _meta = load_engine_params_from_farm(farm_id, farm_registry=broker.farm_registry)
        updates = empirical_rates(params.components, observations, prior_turbine_years)
        return {"start": observations.start, "end": observations.end,
                "turbine_years": round(observations.turbine_years, 4), "prior_turbine_years": prior_turbine_years,
                "components": [u.to_dict() for u in updates], "unmapped": unmapped_repairs(observations)}

    return await asyncio.to_thread(compute)


@router.get("/fault-records", dependencies=[Depends(require_roles(Role.SUPERVISOR))])
async def fault_records(
    turbine_id: Annotated[Optional[str], Query(min_length=1, max_length=64)] = None,
    open_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=2000)] = 200,
) -> Dict[str, object]:
    """不對外的故障紀錄：即時風場每一筆故障的發生、第一次警報、跳機、修復，加上答案欄位。

    這是 Live 版的標準答案，只給評分端。

    Args:
        turbine_id: 只取這台機組；不給＝全部。
        open_only: 只取還沒修好的。
        limit: 最多幾筆（新的在前）。

    Returns:
        ``{"cases": [...]}``。
    """
    broker = get_broker()
    cases = await asyncio.to_thread(broker.fault_records.cases, turbine_id, open_only, limit)
    return {"cases": cases}
