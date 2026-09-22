"""資料來源選擇 API（WMOM-20260719-04, DEC-20260719-01 #3）。

開機不再自動啟動任何資料來源（修「一進系統就自動以預設風場產資料」）。使用者強制登入後，
前端顯示「選擇資料來源」頁，選定才由本 router 啟動：

- ``simulation``：即時模擬（起 simulator 連續自由跑生成）。
- ``scenario``：產生情境（DEC-20260720-01 PR B）——起 simulator 供批次生成，但**不自由跑**、
  **不起 Modbus**（情境是可重現的凍結資料集，不該持續產生新資料）。
- ``live``：實際資料對接（OPC DA）。
- ``view``：僅調閱過去情境——**不啟動任何來源**（情境調閱只讀 storage），避免又開始產資料。

- ``GET  /api/source/status``  目前是否已選來源 + 種類（前端據此決定是否顯示選擇頁）
- ``POST /api/source/select``  選定並啟動來源
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from modules.auth.dependencies import require_authenticated, require_role
from modules.auth.roles import Role
from pydantic import BaseModel

router = APIRouter(prefix="/api/source", tags=["source"])


def get_broker():
    """Return the shared DataBroker instance from the main app module."""
    from server.app import broker
    return broker


class SourceSelect(BaseModel):
    """來源選擇 payload。mode ∈ simulation / scenario / live / view。"""
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
async def select_source(req: SourceSelect, request: Request):
    """選定並啟動資料來源。

    simulation / view＝任何登入者（含現場工程師的必經入口）；live（實際對接，會嘗試對外 OPC
    握手且影響全域）比照 farm-activate 要求 SUPERVISOR 以上——但僅在 enforce 開時強制（過渡期
    enforce 關時維持與其他 mode 一致開放，不破壞現行 no-token 操作）。

    Must-fix（WMOM-20260720-04 (2)）：起 live 需 SUPERVISOR，但**切走** live 之前無角色檢查——
    前端 #144 的二次確認只防手滑，不防任何登入者直接呼叫本 API 斷現場連線。切走 live 與起
    live 同等敏感，故對稱地要求 SUPERVISOR。

    註：這個角色檢查跑在下面 mode 合法性判斷之前，所以「目前是 live 且非 SUPERVISOR」時，
    即使傳了不合法的 mode（如打錯字）也會先拿到 403 而非 400——是刻意 fail-closed，不代表
    mode 一定合法。
    """
    b = get_broker()
    mode = (req.mode or "").strip().lower()
    if b.source_kind == "live" and mode != "live":
        require_role(Role.SUPERVISOR)(request)
    if mode == "simulation":
        # 即時模擬：自由跑連續產資料（source_kind=simulation）。
        from server.app import activate_simulation
        activate_simulation(run_loop=True)
    elif mode == "scenario":
        # 產生情境（DEC-20260720-01 PR B）：起 simulator 供批次生成，但**不自由跑**——情境是可重現
        # 的凍結資料集，不該持續產生新資料（source_kind=scenario）。
        from server.app import activate_simulation
        activate_simulation(run_loop=False)
    elif mode == "live":
        # live 影響全域且會嘗試對外 OPC 握手 → 比照 farm-activate 需 SUPERVISOR。
        # 重用 enforce-aware 的 require_role（過渡期放行、cutover 後強制），不手刻第二份角色判斷。
        require_role(Role.SUPERVISOR)(request)
        from server.app import activate_live
        activate_live()
    elif mode == "view":
        b.select_view_only()
    else:
        raise HTTPException(400, f"Unknown source mode: {req.mode!r}. Use: simulation, scenario, live, view")

    return {"status": "ok", "active": b.source_active, "kind": b.source_kind}
