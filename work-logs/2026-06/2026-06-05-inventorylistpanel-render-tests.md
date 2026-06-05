# 2026-06-05 — InventoryListPanel component render 測試（EPIC-M5 測試覆蓋擴大）

> autonomous worker session（每 3 小時 cron）。接續 2026-06-05 MaterialRequestListPanel handoff 建議：
> 「同範式續推 workflow 子面板（PendingApprovalPanel / InventoryListPanel / …）」。
> 挑 **InventoryListPanel**（核心「庫存」模組料件清單，`/admin/workflow` 庫存 tab 主畫面）。
> 它與 WorkOrderListPanel / MaterialRequestListPanel **高度同構**，可最快複用既有範式 → 單 session 穩定完工。
> issue：**WMOM-20260605-04**（InventoryListPanel component render 測試）

---

## 1. 為什麼做這個

開工 preflight（決策樹）：

- 優先級 #1 known blocker / #2 baseline regression / #3 飛輪壞掉 → **皆無**。
  - backend `pytest` → **638 passed / 1 xfailed**（綠）
  - frontend `vitest` → **242 passed**（綠；上個 session MaterialRequestListPanel 22 tests 已 auto-merge 進 main，PR #82）
  - 飛輪健康：…→WorkOrderListPanel(#81)→MaterialRequestListPanel(#82) 連續 render 測試 PR 皆 auto-merge 進 main。
- stack-aware：`list_pull_requests` open=22，全為飛輪上線前的 stale PR（無 `[WIP]`、非本 session 系列）。
  本次工作（net-new 測試檔）與它們**零 collision**。

→ 落到優先級 #4「乾淨 autonomous 工作」。MaterialRequestListPanel handoff **背書**「同範式續推 workflow 子面板」。
選 **InventoryListPanel**（`components/workflow/InventoryListPanel.tsx`，286 行）：

- **零設計歧義、單 session 可完工**：純 props 元件（`items`/`total`/`loading`/`error`/`warehouses`/
  `warehouseId`/`belowSafetyOnly`/`search` + 5 callback + `lang`），**無 hook / 無 fetch / 無 internal state**，
  與 WorkOrderListPanel / MaterialRequestListPanel 同構。ui primitive（Btn/Card/Field/Input/Select/StatusPill）
  真渲染；`fmtDateTime`（已有單元測試）真調用。
- **覆蓋價值**：`/admin/workflow` 庫存 tab 是核心「庫存」模組的主操作清單。先前無任何測試覆蓋本面板
  其**真實渲染**（warehouse selector / below-safety toggle / search / counter / error / empty /
  每筆 row 的 SKU·name·unit·三欄 stock·安全·可用·LOW pill·最後出庫時間 / 點擊接線）。
  比前兩個面板**多了 warehouse Select（★ default 倉前綴）+ below-safety toggle（aria-pressed）** 兩個過濾控件。

## 2. 認領

**WMOM-20260605-04** — InventoryListPanel component render 測試（EPIC-M5 測試覆蓋擴大）。

## 3. 本次完成（Implement）

以測試為主，外加同型 **1 行 production UX bug 修正**（Refresh 按鈕載入中未 disabled）：

| 檔案 | 內容 |
|---|---|
| `frontend/components/workflow/__tests__/InventoryListPanel.test.tsx`（新，**29 tests**） | InventoryListPanel render 測試。`makeItem()`/`makeWarehouse()` 工廠結構式滿足 `InventoryItemResponse`/`WarehouseResponse`（所有欄位齊備，不用 `as` 強轉）；`renderPanel()` helper 注入 props + 回傳 callback spy。無 fetch / 無 hook → 不需 stub global.fetch、不需 async act。 |
| `frontend/components/workflow/InventoryListPanel.tsx`（改，**1 行**） | 補傳 `loading={loading}` 給 Refresh 的 `Btn`。修正載入中按鈕未 disabled 的 UX bug（避免使用者在 fetch 進行中重複點擊 Refresh 重複觸發查詢）。Btn 既有 `isDisabled = disabled \|\| loading` 邏輯，僅需把 prop 接上。與前兩個 session 對 WorkOrderListPanel / MaterialRequestListPanel 的同型修正一致。 |

### 覆蓋的 UX 契約
- **基本渲染 + 語系**：zh「倉別」/「搜尋（料號 / 名稱）」/「重新整理」+ counter「顯示 1 / 3 個料件」；
  en「Warehouse」/「Search (SKU / name)」/「Refresh」/「Showing 1 of 5 inventory items」（含 negative 守 zh 不外洩）。
- **warehouse filter**：Select 選項涵蓋「全部倉」+ 各倉（`is_default` 倉前綴 `★`）；value 反映 `warehouseId` prop；
  onChange → `onWarehouseChange` 帶選取值。
- **below-safety toggle**：文案隨 `belowSafetyOnly` 切換（「全部」↔「只顯示低於安全庫存」）；`aria-pressed` 反映狀態；
  onClick → `onBelowSafetyChange` 帶**取反值**。
- **search**：Input value 反映 `search` prop；onChange → `onSearchChange` 帶輸入值。
- **refresh**：onClick → `onRefresh`；`loading=true` → 按鈕文案「載入中…」/「Loading…」**且 disabled**；
  disabled 時點擊**不**觸發 `onRefresh`（守防重複觸發行為）。
- **error 態**：warn card 顯示 ⚠ + 錯誤訊息。
- **empty 態**：`items=[] && !loading && !error` → 「目前沒有符合條件的料件。」；
  loading 中**不**顯示空狀態（避免閃爍）；error 時**不**顯示空狀態（讓位給錯誤卡）。
- **列表 row**：SKU / name / 單位 / 三欄 stock（全新·良品·維修中）/ 安全·可用 / 最後出庫時間（時區）/
  `below_safety=true` → LOW pill「低於安全」（=false 不顯示）；`last_used_at=null` → 不顯示「最後出庫」；
  aria-label 帶 SKU；多筆各自渲染。
- **點擊接線**：點 row → `onSelect` 帶**該筆** inventory item（多筆中精準命中，`objectContaining` 守語意）。

### 技術要點
- **純 props → 測試最單純**：無 fetch / 無 effect，故不需 `global.fetch` stub 或 `await act(async)` flush；
  直接 render + fireEvent + 斷言。
- **computed 欄位明確 override**：`total_available` / `below_safety` 是 backend `@computed_field`（前端唯讀）。
  工廠 `makeItem` JSDoc 註明這點；測 LOW pill 等行為時以 overrides 明確指定 `below_safety`，
  避免依賴工廠對 computed 欄位的推導假設。
- **row 以 aria-label 鎖定**：每筆 row 是帶 `aria-label="開啟料件 {sku}"` 的 button，
  以 `getByRole('button', { name: ... })` 精準定位。
- **`makeItem`/`makeWarehouse` 結構式滿足型別**：所有欄位齊備（不用 `as` 強轉），
  真實 Props/型別 signature 漂移時 tsc 編譯失敗而非假綠。

## 4. Verify（本機跑綠才開 PR）

- `npx tsc --noEmit` → **0 error**
- `npx vitest run`（全量）→ **271 passed**（242 baseline + 29 新，**零 regression**）
- `npx vite build` → ✓ built（既有 chunk-size warning 與本次無關）
- backend 未動 → **638 passed / 1 xfailed** 不受影響

## 5. Review

跑 `code-reviewer` subagent 對 staged diff 找 must-fix / should-fix（production fix 判定正確安全；must-fix 2、should-fix 3、nice 3）。採納：

- **採納（must-fix #1）**：原「below_safety=true/false」測試在單一 `it` 內手動呼叫 `cleanup()` + 二次 render，
  破壞 fixture 隔離且兩情境共用一個測試標題。**拆成兩個獨立 `it`**（true→顯示 LOW pill / false→不顯示）。
- **採納（must-fix #2）**：below-safety toggle 原只測 `false→fires true` 單向。`!belowSafetyOnly` 反轉邏輯需雙向守護，
  **新增 `true→fires false`** 測試（本面板是三列表中唯一有此反轉 toggle，最需雙向覆蓋）。
- **採納（should-fix）**：新增 en warehouse Select 選項 `toEqual(['All warehouses', ...])` **正向**斷言
  （避免 `ui('All warehouses','全部倉')` 參數倒置時僅靠 negative test 誤判通過）。
- **採納（nice）**：新增 en below-safety toggle 文案測試（「All stock」/「Showing low stock only」正向守住）。
- **不採納**：computed 欄位工廠預設值的維護註解強化（價值低，現有 JSDoc 已說明 computed 唯讀）；
  loading 時 toggle/warehouse 仍可操作的契約測試（production 無此 gate，屬假想 future risk，低優先級）。

→ 測試數 24 → **29**。Re-verify 後 `vitest` **271 passed**（零 regression）。

## 6. 下次怎麼接手

同範式仍有候選（workflow 子面板，由小到大）：
- **PendingApprovalPanel**（270 行）— 簽核 panel，核心業務流程（仍未補測試）。
- 較大的 modal：**WorkOrderDetailModal**（933）/ **MaterialRequestDetailModal**（902）/
  **InventoryItemDetailModal/Drawer** — 互動多、需 mock dialog。
- **TurbineDetail**（1056 行）— 單機詳情，最大、demo 重要；recharts 多（jsdom 不渲染內部不影響斷言）。

> 至此 workflow 三大列表面板（WorkOrder / MaterialRequest / Inventory）render 測試**皆已落地**，
> 且同型「Refresh 載入中未 disabled」UX bug 三處**全數修正**。下個自然延伸是 PendingApprovalPanel
> 或進入 detail modal（互動較複雜）。

非 render 測試方向（需劉老師 / 素材）：
- M5-2 ChromaDB 整合 🔵（需評估 chromadb 依賴 + 向量檔來源）。
- M5-5 Part B-2 `/field/` my work orders（🟡 需釐清 persona/auth）。
- stale PR triage（飛輪上線前留下 22 筆，多數可能已過時 → 建議劉老師確認關閉或重開）。

## 7. 卡點 / 給劉老師

- 無技術卡點。
- **建議**：pre-flywheel stale open PR 累積中（22 筆），建議找時間 triage，
  避免 stack-aware 檢查每次都要略過一大票雜訊。
