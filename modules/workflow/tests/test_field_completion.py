"""現場完工佐證 + assignee 過濾測試（WMOM-20260608-02 / DEC-20260608-02）。

涵蓋：
- 完工 signature + photos 持久化 / round-trip（JSON 序列化）
- 未帶佐證時 default（office finish 不破壞）
- list 依 assignee_id 過濾（「我的工單」）
- 既有 DB 缺欄的輕量 migration（ALTER TABLE ADD COLUMN 冪等）
- API 層：finish 帶佐證 + list?assignee_id
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.workflow.domain import FollowupKind, WorkOrderType
from modules.workflow.repository import (
    SignoffRepository,
    WorkOrderRepository,
    get_repository,
    get_signoff_repository,
)
from modules.workflow.repository.work_order_repository import (
    _get_engine,
    _load_completion_photos,
    _migrate_completion_columns,
    clear_engine_cache_for_test,
)
from modules.workflow.routers import approval_router, router as workflow_router
from modules.workflow.routers.approval_router import set_signoff_factories
from modules.workflow.routers.work_order_router import set_repository_factory

# 簡短 base64 data URL stub（佐證內容不重要，測「有存到 + round-trip」）。
_SIG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCA— sig"
_PHOTO1 = "data:image/jpeg;base64,/9j/4AAQSkZJRg— photo1"
_PHOTO2 = "data:image/jpeg;base64,/9j/4AAQSkZJRg— photo2"


# ─────────────────────────────────────────────────────────────────────────
# Repository fixture + helpers
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def repo(tmp_path):
    clear_engine_cache_for_test()
    yield get_repository(str(tmp_path / "wind_farm.db"))
    clear_engine_cache_for_test()


def _make(repo, **overrides):
    base = dict(
        farm_id="台中港曲風場",
        turbine_id="WT001",
        type=WorkOrderType.CORRECTIVE,
        title="軸承過熱",
        description="主軸承溫度 75°C",
    )
    base.update(overrides)
    return repo.create(**base)


def _drive_to_in_progress(repo, wo, assignee):
    """create 後 → dispatch（帶 assignee）→ start_work，停在 IN_PROGRESS。"""
    repo.transition(wo.id, "dispatch", actor_id=uuid4(), assignee_id=assignee)
    repo.transition(wo.id, "start_work")


# ─────────────────────────────────────────────────────────────────────────
# 完工佐證 round-trip
# ─────────────────────────────────────────────────────────────────────────


def test_finish_persists_signature_and_photos(repo):
    """完工帶簽名 + 多張照片 → get 後逐項還原（JSON round-trip）。"""
    assignee = uuid4()
    wo = _make(repo)
    _drive_to_in_progress(repo, wo, assignee)
    repo.transition(
        wo.id, "finish",
        actual_hours=3.5,
        followup_kind=FollowupKind.NONE,
        completion_signature=_SIG,
        completion_photos=[_PHOTO1, _PHOTO2],
    )
    got = repo.get(wo.id)
    assert got is not None
    assert got.completion_signature == _SIG
    assert got.completion_photos == [_PHOTO1, _PHOTO2]


def test_finish_without_evidence_defaults_empty(repo):
    """office finish 不帶佐證 → signature None / photos []（既有 path 不破壞）。"""
    wo = _make(repo)
    _drive_to_in_progress(repo, wo, uuid4())
    repo.transition(wo.id, "finish", actual_hours=1.0, followup_kind=FollowupKind.NONE)
    got = repo.get(wo.id)
    assert got is not None
    assert got.completion_signature is None
    assert got.completion_photos == []


def test_empty_photos_list_persists_as_empty(repo):
    """簽名有、照片空清單 → photos 仍為 []（存 None 但讀回 []）。"""
    wo = _make(repo)
    _drive_to_in_progress(repo, wo, uuid4())
    repo.transition(
        wo.id, "finish",
        actual_hours=2.0,
        followup_kind=FollowupKind.NONE,
        completion_signature=_SIG,
        completion_photos=[],
    )
    got = repo.get(wo.id)
    assert got.completion_signature == _SIG
    assert got.completion_photos == []


# ─────────────────────────────────────────────────────────────────────────
# assignee 過濾（我的工單）
# ─────────────────────────────────────────────────────────────────────────


def test_list_filters_by_assignee(repo):
    """list(assignee_id=X) 只回指派給 X 的工單。"""
    alice, bob = uuid4(), uuid4()
    wo_a = _make(repo, turbine_id="WT001")
    wo_b = _make(repo, turbine_id="WT002")
    repo.transition(wo_a.id, "dispatch", actor_id=uuid4(), assignee_id=alice)
    repo.transition(wo_b.id, "dispatch", actor_id=uuid4(), assignee_id=bob)

    items, total = repo.list(farm_id="台中港曲風場", assignee_id=alice)
    assert total == 1
    assert [w.id for w in items] == [wo_a.id]
    assert items[0].assignee_id == alice


def test_list_without_assignee_returns_all(repo):
    """不帶 assignee_id → 全列（向後相容）。"""
    _make(repo, turbine_id="WT001")
    _make(repo, turbine_id="WT002")
    _items, total = repo.list(farm_id="台中港曲風場")
    assert total == 2


def test_list_assignee_excludes_unassigned(repo):
    """未指派（DRAFT，assignee_id=None）的工單不被 assignee 過濾撈出（SQL NULL≠UUID）。"""
    alice = uuid4()
    _make(repo, turbine_id="WT001")  # DRAFT，未 dispatch → assignee_id None
    _items, total = repo.list(farm_id="台中港曲風場", assignee_id=alice)
    assert total == 0


# ─────────────────────────────────────────────────────────────────────────
# migration（既有 DB 缺欄補上）
# ─────────────────────────────────────────────────────────────────────────


def test_migration_adds_columns_to_legacy_table(tmp_path):
    """既有 wmom_work_orders 缺完工佐證欄 → migration 補上且冪等。"""
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "legacy.db")
    eng = _get_engine(db_path)
    # 模擬舊 schema：建一個沒有 completion_* 欄的最小 wmom_work_orders。
    with eng.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE wmom_work_orders (id TEXT PRIMARY KEY, status TEXT)"
        )

    def _cols():
        with eng.connect() as c:
            return {
                r[1]
                for r in c.exec_driver_sql(
                    "PRAGMA table_info(wmom_work_orders)"
                ).fetchall()
            }

    assert "completion_signature" not in _cols()
    _migrate_completion_columns(eng)
    cols = _cols()
    assert "completion_signature" in cols
    assert "completion_photos" in cols
    # 冪等：再跑一次不該 raise（欄已存在）。
    _migrate_completion_columns(eng)
    clear_engine_cache_for_test()


def test_load_completion_photos_robustness():
    """_load_completion_photos：None / 空 / 壞 JSON / 非 list → []；正常 list 還原。"""
    assert _load_completion_photos(None) == []
    assert _load_completion_photos("") == []
    assert _load_completion_photos("{not json") == []
    assert _load_completion_photos('"just a string"') == []  # 非 list
    assert _load_completion_photos('["a", "b"]') == ["a", "b"]


# ─────────────────────────────────────────────────────────────────────────
# API 層
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path):
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")

    def wo_factory(farm_id: str) -> WorkOrderRepository:
        return get_repository(db_path)

    def sg_factory(farm_id: str) -> SignoffRepository:
        return get_signoff_repository(db_path)

    set_repository_factory(wo_factory)
    set_signoff_factories(sg_factory, wo_factory)
    app = FastAPI(title="field-completion-test")
    app.include_router(workflow_router)
    app.include_router(approval_router)
    yield TestClient(app)
    set_repository_factory(None)
    set_signoff_factories(None, None)
    clear_engine_cache_for_test()


_FARM = "台中港曲風場"
_Q = f"?farm_id={_FARM}"


def _create_and_start(client, assignee_id: str, turbine_id: str = "WT001") -> str:
    """API：create → dispatch（帶 assignee）→ start-work，回 work_order_id。"""
    r = client.post(
        "/api/workflow/work-orders",
        json={
            "farm_id": _FARM,
            "turbine_id": turbine_id,
            "type": "corrective",
            "title": "軸承過熱",
            "description": "主軸承溫度 75°C",
        },
    )
    assert r.status_code == 201, r.text
    wo_id = r.json()["id"]
    r = client.post(
        f"/api/workflow/work-orders/{wo_id}/dispatch{_Q}",
        json={"actor_id": str(uuid4()), "assignee_id": assignee_id},
    )
    assert r.status_code == 200, r.text
    r = client.post(f"/api/workflow/work-orders/{wo_id}/start-work{_Q}", json={})
    assert r.status_code == 200, r.text
    return wo_id


def test_finish_via_api_with_signature_and_photo(client):
    """API 完工帶簽名 + 照片 → response 回存的佐證。"""
    wo_id = _create_and_start(client, str(uuid4()))
    r = client.post(
        f"/api/workflow/work-orders/{wo_id}/finish{_Q}",
        json={
            "actual_hours": 4.0,
            "followup_kind": "none",
            "work_summary": "更換主軸承",
            "completion_signature": _SIG,
            "completion_photos": [_PHOTO1, _PHOTO2],
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "awaiting_signoff"
    assert data["completion_signature"] == _SIG
    assert data["completion_photos"] == [_PHOTO1, _PHOTO2]


def test_finish_via_api_without_evidence_ok(client):
    """API 完工不帶佐證仍可（office path）→ 200 + 空佐證。"""
    wo_id = _create_and_start(client, str(uuid4()))
    r = client.post(
        f"/api/workflow/work-orders/{wo_id}/finish{_Q}",
        json={"actual_hours": 1.0, "followup_kind": "none"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["completion_signature"] is None
    assert data["completion_photos"] == []


def test_list_by_assignee_via_api(client):
    """API：list?assignee_id=X 只回 X 的工單（我的工單）。"""
    alice, bob = str(uuid4()), str(uuid4())
    _create_and_start(client, alice, turbine_id="WT001")
    _create_and_start(client, bob, turbine_id="WT002")

    r = client.get(f"/api/workflow/work-orders{_Q}&assignee_id={alice}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["assignee_id"] == alice
