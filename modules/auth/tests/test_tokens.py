"""tokens HS256 JWT — 簽發 / 驗證 / 過期 / 竄改 / 金鑰（DEC-20260716-01）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.auth.tokens import TokenError, create_access_token, decode_access_token

_TTL_12H = 12 * 60 * 60


@pytest.fixture(autouse=True)
def _prod_secret(monkeypatch):
    """預設：production-like（設 env 金鑰、關 dev_mode）。個別 test 可覆寫。"""
    monkeypatch.setenv("WMOM_JWT_SECRET", "test-secret-abc")
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)


def test_roundtrip_returns_claims():
    token = create_access_token(subject="u1", role="employee", name="Alice", now=1000)
    payload = decode_access_token(token, now=1000)
    assert payload["sub"] == "u1"
    assert payload["role"] == "employee"
    assert payload["name"] == "Alice"
    assert payload["iat"] == 1000
    assert payload["exp"] == 1000 + _TTL_12H


def test_custom_ttl_boundary():
    token = create_access_token(subject="u1", role="admin", name="O", ttl_seconds=60, now=1000)
    assert decode_access_token(token, now=1059)["sub"] == "u1"  # 未到 exp
    with pytest.raises(TokenError):
        decode_access_token(token, now=1060)  # current >= exp → 過期


def test_expired_raises():
    token = create_access_token(subject="u1", role="leader", name="B", ttl_seconds=10, now=1000)
    with pytest.raises(TokenError):
        decode_access_token(token, now=2000)


def test_tampered_signature_raises():
    token = create_access_token(subject="u1", role="leader", name="B", now=1000)
    head, payload, sig = token.split(".")
    tampered = f"{head}.{payload}.{'A' if sig[0] != 'A' else 'B'}{sig[1:]}"
    with pytest.raises(TokenError):
        decode_access_token(tampered, now=1000)


def test_tampered_payload_raises():
    token = create_access_token(subject="u1", role="employee", name="B", now=1000)
    head, _payload, sig = token.split(".")
    # 換一個「role=admin」的 payload 但沿用舊簽章 → 簽章不符。
    import base64
    import json

    forged = base64.urlsafe_b64encode(
        json.dumps({"sub": "u1", "role": "admin", "name": "B", "iat": 1000, "exp": 1000 + _TTL_12H}).encode()
    ).rstrip(b"=").decode()
    with pytest.raises(TokenError):
        decode_access_token(f"{head}.{forged}.{sig}", now=1000)


def test_wrong_secret_fails(monkeypatch):
    token = create_access_token(subject="u1", role="leader", name="B", now=1000)
    monkeypatch.setenv("WMOM_JWT_SECRET", "different-secret")
    with pytest.raises(TokenError):
        decode_access_token(token, now=1000)


def test_malformed_token_raises():
    with pytest.raises(TokenError):
        decode_access_token("only.two", now=1000)
    with pytest.raises(TokenError):
        decode_access_token("a.b.c.d.e", now=1000)


def test_missing_secret_in_prod_raises(monkeypatch):
    monkeypatch.delenv("WMOM_JWT_SECRET", raising=False)
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    with pytest.raises(RuntimeError):
        create_access_token(subject="u1", role="employee", name="A", now=1000)


def test_dev_mode_allows_default_secret(monkeypatch):
    monkeypatch.delenv("WMOM_JWT_SECRET", raising=False)
    monkeypatch.setenv("WMOM_DEV_MODE", "true")
    token = create_access_token(subject="u1", role="employee", name="A", now=1000)
    assert decode_access_token(token, now=1000)["sub"] == "u1"
