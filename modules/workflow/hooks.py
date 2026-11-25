"""工單事件的掛鉤（WMOM-20261125-04，運維閉環）。

workflow 模組不 import 其他模組；要在工單建立或狀態改變時做事的一方（monitoring 的運維閉環：開工進入
維修模式、完工修復機組；之後的出發前準備卡）在這裡登記一個 listener。

- listener 在工單的變更**已經寫進資料庫之後**才被呼叫，所以它失敗不會讓工單的操作失敗或回滾；例外只記
  log。
- listener 在呼叫 repository 的那條執行緒上同步執行（API 的請求、或即時模擬的執行緒），要自己注意執行緒
  安全，而且不要做很久。
- 登記是 process 層級的：每一座風場的工單都會通知，listener 自己用 ``work_order.farm_id`` 過濾。
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, List, Optional

from modules.workflow.domain.work_order import WorkOrder, WorkOrderStatus

_logger = logging.getLogger(__name__)

# (工單（變更後）, 動作, 變更前的狀態)。動作是 ``create`` 或狀態機的 action 名稱
# （``dispatch`` / ``start_work`` / ``update_progress`` / ``finish`` / ``approve_all`` / ``reject`` /
# ``cancel`` / ``reopen``）；``create`` 時變更前的狀態為 None。
WorkOrderListener = Callable[[WorkOrder, str, Optional[WorkOrderStatus]], None]

_listeners: List[WorkOrderListener] = []
_lock = threading.Lock()


def add_work_order_listener(listener: WorkOrderListener) -> None:
    """登記一個 listener（同一個函式重複登記只算一次）。

    Args:
        listener: 工單建立或狀態改變之後要呼叫的函式。
    """
    with _lock:
        if listener not in _listeners:
            _listeners.append(listener)


def remove_work_order_listener(listener: WorkOrderListener) -> None:
    """取消登記；沒登記過就不做事。

    Args:
        listener: 之前登記的函式。
    """
    with _lock:
        if listener in _listeners:
            _listeners.remove(listener)


def clear_work_order_listeners() -> None:
    """清掉全部 listener（測試用）。"""
    with _lock:
        _listeners.clear()


def notify_work_order(work_order: WorkOrder, action: str, from_status: Optional[WorkOrderStatus]) -> None:
    """通知全部 listener。個別 listener 的例外只記 log，不往上丟。

    Args:
        work_order: 變更後的工單。
        action: ``create`` 或狀態機的 action 名稱。
        from_status: 變更前的狀態；``create`` 時為 None。
    """
    with _lock:
        listeners = list(_listeners)
    for listener in listeners:
        try:
            listener(work_order, action, from_status)
        except Exception:  # noqa: BLE001  工單已經寫進資料庫：listener 出錯不能讓操作看起來失敗
            _logger.exception("work order listener failed (work_order=%s, action=%s)", work_order.id, action)
