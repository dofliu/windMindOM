# 2026-05-19 WMOM-20260509-F1 — `add_return` 寫 ledger 沖銷 entry

> **Issue**：WMOM-20260509-F1 — Material return 不寫 ledger 沖銷，月報材料成本偏高
> **Branch**：`claude/nice-brown-00sSk`（autonomous daily worker session 指派）
> **Goal**：補上退料時的 cost ledger 負向 entry，讓 `summary_by_category(status=CONFIRMED)` 正確反映退料後的淨材料成本

---

## 1. 為什麼今天做這個

2026-05-19 上午（前一段 session）剛完成 WMOM-20260518-01（MR detail items 加 SKU/name/unit）；
handoff doc 列今日候選 3 條：
- M5 規劃（最大，但 single-session 不易完成）
- WMOM-20260513-02 demo orchestrator simulator 接合（2-3d 跨多 session）
- **F1-F6 follow-up**（5 個 0.5h-0.5d 小修，可一個 session 全做完）

F1 是 follow-up 中**商業價值最高**的：客戶 demo 看月報時，退料後材料成本沒沖銷掉是會被發現的會計錯誤；
其他 F2-F6 多是 cosmetic refactor / 低資料量無感優化。

本 session 鎖定 F1 完整做完（單一 issue 收尾），不貪多 F2-F6（避免 scope creep）。

---

## 2. 設計決策

### 2.1 沖銷走「新 entry with negative amount」還是「update 既有 entry」？

選 **新 entry**（issue description 已建議）：
- 保留退料 audit trail（時間軸 / 原因 / 數量 / 操作者皆獨立記錄）
- 既有 `dispatch` entry 不被動，confirm flow 邏輯不需改
- 月報加總時 SQL `SUM(amount)` 自動沖銷（不需特別處理）

### 2.2 `locked_unit_cost` 從哪拿？

選項：
- A. 從現任 `inventory_item.unit_cost` 拿（dispatch 後若 unit_cost 改動會不一致）
- B. **從原 dispatch ledger entry 拿 locked_unit_cost**（保證 accounting consistency）

選 **B**。理由與 review fix #1 同源：dispatch 當下的 locked_unit_cost 才是會計做帳基礎；
退料沖銷必須對得上同一基礎，否則會出現「dispatch 時 +900、退料時 -500」這種不平衡。

### 2.3 怎麼找對應 dispatch ledger entry？

`add_return` 帶 `(request_id, item_id)`，其中 `item_id` 是 **inventory item id**，
而 ledger entry 的 `source_item_id` 是 **MR line item id**。所以需兩步：

1. 用 `(request_id, inventory_item_id)` 查 `MaterialRequestItemORM` → 拿 line_item.id
2. 用 `(source_event_id=request_id, source_item_id=line_item.id, source_type=MATERIAL_REQUEST)`
   查 `CostLedgerEntryORM` → 拿 locked_unit_cost

注意：理論上同一張 MR 同一個 inventory item 不應重覆出現多次 line（前端 wizard 不允許），
但 schema 沒強制 unique constraint。**若有多 line，取第一個 match**（記錄 warning log）。

### 2.4 找不到 dispatch ledger entry 時怎麼辦？

可能情境：
- 該料件根本沒走過 dispatch（罕見 — 通常 add_return 前必經 dispatch；但 schema 沒擋）
- ledger entry 被外部清理（DB 維護）

選擇：**log warning + skip ledger 沖銷**（不 raise）。理由：
- 退料本身的 stock add-back 是 user 直接操作的物理事實，不該因 audit 缺失就 fail
- 多寫個 ledger entry 不是退料的必要結果，只是 accounting nice-to-have

### 2.5 沖銷 entry 的 `status`？

選 **CONFIRMED**。理由：
- 退料是「**definitive event**」（user 物理操作，不是估計）
- Issue 明確指出 `summary_by_category(status=CONFIRMED)` 必須包含沖銷
- 與 dispatch entry（ESTIMATED → 在 WO finish 翻成 CONFIRMED）不衝突；
  finish hook 只 flip 自己的 entry，不會碰新加的 offset entry

### 2.6 transaction boundary

退料三件事（stock add-back / MaterialReturn / ledger offset）必須在**同一 session**：
- 若 ledger insert 失敗 → 整個 transaction rollback → stock 不變、return 不留
- 既有 add_return 已是 atomic（同 session commit），加上 ledger insert 進同 session 即可

---

## 3. 檔案異動（規劃）

### 3.1 修改 backend

```
M modules/workflow/repository/material_request_repository.py
  - add_return 加 ledger 沖銷 (lazy import cost_ledger 同 dispatch_request)
  - 更新 docstring 與檔頭模組註解
```

### 3.2 修改 tests

```
+ modules/workflow/tests/test_add_return_ledger_offset.py
  - test_add_return_writes_negative_ledger_offset (happy path)
  - test_add_return_offset_uses_dispatch_locked_unit_cost (price drift 不影響)
  - test_add_return_partial_return_offsets_partial_amount
  - test_add_return_multiple_returns_each_writes_offset
  - test_add_return_summary_after_return_excludes_amount (月報加總)
  - test_add_return_without_dispatch_entry_logs_skip (defensive edge)
  - test_add_return_atomic_rollback_on_ledger_failure (atomicity)
```

### 3.3 修改 tracking

```
M ISSUES.md           WMOM-20260509-F1 → done
M STATUS.yaml         last_updated / next_milestone
+ work-logs/2026-05/2026-05-19-add-return-ledger-offset.md  本檔
```

### 3.4 不修改

- domain layer（`MaterialReturn` 不加屬性）
- router（API 簽章 / 回應不變）
- frontend（沒 user-visible 變動 — 等月報重算後客戶才看得到差異）

---

## 4. TODO

- [x] Read existing code（add_return / dispatch_request / cost_ledger / lifecycle tests）
- [x] Branch + work-log
- [x] backend `add_return` 加 ledger 沖銷邏輯（lazy import + 同 session insert）
- [x] backend `_resolve_return_ledger_offset` helper（line item 查找 + locked_cost lookup）
- [x] backend module docstring + add_return docstring 更新
- [x] backend test 新增 7 cases
- [x] backend pytest zero regression（modules/workflow + cost + reporting + e2e）
- [x] code-reviewer subagent + 採納 must-fix / should-fix
- [x] ISSUES.md / STATUS.yaml update
- [ ] commit + push + PR

---

## 5. 實作紀錄

### 5.1 完成檔案

**Backend 修改（1 個檔）：**
- `modules/workflow/repository/material_request_repository.py`
  - module docstring §5 改為「同 transaction 內加回 stock + **寫 ledger 沖銷**」
  - `add_return` docstring 改為「同 transaction 加回 stock + ledger 負向 entry（找不到 dispatch entry 時 log warning + skip）」
  - 加 private helper `_resolve_dispatch_ledger_meta(sess, request_id, inventory_item_id) -> tuple[UUID | None, Decimal | None]`
    - 用 inventory item id 找 MR line item ORM → 拿 line_item.id
    - 用 line item id + source_event_id 找 dispatch ledger entry → 拿 locked_unit_cost
    - 多 line 取第一筆 + log warning；找不到 → return (None, None) + log warning
  - `add_return` 在 stock add-back + MaterialReturn add 後加：
    - `mr_item_id, locked_cost = self._resolve_dispatch_ledger_meta(...)`
    - 若 locked_cost is not None：`insert_in_session(sess, CostLedgerEntry(amount=-qty*locked_cost, status=CONFIRMED, ...))`

**Backend 測試新增（1 個檔，7 test）：**
- `modules/workflow/tests/test_add_return_ledger_offset.py`

### 5.2 設計決策落實

- 新 ledger entry 而非 update 既有 → audit trail 完整
- locked_unit_cost 從 dispatch entry 拿 → accounting consistency
- 找不到 dispatch entry → log warning + skip（不阻 stock add-back）
- status=CONFIRMED → 月報 `status=CONFIRMED` 查得到
- 同 session atomic → 任一步失敗整段 rollback

### 5.3 Build / test 驗證

- 待補

### 5.4 Code review 採納

- 待補

---

## 6. 下次接手指南

### 已完成
- WMOM-20260509-F1：material return 寫 ledger 沖銷 entry，月報 CONFIRMED 加總自動扣回退料金額

### 待辦（不阻塞）
- F2-F6 follow-up 4 個小修（皆 0.5h-0.5d）
- WMOM-20260513-02 demo orchestrator simulator 接合（M5 demo 視覺化用）

### 建議下次 session 工作
1. **F2 `func.count`** — 10 分鐘可清掉（資料量小無感但 code quality 加分）
2. **F4 `_FARM_REGISTRY` shared singleton** — 1h refactor（4 個 router 去重）
3. **M5 規劃** — 讀 ROADMAP M5 章節決定第一個 issue
