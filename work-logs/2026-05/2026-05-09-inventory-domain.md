# 2026-05-09 — Inventory + MaterialRequest Domain（WMOM-20260509-01）

> Session 類型：實作（pure-domain dataclass + state machine + tests）
> Session 長度：短（~半天）
> 主導：Claude
> 結果：M4 backend 主菜的根基（A1）就位；Inventory + MaterialRequest 7 個 dataclass + 3 個 enum + 8 個 transition action 全 pure-domain，60 測試 pass，0 SQLAlchemy / FastAPI 滲入。

---

## 1. Session 目標

依 ISSUES.md WMOM-20260509-01 acceptance：

- `modules/workflow/domain/inventory.py`：3 enum（StockKind / MaterialRequestStatus / ReturnReason）+ 7 dataclass（Warehouse / InventoryItem / MaterialRequest / MaterialRequestItem / MaterialReturn / MaterialRequestNotification / InventoryAdjustmentLog）
- `modules/workflow/domain/inventory_state_machine.py`：MaterialRequest 8 transitions（submit_for_approval / approve_all / reject / dispatch / receive / mark_used / close / cancel）
- `modules/workflow/domain/__init__.py`：export 新符號
- 30+ unit test pass（pure，不接 DB）
- 純 domain：不 import SQLAlchemy / FastAPI

---

## 2. 實際完成

### 2.1 新檔（共 3 個）

- `modules/workflow/domain/inventory.py`（~250 行）
  - 3 enum：`StockKind ∈ {NEW, USED, REPAIRING}`、`MaterialRequestStatus`（9 狀態）、`ReturnReason ∈ {SURPLUS, WRONG_PART, FAILED_INSTALL, OTHER}`
  - 7 dataclass：見上方
  - `InventoryItem` 提供 helper：`total_available()`、`is_below_safety()`、`get_stock(kind)`
  - `unit_cost: Decimal` 避免 float 誤差
  - `MaterialRequestItem` + `MaterialReturn` 在 `__post_init__` 擋 qty <= 0
- `modules/workflow/domain/inventory_state_machine.py`（~280 行）
  - 8 transitions + 5 guard funcs + side-effect dispatcher（與 work_order state_machine 同模式）
  - `MATERIAL_REQUEST_TRANSITIONS` 為 source-of-truth 表
  - `MaterialRequestStateMachine.{transition, can_transition, available_actions}` 入口
  - 重用 `state_machine.InvalidTransition`（exception 共用）
  - helper：`open_states_mr()` / `terminal_states_mr()`
- `modules/workflow/tests/test_inventory_domain.py`（~22 tests，~280 行）
- `modules/workflow/tests/test_material_request_state_machine.py`（~38 tests，~340 行）

### 2.2 改檔（共 1 個）

- `modules/workflow/domain/__init__.py`：加入 13 個新 export（10 inventory entity + 3 state machine helper）

### 2.3 驗收 / 測試

- **60 inventory test pass**（22 domain + 38 state machine）— 0.10 秒
- **全 workflow tests 233 pass**（60 新 + 173 既有，0 regression）— 4.21 秒
- **no SQLAlchemy / FastAPI / pydantic import**（測試用 `ast` 解析 import 樹確認）

---

## 3. 設計決策

### 3.1 REJECTED 狀態語意 — 終態 vs 回 DRAFT

DN-02 D2-Q3 寫的是「reject → 領料單回 DRAFT（給機會修正）」，但這跟有 REJECTED 狀態的設計衝突。我選擇 **REJECTED 為終態**（簽核 chain 駁回 → MR 進 REJECTED 不可動，操作員若要再申請須建新 MR）。理由：

1. **乾淨的 audit trail**：每張 MR 從生到死可追，駁回過幾次 / 哪一階駁的 → 統計清楚
2. **避免狀態 ping-pong**：reject → DRAFT → re-submit → reject → DRAFT 反覆無限循環不利 KPI
3. **強制操作員重新整理意圖**：被駁回後是真的要重做，而非繞過 reviewer 的意見

如劉老師決定要按 DN-02 改成「reject → DRAFT」，state machine 改一行就好（reject rule 的 to_state）：影響 1 行程式 + 2 個 test。Walkthrough 再 confirm。

### 3.2 cancel 在 DISPATCHED 之後不允許

物料已離庫，cancel 沒意義（庫存不會自動加回）。要退庫須走 `MaterialReturn` entity。state machine guard：

```python
"cancel": from_states=frozenset({DRAFT, AWAITING_APPROVAL, APPROVED}),
```

### 3.3 close 兩條 source state

正常 path 是 `RECEIVED → USED → CLOSED`，但若工單關了沒實際用到（領料但沒裝），允許 `RECEIVED → CLOSED` 跳過 USED。簡化 reporting / 處理「全退」場景（actual_qty=0 → 直接 close）。

### 3.4 receive 用 dict 帶 actual_qty

receive 不能逐 item 各自呼叫 — 需要 atomic 一次寫多筆 actual_qty。所以 transition kwargs 設計：

```python
MaterialRequestStateMachine.transition(
    mr, "receive",
    actual_quantities={item_id_1: 3, item_id_2: 1, item_id_3: 0},  # 必須涵蓋所有 items
)
```

guard 強制 dict 覆蓋所有 items（缺漏會 raise）。允許單個 item 的 actual=0（全退場景）。

### 3.5 dispatch 在 domain 層只動 status

真正的庫存扣帳 + cost ledger 寫入是 A2（repository 雙寫 transaction）的範圍。Domain 層 dispatch 純粹更新 status + dispatched_at，guard 只檢查「items 非空」這種 domain-level 條件。stock 充足與否在 repo 內 SELECT FOR UPDATE 後檢，避免 race。

### 3.6 import 防護用 AST 解析

第一版用 `'sqlalchemy' in src.lower()` naïve 檢查，誤判 docstring 內提及「SQLAlchemy mapping」。改用 `ast.parse` 解析 import 樹，只看真實 import statement。CI 級別 regression 防護穩定。

---

## 4. Follow-up

- ⬜ A2 (Repository + 雙寫 transaction) — 直接接 — 設計關鍵：SELECT FOR UPDATE + atomic stock + ledger
- ⬜ A3 (MaterialRequest CRUD + state API) — schema + router 接 transition entry
- ⬜ DN-02 D2-Q3 「reject → DRAFT」與本檔「reject → REJECTED」的差異留給 walkthrough confirm
- ⬜ M3 衍生 -21 (day_work_form) / -22 (inspection_schedule) 跟 inventory 平行不阻塞

---

## 5. Commit

`feat(#WMOM-20260509-01): inventory + material_request domain (M4 A1)` — 5 files
