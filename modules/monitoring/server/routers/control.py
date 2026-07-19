"""Turbine operator control API — stop/start/reset/curtail/service mode."""

from fastapi import APIRouter, Depends, HTTPException
from modules.auth.dependencies import require_authenticated, require_role
from modules.auth.roles import Role
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/control", tags=["control"])


def get_broker():
    """Return the shared DataBroker instance from the main app module."""
    from server.app import broker
    return broker


class TurbineCommand(BaseModel):
    """Command payload for turbine control."""
    turbineId: str
    command: str   # "stop", "emergency_stop", "start", "reset", "service_on", "service_off"


class CurtailCommand(BaseModel):
    """Set per-turbine power curtailment."""
    turbineId: str
    powerLimitKw: Optional[float] = None  # None = remove curtailment


@router.post(
    "/command",
    # WMOM-20260716-05h-2：操作指令＝主管
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def send_command(cmd: TurbineCommand):
    """Send operator command to a turbine.

    Commands (mapped to Bachmann Modbus Coil[1-3]):
      - stop:        Manual stop (Coil[2], normal shutdown)
      - emergency_stop: Immediate shutdown / trip-style stop
      - start:       Manual start (Coil[1], resume from stop/standby)
      - reset:       Acknowledge latched trip & attempt restart (Coil[3]);
                     does NOT resolve an active fault (that needs 維護中心 /api/faults/clear)
      - service_on:  Enter maintenance/inspection mode (WSRV_SrvOn=1)
      - service_off: Exit maintenance mode (WSRV_SrvOn=0)
    """
    b = get_broker()
    if not b.simulator:
        raise HTTPException(400, "Simulator not running")

    model = b.simulator.turbines.get(cmd.turbineId)
    if not model:
        raise HTTPException(404, f"Turbine {cmd.turbineId} not found")

    if cmd.command == "stop":
        model.cmd_stop()
    elif cmd.command == "emergency_stop":
        model.cmd_emergency_stop(cause="operator_emergency")
    elif cmd.command == "start":
        model.cmd_start()
    elif cmd.command == "reset":
        # 復位＝解除 latched trip 並嘗試重啟，但「不」移除未解決的故障。
        # 若該機組的故障仍在 fault_engine 且已 tripped，引擎每步會重新
        # emergency-stop 它（engine._run_one_step），故復位無法讓帶病機組恢復
        # 發電——這正是現場語意：復位只是「確認並嘗試重啟」，不是「修好」。
        # 唯一真正清除故障的路徑是維護中心 /api/faults/clear（工單完成）。
        model.cmd_reset()
    elif cmd.command == "service_on":
        model.cmd_service(True)
    elif cmd.command == "service_off":
        model.cmd_service(False)
    else:
        raise HTTPException(400, f"Unknown command: {cmd.command}. Use: stop, emergency_stop, start, reset, service_on, service_off")

    b.record_event(
        event_type="operator",
        source="control",
        title=f"Operator command: {cmd.command}",
        turbine_id=cmd.turbineId,
        detail=f"Command {cmd.command} issued to {cmd.turbineId}",
        payload={"command": cmd.command, "turbineId": cmd.turbineId},
    )

    return {
        "status": "ok",
        "turbineId": cmd.turbineId,
        "command": cmd.command,
        "control": model.get_control_status(),
    }


@router.post(
    "/curtail",
    # WMOM-20260716-05h-2：限載＝主管
    dependencies=[Depends(require_role(Role.SUPERVISOR))],
)
async def set_curtailment(cmd: CurtailCommand):
    """Set per-turbine power curtailment (限載).

    Set powerLimitKw to limit output. Set to null to remove curtailment.
    Pitch angle will automatically adjust to maintain the power limit.
    """
    b = get_broker()
    if not b.simulator:
        raise HTTPException(400, "Simulator not running")

    model = b.simulator.turbines.get(cmd.turbineId)
    if not model:
        raise HTTPException(404, f"Turbine {cmd.turbineId} not found")

    model.cmd_curtail(cmd.powerLimitKw)
    b.record_event(
        event_type="operator",
        source="control",
        title="Curtailment updated",
        turbine_id=cmd.turbineId,
        detail=f"Curtailment set to {cmd.powerLimitKw if cmd.powerLimitKw is not None else 'off'} kW",
        payload={"turbineId": cmd.turbineId, "powerLimitKw": cmd.powerLimitKw},
    )
    return {
        "status": "ok",
        "turbineId": cmd.turbineId,
        "curtailment_kw": cmd.powerLimitKw,
        "control": model.get_control_status(),
    }


@router.get(
    "/{turbine_id}/status",
    # WMOM-20260716-05h-2：檢視＝任何登入者
    dependencies=[Depends(require_authenticated())],
)
async def get_control_status(turbine_id: str):
    """Get current operator control status for a turbine."""
    b = get_broker()
    if not b.simulator:
        raise HTTPException(400, "Simulator not running")

    model = b.simulator.turbines.get(turbine_id)
    if not model:
        raise HTTPException(404, f"Turbine {turbine_id} not found")

    return {
        "turbineId": turbine_id,
        **model.get_control_status(),
    }
