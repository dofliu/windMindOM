"""FastAPI reporting router tests（WMOM-20260509-08）— 3 endpoints。"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.cost.repository.cost_ledger import (
    CostLedgerCategory,
    CostLedgerEntry,
    CostLedgerSourceType,
    CostLedgerStatus,
    insert_in_session,
)
from modules.cost.repository.cost_ledger_repository import (
    get_cost_ledger_repository,
)
from modules.workflow.repository.orm_models import WorkOrderORM
from modules.workflow.repository.work_order_repository import (
    clear_engine_cache_for_test,
    get_repository as get_wo_repository,
)

from modules.reporting.routers.reporting_router import (
    router as reporting_router,
    set_ledger_factory,
    set_work_order_factory,
    set_availability_provider,
)


FARM = "changhua"


@pytest.fixture
def client(tmp_path):
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")

    def ledger_factory(_):
        return get_cost_ledger_repository(db_path)

    def wo_factory(_):
        return get_wo_repository(db_path)

    set_ledger_factory(ledger_factory)
    set_work_order_factory(wo_factory)
    set_availability_provider(None)

    app = FastAPI(title="reporting-test")
    app.include_router(reporting_router)
    yield TestClient(app), db_path

    set_ledger_factory(None)
    set_work_order_factory(None)
    set_availability_provider(None)
    clear_engine_cache_for_test()


def _seed_data(db_path):
    """Seed: 1 confirmed material entry + 1 finished WO（在 2026-05）。"""
    ledger_repo = get_cost_ledger_repository(db_path)
    wo_repo = get_wo_repository(db_path)
    entry = CostLedgerEntry(
        farm_id=FARM,
        category=CostLedgerCategory.MATERIAL,
        amount=Decimal("450"),
        source_event_id=uuid4(),
        source_type=CostLedgerSourceType.MATERIAL_REQUEST,
        status=CostLedgerStatus.CONFIRMED,
        recorded_at=datetime(2026, 5, 15, tzinfo=timezone.utc),
    )
    with ledger_repo._sessionmaker() as sess:
        insert_in_session(sess, entry)
        sess.commit()

    from sqlalchemy.orm import Session
    with Session(wo_repo._engine) as sess:
        sess.add(WorkOrderORM(
            id=str(uuid4()),
            business_key=f"WO-T-{uuid4().hex[:6]}",
            farm_id=FARM, turbine_id="WT001",
            type="corrective", status="closed", priority="high",
            title="bearing", description="d",
            finished_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
            closed_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
            actual_hours=4.5, followup_kind="none",
            created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
        ))
        sess.commit()


# ─────────────────────────────────────────────────────────────────────────
# GET /api/reporting/templates
# ─────────────────────────────────────────────────────────────────────────


def test_list_templates_returns_known_templates(client):
    c, _ = client
    resp = c.get("/api/reporting/templates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 2
    ids = [t["id"] for t in body["items"]]
    assert "monthly_v1" in ids
    assert "annual_budget_v1" in ids


# ─────────────────────────────────────────────────────────────────────────
# POST /api/reporting/monthly
# ─────────────────────────────────────────────────────────────────────────


def test_monthly_pdf_returns_pdf_binary(client):
    c, db_path = client
    _seed_data(db_path)
    resp = c.post(
        "/api/reporting/monthly",
        params={"farm_id": FARM, "year": 2026, "month": 5, "format": "pdf"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF-")
    assert "filename" in resp.headers["content-disposition"]


def test_monthly_html_returns_html(client):
    c, db_path = client
    _seed_data(db_path)
    resp = c.post(
        "/api/reporting/monthly",
        params={"farm_id": FARM, "year": 2026, "month": 5, "format": "html"},
    )
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "1. 摘要 KPI" in resp.text
    assert "2. 成本明細" in resp.text


def test_monthly_json_returns_structured_data(client):
    c, db_path = client
    _seed_data(db_path)
    resp = c.post(
        "/api/reporting/monthly",
        params={"farm_id": FARM, "year": 2026, "month": 5, "format": "json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["farm_id"] == FARM
    assert data["year"] == 2026
    assert data["month"] == 5
    assert data["kpi"]["work_orders_finished"] == 1
    assert Decimal(data["cost"]["grand_total"]) == Decimal("450")
    assert data["work_orders"]["total_finished"] == 1


def test_monthly_rejects_invalid_month(client):
    c, _ = client
    resp = c.post(
        "/api/reporting/monthly",
        params={"farm_id": FARM, "year": 2026, "month": 13, "format": "json"},
    )
    # Pydantic validates month 1-12 → 422
    assert resp.status_code == 422


def test_monthly_rejects_invalid_format(client):
    c, _ = client
    resp = c.post(
        "/api/reporting/monthly",
        params={"farm_id": FARM, "year": 2026, "month": 5, "format": "xml"},
    )
    assert resp.status_code == 422


def test_monthly_returns_4_zero_categories_for_empty_month(client):
    """空月份也能 render — 不掛機。"""
    c, _ = client
    resp = c.post(
        "/api/reporting/monthly",
        params={"farm_id": FARM, "year": 2026, "month": 1, "format": "json"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["cost"]["by_category"]) == 4
    assert data["work_orders"]["total_finished"] == 0


# ─────────────────────────────────────────────────────────────────────────
# POST /api/reporting/annual-budget
# ─────────────────────────────────────────────────────────────────────────


def test_annual_budget_json_returns_12_months(client):
    c, db_path = client
    _seed_data(db_path)
    resp = c.post(
        "/api/reporting/annual-budget",
        params={
            "farm_id": FARM, "year": 2026, "format": "json",
            "current_month": 6,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["months"]) == 12


def test_annual_budget_pdf(client):
    c, db_path = client
    _seed_data(db_path)
    resp = c.post(
        "/api/reporting/annual-budget",
        params={"farm_id": FARM, "year": 2026, "format": "pdf",
                "current_month": 6},
    )
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF-")


def test_annual_budget_rejects_unsupported_method(client):
    c, _ = client
    resp = c.post(
        "/api/reporting/annual-budget",
        params={"farm_id": FARM, "year": 2026, "method": "ml_lstm",
                "current_month": 1},
    )
    assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────
# Security: Content-Disposition header injection（review fix must-fix #3）
# ─────────────────────────────────────────────────────────────────────────


def test_monthly_pdf_sanitizes_farm_id_in_filename(tmp_path):
    """惡意 farm_id 含引號 / 分號 不該在 Content-Disposition header 注入。"""
    from modules.reporting.routers.reporting_router import (
        set_ledger_factory, set_work_order_factory, _safe_filename_token,
    )
    # 直接測 helper（API 端要 farm 存在 → 為 isolation 也加 unit-level assertion）
    assert _safe_filename_token('foo"; filename="evil') == "foo___filename__evil"
    assert _safe_filename_token("changhua") == "changhua"
    assert _safe_filename_token("../../etc/passwd") == "______etc_passwd"
    assert _safe_filename_token("") == "unknown"
