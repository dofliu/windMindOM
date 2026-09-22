from datetime import datetime
from typing import List, Optional, Set

from fastapi import APIRouter, HTTPException, Depends
from modules.auth.dependencies import require_authenticated, require_role
from modules.auth.roles import Role
from server.models import DataSourceConfig, SimulationConfig, DataSourceMode, WindOverrideRequest, GridOverrideRequest
from simulator.physics.fault_engine import FAULT_SCENARIOS, TestPlanStep

router = APIRouter(prefix="/api/config", tags=["config"])


def get_broker():
    """Return the shared DataBroker instance from the application."""
    from server.app import broker
    return broker


def _parse_fault_schedule(raw: List[dict], valid_turbine_ids: Set[str]) -> List[TestPlanStep]:
    """把 API body 的 ``fault_schedule`` 轉成排序好且驗證過的 ``TestPlanStep`` 清單。

    Scenario 模式（DEC-20260718-01）用：讓使用者定義「在某 sim-time 對某機組注入某故障」。
    每筆接受（dict）：
      - ``scenario_id``（必填，須在 ``FAULT_SCENARIOS``）
      - ``turbine_id``（必填，須為現有機組）
      - ``at_hour`` 或 ``offset_seconds``（擇一；注入的 sim-time 位移，預設 0）
      - ``severity_rate``（選填，預設 0.0002 ≈ 18 小時到滿）
      - ``initial_severity``（選填，預設 0.0）
      - ``description``（選填）

    Args:
        raw: API body 的 fault_schedule 原始清單。
        valid_turbine_ids: 目前 simulator 的機組 ID 集合，用於驗證 turbine_id。

    Returns:
        依 ``offset_seconds`` 升冪排序的 ``TestPlanStep`` 清單（空清單代表無排程）。

    Raises:
        HTTPException: raw 非陣列 / 某筆非物件 / 數值欄位格式錯誤 / 負位移時 400；
            未知情境 / 未知機組時 404。
    """
    if not isinstance(raw, list):
        raise HTTPException(400, "fault_schedule 必須是陣列")

    steps: List[TestPlanStep] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise HTTPException(400, f"fault_schedule[{i}] 必須是物件")

        scenario_id = item.get("scenario_id")
        turbine_id = item.get("turbine_id")
        if scenario_id not in FAULT_SCENARIOS:
            raise HTTPException(
                404,
                f"fault_schedule[{i}]: 未知故障情境 {scenario_id!r}；可用：{sorted(FAULT_SCENARIOS)}",
            )
        if turbine_id not in valid_turbine_ids:
            raise HTTPException(404, f"fault_schedule[{i}]: 未知機組 {turbine_id!r}")

        # 數值欄位一律經 float()；畸形輸入（字串/None/list）→ 乾淨 400 而非未預期 500。
        try:
            # offset：優先 offset_seconds（秒），其次 at_hour（小時 × 3600）。
            if "offset_seconds" in item:
                offset = float(item["offset_seconds"])
            else:
                offset = float(item.get("at_hour", 0.0)) * 3600.0
            severity_rate = float(item.get("severity_rate", 0.0002))
            initial_severity = float(item.get("initial_severity", 0.0))
        except (TypeError, ValueError):
            raise HTTPException(400, f"fault_schedule[{i}]: 數值欄位格式錯誤（offset/at_hour/severity_rate/initial_severity 須為數字）")

        if offset < 0:
            raise HTTPException(400, f"fault_schedule[{i}]: offset 不可為負")

        steps.append(TestPlanStep(
            offset_seconds=offset,
            scenario_id=scenario_id,
            turbine_id=turbine_id,
            severity_rate=severity_rate,
            initial_severity=initial_severity,
            description=str(item.get("description", "")),
        ))

    return sorted(steps, key=lambda s: s.offset_seconds)


@router.get(
    "",
    # WMOM-20260716-05h-2：檢視＝任何登入者
    dependencies=[Depends(require_authenticated())],
)
async def get_config():
    """Get current data source configuration."""
    b = get_broker()
    return {
        "mode": b.mode.value,
        "turbineCount": len(b.turbine_ids),
        "isRunning": b.simulator.is_running if b.simulator else False,
    }


@router.post(
    "/datasource",
    # WMOM-20260716-05h-2：設定變更＝主管
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def set_datasource(config: DataSourceConfig):
    """Switch data source mode (simulation / opc_da)."""
    b = get_broker()
    b.switch_mode(config)
    return {"status": "ok", "mode": b.mode.value}


@router.post(
    "/simulation",
    # WMOM-20260716-05h-2：設定變更＝主管
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def set_simulation(config: SimulationConfig):
    """Update simulation parameters. Only restarts if turbine count changed."""
    b = get_broker()

    # Must-fix（WMOM-20260720-04 (3)）：definitive fix——前端 #146 的來源 gate 只能 best-effort
    # （設定頁 ≤5s 輪詢窗蓋不到「編輯到一半來源被切走」的空隙）。active source 非即時模擬
    # （view/live/scenario）時，本端點若照舊往下跑會落到 switch_mode(SIMULATION)，悄悄把
    # live 斷線、或打斷情境調閱／產生情境的凍結資料集語意。改為直接拒絕，要求使用者先在
    # 「選擇資料來源」切回即時模擬再調整參數。
    if b.source_kind not in (None, "simulation"):
        raise HTTPException(
            409,
            f"目前來源為 {b.source_kind}，非即時模擬中，不可在此調整模擬參數"
            "（會悄悄切換資料來源）。請先到「選擇資料來源」切回即時模擬。",
        )

    # Only restart if turbine count actually changed
    current_count = len(b.turbine_ids) if b.simulator else 0
    if b.simulator and b.simulator.is_running and config.turbineCount == current_count:
        # WMOM-20260718-01 fix：base wind speed 之前在此被丟掉（只套 turbulence），
        # 導致 Settings 改風速對跑著的 sim 完全無反應。改用 wind override 一併套用
        # base wind + turbulence，讓「改風速 → farm 基準風速改變 → 發電對應」成立
        # （各機組仍由 turbulence / wake 在此基準上變化）。返回自動日變風況請用
        # Wind Control 的 `auto` profile（/api/config/wind/clear）。
        b.simulator.wind_model.set_override(
            wind_speed=config.baseWindSpeed,
            turbulence=config.turbulenceIntensity,
        )
        return {
            "status": "ok",
            "turbineCount": config.turbineCount,
            "baseWindSpeed": config.baseWindSpeed,
            "restarted": False,
        }

    # Turbine count changed — full restart required
    ds_config = DataSourceConfig(mode=DataSourceMode.SIMULATION)
    b.switch_mode(ds_config, config)
    return {
        "status": "ok",
        "turbineCount": config.turbineCount,
        "baseWindSpeed": config.baseWindSpeed,
        "restarted": True,
    }


@router.get(
    "/wind",
    # WMOM-20260716-05h-2：檢視＝任何登入者
    dependencies=[Depends(require_authenticated())],
)
async def get_wind_status():
    """Get current wind model status (auto/manual, override values)."""
    b = get_broker()
    if not b.simulator:
        raise HTTPException(400, "Simulator not running")
    return b.simulator.wind_model.get_status()


@router.post(
    "/wind",
    # WMOM-20260716-05h-2：設定變更＝主管
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def set_wind(req: WindOverrideRequest):
    """Set wind conditions manually, or activate a profile.

    Profiles: calm, moderate, rated, strong, storm, gusty, ramp_up, ramp_down, auto
    Or set individual values: windSpeed, windDirection, ambientTemp, turbulence
    """
    b = get_broker()
    if not b.simulator:
        raise HTTPException(400, "Simulator not running")

    wm = b.simulator.wind_model
    b.close_open_events("wind", source="config")
    if req.profile:
        wm.set_profile(req.profile)
    else:
        wm.set_override(
            wind_speed=req.windSpeed,
            wind_direction=req.windDirection,
            ambient_temp=req.ambientTemp,
            turbulence=req.turbulence,
        )
    b.record_event(
        event_type="wind",
        source="config",
        title=f"Wind config updated{f': {req.profile}' if req.profile else ''}",
        detail="Wind profile or override changed",
        payload=req.model_dump(),
    )
    return wm.get_status()


@router.post(
    "/wind/clear",
    # WMOM-20260716-05h-2：設定變更＝主管
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def clear_wind():
    """Return to automatic daily pattern wind model."""
    b = get_broker()
    if not b.simulator:
        raise HTTPException(400, "Simulator not running")
    b.simulator.wind_model.clear_override()
    b.close_open_events("wind", source="config")
    b.record_event(
        event_type="wind",
        source="config",
        title="Wind config cleared",
        detail="Returned wind model to auto mode",
        payload={"mode": "auto"},
    )
    return {"status": "ok", "mode": "auto"}


@router.get(
    "/simulation/time-scale",
    # WMOM-20260716-05h-2：檢視＝任何登入者
    dependencies=[Depends(require_authenticated())],
)
async def get_time_scale():
    """Get current simulation time scale."""
    b = get_broker()
    if not b.simulator:
        raise HTTPException(400, "Simulator not running")
    return {"time_scale": b.simulator.time_scale}


@router.post(
    "/simulation/time-scale",
    # WMOM-20260716-05h-2：設定變更＝主管
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def set_time_scale(body: dict):
    """Set simulation time acceleration factor.

    time_scale=1: real-time
    time_scale=60: 1 minute of simulation per second
    time_scale=3600: 1 hour of simulation per second
    """
    b = get_broker()
    if not b.simulator:
        raise HTTPException(400, "Simulator not running")
    scale = body.get("time_scale", 1.0)
    if scale < 1.0 or scale > 86400:
        raise HTTPException(400, "time_scale must be between 1 and 86400")
    b.simulator.time_scale = float(scale)
    return {"time_scale": b.simulator.time_scale}


@router.post(
    "/simulation/generate-bulk",
    # WMOM-20260716-05h-2：設定變更＝主管
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def generate_bulk(body: dict):
    """Generate bulk historical data at maximum speed.

    Parameters:
      duration_hours: hours of simulated data (e.g. 720 for 30 days)
      time_step: physics step in seconds (default 10, use 60 for faster)
      fault_schedule: 選填。Scenario 模式的故障排程（DEC-20260718-01）。每筆
        ``{scenario_id, turbine_id, at_hour|offset_seconds, severity_rate?, initial_severity?}``
        於指定 sim-time 注入，讓批次資料集包含該故障的發展（見 ``_parse_fault_schedule``）。

    The data is written to SQLite via the normal storage pipeline.
    This runs synchronously and may take minutes for large durations.

    本呼叫與 Live 背景迴圈共用同一個 simulator instance，故批次全程以
    ``DataBroker.pause_live_for_batch()`` **暫停 Live 自由跑迴圈**（結束後恢復）。否則
    ``generate_bulk`` 同步跑在 request thread，會與 Live 背景 thread 併發呼叫同一批
    ``model.step()`` / ``fault_engine.step()``（``engine._lock`` 只保護 ``latest_data``、不含
    ``model.step()`` 本身）並同時寫同一 SQLite → Windows 上實測撞 ``database is locked``。
    暫停期間才 ``fault_engine.clear()``（帶 ``fault_schedule`` 時求乾淨情境）＋ 生成 ＋ 收尾寫入，
    確保無第二個 writer。資料落地另以專屬 ``session_id`` 隔離（見 ``name`` 參數）。
    註：姊妹端點 ``faults.py::run_test_plan`` 亦共用 ``pause_live_for_batch``。
    """
    b = get_broker()
    if not b.simulator:
        raise HTTPException(400, "Simulator not running")

    duration = body.get("duration_hours", 24)
    step = body.get("time_step", 10.0)
    if duration > 8760:
        raise HTTPException(400, "Max 8760 hours (1 year)")

    # Scenario 模式：選填故障排程（WMOM-20260718-03, DEC-20260718-01）。
    schedule = _parse_fault_schedule(
        body.get("fault_schedule") or [],
        set(b.simulator.turbines.keys()),
    )
    # 情境保存（DEC-20260718-01 #4）：帶 name 時把這批資料寫進一個「專屬情境 session」，
    # 與 Live/其他歷史隔離、事後可 list / load / delete；不帶 name 則沿用舊行為（寫進當前
    # active session、融進歷史）——保留 FaultInjectionPanel/快速批次的既有用法。
    scenario_name = body.get("name")
    scenario_name = scenario_name.strip() if isinstance(scenario_name, str) else ""
    wind_profile = body.get("wind_profile")

    if scenario_name:
        # 把當下機型的額定功率釘進情境 session——情境是凍結資料集，容量因數的分母應反映「生成當時的
        # 機型」而非日後查詢時 simulator 的 spec（見 scenarios.py A0 摘要）。取第一台機組的 spec；
        # 取不到則留 None，由摘要端點兜底預設。
        _models = list(b.simulator.turbines.values())
        scenario_rated_kw: Optional[float] = (
            getattr(getattr(_models[0], "spec", None), "rated_power_kw", None)
            if _models else None
        )
        scenario_id: Optional[int] = b.storage.create_session(
            data_source="simulation",  # 情境資料一律模擬產生；情境判別靠 config.kind
            turbine_count=len(b.simulator.turbines),
            rated_power_kw=scenario_rated_kw,
            config={
                "kind": b.storage.SCENARIO_KIND,
                "name": scenario_name,
                "wind_profile": wind_profile,
                "duration_hours": duration,
                "time_step": step,
                "fault_schedule": [
                    {
                        "scenario_id": s.scenario_id,
                        "turbine_id": s.turbine_id,
                        "offset_seconds": s.offset_seconds,
                        "severity_rate": s.severity_rate,
                    }
                    for s in schedule
                ],
            },
        )
        session_id = scenario_id
    else:
        scenario_id = None
        session_id = b._session_id

    injected_count = 0  # 實際注入數（offset 超過批次總長者不會注入 → 不計入）
    sim_window: dict = {"start": None, "end": None}  # 情境的模擬時間窗（供調閱設範圍）

    def store_cb(readings: List[dict]) -> None:
        """Persist generated bulk readings to storage（情境模式寫進專屬 session）。"""
        for r in readings:
            ts = r.get("timestamp")
            if ts:  # ISO 字串可字典序比較
                if sim_window["start"] is None or ts < sim_window["start"]:
                    sim_window["start"] = ts
                if sim_window["end"] is None or ts > sim_window["end"]:
                    sim_window["end"] = ts
        b.storage.store_readings(readings, session_id)

    def on_inject(fstep: TestPlanStep, sim_time: datetime) -> None:
        """把排定故障寫成事件（用注入的**模擬時間戳**），讓事件標記與資料時間軸對齊、可追溯。"""
        nonlocal injected_count
        injected_count += 1
        # 注入時間戳早於本 step 的首筆 reading（on_inject 在物理子步推進「前」觸發），
        # 故 offset=0 的事件會落在首筆 reading 前一個 time_step。把注入時間也納入 sim_window
        # 下界，否則調閱時 `timestamp >= sim_start` 會把「情境一開始就注入」的故障事件排除掉。
        inj_ts = sim_time.isoformat()
        if sim_window["start"] is None or inj_ts < sim_window["start"]:
            sim_window["start"] = inj_ts
        b.record_event(
            event_type="fault",
            source="scenario",
            title=f"Scenario fault: {fstep.scenario_id} on {fstep.turbine_id}",
            turbine_id=fstep.turbine_id,
            detail=fstep.description or f"Scheduled {fstep.scenario_id} @ {fstep.offset_seconds / 3600:.1f}h",
            timestamp=sim_time.isoformat(),
            payload={
                "scenarioId": fstep.scenario_id,
                "turbineId": fstep.turbine_id,
                "offsetSeconds": fstep.offset_seconds,
                "severityRate": fstep.severity_rate,
                "initialSeverity": fstep.initial_severity,
            },
        )

    # 批次生成前先停 Live 自由跑迴圈，全程（清故障 + 生成 + 收尾寫入）Live 都停著，離開 context
    # 才恢復。否則 live thread 會與批次「同時 step 同一組物理模型」（race）並「同時寫同一 SQLite」
    # → Windows 上實測 generate-bulk 撞 ``database is locked``。停 / 恢復集中在
    # DataBroker.pause_live_for_batch（faults.py::run_test_plan 共用同一套，避免漏套）。
    sim = b.simulator
    with b.pause_live_for_batch():
        if schedule:
            # 乾淨情境：清掉殘留的 runtime 故障，讓資料集只含本情境排定者。挪到「停 Live 之後」，
            # 避免 clear() 與 Live 的 fault_engine.step() 併發動同一組非 lock 保護的物理狀態。
            sim.fault_engine.clear()
        try:
            total = sim.generate_bulk(
                duration_hours=duration,
                time_step=step,
                callback=store_cb,
                fault_schedule=schedule or None,
                on_fault_injected=on_inject if schedule else None,
            )
            # Run downsampling after bulk generation
            b.storage.run_downsampling()
            if scenario_id is not None:
                # 回填統計 + 模擬時間窗並結束情境 session。趁 Live 仍停時寫（避免與恢復的 live 搶鎖）。
                b.storage.update_session_config(scenario_id, {
                    "status": "ok",
                    "total_readings": total,
                    "faults_injected": injected_count,
                    "sim_start": sim_window["start"],
                    "sim_end": sim_window["end"],
                })
                b.storage.end_session(scenario_id)
        except Exception:
            # 生成中途失敗（如物理發散）也必須收尾情境 session，否則它會卡在 ended_at IS NULL、
            # 被 get_active_session 誤認成 Live、並以殘破項目出現在 list_scenarios。
            if scenario_id is not None:
                b.storage.update_session_config(scenario_id, {"status": "error"})
                b.storage.end_session(scenario_id)
            raise

    stats = b.storage.get_db_stats()
    return {
        "status": "ok",
        "scenario_id": scenario_id,
        "duration_hours": duration,
        "time_step": step,
        "total_readings": total,
        "faults_injected": injected_count,
        "final_fault_status": b.simulator.fault_engine.get_fault_status() if schedule else [],
        "storage_stats": stats,
    }


@router.get(
    "/grid",
    # WMOM-20260716-05h-2：檢視＝任何登入者
    dependencies=[Depends(require_authenticated())],
)
async def get_grid_status():
    """Return current grid model status including mode, profile, and overrides."""
    b = get_broker()
    if not b.simulator:
        raise HTTPException(400, "Simulator not running")
    return b.simulator.grid_model.get_status()


@router.post(
    "/grid",
    # WMOM-20260716-05h-2：設定變更＝主管
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def set_grid(req: GridOverrideRequest):
    """Apply grid profile or manual frequency/voltage override."""
    b = get_broker()
    if not b.simulator:
        raise HTTPException(400, "Simulator not running")

    gm = b.simulator.grid_model
    b.close_open_events("grid", source="config")
    if req.profile:
        gm.set_profile(req.profile)
    else:
        gm.set_override(req.frequencyHz, req.voltageV)
    b.record_event(
        event_type="grid",
        source="config",
        title=f"Grid config updated{f': {req.profile}' if req.profile else ''}",
        detail="Grid profile or override changed",
        payload=req.model_dump(),
    )
    return gm.get_status()


@router.post(
    "/grid/clear",
    # WMOM-20260716-05h-2：設定變更＝主管
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def clear_grid():
    """Clear grid overrides and return to auto mode."""
    b = get_broker()
    if not b.simulator:
        raise HTTPException(400, "Simulator not running")
    b.simulator.grid_model.clear_override()
    b.close_open_events("grid", source="config")
    b.record_event(
        event_type="grid",
        source="config",
        title="Grid config cleared",
        detail="Returned grid model to auto mode",
        payload={"mode": "auto"},
    )
    return {"status": "ok", "mode": "auto"}


# ─── Turbine Specification ─────────────────────────────────────────────

# ─── Storage & Session Info ───────────────────────────────────────────

@router.get(
    "/storage/stats",
    # WMOM-20260716-05h-2：檢視＝任何登入者
    dependencies=[Depends(require_authenticated())],
)
async def get_storage_stats():
    """Get database storage statistics (row counts, size)."""
    b = get_broker()
    stats = b.storage.get_db_stats()
    stats["write_interval_s"] = b.WRITE_INTERVAL_S
    stats["raw_retention_days"] = b.RAW_RETENTION_DAYS
    stats["agg_1m_retention_days"] = b.AGG_1M_RETENTION_DAYS
    return stats


@router.get(
    "/sessions",
    # WMOM-20260716-05h-2：檢視＝任何登入者
    dependencies=[Depends(require_authenticated())],
)
async def list_sessions():
    """List recent sessions."""
    b = get_broker()
    sessions = b.storage.get_sessions(limit=20)
    active = b.storage.get_active_session()
    return {"active_session_id": active["id"] if active else None, "sessions": sessions}


@router.post(
    "/storage/maintenance",
    # WMOM-20260716-05h-2：儲存清理＝系統管理員（破壞性）
    dependencies=[Depends(require_role(Role.ADMIN))],
)
async def run_maintenance():
    """Manually trigger downsampling and cleanup."""
    b = get_broker()
    b.storage.run_downsampling()
    cleanup = b.storage.run_cleanup(
        raw_retention_days=b.RAW_RETENTION_DAYS,
        agg_1m_retention_days=b.AGG_1M_RETENTION_DAYS,
    )
    stats = b.storage.get_db_stats()
    return {"cleanup": cleanup, "stats": stats}


# ─── Turbine Specification ─────────────────────────────────────────────

@router.get(
    "/turbine-spec",
    # WMOM-20260716-05h-2：檢視＝任何登入者
    dependencies=[Depends(require_authenticated())],
)
async def get_turbine_spec():
    """Get current turbine specification."""
    b = get_broker()
    if not b.simulator or not b.simulator.turbines:
        raise HTTPException(400, "Simulator not running")
    # Return spec from first turbine (all share same spec)
    first_tid = list(b.simulator.turbines.keys())[0]
    model = b.simulator.turbines[first_tid]
    return model.spec.to_dict()


@router.post(
    "/turbine-spec",
    # WMOM-20260716-05h-2：設定變更＝主管
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def set_turbine_spec(spec_dict: dict):
    """Update turbine specifications for all turbines.

    Accepts partial updates — only provided fields are changed.
    Example: {"rated_power_kw": 3000, "cut_in_speed": 4.0, "curtailment_kw": 2000}

    Or use a preset: {"preset": "vestas_v90_3mw"}
    Available presets: z72_5mw, vestas_v90_3mw, sg_8mw, goldwind_2.5mw
    """
    b = get_broker()
    if not b.simulator:
        raise HTTPException(400, "Simulator not running")

    from simulator.physics import TurbineSpec, TURBINE_PRESETS

    # Check for preset
    preset_name = spec_dict.pop("preset", None)
    if preset_name:
        if preset_name not in TURBINE_PRESETS:
            raise HTTPException(404, f"Unknown preset: {preset_name}. Available: {list(TURBINE_PRESETS.keys())}")
        new_spec = TURBINE_PRESETS[preset_name]
    else:
        # Get current spec and merge updates
        first_model = list(b.simulator.turbines.values())[0]
        current = first_model.spec.to_dict()
        current.update({k: v for k, v in spec_dict.items() if v is not None})
        new_spec = TurbineSpec.from_dict(current)

    # Apply to all turbines
    for model in b.simulator.turbines.values():
        model.update_spec(new_spec)

    # Create a new session to separate data from different turbine models
    if b._session_id is not None:
        b.storage.end_session(b._session_id)
    b._session_id = b.storage.create_session(
        data_source="simulation",
        turbine_count=len(b.turbine_ids),
        rated_power_kw=new_spec.rated_power_kw,
        rotor_diameter_m=new_spec.rotor_diameter_m,
        model_name=preset_name or "Custom",
        config=new_spec.to_dict(),
    )

    return {"status": "ok", "spec": new_spec.to_dict(), "session_id": b._session_id}


@router.get(
    "/turbine-spec/presets",
    # WMOM-20260716-05h-2：檢視＝任何登入者
    dependencies=[Depends(require_authenticated())],
)
async def list_turbine_presets():
    """List available turbine specification presets."""
    from simulator.physics import TURBINE_PRESETS
    return {
        name: spec.to_dict() for name, spec in TURBINE_PRESETS.items()
    }
