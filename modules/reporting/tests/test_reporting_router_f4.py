"""WMOM-20260522-01 — reporting_router F4 follow-up regression tests。

驗證 reporting_router 已正確 migrate 到 ``shared.farm_registry_provider``：

- ``_get_ledger_repo`` / ``_get_wo_repo`` 預設路徑走 shared ``resolve_farm_db_path``
- factory 注入時不觸動 shared registry（mock 路徑優先）
- ``set_ledger_factory(None)`` / ``set_work_order_factory(None)`` 觸發 shared
  ``reset_farm_registry()``（兩個 setter 互不影響其他 setter；對齊 5/21 F4 既有 4 routers）

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
from modules.reporting.routers import reporting_router


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
    """每個 test 前後重置 shared singleton + 注入 fake FarmRegistry。

    確保 factory state 也清掉，避免 test 間殘留。
    """
    farm_registry_provider.reset_farm_registry()
    _FakeFarmRegistry.init_calls = 0
    reporting_router.set_ledger_factory(None)
    reporting_router.set_work_order_factory(None)

    fake_module = types.ModuleType("modules.monitoring.server.farm_registry")
    fake_module.FarmRegistry = _FakeFarmRegistry  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "modules.monitoring.server.farm_registry", fake_module)
    yield
    farm_registry_provider.reset_farm_registry()
    reporting_router.set_ledger_factory(None)
    reporting_router.set_work_order_factory(None)


# ─────────────────────────────────────────────────────────────────────────
# Default factories — 預設路徑走 shared resolve_farm_db_path
# ─────────────────────────────────────────────────────────────────────────


def test_get_ledger_repo_default_path_uses_shared_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """無注入 factory 時，``_get_ledger_repo`` 走 shared resolve 後傳 ``get_cost_ledger_repository``。"""
    captured: dict[str, str] = {}

    def fake_get_cost_ledger_repository(db_path: str):  # type: ignore[no-untyped-def]
        captured["path"] = db_path
        return object()

    monkeypatch.setattr(
        reporting_router,
        "get_cost_ledger_repository",
        fake_get_cost_ledger_repository,
    )
    reporting_router._get_ledger_repo("changhua")
    assert captured["path"] == "/tmp/changhua.db"


def test_get_wo_repo_default_path_uses_shared_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_get_wo_repo`` 走 shared resolve 後傳 ``get_work_order_repository``。"""
    captured: dict[str, str] = {}

    def fake_get_work_order_repository(db_path: str):  # type: ignore[no-untyped-def]
        captured["path"] = db_path
        return object()

    monkeypatch.setattr(
        reporting_router,
        "get_work_order_repository",
        fake_get_work_order_repository,
    )
    reporting_router._get_wo_repo("changhua")
    assert captured["path"] == "/tmp/changhua.db"


def test_get_ledger_repo_unknown_farm_returns_404() -> None:
    """未知 farm → HTTPException(404)（透過 shared resolve）。"""
    with pytest.raises(HTTPException) as exc_info:
        reporting_router._get_ledger_repo("__nope__")
    assert exc_info.value.status_code == 404


# ─────────────────────────────────────────────────────────────────────────
# Factory 注入 — 不觸動 shared singleton（保留 test mock 效率）
# ─────────────────────────────────────────────────────────────────────────


def test_injected_ledger_factory_bypasses_shared_provider() -> None:
    """注入 factory 後完全不碰 shared singleton（用 init_calls == 0 驗）。"""
    sentinel = object()
    reporting_router.set_ledger_factory(lambda fid: sentinel)  # type: ignore[arg-type]

    repo = reporting_router._get_ledger_repo("any_farm_even_unknown")
    assert repo is sentinel
    assert _FakeFarmRegistry.init_calls == 0  # shared registry 未被觸動


def test_set_ledger_factory_none_resets_shared_singleton() -> None:
    """``set_ledger_factory(None)`` 清 shared registry cache。"""
    farm_registry_provider.get_farm_registry()  # warm up
    assert _FakeFarmRegistry.init_calls == 1

    reporting_router.set_ledger_factory(lambda fid: object())  # type: ignore[arg-type]
    reporting_router.set_ledger_factory(None)  # reset trigger

    farm_registry_provider.get_farm_registry()
    assert _FakeFarmRegistry.init_calls == 2


def test_set_work_order_factory_none_resets_shared_singleton() -> None:
    """``set_work_order_factory(None)`` 同樣清 shared registry cache（兩 setter 對稱）。"""
    farm_registry_provider.get_farm_registry()
    assert _FakeFarmRegistry.init_calls == 1

    reporting_router.set_work_order_factory(lambda fid: object())  # type: ignore[arg-type]
    reporting_router.set_work_order_factory(None)

    farm_registry_provider.get_farm_registry()
    assert _FakeFarmRegistry.init_calls == 2
