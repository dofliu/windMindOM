"""Z72 真實 PLC tag 名稱清單（WMOM-20261021-05，EPIC-DS Phase 3a）。

資料來源是 `shared/data/z72_plc_tags.json`，由 `tools/build_z72_plc_tags.py` 從 PLC / OPC tag
清單 xlsx 的全部 sheet 擷取。用途：判定模擬器的 SCADA tag 是真實 Bachmann tag 還是依命名規則
自創——情境資料包的 tag 字典據此標 `source: bachmann_real | synthetic`（設計文件 §4 原則 3）。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import FrozenSet

PLC_TAGS_PATH = Path(__file__).resolve().parent / "data" / "z72_plc_tags.json"


@lru_cache(maxsize=1)
def real_plc_tags() -> FrozenSet[str]:
    """真實 Z72 PLC tag 名稱（不含 `WMET.` 這類 OPC 分組前綴）。

    Returns:
        tag 名稱集合，例 `Z72PLC__UI_Loc_WTUR_Analogue_TotPwrAt`。
    """
    raw = json.loads(PLC_TAGS_PATH.read_text(encoding="utf-8"))
    return frozenset(entry["name"] for entry in raw["tags"])


def is_real_plc_tag(name: str) -> bool:
    """tag 名稱是否出現在真實 Z72 PLC tag 清單。

    Args:
        name: PLC tag 名稱；可帶 OPC 分組前綴（`WMET.Z72PLC__...`），會先去掉。

    Returns:
        真實存在時為 True。
    """
    return name.split(".", 1)[-1] in real_plc_tags()
