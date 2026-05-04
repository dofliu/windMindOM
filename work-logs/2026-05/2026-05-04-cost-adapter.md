# 2026-05-04 — Cost adapter + schemas（WMOM-20260504-06）

> Session 類型：實作 / refactor / 設計
> Session 長度：中
> 主導：Claude（劉老師指示「繼續做-06」）
> 結果：adapter.py + cost_schemas.py 就位，4 個 test refactor 省 326 行，整 cost module 29 PASS + 1 XFAIL

---

## 1. Session 目標

WMOM-20260504-06 — M2 第 6 個 issue。把 4 engine submodule done 之後，需要：

1. **Adapter**：把 K13 dataset 載入 + result→response 的轉換邏輯收斂到一個地方
   （4 個 test 內重複的 ~200 行 `build_*_params` 是 code smell）
2. **Schemas**：定義 pydantic request / response model，給 -07 FastAPI router 用
3. **Refactor**：4 個 test 改用新 loader，不破壞既有 21 tests pass

雖然 issue title 寫 "adapter"，實質上含 3 件事的綜合：refactor + 抽象層設計 + 為 API 預備。

## 2. 實際完成

### 2.1 主要工作

- ✅ 寫 `modules/cost/adapter.py`（393 行）：
  - `EngineParams` 命名 dataclass（避免 6-tuple 順序記不住）
  - `load_k13_engine_params(stochastic=False)` — 統一 loader，stochastic flag 控制是否
    加 ±20%/30% bounds（給 monte_carlo 用）
  - `cost_result_to_response()` / `lcoe_result_to_response()` /
    `mc_result_to_response()` / `vf_result_to_response()` — engine result → API dict
  - `K13_FTC_DEFAULTS` / `K13_MC_EQUIPMENT` / `DEFAULT_DATA_DIR` 常數
- ✅ 寫 `modules/cost/schemas/cost_schemas.py`（198 行）：
  - Request: `CostForecastRequest` / `LCOERequest` / `MonteCarloRequest` / `VarFluctRequest`
  - Response: `CostForecastResponse` / `SeasonalCostBreakdown` / `LCOEResponse` /
    `MonteCarloResponse` / `PercentileStats` / `VarFluctResponse` / `YearResultResponse` /
    `VarFluctSummaryResponse` / `BathtubConfig`
  - `DatasetName = Literal["k13"]` — M2 PoC 限定 k13；之後可擴 user-upload
- ✅ Refactor 3 個 test 用新 loader：
  - `test_k13_equivalence.py`: 362 → 155 行（**省 207**）— pinned constants 保留，移除 build_all_params
  - `test_monte_carlo.py`: 370 → 203 行（**省 167**）— 加 mc_params fixture，build_mc_params 拿掉
  - `test_var_fluct.py`: 402 → 243 行（**省 159**）— build_k13_params 拿掉
  - `test_waiting_time.py`: **不動**（讀 metocean CSV 是 waiting_time 專屬流程，不重複）
- ✅ 寫 `modules/cost/tests/test_adapter.py`（207 行）：9 tests 全 PASS
  - K13 loader counts + key 數字
  - stochastic=False/True 的 bounds 差異
  - 4 個 result→response 轉換 + pydantic round-trip
  - Adapter 跑出來的 baseline == ECN pinned baseline（regression gate）
- ✅ 整個 cost module pytest：**29 PASS + 1 XFAIL**（4.17s）

### 2.2 卡住或延後的事

- 第一次 refactor `test_k13_equivalence.py` 不小心連 pinned constants 一起刪了 →
  test fail，立即補回；之後 refactor 其它 test 就有經驗，先確認 pinned 區段邊界
- `test_load_k13_returns_engine_params` 的 K13 turbine 資料寫成 5000 kW（直覺猜的），
  實際是 4000 kW（K13 是 4 MW turbine），改正

### 2.3 重大決策

- **Adapter 不重新設計 schema**，鏡像 ECN dataclass 的欄位 → 確保 migration bit-perfect
- **`stochastic` 為 bool flag**，不分兩個 function — 90% 邏輯重複，flag 比較乾淨
- **`test_waiting_time.py` 不動** — 它讀 CSV 而非 engine params build，與 adapter
  scope 不同；強行 refactor 會引入錯誤抽象
- **Pydantic schema 用 Field with description** — 為 -07 OpenAPI doc 預備

## 3. 產出清單

### 新增檔案

- `modules/cost/adapter.py`（393 行）— K13 loader + result→response converter
- `modules/cost/schemas/cost_schemas.py`（198 行）— pydantic request / response models
- `modules/cost/tests/test_adapter.py`（207 行）— 9 tests
- `work-logs/2026-05/2026-05-04-cost-adapter.md`（本檔）

### 修改檔案

- `modules/cost/tests/test_k13_equivalence.py`（362→155，省 207）
- `modules/cost/tests/test_monte_carlo.py`（370→203，省 167）
- `modules/cost/tests/test_var_fluct.py`（402→243，省 159）
- `ISSUES.md`（WMOM-06 done；統計 +1 done）
- `STATUS.yaml`（M2 progress 75→85）

### Code metrics

| 類別 | 改前 | 改後 | Delta |
|------|------|------|-------|
| Tests | 1439 行 | 1113 行 | -326（refactor 省下） |
| Adapter | 0 | 393 | +393 |
| Schemas | 0 | 198 | +198 |
| **Net** | **1439** | **1704** | **+265** |

淨加 265 行，但：
- 重複 code 完全消除（4 處 build_*_params → 1 處 load_k13_engine_params）
- 新增 9 個 adapter test 涵蓋雙向轉換
- Pydantic schema 為 -07 FastAPI 預備
- 整 cost module 21 → 30 tests，皆 PASS

### 動了狀態的 issue

- WMOM-20260504-06: 新建 + done

## 4. 下次怎麼接手

下一個 issue：**WMOM-20260504-07 — FastAPI cost router**

```
modules/cost/routers/cost_router.py:
  POST /api/cost/forecast    — CostForecastRequest → CostForecastResponse
  POST /api/cost/lcoe         — LCOERequest → LCOEResponse
  POST /api/cost/monte-carlo  — MonteCarloRequest → MonteCarloResponse
  POST /api/cost/var-fluct    — VarFluctRequest → VarFluctResponse
```

Schemas 已就位，adapter 已就位，只需要：
1. 寫 4 個 router endpoint 串 adapter
2. 寫 `modules/cost/tests/test_cost_api.py`（用 FastAPI TestClient）
3. 把 router 掛進 windMindOM 主 FastAPI app（modules/monitoring/server/?）

估時：~30-45 分鐘。

之後（-08）frontend `/admin/cost/`，估 1-2 天。

阻擋項：無。

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 設計 schema 架構（思考 + 寫設計 sketch） | 10% |
| 寫 adapter.py（4 個 result→response + K13 loader） | 30% |
| 寫 cost_schemas.py（10 個 pydantic models） | 15% |
| Refactor 3 個 test（含一輪 pinned constants 補回 debug） | 25% |
| 寫 test_adapter.py（9 tests） | 15% |
| 收尾（ISSUES / STATUS / work-log / commit） | 5% |

## 6. 學到的事

- **Refactor 的 code smell 識別**：4 個 test 內 200+ 行幾乎一字不差的 `build_*_params`
  是經典抽象 missing。但要等 4 個 use case 全寫完再抽，不能太早；早抽會錯抽。
- **`stochastic: bool` flag** 比 `build_for_cost_cal()` / `build_for_mc()` 雙函數
  乾淨 — 讓 caller 決定是否要 stochastic bound，不在 loader 強制
- **Pydantic schema 與 engine dataclass 解耦**的好處：engine 維持 ECN-compatible
  bit-perfect，schema 自由設計給 windMindOM API；翻譯層在 adapter，**單向依賴**
- **Pinned constants 不能順手刪**：refactor 時要識別「測試 oracle」vs「測試 fixture
  builder」— 前者必須保留，後者可換
- **K13 turbine 是 4 MW 不是 5 MW** — 直覺與資料對不上，test 跑出來才看到

## 7. Open questions（park）

- `EngineParams` dataclass 是否需要支援 user-supplied dataset（非 K13）？M2 PoC
  不做；M3+ 客戶實際 dataset 進來時再開 issue
- `cost_request_to_engine()` adapter 還沒寫（POST request → engine params）—
  等 -07 寫 router 時再加，因為 router 會 call「`load_k13_engine_params(req.dataset)`」
  這一行為主，不太需要獨立 adapter function
- 是否要把 `K13_FTC_DEFAULTS` / `K13_MC_EQUIPMENT` 也搬到 K13 JSON 裡？目前是
  hard-coded constant；長期看應該入 dataset。M2 不做。
