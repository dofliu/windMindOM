"""情境資料包匯出 CLI（WMOM-20261021-05，EPIC-DS Phase 3a ① 檔案）。

從風場 DB 把一個命名情境匯出成資料包目錄（設計文件 §5.1）。預設是盲測版（不含答案），給受測端；
`--ground-truth` 另附 `ground_truth.json`，只給評分端。

範例：
  # 列出 DB 裡可匯出的情境
  python tools/export_scenario_pack.py "modules/monitoring/data/farms/<farm>/wind_farm.db" --list

  # 盲測版資料包（目錄）
  python tools/export_scenario_pack.py "<db>" 12 --out packs/

  # 評分端版，另壓成 zip
  python tools/export_scenario_pack.py "<db>" 12 --out packs/ --ground-truth --zip
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

from server.scenario_pack import (  # noqa: E402
    ScenarioPackError,
    export_scenario_pack,
    pack_id_for,
    write_pack_zip,
)
from server.storage import Storage  # noqa: E402


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 進入點。

    Args:
        argv: 命令列參數（測試用）；None＝`sys.argv`。

    Returns:
        exit code（0 成功、1 情境不能匯出、2 參數錯誤）。
    """
    parser = argparse.ArgumentParser(description="匯出情境資料包（EPIC-DS §5.1）")
    parser.add_argument("db", type=Path, help="風場 SQLite DB 路徑")
    parser.add_argument("scenario_id", type=int, nargs="?", help="情境 session id")
    parser.add_argument("--out", type=Path, default=Path("."), help="輸出目錄（資料包放在其下的 <pack_id>/）")
    parser.add_argument("--ground-truth", action="store_true", help="附 ground_truth.json（評分端版）")
    parser.add_argument("--zip", action="store_true", help="另壓成 <pack_id>.zip")
    parser.add_argument("--list", action="store_true", help="列出 DB 裡的情境")
    args = parser.parse_args(argv)

    if not args.db.exists():
        print(f"找不到 DB：{args.db}", file=sys.stderr)
        return 2
    # 匯出只讀：不在開檔時順便改寫舊版時間戳（WMOM-20261021-03-c 的一次性轉換留給伺服器做）
    storage = Storage(db_path=str(args.db), migrate_timestamps=False)
    if args.list:
        for scenario in storage.list_scenarios(limit=1000):
            config = scenario.get("config") or {}
            exportable = config.get("status") == "ok" and config.get("events_session_isolated") is True
            print(f"{scenario['id']:>6}  {'可匯出' if exportable else '不可匯出'}  {config.get('name')!r}  "
                  f"{config.get('duration_hours')} h  {scenario.get('started_at')}")
        return 0
    if args.scenario_id is None:
        parser.error("需要 scenario_id（或用 --list 列出情境）")

    pack_id = pack_id_for(args.scenario_id)
    pack_dir = args.out / pack_id
    try:
        manifest = export_scenario_pack(storage, args.scenario_id, pack_dir,
                                        include_ground_truth=args.ground_truth)
    except ScenarioPackError as exc:
        print(f"無法匯出：{exc}", file=sys.stderr)
        return 1
    counts = manifest["counts"]
    print(f"資料包 {pack_dir}：raw {counts['raw_rows']} 列、10 分鐘統計 {counts['stats_rows']} 列"
          f"（殘缺窗 {counts['partial_windows']}）、事件 {counts['events']} 筆、"
          f"{'含' if args.ground_truth else '不含'}標準答案")
    if args.zip:
        zip_path = args.out / f"{pack_id}{'-full' if args.ground_truth else ''}.zip"
        write_pack_zip(pack_dir, zip_path, args.ground_truth)
        print(f"zip：{zip_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
