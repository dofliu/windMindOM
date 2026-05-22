"""WMOM-20260522-01 — reporting_router 改用 shared FARM_REGISTRY 後的 regression test。

驗證 F4 收尾後：
1. ``set_ledger_factory(None)`` / ``set_work_order_factory(None)`` 各自會清 shared singleton
2. ``set_availability_provider`` **不**動 shared registry（availability 與 farm 解析無關）
3. reporting_router 不再有自己的 ``_FARM_REGISTRY`` global / ``_resolve_farm_db_path`` 函式
"""

from __future__ import annotations

import sys
import types
from typing import Generator

import pytest

from shared import farm_registry_provider
from modules.reporting.routers import reporting_router


class _FakeFarmRegistry:
    def __init__(self) -> None:
        self._paths: dict[str, str] = {"changhua": "/tmp/rep_test_changhua.db"}

    def get_farm_db_path(self, farm_id: str) -> str | None:
        return self._paths.get(farm_id)


@pytest.fixture(autouse=True)
def _isolate_shared_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    farm_registry_provider.reset_farm_registry()
    fake_module = types.ModuleType("modules.monitoring.server.farm_registry")
    fake_module.FarmRegistry = _FakeFarmRegistry  # type: ignore[attr-defined]
    monkeypatch.setitem(
        sys.modules, "modules.monitoring.server.farm_registry", fake_module
    )
    yield
    farm_registry_provider.reset_farm_registry()
    reporting_router.set_ledger_factory(None)
    reporting_router.set_work_order_factory(None)
    reporting_router.set_availability_provider(None)


def test_set_ledger_factory_none_resets_shared_registry() -> None:
    farm_registry_provider.resolve_farm_db_path("changhua")
    assert farm_registry_provider._FARM_REGISTRY is not None

    reporting_router.set_ledger_factory(None)
    assert farm_registry_provider._FARM_REGISTRY is None


def test_set_work_order_factory_none_resets_shared_registry() -> None:
    farm_registry_provider.resolve_farm_db_path("changhua")
    assert farm_registry_provider._FARM_REGISTRY is not None

    reporting_router.set_work_order_factory(None)
    assert farm_registry_provider._FARM_REGISTRY is None


def test_set_availability_provider_none_does_not_reset_shared_registry() -> None:
    """availability provider 與 farm 解析無關，不該動 shared singleton。

    這條 guard 防止後續有人把 reset 「順手」加進 availability setter，
    導致 availability 切換時意外清掉 farm cache（不必要的副作用）。
    """
    farm_registry_provider.resolve_farm_db_path("changhua")
    before = farm_registry_provider._FARM_REGISTRY
    assert before is not None

    reporting_router.set_availability_provider(None)

    # availability provider 變更不該影響 farm registry
    assert farm_registry_provider._FARM_REGISTRY is before


def test_reporting_router_has_no_local_farm_registry_global() -> None:
    """禁止 reporting_router 再有自己的 ``_FARM_REGISTRY`` global / ``_resolve_farm_db_path`` 函式。"""
    assert not hasattr(reporting_router, "_FARM_REGISTRY"), (
        "reporting_router must not own _FARM_REGISTRY; use shared.farm_registry_provider"
    )
    assert not hasattr(reporting_router, "_resolve_farm_db_path"), (
        "reporting_router must not own _resolve_farm_db_path; use shared.resolve_farm_db_path"
    )


def test_get_repos_route_through_shared_when_factory_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """factory 為 None 時 ``_get_ledger_repo`` / ``_get_wo_repo`` 應該走 shared 解析路徑。

    Review N1：直接驗 production code path（不只 setter 副作用），
    確保 refactor 後 shared lookup 真的有被 hit。
    """
    calls: list[str] = []

    def _spy(farm_id: str) -> str:
        calls.append(farm_id)
        return f"/tmp/spy_{farm_id}.db"

    # factory 為 None（無 mock injection）→ 必須走 shared
    reporting_router.set_ledger_factory(None)
    reporting_router.set_work_order_factory(None)
    monkeypatch.setattr(reporting_router, "resolve_farm_db_path", _spy)

    # 各呼叫一次 — 不關心回傳 repo 物件，只看 shared 是否被 hit
    # 兩 helper 都會嘗試建立 repository（呼叫 SQLAlchemy engine），
    # 預期 path 不真實存在所以 sqlalchemy 不會踩到 actual disk，
    # 但要避免 import error；用 try/except 兜底，重點在 spy 被觸發
    try:
        reporting_router._get_ledger_repo("changhua")
    except Exception:  # noqa: BLE001
        pass
    try:
        reporting_router._get_wo_repo("changhua")
    except Exception:  # noqa: BLE001
        pass

    # 兩 helper 各打一次 shared
    assert calls == ["changhua", "changhua"]
