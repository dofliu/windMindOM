# 2026-05-05 — Work Order CRUD + REST API（WMOM-20260504-17）

> Session 類型：實作（API + persistence）
> Session 長度：中
> 主導：Claude
> 結果：用 SQLAlchemy 2.0 + FastAPI 把 PR #5 的 pure domain 包成可呼叫的 REST API

---

## 1. Session 目標

進 M3 主線實作第 2 個 issue。範圍：
- `modules/workflow/repository/`：SQLAlchemy 2.0 ORM + Repository 層
  - WorkOrderORM / ProgressNoteORM / WorkOrderEventLogORM
  - WorkOrderRepository（CRUD + multi-WO constraint + business_key 生成 + state machine wrap）
- `modules/workflow/schemas/`：pydantic request / response
- `modules/workflow/routers/`：FastAPI router（11 endpoints）
- Tests: repository + API
- Mount 進 main FastAPI app

技術選型：
- SQLAlchemy 2.0 mapped class（type-safe，integrate dataclass-style）
- 同一個 farm DB（`wind_farm.db`）— monitoring 用 raw sqlite3 + WAL，並存無衝突
- DB schema 在 startup 時 `Base.metadata.create_all()` if not exists（不導 alembic 過度工程）

---

## 2. 實際完成

### 2.1 主要工作

- ✅ `modules/workflow/repository/`：
  - `orm_models.py`：3 個 SQLAlchemy 2.0 mapped class（WorkOrderORM / ProgressNoteORM / WorkOrderEventLogORM）
  - `work_order_repository.py`：engine cache + WorkOrderRepository（CRUD + transition + multi-WO constraint + business_key 生成 + event log）
- ✅ `modules/workflow/schemas/work_order_schemas.py`：10 個 pydantic v2 model（7 request + 3 response）
- ✅ `modules/workflow/routers/work_order_router.py`：11 個 FastAPI endpoint（CRUD + 8 state transitions）+ repository factory injection point
- ✅ Mount workflow router into `modules/monitoring/server/app.py`
- ✅ Tests：
  - `test_work_order_repository.py` × 31（含 review fix 後增 5 個）
  - `test_work_order_api.py` × 19
- ✅ Code review by code-reviewer agent — **9 finding**：3 must-fix + 5 should-fix + 1 nice-to-have **全處理**

### 2.2 Code review fix 重點

| Finding | 修法 |
|---------|------|
| #1 must `business_key` race 撞 IntegrityError | catch `IntegrityError` + retry once + 仍撞 raise `BusinessRuleViolation`（409 not 500） |
| #2 must `_apply_domain_to_orm` UTC validation 缺 | 加 `_assert_utc()` static helper；naive / non-UTC offset → `ValueError` |
| #3 must `FarmRegistry()` per request | 改 `_get_default_farm_registry()` lazy singleton |
| #5 should WAL pragma 沒主動設 | SQLAlchemy `connect` event listener 主動設 WAL + busy_timeout + synchronous=NORMAL |
| #6 should `update_progress` 依賴 `progress_notes[-1]` 脆弱 | 改用 kwargs 直接重建 ProgressNoteORM，不依賴 list 順序 |
| #7 should `create_all` 每次都跑 | `_SCHEMA_INITIALIZED` set 紀錄已建表的 db_path，第二次跳過 |
| #9 should `_clear_engine_cache_for_test` private prefix 卻被 tests 用 | 重命名 `clear_engine_cache_for_test`（公開 API），保留 `_` alias 兼容 |
| nice-to-have #1 `total = len(items)` 截斷錯誤 | 改 `repo.list()` 回 `(items, total)`，total 是真實 DB count（不受 limit 影響） |
| nice-to-have #2 frozen identity | `_apply_domain_to_orm` docstring 明示「id / farm_id / turbine_id / type 刻意不寫」+ comment 註保護 |

### 2.3 卡住或延後的事

- 無

### 2.4 重大決策

- workflow 用 SQLAlchemy 2.0，與 monitoring (raw sqlite3) 並存於同一 farm DB；WAL pragma 由 workflow engine 主動設置（避免 standalone 場景沒 WAL 撞鎖）
- repository 層 multi-WO constraint 走 application-level（DB unique partial index 在 SQLite 跨版本行為不一致）
- business_key collision retry 一次 — 真實 prod 可進一步用 SELECT MAX FOR UPDATE（PostgreSQL 換好後）

---

## 3. 產出清單

- 新增 `modules/workflow/repository/__init__.py`
- 新增 `modules/workflow/repository/orm_models.py`
- 新增 `modules/workflow/repository/work_order_repository.py`
- 新增 `modules/workflow/schemas/__init__.py`
- 新增 `modules/workflow/schemas/work_order_schemas.py`
- 新增 `modules/workflow/routers/__init__.py`
- 新增 `modules/workflow/routers/work_order_router.py`
- 新增 `modules/workflow/tests/test_work_order_repository.py`
- 新增 `modules/workflow/tests/test_work_order_api.py`
- 修改 `modules/monitoring/server/app.py`（mount workflow router）

## 4. 下次怎麼接手

進 WMOM-18 — Approval signoff API（依 DN-02）。
