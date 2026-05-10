# 2026-05-10 — Reporting backend（monthly_report PDF + annual_budget）

> Issue：[WMOM-20260509-08](../../ISSUES.md) M4 reporting backend
> Branch：`claude/issue-WMOM-20260509-08-2026-05-10`
> Estimate：1.5d
> Goal：M6 demo killer feature — 客戶第一份月報沒被退

---

## 1. 開工 context

- 從 main 接手（446 + 1 xfailed），M4 backend 100% 完工
- A8 是 M4 backend 最後一塊；A5 ledger summary 已就緒可直接拼月報
- 與 A6/A7 frontend 可平行進行

---

## 2. 設計決策（開工前）

### 2.1 PDF library 選擇

Issue spec 寫「WeasyPrint 或 reportlab」二擇一。實際 probe：

```
python -c "import weasyprint" → OSError: cannot load library 'libgobject-2.0-0.dll'
python -c "import reportlab" → OK 4.2.5
```

劉老師 Windows 機器 WeasyPrint 撞 Pango/GObject native DLL 衝突（Tesseract-OCR 安裝路徑搞壞 PATH）。**決定用 reportlab**，避免後續 demo 環境鋪設踩雷。

### 2.2 HTML / PDF 雙軌

- Jinja2 HTML 仍保留（template render 容易 unit test，preview 在瀏覽器，未來可換 WeasyPrint）
- reportlab Platypus 直接吃 KPI 結構化 dict 產 PDF
- Endpoint 接 `?format=pdf|html` query

### 2.3 Availability 來源

Spec 寫「物理模擬 availability（time / energy）」。但 monitoring module 沒暴露此 metric。

**決定**：
- 寫 `availability_provider` 為 callable injectable
- Default impl：從 work order `actual_hours` 推 `time_availability = 1 - (down_hours / month_hours)`
- `energy_availability` 預設 = `time_availability`（無更精細資料）
- 留 hook 給未來物理模擬填精確值

### 2.4 Module 結構

```
modules/reporting/
├── __init__.py
├── services/
│   ├── kpi_calculator.py    # pure agg (cost + WO + avail)
│   ├── monthly_report.py    # Jinja2 + reportlab
│   └── annual_budget.py     # 12-month forecast
├── routers/
│   └── reporting_router.py  # 3 endpoints
├── schemas/
│   └── reporting_schemas.py
├── templates/
│   ├── monthly_report.html
│   └── monthly_report.css
└── tests/
    ├── test_kpi_calculator.py
    ├── test_monthly_report.py
    ├── test_annual_budget.py
    └── test_reporting_api.py
```

---

## 3. 實作步驟

[ ] 3.1 module skeleton
[ ] 3.2 kpi_calculator（agg cost + WO + avail）
[ ] 3.3 Jinja2 template + CSS
[ ] 3.4 monthly_report service（HTML + PDF）
[ ] 3.5 annual_budget service
[ ] 3.6 router + schemas + register in app.py
[ ] 3.7 25+ pytest
[ ] 3.8 整段 pytest pass + code review

---

## 4. Acceptance criteria（issue spec）

- [ ] 跑得出真實 PDF（以 fixture month data 驗 5 次）
- [ ] 月報 4 大區塊正確（KPI / cost / work orders / availability）
- [ ] 25+ pytest pass

---

## 5. 收尾（done）

### 5.1 結果

A8 backend 完工 + code review 全通：

- 新 module `modules/reporting/` ：
  - `services/_pdf_styles.py`（review fix should-fix #3：reportlab style 共用）
  - `services/kpi_calculator.py`（核心聚合邏輯）
  - `services/monthly_report.py`（Jinja2 HTML inline CSS + reportlab PDF）
  - `services/annual_budget.py`（12 個月 forecast，含 actual_partial 區隔）
  - `routers/reporting_router.py`（3 endpoints + DI factory pattern）
  - `schemas/reporting_schemas.py`（Pydantic models）
  - `templates/monthly_report.html` + `static/reporting.css`
  - 4 個 test files

### 5.2 新增 endpoints

```
GET  /api/reporting/templates                            → list 可用 template
POST /api/reporting/monthly?farm_id&year&month&format    → PDF / HTML / JSON
POST /api/reporting/annual-budget?farm_id&year&format    → PDF / JSON
```

已 register 在 `modules/monitoring/server/app.py:117-118`。

### 5.3 測試

- **48 → 56 tests**（含 8 個 review fix regression tests）
- KPI calculator: 25
- monthly_report (HTML+PDF): 11
- annual_budget: 11
- API endpoints: 11

**全 backend：446 → 502 passed, 1 xfailed**（zero regression）。

```bash
python -m pytest modules/reporting/tests/ -v   # 56 passed
python -m pytest modules/reporting/tests/ modules/workflow/tests/ modules/cost/tests/  # 502+1
```

### 5.4 Code review 結果

`code-reviewer` subagent 找出 **4 must-fix + 4 should-fix**，全數已修：

| 類別 | 議題 | 處置 |
|---|---|---|
| Must #1 | `in_progress` 跨月雙計（沒下界 + 漏 DRAFT/REOPENED） | 改用 `open_states()` + 加 `closed_at >= period_start` 上下界 + 2 個 regression tests |
| Must #2 | annual budget current_month 把 partial 當 actual | 區分 `actual_partial`，forecast_total 走歷史平均 + regression test |
| Must #3 | Content-Disposition header injection via farm_id | `_safe_filename_token` regex sanitize + 4 unit assertions |
| Must #4 | `compute_notable_events` 重複 query WO | 抽 `fetch_all_work_orders` 共用 snapshot |
| Should #1 | `history_window > 12` 崩潰 | `compute_annual_budget` 開頭 guard + regression test |
| Should #2 | `page_size=1000` hardcode | 抽模組常數 `_WO_FETCH_PAGE_SIZE` |
| Should #3 | reportlab style 兩處重複 | 抽 `services/_pdf_styles.py` 共用 |
| Should #4 | HTML preview CSS 載不到 | inline `<style>{{ inline_css }}</style>` + regression test |

Nice-to-have 4 條（未做，留 follow-up）：
- N1：`_month_period` 兩處實作（kpi vs annual_budget）— 統一
- N2：notable_events 加 `work_order_stalled` event type
- N3：`_jinja_env` 多執行緒 race（GIL 下不會錯，僅提示）
- N4：`_FARM_REGISTRY` global 跨 setter 互相重置 — design smell

### 5.5 設計決策追加

1. **Reportlab 而非 WeasyPrint**：劉老師 Windows 機器 weasyprint 撞 Pango/GObject DLL，pure-Python reportlab 跨平台 zero-dep
2. **HTML preview inline CSS**：`<link rel="stylesheet">` 在 API response 場景永遠 404；`render_html` 直接讀 `static/reporting.css` 內嵌
3. **Availability 從 work order 推算**：monitoring 沒暴露物理 availability，先用 `total_actual_hours / total_hours` 近似；留 `availability_provider` callable 給 M5 物理模擬注入
4. **`actual_partial` 與 `actual` 分離**：current_month 那筆 actual_total 是「截至產出日的部分金額」，PDF / 前端可顯示警示，避免主管誤以為已結帳
5. **`_safe_filename_token`**：Content-Disposition header 規則嚴格，任意字元註入會被瀏覽器當 filename 替換，未 auth 場景下安全敏感

### 5.6 接手 A6 / A7 / A9 / A10 注意事項

**A9 frontend `/admin/reports`** — backend 已就緒可接：
- `MonthlyReportPanel` 直接 POST `/api/reporting/monthly?format=pdf` → `Response.blob()` → `URL.createObjectURL` 觸發瀏覽器下載
- `format=html` → `iframe srcdoc=...` 預覽
- `format=json` → 自繪互動圖表
- `AnnualBudgetPanel`：先 GET json 拿 12 個月資料畫 chart.js，再點 PDF download

**A6/A7 frontend** — 不直接相關，A8 後端純獨立

**A10 E2E lifecycle test** — 未來可在 lifecycle test 末尾加：
```python
resp = client.post("/api/reporting/monthly", params={...})
assert resp.status_code == 200 and resp.content.startswith(b"%PDF-")
```
驗整個 fault → signoff → ledger → monthly report 完整鏈路。

### 5.7 下次 session 入口

```bash
cd D:\Project_CodingSimulation\researchTopic\windMindOM
git checkout main && git pull
python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/
# → expect 502+1
```

候選工作：A6 / A7 / A9 frontend，或 F1-F6 follow-up，或 A8 nice-to-have N1/N2。

---

**Session 結束。M4 backend 100% 完工 + 月報 PDF demo-ready。**
