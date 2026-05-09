# 2026-05-09 — Inventory API（WMOM-20260509-04）

> Session 類型：實作（FastAPI router + schemas）
> Session 長度：短（A1/A2/A3 同日連續第四輪）
> 主導：Claude
> 結果：**M4 backend 全收**（A1+A2+A3+A4 backend 主菜 4/4 done）；8 endpoints + 28 tests pass + 全 403 tests 0 regression。

---

## 1. Session 目標

依 ISSUES.md WMOM-20260509-04 acceptance：

- `modules/workflow/schemas/inventory_schemas.py`：InventoryItemResponse / AdjustmentRequest 等
- `modules/workflow/routers/inventory_router.py`：6 endpoints + 2 warehouse 額外
- safety_stock 警示：`stock_new + stock_used < safety_stock` flag warn
- mount 進 `monitoring/server/app.py`
- 25+ pytest pass + adjustment endpoint 連同 audit log 落地

---

## 2. 實際完成

### 2.1 新檔（3）

- `modules/workflow/schemas/inventory_schemas.py`（~190 行）：
  - 5 request body：CreateWarehouseRequest / CreateInventoryItemRequest / UpdateInventoryMetadataRequest / AdjustInventoryRequest（+ AdjustInventoryResult 收 item + log）
  - 6 response model：WarehouseResponse / WarehouseListResponse / InventoryItemResponse（含 `total_available` / `below_safety` 兩個 `@computed_field` ）/ InventoryItemListResponse / AdjustmentLogResponse / AdjustmentLogListResponse
- `modules/workflow/routers/inventory_router.py`（~290 行）：8 endpoints + repo factory injection
- `modules/workflow/tests/test_inventory_api.py`（~470 行 / 28 tests）

### 2.2 改檔（3）

- `modules/workflow/routers/__init__.py`：加 `inventory_router` export + 完整 endpoint table
- `modules/workflow/schemas/__init__.py`：加 11 個新 schema export
- `modules/monitoring/server/app.py`：mount `inventory_router`

### 2.3 8 endpoints

**Inventory（6 主菜）**：
| Method | Path | 用途 |
|---|---|---|
| POST | `/api/workflow/inventory` | create item（farm_id+sku unique → 409） |
| GET | `/api/workflow/inventory` | list + safety filter + pagination |
| GET | `/api/workflow/inventory/{id}` | detail（含 below_safety / total_available 計算欄位）|
| PATCH | `/api/workflow/inventory/{id}` | update metadata（不動 stock）|
| POST | `/api/workflow/inventory/{id}/adjust` | 手動 +/- 異動 + atomic audit log |
| GET | `/api/workflow/inventory/{id}/adjustments` | audit log 反序 |

**Warehouse（2 額外）**：
| Method | Path | 用途 |
|---|---|---|
| POST | `/api/workflow/warehouses` | create warehouse |
| GET | `/api/workflow/warehouses` | list（default 在前）|

### 2.4 驗收

- **28 new tests pass** in 1.76s
- **全 workflow 346 pass**（M3 173 + A1 60 + A2 58 + A3 27 + A4 28）
- **cost+workflow 403 pass + 1 xfailed (existing) — 0 regression**

---

## 3. 設計決策

### 3.1 InventoryItemResponse 加 `@computed_field`

`below_safety` 與 `total_available` 是兩個常用的派生屬性，前端每張 row 都要顯示。讓 backend 計算，前端不重複邏輯：

```python
@computed_field
@property
def below_safety(self) -> bool:
    return self.stock_new + self.stock_used < self.safety_stock
```

pydantic v2 `@computed_field` 直接序列化進 JSON。前端不需自己計算，避免「frontend 計算 vs backend list 已 filter」的不一致。

### 3.2 加 2 個 warehouse endpoints（超出 ISSUES spec）

ISSUES.md 只列 6 inventory endpoints。但 `create_inventory_item` 必須帶 `warehouse_id`，前端要建料件前必須先有 warehouse — 沒 warehouse endpoint 就要 ops 直接動 DB。

加 2 個基本 endpoints（POST create + GET list）讓 frontend 自足。`get default warehouse` 已在 repo 有 helper，未來 frontend 需要時再加 endpoint。

### 3.3 PATCH metadata 用 `model_dump(exclude_unset=True)` 部分更新

只更新傳入的欄位，沒傳的維持原值。pydantic v2 `exclude_unset=True` 配合 repo 的 `update_metadata(**payload)` kwargs 展開，乾淨支援 partial update 而不需在 schema 內手動寫 None checks。

### 3.4 Adjust 失敗的錯誤映射

- `StockAdjustmentError("not found")` → 404（item 不存在）
- `StockAdjustmentError(其他)` → 422（reason 空 / safety_stock 負）
- `InsufficientStock` → 409（扣到負數，state 衝突）

語意正確：404=資源不存在 / 422=請求格式錯 / 409=資源狀態衝突。

### 3.5 list_warehouses 走 raw SQL

`InventoryRepository` 沒提供 `list_warehouses` 方法（caller 用量低）。Router 直接用 `repo._sessionmaker()` + `WarehouseORM` query，避免另開一個只用 1 次的 repo method。Trade-off：稍微 leak 抽象，但避免 over-engineering。

### 3.6 unit_cost Decimal precision

SQLAlchemy `Numeric(12, 4)` 保留 4 位小數，所以 "450.00" 寫進 DB 讀出來是 "450.0000"。Test 用 `Decimal(s) == Decimal("450.00")` 比值不比字串。

---

## 4. M4 進度

- ✅ A1 domain (60 tests)
- ✅ A2 repository + atomic dispatch (58 tests)
- ✅ A3 MaterialRequest API + signoff 整合 (27 tests)
- ✅ **A4 Inventory query + adjustment API** (28 tests) ← 剛完成
- 🎉 **M4 backend 4 issue 全 done**
- ⬜ A5 cost ledger 整合（next）
- ⬜ A6 material frontend
- ⬜ A7 inventory frontend
- ⬜ A8 reporting backend
- ⬜ A9 reporting frontend
- ⬜ A10 E2E lifecycle test

**M4 backend 累計**：4 個 issue / 173 new tests / 8 + 9 + 8 + 6 = ~31 endpoints / atomic 雙寫 + cost ledger schema + 完整 lifecycle 鏈路（建料件 → 開單 → 簽核 → 出庫 → 簽收 → 完工 → cost ledger）。

---

## 5. Commit

`feat(#WMOM-20260509-04): inventory query + adjustment API (M4 A4)` — files & line count 看 git
