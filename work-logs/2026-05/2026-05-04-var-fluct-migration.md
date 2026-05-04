# 2026-05-04 — var_fluct engine 移植（WMOM-20260504-05）

> Session 類型：實作 / 移植（4 engine 收官）
> Session 長度：短（~25 分鐘）
> 主導：Claude（劉老師指示「繼續-05」）
> 結果：var_fluct 3 檔完全移植，9 tests 全 PASS（從零寫）。**4 個 ECN engine submodule 全部 done**

---

## 1. Session 目標

WMOM-20260504-05 — 移植最後一個 engine submodule。ECN 沒有對應 unit test，
從零寫 9 個 tests 涵蓋 bathtub curve + K13 var_fluct year-by-year calculation。

完成這個 issue 後，4 個 engine submodule（cost_cal / waiting_time / monte_carlo /
var_fluct）全部 ported + 100% pinned bit-perfect。

## 2. 實際完成

### 2.1 主要工作

- ✅ `cp ../ECN/backend/app/engine/var_fluct/*.py modules/cost/engine/var_fluct/`（3 檔，360 行）
- ✅ `sed` 改 import path
- ✅ Grep 確認無 ECN-specific 依賴
- ✅ 讀 `bathtub.py` + `calculator.py` 設計 test 範圍：
  - `bathtub_multiplier(year, params)` — 3 phase（early decay / mid constant / late peak）
  - `compute_bathtub_curve(params)` — 整年 list of dicts
  - `run_var_fluct_calculation(...)` — year-by-year，回傳 `VarFluctCalcResult`
    （`yearly: list[YearResult]` + `summary: VarFluctSummary`）
- ✅ 寫 `tools/pin_var_fluct.py` 取 baseline：
  - 20 年 bathtub 完整曲線
  - 6 個邊界 case（year 0/1/3/10/15/20）
  - K13 Year 1（early peak）/ 10（mid）/ 20（late peak）完整 YearResult
  - Summary（NPV + min/max + lifetime availability）
- ✅ 寫 `modules/cost/tests/test_var_fluct.py`：**9 tests 全 PASS**
  - `test_bathtub_default_curve` — 20 年曲線 bit-perfect
  - `test_bathtub_edges` — 6 個邊界 case bit-perfect
  - `test_bathtub_curve_helper` — `compute_bathtub_curve` 與 `bathtub_multiplier` 一致
  - `test_varfluct_lifetime_length` — yearly 必有 20 entries
  - `test_varfluct_year_1_pinned` — Year 1（early peak）14 個欄位 bit-perfect
  - `test_varfluct_year_10_pinned` — Year 10（mid life）availability 同 -03 cost_cal baseline
  - `test_varfluct_year_20_pinned` — Year 20（late peak）total_effort 比 Year 1 高 ~50%
  - `test_varfluct_summary_pinned` — Summary 10 個 field bit-perfect
  - `test_varfluct_year_index_consistency` — yearly[i].year == i+1
- ✅ Engine 自己有 `round()`：multiplier/escalation/cap_deg 4 位、summary 2 位 — pin 數字反映
  此 rounding，不會因外部精度漂移
- ✅ 整個 cost module pytest：**20 PASS + 1 XFAIL**（4.88s）

### 2.2 卡住或延後的事

無。pin 數字一次跑就 PASS。

### 2.3 重大決策

- 對 var_fluct 的 test 涵蓋設計：3 個 sample year（早 / 中 / 晚）+ summary，足夠
  detect 任何 migration drift；不全 20 年都 pin 因為冗餘
- Year 10（mid life）availability **必須** 等於 -03 cost_cal pinned baseline 0.9402 —
  這個 cross-test invariant 是 var_fluct 與 cost_cal 之間的 sanity 連動驗證

## 3. 產出清單

### 新增檔案

- `modules/cost/engine/var_fluct/{__init__,bathtub,calculator}.py`（3 檔，360 行）
- `modules/cost/tests/test_var_fluct.py`（9 tests + ~30 個 pinned 數字）
- `work-logs/2026-05/2026-05-04-var-fluct-migration.md`（本檔）

### 修改檔案

- `ISSUES.md`（WMOM-20260504-05 done；統計表 +1 done = 9）
- `STATUS.yaml`（M2 progress 60→75；overall 35→38）

### 動了狀態的 issue

- WMOM-20260504-05: 新建 + done

## 4. 下次怎麼接手

**4 個 engine submodule 全 done**。M2 還剩 3 個 issue：

| Issue | 內容 | 估時 |
|-------|------|------|
| WMOM-20260504-06 | Cost adapter — windMindOM canonical schema ⇄ engine dataclass 雙向轉換 | 0.5-1 天 |
| WMOM-20260504-07 | FastAPI cost router — POST /api/cost/forecast、GET /api/cost/ledger、/api/cost/lcoe | 0.5-1 天 |
| WMOM-20260504-08 | Frontend `/admin/cost/` — budget view + ledger + LCOE dashboard | 1-2 天 |

下個 session 推薦：**WMOM-20260504-06 cost adapter**。

理由：
- API 設計需要先有 schema（adapter 定義）
- Frontend 需要 API 才能做
- Adapter 還會 refactor 4 個 test 內重複的 `build_*_params` 函數

阻擋項：無。

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| Copy + sed + grep + smoke test | 5% |
| 讀 bathtub.py + calculator.py 理解 API | 15% |
| 寫 pin_var_fluct.py 取 ~30 個 pinned 數字 | 35% |
| 寫 test_var_fluct.py（9 tests，含 bathtub helper consistency） | 35% |
| Pytest 跑通 + cleanup | 5% |
| 收尾（ISSUES / STATUS / work-log / commit） | 5% |

## 6. 學到的事

- **Engine 內部 round** → pin 用 `repr()` 仍然抓得到「engine 對外回傳的精度」，不會
  因為 round 而失真（例如 `776626181.4` 是 round(776626181.395, 2) 的結果，repr 直接
  給 `.4` 就好）
- **Cross-test invariant**（Year 10 var_fluct availability == cost_cal baseline）= 強連
  動驗證，比單獨 pin 更能 catch 邏輯 bug（例如以後若 var_fluct 的 mid-life 計算被
  動到，會同步 break 兩個 test）
- **從零寫 test 比沿用 ECN test 多花 ~50% 時間**，但設計權更靈活（可以針對 phase
  選 sample year，不被 ECN 既有結構綁定）
- **4 個 engine SOP 對比**：
  - waiting_time（暖身）：~60 分（含 SOP 摸索 + xfail debug）
  - cost_cal（主菜）：~30 分
  - monte_carlo：~25 分
  - var_fluct（從零寫 test）：~25 分
  - 第二次以後 SOP 完全成熟，從 1 小時收斂到 25 分鐘

## 7. Open questions（park）

- VarFluctConfig 有 `failure_rate_model: "constant" | "bathtub" | "custom"` 三種，
  目前只測 default bathtub；要不要補 constant / custom 的 test？暫不做，等
  -06/-07 用到時再補
- VarFluct 的 `tariff_schedule` (year → kWh price) 沒測；目前用 default kwh_price
  即可，未來客戶有實際 tariff schedule 時再補
