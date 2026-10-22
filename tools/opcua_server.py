"""以 OPC UA 播出情境回放（WMOM-20261021-07，EPIC-DS Phase 3c ③）。

模仿 Bachmann Z72 的 tag（``Z72.H{nn}.{group}.Z72PLC__UI_Loc_*``、``Z72PLC__ActiveAlarm[0..20]`` …），
資料來自一個回放（``tools/replay_runs.py create`` 建立）。受測端用 OPC UA 讀資料，判斷照樣經 WS 送：
``ws://<host>:8000/ws/replay?stream=false``（同一個回放 token，伺服器蓋 ``ts``）。

- **正式評測（evaluation）**：server 一啟動就開播（寫入回放的開始時間），之後的 WS 連線加入同一個時鐘；
  回放已開始（例：server 重啟）就接著播。播完後不能再開。
- **練習（practice）**：每次啟動都從頭播。

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
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
MONITORING_ROOT = REPO_ROOT / "modules" / "monitoring"
for _path in (REPO_ROOT, MONITORING_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from server import opcua_server as ou  # noqa: E402
from server import replay as rp  # noqa: E402
from server.scenario_pack import ScenarioPackError  # noqa: E402
from server.storage import Storage  # noqa: E402
from simulator.time_utils import iso_utc, parse_iso  # noqa: E402


def _unusable(run: Optional[dict]) -> Optional[str]:
    """回放不能再播的原因（不存在 / 撤銷 / 到期），可以播回 None。"""
    if run is None:
        return "回放不存在"
    if run["revoked_at"]:
        return "回放已撤銷"
    if parse_iso(run["expires_at"]).timestamp() < rp.wall_time():
        return "回放 token 已到期"
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
        raise ValueError(reason)
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
    """開播：正式評測寫入開始時間（已開始就沿用，WS 連線共用同一個時鐘）；練習從現在播。

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
    if run["mode"] != "evaluation":
        return _clock(run, replay, now)
    started_at = storage.start_replay_run(int(run["id"]), iso_utc(datetime.fromtimestamp(now, tz=timezone.utc)))
    return _clock(run, replay, parse_iso(started_at).timestamp())


async def serve(storage: Storage, run_id: int, host: str, port: int, exit_when_finished: bool) -> int:
    """起 server 並播出回放（節點建好、開始監聽之後才開播）。

    Returns:
        exit code（0 播完、1 回放被撤銷 / 到期）。
    """
    run, replay = load_run(storage, run_id)
    server = ou.Z72OpcUaServer(host=host, port=port)
    await server.start(turbines=replay.turbines)
    try:
        clock = start_clock(storage, run, replay)

        async def check_run() -> Optional[str]:
            reason = _unusable(await asyncio.to_thread(storage.get_replay_run, run_id))
            return None if reason is None else ("revoked" if "撤銷" in reason else "expired")

        feeder = ou.ReplayFeeder(server, replay, clock, str(run["mode"]), float(run["speed"]), check_run=check_run)
        await feeder.setup()
        print(f"OPC UA：{server.endpoint}（namespace {ou.NAMESPACE_URI}）")
        print(f"回放 #{run_id}：{replay.pack_id}（{run['mode']}，{run['speed']:g}x），"
              f"{rp.z(replay.sim_start)} → {rp.z(replay.sim_end)}；目前模擬時間 {rp.z(clock.sim_now())}")
        await feeder.run()
        if feeder.stop_reason is not None:
            print(f"回放已停止：{feeder.stop_reason}", file=sys.stderr)
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
        exit code（0 成功、1 回放不能播 / 被撤銷、2 參數錯誤）。
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
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
