# Work Log — 2026-06-06 — AnnualBudgetPanel component render 測試

- **Issue**: WMOM-20260606-08
- **Milestone**: M5（測試覆蓋持續工作 / EPIC-M5 測試覆蓋擴大）
- **Branch**: `claude/exciting-cori-r41vb`
- **Owner**: Claude (autonomous worker, session 2026-06-06 第八輪)

---

## 目標

為 `frontend/components/reporting/AnnualBudgetPanel.tsx`（A9 年度預算面板，
MonthlyReportPanel 的姊妹面板）補 component render 測試。本面板與月報面板同樣直接餵
**M6-6「第一份自動月報 / 預算交業主」** deliverable，但先前頁面層 `ReportsPage` 把它 mock 掉、
僅 `formatters` 有單元測試，**本面板本體零 render 覆蓋**（filter bar / 生成接線 / KPI /
method pill 三態 / 12 月明細表 / PDF 下載 async / 雙 error / empty state / 語系）。

## 決策樹

- preflight 全綠（backend 638 / 1 xfailed、frontend 628、tsc 0 error、build ✓）
- stack-aware：open PR 全為飛輪上線前 stale draft（#30–#68 共 22 筆），無進行中 WIP（依日期上輪
  MonthlyReportPanel PR #94 已 auto-merge 進 main，baseline 自 595 推進到 628）
- 決策樹 #1/#2/#3 皆無 blocker / regression / 飛輪故障 → 落 **#4 乾淨 autonomous 工作**
- 來源：上輪 handoff 明列「下一步 render 測試剩餘 untested 元件」首位即 **AnnualBudgetPanel 姊妹面板**，
  商業關聯度最高（reporting → M6-6）

## 完成內容

**新增** `frontend/components/reporting/__tests__/AnnualBudgetPanel.test.tsx`
（**35 tests，純測試零 production 變更**）。

延續既有 render 測試範式：純 props-driven 元件 + `ThemeProvider` 包裹 + jest-dom matcher +
`afterEach` cleanup。元件依賴僅 `useTheme`，無 fetch / 無自訂 hook，唯一 async 副作用是
`onDownloadPdf`（prop 注入 Promise）→ 以受控 Promise 驗下載中態 + 失敗錯誤卡。
`Btn`/`Card`/`Field`/`Select`/`Stat`/`StatusPill` 用真實 ui 元件不 mock。
**recharts 全 stub 成 marker div**（對齊 CostPage 範式），避免 jsdom 下 `ResponsiveContainer`
0 寬度的圖表渲染細節干擾文字斷言。

覆蓋的 UX 契約：
- **filter bar**：年份 + 當月（結算邊界）Select + Generate（farmId 空 disabled）；預設 year=今年、
  currentMonth=本月（1-based）；年份範圍 cur-4…cur+1（共 6 個）
- **生成接線**：Generate → `onGenerate(year, currentMonth)` 帶當前選擇（含改選年份 / 當月後）
- **loading**：Generate 鈕文字轉「生成中…」+ disabled（以 aria-label 取鈕、textContent 驗）
- **empty state**：未生成且非 loading / error 時引導卡；其餘三態不顯示
- **KPI**：farm / year / method + 2 個 Stat（全年預測 / 實際合計）`fmtMoneyDecimal` 格式化
  （€1.23M / €456.79k）；farmName 空退 farmId；notes 非空才顯示
- **圖表**：months 非空才渲染圖表卡標題；空陣列不渲染
- **明細表**：表頭 4 類別欄 + method pill 三態（actual→實際 / actual_partial→當月部分 /
  historical_average→預測）+ 各類別成本 `fmtMoneyDecimal` + actual_total null 退 dash「—」+ 年度合計列
- **PDF 下載**：data 存在才顯示鈕 → 下載中態 → 完成恢復 → 失敗錯誤卡
- **雙 error 獨立**：generate error + download error 各自顯示、generate 清舊 download error
- **語系**：lang='en' 英文 filter / 按鈕 / KPI / 表格 / 圖表標題 / method pill

## 眉角

1. **時間依賴**：預設選今年 + 本月依賴 `new Date()`，不用 fake timers（會卡死 waitFor polling），
   改用與元件相同邏輯動態算期望 year/month（`getMonth()+1`），跨月 / 跨年跑都穩定。
2. **月份標籤重複**：`1月`/`Jan` 同時出現在「當月 Select 選項」與「明細表 cell」，
   row 查詢需先 `within(screen.getByRole('table'))` scope 到表格再取 row，避免 multi-element error。
3. **Btn accessible name**：`Btn` 的 `aria-label` 固定不隨文字變，loading 態須以 aria-label 取鈕、
   再用 `toHaveTextContent('生成中…')` 驗中間態。

## Verify

- backend：未動，`pytest modules/...` **638 passed / 1 xfailed**
- frontend：`tsc --noEmit` **0 error** + `vitest run` **663 passed**（628 baseline + 35 新，零 regression）
  + `vite build` ✓

## code-reviewer

回 **2 must-fix + 3 should-fix + 3 nice-to-have，採納 6 / 婉拒 2**：

- **must#1（採納）** KPI 年份斷言假綠：裸 `screen.getByText('2026')` 在 2026 年實際命中年份 Select 的
  `<option>2026</option>`（KPI 卡把 `data.year` 渲染為大段 div 的 inline text，完整 textContent ≠ '2026'）。
  → 改以 farm span 的 `closest('div')` scope 到 KPI header + `toHaveTextContent('2026')` 精確守住。
- **must#2（採納）** `getAllByText(...).length >= 1` 過鬆（合計列渲染故障也綠）→ 改 `toHaveLength(2)`
  同時守 KPI Stat + 年度合計列兩渲染點。
- **should#3（採納）** method pill `lang='en'` 只測 Actual → 補 Feb（Partial）/ Mar（Forecast）三態。
- **should#4（採納）** `actual_total: undefined`（欄位 omit）退 dash 路徑未測 → 新增 it。
- **should#5（採納）** 補 null-guard 註解與姊妹測試一致。
- **nice#7（採納）** 補 `lang='en'` empty state 引導文字測試。
- **nice#6（婉拒）** `vi.fn` generic 形式提醒——已與姊妹測試對齊，非問題。
- **nice#8（婉拒）** `forecast_by_category` 缺 key 防禦路徑——低價值邊界，現行 backend 固定回 4 類別。

採納後測試數 35 → **37**。

## 下一步 / 接手指南

render 測試剩餘 untested 元件（依商業關聯度）：
- `UserSwitcher` / `FarmSelector`（殼層共用）
- `EventComparisonView` / `TrendChartPanel`（monitoring 分析）
- `MaintenanceHub` / `FaultInjectionPanel`（simulator demo 路徑）
- `ui/` primitives（Card / Charts / Sidebar / PageHeader 尚未全覆蓋）

非 render 方向：
- M5-2 ChromaDB（🟡 需劉老師拍板依賴 + 向量檔來源）
- M5-5 `/field/` mobile Part B-2（🟡 需劉老師拍板現場工程師身分 / 完工流程）
- **stale PR triage（#30–#68 共 22 筆）** —— 飛輪上線前的 draft，建議劉老師決定批次關閉或逐一 rebase
