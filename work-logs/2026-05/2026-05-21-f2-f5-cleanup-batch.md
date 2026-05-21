# 2026-05-21 WMOM-20260509-F2/F3/F4/F5 — F1-F6 follow-up cleanup batch（4-in-1）

> **Issue**：WMOM-20260509-F2 / -F3 / -F4 / -F5 — 4 個低風險小修一次清掉
> **Branch**：`claude/blissful-turing-nR5qR`（autonomous daily worker session 2026-05-21 20:00）
> **Goal**：消滅 4 個 code review 留下的 cosmetic / refactor 議題；不動商業邏輯，純結構整理

---

## 1. 為什麼今天做這個

2026-05-19 F1 handoff doc 列下次候選 4 條：
- WMOM-20260519-01（F1 follow-up，0.5-1d，需 design 決策 — 改 domain layer guard 邏輯）
- **F2-F5 一次清掉**（4 個 0.5h-1h，無 design 決策、無新測試需求）
- M5 規劃（需先讀 ROADMAP M5 章節）
- WMOM-20260513-02 demo orchestrator simulator（2-3d）

F2-F5 是「**zero behavior change refactor 集合**」：

| Issue | 改動 | Estimate |
|-------|------|----------|
| F2 | `inventory_repository.list_items` / `material_request_repository.list` 用 `func.count` 而非 Python `len` | 0.5h |
| F3 | `inventory_router.list_warehouses` 從 raw SQL 改用 `InventoryRepository.list_warehouses` | 0.5h |
| F4 | 4 個 routers 重複的 `_FARM_REGISTRY` lazy singleton 抽 `shared/farm_registry_provider.py` | 1h |
| F5 | `InventoryAdjustmentLog.actor_id: UUID` → `UUID | None`（system-adjust path 不再被迫塞 fake UUID） | 15min |

合計 ≈ 2-2.5h，single-session 落地剛好。

商業價值：低（不影響 demo），但對未來新人讀 code 友善（少 4 個 cosmetic「為什麼這樣寫」的問號）。

---

## 2. 設計決策

### 2.1 F2 — SQL count vs Python len

兩個 repo 都用 `total = len(sess.execute(count_stmt).scalars().all())` — 把所有 id 撈回 Python 後算 `len()`。

改用 SQLAlchemy 標準 pattern：

```python
from sqlalchemy import func
count_stmt = select(func.count()).select_from(base.subquery())
total = sess.execute(count_stmt).scalar_one()
```

`.subquery()` 包住 base SELECT 後外層 `func.count()`，避免 ORDER BY / LIMIT 干擾。

兩處改法相同 (`inventory_repository.list_items` + `material_request_repository.list`)。

### 2.2 F3 — list_warehouses 拉進 repo

現況：`inventory_router.list_warehouses` 直接用 `repo._sessionmaker()` query `WarehouseORM`，violates repository 封裝原則。

新增 `InventoryRepository.list_warehouses(farm_id: str) -> list[Warehouse]`：
- 內部 SQL = 既有 router 用的 query（`farm_id` filter + ORDER BY `is_default DESC, name`）
- 回 domain 物件 list（用 `_warehouse_to_domain` 既有 helper）
- router 變兩行：`whs = repo.list_warehouses(farm_id); return WarehouseListResponse(items=[WarehouseResponse.model_validate(w) for w in whs])`

### 2.3 F4 — _FARM_REGISTRY 抽 shared

4 個 routers 各自重複 lazy singleton：
- `modules/workflow/routers/inventory_router.py`
- `modules/workflow/routers/material_request_router.py`
- `modules/workflow/routers/approval_router.py`
- `modules/cost/routers/cost_ledger_router.py`

新檔 `shared/farm_registry_provider.py`：
- `get_farm_registry() -> FarmRegistry`（module-level lazy singleton + cached）
- `resolve_farm_db_path(farm_id: str) -> str`（raise HTTPException(404) 若 farm 不存在）
- `reset_farm_registry() -> None`（給 test mock 用 — 走 `set_*_factory(None)` 清狀態）

4 個 routers 改：
- 刪 module-level `_FARM_REGISTRY = None` + `_resolve_farm_db_path()` function
- import shared helper
- `set_*_factory(None)` 路徑改呼叫 `reset_farm_registry()`（注意：本身會清掉**所有** routers 共用的 singleton — 測試 fixture 重新 init 一次即可，影響可忽略）
- 既有 import 「from modules.monitoring.server.farm_registry import FarmRegistry」搬進 shared

### 2.4 F5 — actor_id 改 Optional

3 處要改：
- `modules/workflow/domain/inventory.py:InventoryAdjustmentLog.actor_id: UUID` → `actor_id: UUID | None = None`（移到 dataclass field with default 之前還是之後？— 因 dataclass 規則：non-default field 不可在 default field 之後。`actor_id` 之前的 fields (`item_id/delta_kind/delta/reason`) 都是 non-default。把 `actor_id` 改成 default=None 後，必須移到 default field group 內 / 或保留位置但用 `Optional[UUID] = None` — 後者語法可行但會影響既有 caller 的 positional 用法。**安全做法**：保留 keyword-only 介面，不改 field 順序，加 default。實際 dataclass 場景下這需要 `field(default=None)` 或重排）
- `modules/workflow/repository/inventory_repository.py:adjust(actor_id: UUID)` → `actor_id: UUID | None = None`；ORM 寫入時 `actor_id = str(actor_id) if actor_id else None`
- `modules/workflow/repository/inventory_orm.py:InventoryAdjustmentLogORM.actor_id` → `Mapped[Optional[str]]`（DB column nullable）
- `modules/workflow/schemas/inventory_schemas.py:AdjustInventoryRequest.actor_id: UUID` → `Optional[UUID] = None`；`AdjustmentLogResponse.actor_id: UUID` → `Optional[UUID] = None`
- `_log_to_domain`: `actor_id=UUID(orm.actor_id) if orm.actor_id else None`

**dataclass field order 注意**：`InventoryAdjustmentLog` 既有順序：
```
item_id, delta_kind, delta, reason, actor_id, id=..., note=None, occurred_at=...
```

`actor_id` 改有 default 後，與後續 `id/note/occurred_at` default 不衝突。但 **caller 用 positional 會炸**。grep 確認所有 caller 都用 keyword：repo 內 dataclass instantiation `InventoryAdjustmentLog(item_id=..., delta_kind=..., delta=..., reason=..., actor_id=...)` 全 keyword。安全改。

### 2.5 backward compat

F2/F3/F4 是 pure refactor — public API + 行為完全不變。
F5 對舊 caller 全相容（`actor_id` 仍可傳 UUID；不傳則寫 NULL）。

DB schema 改動：F5 改 `inventory_adjustment_log.actor_id` from NOT NULL → NULLABLE。
- SQLite：ORM 重建 schema 自動帶入（tests 用 ephemeral SQLite，建立時走最新 schema 不會炸）
- PostgreSQL 生產：需 ALTER TABLE migration（F6 PG 部署 issue 已 open；本 issue 內不做 migration script，note in commit）

### 2.6 scope 邊界

**做**：
- F2/F3/F4/F5 純結構改動
- 為 F3 / F5 加 unit test（F3 新 repo method test；F5 actor_id=None happy path test）
- F4 helper 加 unit test（不重複 4 routers 的 integration test）

**不做**：
- F6（PG row-lock test，需 docker postgres，跨 session 大工程）
- WMOM-20260519-01（domain guard 設計，需與劉老師確認）
- DB migration script（F5 NULL 改動；M6 PG 部署再做）

---

## 3. 檔案異動（規劃）

### 3.1 修改 backend

```
+ shared/farm_registry_provider.py                                  新增 lazy singleton + resolve_farm_db_path
M modules/workflow/repository/inventory_repository.py               F2 (list_items SQL count) + F3 (list_warehouses) + F5 (actor_id Optional)
M modules/workflow/repository/material_request_repository.py        F2 (list SQL count)
M modules/workflow/repository/inventory_orm.py                      F5 (actor_id nullable)
M modules/workflow/domain/inventory.py                              F5 (actor_id Optional[UUID])
M modules/workflow/schemas/inventory_schemas.py                     F5 (actor_id Optional in Request + Response)
M modules/workflow/routers/inventory_router.py                      F3 (raw SQL → repo.list_warehouses) + F4 (shared FARM_REGISTRY)
M modules/workflow/routers/material_request_router.py               F4 (shared FARM_REGISTRY)
M modules/workflow/routers/approval_router.py                       F4 (shared FARM_REGISTRY)
M modules/cost/routers/cost_ledger_router.py                        F4 (shared FARM_REGISTRY)
+ tests/test_farm_registry_provider.py                              F4 helper test
+ modules/workflow/tests/test_f2_f3_f5_followup.py                  F2 list count + F3 list_warehouses + F5 actor_id Optional
```

### 3.2 修改 tracking

```
M ISSUES.md            F2/F3/F4/F5 → done（issue_stats open 19 → 15 / done 37 → 41）
M STATUS.yaml          last_updated / next_milestone
+ work-logs/2026-05/2026-05-21-f2-f5-cleanup-batch.md  本檔
```

### 3.3 不修改

- F1 已完成的 `add_return` ledger logic
- M4 已收的 frontend（純 backend cleanup）
- 任何 modules/monitoring / cost engine / reporting PDF logic
- DB migration script（留給 M6 PG 部署）

---

## 4. TODO

- [x] Read existing code（4 routers + 2 repos + orm + schemas + domain）
- [x] Branch + work-log
- [x] F2 backend：inventory_repository.list_items 用 func.count
- [x] F2 backend：material_request_repository.list 用 func.count
- [x] F3 backend：InventoryRepository.list_warehouses 加 method
- [x] F3 backend：inventory_router.list_warehouses 改用 repo method
- [x] F4 backend：shared/farm_registry_provider.py 新增
- [x] F4 backend：4 個 routers 改用 shared helper
- [x] F5 backend：domain / orm / schema / repo / 改 actor_id Optional
- [x] Tests for F2 / F3 / F5（10 test）+ helper file for F4（5 test）
- [x] backend pytest zero regression（566 pass = 550 baseline + 15 new + 1 flaky concurrency 過 / + 1 xfailed + 3 pre-existing numpy drift）
- [ ] code-reviewer subagent + 採納 must-fix / should-fix
- [x] ISSUES.md / STATUS.yaml update
- [ ] commit + push + PR

---

## 5. 實作紀錄

### 5.1 完成檔案

**Backend 修改（9 個檔）：**
- `shared/farm_registry_provider.py` — 新檔，提供 `get_farm_registry()` / `resolve_farm_db_path()` / `reset_farm_registry()`（lazy import + module-level cached + threading.Lock；shared 不依賴 modules 用 `Any` 型別）
- `modules/workflow/repository/inventory_repository.py` — F2 list_items 改 `select(func.count()).select_from(base.subquery())`；F3 加 `list_warehouses(farm_id)`；F5 `adjust(actor_id: UUID | None = None)` + `_log_to_domain` None 分支
- `modules/workflow/repository/material_request_repository.py` — F2 list 改 SQL count
- `modules/workflow/repository/inventory_orm.py` — F5 `actor_id` 改 `Mapped[Optional[str]] + nullable=True`
- `modules/workflow/domain/inventory.py` — F5 `InventoryAdjustmentLog.actor_id: UUID | None = None`
- `modules/workflow/schemas/inventory_schemas.py` — F5 `AdjustInventoryRequest.actor_id` + `AdjustmentLogResponse.actor_id` 改 `Optional[UUID]`
- `modules/workflow/routers/inventory_router.py` — F3 endpoint 改用 repo method；F4 移除 `_FARM_REGISTRY` + `_resolve_farm_db_path` 改 import shared
- `modules/workflow/routers/material_request_router.py` — F4 移除 + import shared
- `modules/workflow/routers/approval_router.py` — F4 移除 + import shared
- `modules/cost/routers/cost_ledger_router.py` — F4 移除 + import shared

**Backend 測試新增（2 個檔，15 test）：**
- `tests/test_farm_registry_provider.py` — F4 helper 5 test：lazy init 一次 + cached / resolve happy / 404 / reset 清狀態後重新 init / import 失敗 500
- `modules/workflow/tests/test_f2_f3_f5_followup.py` — 10 test：F2（list_items 7→limit 3 total=7 / empty / MR list 同型）+ F3（default 排前 / farm filter / empty）+ F5（domain dataclass default None / repo with actor / repo without actor → DB NULL → round-trip None / mixed 同表 reason→actor map）

**Tracking：**
- `ISSUES.md` — F2/F3/F4/F5 → done；統計表 open 19→15 / done 37→41；F4 followup note（work_order/reporting 未在 scope）
- `STATUS.yaml` — last_updated / next_milestone / issue_stats

### 5.2 設計決策落實

- **F4 lazy import**：`shared/` 不該硬綁 `modules/monitoring`；改 lazy `import modules.monitoring.server.farm_registry` 在 `get_farm_registry()` 第一次呼叫時動態載入，並用 `Any` 型別 hint 不洩 modules 內部
- **F4 thread safety**：DC lock + double-checked locking pattern 避免並發 init 兩次
- **F4 test mock 策略**：用 `monkeypatch.setitem(sys.modules, "modules.monitoring.server.farm_registry", fake_module)` 注入 fake FarmRegistry；測試完全不依賴 monitoring 真實 DB
- **F4 scope 邊界**：發現 `work_order_router.py` + `reporting/routers/reporting_router.py` 有相似 pattern，但 issue 明確列 4 個；記在 follow-up note 不擴大 scope
- **F5 dataclass field order**：`actor_id: UUID | None = None` 後續 `id` / `note` / `occurred_at` 都已有 default，dataclass 規則不破。grep confirm 所有 caller 用 keyword
- **F5 ORM column nullable**：SQLite 重建 schema 自動帶；PostgreSQL ALTER 留 M6（F6 PG 部署 issue 已 open）
- **F5 schema Response Optional**：FastAPI auto-generated docs 會正確顯示 `actor_id: UUID | null`，前端 type 不會被打壞

### 5.3 Build / test 驗證

- `python -m pytest tests/test_farm_registry_provider.py modules/workflow/tests/test_f2_f3_f5_followup.py -v` → **15 passed**
- `python -m pytest modules/workflow/tests/ modules/cost/tests/ modules/reporting/tests/ tests/e2e/ tests/test_farm_registry_provider.py -q` → **566 passed (+16 = 15 new + 1 flaky concurrency 過), 1 xfailed, 3 failed**（3 pre-existing numpy drift；與 main baseline 同 — **zero regression**）
