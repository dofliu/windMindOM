# 2026-05-04 — cost_cal engine 移植（WMOM-20260504-03）

> Session 類型：實作 / 移植（M2 主菜）
> Session 長度：短（~30 分鐘，因 SOP 已成熟）
> 主導：Claude（劉老師指示「直接開始做」）
> 結果：cost_cal engine 8 檔完全移植，3 tests pass，6 個 top-level metric + 4 季 × 5 cost subcategories 全 bit-perfect == ECN

---

## 1. Session 目標

WMOM-20260504-03 — M2 主菜：cost_cal engine 移植 + K13 numerical equivalence 驗證。

ROADMAP 寫「ECN 計算結果如果跟原 tool 對不上，第一週就要發現並修」— 本 issue
是 K13 主驗證 gate。Pin 6 個 top-level metric（availability time/energy、revenue
loss、repair cost、total effort、cost per kWh）+ 4 季 × 5 cost subcategories
（material/equipment/revenue_loss/preventive_material/fixed_cost），任何 drift
都 fail。

## 2. 實際完成

### 2.1 主要工作

- ✅ `cp ../ECN/backend/app/engine/cost_cal/*.py modules/cost/engine/cost_cal/`（8 檔，957 行）
- ✅ `sed -i 's|from app\.engine\.|from modules.cost.engine.|g'` 改 import path
- ✅ `grep app.` 確認 cost_cal **完全乾淨**：無任何 ECN-specific 依賴（不需要
  stub 任何 function，比 waiting_time 更乾淨）
- ✅ 寫 `tools/pin_cost_cal.py` 一次性工具，跑 K13 + 用 `repr()` 取 float64
  完整精度 → 印出來 26 個數字（6 top-level + 20 seasonal）
- ✅ 寫 `modules/cost/tests/test_k13_equivalence.py`：3 tests
  - `test_k13_migration_equivalence_pinned` — 6 top-level metrics bit-perfect == ECN
  - `test_k13_migration_equivalence_seasonal` — 4 seasons × 5 fields bit-perfect == ECN
  - `test_k13_cost_calculation` — ECN V5 reference value 比對（與 ECN 原版同 tolerance 5-30%）
- ✅ 用 `@pytest.fixture(scope="module")` 共用 K13 結果，避免 3 個 test 各跑一次
- ✅ 刪掉 `tools/pin_cost_cal.py`（一次性工具，pin 完不留）
- ✅ 整個 cost module pytest：**6 PASS + 1 XFAIL**（含 -02 waiting_time 的 4 tests）

### 2.2 卡住或延後的事

- 無

### 2.3 重大決策

- 確認 cost_cal 比 waiting_time 更乾淨（無 ECN-specific 依賴），代表後續 -04
  monte_carlo / -05 var_fluct 大概率也會這樣 — migration 越來越快
- pin tool 用一次性 script + 跑完刪掉 pattern（不污染 tools/ 長期 codebase）

## 3. 產出清單

### 新增檔案

- `modules/cost/engine/cost_cal/{__init__,aggregator,corrective,data_classes,fixed,lcoe,preventive,revenue_loss}.py`（8 檔，957 行）
- `modules/cost/tests/test_k13_equivalence.py`（含 build_all_params helper + 3 tests + 26 個 pinned 數字）
- `work-logs/2026-05/2026-05-04-cost-cal-migration.md`（本檔）

### 修改檔案

- `ISSUES.md`（WMOM-20260504-03 done；統計表 +1 done）
- `STATUS.yaml`（M2 progress 25→45）

### 動了狀態的 issue

- WMOM-20260504-03: 新建 + done

## 4. 下次怎麼接手

下一個 issue：**WMOM-20260504-04 — `engine/monte_carlo/` 移植**

SOP 沿用 -02/-03：

1. `cp ../ECN/backend/app/engine/monte_carlo/*.py modules/cost/engine/monte_carlo/`（4 檔，674 行）
2. `sed -i 's|from app\.engine\.|from modules.cost.engine.|g'`
3. grep 確認沒 ECN-specific 依賴
4. 適配 `test_monte_carlo.py` → `modules/cost/tests/test_monte_carlo.py`
5. 加 pinned equivalence test：固定 random seed 比對 deterministic + sample distribution + LCOE
6. 注意 random seed 處理（`np.random.seed` 或 `np.random.default_rng(seed)`）以保證 reproducibility

monte_carlo 依賴 cost_cal（每次 iteration 都 call `run_cost_calculation`）— cost_cal
已 done，依賴解開。

估時：30 分鐘（檔案少 + SOP 熟）。

阻擋項：無。

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| Copy + sed import | 5% |
| Grep 驗證 + smoke test | 5% |
| 寫 pin_cost_cal.py 取 baseline 數字 | 25% |
| 寫 test_k13_equivalence.py + 6 個 metric + 20 個 seasonal pin | 50% |
| Pytest 跑通 + cleanup | 5% |
| 收尾（ISSUES / STATUS / work-log / commit） | 10% |

## 6. 學到的事

- **SOP 第二次跑就快很多** — waiting_time 用 ~1 小時，cost_cal 30 分鐘（pin 工具
  + test 結構複用）
- **pytest fixture(scope="module")** 對 expensive setup（多 build_* + run_cost_calculation）
  共享結果很好用 — 3 個 test 跑 0.22s，比 3 次跑快 3 倍
- **build_* 函數從 ECN test 沿用** — 那些 helper 也算 K13 ↔ data_classes 的
  adapter；之後 -06（cost adapter issue）寫 windMindOM canonical schema ↔ engine
  時會 refactor 進 `modules/cost/adapter.py`
- **Pin 26 個數字** vs 寫一個近似 tolerance test — 我選 pin 是因為 migration 邏輯
  上應該 bit-perfect，不該有任何 drift；如果以後 numpy 升級造成 1e-15 drift，
  那是 ecosystem 問題不是 migration 問題，再來改

## 7. Open questions（park）

- 目前 4 季 pin 5 個 field（material / equipment / revenue_loss / preventive_material
  / fixed_cost）— 可不可以 pin 全部 14 個 field（含 corrective_bop_*、preventive_*、
  preventive_downtime…）？暫不做，5 field 抽樣已能 detect drift；全 pin 會讓 test
  變肥
- monte_carlo 移植時 random seed 的 reproducibility 行為要確認（numpy / Python random
  各種 generator）
