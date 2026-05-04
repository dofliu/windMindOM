# 2026-05-04 — monte_carlo engine 移植（WMOM-20260504-04）

> Session 類型：實作 / 移植
> Session 長度：短（~25 分鐘）
> 主導：Claude（劉老師指示「繼續做」）
> 結果：monte_carlo engine 4 檔完全移植，5 tests 全 PASS，含 LCOE = 72.94 EUR/MWh bit-perfect

---

## 1. Session 目標

WMOM-20260504-04 — 移植 ECN `engine/monte_carlo/`（依賴已 done 的 cost_cal）。
特別 focus：random seed reproducibility 確保 pin 數字穩定。

## 2. 實際完成

### 2.1 主要工作

- ✅ `cp ../ECN/backend/app/engine/monte_carlo/*.py modules/cost/engine/monte_carlo/`（4 檔，674 行）
- ✅ `sed` 改 import path
- ✅ Grep 確認 monte_carlo **完全乾淨**（無 ECN-specific 依賴）— 與 cost_cal 一樣
- ✅ 確認 ECN 用 `np.random.default_rng(seed)`（modern API），seed=42 完全 reproducible
- ✅ 寫 `tools/pin_monte_carlo.py` 一次性工具，跑 K13 + n=100 + seed=42 → 印 21 個 pinned 數字
  - 4 個 deterministic
  - 11 個 percentile（cost p10/p50/p90/mean/std + avail_t/e p10/p50/p90）
  - 6 個 LCOE（含 LCOE = 72.94 EUR/MWh 黃金數字）
- ✅ 寫 `modules/cost/tests/test_monte_carlo.py`：5 tests 全 PASS
  - `test_mc_deterministic_pinned` — 4 metric bit-perfect（reuse cost_cal）
  - `test_mc_percentiles_pinned` — 11 percentile bit-perfect（驗證 sampler / runner）
  - `test_mc_lcoe_pinned` — 6 個 LCOE component bit-perfect（72.94 EUR/MWh）
  - `test_mc_sanity_checks` — P10 < P50 < P90、std > 0、CDF monotonic、P50 vs det < 20%
  - `test_mc_tornado` — bars > 0 且按 cost_range 排序
- ✅ 整個 cost module pytest：**11 PASS + 1 XFAIL**（含 -02 waiting_time 4 + -03 cost_cal 3 + 本次 5）

### 2.2 卡住或延後的事

無。所有 21 個 pinned 數字一次跑就 PASS。

### 2.3 重大決策

- 用 `pytest.fixture(scope="module")` 共用 mc_result + percentiles，避免 5 個 test 各跑 100 次 MC
  iteration —— 整個 test_monte_carlo.py 跑 0.45s

## 3. 產出清單

### 新增檔案

- `modules/cost/engine/monte_carlo/{__init__,runner,sampler,statistics}.py`（4 檔，674 行）
- `modules/cost/tests/test_monte_carlo.py`（5 tests + 21 個 pinned 數字）
- `work-logs/2026-05/2026-05-04-monte-carlo-migration.md`（本檔）

### 修改檔案

- `ISSUES.md`（WMOM-20260504-04 done；統計表 +1 done）
- `STATUS.yaml`（M2 progress 45→60）

### 動了狀態的 issue

- WMOM-20260504-04: 新建 + done

## 4. 下次怎麼接手

下一個 issue：**WMOM-20260504-05 — `engine/var_fluct/` 移植**

最後一個 engine submodule，最簡單（2 檔，360 行，無 dependency）。ECN 沒有對應 unit test —
需要新建一個。

預期 SOP：
1. cp + sed
2. 寫 `tools/pin_var_fluct.py` 跑 bathtub multiplier + var_fluct calculator → 取 pin 數字
3. 寫 `modules/cost/tests/test_var_fluct.py`：bathtub multiplier 隨年份的曲線 + calculator 結果
4. 4 engine submodule 全部 done → M2 progress 75%

估時：~25 分鐘（最簡單，且 SOP 已穩定）。

阻擋項：無。

之後（M2 後段，估再 1-2 天）：
- WMOM-20260504-06：Cost adapter（schema ⇄ engine）
- WMOM-20260504-07：FastAPI cost router
- WMOM-20260504-08：Frontend `/admin/cost/`

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| Copy + sed | 5% |
| Smoke test + 跑 ECN test | 5% |
| 寫 pin_monte_carlo.py 取 21 個數字 | 35% |
| 寫 test_monte_carlo.py（5 tests，含 sanity + tornado） | 45% |
| Pytest 跑通 + cleanup | 5% |
| 收尾（ISSUES / STATUS / work-log / commit） | 5% |

## 6. 學到的事

- **`np.random.default_rng(seed)` 完全 reproducible** — 跨 Python 版本、跨 import 順序，
  只要 seed 一樣輸出就一樣（modern numpy API，比舊的 `np.random.seed()` 更穩定）
- **Fixture 嵌套**：`percentiles` fixture 依賴 `mc_result` fixture —— pytest 自動處理
  ordering，scope="module" 確保 100-iteration MC 只跑一次給 5 個 test 用
- **Pin 21 個數字** vs 寫近似 tolerance：選 pin 是因為 monte_carlo 對 random seed 敏感；
  bit-perfect 比對是 migration 正確性最強 gate
- **build_mc_params 與 build_all_params**（-03）有大量重複 — 之後 -06 寫 cost adapter
  時應該 refactor 進 `modules/cost/adapter.py` 共用，本次先重複保 test 獨立

## 7. Open questions（park）

- Tornado 那 74 個 parameters，要不要 pin top-5 名稱以驗證 sampler ordering 穩定？
  → 暫不做，cost_range 的數字會隨 numpy / pandas 微調而漂；當前 sanity check（bars > 0
  + 排序正確）已夠
