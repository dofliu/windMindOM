"""以 OPC UA 播出情境回放（WMOM-20261021-07，EPIC-DS Phase 3c ③）。

模仿 Bachmann Z72 的 tag（``Z72.H{nn}.{group}.Z72PLC__UI_Loc_*``、``Z72PLC__ActiveAlarm[0..20]`` …），
資料來自一個回放（``tools/replay_runs.py create`` 建立）。受測端用 OPC UA 讀資料，判斷照樣經 WS 送：
``ws://<host>:8000/ws/replay?stream=false``（同一個回放 token，伺服器蓋 ``ts``）。

- **正式評測（evaluation）**：server 一啟動就開播（寫入回放的開始時間），之後的 WS 連線加入同一個時鐘；
  回放已開始（例：server 重啟）就接著播。播完後不能再開。
- **練習（practice）**：每次啟動都從頭播；起點記在回放上，WS ``?stream=false`` 以它對時。

範例：
  # 先建回放（印出 token 與回放 id）
  python tools/replay_runs.py "<db>" create 12 --speed 60
  # 以 OPC UA 播出回放 #3（opc.tcp://0.0.0.0:4840/windmindom/）
  python tools/opcua_server.py "<db>" 3
  python tools/opcua_server.py "<db>" 3 --port 4841 --exit-when-finished

即時模擬的 OPC UA 由主程式提供：``WMOM_OPCUA_ENABLE=true python run.py``。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
MONITORING_ROOT = REPO_ROOT / "modules" / "monitoring"
for _path in (REPO_ROOT, MONITORING_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from modules.auth.dependencies import is_auth_enforced  # noqa: E402
from server import opcua_server as ou  # noqa: E402
from server import replay as rp  # noqa: E402
from server.scenario_pack import ScenarioPackError  # noqa: E402
from server.storage import Storage  # noqa: E402
from simulator.time_utils import iso_utc, parse_iso  # noqa: E402


# 回放被撤銷 / 到期 / 刪除後，server 再開幾秒讓客戶端讀到 WindMindOM.Status
STOP_LINGER_S = 10.0


def _unusable(run: Optional[dict]) -> Optional[Tuple[str, str]]:
    """回放不能再播的原因：``(代碼, 說明)``，代碼 ∈ ``missing`` / ``revoked`` / ``expired``；可以播回 None。"""
    if run is None:
        return "missing", "回放不存在"
    if run["revoked_at"]:
        return "revoked", "回放已撤銷"
    if parse_iso(run["expires_at"]).timestamp() < rp.wall_time():
        return "expired", "回放 token 已到期"
    return None


def load_run(storage: Storage, run_id: int) -> Tuple[dict, rp.ScenarioReplay]:
    """載入回放並檢查能不能播（還沒開播、不動時鐘）。

    Args:
        storage: 風場 DB。
        run_id: 回放 id。

    Returns:
        ``(run, replay)``。

    Raises:
        ValueError: 回放不能播（訊息說明原因）。
    """
    run = storage.get_replay_run(run_id)
    reason = _unusable(run)
    if reason is not None:
        raise ValueError(reason[1])
    assert run is not None
    try:
        replay = rp.ScenarioReplay(storage, int(run["scenario_id"]))
    except ScenarioPackError as exc:
        raise ValueError(f"情境不能回放：{exc}") from exc
    if run["mode"] == "evaluation" and run["started_at"]:
        _clock(run, replay, parse_iso(run["started_at"]).timestamp())  # 已經播完就在這裡擋下
    return run, replay


def _clock(run: dict, replay: rp.ScenarioReplay, wall_start: float) -> rp.ReplayClock:
    clock = rp.ReplayClock(replay.sim_start, float(run["speed"]), wall_start)
    if run["mode"] == "evaluation" and rp.wall_time() > clock.wall_at(replay.sim_end) + rp.CLOSE_GRACE_S:
        raise ValueError("單次回放已結束")
    return clock


def start_clock(storage: Storage, run: dict, replay: rp.ScenarioReplay) -> rp.ReplayClock:
    """開播。

    - 正式評測：寫入開始時間（已開始就沿用），WS 連線共用同一個時鐘。
    - 練習：從現在播，並把起點記在回放上（每次啟動都覆寫），WS ``?stream=false`` 用它對時。

    Args:
        storage: 風場 DB。
        run: ``load_run`` 回傳的回放。
        replay: ``load_run`` 回傳的回放資料。

    Returns:
        回放時鐘。

    Raises:
        ValueError: 單次回放已結束。
    """
    now = rp.wall_time()
    now_iso = iso_utc(datetime.fromtimestamp(now, tz=timezone.utc))
    if run["mode"] != "evaluation":
        storage.anchor_practice_run(int(run["id"]), now_iso)
        return _clock(run, replay, parse_iso(now_iso).timestamp())
    started_at = storage.start_replay_run(int(run["id"]), now_iso)
    return _clock(run, replay, parse_iso(started_at).timestamp())


def _connect_hint(host: str, port: int) -> str:
    if host not in ("0.0.0.0", "::", ""):
        return ""
    return f"（受測端請用這台電腦的 IP 或主機名稱連線，例 opc.tcp://{socket.gethostname()}:{port}{ou.ENDPOINT_PATH}）"


async def serve(storage: Storage, run_id: int, host: str, port: int, exit_when_finished: bool) -> int:
    """起 server 並播出回放（節點建好、開始監聽之後才開播）。

    Returns:
        exit code（0 播完、1 回放被撤銷 / 到期 / 刪除）。

    Raises:
        ValueError: 回放不能播（含：正式評測但沒有強制登入，``WMOM_AUTH_ENFORCE``）。
        OSError: 埠被占用等，server 起不來。
    """
    run, replay = load_run(storage, run_id)
    # 伺服器是否強制登入看環境變數：與主程式用同一套設定（DEC-20261022-05）
    if run["mode"] == "evaluation" and not is_auth_enforced():
        raise ValueError(rp.EVALUATION_NEEDS_AUTH)
    server = ou.Z72OpcUaServer(host=host, port=port)
    await server.start(turbines=replay.turbines)
    try:
        clock = start_clock(storage, run, replay)

        async def check_run() -> Optional[str]:
            reason = _unusable(await asyncio.to_thread(storage.get_replay_run, run_id))
            return None if reason is None else reason[0]

        feeder = ou.ReplayFeeder(server, replay, clock, str(run["mode"]), float(run["speed"]), check_run=check_run)
        await feeder.setup()
        print(f"OPC UA：{server.endpoint}（namespace {ou.NAMESPACE_URI}）{_connect_hint(host, port)}")
        print(f"回放 #{run_id}：{replay.pack_id}（{run['mode']}，{run['speed']:g}x），"
              f"{rp.z(replay.sim_start)} → {rp.z(replay.sim_end)}；目前模擬時間 {rp.z(clock.sim_now())}")
        await feeder.run()
        if feeder.stop_reason is not None:
            print(f"回放已停止：{feeder.stop_reason}（{STOP_LINGER_S:g} 秒後關閉 server）", file=sys.stderr)
            await asyncio.sleep(STOP_LINGER_S)
            return 1
        print(f"資料播完（模擬時間 {rp.z(replay.sim_end)}）")
        if not exit_when_finished:
            print("節點保留最後的值；Ctrl+C 結束")
            await asyncio.Event().wait()
        return 0
    finally:
        await server.stop()


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 進入點。

    Returns:
        exit code（0 成功、1 回放不能播 / 被撤銷 / server 起不來、2 參數錯誤）。
    """
    parser = argparse.ArgumentParser(description="以 OPC UA 播出情境回放（模仿 Bachmann Z72 tag）")
    parser.add_argument("db", type=Path, help="風場 SQLite DB 路徑")
    parser.add_argument("run_id", type=int, help="回放 id（tools/replay_runs.py create / list）")
    parser.add_argument("--host", default="0.0.0.0", help="監聽位址（預設 0.0.0.0）")
    parser.add_argument("--port", type=int, default=ou.DEFAULT_PORT, help=f"監聽埠（預設 {ou.DEFAULT_PORT}）")
    parser.add_argument("--exit-when-finished", action="store_true", help="資料播完就結束（預設保留最後的值）")
    args = parser.parse_args(argv)
    if not args.db.exists():
        print(f"找不到 DB：{args.db}", file=sys.stderr)
        return 2
    logging.getLogger("asyncua").setLevel(logging.WARNING)
    try:
        return asyncio.run(serve(Storage(db_path=str(args.db)), args.run_id, args.host, args.port,
                                 args.exit_when_finished))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError as exc:  # 埠被占用、位址不對
        print(f"OPC UA server 起不來（{args.host}:{args.port}）：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
