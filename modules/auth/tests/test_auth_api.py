"""auth router — /api/auth/login + /api/auth/me（DEC-20260716-01）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.auth.passwords import hash_password
from modules.auth.roles import Role
from modules.auth.routers import router as auth_router
from modules.auth.routers.auth_router import set_user_store
from modules.auth.users import AuthUser, InMemoryUserStore


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setenv("WMOM_JWT_SECRET", "test-secret-abc")
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    set_user_store(
        InMemoryUserStore([AuthUser("id-a1", "alice", "Alice Chen", Role.EMPLOYEE, hash_password("pw"))])
    )


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(auth_router)
    return TestClient(app)


def test_login_success_returns_token_and_actor():
    resp = _client().post("/api/auth/login", json={"username": "alice", "password": "pw"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["actor"] == {"id": "id-a1", "name": "Alice Chen", "role": "employee"}


def test_login_wrong_password_401():
    resp = _client().post("/api/auth/login", json={"username": "alice", "password": "bad"})
    assert resp.status_code == 401


def test_login_unknown_user_401():
    resp = _client().post("/api/auth/login", json={"username": "ghost", "password": "pw"})
    assert resp.status_code == 401


def test_me_with_token_returns_actor():
    client = _client()
    token = client.post("/api/auth/login", json={"username": "alice", "password": "pw"}).json()["access_token"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["id"] == "id-a1"


def test_me_without_token_prod_401():
    assert _client().get("/api/auth/me").status_code == 401


def test_me_without_token_dev_mode_fallback(monkeypatch):
    monkeypatch.setenv("WMOM_DEV_MODE", "true")
    resp = _client().get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"
