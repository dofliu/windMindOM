"""把讀值轉成 PLC 資料型別能表示的值（WMOM-20261125-03-c）。

Live 讀值有兩個來源：SQLite 的 ``turbine_data``（整包 SCADA 值存成 JSON，float64）與每日 Parquet 歸檔
（照 PLC 資料型別存）。兩邊都經過這裡的同一套轉換，所以不論一筆讀值在哪一層，給出去的值相同：

- ``REAL32``：取 float32；超出 float32 範圍（變成無限大）的當成缺值。
- ``SINT16`` / ``UINT16``：四捨六入五成雙；超出型別範圍的當成缺值。
- ``BOOL``：非零為 1。
- 不在 SCADA 註冊表裡的 tag：缺值（歸檔沒有這個欄位）。

缺值一律是 NaN。情境資料包的 raw Parquet 用同樣的型別（``scenario_pack._to_arrow``），差別只在那邊遇到
超出範圍的整數會報錯（出題端要處理），這裡當成缺值（例行工作不能被一筆壞值卡住）。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Dict, Sequence, Tuple

import numpy as np

from simulator.physics.scada_registry import SCADA_REGISTRY

_INT_RANGES: Dict[str, Tuple[float, float]] = {
    "SINT16": (float(np.iinfo(np.int16).min), float(np.iinfo(np.int16).max)),
    "UINT16": (float(np.iinfo(np.uint16).min), float(np.iinfo(np.uint16).max)),
}


def typed_column(values: np.ndarray, data_type: str) -> np.ndarray:
    """同一個 tag 的一串值 → PLC 資料型別能表示的值（float64 陣列，NaN＝缺值）。

    Args:
        values: 數值（NaN＝缺值）。
        data_type: SCADA 註冊表的資料型別（``REAL32`` / ``SINT16`` / ``UINT16`` / ``BOOL``）。

    Returns:
        轉換後的數值（新的陣列）。

    Raises:
        ValueError: 不認得的資料型別。
    """
    out = np.asarray(values, dtype=np.float64).copy()
    if data_type == "REAL32":
        with np.errstate(over="ignore"):
            out = out.astype(np.float32).astype(np.float64)
        out[np.isinf(out)] = np.nan
        return out
    if data_type == "BOOL":
        return np.where(np.isnan(out), np.nan, (out != 0.0).astype(np.float64))
    if data_type in _INT_RANGES:
        low, high = _INT_RANGES[data_type]
        out = np.rint(out)
        out[(out < low) | (out > high)] = np.nan
        return out
    raise ValueError(f"不認得的 PLC 資料型別：{data_type}")


@lru_cache(maxsize=16)
def _row_plan(tag_ids: Tuple[str, ...]) -> Tuple[Tuple[str, np.ndarray], ...]:
    """一列讀值裡，每種資料型別佔哪些位置；不在註冊表裡的 tag 歸在 ``""``。"""
    kinds = {tag.id: tag.data_type for tag in SCADA_REGISTRY.all_tags}
    groups: Dict[str, list] = {}
    for position, tag_id in enumerate(tag_ids):
        groups.setdefault(kinds.get(tag_id, ""), []).append(position)
    return tuple((kind, np.array(positions, dtype=np.intp)) for kind, positions in groups.items())


def plc_typed(values: np.ndarray, tag_ids: Sequence[str]) -> np.ndarray:
    """一列讀值（依 ``tag_ids`` 順序）→ PLC 資料型別能表示的值（float64 陣列，NaN＝缺值）。

    Args:
        values: 依 ``tag_ids`` 順序的數值。
        tag_ids: tag id。

    Returns:
        轉換後的數值（新的陣列）。
    """
    out = np.asarray(values, dtype=np.float64).copy()
    for kind, positions in _row_plan(tuple(tag_ids)):
        out[positions] = typed_column(out[positions], kind) if kind else np.nan
    return out
