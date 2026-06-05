# 2026-06-05 — WorkOrderListPanel component render 測試（EPIC-M5 測試覆蓋擴大）

> autonomous worker session（每 3 小時 cron）。接續 2026-06-05 HistoryPage handoff 建議：
> 「同範式續推 TurbineDetail（1056）/ workflow 子面板（WorkOrderListPanel / PendingApprovalPanel 等 panel 級互動）」。
> 挑 **WorkOrderListPanel**（核心「派工」模組工單清單，`/admin/workflow` 工單 tab 主畫面）為本次目標。
> issue：**WMOM-20260605-02**（WorkOrderListPanel component render 測試）

---

## 1. 為什麼做這個

開工 preflight（決策樹）：

- 優先級 #1 known blocker / #2 baseline regression / #3 飛輪壞掉 → **皆無**。
  - backend `pytest` → **638 passed / 1 xfailed**（綠）
  - frontend `vitest` → **200 passed**（綠；上個 session HistoryPage 21 tests 已 auto-merge 進 main，PR #80）
  - 飛輪健康：…→SettingsPage(#79)→HistoryPage(#80) 連續 render 測試 PR 皆 auto-merge 進 main。
- stack-aware：`list_pull_requests` open=22+，全為飛輪上線前的 stale PR（無 `[WIP]`、非本 session 系列）。
  本次工作（net-new 測試檔）與它們**零 collision**。

→ 落到優先級 #4「乾淨 autonomous 工作」。HistoryPage handoff **背書**「同範式續推 workflow 子面板」。
選 **WorkOrderListPanel**（`components/workflow/WorkOrderListPanel.tsx`，221 行）：

- **零設計歧義、單 session 可完工**：純 props 元件（`items`/`total`/`loading`/`error`/`status`/`search`
  + 4 個 callback + `lang`），**無 hook / 無 fetch / 無 internal state**，比 HistoryPage 更單純。
  ui primitive（Btn/Card/Field/Input/Select/StatusPill）真渲染；`statusUtils` helper（已有單元測試）真調用。
- **覆蓋價值**：`/admin/workflow` 工單 tab 是核心「派工」demo 主操作清單。先前 `WorkflowPage.test.tsx`
  把本面板 mock 成 marker，其**真實渲染**（status filter / search / counter / error / empty /
  每筆 row 的 business_key·turbine·type·title·更新時間·預估工時·優先級+狀態 pill / 點擊接線）零覆蓋。

## 2. 認領

**WMOM-20260605-02** — WorkOrderListPanel component render 測試（EPIC-M5 測試覆蓋擴大）。

## 3. 本次完成（Implement）

以測試為主，外加 review 抓出的 **1 行 production UX bug 修正**（Refresh 按鈕載入中未 disabled）：

| 檔案 | 內容 |
|---|---|
| `frontend/components/workflow/__tests__/WorkOrderListPanel.test.tsx`（新，**20 tests**） | WorkOrderListPanel render 測試。`makeWO()` 工廠結構式滿足 `WorkOrderResponse`（所有欄位齊備，不用 `as` 強轉）；`renderPanel()` helper 注入 props + 回傳 callback spy。無 fetch / 無 hook → 不需 stub global.fetch、不需 async act。 |
| `frontend/components/workflow/WorkOrderListPanel.tsx`（改，**1 行**） | 補傳 `loading={loading}` 給 Refresh 的 `Btn`（review must-fix #1）。修正載入中按鈕未 disabled 的 UX bug（避免使用者在 fetch 進行中重複點擊 Refresh 重複觸發查詢）。Btn 既有 `isDisabled = disabled \|\| loading` 邏輯，僅需把 prop 接上。 |

### 覆蓋的 UX 契約
- **基本渲染 + 語系**：zh「狀態」/「搜尋（編號 / 標題 / 風機）」/「重新整理」+ counter「顯示 1 / 3 筆工單」；
  en「Status」/「Search (key / title / turbine)」/「Refresh」/「Showing 1 of 5 work orders」（含 negative 守 zh 不外洩）。
- **status filter**：Select 選項涵蓋「全部狀態」+ 7 個工單 status label（順序鎖定 WorkOrderStatusValues）；
  value 反映 `status` prop；onChange → `onStatusChange` 帶選取值。
- **search**：Input value 反映 `search` prop；onChange → `onSearchChange` 帶輸入值。
- **refresh**：onClick → `onRefresh`；`loading=true` → 按鈕文案「載入中…」/「Loading…」**且 disabled**（防重複點擊）。
- **error 態**：warn card 顯示 ⚠ + 錯誤訊息。
- **empty 態**：`items=[] && !loading && !error` → 「目前沒有符合條件的工單。」；
  loading 中**不**顯示空狀態（避免閃爍）；error 時**不**顯示空狀態（讓位給錯誤卡）。
- **列表 row**：business_key / `turbine_id · typeLabel` / title / 優先級 + 狀態 label；
  `estimated_hours` 有值 → 「預估 6h」，為 `null` → **不**顯示「預估」；aria-label 帶 business_key；多筆各自渲染。
- **點擊接線**：點 row → `onSelect` 帶**該筆** work order（多筆中精準命中）。

### 技術要點
- **純 props → 測試最單純**：WorkOrderListPanel 無 fetch / 無 effect，故不需 `global.fetch` stub 或
  `await act(async)` flush；直接 render + fireEvent + 斷言。
- **status 選項順序鎖定**：以 `toEqual([...])` 斷言完整選項陣列，守住 `WorkOrderStatusValues` 順序契約
  （新增/重排 status 會讓測試失敗而非靜默漂移）。
- **row 以 aria-label 鎖定**：每筆 row 是帶 `aria-label="開啟工單 {business_key}"` 的 button，
  以 `getByRole('button', { name: ... })` 精準定位，避免 `getByText` 命中多元素。
- **`makeWO` 結構式滿足型別**：所有 `WorkOrderResponse` 欄位齊備（不用 `as` 強轉），
  真實 Props/型別 signature 漂移時 tsc 編譯失敗而非假綠。

## 4. Verify（本機跑綠才開 PR）

- `npx tsc --noEmit` → **0 error**
- `npx vitest run`（全量）→ **220 passed**（200 baseline + 20 新，**零 regression**）
- `npx vite build` → ✓ built（既有 chunk-size warning 與本次無關）
- backend 未動 → **638 passed / 1 xfailed** 不受影響

## 5. Review

跑 `code-reviewer` subagent 對 staged diff 找 must-fix / should-fix（結果：must-fix 3、should-fix 4、nice 2）。採納結果：

- **採納（must-fix #1）**：reviewer 指出 production code `WorkOrderListPanel.tsx:105` 的 Refresh `Btn`
  漏傳 `loading` prop → 載入中按鈕不會 disabled（可重複點擊重複觸發查詢）。**修 production（補 1 行 `loading={loading}`）**
  + 兩個 loading 測試補 `expect(btn).toBeDisabled()`。是測試抓出的真實 UX bug。
- **採納（must-fix #2）**：error 態斷言不再繞 ⚠ icon。改 `getByText(/載入工單失敗（500）/).toBeInTheDocument()`
  直接比對訊息文字節點 + 另獨立 `getByText(/⚠/).toBeInTheDocument()` 守視覺提示，避免 icon 被抽成獨立元素時的結構耦合。
- **採納（should-fix #4）**：en negative leak 補強。除 `重新整理` 外，再加 `狀態` / `全部狀態` / `/顯示.*筆工單/`
  三個 zh 專屬字串的 `queryByText().not.toBeInTheDocument()`，守住 `ui()` zh/en 沒倒置。
- **採納（should-fix #5）**：row 渲染補 `更新於` + 時區斷言（`updated_at '2026-06-02T08:30:00Z'`
  → `fmtDateTime(Asia/Taipei)` = `2026-06-02 16:30`），同時覆蓋 `fmtDateTime` 時區正確性。
- **採納（should-fix #6 onSelect identity）**：`toHaveBeenCalledWith(target)` 改
  `expect.objectContaining({ id, business_key })`，守語意契約而非物件 identity，避免日後面板淺複製 items 時假紅。
- **採納（should-fix #7 counter）**：多筆 row 測試補 `顯示 3 / 3 筆工單`；新增「items.length < total（2 / 50）」
  counter 測試守住 filter 截斷語意。測試數 19→**20**。
- **不採納（must-fix #3 status 選項 toEqual 順序）**：reviewer 建議改 `toHaveLength + toContain` 降順序耦合。
  **保留 `toEqual([...])`**：此處 option label 皆為 string（由 `statusLabel()` 生成，非 ReactNode → 無空字串假綠風險），
  且鎖定順序是**刻意契約**——`WorkOrderStatusValues` 順序若異動，測試 fail 讓人確認 UI 順序變更為刻意，屬良好設計而非 flaky。
  `toEqual` 嚴格度（長度+順序+內容）強於 `toHaveLength+toContain`，loosen 非改善。
- **不採納（nice #8/#9 風格）**：`within` / `RenderOpts` 屬可讀性偏好，與 codebase 既有測試一致，保留。

## 6. 下次怎麼接手

同範式仍有候選（workflow 子面板）：
- **PendingApprovalPanel**（270 行）— 簽核 panel，核心業務流程。
- **MaterialRequestListPanel**（203 行）— 領料單清單（與本面板高度同構，可快速複用範式）。
- **InventoryListPanel**（286 行）— 庫存清單。
- 較大的 modal：**WorkOrderDetailModal**（933）/ **MaterialRequestDetailModal**（902）— 互動多、需 mock dialog。
- **TurbineDetail**（1056 行）— 單機詳情，最大、demo 重要；recharts 多（jsdom 不渲染內部不影響斷言）。

非 render 測試方向（需劉老師 / 素材）：
- M5-2 ChromaDB 整合 🔵（需評估 chromadb 依賴 + 向量檔來源）。
- M5-5 Part B-2 `/field/` my work orders（🟡 需釐清 persona/auth）。
- stale PR triage（飛輪上線前留下，多數可能已過時 → 建議劉老師確認關閉或重開）。

## 7. 卡點 / 給劉老師

- 無技術卡點。
- **建議**：pre-flywheel stale open PR 累積中（20+ 筆），建議找時間 triage，
  避免 stack-aware 檢查每次都要略過一大票雜訊。
