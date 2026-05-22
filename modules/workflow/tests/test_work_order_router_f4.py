"""WMOM-20260522-01 — work_order_router F4 follow-up regression tests。

驗證 work_order_router 已正確 migrate 到 ``shared.farm_registry_provider``：

- ``_default_repository_factory`` 走 shared ``resolve_farm_db_path``（happy + 404）
- ``_resolve_db_path_for_finish_hook`` 保留「失敗安靜跳過」語義（registry 載入失敗 / farm 未知都回 None，不 raise）
- ``set_repository_factory(None)`` 觸發 shared ``reset_farm_registry()``（不再殘留 module-private singleton）

mock ``FarmRegistry`` 避免依賴 monitoring DB；fixture autouse 重置 shared singleton。
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Generator

import pytest
from fastapi import HTTPException

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from shared import farm_registry_provider
from modules.workflow.routers import work_order_router


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
    """每個 test 前後都重置 shared lazy singleton + 注入 fake FarmRegistry。

    Code review must-fix：fixture 也要在 setup / teardown 兩段清 ``_repository_factory``，
    對齊 reporting_router test 模式；避免上一個 test 注入的 mock factory 洩漏到本文件，
    或 test 中途 fail 後 factory 殘留污染後續 test 文件。
    """
    farm_registry_provider.reset_farm_registry()
    _FakeFarmRegistry.init_calls = 0
    work_order_router.set_repository_factory(None)
    work_order_router.clear_finish_hook_db_paths()

    fake_module = types.ModuleType("modules.monitoring.server.farm_registry")
    fake_module.FarmRegistry = _FakeFarmRegistry  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "modules.monitoring.server.farm_registry", fake_module)
    yield
    farm_registry_provider.reset_farm_registry()
    work_order_router.set_repository_factory(None)
    work_order_router.clear_finish_hook_db_paths()


# ─────────────────────────────────────────────────────────────────────────
# Main repository factory — 走 shared resolve_farm_db_path
# ─────────────────────────────────────────────────────────────────────────


def test_default_factory_resolves_via_shared_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_default_repository_factory`` 從 shared 拿 path 後傳 ``get_repository``。"""
    captured: dict[str, str] = {}

    def fake_get_repository(db_path: str):  # type: ignore[no-untyped-def]
        captured["path"] = db_path
        return object()

    monkeypatch.setattr(work_order_router, "get_repository", fake_get_repository)
    work_order_router._default_repository_factory("changhua")
    assert captured["path"] == "/tmp/changhua.db"


def test_default_factory_unknown_farm_returns_404() -> None:
    """未知 farm_id → HTTPException(404)（透過 shared ``resolve_farm_db_path``）。"""
    with pytest.raises(HTTPException) as exc_info:
        work_order_router._default_repository_factory("__nope__")
    assert exc_info.value.status_code == 404
    assert "__nope__" in str(exc_info.value.detail)


def test_set_repository_factory_none_resets_shared_singleton() -> None:
    """``set_repository_factory(None)`` 必須清掉 shared ``_FARM_REGISTRY``。

    無此 reset，下次 test 拿到上一輪 _FakeFarmRegistry instance 殘留。
    """
    farm_registry_provider.get_farm_registry()  # warm up
    assert _FakeFarmRegistry.init_calls == 1

    work_order_router.set_repository_factory(lambda fid: object())  # type: ignore[arg-type]
    work_order_router.set_repository_factory(None)

    farm_registry_provider.get_farm_registry()
    assert _FakeFarmRegistry.init_calls == 2


# ─────────────────────────────────────────────────────────────────────────
# Finish hook — 保留「失敗安靜跳過」語義（不能 raise）
# ─────────────────────────────────────────────────────────────────────────


def test_finish_hook_resolves_via_shared_provider() -> None:
    """無 override 時 hook 走 shared registry → 拿 fake path。"""
    path = work_order_router._resolve_db_path_for_finish_hook("changhua")
    assert path == "/tmp/changhua.db"


def test_finish_hook_unknown_farm_returns_none_silently() -> None:
    """未知 farm_id → 安靜回 None（finish hook 不能因 farm 找不到就 raise，
    工單已經 AWAITING_SIGNOFF）。"""
    path = work_order_router._resolve_db_path_for_finish_hook("__nope__")
    assert path is None


def test_finish_hook_registry_unavailable_returns_none_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """monitoring 未掛載（FarmRegistry import 失敗）→ shared helper 會 raise
    HTTPException(500)；hook 必須接住後安靜回 None，不可炸 endpoint。"""
    farm_registry_provider.reset_farm_registry()
    monkeypatch.setitem(sys.modules, "modules.monitoring.server.farm_registry", None)

    path = work_order_router._resolve_db_path_for_finish_hook("changhua")
    assert path is None


def test_finish_hook_override_bypasses_shared_provider(tmp_path) -> None:
    """設定 override 後完全不碰 shared registry（保留既有 multi-farm safe 行為）。"""
    override_path = str(tmp_path / "override.db")
    work_order_router.set_finish_hook_db_path(override_path, farm_id="changhua")

    path = work_order_router._resolve_db_path_for_finish_hook("changhua")
    assert path == override_path
    # shared registry 不該被觸動（init_calls == 0 驗證）
    assert _FakeFarmRegistry.init_calls == 0
