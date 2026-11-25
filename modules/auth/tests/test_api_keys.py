"""外部系統的 API 金鑰（WMOM-20261125-02）：store、驗證 dependency、admin 管理端點。

**金鑰與帳號一律執行期生成**（原始碼中沒有任何金鑰字面值），與 ``test_admin_api.py`` 同一個測試衛生原則。
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path
from typing import Iterator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.auth import api_keys as ak
from modules.auth.repository import SqlApiKeyStore
from modules.auth.routers import router as auth_router
from modules.auth.tokens import create_access_token


@pytest.fixture(autouse=True)
def _setup(monkeypatch) -> Iterator[None]:
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)
    ak.set_api_key_store(ak.InMemoryApiKeyStore())
    yield
    ak.set_api_key_store(None)


def _admin_client() -> TestClient:
    app = FastAPI()
    app.include_router(auth_router)
    return TestClient(app)


def _bearer(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject=f'{role}-1', role=role, name=role)}"}


def _protected_client(scope: str = ak.SCOPE_EXTERNAL_READ) -> TestClient:
    app = FastAPI()

    @app.get("/probe")
    def probe(client: ak.ExternalClient = Depends(ak.require_api_key(scope))) -> dict[str, str]:
        return {"key_id": client.key_id, "name": client.name, "scope": client.scope}

    return TestClient(app)


# ── 金鑰與 store ───────────────────────────────────────────────────────────


def test_issued_key_is_stored_only_as_a_hash() -> None:
    store = ak.InMemoryApiKeyStore()
    record, key = ak.issue_api_key(store, "  rag-assistant  ", created_by="admin-1")
    assert key.startswith(ak.API_KEY_PREFIX) and len(key) > 40
    assert record.name == "rag-assistant" and record.scope == ak.SCOPE_EXTERNAL_READ and record.is_active
    assert record.key_hash == ak.api_key_digest(key) and key not in repr(record)
    assert key.startswith(record.prefix) and len(record.prefix) < 12, "前綴只夠辨識，不足以猜出金鑰"
    assert store.get_by_hash(ak.api_key_digest(key)) == record
    assert ak.issue_api_key(store, "second", created_by="admin-1")[1] != key


@pytest.mark.parametrize("name,scope", [("", ak.SCOPE_EXTERNAL_READ), ("   ", ak.SCOPE_EXTERNAL_READ),
                                        ("ok", "admin:everything")])
def test_issue_rejects_blank_name_and_unknown_scope(name: str, scope: str) -> None:
    with pytest.raises(ValueError):
        ak.issue_api_key(ak.InMemoryApiKeyStore(), name, created_by="a", scope=scope)


@pytest.mark.parametrize("make_store", [
    lambda tmp_path: ak.InMemoryApiKeyStore(),
    lambda tmp_path: SqlApiKeyStore(f"sqlite:///{tmp_path / 'auth.db'}"),
])
def test_store_roundtrip_revoke_and_touch(tmp_path, make_store) -> None:
    store = make_store(tmp_path)
    first, key = ak.issue_api_key(store, "first", created_by="admin-1")
    second, _ = ak.issue_api_key(store, "second", created_by="admin-2")
    assert {k.id for k in store.list_keys()} == {first.id, second.id}
    assert store.get_by_hash("0" * 64) is None

    store.touch(first.id, "2026-01-01T00:00:00+00:00")
    assert store.get_by_hash(first.key_hash).last_used_at == "2026-01-01T00:00:00+00:00"

    assert store.revoke(first.id, "2026-01-02T00:00:00+00:00") is True
    assert store.revoke(first.id, "2026-01-03T00:00:00+00:00") is True, "重複撤銷不算錯"
    revoked = store.get_by_hash(ak.api_key_digest(key))
    assert revoked.revoked_at == "2026-01-02T00:00:00+00:00" and not revoked.is_active, "保留第一次撤銷的時間"
    assert store.revoke("no-such-id", "2026-01-02T00:00:00+00:00") is False
    assert store.get_by_hash(second.key_hash).is_active


def test_sql_store_persists_across_instances(tmp_path) -> None:
    """伺服器重啟後，外部系統手上的金鑰要還能用。"""
    url = f"sqlite:///{tmp_path / 'auth.db'}"
    record, key = ak.issue_api_key(SqlApiKeyStore(url), "persist", created_by="admin-1")
    assert SqlApiKeyStore(url).get_by_hash(ak.api_key_digest(key)).id == record.id


def test_default_store_uses_the_auth_db_url(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WMOM_AUTH_DB_URL", f"sqlite:///{tmp_path / 'default.db'}")
    ak.set_api_key_store(None)
    store = ak.get_api_key_store()
    assert isinstance(store, SqlApiKeyStore) and ak.get_api_key_store() is store
    assert (tmp_path / "default.db").exists()


# ── 驗證 dependency ────────────────────────────────────────────────────────


def test_dependency_accepts_a_valid_key() -> None:
    record, key = ak.issue_api_key(ak.get_api_key_store(), "rag", created_by="admin-1")
    resp = _protected_client().get("/probe", headers={ak.API_KEY_HEADER: key})
    assert resp.status_code == 200
    assert resp.json() == {"key_id": record.id, "name": "rag", "scope": ak.SCOPE_EXTERNAL_READ}


def test_dependency_rejects_missing_wrong_and_revoked_keys() -> None:
    store = ak.get_api_key_store()
    record, key = ak.issue_api_key(store, "rag", created_by="admin-1")
    client = _protected_client()
    for headers in ({}, {ak.API_KEY_HEADER: ""}, {ak.API_KEY_HEADER: "abc"},
                    {ak.API_KEY_HEADER: ak.new_api_key()}, {"Authorization": f"Bearer {key}"}):
        resp = client.get("/probe", headers=headers)
        assert resp.status_code == 401 and resp.headers["WWW-Authenticate"] == "ApiKey"
    store.revoke(record.id, "2026-01-01T00:00:00+00:00")
    assert client.get("/probe", headers={ak.API_KEY_HEADER: key}).status_code == 401


def test_dependency_ignores_dev_mode_and_enforce_flag(monkeypatch) -> None:
    monkeypatch.setenv("WMOM_DEV_MODE", "true")
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "false")
    assert _protected_client().get("/probe").status_code == 401


def test_dependency_checks_scope() -> None:
    _, key = ak.issue_api_key(ak.get_api_key_store(), "rag", created_by="admin-1")
    resp = _protected_client(scope="other:scope").get("/probe", headers={ak.API_KEY_HEADER: key})
    assert resp.status_code == 403


def test_last_used_is_written_at_most_once_a_minute(monkeypatch) -> None:
    store = ak.get_api_key_store()
    record, key = ak.issue_api_key(store, "rag", created_by="admin-1")
    touches: list[str] = []
    original = store.touch
    monkeypatch.setattr(store, "touch", lambda key_id, used_at: (touches.append(key_id), original(key_id, used_at)))
    clock = [1000.0]
    monkeypatch.setattr(ak.time, "monotonic", lambda: clock[0])
    client = _protected_client()
    headers = {ak.API_KEY_HEADER: key}
    for _ in range(5):
        assert client.get("/probe", headers=headers).status_code == 200
    assert touches == [record.id] and store.get_by_hash(record.key_hash).last_used_at is not None
    clock[0] += 61.0
    client.get("/probe", headers=headers)
    assert touches == [record.id, record.id]


# ── admin 管理端點 ─────────────────────────────────────────────────────────


def test_admin_creates_lists_and_revokes_keys() -> None:
    client = _admin_client()
    created = client.post("/api/auth/api-keys", json={"name": "rag-assistant"}, headers=_bearer("admin"))
    assert created.status_code == 201
    body = created.json()
    key = body["key"]
    assert key.startswith(ak.API_KEY_PREFIX) and body["created_by"] == "admin-1"
    assert body["scope"] == ak.SCOPE_EXTERNAL_READ and body["revoked_at"] is None
    assert "key_hash" not in body

    listed = client.get("/api/auth/api-keys", headers=_bearer("admin"))
    assert listed.status_code == 200
    (item,) = listed.json()
    assert item["id"] == body["id"] and "key" not in item and "key_hash" not in item, "金鑰只在建立時出現一次"
    assert key not in listed.text

    assert _protected_client().get("/probe", headers={ak.API_KEY_HEADER: key}).status_code == 200
    revoked = client.delete(f"/api/auth/api-keys/{body['id']}", headers=_bearer("admin"))
    assert revoked.status_code == 200 and revoked.json()["revoked_at"] is not None
    assert _protected_client().get("/probe", headers={ak.API_KEY_HEADER: key}).status_code == 401
    assert client.delete("/api/auth/api-keys/no-such-id", headers=_bearer("admin")).status_code == 404


@pytest.mark.parametrize("method,path", [("post", "/api/auth/api-keys"), ("get", "/api/auth/api-keys"),
                                         ("delete", "/api/auth/api-keys/some-id")])
def test_key_management_is_admin_only(method: str, path: str) -> None:
    client = _admin_client()
    kwargs = {"json": {"name": "x"}} if method == "post" else {}
    assert getattr(client, method)(path, **kwargs).status_code == 401
    for role in ("employee", "leader", "supervisor", "treasury"):
        assert getattr(client, method)(path, headers=_bearer(role), **kwargs).status_code == 403
    assert not ak.get_api_key_store().list_keys()


def test_an_api_key_cannot_manage_keys() -> None:
    """外部系統不能用手上的金鑰替自己再發一把。"""
    _, key = ak.issue_api_key(ak.get_api_key_store(), "rag", created_by="admin-1")
    client = _admin_client()
    for headers in ({ak.API_KEY_HEADER: key}, {"Authorization": f"Bearer {key}"}):
        assert client.post("/api/auth/api-keys", json={"name": "more"}, headers=headers).status_code == 401
        assert client.get("/api/auth/api-keys", headers=headers).status_code == 401


def test_create_rejects_blank_name() -> None:
    client = _admin_client()
    assert client.post("/api/auth/api-keys", json={"name": ""}, headers=_bearer("admin")).status_code == 422
    assert client.post("/api/auth/api-keys", json={"name": "   "}, headers=_bearer("admin")).status_code == 422
