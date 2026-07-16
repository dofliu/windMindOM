"""FastAPI 授權 dependency（DEC-20260716-01）。

## 非破壞式接入策略

- ``get_current_actor``：**opt-in per route**。既有 router 尚未採用它 → 行為零改變
  （仍收 body 的 ``actor_id``）。新 route（如 ``/auth/me``）與日後逐支遷移的 router 才用。
- 無 / 無效 token 時的行為：
    - **dev_mode**：fallback 到 dev actor（保留單人跑完整 demo lifecycle 的能力）。
    - **production**：raise 401（採用本 dependency 的 route 即受保護）。

這樣「加了 auth 機制」與「開始強制 auth」是兩個獨立步驟，可分批、可審、可回退。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status

from shared.dev_mode import is_dev_mode_enabled

from .roles import Role
from .tokens import TokenError, decode_access_token

# dev_mode 無 token 時的 fallback 身分（沿用 workOrderService.ts 的 DEV_ACTOR_ID）。
_DEV_ACTOR_ID = "00000000-0000-0000-0000-000000000001"

# 授權強制旗標（WMOM-20260716-05 P1/P3 cutover）。預設 false = 雙模式過渡期。
_AUTH_ENFORCE_ENV = "WMOM_AUTH_ENFORCE"
_TRUTHY = frozenset({"true", "1", "yes", "on"})


def is_auth_enforced() -> bool:
    """讀 ``WMOM_AUTH_ENFORCE``；``true``/``1``/``yes``/``on`` → True，其餘 False。

    - **false（預設，過渡期）**：業務 router 走雙模式——有 token 用 token，無 token
      沿用 body ``actor_id``（現有行為），``require_role`` 放行。
    - **true（cutover 後）**：無 token → 401，``require_role`` 實際檢查角色。
    每次呼叫都重讀 env（test 友善）。
    """
    return os.environ.get(_AUTH_ENFORCE_ENV, "").strip().lower() in _TRUTHY


@dataclass(frozen=True)
class Actor:
    """已驗證的操作主體。``id`` 即 signoff/dispatch 的 ``actor_id``。"""

    id: str
    name: str
    role: Role


def _dev_fallback_actor() -> Actor:
    """dev_mode 專用 fallback 身分（ADMIN 全權，方便單人跑 demo）。"""
    return Actor(id=_DEV_ACTOR_ID, name="Dev User (fallback)", role=Role.ADMIN)


def _extract_bearer_token(request: Request) -> str | None:
    """從 ``Authorization: Bearer <token>`` 取出 token；無則 ``None``。"""
    header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if header.startswith(prefix):
        return header[len(prefix):].strip() or None
    return None


def get_current_actor(request: Request) -> Actor:
    """解析請求的身分。

    有效 token → token 的主體；無 / 無效 token → dev_mode fallback 或 401。

    Raises:
        HTTPException: 401（非 dev_mode 且無有效 token）。
    """
    token = _extract_bearer_token(request)
    if token is not None:
        try:
            payload = decode_access_token(token)
        except TokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"invalid token: {exc}",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        try:
            role = Role(payload["role"])
        except (KeyError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="token role 無法解析",
            ) from exc
        return Actor(id=str(payload["sub"]), name=str(payload.get("name", "")), role=role)

    if is_dev_mode_enabled():
        return _dev_fallback_actor()

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="需要登入（缺 Bearer token）",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_roles(*allowed: Role):
    """產生一個 dependency：actor 角色須屬 ``allowed`` 否則 403。

    ``Role.ADMIN`` 永遠通過（全權）。

    Args:
        *allowed: 允許的角色集合。

    Returns:
        可放進 ``Depends(...)`` 的 dependency callable。
    """
    allowed_set = set(allowed)

    def _dependency(actor: Actor = Depends(get_current_actor)) -> Actor:
        if actor.role is Role.ADMIN or actor.role in allowed_set:
            return actor
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"角色 {actor.role.value} 無此操作權限",
        )

    return _dependency


# ─────────────────────────────────────────────────────────────────────────
# WMOM-20260716-05 P1：業務 router 雙模式接入（非破壞，enforce=false 保留現有行為）
# ─────────────────────────────────────────────────────────────────────────


def resolve_actor_id(request: Request, body_actor_id: str | None) -> str:
    """雙模式解析 request 的 actor_id。

    - 有有效 Bearer token → token 的 ``sub``（已驗證，優先）。
    - 無 token：
        - ``WMOM_AUTH_ENFORCE=true`` → 401（需登入）。
        - 否則（過渡期）→ 沿用 body 的 ``actor_id``（現有行為）；dev_mode 下可 fallback。

    Args:
        request: 進來的請求（讀 Authorization header）。
        body_actor_id: 請求體帶的 legacy ``actor_id``（過渡期用）。

    Returns:
        有效的 actor_id 字串（交給 domain / repository）。

    Raises:
        HTTPException: 401（token 無效，或 enforce 下無 token）；400（過渡期連 body actor_id 都缺）。
    """
    token = _extract_bearer_token(request)
    if token is not None:
        try:
            payload = decode_access_token(token)
        except TokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"invalid token: {exc}",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        return str(payload["sub"])

    if is_auth_enforced():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要登入（缺 Bearer token）",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 過渡期（未強制）：沿用 legacy body actor_id。
    if body_actor_id:
        return body_actor_id
    if is_dev_mode_enabled():
        return _DEV_ACTOR_ID
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="缺 actor_id（過渡期需帶 body actor_id 或登入）",
    )


def resolve_actor_id_optional(request: Request, body_actor_id: str | None) -> str | None:
    """同 :func:`resolve_actor_id`，但允許「無 actor」（系統 / 匿名動作）。

    用於 actor 可省略的端點（如系統自動 inventory adjust——無真人簽）。

    - 有有效 token → sub。
    - 無 token：``WMOM_AUTH_ENFORCE=true`` → 401；否則回 ``body_actor_id``（**可為 None**，
      不 dev fallback、不 400）。
    """
    token = _extract_bearer_token(request)
    if token is not None:
        try:
            payload = decode_access_token(token)
        except TokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"invalid token: {exc}",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        return str(payload["sub"])
    if is_auth_enforced():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要登入（缺 Bearer token）",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return body_actor_id  # 過渡期：可為 None（系統 adjust）


def require_role(*allowed: Role):
    """enforce-aware 角色閘門 dependency（業務 router 用）。

    - ``WMOM_AUTH_ENFORCE=false``（過渡期）→ **放行**（role 尚未可信，保留現有行為）。
    - ``true`` → 檢查 token 角色（``ADMIN`` 全權），不符 403、無 token 401。

    與 :func:`require_roles`（永遠強制，auth 管理端點用）刻意分開。
    """
    allowed_set = set(allowed)

    def _dependency(request: Request) -> None:
        if not is_auth_enforced():
            return
        actor = get_current_actor(request)  # 強制模式：token / dev-fallback / 401
        if actor.role is Role.ADMIN or actor.role in allowed_set:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"角色 {actor.role.value} 無此操作權限",
        )

    return _dependency


def require_authenticated():
    """enforce-aware「需登入」閘門（不限角色）。給無角色限制、但強制後需登入的端點用。

    - ``WMOM_AUTH_ENFORCE=false`` → 放行；``true`` → 需有效 token（任何角色），無則 401。
    """

    def _dependency(request: Request) -> None:
        if not is_auth_enforced():
            return
        get_current_actor(request)  # token / dev-fallback / 401

    return _dependency
