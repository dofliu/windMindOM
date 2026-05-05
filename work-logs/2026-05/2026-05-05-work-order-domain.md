# 2026-05-05 — Work Order 領域模型 + 狀態機（WMOM-20260504-16）

> Session 類型：實作（pure domain）
> Session 長度：中
> 主導：Claude
> 結果：依 DN-01 寫出 work_order.py + state_machine.py + tests，不接 SQLAlchemy / FastAPI

---

## 1. Session 目標

進 M3 主線實作第 1 個 issue。範圍嚴格依 DN-01：
- `modules/workflow/domain/work_order.py`：`WorkOrder` dataclass / `WorkOrderStatus` / `WorkOrderType` / `FollowupKind` / `Priority` Enum + `WorkOrderFollowup`
- `modules/workflow/domain/state_machine.py`：states + 9 個 transition + guard 條件
- `modules/workflow/tests/test_work_order.py` + `test_state_machine.py`：所有 transition 正例 / 反例
- **不接 SQLAlchemy / FastAPI**，純 domain；下個 issue (-17) 才 wrap

---

## 2. 實際完成

### 2.1 主要工作

- ✅ `modules/workflow/domain/__init__.py`：API exports（含 reopenable_states helper）
- ✅ `modules/workflow/domain/work_order.py`：
  - 4 個 Enum：`WorkOrderStatus` (7) / `WorkOrderType` (4) / `FollowupKind` (2) / `Priority` (4)
  - `ProgressNote` / `WorkOrderFollowup`（kw_only `parent_work_order_id` 必填）
  - `WorkOrder` 主 dataclass — 完整含 onshore baseline + offshore 延伸（vessel / WW / crew）+ reject / reopen 獨立欄位
  - `is_open()` / `is_terminal()` / `to_dict()` helper
  - `_utc_now()` UTC timestamp factory
- ✅ `modules/workflow/domain/state_machine.py`：
  - `TransitionRule` + `WORK_ORDER_TRANSITIONS` table（9 條 rule / 8 unique action — start_work 雙 source state）
  - 6 個 guard 函式（含 _guard_update_progress 為 fix #2 新增）
  - guard 簽名 `(WorkOrder, UUID | None, dict) -> None`（fix #3 加 actor_id）
  - `WorkOrderStateMachine.transition` / `can_transition` / `available_actions`
  - `open_states()` / `terminal_states()` / `reopenable_states()` helpers
  - reopen 走獨立 `reopen_reason` 欄位，不串接 followup_note（fix #7）
- ✅ `modules/workflow/tests/test_work_order.py` (20 tests)：Enum sanity + dataclass 行為 + UTC timestamp + Followup kw_only
- ✅ `modules/workflow/tests/test_state_machine.py` (53 tests)：所有 transition × 正反例 + 3 個完整 lifecycle + 1 個 guard 不污染 state 不變式
- ✅ Code review by code-reviewer agent — **13 finding 全處理**（5 must-fix + 5 should-fix + 3 nice-to-have，2 個 nice-to-have 評估後 skip）

### 2.2 Code review fix 重點

| Finding | 修法 |
|---------|------|
| #1 `WorkOrderFollowup.parent_work_order_id` type ignore 掩蓋型別 | 改 `kw_only=True` 必填，移除 type:ignore；加 test 驗 TypeError |
| #2 `update_progress` actor_id 可為 None 但 `ProgressNote.actor_id: UUID` | 新加 `_guard_update_progress` 強制 note + actor_id 非空；strip whitespace + 拒絕純空白 |
| #3 `_guard_dispatch` 沒檢 actor_id（架構問題） | guard 簽名加 actor_id 參數；dispatch 檢 audit actor_id 必填 |
| #4 `terminal_states()` 與 reopen 語意矛盾 | docstring 明示 reopen 為 CLOSED 合法 exit transition；新加 `reopenable_states()` helper |
| #5 `datetime.now()` naive datetime | 加 `_utc_now()` 統一回 timezone-aware UTC，所有 default_factory 與 transition 內 timestamp 改用 |
| #7 `reopen_reason` 串到 followup_note 污染 | 新加 `reopened_at` + `reopen_reason` 獨立欄位；test 驗 followup_note 不被改動 |
| #10 部分 test 用 for loop 未 parametrize | 改用 `@pytest.mark.parametrize` 統一 dispatch source / cancel terminal / reopen invalid |
| #11 dict 順序語意可能誤導 | 加 comment 明示「順序無語意，alphabetical-by-action」 |
| #13 DN-01 §2.3 schema 缺 reject/reopen 欄位 | 同步補上 reject_reason / reopen_reason / reopened_at + 標記 timestamps tz=UTC |
| #8 frozen=True 文件 contract | skip — maintain 成本太高 vs scope，下個 issue 評估 |
| #9 typing.Any | skip — `to_dict` 用 asdict 本身就回 dict[str, Any]，原生型別約束 |
| #12 _apply_side_effects refactor | skip — 8 個 branch 仍可讀，>10 再 refactor |

### 2.3 卡住或延後的事

- 無

### 2.4 重大決策

- guard 簽名從 `(WorkOrder, dict)` 改為 `(WorkOrder, UUID | None, dict)` — 為 audit actor 提供結構性管道，避免「caller 自己 stuff actor_id 進 kwargs」這種 hack
- `_utc_now()` 取代 `datetime.now()` — 整 codebase 該規則往 cost / ledger 推（M4 後續評估）

---

## 3. 產出清單

- 新增 `modules/workflow/domain/__init__.py`
- 新增 `modules/workflow/domain/work_order.py`
- 新增 `modules/workflow/domain/state_machine.py`
- 新增 `modules/workflow/tests/__init__.py`
- 新增 `modules/workflow/tests/test_work_order.py`
- 新增 `modules/workflow/tests/test_state_machine.py`

## 4. 下次怎麼接手

進 WMOM-20260504-17 — Work Order CRUD + REST API（依 -16 domain 包 SQLAlchemy + FastAPI）。
