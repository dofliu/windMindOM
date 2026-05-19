# 2026-05-19 — WMOM-20260519-01 `add_return` 超量退料 domain guard

> Autonomous daily worker session（5/19 第二場，20:00 cron 觸發）。
> 接續 5/19 早場 WMOM-20260509-F1（`add_return` 寫 ledger offset entry）— 完成 F1 留下的會計邊界 follow-up。

---

## 1. 任務範圍

**Issue**：WMOM-20260519-01 — `add_return` 超量退料 domain guard 評估（F1 follow-up）

**痛點**：F1 把 `add_return` 升級成「寫 stock + MaterialReturn + ledger offset entry」三寫，但
F1 docstring 標註會計邊界「caller 責任」：

```
dispatched 2 件 + wo finish actual=1 confirm + 退料 2 件
→ dispatch entry confirmed = +300
→ return offset entry confirmed = -600
→ confirmed 視角總和 = -300（**負值材料成本**，月報異常）
```

物理層面也錯：庫存只出去 2 件，退回 2 件等同消費歸零；但若 wo finish 已報 actual=1，
等同 user 自相矛盾（「我用了 1 件」+「我全部退回」）。

**目標**：在 domain 層加 guard 阻擋這類超量退料，errno 422 給 UI/router 看。

---

## 2. 設計決策

### 2.1 Guard 公式

```
max_returnable = total_dispatched - total_consumed - already_returned
```

其中：
- `total_dispatched` = `sum(MaterialRequestItem.estimated_qty)` for (request_id, item_id) 
  — **跨 stock_kind aggregate**（支援 cross-kind return：dispatch NEW 5 → return USED 5）
- `total_consumed` = `sum(MaterialRequestItem.actual_qty)` for (request_id, item_id), `actual_qty IS NOT NULL`
  — wo finish 後 `actual_qty` 寫回；未填者視為 0（尚未報耗用）
- `already_returned` = `sum(MaterialReturn.qty)` for (request_id, item_id)
  — 跨 return_to_kind aggregate

Raise `MaterialRequestRuleViolation` 若 `qty > max_returnable`。

### 2.2 為什麼跨 stock_kind / return_to_kind aggregate？

Cross-kind 是合法業務情境（dispatch NEW、試裝失敗後歸 USED）。若 guard 按 stock_kind 分開
比對，cross-kind 退料會誤 block。

聚合 by (request_id, item_id) 嚴格擋「退多於派」物理上限，且不誤殺 cross-kind。

### 2.3 為什麼選 domain 層而不是 router 層？

- Repository test 涵蓋（不只 API integration test）
- 任何 caller 不論走 router / 內部呼叫都享有 guard
- Atomic：guard fail → 整 transaction rollback，stock / return / ledger 全不寫

### 2.4 其他考量（**不做**）

- **不做** restricted MR status guard（如「只允許 DISPATCHED 退料」）— 已存在
  `test_add_return_without_dispatch_entry_uses_inventory_fallback` 認可 DRAFT 退料的
  fallback 路徑（F1 已實作），不破壞既有 contract
- **不做** UI 層擋（前端已有 wizard 但 backend 必須是 source of truth）
- **不做** 「return 時自動修正 wo actual_qty」— 跨 domain 改動，scope creep

---

## 3. 實作步驟（執行紀錄逐步補）

### 3.1 程式碼

- [x] `material_request_repository.py:add_return` 加 guard call
- [x] 抽 `_assert_return_within_dispatched` static helper（testability + 單一責任）
- [x] 更新 add_return docstring（會計邊界段改寫，加 guard 說明 + F1-follow-up 已關閉）

### 3.2 測試（新加 negative path + 邊界）

- [x] `test_add_return_rejects_over_dispatched_single_shot`：5 dispatched, return 6 → block
- [x] `test_add_return_rejects_over_returned_cumulative`：3 + 3 of 5 → 第二次 block
- [x] `test_add_return_rejects_over_consumed_after_wo_finish`：dispatched=2, actual=1, return=2 → block
- [x] `test_add_return_allows_return_within_consumed_gap`：dispatched=2, actual=1, return=1 → 允許
- [x] `test_add_return_allows_full_return_pre_wo_finish`：dispatched=2, return=2 (no actual) → 允許
- [x] `test_add_return_guard_cross_stock_kind_aggregates_by_item`：dispatch NEW 5 → return USED 5 ≤ 5 → 允許
- [x] `test_add_return_guard_multi_line_same_item_aggregates`：MR 含 (NEW 3, USED 2) → return USED 5 ≤ 5 → 允許
- [x] `test_add_return_rejects_unknown_item_in_mr`：item 不在 MR → block
- [x] `test_add_return_over_return_atomic_no_side_effects`：block 時 stock/return/ledger 都不變
- [x] 確認既有 17 個 F1 test 不被破壞

### 3.3 Verify

- [x] backend `python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/`
- [x] frontend 無改 — 跳過 frontend build

### 3.4 Review

- [x] `code-reviewer` subagent 跑 staged diff

### 3.5 Wrap-up + commit + push

- [x] 更新 STATUS.yaml + ISSUES.md
- [x] commit + push branch + open PR

---

## 4. 結果（執行後補）

### 4.1 Backend tests

- 新加 test：11 個全 pass（review 後新增 2 個：DRAFT MR 擋 + surplus-after-full-receive 允許）
- 既有 add_return F1 test：17 個全 pass（zero regression）
- 整體：`modules/workflow + cost + reporting` 555 passed + 1 xfailed + 4 pre-existing baseline failures
  （1 SQLite WAL flaky 沙箱限制 + 3 numpy drift）

### 4.2 Code review must-fix（採納全 3 個）

1. **MF#1 actual_qty semantic 修正**（最關鍵）：原以為 actual_qty 是 wo finish 耗用量，
   reviewer 指出實際是 `receive` transition 簽收量。formula 從
   `max = estimated - consumed - returned`（subtraction，誤殺 full-receive surplus）
   改為 `physical_ceiling = (actual if set else estimated)` per-line aggregate
   （replacement，正確 model 物理上限）。helper 改名
   `_assert_return_within_physical_ceiling`，docstring 補詳細 semantic 說明。
2. **MF#2 race condition**：`add_return` MR row select 加 `with_for_update()`，
   序列化 concurrent callers（同 dispatch_request pattern）。
3. **MF#3 DRAFT MR explicit test**：原本改 `test_add_return_increments_stock`
   只是讓它過 guard，沒明確 document DRAFT MR 也受 estimated_qty 約束。加
   `test_add_return_draft_mr_rejects_over_estimated` 補上。

### 4.3 Code review should-fix（採納 4/6）

- ✅ SF#1 error message 繁中化（CLAUDE.md §7：使用者輸出繁體中文）
- ✅ SF#2 加 surplus-after-full-receive happy path test
- ✅ SF#3 cumulative atomic 加 already_returned 累計不變斷言
- ✅ SF#4 開 follow-up WMOM-20260519-02 補 `_guard_receive` 上限校驗
- ❌ SF#5 actual_qty > estimated_qty 的 confusing-message test：移到 WMOM-20260519-02 scope
- ❌ SF#6 max_returnable < 0 distinct error：與 SF#5 同源，靠 -02 修了上限就消失

### 4.4 Code review nice-to-have（不採納）

- NH#1 `or 0` 雙保險：cosmetic，留 defensive
- NH#2 兩 query 合 CTE：premature optimization at current scale
- NH#3 `_setup_dispatched_mr` 抽 conftest：fixture 抽集中是更大重構，scope creep

### 4.5 PR

- 開 PR：超量退料 domain guard + 11 個新 test + 採納 9/12 review items

---

## 5. 下次接手

- **F2-F5 一次清掉**（4 個 cosmetic refactor，估時各 0.5h-1h）
- **M5 規劃** — Knowledge / RAG + 現場 mobile UI
- **WMOM-20260513-02 demo orchestrator simulator**（M5 demo polish）

