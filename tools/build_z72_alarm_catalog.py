"""Z72 真實警報目錄建置 CLI（WMOM-20261021-02，EPIC-DS Phase 1a）。

把兩份真實來源合併成 `shared/data/z72_alarm_catalog.json`，作為模擬器警報碼的
唯一 source of truth（DEC-20261021-01）：

1. PLC / OPC tag 清單 `docs/1040610-Z72_PLC_OPC_TAG_1040510.xlsx` 的「警告訊息列表」
   sheet（314 筆）——PLC 實際送出的 code、等級（A/T1/T2/I）、顯示文字、對應的
   `Z72PLC__ActiveAlarm` / `ActiveTrip1` / `ActiveTrip2` tag。只採 A-D 欄；E-H 欄是
   另一份錯位的對照清單，不使用。
2. 使用手冊 `docs/__Z72UserManual.pdf` Appendix C「List of events」（p.104-130，
   307 筆）——原因（meaning / possible causes）、處置（test and rectification）、
   每小時最大重啟次數，以及所在頁碼。

合併規則：code / level / text / plc_tag 以 xlsx 為準（PLC 實際送出的內容）；手冊
補上 cause / rectification / max_per_hour / manual_page；兩者等級不一致時另記
`manual_level`，文字不一致時另記 `manual_text`，供人工檢視。

Build-time 才需要 `openpyxl` 與 `pdfplumber`（不在 runtime requirements）；
runtime 只讀產出的 JSON（見 `shared/alarm_codes.py`）。

Usage:
    python tools/build_z72_alarm_catalog.py
    python tools/build_z72_alarm_catalog.py --check   # 只比對，不寫檔；有差異 exit 1
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, TypedDict

REPO_ROOT = Path(__file__).resolve().parents[1]
XLSX_PATH = REPO_ROOT / "docs" / "1040610-Z72_PLC_OPC_TAG_1040510.xlsx"
PDF_PATH = REPO_ROOT / "docs" / "__Z72UserManual.pdf"
OUTPUT_PATH = REPO_ROOT / "shared" / "data" / "z72_alarm_catalog.json"

XLSX_SHEET = "警告訊息列表"
MANUAL_FIRST_PAGE = 104
MANUAL_LAST_PAGE = 130
SCHEMA_VERSION = 1
VALID_LEVELS = ("A", "T1", "T2", "I")


class XlsxEvent(TypedDict):
    """xlsx「警告訊息列表」一列。"""

    code: int
    level: str
    text: str
    plc_tag: Optional[str]


class ManualEvent(TypedDict):
    """手冊 Appendix C 一筆事件。"""

    code: int
    text: str
    cause: str
    rectification: str
    level: str
    max_per_hour: Optional[int]
    manual_page: int


def _clean(value: object) -> str:
    """把儲存格內容正規化成單行字串。"""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def read_xlsx_events(path: Path = XLSX_PATH) -> List[XlsxEvent]:
    """讀 xlsx「警告訊息列表」A-D 欄。

    Args:
        path: xlsx 路徑。

    Returns:
        依 code 排序的事件清單。
    """
    import openpyxl  # build-time only

    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb[XLSX_SHEET]
    events: List[XlsxEvent] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        tag, level, code, text = row[0], row[1], row[2], row[3]
        if code is None:
            continue
        tag_str = _clean(tag)
        events.append(
            XlsxEvent(
                code=int(code),
                level=_clean(level),
                text=_clean(text),
                # I 類事件在 xlsx 的 tag 欄是備註文字（「這幾個的TAG我還沒找到」），不是 tag
                plc_tag=tag_str if tag_str.startswith("Z72PLC__") else None,
            )
        )
    return sorted(events, key=lambda e: e["code"])


def _manual_row_cells(row: List[Optional[str]]) -> Optional[List[str]]:
    """把 pdfplumber 表格列正規化成 6 欄 [id, message, meaning, rect, level, max]。

    p.104 的表格是 14 欄寬版面（含空欄），其餘頁面是 6 欄。
    """
    cells = [_clean(c) for c in row]
    if len(cells) == 6:
        return cells
    if len(cells) == 14:
        return [cells[i] for i in (0, 3, 4, 7, 10, 11)]
    return None


def read_manual_events(path: Path = PDF_PATH) -> List[ManualEvent]:
    """解析手冊 Appendix C 表格。

    跨頁 / 跨列的續行（第一欄空白）併回上一筆事件對應欄位。

    Args:
        path: 手冊 PDF 路徑。

    Returns:
        依 code 排序的事件清單。
    """
    import pdfplumber  # build-time only

    events: List[ManualEvent] = []
    with pdfplumber.open(path) as pdf:
        for page_no in range(MANUAL_FIRST_PAGE, MANUAL_LAST_PAGE + 1):
            page = pdf.pages[page_no - 1]
            for table in page.extract_tables():
                for raw in table:
                    cells = _manual_row_cells(raw)
                    if cells is None:
                        continue
                    ev_id, message, meaning, rect, level, max_hr = cells
                    if re.fullmatch(r"\d{3}", ev_id):
                        events.append(
                            ManualEvent(
                                code=int(ev_id),
                                text=message,
                                cause=meaning,
                                rectification=rect,
                                level=level,
                                max_per_hour=int(max_hr) if max_hr.isdigit() else None,
                                manual_page=page_no,
                            )
                        )
                    elif not ev_id and events and not level:
                        # 續行：只補文字欄（表頭列也會落到這裡，但表頭只出現在第一筆之前）
                        last = events[-1]
                        if message:
                            last["text"] = f"{last['text']} {message}".strip()
                        if meaning:
                            last["cause"] = f"{last['cause']} {meaning}".strip()
                        if rect:
                            last["rectification"] = f"{last['rectification']} {rect}".strip()
    return sorted(events, key=lambda e: e["code"])


def _same_text(a: str, b: str) -> bool:
    """比對兩段文字是否只差大小寫 / 空白 / 標點。"""
    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s.lower())

    return norm(a) == norm(b)


def build_catalog(xlsx_events: List[XlsxEvent], manual_events: List[ManualEvent]) -> Dict[str, object]:
    """合併兩份來源成目錄 dict。

    Args:
        xlsx_events: xlsx 事件。
        manual_events: 手冊事件。

    Returns:
        可直接 `json.dump` 的目錄。
    """
    manual_by_code = {e["code"]: e for e in manual_events}
    entries: List[Dict[str, object]] = []
    for x in xlsx_events:
        m = manual_by_code.get(x["code"])
        entry: Dict[str, object] = {
            "code": x["code"],
            "level": x["level"],
            "text": x["text"],
            "plc_tag": x["plc_tag"],
            "cause": m["cause"] if m else None,
            "rectification": (m["rectification"] or None) if m else None,
            "max_per_hour": m["max_per_hour"] if m else None,
            "manual_page": m["manual_page"] if m else None,
        }
        if m and m["level"] and m["level"] != x["level"]:
            entry["manual_level"] = m["level"]
        if m and not _same_text(m["text"], x["text"]):
            entry["manual_text"] = m["text"]
        entries.append(entry)

    xlsx_codes = {x["code"] for x in xlsx_events}
    manual_only = sorted(c for c in manual_by_code if c not in xlsx_codes)
    return {
        "schema_version": SCHEMA_VERSION,
        "turbine_model": "Z72",
        "sources": {
            "event_list": f"docs/{XLSX_PATH.name}#{XLSX_SHEET}",
            "manual": f"docs/{PDF_PATH.name} Appendix C (p.{MANUAL_FIRST_PAGE}-{MANUAL_LAST_PAGE})",
        },
        "generated_by": "tools/build_z72_alarm_catalog.py",
        "manual_only_codes": manual_only,
        "events": entries,
    }


def _render(catalog: Dict[str, object]) -> str:
    return json.dumps(catalog, ensure_ascii=False, indent=1) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="只比對既有 JSON，不寫檔")
    args = parser.parse_args(argv)

    xlsx_events = read_xlsx_events()
    manual_events = read_manual_events()
    bad_levels = [x["code"] for x in xlsx_events if x["level"] not in VALID_LEVELS]
    if bad_levels:
        print(f"[ERROR] xlsx 有未知等級的 code：{bad_levels}", file=sys.stderr)
        return 1

    catalog = build_catalog(xlsx_events, manual_events)
    rendered = _render(catalog)
    events = catalog["events"]
    assert isinstance(events, list)
    with_manual = sum(1 for e in events if e["manual_page"] is not None)
    level_diff = [e["code"] for e in events if "manual_level" in e]
    print(f"xlsx {len(xlsx_events)} 筆、手冊 {len(manual_events)} 筆；"
          f"目錄 {len(events)} 筆，其中 {with_manual} 筆有手冊條目")
    print(f"手冊獨有 code：{catalog['manual_only_codes']}")
    print(f"等級不一致（xlsx vs 手冊）：{level_diff}")

    if args.check:
        current = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        if current != rendered:
            print(f"[DIFF] {OUTPUT_PATH.relative_to(REPO_ROOT)} 與來源不一致，請重新產生", file=sys.stderr)
            return 1
        print("[OK] 目錄與來源一致")
        return 0

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    print(f"已寫入 {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
