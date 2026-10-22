"""情境 WebSocket 回放的出題端 CLI（WMOM-20261021-06，EPIC-DS Phase 3b ② 串流）。

直接操作風場 DB（不必登入），與 REST 端點 ``/api/scenarios/{id}/replay-runs`` 相同。受測端連線時伺服器
必須在跑，且以同一個風場為目前風場（回放存在那個風場的 DB）。

範例：
  # 建立單次回放（60 倍速），印出 token——只會出現這一次
  python tools/replay_runs.py "modules/monitoring/data/farms/<farm>/wind_farm.db" create 12 --speed 60

  # 練習回放（每次連線從頭播）
  python tools/replay_runs.py "<db>" create 12 --mode practice --speed 600 --label 第3組練習

  # 列出情境的回放、撤銷
  python tools/replay_runs.py "<db>" list 12
  python tools/replay_runs.py "<db>" revoke 3

  # 下載受測端送來的預測，給 starter kit 評分
  python tools/replay_runs.py "<db>" predictions 3 -o predictions.jsonl
  python examples/rag_starter_kit/score.py --answers <評分端版資料包目錄> --predictions predictions.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
MONITORING_ROOT = REPO_ROOT / "modules" / "monitoring"
for _path in (REPO_ROOT, MONITORING_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from server import replay as rp  # noqa: E402
from server.scenario_pack import ScenarioPackError  # noqa: E402
from server.storage import Storage  # noqa: E402
from simulator.time_utils import iso_utc  # noqa: E402


def _print_run(view: dict) -> None:
    print(f"  #{view['id']}  {view['mode']:<10} {view['speed']:>8g}x  {view['status']:<11} "
          f"連線 {view['connections']}  預測 {view['predictions']}  到期 {view['expires_at']}"
          + (f"  結束 {view['ends_at']}" if view.get("ends_at") else "")
          + (f"  （{view['label']}）" if view.get("label") else ""))


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 進入點。

    Args:
        argv: 命令列參數（測試用）；None＝``sys.argv``。

    Returns:
        exit code（0 成功、1 情境不能回放 / 回放不存在、2 參數錯誤）。
    """
    parser = argparse.ArgumentParser(description="情境 WebSocket 回放（合約 v1.1 §12）")
    parser.add_argument("db", type=Path, help="風場 SQLite DB 路徑")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="建立回放並印出 token")
    create.add_argument("scenario_id", type=int)
    create.add_argument("--mode", choices=rp.REPLAY_MODES, default="evaluation",
                        help="evaluation＝單次直播（預設）；practice＝每次連線從頭播")
    create.add_argument("--speed", type=float, default=rp.DEFAULT_SPEED,
                        help=f"模擬秒 / 實際秒（{rp.MIN_SPEED:g}–{rp.MAX_SPEED:g}，預設 {rp.DEFAULT_SPEED:g}）")
    create.add_argument("--label", help="備註（受測端看不到）")
    create.add_argument("--expires-hours", type=float, default=rp.DEFAULT_EXPIRES_HOURS, help="token 有效時數")
    listing = commands.add_parser("list", help="列出情境的回放")
    listing.add_argument("scenario_id", type=int)
    revoke = commands.add_parser("revoke", help="撤銷回放")
    revoke.add_argument("run_id", type=int)
    predictions = commands.add_parser("predictions", help="下載受測端的預測（predictions.jsonl）")
    predictions.add_argument("run_id", type=int)
    predictions.add_argument("--connection", type=int, help="只取某次連線（練習模式）")
    predictions.add_argument("-o", "--out", type=Path, help="輸出檔（預設印到標準輸出）")
    args = parser.parse_args(argv)
    if not args.db.exists():
        print(f"找不到 DB：{args.db}", file=sys.stderr)
        return 2
    storage = Storage(db_path=str(args.db))

    if args.command == "create":
        if args.label is not None and len(args.label) > 100:
            print("--label 最多 100 字", file=sys.stderr)
            return 2
        try:
            run, token = rp.create_run(storage, args.scenario_id, mode=args.mode, speed=args.speed, label=args.label,
                                       expires_in_hours=args.expires_hours, created_by="cli")
        except ScenarioPackError as exc:
            print(f"情境不能回放：{exc}", file=sys.stderr)
            return 1
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        _print_run(rp.run_view(storage, run))
        print(f"token：{token}")
        print("受測端連線：ws://<host>:<port>/ws/replay（標頭 Authorization: Bearer <token>，或 ?token=<token>）")
        return 0
    if args.command == "list":
        runs = storage.list_replay_runs(args.scenario_id)
        if not runs:
            print(f"情境 {args.scenario_id} 沒有回放")
        for run in runs:
            _print_run(rp.run_view(storage, run))
        return 0
    if args.command == "revoke":
        if not storage.revoke_replay_run(args.run_id, iso_utc()):
            print(f"回放 {args.run_id} 不存在", file=sys.stderr)
            return 1
        run = storage.get_replay_run(args.run_id)
        assert run is not None
        _print_run(rp.run_view(storage, run))
        return 0
    if storage.get_replay_run(args.run_id) is None:
        print(f"回放 {args.run_id} 不存在", file=sys.stderr)
        return 1
    text = rp.predictions_jsonl(storage, args.run_id, args.connection)
    if args.out is None:
        sys.stdout.write(text)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8", newline="\n")
        print(f"{text.count(chr(10))} 筆預測 → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
