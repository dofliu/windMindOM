"""Annual budget service — 12 個月 forecast（WMOM-20260509-08）。

責任：
- 給定 farm_id + year，產出 12 個月的 budget forecast
- 對「過去月份」用實際 ledger confirmed 值
- 對「未來月份」用歷史平均（前 N 個月，預設 N=3）推算
- 同步輸出 PDF / JSON 兩種

設計重點：
- 推算法簡單，不過度工程：歷史平均（``method="historical_average"``）
- 預留 ``method="linear_trend"`` hook（M5+ 可加 SciPy 線性回歸）
- 不依賴外部 forecast service，自己跑 — A5 ledger 是唯一資料源
"""

from __future__ import annotations

import io
import logging
from calendar import monthrange
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from modules.cost.repository.cost_ledger import (
    CostLedgerCategory,
    CostLedgerStatus,
)
from modules.cost.repository.cost_ledger_repository import CostLedgerRepository

from modules.reporting.schemas.reporting_schemas import (
    AnnualBudgetData,
    MonthlyBudgetEntry,
)
from modules.reporting.services._pdf_styles import (
    BORDER_GREY,
    META as _META,
    PANEL_BG,
    PRIMARY_GREEN,
    SUBTITLE as _SUBTITLE,
    TITLE as _TITLE,
)

_logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# 推算法
# ─────────────────────────────────────────────────────────────────────────


def _historical_average(
    history: list[Decimal],
    *,
    window: int = 3,
) -> Decimal:
    """前 N 個月平均（不夠 N 個就用所有可得月份）。"""
    if not history:
        return Decimal("0")
    take = history[-window:] if len(history) >= window else history
    if not take:
        return Decimal("0")
    return sum(take, Decimal("0")) / Decimal(len(take))


def _historical_average_by_category(
    history_by_cat: dict[CostLedgerCategory, list[Decimal]],
    *,
    window: int = 3,
) -> dict[str, Decimal]:
    """每類別獨立算歷史平均，回傳 dict[str, Decimal]。"""
    return {
        cat.value: _historical_average(history_by_cat.get(cat, []), window=window)
        for cat in CostLedgerCategory
    }


# ─────────────────────────────────────────────────────────────────────────
# Period helper
# ─────────────────────────────────────────────────────────────────────────


def _month_period(year: int, month: int) -> tuple[datetime, datetime]:
    period_start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        period_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        period_end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    _ = monthrange(year, month)
    return period_start, period_end


# ─────────────────────────────────────────────────────────────────────────
# 主要：compute_annual_budget
# ─────────────────────────────────────────────────────────────────────────


def compute_annual_budget(
    *,
    ledger_repo: CostLedgerRepository,
    farm_id: str,
    year: int,
    farm_name: Optional[str] = None,
    method: str = "historical_average",
    history_window: int = 3,
    current_month: Optional[int] = None,
) -> AnnualBudgetData:
    """產出某年度 12 個月 budget forecast。

    Args:
        ledger_repo: 拉歷史 confirmed cost
        farm_id, year, farm_name: 報表標頭
        method: 預測法（目前只支援 ``historical_average``）
        history_window: 歷史平均往前抓幾個月
        current_month: 「現在是幾月」— 之前的月份用實際資料，之後用 forecast。
            None 時用 ``datetime.now().month`` 推；測試傳固定值更好。
    """
    if method != "historical_average":
        raise ValueError(
            f"Unsupported method '{method}'; only 'historical_average' implemented",
        )
    # Review fix (should-fix #1)：history_window > 12 會造成 hist_month 跑負數，
    # 給明確錯誤訊息而非讓 datetime constructor 拋無意義 ValueError。
    if not (1 <= history_window <= 12):
        raise ValueError(
            f"history_window must be 1-12, got {history_window}; "
            "cross-year look-back not yet implemented"
        )
    if current_month is None:
        current_month = datetime.now(tz=timezone.utc).month
    if not (1 <= current_month <= 12):
        raise ValueError(f"current_month must be 1-12, got {current_month}")

    months: list[MonthlyBudgetEntry] = []
    annual_forecast = Decimal("0")
    annual_actual = Decimal("0")

    # 滾動歷史 buffer（從去年同月開始累積）
    rolling_history: dict[CostLedgerCategory, list[Decimal]] = {
        cat: [] for cat in CostLedgerCategory
    }

    # 先把去年最後 N 個月（按月序老 → 新）的 actual confirmed 抓進歷史 buffer，
    # 給 1 月起頭預測用。範例 window=3, year=2026 → 抓 2025-10 / 2025-11 / 2025-12。
    # （目前簡化：history_window 上限假設 ≤ 12；超過 12 要再加跨年邏輯）
    for hist_month in range(13 - history_window, 13):
        hist_start, hist_end = _month_period(year - 1, hist_month)
        hist_summary = ledger_repo.summary_by_category(
            farm_id=farm_id,
            from_date=hist_start,
            to_date=hist_end,
            status=CostLedgerStatus.CONFIRMED,
        )
        for cat in CostLedgerCategory:
            rolling_history[cat].append(hist_summary.get(cat, Decimal("0")))

    for month in range(1, 13):
        period_start, period_end = _month_period(year, month)

        if month <= current_month:
            # 當月或過去 — 用實際 confirmed
            actual_summary = ledger_repo.summary_by_category(
                farm_id=farm_id,
                from_date=period_start,
                to_date=period_end,
                status=CostLedgerStatus.CONFIRMED,
            )
            actual_by_cat = {
                cat.value: actual_summary.get(cat, Decimal("0"))
                for cat in CostLedgerCategory
            }
            actual_total = sum(actual_by_cat.values(), Decimal("0"))
            # 把實際資料推進歷史 buffer，給後續月份預測用
            for cat in CostLedgerCategory:
                rolling_history[cat].append(actual_summary.get(cat, Decimal("0")))

            # Review fix (must-fix #2)：當月（partial）vs 過去月（complete）區分。
            # current_month 那筆只是「截至產出日的部分 confirmed 金額」，不是全月實際；
            # 給單獨 method="actual_partial"，前端 / PDF 才能標示警告。
            # forecast_total 對 partial 月用歷史平均推全月（避免低估全年 forecast）。
            is_partial = month == current_month
            if is_partial:
                forecast_by_cat_full = _historical_average_by_category(
                    rolling_history, window=history_window,
                )
                forecast_total_full = sum(
                    forecast_by_cat_full.values(), Decimal("0"),
                )
            else:
                forecast_by_cat_full = actual_by_cat
                forecast_total_full = actual_total

            entry = MonthlyBudgetEntry(
                month=month,
                forecast_total=forecast_total_full,
                forecast_by_category=forecast_by_cat_full,
                actual_total=actual_total,
                method="actual_partial" if is_partial else "actual",
            )
            annual_actual += actual_total
            annual_forecast += forecast_total_full
        else:
            # 未來月 — 用歷史平均
            forecast_by_cat = _historical_average_by_category(
                rolling_history, window=history_window,
            )
            forecast_total = sum(forecast_by_cat.values(), Decimal("0"))
            entry = MonthlyBudgetEntry(
                month=month,
                forecast_total=forecast_total,
                forecast_by_category=forecast_by_cat,
                actual_total=None,
                method=method,
            )
            annual_forecast += forecast_total
            # 把 forecast 也推進歷史 buffer，連續預測時月與月才有 trend 延續
            for cat_str, v in forecast_by_cat.items():
                rolling_history[CostLedgerCategory(cat_str)].append(v)

        months.append(entry)

    return AnnualBudgetData(
        farm_id=farm_id,
        farm_name=farm_name,
        year=year,
        generated_at=datetime.now(tz=timezone.utc),
        months=months,
        annual_forecast_total=annual_forecast,
        annual_actual_total=annual_actual,
        method=method,
        notes=(
            f"預測法：{method}，歷史窗 {history_window} 個月。"
            f"current_month={current_month}（含）以前用實際 confirmed 資料。"
        ),
    )


# ─────────────────────────────────────────────────────────────────────────
# PDF render
# ─────────────────────────────────────────────────────────────────────────


def render_annual_budget_pdf(data: AnnualBudgetData) -> bytes:
    """Render annual budget PDF — 1 張 A4 + 12 個月 table。"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Annual Budget — {data.farm_id} {data.year}",
        author="windMindOM",
    )
    story: list = []

    story.append(Paragraph("年度預算 / Annual Budget Forecast", _TITLE))
    story.append(Paragraph(
        f"{data.farm_name or data.farm_id} — {data.year} 年", _SUBTITLE,
    ))
    story.append(Paragraph(
        f"產出時間：{data.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}", _META,
    ))
    story.append(Paragraph(f"預測法：{data.method}", _META))
    story.append(Spacer(1, 6 * mm))

    # 12 個月明細 table
    header = [
        "月份", "Material", "Labour", "Equipment", "Revenue Loss",
        "Forecast", "Actual",
    ]
    rows: list = [header]
    for m in data.months:
        rows.append([
            f"{m.month}月",
            "{:,.2f}".format(m.forecast_by_category.get("material", Decimal("0"))),
            "{:,.2f}".format(m.forecast_by_category.get("labour", Decimal("0"))),
            "{:,.2f}".format(m.forecast_by_category.get("equipment", Decimal("0"))),
            "{:,.2f}".format(m.forecast_by_category.get("revenue_loss", Decimal("0"))),
            "{:,.2f}".format(m.forecast_total),
            "{:,.2f}".format(m.actual_total) if m.actual_total is not None else "—",
        ])
    rows.append([
        "全年合計",
        "—", "—", "—", "—",
        "{:,.2f}".format(data.annual_forecast_total),
        "{:,.2f}".format(data.annual_actual_total),
    ])
    tbl = Table(
        rows,
        colWidths=[18 * mm, 24 * mm, 24 * mm, 24 * mm, 28 * mm, 26 * mm, 26 * mm],
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("BACKGROUND", (0, -1), (-1, -1), PANEL_BG),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER_GREY),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, BORDER_GREY),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(tbl)

    if data.notes:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(data.notes, _META))

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


__all__ = ["compute_annual_budget", "render_annual_budget_pdf"]
