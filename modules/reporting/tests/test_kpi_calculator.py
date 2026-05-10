"""KPI calculator unit tests（WMOM-20260509-08）。

直接打 cost_ledger.insert_in_session + WorkOrderORM 寫入 fixture data，
測 ``compute_*`` 純函式輸出正確。
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

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

from modules.reporting.services.kpi_calculator import (
    compute_availability,
    compute_cost_summary,
    compute_kpi,
    compute_monthly_report_data,
    compute_notable_events,
    compute_work_order_summary,
    fetch_all_work_orders,
    hours_in_period,
    month_period,
)


FARM = "changhua"


# ─────────────────────────────────────────────────────────────────────────
# Period helpers
# ─────────────────────────────────────────────────────────────────────────


def test_month_period_returns_utc_half_open():
    start, end = month_period(2026, 5)
    assert start == datetime(2026, 5, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_month_period_handles_december_year_rollover():
    start, end = month_period(2026, 12)
    assert end == datetime(2027, 1, 1, tzinfo=timezone.utc)


def test_month_period_rejects_invalid_month():
    with pytest.raises(ValueError, match="month must be 1-12"):
        month_period(2026, 13)
    with pytest.raises(ValueError):
        month_period(2026, 0)


def test_hours_in_period_31_day_month():
    start, end = month_period(2026, 1)  # 31 天
    assert hours_in_period(start, end) == pytest.approx(31 * 24)


# ─────────────────────────────────────────────────────────────────────────
# Fixture
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def repos(tmp_path):
    """共用 db_path 的 ledger + wo repository。"""
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")
    ledger_repo = get_cost_ledger_repository(db_path)
    wo_repo = get_wo_repository(db_path)
    yield {"ledger_repo": ledger_repo, "wo_repo": wo_repo, "db_path": db_path}
    clear_engine_cache_for_test()


def _insert_ledger(
    ledger_repo,
    *,
    farm_id=FARM,
    category=CostLedgerCategory.MATERIAL,
    amount=Decimal("100"),
    status=CostLedgerStatus.ESTIMATED,
    recorded_at=None,
    source_type=CostLedgerSourceType.MATERIAL_REQUEST,
):
    if recorded_at is None:
        recorded_at = datetime(2026, 5, 15, tzinfo=timezone.utc)
    entry = CostLedgerEntry(
        farm_id=farm_id,
        category=category,
        amount=amount,
        source_event_id=uuid4(),
        source_type=source_type,
        status=status,
        recorded_at=recorded_at,
    )
    with ledger_repo._sessionmaker() as sess:
        insert_in_session(sess, entry)
        sess.commit()
    return entry


def _insert_wo_orm(
    wo_repo,
    *,
    farm_id=FARM,
    turbine_id="WT001",
    type_="corrective",
    status="closed",
    priority="normal",
    finished_at=None,
    closed_at=None,
    actual_hours=None,
    created_at=None,
    business_key=None,
):
    """直接用 ORM 插一張完成 WO（不跑 state machine — 測試 KPI calculator 用）。"""
    from sqlalchemy.orm import Session

    if created_at is None:
        created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    if business_key is None:
        business_key = f"WO-TEST-{uuid4().hex[:8]}"
    orm = WorkOrderORM(
        id=str(uuid4()),
        business_key=business_key,
        farm_id=farm_id,
        turbine_id=turbine_id,
        type=type_,
        status=status,
        priority=priority,
        title="t",
        description="d",
        finished_at=finished_at,
        closed_at=closed_at,
        actual_hours=actual_hours,
        followup_kind="none",
        created_at=created_at,
        updated_at=created_at,
    )
    with Session(wo_repo._engine) as sess:
        sess.add(orm)
        sess.commit()
    return orm


# ─────────────────────────────────────────────────────────────────────────
# compute_cost_summary
# ─────────────────────────────────────────────────────────────────────────


def test_cost_summary_empty_returns_4_zero_categories(repos):
    start, end = month_period(2026, 5)
    summary = compute_cost_summary(
        repos["ledger_repo"], farm_id=FARM,
        period_start=start, period_end=end,
    )
    assert len(summary.by_category) == 4
    assert {c.category for c in summary.by_category} == {
        "material", "labour", "equipment", "revenue_loss",
    }
    assert summary.grand_total == Decimal("0")


def test_cost_summary_aggregates_estimated_and_confirmed(repos):
    _insert_ledger(repos["ledger_repo"], category=CostLedgerCategory.MATERIAL,
                   amount=Decimal("100"), status=CostLedgerStatus.ESTIMATED)
    _insert_ledger(repos["ledger_repo"], category=CostLedgerCategory.MATERIAL,
                   amount=Decimal("50"), status=CostLedgerStatus.CONFIRMED)
    _insert_ledger(repos["ledger_repo"], category=CostLedgerCategory.LABOUR,
                   amount=Decimal("200"), status=CostLedgerStatus.CONFIRMED)
    start, end = month_period(2026, 5)
    summary = compute_cost_summary(
        repos["ledger_repo"], farm_id=FARM, period_start=start, period_end=end,
    )
    by_cat = {c.category: c for c in summary.by_category}
    assert by_cat["material"].estimated == Decimal("100")
    assert by_cat["material"].confirmed == Decimal("50")
    assert by_cat["material"].total == Decimal("150")
    assert by_cat["labour"].confirmed == Decimal("200")
    assert summary.estimated_total == Decimal("100")
    assert summary.confirmed_total == Decimal("250")
    assert summary.grand_total == Decimal("350")


def test_cost_summary_filters_by_period(repos):
    # Apr entry — should be excluded
    _insert_ledger(repos["ledger_repo"],
                   amount=Decimal("999"),
                   recorded_at=datetime(2026, 4, 30, 23, tzinfo=timezone.utc))
    # May entry — included
    _insert_ledger(repos["ledger_repo"],
                   amount=Decimal("100"),
                   recorded_at=datetime(2026, 5, 1, tzinfo=timezone.utc))
    start, end = month_period(2026, 5)
    summary = compute_cost_summary(
        repos["ledger_repo"], farm_id=FARM, period_start=start, period_end=end,
    )
    assert summary.grand_total == Decimal("100")


# ─────────────────────────────────────────────────────────────────────────
# compute_work_order_summary
# ─────────────────────────────────────────────────────────────────────────


def test_wo_summary_empty(repos):
    start, end = month_period(2026, 5)
    items = fetch_all_work_orders(repos["wo_repo"], farm_id=FARM)
    s = compute_work_order_summary(items, period_start=start, period_end=end)
    assert s.total_finished == 0
    assert s.total_closed == 0
    assert s.total_in_progress == 0
    assert s.total_actual_hours == 0.0


def test_wo_summary_counts_finished_and_actual_hours(repos):
    _insert_wo_orm(
        repos["wo_repo"],
        type_="corrective", status="closed",
        finished_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        closed_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
        actual_hours=4.5,
    )
    _insert_wo_orm(
        repos["wo_repo"],
        type_="preventive", status="closed",
        finished_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        closed_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        actual_hours=2.0,
    )
    start, end = month_period(2026, 5)
    items = fetch_all_work_orders(repos["wo_repo"], farm_id=FARM)
    s = compute_work_order_summary(items, period_start=start, period_end=end)
    assert s.total_finished == 2
    assert s.total_closed == 2
    assert s.total_actual_hours == pytest.approx(6.5)
    by_type = {x.type: x for x in s.by_type}
    assert by_type["corrective"].finished == 1
    assert by_type["preventive"].finished == 1
    assert by_type["inspection"].finished == 0


def test_wo_summary_excludes_other_period(repos):
    # April — excluded
    _insert_wo_orm(
        repos["wo_repo"], type_="corrective", status="closed",
        finished_at=datetime(2026, 4, 28, tzinfo=timezone.utc),
        actual_hours=10.0,
    )
    start, end = month_period(2026, 5)
    items = fetch_all_work_orders(repos["wo_repo"], farm_id=FARM)
    s = compute_work_order_summary(items, period_start=start, period_end=end)
    assert s.total_finished == 0
    assert s.total_actual_hours == 0.0


def test_wo_summary_in_progress_state_counts(repos):
    _insert_wo_orm(
        repos["wo_repo"], type_="inspection", status="in_progress",
        created_at=datetime(2026, 5, 5, tzinfo=timezone.utc),
    )
    _insert_wo_orm(
        repos["wo_repo"], type_="corrective", status="dispatched",
        created_at=datetime(2026, 5, 6, tzinfo=timezone.utc),
    )
    start, end = month_period(2026, 5)
    items = fetch_all_work_orders(repos["wo_repo"], farm_id=FARM)
    s = compute_work_order_summary(items, period_start=start, period_end=end)
    assert s.total_in_progress == 2


def test_wo_summary_in_progress_includes_draft_and_reopened(repos):
    """Review fix #1：DRAFT 與 REOPENED 都是 open state，必須計入 in_progress。"""
    _insert_wo_orm(
        repos["wo_repo"], type_="corrective", status="draft",
        created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    _insert_wo_orm(
        repos["wo_repo"], type_="preventive", status="reopened",
        created_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
    )
    start, end = month_period(2026, 5)
    items = fetch_all_work_orders(repos["wo_repo"], farm_id=FARM)
    s = compute_work_order_summary(items, period_start=start, period_end=end)
    assert s.total_in_progress == 2


def test_wo_summary_in_progress_excludes_already_closed_before_period(repos):
    """Review fix #1：closed_at < period_start 的工單不該算為「期間結尾仍 in_progress」。

    雖然 status 仍是 closed 不在 open_states，但這條 guard 是給 status 已 cancelled
    或 reopened 的歷史單防 regression。
    """
    # 4 月已 closed 的 corrective 不該被計入 5 月的 in_progress（status=closed 自然排除）
    _insert_wo_orm(
        repos["wo_repo"], type_="corrective", status="closed",
        created_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        closed_at=datetime(2026, 4, 15, tzinfo=timezone.utc),
        finished_at=datetime(2026, 4, 14, tzinfo=timezone.utc),
        actual_hours=2.0,
    )
    start, end = month_period(2026, 5)
    items = fetch_all_work_orders(repos["wo_repo"], farm_id=FARM)
    s = compute_work_order_summary(items, period_start=start, period_end=end)
    assert s.total_in_progress == 0


def test_wo_summary_in_progress_does_not_double_count_cross_month(repos):
    """Review fix #1（核心 regression）：3 月建立、目前仍 dispatched 的工單，
    在 3/4/5 月月報應該各算 1 次 in_progress（每月當下都仍在進行），
    但不該在「跑 5 月月報」時被當成「5 月新增」。
    """
    _insert_wo_orm(
        repos["wo_repo"], type_="corrective", status="dispatched",
        created_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
    )
    items = fetch_all_work_orders(repos["wo_repo"], farm_id=FARM)

    may_start, may_end = month_period(2026, 5)
    feb_start, feb_end = month_period(2026, 2)

    # 5 月月報仍應計入（持續進行中）— 1
    s_may = compute_work_order_summary(
        items, period_start=may_start, period_end=may_end,
    )
    assert s_may.total_in_progress == 1

    # 但 2 月月報（建單前）不該計入 — 0
    s_feb = compute_work_order_summary(
        items, period_start=feb_start, period_end=feb_end,
    )
    assert s_feb.total_in_progress == 0


# ─────────────────────────────────────────────────────────────────────────
# compute_availability
# ─────────────────────────────────────────────────────────────────────────


def test_availability_default_provider_uses_wo_actual_hours(repos):
    """work_order_derived 路徑 — downtime 從 actual_hours 推算。"""
    _insert_wo_orm(
        repos["wo_repo"], type_="corrective", status="closed",
        finished_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        actual_hours=24.0,  # 1 天 downtime
    )
    start, end = month_period(2026, 5)  # 31 days = 744 hours
    items = fetch_all_work_orders(repos["wo_repo"], farm_id=FARM)
    wo_summary = compute_work_order_summary(items, period_start=start, period_end=end)
    avail = compute_availability(
        farm_id=FARM, period_start=start, period_end=end,
        work_order_summary=wo_summary,
    )
    assert avail.source == "work_order_derived"
    assert avail.downtime_hours == 24.0
    assert avail.total_hours_in_period == pytest.approx(744.0)
    assert avail.time_availability == pytest.approx(1 - 24 / 744, rel=1e-6)
    assert avail.energy_availability == avail.time_availability


def test_availability_clamps_when_downtime_exceeds_period():
    """downtime > total_hours → time_availability clamps to 0。"""
    from modules.reporting.schemas.reporting_schemas import WorkOrderSummary

    start, end = month_period(2026, 5)
    summary = WorkOrderSummary(
        by_type=[], total_finished=0, total_closed=0, total_in_progress=0,
        total_actual_hours=10000.0,  # > 744
    )
    avail = compute_availability(
        farm_id=FARM, period_start=start, period_end=end,
        work_order_summary=summary,
    )
    assert avail.time_availability == 0.0


def test_availability_provider_overrides_default():
    """注入的 provider 取代 work_order 推算 → source=physics_simulator。"""
    from modules.reporting.schemas.reporting_schemas import WorkOrderSummary

    start, end = month_period(2026, 5)
    summary = WorkOrderSummary(
        by_type=[], total_finished=0, total_closed=0, total_in_progress=0,
        total_actual_hours=24.0,
    )

    def provider(_farm, _start, _end):
        return (0.95, 0.92)

    avail = compute_availability(
        farm_id=FARM, period_start=start, period_end=end,
        work_order_summary=summary, provider=provider,
    )
    assert avail.source == "physics_simulator"
    assert avail.time_availability == 0.95
    assert avail.energy_availability == 0.92


def test_availability_provider_returning_none_falls_back():
    """provider 回 None → 走 work_order 推算。"""
    from modules.reporting.schemas.reporting_schemas import WorkOrderSummary

    start, end = month_period(2026, 5)
    summary = WorkOrderSummary(
        by_type=[], total_finished=0, total_closed=0, total_in_progress=0,
        total_actual_hours=0.0,
    )
    avail = compute_availability(
        farm_id=FARM, period_start=start, period_end=end,
        work_order_summary=summary,
        provider=lambda *_a: None,
    )
    assert avail.source == "work_order_derived"
    assert avail.time_availability == 1.0


# ─────────────────────────────────────────────────────────────────────────
# compute_kpi
# ─────────────────────────────────────────────────────────────────────────


def test_kpi_zero_division_safe():
    """0 工單 / 0 成本 → ratio + avg = 0。"""
    from modules.reporting.schemas.reporting_schemas import (
        AvailabilityMetrics, CostSummary, WorkOrderSummary,
    )
    cost = CostSummary(
        by_category=[], estimated_total=Decimal("0"),
        confirmed_total=Decimal("0"), grand_total=Decimal("0"),
    )
    wo = WorkOrderSummary(
        by_type=[], total_finished=0, total_closed=0, total_in_progress=0,
        total_actual_hours=0.0,
    )
    avail = AvailabilityMetrics(
        time_availability=1.0, energy_availability=1.0,
        total_hours_in_period=744.0, downtime_hours=0.0,
        source="work_order_derived",
    )
    kpi = compute_kpi(cost=cost, work_orders=wo, availability=avail)
    assert kpi.confirmed_cost_ratio == 0.0
    assert kpi.average_repair_hours == 0.0
    assert kpi.work_orders_finished == 0
    assert kpi.time_availability == 1.0


def test_kpi_normal_calculation():
    from modules.reporting.schemas.reporting_schemas import (
        AvailabilityMetrics, CostBreakdownItem, CostSummary, WorkOrderSummary,
    )
    cost = CostSummary(
        by_category=[
            CostBreakdownItem(category="material",
                              estimated=Decimal("200"), confirmed=Decimal("800"),
                              total=Decimal("1000")),
        ],
        estimated_total=Decimal("200"),
        confirmed_total=Decimal("800"),
        grand_total=Decimal("1000"),
    )
    wo = WorkOrderSummary(
        by_type=[], total_finished=4, total_closed=4, total_in_progress=0,
        total_actual_hours=20.0,
    )
    avail = AvailabilityMetrics(
        time_availability=0.97, energy_availability=0.95,
        total_hours_in_period=744.0, downtime_hours=20.0,
        source="work_order_derived",
    )
    kpi = compute_kpi(cost=cost, work_orders=wo, availability=avail)
    assert kpi.confirmed_cost_ratio == pytest.approx(0.8)
    assert kpi.average_repair_hours == pytest.approx(5.0)
    assert kpi.grand_total_cost == Decimal("1000")


# ─────────────────────────────────────────────────────────────────────────
# compute_notable_events
# ─────────────────────────────────────────────────────────────────────────


def test_notable_events_filters_by_priority(repos):
    _insert_wo_orm(
        repos["wo_repo"], priority="normal",
        created_at=datetime(2026, 5, 5, tzinfo=timezone.utc),
        finished_at=datetime(2026, 5, 6, tzinfo=timezone.utc),
        actual_hours=2.0, status="closed",
    )
    _insert_wo_orm(
        repos["wo_repo"], priority="high",
        created_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        finished_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
        actual_hours=8.0, status="closed",
    )
    start, end = month_period(2026, 5)
    items = fetch_all_work_orders(repos["wo_repo"], farm_id=FARM)
    events = compute_notable_events(items, period_start=start, period_end=end)
    # high priority WO 創建 + 完工 = 2 個 events
    assert len(events) == 2
    assert all("HIGH" in e.title for e in events)


# ─────────────────────────────────────────────────────────────────────────
# compute_monthly_report_data — 整合
# ─────────────────────────────────────────────────────────────────────────


def test_monthly_report_data_full_assembly(repos):
    # cost：material 估 100 / 確 50；labour 確 200
    _insert_ledger(repos["ledger_repo"], category=CostLedgerCategory.MATERIAL,
                   amount=Decimal("100"), status=CostLedgerStatus.ESTIMATED)
    _insert_ledger(repos["ledger_repo"], category=CostLedgerCategory.MATERIAL,
                   amount=Decimal("50"), status=CostLedgerStatus.CONFIRMED)
    _insert_ledger(repos["ledger_repo"], category=CostLedgerCategory.LABOUR,
                   amount=Decimal("200"), status=CostLedgerStatus.CONFIRMED)
    # WO：1 張 corrective 完工 4hr，1 張 preventive 完工 2hr
    _insert_wo_orm(
        repos["wo_repo"], type_="corrective", status="closed",
        finished_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        closed_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
        actual_hours=4.0,
    )
    _insert_wo_orm(
        repos["wo_repo"], type_="preventive", status="closed",
        finished_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        closed_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        actual_hours=2.0,
    )

    data = compute_monthly_report_data(
        ledger_repo=repos["ledger_repo"],
        wo_repo=repos["wo_repo"],
        farm_id=FARM, year=2026, month=5,
        farm_name="Changhua Demo",
    )
    assert data.farm_name == "Changhua Demo"
    assert data.year == 2026
    assert data.month == 5
    assert data.cost.grand_total == Decimal("350")
    assert data.work_orders.total_finished == 2
    assert data.work_orders.total_actual_hours == pytest.approx(6.0)
    assert data.kpi.work_orders_finished == 2
    assert data.kpi.average_repair_hours == pytest.approx(3.0)
    assert data.availability.source == "work_order_derived"
    assert data.availability.time_availability < 1.0
