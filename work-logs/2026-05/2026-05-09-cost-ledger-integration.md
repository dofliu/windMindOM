# 2026-05-09 — Cost Ledger 整合（WMOM-20260509-05 / A5）

> Session 類型：實作（schema migration + repository + router + WO finish hook）
> Session 長度：中（A1/A2/A3/A4 同日連續第五輪）
> 主導：Claude
> 結果：**🎉 M4 backend 收官**（A1+A2+A3+A4+A5 全 done） — cost ledger estimated → confirmed flow 就位，月報資料源齊全。32 new tests + 全 435 pass / 0 regression。

---

## 1. Session 目標

依 ISSUES.md WMOM-20260509-05 acceptance：

- 擴充 `cost_ledger.py`：加 `source_item_id` 欄位 + ORM index 給 confirm flow
- `cost_ledger_repository.py`：query (get / list / find_for_mr_item / list_for_subject / summary_by_category) + confirm (`confirm_entry` idempotent)
- `cost_ledger_schemas.py` + `cost_ledger_router.py`：`GET /api/cost/ledger` + `GET /api/cost/ledger/summary`
- WO `finish` endpoint hook：對所有 linked MR 的 line item，用 `actual_qty × unit_cost` 翻 estimated → confirmed
- 完整鏈路一次測過：material_request dispatch → ledger entry created (estimated) → wo finish → ledger entry updated (confirmed)
- 15+ pytest pass

---

## 2. 實際完成

### 2.1 改檔（5）

- `modules/cost/repository/cost_ledger.py`：加 `source_item_id` 欄位（dataclass + ORM + insert_in_session）+ `confirmed_at` 欄位 + 新 index `ix_cost_ledger_source_item`
- `modules/workflow/repository/material_request_repository.py`：dispatch_request 寫 ledger 時帶 `source_item_id=UUID(it.id)` 給 confirm flow 用；cost_ledger 改成 lazy import 避循環
- `modules/cost/repository/__init__.py`：加 `CostLedgerRepository` + `get_cost_ledger_repository` export
- `modules/cost/routers/__init__.py`：export `ledger_router`
- `modules/monitoring/server/app.py`：mount `cost_ledger_router`
- `modules/workflow/routers/work_order_router.py`：finish endpoint 後加 `_confirm_material_ledger_for_finished_wo` hook + `set_finish_hook_db_path` test override
- `modules/workflow/tests/test_dispatch_atomic_transaction.py`：mock patch path 從 `mr_repo.insert_in_session` 改成 `cost_ledger.insert_in_session`（lazy import 後正確 target）

### 2.2 新檔（5）

- `modules/cost/repository/cost_ledger_repository.py`：CostLedgerRepository（180 行）— get / list (filters + pagination) / find_for_mr_item / list_for_subject / summary_by_category / confirm_entry idempotent
- `modules/cost/schemas/cost_ledger_schemas.py`：4 response model（CostLedgerEntryResponse / CostLedgerListResponse / CategorySummaryItem / CostLedgerSummaryResponse）
- `modules/cost/routers/cost_ledger_router.py`：2 read-only endpoints + factory injection
- `modules/cost/tests/test_cost_ledger_repository.py`：17 tests
- `modules/cost/tests/test_cost_ledger_api.py`：10 tests
- `modules/workflow/tests/test_lifecycle_ledger_confirmation.py`：5 acceptance tests（**完整 lifecycle 鏈路**）

### 2.3 2 endpoints

| Method | Path | 用途 |
|---|---|---|
| GET | `/api/cost/ledger` | list + filters (farm/from/to/category/status/source_type) + pagination |
| GET | `/api/cost/ledger/summary` | group by category，給月報用（status=confirmed → actual cost） |

⚠ **不暴露 POST/PATCH** — ledger 所有 mutation 必須走業務 atomic transaction（dispatch_request / wo finish hook），避免外部誤改帳本。

### 2.4 驗收

- **32 new tests pass** in 3.12s
- **全 workflow + cost combined 435 pass + 1 xfailed (existing) — 0 regression**
- ✅ 完整鏈路 acceptance test 過：建料件 → 建工單 → 開 MR linked to WO → submit + 3 階 approve（auto dispatch）→ ledger entry estimated（amount=900 = 2×450）→ receive actual_qty=2 → finish WO → **ledger entry confirmed with same amount**（actual=estimated 場景）
- ✅ Edge case 一個 test：`test_lifecycle_actual_differs_from_estimated` actual_qty=1 ≠ estimated_qty=2 → ledger 翻成 1×450=450
- ✅ Edge case 二個 test：`test_lifecycle_finish_without_receive_leaves_estimated` MR 未 receive → ledger 留 estimated（hook actual_qty=None 跳過）
- ✅ Edge case 三個 test：`test_lifecycle_no_linked_mr_finish_works` 工單沒 linked MR → finish 正常
- ✅ Reporting acceptance：`test_lifecycle_summary_after_confirm` 完整流程後 `summary_by_category(status=CONFIRMED)` 拿到 1350 EUR (3×450) 給月報用

---

## 3. 設計決策

### 3.1 加 `source_item_id` 欄位（schema migration）

A2 dispatch_request 對 MR 的 N 個 line items 寫 N 筆 ledger entries — 全部 `source_event_id=mr.id`。要 confirm 時得逐筆找對應 ledger entry，但只有 source_event_id 不夠（一張 MR 多 entries 同 event_id）。

加 `source_item_id` (nullable，給其他 source_type 留空間) 讓 confirm flow 用 `(source_event_id, source_item_id)` 精確找。Index `ix_cost_ledger_source_item` 加速查詢。

### 3.2 Confirm 用 idempotent semantics

`confirm_entry()` 內：

```python
if orm.status == CostLedgerStatus.CONFIRMED.value:
    return self._to_domain(orm)  # no-op
```

理由：
- WO 可能 finish → reject → finish 多次（DN-01 reject 回 IN_PROGRESS 流程），ledger 不能因此被改回
- 第一次 confirm 落地 amount = actual × unit_cost；後續即便 unit_cost 變動，confirmed amount 不變（鎖定當時的成本）

### 3.3 finish hook 寫在 router 而非 repository

WO finish hook 是 cross-module concern（讀 MR + inv + ledger）。如果寫在 `WorkOrderRepository.transition`，會讓 workflow.repository 直接 import cost.repository — 增加 repository 層的 cross-module 耦合。

寫在 `work_order_router.finish` 比較乾淨：router 是「協調 multiple modules」的層，這正是 router 該做的事。

### 3.4 finish hook 用 db_path override 做 test injection

既有 work_order_router 的 test injection 是 `set_repository_factory(wo_factory)`。但 hook 需要 mr/inv/ledger 三個 repos，全用 factory 注入很多 boilerplate。

折衷：加 `_finish_hook_db_path_override` + `set_finish_hook_db_path(path)` — test 直接告訴 hook 用哪個 db_path，hook 內部用 public factory `get_*_repository(db_path)` 獲取所有 repos。生產則 `_finish_hook_db_path_override = None` → 走 FarmRegistry。

既有 test_work_order_api / test_approval_api 不破：override 沒設 + FarmRegistry 沒 mock → hook 拿 db_path=None → 安靜跳過（log warning）。lifecycle test 設 override → hook 完整跑。

### 3.5 lazy import 解循環

A2 把 `cost_ledger.py` 引進 workflow 的 Base，從而觸發循環：

```
material_request_repository → cost_ledger →
modules.workflow.repository.orm_models（loads workflow.repository.__init__） →
material_request_repository（still loading）→
from cost_ledger import (...)（partial module）→ ImportError
```

修法：把 `material_request_repository.py` 對 cost_ledger 的 imports 改成 lazy（搬進 `dispatch_request` 函式內）。test patch path 也跟著從 `mr_repo.insert_in_session` 改成 `cost_ledger.insert_in_session`（lazy 後 attribute 不在 mr_repo 模組層）。

`cost_ledger_repository.py` 對 workflow 的 imports 也改 lazy（在 `get_cost_ledger_repository` 函式內）— 同理避循環。

### 3.6 不暴露 ledger POST/PATCH endpoints

Ledger 是「事實帳本」— 所有 mutation 必須走業務 atomic transaction（dispatch / wo finish）才有正確的 cross-table 一致性。如果暴露 POST endpoint 給外部寫，操作員一個誤點就讓 ledger 跟 MR 的數對不上。

寫死在 router 文件 + module docstring 強調這點，後續 reviewer 看到不會誤加。

### 3.7 summary endpoint 給月報用 status=confirmed

`GET /api/cost/ledger/summary?status=confirmed` 才是「actual cost」結算數字。預設 status=None 是 dashboard 看 in-flight cost 用（全部加總不分 estimated/confirmed）。A8 monthly_report.py 直接 hit confirmed-only 拼月報。

---

## 4. M4 進度

- ✅ A1 domain (60 tests)
- ✅ A2 repository + atomic dispatch (58 tests)
- ✅ A3 MaterialRequest API + signoff 整合 (27 tests)
- ✅ A4 Inventory query + adjustment API (28 tests)
- ✅ **A5 cost ledger 整合** (32 tests) ← 剛完成
- 🎉 **M4 backend 5 issue 全 done**
- ⬜ A6 material frontend
- ⬜ A7 inventory frontend
- ⬜ A8 reporting backend
- ⬜ A9 reporting frontend
- ⬜ A10 E2E lifecycle test

**M4 backend 累計**：5 issue / 205 new tests / 33 endpoints / 完整 lifecycle 鏈路（建料件 → 開單 → 簽核 → atomic 出庫 → 簽收 → 完工 → **ledger confirmed**）。M4 milestone progress 45% → 60%。

A5 是 M4 最後一塊 backend 拼圖。下一步：A6 frontend 接 API（material_request UI）或 A8 reporting backend（月報生成）。

---

## 5. Commit

`feat(#WMOM-20260509-05): cost ledger 整合 — estimated → confirmed flow (M4 A5 — backend 收官)`
