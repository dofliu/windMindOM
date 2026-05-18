# 2026-05-18 WMOM-20260509-F1 — `add_return` 寫 ledger 沖銷

> **Issue**：WMOM-20260509-F1
> **Branch**：`claude/nice-brown-j3oMK`（daily autonomous worker session 指定分支）
> **Goal**：補上 `MaterialRequestRepository.add_return` 同 transaction 內寫
> 一筆 **負值 cost ledger entry**，讓 monthly report `summary_by_category(status=CONFIRMED)`
> 不再因退料而偏高。

---

## 1. 為什麼今天做這個

依 5/18 早上 handoff（farm `is_offshore` Part C+D 收尾後）「下次候選」清單，
F1 是唯一兼具：

- **真實 correctness bug**：退料後月報材料成本偏高，是 M6 客戶 demo 會被發現的會計錯誤
- **scope 收斂**：0.5 day 估時，單一 method 修補 + regression tests，一個 session 可獨立完工
- **不阻塞 frontend A6 / A7**：可平行進行

A6 / A7（領料 / 庫存 frontend）估 1 day 整、F4（singleton refactor）只是 cosmetic。
F1 給 demo 用的 monthly report 報表正確性把關，優先級最合適。

---

## 2. Scope 與設計決策

### 2.1 為什麼走「新 entry with negative amount」而不是改既有 entry

ISSUES.md F1 已預設這個方向。重申理由：

- **Audit trail 完整**：退料事件獨立成 ledger row，可在 `list_for_subject` 看到「dispatch + N 筆退料」完整時序
- **避免「已 CONFIRMED entry 被改 amount」破壞 idempotent**：`confirm_entry` 設計成 idempotent
  no-op 已 CONFIRMED — 改 amount 等於 by-pass 這個 invariant
- **WO finish hook 無干擾**：hook 只 flip ESTIMATED → CONFIRMED 的「parent dispatch entry」，
  新負值 entry 從一開始就是 CONFIRMED，hook 自然跳過

### 2.2 `source_item_id` 用 `mr_item.id` 還是 `return.id`?

**選 `return.id`**（與 F1 issue 原描述不同 — 原描述寫 `source_item_id=item.id`）。

原因：`CostLedgerRepository.find_for_mr_item(mr_id, mr_item_id)` 用 `scalar_one_or_none()`，
**多筆同 `(source_event_id, source_item_id)` 會 raise `MultipleResultsFound`**。

若退料 entry 仍用 `mr_item.id`：
- dispatch 寫一筆（mr.id, mr_item.id）
- 退料寫一筆（mr.id, mr_item.id）
- WO finish hook 跑 `find_for_mr_item(mr.id, mr_item.id)` → 炸

改 `source_item_id=return.id`（MaterialReturn 的 UUID）：
- dispatch parent entry：`(mr.id, mr_item.id)` 維持唯一
- 退料 offset entry：`(mr.id, return.id)` 與 parent 不同 row、可獨立 query
- `find_for_mr_item(mr.id, mr_item.id)` 仍 scalar_one_or_none，無 collision
- `summary_by_category` 加總時兩種 entry 都進來，數字相加正確

把這個語意寫進 `CostLedgerEntry` docstring（"當 source 是 material_return 沖銷時，source_item_id=MaterialReturn.id"）。

### 2.3 `locked_unit_cost` 從哪取？

**從 parent dispatch entry 反查**，不重新查 `inventory.unit_cost`。

理由（與 review fix #1 一致）：dispatch 後若 inventory unit_cost 改變（市場價變動 / 手動 admin
修正），退料沖銷必須用「當初付出去那個成本」反沖才有會計意義。否則 dispatch 時付 450、
unit_cost 跳到 500、退料按 500 反沖 → 多沖了 50/件，confirm 後月報數字錯亂。

實作：在 `add_return` 同 session 內查 `(source_event_id=mr.id, source_item_id=mr_item.id,
source_type=material_request)` 拿 parent entry。

Fallback：parent 沒 `locked_unit_cost`（老舊 entries）→ fallback 查 inventory + log warning，
與 `_confirm_material_ledger_for_finished_wo` 同 pattern。

Fallback 之外：parent 完全找不到（dispatch 失敗但 status 進 DISPATCHED 之類的 corruption）
→ log warning + 跳過 ledger 寫入（**不阻擋 stock + MaterialReturn record**，避免退料卡在
exception 影響現場作業）。後續 reconciliation 再人工補。

### 2.4 status 用 CONFIRMED 還是 match parent?

**選 CONFIRMED**。退料是 definitive event（物料已實體入庫），與「dispatch 時尚未實際耗用所以
estimated」語意不同。`confirmed_at` 設 `_utc_now()`。

副作用：若 monthly report 跑在「dispatch 後但 WO 未 finish 前」時段，會看到 negative material
cost。但 M4 demo flow（dispatch → receive → finish → 報表）順序合理，這個 edge case 不會
頻繁出現；report tooling 也可用 status=None 或加總過濾另作呈現。

### 2.5 actor_id 用什麼

`returned_by`（add_return 既有參數 — 退料人）。與 dispatch entry 的 `actor_id`（dispatch 操作者）
獨立，後續 audit 看 actor_id 即可區分「dispatch by A / return by B」。

---

## 3. 檔案異動（規劃）

### 3.1 修改

```
M modules/workflow/repository/material_request_repository.py
    add_return：同 session 查 parent ledger entry → 寫負值 CONFIRMED entry
M modules/cost/repository/cost_ledger.py
    CostLedgerEntry docstring 補「source_item_id 對 material_return 沖銷時 = MaterialReturn.id」
M ISSUES.md
    F1 status → done
M STATUS.yaml
    progress / last_updated / next_milestone
```

### 3.2 新增 tests

```
M modules/workflow/tests/test_material_request_repository.py
    + test_add_return_writes_negative_ledger_entry
    + test_add_return_uses_parent_locked_unit_cost_not_current_inventory
    + test_add_return_multiple_returns_each_writes_offset
    + test_add_return_no_parent_entry_logs_warning_still_succeeds
    + test_add_return_atomic_rollback_on_ledger_failure
    + test_summary_by_category_confirmed_net_of_returns
```

---

## 4. TODO

- [x] Preflight + Branch + work-log
- [x] Read existing add_return / dispatch_request / find_for_mr_item / CostLedgerEntry
- [x] Implement add_return ledger offset
- [x] Update CostLedgerEntry docstring
- [x] Add regression tests（9 條）
- [x] backend pytest zero new regression（521 passed / 1 xfailed / 3 numpy 精度漂移 pre-existing）
- [x] code-reviewer subagent — 採納 2 must-fix + 1 should-fix + 1 nice-to-have
- [x] STATUS.yaml + ISSUES.md
- [ ] commit + push + PR

## 5. Code review 採納

Code-reviewer subagent 找出 **2 must-fix + 3 should-fix + 2 nice-to-have**。

**Must-fix 全採納（2/2）**：

1. ✅ `test_add_return_atomic_rollback_on_failure` 注入點在 `MaterialReturnORM` 建構，
   執行序早於 ledger insert，等於只驗 trivial path。**Fix**：rename 成
   `test_add_return_atomic_rollback_after_ledger_insert`，改 monkey-patch
   `cost_ledger.insert_in_session`：先呼叫原版 `insert_in_session` 讓 ledger entry
   進 session，再 raise — 驗證真正的 partial-flush rollback 路徑。新增 assertion：
   `MaterialReturn` record 也不可寫進 DB。
2. ✅ Function-level lazy import 與 top-level import 注解矛盾。**Fix**：保留
   top-level `import modules.cost.repository.cost_ledger as _cost_ledger`（觸發
   `cost_ledger_entries` 進 `Base.metadata`），移除 `dispatch_request` 與 `add_return`
   裡的 function-level `from ... import ...`，改 attr-access `_cost_ledger.X`。
   注解整理為單一源頭說明為何走 package 入口而非 `from .cost_ledger import` 直 import
   （後者會撞 partial-init circular）。

**Should-fix 採納（1/3）**：

- ⏭ Should-fix #3：`MaterialRequestItemORM` 無 `(request_id, item_id)` UniqueConstraint，
  同 MR 重複下料件 `parent_item_stmt.scalar_one_or_none()` 會 raise。**不採納**：
  既有 `MaterialRequest.create` 的 (item_id, qty, kind) tuple 沒去重保證，加
  UniqueConstraint 需 Alembic migration 動現有資料，**out of F1 scope**。風險
  mitigation：本場景下 `MultipleResultsFound` 會被外層 `except Exception:
  sess.rollback()` 接住整單 rollback，stock 不變、不產生 partial state；user
  看到 500 而非靜默資料毀損。建議獨立開 issue 改 create() 去重或加 UniqueConstraint。
- ✅ Should-fix #4：`confirm_entry` docstring 補一行說明「退料沖銷 entry（負 amount
  CONFIRMED）不走本 method，由 add_return 直接寫入」，避免未來誤用。
- ✅ Should-fix #5：加 `test_summary_by_category_confirmed_net_of_returns_within_date_range`
  — 模擬 monthly report 邊界：dispatch 1000 + 月內退 -100 + 月後退 -200，驗證月份內
  summary 應該只看到 900，全期 700。

**Nice-to-have 採納（1/2）**：

- ✅ Nice-to-have #6：`add_return` fallback 路徑 — `parent_entry` 有但
  `locked_unit_cost=None` 且 `inv_orm=None` 時，原本 fallback warning 仍指「no parent」
  訊息桶誤導 debug。**Fix**：單獨 log warning 「has no locked_unit_cost AND inventory
  item not found — skipping ledger offset」。
- ⏭ Nice-to-have #7：`test_add_return_multiple_returns_each_writes_offset` 的 expected
  amounts list 順序與 qty 變動不同步。**不採納**：trivial cosmetic，且原 assert 已
  sort，順序明確即可，不增加維護成本。

## 6. 最終驗證結果

- Backend: `pytest modules/workflow/ modules/cost/ modules/reporting/` →
  **521 passed / 1 xfailed**（baseline 512 + 8 F1 tests + 1 review-fix date-range test）
  + 3 pre-existing numpy 精度漂移 failure（無關 F1）
- 沒動 frontend（純 backend 修補，不需 tsc / vite build）

## 7. 下次接手建議

下次 daily session 候選工作（priority 排序）：

1. **A6 `/admin/workflow/material` 領料單 frontend**（high priority, 1d）— M4 frontend
   收官；用 ui kit + WorkOrderDetailModal pattern 寫 materialService / hook / list /
   wizard / detail modal + 改 WorkflowPage 加 material tab
2. **A7 `/admin/workflow/inventory` 庫存 frontend**（high priority, 0.5-1d）— 與 A6
   平行；料件列表 + safety_stock 警示 pill + 調整對話框 + audit drawer
3. **F2 `func.count` 取代 Python `len`**（low priority, 0.5h）— cosmetic perf；可
   塞進其他 PR
4. **F3 `list_warehouses` 加 repo method**（low priority, 0.5h）— cosmetic refactor
5. **F4 `_FARM_REGISTRY` lazy singleton 抽 shared**（low priority, 1h）— cosmetic
6. **WMOM-20260513-02 Demo Orchestrator full impl**（待 design 決定）

## 8. 重要決策記錄

- **`source_item_id=MaterialReturn.id`**（不用 `mr_item.id`）— 保護
  `find_for_mr_item.scalar_one_or_none()` 唯一性。Docstring 更新到 `CostLedgerEntry`
  的兩種 row pattern 說明
- **退料 entry status=CONFIRMED 直接寫**（不走 confirm_entry）— 退料是 definitive
  event，amount 為負值，與 confirm_entry 的「正向 flip」語意不重疊
- **Top-level `import cost_ledger`（不 from import）**— 觸發 Base.metadata 註冊
  cost_ledger_entries 表，但避開 partial-init circular（直接 from import 在
  workflow.repository.__init__ 載入過程中會撞）
- **Should-fix #3 (UniqueConstraint) 延後處理** — out of F1 scope，需 Alembic migration
