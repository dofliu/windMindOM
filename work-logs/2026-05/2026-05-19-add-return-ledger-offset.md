# 2026-05-19 WMOM-20260509-F1 — `add_return` 寫 ledger 沖銷

> **Issue**：WMOM-20260509-F1 — `add_return` 退料後沒寫 ledger 沖銷 entry，導致
> `summary_by_category(status=CONFIRMED)` 月報材料成本偏高。
> **Branch**：`claude/nice-brown-W1rov`（daily worker designated branch）
> **Goal**：退料時於同 transaction 內寫一筆 negative ledger entry，沖銷原 dispatch
> 已 confirmed 的成本，使月報數字正確；保留完整 audit trail。

---

## 1. 為什麼今天做這個

依 2026-05-18 inventory frontend handoff doc 建議候選：M5 規劃 / F1-F6 / WMOM-20260518-01。
M4 已 100%；F1 是 medium priority、0.5d 規模、有實際 customer impact
（demo 給客戶看月報時，已 confirmed 的材料成本偏高 — 客戶很可能會直接發現）。
單天一項重要工作 — F1 是「對的尺寸 × 對的優先級」。

---

## 2. Scope 與設計決策

### 2.1 新 entry vs update 既有 entry

選 **新 negative entry**（issue 描述 + code-reviewer 建議）：
- 保留完整 audit trail（看得到「dispatch +X 元 → 退料 -Y 元」兩筆 history）
- 不破壞既有 entry 的 source_item_id / locked_unit_cost / confirmed_at snapshot
- 月報照常 SUM(amount) 自動 net out
- 與 dispatch flow 「每筆 source event 一筆 entry」對稱

### 2.2 Status：CONFIRMED

退料 = 實際發生的負成本（已 reverse 的庫存），不是估計。直接寫 CONFIRMED + 設
`confirmed_at = now`，避免「dangling estimated」造成月報 estimated 桶亂跳。

### 2.3 locked_unit_cost 來源

從原 dispatch entry 拿 `locked_unit_cost`（會計一致性 — 退料金額 = 領料金額 ×
退量/領量 同基礎）：
1. 在 `add_return` session 內 query `CostLedgerEntryORM`，by
   `source_event_id=mr_id, source_item_id=MR_line_item.id, source_type=MATERIAL_REQUEST`
2. 若 entry 有 `locked_unit_cost` → 使用該值
3. 若 entry `locked_unit_cost is None`（老 entries 向後相容）→ fallback 查
   `inventory_item.unit_cost`（同 wo_finish hook pattern）
4. 若連 entry 都查不到（罕見：dispatch 之前的 return？）→ log warning, skip
   ledger write，**仍寫 MaterialReturn**（不擋 stock 加回）

### 2.4 MR line item lookup

`add_return.item_id` 是 inventory SKU，ledger entry `source_item_id` 是
MR line item `MaterialRequestItem.id`。需要 join：
```python
sess.execute(
    select(MaterialRequestItemORM).where(
        MaterialRequestItemORM.request_id == str(request_id),
        MaterialRequestItemORM.item_id == str(item_id),       # SKU
        MaterialRequestItemORM.stock_kind == return_to_kind.value,
    )
).scalars().first()
```

若同一張 MR 內同 SKU+kind 出現多筆 line item（理論不該但防禦） → 取第一筆。
若找不到 line item → log warning, skip ledger write。

### 2.5 Atomicity

寫在 `add_return` 同一個 session，與 stock += qty 屬同 transaction：
- 半路任一 raise → `sess.rollback()` → stock / ledger / return record 全部不變
- commit 才一起 visible

### 2.6 `actor_id`

帶入 `returned_by`（誰退的料 = ledger entry actor），與 dispatch 用 `actor_id`
對稱。

### 2.7 Note 格式

`note=f"退料沖銷 reason={reason.value} qty={qty} {kind} ret={return_id_short}"`
— 給月報 / audit trail 一眼看得出沖銷類型 + 反查 MaterialReturn 紀錄。

---

## 3. 檔案異動（規劃）

### 3.1 修改

```
M modules/workflow/repository/material_request_repository.py
  - add_return() 內 atomic 加寫 negative ledger entry
  - 移除 docstring 內「⚠ 不寫 ledger 沖銷」說明
M modules/workflow/tests/test_material_request_repository.py
  - 加 regression test：退料寫負 entry / SUM(amount) net 正確 / 退料前後
    confirmed summary 對得上
M ISSUES.md
  - F1 → done
M STATUS.yaml
  - issue_stats / last_updated / next_milestone
```

### 3.2 新增

```
+ work-logs/2026-05/2026-05-19-add-return-ledger-offset.md（本檔）
```

### 3.3 不修改

- `cost_ledger.py` schema 不動（已 nullable / 含必要欄位）
- `wo_finish` hook 不動（退料後若再 finish 同 wo，重新 confirm 不會影響負 entry，
  因為負 entry 是獨立新 entry，不會被 `find_for_mr_item` 翻轉 — 原 dispatch 對應
  的正 entry 也仍只翻轉一次）
- Frontend 不動（退料 UI 之後再做，不在本 issue scope）

---

## 4. TODO（implementation checklist）

- [x] Read existing `add_return` + `dispatch_request` + `_confirm_material_ledger_for_finished_wo`
- [x] Branch on `claude/nice-brown-W1rov` + work-log
- [x] Implement `add_return` ledger offset
- [x] Regression tests（5 個新 test 全 pass）
- [x] Verify backend pytest（**zero regression**：517 passed + 1 xfailed + 3 pre-existing
      numpy drift；今天 flaky concurrency test 也通過）
- [x] code-reviewer subagent 跑 staged diff（async background）
- [ ] 修 must-fix（如有）
- [ ] STATUS.yaml + ISSUES.md
- [ ] commit + push branch

---

## 5. 實作紀錄

### 5.1 修改檔案

`modules/workflow/repository/material_request_repository.py`（+ ~75 行）
- `add_return()` 加 lazy import `cost_ledger` 6 個 symbol（含新 `CostLedgerEntryORM`
  for in-session reverse lookup）
- 同 session 內 query `MaterialRequestItemORM` by `(request_id, item_id, stock_kind)`
- 同 session 內 query `CostLedgerEntryORM` by `(source_event_id, source_item_id,
  source_type)` 拿 `locked_unit_cost`
- 三條 sourcing fallback：dispatch entry → inventory.unit_cost → skip
- 寫 `CostLedgerEntry` with `amount=-qty*locked_cost, status=CONFIRMED,
  confirmed_at=now, actor_id=returned_by, note="退料沖銷 reason=... qty=... kind=... ret=..."`
- 移除舊 docstring「⚠ 不寫 ledger 沖銷」說明，改寫實作後語意

`modules/workflow/tests/test_material_request_repository.py`（+ ~150 行）
- `_dispatch_mr` / `_query_ledger` helper
- `test_add_return_writes_negative_ledger_entry`：dispatch 3 → 退 2 → ledger 多 1 筆
  `amount=-900, status=confirmed, source_item_id, locked_unit_cost, note`
- `test_add_return_uses_dispatch_locked_unit_cost_even_if_inventory_changed`：
  dispatch 後改 inventory.unit_cost 999.99 → 退料金額仍用 dispatch snapshot 450
- `test_add_return_summary_by_category_nets_correctly`：dispatch 3 confirm → 退 2 →
  `summary_by_category(CONFIRMED)` material = 1350 + (-900) = 450
- `test_add_return_no_matching_line_item_still_returns_stock`：item_b 不在 MR 內，
  退料 stock 加回但 ledger 不寫（防禦：不擋庫存）
- `test_add_return_atomic_rollback_on_failure`：patch `insert_in_session` raise →
  stock 沒變、ledger 沒新 entry（同 transaction rollback）

### 5.2 設計決策落實

- **新負 entry vs update 既有**：選新負 entry — 保留 audit trail，月報 SUM(amount)
  自動 net out。
- **status=CONFIRMED + confirmed_at=now**：退料是實際發生的負成本，避免「dangling
  estimated」影響月報 estimated 桶。
- **locked_unit_cost sourcing**：優先 dispatch entry 的 snapshot（會計一致性），
  fallback inventory.unit_cost（老 entries 向後相容），都查不到 → skip ledger 但
  stock 仍加回（防禦：不擋退料）。
- **同 session 反查 ledger**：用 `sess.execute(select(CostLedgerEntryORM))` 而不是
  call `cost_ledger_repository.find_for_mr_item()`（避免跨 session 不一致 + 簡化
  rollback 邊界 — 一切在同 transaction）。
- **多 line item 同 SKU+kind 取第一筆**：`scalars().first()` deterministic；實務
  build wizard 不會建這種重複 line，純防禦。
- **note 格式**：`退料沖銷 reason=surplus qty=2 new ret=a1b2c3d4`，給月報 / audit
  trail 一眼看出沖銷類型 + 反查 MaterialReturn。

### 5.3 Build / test 驗證

- `python -m pytest modules/workflow/tests/test_material_request_repository.py`
  → 25 passed in 1.46s（5 new + 20 existing）
- `python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/`
  → **517 passed + 1 xfailed + 3 failed**（3 failed 全是 pre-existing numpy 2.x
  pinned-value drift `test_monte_carlo_k13_seed_42` / `test_mc_percentiles_pinned`
  / `test_varfluct_year_1_pinned`，與 main baseline 完全一致 — zero regression；
  flaky `test_concurrent_dispatch_same_item_serialized_correctly` 今天通過）

### 5.4 Code review

Code-reviewer subagent 已啟動 async background，回報後若有 must-fix 第二輪
commit 修正。

---

## 6. 下次接手指南

### 已完成
- F1 主流程：退料同 transaction 寫 negative ledger entry，
  `summary_by_category(CONFIRMED)` 月報數字正確 net out
- 5 個 regression test 覆蓋 happy / locked snapshot / summary / 防禦 / atomic
- Zero regression（與 main baseline 同）

### 待辦（不阻塞）
- code-reviewer must-fix 如有 → 第二 commit 修
- F2-F6 follow-up 任選；本 F1 為 medium，剩 F2/F3/F5 為 0.5-1h 小修，F4 (1h
  refactor 4 routers) 也適合下次 daily session

### 建議下次 session 工作
1. **F4** `_FARM_REGISTRY` lazy singleton 抽 shared（1h，跨 4 routers refactor，
   價值/規模比好）
2. F2 SQL-side `func.count`（0.5h，純技術債清掃）
3. F3 `list_warehouses` repo method（0.5h，封裝補完）
4. WMOM-20260518-01 MR detail items SKU+name join（A6 follow-up，要動 backend
   `MaterialRequestItemResponse` + repo join）
5. M5 規劃：M4 既已 100%，下一步是 knowledge module + RAG plumbing；先讀
   `docs/product/ROADMAP.md` M5 章節定第一個 issue
