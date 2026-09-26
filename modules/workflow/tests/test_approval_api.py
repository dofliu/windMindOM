"""Approval API + work_order finish auto-chain integration tests（WMOM-20260504-18）。"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

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


@pytest.fixture
def client(tmp_path) -> TestClient:
    """FastAPI TestClient — 注入 tmp DB factories（work_order + signoff 共用同檔）。"""
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")

    def wo_factory(farm_id: str) -> WorkOrderRepository:
        return get_repository(db_path)

    def sg_factory(farm_id: str) -> SignoffRepository:
        return get_signoff_repository(db_path)

    set_repository_factory(wo_factory)
    set_signoff_factories(sg_factory, wo_factory)

    app = FastAPI(title="approval-test")
    app.include_router(workflow_router)
    app.include_router(approval_router)
    yield TestClient(app)

    set_repository_factory(None)
    set_signoff_factories(None, None)
    clear_engine_cache_for_test()


def _create_and_finish_wo(client) -> tuple[str, str, dict]:
    """Helper：建工單 → dispatch → start_work → finish。

    Returns ``(wo_id, farm_id, finish_response_dict)``（review fix #8：原 type hint 標錯）。
    """
    actor = str(uuid4())
    farm_id = "台中港曲風場"
    qs = f"?farm_id={farm_id}"

    created = client.post("/api/workflow/work-orders", json={
        "farm_id": farm_id,
        "turbine_id": "WT001",
        "type": "corrective",
        "title": "test",
        "description": "x",
        "assignee_id": actor,
    }).json()
    wo_id = created["id"]

    client.post(f"/api/workflow/work-orders/{wo_id}/dispatch{qs}",
                json={"actor_id": actor})
    client.post(f"/api/workflow/work-orders/{wo_id}/start-work{qs}",
                json={"require_weather_window": False})
    finish_resp = client.post(
        f"/api/workflow/work-orders/{wo_id}/finish{qs}",
        json={
            "actual_hours": 2.0,
            "followup_kind": "none",
            "work_summary": "完成",
        },
    )
    return wo_id, farm_id, finish_resp.json()


# ─────────────────────────────────────────────────────────────────────────
# Integration: work_order finish → 自動建 chain
# ─────────────────────────────────────────────────────────────────────────


def test_finish_auto_creates_signoff_chain(client):
    """work_order.finish() 完成後，response 帶上 signoff_chain_id；
    pending list 也能查到對應 chain（含正確 subject_id + levels）。"""
    wo_id, farm_id, finish_data = _create_and_finish_wo(client)

    assert finish_data["status"] == "awaiting_signoff"
    assert finish_data["signoff_chain_id"] is not None  # auto-created chain

    # 從 pending list 反查 chain，驗 levels + subject_id 正確（review nice-to-have #1）
    pending = client.get(
        f"/api/workflow/approvals/pending?farm_id={farm_id}&level=employee"
    ).json()
    assert pending["total"] == 1
    chain = pending["items"][0]["chain"]
    assert chain["subject_id"] == wo_id
    assert chain["subject_type"] == "work_order"
    assert chain["levels"] == ["employee", "leader"]
    assert chain["current_level_index"] == 0


def test_finish_chain_visible_in_pending_employee_list(client):
    """剛 finish 的工單 — EMPLOYEE level pending list 應該看得到。"""
    wo_id, farm_id, _ = _create_and_finish_wo(client)

    r = client.get(
        f"/api/workflow/approvals/pending?farm_id={farm_id}&level=employee"
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["chain"]["subject_id"] == wo_id


# ─────────────────────────────────────────────────────────────────────────
# approve_step lifecycle
# ─────────────────────────────────────────────────────────────────────────


def test_approve_first_step_advances_chain_no_subject_change(client):
    """通過 EMPLOYEE 階 → chain.current_level_index = 1，工單仍 AWAITING_SIGNOFF。"""
    wo_id, farm_id, _ = _create_and_finish_wo(client)
    qs = f"?farm_id={farm_id}"

    # 拿到 step1 id
    pending = client.get(
        f"/api/workflow/approvals/pending?farm_id={farm_id}&level=employee"
    ).json()
    step_id = pending["items"][0]["step"]["id"]

    r = client.post(
        f"/api/workflow/approvals/{step_id}/approve{qs}",
        json={"actor_id": str(uuid4()), "comment": "ok"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["chain"]["current_level_index"] == 1
    assert data["chain"]["overall_status"] == "pending"
    assert data["chain_completed"] is False
    assert data["subject_status_changed"] is False  # 還沒到最後一階

    # 工單仍 AWAITING_SIGNOFF
    wo = client.get(f"/api/workflow/work-orders/{wo_id}{qs}").json()
    assert wo["status"] == "awaiting_signoff"


def test_approve_last_step_closes_work_order(client):
    """通過 LEADER 階（最後一階）→ chain APPROVED + 自動 work_order.approve_all → CLOSED。"""
    wo_id, farm_id, _ = _create_and_finish_wo(client)
    qs = f"?farm_id={farm_id}"
    # WMOM-20260510-01 Part A：separation-of-duties → 每階用不同 actor
    actor_emp = str(uuid4())
    actor_lead = str(uuid4())

    # 第一階
    pending_emp = client.get(
        f"/api/workflow/approvals/pending?farm_id={farm_id}&level=employee"
    ).json()
    client.post(
        f"/api/workflow/approvals/{pending_emp['items'][0]['step']['id']}/approve{qs}",
        json={"actor_id": actor_emp},
    )

    # 第二階 LEADER
    pending_lead = client.get(
        f"/api/workflow/approvals/pending?farm_id={farm_id}&level=leader"
    ).json()
    r = client.post(
        f"/api/workflow/approvals/{pending_lead['items'][0]['step']['id']}/approve{qs}",
        json={"actor_id": actor_lead, "comment": "all good"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["chain"]["overall_status"] == "approved"
    assert data["chain_completed"] is True
    assert data["subject_status_changed"] is True  # 工單也 close 了

    # 工單 → CLOSED
    wo = client.get(f"/api/workflow/work-orders/{wo_id}{qs}").json()
    assert wo["status"] == "closed"
    assert wo["closed_at"] is not None


def test_approve_last_step_closes_work_order_also_appends_day_work_form_activity(
    client, tmp_path,
):
    """WMOM-20260926-01 item 2 端到端整合測試：走 production 唯一真實的完工路徑——
    ``approval_router`` 簽核鏈最後一階 HTTP endpoint 自動觸發
    ``wo_repo.transition(chain.subject_id, "approve_all")``——確認掛在共用
    ``WorkOrderRepository.transition()`` 內部的 day_work_form 自動寫入 hook
    （見 ``work_order_repository.py::_record_completed_wo_activity``）也確實被觸發。

    比 ``test_work_order_finish_day_work_form_hook.py`` 裡直接呼叫
    ``repo.transition()`` 的單元測試更進一步：完整跑過 FastAPI router + 簽核鏈
    state machine，不是只驗證 repository 私有方法本身。
    """
    from modules.workflow.domain.day_work_form import ActivityKind
    from modules.workflow.repository.day_work_form_repository import (
        get_day_work_form_repository,
    )
    from modules.workflow.repository.work_order_repository import _TAIPEI_TZ

    wo_id, farm_id, finish_data = _create_and_finish_wo(client)
    assignee_id = finish_data["assignee_id"]
    qs = f"?farm_id={farm_id}"
    actor_emp = str(uuid4())
    actor_lead = str(uuid4())

    pending_emp = client.get(
        f"/api/workflow/approvals/pending?farm_id={farm_id}&level=employee"
    ).json()
    client.post(
        f"/api/workflow/approvals/{pending_emp['items'][0]['step']['id']}/approve{qs}",
        json={"actor_id": actor_emp},
    )
    pending_lead = client.get(
        f"/api/workflow/approvals/pending?farm_id={farm_id}&level=leader"
    ).json()
    r = client.post(
        f"/api/workflow/approvals/{pending_lead['items'][0]['step']['id']}/approve{qs}",
        json={"actor_id": actor_lead, "comment": "all good"},
    )
    assert r.json()["subject_status_changed"] is True  # 工單也 close 了

    from datetime import datetime
    from uuid import UUID

    dwf_repo = get_day_work_form_repository(str(tmp_path / "wind_farm.db"))
    today_taipei = datetime.now(tz=_TAIPEI_TZ).date()
    form = dwf_repo.get_by_date(
        farm_id=farm_id, employee_id=UUID(assignee_id), work_date=today_taipei,
    )
    assert form is not None
    assert len(form.activities) == 1
    entry = form.activities[0]
    assert entry.kind == ActivityKind.COMPLETED_WO
    assert str(entry.wo_id) == wo_id


# ─────────────────────────────────────────────────────────────────────────
# reject_step
# ─────────────────────────────────────────────────────────────────────────


def test_reject_step_returns_work_order_to_in_progress(client):
    """reject 任一階 → chain REJECTED + 工單回 IN_PROGRESS。"""
    wo_id, farm_id, _ = _create_and_finish_wo(client)
    qs = f"?farm_id={farm_id}"

    pending = client.get(
        f"/api/workflow/approvals/pending?farm_id={farm_id}&level=employee"
    ).json()
    step_id = pending["items"][0]["step"]["id"]

    r = client.post(
        f"/api/workflow/approvals/{step_id}/reject{qs}",
        json={"actor_id": str(uuid4()), "reason": "缺照片"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["chain"]["overall_status"] == "rejected"
    assert data["chain"]["rejected_at_level"] == "employee"
    assert data["chain"]["rejected_reason"] == "缺照片"
    assert data["subject_status_changed"] is True

    # 工單 → IN_PROGRESS（給機會修正）
    wo = client.get(f"/api/workflow/work-orders/{wo_id}{qs}").json()
    assert wo["status"] == "in_progress"
    assert wo["reject_reason"] == "缺照片"


def test_reject_requires_reason_422(client):
    wo_id, farm_id, _ = _create_and_finish_wo(client)
    qs = f"?farm_id={farm_id}"
    pending = client.get(
        f"/api/workflow/approvals/pending?farm_id={farm_id}&level=employee"
    ).json()
    step_id = pending["items"][0]["step"]["id"]

    # pydantic schema reason min_length=1 → 422
    r = client.post(
        f"/api/workflow/approvals/{step_id}/reject{qs}",
        json={"actor_id": str(uuid4()), "reason": ""},
    )
    assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────
# pending list filters
# ─────────────────────────────────────────────────────────────────────────


def test_pending_list_filters_by_level(client):
    wo_id, farm_id, _ = _create_and_finish_wo(client)

    # EMPLOYEE 看到 1 筆
    emp = client.get(
        f"/api/workflow/approvals/pending?farm_id={farm_id}&level=employee"
    ).json()
    assert emp["total"] == 1

    # LEADER 看不到（chain.current_level_index 還是 0）
    lead = client.get(
        f"/api/workflow/approvals/pending?farm_id={farm_id}&level=leader"
    ).json()
    assert lead["total"] == 0


def test_approve_404_for_unknown_step(client):
    qs = "?farm_id=台中港曲風場"
    r = client.post(
        f"/api/workflow/approvals/{uuid4()}/approve{qs}",
        json={"actor_id": str(uuid4())},
    )
    assert r.status_code == 404


def test_approve_409_for_terminal_chain(client):
    """已 reject 的 chain 上不可再 approve → 409。"""
    wo_id, farm_id, _ = _create_and_finish_wo(client)
    qs = f"?farm_id={farm_id}"
    actor = str(uuid4())

    pending = client.get(
        f"/api/workflow/approvals/pending?farm_id={farm_id}&level=employee"
    ).json()
    step_id = pending["items"][0]["step"]["id"]

    # 先 reject
    client.post(
        f"/api/workflow/approvals/{step_id}/reject{qs}",
        json={"actor_id": actor, "reason": "x"},
    )
    # 然後嘗試 approve 同 step
    r = client.post(
        f"/api/workflow/approvals/{step_id}/approve{qs}",
        json={"actor_id": actor},
    )
    assert r.status_code == 409


# ─────────────────────────────────────────────────────────────────────────
# Review fix #2 — reject 後 work_order.signoff_chain_id 應清掉
# ─────────────────────────────────────────────────────────────────────────


def test_reject_clears_work_order_signoff_chain_pointer(client):
    """review fix #2：reject 後 wo.signoff_chain_id 應為 None（避免 stale pointer）。"""
    wo_id, farm_id, finish_resp = _create_and_finish_wo(client)
    qs = f"?farm_id={farm_id}"

    # finish 後有 chain id
    assert finish_resp["signoff_chain_id"] is not None

    # reject
    pending = client.get(
        f"/api/workflow/approvals/pending?farm_id={farm_id}&level=employee"
    ).json()
    client.post(
        f"/api/workflow/approvals/{pending['items'][0]['step']['id']}/reject{qs}",
        json={"actor_id": str(uuid4()), "reason": "x"},
    )

    # wo 應回 IN_PROGRESS + signoff_chain_id 已清
    wo = client.get(f"/api/workflow/work-orders/{wo_id}{qs}").json()
    assert wo["status"] == "in_progress"
    assert wo["signoff_chain_id"] is None  # ← 關鍵 assertion


def test_re_finish_after_reject_creates_new_chain(client):
    """review fix #2：reject → 重新 finish 應建新 chain，wo.signoff_chain_id 指向新 chain。"""
    wo_id, farm_id, finish1 = _create_and_finish_wo(client)
    qs = f"?farm_id={farm_id}"
    actor = str(uuid4())
    chain1_id = finish1["signoff_chain_id"]

    # reject 第一輪
    pending1 = client.get(
        f"/api/workflow/approvals/pending?farm_id={farm_id}&level=employee"
    ).json()
    client.post(
        f"/api/workflow/approvals/{pending1['items'][0]['step']['id']}/reject{qs}",
        json={"actor_id": actor, "reason": "缺料"},
    )

    # 第二輪 finish — 重新建 chain
    finish2 = client.post(
        f"/api/workflow/work-orders/{wo_id}/finish{qs}",
        json={"actual_hours": 4.0, "followup_kind": "none"},
    ).json()

    chain2_id = finish2["signoff_chain_id"]
    assert chain2_id is not None
    assert chain2_id != chain1_id  # 新 chain，不是舊的
