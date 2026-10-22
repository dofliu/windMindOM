"""批次生成（產生情境 / 測試計畫）的程序狀態（WMOM-20261022-01，DEC-20261022-05）。

批次在背景執行緒跑，不卡 event loop：WS 回放、OPC UA、查詢照常運作。代價是其他請求不再被「卡住的
event loop」自動排隊，所以：

- 同時只允許一個批次（``batch_slot``；第二個回 409）。
- 批次期間會改到模擬器的請求（切換來源 / 風場、風況 / 電網 / 模擬設定、控制指令、注入 / 清除故障、刪除情境）
  回 409（路由掛 ``reject_during_batch``）：否則會與批次同時 step / 改同一組物理模型。

佔位與釋放都在執行批次的那個執行緒裡做：請求被取消時，背景執行緒仍在跑，位子不會提早被放掉。
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator, Optional

from fastapi import HTTPException

_slot = threading.Lock()
_label: Optional[str] = None


def running() -> Optional[str]:
    """正在跑的批次（``"產生情境"`` / ``"執行測試計畫"``）；沒有回 None。"""
    return _label


@contextmanager
def batch_slot(label: str) -> Iterator[None]:
    """佔住唯一的批次位子（在執行批次的執行緒裡用）。

    Args:
        label: 批次名稱（給 409 的說明用）。

    Raises:
        HTTPException: 409，已有批次在跑。
    """
    global _label
    if not _slot.acquire(blocking=False):
        raise HTTPException(409, f"正在{_label or '執行批次'}：同時只能有一個批次，結束後再試")
    _label = label
    try:
        yield
    finally:
        _label = None
        _slot.release()


def reject_during_batch() -> None:
    """FastAPI dependency：批次期間拒絕會改到模擬器的請求。

    Raises:
        HTTPException: 409，批次進行中。
    """
    label = _label
    if label is not None:
        raise HTTPException(409, f"正在{label}：結束後再操作模擬器")
