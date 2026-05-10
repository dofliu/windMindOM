"""windMindOM reporting module — 月報 / 年度預算 PDF（WMOM-20260509-08）。

提供 4 大區塊月報（KPI / cost / work orders / availability）+ 12 個月年度預算 forecast。

主要 entry：
- ``services.kpi_calculator`` — 純資料聚合（給單元測試友善）
- ``services.monthly_report`` — Jinja2 HTML render + reportlab PDF render
- ``services.annual_budget`` — 12 個月 forecast
- ``routers.reporting_router`` — 3 endpoints (POST monthly / annual / GET templates)
"""

from __future__ import annotations
