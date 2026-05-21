"""shared.farm_registry_provider — 統一的 ``FarmRegistry`` lazy singleton + farm DB path resolver。

WMOM-20260509-F4 — 抽出原本散在 4 個 routers 各自重複的 lazy init pattern：

- ``modules/workflow/routers/inventory_router.py``
- ``modules/workflow/routers/material_request_router.py``
- ``modules/workflow/routers/approval_router.py``
- ``modules/cost/routers/cost_ledger_router.py``

由於 ``FarmRegistry`` 來自 ``modules/monitoring``，但 ``shared/`` 不允許 import ``modules/``。
解法：lazy import — 第一次呼叫 ``get_farm_registry()`` 時才動態載入。Test 環境若沒 mount
monitoring，仍可走各 router 的 ``set_*_factory()`` 注入 mock，從不觸及這裡。

設計重點：
- module-level singleton（含 caching；同 process 內共用）
- ``reset_farm_registry()`` 讓 test fixture / `set_*_factory(None)` 清狀態
- ``resolve_farm_db_path(farm_id)`` 失敗時 raise ``HTTPException(404)``，沿用原 router 行為
"""

from __future__ import annotations

import threading
from typing import Any

from fastapi import HTTPException


_FARM_REGISTRY: Any = None
_LOCK = threading.Lock()


def get_farm_registry() -> Any:
    """取得共用 ``FarmRegistry`` instance；首呼叫 lazy import + init。

    回 ``Any`` 而非具體型別：``shared/`` 不該硬綁 ``modules/monitoring`` 型別
    （避免 import cycle / 違反「shared 不依賴 modules」原則）。
    """
    global _FARM_REGISTRY
    if _FARM_REGISTRY is not None:
        return _FARM_REGISTRY
    with _LOCK:
        if _FARM_REGISTRY is not None:
            return _FARM_REGISTRY
        try:
            from modules.monitoring.server.farm_registry import FarmRegistry  # type: ignore
        except ImportError as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    "FarmRegistry not available; "
                    "call set_*_factory() in the router to inject a mock"
                ),
            ) from exc
        _FARM_REGISTRY = FarmRegistry()
        return _FARM_REGISTRY


def resolve_farm_db_path(farm_id: str) -> str:
    """查 farm 對應 SQLite DB path；找不到 farm → 404。

    所有 4 個 routers 解析 farm DB path 時統一走這條，避免重複 lazy init 邏輯。
    """
    registry = get_farm_registry()
    db_path = registry.get_farm_db_path(farm_id)
    if db_path is None:
        raise HTTPException(status_code=404, detail=f"Farm not found: {farm_id}")
    return str(db_path)


def reset_farm_registry() -> None:
    """清掉 lazy singleton；test fixture / ``set_*_factory(None)`` 用。

    注意：清的是 process-wide singleton（所有 routers 共用）；多 router test fixture
    交替清狀態時不會互相干擾，第一次 ``resolve_farm_db_path()`` 會重新 init。
    """
    global _FARM_REGISTRY
    with _LOCK:
        _FARM_REGISTRY = None
