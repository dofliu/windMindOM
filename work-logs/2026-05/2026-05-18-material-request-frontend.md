# 2026-05-18 WMOM-20260509-06 — `/admin/workflow/material` 領料單 frontend (A6)

> **Issue**：WMOM-20260509-06 — A6 領料單 frontend（service + hook + List/Wizard/Detail + WorkflowPage `material` tab）
> **Branch**：`claude/issue-WMOM-20260509-06-2026-05-18`
> **Goal**：把 M4 backend 既有的 9 個 material_request endpoint 拉到前端，補完 demo flow：
> 「建工單 → 開領料單 → submit → leader 簽 → treasury 簽 → 自動 DISPATCHED → 點 receive 填 actual_qty」。

---

## 1. 為什麼今天做這個

依 2026-05-18 farm `is_offshore` Part C/D handoff doc 建議：「下次候選：**A6 領料 frontend** / A7 庫存 frontend / F1-F6 follow-up / WMOM-20260513-02 demo orchestrator 後續」。

A6 是 M4 最後一片 demo-blocker 大 frontend（A7 比較小）。M4 progress = 98%，A6 done 後可能直接到 100%。

E2E test（WMOM-20260509-10）2026-05-13 已驗 backend lifecycle 跑得通；前端 UI 是上 demo 給劉老師 / 客戶看 lifecycle 的視覺管道。

---

## 2. Scope 與設計決策

### 2.1 領料 picker 在 wizard 怎麼選 item？

選項：
- **A. 純 UUID input**（user 從別處拿到 item.id 貼上）— 對 demo 不友善
- **B. 內嵌「inventory item picker」** — wizard step 內 fetch `GET /api/workflow/inventory?farm_id=...` 列 item，點按鈕加進 cart。
- **C. 完整搜尋對話框** — 多按一次按鈕

選 **B** — 對 demo 視覺最自然（左邊待選料件 + 右邊已選 cart），且 A7 庫存頁未到位前可直接看 stock 數量。

需要新增小 hook `useInventoryItems`（只給 picker 用，不做完整 CRUD — A7 才做完整版）。

### 2.2 Approval flow 怎麼帶 MR detail？

既有 `usePendingApprovals` 已支援 `subject_type=material_request` filter + 自動 fetch work_order cache。對 material_request 也比照辦理：拉 MR detail 進 `materialRequestCache`，給 `PendingApprovalPanel` 顯示 MR business_key + items 摘要。

但動 `usePendingApprovals` + `PendingApprovalPanel` 等於同時動兩個 component，scope 偏大。妥協：
- **本 issue 內**只加 `materialRequestCache`（在 usePendingApprovals 並加 fetch），UI 顯示沿用「subject_type 是 material_request 時」的 fallback path（顯示 `…subject_id8` + `領料單`）。
- 把「approval panel 顯示 MR business_key + items」當 **follow-up nice-to-have**，不阻塞本 PR。

### 2.3 Detail Modal 的 transitions

MR 有 9 state；對應 6 個非 approval transitions：
- `submit_for_approval`（DRAFT → AWAITING_APPROVAL）
- `dispatch`（APPROVED → DISPATCHED，**通常 backend signoff 完自動觸發**，這裡只給 ops 手動補用）
- `receive`（DISPATCHED → RECEIVED + actual_qty 填寫）
- `close`（RECEIVED/USED → CLOSED）
- `cancel`（DRAFT/AWAITING_APPROVAL/APPROVED → CANCELLED）
- `returns`（建退料記錄 + atomic 加回 stock）

`approve` 走 approval tab（不在 detail modal 提供按鈕，避免讓 user 在兩個地方做同件事）。

`receive` 是最關鍵的 demo step — items 一個個顯示 estimated_qty + 給 user 填 actual_qty，submit 一次帶整個 dict 進 backend。

### 2.4 退料 UI

退料是 nice-to-have for demo（劉老師 demo 不一定要走退料 path），但 backend 已實作 + e2e 已涵蓋。MVP 在 detail modal 加「+ 退料」按鈕 → 簡易表單（item_id 從現有 items 選、qty、reason 4 種、return_to_kind）。

### 2.5 WorkflowPage tab 改 3 個（orders / approval / material）

- 現有 tabs 在 grid 內，加第三個 tab 不需要改 layout，只多一個 button + state.
- approval tab 的 subject_type filter 預留已存在，本 issue 不動。

---

## 3. 檔案異動（規劃）

### 3.1 新增

```
+ frontend/services/materialService.ts            client + types（mirror workOrderService 模式）
+ frontend/hooks/useMaterialRequests.ts            list + 6 transitions
+ frontend/hooks/useInventoryItems.ts              picker 用最小 hook（list items only）
+ frontend/components/workflow/MaterialRequestListPanel.tsx
+ frontend/components/workflow/CreateMaterialRequestWizard.tsx
+ frontend/components/workflow/MaterialRequestDetailModal.tsx
```

### 3.2 修改

```
M frontend/components/workflow/statusUtils.ts     加 MR status / return reason / stock kind label
M frontend/components/workflow/WorkflowPage.tsx   加 `material` tab + state + 新 modals
M ISSUES.md                                       WMOM-20260509-06 → done
M STATUS.yaml                                     M4 progress / last_updated / next_milestone
```

### 3.3 不新增 / 不修改

- `frontend/hooks/usePendingApprovals.ts` 內加 MR cache — 留 follow-up（scope 控制）
- `PendingApprovalPanel.tsx` 顯示 MR business_key — 留 follow-up

---

## 4. TODO（implementation checklist）

- [x] Read existing code（workOrderService / workflow components）
- [x] Branch + work-log
- [x] materialService.ts + inventoryService 部分（只給 picker 用）
- [x] useMaterialRequests.ts
- [x] useInventoryItems.ts
- [x] statusUtils.ts 擴
- [x] MaterialRequestListPanel.tsx
- [x] CreateMaterialRequestWizard.tsx
- [x] MaterialRequestDetailModal.tsx
- [x] WorkflowPage.tsx tab + modals
- [x] tsc clean
- [x] vite build zero error（4.05s, 743 modules）
- [x] backend zero regression（無動 backend；511 passed + 1 xfailed，與 baseline 完全一致：3 pre-existing numpy precision drift + 1 flaky concurrency test）
- [ ] code-reviewer subagent 跑 + 採納 must-fix
- [ ] STATUS.yaml + ISSUES.md
- [ ] commit + push + PR

---

## 5. 實作紀錄

### 5.1 完成檔案

新增（8 個檔）：
- `frontend/services/materialService.ts` — 9 endpoint client（material request 7 + inventory 1 + 共用 helpers）
- `frontend/hooks/useMaterialRequests.ts` — list + 6 transitions（create / submit / dispatch / receive / close / cancel / createReturn）
- `frontend/hooks/useInventoryItems.ts` — picker 用最小 hook（只 list）
- `frontend/components/workflow/MaterialRequestListPanel.tsx` — 列表 + status filter + business_key search
- `frontend/components/workflow/CreateMaterialRequestWizard.tsx` — 3 步精靈（關聯工單 → 選料件 → 檢閱）
- `frontend/components/workflow/MaterialRequestDetailModal.tsx` — 詳情 + 6 transition forms + items table
- `work-logs/2026-05/2026-05-18-material-request-frontend.md`

修改（2 個檔）：
- `frontend/components/workflow/WorkflowPage.tsx` — 加 `material` tab + 新 modals + create handler
- `frontend/components/workflow/statusUtils.ts` — 加 `mrStatusLabel` / `mrStatusTone` / `stockKindLabel` / `returnReasonLabel`

### 5.2 設計決策落實

- **Wizard 工單關聯 step 1**：filter 規則改用「排除 closed/cancelled」（涵蓋 draft/dispatched/in_progress/awaiting_signoff/reopened），比正面列舉更安全
- **Picker 兩欄 layout**：左 inventory pool / 右 cart，視覺對齊（review 階段確認）
- **Receive form 預填 estimated_qty**：避免空白導致 422，user 只改不一致的列
- **Stock kind / Return reason label**：3 + 4 = 7 個 enum 全覆蓋（建 cart 時 default `new` / `surplus`）
- **退料 item_id 對的是 inventory_item.id**（不是 MaterialRequestItem row id）— modal `setReturnItemId` value 是 `it.item_id`，submit 帶進 backend 的 `CreateMaterialReturn.item_id`

### 5.3 Build / test 驗證

- `npx tsc --noEmit` → exit=0
- `npx vite build` → 4.05s, 743 modules transformed, 896.86 kB（gzip 260.49 kB）— 與 reports frontend baseline 一致
- `python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/` → 511 passed, 1 xfailed, 4 failed（3 numpy drift + 1 flaky dispatch test — **與 main baseline 完全相同**，zero regression）

---

## 6. Code review 採納

Code-reviewer subagent 找出 **2 must-fix + 4 should-fix + 3 nice-to-have**。

**Must-fix 全採納（2/2）**：
1. ✅ `fmtDateTime` / `fmtDate` 使用 browser local timezone — 改用 `Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Taipei', … })` 顯式對 Asia/Taipei format，避免不同 browser timezone 漂移（既有 bug，本 PR 擴大 fmtDateTime 使用範圍至 MR timeline 6 個時間點，順手修齊。修法影響範圍：WorkOrderListPanel / WorkOrderDetailModal / PendingApprovalPanel / 新 MR components — 全部走同函式，在 Asia/Taipei browser 顯示結果完全一致；其他 timezone browser 從 local time 改顯示 Taipei time，更正確）
2. ✅ `selectedMR` sync 依賴 `mrHook.items`（filtered）— 在 search 啟用時把 selected row filter 掉導致 stale。Fix：`useMaterialRequests` 多 expose `rawItems`（未 filter），sync effect 改讀 `rawItems`

**Should-fix 採納（2/4）**：
- ✅ Should #1：backdrop click 在 wizard step 2 cart 有料件時直接關閉 — 加 `window.confirm` 防誤關
- ✅ Should #2：`mrStatusTone` 區分 received / used — 改成「進度感」漸進色：dispatched=accent / received=accent / used=ok / closed=ok（建立 demo 視覺進度感）
- ⏭ Should #3：AbortController 未串到 fetch signal — **此為 useWorkOrders 既有設計**，state-guard 已足夠（race 不會把舊回應寫進 state），fetch 多送一次 request 對 dev/local 影響小；統一改動需動 workOrderService（scope creep）。改為更新 `useInventoryItems` comment 註明，列為 follow-up 候選
- ⏭ Should #4：detail modal 料件表只顯 truncated UUID 不顯 SKU/name — 需 backend `MaterialRequestItemResponse` join inventory item（加 sku/name 欄）。對 demo 影響大，**已開 follow-up issue WMOM-20260518-01**（見下）

**Nice-to-have 採納（1/3）**：
- ✅ Nice #2：`useInventoryItems` comment 與實作矛盾 — 改為「state-guard 用 AbortController；fetch signal 未串入」
- ⏭ Nice #1：sortedWorkOrders 排序意圖無 comment — 既有 demo 場景最新工單在前是合理 default，留作 follow-up
- ⏭ Nice #3：`handleCreateMR` useCallback dep 應改為 `mrHook.create` — micro-optimization，沿用既有 useWorkOrders pattern（也是傳整個 hook object），統一改動 scope creep

### Follow-up issue（本 session 開）

**WMOM-20260518-01**（pending — 本 work-log 寫進，明日加進 ISSUES.md）：MR detail modal 料件表加 SKU/name 顯示。Backend 改 `MaterialRequestItemResponse` join 取 inventory_item 的 sku + name 兩欄；frontend 改 detail modal items table 顯示 SKU + name。Estimate 0.5d。Priority: medium（demo 給現場工程師看時更友善）。

### Build / test 再次驗證

- 修完 tsc 仍 0 error；vite build 3.56s, 743 modules → 897.21 kB（gzip 260.75 kB；比修前 +0.36 kB，Intl format 多）
- Backend 未動，pytest 仍 zero regression
