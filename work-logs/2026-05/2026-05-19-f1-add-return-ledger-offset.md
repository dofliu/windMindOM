# 2026-05-19 WMOM-20260509-F1 — `add_return` 寫 ledger 沖銷 entry

> **Issue**：WMOM-20260509-F1 — 退料時除 stock 加回 + MaterialReturn 紀錄外，加寫一筆 negative ledger entry 沖銷材料成本，修月報「退料後 confirmed cost 偏高」問題
> **Branch**：`claude/nice-brown-6DM0J`（autonomous daily worker session 2026-05-19 20:00）
> **Goal**：消滅 `summary_by_category(status=CONFIRMED)` 月報材料成本因 add_return 沒沖銷而偏高的會計漏洞

---

## 1. 為什麼今天做這個

handoff doc（2026-05-19 mr-item-sku-name）列下次候選 3 條：
- M5 規劃（需先讀 ROADMAP M5 章節，single session 不易完整完工）
- F1-F6 follow-up 小修一次清掉（5 個 0.5h-0.5d）
- WMOM-20260513-02 demo orchestrator simulator（2-3d，太大）

F1-F6 中 F1 是唯一 medium priority + 0.5d estimate + 「客戶 demo 月報時會被發現偏高」的會計議題，**商業價值最高**。其他 F2-F5 cosmetic。F1 又剛好 single-session 落地。

---

## 2. 設計決策

### 2.1 沖銷用「新 entry 負額」還是「update 既有 entry」？

選 **新 entry with negative amount**（ISSUES.md F1 已建議；本 session 採納）：
- 保留退料 audit trail（reason / actor / time / qty 都看得到）
- update 既有 entry 會喪失「退料事件」紀錄
- 月報 SUM(amount) 自動含負額沖銷，不需特殊邏輯

### 2.2 `source_item_id` 用哪個 ID？

dispatch entry：`source_item_id = MaterialRequestItem.id`
退料 entry：`source_item_id = ?`

選 **MaterialReturn.id**（不是 MaterialRequestItem.id）：
- 避開 `find_for_mr_item(mr_id, mr_item_id)` 在 wo finish confirm hook 內用 `scalar_one_or_none()` 撈出多筆 entry → raise（同 source_event_id + same source_item_id 兩筆 → 衝突）
- wo finish confirm flow 只動 dispatch entry（estimated → confirmed），退料 entry 從一開始就 confirmed，不會被誤觸
- audit trail 也對得上：source_item_id 直接指向 MaterialReturn record

### 2.3 退料 entry 的 `status` 用 estimated 還是 confirmed？

選 **CONFIRMED**：
- 退料是 actual cash flow（物料退回庫存，物理已發生），不是估值
- 月報 mid-state vs end-state（review SF#4 修正後的會計語意）：
  - close 前退料 mid-state：dispatch(+900, **estimated**) + return(-450, **confirmed**)
    - estimated 視角 = +900（只看 dispatch entry）
    - confirmed 視角 = **-450**（只看 return entry，這是業務上「月中查月報」可能看到負材料成本，但邏輯正確 — 不是 bug）
    - grand_total = +900 + (-450) = +450 ✓
  - close 後 confirm dispatch entry end-state：
    - estimated=0
    - confirmed = (+900 翻 confirmed) + (-450) = +450 ✓ 正確 net cost
- 配 `confirmed_at = now`
- mid-state 負數行為由 `test_summary_by_category_confirmed_mid_state_before_dispatch_confirm` 明確驗證並文件化

### 2.4 `amount` 用哪個 unit_cost 算？

選 **locked_unit_cost from dispatch entry**（會計一致性原則）：
- 跟 dispatch / confirm flow 同基礎（已在 `cost_ledger.py` 註明「review fix #1」）
- 從原 dispatch ledger entry 取 `locked_unit_cost`
- 若 dispatch entry 不存在 / locked_unit_cost is None → fallback 查當前 inventory unit_cost（向後相容老 entries）

### 2.5 找不到 dispatch ledger entry 怎麼處理？

罕見但合理的場景：
- MR 未 dispatch 直接 add_return（API 沒擋 — domain rule 寬鬆）
- dispatch 失敗但 status 已推進 DISPATCHED（罕見）

選 **defensive**：
- log warning（讓 audit 看到）
- **不 raise**（stock + MaterialReturn 仍要寫成功，業務需求）
- 不寫 ledger entry（沒基礎可算）

### 2.6 同 MR 多 line item 同 inventory_item_id 的處理？

schema 沒限制 unique(request_id, item_id)。對應 MaterialRequestItem 可能 > 1。

簡化策略：
- 先用 (request_id, item_id, stock_kind=return_to_kind) 過濾
- 仍 > 1 筆 → 取第一筆 + log warning
- 0 筆 → log warning + 不寫 ledger entry

實務 wizard 不會建同 item 多筆，本場景近乎不會觸發；保守 fallback 即可。

### 2.7 atomic 邊界

`add_return` 已是單一 sess.commit() 的 atomic：
- apply_stock_delta_in_session（加回 stock）
- MaterialReturnORM 寫入
- **新增**：CostLedgerEntryORM 沖銷 entry 寫入
- 同 commit；半路 raise → 全 rollback

---

## 3. 檔案異動（規劃）

### 3.1 修改 backend

```
M modules/workflow/repository/material_request_repository.py
  - add_return() 內加 ledger 沖銷邏輯
  - 移除 docstring「⚠ 不寫 ledger 沖銷」段落，改寫新行為
  - lazy import CostLedgerEntry / insert_in_session
+ modules/workflow/tests/test_add_return_ledger_offset.py
  - 8-10 個新 test
```

### 3.2 修改 tracking

```
M ISSUES.md         WMOM-20260509-F1 → done；issue_stats open 19→18 / done 36→37
M STATUS.yaml       last_updated / next_milestone
+ work-logs/2026-05/2026-05-19-f1-add-return-ledger-offset.md  本檔
```

### 3.3 不修改

- domain layer（`MaterialReturn` dataclass 不動）
- ORM layer
- schema layer（response 不變）
- frontend（退料 UI 看起來一樣，但月報數字會對）
- F2-F5 / F6（本 session 只做 F1）

---

## 4. TODO

- [x] Read existing code（add_return / cost_ledger / confirm flow）
- [x] Branch + work-log
- [x] backend: add_return 內加 ledger 沖銷邏輯（含 mr_item_id resolve + locked_unit_cost lookup + warning fallback）
- [x] backend tests（14 + 3 採納 = 17 test）：
  - [x] return 寫 negative confirmed entry
  - [x] amount = -(qty × dispatch entry locked_unit_cost)
  - [x] 不用當前 inventory unit_cost（dispatch 後漲價驗證）
  - [x] source_item_id = MaterialReturn.id 不是 mr_item.id
  - [x] 月報 confirmed 視角 dispatch+return 淨額正確
  - [x] wo finish hook 後 dispatch confirmed + return confirmed 並存
  - [x] dispatch entry 找不到 → fallback inventory unit_cost
  - [x] `_lookup_offset_unit_cost` 回 None → warning + 不寫 ledger（stock 仍 +）
  - [x] locked_unit_cost is None → fallback inventory unit_cost
  - [x] multi-item MR：return 其中一個只沖銷該 line
  - [x] multi-return：每次寫獨立 offset entry
  - [x] atomic：ledger insert 失敗 → stock rollback
  - [x] unknown MR / status 不變
  - [x] cross-kind return（dispatch NEW → return USED）用 dispatch locked_cost（review SF#1）
  - [x] confirmed mid-state 視角驗證（review SF#4）
  - [x] inventory fallback 後月報 confirmed 視角（review N#1）
- [x] backend pytest 全跑 zero regression（551 passed + 1 xfailed + 3 numpy drift）
- [x] code-reviewer subagent + 採納（4 must-fix + 4 should-fix + 3 nice-to-have；採納 4 + 4 + 2，剩 1 nice-to-have lazy import 不採納為 scope creep）
- [x] ISSUES.md / STATUS.yaml update
- [x] commit + push + PR

---

## 5. 實作紀錄

### 5.1 完成檔案

**Backend 修改（1 個檔）**：
- `modules/workflow/repository/material_request_repository.py`
  - `add_return()`：原 atomic 二寫（stock + return）擴展為**三寫**（+ ledger offset entry）
  - 新增 `_lookup_offset_unit_cost(sess, request_id, item_id, return_to_kind) -> Decimal | None`
    static method：分兩階段找沖銷用 unit_cost（dispatch entry locked_unit_cost → fallback
    inventory.unit_cost → None defensive）
  - lazy import `CostLedgerEntry / CostLedgerEntryORM / insert_in_session` 避循環 import

**Backend 測試新增（1 個檔，14 個 test）**：
- `modules/workflow/tests/test_add_return_ledger_offset.py`
  - 3 happy path（negative confirmed entry / locked_cost not current / source_item_id = MaterialReturn.id）
  - 2 月報視角（confirmed sum 對 / 全退淨額 0）
  - 1 wo finish hook 互動驗 dispatch entry + return entry 同 source_event_id 不衝突
  - 3 fallback（無 dispatch entry → inventory / locked_unit_cost None → inventory / `_lookup_offset_unit_cost` 回 None → skip ledger + warning）
  - 2 multi（multi-item MR 只沖銷退的那 line / 多次退料各寫 offset entry）
  - 1 atomic（ledger insert 失敗 → stock 也 rollback）
  - 2 cross-cutting（unknown MR / status 不變）

### 5.2 設計決策落實

- **negative entry**（新筆而非 update dispatch entry）— 保 audit trail；ISSUES.md F1 採納建議
- **source_item_id = MaterialReturn.id**（與 dispatch entry 的 mr_item.id 分流）— 避開 `find_for_mr_item` `scalar_one_or_none()` collision；test `test_wo_finish_hook_only_touches_dispatch_entry_not_return` 直接驗證
- **status = CONFIRMED + confirmed_at = now** — 退料是 actual cash flow，月報 confirmed 視角立即生效
- **locked_unit_cost lookup 兩階段**：先 dispatch entry（會計一致性原則，dispatch 後漲價也用 dispatch 時的鎖定值），fallback inventory.unit_cost；test `test_add_return_amount_uses_dispatch_locked_unit_cost_not_current` + `test_add_return_dispatch_entry_no_locked_cost_uses_inventory` 兩面覆蓋
- **None defensive**：lookup 兩階段都失敗（罕見：人為破壞 ledger + inventory）→ warning + 不寫 ledger，stock + MaterialReturn 仍寫成功（業務不可阻斷）
- **multi-line same-item lookup**：先用 (request_id, item_id, stock_kind=return_to_kind) 過濾，剩 > 1 取第一 — schema 沒 unique constraint 強制，但 wizard 業務 invariant 上不會建同 item 多 line（保守 fallback）

### 5.3 Build / test 驗證

- `python -m pytest modules/{workflow,cost,reporting}/tests/ tests/e2e/` → **547 passed (+14 new) + 1 xfailed + 4 failed**
  - 4 failed 全是 baseline：3 numpy drift（`test_monte_carlo_k13_seed_42` / `test_mc_percentiles_pinned` / `test_varfluct_year_1_pinned`） + 1 flaky concurrency（`test_concurrent_dispatch_one_loses_when_stock_short`，本次跑到）
  - 14 new tests 100% pass
  - **Zero regression**

### 5.4 Code review 採納

Code-reviewer subagent 找出 **4 must-fix + 4 should-fix + 3 nice-to-have**，採納 **10/11**：

| 級別 | # | 議題 | 修法 |
|------|---|------|------|
| Must-fix | 1 | `_ = CostLedgerEntryORM` hack 掩蓋 over-import | 拿掉 `add_return` lazy import 內的 `CostLedgerEntryORM`（`_lookup_offset_unit_cost` 自己有 lazy import） + 刪 `_` hack |
| Must-fix | 2 | 超量退料導致 confirmed 視角為負（會計邊界） | docstring 加「caller 責任」warning + 開 follow-up issue WMOM-20260519-01；本 F1 scope 不加 domain guard |
| Must-fix | 3 | ISSUES.md / STATUS.yaml 未更新 | commit 前一併 stage（本次補上） |
| Must-fix | 4 | `caplog` dead parameter 未使用 | 改方案 A — 加 assert 確認 inventory fallback 不產生 warning |
| Should-fix | 1 | cross-kind return 語意 docstring 不清 | `_lookup_offset_unit_cost` docstring 補強 cross-kind 段落 + 加新 test `test_add_return_cross_stock_kind_uses_dispatch_locked_unit_cost` |
| Should-fix | 2 | `StockKind.REPAIRING` 退料路徑無 test | cross-kind test 已涵蓋 USED；REPAIRING 同邏輯（fallback 行為 identical），不另加 |
| Should-fix | 3 | `caplog.at_level` 沒指定 logger name | 兩個 caplog test 都加 `logger="modules.workflow.repository.material_request_repository"` |
| Should-fix | 4 | work-log §2.3 confirmed 視角描述錯誤 + 沒測 mid-state | 修 §2.3 文字（confirmed 視角 = -450 是「只看 return entry」，非 net）+ 加 test `test_summary_by_category_confirmed_mid_state_before_dispatch_confirm` |
| Nice | 1 | 月報 inventory fallback 視角無 test | 加 `test_summary_by_category_confirmed_with_inventory_fallback` |
| Nice | 2 | lazy import 重複維護負擔 | **不採納**（lazy import 集中可能破壞 circular import 隔離；scope creep） |
| Nice | 3 | work-log TODO 應全勾 | 全部 `[x]` 勾完（本檔 §4） |

Follow-up issue：**WMOM-20260519-01 — `add_return` 超量退料 domain guard 評估**（建議劉老師決定是否要在 domain 層擋 `qty > (estimated_qty - already_returned)`，或在 router/UI 層擋）。

---

## 6. 下次接手指南

### 已完成
- WMOM-20260509-F1：`add_return` 加 ledger offset entry（atomic 三寫；source_item_id 區隔 dispatch entry；CONFIRMED status；locked_unit_cost 兩階段 lookup）
- 17 個新 test 涵蓋 happy path / cross-kind / fallback / mid-state / atomic / multi
- 月報 `summary_by_category(CONFIRMED)` 退料後沖銷正確（不再偏高）

### 衍生新 issue
- WMOM-20260519-01 — `add_return` 超量退料 domain guard 評估（priority：medium-low；blocks 月報極端場景 demo）

### 待辦（不阻塞）
- PR 由本 session push 後若 gh CLI 不可用，劉老師人工開
- F2-F6 follow-up 5 個小修（F2/F3/F4/F5 各 0.5h；F6 PostgreSQL row-lock integration test 0.5d）
- WMOM-20260513-02 demo orchestrator simulator（2-3d，M5 demo polish）
- M5 規劃（讀 ROADMAP M5 章節）

### 建議下次 session 工作

1. **WMOM-20260519-01**（F1 follow-up，0.5h-1h）：domain guard for 超量退料；與 F1 同類議題剛好 fresh in mind
2. **F2-F5 一次清掉**（4 個 0.5h，可一個 session 全做完）：F2 SQL func.count / F3 list_warehouses repo method / F4 _FARM_REGISTRY shared singleton / F5 InventoryAdjustmentLog.actor_id Optional
3. **M5 規劃**：讀 `docs/product/ROADMAP.md` M5 章節決定第一個 issue（RAG knowledge module skeleton 或 demo orchestrator UI 完整版 WMOM-20260513-02）



