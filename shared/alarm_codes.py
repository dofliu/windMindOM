"""Z72 真實警報目錄查詢 API（WMOM-20261021-02，EPIC-DS Phase 1a）。

資料來源是 `shared/data/z72_alarm_catalog.json`，由
`tools/build_z72_alarm_catalog.py` 從 PLC/OPC tag 清單 xlsx（314 筆）與使用手冊
Appendix C 合併產生；手冊獨有的碼（A039 Auto restart blocked）也收錄，JSON 標 ``manual_only``。
這是模擬器警報碼的唯一 source of truth（DEC-20261021-01）：
故障情境、資料包匯出、串流與 OPC UA server 用到的警報碼、等級、文字都應從這裡查。

等級（level）：
    A  — 警報，需要注意但不停機
    T1 — 由正常變槳伺服系統停機的跳機
    T2 — 由緊急變槳系統停機的跳機
    I  — 狀態資訊（啟動 / 停止 / 解纜等）
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Literal, Optional, Tuple, cast

AlarmLevel = Literal["A", "T1", "T2", "I"]
VALID_LEVELS: Tuple[AlarmLevel, ...] = ("A", "T1", "T2", "I")

CATALOG_PATH = Path(__file__).resolve().parent / "data" / "z72_alarm_catalog.json"
TRIP_LEVELS: Tuple[AlarmLevel, ...] = ("T1", "T2")


@dataclass(frozen=True)
class AlarmDef:
    """單一 Z72 事件定義。

    Attributes:
        code: PLC 事件碼（1-656）。
        level: 事件等級（A / T1 / T2 / I）。
        text: PLC 顯示文字（xlsx 原文）。
        plc_tag: 送出此事件的 PLC tag（`Z72PLC__ActiveAlarm` / `ActiveTrip1` /
            `ActiveTrip2`）；I 類事件為 None。
        cause: 手冊 Appendix C「Meaning of the message – possible causes」。
        rectification: 手冊「Test and rectification」處置提示。
        max_per_hour: 每小時允許的同類跳機自動重啟次數；A / I 類為 None。
        manual_page: 手冊頁碼；手冊未收錄時為 None。
    """

    code: int
    level: AlarmLevel
    text: str
    plc_tag: Optional[str]
    cause: Optional[str]
    rectification: Optional[str]
    max_per_hour: Optional[int]
    manual_page: Optional[int]

    @property
    def is_trip(self) -> bool:
        """是否為跳機事件（T1 / T2）。"""
        return self.level in TRIP_LEVELS

    @property
    def event_id(self) -> str:
        """HMI 慣用的事件 ID，例如 `A_262`、`T_240`、`I_002`。"""
        prefix = "T" if self.is_trip else self.level
        return f"{prefix}_{self.code:03d}"


@lru_cache(maxsize=1)
def _load_catalog() -> Dict[int, AlarmDef]:
    """讀取並快取目錄 JSON。

    Returns:
        事件碼 → `AlarmDef` 對照表。

    Raises:
        ValueError: JSON 內有未知等級（目錄檔被手動改壞時及早失敗）。
    """
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    catalog: Dict[int, AlarmDef] = {}
    for e in raw["events"]:
        if e["level"] not in VALID_LEVELS:
            raise ValueError(f"Z72 警報目錄事件碼 {e['code']} 的等級 {e['level']!r} 不合法")
        catalog[int(e["code"])] = AlarmDef(
            code=int(e["code"]),
            level=cast(AlarmLevel, e["level"]),
            text=e["text"],
            plc_tag=e["plc_tag"],
            cause=e["cause"],
            rectification=e["rectification"],
            max_per_hour=e["max_per_hour"],
            manual_page=e["manual_page"],
        )
    return catalog


def find_alarm(code: int) -> Optional[AlarmDef]:
    """依事件碼查詢；查無時回傳 None。

    Args:
        code: Z72 事件碼。

    Returns:
        對應的 `AlarmDef`，或 None。
    """
    return _load_catalog().get(code)


def get_alarm(code: int) -> AlarmDef:
    """依事件碼查詢；查無時丟 KeyError。

    Args:
        code: Z72 事件碼。

    Returns:
        對應的 `AlarmDef`。

    Raises:
        KeyError: 目錄中沒有此事件碼。
    """
    alarm = find_alarm(code)
    if alarm is None:
        raise KeyError(f"Z72 警報目錄沒有事件碼 {code}")
    return alarm


def is_known_code(code: int) -> bool:
    """事件碼是否存在於 Z72 目錄。

    Args:
        code: Z72 事件碼。

    Returns:
        存在時為 True。
    """
    return code in _load_catalog()


def all_alarms() -> Tuple[AlarmDef, ...]:
    """依事件碼排序回傳全部事件定義。

    Returns:
        全部 `AlarmDef`，依事件碼遞增排序。
    """
    catalog = _load_catalog()
    return tuple(catalog[c] for c in sorted(catalog))
