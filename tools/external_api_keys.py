"""對外唯讀 API 的金鑰管理 CLI（WMOM-20261125-02，EPIC-SF 第 1 項）。

直接操作 auth DB（不必登入），與 admin 端點 ``/api/auth/api-keys`` 相同。請在伺服器那台機器、用與伺服器相同的
``WMOM_AUTH_DB_URL`` 執行（沒設＝目前目錄的 ``wmom_auth.db``，所以也要在伺服器的啟動目錄下執行）。伺服器不必
重啟：新金鑰立刻可用，撤銷立刻失效。

範例：
  # 發一把金鑰給 RAG 運維助理——金鑰只會印出這一次
  python tools/external_api_keys.py create rag-assistant

  # 列出金鑰（不含金鑰本身）、撤銷
  python tools/external_api_keys.py list
  python tools/external_api_keys.py revoke <id>

外部系統在每個請求帶 ``X-API-Key: <金鑰>``，只能讀 ``/api/ext/v1``（見 docs/integration/external_api_v1.md）。
盲測要成立，伺服器要開 ``WMOM_AUTH_ENFORCE=true``——否則其他端點本來就不用登入。
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.auth import api_keys as ak  # noqa: E402
from modules.auth.dependencies import is_auth_enforced  # noqa: E402

CLI_ACTOR = "cli"


def _print_key(key: ak.ApiKey) -> None:
    state = f"已撤銷 {key.revoked_at}" if key.revoked_at else "有效"
    print(f"  {key.id}  {key.prefix}…  {state:<8}  建立 {key.created_at}  "
          f"最近使用 {key.last_used_at or '—'}  （{key.name}）")


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 進入點。

    Args:
        argv: 命令列參數（測試用）；None＝``sys.argv``。

    Returns:
        exit code（0 成功、1 金鑰不存在、2 參數錯誤）。
    """
    parser = argparse.ArgumentParser(description="對外唯讀 API（/api/ext/v1）的金鑰管理")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="發一把金鑰（只印出這一次）")
    create.add_argument("name", help="用途說明，例 rag-assistant")
    sub.add_parser("list", help="列出金鑰（不含金鑰本身）")
    revoke = sub.add_parser("revoke", help="撤銷金鑰（立刻失效）")
    revoke.add_argument("key_id", help="金鑰 ID（list 的第一欄）")
    args = parser.parse_args(argv)

    store = ak.get_api_key_store()
    if args.command == "create":
        try:
            record, key = ak.issue_api_key(store, args.name, created_by=CLI_ACTOR)
        except ValueError as exc:
            print(f"錯誤：{exc}", file=sys.stderr)
            return 2
        print(f"已建立金鑰 {record.id}（{record.name}）。金鑰只顯示這一次，請現在存好：")
        print(key)
        if not is_auth_enforced():
            print("提醒：目前環境沒有開 WMOM_AUTH_ENFORCE=true。伺服器若也沒開，其他端點不用登入就能讀，"
                  "拿到金鑰的外部系統等於看得到故障注入資訊。", file=sys.stderr)
        return 0
    if args.command == "list":
        keys = store.list_keys()
        if not keys:
            print("沒有金鑰。")
        for item in keys:
            _print_key(item)
        return 0
    revoked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not store.revoke(args.key_id, revoked_at):
        print(f"錯誤：找不到金鑰 {args.key_id}", file=sys.stderr)
        return 1
    print(f"已撤銷金鑰 {args.key_id}。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
