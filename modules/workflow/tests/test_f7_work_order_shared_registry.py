"""WMOM-20260522-01 — work_order_router 改用 shared FARM_REGISTRY 後的 regression test。

驗證 F4 收尾後：
1. ``set_repository_factory(None)`` 真的會清 shared ``_FARM_REGISTRY``（與 4 個 F4 routers 對齊）
2. ``_resolve_db_path_for_finish_hook`` 在 shared raise HTTPException 時安靜返回 None
3. work_order_router 不再有自己的 ``_FARM_REGISTRY`` global（防止再有人加回 local cache）

Mock ``FarmRegistry`` 避免依賴 monitoring DB；teardown reset shared singleton 避免污染他 test。
"""

from __future__ import annotations

import sys
import types
from typing import Generator

import pytest
from fastapi import HTTPException

from shared import farm_registry_provider
from modules.workflow.routers import work_order_router


class _FakeFarmRegistry:
    """Mock — 只 stub get_farm_db_path。"""

    def __init__(self) -> None:
        self._paths: dict[str, str] = {"changhua": "/tmp/wo_test_changhua.db"}

    def get_farm_db_path(self, farm_id: str) -> str | None:
        return self._paths.get(farm_id)


@pytest.fixture(autouse=True)
def _isolate_shared_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """每個 test 前後 reset shared registry；注入 fake FarmRegistry。

    Teardown 故意呼叫 ``set_repository_factory(None)``（內部已包含 reset）+
    ``clear_finish_hook_db_paths``，single 完整入口清狀態避免污染他 test
    （review S2：不再額外重複呼叫 ``reset_farm_registry()``）。
    """
    farm_registry_provider.reset_farm_registry()
    fake_module = types.ModuleType("modules.monitoring.server.farm_registry")
    fake_module.FarmRegistry = _FakeFarmRegistry  # type: ignore[attr-defined]
    monkeypatch.setitem(
        sys.modules, "modules.monitoring.server.farm_registry", fake_module
    )
    yield
    # set_repository_factory(None) 內部會呼叫 reset_farm_registry()，不重複
    work_order_router.set_repository_factory(None)
    work_order_router.clear_finish_hook_db_paths()


def test_set_repository_factory_none_resets_shared_registry() -> None:
    """set_repository_factory(None) → shared ``_FARM_REGISTRY`` 被清。

    與 F4 batch 的 4 個 routers 一致：呼叫 None 時必須 reset shared singleton，
    讓下次的 ``_default_repository_factory`` 能重新 init（測試 fixture 切換時關鍵）。
    """
    # 先呼叫 resolve 觸發 lazy init
    farm_registry_provider.resolve_farm_db_path("changhua")
    assert farm_registry_provider._FARM_REGISTRY is not None

    # 呼叫 set None
    work_order_router.set_repository_factory(None)

    # shared singleton 被清
    assert farm_registry_provider._FARM_REGISTRY is None


def test_work_order_router_has_no_local_farm_registry_global() -> None:
    """禁止 work_order_router 再有自己的 ``_FARM_REGISTRY`` global。

    防止後續有人為了 micro-optimization 在 router 內部加回 local cache，
    導致與 shared singleton 不同步（F4 重構的根本目的）。
    """
    assert not hasattr(work_order_router, "_FARM_REGISTRY"), (
        "work_order_router must not own _FARM_REGISTRY; use shared.farm_registry_provider"
    )
    assert not hasattr(work_order_router, "_get_default_farm_registry"), (
        "work_order_router must not own _get_default_farm_registry; use shared.resolve_farm_db_path"
    )


def test_finish_hook_silent_on_shared_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """shared ``resolve_farm_db_path`` raise HTTPException(500) 時，finish hook 安靜返回 None。

    模擬 FarmRegistry 不可用（生產不該發生，但 partial deploy / test 場景）；
    finish hook 失敗不能阻擋工單收尾。

    Review M1：改 patch shared.resolve_farm_db_path 直接 raise，避免 patch
    ``__import__`` 的 cross-version 不一致風險 + 全 process import 高危副作用。
    """
    def _always_raise_500(_farm_id: str) -> str:
        raise HTTPException(status_code=500, detail="FarmRegistry not available")

    monkeypatch.setattr(
        work_order_router, "resolve_farm_db_path", _always_raise_500
    )
    result = work_order_router._resolve_db_path_for_finish_hook("changhua")
    assert result is None


def test_finish_hook_silent_on_farm_not_found() -> None:
    """Farm 不存在時 finish hook 安靜返回 None（不 raise 404）。"""
    # 無 override + fake registry 不含 "ghost_farm"
    result = work_order_router._resolve_db_path_for_finish_hook("ghost_farm")
    assert result is None


def test_finish_hook_override_takes_priority_over_shared() -> None:
    """Per-farm / wildcard override 仍優先於 shared lookup（F4 重構不該打破）。"""
    work_order_router.set_finish_hook_db_path("/tmp/override.db", farm_id="changhua")
    # 即便 shared 能解析 changhua，override 該優先
    result = work_order_router._resolve_db_path_for_finish_hook("changhua")
    assert result == "/tmp/override.db"
