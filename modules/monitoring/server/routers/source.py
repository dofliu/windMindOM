"""資料來源選擇 API（WMOM-20260719-04, DEC-20260719-01 #3）。

開機不再自動啟動任何資料來源（修「一進系統就自動以預設風場產資料」）。使用者強制登入後，
前端顯示「選擇資料來源」頁，選定才由本 router 啟動：

- ``simulation``：即時模擬（起 simulator 連續生成）——「即時模擬」與「產生情境」皆用此。
- ``live``：實際資料對接（OPC DA）。
- ``view``：僅調閱過去情境——**不啟動任何來源**（情境調閱只讀 storage），避免又開始產資料。

- ``GET  /api/source/status``  目前是否已選來源 + 種類（前端據此決定是否顯示選擇頁）
- ``POST /api/source/select``  選定並啟動來源
"""

from fastapi import APIRouter, Depends, HTTPException
from modules.auth.dependencies import require_authenticated
from pydantic import BaseModel

router = APIRouter(prefix="/api/source", tags=["source"])


def get_broker():
    """Return the shared DataBroker instance from the main app module."""
    from server.app import broker
    return broker


class SourceSelect(BaseModel):
    """來源選擇 payload。mode ∈ simulation / live / view。"""
    mode: str


@router.get(
    "/status",
    # 檢視＝任何登入者（每個 persona 登入後都要看是否已選來源）
    dependencies=[Depends(require_authenticated())],
)
async def source_status():
    """回報目前是否已選定資料來源（未選＝前端顯示選擇頁）。"""
    b = get_broker()
    return {
        "active": b.source_active,
        "kind": b.source_kind,
        "mode": b.mode.value if b.source_active and b.source_kind != "view" else None,
    }


@router.post(
    "/select",
    # 選來源＝任何登入者（這是登入後的必經入口，含現場工程師）
    dependencies=[Depends(require_authenticated())],
)
async def select_source(req: SourceSelect):
    """選定並啟動資料來源。"""
    b = get_broker()
    mode = (req.mode or "").strip().lower()
    if mode == "simulation":
        from server.app import activate_simulation
        activate_simulation()
    elif mode == "live":
        from server.app import activate_live
        activate_live()
    elif mode == "view":
        b.select_view_only()
    else:
        raise HTTPException(400, f"Unknown source mode: {req.mode!r}. Use: simulation, live, view")

    return {"status": "ok", "active": b.source_active, "kind": b.source_kind}
