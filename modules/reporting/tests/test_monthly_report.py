"""Monthly report HTML + PDF render tests（WMOM-20260509-08）。"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.reporting.schemas.reporting_schemas import (
    AvailabilityMetrics,
    CostBreakdownItem,
    CostSummary,
    KpiHighlights,
    MonthlyReportData,
    NotableEvent,
    WorkOrderSummary,
    WorkOrderTypeStats,
)
from modules.reporting.services.monthly_report import render_html, render_pdf


def _sample_data(*, with_events: bool = False) -> MonthlyReportData:
    cost = CostSummary(
        by_category=[
            CostBreakdownItem(category="material",
                              estimated=Decimal("100"), confirmed=Decimal("50"),
                              total=Decimal("150")),
            CostBreakdownItem(category="labour",
                              estimated=Decimal("0"), confirmed=Decimal("200"),
                              total=Decimal("200")),
            CostBreakdownItem(category="equipment",
                              estimated=Decimal("0"), confirmed=Decimal("0"),
                              total=Decimal("0")),
            CostBreakdownItem(category="revenue_loss",
                              estimated=Decimal("0"), confirmed=Decimal("0"),
                              total=Decimal("0")),
        ],
        estimated_total=Decimal("100"),
        confirmed_total=Decimal("250"),
        grand_total=Decimal("350"),
    )
    wo_summary = WorkOrderSummary(
        by_type=[
            WorkOrderTypeStats(type="corrective", finished=2, closed=2, in_progress=1),
            WorkOrderTypeStats(type="preventive", finished=1, closed=1, in_progress=0),
            WorkOrderTypeStats(type="inspection", finished=0, closed=0, in_progress=0),
            WorkOrderTypeStats(type="commissioning", finished=0, closed=0, in_progress=0),
        ],
        total_finished=3, total_closed=3, total_in_progress=1,
        total_actual_hours=12.5,
    )
    avail = AvailabilityMetrics(
        time_availability=0.983,
        energy_availability=0.983,
        total_hours_in_period=744.0,
        downtime_hours=12.5,
        source="work_order_derived",
    )
    kpi = KpiHighlights(
        grand_total_cost=Decimal("350"),
        confirmed_cost_ratio=0.714,
        work_orders_finished=3,
        average_repair_hours=4.166,
        time_availability=0.983,
    )
    events: list[NotableEvent] = []
    if with_events:
        events = [
            NotableEvent(
                occurred_at=datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc),
                event_type="work_order_created",
                title="[HIGH] WO-001 — Gearbox bearing failure",
                detail="turbine=WT001",
            ),
            NotableEvent(
                occurred_at=datetime(2026, 5, 9, 18, 0, tzinfo=timezone.utc),
                event_type="work_order_finished",
                title="[HIGH] WO-001 完工",
                detail="actual_hours=8.0",
            ),
        ]
    return MonthlyReportData(
        farm_id="changhua",
        farm_name="Changhua Demo Farm",
        year=2026,
        month=5,
        period_start=datetime(2026, 5, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 6, 1, tzinfo=timezone.utc),
        generated_at=datetime(2026, 5, 31, 23, 59, tzinfo=timezone.utc),
        kpi=kpi,
        cost=cost,
        work_orders=wo_summary,
        availability=avail,
        notable_events=events,
    )


# ─────────────────────────────────────────────────────────────────────────
# HTML render
# ─────────────────────────────────────────────────────────────────────────


def test_render_html_contains_4_sections():
    html = render_html(_sample_data())
    assert "1. 摘要 KPI" in html
    assert "2. 成本明細" in html
    assert "3. 工單統計" in html
    assert "4. 可用率指標" in html


def test_render_html_renders_farm_info():
    html = render_html(_sample_data())
    assert "Changhua Demo Farm" in html
    assert "2026" in html


def test_render_html_includes_grand_total():
    html = render_html(_sample_data())
    assert "350.00" in html


def test_render_html_omits_events_section_when_empty():
    html = render_html(_sample_data(with_events=False))
    assert "5. 重大事件" not in html


def test_render_html_includes_events_section_when_present():
    html = render_html(_sample_data(with_events=True))
    assert "5. 重大事件" in html
    assert "WO-001" in html


def test_render_html_inlines_css_so_browser_preview_works():
    """Review fix (should-fix #4)：CSS 必須 inline 進 <style>，
    避免 API HTML response 載不到外部檔。
    """
    html = render_html(_sample_data())
    assert "<style>" in html
    # 從 reporting.css 取一段 selector 確認真有內嵌
    assert ".kpi-table" in html
    # 確保沒有殘留外部 link
    assert '<link rel="stylesheet" href="reporting.css">' not in html


# ─────────────────────────────────────────────────────────────────────────
# PDF render
# ─────────────────────────────────────────────────────────────────────────


def test_render_pdf_returns_non_empty_bytes():
    pdf = render_pdf(_sample_data())
    assert isinstance(pdf, bytes)
    assert len(pdf) > 1000  # 真實 PDF 至少 1KB


def test_render_pdf_starts_with_pdf_magic_bytes():
    pdf = render_pdf(_sample_data())
    assert pdf.startswith(b"%PDF-")  # PDF magic header


def test_render_pdf_with_events_larger_than_without():
    """有 events section 的 PDF 體積應該比無 events 大。"""
    pdf_no_events = render_pdf(_sample_data(with_events=False))
    pdf_with_events = render_pdf(_sample_data(with_events=True))
    assert len(pdf_with_events) > len(pdf_no_events)


def test_render_pdf_deterministic_size_for_same_input():
    """相同 input render 兩次 size 接近（reportlab 內含 timestamp 會微差）。"""
    pdf1 = render_pdf(_sample_data())
    pdf2 = render_pdf(_sample_data())
    # 容許 5% 差異（reportlab metadata 含 timestamp）
    assert abs(len(pdf1) - len(pdf2)) < max(len(pdf1), len(pdf2)) * 0.05


def test_render_pdf_handles_zero_cost_zero_wo():
    """空資料月份也能 render 不掛。"""
    data = _sample_data()
    empty = data.model_copy(update={
        "cost": CostSummary(
            by_category=[CostBreakdownItem(category=c)
                         for c in ("material", "labour", "equipment", "revenue_loss")],
            estimated_total=Decimal("0"),
            confirmed_total=Decimal("0"),
            grand_total=Decimal("0"),
        ),
        "work_orders": WorkOrderSummary(
            by_type=[], total_finished=0, total_closed=0, total_in_progress=0,
            total_actual_hours=0.0,
        ),
        "kpi": KpiHighlights(
            grand_total_cost=Decimal("0"),
            confirmed_cost_ratio=0.0,
            work_orders_finished=0,
            average_repair_hours=0.0,
            time_availability=1.0,
        ),
    })
    pdf = render_pdf(empty)
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1000
