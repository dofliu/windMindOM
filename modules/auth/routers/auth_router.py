"""auth FastAPI router：登入發 token + 查目前身分（DEC-20260716-01）。

掛載於主 app（``modules/monitoring/server/app.py``）的 ``/api/auth`` 前綴。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import Actor, get_current_actor
from ..schemas import ActorInfo, LoginRequest, TokenResponse
from ..tokens import create_access_token
from ..users import InMemoryUserStore, build_default_store

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 模組層預設 store（dev_mode → demo users；prod → 空）。測試可用 set_user_store 覆寫。
_store: InMemoryUserStore = build_default_store()


def set_user_store(store: InMemoryUserStore) -> None:
    """覆寫模組層 user store（測試 / 未來接 DB store 用）。"""
    global _store
    _store = store


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    """以帳密登入，成功回 JWT + 主體資訊；失敗 401。"""
    user = _store.authenticate(payload.username, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="帳號或密碼錯誤",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(subject=user.id, role=user.role.value, name=user.name)
    return TokenResponse(
        access_token=token,
        actor=ActorInfo(id=user.id, name=user.name, role=user.role),
    )


@router.get("/me", response_model=ActorInfo)
def me(actor: Actor = Depends(get_current_actor)) -> ActorInfo:
    """回傳目前請求的已驗證身分（無 / 無效 token 依 dev_mode → fallback 或 401）。"""
    return ActorInfo(id=actor.id, name=actor.name, role=actor.role)
