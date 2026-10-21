"""Z72 真實 PLC tag 清單建置 CLI（WMOM-20261021-05，EPIC-DS Phase 3a）。

從 PLC / OPC tag 清單 `docs/1040610-Z72_PLC_OPC_TAG_1040510.xlsx` 的全部 sheet 擷取所有
`Z72PLC__*` tag 名稱，寫成 `shared/data/z72_plc_tags.json`。情境資料包的 tag 字典以它判定
每個模擬 tag 是真實 Bachmann tag（`bachmann_real`）還是依命名規則自創（`synthetic`）——
設計文件 §4 原則 3「真實存在的 tag 一律用真名；自創 tag 標 synthetic」。

Build-time 才需要 `openpyxl`（不在 runtime requirements）；runtime 只讀產出的 JSON（見
`shared/plc_tags.py`）。

Usage:
    python tools/build_z72_plc_tags.py
    python tools/build_z72_plc_tags.py --check   # 只比對，不寫檔；有差異 exit 1
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
XLSX_PATH = REPO_ROOT / "docs" / "1040610-Z72_PLC_OPC_TAG_1040510.xlsx"
OUTPUT_PATH = REPO_ROOT / "shared" / "data" / "z72_plc_tags.json"

SCHEMA_VERSION = 1
# 陣列 tag（例 `Z72PLC__ActiveAlarm[0]`）連同索引一起收；分組前綴（`WMET.`）不在名稱內
_TAG_PATTERN = re.compile(r"Z72PLC__[A-Za-z0-9_\[\]]+")
# 版面 / 套件變動時的 sanity guard：解析結果明顯變少就中止
MIN_TAGS = 1500


def extract_tags(xlsx_path: Path) -> Dict[str, List[str]]:
    """擷取每個 sheet 出現的 `Z72PLC__*` tag 名稱。

    Args:
        xlsx_path: tag 清單 xlsx。

    Returns:
        tag 名稱 → 出現的 sheet 名稱（依 xlsx 順序）。
    """
    import openpyxl  # build-time 依賴

    found: Dict[str, List[str]] = {}
    workbook = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows(values_only=True):
            for value in row:
                if not isinstance(value, str):
                    continue
                for tag in _TAG_PATTERN.findall(value):
                    sheets = found.setdefault(tag, [])
                    if sheet.title not in sheets:
                        sheets.append(sheet.title)
    return found


def render(found: Dict[str, List[str]]) -> str:
    """組成 JSON 文字（tag 依名稱排序，輸出穩定）。

    Args:
        found: `extract_tags` 的結果。

    Returns:
        JSON 文字。
    """
    data = {
        "schema_version": SCHEMA_VERSION,
        "turbine_model": "Z72",
        "source": "docs/1040610-Z72_PLC_OPC_TAG_1040510.xlsx (all sheets)",
        "generated_by": "tools/build_z72_plc_tags.py",
        "tags": [{"name": name, "sheets": found[name]} for name in sorted(found)],
    }
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 進入點。

    Args:
        argv: 命令列參數（測試用）；None＝`sys.argv`。

    Returns:
        exit code。
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="只比對既有 JSON，不寫檔")
    args = parser.parse_args(argv)

    found = extract_tags(XLSX_PATH)
    if len(found) < MIN_TAGS:
        print(f"只擷取到 {len(found)} 個 tag（< {MIN_TAGS}），xlsx 版面可能變了，中止", file=sys.stderr)
        return 2
    rendered = render(found)
    if args.check:
        current = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        if current != rendered:
            print(f"{OUTPUT_PATH} 與 xlsx 不一致，請重跑 tools/build_z72_plc_tags.py", file=sys.stderr)
            return 1
        print(f"{OUTPUT_PATH} 一致（{len(found)} 個 tag）")
        return 0
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    print(f"寫出 {OUTPUT_PATH}（{len(found)} 個 tag）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
