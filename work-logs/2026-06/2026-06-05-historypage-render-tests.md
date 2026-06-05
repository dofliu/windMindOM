# 2026-06-05 — HistoryPage component render 測試（EPIC-M5 測試覆蓋擴大）

> autonomous worker session（每 3 小時 cron）。接續 2026-06-04 SettingsPage handoff 建議：
> 「同範式續推 HistoryPage（809）/ TurbineDetail（1056）/ workflow 子面板測試」。
> 挑 **HistoryPage**（候選中次小、`/admin/history` demo 主畫面、SCADA 歷史查詢 + 事件標記 + CSV 匯出）為本次目標。
> issue：**WMOM-20260605-01**（HistoryPage component render 測試）

---

## 1. 為什麼做這個

開工 preflight（決策樹）：

- 優先級 #1 known blocker / #2 baseline regression / #3 飛輪壞掉 → **皆無**。
  - backend `pytest` → **638 passed / 1 xfailed**（綠）
  - frontend `vitest` → **179 passed**（綠；上個 session SettingsPage 17 tests 已 auto-merge 進 main，PR #79）
  - 飛輪健康：FieldPage→ReportsPage→CostPage→FarmOverview→WorkflowPage→SettingsPage 連續六個 render 測試 PR（#74~#79）皆 auto-merge 進 main。
- stack-aware：`list_pull_requests` open=22，全為飛輪上線前的 stale PR（無 `[WIP]`、非本 session 系列）。本次工作（net-new 測試檔）與它們**零 collision**。

→ 落到優先級 #4「乾淨 autonomous 工作」。SettingsPage handoff **背書**「同範式續推 HistoryPage」。
選 **HistoryPage**（`components/HistoryPage.tsx`，809 行）：

- **零設計歧義、單 session 可完工**：純 props（`turbines` / `lang`）+ 兩條 fetch（`/api/i18n/tags`、
  `/api/turbines/:id/history`）驅動，唯一重子元件 `EventComparisonView`（compare tab）可 mock 成 sentinel。
  ui primitive（Btn/Card/Field/Input/Select/PageHeader/StatusPill）真渲染；recharts 圖表在 jsdom
  width=0 不渲染內部、但不 crash → 斷言聚焦非圖表 UI。範式（CostPage/FarmOverview/SettingsPage）已成熟。
- **覆蓋價值**：`/admin/history` 是 demo「查 SCADA 標籤 + 看事件標記 + CSV 匯出」的主操作畫面，
  先前頁面層零覆蓋。守住「單機/比較 tab」「查詢卡風機/筆數 Select 接線」「歷史 fetch → 圖表+事件填充」
  「事件清單→詳情」「事件類型/搜尋過濾」「標籤預設/自訂切換」「CSV 匯出 window.open」核心契約。

## 2. 認領

**WMOM-20260605-01** — HistoryPage component render 測試（EPIC-M5 測試覆蓋擴大）。

## 3. 本次完成（Implement）

純測試，**不動任何 production 程式**：

| 檔案 | 內容 |
|---|---|
| `frontend/components/__tests__/HistoryPage.test.tsx`（新，**21 tests**） | HistoryPage render 測試。mock `EventComparisonView` 成 sentinel；stub `global.fetch` 路由 `/api/i18n/tags` + `/history`；stub `window.open`（jsdom 未實作）；`makeTurbine`/`makeHistoryPayload` 工廠結構式滿足型別（不用 `as` 強轉）。所有 mount / 互動以 `await act(async)` + `setTimeout(0)` flush fetch chain（fetch→json→setState→finally）。 |

### 覆蓋的 UX 契約
- **基本渲染 + 語系**：zh「歷史資料」+ CSV 匯出按鈕「匯出區間」「匯出聚焦」+ tab「單機歷史」「多機比較」；
  en「History」/「Single turbine」/「Multi compare」/「CSV (range)」/「Latest 20 rows」（含 negative 守 zh 不外洩）；
  en → i18n GET 帶 `lang=en`。
- **tab 切換**：預設 single aria-pressed=true、compare=false；點「多機比較」→ 掛 EventComparisonView sentinel +
  single 查詢卡（風機 Select）消失 + compare aria-pressed 翻 true。
- **查詢條件卡**：風機 Select options 由 turbines props 生成（`WT001 · WTG-01`）；mount 即 fetch `/api/turbines/WT001/history`；
  切換風機 Select → 重新 fetch 新風機；切換筆數 Select（600）→ 重新 fetch 帶 `limit=600`。
- **歷史資料表**：數值 `toFixed(2)`（12.34）+ 缺值「—」（第二筆缺 WCNV_CnvGnFrq）；表頭預設 startup 標籤。
- **事件紀錄與詳情**：清單渲染各事件 title（以 button role 鎖定清單，避開詳情 div 同名）；點故障事件 →
  詳情顯示 detail +「temp": 92」payload；空事件 →「目前區間沒有事件。」+「請從左側選擇事件。」。
- **事件篩選**：關「故障」toggle（aria-pressed）→ 故障事件從清單消失、grid 仍在；事件搜尋「電網」→ 只留命中。
- **標籤切換**：點預設「thermal」→ 重新 fetch + 表頭換 thermal 標籤（WGEN_GnStaTmp1）+ startup 標籤消失；
  自訂標籤輸入 + 套用 → activeTags 換成自訂值（WTUR_TotWh 出現、舊 startup 標籤離場）。
- **error path**：history fetch reject → `.catch` 靜默吞 → UI 不崩潰、事件清單落空狀態。
- **CSV 匯出**：點「匯出區間」→ `window.open` 帶 `/api/export/history?...format=csv&turbine_id=WT001`。
- **i18n 標籤對映**：i18n 回 `{WTUR_TurSt:'渦輪狀態'}` → 表頭顯示中文標籤而非原始 tag。

### 技術要點
- **fetch stub 不靜默**：未預期 URL `reject(Error('Unexpected fetch'))`，新增 API 呼叫不會被靜默吞掉。
- **事件 title 雙處出現**：grid 事件預設被選中 → title 同時在「事件紀錄」button 與「事件詳情」div。
  斷言以 `getByRole('button', { name: /title/ })` 鎖定清單項，避免 `getByText` 命中多元素。
- **window.open 用 spy**：jsdom 未實作 `window.open`（會印 Not implemented），CSV 契約只需驗「以正確 URL 被呼叫」。
- **tagLabels per-test 覆寫**：`beforeEach` reset `tagLabels = {}`（i18n stub 從此變數讀），i18n-mapping 測試在
  render 前覆寫 → 無跨測試殘留。fetchMock 每個 beforeEach 重建、`afterEach` `unstubAllGlobals + clearAllMocks`。
- **無 module-level 可變快取依賴**：HistoryPage 不像 FarmOverview 有 `_trendCache`，故測試彼此獨立、`--randomize` 安全。

## 4. Verify（本機跑綠才開 PR）

- `npx tsc --noEmit` → **0 error**
- `npx vitest run`（全量）→ **200 passed**（179 baseline + 21 新，**零 regression**）
- `npx vite build` → ✓ built（既有 chunk-size warning 與本次無關）
- backend 未動 → **638 passed / 1 xfailed** 不受影響

## 5. Review

跑 `code-reviewer` subagent 對 staged diff（純測試新增）找 must-fix / should-fix。採納結果：

- **採納（must-fix #2）**：加 `vi.mock('recharts', ...)` stub（對齊 CostPage 既有範式）。HistoryPage 折線圖
  在 jsdom 0 寬度本就不渲染內部，但顯式 stub 確保資料表 / 事件清單文字斷言不被未來 recharts tick/tooltip
  渲染細節干擾而 flaky。
- **採納（must-fix #3）**：「點故障事件」改用 `getByRole('button', { name: /齒輪箱高溫/ })` 點擊（非 `getByText`
  可能命中 span），確保點到帶 onClick 的 button。
- **採納（should-fix #7）**：自訂標籤測試改用較真實的 tag 名（`WTUR_TotWh`）+ 補負面斷言（startup 標籤
  `WTUR_TurSt` 套用後離場），守住 setActiveTags 整批取代而非疊加。
- **採納（nice #9）**：新增「history fetch 失敗 → UI 不崩潰、事件清單空狀態」error path 測試（涵蓋
  production `.catch(() => {})` 靜默吞錯分支）→ 測試數 20→**21**。
- **採納（should-fix #6）**：空事件測試補註解，說明「沒有事件」warn 與「請從左側選擇事件」提示並存屬預期非矛盾。
- **不採納（must-fix #4 事件 toggle 取法）**：本機跑綠確認 `getAllByText('故障').find(aria-pressed==='true')`
  穩定命中 toggle（StatusPill 無 aria-pressed 被濾除；toggle button 文字為直接子節點），reviewer 顧慮屬
  推測；改寫 `within(filterSection)` 反引入 DOM 結構耦合風險，故保留現法。
- **不採納（should-fix #5 flushAsync）**：`act(async)` 包 render + `setTimeout(0)` 與 FarmOverview 既有範式
  一致，本機零 act 警告，維持 codebase 一致性。
- **撤回（reviewer 自撤）**：#1 tagLabels closure 一說 reviewer 已自行撤回（closure 抓變數綁定非值，per-test
  覆寫正確）。

## 6. 下次怎麼接手

同範式仍有候選：
- **TurbineDetail**（1056 行）— 單機詳情，最大、demo 重要；recharts 多、但範式可複用（圖表 jsdom 不渲染內部不影響）。
- **workflow 子面板**（WorkOrderListPanel / PendingApprovalPanel 等 panel 級互動）。
- **HistoryPage 補充**：focus window 聚焦（focusWindowSec 30/120）對 chartData / event 過濾的更深斷言、
  EventComparisonView 自身（目前 mock）的獨立測試。

非 render 測試方向（需劉老師 / 素材）：
- M5-2 ChromaDB 整合 🔵（需評估 chromadb 依賴 + 向量檔來源）。
- M5-5 Part B-2 `/field/` my work orders（🟡 需釐清 persona/auth）。
- 22 個 stale PR triage（飛輪上線前留下，多數可能已過時 → 建議劉老師確認關閉或重開）。

## 7. 卡點 / 給劉老師

- 無技術卡點。
- **建議**：22 個 pre-flywheel stale open PR 累積中，建議找時間 triage（關閉已被後續 main 覆蓋的、或重 rebase 仍有價值的），
  避免 stack-aware 檢查每次都要略過一大票雜訊。
