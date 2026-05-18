# 2026-05-18 WMOM-20260509-F1 — `add_return` 寫 ledger 沖銷

> **Issue**：WMOM-20260509-F1 — `MaterialRequestRepository.add_return` 退料時補寫 ledger 沖銷 entry
> **Branch**：`claude/nice-brown-VTEh0`（autonomous daily worker session 指定分支）
> **Goal**：修正退料後月報材料成本偏高（沒扣回退料金額）— A5 cost ledger 整合的 follow-up

---

## 1. 為什麼今天做這個

依 2026-05-18 Part C/D handoff doc 建議：「下次候選：A6 領料 frontend / A7 庫存 frontend / **F1-F6 follow-up**」。

A6 / A7 是 1 天的完整 frontend 任務（含多 component + service + hook + modal），對單一 autonomous session 風險過高；F1 是 0.5d 焦點 backend task，有清楚的 acceptance（測試 + summary_by_category 結果正確），剛好適合一個 session 收掉。

F1 還是個真的 correctness issue：demo 給客戶看月報時，退料後材料成本沒扣回，會被發現偏高（issue 描述）。

---

## 2. Scope 與設計決策

### 2.1 為什麼走「新 entry with negative amount」而不是 update 既有 entry

Issue 描述兩個選項：
- **A. 新 negative entry**：保留退料 audit trail，sum 自動扣回，會計做帳習慣
- **B. update 既有 entry 的 amount**：少一筆紀錄但失去退料紀錄；若退料後又再退料（cumulative）難處理

選 **A**。同 issue 描述「建議走『新 entry with negative amount』更乾淨」。

### 2.2 status 怎麼定 — match original 還是固定 CONFIRMED

兩個情境：
1. 退料發生在工單 finish 之前 → 原 entry 是 `ESTIMATED`（dispatch 寫入，still pending confirm）
2. 退料發生在工單 finish 之後 → 原 entry 是 `CONFIRMED`（hook 已 flip）

**選 match original status**：
- 情境 1：offset entry=ESTIMATED；`summary(status=CONFIRMED)` 不受影響（正確，因為原本也還沒進 confirmed sum）。日後工單 finish 時 hook 不會 confirm 這個 offset（因為 `confirm_entry` 走 `find_for_mr_item` 找 dispatch 那筆，offset 在 hook 邏輯外），但 offset 仍然會自然進 ESTIMATED sum
- 情境 2：offset entry=CONFIRMED；`summary(status=CONFIRMED)` 馬上扣回，**這正是 issue 要修的場景**
- 寫死 CONFIRMED 會在情境 1 的 ESTIMATED sum 漏扣（偏高）

### 2.3 locked_unit_cost 怎麼來

- 若原 entry 存在：用原 entry 的 `locked_unit_cost`（A5 review fix #1 — dispatch 當下快照），確保 estimated / confirmed / offset **同基礎**會計做帳
- 若原 entry 不存在（理論上不該發生，但防 dispatch 失敗 + status 進 DISPATCHED 的 corner case）：log warning + skip ledger write，**stock 仍加回**（不阻塞 returns 主功能）

### 2.4 為什麼把 ledger 寫進同一 session

`add_return` 既有 transaction 已 atomic 加回 stock + 寫 MaterialReturn。Ledger offset 必須跟它原子化 — 若 ledger 寫成功但 stock 回滾，會出現「成本沖銷但物料沒回」的失衡。直接在同 session 用 `select` 查 + `insert_in_session` 寫，pattern 與 `dispatch_request` 對稱。

### 2.5 actor_id / note

- `actor_id = returned_by`（誰退料就誰當 actor）
- `note = f"退料 reason={reason.value} qty={qty} kind={return_to_kind.value}"`（demo 看月報明細可直接認出退料來源）

### 2.6 farm_id 從哪來

mr_orm 已在 session 內 load 過（檢查 LookupError 那邊），複用 `mr_orm.farm_id` 不需再查。

---

## 3. 檔案異動（規劃）

### 3.1 修改

```
M modules/workflow/repository/material_request_repository.py
  - add_return: 加 ledger offset 寫入邏輯
  - docstring 更新（不再說「⚠ 不寫 ledger 沖銷」）
M ISSUES.md
  - WMOM-20260509-F1 status: open → done
M STATUS.yaml
  - issue_stats / next_milestone / last_updated
```

### 3.2 新增 tests

```
+ modules/workflow/tests/test_add_return_ledger_offset.py（或加到既有 test 檔）
  - test_add_return_writes_confirmed_ledger_offset_after_finish
  - test_add_return_writes_estimated_ledger_offset_before_finish
  - test_add_return_no_ledger_when_dispatch_never_happened（warning + 不 raise）
  - test_add_return_offset_uses_original_locked_unit_cost（避免重新查 inventory）
  - test_add_return_atomic_rollback_on_ledger_failure（stock 不應加回若 ledger 寫失敗）
```

---

## 4. TODO（implementation checklist）

- [x] Read existing code（material_request_repository / cost_ledger / cost_ledger_repository）
- [x] Branch + work-log
- [x] backend: add_return 加 ledger offset
- [x] backend tests（6 個新 regression test）
- [x] backend pytest run zero new regression（518 passed / 1 xfailed / 3 pre-existing numpy 漂移）
- [x] code-reviewer subagent 跑：採納 must-fix（2/2）+ should-fix（4/4）+ nice-to-have（1/2）
- [x] backend pytest re-run（review fix 後）525 passed / 1 xfailed / 3 pre-existing numpy 漂移
- [x] STATUS.yaml + ISSUES.md 更新
- [ ] commit + push + PR（hook 後續處理）

## 5. Code review 採納

Code-reviewer subagent 找 **2 must-fix + 4 should-fix + 2 nice-to-have**。

### Must-fix（2/2 全採納）

1. ✅ **CRITICAL** — `find_for_mr_item` 用 `scalar_one_or_none()`，本 fix 寫入 offset
   entry 後同 `(source_event_id, source_item_id)` 會有 ≥2 列 → 必炸
   `MultipleResultsFound`，wo_finish hook 無法 confirm ledger。Fix：
   `find_for_mr_item` 加 `CostLedgerEntryORM.amount > 0` filter，只回原 dispatch
   entry。同步加 regression test
   `test_find_for_mr_item_returns_dispatch_entry_after_return_not_offset`
2. ✅ `test_add_return_skips_ledger_offset_when_no_dispatch_entry` 測的不是聲稱的
   corner case（用 CREATED 狀態 bypass）。Fix：改成手動把 status 寫 DISPATCHED +
   手動扣 stock（模擬 dispatch atomic 半途失敗，stock 已扣但 ledger 沒寫成）

### Should-fix（4/4 全採納）

3. ✅ offset entry 的 `confirmed_at` 語意：dispatch entry 的 `confirmed_at` 是 wo
   finish 時刻；offset 的 `confirmed_at` 是退料時刻。Fix：在 add_return 加 inline
   comment 說明此 audit query 時的差異，`recorded_at` 仍是退料時刻不變
4. ✅ **Numeric precision**：`Numeric(15,2)` × `Numeric(12,4)` × `int qty` 可能寫
   入時被 SQLite 截斷造成 1 分錢漂移。Fix：`.quantize(Decimal("0.01"))` 明確 round
5. ✅ `mr_item_id_str` 在外層已守衛非 None 但內層 `UUID(...) if ... else None`
   冗餘。Fix：移除冗餘分支 + assert 增加可讀性與 mypy 型別收窄
6. ✅ 測試 helper `_get_ledger_entries` 直接用 `mr_repo._sessionmaker()` private
   API。Fix：改用 `ledger_repo.list_for_subject` + `ledger_repo.list` public API

### Nice-to-have（1/2 採納）

7. ⏭ 「同 MR 兩個 line item 指向同 item_id」場景測試 — 跳過（MR domain 層應禁止此情境，
   ledger 層保護成本高於價值；F2+ 可加 domain-level guard 補強）
8. ✅ Docstring「情境 1 退料前 finish → ESTIMATED 兩邊」措辭歧義。Fix：改寫為
   「退料發生在 wo finish **之前**」/「**之後**」明確語序

### Regression test 補強

- `test_find_for_mr_item_returns_dispatch_entry_after_return_not_offset`（防 Must-fix #1 倒退）

## 6. 收尾摘要

- backend：525 passed (= 519 baseline + 7 new F1 tests) / 1 xfailed / 3 pre-existing
  numpy 精度漂移
- E2E lifecycle test 6 個全 pass（dispatch + return + confirm 鏈路無 regression）
- 修了一條本來會在 demo 時被發現的 production bug（退料後 wo finish 無法 confirm）+
  原 issue 主訴（月報材料成本偏高）

下次候選：A6 / A7 frontend（1d 大任務，需單獨 session） / F2-F6 剩餘 follow-up（F2 0.5h
+ F3 0.5h 可同 session 收兩個）。
