"""雙模式授權 scaffold — is_auth_enforced / resolve_actor_id / require_role（WMOM-20260716-05 P1）。

驗證「非破壞過渡（enforce=false）」與「cutover 後（enforce=true）」兩種行為。
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.auth.dependencies import is_auth_enforced, require_role, resolve_actor_id
from modules.auth.roles import Role
from modules.auth.tokens import create_access_token

_LEGACY_ID = "00000000-0000-0000-0000-0000000000aa"
_TOKEN_ID = "00000000-0000-0000-0000-0000000000bb"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)


def _client() -> TestClient:
    app = FastAPI()

    @app.post("/echo-actor")
    def echo_actor(body: dict, request: Request):
        return {"actor_id": resolve_actor_id(request, body.get("actor_id"))}

    @app.post("/leader-area", dependencies=[Depends(require_role(Role.LEADER, Role.SUPERVISOR))])
    def leader_area():
        return {"ok": True}

    return TestClient(app)


def _bearer(role: str = "leader", subject: str = _TOKEN_ID) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject=subject, role=role, name='U')}"}


# ── is_auth_enforced ────────────────────────────────────────────────
@pytest.mark.parametrize("val,expected", [("true", True), ("1", True), ("on", True),
                                          ("false", False), ("", False), ("no", False)])
def test_is_auth_enforced(monkeypatch, val, expected):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", val)
    assert is_auth_enforced() is expected


# ── resolve_actor_id ────────────────────────────────────────────────
def test_resolve_token_wins():
    resp = _client().post("/echo-actor", json={"actor_id": _LEGACY_ID}, headers=_bearer(subject=_TOKEN_ID))
    assert resp.json()["actor_id"] == _TOKEN_ID  # token 優先於 body


def test_resolve_legacy_body_when_not_enforced():
    resp = _client().post("/echo-actor", json={"actor_id": _LEGACY_ID})  # 無 token、enforce=false
    assert resp.status_code == 200 and resp.json()["actor_id"] == _LEGACY_ID


def test_resolve_no_token_enforced_401(monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert _client().post("/echo-actor", json={"actor_id": _LEGACY_ID}).status_code == 401


def test_resolve_invalid_token_401():
    resp = _client().post("/echo-actor", json={"actor_id": _LEGACY_ID},
                          headers={"Authorization": "Bearer garbage.tok.en"})
    assert resp.status_code == 401


def test_resolve_dev_fallback_when_no_body(monkeypatch):
    monkeypatch.setenv("WMOM_DEV_MODE", "true")
    resp = _client().post("/echo-actor", json={})  # 無 token、無 body actor_id、dev
    assert resp.status_code == 200 and resp.json()["actor_id"] == "00000000-0000-0000-0000-000000000001"


def test_resolve_missing_actor_id_400():
    resp = _client().post("/echo-actor", json={})  # 無 token、無 body、非 dev、非 enforce
    assert resp.status_code == 400


# ── require_role（enforce-aware）─────────────────────────────────────
def test_require_role_lenient_when_not_enforced():
    # enforce=false → 放行，即使無 token / 角色不符
    assert _client().post("/leader-area").status_code == 200


def test_require_role_enforced_allows_matching(monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert _client().post("/leader-area", headers=_bearer(role="leader")).status_code == 200


def test_require_role_enforced_admin_always(monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert _client().post("/leader-area", headers=_bearer(role="admin")).status_code == 200


def test_require_role_enforced_forbids_other(monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert _client().post("/leader-area", headers=_bearer(role="employee")).status_code == 403


def test_require_role_enforced_no_token_401(monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert _client().post("/leader-area").status_code == 401


def test_require_role_enforced_dev_fallback(monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    monkeypatch.setenv("WMOM_DEV_MODE", "true")  # dev fallback = admin → 放行
    assert _client().post("/leader-area").status_code == 200
