"""knowledge router 授權（WMOM-20260716-05h）。

警報 RAG / 查手冊＝任何登入者（`require_authenticated`；現場工程師必需）。授權 gate
在 body 驗證前執行：被擋＝401；過 gate＝其餘。enforce=false 全放行（非破壞）。
token 直接鑄造、無密碼字面值。
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.auth.tokens import create_access_token
from modules.knowledge.routers.knowledge_router import router as knowledge_router


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)


@pytest.fixture
def client():
    app = FastAPI(title="knowledge-auth-test")
    app.include_router(knowledge_router)
    return TestClient(app)


def _bearer(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject='u1', role=role, name='U')}"}


def test_legacy_passes_gate(client):
    """enforce=false：gate 放行（非 401）。"""
    assert client.post("/api/knowledge/query", json={}).status_code != 401


def test_enforced_no_token_401(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert client.post("/api/knowledge/query", json={}).status_code == 401


def test_enforced_employee_passes_gate(client, monkeypatch):
    """require_authenticated 不限角色 → employee 也過 gate（現場工程師必需）。"""
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    r = client.post("/api/knowledge/query", json={}, headers=_bearer("employee"))
    assert r.status_code != 401


def test_info_enforced_no_token_401(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert client.get("/api/knowledge/info").status_code == 401
