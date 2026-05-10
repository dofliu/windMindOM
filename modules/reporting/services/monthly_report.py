"""Monthly report service — HTML (Jinja2) + PDF (reportlab) render（WMOM-20260509-08）。

責任：吃 ``MonthlyReportData``（kpi_calculator 算出的結構化資料），輸出 bytes：
- ``render_html(data) -> str``：Jinja2 渲染 HTML（給瀏覽器 preview / 未來 WeasyPrint）
- ``render_pdf(data) -> bytes``：reportlab Platypus 直接拼 PDF（Windows / Linux 都跑）

設計決策：
- 為何選 reportlab 而非 WeasyPrint：劉老師 Windows 機器 WeasyPrint 撞 Pango/GObject
  native DLL 衝突，部署 / demo 環境風險高；reportlab pure-Python 跨平台。
- Jinja2 仍保留：HTML preview 在 dev mode 比 PDF 快很多，且未來換 WeasyPrint
  可直接吃同一份 template。
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from modules.reporting.schemas.reporting_schemas import MonthlyReportData
from reportlab.lib import colors

from modules.reporting.services._pdf_styles import (
    BODY as _BODY,
    BODY_BLACK,
    BORDER_GREY,
    META as _META,
    PANEL_BG,
    PRIMARY_GREEN,
    SECTION as _SECTION,
    SUBTITLE as _SUBTITLE,
    TITLE as _TITLE,
)

_logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# Jinja2 environment（lazy）
# ─────────────────────────────────────────────────────────────────────────


_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_jinja_env: Environment | None = None


def _get_jinja_env() -> Environment:
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
    return _jinja_env


# ─────────────────────────────────────────────────────────────────────────
# HTML render
# ─────────────────────────────────────────────────────────────────────────


_CSS_PATH = Path(__file__).resolve().parent.parent / "static" / "reporting.css"


def _load_inline_css() -> str:
    """Review fix (should-fix #4)：HTML preview 從 API endpoint 回傳時，
    瀏覽器 GET 不到 ``reporting.css``（router 沒掛 static），所以 inline 進
    ``<style>`` 標籤；template 用 ``{{ inline_css }}`` 渲染。
    """
    try:
        return _CSS_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        _logger.warning("CSS file not found at %s; rendering without styles", _CSS_PATH)
        return ""


def render_html(data: MonthlyReportData, *, template: str = "monthly_report.html") -> str:
    """Render HTML 字串。

    Args:
        data: KPI calculator 算出的月報資料
        template: 預設 ``monthly_report.html``，可換 alt template
    """
    env = _get_jinja_env()
    tmpl = env.get_template(template)
    return tmpl.render(data=data, inline_css=_load_inline_css())


# ─────────────────────────────────────────────────────────────────────────
# PDF render — reportlab Platypus
# ─────────────────────────────────────────────────────────────────────────


def _money(value: Any) -> str:
    """格式化貨幣（千分位 + 兩位小數）。"""
    return "{:,.2f}".format(value)


def _pct(value: float) -> str:
    return "{:.2%}".format(value)


def _kpi_table(data: MonthlyReportData) -> Table:
    rows = [
        ["當月總成本", f"{_money(data.kpi.grand_total_cost)} EUR"],
        ["實際確認比例", _pct(data.kpi.confirmed_cost_ratio)],
        ["當月完工工單", f"{data.kpi.work_orders_finished} 張"],
        ["平均維修工時", f"{data.kpi.average_repair_hours:.2f} 小時/張"],
        ["時間可用率", _pct(data.kpi.time_availability)],
    ]
    tbl = Table(rows, colWidths=[55 * mm, 100 * mm])
    tbl.setStyle(_two_col_style())
    return tbl


def _two_col_style() -> TableStyle:
    return TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), PANEL_BG),
        ("TEXTCOLOR", (0, 0), (-1, -1), BODY_BLACK),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER_GREY),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, BORDER_GREY),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ])


def _cost_breakdown_table(data: MonthlyReportData) -> Table:
    header = ["類別 (Category)", "估計", "確認", "合計"]
    rows: list[list[Any]] = [header]
    for item in data.cost.by_category:
        rows.append([
            item.category,
            _money(item.estimated),
            _money(item.confirmed),
            _money(item.total),
        ])
    rows.append([
        "合計",
        _money(data.cost.estimated_total),
        _money(data.cost.confirmed_total),
        _money(data.cost.grand_total),
    ])
    tbl = Table(rows, colWidths=[55 * mm, 33 * mm, 33 * mm, 34 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("BACKGROUND", (0, -1), (-1, -1), PANEL_BG),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER_GREY),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, BORDER_GREY),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return tbl


def _wo_summary_table(data: MonthlyReportData) -> Table:
    header = ["類型 (Type)", "完工", "關閉", "進行中"]
    rows: list[list[Any]] = [header]
    for stat in data.work_orders.by_type:
        rows.append([stat.type, str(stat.finished), str(stat.closed), str(stat.in_progress)])
    rows.append([
        "合計",
        str(data.work_orders.total_finished),
        str(data.work_orders.total_closed),
        str(data.work_orders.total_in_progress),
    ])
    tbl = Table(rows, colWidths=[55 * mm, 33 * mm, 33 * mm, 34 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("BACKGROUND", (0, -1), (-1, -1), PANEL_BG),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER_GREY),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, BORDER_GREY),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return tbl


def _availability_table(data: MonthlyReportData) -> Table:
    rows = [
        ["時間可用率 (Time)", _pct(data.availability.time_availability)],
        ["能量可用率 (Energy)", _pct(data.availability.energy_availability)],
        ["區間總時數", f"{data.availability.total_hours_in_period:.1f} hrs"],
        ["停機工時", f"{data.availability.downtime_hours:.2f} hrs"],
        ["資料來源", data.availability.source],
    ]
    tbl = Table(rows, colWidths=[55 * mm, 100 * mm])
    tbl.setStyle(_two_col_style())
    return tbl


def render_pdf(data: MonthlyReportData) -> bytes:
    """Render PDF bytes via reportlab Platypus。

    輸出包含 5 區塊：封面 / KPI / cost breakdown / work order stats / availability /
    重大事件 timeline（若有）。
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Monthly Report — {data.farm_id} {data.year}-{data.month:02d}",
        author="windMindOM",
    )
    story: list[Any] = []

    # ── 封面 ─────────────────────────────────────────────────────────
    story.append(Paragraph("月運維報表 / Monthly Operations Report", _TITLE))
    story.append(Paragraph(
        f"{data.farm_name or data.farm_id} — {data.year} 年 {data.month} 月",
        _SUBTITLE,
    ))
    story.append(Paragraph(
        f"區間：{data.period_start.strftime('%Y-%m-%d')} → {data.period_end.strftime('%Y-%m-%d')}",
        _META,
    ))
    story.append(Paragraph(
        f"產出時間：{data.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        _META,
    ))
    story.append(Spacer(1, 8 * mm))

    # ── 1. KPI ──────────────────────────────────────────────────────
    story.append(Paragraph("1. 摘要 KPI", _SECTION))
    story.append(_kpi_table(data))
    story.append(Spacer(1, 4 * mm))

    # ── 2. Cost ─────────────────────────────────────────────────────
    story.append(Paragraph("2. 成本明細（4 大類）", _SECTION))
    story.append(_cost_breakdown_table(data))
    story.append(Spacer(1, 4 * mm))

    # ── 3. Work order stats ──────────────────────────────────────────
    story.append(Paragraph("3. 工單統計", _SECTION))
    story.append(_wo_summary_table(data))
    story.append(Paragraph(
        f"當月實際維修工時加總：{data.work_orders.total_actual_hours:.2f} 小時",
        _META,
    ))
    story.append(Spacer(1, 4 * mm))

    # ── 4. Availability ──────────────────────────────────────────────
    story.append(Paragraph("4. 可用率指標", _SECTION))
    story.append(_availability_table(data))

    # ── 5. Notable events（optional）─────────────────────────────────
    if data.notable_events:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("5. 重大事件 timeline", _SECTION))
        for ev in data.notable_events:
            line = (
                f"<b>{ev.occurred_at.strftime('%m-%d %H:%M')}</b> &nbsp; "
                f"{ev.title}"
            )
            if ev.detail:
                line += f"<br/><font color='#6a7176'>　{ev.detail}</font>"
            story.append(Paragraph(line, _BODY))
            story.append(Spacer(1, 2 * mm))

    # ── footer paragraph ────────────────────────────────────────────
    # 註：inline <font> 標籤的 color attr 需要 hex 字串格式，不接 HexColor 物件，
    # 故這裡保留字面值（與 _pdf_styles.FOOTER_GREY 同色 #9aa0a6）。
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph(
        f"<font color='#9aa0a6' size='8'>"
        f"windMindOM 月報 — {data.farm_id} — generated "
        f"{data.generated_at.strftime('%Y-%m-%d')}</font>",
        _BODY,
    ))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    _logger.info(
        "Monthly report PDF rendered: farm=%s, month=%d-%02d, size=%d bytes",
        data.farm_id, data.year, data.month, len(pdf_bytes),
    )
    return pdf_bytes


# 預留：未來分頁切割（資料量大時 PageBreak）
__all__ = ["render_html", "render_pdf"]
_ = PageBreak  # 留給未來
