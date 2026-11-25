"""DB-backed user store（SQLAlchemy，WMOM-20260716-04，接 DEC-20260716-01 follow-up）。

把 M6-4 基礎層的 seeded in-memory store 換成可持久化的 SQL store，供 production 佈建
真實使用者。**非破壞**：與 :class:`modules.auth.users.InMemoryUserStore` 同介面
（``get_by_username`` / ``authenticate`` / ``add``），是 :func:`build_default_store` 的
drop-in production 實作；dev_mode 仍走 in-memory demo。

- 表：``auth_users``（自 ``metadata.create_all`` 建，無需 migration 工具）。
- DB 位置：``WMOM_AUTH_DB_URL``（預設 ``sqlite:///./wmom_auth.db``）。
- 密碼只存 PBKDF2 雜湊（見 ``passwords.py``），不存明文。
- 外部系統的 API 金鑰（``auth_api_keys``，WMOM-20261125-02）同一個 DB；只存 sha256，見 ``api_keys.py``。
"""

from __future__ import annotations

from sqlalchemy import Boolean, String, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .api_keys import ApiKey
from .passwords import verify_password
from .roles import Role
from .users import AuthUser


class AuthBase(DeclarativeBase):
    """auth module 專屬 ORM base（與 workflow 的 Base 分離，避免跨模組耦合）。"""


class UserRow(AuthBase):
    """``auth_users`` 資料列。"""

    __tablename__ = "auth_users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(32))
    password_hash: Mapped[str] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def to_auth_user(self) -> AuthUser:
        """轉回 domain 的 :class:`AuthUser`。"""
        return AuthUser(
            id=self.id,
            username=self.username,
            name=self.name,
            role=Role(self.role),
            password_hash=self.password_hash,
            is_active=self.is_active,
        )


class SqlUserStore:
    """SQLAlchemy 支撐的 user store。介面與 ``InMemoryUserStore`` 一致。"""

    def __init__(self, db_url: str = "sqlite:///./wmom_auth.db") -> None:
        self._engine = create_engine(db_url, future=True)
        AuthBase.metadata.create_all(self._engine)
        self._sessionmaker = sessionmaker(self._engine, expire_on_commit=False, future=True)

    def add(self, user: AuthUser) -> None:
        """新增或以 username 為鍵覆寫一個 user（upsert）。"""
        with self._sessionmaker() as sess:
            existing = sess.scalar(select(UserRow).where(UserRow.username == user.username.lower()))
            if existing is None:
                sess.add(
                    UserRow(
                        id=user.id,
                        username=user.username.lower(),
                        name=user.name,
                        role=user.role.value,
                        password_hash=user.password_hash,
                        is_active=user.is_active,
                    )
                )
            else:
                existing.name = user.name
                existing.role = user.role.value
                existing.password_hash = user.password_hash
                existing.is_active = user.is_active
            sess.commit()

    def get_by_username(self, username: str) -> AuthUser | None:
        """依 username（大小寫不敏感）取 user；無則 ``None``。"""
        with self._sessionmaker() as sess:
            row = sess.scalar(select(UserRow).where(UserRow.username == username.strip().lower()))
            return row.to_auth_user() if row is not None else None

    def authenticate(self, username: str, password: str) -> AuthUser | None:
        """驗證帳密，成功回 :class:`AuthUser`，失敗（含停用/查無）回 ``None``。"""
        user = self.get_by_username(username)
        if user is None or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    def list_users(self) -> list[AuthUser]:
        """列出所有 user（不含密碼雜湊以外的敏感資料；hash 仍在 domain 物件內，呼叫端勿外洩）。"""
        with self._sessionmaker() as sess:
            rows = sess.scalars(select(UserRow).order_by(UserRow.username)).all()
            return [r.to_auth_user() for r in rows]

    def count(self) -> int:
        """user 總數（用於 bootstrap 判斷 store 是否為空）。"""
        with self._sessionmaker() as sess:
            return int(sess.scalar(select(func.count()).select_from(UserRow)) or 0)


class ApiKeyRow(AuthBase):
    """``auth_api_keys`` 資料列（外部系統的 API 金鑰，WMOM-20261125-02）。"""

    __tablename__ = "auth_api_keys"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    prefix: Mapped[str] = mapped_column(String(32))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    scope: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))
    created_by: Mapped[str] = mapped_column(String(64))
    last_used_at: Mapped[str | None] = mapped_column(String(40), nullable=True, default=None)
    revoked_at: Mapped[str | None] = mapped_column(String(40), nullable=True, default=None)

    def to_api_key(self) -> ApiKey:
        """轉回 domain 的 :class:`ApiKey`。"""
        return ApiKey(
            id=self.id,
            name=self.name,
            prefix=self.prefix,
            key_hash=self.key_hash,
            scope=self.scope,
            created_at=self.created_at,
            created_by=self.created_by,
            last_used_at=self.last_used_at,
            revoked_at=self.revoked_at,
        )


class SqlApiKeyStore:
    """SQLAlchemy 支撐的 API 金鑰 store。介面與 ``InMemoryApiKeyStore`` 一致。"""

    def __init__(self, db_url: str = "sqlite:///./wmom_auth.db") -> None:
        self._engine = create_engine(db_url, future=True)
        AuthBase.metadata.create_all(self._engine)
        self._sessionmaker = sessionmaker(self._engine, expire_on_commit=False, future=True)

    def add(self, key: ApiKey) -> None:
        """新增一把金鑰。"""
        with self._sessionmaker() as sess:
            sess.add(
                ApiKeyRow(
                    id=key.id,
                    name=key.name,
                    prefix=key.prefix,
                    key_hash=key.key_hash,
                    scope=key.scope,
                    created_at=key.created_at,
                    created_by=key.created_by,
                    last_used_at=key.last_used_at,
                    revoked_at=key.revoked_at,
                )
            )
            sess.commit()

    def get_by_hash(self, key_hash: str) -> ApiKey | None:
        """依 sha256 取金鑰；無則 ``None``。"""
        with self._sessionmaker() as sess:
            row = sess.scalar(select(ApiKeyRow).where(ApiKeyRow.key_hash == key_hash))
            return row.to_api_key() if row is not None else None

    def list_keys(self) -> list[ApiKey]:
        """列出全部金鑰（依建立時間；含已撤銷的）。"""
        with self._sessionmaker() as sess:
            rows = sess.scalars(select(ApiKeyRow).order_by(ApiKeyRow.created_at, ApiKeyRow.id)).all()
            return [r.to_api_key() for r in rows]

    def revoke(self, key_id: str, revoked_at: str) -> bool:
        """撤銷金鑰；不存在回 False，已撤銷的維持原撤銷時間並回 True。"""
        with self._sessionmaker() as sess:
            row = sess.get(ApiKeyRow, key_id)
            if row is None:
                return False
            if row.revoked_at is None:
                row.revoked_at = revoked_at
                sess.commit()
            return True

    def touch(self, key_id: str, used_at: str) -> None:
        """記下最近一次使用的時間。"""
        with self._sessionmaker() as sess:
            row = sess.get(ApiKeyRow, key_id)
            if row is not None:
                row.last_used_at = used_at
                sess.commit()
