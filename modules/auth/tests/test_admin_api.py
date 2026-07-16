"""admin 建帳 / 列帳 API — /api/auth/users（WMOM-20260716-04）。

**帳號與密碼一律以 ``secrets`` 執行期生成、以變數引用**（原始碼中無任何 username/password
字面值）→ 消除 secret scanner 對測試 fixture 的誤報，也是較好的測試衛生。
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.auth.routers import router as auth_router
from modules.auth.routers.auth_router import set_user_store
from modules.auth.tokens import create_access_token
from modules.auth.users import InMemoryUserStore

# 全部執行期生成，原始碼無字面帳密。
_NEW_PW = secrets.token_urlsafe(12)
_SHORT_PW = secrets.token_urlsafe(3)  # ~4 碼 < 8 → 觸發 pw 政策 422
_USER = "u" + secrets.token_hex(4)
_USER2 = "u" + secrets.token_hex(4)


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    set_user_store(InMemoryUserStore())  # 每個 test 一個乾淨空 store


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(auth_router)
    return TestClient(app)


def _headers(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject=f'{role}-1', role=role, name=role)}"}


def _payload(*, username: str = _USER, password: str = _NEW_PW) -> dict[str, object]:
    return {"username": username, "password": password, "name": "Test User", "role": "leader"}


def _login_body(username: str, password: str) -> dict[str, str]:
    return {"username": username, "password": password}


def test_create_user_as_admin_201():
    resp = _client().post("/api/auth/users", json=_payload(), headers=_headers("admin"))
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == _USER and body["role"] == "leader" and body["is_active"] is True
    assert "password" not in body and "password_hash" not in body  # 不外洩密碼


def test_create_user_non_admin_403():
    resp = _client().post("/api/auth/users", json=_payload(), headers=_headers("supervisor"))
    assert resp.status_code == 403


def test_create_user_no_token_401():
    assert _client().post("/api/auth/users", json=_payload()).status_code == 401


def test_create_user_duplicate_409():
    client = _client()
    client.post("/api/auth/users", json=_payload(), headers=_headers("admin"))
    dup = client.post("/api/auth/users", json=_payload(), headers=_headers("admin"))
    assert dup.status_code == 409


def test_create_user_short_password_422():
    resp = _client().post("/api/auth/users", json=_payload(password=_SHORT_PW), headers=_headers("admin"))
    assert resp.status_code == 422


def test_created_user_can_login():
    client = _client()
    client.post("/api/auth/users", json=_payload(), headers=_headers("admin"))
    login = client.post("/api/auth/login", json=_login_body(_USER, _NEW_PW))
    assert login.status_code == 200 and login.json()["actor"]["role"] == "leader"


def test_list_users_as_admin():
    client = _client()
    client.post("/api/auth/users", json=_payload(username=_USER), headers=_headers("admin"))
    client.post("/api/auth/users", json=_payload(username=_USER2), headers=_headers("admin"))
    resp = client.get("/api/auth/users", headers=_headers("admin"))
    assert resp.status_code == 200
    assert {u["username"] for u in resp.json()} == {_USER, _USER2}


def test_list_users_non_admin_403():
    assert _client().get("/api/auth/users", headers=_headers("employee")).status_code == 403
