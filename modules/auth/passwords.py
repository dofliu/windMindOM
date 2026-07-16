"""密碼雜湊與驗證（PBKDF2-HMAC-SHA256，純 stdlib，DEC-20260716-01）。

## 為什麼 PBKDF2 而非 bcrypt/argon2

- ``hashlib.pbkdf2_hmac`` 是 stdlib，**零新依賴、無原生 build**（bcrypt/argon2 都要編譯
  原生輪子，sandbox 與部分客戶 on-prem 環境會卡）。PBKDF2-SHA256 搭配足夠迭代數是
  被廣泛接受的密碼雜湊（如 Django 歷來預設）。
- 儲存格式：``pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>``（自描述，可提高迭代數而不破舊雜湊）。
- 未來要更強（argon2id）時，只需在 ``verify_password`` 依 prefix 分派即可漸進遷移。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_ALGO_PREFIX = "pbkdf2_sha256"
_DEFAULT_ITERATIONS = 240_000
_SALT_BYTES = 16


def hash_password(password: str, *, iterations: int = _DEFAULT_ITERATIONS) -> str:
    """回傳自描述的密碼雜湊字串。

    Args:
        password: 明文密碼。
        iterations: PBKDF2 迭代數，預設 240k。

    Returns:
        ``pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>`` 格式字串。
    """
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    salt_b64 = base64.b64encode(salt).decode("ascii")
    hash_b64 = base64.b64encode(derived).decode("ascii")
    return f"{_ALGO_PREFIX}${iterations}${salt_b64}${hash_b64}"


def verify_password(password: str, encoded: str) -> bool:
    """常數時間驗證明文密碼是否符合 :func:`hash_password` 的雜湊。

    Args:
        password: 待驗證的明文密碼。
        encoded: :func:`hash_password` 產出的自描述雜湊字串。

    Returns:
        符合為 ``True``；格式不符或不符皆回 ``False``（不 raise，避免洩漏差異）。
    """
    try:
        algo, iter_str, salt_b64, hash_b64 = encoded.split("$")
    except ValueError:
        return False
    if algo != _ALGO_PREFIX:
        return False
    try:
        iterations = int(iter_str)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, TypeError):
        return False
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(derived, expected)
