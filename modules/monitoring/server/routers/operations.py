"""運維閉環的查詢端點（WMOM-20261125-04）：可用率、停機時數、損失發電量。

數字由運轉狀態紀錄計算（``server/om_loop.py``），不是由工單工時推估。這些是管理端的內部指標：分類用到
「這台機組是不是故障跳機後在等維修」，不對外（對外唯讀 API 沒有這個端點）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from modules.auth.dependencies import require_authenticated
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
