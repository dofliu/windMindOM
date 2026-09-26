"""FastAPI day-work-form router tests（WMOM-20260505-21）。

涵蓋 5 endpoints（get-or-create / list / by-date / detail / append-activity）+ 雙模式授權
（enforce=false 過渡期放行 / enforce=true 後 role gate 生效），比照
``test_inspection_router_auth.py`` 慣例。
"""

from __future__ import annotations

import secrets
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.auth.tokens import create_access_token
from modules.workflow.repository.day_work_form_repository import (
    get_day_work_form_repository,
)
from modules.workflow.repository.work_order_repository import (
    clear_engine_cache_for_test,
)
from modules.workflow.routers import day_work_form_router
from modules.workflow.routers.day_work_form_router import set_day_work_form_factory


WORK_DATE = "2026-05-05"


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch):
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)


@pytest.fixture
def client_and_repo(tmp_path):
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")
    set_day_work_form_factory(lambda _f: get_day_work_form_repository(db_path))

    app = FastAPI(title="day-work-form-test")
    app.include_router(day_work_form_router)
    client = TestClient(app)
    repo = get_day_work_form_repository(db_path)

    yield client, repo

    set_day_work_form_factory(None)
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
    base = {"farm_id": "changhua", "work_date": WORK_DATE}
    base.update(overrides)
    return base


# ─────────────────────────────────────────────────────────────────────────
# get-or-create — enforce=false（過渡期，body employee_id 放行）
# ─────────────────────────────────────────────────────────────────────────


def test_create_ok_with_body_employee_id(client):
    employee_id = str(uuid4())
    resp = client.post(
        "/api/workflow/day-work-forms",
        json=_create_payload(employee_id=employee_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["employee_id"] == employee_id
    assert body["farm_id"] == "changhua"
    assert body["activities"] == []


def test_create_idempotent_same_employee_and_date(client):
    employee_id = str(uuid4())
    first = client.post(
        "/api/workflow/day-work-forms",
        json=_create_payload(employee_id=employee_id),
    ).json()
    second = client.post(
        "/api/workflow/day-work-forms",
        json=_create_payload(employee_id=employee_id),
    ).json()
    assert first["id"] == second["id"]


def test_create_no_body_employee_id_no_token_400(client):
    """過渡期：無 token 也無 body employee_id → 400（缺 actor）。"""
    resp = client.post("/api/workflow/day-work-forms", json=_create_payload())
    assert resp.status_code == 400


def test_create_token_overrides_body_employee_id(client):
    """token 優先——即使 body 帶了不同的 employee_id 也用 token sub。"""
    token_subject = str(uuid4())
    body_employee_id = str(uuid4())
    resp = client.post(
        "/api/workflow/day-work-forms",
        json=_create_payload(employee_id=body_employee_id),
        headers=_bearer("employee", token_subject),
    )
    assert resp.status_code == 200
    assert resp.json()["employee_id"] == token_subject


# ─────────────────────────────────────────────────────────────────────────
# list / by-date / detail
# ─────────────────────────────────────────────────────────────────────────


def test_get_roundtrip(client):
    employee_id = str(uuid4())
    created = client.post(
        "/api/workflow/day-work-forms",
        json=_create_payload(employee_id=employee_id),
    ).json()
    resp = client.get(
        f"/api/workflow/day-work-forms/{created['id']}",
        params={"farm_id": "changhua"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_not_found_404(client):
    resp = client.get(
        f"/api/workflow/day-work-forms/{uuid4()}", params={"farm_id": "changhua"}
    )
    assert resp.status_code == 404


def test_list_returns_created_items(client):
    client.post(
        "/api/workflow/day-work-forms",
        json=_create_payload(employee_id=str(uuid4())),
    )
    client.post(
        "/api/workflow/day-work-forms",
        json=_create_payload(employee_id=str(uuid4())),
    )
    resp = client.get("/api/workflow/day-work-forms", params={"farm_id": "changhua"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


def test_by_date_found(client):
    employee_id = str(uuid4())
    client.post(
        "/api/workflow/day-work-forms",
        json=_create_payload(employee_id=employee_id),
    )
    resp = client.get(
        "/api/workflow/day-work-forms/by-date",
        params={"farm_id": "changhua", "employee_id": employee_id, "work_date": WORK_DATE},
    )
    assert resp.status_code == 200
    assert resp.json()["employee_id"] == employee_id


def test_by_date_not_found_404(client):
    resp = client.get(
        "/api/workflow/day-work-forms/by-date",
        params={
            "farm_id": "changhua",
            "employee_id": str(uuid4()),
            "work_date": WORK_DATE,
        },
    )
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────
# append-activity
# ─────────────────────────────────────────────────────────────────────────


def test_append_patrol_activity(client):
    """過渡期（無 token）：body ``employee_id`` 需與建立日誌時同一人（不支援代填）。"""
    employee_id = str(uuid4())
    created = client.post(
        "/api/workflow/day-work-forms",
        json=_create_payload(employee_id=employee_id),
    ).json()
    resp = client.post(
        f"/api/workflow/day-work-forms/{created['id']}/activities",
        params={"farm_id": "changhua"},
        json={"kind": "patrol", "area": "機艙", "employee_id": employee_id},
    )
    assert resp.status_code == 200
    activities = resp.json()["activities"]
    assert len(activities) == 1
    assert activities[0]["kind"] == "patrol"
    assert activities[0]["area"] == "機艙"


def test_append_activity_different_employee_403(client):
    """Review must-fix repro：換一個 employee_id 想寫進別人的日誌 → 403（不支援代填）。"""
    owner_id = str(uuid4())
    other_id = str(uuid4())
    created = client.post(
        "/api/workflow/day-work-forms",
        json=_create_payload(employee_id=owner_id),
    ).json()
    resp = client.post(
        f"/api/workflow/day-work-forms/{created['id']}/activities",
        params={"farm_id": "changhua"},
        json={"kind": "patrol", "area": "機艙", "employee_id": other_id},
    )
    assert resp.status_code == 403


def test_append_activity_missing_required_field_422(client):
    employee_id = str(uuid4())
    created = client.post(
        "/api/workflow/day-work-forms",
        json=_create_payload(employee_id=employee_id),
    ).json()
    resp = client.post(
        f"/api/workflow/day-work-forms/{created['id']}/activities",
        params={"farm_id": "changhua"},
        json={"kind": "patrol", "employee_id": employee_id},  # 缺 area
    )
    assert resp.status_code == 422


def test_append_activity_not_found_404(client):
    """404 優先於 403——查無此日誌不需要先解出 employee_id。"""
    resp = client.post(
        f"/api/workflow/day-work-forms/{uuid4()}/activities",
        params={"farm_id": "changhua"},
        json={"kind": "patrol", "area": "機艙"},
    )
    assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────
# enforce=true（cutover 後）— role gate
# ─────────────────────────────────────────────────────────────────────────


def test_create_enforced_no_token_401(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = client.post("/api/workflow/day-work-forms", json=_create_payload())
    assert resp.status_code == 401


def test_create_enforced_treasury_403(client, monkeypatch):
    """庫管不填工作日誌——比照 work_order 建單權限（EMPLOYEE/LEADER/SUPERVISOR）。"""
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = client.post(
        "/api/workflow/day-work-forms",
        json=_create_payload(),
        headers=_bearer("treasury", str(uuid4())),
    )
    assert resp.status_code == 403


def test_create_enforced_employee_ok(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = client.post(
        "/api/workflow/day-work-forms",
        json=_create_payload(),
        headers=_bearer("employee", str(uuid4())),
    )
    assert resp.status_code == 200


def test_list_enforced_no_token_401(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = client.get("/api/workflow/day-work-forms", params={"farm_id": "changhua"})
    assert resp.status_code == 401


def test_list_enforced_any_role_ok(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = client.get(
        "/api/workflow/day-work-forms",
        params={"farm_id": "changhua"},
        headers=_bearer("treasury", str(uuid4())),
    )
    assert resp.status_code == 200


def test_append_activity_enforced_treasury_403(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    created = client.post(
        "/api/workflow/day-work-forms",
        json=_create_payload(),
        headers=_bearer("supervisor", str(uuid4())),
    ).json()
    resp = client.post(
        f"/api/workflow/day-work-forms/{created['id']}/activities",
        params={"farm_id": "changhua"},
        json={"kind": "patrol", "area": "機艙"},
        headers=_bearer("treasury", str(uuid4())),
    )
    assert resp.status_code == 403


def test_append_activity_enforced_employee_ok(client, monkeypatch):
    """同一人（同 token subject）建立日誌後幫自己補活動 → 200。"""
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    subject = str(uuid4())
    created = client.post(
        "/api/workflow/day-work-forms",
        json=_create_payload(),
        headers=_bearer("employee", subject),
    ).json()
    resp = client.post(
        f"/api/workflow/day-work-forms/{created['id']}/activities",
        params={"farm_id": "changhua"},
        json={"kind": "patrol", "area": "機艙"},
        headers=_bearer("employee", subject),
    )
    assert resp.status_code == 200


def test_append_activity_enforced_different_employee_403(client, monkeypatch):
    """Review must-fix repro：enforce 模式下換一個人的 token 想寫進別人的日誌 → 403。

    先前這裡誤用兩個不同的隨機 subject 卻斷言 200，字面上鎖住了「任何 EMPLOYEE
    角色都能寫進任何人日誌」的錯誤行為（code review 抓到）；現在明確拆成
    ``test_append_activity_enforced_employee_ok``（同一人 OK）與本測試（換人 403）。
    """
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    created = client.post(
        "/api/workflow/day-work-forms",
        json=_create_payload(),
        headers=_bearer("employee", str(uuid4())),
    ).json()
    resp = client.post(
        f"/api/workflow/day-work-forms/{created['id']}/activities",
        params={"farm_id": "changhua"},
        json={"kind": "patrol", "area": "機艙"},
        headers=_bearer("employee", str(uuid4())),
    )
    assert resp.status_code == 403


def test_append_activity_supervisor_cannot_write_others_log_403(client, monkeypatch):
    """不支援代填——SUPERVISOR 有寫入權限（role gate 過），但不是日誌本人一樣 403。

    比照 walkthrough Q6「day_work_form 是自填日誌」的設計不變量，不因角色較高
    就允許代填（與 LEADER/SUPERVISOR 可以查全員日誌是兩件事，見 list/by-date）。
    """
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    created = client.post(
        "/api/workflow/day-work-forms",
        json=_create_payload(),
        headers=_bearer("employee", str(uuid4())),
    ).json()
    resp = client.post(
        f"/api/workflow/day-work-forms/{created['id']}/activities",
        params={"farm_id": "changhua"},
        json={"kind": "patrol", "area": "機艙"},
        headers=_bearer("supervisor", str(uuid4())),
    )
    assert resp.status_code == 403
