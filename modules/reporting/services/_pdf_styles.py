"""Shared reportlab ParagraphStyle / palette（review fix — should-fix #3）。

monthly_report.py + annual_budget.py 共用，避免兩處改一個顏色要改兩次造成
PDF 視覺不一致。
"""

from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet


# ─────────────────────────────────────────────────────────────────────────
# Palette
# ─────────────────────────────────────────────────────────────────────────


PRIMARY_GREEN = colors.HexColor("#2f6f4d")
SUBTITLE_GREY = colors.HexColor("#4a5256")
META_GREY = colors.HexColor("#6a7176")
BODY_BLACK = colors.HexColor("#1d1f23")
PANEL_BG = colors.HexColor("#f3f6f4")
BORDER_GREY = colors.HexColor("#d4d8dc")
FOOTER_GREY = colors.HexColor("#9aa0a6")


# ─────────────────────────────────────────────────────────────────────────
# Paragraph styles（global，import 直接用）
# ─────────────────────────────────────────────────────────────────────────


_styles = getSampleStyleSheet()

TITLE = ParagraphStyle(
    "ReportTitle", parent=_styles["Title"], fontSize=22, leading=26,
    textColor=PRIMARY_GREEN, spaceAfter=4,
)
SUBTITLE = ParagraphStyle(
    "ReportSubtitle", parent=_styles["Heading2"], fontSize=14,
    textColor=SUBTITLE_GREY, spaceAfter=14,
)
SECTION = ParagraphStyle(
    "Section", parent=_styles["Heading2"], fontSize=13,
    textColor=PRIMARY_GREEN, spaceBefore=12, spaceAfter=6,
)
BODY = ParagraphStyle(
    "Body", parent=_styles["BodyText"], fontSize=10, leading=13,
)
META = ParagraphStyle(
    "Meta", parent=_styles["BodyText"], fontSize=9,
    textColor=META_GREY, spaceAfter=2,
)
