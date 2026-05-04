# ECN Engine Inventory & Migration Plan

> 對應 issue：WMOM-20260504-01
> 用途：盤點 ECN 4 個 engine submodule 的內容、依賴與遷移計畫，**讓後續 migration issue
> 知道做什麼、按什麼順序、要驗證什麼**
> Source：`../ECN/backend/app/engine/`
> 對應 baseline 數字：[`ecn_k13_baseline.md`](ecn_k13_baseline.md)

---

## TL;DR

ECN engine 共 ~3,000 行 Python，分 4 submodule：

| Submodule | Lines | 對外依賴 | 移植順序建議 | 估時 |
|---|---|---|---|---|
| `waiting_time/` | 1,059 | 無（pure compute） | 1 | 0.5 天 |
| `cost_cal/` | 957 | 無（pure compute） | 2 | 1-1.5 天 |
| `monte_carlo/` | 674 | 依賴 `cost_cal` | 3 | 0.5 天 |
| `var_fluct/` | 360 | 無 | 4 | 0.5 天 |

**好消息**：engine 之間 **沒有引用 ECN 的 `app.models` 或 `app.schemas`**（完全純函數庫），
所以 migration 是「複製 + 改 import path + 跑 K13 比對」，**不用碰 SQLAlchemy / FastAPI**。

**邊界**：windMindOM **只移 engine**，不移：
- `app/models/`（ECN 的 SQLAlchemy ORM）→ windMindOM 用自己的 schema
- `app/routers/`（ECN 的 FastAPI 路由）→ windMindOM 自己設計 cost API
- `app/database.py` / `app/config.py` / `app/main.py` → 不適用
- `app/utils/` → 視情況，需要時 case-by-case 拉

---

## 1. `cost_cal/` — 核心成本計算（M2 主菜）

**位置**：`../ECN/backend/app/engine/cost_cal/`
**總行數**：957 行 (8 檔)
**對應 K13 metric**：availability、revenue loss、repair cost、total effort、cost per kWh

### 1.1 檔案清單

| File | Lines | 角色 |
|---|---|---|
| `__init__.py` | 16 | 公開 `run_cost_calculation` 與 `CostCalResult` |
| `data_classes.py` | 214 | 輸入/輸出 dataclass（WindFarmParams、ComponentParams、SeasonResult、CostCalResult…） |
| `corrective.py` | 251 | Corrective maintenance cost（最大塊；含 vessel mob、equipment、material、labour、revenue loss） |
| `preventive.py` | 136 | Preventive maintenance cost（依季節排程） |
| `fixed.py` | 31 | 固定成本（保險、場地、監控） |
| `revenue_loss.py` | 74 | Annual energy production + revenue loss 計算 |
| `lcoe.py` | 76 | LCOE = (CAPEX + OPEX_NPV) / Energy_NPV |
| `aggregator.py` | 159 | 把以上加總成 4-季 → 全年 → CostCalResult 總入口 |

### 1.2 內部依賴（mermaid 文字版）

```
data_classes.py  ←  (其他全部都 import)
       ↑
       │
corrective.py ─┐
preventive.py ─┼→ aggregator.py ─→ run_cost_calculation()  (公開 API)
fixed.py      ─┤
revenue_loss.py┤
lcoe.py       ─┘
```

### 1.3 對 ECN 其他層的依賴

**無**（grep 結果：所有 import 都是 `from app.engine.cost_cal.X` 或 stdlib + numpy/pandas）

### 1.4 Migration mapping

| ECN 路徑 | windMindOM 路徑 |
|---|---|
| `app/engine/cost_cal/*.py` | `modules/cost/engine/cost_cal/*.py` |
| `data/demo/k13_*.{json,csv}` | `modules/cost/data/demo/k13_*.{json,csv}` |
| `tests/test_cost_cal_engine.py` | `modules/cost/tests/test_k13_equivalence.py`（改名 + import path 改） |

**Import 改寫**：`from app.engine.cost_cal.X` → `from modules.cost.engine.cost_cal.X`

### 1.5 驗證 SOP

K13 執行後比對 [`ecn_k13_baseline.md`](ecn_k13_baseline.md) §2.1 與 §2.2 的所有
數字，浮點誤差 < 1e-6。任何 deviation 超過 → block merge。

---

## 2. `waiting_time/` — 氣象等待時間計算

**位置**：`../ECN/backend/app/engine/waiting_time/`
**總行數**：1,059 行 (7 檔)
**對應 K13 metric**：waiting time polynomial coefficients、weather window 統計

### 2.1 檔案清單

| File | Lines | 角色 |
|---|---|---|
| `__init__.py` | 264 | 公開 API + 高層 orchestrator（**檔頭較重**，注意） |
| `weather_windows.py` | 203 | Weather window 計算（Hs / Tp / wind 門檻） |
| `waiting_calculator.py` | 194 | 給定 mission time → 等待 distribution |
| `season_filter.py` | 157 | 按季分類 metocean data |
| `data_processor.py` | 99 | metocean CSV 載入 + 預處理 |
| `power_calculator.py` | 74 | Power curve 計算 |
| `polynomial_fitter.py` | 68 | 等待時間 → polynomial coefficients（給 cost_cal 用） |

### 2.2 對 cost_cal 的關係

**單向**：waiting_time 計算出來的 polynomial 係數**寫進 `k13_waiting_time_coefficients.json`**，
cost_cal 從 JSON 讀進來當 input；engine 之間**不直接 import**。

意思是：waiting_time 與 cost_cal 可以獨立開發 + 獨立測試。

### 2.3 Migration mapping

| ECN 路徑 | windMindOM 路徑 |
|---|---|
| `app/engine/waiting_time/*.py` | `modules/cost/engine/waiting_time/*.py` |
| `tests/test_waiting_time_engine.py` | `modules/cost/tests/test_waiting_time.py`（沿用） |

### 2.4 驗證 SOP

K13 metocean → polynomial 係數後比對 ECN test 內 expected coefficients。

---

## 3. `monte_carlo/` — 風險評估（依賴 cost_cal）

**位置**：`../ECN/backend/app/engine/monte_carlo/`
**總行數**：674 行 (4 檔)
**對應 K13 metric**：cost_per_kwh 抽樣分布、p10/p50/p90、tornado / sensitivity、LCOE

### 3.1 檔案清單

| File | Lines | 角色 |
|---|---|---|
| `__init__.py` | 12 | 公開 `run_monte_carlo`、`MonteCarloResult`、stat helpers |
| `runner.py` | 122 | Monte Carlo orchestrator（call `run_cost_calculation` n 次） |
| `sampler.py` | 198 | 從 distributions 抽 fault rate / repair time / cost 等參數 |
| `statistics.py` | 342 | percentiles / CDF / tornado / sensitivity |

### 3.2 依賴

**`cost_cal/`**：每次 iteration 都 call `run_cost_calculation`。

```python
# runner.py 內部
from app.engine.cost_cal.aggregator import run_cost_calculation
```

→ 必須先移完 cost_cal 才能移 monte_carlo。

### 3.3 Migration mapping

| ECN 路徑 | windMindOM 路徑 |
|---|---|
| `app/engine/monte_carlo/*.py` | `modules/cost/engine/monte_carlo/*.py` |
| `tests/test_monte_carlo.py` | `modules/cost/tests/test_monte_carlo.py`（沿用，需固定 random seed） |

### 3.4 驗證 SOP

固定 random seed 重跑 K13 n=100，要：
1. Deterministic 結果與 cost_cal §1.5 一致
2. Sample 分布的 mean/std 與 ECN 跑出的相同（若 seed 相同）
3. p10 < p50 < p90（單調性）
4. LCOE 與 baseline §2.3 一致（72.94 EUR/MWh）

---

## 4. `var_fluct/` — 變動性與生命週期（最簡單）

**位置**：`../ECN/backend/app/engine/var_fluct/`
**總行數**：360 行 (3 檔)
**對應 K13 metric**：bathtub failure rate（infant mortality + random + wear-out）；
component lifecycle 模擬

### 4.1 檔案清單

| File | Lines | 角色 |
|---|---|---|
| `__init__.py` | 5 | 公開 |
| `bathtub.py` | 76 | Bathtub failure rate function（3 段：infant / random / wear-out） |
| `calculator.py` | 279 | 多年 component-by-component 模擬 |

### 4.2 依賴

**無對外依賴**（自己有 `BathtubParams` 等 dataclass）。

### 4.3 Migration mapping

| ECN 路徑 | windMindOM 路徑 |
|---|---|
| `app/engine/var_fluct/*.py` | `modules/cost/engine/var_fluct/*.py` |
| （無對應 test，需新建） | `modules/cost/tests/test_var_fluct.py`（新增 K13 fixture） |

### 4.4 驗證 SOP

ECN 沒有 var_fluct 專屬 test，但 monte_carlo test 間接驗證了 var_fluct 的
bathtub 是否被正確 call。Migration 後可以加一個直接的 unit test。

---

## 5. 推薦移植順序

```
WMOM-20260504-02  →  waiting_time （0.5 天，獨立、簡單，先暖身）
WMOM-20260504-03  →  cost_cal     （1-1.5 天，主菜，K13 baseline 主驗證）
WMOM-20260504-04  →  monte_carlo  （0.5 天，依賴 cost_cal）
WMOM-20260504-05  →  var_fluct    （0.5 天，最簡單，最後做）
```

**完整移植估時**：3-3.5 天（含 K13 numerical equivalence 驗證）。

加上後續：
- `WMOM-20260504-06`：Cost adapter（windMindOM canonical schema ⇄ ECN engine dataclass）
- `WMOM-20260504-07`：FastAPI router for cost endpoints（POST /api/cost/forecast、GET /api/cost/ledger）
- `WMOM-20260504-08`：Frontend `/admin/cost/`（budget view + ledger + LCOE dashboard）

完整 M2 估時：1.5-2 週（與 ROADMAP 「Month 2 = Cost module」一致）。

---

## 6. Migration 風險與緩解

### 6.1 高風險：K13 數字對不上

**機率**：中（純函數移植不該對不上，但 numpy version drift / float precision 可能造成微差）
**緩解**：
- 嚴格 < 1e-6 浮點誤差作為 merge gate
- 比對失敗時逐 layer 回退（先比 corrective 一塊、再加 preventive…）

### 6.2 中風險：Engine 內部隱性依賴 ECN config

**機率**：低（grep 沒看到 `app.config` import）
**緩解**：
- 移植前重 grep `from app\.` 確認沒新增的 cross-import
- Pin `numpy` / `pandas` 版本（同 ECN `requirements.txt`）

### 6.3 中風險：waiting_time 計算結果與 cost_cal input mismatch

**機率**：低（兩者透過 JSON 串接，不直接 import）
**緩解**：
- 不重新計算 waiting_time coefficients；直接用 ECN 的 `k13_waiting_time_coefficients.json`
- 純驗證 windMindOM waiting_time engine 跑出來的係數 == JSON 內的數字

### 6.4 低風險：ECN 之後改 engine 我們追不上

**機率**：低（ECN repo 已 80% 完成，主要功能凍結）
**緩解**：
- Migration 後 windMindOM 的 cost engine **就是自己 fork**，不再 sync ECN
- ECN 若有重大 bug fix（< M5 期間），人工 cherry-pick 進來；不做 auto-sync

---

## 7. 不移的東西（明確 boundary）

| ECN 路徑 | 為什麼不移 | windMindOM 對等做法 |
|---|---|---|
| `app/models/*.py`（13 個 SQLAlchemy model） | ECN ORM 與 windMindOM schema 不對齊 | windMindOM 自己設計 cost-related schema 在 `shared/schemas/` |
| `app/routers/*.py`（8 個 FastAPI router） | ECN API 設計不對應 windMindOM 的 product flow | windMindOM 自己設計 cost API 在 `modules/cost/routers/` |
| `app/database.py` / `config.py` / `main.py` | infra 層，已有對應在 windMindOM | 沿用 windMindOM 既有 |
| `app/dependencies.py` / `auth.py` | ECN 自己 user / auth | windMindOM 已有 auth flow |
| `frontend/`（Next.js） | windMindOM 用 React，不一樣 | windMindOM 自己做 cost UI |
| `deploy/` / `DEPLOY_GCP.md` | windMindOM 自有 docker-compose | 不適用 |

---

## 8. 後續 issue 模板（給下個 session 直接抄）

```markdown
### WMOM-20260504-02 — `engine/waiting_time/` 移植 + ECN test 沿用

- **Status**: open
- **Milestone**: M2
- **Priority**: high
- **Estimate**: 0.5 工作天
- **Depends on**: WMOM-20260504-01 (done)
- **Description**:
  把 `../ECN/backend/app/engine/waiting_time/` 7 檔複製到 `modules/cost/engine/waiting_time/`，
  改 import path（`from app.X` → `from modules.cost.engine.X`），跑 ECN 既有
  test 確認結果一致（< 1e-6 誤差）。
- **Deliverable**:
  - `modules/cost/engine/waiting_time/*.py`（7 檔）
  - `modules/cost/tests/test_waiting_time.py`（從 ECN 沿用 + import path 修正）
  - `modules/cost/data/demo/k13_metocean.csv`、`k13_weather_windows.json`、
    `k13_waiting_time_coefficients.json`
  - 跑通 `python -m pytest modules/cost/tests/test_waiting_time.py -v` 全 pass
- **Reference**:
  - `docs/legacy/ecn_engine_inventory.md` §2 (waiting_time)
  - `docs/legacy/ecn_k13_baseline.md` §2.4 (waiting_time baseline)
```

（其他 issue 模式類似，每個 module 一張）
