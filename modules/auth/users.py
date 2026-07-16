"""使用者存放層（seeded in-memory store，DEC-20260716-01）。

## store 選擇（:func:`build_default_store`）

- **dev_mode**：``InMemoryUserStore`` seed 4 個 demo user（對映 ``mockUsers.ts``），前端 mock
  login 可換成真 ``/auth/login``。
- **production（非 dev_mode）**：``SqlUserStore``（見 ``repository.py``，WMOM-20260716-04）——
  DB 持久化 + admin 由 ``/api/auth/users`` 建帳。首個 admin 由 ``WMOM_ADMIN_USER``/
  ``WMOM_ADMIN_PASSWORD`` env bootstrap（store 為空時），避免雞生蛋死結；未設則 store 為空、
  無人可登入（安全預設，不把 demo 密碼帶進 prod）。

兩種 store 同滿足 :class:`UserStore` 介面，可互換。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from shared.dev_mode import is_dev_mode_enabled

from .passwords import hash_password, verify_password
from .roles import Role

_log = logging.getLogger(__name__)

# demo 用固定 dev 密碼；僅在 dev_mode seed，production store 不含（見模組 docstring）。
_DEMO_PASSWORD = "demo1234"  # noqa: S105


@dataclass(frozen=True)
class AuthUser:
    """一個可登入的使用者。``id`` 即簽核/派工 action 帶的 ``actor_id``。"""

    id: str
    username: str
    name: str
    role: Role
    password_hash: str
    is_active: bool = True


class UserStore(Protocol):
    """user store 介面。``InMemoryUserStore``（dev）與 ``SqlUserStore``（prod）皆滿足。"""

    def add(self, user: AuthUser) -> None: ...
    def get_by_username(self, username: str) -> AuthUser | None: ...
    def authenticate(self, username: str, password: str) -> AuthUser | None: ...
    def list_users(self) -> list[AuthUser]: ...
    def count(self) -> int: ...


class InMemoryUserStore:
    """以 username 為 key 的記憶體 user store。"""

    def __init__(self, users: list[AuthUser] | None = None) -> None:
        self._by_username: dict[str, AuthUser] = {}
        for user in users or []:
            self.add(user)

    def add(self, user: AuthUser) -> None:
        """加入（或覆寫）一個 user。"""
        self._by_username[user.username.lower()] = user

    def get_by_username(self, username: str) -> AuthUser | None:
        """依 username（大小寫不敏感）取 user；無則 ``None``。"""
        return self._by_username.get(username.strip().lower())

    def authenticate(self, username: str, password: str) -> AuthUser | None:
        """驗證帳密，成功回 :class:`AuthUser`，失敗（含停用/查無）回 ``None``。"""
        user = self.get_by_username(username)
        if user is None or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    def list_users(self) -> list[AuthUser]:
        """列出所有 user（依 username 排序）。"""
        return [self._by_username[k] for k in sorted(self._by_username)]

    def count(self) -> int:
        """user 總數。"""
        return len(self._by_username)


def _demo_users() -> list[AuthUser]:
    """對映 frontend mockUsers.ts 的 4 個 fixture（id 與角色一致）。"""
    demo_hash = hash_password(_DEMO_PASSWORD)
    return [
        AuthUser("00000000-0000-0000-0000-0000000000a1", "alice", "Alice Chen", Role.EMPLOYEE, demo_hash),
        AuthUser("00000000-0000-0000-0000-0000000000a2", "bob", "Bob Lin", Role.LEADER, demo_hash),
        AuthUser("00000000-0000-0000-0000-0000000000a3", "carol", "Carol Wang", Role.TREASURY, demo_hash),
        AuthUser("00000000-0000-0000-0000-0000000000a4", "owner", "Owner (dev)", Role.ADMIN, demo_hash),
    ]


def build_default_store() -> UserStore:
    """建預設 store：dev_mode → in-memory demo；production → SQL store（+ bootstrap admin）。"""
    if is_dev_mode_enabled():
        return InMemoryUserStore(_demo_users())
    from .repository import SqlUserStore  # lazy import：避免 users ↔ repository 循環

    db_url = os.environ.get("WMOM_AUTH_DB_URL", "").strip() or "sqlite:///./wmom_auth.db"
    store = SqlUserStore(db_url)
    _maybe_bootstrap_admin(store)
    return store


def _maybe_bootstrap_admin(store: UserStore) -> None:
    """production store 為空時，若設了 ``WMOM_ADMIN_USER``/``WMOM_ADMIN_PASSWORD`` 就建初始 admin；否則 warn。

    避免「空 store → 無人可登入 → 也無法用 admin API 建第一個帳」的雞生蛋死結。
    """
    if store.count() > 0:
        return
    admin_user = os.environ.get("WMOM_ADMIN_USER", "").strip()
    admin_pw = os.environ.get("WMOM_ADMIN_PASSWORD", "")
    if admin_user and admin_pw:
        store.add(
            AuthUser(
                id=str(uuid4()),
                username=admin_user,
                name=os.environ.get("WMOM_ADMIN_NAME", "Administrator").strip() or "Administrator",
                role=Role.ADMIN,
                password_hash=hash_password(admin_pw),
            )
        )
        _log.info("已 bootstrap 初始 admin '%s'", admin_user)
    else:
        _log.warning(
            "production auth store 為空且未設 WMOM_ADMIN_USER/WMOM_ADMIN_PASSWORD → 目前無人可登入；"
            "請設環境變數佈建初始 admin。"
        )
