# 2026-05-18 WMOM-20260510-01 Part C — Farm `is_offshore` backend field

> **Issue**：WMOM-20260510-01 Part C — Farm `is_offshore` 屬性
> **Branch**：`claude/issue-WMOM-20260510-01C-2026-05-18`
> **Goal**：M5 demo polish 第三步 — 讓 farm config 帶 `is_offshore` 旗標，
> 後續 work order 的 `start_work` weather window 行為可依此自動決定（不再手動勾）。

---

## 1. 為什麼今天做這個

依 2026-05-15 Part B 完工後的進度：
- Part A backend dev mode ✅ (2026-05-14)
- Part B frontend mock login ✅ (2026-05-15)
- **Part C farm `is_offshore` field ← 今日**
- Part D farm 設定頁 checkbox + start_work 自動 weather window（next session）

Part C 是純 backend 工作，只需動 `FarmConfig` dataclass、SQLite schema、`farms_router`，
不會碰 frontend 行為（除了 TS type 同步）。Part D 改 frontend UI 更穩，分兩個 PR 較容易 review。

---

## 2. Scope 與設計決策

### 2.1 SQLite schema migration 策略

`farms` 表是既有 schema（已 3 個 farm 在 production 用）。加新 column 必須 backward-compatible。

選用方案：**`_init_db()` 內加 `_migrate_schema()` 偵測缺欄就 `ALTER TABLE ADD COLUMN`**。

理由：
- repo 目前無 alembic / yoyo migration 工具，全靠 `CREATE TABLE IF NOT EXISTS`
- SQLite `ALTER TABLE ADD COLUMN` 是 schema-cheap（O(1)），不掃資料
- 既有資料 default `is_offshore = 0`（false），符合「劉老師 demo 用陸上」需求
- 避免引入 alembic — Part C 不該擴張 scope

### 2.2 為什麼 default = false（陸上）

劉老師 demo 用 3 個陸上 farm，加 1 個「彰化離岸風場台電」設成 true。Default false 確保
**既有 farm 升級後不會誤觸發 offshore weather-window 卡關**（避免 silent regression）。

### 2.3 `update_farm()` 為什麼要加 `is_offshore` 到 `field_map`

不加的話 PATCH `/api/farms/{id}` 收 `is_offshore` 會 silently ignore，UX 很糟。
SQLite 用 INTEGER 0/1 儲存 bool，read 回來透過 `from_row()` 還原成 Python bool。

### 2.4 `clone_farm()` 要不要繼承 `is_offshore`

要 — clone 是「複製一份新的同性質 farm」，is_offshore 是 farm 的本質屬性，應跟著走。

### 2.5 Frontend 改動最小化

只更新 `FarmInfo` interface 加 `is_offshore: boolean`。不動任何元件邏輯。
Part D 才動 FarmSelector 顯示「離岸」tag + Farm 管理頁的 checkbox。

---

## 3. 檔案異動（規劃）

### 3.1 修改

```
M modules/monitoring/server/farm_registry.py
  - FarmConfig 加 `is_offshore: bool = False`
  - to_dict() 自動帶 is_offshore（dataclass 自動 enumerate）
  - from_row() 讀 is_offshore（INTEGER 0/1 → bool）
  - _init_db() 加 _migrate_schema() 偵測 + ALTER TABLE
  - create_farm() 加 is_offshore 參數 + INSERT 進 DB + config.json
  - update_farm() field_map 加 is_offshore（bool → INTEGER）
  - clone_farm() 繼承 source.is_offshore

M modules/monitoring/server/routers/farms.py
  - POST `/api/farms` 接受 is_offshore（default false）
  - PATCH `/api/farms/{id}` 接受 is_offshore

M frontend/services/workOrderService.ts
  - FarmInfo 加 `is_offshore: boolean`

M frontend/components/FarmSelector.tsx
  - Farm interface 加 `is_offshore: boolean`（TS 同步，UI 暫不顯示）
```

### 3.2 新增

```
+ modules/monitoring/tests/test_farm_registry_is_offshore.py
  - 5+ test: schema migration / create / update / clone / list/get round-trip
```

### 3.3 更新

```
M ISSUES.md         Part C 標 in_progress（合併後 → done）
M STATUS.yaml       progress / last_updated
```

---

## 4. TODO（implementation checklist）

- [x] FarmConfig 加 is_offshore（+ `_row_get_int` 安全 column 讀取輔助）
- [x] _init_db() 加 schema migration（ALTER TABLE ADD COLUMN if missing）+ 雙路徑設計文件
- [x] create_farm / update_farm / clone_farm / from_row 接 is_offshore
- [x] farms.py router POST/PATCH 接受 is_offshore + **PATCH 加正規化** 與 POST 對齊
- [x] 寫 tests/test_farm_registry_is_offshore.py（14 tests：migration + CRUD + clone + router POST/PATCH 正規化）
- [x] frontend FarmInfo + FarmSelector.Farm type 同步加 `is_offshore: boolean`
- [x] backend pytest zero new regression（3 條 numpy 精度漂移 pre-existing）
- [x] frontend tsc + vite build zero error（737 modules / 860 KB bundle）
- [x] code-reviewer 跑 + 採納 2 must-fix + 4 should-fix
- [x] 更新 STATUS.yaml + ISSUES.md
- [ ] commit + push + PR

---

## 5. 卡點 / 風險

- **既有 production `farms.db`** 不在 repo（gitignored）；migration 必須在 runtime 自動偵測 + 適配 → ✅ `_migrate_schema` PRAGMA + ALTER TABLE 覆蓋此情境並有 test 驗證
- **`is_offshore` 從 0/1 還原成 bool**：sqlite3.Row 取出來是 int，要顯式 `bool(row[...])` → ✅ 用 `_row_get_int` + `bool()` ternary 處理 None
- **Part D 還沒做** — Part C 完成後 frontend 看不到視覺改變，只有 API contract 多一欄

---

## 6. Code review 採納

Code-reviewer subagent 找出 **2 must-fix + 5 should-fix + 3 nice-to-have**。

**Must-fix 全採納（2/2）**：
1. ✅ `update_farm` 的 `bool("false") is True` 陷阱 + comment/test docstring 與實作不一致
   → 刪除「支援字串 boolean」的宣稱（registry 層只接受 bool/int），改在 comment 明示「字串 boolean 不支援,router 端應先正規化」
2. ✅ PATCH router 不對 `is_offshore` coerce，與 POST 行為不一致
   → PATCH handler 加 `body = {**body, "is_offshore": bool(body["is_offshore"])}` 與 POST 對齊；加 2 個 router regression test 鎖定行為

**Should-fix 採納 4/5**：
3. ✅ POST docstring 加 `is_offshore`；PATCH docstring 改為列出全部支援欄位
4. ✅ `test_update_farm_accepts_truthy_values` rename → `test_update_farm_accepts_int_0_1`；docstring 改為精確描述「字串 boolean 不支援」+ assertion 改 int 0/1 + Python bool round-trip
5. ✅ `_migrate_schema` docstring 加「雙路徑設計」說明（新 DB 走 CREATE TABLE / 舊 DB 走 ALTER）+ 維護原則
6. ✅ `_row_get` rename → `_row_get_int`，回傳型別 `Optional[int]`（比原 `object` 精確）
7. ✅ test_migrate_schema_adds_missing_column 加 lazy import comment 解釋為何函式內才 import FarmRegistry

**Should-fix 暫不採納（1/5）**：
- ⏭ `sys.path.insert` module level 污染：pre-existing pattern（既有 `test_broker_snapshot_dedupe.py` 同樣寫法），單動本 test 檔會造成 inconsistent；登記為 future cleanup

**Nice-to-have 全暫不採納（0/3）**：
- ⏭ `datetime.now()` 缺 tz：pre-existing 全 repo 問題，獨立 issue 處理
- ⏭ 三個 frontend Farm-like interface 合併：Part D 結束後再評估技術債清理
- ⏭ test 直接戳 `_get_conn()`：12 行 white-box 不值得抽 helper
