import asyncio
import json
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import List

from server.models import DataSourceConfig, DataSourceMode, SimulationConfig
from server.farm_registry import FarmRegistry
from server.data_broker import DataBroker

# Global instances
farm_registry = FarmRegistry()
broker = DataBroker(farm_registry=farm_registry)

# WebSocket connection manager
ws_clients: List[WebSocket] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle: start simulator and Modbus on startup, clean up on shutdown."""
    # WMOM-20260510-01 Part A：啟動時 log dev mode warning（若 WMOM_DEV_MODE=true）。
    # helper 已用 logging.warning；額外 print 到 stdout 是為了確保 lifespan 階段
    # logging handler 尚未配齊時操作者仍看得到（雙保險 — 訊息字串一致，便於 log
    # aggregator dedupe）。
    from shared.dev_mode import log_dev_mode_warning_if_enabled
    _DEV_MODE_BANNER = (
        "[WARNING] WMOM_DEV_MODE active - separation-of-duties checks bypassed "
        "(dispatcher==assignee allowed, same actor may sign consecutive signoff levels). "
        "DO NOT use this build for production."
    )
    if log_dev_mode_warning_if_enabled():
        print(f"[Server] {_DEV_MODE_BANNER}")

    # Migrate legacy DB if it exists
    from pathlib import Path
    legacy_path = Path(__file__).parent.parent / "wind_farm_data.db"
    migrated = farm_registry.migrate_legacy_db(legacy_path)
    if migrated:
        print(f"[Server] Migrated legacy database to farm '{migrated}'")

    # Determine active farm and its config
    farm_id = farm_registry.ensure_default_farm()
    farm = farm_registry.get_farm(farm_id)
    turbine_count = farm.turbine_count if farm else 14
    print(f"[Server] Active farm: {farm_id} ({turbine_count} turbines)")

    # Startup: start simulator with active farm
    config = DataSourceConfig(mode=DataSourceMode.SIMULATION)
    sim_config = SimulationConfig(turbineCount=turbine_count)
    broker.start(config, sim_config)

    # Apply farm turbine spec if defined
    if farm and farm.turbine_spec and broker.simulator:
        from simulator.physics.turbine_physics import TurbineSpec
        try:
            spec = TurbineSpec.from_dict(farm.turbine_spec)
            for model in broker.simulator.turbines.values():
                model.update_spec(spec)
            print("[Server] Applied turbine spec from farm config")
        except Exception as e:
            print(f"[Server] Warning: could not apply farm spec: {e}")

    print(f"[Server] Wind farm simulator started with {turbine_count} turbines")

    # Auto-start Modbus TCP server
    if broker.simulator:
        from simulator.modbus_server import ModbusSimServer
        modbus_port = int(os.environ.get("MODBUS_PORT", "5020"))
        broker.simulator.modbus_server = ModbusSimServer(
            port=modbus_port, turbine_count=len(broker.simulator.turbines)
        )
        broker.simulator.modbus_server.start()
        print(f"[Server] Modbus TCP server started on port {modbus_port}")

    # Start WebSocket broadcast task
    task = asyncio.create_task(_ws_broadcast_loop())

    yield

    # Shutdown
    task.cancel()
    if broker.simulator and broker.simulator.modbus_server:
        broker.simulator.modbus_server.stop()
    broker.stop()
    print("[Server] Shutdown complete")


app = FastAPI(
    title="Wind Farm Monitor API",
    description="Real-time wind farm monitoring with simulation and OPC DA support",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS：browser spec 禁止 `allow_origins=["*"]` 配 `allow_credentials=True` 同時生效
# （等於沒設），fix 為列舉 dev / docker localhost 來源。生產可從 env 讀。
import os as _os  # noqa: E402

_default_cors_origins = [
    "http://localhost:3100",   # Vite dev (本 repo 預設)
    "http://localhost:5173",   # Vite default
    "http://localhost:5179",   # legacy Vite (handoff doc 提的)
    "http://127.0.0.1:3100",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5179",
]
_env_cors = _os.environ.get("WMOM_CORS_ORIGINS", "").strip()
_cors_origins = (
    [o.strip() for o in _env_cors.split(",") if o.strip()]
    if _env_cors
    else _default_cors_origins
)

# methods / headers 明列（不用 ["*"]）——舊版 Starlette（< 0.19）不會把 ["*"] 展開成實際
# methods，導致 JSON POST 的 preflight（OPTIONS）在 method 檢查落空被判 400、被瀏覽器 CORS
# 擋下（GET 不觸發 preflight 故正常，只有 POST/PUT/PATCH 掛）。明列可跨 Starlette 版本穩定，
# 也是帶 credentials 時 CORS 的較安全寫法（利客戶現場部署，環境版本不一）。
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
CORS_ALLOW_HEADERS = ["Content-Type", "Authorization", "Accept", "Origin", "X-Requested-With"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=CORS_ALLOW_METHODS,
    allow_headers=CORS_ALLOW_HEADERS,
)

# Register routers (after app creation to avoid circular imports)
from server.routers.turbines import router as turbines_router  # noqa: E402
from server.routers.config import router as config_router  # noqa: E402
from server.routers.export import router as export_router  # noqa: E402
from server.routers.faults import router as faults_router  # noqa: E402
from server.routers.i18n import router as i18n_router  # noqa: E402
from server.routers.modbus import router as modbus_router  # noqa: E402
from server.routers.control import router as control_router  # noqa: E402
from server.routers.maintenance import router as maintenance_router  # noqa: E402
from server.routers.farms import router as farms_router  # noqa: E402
from server.routers.scenarios import router as scenarios_router  # noqa: E402

# WMOM-20260504-07 + -20260509-05: cost module routers (M2 cost API + ledger query)
from modules.cost.routers import (  # noqa: E402
    ledger_router as cost_ledger_router,
    router as cost_router,
)

# WMOM-20260504-17 / -18 / -20260509-03 / -04: workflow + approval + material_request + inventory
from modules.workflow.routers import (  # noqa: E402
    approval_router,
    inventory_router,
    material_request_router,
    router as workflow_router,
)

# WMOM-20260509-08: reporting router (monthly PDF + annual budget)
from modules.reporting.routers import router as reporting_router  # noqa: E402

# WMOM-20260603-01 (M5-6): knowledge router (警報 → RAG 手冊檢索)
from modules.knowledge.routers import router as knowledge_router  # noqa: E402

# DEC-20260716-01 (M6-4): auth router（JWT 登入 + 目前身分）；非破壞式，既有 router 不受影響
from modules.auth.routers import router as auth_router  # noqa: E402

app.include_router(turbines_router)
app.include_router(config_router)
app.include_router(export_router)
app.include_router(faults_router)
app.include_router(i18n_router)
app.include_router(modbus_router)
app.include_router(control_router)
app.include_router(maintenance_router)
app.include_router(farms_router)
app.include_router(scenarios_router)
app.include_router(cost_router)
app.include_router(cost_ledger_router)
app.include_router(workflow_router)
app.include_router(approval_router)
app.include_router(material_request_router)
app.include_router(inventory_router)
app.include_router(reporting_router)
app.include_router(knowledge_router)
app.include_router(auth_router)


@app.get("/api/health")
async def health():
    """Return system health status including data source mode and turbine count."""
    return {
        "status": "ok",
        "mode": broker.mode.value,
        "turbineCount": len(broker.turbine_ids),
        "activeFarmId": broker.active_farm_id,
    }


@app.websocket("/ws/realtime")
async def websocket_realtime(ws: WebSocket):
    """Handle a WebSocket connection for real-time SCADA data streaming."""
    await ws.accept()
    ws_clients.append(ws)
    try:
        while True:
            # Keep connection alive, receive any client messages (ignored)
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if ws in ws_clients:
            ws_clients.remove(ws)


async def _ws_broadcast_loop():
    """Broadcast turbine data to all WebSocket clients every 2 seconds."""
    while True:
        await asyncio.sleep(2)
        if not ws_clients:
            continue

        turbines = broker.get_all_turbines()
        if not turbines:
            continue

        data = json.dumps(
            [t.model_dump(mode='json') for t in turbines],
            default=str,
        )

        disconnected = []
        for ws in ws_clients:
            try:
                await ws.send_text(data)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            if ws in ws_clients:
                ws_clients.remove(ws)
