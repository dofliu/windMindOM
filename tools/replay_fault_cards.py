"""故障出勤卡的離線重播與自動評分 CLI（WMOM-20261127-08，出發前助理企劃的階段 A）。

拿盲測版資料包與標準答案重播：每次跳機產生一張故障出勤卡（和即時風場同一個 ``build_fault_card``），用標準
答案評分；可以加資料條件（缺測、讀值晚到、重複、只有 10 分鐘統計）。

範例：
  # 學生 starter kit 的 7 個範例資料包、全部資料條件
  python tools/replay_fault_cards.py

  # 指定資料包與答案目錄、只跑原始資料，報告寫到檔案
  python tools/replay_fault_cards.py --packs packs/ --answers answers/ --modes raw --markdown report.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
MONITORING_ROOT = REPO_ROOT / "modules" / "monitoring"
for _path in (REPO_ROOT, MONITORING_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from server.briefing_replay import MODES, markdown_report, replay_all  # noqa: E402

KIT = REPO_ROOT / "examples" / "rag_starter_kit"


def main(argv: Optional[List[str]] = None) -> int:
    """命令列進入點。"""
    parser = argparse.ArgumentParser(description="故障出勤卡的離線重播與自動評分")
    parser.add_argument("--packs", type=Path, default=KIT / "packs", help="盲測版資料包的上層目錄")
    parser.add_argument("--answers", type=Path, default=KIT / "answers",
                        help="標準答案目錄（<pack_id>.ground_truth.json）")
    parser.add_argument("--modes", default=",".join(MODES), help=f"資料條件，逗號分隔（{', '.join(MODES)}）")
    parser.add_argument("--json", type=Path, help="逐筆結果寫成 JSON")
    parser.add_argument("--markdown", type=Path, help="報告寫成 Markdown；不給就印出來")
    args = parser.parse_args(argv)
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    unknown = sorted(set(modes) - set(MODES))
    if unknown:
        parser.error(f"不認得的資料條件：{unknown}")
    result = replay_all(args.packs, args.answers, modes)
    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    report = markdown_report(result)
    if args.markdown:
        args.markdown.write_text(report, encoding="utf-8")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
