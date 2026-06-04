# 2026-06-04 — CostPage component render 測試（EPIC-M5 測試覆蓋擴大）

> autonomous worker session（每 3 小時 cron）。接續 reportspage-render-tests handoff #1：
> 「同範式續推 component render 測試：CostPage（784 行）/ FarmOverview / workflow」。
> issue：**WMOM-20260604-03**（CostPage component render 測試）

---

## 1. 為什麼做這個

開工 preflight（決策樹）：

- 優先級 #1 known blocker / #2 baseline regression / #3 飛輪壞掉 → **皆無**。
  - backend `pytest` → **638 passed / 1 xfailed**（綠）
  - frontend `vitest` → **108 passed**（綠；上個 session ReportsPage 11 tests 已 auto-merge 進 main）
  - 飛輪健康：PR #75（ReportsPage render 測試）已 auto-merge 進 main。
- stack-aware：`list_pull_requests` open=22，全為飛輪上線前的 stale PR（無 `[WIP]`、非本 session 系列）。本次工作（net-new 測試檔）與它們**零 collision**。

→ 落到優先級 #4「乾淨 autonomous 工作」。前兩個同日 session（FieldPage / ReportsPage）連續 handoff 背書「同範式續推 CostPage」。CostPage（`components/CostPage.tsx`，784 行）是 admin 成本模型主入口，串 `useCostData` 4 endpoints（forecast / lcoe / monteCarlo / varFluct），分支邏輯豐富（dataset 自動 run + reset / 4 panel run 接線 / loading·error 態 / KPI strip 格式化 / DatasetMetaBadge / 語系），依賴可乾淨 mock，**零設計歧義、單 session 可完工** → 選定。

## 2. 認領

**WMOM-20260604-03** — CostPage component render 測試（EPIC-M5 測試覆蓋擴大）。

## 3. 本次完成（Implement）

純測試，**不動任何 production 程式**：

| 檔案 | 內容 |
|---|---|
| `frontend/components/__tests__/CostPage.test.tsx`（新） | CostPage render 測試。mock `useCostData` hook（控 4 個 AsyncState：data/loading/error/run/reset spy）+ mock `recharts`（輕量 stub div，避免 jsdom 0-width 圖表噪音 + 讓 data-present 渲染穩定）+ stub `global.fetch`（路由 `/api/farms` farms list + `/api/i18n/tags/all`）。元件用 `ThemeProvider` 包裹。localStorage `windFarmLang` 控語系（CostPage 經 `useI18n` 讀 localStorage，非吃 prop）。 |

### 覆蓋的 UX 契約
- **mount 自動接線**：dataset effect 觸發 `forecast.run({dataset:'k13'})` + `lcoe/monteCarlo/varFluct.reset()`（守「切 dataset 自動跑預測、清其他 panel stale 數字」契約）
- **dataset 切換**：選 farm dataset → `forecast.run` 帶新 dataset + 其他三個 reset
- **farms 載入接線**：`/api/farms` resolve → dataset selector 出現 farm 選項
- **Run scenario 全跑**：header 按鈕 → 4 個 run 帶正確 params（capex 1250 / discount 0.08 / nSim 1000 / seed 42）
- **各 panel run 按鈕**：Forecast / LCOE（帶 capex·discount 預設）/ MonteCarlo（帶 nSim·seed 預設）/ VarFluct
- **loading / error 態**：forecast.loading → 按鈕 disabled + 「計算中…」；forecast.error → ErrorBox 顯示訊息
- **KPI strip 格式化**：forecast/lcoe/monteCarlo/varFluct data present → Total Cost / LCOE / NPV / MC P50 / CapEx / Avg-yr 正確格式（fmtMoney €M、LCOE 兩位小數）；無資料顯示「—」
- **DatasetMetaBadge**：meta source → 對應繁中標籤（farm_overlay → 風場覆寫）
- **語系**：localStorage en → 標題 'Cost Model' 英文

### 技術要點
- **recharts mock**：圖表元件全 stub 成 marker div，測試聚焦 CostPage 路由 / 接線 / KPI 文字，不被 ResponsiveContainer 在 jsdom 下 0 寬度的渲染細節干擾。
- **fetch 路由**：單一 `fetchMock` 依 URL 分流 farms / i18n，零真連線。
- **fixtures 型別嚴格**：`CostForecastResponse` / `LCOEResponse` / `MonteCarloResponse` / `VarFluctResponse` 用工廠建構、不用 `as` 強轉，讓 tsc 守住與 service 真實 signature 對齊（漏欄位編譯失敗而非靜默假綠）。

## 4. Verify（本機全綠才開 PR）

- `npx tsc --noEmit` → **0 error**
- `npx vitest run` → **123 passed**（108 baseline + 15 新，零 regression、零 act() 警告）
- `npx vite build` → ✓
- backend 未動 → **638 passed / 1 xfailed** 不受影響（開工已驗）

## 5. Code review

用 `code-reviewer` subagent 對 staged diff 跑審查（聚焦測試正確性 / 假綠 / mock 漂移 / flake / cleanup）：
**0 must-fix / 3 should-fix / 5 nice-to-have，verdict Approve**。

**已採納（全部 3 should-fix + 3 cheap nice-to-have）**：
1. **[should]** `Slice<T>.run` 型別 `() => Promise<void>` 比真實 `(req?: TReq) => Promise<void>` 窄 → 結構式可賦值但「TReq 內新增必填欄位」不會被 tsc 抓到（半邊保護）。改 `Slice<TData, TReq>` 帶 run 參數型別，並把 4 個 endpoint 的 request 型別（`CostForecastRequest`…）引入；makeCost 回傳結構式滿足 `CostReturn`，run 簽章漂移即編譯失敗。
2. **[should]** KPI money 斷言 `getAllByText('€14.0M').length >= 1` 過弱（formatter 沒壞就不會 false-pass，但 KPI strip 被移除也不報錯）→ 把 fixture 調成每個 money 字串「恰好出現 2 次」（KPI + 對應且唯一的 panel SmallStat；MonteCarlo deterministic 改用不同 total_effort 13M 避免第三處撞、varFluct avg 改 14.3M），斷言改 `toHaveLength(2)`：KPI strip regress → 計數降 1 即失敗。
3. **[should]** 同步測試未 flush farms / useI18n 兩條 async fetch effect → 潛在 act() 警告。把 `renderCost` 改 `async` + `act(async)` 包 render flush microtask；全部測試改 `await renderCost(...)`。實測輸出**零 act() 警告**。
4. **[nice]** `routeFetch` fallback 靜默回 `{}` → 改未知 URL `reject(Error('Unexpected fetch'))`，新增 fetch 呼叫不會被靜默吞掉。
5. **[nice]** 無資料 dash 斷言 `>= 6` → `toHaveLength(6)`（KpiStrip 固定 6 卡，精確）。
6. **[nice]** DatasetMetaBadge 測試補 `farm_id` 後綴（`風場覆寫 · farm-001`），守住 `meta.farm_id ? ' · …' : ''` 分支；語系 en 測試補 MonteCarlo `Run` / VarFluct `Run lifetime sim` 英文按鈕名。

**未採納（記錄理由）**：
- nice #8（`dataset_meta: undefined` 不渲染 Badge 的 absent-path test）：`DatasetMetaBadge` 的 `if (!meta) return null` 在「無 forecast.data」測試已間接覆蓋（無 data → 無 badge），不另開 case 避免重複。

**Verify（採納後）**：`tsc` 0 error + `vitest` **123 passed**（108 baseline + 15 新，零 regression、零 act 警告）+ `vite build` ✓。

## 6. 下次 session 接手建議

- **同範式續推 component render 測試**：FarmOverview（730 行）/ SettingsPage（781）/ HistoryPage（809）/ workflow 各 panel。基礎設施 + 三個範例（FieldPage / ReportsPage / CostPage）已就位。
- **M5-5 Part B-2**（my work orders + completion）—— 仍需劉老師釐清 persona/auth「who is me」（🟡）。
- **M5-2 ChromaDB**（🔵；需評估 CI 加 `chromadb` 重依賴的安裝時間 / Linux runner 相容）。
- **22 個 stale PR triage**（待劉老師 / 後續 session）。

## 7. 給劉老師

- 純測試擴充，**零 production 程式改動**，無 schema / DB / 部署影響，CI 綠即 auto-merge。
- CostPage 是 admin 成本模型主入口（LCOE / NPV / 蒙地卡羅 / 20 年預測），現有 render 測試守住「dataset 自動接線 + 4 panel run + KPI 格式化 + 語系」核心契約，日後改動有 regression 防護網。
