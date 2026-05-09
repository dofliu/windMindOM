# 2026-05-09 — Inventory Repository + Atomic Dispatch（WMOM-20260509-02）

> Session 類型：實作（SQLAlchemy 2.0 ORM + repository + 雙寫交易 + 並發測試）
> Session 長度：中（A1 同日接力）
> 主導：Claude
> 結果：M4 核心完成 — Inventory + MaterialRequest persistence + atomic dispatch（stock + cost ledger 同 transaction），58 新測試 pass + 全 348 測試 0 regression。

---

## 1. Session 目標

依 ISSUES.md WMOM-20260509-02 acceptance：

- `modules/workflow/repository/inventory_orm.py`：7 SQLAlchemy mapped class（Warehouse / InventoryItem / MaterialRequest / MaterialRequestItem / MaterialReturn / MaterialRequestNotification / InventoryAdjustmentLog）+ Numeric for unit_cost
- `modules/cost/repository/cost_ledger.py`：CostLedgerEntryORM minimal layer（A5 expand）；共用 workflow Base 才能同 transaction 寫
- `modules/workflow/repository/inventory_repository.py`：CRUD + safety_stock + manual adjust + audit log
- `modules/workflow/repository/material_request_repository.py`：CRUD + state transition + **`dispatch_request()` atomic 雙寫**
- 50+ tests（含 mid-transaction failure rollback + parallel dispatch race + insufficient_stock + state mismatch）

---

## 2. 實際完成

### 2.1 新檔（7）

- `modules/workflow/repository/inventory_orm.py`（~180 行）— 7 ORM mapped class，共用 workflow `Base`
- `modules/cost/repository/__init__.py` + `modules/cost/repository/cost_ledger.py`（~140 行）— CostLedgerEntryORM + 3 enum + pure dataclass + `insert_in_session()` helper（不 commit，caller 控）
- `modules/workflow/repository/inventory_repository.py`（~290 行）— InventoryRepository + `apply_stock_delta_in_session()` helper（lock + 異動 stock，給 dispatch 用）
- `modules/workflow/repository/material_request_repository.py`（~360 行）— MaterialRequestRepository + atomic `dispatch_request()` + atomic `add_return()`
- `tests/test_inventory_repository.py`（21 tests）
- `tests/test_material_request_repository.py`（19 tests）
- `tests/test_dispatch_atomic_transaction.py`（**18 tests — M4 核心**）

### 2.2 改檔（1）

- `modules/workflow/repository/__init__.py`：加 13 個新 export（7 ORM + 3 repository + 3 exception/helper）

### 2.3 驗收

- **58 new tests pass** in 4.36s
- **全 workflow suite 291 pass** (60 inventory domain + 173 work order/signoff + 58 A2) in 10.69s
- **cost + workflow combined 348 pass + 1 xfailed** (existing) in 18.10s — **0 regression**
- AcceptanceCriteria 全達標：
  - ✅ `dispatch_request` mid-transaction raise → **庫存 + ledger 同 rollback**（`unittest.mock.patch` 偽造 mid-failure 驗）
  - ✅ SELECT FOR UPDATE 在 SQLite WAL 下行為（並行 dispatch 自動序列化）
  - ✅ insufficient_stock / state mismatch / multi-item partial-fail 都正確擋

---

## 3. 設計決策

### 3.1 Cost ledger 放哪裡 — 共用 Base

`dispatch_request` 必須在同一個 `Session.commit()` 內寫 inventory + cost_ledger 兩張表才能 atomic。所以 CostLedgerEntryORM 必須跟 workflow ORM 共用 SQLAlchemy `Base`，雖然語意上是跨 module 耦合（`modules.cost` import `modules.workflow.repository.orm_models.Base`）。

替代方案：
- a) 用 distributed 2-phase commit — 過度工程，SQLite 也不支援
- b) 寫 ledger 失敗 retry — 不滿足 atomic 不變式
- c) 把 ledger 改丟 message queue — 走 eventual consistency，違反 DN-03 §2.3 "atomic 不變式"

最終選 **共用 Base**。`modules.cost.repository` 是 minimal layer，A5 才擴 query API + finish hook。

### 3.2 SELECT FOR UPDATE 在 SQLite 上的真實行為

SQLAlchemy 的 `with_for_update()` 在 SQLite 是 **no-op** — SQLite 沒 row-level lock。但 SQLite 的：
- BEGIN IMMEDIATE（SQLAlchemy 預設 transaction mode）
- WAL journal mode
- `busy_timeout=5000` PRAGMA（在 `_set_sqlite_pragmas` 設）

加起來會把寫入序列化（一次只一個 writer，其他 wait or timeout）。**並行 dispatch 在 SQLite 上會自動 serialize**，加上 ORM 內檢查 stock，最終結果正確（不會 double-spend）。

PostgreSQL 部署時 `with_for_update()` 才真做 row-lock，並發效能更好但語意一致。Test 內 `test_concurrent_dispatch_*` 兩個 thread 同時 dispatch 同 item 驗證了序列化的正確性（5 stock 兩個各要 4 個 → 1 成功 1 fail with InsufficientStock，最終 stock=1）。

### 3.3 `dispatch_request` 不走 `transition('dispatch')`

Domain 層 state machine 的 `dispatch` action 只動 status；真正扣 stock + 寫 ledger 在 repository。為避免 caller 誤用 `repo.transition(mr_id, 'dispatch')` 而漏掉 atomic 雙寫，repository 在這個 entry **明確 raise `MaterialRequestRuleViolation`** 提示 caller 改用 `dispatch_request()`。

### 3.4 工單 `material_request_ids` 欄位不寫入 work_orders 表

ISSUES.md A2 spec 提到「工單 material_request_ids 欄位回填邏輯」。我選 **reverse-lookup** 設計：在 `MaterialRequestRepository.list_for_work_order(wo_id)` 用 `WHERE work_order_id == wo_id` 查回所有 MR。優點：
- 不用動 `WorkOrderORM` schema（避免 migration）
- 沒有 list[UUID] JSON 欄位 vs FK 不同步的風險
- 反查效率有索引（`work_order_id` index 已加）

`WorkOrder.material_request_ids` dataclass 欄位仍存在但 ORM 不持久化；router 層需要時 caller 自己 `mr_repo.list_for_work_order()` 拿。

### 3.5 add_return 暫不寫 ledger 沖銷

`add_return()` 只動 stock + log，不寫 ledger 沖銷 entry。理由：

ledger 沖銷可以走兩條路：
- **每次退料寫一筆 negative ledger entry** — 簡單但 ledger 變很多筆
- **工單 finish hook 一次到位**：用 `actual_qty` vs `estimated_qty` 算差，把估計 entry status=estimated 翻成 confirmed + 修正 amount

A5 (cost ledger 整合) 會做後者，較精確。所以 A2 的 `add_return()` 暫只做 stock 加回 + log，不寫 ledger。

### 3.6 Numeric Decimal in SQLite

SQLAlchemy `Numeric(12, 4)` 在 SQLite 走 TEXT storage 但 round-trip 自動還原 Decimal。Test `test_create_item_unit_cost_decimal_roundtrip` 驗 4 位小數（123.4567）寫進 read 出仍然是同 Decimal。

---

## 4. Follow-up

- ⬜ A3 (MaterialRequest CRUD + state transitions API) — schema + router 接 transition + dispatch_request
- ⬜ A4 (Inventory query + adjustment API) — 純 read + adjust endpoint
- ⬜ A5 (cost ledger 整合) — read API + finish hook 把 estimated → confirmed
- ⬜ Integration with approval_router：當 MR signoff chain 全 approve → 自動 `mr_repo.transition(mr_id, 'approve_all')` → 然後 `mr_repo.dispatch_request(mr_id)`（A3 router 範圍）

---

## 5. Commit

`feat(#WMOM-20260509-02): inventory + material_request repository (atomic dispatch — M4 core)` — 9 files
