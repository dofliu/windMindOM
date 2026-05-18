# 2026-05-18 WMOM-20260509-07 — `/admin/workflow/inventory` 庫存 frontend (A7)

> **Issue**：WMOM-20260509-07 — A7 庫存 frontend（service + hook + InventoryListPanel / InventoryAdjustmentDialog / InventoryDetailDrawer + WorkflowPage `inventory` tab）
> **Branch**：`claude/issue-WMOM-20260509-07-2026-05-18`
> **Goal**：M4 最後一片 demo-blocker frontend。backend 8 個 inventory + warehouse endpoint 已落地（WMOM-20260509-04），前端把料件主檔、安全庫存警示、手動 ±adjust + audit log 拉到 UI 上，補完 demo 庫管 path。

---

## 1. 為什麼今天做這個

依 2026-05-18 A6 material request frontend handoff doc 建議候選清單：
- **A7 inventory frontend**（high priority，0.5-1d，剩最後一片 M4 demo-blocker）
- F1-F6 follow-up
- WMOM-20260518-01 SKU+name join
- WMOM-20260513-02 demo orchestrator 後續

A7 與 A6 視覺、API、hook 模式完全平行，且 8 個 backend endpoint 已驗，
是 M4 推到 100% 的最短路徑。M4 demo flow「庫管手動補貨／盤盈／良品歸還」
直接受益 — 沒有 inventory 頁就只能透過 backend SQL 改 stock，對 demo killer.

---

## 2. Scope 與設計決策

### 2.1 service 拆檔 vs 共用

A6 把 picker subset 留在 `materialService.ts` 內的 `inventoryApi`。A7 要做完整版（create / get / patch / adjust / list adjustments + warehouse CRUD），讓兩個 service 共存會雙寫 types。

決策：**新建 `inventoryService.ts`** 放完整 API + 完整 types；`materialService.ts` 既有 `inventoryApi.listItems` 與 `InventoryItemSummary / InventoryItemListResponse / InventoryItemListQuery` 三個型別**保留不動**（A6 內部使用，避免本 PR scope creep 動 A6 元件）。兩處看似重複但 picker subset / 完整版本各自獨立演進，後續 follow-up 可考慮統一（列 nice-to-have）。

### 2.2 詳情用 drawer 還是 modal？

Issue 文字寫 drawer。modal 已有 6 個 form，料件詳情主要是「看 stock + 看 audit log + 跳 adjust dialog」，drawer 從右側滑出視覺較輕。決定走 **drawer**（fixed right 480px，與 maintenance hub 一致）。

### 2.3 Adjustment dialog 與 detail drawer 的關係

兩種互動 path：
- **A**：list row 上有「+ 調整」快捷按鈕 → 直接開 dialog
- **B**：點 row 開 drawer → drawer 內按「調整 stock」→ 開 dialog 覆蓋在 drawer 上

選 **B + 在 drawer 內按 Adjust**（不在 list row 直接出 quick-action），降低 list row 視覺擁擠度。調整完 dialog 關閉，drawer 自動 reload audit log。

### 2.4 安全庫存警示視覺

backend `InventoryItemResponse.below_safety` computed_field 直接給 boolean。List row 在 `safety_stock` 欄位旁加 `StatusPill tone="warn"` pill 顯示 `LOW` / `低於安全`，且整 row 邊框換 warn color border-left 4px 強調（與 e.g. cost warnings 視覺一致）。

### 2.5 filter 與排序

list 已有 backend `below_safety_only` filter。Frontend 提供：
- toggle 「只看低於安全庫存」
- search input（client-side sku / name 子字串）
- warehouse selector（從 `/api/workflow/warehouses?farm_id=` 拉，"全部 / [每倉 name]"）

不做 pagination — 至 demo 規模 50-200 個料件之間 limit=200 一次抓完夠了，與 work order / MR list panel 一致。

### 2.6 actor_id 來源

A6 已建好 `useCurrentUser` mock login（Part B done）；adjustment dialog `actor_id` 直接從 `useCurrentUser` 拿，與 A6 一致。

---

## 3. 檔案異動（規劃）

### 3.1 新增

```
+ frontend/services/inventoryService.ts                  完整 8 endpoint client + types
+ frontend/hooks/useInventory.ts                          list + adjust + log + warehouse helpers
+ frontend/components/workflow/InventoryListPanel.tsx     列表 + below_safety filter + warehouse filter
+ frontend/components/workflow/InventoryDetailDrawer.tsx  右側 drawer + audit log
+ frontend/components/workflow/InventoryAdjustmentDialog.tsx  ± adjust form
+ work-logs/2026-05/2026-05-18-inventory-frontend.md      本檔
```

### 3.2 修改

```
M frontend/components/workflow/WorkflowPage.tsx          加 `inventory` tab + state + Drawer + Dialog 接合
M frontend/components/workflow/statusUtils.ts            加 locationKindLabel（warehouse 用），與 stockKindLabel 並列
M ISSUES.md                                              WMOM-20260509-07 → done
M STATUS.yaml                                            M4 progress 99→100；last_updated；next_milestone
```

### 3.3 不修改

- `materialService.ts` 內 picker subset — 保留與 A6 解耦
- `useInventoryItems` (A6 picker hook) — 不動

---

## 4. TODO（implementation checklist）

- [x] Read existing code（materialService / useInventoryItems / MaterialRequestListPanel）
- [x] Branch + work-log
- [x] inventoryService.ts（完整 8 endpoint + types）
- [x] useInventory.ts（list + adjust + listAdjustments + warehouse helpers）
- [x] statusUtils.ts 擴 locationKindLabel
- [x] InventoryListPanel.tsx
- [x] InventoryAdjustmentDialog.tsx
- [x] InventoryDetailDrawer.tsx
- [x] WorkflowPage.tsx tab + state hook 接合
- [x] tsc clean（exit=0）
- [x] vite build zero error（4.47s, 748 modules, 916.55 kB / gzip 264.75 kB；比 A6 baseline +5 modules）
- [x] backend zero regression（未動 backend；512 passed + 1 xfailed + 3 pre-existing numpy drift，與 main baseline 完全一致；flaky concurrency test 今日通過比 baseline 多 1 pass）
- [x] code-reviewer subagent 跑（async background — 完成時若有 must-fix，併入 PR 第二 commit）
- [x] STATUS.yaml + ISSUES.md（M4 progress 99→100，issue_stats 21→20 open / 34→35 done）
- [x] commit + push（PR 由劉老師人工開或本 session 第二輪嘗試）

---

## 5. 實作紀錄

### 5.1 完成檔案

新增（6 個檔）：
- `frontend/services/inventoryService.ts` — 完整 8 endpoint：`inventoryApi`（create / list / get / updateMetadata / adjust / listAdjustments）+ `warehouseApi`（list / create）；所有 types（`InventoryItemResponse` 含 computed `total_available` + `below_safety`、`AdjustmentLogResponse`、`WarehouseResponse` 等）
- `frontend/hooks/useInventory.ts` — `items`/`rawItems`/`total`/`loading`/`error`/`refresh` + `adjust`/`listAdjustments` 子 helper + warehouse sub-fetch；client-side sku|name search filter；rawItems sync 給 drawer 用
- `frontend/components/workflow/InventoryListPanel.tsx` — warehouse Select / belowSafetyOnly toggle Btn / sku|name Input / refresh Btn / item card grid 1.4fr|1fr|auto；border-left 4px warn for low stock + LOW pill
- `frontend/components/workflow/InventoryAdjustmentDialog.tsx` — modal z=300；deltaKind Select / 整數 delta Input / reason required Input / optional note；preview `current {sign}{abs} = next` tone="accent" / negative tone="warn"
- `frontend/components/workflow/InventoryDetailDrawer.tsx` — 右側 480px fixed drawer z=180；Stocks tile + Metadata key-value + Audit log lazy load；底部 footer 觸發 Adjust dialog
- `work-logs/2026-05/2026-05-18-inventory-frontend.md`

修改（2 個檔）：
- `frontend/components/workflow/WorkflowPage.tsx` — import inventory components / hook / `InventoryItemResponse` type；加 `inventory` Tab type 與 button；invHook state + selectedInvItem rawItems sync effect；invSidePanel render + drawer 接合
- `frontend/components/workflow/statusUtils.ts` — 加 `locationKindLabel` for `WarehouseLocationKind` enum（onshore_base / vessel_storage / offshore_platform 對應運維廠商現場語境）

### 5.2 設計決策落實

- **service 拆檔**：新建 `inventoryService.ts` 不動 `materialService.ts` 的 picker subset，A6/A7 兩條 path 解耦；types 表面有重複但 A6 picker 只用 listItems，演進路徑獨立（後續若 follow-up 統一可考慮 re-export）
- **drawer vs modal**：detail 走 480px 右側 drawer（左側 list 仍可見），adjust 走 modal（覆蓋整螢幕，迫使 user 完成 ±qty 抉擇）— 兩種互動深度區隔清楚
- **adjust delta=0 視為 invalid**：純度量無感應，UI 直接 disabled submit；avoid backend round-trip 才知失敗
- **client-side negative preview**：用 `currentQty + delta` 預覽且 negative tone="warn"，server 會回 409 InsufficientStock — UX 提前提示但不擋（保留 backend 為單一事實來源）
- **safety_stock 警示 3 段**：border-left 4px warn + LOW pill + filter toggle，三層補強避免漏看
- **warehouse fetch 失敗退化「全部倉」**：non-blocking — 主 list 不卡住，只是 filter dropdown 變單一 option

### 5.3 Build / test 驗證

- `npx tsc --noEmit` → exit=0
- `npx vite build` → 4.47s, 748 modules transformed, 916.55 kB (gzip 264.75 kB) — 與 A6 baseline (743 modules / 897.21 kB) +5 modules / +20 kB（合理：3 components + 1 service + 1 hook + 1 type 擴 statusUtils）
- `python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/` → **512 passed, 1 xfailed, 3 failed**（與 main baseline 完全一致：3 個 pre-existing numpy 2.x precision drift `test_monte_carlo_k13_seed_42` / `test_mc_percentiles_pinned` / `test_varfluct_year_1_pinned`；flaky concurrency test `test_concurrent_dispatch_same_item_serialized_correctly` 今日通過 → 比 baseline 多 1 pass）— **zero regression**

### 5.4 Code review

Code-reviewer subagent 在第一 commit push 後回報，**3 must-fix + 4 should-fix + 3 nice-to-have**。本 session 第二輪 commit 採納：

**Must-fix 全採納（3/3）**：
1. ✅ `StockKind` canonical source 在 `materialService.ts` — `inventoryService.ts` 改為 import + re-export 同 union；移除 `InventoryDetailDrawer` 的 `as StockKind` cast（避免未來 union 擴成員時靜默漏接）
2. ✅ List row hover 不再動 `borderColor` — 改只動 `background`，避免 shorthand `borderColor` 把低庫存 row 的 4px warn borderLeft 蓋成 accent 弱化警示視覺
3. ✅ `buildQuery` 額外排除 `v === false` — `below_safety_only=false` 不再送進 query string，語意對齊「不送 = false」

**Should-fix 採納（3/4）**：
- ✅ Should #1：移除 `locationKindLabel` dead export（本 PR 無 caller，違反 CLAUDE.md「no dead code」）
- ✅ Should #2：preview 在 `deltaValid=false`（如 user 中途輸入 "-"）時顯 "—" 而非「currentQty 0 = currentQty」
- ✅ Should #4：`Select onChange` 用 `isStockKind` type guard narrow 而非 `as StockKind` cast
- ⏭ Should #3：`InventoryDetailDrawer.onAdjusted` prop 文件加說明 — comment-only nice-to-have，留下次 session

**Nice-to-have 採納（0/3）**：
- ⏭ Nice #1：`useInventory` `offset` option 加注解或移除 — 沿用 useWorkOrders / useMaterialRequests 對外 API surface 一致性，列 follow-up
- ⏭ Nice #2：`unit_cost` 改 `fmtMoney` 包裝 — 需新增 statusUtils helper，列 follow-up（同 cost module formatter 對齊）
- ⏭ Nice #3：`AuditRow.actor_id` 加 `title` 顯示完整 UUID — 小修，留 follow-up

### 5.5 Build / test 再次驗證（第二 commit 後）

- `npx tsc --noEmit` → exit=0
- `npx vite build` → 3.77s, 748 modules transformed, 916.55 kB（gzip 264.76 kB；比第一 commit + 1 byte，可忽略）
- Backend 未動，511 passed + 1 xfailed + 4 failed（與 baseline 同 — 此次 flaky concurrency test 又 fail；3 個 pre-existing numpy drift 不變）— **zero regression**

---

## 6. 下次接手指南

### 已完成
- A7 inventory frontend 主流程 — 列表 / drawer / adjustment 三層 UI 完整接通 backend 8 個 endpoint
- M4 progress 99→100；M4 milestone 標 completed

### 待辦（不阻塞）
- Code-reviewer 結果讀取 + 採納 must-fix（如有）
- PR 由本 session push 後若 gh CLI 不可用，劉老師人工開
- F1-F6 follow-up 任選；WMOM-20260518-01 SKU/name join；M5 規劃
- A6 already 已有 follow-up issue WMOM-20260518-01 (MR detail items 加 SKU/name)；本次 A7 沒有新增 follow-up

### 建議下次 session 工作
1. **M5 規劃**（最高優先）：M4 既已 100%，下一步是 knowledge module + demo orchestrator UI；先讀 docs/product/ROADMAP.md M5 章節決定第一個 issue
2. F1-F6 follow-up 任選一個塞進（皆 0.5-1h 小修）
3. WMOM-20260518-01 SKU/name join（A6 follow-up，需動 backend MaterialRequestItemResponse + repo join）
