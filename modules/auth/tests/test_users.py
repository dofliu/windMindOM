"""users store — 認證 / 停用 / 大小寫 / dev-vs-prod seed（DEC-20260716-01）。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.auth.passwords import hash_password
from modules.auth.roles import Role
from modules.auth.users import AuthUser, InMemoryUserStore, build_default_store


def _store_with(pw: str = "pw", *, active: bool = True) -> InMemoryUserStore:
    return InMemoryUserStore(
        [AuthUser("id-1", "Alice", "Alice Chen", Role.EMPLOYEE, hash_password(pw), is_active=active)]
    )


def test_authenticate_success():
    user = _store_with().authenticate("alice", "pw")
    assert user is not None and user.role is Role.EMPLOYEE


def test_authenticate_wrong_password():
    assert _store_with().authenticate("alice", "bad") is None


def test_authenticate_unknown_user():
    assert _store_with().authenticate("nobody", "pw") is None


def test_authenticate_inactive_user():
    assert _store_with(active=False).authenticate("alice", "pw") is None


def test_username_case_insensitive():
    assert _store_with().authenticate("ALICE", "pw") is not None


def test_build_default_store_dev_seeds_demo_users(monkeypatch):
    monkeypatch.setenv("WMOM_DEV_MODE", "true")
    store = build_default_store()
    # 對映 mockUsers.ts 的 4 個 fixture，demo 密碼 demo1234。
    for username, role in [("alice", Role.EMPLOYEE), ("bob", Role.LEADER),
                           ("carol", Role.TREASURY), ("owner", Role.ADMIN)]:
        user = store.authenticate(username, "demo1234")
        assert user is not None and user.role is role


def test_build_default_store_prod_is_empty(monkeypatch):
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    store = build_default_store()
    assert store.authenticate("alice", "demo1234") is None  # prod 無 demo user（安全預設）
