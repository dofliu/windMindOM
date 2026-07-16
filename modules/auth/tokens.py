"""HS256 JWT 簽發與驗證（純 stdlib，DEC-20260716-01）。

## 為什麼自己實作而不用 PyJWT

- HS256 只需 ``hmac`` + ``hashlib``（stdlib），不需 ``cryptography`` 原生套件；
  PyJWT 為了 RS/ES 演算法會 import ``cryptography``（原生 build，部署與 sandbox 都易卡）。
- 單客戶 on-prem PoC 用對稱金鑰 HS256 已足夠；**零新依賴**也直接呼應
  ``PROJECT_REVIEW`` F5 的部署 footprint 顧慮（不再往 image 疊 crypto 原生輪子）。
- 未來要非對稱金鑰 / 金鑰輪替，再換 PyJWT+cryptography（介面已隔離在本檔）。

## 金鑰

從環境變數 ``WMOM_JWT_SECRET`` 讀。**production（非 dev_mode）未設會 raise**，
杜絕 silent insecure default；dev_mode 下用 per-process 隨機臨時金鑰（不寫死任何字面值）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from shared.dev_mode import is_dev_mode_enabled

_ALG = "HS256"
_JWT_SECRET_ENV = "WMOM_JWT_SECRET"
_DEFAULT_TTL_SECONDS = 12 * 60 * 60  # 12 小時

# dev_mode 且未設 env 金鑰時，per-process 生成的臨時金鑰（不寫死任何字面值）。
# 同一 process 內一致（tokens 簽/驗一致）；重啟即換 → dev token 不跨重啟，安全且無 hardcoded secret。
_dev_secret_cache: str | None = None


class TokenError(Exception):
    """token 無效 / 過期 / 簽章不符時拋出。"""


def _get_secret() -> str:
    """取 JWT 簽章金鑰。

    Returns:
        金鑰字串。

    Raises:
        RuntimeError: 非 dev_mode 且 ``WMOM_JWT_SECRET`` 未設（避免不安全預設）。
    """
    secret = os.environ.get(_JWT_SECRET_ENV, "").strip()
    if secret:
        return secret
    if is_dev_mode_enabled():
        global _dev_secret_cache
        if _dev_secret_cache is None:
            _dev_secret_cache = secrets.token_urlsafe(32)
        return _dev_secret_cache
    raise RuntimeError(
        f"{_JWT_SECRET_ENV} 未設定：production 必須提供 JWT 金鑰。"
        " 設 WMOM_DEV_MODE=true 可用 dev 金鑰（僅測試/demo）。"
    )


def _b64url_encode(raw: bytes) -> str:
    """base64url 無 padding 編碼（JWT 標準）。"""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    """base64url 無 padding 解碼（補回 padding）。"""
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _sign(signing_input: bytes, secret: str) -> str:
    """對 ``header.payload`` 以 HMAC-SHA256 簽章，回 base64url 字串。"""
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return _b64url_encode(sig)


def create_access_token(
    *,
    subject: str,
    role: str,
    name: str,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    now: float | None = None,
) -> str:
    """簽發一個 HS256 access token。

    Args:
        subject: 使用者唯一識別（actor_id / UUID 字串），放進 ``sub``。
        role: :class:`modules.auth.roles.Role` 的 value。
        name: 顯示名（放進 ``name``，方便前端與稽核）。
        ttl_seconds: 有效秒數，預設 12 小時。
        now: 覆寫「現在」時間（epoch 秒），僅測試用；預設 ``time.time()``。

    Returns:
        編碼後的 JWT 字串。
    """
    issued_at = int(now if now is not None else time.time())
    header = {"alg": _ALG, "typ": "JWT"}
    payload = {
        "sub": subject,
        "role": role,
        "name": name,
        "iat": issued_at,
        "exp": issued_at + int(ttl_seconds),
    }
    segments = [
        _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
        _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
    ]
    signing_input = ".".join(segments).encode("ascii")
    segments.append(_sign(signing_input, _get_secret()))
    return ".".join(segments)


def decode_access_token(token: str, *, now: float | None = None) -> dict[str, object]:
    """驗證簽章與過期時間並回傳 payload。

    Args:
        token: JWT 字串。
        now: 覆寫「現在」時間（epoch 秒），僅測試用；預設 ``time.time()``。

    Returns:
        payload dict（含 ``sub`` / ``role`` / ``name`` / ``iat`` / ``exp``）。

    Raises:
        TokenError: 格式錯誤、簽章不符、或已過期。
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise TokenError("token 格式錯誤（應為 header.payload.signature）")
    header_seg, payload_seg, signature_seg = parts

    signing_input = f"{header_seg}.{payload_seg}".encode("ascii")
    expected_sig = _sign(signing_input, _get_secret())
    # 常數時間比對，避免 timing attack。
    if not hmac.compare_digest(expected_sig, signature_seg):
        raise TokenError("簽章不符")

    try:
        payload = json.loads(_b64url_decode(payload_seg))
    except (ValueError, json.JSONDecodeError) as exc:
        raise TokenError("payload 無法解碼") from exc

    current = int(now if now is not None else time.time())
    exp = payload.get("exp")
    if not isinstance(exp, int) or current >= exp:
        raise TokenError("token 已過期")
    return payload
