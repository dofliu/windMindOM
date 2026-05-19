# 2026-05-19 WMOM-20260519-01 — `add_return` 超量退料 domain guard

> **Issue**：WMOM-20260519-01 — `add_return` 超量退料 domain guard 評估（F1 follow-up）
> **Branch**：`claude/nice-brown-ll4vQ`（autonomous daily worker session 2026-05-19 20:00）
> **Goal**：擋住「退料 qty > dispatched − actual_consumed − already_returned」的 illegal call；
> 修補 WMOM-20260509-F1 完成後留下的會計邊界（confirmed 視角可能為負值）

---

## 1. 為什麼今天做這個

handoff doc（2026-05-19 F1 wrap-up）列下次候選 3 條：
1. **WMOM-20260519-01**（F1 follow-up，0.5h-1h）：domain guard for 超量退料；與 F1 同類議題剛好 fresh in mind
2. F2-F5 一次清掉（4 個 0.5h）
3. M5 規劃 / WMOM-20260513-02

挑 WMOM-20260519-01：
- 直接延伸昨日 F1 留下的會計邊界，**對 demo 月報數字最直接影響**
- single-session 可完工
- 與 F1 共享 mental model（add_return + cost ledger 互動），不用 context switch

---

## 2. 設計決策

### 2.1 Guard 放在哪一層？（issue 提的 4 個方案）

| 方案 | 取捨 | 採用？ |
|------|------|--------|
| A. Domain 層 `MaterialRequest` 加 method | 純 domain invariant；repo / router / 任何 caller 共享 | **採用** |
| B. Repository 層 (`add_return`) 加查詢 | 必要 — already_returned 需查 DB | **採用**（dom + repo 合作） |
| C. Router 層 | 422 user-facing；但繞過 router（如其他 service）的呼叫漏掉 | 不採用（不夠 defensive） |
| D. UI 層 | 不防 API 直接呼叫；只是輔助 | 不採用（但 UX 仍應提示） |

**選 A+B**：domain 提供 pure-method 算 upper bound（不碰 DB），repository 補 `already_returned` 並做最終比較 + raise。

### 2.2 Domain invariant 公式

```
max_returnable_upper_bound(item_id)
    = max(0, dispatched_total - consumed_total)

dispatched_total = Σ estimated_qty  for items where item_id matches
consumed_total   = Σ actual_qty     for items where item_id matches AND actual_qty is not None

guard: existing_returns_qty + new_qty <= max_returnable_upper_bound
```

**Rationale**：
- `estimated_qty` 是 dispatch 時實際扣 stock 的量（dispatch_request 雙寫核心）
- `actual_qty` 是 receive 時填的「實際領用 / 已消耗」（wo finish hook 用它算 confirmed 成本）
- 工人現有未消耗物料 = dispatched − consumed
- 退料上限就是這個未消耗量；多次退料用 cumulative 比較

**Cross-kind / multi-line 處理**：同一個 `item_id`（InventoryItem）可能在 MR 內被多行（不同 stock_kind）共享；
guard 用 `item_id` aggregate 不 group by stock_kind — 物理上「同一個料件」的進出總帳。

### 2.3 為什麼不只用 `estimated_qty`（不看 `actual_qty`）？

只用 `estimated_qty` 會漏掉 F1 描述的場景：
- dispatched 2 件、receive actual_qty=1（worker 說只用 1）
- 若不看 actual_qty → max 上限 = 2 件，return 2 件不被擋 → confirmed = 300 − 600 = −300 ❌

加 actual_qty 後：
- max 上限 = 2 − 1 = 1，return 2 件被擋 ✓

### 2.4 為什麼不只用 `dispatched`（不看 `estimated`）？

DB schema 沒有 `dispatched_qty` 欄位 — dispatch 是用 `estimated_qty` 扣 stock（看 `dispatch_request`），所以 dispatched = estimated 在當前資料模型內等價。未來如果支援「partial dispatch」需重評。

### 2.5 Already-returned 怎麼算？

`SUM(MaterialReturnORM.qty) WHERE request_id=X AND item_id=Y`，**不 group by stock_kind**：
- 跨 stock_kind 退料（dispatch NEW → return USED）仍視為「同一個物理料件的歸還」
- 與 F1 `_lookup_offset_unit_cost` 找 dispatch entry 的策略一致（item_id 為 key，stock_kind 為輔）

### 2.6 Guard fail 時用哪個 exception？

`MaterialRequestRuleViolation`（既有；router 已 catch → 422）。
比 `ValueError` 更語意化 + 對 API user 是清楚的 422 + 給對的 detail 字串。

### 2.7 Domain method 命名

`compute_returnable_upper_bound(item_id) -> int`：
- 直接表達「最高可退多少（累計）」
- 不混合 `already_returned`（caller 自己減）→ pure function 易測
- 避免 `max_returnable` 字眼歧義（看起來像「現在還可退」而不是「累計上限」）

### 2.8 Scope 邊界（**不**做）

- **不**加 MR status guard（DRAFT 不可退 / DISPATCHED 才可退）— 這是另一個 follow-up scope；
  本 issue 只解決「qty 超量」的會計問題
- **不**改 router 行為（既有 422 path 沿用）
- **不**改 `_lookup_offset_unit_cost`（F1 已穩定）
- **不**動 frontend（API 422 就夠 — UI 後續 polish 在 WMOM-20260513-01 / WMOM-20260507-02）

---

## 3. 檔案異動（規劃）

### 3.1 修改 backend

```
M modules/workflow/domain/inventory.py
  - MaterialRequest 加 compute_returnable_upper_bound(item_id) -> int
M modules/workflow/repository/material_request_repository.py
  - add_return() 內加 guard：query already_returned + 比較 upper bound + raise MaterialRequestRuleViolation
  - docstring 拿掉「caller 責任」段，改寫新行為
+ modules/workflow/tests/test_add_return_over_quantity_guard.py
  - 8-10 個新 test（domain + repo）
M modules/workflow/tests/test_material_request_repository.py
  - test_add_return_increments_stock：estimated_qty 1→2 對齊 return qty 2（修「超量退料」不再合法）
M modules/workflow/tests/test_material_request_item_metadata.py
  - test_metadata_after_add_return：actual_qty 5→4（worker 實用 4、退 1 surplus 才是 realistic + 通過 guard）
```

### 3.2 修改 tracking

```
M ISSUES.md         WMOM-20260519-01 → done；F1 docstring 警告段可拿掉；issue_stats open 19→18 / done 37→38
M STATUS.yaml       last_updated / next_milestone
+ work-logs/2026-05/2026-05-19-wmom-20260519-01-add-return-over-quantity-guard.md  本檔
```

### 3.3 不修改

- ORM layer
- schema layer（response / 422 已 OK）
- F1 寫的 17 個 test（情境設定都在 upper bound 內，不會 trigger guard）
- frontend
- cost ledger module

---

## 4. TODO

- [x] Read existing code（add_return / domain / 既有 add_return 測試）
- [x] Branch + work-log
- [x] Domain layer 加 `compute_returnable_upper_bound`
- [x] Repository layer guard：query already_returned + 比較 + raise
- [x] 修既有 2 個會 trigger 新 guard 的 test
- [x] 新 test file 涵蓋 guard 邊界
- [x] backend pytest 全跑 zero regression
- [x] code-reviewer subagent + 採納
- [x] ISSUES.md / STATUS.yaml update
- [x] commit + push + PR

---

## 5. 實作紀錄

### 5.1 完成檔案

**Backend 修改（2 個檔）**：
- `modules/workflow/domain/inventory.py`
  - `MaterialRequest.compute_returnable_upper_bound(item_id)` pure-domain method
- `modules/workflow/repository/material_request_repository.py`
  - `add_return` 先 query already-returned + 算 upper bound + raise `MaterialRequestRuleViolation`
  - docstring 改寫「caller 責任」段為「domain guard 保護」

**Backend 測試新增（1 個檔，15 個 test）**：
- `modules/workflow/tests/test_add_return_over_quantity_guard.py`
  - Domain layer pure tests (5)：dispatched only / consumed subtracts / multi-line aggregate cross-kind / unknown item_id zero / consumed > dispatched floor at 0
  - Repository layer (9)：qty exceeds raise / boundary equal allowed / F1 邊界場景 / cumulative already-returned blocks 2nd / cross-kind aggregate / no matching item / 月報 confirmed 不再負值 / unknown MR LookupError / qty=0 早擋
  - Router integration (1)：API 422 response with detail string

**修補既有測試（2 個）**：
- `modules/workflow/tests/test_material_request_repository.py:test_add_return_increments_stock` — estimated 1→2
- `modules/workflow/tests/test_material_request_item_metadata.py:test_metadata_after_add_return` — actual 5→4

### 5.2 Build / test 驗證

- `python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/` →
  - 560 passed (+15 new) + 1 xfailed + 3 numpy drift（pre-existing baseline，本次未動 cost/reporting code）
  - 15 new tests 100% pass
  - **Zero regression**（既有 test 全 pass）
- `python -m pytest tests/e2e/` → 6 passed（lifecycle 全綠）

### 5.3 Code review 採納

Code-reviewer subagent 找 1 must-fix + 3 should-fix + 2 nice-to-have，採納情況：

| 級別 | # | 議題 | 處置 |
|------|---|------|------|
| Must-fix | 1 | DRAFT 狀態 add_return 仍會 stock += qty | **不採納本 PR scope** — out-of-scope 設計決策（F1 fallback test 與此衝突，需獨立 PR）；開 follow-up **WMOM-20260519-02** 評估 status guard。Code 內加 comment 提示。 |
| Should-fix | 1 | `already_returned + qty` 型別在 PostgreSQL 可能不安全 | **採納** — `int()` cast 加在 query 結果上 |
| Should-fix | 2 | item_id ORM 型別跨 DB 相容性 | **不採納** — ORM 是 `String(36)`，與 F1 既有 `_lookup_offset_unit_cost` 同 pattern，一致使用 `str(item_id)` |
| Should-fix | 3 | router test 用 importlib reload 脆弱 | **採納** — 改用 `from ... import router` trigger import 後從 sys.modules 拿 submodule 再 monkeypatch（避開 __init__.py rebind） |
| Nice | 1 | `compute_returnable_upper_bound` 加 defensive 型別斷言 | **不採納** — `MaterialRequestItem.__post_init__` 已 enforce `estimated_qty > 0`；scope creep |
| Nice | 2 | work-log 計數 11 → 15 對齊實際 test 數 | **採納** — 本檔已更新 |

Follow-up issue：**WMOM-20260519-02 — `add_return` 在非 dispatched 狀態下仍會加 stock**（priority: low-medium；F1 cost ledger 已自動沖銷，但 stock 層 leak 仍存在；需獨立評估 status guard 與 F1 fallback test 的互動）。

---

## 6. 下次接手指南

### 已完成
- WMOM-20260519-01：`add_return` 加 domain-level upper-bound guard
- Domain 加 `MaterialRequest.compute_returnable_upper_bound(item_id)` pure method
- repo `add_return` 先比對 already_returned + new_qty 不超 upper bound，否則 422 `MaterialRequestRuleViolation`
- F1 docstring「⚠ 會計邊界（caller 責任）」改寫為「domain guard」段
- 11 個新 test 涵蓋 domain + repo + boundary + multi-line + cross-kind

### 待辦（不阻塞）
- F2-F5 follow-up 4 個 0.5h 小修可一次清掉
- F6 PostgreSQL row-lock integration test
- M5 規劃（讀 `docs/product/ROADMAP.md` M5 章節）

### 建議下次 session 工作

1. **F2-F5 一次清掉**（4 個 0.5h，single session 可全做完）
2. **M5 規劃**：讀 `docs/product/ROADMAP.md` M5 章節決定第一個 issue
3. WMOM-20260513-02 demo orchestrator simulator（2-3d）
