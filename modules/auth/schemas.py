"""auth API 的 pydantic schema（DEC-20260716-01）。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .roles import Role


class LoginRequest(BaseModel):
    """``POST /api/auth/login`` 請求體。"""

    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class ActorInfo(BaseModel):
    """已驗證主體的公開資訊（回前端 / 稽核用）。"""

    id: str
    name: str
    role: Role


class TokenResponse(BaseModel):
    """登入成功回傳：JWT + 主體資訊。"""

    access_token: str
    token_type: str = "bearer"
    actor: ActorInfo


class CreateUserRequest(BaseModel):
    """``POST /api/auth/users``（admin 建帳）請求體。"""

    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=256)  # 密碼政策：至少 8 碼
    name: str = Field(min_length=1, max_length=256)
    role: Role


class UserInfo(BaseModel):
    """使用者的公開資訊（**不含密碼雜湊**）。"""

    id: str
    username: str
    name: str
    role: Role
    is_active: bool
