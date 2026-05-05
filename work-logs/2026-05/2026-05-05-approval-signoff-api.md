# 2026-05-05 — Approval signoff API（WMOM-20260504-18）

> Session 類型：實作（domain + repo + API + 整合）
> Session 長度：中
> 主導：Claude
> 結果：依 DN-02 的 4 階 signoff chain 設計實作；整合 work_order finish → 自動建 chain；approve last step → 觸發 work_order.approve_all

---

## 1. Session 目標

進 M3 主線實作第 3 個 issue。範圍：
- `modules/workflow/domain/signoff.py`：4 階 SignoffLevel + chain / step / history dataclasses + chain policy
- `modules/workflow/repository/`：加 SignoffChainORM / SignoffStepORM / SignoffHistoryORM + SignoffRepository
- `modules/workflow/schemas/signoff_schemas.py`：pydantic
- `modules/workflow/routers/approval_router.py`：endpoints
  - `GET /api/workflow/approvals/pending` (我的待簽)
  - `POST /api/workflow/approvals/{step_id}/approve`
  - `POST /api/workflow/approvals/{step_id}/reject`
- 整合：
  - work_order `finish` 完成後自動 `signoff_repo.create_chain_for_work_order()`
  - 簽核最後一階 approve → 觸發 work_order `approve_all`
  - 任一階 reject → 觸發 work_order `reject(reason)`
- Tests + code review

---

## 2. 實際完成

### 2.1 主要工作

- ✅ `modules/workflow/domain/signoff.py`：4 階 SignoffLevel + chain / step / history dataclasses + chain policy + user_group_to_level helper
- ✅ `modules/workflow/repository/orm_models.py`：+3 個 SQLAlchemy 2.0 mapped class（SignoffChainORM / SignoffStepORM / SignoffHistoryORM）
- ✅ `modules/workflow/repository/signoff_repository.py`：完整 SignoffRepository（create_chain / approve_step / reject_step / pending list / history audit）
- ✅ `modules/workflow/schemas/signoff_schemas.py`：6 個 pydantic v2 model（含 ApprovalResultResponse 帶 subject_transition_error）
- ✅ `modules/workflow/routers/approval_router.py`：3 個 FastAPI endpoints + factory injection + public `get_signoff_repo_for_farm`
- ✅ `modules/workflow/routers/work_order_router.py`：finish endpoint 整合 auto-create chain + backlink signoff_chain_id
- ✅ Mount approval router 進主 FastAPI app
- ✅ Tests +34（signoff repo 28 + approval API 9）整 pytest **250 PASS + 1 XFAIL**
- ✅ Code review by code-reviewer agent — **11 finding 全處理**（5 must-fix + 4 should-fix + 2 nice-to-have）

### 2.2 Code review fix 重點

| Finding | 修法 |
|---------|------|
| #1+#2 must approve/reject 後 wo transition 失敗的不一致 state | 改回 200 + `subject_transition_error` 欄位（不 raise 500），caller 看到 chain 已 terminal + 工單沒跟上即可走 backfill |
| #3 must `build_chain_levels` 全 disabled silent fallback | 改 raise `ValueError("不可關閉所有層級")` |
| #4 must work_order_router → approval_router private import | 加 public `get_signoff_repo_for_farm()` |
| #5 must `get_chain_for_subject` tie-break race | secondary sort `(started_at desc, id desc)` + test 加 sleep 確保 ordering |
| #6 should `parallel_group_id` 暴露但 ignored | `_validate_step_decidable` 檢出非 None 直接 `NotImplementedError` |
| #7 should approve/reject race | `with_for_update=True` on chain 取得（SQLite 限制下對未來 PG 切換 ready） |
| #8 should `finish` except Exception 吞所有錯 | 細分 `(ValueError, LookupError)` warn + 其他 error log |
| #9 should `SignoffHistoryEntry.id` UUID vs ORM int 不一致 | dataclass 改 `int \| None` 對齊 ORM autoincrement |
| #11 nice `signoff_disabled_levels` list[str] vs list[SignoffLevel] | 自動 coerce string → enum |

### 2.3 卡住或延後的事

- 無

### 2.4 重大決策

- approve/reject + work_order transition 走 **兩個獨立 transaction**（不同 repository / 不同 connection）。reviewer 提出 outbox pattern 但對 SQLite + M3 scope 過度工程；改用「response 帶錯誤訊息給 caller」走 graceful degradation
- `parallel_group_id` 為 D2-Q4 預留欄位但 M3 拒絕使用（NotImplementedError），避免「設了沒用」的 silent bug

---

## 3. 產出清單

- 新增 `modules/workflow/domain/signoff.py`
- 修改 `modules/workflow/domain/__init__.py`（exports）
- 修改 `modules/workflow/repository/orm_models.py`（+3 表）
- 新增 `modules/workflow/repository/signoff_repository.py`
- 新增 `modules/workflow/schemas/signoff_schemas.py`
- 新增 `modules/workflow/routers/approval_router.py`
- 修改 `modules/workflow/routers/work_order_router.py`（finish 完整合）
- 修改 `modules/monitoring/server/app.py`（mount approval router）
- 新增 `modules/workflow/tests/test_signoff_*.py`

## 4. 下次怎麼接手

進 WMOM-19 — `/admin/workflow/orders` frontend（建工單精靈 + 列表 + 詳情；React + TypeScript + Tailwind）。
