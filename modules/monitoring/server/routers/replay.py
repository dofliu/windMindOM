"""情境 WebSocket 回放端點（WMOM-20261021-06，EPIC-DS Phase 3b ② 串流）。

出題 / 評分端（主管）：

- ``POST   /api/scenarios/{id}/replay-runs``：建立回放（模式、速度、到期），回傳回放 token——只回這一次。
- ``GET    /api/scenarios/{id}/replay-runs``：列出情境的回放與狀態。
- ``DELETE /api/replay-runs/{run_id}``：撤銷（不能再連線、送預測）。
- ``GET    /api/replay-runs/{run_id}/predictions``：下載受測端經 WS 送來的預測（``predictions.jsonl``，
  ``ts`` 為伺服器收到時的模擬時間，可直接給 starter kit 的 ``score.py``）。

受測端（回放 token，不開帳號，DEC-20261021-03）：

- ``WS /ws/replay``：token 放 ``Authorization: Bearer <token>``（建議）或 ``?token=``。伺服器送
  ``control`` / ``reading`` / ``event`` / ``stats``，受測端送 ``prediction``（合約 v1.1 §12）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel, Field

from modules.auth.dependencies import Actor, require_roles
from modules.auth.roles import Role
from server import replay as rp
from server import scenario_pack as sp
from server.storage import Storage
from simulator.time_utils import iso_utc, parse_iso

router = APIRouter(tags=["replay"])
logger = logging.getLogger(__name__)

# 每個回放目前開著的連線數（單一程序；超過 MAX_CONNECTIONS_PER_RUN 拒絕）
_open_connections: Dict[int, int] = {}


def get_broker():
    """Return the shared DataBroker instance from the main app module."""
    from server.app import broker
    return broker


class ReplayRunCreate(BaseModel):
    """建立回放的參數。"""

    mode: Literal["evaluation", "practice"] = Field(
        "evaluation", description="evaluation＝單次直播（從第一次連線起算、不能倒帶）；practice＝每次連線從頭播")
    speed: float = Field(rp.DEFAULT_SPEED, ge=rp.MIN_SPEED, le=rp.MAX_SPEED, description="模擬秒 / 實際秒")
    label: Optional[str] = Field(None, max_length=100, description="出題者備註（受測端看不到）")
    expires_in_hours: float = Field(rp.DEFAULT_EXPIRES_HOURS, gt=0, le=rp.MAX_EXPIRES_HOURS,
                                    description="token 多久後不能再連線")


def _storage() -> Storage:
    return get_broker().storage


@router.post("/api/scenarios/{scenario_id}/replay-runs", status_code=201)
async def create_replay_run(scenario_id: int, body: ReplayRunCreate,
                            actor: Actor = Depends(require_roles(Role.SUPERVISOR))) -> dict:
    """建立回放並回傳 token（只回這一次；DB 只存 sha256）。"""
    storage = _storage()
    try:
        run, token = await asyncio.to_thread(
            rp.create_run, storage, scenario_id, mode=body.mode, speed=body.speed, label=body.label,
            expires_in_hours=body.expires_in_hours, created_by=actor.id,
        )
    except sp.ScenarioPackError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    view = await asyncio.to_thread(rp.run_view, storage, run)
    return {"run": view, "token": token, "ws_path": "/ws/replay"}


@router.get("/api/scenarios/{scenario_id}/replay-runs",
            dependencies=[Depends(require_roles(Role.SUPERVISOR))])
async def list_replay_runs(scenario_id: int) -> dict:
    """列出情境的回放（新的在前）。"""
    storage = _storage()

    def views() -> list:
        return [rp.run_view(storage, run) for run in storage.list_replay_runs(scenario_id)]

    return {"runs": await asyncio.to_thread(views)}


@router.delete("/api/replay-runs/{run_id}", dependencies=[Depends(require_roles(Role.SUPERVISOR))])
async def revoke_replay_run(run_id: int) -> dict:
    """撤銷回放：之後不能再連線，已連線者送的預測也不再收。"""
    storage = _storage()
    if not await asyncio.to_thread(storage.revoke_replay_run, run_id, iso_utc()):
        raise HTTPException(status_code=404, detail=f"Replay run {run_id} not found")
    run = await asyncio.to_thread(storage.get_replay_run, run_id)
    assert run is not None
    return {"run": await asyncio.to_thread(rp.run_view, storage, run)}


@router.get("/api/replay-runs/{run_id}/predictions", dependencies=[Depends(require_roles(Role.SUPERVISOR))])
async def download_replay_predictions(run_id: int, connection: Optional[int] = None) -> Response:
    """受測端經 WS 送來的預測（``predictions.jsonl``；練習模式可用 ``connection`` 只取某次連線）。"""
    storage = _storage()
    run = await asyncio.to_thread(storage.get_replay_run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Replay run {run_id} not found")
    body = await asyncio.to_thread(rp.predictions_jsonl, storage, run_id, connection)
    name = f"{sp.pack_id_for(int(run['scenario_id']))}-run{run_id}.predictions.jsonl"
    return Response(content=body.encode("utf-8"), media_type="application/x-ndjson",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ── WebSocket ────────────────────────────────────────────────────────────────


def _token_from(ws: WebSocket) -> Optional[str]:
    header = ws.headers.get("authorization", "")
    if header.startswith("Bearer "):
        return header[len("Bearer "):].strip() or None
    return ws.query_params.get("token") or None


def _open_run(storage: Storage, token: Optional[str]) -> dict:
    """token → 可以連線的回放。

    Raises:
        ReplayError: token 缺 / 無效（4401）、撤銷或到期（4403）。
    """
    if not token:
        raise rp.ReplayError("缺少回放 token（Authorization: Bearer <token> 或 ?token=）", 4401)
    run = storage.find_replay_run(rp.token_digest(token))
    if run is None:
        raise rp.ReplayError("回放 token 無效", 4401)
    if run["revoked_at"]:
        raise rp.ReplayError("回放已撤銷", 4403)
    if parse_iso(run["expires_at"]).timestamp() < rp.wall_time():
        raise rp.ReplayError("回放 token 已到期", 4403)
    return run


class _ReplayConnection:
    """一條回放連線：依時鐘送訊息，同時收受測端的預測並以收到時的模擬時間蓋上 ``ts``。"""

    def __init__(self, ws: WebSocket, storage: Storage, run: dict, replay: rp.ScenarioReplay,
                 clock: rp.ReplayClock, connection_no: int, skip_before: Optional[datetime]) -> None:
        self._ws = ws
        self._storage = storage
        self._run = run
        self._replay = replay
        self._clock = clock
        self._connection_no = connection_no
        self._skip_before = skip_before
        self._send_lock = asyncio.Lock()
        self.end_wall = clock.wall_at(replay.sim_end)

    async def send(self, message: dict) -> None:
        async with self._send_lock:
            try:
                await self._ws.send_text(json.dumps(message, ensure_ascii=False))
            except RuntimeError as exc:  # 受測端已關閉連線（Starlette 對已關閉的連線送訊息）
                raise WebSocketDisconnect(code=1006) from exc

    async def started(self, backfill: bool) -> None:
        stream = self._replay.describe()
        stream.update(mode=self._run["mode"], speed=self._run["speed"], connection_no=self._connection_no,
                      backfill=backfill, close_grace_s=rp.CLOSE_GRACE_S)
        await self.send({
            "type": "control", "status": "started", "sim_ts": rp.z(self._clock.sim_now()), "stream": stream,
            "tag_dictionary": self._replay.tag_dictionary(), "alarm_catalog": sp.alarm_catalog_snapshot(),
        })

    async def stream(self) -> None:
        """依時鐘送出全部訊息；送完 ``finished`` 後連線再開 ``CLOSE_GRACE_S`` 秒（讓途中的預測拿到 ack）。"""
        buffer: Deque[rp.ReplayFrame] = deque()
        while True:
            if not buffer:
                if self._replay.done:
                    break
                buffer.extend(await asyncio.to_thread(self._replay.next_frames))
                continue
            frame = buffer[0]
            wait = self._clock.wall_at(frame.due) - rp.wall_time()
            if wait > 0:
                await asyncio.sleep(min(wait, 1.0))
                continue
            buffer.popleft()
            if self._skip_before is not None and frame.due < self._skip_before:
                continue
            await self.send(frame.message)
        await self.send({"type": "control", "status": "finished", "sim_ts": rp.z(self._clock.sim_now()),
                         "closing_in_s": rp.CLOSE_GRACE_S})
        remaining = self.end_wall + rp.CLOSE_GRACE_S - rp.wall_time()
        if remaining > 0:
            await asyncio.sleep(remaining)

    async def receive(self) -> None:
        """收受測端訊息直到斷線。"""
        while True:
            message = await self._ws.receive()
            if message["type"] == "websocket.disconnect":
                return
            text = message.get("text")
            if text is None:
                await self.send({"type": "error", "message": "只接受文字（JSON）訊息"})
                continue
            if len(text.encode("utf-8")) > rp.MAX_CLIENT_MESSAGE_BYTES:
                await self.send({"type": "error", "message": f"訊息超過 {rp.MAX_CLIENT_MESSAGE_BYTES} bytes"})
                continue
            try:
                item = json.loads(text)
            except (json.JSONDecodeError, RecursionError):
                await self.send({"type": "error", "message": "不是 JSON"})
                continue
            if not isinstance(item, dict):
                await self.send({"type": "error", "message": "訊息必須是 JSON 物件"})
            elif item.get("type") == "prediction":
                await self._prediction(item)
            elif item.get("type") == "ping":
                await self.send({"type": "pong", "sim_ts": rp.z(self._clock.sim_now())})
            else:
                await self.send({"type": "error", "message": f"不認得的訊息種類 {item.get('type')!r}"})

    async def _prediction(self, item: dict) -> None:
        wall = rp.wall_time()
        sim_ts = self._clock.sim_now(wall)
        ack: dict = {"type": "ack", "accepted": False, "ts": rp.z(sim_ts), "errors": []}
        ref = item.get("id")
        if isinstance(ref, (str, int)) and not isinstance(ref, bool):
            ack["ref"] = ref
        run = await asyncio.to_thread(self._storage.get_replay_run, int(self._run["id"]))
        if sim_ts > self._replay.sim_end:
            ack["errors"].append("情境已結束（模擬時間超過 sim_end），不再收預測")
        elif run is None or run["revoked_at"]:
            ack["errors"].append("回放已撤銷")
        elif int(run["predictions"]) >= rp.MAX_PREDICTIONS_PER_RUN:
            ack["errors"].append(f"這個回放的預測已達上限 {rp.MAX_PREDICTIONS_PER_RUN} 筆")
        else:
            try:
                fields = rp.validate_prediction(item, self._replay.turbines)
            except ValueError as exc:
                ack["errors"].append(str(exc))
            else:
                record = rp.prediction_record(self._replay.pack_id, sim_ts, fields)
                await asyncio.to_thread(self._storage.add_replay_prediction, int(self._run["id"]),
                                        self._connection_no, iso_utc(), str(record["ts"]), record)
                ack["accepted"] = True
        await self.send(ack)


async def _close(ws: WebSocket, code: int) -> None:
    try:
        await ws.close(code=code)
    except (RuntimeError, WebSocketDisconnect):  # 受測端先關了
        pass


async def _reject(ws: WebSocket, error: rp.ReplayError) -> None:
    try:
        await ws.send_text(json.dumps({"type": "error", "code": error.close_code, "message": str(error)},
                                      ensure_ascii=False))
    except (RuntimeError, WebSocketDisconnect):
        return
    await _close(ws, error.close_code)


@router.websocket("/ws/replay")
async def replay_websocket(ws: WebSocket, backfill: bool = True) -> None:
    """情境回放串流（合約 v1.1 §12）。

    Args:
        ws: 連線。
        backfill: 單次回放已開始後才連上時，是否先補送已經過去的資料（預設是；時間不會倒回）。
    """
    await ws.accept()
    storage = _storage()
    try:
        run = await asyncio.to_thread(_open_run, storage, _token_from(ws))
        try:
            replay = await asyncio.to_thread(rp.ScenarioReplay, storage, int(run["scenario_id"]))
        except sp.ScenarioPackError as exc:
            raise rp.ReplayError(f"情境不能回放：{exc}", 4404) from exc
        run_id = int(run["id"])
        if _open_connections.get(run_id, 0) >= rp.MAX_CONNECTIONS_PER_RUN:
            raise rp.ReplayError(f"這個回放已有 {rp.MAX_CONNECTIONS_PER_RUN} 條連線", 4409)
        now = rp.wall_time()
        if run["mode"] == "evaluation":
            started_at = await asyncio.to_thread(storage.start_replay_run, run_id,
                                                 iso_utc(datetime.fromtimestamp(now, tz=timezone.utc)))
            clock = rp.ReplayClock(replay.sim_start, float(run["speed"]), parse_iso(started_at).timestamp())
            if now > clock.wall_at(replay.sim_end) + rp.CLOSE_GRACE_S:
                raise rp.ReplayError("單次回放已結束", 4410)
        else:
            clock = rp.ReplayClock(replay.sim_start, float(run["speed"]), now)
    except rp.ReplayError as exc:
        await _reject(ws, exc)
        return

    _open_connections[run_id] = _open_connections.get(run_id, 0) + 1
    try:
        connection_no = await asyncio.to_thread(storage.next_replay_connection, run_id)
        skip_before = None if backfill else clock.sim_now()
        connection = _ReplayConnection(ws, storage, run, replay, clock, connection_no, skip_before)
        await connection.started(backfill)
        streaming = asyncio.create_task(connection.stream())
        receiving = asyncio.create_task(connection.receive())
        done, pending = await asyncio.wait({streaming, receiving}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in pending:
            try:
                await task
            except (asyncio.CancelledError, WebSocketDisconnect):
                pass
        failed = [task.exception() for task in done
                  if task.exception() is not None and not isinstance(task.exception(), WebSocketDisconnect)]
        if failed:
            logger.warning("replay run %s connection %s failed: %r", run_id, connection_no, failed[0])
            await _close(ws, 1011)
        elif streaming in done:
            await _close(ws, 1000)
    except WebSocketDisconnect:
        pass
    finally:
        _open_connections[run_id] -= 1
        if _open_connections[run_id] <= 0:
            del _open_connections[run_id]
