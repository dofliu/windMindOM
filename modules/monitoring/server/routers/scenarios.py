"""情境保存/調閱 API（DEC-20260718-01 #4，WMOM-20260719-02）。

情境＝一個以 ``config_json.kind == "scenario"`` 標記的專屬 session（見 ``storage``）。
批次生成（``/api/config/simulation/generate-bulk`` 帶 ``name``）會把資料寫進該 session、
與 Live/其他歷史隔離；本 router 讓使用者事後把它們列出來、調某一個回來觀察、或刪除。

- ``GET  /api/scenarios``                                     列出已保存情境（新到舊）
- ``GET  /api/scenarios/{id}``                                單一情境詮釋資料
- ``GET  /api/scenarios/{id}/turbines/{turbine_id}/history``  某情境某機組的資料（隔離調閱）
- ``DELETE /api/scenarios/{id}``                              刪除情境（含資料列）
"""

from fastapi import APIRouter, Depends, HTTPException
from modules.auth.dependencies import require_authenticated, require_role
from modules.auth.roles import Role

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


def get_broker():
    """Return the shared DataBroker instance from the main app module."""
    from server.app import broker
    return broker


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
