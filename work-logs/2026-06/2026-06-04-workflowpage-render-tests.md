# 2026-06-04 — WorkflowPage component render 測試（EPIC-M5 測試覆蓋擴大）

> autonomous worker session（每 3 小時 cron）。接續同日 farmoverview-render-tests handoff 建議：
> 「同範式續推 SettingsPage / HistoryPage / workflow 各 panel 測試」。挑 **workflow 模組主入口**
> （核心庫存派工簽核，商業價值最高且先前頁面層零覆蓋）為本次目標。
> issue：**WMOM-20260604-05**（WorkflowPage component render 測試）

---

## 1. 為什麼做這個

開工 preflight（決策樹）：

- 優先級 #1 known blocker / #2 baseline regression / #3 飛輪壞掉 → **皆無**。
  - backend `pytest` → **638 passed / 1 xfailed**（綠）
  - frontend `vitest` → **141 passed**（綠；上個 session FarmOverview 18 tests 已 auto-merge 進 main，PR #77）
  - 飛輪健康：FieldPage→ReportsPage→CostPage→FarmOverview 連續四個 render 測試 PR（#74~#77）皆 auto-merge 進 main。
- stack-aware：`list_pull_requests` open=22，全為飛輪上線前的 stale PR（無 `[WIP]`、非本 session 系列、無 CI run 不會被誤合）。本次工作（net-new 測試檔）與它們**零 collision**。

→ 落到優先級 #4「乾淨 autonomous 工作」。前四個同日 session 連續 handoff 背書「同範式續推 workflow 各 panel」。在候選（SettingsPage 781 / HistoryPage 809 / workflow 各元件）中選 **WorkflowPage**（`components/workflow/WorkflowPage.tsx`，502 行）：

- **商業價值最高**：workflow 是 windMindOM 五大 module 的核心「庫存派工簽核」，主入口先前 `components/workflow/` 目錄只有 `statusUtils` helper 單元測試、頁面層零覆蓋。
- **零設計歧義、單 session 可完工**：純 tab 路由 + hook 接線，5 個 stateful hook + 11 個子元件依賴可乾淨 mock，範式（FieldPage/ReportsPage/CostPage/FarmOverview）已成熟。

## 2. 認領

**WMOM-20260604-05** — WorkflowPage component render 測試（EPIC-M5 測試覆蓋擴大）。

## 3. 本次完成（Implement）

純測試，**不動任何 production 程式**：

| 檔案 | 內容 |
|---|---|
| `frontend/components/workflow/__tests__/WorkflowPage.test.tsx`（新） | WorkflowPage render 測試 **21 tests**（review 後從 17 擴到 21）。mock 5 個 stateful hook（`useWorkOrders` / `useMaterialRequests` / `useInventory` / `usePendingApprovals` / `useCurrentUser`）+ 11 個子面板/wizard/modal 以 marker 取代（攤平關鍵 props 到 `data-*` + 提供觸發 `onSelect`/`onSubmit`/`onApproveClick`/`onRejectClick` 回呼的按鈕）+ `global.fetch` stub 路由 `/api/farms`（active farm 載入）。元件用 `ThemeProvider` 包裹。 |

### 21 tests 覆蓋的 UX 契約
- **active farm 載入三態**：載入中（farmId null 初始態 → 「載入風場中…」，不渲染 tab/面板）/ fetch 失敗（`errorResponse(500)` → warn card「無法載入目前風場：」）/ 成功（header 顯示風場名 + 目前身份 currentUser.name + 中文標題 + 預設停工單 tab aria-pressed）
- **四 tab 切換**：工單 / 領料單 / 庫存 / 簽核 —— 面板切換 + aria-pressed 翻轉 + 互斥（切走舊面板消失）
- **Create 按鈕依 tab**：orders → 「建立工單」/ material → 「建立領料單」/ inventory·approval → 無 create 按鈕
- **簽核 pending 徽章**：`approvals.total>0` → tab 內顯示數量徽章；`=0` 不顯示
- **子面板 props wiring（四面板對等）**：工單 / 領料單 / 庫存 / 待簽 面板各自收到對應 hook 的 `total`/`loading`/`error`（攤平到 data-* 斷言，避免接錯 hook）
- **row 點選開 modal/drawer**：點工單→WorkOrderDetailModal / 點領料單→MaterialRequestDetailModal / 點庫存→InventoryDetailDrawer / 點核准→ApprovalActionDialog（approve）/ 點駁回→ApprovalActionDialog（reject，對稱守住）
- **建立 wizard 接線（對稱）**：建立工單→wizard 開→送出→`wo.create` 帶正確 req + wizard 關閉（handleCreate 兩半契約）；建立領料單→wizard 開→送出→`mrHook.create` 帶正確 req + wizard 關閉（handleCreateMR）
- **語系**：`lang='en'` → 四個 tab + create 按鈕 aria-label 英文 + negative（不出現中文 tab 名，守 ui() 映射未對調）；`lang='zh'`（成功載入測試）反向守住中文

### 技術要點
- **marker mock 攤平 props**：不渲染 350~930 行子元件（WorkOrderDetailModal 933 / MaterialRequestDetailModal 902 / CreateMaterialRequestWizard 690 …）內部，只驗 WorkflowPage 的 tab 路由 / 接線。
- **hook 工廠結構式對齊**：`makeWO`/`makeMR`/`makeInv`/`makeApprovals` 完整實作 `UseXxxResult` 介面（不用 `as` 強轉），任一欄位/簽章漂移 tsc 即編譯失敗，而非靜默假綠。
- **fixtures 型別嚴格**：`makeWorkOrder`/`makeMaterialRequest`/`makeInventoryItem`/`makePending` 全列必填欄位、enum 值用字面量 union，tsc 守住與 service 真實 signature 對齊。
- **async farm 載入態**：WorkflowPage 在 `useEffect` 內 `await farmApi.list()`，故載入態用永不 resolve 的 promise 斷言初始 render；其餘態以 `await renderWorkflow()`（內部 `act(async)` flush）等 effect settle，零 act() 警告。
- **fetch stub 不靜默**：未預期 URL `reject(Error('Unexpected fetch'))`，新增 API 呼叫不會被靜默吞掉。

## 4. Verify（本機全綠才開 PR）

- `npx tsc --noEmit` → **0 error**（無 `any`，hook/子元件 mock 與真實型別嚴格對齊）。
- `npx vitest run` → **162 passed**（141 baseline + 21 新；**零 regression**）。
- `npx vitest run …WorkflowPage --sequence.shuffle` → 21 passed（順序無關、無共享狀態污染）。
- `npx vite build` → ✓ built（僅既有 chunk-size 提示，無新警告）。
- backend 未動 → **638 passed / 1 xfailed** 不受影響（開工已驗）。

## 5. Code review

用 `code-reviewer` subagent 對 staged diff 跑審查（聚焦測試正確性 / 假綠 / mock 漂移 / flaky / cleanup）：
**3 must-fix / 6 should-fix / 3 nice-to-have，verdict Needs revision**。

**已採納（全部 3 must-fix + 6 should-fix + 3 nice-to-have，17 tests → 21 tests）**：
1. **[must-1 假綠]** 建立工單測試只驗 `wo.create` 被呼叫、未驗 wizard 關閉（`handleCreate` 兩半契約只守一半）→ 補 `expect(queryByTestId('create-wo-wizard')).not.toBeInTheDocument()`。
2. **[must-2 型別漂移]** `CreateWizardMockProps<unknown>` 把 onSubmit 型別抹成 unknown → 改具體 `CreateWOWizardMockProps`（`onSubmit: (req: CreateWorkOrderRequest) => Promise<void>`）/ `CreateMRWizardMockProps`（`CreateMaterialRequestPayload`），真實 Props signature 漂移即 tsc 失敗。
3. **[must-3 接線缺口]** `PendingApprovalPanel.onRejectClick` 接線完全未測 → mock 補 `onRejectClick` 欄位 + 「駁回」按鈕 + 新增「點駁回→ApprovalActionDialog 開」對稱測試。
4. **[should-4]** fetch 失敗路徑 inline `as unknown as Response` → 抽 `errorResponse(status)` helper，cast 集中一處。
5. **[should-5]** 「載入中」測試誤用永不 resolve fetch + act flush（語意混淆）→ 改為「farmId null 初始態」直接 render（不 act flush、不阻斷 fetch），加註解說明為何第一次 render 即 loading。
6. **[should-6]** `useCurrentUser` mock return 未對齊介面 → 抽 `makeCurrentUserResult`（型別 `ReturnType<typeof useCurrentUser>`，欄位漂移 tsc 告警），與其他四個 hook 工廠同範式。
7. **[should-7]** 只測工單面板 props wiring → 其他三個 panel mock 補 `data-loading`/`data-error`，新增領料單/庫存/待簽三個對等 wiring 測試（守住「接對 hook」）。
8. **[should-8]** row-select 用 `getByText` 與既有 `getByRole` 風格不一致 → 全改 `getByRole('button', {name})`。
9. **[should-9]** 語系測試風險不對稱 → en 測試補 negative（不出現中文 tab 名）+ 成功載入測試補中文標題斷言（雙向守 ui() 映射未對調）。
10. **[nice-10/11/12]** 工廠函式補一行 JSDoc；`TURBINES` 補註解「只傳進 mocked wizard、不對內容斷言」；新增領料單 wizard onSubmit→`mrHook.create`+close 測試（與工單對稱）。

**未採納**：無（全數採納；nice-to-have 多為與 must/should 同檔順手修）。

**Verify（採納後）**：`tsc` 0 error + `vitest` **162 passed**（141 baseline + 21 新，零 regression、`--sequence.shuffle` 亦綠）+ `vite build` ✓。

## 6. 下次 session 接手建議

- **同範式續推 component render 測試**：SettingsPage（781）/ HistoryPage（809）/ TurbineDetail（1056）/ workflow 子面板（WorkOrderListPanel / PendingApprovalPanel 等的 panel 級互動）。基礎設施 + 五個範例（FieldPage / ReportsPage / CostPage / FarmOverview / WorkflowPage）已就位。
- **M5-5 Part B-2**（my work orders + completion）—— 仍需劉老師釐清 persona/auth「who is me」（🟡）。
- **M5-2 ChromaDB**（🔵；需評估 CI 加 `chromadb` 重依賴的安裝時間 / Linux runner 相容，謹慎勿動搖飛輪）。
- **22 個 stale PR triage**（待劉老師 / 後續 session）。

## 7. 給劉老師小問題

- （無新增；沿用前次 FarmOverview「7D 趨勢實際只拉 1 天」待確認問題。）
