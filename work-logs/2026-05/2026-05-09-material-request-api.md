# 2026-05-09 — MaterialRequest API + Approval MR Hook（WMOM-20260509-03）

> Session 類型：實作（FastAPI router + schemas + approval router 整合）
> Session 長度：短（A1 / A2 同日接力第三輪）
> 主導：Claude
> 結果：M4 backend 主菜 3/4 完工 — 9 個 MR endpoints + signoff 整合就位；27 new tests pass + 全 375 tests 0 regression。

---

## 1. Session 目標

依 ISSUES.md WMOM-20260509-03 acceptance：

- `modules/workflow/schemas/material_request_schemas.py`：CreateMaterialRequest / submit / dispatch / receive / close / cancel / return + response 模型
- `modules/workflow/routers/material_request_router.py`：9 endpoints 接 MaterialRequestRepository
- 改 `signoff_repository.py`：加 `create_chain_for_material_request` (DN-02 預設 3 階：employee/leader/treasury)
- 改 `approval_router.py`：MATERIAL_REQUEST chain 簽核完成時自動觸發 `dispatch_request()`；reject 時自動 `transition('reject')` 進 REJECTED 終態
- mount 進 `modules/monitoring/server/app.py`
- 30+ pytest 含 422 / 409 / 404 error mapping + approval 整合 happy + edge case

---

## 2. 實際完成

### 2.1 新檔（3）

- `modules/workflow/schemas/material_request_schemas.py`（~150 行）：8 request body + 3 response model + sub-models（item / return）
- `modules/workflow/routers/material_request_router.py`（~290 行）：9 endpoints + repo factory injection（同 work_order / approval pattern）+ error mapping helper
- `modules/workflow/tests/test_material_request_api.py`（~480 行 / 27 tests）：CRUD + state transitions + 完整 approval + auto-dispatch lifecycle + edge cases

### 2.2 改檔（5）

- `modules/workflow/repository/signoff_repository.py`：加 `create_chain_for_material_request()`（mirror work_order 版本，subject_type=MATERIAL_REQUEST）
- `modules/workflow/routers/approval_router.py`：
  - `set_signoff_factories(...)` 加 `material_request` 第三個 factory 參數（向後相容預設 None）
  - `_get_material_request_repo(farm_id)` helper
  - `approve_step` 加 MATERIAL_REQUEST branch：last step approve → `mr_repo.transition('approve_all')` → `dispatch_request()` atomic 雙寫
  - `reject_step` 加 MATERIAL_REQUEST branch：→ `mr_repo.transition('reject', reject_reason)` 進 REJECTED 終態
- `modules/workflow/repository/material_request_repository.py`：dispatch_request error message 從 "must be APPROVED" 改為 "cannot transition from {status} (must be APPROVED)" — 讓 router 的 `_map_state_error` 看到 "cannot transition" 後正確 map 成 409 Conflict（vs 422 Unprocessable Entity）
- `modules/workflow/routers/__init__.py`：export `material_request_router`
- `modules/workflow/schemas/__init__.py`：export 12 個新 schema
- `modules/monitoring/server/app.py`：mount `material_request_router`

### 2.3 9 endpoints

| Method | Path | 用途 |
|---|---|---|
| POST | `/api/workflow/material-requests` | create DRAFT |
| GET | `/api/workflow/material-requests` | list (filter farm/work_order/status + pagination) |
| GET | `/api/workflow/material-requests/{id}` | detail |
| POST | `/api/workflow/material-requests/{id}/submit-for-approval` | DRAFT → AWAITING + 建 chain |
| POST | `/api/workflow/material-requests/{id}/dispatch` | APPROVED → DISPATCHED + atomic 雙寫（通常走 approval auto-trigger，此 endpoint 給 ops 手動補） |
| POST | `/api/workflow/material-requests/{id}/receive` | DISPATCHED → RECEIVED + 寫 actual_qty |
| POST | `/api/workflow/material-requests/{id}/close` | USED/RECEIVED → CLOSED |
| POST | `/api/workflow/material-requests/{id}/cancel` | DRAFT/AWAITING/APPROVED → CANCELLED |
| POST | `/api/workflow/material-requests/{id}/returns` | 建退料 + 加回 stock |

### 2.4 驗收

- **27 new tests pass** in 5.35s（含 happy lifecycle / signoff 整合 / 簽核時 stock 抽走的 edge case / cancel 在 DISPATCHED 不允許 / receive 缺 actual_qty 422 / unknown subject 404 / pagination）
- **全 workflow suite 318 pass**（M3 173 + A1 60 + A2 58 + A3 27）
- **cost + workflow 375 pass + 1 xfailed (existing) — 0 regression**
- AcceptanceCriteria 達標：30+ pytest（API + repo 整合 + 422/409/404 error mapping）+ approve last step 自動觸發 dispatch（在 approval_router 的 MATERIAL_REQUEST branch）

---

## 3. 設計決策

### 3.1 submit-for-approval 的順序：先建 chain，再 transition

如果先 transition 把 MR 改成 AWAITING_APPROVAL，建 chain 失敗就會留下 inconsistent state（MR 已 AWAITING 但無 chain）。所以：

1. `signoff_repo.create_chain_for_material_request(...)` ← 失敗 raise 422，MR 仍是 DRAFT
2. `mr_repo.transition('submit_for_approval')` ← 成功才繼續
3. `mr_repo.set_signoff_chain_id(chain.id)` ← backlink

如果第 2 步失敗（不太可能），chain 會孤立 — 寫 follow-up issue 給未來清理 task。

### 3.2 Approval 自動 dispatch：`approve_all` + `dispatch_request` 兩步

DN-03 設計上 approve last step → 直接出庫。技術上要分兩步：

```python
mr_repo.transition(mr_id, "approve_all")  # AWAITING → APPROVED
mr_repo.dispatch_request(mr_id, actor_id=req.actor_id)  # APPROVED → DISPATCHED + atomic
```

如果 `approve_all` 成功但 `dispatch_request` 失敗（最常見：簽核期間 stock 被別張單抽走），chain 已落地不能 retry，但 MR 卡在 APPROVED。處理：

- 回 200 + `subject_status_changed=False` + `subject_transition_error="..."` 訊息給 caller
- Test `test_dispatch_fails_at_approval_when_stock_drained` 驗：兩張各要 6 個但 stock=10 → a 全 approve 成功 dispatch 後 stock=4 → b 全 approve 成功但 dispatch 因 4<6 失敗 → MR b 卡在 APPROVED，operator 需要手動補（去 `/dispatch` endpoint 或 cancel）

### 3.3 Approval reject 對 MATERIAL_REQUEST 的處理

對應 DN-03 設計：MR 駁回後不就地 resubmit，operator 須建新 MR。所以 chain reject → MR 進 REJECTED 終態。Test `test_chain_reject_transitions_mr_to_rejected` 驗：reject employee 階就讓 MR 立刻進 REJECTED，跟 work_order 的「reject 回 IN_PROGRESS」明顯不同。

### 3.4 dispatch error message 改用 "cannot transition" 字眼

Router 的 `_map_state_error` 用 `"cannot transition" in msg` 區分 409 vs 422。dispatch_request 原本錯誤訊息是 "must be APPROVED" → 結果 mapping 成 422 不是 409。改字眼後能正確 mapping。

語意上：
- 409 Conflict = 工單目前 state 不對（caller 改 state 即可恢復）
- 422 Unprocessable Entity = request body 缺欄位 / 格式錯（caller 要改請求）

dispatch from DRAFT 屬前者 → 應該 409。

### 3.5 為何 `set_signoff_factories` 加第三個 material_request 參數

approval_router 的 MATERIAL_REQUEST branch 需要 mr_repo。但既有 caller（test_work_order_api.py）只傳兩個參數。為向後相容：第三個參數預設 None，舊 test 不破。新 test 可傳第三個 mock factory。

---

## 4. M4 進度

- ✅ A1 domain (60 tests)
- ✅ A2 repository + atomic dispatch (58 tests)
- ✅ **A3 MaterialRequest API + signoff 整合** (27 tests) ← 剛完成
- ⬜ A4 Inventory query + adjustment API（next）
- ⬜ A5 cost ledger 整合
- ⬜ A6 material frontend
- ⬜ A7 inventory frontend
- ⬜ A8 reporting backend
- ⬜ A9 reporting frontend
- ⬜ A10 E2E lifecycle test

---

## 5. Commit

`feat(#WMOM-20260509-03): material_request API + approval auto-dispatch (M4 A3)` — 9 files / 145 + 1 modified
