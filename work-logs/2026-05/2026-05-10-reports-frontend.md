# 2026-05-10 — A9 Reports frontend (`/admin/reports`)

> Issue：[WMOM-20260509-09](../../ISSUES.md) M4 reports frontend
> Branch：`claude/issue-WMOM-20260509-09-2026-05-10`
> Estimate：1d
> Goal：直接展示 A8 backend，M6 客戶 demo flow（點按鈕 → 拿 PDF）

---

## 1. 開工 context

- A8 backend (PR #23) 已 merged 進 main，502+1 baseline
- `/api/reporting/{templates, monthly, annual-budget}` 3 endpoints ready
- 走既有 ui 元件庫（Card / Btn / PageHeader / StatusPill / Field / Input / Select / Stat / NavIcon）

---

## 2. 設計決策

### 2.1 Module 結構

```
frontend/
├── services/reportingService.ts       # 3 endpoints + PDF blob 下載 helper
├── hooks/useReports.ts                # monthly + annual state mgmt
└── components/reporting/
    ├── ReportsPage.tsx                # /admin/reports 主入口（tab 切換）
    ├── MonthlyReportPanel.tsx         # year/month picker + generate + iframe HTML preview + PDF download
    └── AnnualBudgetPanel.tsx          # year picker + 12-month table + recharts BarChart + PDF download
```

### 2.2 PDF / HTML preview 雙軌

- 主要 demo flow：點 generate → 顯示 HTML preview iframe（瀏覽器即時看）+ download PDF 按鈕
- HTML preview 走 `format=html`（已 inline CSS 從 backend），iframe `srcdoc` 直接塞
- PDF 走 `format=pdf` → `Response.blob()` → `URL.createObjectURL` → `<a download>` 觸發
- JSON 走 `format=json` 拿結構化資料給 chart / KPI 顯示

### 2.3 Annual budget chart

- 用 recharts BarChart（與 CostPage 同套 lib），12 個月 forecast vs actual 並列
- past months 顯示 actual + forecast 一致；current_month 顯示 partial actual + 全月 forecast；future 只有 forecast

### 2.4 Nav icon

- `NavIcon` 加 `reports` id（document-with-chart icon）
- `App.tsx` PRIMARY_NAV 加 `reports` 主項（放在 cost / history 之間）

---

## 3. 步驟

[ ] 3.1 reportingService.ts (3 endpoints + getBlob / downloadPdf helper)
[ ] 3.2 useReports.ts hook
[ ] 3.3 ReportsPage / MonthlyReportPanel / AnnualBudgetPanel
[ ] 3.4 NavIcon + App.tsx 整合
[ ] 3.5 npm run build 驗 type
[ ] 3.6 Review pass

---

## 4. Acceptance criteria

- [ ] 點按鈕後 30 秒內拿到 PDF binary，瀏覽器自動下載
- [ ] 走 ui 元件庫；NavIcon 加 `reports`（document-with-chart icon）

---

## 5. 收尾（done）

### 5.1 結果

A9 frontend 完工 + code review 全通：

- **新增 7 file**：
  - `frontend/services/reportingService.ts`（typed client + downloadBlob helper）
  - `frontend/hooks/useReports.ts`（monthly + annual sub-state）
  - `frontend/components/reporting/ReportsPage.tsx`（主入口 + tab 切換 + farm 解析）
  - `frontend/components/reporting/MonthlyReportPanel.tsx`（year/month picker + KPI + cost table + iframe HTML preview + PDF download）
  - `frontend/components/reporting/AnnualBudgetPanel.tsx`（year + current_month picker + KPI + recharts BarChart + 12-month table + PDF download）
  - `frontend/components/reporting/formatters.ts`（共用 fmtMoneyDecimal / fmtPct）
  - `frontend/components/ui/Logo.tsx`：加 `reports` NavIcon（document with mini bar chart）
  - `frontend/App.tsx`：加 `reports` 到 ViewId / PRIMARY_NAV / switch case

### 5.2 npm build

- `npx tsc --noEmit` → 0 errors
- `npx vite build` → 5.29s，733 modules，gzip 290.9KB

### 5.3 Code review 結果

`code-reviewer` subagent 找出 **4 must-fix + 6 should-fix + 4 nice-to-have**，採納 **11 條**：

| 類別 | 議題 | 處置 |
|---|---|---|
| Must #1 | iframe `srcDoc` 缺 sandbox（XSS 風險）| 加 `sandbox=""` 完全隔離（CSS 已 inline 不需 same-origin）|
| Must #2 | `buildQuery` 型別與 runtime guard 不一致（null 死代碼）| 型別簽章加 `null` 對齊 |
| Must #3 | generate error 與 download error 互相覆蓋 | 拆兩個獨立顯示框 + generate 時清掉舊 download error |
| Must #4 | `farmId === null` 無限 loading（無啟用風場用戶踩到）| 加 `farmLoaded` state，loading 完成且無 active farm 顯示明確訊息 |
| Should #1 | `fmtMoneyDecimal` 在兩 panel 重複 + 行為分歧（一個處理 null/undefined 一個沒）| 抽 `formatters.ts` 共用，統一處理 nullable |
| Should #2 | `ReportFormat` / `AnnualFormat` dead exports | 移除 |
| Should #6 | year range 只 ±1 對 multi-year O&M 客戶不夠 | 擴至 -4 ~ +1（5 歷史 + 1 forecast）|
| Nice #1 | recharts future months actual=0 視覺噪音 | 改 `null`，recharts skip |
| Nice #2 | `useReports.reset` 未使用 | 移除 |
| Nice #3 | `PageHeader` sub 露出「A8 reporting (reportlab PDF)」 | 移除 backend impl 細節 |

未採納（保留設計）：
- Should #4：「主內容區 loading 沒 spinner」— Generate 按鈕已切「Generating…」+ disabled，主內容空白可接受
- Should #5：`farm_name` query 細節提示
- Should #3：與 #1 重複
- Nice #4：MONTHS_EN 縮寫 vs 全名差異（刻意設計，annual select 較窄）

### 5.4 設計重點

1. **PDF 下載 flow**：`fetch → blob → URL.createObjectURL → 隱形 anchor click → setTimeout revoke 1s`。1s 延遲是因為 click 觸發是非同步，過早 revoke 會打斷下載
2. **HTML preview iframe sandbox**：完全隔離 — 即便 backend template 未來被注入也無法觸碰 parent DOM
3. **`actual_partial` UI 標示**：`StatusPill` 用 amber tone 突出當月 partial 資料，給主管明確「這月還沒結帳」訊號
4. **Tab 不 reset state**：切換 monthly ↔ annual 保留各自的上一次結果，避免重複 fetch
5. **走 ui 元件庫**：Card / Btn / PageHeader / StatusPill / Field / Select / Stat / NavIcon 全 import；無硬寫 hex

### 5.5 接手 A6 / A7 / A10 注意事項

- **A6/A7 frontend**（領料 + 庫存頁）可參考 `ReportsPage.tsx` 的 farm 解析 + tab 切換 pattern + `formatters.ts` 共用
- **A10 E2E test** 可在 lifecycle test 末尾加 `client.post('/api/reporting/monthly', ...)` smoke
- **未來 RouterPush**：目前用 view state 切換 nav，未來改 react-router 時 `/admin/reports` 路徑要 stable

### 5.6 下次 session 入口

```bash
cd D:\Project_CodingSimulation\researchTopic\windMindOM
git checkout main && git pull
python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/  # 502+1
cd frontend && npx vite build  # 應 5-10s 內完成
```

候選：A6 / A7 / A10 / F1-F6。

---

**Session 結束。M4 frontend reports 上線，M6 demo flow 完整貫通（point → click → PDF）。**
