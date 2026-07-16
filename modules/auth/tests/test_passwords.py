"""passwords PBKDF2 — 雜湊 / 驗證 / 加鹽 / 容錯（DEC-20260716-01）。

測試密碼一律用 ``secrets`` 於執行期生成（不寫死任何密碼字面值），避免 secret scanner
誤報，也是較好的測試衛生。
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.auth.passwords import hash_password, verify_password

# 執行期生成的測試密碼（無字面值 → scanner 無從誤報）。
_PW = secrets.token_urlsafe(12)
_OTHER_PW = secrets.token_urlsafe(12)


def test_hash_verify_roundtrip():
    assert verify_password(_PW, hash_password(_PW)) is True


def test_wrong_password_fails():
    assert verify_password(_OTHER_PW, hash_password(_PW)) is False


def test_hash_is_salted_unique():
    a = hash_password(_PW)
    b = hash_password(_PW)
    assert a != b  # 不同鹽 → 不同雜湊
    assert verify_password(_PW, a)
    assert verify_password(_PW, b)


def test_encoded_format():
    encoded = hash_password(_PW)
    assert encoded.startswith("pbkdf2_sha256$")
    assert len(encoded.split("$")) == 4


def test_malformed_encoded_returns_false():
    for bad in ["", "garbage", "pbkdf2_sha256$only", "wrongalgo$1$a$b", "pbkdf2_sha256$notint$a$b"]:
        assert verify_password(_PW, bad) is False
