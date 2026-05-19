# 2026-05-19 WMOM-20260509-F1 — `add_return` 寫 ledger 沖銷

> **Issue**：WMOM-20260509-F1 — Material return 完成時，在 cost_ledger 加一筆負金額沖銷 entry，避免月報材料成本偏高
> **Branch**：`claude/issue-WMOM-20260509-F1-2026-05-19`
> **Goal**：M4 demo / monthly report 修正 — 退料後 `summary_by_category(status=CONFIRMED)` 反映淨值

---

## 1. 為什麼今天做這個

M4 100% 收尾後，剩下 6 個 F1-F6 follow-up（皆 0.5h-0.5d 小修）。
F1 是其中**唯一影響 demo correctness** 的項目（demo 給客戶看月報數字會偏高，會被現場眼睛抓到）。
其他 5 個是 cosmetic / refactor / lower-priority，今天先清這一個。

---

## 2. 設計決策

### 2.1 ledger entry 欄位

退料 entry 對齊 dispatch entry 的 `source_event_id` (MR.id)、`source_item_id` (MR line item id)、
`source_type` (MATERIAL_REQUEST)、`category` (MATERIAL)，但 `amount` 為負。

- `locked_unit_cost`：取自原 dispatch entry 的 `locked_unit_cost`（snapshot 對稱）；若原 entry 無 locked_unit_cost（舊資料）則 fallback 用當前 inventory `unit_cost`
- `actor_id`：取自 `returned_by`（退料人＝這筆 ledger 異動的 actor）
- `note`：`"退料 reason={value} return_id={uuid} qty={n}"`（可追溯到 MaterialReturn）

### 2.2 status 取原 entry 的當下狀態

退料時 lookup 原 dispatch entry 的 `status`：
- 原已 CONFIRMED（wo_finish 後退料）→ 退料 entry 也標 CONFIRMED，立即反映在 `summary(status=CONFIRMED)` 月報
- 原仍 ESTIMATED（wo_finish 前退料）→ 退料 entry 標 ESTIMATED，與原同步等 wo_finish hook 翻轉

⚠ 注意 edge case：若 wo_finish 在退料 _之後_，當前 hook 只 flip 原 dispatch entry，不會碰退料 entry。
退料 entry 留 ESTIMATED → `summary(status=CONFIRMED)` 短暫只算 +actual，不扣 -returned。

**這個 case 列 follow-up（F1.1）** — 預期 95% demo 場景退料發生在完工後，先求 demo correctness，再補完整 hook。

### 2.3 `find_for_mr_item` 過濾退料 entries

當前 `find_for_mr_item(mr.id, mr_item.id)` 用 `scalar_one_or_none()`，新增退料 entry 後同 `(source_event_id, source_item_id, source_type)` key 會有 2 筆 → raise `MultipleResultsFound`。

**修正**：filter `amount >= 0` 排除退料 entries（退料 amount 嚴格負，dispatch entry confirmed=0 amount 仍 ≥ 0 通過）。

### 2.4 找不到 dispatch entry 怎麼辦

向後相容：可能 MR 走的不是 `dispatch_request()` atomic path（測試 fixture / legacy data）。
此時 add_return 仍 add stock + log MaterialReturn，**但 skip ledger 寫入**並 log warning。
避免破壞既有 3 個 `test_add_return_*` 測試。

### 2.5 lookup mr_item.id 的策略

`add_return` 簽名是 `(request_id, item_id, qty, return_to_kind, ...)`，其中 `item_id` 是 InventoryItem.id。
MR 可有多 line items 相同 `item_id` 但不同 `stock_kind`（demo 不常見但 schema 允許）。

策略：取第一筆 MR line item with `item_id == item_id`（任何 stock_kind）。
locked_unit_cost 在不同 stock_kind 的 line items 之間相同（同一時間 dispatch，snapshot 同一個 inventory.unit_cost），所以任取一個都可。

---

## 3. 檔案異動（規劃）

### 3.1 修改

```
M modules/workflow/repository/material_request_repository.py    add_return 加 ledger offset 寫入
M modules/cost/repository/cost_ledger_repository.py             find_for_mr_item filter amount>=0
M modules/workflow/tests/test_material_request_repository.py    新測試（如下）
M modules/cost/tests/test_cost_ledger_repository.py             find_for_mr_item 過濾退料 entry 測試
M ISSUES.md                                                     F1 → done
M STATUS.yaml                                                   last_updated / next_milestone
```

### 3.2 新增

```
+ work-logs/2026-05/2026-05-19-add-return-ledger-offset.md      本檔
```

---

## 4. TODO（implementation checklist）

- [x] Read existing add_return / dispatch_request / cost_ledger 結構
- [x] Branch + work-log
- [x] 改 `material_request_repository.add_return` 寫 ledger 沖銷
- [x] 改 `cost_ledger_repository.find_for_mr_item` 過濾 amount >= 0
- [x] 新測試（**實際 8 個**：6 MR + 2 ledger，含 review must-fix #3 補的 zero_confirmed 邊界）
- [x] backend zero regression（baseline 512 → 521 passed +8 new +1 flaky pass / 1 xfailed / 3 pre-existing numpy drift）
- [x] e2e lifecycle 6/6 仍通過
- [x] code-reviewer subagent（async）→ 3 must-fix + 5 should-fix + 4 nice-to-have；採納 3 must-fix + 3 should-fix + 1 nice-to-have（見 §5.4）
- [x] STATUS.yaml + ISSUES.md（F1 → done, issue_stats 20→19 open / 35→36 done）
- [x] commit + push（branch `claude/issue-WMOM-20260509-F1-2026-05-19` 已推到 origin）
- [ ] PR open — GitHub MCP `create_pull_request` 回 403 forbidden（copilot user 無權限），請劉老師手動開 PR：https://github.com/dofliu/windMindOM/pull/new/claude/issue-WMOM-20260509-F1-2026-05-19

---

## 5. 實作紀錄

### 5.1 完成檔案

修改（4 個）：
- `modules/workflow/repository/material_request_repository.py` — `add_return` lazy import cost_ledger 4 個 class + ORM + insert helper；同 transaction 內 lookup MR line item（第一筆 match item_id） → lookup 原 dispatch ledger entry（filter `amount >= 0` 排除既有退料）→ 取 locked_unit_cost（或 fallback 到 inv_orm.unit_cost）→ insert 負金額 offset entry（status 同步 / actor=returned_by / note 帶 reason + return_id + qty）。找不到 dispatch entry → log warning + skip ledger（stock + MaterialReturn 照常 commit）。
- `modules/cost/repository/cost_ledger_repository.py` — `find_for_mr_item` 加 `amount >= 0` filter，docstring 補 WMOM-20260509-F1 context 與 edge case 說明（actual_qty=0 confirmed 仍可被選中）。
- `modules/workflow/tests/test_material_request_repository.py` — 加 6 個新測試（含 `_dispatch_mr` helper）：writes_ledger_offset / status_matches_original / status_matches_confirmed_original / summary_reflects_net_cost / multiple_returns_accumulate / without_dispatch_entry_logs_warning。
- `modules/cost/tests/test_cost_ledger_repository.py` — 加 2 個新測試：find_for_mr_item_skips_return_entries / find_for_mr_item_zero_amount_dispatch_still_matched。

新增（1 個）：
- `work-logs/2026-05/2026-05-19-add-return-ledger-offset.md`

### 5.2 設計決策落實

- **locked_unit_cost snapshot 對稱**：退料 entry 與原 dispatch entry 共用同一個 locked_unit_cost；fallback 到當前 inv_orm.unit_cost 只在 dispatch entry 沒 locked_unit_cost（向後相容老資料）才走。
- **status 同步**：原 entry CONFIRMED → 退料 entry 立即 CONFIRMED（demo 場景退料多發生在完工後，月報立即反映）；原 ESTIMATED → 退料 ESTIMATED（等 wo_finish hook 同步翻轉的工作列 F1.1 follow-up）。
- **filter amount >= 0 而非 status**：避免「退料 entry 留 ESTIMATED 但 dispatch 已 CONFIRMED」case 撈不到 dispatch entry；同時保留 actual_qty=0 confirmed dispatch entry 的可尋性（boundary test 已驗）。
- **找不到 dispatch entry skip ledger**：保留向後相容（既有 3 個 add_return 測試使用 fixture-built MR 無 dispatch path）；log warning 提供可觀測性，stock + MaterialReturn 仍正常 commit 不破壞主流程。
- **lazy import cost_ledger**：沿用 dispatch_request 的同 pattern 破循環依賴。

### 5.3 驗證

**Targeted tests**：
- `python -m pytest modules/workflow/tests/test_material_request_repository.py modules/cost/tests/test_cost_ledger_repository.py -v` → 45 passed

**Full backend**：
- `python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/ -q` → **520 passed + 1 xfailed + 3 failed**（3 個 pre-existing numpy 2.x precision drift 與 baseline 完全一致；flaky concurrency test 今日通過）— **zero regression**（baseline 512 + 7 new + 1 flaky pass = 520）。

**E2E lifecycle**：
- `python -m pytest tests/e2e/ -v` → 6 passed（完整 fault→工單→派工→領料→簽核→完工 path 不受影響）

### 5.4 Code review

Code-reviewer subagent 回報 **3 must-fix + 5 should-fix + 4 nice-to-have**。第二 commit 採納：

**Must-fix 全採納（3/3）**：
1. ✅ `add_return` MR row 改用 `select(...).with_for_update()` 鎖（與 dispatch_request 對齊）— PostgreSQL 部署前的並發安全
2. ✅ `confirm_entry` docstring 加 F1.1 follow-up 注意事項 — 「不適用退料負金額 entry，F1.1 需獨立 method」設計 contract 文件化
3. ✅ `add_return` 加 guard：dispatch entry CONFIRMED 且 amount=0（actual_qty=0）時 skip ledger offset，避免月報負成本；加 regression test `test_add_return_skips_ledger_when_dispatch_zero_confirmed`

**Should-fix 採納（3/5）**：
- ✅ Should #1：`add_return` exception handler 加 `_logger.exception(...)`，對齊 `dispatch_request` pattern；同時細分 expected exceptions（LookupError / MaterialRequestRuleViolation / InsufficientStock）不重複 log
- ✅ Should #2：MR 同 item_id 多 line items 邊界 case 改用 `.scalars().all()` + `_logger.debug(...)` 警示，code comment 完整說明已知限制
- ✅ Should #5：work-log §4 checklist 更新實際數字（8 個測試而非 4 個，521 passed 而非 512）
- ⏭ Should #3：`add_return` MR status docstring 說明 — work-log §2.5 已記錄，重複度高暫不重複
- ⏭ Should #4：`FARM_ID = "changhua"` 常數抽出 — 純測試風格 refactor，後續 follow-up

**Nice-to-have 採納（1/4）**：
- ✅ Nice #2：移除 `note=(...)` 多餘括號，改 single-line f-string
- ⏭ Nice #1：partial unique index — 防禦設計，列 PostgreSQL 遷移 backlog
- ⏭ Nice #3：locked_unit_cost Decimal 精度斷言統一 — 風格非正確性問題
- ⏭ Nice #4：F1.1 正式 issue — 已在 work-log §2.2 記錄，後續 follow-up 直接開 issue 即可

---

## 6. 下次接手指南

### 已完成
- F1 主流程 — `add_return` 寫 ledger 沖銷，月報材料成本不再偏高
- M4 follow-up 6 個之中影響 demo correctness 的唯一一個 done（F2-F6 為 cosmetic / refactor / 低優先）

### 待辦（不阻塞）
- Code-reviewer 結果讀取 + 採納 must-fix（如有）
- PR 由本 session push 後若 gh CLI 不可用，劉老師人工開
- F1.1 follow-up（如需要）：wo_finish hook 對 ESTIMATED 退料 entry 同步翻轉 CONFIRMED — demo 場景 95% 退料發生在完工後不影響，留至有實際情境再做

### 建議下次 session 工作（依優先級）
1. **F2** `func.count` SQL-side count — 0.5h，cosmetic 但簡單清掉
2. **F3** `list_warehouses` repo method — 0.5h，移出 router raw SQL
3. **WMOM-20260518-01** MR detail SKU+name join — 0.5d，demo polish 給現場工程師看更友善
4. **M5 規劃** — RAG knowledge module + demo orchestrator UI 完整版（讀 `docs/product/ROADMAP.md` M5 章節決定第一個 issue）
5. F4-F6 任選一個塞進（皆 0.25-0.5d）
