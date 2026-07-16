"""dependencies — get_current_actor fallback/401 + require_roles（DEC-20260716-01）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.auth.dependencies import Actor, get_current_actor, require_roles
from modules.auth.roles import Role
from modules.auth.tokens import create_access_token


@pytest.fixture(autouse=True)
def _prod_secret(monkeypatch):
    monkeypatch.setenv("WMOM_JWT_SECRET", "test-secret-abc")
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)


def _client() -> TestClient:
    app = FastAPI()

    @app.get("/whoami")
    def whoami(actor: Actor = Depends(get_current_actor)):
        return {"id": actor.id, "role": actor.role.value}

    @app.get("/supervisor-only")
    def supervisor_only(actor: Actor = Depends(require_roles(Role.SUPERVISOR))):
        return {"role": actor.role.value}

    return TestClient(app)


def _bearer(role: str = "employee", subject: str = "u1", name: str = "U") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject=subject, role=role, name=name)}"}


def test_valid_token_resolves_actor():
    resp = _client().get("/whoami", headers=_bearer(role="leader", subject="u9"))
    assert resp.status_code == 200
    assert resp.json() == {"id": "u9", "role": "leader"}


def test_no_token_prod_401():
    assert _client().get("/whoami").status_code == 401


def test_no_token_dev_mode_fallback(monkeypatch):
    monkeypatch.setenv("WMOM_DEV_MODE", "true")
    resp = _client().get("/whoami")
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"  # fallback = dev admin


def test_invalid_token_401():
    assert _client().get("/whoami", headers={"Authorization": "Bearer garbage.token.xx"}).status_code == 401


def test_require_roles_allows_matching_role():
    assert _client().get("/supervisor-only", headers=_bearer(role="supervisor")).status_code == 200


def test_require_roles_forbids_other_role():
    assert _client().get("/supervisor-only", headers=_bearer(role="employee")).status_code == 403


def test_require_roles_admin_always_allowed():
    assert _client().get("/supervisor-only", headers=_bearer(role="admin")).status_code == 200
