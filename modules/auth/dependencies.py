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

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status

from shared.dev_mode import is_dev_mode_enabled

from .roles import Role
from .tokens import TokenError, decode_access_token

# dev_mode 無 token 時的 fallback 身分（沿用 workOrderService.ts 的 DEV_ACTOR_ID）。
_DEV_ACTOR_ID = "00000000-0000-0000-0000-000000000001"


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
