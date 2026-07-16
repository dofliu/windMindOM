"""approval / signoff 端點的雙模式授權（WMOM-20260716-05e）。

approval_router 是 auth 批次中最敏感的一支——它疊在既有「職責分離」
（``_check_actor_separation``：同一人不可連簽同 chain 的先前階）之上。故本檔除了
基本 gate（401/放行）外，特別驗證**核心安全性質**：

> ``WMOM_AUTH_ENFORCE=true`` 後，簽核身分來自**已驗證 token**（非可竄改的 body
> ``actor_id``），職責分離才建立在可信身分上（防冒簽）。

以「同一 token 連簽兩階 → 第二階被職責分離擋下（409）」反證之。

gate 設計：pending / approve / reject 皆 ``require_authenticated``（任何登入者）；
「該角色能否簽此 level」為更細的 domain 強化，屬後續，本 PR 不含。token 直接鑄造。
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.auth.tokens import create_access_token
from modules.workflow.repository import (
    SignoffRepository,
    WorkOrderRepository,
    get_repository,
    get_signoff_repository,
)
from modules.workflow.repository.work_order_repository import (
    clear_engine_cache_for_test,
)
from modules.workflow.routers import approval_router, router as workflow_router
from modules.workflow.routers.approval_router import set_signoff_factories
from modules.workflow.routers.work_order_router import set_repository_factory


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch):
    """每 test 給 JWT secret；清 dev_mode（讓職責分離生效）/ enforce（各 test 自行 opt-in）。"""
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)


@pytest.fixture
def client_approval(tmp_path):
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")

    def wo_factory(_f: str) -> WorkOrderRepository:
        return get_repository(db_path)

    def sg_factory(_f: str) -> SignoffRepository:
        return get_signoff_repository(db_path)

    set_repository_factory(wo_factory)
    set_signoff_factories(sg_factory, wo_factory)

    app = FastAPI(title="approval-auth-test")
    app.include_router(workflow_router)
    app.include_router(approval_router)
    yield TestClient(app), db_path

    set_repository_factory(None)
    set_signoff_factories(None, None)
    clear_engine_cache_for_test()


def _bearer(role: str, subject: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject=subject, role=role, name='U')}"}


def _finish_wo_and_get_step(client, *, level: str = "employee") -> tuple[str, str]:
    """建工單→dispatch→start→finish（自動建 signoff chain），回 (farm_id, 該 level 的 pending step_id)。

    全程在 enforce=false 下跑（work_order 端點尚未 gated；此處僅為取得一個可簽的 step）。
    """
    farm_id = "changhua"
    qs = f"?farm_id={farm_id}"
    setup_actor = str(uuid4())
    created = client.post(
        "/api/workflow/work-orders",
        json={
            "farm_id": farm_id,
            "turbine_id": "WT001",
            "type": "corrective",
            "title": "auth-test",
            "description": "x",
            "assignee_id": setup_actor,
        },
    )
    assert created.status_code in (200, 201), created.text
    wo_id = created.json()["id"]
    client.post(f"/api/workflow/work-orders/{wo_id}/dispatch{qs}", json={"actor_id": setup_actor})
    client.post(
        f"/api/workflow/work-orders/{wo_id}/start-work{qs}",
        json={"require_weather_window": False},
    )
    fin = client.post(
        f"/api/workflow/work-orders/{wo_id}/finish{qs}",
        json={"actual_hours": 2.0, "followup_kind": "none", "work_summary": "done"},
    )
    assert fin.status_code == 200, fin.text
    pending = client.get(
        f"/api/workflow/approvals/pending?farm_id={farm_id}&level={level}"
    ).json()
    assert pending["total"] >= 1, pending
    return farm_id, pending["items"][0]["step"]["id"]


def _approve(client, step_id, farm_id, *, body_actor, headers=None, comment="ok"):
    body: dict = {"comment": comment}
    if body_actor is not None:
        body["actor_id"] = body_actor
    return client.post(
        f"/api/workflow/approvals/{step_id}/approve?farm_id={farm_id}",
        json=body,
        headers=headers or {},
    )


def _reject(client, step_id, farm_id, *, body_actor, headers=None, reason="nope"):
    body: dict = {"reason": reason}
    if body_actor is not None:
        body["actor_id"] = body_actor
    return client.post(
        f"/api/workflow/approvals/{step_id}/reject?farm_id={farm_id}",
        json=body,
        headers=headers or {},
    )


# ── approve：require_authenticated ────────────────────────────────────────
def test_approve_legacy_body_actor_ok(client_approval):
    """enforce=false：沿用 body actor_id（現有行為，非破壞）。"""
    client, _ = client_approval
    farm_id, step_id = _finish_wo_and_get_step(client)
    resp = _approve(client, step_id, farm_id, body_actor=str(uuid4()))
    assert resp.status_code == 200, resp.text
    assert resp.json()["chain"]["current_level_index"] == 1


def test_approve_token_ok(client_approval):
    """enforce=false：帶 token 一樣放行。"""
    client, _ = client_approval
    farm_id, step_id = _finish_wo_and_get_step(client)
    resp = _approve(
        client, step_id, farm_id, body_actor=str(uuid4()), headers=_bearer("employee", str(uuid4()))
    )
    assert resp.status_code == 200, resp.text


def test_approve_enforced_no_token_401(client_approval, monkeypatch):
    """enforce=true：無 token → 401（body actor_id 不再被信任）。"""
    client, _ = client_approval
    farm_id, step_id = _finish_wo_and_get_step(client)
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = _approve(client, step_id, farm_id, body_actor=str(uuid4()))
    assert resp.status_code == 401


def test_approve_enforced_employee_ok(client_approval, monkeypatch):
    """enforce=true：require_authenticated 不限角色 → employee token 放行。"""
    client, _ = client_approval
    farm_id, step_id = _finish_wo_and_get_step(client)
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = _approve(
        client, step_id, farm_id, body_actor=str(uuid4()), headers=_bearer("employee", str(uuid4()))
    )
    assert resp.status_code == 200, resp.text


# ── 核心安全性質：enforce 後身分來自 token（以職責分離反證）────────────────
def test_approve_enforced_token_identity_drives_separation_of_duties(client_approval, monkeypatch):
    """enforce=true 後 decided_by 記的是 token（非 body）。

    同一 token 連簽 employee + leader 兩階 → 第二階被 ``_check_actor_separation`` 擋下（409）。
    若 body 身分被採用，兩階 decided_by 不同、不觸發職責分離 → 反證成立。
    """
    client, _ = client_approval
    farm_id, step1_id = _finish_wo_and_get_step(client, level="employee")
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")

    tok = _bearer("leader", str(uuid4()))  # 同一身分貫穿兩階
    # step1（employee 階）：token 簽，body 帶不同 actor_id（應被忽略）
    r1 = _approve(client, step1_id, farm_id, body_actor=str(uuid4()), headers=tok)
    assert r1.status_code == 200, r1.text
    assert r1.json()["chain"]["current_level_index"] == 1

    # step2（leader 階）：同一 token 再簽 → 職責分離擋下
    pending = client.get(
        f"/api/workflow/approvals/pending?farm_id={farm_id}&level=leader", headers=tok
    ).json()
    step2_id = pending["items"][0]["step"]["id"]
    r2 = _approve(client, step2_id, farm_id, body_actor=str(uuid4()), headers=tok)
    assert r2.status_code == 409, r2.text  # 同一 token 身分連簽 → SignoffActionError


# ── reject：require_authenticated ─────────────────────────────────────────
def test_reject_enforced_no_token_401(client_approval, monkeypatch):
    """enforce=true：無 token → 401。"""
    client, _ = client_approval
    farm_id, step_id = _finish_wo_and_get_step(client)
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = _reject(client, step_id, farm_id, body_actor=str(uuid4()))
    assert resp.status_code == 401


def test_reject_enforced_token_ok(client_approval, monkeypatch):
    """enforce=true：有效 token → 放行（駁回不限角色），chain 進 rejected。"""
    client, _ = client_approval
    farm_id, step_id = _finish_wo_and_get_step(client)
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = _reject(
        client, step_id, farm_id, body_actor=str(uuid4()), headers=_bearer("leader", str(uuid4()))
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["chain"]["overall_status"] == "rejected"


# ── pending：require_authenticated ────────────────────────────────────────
def test_pending_enforced_no_token_401(client_approval, monkeypatch):
    """enforce=true：待簽列表也需登入 → 無 token 401。"""
    client, _ = client_approval
    farm_id, _step = _finish_wo_and_get_step(client)
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = client.get(f"/api/workflow/approvals/pending?farm_id={farm_id}&level=employee")
    assert resp.status_code == 401


def test_pending_enforced_token_ok(client_approval, monkeypatch):
    """enforce=true：有效 token → 200。"""
    client, _ = client_approval
    farm_id, _step = _finish_wo_and_get_step(client)
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    resp = client.get(
        f"/api/workflow/approvals/pending?farm_id={farm_id}&level=employee",
        headers=_bearer("employee", str(uuid4())),
    )
    assert resp.status_code == 200, resp.text
