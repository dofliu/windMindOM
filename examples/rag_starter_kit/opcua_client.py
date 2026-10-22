"""OPC UA 的受測端範例（介面合約 v1.2 §13，WMOM-20261021-07）。

像接真實的 Z72 PLC 一樣：定期從 windMindOM 的 OPC UA server 讀目前值（運轉狀態、功率、風速、
``ActiveAlarm`` / ``ActiveTrip1`` / ``ActiveTrip2`` 事件碼陣列），陣列裡出現新的碼就用基準助手
（``baseline_assistant.BaselineAssistant``）判斷；判斷照樣經 WebSocket 送
（``/ws/replay?stream=false``：同一個回放 token、伺服器蓋 ``ts``、不再收一份資料）。示範三件事：

1. **OPC UA 是「目前值」介面**：只看得到每次讀的當下；兩次讀之間出現又消失的警報看不到。要每一筆
   讀值與 10 分鐘統計，用 WS 回放（``stream_client.py``）或資料包。
2. **節點 ID 就是真實 PLC 的 item ID**（例 ``Z72.H01.WTUR.Z72PLC__UI_Loc_WTUR_State_TurSt``）：
   之後接真實 PLC 時，把讀值那一段換成 OPC DA client 即可。
3. **事件碼陣列 → 事件**：比較前後兩次讀到的陣列，新的碼當成 ``alarm_raised`` / ``trip``。警報文字
   用 WS 開播訊息裡的警報目錄查。

需要 ``asyncua`` 與 ``websockets``（``pip install -r requirements.txt``）。用法::

    python opcua_client.py opc.tcp://<host>:4840/windmindom/ --ws ws://<host>:8000/ws/replay --token <token>
    python opcua_client.py opc.tcp://<host>:4840/windmindom/        # 只看（不送判斷；即時模擬也可以）

token 也可以放環境變數 ``WMOM_REPLAY_TOKEN``。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from asyncua import Client, Node, ua
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from baseline_assistant import BaselineAssistant
from stream_client import CLOSE_CODES, Summary, connect_options, with_params

JsonObject = Dict[str, object]

NAMESPACE_URI = "urn:windmindom:z72sim"
SLOTS = 21  # 事件碼陣列的長度（PLC 的 SINT16[21]）
LISTS: Dict[str, str] = {"A": "Z72PLC__ActiveAlarm", "T1": "Z72PLC__ActiveTrip1", "T2": "Z72PLC__ActiveTrip2"}
WATCH: Dict[str, str] = {
    "state": "WTUR.Z72PLC__UI_Loc_WTUR_State_TurSt",
    "power_kw": "WTUR.Z72PLC__UI_Loc_WTUR_Analogue_TotPwrAt",
    "wind": "WMET.Z72PLC__UI_Loc_WMET_Analogue_WSpeedNac",
    "wind_10m": "WMET.Z72PLC__UI_Loc_WMET_Analogue_WSpeedNacAvg10m",
}
END_STATUSES = ("finished", "revoked", "expired")


def node(client: Client, idx: int, item_id: str) -> Node:
    """item ID → 節點（字串 NodeId ``ns=<idx>;s=<item ID>``）。"""
    return client.get_node(f"ns={idx};s={item_id}")


def list_events(turbine_id: str, before: Dict[str, List[int]], after: Dict[str, List[int]],
                catalog: Dict[int, JsonObject], ts: str) -> List[JsonObject]:
    """前後兩次讀到的事件碼陣列 → 事件（欄位同 ``events.jsonl``）。

    Args:
        turbine_id: 機組 ID。
        before: 上一次的陣列（``{"A": [...], "T1": [...], "T2": [...]}``，不含空位 0）。
        after: 這一次的陣列。
        catalog: 警報目錄（``{code: {...}}``；查不到的碼文字留空）。
        ts: 這一次讀到的時間。

    Returns:
        新成立（``alarm_raised`` / ``trip``）與解除（``alarm_cleared`` / ``trip_cleared``）的事件。
    """
    events: List[JsonObject] = []
    for level in LISTS:
        old, new = before.get(level, []), after.get(level, [])
        raised = [c for c in new if c not in old]
        cleared = [c for c in old if c not in new]
        for code, kind in [(c, "alarm_raised" if level == "A" else "trip") for c in raised] + \
                [(c, "alarm_cleared" if level == "A" else "trip_cleared") for c in cleared]:
            events.append({"ts": ts, "turbine_id": turbine_id, "event_type": kind, "alarm_code": code,
                           "alarm_level": level, "alarm_text": str(catalog.get(code, {}).get("text", ""))})
    return events


class Watcher:
    """讀 OPC UA 節點（每台機組：``WATCH`` 的值 + 三個事件碼陣列）。"""

    def __init__(self, client: Client, idx: int, stations: Sequence[str]) -> None:
        self._client = client
        self.stations = list(stations)
        self._status = [node(client, idx, f"WindMindOM.{name}") for name in ("Status", "SimTime")]
        self._nodes: List[Node] = []
        for station in self.stations:
            self._nodes += [node(client, idx, f"Z72.{station}.{tag}") for tag in WATCH.values()]
            self._nodes += [node(client, idx, f"Z72.{station}.{tag}[{i}]")
                            for tag in LISTS.values() for i in range(SLOTS)]

    async def read(self) -> Dict[str, object]:
        """讀一次（一個 OPC UA Read 請求）。

        Returns:
            ``{"status", "sim_time", "turbines": {站號: {"values": {...}, "lists": {...}}}}``；
            還沒有值的節點為 None。
        """
        data = await self._client.read_attributes(self._status + self._nodes)
        values = [d.Value.Value if d.StatusCode is not None and d.StatusCode.is_good() and d.Value is not None else None for d in data]
        status, sim_time = values[0], values[1]
        per = len(WATCH) + len(LISTS) * SLOTS
        turbines: Dict[str, object] = {}
        for n, station in enumerate(self.stations):
            row = values[2 + n * per: 2 + (n + 1) * per]
            lists = {level: [int(c) for c in row[len(WATCH) + k * SLOTS: len(WATCH) + (k + 1) * SLOTS] if c]
                     for k, level in enumerate(LISTS)}
            turbines[station] = {"values": dict(zip(WATCH, row[:len(WATCH)])), "lists": lists}
        return {"status": status, "sim_time": sim_time, "turbines": turbines}


async def connect_opcua(client: Client) -> Tuple[int, Dict[str, object], List[str]]:
    """讀 namespace、狀態節點與機組站號（``Objects/Z72`` 底下的 ``H01`` …）。

    Returns:
        ``(namespace index, 狀態 dict, 站號清單)``。
    """
    idx = await client.get_namespace_index(NAMESPACE_URI)
    status: Dict[str, object] = {}
    for name in ("Source", "Status", "SimTime", "PackId", "Mode", "Speed"):
        status[name] = await node(client, idx, f"WindMindOM.{name}").read_value()
    z72 = await client.nodes.objects.get_child([f"{idx}:Z72"])
    stations = sorted([str((await child.read_browse_name()).Name) for child in await z72.get_children()])
    return idx, status, stations


def _turbine_for(station: str, turbines: Sequence[str]) -> str:
    """站號 → 機組 ID（``H01`` → ``WT001``，依數字對應；WS 開播訊息的機組清單）。"""
    number = int(station[1:])
    return next((t for t in turbines if int("".join(ch for ch in t if ch.isdigit()) or -1) == number), station)


async def _receive(ws: ClientConnection, summary: Summary, done: asyncio.Event, verbose: bool) -> None:
    """收 ack / 結束 / 錯誤（``stream=false`` 不會有讀值）。"""
    try:
        async for raw in ws:
            message = json.loads(raw)
            summary.add(message)
            if message.get("type") == "ack" and verbose:
                state = "收下" if message.get("accepted") else f"退回 {message.get('errors')}"
                print(f"  判斷 #{message.get('ref')} {state}，蓋章時間 {message['ts']}")
            elif message.get("type") == "control" and message.get("status") == "finished":
                print(f"資料播完（模擬時間 {message['sim_ts']}）")
                done.set()
            elif message.get("type") == "error":
                print(f"伺服器：{message.get('message')}", file=sys.stderr)
    except ConnectionClosed:
        pass
    finally:
        summary.close_code = ws.close_code
        done.set()


async def run(endpoint: str, ws_url: Optional[str] = None, token: Optional[str] = None, *, poll_s: float = 1.0,
              verbose: bool = True, use_env_proxy: bool = False, max_polls: Optional[int] = None) -> Summary:
    """讀 OPC UA 直到回放結束（有 WS 時送判斷）。

    Args:
        endpoint: ``opc.tcp://<host>:4840/windmindom/``。
        ws_url: ``ws://<host>:8000/ws/replay``；None＝只看、不送判斷。
        token: 回放 token（有 ``ws_url`` 時必填）。
        poll_s: 讀的間隔（實際秒）。
        verbose: 印出每個事件與判斷。
        use_env_proxy: WS 經過環境變數設定的 proxy；預設直連。
        max_polls: 最多讀幾次（None＝直到回放結束；即時模擬要 Ctrl+C）。

    Returns:
        統計（``counts["opcua_read"]`` 是讀的次數，``counts["opcua_event"]`` 是由陣列變化得到的事件數）。
    """
    summary = Summary()
    async with Client(endpoint) as client:
        idx, status, stations = await connect_opcua(client)
        print(f"OPC UA：{status['Source']}（{status['Status']}），資料包 {status['PackId'] or '-'}，"
              f"機組 {', '.join(stations)}")
        watcher = Watcher(client, idx, stations)
        ws: Optional[ClientConnection] = None
        done = asyncio.Event()
        receiver: Optional["asyncio.Task[None]"] = None
        catalog: Dict[int, JsonObject] = {}
        turbines: List[str] = []
        if ws_url is not None:
            ws = await connect(with_params(ws_url, ["stream=false"]),
                               **connect_options(token or "", use_env_proxy))  # type: ignore[arg-type]  # 依 websockets 版本組成
            first = json.loads(await ws.recv())
            summary.add(first)
            if first.get("type") != "control":
                print(f"WS 被拒絕：{first.get('message')}", file=sys.stderr)
                await ws.close()
                summary.close_code = ws.close_code
                return summary
            catalog = {int(e["code"]): e for e in first["alarm_catalog"]["events"]}
            turbines = list(first["stream"]["turbines"])
            receiver = asyncio.create_task(_receive(ws, summary, done, verbose))
        assistant = BaselineAssistant()
        previous: Dict[str, Dict[str, List[int]]] = {}
        sent = polls = 0
        try:
            while not done.is_set() and (max_polls is None or polls < max_polls):
                snapshot = await watcher.read()
                polls += 1
                summary.counts["opcua_read"] = polls
                sim_time = snapshot["sim_time"]
                ts = (sim_time.replace(tzinfo=timezone.utc) if isinstance(sim_time, datetime)
                      else datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                for station, current in snapshot["turbines"].items():  # type: ignore[attr-defined]
                    turbine = _turbine_for(station, turbines)
                    for event in list_events(turbine, previous.get(station, {}), current["lists"], catalog, ts):
                        summary.counts["opcua_event"] = summary.counts.get("opcua_event", 0) + 1
                        judgement = assistant.on_event(event) if ws is not None else None
                        if verbose:
                            print(f"  {ts} {turbine} {event['event_type']} {event['alarm_code']} "
                                  f"{event['alarm_text']}（TurSt {current['values']['state']}）"
                                  + (f" → 送出判斷 #{sent + 1} {judgement['component']}" if judgement else ""))
                        if judgement is not None and ws is not None:
                            sent += 1
                            await ws.send(json.dumps({"type": "prediction", "id": sent, **judgement},
                                                     ensure_ascii=False))
                    previous[station] = current["lists"]
                if ws is None and snapshot["status"] in END_STATUSES:
                    print(f"回放狀態：{snapshot['status']}")
                    break
                try:
                    await asyncio.wait_for(done.wait(), poll_s)
                except asyncio.TimeoutError:
                    pass
            if ws is not None:
                # 送出的判斷都拿到 ack 再離開（伺服器在資料播完後還會開一小段時間收 ack）
                for _ in range(100):
                    if summary.counts.get("ack", 0) >= sent or ws.close_code is not None:
                        break
                    await asyncio.sleep(0.05)
        finally:
            if ws is not None:
                await ws.close()
            if receiver is not None:
                await receiver
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 進入點。

    Returns:
        exit code（0 成功、1 被拒絕 / 有判斷被退回 / 連不上、2 參數錯誤）。
    """
    parser = argparse.ArgumentParser(description="OPC UA 的受測端範例（讀 Z72 tag、經 WS 送判斷）")
    parser.add_argument("endpoint", help="opc.tcp://<host>:4840/windmindom/")
    parser.add_argument("--ws", help="ws://<host>:8000/ws/replay（不給＝只看、不送判斷）")
    parser.add_argument("--token", default=os.environ.get("WMOM_REPLAY_TOKEN"), help="回放 token")
    parser.add_argument("--poll", type=float, default=1.0, help="讀的間隔（秒，預設 1）")
    parser.add_argument("--use-env-proxy", action="store_true", help="WS 經過環境變數設定的 HTTP proxy（預設直連）")
    parser.add_argument("-q", "--quiet", action="store_true", help="只印開始 / 結束與統計")
    args = parser.parse_args(argv)
    if args.ws and not args.token:
        print("送判斷需要 --token（或環境變數 WMOM_REPLAY_TOKEN）", file=sys.stderr)
        return 2
    if args.poll <= 0:
        print("--poll 要大於 0", file=sys.stderr)
        return 2
    try:
        summary = asyncio.run(run(args.endpoint, args.ws, args.token, poll_s=args.poll, verbose=not args.quiet,
                                  use_env_proxy=args.use_env_proxy))
    except (OSError, asyncio.TimeoutError, ua.UaError) as exc:  # 連不上（位址、埠、防火牆）
        print(f"連不上：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    code = summary.close_code
    if args.ws:
        print(f"WS 連線關閉：{code}（{CLOSE_CODES.get(code or 0, '其他')}）")
    print("統計：" + "、".join(f"{k} {v}" for k, v in sorted(summary.counts.items())))
    print(f"判斷：收下 {summary.accepted}、退回 {len(summary.rejected)}")
    return 1 if summary.rejected or summary.errors or code not in (1000, None) else 0


if __name__ == "__main__":
    sys.exit(main())
