"""
Wind Farm management API — CRUD, activate, clone, export.
"""

import asyncio
import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from modules.auth.dependencies import require_authenticated, require_role
from modules.auth.roles import Role

router = APIRouter(prefix="/api/farms", tags=["farms"])


def _get_registry():
    from server.app import farm_registry
    return farm_registry


def _get_broker():
    from server.app import broker
    return broker


def _sanitize_id(name: str) -> str:
    """Convert a display name to a valid farm_id slug."""
    s = re.sub(r"[^\w\s-]", "", name.lower())
    s = re.sub(r"[\s]+", "_", s.strip())
    return s[:60] or "farm"


# ── List / Get ──────────────────────────────────────────────────────────

@router.get(
    "",
    # WMOM-20260716-05h-2：檢視＝任何登入者
    dependencies=[Depends(require_authenticated())],
)
async def list_farms():
    """List all wind farm projects."""
    reg = _get_registry()
    farms = reg.list_farms()
    active_id = reg.get_active_farm_id()
    return {
        "active_farm_id": active_id,
        "farms": [f.to_dict() | {"is_active": f.farm_id == active_id} for f in farms],
    }


@router.get(
    "/active",
    # WMOM-20260716-05h-2：檢視＝任何登入者
    dependencies=[Depends(require_authenticated())],
)
async def get_active_farm():
    """Get the currently active wind farm."""
    reg = _get_registry()
    farm_id = reg.get_active_farm_id()
    if not farm_id:
        raise HTTPException(404, "No active farm")
    farm = reg.get_farm(farm_id)
    return farm.to_dict() | {"is_active": True}


@router.get(
    "/{farm_id}",
    # WMOM-20260716-05h-2：檢視＝任何登入者
    dependencies=[Depends(require_authenticated())],
)
async def get_farm(farm_id: str):
    """Get details of a specific wind farm."""
    farm = _get_registry().get_farm(farm_id)
    if not farm:
        raise HTTPException(404, f"Farm not found: {farm_id}")
    active_id = _get_registry().get_active_farm_id()
    return farm.to_dict() | {"is_active": farm_id == active_id}


# ── Create ──────────────────────────────────────────────────────────────

@router.post(
    "",
    # WMOM-20260716-05h-2：farm 建立＝主管
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def create_farm(body: dict):
    """Create a new wind farm project.

    Required: name
    Optional: farm_id, turbine_count, preset, turbine_spec,
              wind_profile, grid_profile, location, description,
              timezone（IANA 名稱，預設 Asia/Taipei；模擬的日夜 / 季節循環依此當地時刻）
    """
    reg = _get_registry()
    name = body.get("name")
    if not name:
        raise HTTPException(400, "name is required")

    farm_id = body.get("farm_id") or _sanitize_id(name)
    if reg.get_farm(farm_id):
        raise HTTPException(409, f"Farm already exists: {farm_id}")

    turbine_count = body.get("turbine_count", 14)
    turbine_spec = body.get("turbine_spec", {})

    preset_name = body.get("preset")
    if preset_name:
        from simulator.physics.turbine_physics import TURBINE_PRESETS
        if preset_name not in TURBINE_PRESETS:
            raise HTTPException(404, f"Unknown preset: {preset_name}. Available: {list(TURBINE_PRESETS.keys())}")
        turbine_spec = TURBINE_PRESETS[preset_name].to_dict()

    try:
        farm = reg.create_farm(
            farm_id=farm_id,
            name=name,
            turbine_count=turbine_count,
            turbine_spec=turbine_spec,
            wind_profile=body.get("wind_profile", {}),
            grid_profile=body.get("grid_profile", {}),
            layout=body.get("layout", {}),
            location=body.get("location", ""),
            description=body.get("description", ""),
            is_offshore=bool(body.get("is_offshore", False)),
            timezone=body.get("timezone"),
        )
    except ValueError as exc:  # 無效的時區名稱
        raise HTTPException(400, str(exc))
    return {"status": "created", "farm": farm.to_dict()}


# ── Update ──────────────────────────────────────────────────────────────

@router.patch(
    "/{farm_id}",
    # WMOM-20260716-05h-2：farm 編輯＝主管
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def update_farm(farm_id: str, body: dict):
    """Update farm metadata (name, description, location, turbine_spec, timezone, etc.).

    時區變更在下次啟動該風場的模擬時生效。
    """
    try:
        farm = _get_registry().update_farm(farm_id, **body)
    except ValueError as exc:  # 無效的時區名稱 / is_offshore 型別
        raise HTTPException(400, str(exc))
    if not farm:
        raise HTTPException(404, f"Farm not found: {farm_id}")
    return {"status": "updated", "farm": farm.to_dict()}


# ── Delete ──────────────────────────────────────────────────────────────

@router.delete(
    "/{farm_id}",
    # WMOM-20260716-05h-2：刪 farm＝系統管理員（破壞性）
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def delete_farm(farm_id: str):
    """Delete a wind farm and all its data. Requires confirmation."""
    reg = _get_registry()
    if reg.get_active_farm_id() == farm_id:
        raise HTTPException(400, "Cannot delete the active farm. Switch to another farm first.")
    ok = reg.delete_farm(farm_id)
    if not ok:
        raise HTTPException(404, f"Farm not found: {farm_id}")
    return {"status": "deleted", "farm_id": farm_id}


# ── Activate ────────────────────────────────────────────────────────────

@router.post(
    "/{farm_id}/activate",
    # WMOM-20260716-05h-2：切換啟用 farm＝主管
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def activate_farm(farm_id: str):
    """Switch the simulator to this wind farm.

    正式評測進行中不切換（409）：回放與 token 存在目前風場的 DB，切走後受測端重連會被當成無效 token、
    REST 的回放 id 也會對到另一個風場的回放（WMOM-20261022-01）。
    """
    b = _get_broker()
    if farm_id != b.active_farm_id and b.storage is not None:
        from server.replay import running_evaluations

        running = await asyncio.to_thread(running_evaluations, b.storage)
        if running:
            ids = ", ".join(f"#{view['id']}" for view in running)
            raise HTTPException(409, f"正式評測進行中（回放 {ids}）：評測結束或撤銷後再切換風場")
    ok = b.switch_farm(farm_id)
    if not ok:
        raise HTTPException(404, f"Farm not found: {farm_id}")
    farm = _get_registry().get_farm(farm_id)
    return {"status": "activated", "farm": farm.to_dict()}


# ── Clone ───────────────────────────────────────────────────────────────

@router.post(
    "/{farm_id}/clone",
    # WMOM-20260716-05h-2：clone farm＝主管
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def clone_farm(farm_id: str, body: dict):
    """Clone a farm. Options: new_name (required), new_farm_id, include_data (bool)."""
    reg = _get_registry()
    new_name = body.get("new_name")
    if not new_name:
        raise HTTPException(400, "new_name is required")

    new_id = body.get("new_farm_id") or _sanitize_id(new_name)
    if reg.get_farm(new_id):
        raise HTTPException(409, f"Farm already exists: {new_id}")

    include_data = body.get("include_data", False)
    farm = reg.clone_farm(farm_id, new_id, new_name, include_data=include_data)
    if not farm:
        raise HTTPException(404, f"Source farm not found: {farm_id}")
    return {"status": "cloned", "farm": farm.to_dict()}


# ── Export ──────────────────────────────────────────────────────────────

@router.post(
    "/{farm_id}/export",
    # WMOM-20260716-05h-2：匯出＝讀取，任何登入者
    dependencies=[Depends(require_authenticated())],
)
async def export_farm(farm_id: str, body: dict = {}):
    """Export a farm as a zip file containing CSV data, events, and config.

    Options:
      format: "csv" (default)
      include_events: true (default)
    """
    reg = _get_registry()
    farm = reg.get_farm(farm_id)
    if not farm:
        raise HTTPException(404, f"Farm not found: {farm_id}")

    from server.storage import Storage
    db_path = str(reg.get_farm_db_path(farm_id))
    if not Path(db_path).exists():
        raise HTTPException(404, f"No data for farm: {farm_id}")

    storage = Storage(db_path=db_path)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("config.json", json.dumps(farm.to_dict(), indent=2, ensure_ascii=False))

        history = storage.query_history(limit=500000)
        if history:
            import csv
            csv_buf = io.StringIO()
            writer = csv.DictWriter(csv_buf, fieldnames=history[0].keys())
            writer.writeheader()
            for row in history:
                writer.writerow(dict(row))
            zf.writestr("history.csv", csv_buf.getvalue())

        include_events = body.get("include_events", True)
        if include_events:
            events = storage.query_events(limit=100000)
            if events:
                events_list = [dict(e) for e in events]
                zf.writestr("events.json", json.dumps(events_list, indent=2, ensure_ascii=False))

    buf.seek(0)
    # 下載檔名用伺服器本地時間（給人看的檔名，不是儲存 / 比較用的時間戳）
    filename = f"{farm_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Dataset Generation（已移除，WMOM-20261021-05）──
# 原 ``POST /api/farms/{farm_id}/datasets/generate`` 自寫一套步進迴圈，檢查從未啟動的
# ``sim._running`` 而永遠產出 0 筆，也不記事件與標準答案。資料集請改用命名情境
# （``POST /api/config/simulation/generate-bulk`` 帶 ``name``），再以
# ``GET /api/scenarios/{id}/pack`` 匯出資料包。
