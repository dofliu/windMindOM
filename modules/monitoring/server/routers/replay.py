"""情境 WebSocket 回放端點（WMOM-20261021-06，EPIC-DS Phase 3b ② 串流）。

出題 / 評分端（主管）：

- ``POST   /api/scenarios/{id}/replay-runs``：建立回放（模式、速度、到期），回傳回放 token——只回這一次。
- ``GET    /api/scenarios/{id}/replay-runs``：列出情境的回放與狀態。
- ``DELETE /api/replay-runs/{run_id}``：撤銷（不能再連線、送預測；開著的連線幾秒內斷線）。
- ``GET    /api/replay-runs/{run_id}/predictions``：下載受測端經 WS 送來的預測（``predictions.jsonl``，
  ``ts`` 為伺服器收到時的模擬時間，可直接給 starter kit 的 ``score.py``）。

受測端（回放 token，不開帳號，DEC-20261021-03）：

- ``WS /ws/replay``：token 放 ``Authorization: Bearer <token>``（建議）或 ``?token=``。伺服器送
  ``control`` / ``reading`` / ``event`` / ``stats``，受測端送 ``prediction``（合約 v1.1 §12）。
  ``?check=true`` 只檢查 token、回報回放狀態，不開始計時（單次回放的時鐘從第一次正式連線起算）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, List, Literal, MutableMapping, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from modules.auth.dependencies import Actor, require_roles
from modules.auth.roles import Role
from server import replay as rp
from server import scenario_pack as sp
from server.storage import Storage
from simulator.time_utils import iso_utc, parse_iso

router = APIRouter(tags=["replay"])
logger = logging.getLogger(__name__)

# 每個回放目前開著的連線數（單一程序）。鍵含 DB 路徑：各風場 DB 的回放 id 各自從 1 起算
_open_connections: Dict[Tuple[str, int], int] = {}
# 串流中每隔幾秒（實際時間）重讀回放狀態：撤銷 / 到期就斷線
RUN_RECHECK_S = 5.0
# 待送訊息剩這麼多就先抓下一頁（與傳送重疊，避免每個頁邊界都落後時鐘）
PREFETCH_LOW_WATER = 300


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
    allow_overlap: bool = Field(False, description="同情境已有另一種模式的回放時仍建立（練習回放可以先看完正式評測的資料）")


def _storage() -> Storage:
    return get_broker().storage


@router.post("/api/scenarios/{scenario_id}/replay-runs", status_code=201)
async def create_replay_run(scenario_id: int, body: ReplayRunCreate,
                            actor: Actor = Depends(require_roles(Role.SUPERVISOR))) -> JSONResponse:
    """建立回放並回傳 token（只回這一次；DB 只存 sha256）。

    Args:
        scenario_id: 情境 session id。
        body: 回放參數。
        actor: 建立者（主管）。

    Returns:
        ``{"run", "token", "ws_path"}``（``Cache-Control: no-store``）。
    """
    storage = _storage()
    try:
        run, token = await asyncio.to_thread(
            rp.create_run, storage, scenario_id, mode=body.mode, speed=body.speed, label=body.label,
            expires_in_hours=body.expires_in_hours, created_by=actor.id, allow_overlap=body.allow_overlap,
        )
    except sp.ScenarioPackError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except rp.ReplayRunConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:  # 例：正式評測的速度超過伺服器能穩定送出的上限
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    view = await asyncio.to_thread(rp.run_view, storage, run)
    return JSONResponse(status_code=201, content={"run": view, "token": token, "ws_path": "/ws/replay"},
                        headers={"Cache-Control": "no-store"})


@router.get("/api/scenarios/{scenario_id}/replay-runs",
            dependencies=[Depends(require_roles(Role.SUPERVISOR))])
async def list_replay_runs(scenario_id: int) -> dict:
    """列出情境的回放（新的在前，不含 token）。

    Args:
        scenario_id: 情境 session id。

    Returns:
        ``{"runs": [...]}``。
    """
    storage = _storage()

    def views() -> list:
        return [rp.run_view(storage, run) for run in storage.list_replay_runs(scenario_id)]

    return {"runs": await asyncio.to_thread(views)}


@router.delete("/api/replay-runs/{run_id}", dependencies=[Depends(require_roles(Role.SUPERVISOR))])
async def revoke_replay_run(run_id: int) -> dict:
    """撤銷回放：之後不能再連線、送預測；開著的連線在 ``RUN_RECHECK_S`` 秒內以 4403 斷線。

    Args:
        run_id: 回放 id。

    Returns:
        ``{"run": ...}``。
    """
    storage = _storage()
    if not await asyncio.to_thread(storage.revoke_replay_run, run_id, iso_utc()):
        raise HTTPException(status_code=404, detail=f"Replay run {run_id} not found")
    run = await asyncio.to_thread(storage.get_replay_run, run_id)
    assert run is not None
    return {"run": await asyncio.to_thread(rp.run_view, storage, run)}


@router.get("/api/replay-runs/{run_id}/predictions", dependencies=[Depends(require_roles(Role.SUPERVISOR))])
async def download_replay_predictions(run_id: int, connection: Optional[int] = None) -> Response:
    """受測端經 WS 送來的預測（``predictions.jsonl``；練習模式可用 ``connection`` 只取某次連線）。

    Args:
        run_id: 回放 id。
        connection: 連線序號；None＝全部。

    Returns:
        JSONL 下載。
    """
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


def _usable_run(run: Optional[dict]) -> dict:
    """回放還能用（存在、沒撤銷、沒到期）。

    Raises:
        ReplayError: 不存在（4401）、撤銷或到期（4403）。
    """
    if run is None:
        raise rp.ReplayError("回放 token 無效", 4401)
    if run["revoked_at"]:
        raise rp.ReplayError("回放已撤銷", 4403)
    if parse_iso(run["expires_at"]).timestamp() < rp.wall_time():
        raise rp.ReplayError("回放 token 已到期", 4403)
    return run


def _open_run(storage: Storage, token: Optional[str]) -> dict:
    """token → 可以連線的回放。

    Raises:
        ReplayError: token 缺 / 無效（4401）、撤銷或到期（4403）。
    """
    if not token:
        raise rp.ReplayError("缺少回放 token（Authorization: Bearer <token> 或 ?token=）", 4401)
    return _usable_run(storage.find_replay_run(rp.token_digest(token)))


def _check_view(storage: Storage, run: dict) -> dict:
    """``?check=true`` 回報的回放狀態（不含出題者備註、建立者）。"""
    view = rp.run_view(storage, run)
    return {key: view[key] for key in ("pack_id", "mode", "speed", "status", "expires_at", "started_at", "ends_at")}


class _ReplayConnection:
    """一條回放連線：依時鐘送訊息，同時收受測端的預測並以收到時的模擬時間蓋上 ``ts``。"""

    def __init__(self, ws: WebSocket, storage: Storage, run: dict, replay: rp.ScenarioReplay,
                 clock: rp.ReplayClock, connection_no: int, skip_before: Optional[datetime]) -> None:
        self._ws = ws
        self._storage = storage
        self._run = run
        self._run_id = int(run["id"])
        self._replay = replay
        self._clock = clock
        self._connection_no = connection_no
        self._skip_before = skip_before
        self._send_lock = asyncio.Lock()
        self._last_due: Optional[datetime] = None  # 已送出的最大 due：蓋章不早於它（時鐘被調回也一樣）
        self._run_checked_at = rp.wall_time()
        self.end_wall = clock.wall_at(replay.sim_end)

    async def send(self, message: dict) -> None:
        """送一則訊息（送資料的 task 與回 ack 的 task 共用連線，以鎖串起來）。

        Args:
            message: JSON 物件。

        Raises:
            WebSocketDisconnect: 受測端已關閉連線。
        """
        async with self._send_lock:
            try:
                await self._ws.send_text(json.dumps(message, ensure_ascii=False))
            except RuntimeError as exc:  # 受測端已關閉連線（Starlette 對已關閉的連線送訊息）
                raise WebSocketDisconnect(code=1006) from exc

    async def started(self, backfill: bool) -> None:
        """送 ``control started``：回放說明、tag 字典、警報目錄。

        Args:
            backfill: 是否補送已過去的資料（回報給受測端）。
        """
        stream = self._replay.describe()
        stream.update(mode=self._run["mode"], speed=self._run["speed"], connection_no=self._connection_no,
                      backfill=backfill, close_grace_s=rp.CLOSE_GRACE_S)
        await self.send({
            "type": "control", "status": "started", "sim_ts": rp.z(self._clock.sim_now()), "stream": stream,
            "tag_dictionary": self._replay.tag_dictionary(), "alarm_catalog": sp.alarm_catalog_snapshot(),
        })

    async def _recheck_run(self) -> None:
        """每 ``RUN_RECHECK_S`` 秒重讀回放：撤銷或到期就丟 ``ReplayError``（4403）。"""
        now = rp.wall_time()
        if now - self._run_checked_at < RUN_RECHECK_S:
            return
        self._run_checked_at = now
        _usable_run(await asyncio.to_thread(self._storage.get_replay_run, self._run_id))

    async def stream(self) -> None:
        """依時鐘送出全部訊息；送完 ``finished`` 後連線再開 ``CLOSE_GRACE_S`` 秒（讓途中的預測拿到 ack）。

        Raises:
            ReplayError: 串流中回放被撤銷或到期（4403）。
        """
        buffer: Deque[rp.ReplayFrame] = deque()
        fetch: Optional["asyncio.Future[List[rp.ReplayFrame]]"] = None
        try:
            while True:
                if fetch is None and not self._replay.done and len(buffer) < PREFETCH_LOW_WATER:
                    fetch = asyncio.ensure_future(asyncio.to_thread(self._replay.next_frames))
                if fetch is not None and (not buffer or fetch.done()):
                    buffer.extend(await fetch)
                    fetch = None
                    continue
                if not buffer:
                    break
                await self._recheck_run()
                frame = buffer[0]
                wait = self._clock.wall_at(frame.due) - rp.wall_time()
                if wait > 0:
                    await asyncio.sleep(min(wait, 1.0))
                    continue
                buffer.popleft()
                if self._skip_before is not None and frame.due < self._skip_before:
                    continue
                await self.send(frame.message)
                if self._last_due is None or frame.due > self._last_due:
                    self._last_due = frame.due
        finally:
            if fetch is not None:
                fetch.cancel()
        await self.send({"type": "control", "status": "finished", "sim_ts": rp.z(self._clock.sim_now()),
                         "closing_in_s": rp.CLOSE_GRACE_S})
        while True:
            remaining = self.end_wall + rp.CLOSE_GRACE_S - rp.wall_time()
            if remaining <= 0:
                return
            await asyncio.sleep(min(remaining, 1.0))
            await self._recheck_run()

    async def receive(self) -> None:
        """收受測端訊息直到斷線；單則訊息處理失敗只回 ``error``，不斷線。"""
        while True:
            message = await self._ws.receive()
            if message["type"] == "websocket.disconnect":
                return
            try:
                await self._handle(message)
            except WebSocketDisconnect:
                raise
            except Exception:  # noqa: BLE001  一則訊息處理失敗不應踢掉受測端
                logger.exception("replay run %s connection %s: message handling failed", self._run_id,
                                 self._connection_no)
                await self.send({"type": "error", "message": "伺服器無法處理這則訊息"})

    async def _handle(self, message: MutableMapping[str, object]) -> None:
        text = message.get("text")
        if not isinstance(text, str):
            await self.send({"type": "error", "message": "只接受文字（JSON）訊息"})
            return
        if len(text) > rp.MAX_CLIENT_MESSAGE_BYTES or len(text.encode("utf-8")) > rp.MAX_CLIENT_MESSAGE_BYTES:
            await self.send({"type": "error", "message": f"訊息超過 {rp.MAX_CLIENT_MESSAGE_BYTES} bytes"})
            return
        try:
            item = json.loads(text)
        except (ValueError, RecursionError):  # JSONDecodeError 與超長整數字串都是 ValueError
            await self.send({"type": "error", "message": "不是 JSON"})
            return
        if not isinstance(item, dict):
            await self.send({"type": "error", "message": "訊息必須是 JSON 物件"})
        elif item.get("type") == "prediction":
            await self._prediction(item)
        elif item.get("type") == "ping":
            await self.send({"type": "pong", "sim_ts": rp.z(self._clock.sim_now())})
        else:
            await self.send({"type": "error", "message": f"不認得的訊息種類 {str(item.get('type'))[:40]!r}"})

    async def _prediction(self, item: dict) -> None:
        sim_ts = self._clock.sim_now()
        if self._last_due is not None and sim_ts < self._last_due:
            sim_ts = self._last_due
        ack: dict = {"type": "ack", "accepted": False, "ts": rp.z(sim_ts), "errors": []}
        ref = item.get("id")
        if isinstance(ref, (str, int)) and not isinstance(ref, bool) and len(str(ref)) <= 64:
            ack["ref"] = ref
        errors: List[str] = ack["errors"]
        if sim_ts > self._replay.sim_end:
            errors.append("情境已結束（模擬時間超過 sim_end），不再收預測")
            await self.send(ack)
            return
        try:
            run = _usable_run(await asyncio.to_thread(self._storage.get_replay_run, self._run_id))
            fields = rp.validate_prediction(item, self._replay.turbines)
        except (rp.ReplayError, ValueError) as exc:
            errors.append(str(exc))
            await self.send(ack)
            return
        record = rp.prediction_record(self._replay.pack_id, sim_ts, fields)
        size = len(json.dumps(record, ensure_ascii=False))
        if int(run["predictions"]) >= rp.MAX_PREDICTIONS_PER_RUN:
            errors.append(f"這個回放的預測已達上限 {rp.MAX_PREDICTIONS_PER_RUN} 筆")
        elif await asyncio.to_thread(self._storage.prediction_bytes, self._run_id) + size \
                > rp.MAX_PREDICTION_BYTES_PER_RUN:
            errors.append(f"這個回放的預測已達儲存上限 {rp.MAX_PREDICTION_BYTES_PER_RUN // (1024 * 1024)} MB")
        else:
            await asyncio.to_thread(self._storage.add_replay_prediction, self._run_id, self._connection_no,
                                    iso_utc(), str(record["ts"]), record)
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


async def _start(ws: WebSocket, storage: Storage, run: dict, backfill: bool) -> _ReplayConnection:
    """已佔到連線名額後：載入回放、決定時鐘（單次回放在這裡開始計時）。

    Raises:
        ReplayError: 單次回放已結束（4410）、情境不能回放（4404）。
    """
    run_id = int(run["id"])
    if run["mode"] == "evaluation" and run["started_at"]:
        # 先用便宜的查詢擋掉已結束的單次回放，不必載入整個情境
        bounds = await asyncio.to_thread(storage.session_reading_bounds, int(run["scenario_id"]))
        if bounds is not None:
            early = rp.ReplayClock(parse_iso(bounds[0]), float(run["speed"]), parse_iso(run["started_at"]).timestamp())
            if rp.wall_time() > early.wall_at(parse_iso(bounds[1])) + rp.CLOSE_GRACE_S:
                raise rp.ReplayError("單次回放已結束", 4410)
    try:
        replay = await asyncio.to_thread(rp.ScenarioReplay, storage, int(run["scenario_id"]))
    except sp.ScenarioPackError as exc:
        raise rp.ReplayError(f"情境不能回放：{exc}", 4404) from exc
    now = rp.wall_time()
    if run["mode"] == "evaluation":
        started_at = await asyncio.to_thread(storage.start_replay_run, run_id,
                                             iso_utc(datetime.fromtimestamp(now, tz=timezone.utc)))
        clock = rp.ReplayClock(replay.sim_start, float(run["speed"]), parse_iso(started_at).timestamp())
        if now > clock.wall_at(replay.sim_end) + rp.CLOSE_GRACE_S:
            raise rp.ReplayError("單次回放已結束", 4410)
    else:
        clock = rp.ReplayClock(replay.sim_start, float(run["speed"]), now)
    connection_no = await asyncio.to_thread(storage.next_replay_connection, run_id)
    skip_before = None if backfill else clock.sim_now()
    return _ReplayConnection(ws, storage, run, replay, clock, connection_no, skip_before)


@router.websocket("/ws/replay")
async def replay_websocket(ws: WebSocket, backfill: bool = True, check: bool = False) -> None:
    """情境回放串流（合約 v1.1 §12）。

    Args:
        ws: 連線。
        backfill: 單次回放已開始後才連上時，是否先補送已經過去的資料（預設是；時間不會倒回）。
        check: 只檢查 token、回報回放狀態後關閉（不開始計時、不佔連線名額）。
    """
    await ws.accept()
    storage = _storage()
    key: Optional[Tuple[str, int]] = None
    try:
        try:
            run = await asyncio.to_thread(_open_run, storage, _token_from(ws))
            if check:
                view = await asyncio.to_thread(_check_view, storage, run)
                await ws.send_text(json.dumps({"type": "control", "status": "checked", "run": view},
                                              ensure_ascii=False))
                await _close(ws, 1000)
                return
            candidate = (storage.db_path, int(run["id"]))
            # 檢查與佔位之間沒有 await：同時湧入的連線不會一起通過檢查
            if _open_connections.get(candidate, 0) >= rp.MAX_CONNECTIONS_PER_RUN:
                raise rp.ReplayError(f"這個回放已有 {rp.MAX_CONNECTIONS_PER_RUN} 條連線", 4409)
            _open_connections[candidate] = _open_connections.get(candidate, 0) + 1
            key = candidate
            connection = await _start(ws, storage, run, backfill)
        except rp.ReplayError as exc:
            await _reject(ws, exc)
            return

        await connection.started(backfill)
        streaming = asyncio.create_task(connection.stream())
        receiving = asyncio.create_task(connection.receive())
        try:
            done, _ = await asyncio.wait({streaming, receiving}, return_when=asyncio.FIRST_COMPLETED)
        except BaseException:
            # handler 本身被取消（伺服器關機等）：子 task 一併取消
            streaming.cancel()
            receiving.cancel()
            raise
        # 先結束的那一個決定怎麼收尾；另一個取消即可，不必等它（受測端已離開時不再做任何 await）
        finished = streaming if streaming in done else receiving
        (receiving if finished is streaming else streaming).cancel()
        error = finished.exception()
        if isinstance(error, rp.ReplayError):
            await _reject(ws, error)
        elif error is not None and not isinstance(error, WebSocketDisconnect):
            logger.error("replay run %s failed", key, exc_info=error)
            await _close(ws, 1011)
        elif finished is streaming:
            await _close(ws, 1000)
    except WebSocketDisconnect:
        pass
    finally:
        if key is not None:
            _open_connections[key] -= 1
            if _open_connections[key] <= 0:
                del _open_connections[key]
