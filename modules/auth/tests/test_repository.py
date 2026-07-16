"""SqlUserStore + build_default_store prod 路徑（WMOM-20260716-04）。

密碼一律 ``secrets`` 執行期生成（不寫死字面值）。
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.auth.passwords import hash_password
from modules.auth.repository import SqlUserStore
from modules.auth.roles import Role
from modules.auth.users import AuthUser, build_default_store

_PW = secrets.token_urlsafe(12)
_OTHER_PW = secrets.token_urlsafe(12)


@pytest.fixture
def store(tmp_path):
    return SqlUserStore(f"sqlite:///{tmp_path}/auth.db")


def _user(username: str = "alice", role: Role = Role.EMPLOYEE, pw: str = _PW, active: bool = True) -> AuthUser:
    return AuthUser(
        id=f"id-{username}", username=username, name=username.title(),
        role=role, password_hash=hash_password(pw), is_active=active,
    )


def test_add_and_get(store):
    store.add(_user())
    u = store.get_by_username("alice")
    assert u is not None and u.role is Role.EMPLOYEE and u.id == "id-alice"


def test_get_case_insensitive(store):
    store.add(_user(username="alice"))
    assert store.get_by_username("ALICE") is not None


def test_get_unknown_returns_none(store):
    assert store.get_by_username("ghost") is None


def test_authenticate_ok_wrong_inactive(store):
    store.add(_user(username="alice"))
    store.add(_user(username="bob", active=False))
    assert store.authenticate("alice", _PW) is not None
    assert store.authenticate("alice", _OTHER_PW) is None
    assert store.authenticate("bob", _PW) is None  # inactive
    assert store.authenticate("ghost", _PW) is None


def test_upsert_by_username(store):
    store.add(_user(username="alice", role=Role.EMPLOYEE))
    store.add(_user(username="alice", role=Role.SUPERVISOR))  # 同 username → 覆寫
    assert store.count() == 1
    assert store.get_by_username("alice").role is Role.SUPERVISOR


def test_list_users_sorted_and_count(store):
    store.add(_user(username="carol"))
    store.add(_user(username="alice"))
    store.add(_user(username="bob"))
    assert [u.username for u in store.list_users()] == ["alice", "bob", "carol"]
    assert store.count() == 3


def test_persistence_across_instances(tmp_path):
    url = f"sqlite:///{tmp_path}/persist.db"
    SqlUserStore(url).add(_user(username="alice"))
    # 新 instance 指向同一 DB → 看得到先前寫入（真的落地）。
    assert SqlUserStore(url).get_by_username("alice") is not None


def test_build_default_store_prod_sql_and_bootstrap_admin(monkeypatch, tmp_path):
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    monkeypatch.setenv("WMOM_AUTH_DB_URL", f"sqlite:///{tmp_path}/prod.db")
    monkeypatch.setenv("WMOM_ADMIN_USER", "root")
    monkeypatch.setenv("WMOM_ADMIN_PASSWORD", _PW)
    store = build_default_store()
    admin = store.authenticate("root", _PW)
    assert admin is not None and admin.role is Role.ADMIN


def test_build_default_store_prod_empty_without_bootstrap(monkeypatch, tmp_path):
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    monkeypatch.setenv("WMOM_AUTH_DB_URL", f"sqlite:///{tmp_path}/empty.db")
    monkeypatch.delenv("WMOM_ADMIN_USER", raising=False)
    monkeypatch.delenv("WMOM_ADMIN_PASSWORD", raising=False)
    store = build_default_store()
    assert store.count() == 0  # 安全預設：空、無人可登入
