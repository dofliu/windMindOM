"""使用者存放層（seeded in-memory store，DEC-20260716-01）。

## 範圍（刻意最小、可換）

本增量只提供 **in-memory seeded store**，對映前端 ``mockUsers.ts`` 的 4 個 fixture
（Alice/Bob/Carol/Owner），讓 auth 機制（JWT + dependency + RBAC）能端到端跑起來與測試。

- **dev_mode**：seed 4 個 demo user（已知 dev 密碼），前端 mock login 可換成真 ``/auth/login``。
- **production（非 dev_mode）**：store **預設為空** → ``/auth/login`` 一律 401，直到接上
  真正的 DB-backed user 表 + 已佈建憑證。這是刻意的安全預設（不把 demo 密碼帶進 prod）。

## 下一步（follow-up，不在本增量）

換成 DB-backed ``UserRepository``（SQLAlchemy，比照 workflow repository 慣例）+ admin
建帳 API + 密碼政策。屆時只需替換 :func:`build_default_store` 回傳的實作。
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.dev_mode import is_dev_mode_enabled

from .passwords import hash_password, verify_password
from .roles import Role

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


def _demo_users() -> list[AuthUser]:
    """對映 frontend mockUsers.ts 的 4 個 fixture（id 與角色一致）。"""
    demo_hash = hash_password(_DEMO_PASSWORD)
    return [
        AuthUser("00000000-0000-0000-0000-0000000000a1", "alice", "Alice Chen", Role.EMPLOYEE, demo_hash),
        AuthUser("00000000-0000-0000-0000-0000000000a2", "bob", "Bob Lin", Role.LEADER, demo_hash),
        AuthUser("00000000-0000-0000-0000-0000000000a3", "carol", "Carol Wang", Role.TREASURY, demo_hash),
        AuthUser("00000000-0000-0000-0000-0000000000a4", "owner", "Owner (dev)", Role.ADMIN, demo_hash),
    ]


def build_default_store() -> InMemoryUserStore:
    """建預設 store：dev_mode → 4 個 demo user；production → 空（安全預設）。"""
    if is_dev_mode_enabled():
        return InMemoryUserStore(_demo_users())
    return InMemoryUserStore()
