# 2026-05-07 — 前端 UI 改版（A · Calm Operator + 雙主題）

> Session 類型：實作（一日全力 frontend 改版）
> Session 長度：長
> 主導：劉老師 + Claude
> 結果：**WMOM-20260507-01 close** — 220 px sidebar + 5 大頁重畫 + 共用 ui 元件庫 + 雙主題；dev server 5179 視覺 review 通過

---

## 1. Session 目標

劉老師提供 `WMOM 介面改版交接書.md` + `app/VA.jsx` 設計稿，目標把 frontend 從原本的 dark cyan + Tailwind + Orbitron（從 digiWindTurbine 繼承）整個換成 A · Calm Operator 風格：

- 220 px 左 Sidebar 取代頂部 header
- 鼠尾草綠（日）/ 翡翠玻璃（夜）兩套主題
- DM Serif Display H1 + Manrope 內文 + JetBrains Mono 數字
- 5 大頁面（Overview / Turbine / Maintenance / Cost / History）按 §4 規格重畫
- **保留全部 API / hooks 不動**

---

## 2. 實際完成

### 2.1 主要工作

- **Phase A 基礎設施**：`frontend/theme/` 兩套 palette + ThemeProvider（Context + localStorage + `<html data-theme>` 同步 + CSS variable）；`index.html` 加字型 CDN、改 body 預設、移除已無使用的 Tailwind CDN
- **Phase B 共用元件**（`frontend/components/ui/`，10 檔 + index）：`Card / Btn / PageHeader / StatusPill / Stat / Logo / NavIcon / Sidebar / BigChart / MiniSparkline / HealthBar / Field / Input / Select / ReadOnlyBox`，全走 theme palette、不寫死 hex
- **Phase C App skeleton**：`App.tsx` 重寫，移除頂部 header 改 sidebar layout（5 主頁 nav + 工具 secondary）；保留 `view` state、所有 hooks、所有 modal；FarmSelector 移入 sidebar 底部、Settings 移到 secondary nav；響應式 ≤ 768 px sidebar 收漢堡
- **Phase D 5 大頁面重寫**：
  - `FarmOverview.tsx` — Hero 4 卡 + 24h SVG 趨勢（1H/6H/24H/7D） + Cards/Summary/Table 三模式
  - `TurbineDetail.tsx` — 麵包屑 + 4 大數字 + 4 通道 sparkline + 8 子系統 HealthBar + 8-tab 詳情 + 即時告警 + 操作控制（保留全部 6 指令 + 限載）+ AI 故障診斷
  - `MaintenanceHub.tsx` — 工單表格（priority 由 SLA age 推導）+ 技師排班（漸層頭像）+ 本週日曆
  - `CostPage.tsx` — 6 KPI 卡（綜整 forecast/lcoe/monteCarlo/varFluct）+ 4 panel（recharts 走 theme）
  - `HistoryPage.tsx` — 4 欄查詢條件 + 含事件折線（FAULT/WIND/STATE 色） + 事件清單與詳情 + 最近 20 筆
- **Phase E 沿用頁套新樣式**：`FaultInjectionPanel / SettingsPage / DispatchModal / WorkOrderDetailModal / FarmSelector / TrendChartPanel / EventComparisonView` 全部換 theme + new ui 元件，功能完全不動
- **Phase F 清理**：刪除 6 個孤兒（`DataCard / Gauge / StatusIndicator / MiniTrendChart / FarmTrendChart / icons.tsx`）
- 跑 `npm install` + `npx tsc --noEmit` 解 3 個 type 錯（recharts ReferenceArea/Line key prop、SettingsPage `Object.entries` unknown、WorkOrderDetailModal FileList iteration）
- 跑 Vite dev server 在 `http://127.0.0.1:5179/`，curl 確認所有 module 200，劉老師於瀏覽器 review 5179 通過

### 2.2 卡住或延後的事

- Chrome MCP 此 session 沒接上，無法 auto 截圖 5 頁 × 2 主題；改用劉老師手動截圖 review 通過
- 主 repo 路徑（3100 dev server）還是舊版 — 預期，因為改動只在 worktree branch `claude/goofy-johnson-14d672`，PR 合進 main 後 3100 重啟才會更新

### 2.3 重大決策（如有）

不開新 ADR（不影響架構），但本次 commit message 內紀錄兩個 inline 決策：

1. **Tailwind 全退**：原規劃保留作 layout utility，但實作後 0 處使用 Tailwind class（全走 inline style + theme palette），Tailwind CDN 變 dead weight 順手移除
2. **recharts 保留 in HistoryPage / CostPage / TrendChartPanel**：互動需求高（hover、zoom、reference line）；overview / cost KPI 的趨勢圖改 SVG 跟 VA.jsx 一致

---

## 3. 產出清單

### 新增檔案（12 檔）

- `frontend/theme/themes.ts`
- `frontend/theme/ThemeProvider.tsx`
- `frontend/components/ui/Card.tsx`
- `frontend/components/ui/Btn.tsx`
- `frontend/components/ui/PageHeader.tsx`
- `frontend/components/ui/StatusPill.tsx`
- `frontend/components/ui/Stat.tsx`
- `frontend/components/ui/Logo.tsx`
- `frontend/components/ui/Sidebar.tsx`
- `frontend/components/ui/Charts.tsx`（BigChart / MiniSparkline / HealthBar）
- `frontend/components/ui/Field.tsx`（Field / Input / Select / ReadOnlyBox）
- `frontend/components/ui/index.ts`

### 修改檔案（14 檔）

- `frontend/index.html`（字型 CDN + 移除 Tailwind + CSS variable 預設）
- `frontend/App.tsx`（sidebar layout + ThemeProvider + 響應式漢堡）
- `frontend/components/FarmOverview.tsx`（5 頁重寫）
- `frontend/components/TurbineDetail.tsx`（5 頁重寫）
- `frontend/components/MaintenanceHub.tsx`（5 頁重寫）
- `frontend/components/CostPage.tsx`（5 頁重寫）
- `frontend/components/HistoryPage.tsx`（5 頁重寫）
- `frontend/components/FaultInjectionPanel.tsx`（沿用 + 新樣式）
- `frontend/components/SettingsPage.tsx`（沿用 + 新樣式）
- `frontend/components/DispatchModal.tsx`（沿用 + 新樣式）
- `frontend/components/WorkOrderDetailModal.tsx`（沿用 + 新樣式）
- `frontend/components/FarmSelector.tsx`（重畫成 sidebar 風格 dropdown）
- `frontend/components/TrendChartPanel.tsx`（換 theme 顏色）
- `frontend/components/EventComparisonView.tsx`（換 theme 顏色）

### 刪除檔案（6 檔孤兒）

- `frontend/components/DataCard.tsx`（→ Card + Stat）
- `frontend/components/Gauge.tsx`（→ HealthBar）
- `frontend/components/StatusIndicator.tsx`（→ StatusPill）
- `frontend/components/MiniTrendChart.tsx`（→ MiniSparkline）
- `frontend/components/FarmTrendChart.tsx`（→ overview 頁內嵌 BigChart）
- `frontend/components/icons.tsx`（→ Logo + NavIcon）

### 動了狀態的 issue

- WMOM-20260507-01: 新增（直接 done）

### 寫進 decision_log 的決策

- 無新 ADR

---

## 4. 下次怎麼接手

1. **PR 合回 main 後**，主 repo 3100 dev server 重啟即可看到新版（測試環境）
2. **M3 frontend 接力**（WMOM-20260504-19 `/admin/workflow/orders` 與 WMOM-20260504-20 `/admin/workflow/approval`）改用新 `components/ui/` 元件庫；不要回到 Tailwind / dark cyan 風格
3. **WMOM-20260505-25 frontend RUL/alarm 視覺化** 同樣套新元件
4. 若要動 turbine detail 內 8-tab 子系統面板，DataRow / SubsystemSection 已就位，新增 SCADA tag 加 row 即可

---

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 與用戶對話、釐清方向（todo list 對齊、3 個決策點確認） | 10% |
| 寫程式（13 個重寫 + 12 個新增 ui 元件 + 1 個 index.html） | 75% |
| Type 錯誤排除（recharts key prop / unknown narrowing） | 5% |
| Code review（self-review）+ dev server 驗證 + curl 端到端 | 10% |

---

## 6. 學到的事

- **VA.jsx 設計稿是 single source of truth 但欄位名與 production data 不一致**：design canvas 用 `power / wind / rpm / gearTemp`，production `TurbineData` 用 `powerOutput / windSpeed / rotorSpeed / temperature`。動工前先確認 type，不靠視覺照抄
- **recharts 3.x + react 19 type 不接受 `key` prop on ReferenceArea / ReferenceLine**：需要 `as React.FC<any>` cast。比每個 element 加 `// @ts-expect-error` 乾淨
- **Tailwind CDN 一旦完全不用就要拔掉**：10 KB 的 dead CDN 對 first-paint 有實際影響，不是省大但乾淨
- **共用 ui 元件先做、頁面重寫晚做**：Phase B（element library）做完後，Phase D 5 頁重寫變得單純。若反過來頁面先做、會在每頁複製貼上樣式 → 後續調 palette 痛
- **Lint / type 錯誤盯緊 unknown narrowing**：`Object.entries(Record<string, string>)` 在嚴格 narrowing 下會回 `[string, unknown]`；要顯式 `String(v)` 或拆 type

---

## 7. Open questions（park）

- `WMOM 介面改版交接書.md` 與 `app/VA.jsx` 在主 repo 根目錄，不在 git 追蹤內。是否要把這份交接書搬進 worktree `docs/product/ux/` 作為設計 source of truth？目前無 worklog 連結，未來改版會找不到。— **不在本 issue 範圍，留作 follow-up 觀察**
- 故障注入頁 / Settings 頁未在 VA.jsx 中重畫，本次只套新元件樣式。若劉老師對外 demo 會帶到這兩頁，可能要再做一輪 layout 級重設計。— **目前的 panel-based 結構功能完整，等真有 demo 場景再評估**
