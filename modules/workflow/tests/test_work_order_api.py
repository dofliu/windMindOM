"""FastAPI work-order router tests（WMOM-20260504-17）。

注入 mock repository factory 避開 monitoring FarmRegistry 依賴。
測試 11 個 endpoints：
- POST /work-orders (create)
- GET /work-orders (list)
- GET /work-orders/{id}
- POST /work-orders/{id}/dispatch
- POST /work-orders/{id}/start-work
- POST /work-orders/{id}/update-progress
- POST /work-orders/{id}/finish
- POST /work-orders/{id}/approve
- POST /work-orders/{id}/reject
- POST /work-orders/{id}/cancel
- POST /work-orders/{id}/reopen
"""

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
    """FastAPI TestClient — 注入 tmp DB factories（含 approval router 給完整 lifecycle test）。"""
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")

    def wo_factory(farm_id: str) -> WorkOrderRepository:
        return get_repository(db_path)

    def sg_factory(farm_id: str) -> SignoffRepository:
        return get_signoff_repository(db_path)

    set_repository_factory(wo_factory)
    set_signoff_factories(sg_factory, wo_factory)

    app = FastAPI(title="workflow-test")
    app.include_router(workflow_router)
    app.include_router(approval_router)
    yield TestClient(app)

    set_repository_factory(None)
    set_signoff_factories(None, None)
    clear_engine_cache_for_test()


def _create_payload(**overrides):
    base = {
        "farm_id": "台中港曲風場",
        "turbine_id": "WT001",
        "type": "corrective",
        "title": "軸承過熱",
        "description": "主軸承溫度 75°C",
    }
    base.update(overrides)
    return base


# ─────────────────────────────────────────────────────────────────────────
# POST /work-orders — create
# ─────────────────────────────────────────────────────────────────────────


def test_create_work_order_201(client):
    r = client.post("/api/workflow/work-orders", json=_create_payload())
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["status"] == "draft"
    assert data["business_key"].startswith("WO-")
    assert data["farm_id"] == "台中港曲風場"


def test_create_work_order_validates_required_fields(client):
    r = client.post("/api/workflow/work-orders", json={"farm_id": "x"})
    assert r.status_code == 422


def test_create_work_order_validates_enum(client):
    r = client.post(
        "/api/workflow/work-orders",
        json=_create_payload(type="invalid_type"),
    )
    assert r.status_code == 422


def test_create_work_order_409_when_too_many_open(client):
    """≤ 3 OPEN per turbine constraint → 4th create returns 409。"""
    for i in range(3):
        r = client.post(
            "/api/workflow/work-orders",
            json=_create_payload(source_alarm_code=f"A{i:03d}"),
        )
        assert r.status_code == 201
    r = client.post(
        "/api/workflow/work-orders",
        json=_create_payload(source_alarm_code="A999"),
    )
    assert r.status_code == 409
    assert "OPEN" in r.json()["detail"]


def test_create_work_order_409_duplicate_alarm_code(client):
    """同 turbine + 同 alarm_code 已有 OPEN → 409。"""
    r1 = client.post(
        "/api/workflow/work-orders",
        json=_create_payload(source_alarm_code="ALARM_X"),
    )
    assert r1.status_code == 201
    r2 = client.post(
        "/api/workflow/work-orders",
        json=_create_payload(source_alarm_code="ALARM_X"),
    )
    assert r2.status_code == 409
    assert "alarm_code" in r2.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────
# GET /work-orders + GET /work-orders/{id}
# ─────────────────────────────────────────────────────────────────────────


def test_list_work_orders_filters_by_farm(client):
    client.post("/api/workflow/work-orders", json=_create_payload(farm_id="A"))
    client.post("/api/workflow/work-orders", json=_create_payload(farm_id="B"))

    r = client.get("/api/workflow/work-orders?farm_id=A")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["items"][0]["farm_id"] == "A"


def test_list_work_orders_only_open_excludes_cancelled(client):
    a = client.post("/api/workflow/work-orders", json=_create_payload(source_alarm_code="A")).json()
    b = client.post(
        "/api/workflow/work-orders",
        json=_create_payload(turbine_id="WT002", source_alarm_code="B"),
    ).json()
    # cancel a
    client.post(
        f"/api/workflow/work-orders/{a['id']}/cancel?farm_id=台中港曲風場",
        json={"cancel_reason": "客戶取消"},
    )

    r = client.get("/api/workflow/work-orders?farm_id=台中港曲風場&only_open=true")
    assert r.status_code == 200
    items = r.json()["items"]
    ids = {it["id"] for it in items}
    assert b["id"] in ids
    assert a["id"] not in ids


def test_get_work_order_detail(client):
    created = client.post("/api/workflow/work-orders", json=_create_payload()).json()
    r = client.get(
        f"/api/workflow/work-orders/{created['id']}?farm_id=台中港曲風場"
    )
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_get_work_order_404_for_missing(client):
    r = client.get(
        f"/api/workflow/work-orders/{uuid4()}?farm_id=x"
    )
    assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────
# State transitions
# ─────────────────────────────────────────────────────────────────────────


def test_dispatch_success(client):
    actor = str(uuid4())
    assignee = str(uuid4())
    created = client.post(
        "/api/workflow/work-orders",
        json=_create_payload(assignee_id=assignee),
    ).json()

    r = client.post(
        f"/api/workflow/work-orders/{created['id']}/dispatch?farm_id=台中港曲風場",
        json={"actor_id": actor},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "dispatched"
    assert data["dispatched_by"] == actor


def test_dispatch_409_from_wrong_state(client):
    """已 cancel 的工單不可 dispatch → 409 conflict。"""
    actor = str(uuid4())
    created = client.post(
        "/api/workflow/work-orders",
        json=_create_payload(assignee_id=str(uuid4())),
    ).json()
    client.post(
        f"/api/workflow/work-orders/{created['id']}/cancel?farm_id=台中港曲風場",
        json={"cancel_reason": "X"},
    )
    r = client.post(
        f"/api/workflow/work-orders/{created['id']}/dispatch?farm_id=台中港曲風場",
        json={"actor_id": actor},
    )
    assert r.status_code == 409
    assert "cannot transition" in r.json()["detail"]


def test_dispatch_422_missing_actor(client):
    """dispatch 缺 actor_id → 422 validation。"""
    created = client.post(
        "/api/workflow/work-orders",
        json=_create_payload(assignee_id=str(uuid4())),
    ).json()
    r = client.post(
        f"/api/workflow/work-orders/{created['id']}/dispatch?farm_id=台中港曲風場",
        json={},
    )
    assert r.status_code == 422


def test_full_happy_path_lifecycle_via_api(client):
    """完整 lifecycle: DRAFT → DISPATCHED → IN_PROGRESS → AWAITING_SIGNOFF → CLOSED。

    Review fix #4：``/approve`` endpoint 強制檢查 signoff chain 全通過，
    所以 lifecycle test 必須走 ``/approvals/{step_id}/approve`` 把 chain 跑完，
    chain 完成後 approval_router 會自動觸發 work_order.approve_all。
    """
    actor = str(uuid4())
    created = client.post(
        "/api/workflow/work-orders",
        json=_create_payload(assignee_id=actor),
    ).json()
    farm_id = "台中港曲風場"
    qs = f"?farm_id={farm_id}"

    # dispatch / start / progress / finish — 同既有
    client.post(f"/api/workflow/work-orders/{created['id']}/dispatch{qs}",
                json={"actor_id": actor})
    client.post(f"/api/workflow/work-orders/{created['id']}/start-work{qs}",
                json={"require_weather_window": False})
    client.post(f"/api/workflow/work-orders/{created['id']}/update-progress{qs}",
                json={"actor_id": actor, "note": "拆下軸承"})
    finish_resp = client.post(
        f"/api/workflow/work-orders/{created['id']}/finish{qs}",
        json={"actual_hours": 3.5, "followup_kind": "none", "work_summary": "完成"},
    ).json()
    assert finish_resp["status"] == "awaiting_signoff"
    assert finish_resp["signoff_chain_id"] is not None  # auto-created chain

    # 走 signoff approve flow (2 階)
    for level in ("employee", "leader"):
        pending = client.get(
            f"/api/workflow/approvals/pending?farm_id={farm_id}&level={level}"
        ).json()
        assert pending["total"] == 1
        step_id = pending["items"][0]["step"]["id"]
        client.post(
            f"/api/workflow/approvals/{step_id}/approve{qs}",
            json={"actor_id": actor},
        )

    # 工單已 CLOSED
    final = client.get(f"/api/workflow/work-orders/{created['id']}{qs}").json()
    assert final["status"] == "closed"


def test_direct_approve_blocked_when_chain_not_completed(client):
    """Review fix #4 (security)：POST /approve 必須 chain 全通過才放行；
    繞過 signoff flow 直接 close 工單應被擋（409）。"""
    actor = str(uuid4())
    created = client.post(
        "/api/workflow/work-orders",
        json=_create_payload(assignee_id=actor),
    ).json()
    qs = "?farm_id=台中港曲風場"
    client.post(f"/api/workflow/work-orders/{created['id']}/dispatch{qs}",
                json={"actor_id": actor})
    client.post(f"/api/workflow/work-orders/{created['id']}/start-work{qs}",
                json={"require_weather_window": False})
    client.post(
        f"/api/workflow/work-orders/{created['id']}/finish{qs}",
        json={"actual_hours": 1.0, "followup_kind": "none"},
    )
    # chain 為 PENDING 狀態 — 直接 /approve 應 409
    r = client.post(f"/api/workflow/work-orders/{created['id']}/approve{qs}")
    assert r.status_code == 409
    assert "signoff" in r.json()["detail"].lower()


def test_reject_returns_to_in_progress(client):
    actor = str(uuid4())
    created = client.post(
        "/api/workflow/work-orders",
        json=_create_payload(assignee_id=actor),
    ).json()
    qs = "?farm_id=台中港曲風場"

    client.post(f"/api/workflow/work-orders/{created['id']}/dispatch{qs}",
                json={"actor_id": actor})
    client.post(f"/api/workflow/work-orders/{created['id']}/start-work{qs}",
                json={"require_weather_window": False})
    client.post(
        f"/api/workflow/work-orders/{created['id']}/finish{qs}",
        json={"actual_hours": 1.0, "followup_kind": "none"},
    )
    r = client.post(
        f"/api/workflow/work-orders/{created['id']}/reject{qs}",
        json={"reject_reason": "缺照片"},
    )
    assert r.json()["status"] == "in_progress"
    assert r.json()["reject_reason"] == "缺照片"


def test_reopen_uses_independent_reason_field(client):
    """walkthrough fix #7：reopen_reason 走獨立欄位，不污染 followup_note。

    Review fix #4：要 close 工單必須走 signoff approve flow，不能直接 /approve。
    """
    actor = str(uuid4())
    created = client.post(
        "/api/workflow/work-orders",
        json=_create_payload(assignee_id=actor),
    ).json()
    farm_id = "台中港曲風場"
    qs = f"?farm_id={farm_id}"

    client.post(f"/api/workflow/work-orders/{created['id']}/dispatch{qs}",
                json={"actor_id": actor})
    client.post(f"/api/workflow/work-orders/{created['id']}/start-work{qs}",
                json={"require_weather_window": False})
    client.post(
        f"/api/workflow/work-orders/{created['id']}/finish{qs}",
        json={
            "actual_hours": 1.0,
            "followup_kind": "none",
            "followup_note": "完工觀察一週",
        },
    )
    # 走 signoff approve flow 把工單帶到 CLOSED
    for level in ("employee", "leader"):
        pending = client.get(
            f"/api/workflow/approvals/pending?farm_id={farm_id}&level={level}"
        ).json()
        client.post(
            f"/api/workflow/approvals/{pending['items'][0]['step']['id']}/approve{qs}",
            json={"actor_id": actor},
        )

    r = client.post(
        f"/api/workflow/work-orders/{created['id']}/reopen{qs}",
        json={"reopen_reason": "同部件再故障"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "reopened"
    assert data["reopen_reason"] == "同部件再故障"
    assert data["followup_note"] == "完工觀察一週"  # 不被污染


def test_offshore_start_work_blocks_without_weather_window(client):
    """offshore farm caller 傳 require_weather_window=true → 沒 ww_id 工單拒絕。"""
    actor = str(uuid4())
    created = client.post(
        "/api/workflow/work-orders",
        json=_create_payload(assignee_id=actor),
    ).json()
    qs = "?farm_id=台中港曲風場"

    client.post(f"/api/workflow/work-orders/{created['id']}/dispatch{qs}",
                json={"actor_id": actor})

    r = client.post(
        f"/api/workflow/work-orders/{created['id']}/start-work{qs}",
        json={"require_weather_window": True},
    )
    # state machine raise InvalidTransition (guard fail) → 422
    assert r.status_code == 422
    assert "weather_window_id" in r.json()["detail"]


def test_cancel_with_reason_persists(client):
    actor = str(uuid4())
    created = client.post(
        "/api/workflow/work-orders",
        json=_create_payload(assignee_id=actor),
    ).json()

    r = client.post(
        f"/api/workflow/work-orders/{created['id']}/cancel?farm_id=台中港曲風場",
        json={"cancel_reason": "客戶要求暫停"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "cancelled"
    assert data["cancel_reason"] == "客戶要求暫停"


def test_finish_422_missing_actual_hours(client):
    """finish 缺 actual_hours → 422 validation（pydantic）。"""
    actor = str(uuid4())
    created = client.post(
        "/api/workflow/work-orders",
        json=_create_payload(assignee_id=actor),
    ).json()
    qs = "?farm_id=台中港曲風場"
    client.post(f"/api/workflow/work-orders/{created['id']}/dispatch{qs}",
                json={"actor_id": actor})
    client.post(f"/api/workflow/work-orders/{created['id']}/start-work{qs}",
                json={"require_weather_window": False})

    r = client.post(
        f"/api/workflow/work-orders/{created['id']}/finish{qs}",
        json={"followup_kind": "none"},  # 缺 actual_hours
    )
    assert r.status_code == 422


def test_update_progress_422_empty_note(client):
    actor = str(uuid4())
    created = client.post(
        "/api/workflow/work-orders",
        json=_create_payload(assignee_id=actor),
    ).json()
    qs = "?farm_id=台中港曲風場"
    client.post(f"/api/workflow/work-orders/{created['id']}/dispatch{qs}",
                json={"actor_id": actor})
    client.post(f"/api/workflow/work-orders/{created['id']}/start-work{qs}",
                json={"require_weather_window": False})

    # pydantic schema 限定 note min_length=1 → 422
    r = client.post(
        f"/api/workflow/work-orders/{created['id']}/update-progress{qs}",
        json={"actor_id": actor, "note": ""},
    )
    assert r.status_code == 422
