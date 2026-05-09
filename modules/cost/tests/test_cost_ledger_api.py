"""FastAPI cost_ledger router tests（WMOM-20260509-05）。

2 endpoints (read-only)：
- GET /api/cost/ledger
- GET /api/cost/ledger/summary
"""

from __future__ import annotations

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

from modules.cost.repository import (
    CostLedgerCategory,
    CostLedgerEntry,
    CostLedgerRepository,
    CostLedgerSourceType,
    CostLedgerStatus,
    get_cost_ledger_repository,
    insert_in_session,
)
from modules.cost.routers import ledger_router
from modules.cost.routers.cost_ledger_router import set_cost_ledger_factory
from modules.workflow.repository.work_order_repository import (
    clear_engine_cache_for_test,
)


@pytest.fixture
def client_and_repo(tmp_path):
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")

    def factory(_farm_id: str) -> CostLedgerRepository:
        return get_cost_ledger_repository(db_path)

    set_cost_ledger_factory(factory)

    app = FastAPI(title="cost-ledger-test")
    app.include_router(ledger_router)
    client = TestClient(app)
    repo = get_cost_ledger_repository(db_path)
    yield client, repo

    set_cost_ledger_factory(None)
    clear_engine_cache_for_test()


@pytest.fixture
def client(client_and_repo):
    return client_and_repo[0]


@pytest.fixture
def repo(client_and_repo):
    return client_and_repo[1]


def _insert_entry(repo, **overrides):
    base = dict(
        farm_id="changhua",
        category=CostLedgerCategory.MATERIAL,
        amount=Decimal("450.00"),
        source_event_id=uuid4(),
        source_type=CostLedgerSourceType.MATERIAL_REQUEST,
        status=CostLedgerStatus.ESTIMATED,
    )
    base.update(overrides)
    entry = CostLedgerEntry(**base)
    with repo._sessionmaker() as sess:
        insert_in_session(sess, entry)
        sess.commit()
    return entry


# ─────────────────────────────────────────────────────────────────────────
# GET /api/cost/ledger
# ─────────────────────────────────────────────────────────────────────────


def test_list_ledger_empty(client):
    resp = client.get("/api/cost/ledger", params={"farm_id": "changhua"})
    assert resp.status_code == 200
    assert resp.json() == {"total": 0, "items": []}


def test_list_ledger_returns_entries(client, repo):
    _insert_entry(repo)
    _insert_entry(repo, category=CostLedgerCategory.LABOUR)
    resp = client.get("/api/cost/ledger", params={"farm_id": "changhua"})
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_list_filter_by_category(client, repo):
    _insert_entry(repo, category=CostLedgerCategory.MATERIAL)
    _insert_entry(repo, category=CostLedgerCategory.LABOUR)
    resp = client.get(
        "/api/cost/ledger",
        params={"farm_id": "changhua", "category": "material"},
    )
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["category"] == "material"


def test_list_filter_by_status(client, repo):
    _insert_entry(repo, status=CostLedgerStatus.ESTIMATED)
    _insert_entry(repo, status=CostLedgerStatus.CONFIRMED)
    resp = client.get(
        "/api/cost/ledger",
        params={"farm_id": "changhua", "status": "confirmed"},
    )
    assert resp.json()["total"] == 1


def test_list_filter_by_source_type(client, repo):
    _insert_entry(repo, source_type=CostLedgerSourceType.MATERIAL_REQUEST)
    _insert_entry(repo, source_type=CostLedgerSourceType.WORK_ORDER)
    resp = client.get(
        "/api/cost/ledger",
        params={"farm_id": "changhua", "source_type": "work_order"},
    )
    assert resp.json()["total"] == 1


def test_list_filter_by_date_range(client, repo):
    _insert_entry(repo, recorded_at=datetime(2026, 1, 15, tzinfo=timezone.utc))
    _insert_entry(repo, recorded_at=datetime(2026, 2, 15, tzinfo=timezone.utc))
    resp = client.get(
        "/api/cost/ledger",
        params={
            "farm_id": "changhua",
            "from": "2026-02-01T00:00:00+00:00",
            "to": "2026-03-01T00:00:00+00:00",
        },
    )
    data = resp.json()
    assert data["total"] == 1


def test_list_pagination(client, repo):
    for _ in range(5):
        _insert_entry(repo)
    resp = client.get(
        "/api/cost/ledger",
        params={"farm_id": "changhua", "limit": 2, "offset": 1},
    )
    data = resp.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2


# ─────────────────────────────────────────────────────────────────────────
# GET /api/cost/ledger/summary
# ─────────────────────────────────────────────────────────────────────────


def test_summary_empty(client):
    resp = client.get(
        "/api/cost/ledger/summary", params={"farm_id": "changhua"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["by_category"] == []
    assert Decimal(data["grand_total"]) == Decimal("0")


def test_summary_groups_by_category(client, repo):
    _insert_entry(repo, category=CostLedgerCategory.MATERIAL, amount=Decimal("100.00"))
    _insert_entry(repo, category=CostLedgerCategory.MATERIAL, amount=Decimal("200.00"))
    _insert_entry(repo, category=CostLedgerCategory.LABOUR, amount=Decimal("75.00"))
    resp = client.get(
        "/api/cost/ledger/summary", params={"farm_id": "changhua"}
    )
    assert resp.status_code == 200
    data = resp.json()
    by_cat = {it["category"]: Decimal(it["total"]) for it in data["by_category"]}
    assert by_cat["material"] == Decimal("300.00")
    assert by_cat["labour"] == Decimal("75.00")
    assert Decimal(data["grand_total"]) == Decimal("375.00")


def test_summary_status_confirmed_only(client, repo):
    """月報用：拿 confirmed entries 才是 actual cost。"""
    _insert_entry(
        repo, category=CostLedgerCategory.MATERIAL, amount=Decimal("100.00"),
        status=CostLedgerStatus.ESTIMATED,
    )
    _insert_entry(
        repo, category=CostLedgerCategory.MATERIAL, amount=Decimal("250.00"),
        status=CostLedgerStatus.CONFIRMED,
    )
    resp = client.get(
        "/api/cost/ledger/summary",
        params={"farm_id": "changhua", "status": "confirmed"},
    )
    data = resp.json()
    by_cat = {it["category"]: Decimal(it["total"]) for it in data["by_category"]}
    assert by_cat["material"] == Decimal("250.00")
    assert Decimal(data["grand_total"]) == Decimal("250.00")
