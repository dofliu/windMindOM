# 2026-05-18 WMOM-20260510-01 Part C + D — Farm `is_offshore` field + start_work auto-driven weather_window

> **Issue**：WMOM-20260510-01 Part C + Part D — `FarmConfig.is_offshore` 後端欄位 + frontend `start_work` 自動依 farm 屬性決定要不要 weather_window
> **Branch**：`claude/nice-brown-PTCla`（autonomous daily worker session 指定分支）
> **Goal**：M5 demo polish 第三 + 第四步 — 把離岸 / 陸上判斷從「user 手動勾」收回 farm config，
> 並收尾 4-part WMOM-20260510-01 全 issue。

---

## 1. 為什麼今天做這個

依 2026-05-15 Part B handoff doc 建議：「下次候選：Part C farm `is_offshore` field（0.5d）+ Part D farm 設定 UI checkbox（0.5d）以收滿 WMOM-20260510-01 全 4 part」。

5/10 hotfix 把 `WorkOrderDetailModal` 的 `start_work` weather_window checkbox 暫時拿掉，預期是「等 farm config 有 `is_offshore` 後改成自動驅動」。本 session 把這條路接回。

兩個 part 加起來估時 1d，可在同一 session 完成。

---

## 2. Scope 與設計決策

### 2.1 為什麼把 Part C / Part D 一起做

Part C 加 backend 欄位，Part D 用它驅動 frontend。分開做的話 Part C PR 沒有 visible behavior change（純 schema 擴充），不利 review；
合併後可在同一 PR 演示「Farm 設離岸 → start_work 對話框自動要求 weather_window」完整 vertical slice，
也方便 demo 給劉老師看完整 flow。

### 2.2 `is_offshore` 的 DB migration 策略

`farms` table 既有資料需相容。`sqlite3` 的 `ALTER TABLE ADD COLUMN` 對既有 row 預設值就好 — `INTEGER NOT NULL DEFAULT 0` 對既有 3 個 farm 全部視為 onshore（劉老師 demo 用陸上）。

在 `_init_db()` 既有的 CREATE TABLE IF NOT EXISTS 後面加 idempotent migration：先查 `PRAGMA table_info(farms)`，若 `is_offshore` 不在欄位中才 ALTER。比起寫獨立 migration 檔，這個 inline pattern 與本 repo 既有 SQLite 慣例一致（`open_sqlite` + 各 module 各自 ensure schema）。

### 2.3 `start_work` 怎麼帶 `weather_window_id`

Offshore farm 走 `require_weather_window=true` 時，工單需先綁 `weather_window_id`。但目前 frontend 沒有 weather_window 管理頁也沒有 PATCH endpoint 可在 start_work 前先綁。

兩個選項：
- **A. 新增 PATCH `/api/workflow/work-orders/{id}` 給 weather_window_id 用**：完整但 scope creep
- **B. 擴 `StartWorkRequest` 多接 `weather_window_id` 一次傳完**：最小可行，與既有「dispatch 接 assignee_id」pattern 對稱

選 B。在 `_apply_side_effects` 的 `start_work` 分支多寫 `wo.weather_window_id = kwargs[...]`；guard 也接受 kwargs 帶值（不只看 wo 既有欄位）。

### 2.4 為什麼 weather_window_id 在 frontend 是純 UUID input 不做 picker

Weather window picker UI 是獨立功能（要排程、視覺化氣象視窗），M5 demo 用不到。本 part 純做「offshore farm 不能無腦 start，要 user 自己貼 UUID 或按 demo placeholder 按鈕」。

UX 上：
- Onshore farm：dialog 沒 weather_window UI，按確認直接送
- Offshore farm：dialog 顯示 weather_window_id 輸入框 + 「使用 demo placeholder」按鈕（產生固定 UUID，演 happy path 用），未填不可送出
- backend guard 不變：若 frontend 漏帶或 user 輸入空字串，仍 raise 422

### 2.5 farm 設定 UI（Part D）

CreateFarmModal 加 toggle。既有 farm 編輯目前沒 frontend UI（只能透過 PATCH /api/farms API 改），不在本 part scope — 劉老師需要把現有 farm 改 offshore 可用 curl 或開新 farm 重試。
M6 客戶 demo 前若需要可再開 issue 補。

---

## 3. 檔案異動（規劃）

### 3.1 修改

```
M modules/monitoring/server/farm_registry.py        FarmConfig.is_offshore + DB schema migrate + create/update 收欄位
M modules/monitoring/server/routers/farms.py        POST/PATCH 接 is_offshore
M modules/workflow/domain/state_machine.py          _guard_start_work 接受 kwargs weather_window_id；side-effect 寫回 wo
M modules/workflow/schemas/work_order_schemas.py    StartWorkRequest 多 weather_window_id 欄
M modules/workflow/routers/work_order_router.py     start_work 把 weather_window_id 傳進 transition
M frontend/components/FarmSelector.tsx              CreateFarmModal 多 is_offshore toggle + Farm interface 加欄位
M frontend/components/workflow/WorkflowPage.tsx     抓 active farm.is_offshore 傳給 modal
M frontend/components/workflow/WorkOrderDetailModal.tsx  start_work form 改自動依 farmIsOffshore
M frontend/services/workOrderService.ts             startWork payload 加 weather_window_id；Farm type 加 is_offshore
M ISSUES.md                                         Part C/D status → done；issue overall done
M STATUS.yaml                                       progress / next_milestone / last_updated
```

### 3.2 新增 tests

```
+ modules/monitoring/tests/test_farm_registry_is_offshore.py  3-4 條 farm CRUD with is_offshore
+ modules/workflow/tests/test_start_work_weather_window.py    2-3 條 start_work + weather_window_id in kwargs
```

---

## 4. TODO（implementation checklist）

- [x] Read existing code（farm_registry, farms router, state_machine, schemas, FarmSelector, WorkOrderDetailModal, WorkflowPage）
- [x] Branch + work-log
- [x] backend Part C: FarmConfig.is_offshore + DB migration + CRUD
- [x] backend Part C tests
- [x] backend domain extension: start_work 接受 weather_window_id kwarg
- [x] backend domain tests
- [x] backend pytest run zero new regression
- [x] frontend Part D: Farm type / FarmSelector createModal toggle
- [x] frontend Part D: WorkflowPage 抓 farm.is_offshore 傳給 modal
- [x] frontend Part D: WorkOrderDetailModal start_work form 改 auto
- [x] frontend `npx tsc --noEmit` zero error
- [x] frontend `npx vite build` zero error
- [x] code-reviewer subagent 跑：採納 must-fix
- [x] STATUS.yaml + ISSUES.md 更新
- [ ] commit + push + PR

## 5. Code review 採納

Code-reviewer subagent 找出 **3 must-fix + 4 should-fix**。

**Must-fix 全採納（3/3）**：
1. ✅ `_apply_side_effects` 與 `_guard_start_work` 對 `weather_window_id` 的 falsy/`is not None` 檢查不對齊 — empty string 會通過 guard 但覆寫工單既有有效 UUID。Fix：side-effect 改 `if kwargs.get("require_weather_window") and kwargs.get("weather_window_id"):` 對齊 guard 的 truthy fallback 行為（且順帶解決 should-fix #4）
2. ✅ `_init_db` ALTER TABLE 雙步驟 TOCTOU race（多 process 同時啟動會 `duplicate column`）— 改 try/except OperationalError 標準 idempotent migration pattern
3. ✅ `update_farm` `is_offshore` 接受 `bool(val)` truthy 轉換 — 字串 `"DROP TABLE"` 會被當 True。Fix：嚴格 isinstance(val, bool) 檢查，否則 raise ValueError

**Should-fix 採納（2/4）**：
- ✅ Should-fix #1：FarmSelector checkbox 用 `<label>` 包但又設 `aria-label`，screen reader 朗讀文字會跟 visible label 不一致。Fix：刪 `aria-label`，由外層 `<label>` 提供 accessible name
- ✅ Should-fix #4：onshore 工單帶 `weather_window_id` kwarg 會被誤寫入。**已隨 must-fix #1 一併解決**（side-effect gate 加 `require_weather_window` 條件）
- ⏭ Should-fix #2：`to_dict()` 未在 diff 內 → 實際上是 `{k: getattr(self, k) for k in __dataclass_fields__}` 自動 enumerate dataclass field，`is_offshore` 既已加進 dataclass 自然會包進 dict。`test_to_dict_includes_is_offshore` 已驗證
- ⏭ Should-fix #3：WorkflowPage 切 farm 後 `farmIsOffshore` 是否 stale → FarmSelector.switchFarm() 走 `window.location.reload()` 全頁 reload，所有 React state 重來，不會 stale

**Regression test 補強**：
- `test_start_work_onshore_does_not_write_weather_window_id_kwarg`（取代舊的「is intentional」測試）
- `test_start_work_offshore_empty_string_weather_window_id_does_not_clobber_existing`
- `test_update_farm_is_offshore_rejects_non_bool`
