"""Test for shared.farm_registry_provider — WMOM-20260509-F4 共用 lazy singleton。

驗證：
- ``get_farm_registry()`` lazy init（首呼叫才 import）+ cached（後續呼叫 same instance）
- ``resolve_farm_db_path()`` farm 不存在 → HTTPException(404)
- ``reset_farm_registry()`` 清狀態後下次重新 init

mock ``FarmRegistry`` 避免依賴 monitoring DB。
"""

from __future__ import annotations

import sys
import types
from typing import Any, Generator

import pytest
from fastapi import HTTPException

from shared import farm_registry_provider


class _FakeFarmRegistry:
    """Mock — 只 stub get_farm_db_path。"""

    init_calls: int = 0

    def __init__(self) -> None:
        type(self).init_calls += 1
        self._paths: dict[str, str] = {"changhua": "/tmp/changhua.db"}

    def get_farm_db_path(self, farm_id: str) -> str | None:
        return self._paths.get(farm_id)


@pytest.fixture(autouse=True)
def _patch_farm_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """每個 test 前後都重置 lazy singleton + 注入 fake FarmRegistry。

    F4-2（review fix）：加 yield + teardown reset — ``_FARM_REGISTRY`` 是 module-level
    全域變數，``monkeypatch`` 只還原 ``sys.modules``，不會清 ``_FARM_REGISTRY`` cache。
    若不在 teardown reset，最後一個 test 結束後 ``_FARM_REGISTRY`` 仍指向 ``_FakeFarmRegistry``
    instance，後續其他 test file 直接呼叫 ``get_farm_registry()`` 會跳過 init 拿到殘留。
    """
    farm_registry_provider.reset_farm_registry()
    _FakeFarmRegistry.init_calls = 0

    fake_module = types.ModuleType("modules.monitoring.server.farm_registry")
    fake_module.FarmRegistry = _FakeFarmRegistry  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "modules.monitoring.server.farm_registry", fake_module)
    yield
    farm_registry_provider.reset_farm_registry()


def test_get_farm_registry_lazy_init_only_once() -> None:
    """首次呼叫 init 一次；後續呼叫共享 cached instance。"""
    first = farm_registry_provider.get_farm_registry()
    second = farm_registry_provider.get_farm_registry()
    third = farm_registry_provider.get_farm_registry()

    assert first is second is third
    assert _FakeFarmRegistry.init_calls == 1


def test_resolve_farm_db_path_existing_farm() -> None:
    """已知 farm_id → 回 str db_path。"""
    path = farm_registry_provider.resolve_farm_db_path("changhua")
    assert path == "/tmp/changhua.db"


def test_resolve_farm_db_path_unknown_farm_raises_404() -> None:
    """未知 farm_id → HTTPException(404)。"""
    with pytest.raises(HTTPException) as exc_info:
        farm_registry_provider.resolve_farm_db_path("__unknown_farm__")

    assert exc_info.value.status_code == 404
    assert "__unknown_farm__" in str(exc_info.value.detail)


def test_reset_farm_registry_clears_cache() -> None:
    """``reset_farm_registry()`` 後下次呼叫重新 init。"""
    farm_registry_provider.get_farm_registry()
    assert _FakeFarmRegistry.init_calls == 1

    farm_registry_provider.reset_farm_registry()
    farm_registry_provider.get_farm_registry()
    assert _FakeFarmRegistry.init_calls == 2


def test_import_failure_raises_500(monkeypatch: pytest.MonkeyPatch) -> None:
    """FarmRegistry import 失敗（modules.monitoring not mounted）→ HTTPException(500)。"""
    farm_registry_provider.reset_farm_registry()
    # 改掉 fake module，模擬 import 失敗
    monkeypatch.setitem(sys.modules, "modules.monitoring.server.farm_registry", None)

    with pytest.raises(HTTPException) as exc_info:
        farm_registry_provider.get_farm_registry()

    assert exc_info.value.status_code == 500
    assert "FarmRegistry not available" in str(exc_info.value.detail)
