"""Reporting services — 純 Python 服務層，不依賴 FastAPI。

- ``kpi_calculator``：聚合 cost ledger + work order + availability 資料
- ``monthly_report``：HTML (Jinja2) + PDF (reportlab) render
- ``annual_budget``：12 個月 forecast
"""

from __future__ import annotations
