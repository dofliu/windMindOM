"""Fault injection API — inject, monitor, and clear simulated faults.

Includes test plan system for automated fault sequences.
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from modules.auth.dependencies import require_authenticated, require_role
from modules.auth.roles import Role
from server.models import FaultInjectionRequest, FaultClearRequest
from simulator.bulk_events import BulkEvent
from simulator.physics.fault_engine import TEST_PLANS, TestPlanStep
from simulator.time_utils import iso_utc

router = APIRouter(prefix="/api/faults", tags=["faults"])


def get_broker():
    """Return the shared DataBroker instance from the main app module."""
    from server.app import broker
    return broker


@router.get(
    "/scenarios",
    # WMOM-20260716-05h-2：檢視＝任何登入者
    dependencies=[Depends(require_authenticated())],
)
async def list_scenarios():
    """List all available fault scenarios (for UI dropdown)."""
    b = get_broker()
    if not b.simulator:
        raise HTTPException(400, "Simulator not running")

    scenarios = b.simulator.fault_engine.get_scenarios()
    return [
        {
            "id": s.id,
            "name_en": s.name_en,
            "name_zh": s.name_zh,
            "description_en": s.description_en,
            "description_zh": s.description_zh,
            "affected_tags": list(s.affected_tags.keys()),
            "alarm_codes": s.alarm_codes,
        }
        for s in scenarios.values()
    ]


@router.post(
    "/inject",
    # WMOM-20260716-05h-2：故障注入＝主管
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def inject_fault(req: FaultInjectionRequest):
    """Inject a fault into a specific turbine."""
    b = get_broker()
    if not b.simulator:
        raise HTTPException(400, "Simulator not running")

    ok = b.simulator.fault_engine.inject(
        scenario_id=req.scenarioId,
        turbine_id=req.turbineId,
        severity_rate=req.severityRate,
        initial_severity=req.initialSeverity,
    )
    if not ok:
        raise HTTPException(404, f"Unknown scenario: {req.scenarioId}")

    b.record_event(
        event_type="fault",
        source="faults",
        title=f"Fault injected: {req.scenarioId}",
        turbine_id=req.turbineId,
        detail=f"Injected {req.scenarioId} on {req.turbineId}",
        payload={
            "scenarioId": req.scenarioId,
            "turbineId": req.turbineId,
            "severityRate": req.severityRate,
            "initialSeverity": req.initialSeverity,
        },
    )

    return {"status": "injected", "scenarioId": req.scenarioId, "turbineId": req.turbineId}


@router.get(
    "/active",
    # WMOM-20260716-05h-2：檢視＝任何登入者
    dependencies=[Depends(require_authenticated())],
)
async def get_active_faults():
    """Get status of all active faults across the farm."""
    b = get_broker()
    if not b.simulator:
        return []
    return b.simulator.fault_engine.get_fault_status()


@router.post(
    "/clear",
    # WMOM-20260716-05h-2：清除故障＝主管
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def clear_faults(req: FaultClearRequest):
    """Clear faults. Omit both fields to clear all."""
    b = get_broker()
    if not b.simulator:
        raise HTTPException(400, "Simulator not running")

    b.simulator.fault_engine.clear(
        turbine_id=req.turbineId,
        scenario_id=req.scenarioId,
    )
    # Reset tripped turbines back to normal
    if req.turbineId and req.turbineId in b.simulator.turbines:
        b.simulator.turbines[req.turbineId].reset()

    b.record_event(
        event_type="fault",
        source="faults",
        title="Faults cleared",
        turbine_id=req.turbineId,
        detail=f"Cleared faults for {req.turbineId or 'all turbines'}",
        payload={"turbineId": req.turbineId, "scenarioId": req.scenarioId},
    )

    return {"status": "cleared"}


# ─── Test Plans ───────────────────────────────────────────────────────

@router.get(
    "/test-plans",
    # WMOM-20260716-05h-2：檢視＝任何登入者
    dependencies=[Depends(require_authenticated())],
)
async def list_test_plans():
    """List available fault injection test plans."""
    plans = []
    for plan_id, plan in TEST_PLANS.items():
        plans.append({
            "id": plan_id,
            "name_en": plan["name_en"],
            "name_zh": plan["name_zh"],
            "description_en": plan["description_en"],
            "description_zh": plan["description_zh"],
            "duration_hours": plan["duration_hours"],
            "fault_count": len(plan["steps"]),
            "turbines_affected": list(set(s.turbine_id for s in plan["steps"])),
            "scenarios_used": list(set(s.scenario_id for s in plan["steps"])),
        })
    return plans


@router.post(
    "/test-plans/{plan_id}/run",
    # WMOM-20260716-05h-2：測試計畫執行＝主管
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def run_test_plan(plan_id: str, body: dict = {}):
    """Run a test plan: generate bulk data with scheduled fault injections.

    This generates the full duration of simulated data with faults injected
    at their scheduled offsets. Data is written to SQLite.

    Options:
      time_step: physics step in seconds (default 10)
    """
    b = get_broker()
    if not b.simulator:
        raise HTTPException(400, "Simulator not running")

    plan = TEST_PLANS.get(plan_id)
    if not plan:
        raise HTTPException(404, f"Unknown test plan: {plan_id}. Available: {list(TEST_PLANS.keys())}")

    time_step = body.get("time_step", 10.0)
    duration = plan["duration_hours"]
    steps = sorted(plan["steps"], key=lambda s: s.offset_seconds)

    session_id = b._session_id

    def store_cb(readings: List[dict]) -> None:
        """Persist generated bulk readings to storage."""
        b.storage.store_readings(readings, session_id)

    def on_inject(s: TestPlanStep, sim_time: datetime) -> None:
        """把測試計畫的排定故障寫成事件（用注入的模擬時間戳），供稽核追溯。"""
        b.record_event(
            event_type="fault",
            source="test_plan",
            title=f"Test plan: {s.scenario_id} on {s.turbine_id}",
            turbine_id=s.turbine_id,
            detail=s.description,
            timestamp=iso_utc(sim_time),
            session_id=session_id,
            payload={
                "plan_id": plan_id,
                "scenarioId": s.scenario_id,
                "severityRate": s.severity_rate,
            },
        )

    def on_trip(turbine_id: str, fault_scenario_id: str, trip_code: int, sim_time: datetime) -> None:
        """PLC 以故障預期碼跳機 → 記一筆 trip 標記（模擬時間戳，WMOM-20261021-04）。"""
        b.record_event(
            event_type="fault",
            source="test_plan",
            title=f"Test plan fault trip: {fault_scenario_id} on {turbine_id} (event {trip_code})",
            turbine_id=turbine_id,
            detail=f"{fault_scenario_id} tripped {turbine_id} via PLC event {trip_code}",
            timestamp=iso_utc(sim_time),
            session_id=session_id,
            payload={
                "plan_id": plan_id,
                "kind": "trip",
                "scenarioId": fault_scenario_id,
                "turbineId": turbine_id,
                "tripCode": trip_code,
            },
        )

    def on_events(events: List[BulkEvent]) -> None:
        """批次的可觀測事件（PLC 警報 / 跳機、狀態轉換，模擬時間戳）→ history_events。"""
        b.record_bulk_events(events, session_id)

    # 批次全程暫停 Live 自由跑迴圈（與 config.py::generate-bulk 共用 pause_live_for_batch）：
    # 否則 Live thread 會與此批次併發 step 同一組物理模型並寫同一 SQLite → Windows 上撞
    # ``database is locked``（與情境生成同根因，此姊妹端點同樣需保護）。
    with b.pause_live_for_batch():
        # Clear any existing faults for a clean plan run（挪到停 Live 之後，避免與 Live 的
        # fault_engine.step() 併發動同一組非 lock 保護的物理狀態）。
        b.simulator.start_clean_scenario()  # 含 Live 殘留的 PLC 狀態（WMOM-20261022-01）
        # Delegate to the shared scheduled-injection primitive (WMOM-20260718-03).
        total_readings = b.simulator.generate_bulk(
            duration_hours=duration,
            time_step=time_step,
            callback=store_cb,
            fault_schedule=steps,
            on_fault_injected=on_inject,
            on_fault_tripped=on_trip,
            on_events=on_events,
        )
        # Downsampling after bulk generation
        b.storage.run_downsampling()

    # Get final fault status
    fault_status = b.simulator.fault_engine.get_fault_status()

    stats = b.storage.get_db_stats()
    return {
        "status": "completed",
        "plan_id": plan_id,
        "duration_hours": duration,
        "total_readings": total_readings,
        "faults_injected": len(steps),
        "final_fault_status": fault_status,
        "storage_stats": stats,
    }
