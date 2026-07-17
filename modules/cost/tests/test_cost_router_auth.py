"""cost router 授權（WMOM-20260716-05h）。

成本檢視＝管理層（`require_role(SUPERVISOR)`，ADMIN 全權）。授權 gate 在 body 驗證前
執行，故用「空 body」即可驗 gate：被擋＝401/403；過 gate＝其餘（如 body 422）。
enforce=false 全放行（非破壞）。token 直接鑄造、無密碼字面值。
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
from modules.cost.routers.cost_router import router as cost_router


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)


@pytest.fixture
def client():
    app = FastAPI(title="cost-auth-test")
    app.include_router(cost_router)
    return TestClient(app)


def _bearer(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject='u1', role=role, name='U')}"}


def test_legacy_passes_gate(client):
    """enforce=false：gate 放行（非 401/403）。"""
    assert client.post("/api/cost/forecast", json={}).status_code not in (401, 403)


def test_enforced_no_token_401(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert client.post("/api/cost/forecast", json={}).status_code == 401


def test_enforced_employee_403(client, monkeypatch):
    """成本檢視＝管理層 → employee 403。"""
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert client.post("/api/cost/forecast", json={}, headers=_bearer("employee")).status_code == 403


def test_enforced_supervisor_passes_gate(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    r = client.post("/api/cost/forecast", json={}, headers=_bearer("supervisor"))
    assert r.status_code not in (401, 403)  # 過授權 gate（body 驗證另計）


def test_enforced_admin_passes_gate(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    r = client.post("/api/cost/forecast", json={}, headers=_bearer("admin"))
    assert r.status_code not in (401, 403)
