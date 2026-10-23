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
`manual_level`，文字不一致時另記 `manual_text`，供人工檢視。手冊有、xlsx 沒有的碼（A039 Auto
restart blocked，自動重啟被封鎖時 PLC 送出）也收進目錄：欄位取手冊、`plc_tag` 依等級推定，並標
`manual_only`（WMOM-20261022-02）。

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
# 等級 → 送出的 PLC tag（xlsx 的對應；手冊獨有的碼依此推定）
_PLC_TAG_BY_LEVEL: Dict[str, str] = {
    "A": "Z72PLC__ActiveAlarm",
    "T1": "Z72PLC__ActiveTrip1",
    "T2": "Z72PLC__ActiveTrip2",
}
# 版面 / 套件變動時的 sanity guard：解析結果明顯變少就中止，不要寫出一份手冊欄位全空的 JSON
MIN_XLSX_EVENTS = 300
MIN_MANUAL_EVENTS = 300


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


class CatalogBuildError(RuntimeError):
    """來源解析結果不合理（筆數過少、重複事件碼、未知等級）。"""


def _clean(value: object) -> str:
    """把儲存格內容正規化成單行字串，並修掉 PDF 換行造成的斷字（`re- configure`）。"""
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return re.sub(r"(?<=[a-z])- (?=[a-z])", "-", text)


def _check_unique(codes: List[int], source: str) -> None:
    """同一來源內事件碼不可重複。"""
    dups = sorted(c for c in set(codes) if codes.count(c) > 1)
    if dups:
        raise CatalogBuildError(f"{source} 有重複事件碼：{dups}")


def read_xlsx_events(path: Path = XLSX_PATH) -> List[XlsxEvent]:
    """讀 xlsx「警告訊息列表」A-D 欄。

    Args:
        path: xlsx 路徑。

    Returns:
        依 code 排序的事件清單。
    """
    import openpyxl  # build-time only

    wb = openpyxl.load_workbook(path, read_only=True)
    events: List[XlsxEvent] = []
    try:
        ws = wb[XLSX_SHEET]
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
    finally:
        wb.close()  # read_only 模式不 close 會在 Windows 鎖住 xlsx
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

    Raises:
        CatalogBuildError: 出現無法辨識的表格列（欄數不是 6 / 14，或不是事件列也不是續行）。
    """
    import pdfplumber  # build-time only

    events: List[ManualEvent] = []
    unrecognized: List[str] = []
    with pdfplumber.open(path) as pdf:
        for page_no in range(MANUAL_FIRST_PAGE, MANUAL_LAST_PAGE + 1):
            page = pdf.pages[page_no - 1]
            for table in page.extract_tables():
                for raw in table:
                    cells = _manual_row_cells(raw)
                    if cells is None:
                        unrecognized.append(f"p.{page_no} {len(raw)} 欄：{raw}")
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
                    elif not ev_id and not events:
                        continue  # p.104 第一筆事件之前的表頭列
                    elif not ev_id and not level:
                        # 續行：只補文字欄
                        last = events[-1]
                        if message:
                            last["text"] = f"{last['text']} {message}".strip()
                        if meaning:
                            last["cause"] = f"{last['cause']} {meaning}".strip()
                        if rect:
                            last["rectification"] = f"{last['rectification']} {rect}".strip()
                    else:
                        unrecognized.append(f"p.{page_no}：{cells}")
    if unrecognized:
        raise CatalogBuildError("手冊 Appendix C 有無法辨識的表格列：\n" + "\n".join(unrecognized))
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
            "cause": (m["cause"] or None) if m else None,
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
    # 手冊獨有的碼也收進目錄（WMOM-20261022-02：自動重啟被封鎖時真實 PLC 送 A039，xlsx 沒列）。
    # code / level / text 取手冊原文，plc_tag 依等級推定，並標 manual_only 供人工檢視
    for code in manual_only:
        m = manual_by_code[code]
        level = m["level"]
        if level not in VALID_LEVELS:
            raise CatalogBuildError(f"手冊獨有的 code {code} 等級 {level!r} 不合法")
        entries.append({
            "code": code,
            "level": level,
            "text": m["text"],
            "plc_tag": _PLC_TAG_BY_LEVEL.get(level),
            "cause": m["cause"] or None,
            "rectification": m["rectification"] or None,
            "max_per_hour": m["max_per_hour"],
            "manual_page": m["manual_page"],
            "manual_only": True,
        })
    entries.sort(key=lambda e: int(str(e["code"])))
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


def render_catalog(catalog: Dict[str, object]) -> str:
    """把目錄 dict 序列化成 commit 用的 JSON 文字。"""
    return json.dumps(catalog, ensure_ascii=False, indent=1) + "\n"


def validate_sources(xlsx_events: List[XlsxEvent], manual_events: List[ManualEvent]) -> None:
    """來源 sanity guard。

    Args:
        xlsx_events: xlsx 事件。
        manual_events: 手冊事件。

    Raises:
        CatalogBuildError: 筆數過少、事件碼重複或出現未知等級。
    """
    if len(xlsx_events) < MIN_XLSX_EVENTS:
        raise CatalogBuildError(f"xlsx 只解析出 {len(xlsx_events)} 筆（預期 ≥ {MIN_XLSX_EVENTS}）")
    if len(manual_events) < MIN_MANUAL_EVENTS:
        raise CatalogBuildError(f"手冊只解析出 {len(manual_events)} 筆（預期 ≥ {MIN_MANUAL_EVENTS}）")
    _check_unique([x["code"] for x in xlsx_events], "xlsx")
    _check_unique([m["code"] for m in manual_events], "手冊")
    bad_levels = [x["code"] for x in xlsx_events if x["level"] not in VALID_LEVELS]
    if bad_levels:
        raise CatalogBuildError(f"xlsx 有未知等級的 code：{bad_levels}")


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="只比對既有 JSON，不寫檔")
    args = parser.parse_args(argv)

    try:
        xlsx_events = read_xlsx_events()
        manual_events = read_manual_events()
        validate_sources(xlsx_events, manual_events)
    except CatalogBuildError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    catalog = build_catalog(xlsx_events, manual_events)
    rendered = render_catalog(catalog)
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
