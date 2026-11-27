import asyncio
import json
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from datetime import datetime

    from modules.cost.services.failure_rates import FailureObservations
    from modules.workflow.domain.work_order import WorkOrder, WorkOrderStatus
    from simulator.engine import WindFarmSimulator

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

    # Determine active farm (used when a source is later selected). WMOM-20260719-04：
    # 開機**不再自動啟動任何資料來源**——使用者登入後於「選擇資料來源」頁挑（實接/即時模擬/
    # 產生情境/調閱過去情境），選定才由 /api/source/select 呼叫 activate_* 啟動。這修掉
    # 「一進系統就自動以預設風場產生資料」。
    farm_id = farm_registry.ensure_default_farm()

    _apply_continuous_run_settings(farm_id)

    # 運維閉環的接線（WMOM-20261125-04）：工單的狀態改變通知到閉環；報表的可用率由運轉狀態紀錄提供
    from modules.reporting.routers.reporting_router import set_availability_provider, set_revenue_provider
    from modules.workflow.hooks import add_work_order_listener, remove_work_order_listener
    add_work_order_listener(_on_work_order)
    set_availability_provider(_availability_for_report)
    set_revenue_provider(_revenue_for_report)
    # 成本模組的故障率回饋讀本風場的維修紀錄（WMOM-20261127-07）
    from modules.cost.services import failure_rates as _failure_rates
    _failure_rates.set_observation_provider(_failure_observations_for_cost)

    # Start WebSocket broadcast task（未選來源前 broker.get_all_turbines() 回空、不廣播）
    task = asyncio.create_task(_ws_broadcast_loop())

    # 選配：即時模擬的 OPC UA server（模仿 Bachmann Z72 tag，WMOM-20261021-07）；WMOM_OPCUA_ENABLE=true 才起，
    # 也才載入 asyncua（沒開就不影響啟動）
    from server.opcua_config import opcua_enabled
    opcua = None
    if opcua_enabled():
        from server.opcua_server import start_live_from_env
        opcua = await start_live_from_env(broker)
        if opcua is not None:
            print(f"[Server] OPC UA (live simulation): {opcua.server.endpoint}")

    yield

    # Shutdown：只收掉自己登記的東西（別人換過 provider 就不動），閉環關回去——同一個 process 之後再用到
    # 這個 broker 時不會還開著
    remove_work_order_listener(_on_work_order)
    from modules.reporting.routers import reporting_router as _reporting
    if _reporting._availability_provider is _availability_for_report:
        set_availability_provider(None)
    if _reporting._revenue_provider is _revenue_for_report:
        set_revenue_provider(None)
    if _failure_rates.get_observation_provider() is _failure_observations_for_cost:
        _failure_rates.set_observation_provider(None)
    if broker._om_loop is not None:
        broker._om_loop.enabled = False
    task.cancel()
    try:
        if opcua is not None:
            await opcua.stop()
    finally:
        if broker.simulator and broker.simulator.modbus_server:
            broker.simulator.modbus_server.stop()
        broker.stop()
        print("[Server] Shutdown complete")


def _apply_continuous_run_settings(farm_id: str) -> None:
    """依環境變數設定持續運轉的仿真風場（WMOM-20261125-03-b；兩個都要明確開，預設都關）。

    - ``WMOM_LIVE_RESUME=true``：即時模擬的狀態定期存檔、啟動時還原（重啟前鎖存的跳機、疲勞、結垢都還在）。
    - ``WMOM_AUTOSTART_SOURCE=simulation``：開機就啟動即時模擬，不等人登入選來源。啟動失敗不讓伺服器起不來，
      留在未選來源的狀態。
    - ``WMOM_RAW_RETENTION_DAYS``（預設 183）：10 秒原始讀值總共留幾天，循環保存；超過熱資料天數的部分在
      每日 Parquet 歸檔裡。0＝不歸檔，只留熱資料天數（WMOM-20261125-03-c）。
    - ``WMOM_RAW_HOT_DAYS``（預設 3）：其中留在 SQLite 的最近幾天。
    - ``WMOM_LIVE_RETRIP``（預設開）：即時模擬裡跳過機的故障不鎖機組——PLC 的鎖存解除後機組自動重啟，故障還在就
      再跳一次，超過每小時上限才由 A039 封鎖等人處理（WMOM-20261125-06-a）。批次情境不受影響。
    - ``WMOM_FAULT_GENERATOR``（預設關）：風場還沒存過設定時，機率式故障產生器開不開（WMOM-20261125-06-b）。
    - ``WMOM_CREW``（預設關）：風場還沒存過設定時，模擬維修班開不開（WMOM-20261125-06-d）。
    - ``WMOM_INSPECTION_PLAN``（預設關）：風場還沒存過設定時，自動定檢計畫開不開（WMOM-20261127-03）。三者存過
      之後以 ``PUT /api/operations/fault-generator`` / ``/crew`` / ``/inspection-plan`` 存的設定為準。
    - ``WMOM_OM_LOOP``（預設開）：運維閉環——即時模擬的跳機自動開工單、工單開工讓機組進維修模式、完工修復
      機組、記運轉狀態供可用率計算（WMOM-20261125-04）。

    Args:
        farm_id: 啟用中的風場（只用在啟動訊息）。
    """
    broker.checkpoint_enabled = _env_flag("WMOM_LIVE_RESUME")
    # 運維閉環預設開：跳機開單、工單完工修復、運轉狀態紀錄（WMOM-20261125-04）；WMOM_OM_LOOP=false 關掉
    om_loop_on = os.environ.get("WMOM_OM_LOOP", "true").strip().lower() not in ("false", "0", "no", "off")
    if om_loop_on or broker._om_loop is not None:
        broker.om_loop.enabled = om_loop_on
    # 跳過機的故障不鎖機組：鎖存解除後自動重啟、故障還在就再跳，超過每小時上限由 A039 封鎖（預設開）
    broker.live_retrip = os.environ.get("WMOM_LIVE_RETRIP", "true").strip().lower() not in ("false", "0", "no", "off")
    # 故障產生器 / 模擬維修班 / 自動定檢計畫：風場還沒存過設定時的預設（預設都關）。存過之後以風場的設定為準
    broker.default_live_settings = {
        "fault_generator": {"enabled": _env_flag("WMOM_FAULT_GENERATOR")},
        "crew": {"enabled": _env_flag("WMOM_CREW")},
        "inspection_plan": {"enabled": _env_flag("WMOM_INSPECTION_PLAN")},
    }
    broker.raw_hot_days = _env_days("WMOM_RAW_HOT_DAYS", broker.RAW_RETENTION_DAYS, minimum=1)
    broker.archive_days = _env_days("WMOM_RAW_RETENTION_DAYS", broker.ARCHIVE_RETENTION_DAYS, minimum=0)
    autostart = os.environ.get("WMOM_AUTOSTART_SOURCE", "").strip().lower()
    if autostart == "simulation":
        try:
            activate_simulation(run_loop=True)
            resumed = "resumed from checkpoint" if broker.live_restored else "fresh state"
            print(f"[Server] Active farm: {farm_id} (autostart: live simulation, {resumed})")
            return
        except Exception as exc:  # noqa: BLE001  自動啟動失敗不能讓伺服器起不來
            print(f"[Server] Warning: 自動啟動即時模擬失敗（{exc!r}），等待選擇資料來源")
    elif autostart:
        print(f"[Server] Warning: WMOM_AUTOSTART_SOURCE={autostart!r} 不支援（只認 simulation），不自動啟動")
    print(f"[Server] Active farm: {farm_id} (idle — awaiting source selection)")


def _on_work_order(work_order: 'WorkOrder', action: str, from_status: 'Optional[WorkOrderStatus]') -> None:
    """工單掛鉤 → 目前 broker 的運維閉環（每次都重新取 ``broker``：測試會換掉它）。"""
    loop = broker._om_loop_if_enabled()
    if loop is not None:
        loop.on_work_order(work_order, action, from_status)


def _availability_for_report(farm_id: str, start: 'datetime', end: 'datetime') -> 'Optional[tuple[float, float]]':
    """報表的可用率：由運轉狀態紀錄計算（WMOM-20261125-04）。

    只算目前啟用中的風場；閉環沒開、別的風場、這段時間沒有紀錄時回 None（報表退回由工單工時推估）。

    Args:
        farm_id: 風場 ID。
        start: 期間起點。
        end: 期間終點。

    Returns:
        （時間可用率, 發電量可用率），或 None。
    """
    loop = broker._om_loop_if_enabled()
    if loop is None or farm_id != broker._active_farm_id:
        return None
    farm = loop.availability(start, end)["farm"]
    time_availability, energy_availability = farm["time_availability"], farm["energy_availability"]
    if time_availability is None or energy_availability is None:
        return None
    return float(time_availability), float(energy_availability)


def _revenue_for_report(farm_id: str, start: 'datetime', end: 'datetime') -> 'Optional[dict]':
    """報表的發電收入：運轉狀態紀錄 × 電價（WMOM-20260504-11）。條件同 ``_availability_for_report``。

    Args:
        farm_id: 風場 ID。
        start: 期間起點。
        end: 期間終點。

    Returns:
        ``{"currency", "kwh_price", "energy_kwh", "revenue", "lost_planned", "lost_unplanned", "fixed_costs",
        "work_order_labour"}``，或 None。``fixed_costs``＝這段時間的人員與設備固定成本（依紀錄的天數攤）；
        ``work_order_labour``＝帳本裡工單的人工分錄（已含在人員固定成本裡，報表不另算，WMOM-20261127-02）。
    """
    loop = broker._om_loop_if_enabled()
    if loop is None or farm_id != broker._active_farm_id:
        return None
    availability = loop.availability(start, end)
    farm = availability["farm"]
    if not farm.get("recorded_hours"):
        return None
    from modules.cost.repository.cost_ledger import CostLedgerCategory, CostLedgerSourceType
    from modules.cost.repository.cost_ledger_repository import get_cost_ledger_repository
    from modules.cost.services.simulation_costs import farm_rates, recorded_farm_days, revenue
    rates = farm_rates(farm_id, broker.farm_registry)
    fixed = loop.fixed_costs(farm_id, availability).for_days(recorded_farm_days(availability))
    labour = get_cost_ledger_repository(str(broker.storage.db_path)).summary_by_category(
        farm_id=farm_id, from_date=start, to_date=end,
        source_type=CostLedgerSourceType.WORK_ORDER).get(CostLedgerCategory.LABOUR, 0)
    return {"currency": rates.currency, "kwh_price": rates.kwh_price,
            "energy_kwh": float(farm.get("energy_kwh") or 0.0), **revenue(farm, rates),
            "fixed_costs": float(fixed["total"]), "work_order_labour": float(labour)}


def _failure_observations_for_cost(farm_id: str) -> 'Optional[FailureObservations]':
    """成本模組故障率回饋用的維修紀錄（WMOM-20261127-07）：正在運轉的仿真風場、從有紀錄到風場時鐘的現在。

    Args:
        farm_id: 風場 ID。

    Returns:
        ``failure_rates.FailureObservations``；不是啟用中的風場、閉環沒開或沒有運轉紀錄時是 None。
    """
    loop = broker._om_loop_if_enabled()
    if loop is None or farm_id != broker._active_farm_id:
        return None
    observations = loop.failure_observations(*loop.history_window())
    return observations if observations.turbine_years > 0 else None


def _env_days(name: str, default: int, minimum: int) -> int:
    """讀一個天數的環境變數；沒設用預設值，不是整數或小於下限就印警告、用預設值。

    Args:
        name: 環境變數名稱。
        default: 沒設或無效時的值。
        minimum: 允許的最小值。

    Returns:
        天數。
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        value = minimum - 1
    if value < minimum or value > 36500:
        print(f"[Server] Warning: {name}={raw!r} 不是 {minimum} 到 36500 的整數，改用預設 {default}")
        return default
    return value


def _env_flag(name: str) -> bool:
    """環境變數是否為真（true / 1 / yes / on，大小寫不拘）。"""
    return os.environ.get(name, "").strip().lower() in ("true", "1", "yes", "on")


def _stop_modbus() -> None:
    """停掉目前 simulator 綁的 Modbus server（換來源前避免 port 佔用）。"""
    if broker.simulator and broker.simulator.modbus_server:
        try:
            broker.simulator.modbus_server.stop()
        except Exception as e:  # noqa: BLE001 — 停 server 失敗不該擋住切換
            print(f"[Server] Warning: could not stop Modbus server: {e}")


def _start_modbus_for(simulator: 'Optional[WindFarmSimulator]') -> None:
    """為 simulator 起選配的 Modbus TCP server；失敗則降級為「無 Modbus 模擬」。

    Modbus TCP 是選配（給外部 Modbus client 讀）。建構失敗（pymodbus 未安裝 / 版本不相容導致
    ``ModbusSimServer`` 建構或 import 失敗，如本專案 requirements 釘 <3.8 而環境裝了 3.14）
    不該擋住整個模擬來源的啟動——降級為 ``modbus_server=None`` 而非讓 activate 500。
    註：port 佔用不會走到這裡——實際綁 port 的 ``StartTcpServer`` 在 ``start()`` 起的背景
    thread 內跑且自帶 try/except，例外不會往上冒到這條路徑。抽成獨立函式以便單元測試降級行為。
    """
    if simulator is None or simulator.modbus_server:
        return
    try:
        from simulator.modbus_server import ModbusSimServer
        modbus_port = int(os.environ.get("MODBUS_PORT", "5020"))
        simulator.modbus_server = ModbusSimServer(
            port=modbus_port, turbine_count=len(simulator.turbines)
        )
        simulator.modbus_server.start()
    except Exception as e:  # noqa: BLE001
        simulator.modbus_server = None
        print(f"[Server] Warning: Modbus TCP server not started: {e}")


def activate_simulation(run_loop: bool = True, fresh: bool = False) -> None:
    """啟動模擬來源：起 simulator + 套風場 spec（+ Modbus）。由 ``/api/source/select`` 呼叫、可重入。

    ``fresh=True``：即使開了重啟續跑（``WMOM_LIVE_RESUME``）也不還原存檔，風場從頭開始（WMOM-20261125-03-b）。

    ``run_loop=True``（「即時模擬」）＝自由跑連續產資料 + 起 Modbus TCP（給外部 client 讀即時值）。
    ``run_loop=False``（「產生情境」，DEC-20260720-01 PR B）＝只建 simulator 供批次生成、**不自由跑**、
    **不起 Modbus**（沒有連續即時值可讀）。source_kind 由 broker 依 run_loop 設為 simulation / scenario。
    """
    farm_id = farm_registry.ensure_default_farm()
    farm = farm_registry.get_farm(farm_id)
    turbine_count = farm.turbine_count if farm else 14

    _stop_modbus()  # 舊 simulator 若有 Modbus，先停（switch_mode 會換掉 simulator 物件）
    broker.switch_mode(
        DataSourceConfig(mode=DataSourceMode.SIMULATION),
        SimulationConfig(turbineCount=turbine_count),
        run_loop=run_loop,
        fresh=fresh,
    )

    if farm and farm.turbine_spec and broker.simulator:
        from simulator.physics.turbine_physics import TurbineSpec
        try:
            spec = TurbineSpec.from_farm_dict(farm.turbine_spec)
            for model in broker.simulator.turbines.values():
                # 規格相同就不重套：update_spec 會重建 PLC 保護層，從存檔還原的鎖存與計數會被清掉
                if model.spec != spec:
                    model.update_spec(spec)
        except Exception as e:  # noqa: BLE001
            print(f"[Server] Warning: could not apply farm spec: {e}")

    if run_loop:
        _start_modbus_for(broker.simulator)
    kind = "simulation (live free-run)" if run_loop else "scenario (batch, no free-run)"
    print(f"[Server] Simulation source active — {kind}, {turbine_count} turbines")


def activate_live(mode: DataSourceMode = DataSourceMode.OPC_DA) -> None:
    """啟動實際資料對接來源（OPC DA）。"""
    _stop_modbus()
    broker.switch_mode(DataSourceConfig(mode=mode))
    print(f"[Server] Live source active ({mode.value})")


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
# X-API-Key：對外唯讀 API（/api/ext/v1）的金鑰 header（WMOM-20261125-02）
CORS_ALLOW_HEADERS = ["Content-Type", "Authorization", "Accept", "Origin", "X-Requested-With", "X-API-Key"]

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
from server.routers.replay import router as replay_router  # noqa: E402
from server.routers.source import router as source_router  # noqa: E402
# WMOM-20261125-02：對外唯讀 API（外部系統以 API 金鑰取可觀測資料與警報）
from server.routers.external import router as external_router  # noqa: E402
from server.routers.operations import router as operations_router  # noqa: E402

# WMOM-20260504-07 + -20260509-05: cost module routers (M2 cost API + ledger query)
from modules.cost.routers import (  # noqa: E402
    ledger_router as cost_ledger_router,
    router as cost_router,
)

# WMOM-20260504-17 / -18 / -20260509-03 / -04 / -20260505-22 / -20260505-21:
# workflow + approval + material_request + inventory + inspection_schedule + day_work_form
from modules.workflow.routers import (  # noqa: E402
    approval_router,
    day_work_form_router,
    inspection_router,
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
app.include_router(replay_router)
app.include_router(source_router)
app.include_router(external_router)
app.include_router(operations_router)
app.include_router(cost_router)
app.include_router(cost_ledger_router)
app.include_router(workflow_router)
app.include_router(approval_router)
app.include_router(material_request_router)
app.include_router(inventory_router)
app.include_router(inspection_router)
app.include_router(day_work_form_router)
app.include_router(reporting_router)
app.include_router(knowledge_router)
app.include_router(auth_router)


@app.get("/api/health")
async def health():
    """Return system health status including data source mode and turbine count."""
    return {
        "status": "ok",
        "mode": broker.mode.value,
        "sourceActive": broker.source_active,
        "sourceKind": broker.source_kind,
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
