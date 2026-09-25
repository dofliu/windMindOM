"""FastAPI inspection-schedule router tests（WMOM-20260505-22）。

涵蓋 8 endpoints（CRUD + activate/deactivate + run-scheduler）+ 雙模式授權
（enforce=false 過渡期放行 / enforce=true 後 role gate 生效），比照
``test_inventory_router_auth.py`` 慣例。
"""

from __future__ import annotations

import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.auth.tokens import create_access_token
from modules.workflow.repository.inspection_repository import get_inspection_repository
from modules.workflow.repository.work_order_repository import (
    clear_engine_cache_for_test,
    get_repository,
)
from modules.workflow.routers import inspection_router
from modules.workflow.routers.inspection_router import (
    set_inspection_factory,
    set_work_order_factory_for_scheduler,
)


UTC = timezone.utc


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch):
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)


@pytest.fixture
def client_and_repo(tmp_path):
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")
    set_inspection_factory(lambda _f: get_inspection_repository(db_path))
    set_work_order_factory_for_scheduler(lambda _f: get_repository(db_path))

    app = FastAPI(title="inspection-test")
    app.include_router(inspection_router)
    client = TestClient(app)
    repo = get_inspection_repository(db_path)

    yield client, repo

    set_inspection_factory(None)
    set_work_order_factory_for_scheduler(None)
    clear_engine_cache_for_test()


@pytest.fixture
def client(client_and_repo):
    return client_and_repo[0]


@pytest.fixture
def repo(client_and_repo):
    return client_and_repo[1]


def _bearer(role: str, subject: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject=subject, role=role, name='U')}"}


def _create_payload(**overrides) -> dict:
    base = {
        "farm_id": "changhua",
        "turbine_id": "WT-01",
        "title": "塔筒螺栓檢查",
        "description": "每月一次塔筒螺栓扭力檢查",
        "recurrence": "monthly",
    }
    base.update(overrides)
    return base


# ─────────────────────────────────────────────────────────────────────────
# CRUD — enforce=false（過渡期，無 token 也放行）
# ─────────────────────────────────────────────────────────────────────────


def test_create_returns_201(client):
    resp = client.post("/api/workflow/inspection-schedules", json=_create_payload())
    assert resp.status_code == 201
    body = resp.json()
    assert body["turbine_id"] == "WT-01"
    assert body["active"] is True
    assert body["last_spawned_work_order_id"] is None


def test_create_custom_days_without_interval_422(client):
    resp = client.post(
        "/api/workflow/inspection-schedules",
        json=_create_payload(recurrence="custom_days"),
    )
    assert resp.status_code == 422


def test_create_custom_days_with_interval_ok(client):
    resp = client.post(
        "/api/workflow/inspection-schedules",
        json=_create_payload(recurrence="custom_days", interval_days=45),
    )
    assert resp.status_code == 201
    assert resp.json()["interval_days"] == 45


def test_get_roundtrip(client):
    created = client.post("/api/workflow/inspection-schedules", json=_create_payload()).json()
    resp = client.get(
        f"/api/workflow/inspection-schedules/{created['id']}",
        params={"farm_id": "changhua"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_not_found_404(client):
    resp = client.get(
        f"/api/workflow/inspection-schedules/{uuid4()}", params={"farm_id": "changhua"}
    )
    assert resp.status_code == 404


def test_list_returns_created_items(client):
    client.post("/api/workflow/inspection-schedules", json=_create_payload(turbine_id="WT-01"))
    client.post("/api/workflow/inspection-schedules", json=_create_payload(turbine_id="WT-02"))
    resp = client.get("/api/workflow/inspection-schedules", params={"farm_id": "changhua"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


def test_list_filters_by_turbine(client):
    client.post("/api/workflow/inspection-schedules", json=_create_payload(turbine_id="WT-01"))
    client.post("/api/workflow/inspection-schedules", json=_create_payload(turbine_id="WT-02"))
    resp = client.get(
        "/api/workflow/inspection-schedules",
        params={"farm_id": "changhua", "turbine_id": "WT-02"},
    )
    assert resp.json()["total"] == 1


def test_update_metadata(client):
    created = client.post("/api/workflow/inspection-schedules", json=_create_payload()).json()
    resp = client.patch(
        f"/api/workflow/inspection-schedules/{created['id']}",
        params={"farm_id": "changhua"},
        json={"title": "新標題"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "新標題"
    assert resp.json()["description"] == created["description"]  # 未帶欄位不變


def test_update_metadata_custom_days_without_interval_422(client):
    """Review must-fix repro at HTTP layer：PATCH 成 custom_days 卻不帶
    interval_days（且排程原本也沒有）→ 422，不能靜默寫入無效組合。"""
    created = client.post("/api/workflow/inspection-schedules", json=_create_payload()).json()
    resp = client.patch(
        f"/api/workflow/inspection-schedules/{created['id']}",
        params={"farm_id": "changhua"},
        json={"recurrence": "custom_days"},
    )
    assert resp.status_code == 422


def test_update_metadata_not_found_404(client):
    resp = client.patch(
        f"/api/workflow/inspection-schedules/{uuid4()}",
        params={"farm_id": "changhua"},
        json={"title": "x"},
    )
    assert resp.status_code == 404


def test_deactivate_then_activate(client):
    created = client.post("/api/workflow/inspection-schedules", json=_create_payload()).json()
    off = client.post(
        f"/api/workflow/inspection-schedules/{created['id']}/deactivate",
        params={"farm_id": "changhua"},
    )
    assert off.status_code == 200
    assert off.json()["active"] is False

    on = client.post(
        f"/api/workflow/inspection-schedules/{created['id']}/activate",
        params={"farm_id": "changhua"},
    )
    assert on.status_code == 200
    assert on.json()["active"] is True


# ─────────────────────────────────────────────────────────────────────────
# run-scheduler
# ─────────────────────────────────────────────────────────────────────────


def test_run_scheduler_spawns_due_schedule(client):
    past_due = (datetime.now(tz=UTC) - timedelta(days=1)).isoformat()
    client.post(
        "/api/workflow/inspection-schedules",
        json=_create_payload(first_due_at=past_due),
    )
    resp = client.post(
        "/api/workflow/inspection-schedules/run-scheduler",
        params={"farm_id": "changhua"},
    )
    assert resp.status_code == 200
    spawned = resp.json()["spawned"]
    assert len(spawned) == 1
    assert spawned[0]["turbine_id"] == "WT-01"


def test_run_scheduler_empty_when_nothing_due(client):
    future = (datetime.now(tz=UTC) + timedelta(days=30)).isoformat()
    client.post(
        "/api/workflow/inspection-schedules",
        json=_create_payload(first_due_at=future),
    )
    resp = client.post(
        "/api/workflow/inspection-schedules/run-scheduler",
        params={"farm_id": "changhua"},
    )
    assert resp.status_code == 200
    assert resp.json()["spawned"] == []


def test_run_scheduler_second_call_idempotent(client):
    past_due = (datetime.now(tz=UTC) - timedelta(days=1)).isoformat()
    client.post(
        "/api/workflow/inspection-schedules",
        json=_create_payload(first_due_at=past_due),
    )
    first = client.post(
        "/api/workflow/inspection-schedules/run-scheduler",
        params={"farm_id": "changhua"},
    )
    second = client.post(
        "/api/workflow/inspection-schedules/run-scheduler",
        params={"farm_id": "changhua"},
    )
    assert len(first.json()["spawned"]) == 1
    assert second.json()["spawned"] == []


# ─────────────────────────────────────────────────────────────────────────
# enforce=true（cutover 後）— role gate
# ─────────────────────────────────────────────────────────────────────────


def test_create_enforced_no_token_401(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = client.post("/api/workflow/inspection-schedules", json=_create_payload())
    assert resp.status_code == 401


def test_create_enforced_employee_403(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = client.post(
        "/api/workflow/inspection-schedules",
        json=_create_payload(),
        headers=_bearer("employee", str(uuid4())),
    )
    assert resp.status_code == 403


def test_create_enforced_leader_ok(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = client.post(
        "/api/workflow/inspection-schedules",
        json=_create_payload(),
        headers=_bearer("leader", str(uuid4())),
    )
    assert resp.status_code == 201


def test_create_enforced_supervisor_ok(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = client.post(
        "/api/workflow/inspection-schedules",
        json=_create_payload(),
        headers=_bearer("supervisor", str(uuid4())),
    )
    assert resp.status_code == 201


def test_list_enforced_no_token_401(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = client.get("/api/workflow/inspection-schedules", params={"farm_id": "changhua"})
    assert resp.status_code == 401


def test_list_enforced_any_role_ok(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = client.get(
        "/api/workflow/inspection-schedules",
        params={"farm_id": "changhua"},
        headers=_bearer("employee", str(uuid4())),
    )
    assert resp.status_code == 200


def test_run_scheduler_enforced_leader_403(client, monkeypatch):
    """run-scheduler 比 CRUD 權限更高（僅 SUPERVISOR）——LEADER 不夠。"""
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = client.post(
        "/api/workflow/inspection-schedules/run-scheduler",
        params={"farm_id": "changhua"},
        headers=_bearer("leader", str(uuid4())),
    )
    assert resp.status_code == 403


def test_run_scheduler_enforced_supervisor_ok(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = client.post(
        "/api/workflow/inspection-schedules/run-scheduler",
        params={"farm_id": "changhua"},
        headers=_bearer("supervisor", str(uuid4())),
    )
    assert resp.status_code == 200


def test_deactivate_enforced_employee_403(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    created = client.post(
        "/api/workflow/inspection-schedules",
        json=_create_payload(),
        headers=_bearer("supervisor", str(uuid4())),
    ).json()
    resp = client.post(
        f"/api/workflow/inspection-schedules/{created['id']}/deactivate",
        params={"farm_id": "changhua"},
        headers=_bearer("employee", str(uuid4())),
    )
    assert resp.status_code == 403
