"""auth FastAPI router：登入發 token + 查目前身分（DEC-20260716-01）。

掛載於主 app（``modules/monitoring/server/app.py``）的 ``/api/auth`` 前綴。
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from ..api_keys import ApiKey, get_api_key_store, issue_api_key
from ..dependencies import Actor, get_current_actor, require_roles
from ..passwords import hash_password
from ..roles import Role
from ..schemas import (
    ActorInfo,
    ApiKeyCreated,
    ApiKeyInfo,
    CreateApiKeyRequest,
    CreateUserRequest,
    LoginRequest,
    TokenResponse,
    UserInfo,
)
from ..tokens import create_access_token
from ..users import AuthUser, UserStore, build_default_store

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 模組層 user store，lazy 建立（首次使用才建，避免 import 時就碰 DB/檔案系統）。
_store: UserStore | None = None


def _get_store() -> UserStore:
    """取得（或首次建立）user store。dev_mode → in-memory demo；prod → SqlUserStore。"""
    global _store
    if _store is None:
        _store = build_default_store()
    return _store


def set_user_store(store: UserStore) -> None:
    """覆寫模組層 user store（測試 / 注入 DB store 用）。"""
    global _store
    _store = store


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    """以帳密登入，成功回 JWT + 主體資訊；失敗 401。"""
    user = _get_store().authenticate(payload.username, payload.password)
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


def _to_user_info(user: AuthUser) -> UserInfo:
    return UserInfo(id=user.id, username=user.username, name=user.name, role=user.role, is_active=user.is_active)


@router.post("/users", response_model=UserInfo, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: CreateUserRequest,
    _actor: Actor = Depends(require_roles(Role.ADMIN)),
) -> UserInfo:
    """admin 建立使用者（WMOM-20260716-04）。username 重複回 409。"""
    store = _get_store()
    if store.get_by_username(payload.username) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username 已存在")
    user = AuthUser(
        id=str(uuid4()),
        username=payload.username,
        name=payload.name,
        role=payload.role,
        password_hash=hash_password(payload.password),
    )
    store.add(user)
    return _to_user_info(user)


@router.get("/users", response_model=list[UserInfo])
def list_users(_actor: Actor = Depends(require_roles(Role.ADMIN))) -> list[UserInfo]:
    """admin 列出所有使用者（不含密碼雜湊）。"""
    return [_to_user_info(u) for u in _get_store().list_users()]


# ── 外部系統的 API 金鑰（WMOM-20261125-02）────────────────────────────────


def _to_api_key_info(key: ApiKey) -> ApiKeyInfo:
    return ApiKeyInfo(
        id=key.id,
        name=key.name,
        prefix=key.prefix,
        scope=key.scope,
        created_at=key.created_at,
        created_by=key.created_by,
        last_used_at=key.last_used_at,
        revoked_at=key.revoked_at,
    )


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
def create_api_key(
    payload: CreateApiKeyRequest,
    actor: Actor = Depends(require_roles(Role.ADMIN)),
) -> ApiKeyCreated:
    """admin 發一把外部系統的唯讀金鑰。金鑰只在這個回應出現一次，之後查不到。"""
    try:
        record, key = issue_api_key(get_api_key_store(), payload.name, created_by=actor.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ApiKeyCreated(**_to_api_key_info(record).model_dump(), key=key)


@router.get("/api-keys", response_model=list[ApiKeyInfo])
def list_api_keys(_actor: Actor = Depends(require_roles(Role.ADMIN))) -> list[ApiKeyInfo]:
    """admin 列出全部金鑰（含已撤銷的；不含金鑰與雜湊）。"""
    return [_to_api_key_info(k) for k in get_api_key_store().list_keys()]


@router.delete("/api-keys/{key_id}", response_model=ApiKeyInfo)
def revoke_api_key(key_id: str, _actor: Actor = Depends(require_roles(Role.ADMIN))) -> ApiKeyInfo:
    """admin 撤銷一把金鑰（立刻失效；紀錄保留）。不存在回 404。"""
    store = get_api_key_store()
    revoked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not store.revoke(key_id, revoked_at):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API 金鑰不存在")
    for key in store.list_keys():
        if key.id == key_id:
            return _to_api_key_info(key)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API 金鑰不存在")
