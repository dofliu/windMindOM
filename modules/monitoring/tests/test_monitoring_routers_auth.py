"""monitoring router 授權代表性驗證（WMOM-20260716-05h-2）。

三種 gate tier 各取一代表端點：
- 讀取（turbines list）→ `require_authenticated`（任何登入者）
- 控制（control/command）→ `require_role(SUPERVISOR)`
- infra（modbus/start）→ `require_role(ADMIN)`（破壞性 / 開 port）
- 情境標準答案（scenarios/{id}/ground-truth）→ `require_roles(SUPERVISOR)`（盲測：一般檢視者看不到答案，
  且不受 enforce 開關影響——答案卷不能預設公開，WMOM-20261021-04）

授權 dependency 在 endpoint body 前執行，故以空 body 驗 gate：被擋＝401/403、
過 gate＝其餘（body 另計）。`enforce=false` 全放行（非破壞）。token 直接鑄造。
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
sys.path.insert(0, str(PROJECT_ROOT / "modules" / "monitoring"))

from modules.auth.tokens import create_access_token
from server.routers.turbines import router as turbines_router
from server.routers.control import router as control_router
from server.routers.modbus import router as modbus_router
from server.routers import scenarios as scenarios_ep


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)


@pytest.fixture
def client():
    app = FastAPI(title="monitoring-auth-test")
    app.include_router(turbines_router)
    app.include_router(control_router)
    app.include_router(modbus_router)
    app.include_router(scenarios_ep.router)
    return TestClient(app)


def _bearer(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject='u1', role=role, name='U')}"}


# ── 讀取 gate（turbines）→ 任何登入者 ─────────────────────────────────────
def test_read_legacy_passes(client):
    """enforce=false：放行（非 401/403）。"""
    assert client.get("/api/turbines").status_code not in (401, 403)


def test_read_enforced_no_token_401(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert client.get("/api/turbines").status_code == 401


def test_read_enforced_employee_passes(client, monkeypatch):
    """監控檢視＝任何登入者 → employee 過 gate。"""
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert client.get("/api/turbines", headers=_bearer("employee")).status_code not in (401, 403)


# ── 控制 gate（control/command）→ SUPERVISOR ──────────────────────────────
def test_control_enforced_no_token_401(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert client.post("/api/control/command", json={}).status_code == 401


def test_control_enforced_employee_403(client, monkeypatch):
    """控制指令＝主管 → employee 403。"""
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert client.post("/api/control/command", json={}, headers=_bearer("employee")).status_code == 403


def test_control_enforced_supervisor_passes(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    r = client.post("/api/control/command", json={}, headers=_bearer("supervisor"))
    assert r.status_code not in (401, 403)


# ── infra gate（modbus/start）→ ADMIN ─────────────────────────────────────
def test_modbus_enforced_supervisor_403(client, monkeypatch):
    """破壞性 / infra＝系統管理員 → supervisor 也 403。"""
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert client.post("/api/modbus/start", json={}, headers=_bearer("supervisor")).status_code == 403


def test_modbus_enforced_admin_passes(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    r = client.post("/api/modbus/start", json={}, headers=_bearer("admin"))
    assert r.status_code not in (401, 403)


# ── 情境標準答案 → SUPERVISOR（盲測，WMOM-20261021-04）─────────────────────
_GROUND_TRUTH_URL = "/api/scenarios/1/ground-truth"


def test_ground_truth_enforced_no_token_401(client, monkeypatch):
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert client.get(_GROUND_TRUTH_URL).status_code == 401


def test_ground_truth_requires_a_token_even_when_auth_is_not_enforced(client):
    """過渡期（enforce=false）其他端點全放行，答案卷仍要登入。"""
    assert client.get(_GROUND_TRUTH_URL).status_code == 401
    assert client.get(_GROUND_TRUTH_URL, headers=_bearer("employee")).status_code == 403


def test_ground_truth_enforced_employee_403(client, monkeypatch):
    """答案卷＝主管 → employee（一般檢視者）403。"""
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert client.get(_GROUND_TRUTH_URL, headers=_bearer("employee")).status_code == 403


def test_ground_truth_enforced_supervisor_passes(client, monkeypatch, tmp_path):
    from server.storage import Storage

    class _Stub:
        storage = Storage(db_path=str(tmp_path / "gt.db"))

    monkeypatch.setattr(scenarios_ep, "get_broker", lambda: _Stub())
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    r = client.get(_GROUND_TRUTH_URL, headers=_bearer("supervisor"))
    assert r.status_code == 404, "過 gate 後才因情境不存在 404"
