"""WebSocket 回放的受測端範例（介面合約 v1.1 §12，WMOM-20261021-06）。

連上 windMindOM 的情境回放，一邊收讀值 / 事件 / 10 分鐘統計，一邊用基準助手
（``baseline_assistant.BaselineAssistant``）即時送出判斷。示範三件事：

1. **收與想分開**：一個 task 只負責把訊息放進佇列，另一個 task 做判斷。回放照模擬時鐘播，不會等你；
   伺服器以「收到判斷時的模擬時間」蓋 ``ts``，判斷拖得越久，時間就越晚。接收端也要一直讀：伺服器每 20 秒
   ping 一次，event loop 被同步的大模型呼叫卡住太久，連線會被斷掉。
2. **判斷不用填 ``ts`` / ``pack_id``**：伺服器會填（填了也不採用）；``ack`` 回報實際蓋上的時間。
3. **被拒絕時看關閉碼**：token 錯、回放已撤銷 / 已結束等，伺服器先送 ``error`` 再關閉（合約 §12.2）。

斷線後直接再執行一次就會重連。正式（evaluation）回放的時鐘不會停，重連時預設補送已過去的資料
（``--no-backfill`` 只從現在開始）。

需要 ``websockets``（``pip install -r requirements.txt``）。用法::

    python stream_client.py ws://<host>:8000/ws/replay --token <出題端給的 token>
    python stream_client.py ws://<host>:8000/ws/replay --token <token> --check     # 只檢查 token，不開始計時
    python stream_client.py ws://<host>:8000/ws/replay --token <token> --record received.jsonl

token 也可以放環境變數 ``WMOM_REPLAY_TOKEN``。預設不經過環境變數設定的 HTTP proxy（直連伺服器）；
校園網路需要 proxy 時加 ``--use-env-proxy``。
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, TextIO

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from baseline_assistant import BaselineAssistant

JsonObject = Dict[str, object]

# 合約 §12.2 的關閉碼
CLOSE_CODES: Dict[int, str] = {
    1000: "正常結束",
    1011: "伺服器錯誤",
    4401: "缺 token 或 token 無效",
    4403: "回放已撤銷或 token 已到期",
    4404: "情境不能回放",
    4409: "這個回放的連線已滿",
    4410: "單次回放已結束",
}


class Summary:
    """收到的訊息統計（結束時印出）。"""

    def __init__(self) -> None:
        self.counts: Dict[str, int] = {}
        self.accepted = 0
        self.rejected: List[JsonObject] = []
        self.errors: List[JsonObject] = []
        self.close_code: Optional[int] = None

    def add(self, message: JsonObject) -> None:
        """記一則訊息。"""
        kind = str(message.get("type"))
        self.counts[kind] = self.counts.get(kind, 0) + 1
        if kind == "ack":
            if message.get("accepted"):
                self.accepted += 1
            else:
                self.rejected.append(message)
        elif kind == "error":
            self.errors.append(message)


async def _receive(ws: ClientConnection, inbox: "asyncio.Queue[Optional[JsonObject]]", summary: Summary,
                   record: Optional[TextIO]) -> None:
    """只收訊息、放進佇列（不在這裡做判斷，免得卡住接收）；連線關閉時記下關閉碼。"""
    try:
        async for raw in ws:
            message = json.loads(raw)
            if record is not None:
                record.write(json.dumps(message, ensure_ascii=False) + "\n")
            await inbox.put(message)
    except ConnectionClosed:
        pass
    finally:
        summary.close_code = ws.close_code
        await inbox.put(None)


async def _think(ws: ClientConnection, inbox: "asyncio.Queue[Optional[JsonObject]]", summary: Summary,
                 verbose: bool) -> None:
    """依序處理訊息並送出判斷；資料播完、送出的判斷都拿到 ack 後關閉連線。"""
    assistant = BaselineAssistant()
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
            if verbose:
                state = "收下" if message.get("accepted") else f"退回 {message.get('errors')}"
                print(f"  判斷 #{message.get('ref')} {state}，蓋章時間 {message['ts']}")
        elif kind == "control" and message.get("status") == "started":
            stream = message["stream"]
            assert isinstance(stream, dict)
            print(f"開始：{stream['pack_id']}（{stream['mode']}，{stream['speed']}x），"
                  f"{stream['sim_start']} → {stream['sim_end']}，機組 {', '.join(stream['turbines'])}；"
                  f"目前模擬時間 {message['sim_ts']}")
        elif kind == "control" and message.get("status") == "checked":
            print(f"token 有效：{json.dumps(message['run'], ensure_ascii=False)}")
        elif kind == "control" and message.get("status") == "finished":
            finished = True
            print(f"資料播完（模擬時間 {message['sim_ts']}）；之後的判斷不收，伺服器 {message['closing_in_s']} 秒後關閉連線")
        elif kind == "event":
            judgement = assistant.on_event(message)
            if judgement is not None:
                sent += 1
                await ws.send(json.dumps({"type": "prediction", "id": sent, **judgement}, ensure_ascii=False))
                if verbose:
                    print(f"  {message['ts']} {message['turbine_id']} {message['event_type']} "
                          f"{message['alarm_code']} → 送出判斷 #{sent} {judgement['component']}")
        elif kind == "error":
            print(f"伺服器：{message.get('message')}", file=sys.stderr)
        if finished and acked >= sent:
            await ws.close()  # 送出的判斷都收到 ack 了才離開


async def run(url: str, token: str, *, backfill: bool = True, check: bool = False, record: Optional[Path] = None,
              verbose: bool = True, use_env_proxy: bool = False) -> Summary:
    """連上回放直到結束。

    Args:
        url: ``ws://<host>:<port>/ws/replay``。
        token: 回放 token。
        backfill: 單次回放已開始時，是否補送已過去的資料。
        check: 只檢查 token、印出回放狀態（不開始計時）。
        record: 把收到的訊息逐行存成 JSONL（除錯 / 離線重現用）。
        verbose: 印出每筆判斷與 ack。
        use_env_proxy: 經過環境變數（``HTTP(S)_PROXY``）設定的 proxy；預設直連。

    Returns:
        統計（含伺服器的關閉碼）。
    """
    summary = Summary()
    params = [] if backfill else ["backfill=false"]
    if check:
        params.append("check=true")
    target = url + ("" if not params else ("&" if "?" in url else "?") + "&".join(params))
    options: Dict[str, object] = {"additional_headers": {"Authorization": f"Bearer {token}"},
                                  "max_size": 8 * 1024 * 1024}
    if "proxy" in inspect.signature(connect).parameters:  # websockets 15 起預設會用環境變數的 proxy
        options["proxy"] = True if use_env_proxy else None
    handle = record.open("w", encoding="utf-8") if record is not None else None
    try:
        async with connect(target, **options) as ws:  # type: ignore[arg-type]  # options 依 websockets 版本組成
            inbox: "asyncio.Queue[Optional[JsonObject]]" = asyncio.Queue()
            await asyncio.gather(_receive(ws, inbox, summary, handle), _think(ws, inbox, summary, verbose))
    finally:
        if handle is not None:
            handle.close()
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 進入點。

    Returns:
        exit code（0 成功、1 被拒絕 / 有判斷被退回 / 伺服器回錯誤、2 參數錯誤）。
    """
    parser = argparse.ArgumentParser(description="WebSocket 回放的受測端範例（基準助手）")
    parser.add_argument("url", help="ws://<host>:<port>/ws/replay")
    parser.add_argument("--token", default=os.environ.get("WMOM_REPLAY_TOKEN"), help="回放 token")
    parser.add_argument("--check", action="store_true", help="只檢查 token、印出回放狀態（不開始計時）")
    parser.add_argument("--no-backfill", action="store_true", help="中途加入時不補送已過去的資料")
    parser.add_argument("--record", type=Path, help="把收到的訊息存成 JSONL")
    parser.add_argument("--use-env-proxy", action="store_true", help="經過環境變數設定的 HTTP proxy（預設直連）")
    parser.add_argument("-q", "--quiet", action="store_true", help="只印開始 / 結束與統計")
    args = parser.parse_args(argv)
    if not args.token:
        print("需要 --token（或環境變數 WMOM_REPLAY_TOKEN）", file=sys.stderr)
        return 2
    try:
        summary = asyncio.run(run(args.url, args.token, backfill=not args.no_backfill, check=args.check,
                                  record=args.record, verbose=not args.quiet, use_env_proxy=args.use_env_proxy))
    except OSError as exc:  # 連不上（位址、埠、防火牆、proxy）
        print(f"連不上 {args.url}：{exc}", file=sys.stderr)
        return 1
    code = summary.close_code
    print(f"連線關閉：{code}（{CLOSE_CODES.get(code or 0, '其他')}）")
    print("收到：" + "、".join(f"{k} {v}" for k, v in sorted(summary.counts.items())))
    print(f"判斷：收下 {summary.accepted}、退回 {len(summary.rejected)}")
    return 1 if summary.rejected or summary.errors or code not in (1000, None) else 0


if __name__ == "__main__":
    sys.exit(main())
