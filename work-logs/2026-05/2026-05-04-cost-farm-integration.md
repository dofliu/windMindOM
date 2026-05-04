# 2026-05-04 — Cost ↔ Farm config 整合（WMOM-20260504-10）

> Session 類型：實作
> Session 長度：中
> 主導：Claude (M3 第一週插入工作)
> 結果：cost engine 從「pure K13 hard-code」升級為「farm-aware overlay」，frontend 可選 dataset

---

## 1. Session 目標

把 M2 cost module 與 M1 farm registry 接起來：

- 規劃缺口：`load_k13_engine_params()` 完全 hard-code K13（130×4MW 北海離岸），與 monitoring 的 14 台模擬風機（Z72/2MW/台中港）脫鉤
- 客戶 demo 會被問倒：「我風場 30 台 V164，你算 130 台 K13 給我看幹嘛？」
- 解法：K13 baseline overlay 機制 — K13 元件/設備/PM/fixed_cost 全沿用，僅依 farm-specific overrides 替換 wind_farm 級參數

---

## 2. 實際完成

### 2.1 主要工作

- ✅ 設計 `cost_inputs.json` schema（farm-level overlay）+ `data/farms/{farm_id}/` 兩個 demo
  - `台中港曲風場/cost_inputs.json` — 14 × 2 MW Z72 onshore（對應 monitoring 的 active farm）
  - `彰化離岸風場台電/cost_inputs.json` — 7 × 8 MW 大型 offshore（對齊真實台電示範案）
- ✅ `adapter.py` 新增 `FarmDatasetMeta` + `load_engine_params_from_farm(farm_id, stochastic, farm_registry=None)`
  - 三層查找：cost_inputs.json → FarmRegistry derived overrides → K13 fallback + warning
- ✅ `schemas/cost_schemas.py`：dataset 從 `Literal["k13"]` 改 `str`（支援 `"k13"` / `"farm:{id}"`）+ 4 個 response 加 optional `dataset_meta`
- ✅ `cost_router.py`：`_resolve_dataset()` 統一處理 `k13` / `farm:{id}` / 未知值（404）
- ✅ Tests：
  - `test_adapter.py` 加 5 tests（farm overlay + fallback + meta + registry-derived）
  - `test_cost_api.py` 加 3 tests（farm dataset / unknown farm / dataset_meta）
- ✅ Frontend `CostPage.tsx` 加 dataset selector dropdown + costService 支援 dataset 字串
- ✅ `docs/product/MVP_ARCHITECTURE.md` 補節「Cost ↔ Farm config 整合」
- ✅ Code review fix（code-reviewer 找到 6 finding，6 個全處理）：
  - **Must-fix #1** farm_id path injection 防呆（router 422 / + 6 parametrize tests）
  - **Must-fix #2** lazy-import FarmRegistry Exception 分 ImportError vs others，加 `logger.warning`
  - **Must-fix #3** overlay 對 numeric 欄位做 type coerce（"14" → 14），無法 cast 直接 raise ValueError 而非帶字串繼續跑
  - **Should-fix #4** test warning 斷言改驗 `meta.source`（不依 warning wording）
  - **Should-fix #6** 切 dataset 時 reset 非 forecast 三 panel 的 data，避免顯示前一 dataset 的 stale 數字
  - **Nice-to-have #7** farm_overlay path 加 K13 onshore-mismatch warning，提醒 component / FTC / equipment 沿用 K13 (offshore reference)
- ✅ Code review #5（Strict Mode race / AbortController）開 follow-up issue WMOM-20260504-13

### 2.2 卡住或延後的事

- 無

### 2.3 重大決策

- 採 K13 overlay 而非「per-farm full dataset」 — scope 可控（M3 第一週 1-2 天），demo 已夠 personalize；第二個 OEM 客戶要差異 FTC 時再延伸

---

## 3. 產出清單

### 新增檔案

- `modules/cost/data/farms/README.md` — schema 說明
- `modules/cost/data/farms/台中港曲風場/cost_inputs.json`
- `modules/cost/data/farms/彰化離岸風場台電/cost_inputs.json`

### 修改檔案

- `modules/cost/adapter.py`（加 `FarmDatasetMeta` + `load_engine_params_from_farm` + `_apply_wind_farm_overrides`）
- `modules/cost/schemas/cost_schemas.py`（dataset → str, 4 response 加 optional `dataset_meta`）
- `modules/cost/routers/cost_router.py`（`_resolve_dataset` 統一處理 + meta 注入 response）
- `modules/cost/tests/test_adapter.py`（+5 tests）
- `modules/cost/tests/test_cost_api.py`（+3 tests）
- `frontend/services/costService.ts`（dataset 接 str + DatasetMeta type）
- `frontend/components/CostPage.tsx`（dataset selector + meta badge）
- `docs/product/MVP_ARCHITECTURE.md`（補節）

### 動了狀態的 issue

- WMOM-20260504-10: open → done

### 寫進 decision_log 的決策

- 暫無（schema 設計 ADR 寫進 MVP_ARCHITECTURE.md 即可，未到 architecture pivot 等級）

## 4. 下次怎麼接手

進 M3 主線：z72_etech 取設計 + Work Order CRUD（ROADMAP M3）。

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 設計 + 探索 | 15% |
| 寫程式 + tests | 60% |
| Frontend 整合 | 15% |
| 文件 + wrap-up | 10% |

## 6. 學到的事

- Overlay 模式比 full dataset replace 簡單很多 — K13 已有的 component / equipment / FTC / PM 全部沿用，只蓋 wind_farm 級參數，risk 最小
- FarmRegistry 與 cost dataset 用 farm_id 當 key 統一，未來 ledger / workflow 也能沿用此 ID
- 三層 fallback（cost_inputs → registry-derived → K13）讓 demo 即使資料半成品也能跑

## 7. Open questions（park）

- 第二個客戶要 Vestas V164 時，FTC table 是否需要 component-level override → M3 後評估
- M4 cost ledger（WMOM-20260504-11）會需要把 `farm_id` 串到 ledger entry 上 — 本次架構已準備好
