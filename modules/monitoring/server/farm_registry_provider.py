"""FarmRegistry lazy singleton provider — 4 個 router 共用（WMOM-20260509-F4）。

## 為什麼放在 monitoring/server/

`FarmRegistry` class 本身在本目錄（`farm_registry.py`），本 provider 就是它的
HTTP-layer wrapper（lazy init + 錯誤映射）。把 wrapper 跟 underlying class 同
package 放最自然；同時 satisfy `shared/__init__.py` 的約束（``shared/`` 不允許
import ``modules/``）— 本 helper 確實是 HTTP 層 application code（用
`fastapi.HTTPException`），不該住 ``shared/``。

## 為什麼存在

`inventory_router` / `material_request_router` / `approval_router` /
`cost_ledger_router` 4 個 router 都需要把 `farm_id` 解析為 SQLite DB 路徑：

```python
from modules.monitoring.server.farm_registry import FarmRegistry
_FARM_REGISTRY = FarmRegistry()
db_path = _FARM_REGISTRY.get_farm_db_path(farm_id)
```

原本各 router 各自維持一份 module-level `_FARM_REGISTRY` lazy singleton +
一份 `_resolve_farm_db_path()` helper，4 份重複。本 module 抽成單一
source-of-truth：

- 同 process 共享同一個 `FarmRegistry` 實例（避免每個 router 各自開一個）
- 統一 lazy init + ImportError / farm-not-found 錯誤訊息
- 測試 hook：`reset_farm_registry()` 給 `set_*_factory(None)` 流程清 state 用

## ⚠ 跨 router 共用副作用（must-fix #3）

`reset_farm_registry()` 清的是 **4 個 router 共用** 的 module-level singleton。
任何一個 router 的 `set_*_factory(None)` 走進這條 path 都會清掉 shared state，
其他 router 下一次 call 會 lazy 重 init。語義上等價（singleton 是 idempotent
建立），但測試環境若有並行（pytest-xdist）需注意。各 router 的
`set_*_factory()` docstring 都標註這個共用副作用。

## 為什麼不用 dependency injection？

4 個 router 都採 FastAPI module-level state 設計（非 DI）；全改 DI 涵蓋面太大，
不在本 follow-up scope。本 module 維持「同 process 同 singleton」語義，但消滅
4 份重複 code。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from fastapi import HTTPException

if TYPE_CHECKING:  # pragma: no cover
    from modules.monitoring.server.farm_registry import FarmRegistry


# Module-level lazy singleton — 同 process 內 4 個 router 共用。
_farm_registry: Optional["FarmRegistry"] = None


def resolve_farm_db_path(farm_id: str) -> str:
    """把 ``farm_id`` 解析為 SQLite DB 檔案絕對路徑。

    第一次呼叫時 lazy import + 初始化 ``FarmRegistry``；後續 call 共用同一個實例。

    404 判斷：``FarmRegistry.get_farm_db_path()`` 永遠回 Path（不回 None），
    所以靠 ``get_farm(farm_id) is None`` 判斷 farm 是否真存在 — 否則任意 farm_id
    都會被建一個空 DB（review should-fix #1）。

    Raises:
        HTTPException(500): FarmRegistry import 失敗（monitoring module 未就位）。
        HTTPException(404): ``farm_id`` 在 registry 內無對應 FarmConfig。
    """
    global _farm_registry
    if _farm_registry is None:
        try:
            from modules.monitoring.server.farm_registry import (  # type: ignore
                FarmRegistry,
            )
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail=(
                    "FarmRegistry not available; "
                    "call set_*_factory() to inject a repository for tests"
                ),
            )
        _farm_registry = FarmRegistry()
    if _farm_registry.get_farm(farm_id) is None:
        raise HTTPException(status_code=404, detail=f"Farm not found: {farm_id}")
    return str(_farm_registry.get_farm_db_path(farm_id))


def reset_farm_registry() -> None:
    """清掉 lazy singleton — 給測試 / `set_*_factory(None)` 流程下次 lazy 重 init 用。

    ⚠ **全域副作用**：此 singleton 由 4 個 router（inventory / material_request /
    approval / cost_ledger）共用，本函式會同時清掉其他 router 後續看到的 registry
    實例。Production code 一般不需要呼叫；test fixture 在 setup / teardown 用，
    避免跨 test 殘留 registry instance 指向舊 DB 路徑。
    """
    global _farm_registry
    _farm_registry = None
