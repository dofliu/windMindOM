# 2026-05-04 — Cost dashboard frontend（WMOM-20260504-08）

> Session 類型：實作（前端 / UI）
> Session 長度：中（~30 分鐘）
> 主導：Claude（劉老師指示「一次把 m2 完成」）
> 結果：CostPage 4 panel 上線，nav 加按鈕，vite build pass，**M2 100% 完成**

---

## 1. Session 目標

WMOM-20260504-08 — M2 最後一個 issue。把 -07 的 4 個 cost endpoints
包成 React dashboard，使用者點 nav「Cost」就能看到完整成本分析。

設計目標：
- 4 個 panel（forecast / LCOE / Monte Carlo / VarFluct）對應 4 endpoints
- 沿用既有 cyan/gray 暗色 Tailwind 主題
- Recharts 做視覺化
- 一進來自動跑 forecast 給使用者看到結果（沒空白頁）

## 2. 實際完成

### 2.1 主要工作

- ✅ 寫 `frontend/services/costService.ts`（160 行）：
  - 完整 TypeScript types 對齊 backend pydantic schemas
  - 4 個 client function：`forecast` / `lcoe` / `monteCarlo` / `varFluct`
  - 統一 `postJSON()` helper 處理 fetch + error
  - API base 從 `import.meta.env.VITE_API_BASE` 拿（預設 `http://localhost:8100`）
- ✅ 寫 `frontend/hooks/useCostData.ts`（70 行）：
  - 通用 `useAsync<TReq, TData>` hook 模板
  - 4 個 endpoint state：`{ data, loading, error, run }`
  - `run(req?)` 觸發 fetch，自動更新 state
- ✅ 寫 `frontend/components/CostPage.tsx`（440 行）：
  - 4 個 sub-component panel：`ForecastPanel` / `LCOEPanel` / `MonteCarloPanel` / `VarFluctPanel`
  - 共用 UI bits：`MetricCard` / `Panel` / `Btn` / `ErrorBox`
  - **Forecast panel**：6 metric cards + 4 季 stacked bar chart
  - **LCOE panel**：capex/discount input → metric cards
  - **Monte Carlo panel**：n_sim/seed input → P10/P50/Mean/P90 bar chart
  - **VarFluct panel**：summary + 20 年 line chart（Total Effort + Multiplier + Availability 三線疊加）
  - Money formatter（自動切 EUR / k EUR / M EUR / B EUR）+ percentage formatter
  - 一進入頁面 auto-run forecast（useEffect）
- ✅ 改 `frontend/App.tsx`：
  - import `CostPage`
  - view union type 加 `'cost'`
  - renderContent switch 加 `case 'cost'`
  - Header nav 加 Cost 按鈕（金幣圖示 SVG inline）
- ✅ Vite build 通過：710 modules，1020 KB（含 recharts），0 TS error
- ✅ 整個 backend test suite 不受影響（前端改動不動 backend）

### 2.2 卡住或延後的事

無。Adapter（-06）+ schemas（-06）+ API（-07）已完整定義 contract，
前端跟著 contract 寫一次過。

### 2.3 重大決策

- **使用 useAsync 通用 hook** 而非寫 4 個獨立 hook — DRY，error handling 統一
- **4 個 panel 用 grid-cols-1 lg:grid-cols-2 layout** — desktop 2x2，手機自動疊
- **Forecast 設 useEffect auto-run** — 進頁就有東西看，不用等使用者點「Run Forecast」
- **LCOE / MC / VarFluct 不 auto-run** — 需要使用者選參數（capex / n_sim），等點按鈕
- **錯誤訊息是 panel-level 不是 page-level** — 一個 panel 失敗不影響其它

## 3. 產出清單

### 新增檔案

- `frontend/services/costService.ts`（160 行）— TypeScript API client
- `frontend/hooks/useCostData.ts`（70 行）— React hook
- `frontend/components/CostPage.tsx`（440 行）— 4 panel dashboard
- `work-logs/2026-05/2026-05-04-cost-frontend.md`（本檔）

### 修改檔案

- `frontend/App.tsx` — import CostPage、加 'cost' view、加 nav button
- `ISSUES.md`（WMOM-08 done；統計 +1 done = 13）
- `STATUS.yaml`（M2 progress 95→100、status in_progress→completed；overall 45→50）

### Build metrics

- Vite production build：710 modules, 1020 KB（含 recharts），0 errors
- Bundle size +~50 KB vs 沒 cost page（recharts 大）

### 動了狀態的 issue

- WMOM-20260504-08: 新建 + done

## 4. 下次怎麼接手

**M2 完成 — windMindOM v0.8.1 第一階段（M1 + M2）100% done**：

- M1 5/5 issue done
- M2 8/8 issue done（含 -09 hotfix）
- 整 modules/ pytest：43 PASS + 1 XFAIL
- Cost backend 4 endpoints 上線 + frontend dashboard 完整

下個月（M3）開工：**Workflow Part 1（Work Order + Approval）**

ROADMAP M3：
1. 從 z72_etech 取設計（5-7 天讀程式）
2. 30 分鐘 user walkthrough（跟劉老師確認 design notes 沒誤解）
3. Work Order CRUD + 狀態機
4. Approval 多階簽核
5. /admin/workflow/orders frontend
6. /admin/workflow/approval frontend

預期 M3 第一個 issue：**WMOM-20260601-01 — z72_etech 取設計 + 30 分鐘 walkthrough**

阻擋項：無。

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 跡 frontend 結構 + UI 風格 | 10% |
| 寫 costService.ts + types | 25% |
| 寫 useCostData.ts | 5% |
| 寫 CostPage.tsx（4 panel + 共用 UI bits + chart） | 50% |
| App.tsx 整合（nav button + view router） | 5% |
| Vite build 跑通 + cleanup | 5% |

## 6. 學到的事

- **Backend → Frontend 完整 type chain** — pydantic schema → TypeScript interface
  幾乎一對一對應；改一邊另一邊也得改，但 contract 清楚
- **Recharts 預設配色不亮** — 暗色主題下要主動指定 stroke="#06b6d4" 等顏色，
  否則看不見
- **`useEffect(() => { ... }, [])` auto-run 模式** vs 全手動觸發 — 對 dashboard，
  進來自動 run 至少一個 endpoint 體驗好太多
- **Vite hot rebuild 0 TS error** = type chain 對齊得很乾淨；如果 backend 變
  schema field name，TS 會立刻爆
- **M2 cost 線總計**：8 issue / 6 工作天估 → **實際 1 天完成**（從早 morning 8 個 issue 一路衝完）
  原因：SOP 一次寫好（pinned equivalence + adapter pattern + auto-build），第 2 個 issue 開始就快了

## 7. Open questions（park）

- Cost page 是否需要中文 i18n？目前 lang prop 接收但內部都英文（`useI18n` hook
  沒整合）。M2 PoC 階段先英文，client demo 時若需求高再補
- 是否要加 export CSV / 下載 PDF 報表功能？M4 reporting module 會做，現在不重複
- VarFluct panel 的 bathtub config UI（讓使用者調 early_peak / late_peak）—
  目前用 default，等 client 真的要 tweak 時再加 advanced settings panel
- Mobile responsiveness：grid 是 lg:grid-cols-2，<lg 時自動單欄，但 chart 寬度
  可能太窄；M5 mobile /field/ UI 時統一處理
