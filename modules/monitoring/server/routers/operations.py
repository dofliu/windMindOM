"""運維閉環的查詢端點：可用率（WMOM-20261125-04）、出發前準備卡（WMOM-20261125-05）。

可用率由運轉狀態紀錄計算（``server/om_loop.py``），不是由工單工時推估。它是管理端的內部指標：分類用到
「這台機組是不是故障跳機後在等維修」，不對外（對外唯讀 API 沒有這個端點）。

準備卡只含可觀測資料，登入的人都看得到；評分（卡片有沒有指到故障的重點訊號）要對答案，只給主管，而且
不管伺服器有沒有開強制登入都要驗（同標準答案的端點）。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Annotated, Dict, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from modules.auth.dependencies import require_authenticated, require_role, require_roles
from modules.auth.roles import Role
from modules.workflow.domain import WorkOrderType
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
    "not_corrective": (409, "只有對得到機組的故障維修工單有出發前準備卡"),
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
    return {"business_key": stored["business_key"], "score": briefing.score_card(stored["card"], answer),
            "answer": answer}
