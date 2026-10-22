"""WebSocket 回放的受測端範例（介面合約 v1.1 §12，WMOM-20261021-06）。

連上 windMindOM 的情境回放，一邊收讀值 / 事件 / 10 分鐘統計，一邊用基準助手（``baseline_assistant``
的關鍵字對照）即時送出診斷。示範三件事：

1. **收與想分開**：一個 task 只負責把訊息放進佇列，另一個 task 做判斷。回放照模擬時鐘播，不會等你；
   伺服器以「收到預測時的模擬時間」蓋 ``ts``，判斷拖得越久，延遲越大。
2. **預測不用填 ``ts`` / ``pack_id``**：伺服器會填（填了也不採用）；``ack`` 回報實際蓋上的時間。
3. **斷線重連**：單次回放（evaluation）的時鐘不會停，重連時預設補送已過去的資料（``backfill``）。

需要 ``websockets``（``pip install -r requirements.txt``）。用法::

    python stream_client.py ws://<host>:8000/ws/replay --token <出題端給的 token>
    python stream_client.py ws://<host>:8000/ws/replay --token <token> --record received.jsonl

token 也可以放環境變數 ``WMOM_REPLAY_TOKEN``。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, TextIO

from websockets.asyncio.client import ClientConnection, connect

from baseline_assistant import guess_component

JsonObject = Dict[str, object]


class OnlineBaseline:
    """``baseline_assistant.diagnose`` 的即時版：一次吃一則事件，需要時回傳一筆預測。

    ``ts`` / ``pack_id`` 留給伺服器填。
    """

    def __init__(self) -> None:
        self._seen_codes: Dict[str, List[int]] = {}

    def on_event(self, event: JsonObject) -> Optional[JsonObject]:
        """處理一則事件。

        Args:
            event: ``{"type": "event", ...}`` 訊息（欄位同 events.jsonl）。

        Returns:
            預測（合約 §6 欄位，不含 ``ts`` / ``pack_id``）或 None。
        """
        turbine = str(event["turbine_id"])
        if event["event_type"] == "info":
            return {"turbine_id": turbine, "category": "nuisance", "component": None,
                    "manual_refs": [event["alarm_code"]],
                    "root_cause": f"Informational event {event['alarm_code']}: {event['alarm_text']}"}
        if event["event_type"] not in ("alarm_raised", "trip"):
            return None
        code = int(str(event["alarm_code"]))
        codes = self._seen_codes.setdefault(turbine, [])
        if code in codes:
            return None
        codes.insert(0, code)
        component = guess_component(str(event["alarm_text"]))
        if component is None:
            return None
        return {"turbine_id": turbine, "category": "real_fault", "component": component, "manual_refs": list(codes),
                "root_cause": f"Alarm {code}: {event['alarm_text']}",
                "actions": ["Check the Z72 manual entries cited in manual_refs."]}


class Summary:
    """收到的訊息統計（結束時印出）。"""

    def __init__(self) -> None:
        self.counts: Dict[str, int] = {}
        self.accepted = 0
        self.rejected: List[JsonObject] = []

    def add(self, message: JsonObject) -> None:
        kind = str(message.get("type"))
        self.counts[kind] = self.counts.get(kind, 0) + 1
        if kind == "ack":
            if message.get("accepted"):
                self.accepted += 1
            else:
                self.rejected.append(message)


async def _receive(ws: ClientConnection, inbox: "asyncio.Queue[Optional[JsonObject]]",
                   record: Optional[TextIO]) -> None:
    """只收訊息、放進佇列（不在這裡做判斷，免得卡住接收）。"""
    try:
        async for raw in ws:
            message = json.loads(raw)
            if record is not None:
                record.write(json.dumps(message, ensure_ascii=False) + "\n")
            await inbox.put(message)
    finally:
        await inbox.put(None)


async def _think(ws: ClientConnection, inbox: "asyncio.Queue[Optional[JsonObject]]", summary: Summary,
                 verbose: bool) -> None:
    """依序處理訊息並送出預測。"""
    assistant = OnlineBaseline()
    sent = acked = 0
    finished = False
    while True:
        message = await inbox.get()
        if message is None:
            return
        summary.add(message)
        kind = message.get("type")
        if kind == "ack":
            acked += 1
        if kind == "control":
            if message.get("status") == "started":
                stream = message["stream"]
                assert isinstance(stream, dict)
                print(f"開始：{stream['pack_id']}（{stream['mode']}，{stream['speed']}x），"
                      f"{stream['sim_start']} → {stream['sim_end']}，機組 {', '.join(stream['turbines'])}；"
                      f"目前模擬時間 {message['sim_ts']}")
            elif message.get("status") == "finished":
                finished = True
                print(f"資料播完（模擬時間 {message['sim_ts']}）；之後的預測不收，"
                      f"伺服器 {message['closing_in_s']} 秒後關閉連線")
        elif kind == "event":
            prediction = assistant.on_event(message)
            if prediction is not None:
                sent += 1
                await ws.send(json.dumps({"type": "prediction", "id": sent, **prediction}, ensure_ascii=False))
                if verbose:
                    print(f"  {message['ts']} {message['turbine_id']} {message['event_type']} "
                          f"{message['alarm_code']} → 送出預測 #{sent} {prediction['component']}")
        elif kind == "ack" and verbose:
            state = "收下" if message.get("accepted") else f"退回 {message.get('errors')}"
            print(f"  預測 #{message.get('ref')} {state}，蓋章時間 {message['ts']}")
        elif kind == "error":
            print(f"伺服器錯誤：{message.get('message')}（code {message.get('code')}）", file=sys.stderr)
        if finished and acked >= sent:
            await ws.close()  # 送出的預測都收到 ack 了才離開


async def run(url: str, token: str, *, backfill: bool = True, record: Optional[Path] = None,
              verbose: bool = True) -> Summary:
    """連上回放直到結束。

    Args:
        url: ``ws://<host>:<port>/ws/replay``。
        token: 回放 token。
        backfill: 單次回放已開始時，是否補送已過去的資料。
        record: 把收到的訊息逐行存成 JSONL（除錯 / 離線重現用）。
        verbose: 印出每筆預測與 ack。

    Returns:
        統計。
    """
    summary = Summary()
    target = url if backfill else f"{url}{'&' if '?' in url else '?'}backfill=false"
    handle = record.open("w", encoding="utf-8") if record is not None else None
    try:
        async with connect(target, additional_headers={"Authorization": f"Bearer {token}"},
                           max_size=8 * 1024 * 1024) as ws:
            inbox: "asyncio.Queue[Optional[JsonObject]]" = asyncio.Queue()
            await asyncio.gather(_receive(ws, inbox, handle), _think(ws, inbox, summary, verbose))
    finally:
        if handle is not None:
            handle.close()
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 進入點。

    Returns:
        exit code（0 成功、1 有預測被退回或伺服器回錯誤、2 參數錯誤）。
    """
    parser = argparse.ArgumentParser(description="WebSocket 回放的受測端範例（基準助手）")
    parser.add_argument("url", help="ws://<host>:<port>/ws/replay")
    parser.add_argument("--token", default=os.environ.get("WMOM_REPLAY_TOKEN"), help="回放 token")
    parser.add_argument("--no-backfill", action="store_true", help="中途加入時不補送已過去的資料")
    parser.add_argument("--record", type=Path, help="把收到的訊息存成 JSONL")
    parser.add_argument("-q", "--quiet", action="store_true", help="只印開始 / 結束與統計")
    args = parser.parse_args(argv)
    if not args.token:
        print("需要 --token（或環境變數 WMOM_REPLAY_TOKEN）", file=sys.stderr)
        return 2
    summary = asyncio.run(run(args.url, args.token, backfill=not args.no_backfill, record=args.record,
                              verbose=not args.quiet))
    print("收到：" + "、".join(f"{k} {v}" for k, v in sorted(summary.counts.items())))
    print(f"預測：收下 {summary.accepted}、退回 {len(summary.rejected)}")
    return 1 if summary.rejected or summary.counts.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
