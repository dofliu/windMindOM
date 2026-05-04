# 2026-05-04 — waiting_time engine 移植（WMOM-20260504-02）

> Session 類型：實作 / 移植
> Session 長度：短
> 主導：Claude（劉老師指示「dev 線優先、功能弄好」）
> 結果：waiting_time engine 7 檔完全移植，4 tests pass（3 PASS + 1 XFAIL with reason），bit-perfect 等於 ECN

---

## 1. Session 目標

WMOM-20260504-02 — M2 第一個真正動程式的 issue，建立 ECN engine migration pattern。

策略：複製 + 改 import path + stub ECN-only 依賴 + 適配 test。完成後可以複用同
SOP 給後續 cost_cal / monte_carlo / var_fluct。

## 2. 實際完成

### 2.1 主要工作

- ✅ Copy `../ECN/backend/app/engine/waiting_time/` 7 檔 → `modules/cost/engine/waiting_time/`
  （覆蓋 -01 建的 placeholder __init__.py）
- ✅ Copy K13 demo 7 檔（json + csv，~32k 行）→ `modules/cost/data/demo/`
- ✅ `sed` 一鍵改 import path：`from app.engine.X` → `from modules.cost.engine.X`
- ✅ Stub `data_processor.preprocess_metocean_data()` — 唯一一個用 `app.models.metocean_data`
  的函數（function-level lazy import，不在 engine pipeline 用到），改 raise
  NotImplementedError 並 docstring 指向未來的 `modules/cost/adapter.py`
- ✅ 適配 ECN test → `modules/cost/tests/test_waiting_time.py`：
  - PROJECT_ROOT 路徑改用 `pathlib.Path(__file__).resolve().parents[3]`
  - DATA_DIR 改指向 `modules/cost/data/demo/`
  - `return True/False` → `assert`（消除 PytestReturnNotNoneWarning，並真正驗證）
- ✅ 加 `test_migration_equivalence_pinned` — windMindOM 必須 bit-perfect 等於 ECN
  在 K13 上的實際輸出（用 `repr()` 取 float64 完整精度做 pin），任何 drift 都 fail
- ✅ 4 tests 結果：
  - `test_ww3_winter` — PASS（4 個 polynomial 係數 < 1e-4）
  - `test_all_windows_winter` — PASS（13 windows × winter，< 1e-2）
  - `test_all_seasons_ww3` — **XFAIL with reason**（pre-existing ECN issue，
    K13 JSON reference 對不上 ECN compute）
  - `test_migration_equivalence_pinned` — PASS（4 季 × 2 coefficients bit-perfect == ECN）

### 2.2 卡住或延後的事

- 一開始 pin 的 ECN 數字精度不夠（用 `:12.6f` 印出來 14 位有效數字，但 float64
  有 17 位）→ 第一輪 migration_equivalence test 顯示 ~1e-7 drift。改用 `repr()`
  取完整精度後 PASS
- ECN 既有 `test_all_seasons_ww3` 算出 spring/summer c0 偏差 1.5（K13 JSON 有問題
  或是 ECN 計算有問題，二選一）— 不在 migration 範圍，xfail 保留診斷

### 2.3 重大決策

- 確立 migration 驗證 SOP：
  1. 沿用 ECN test（適配 path）— 保持 ECN 內既有的數字檢查
  2. 加 pinned equivalence test — windMindOM ≡ ECN 是 migration gate
  3. ECN 既有 fail（不是 migration 引入）xfail with reason，不阻塞

## 3. 產出清單

### 新增檔案

- `modules/cost/engine/waiting_time/{__init__,data_processor,polynomial_fitter,power_calculator,season_filter,waiting_calculator,weather_windows}.py`（7 檔，從 ECN 複製 + import 改寫 + 1 個函數 stub）
- `modules/cost/data/demo/k13_*.{json,csv}`（7 個 K13 dataset）
- `modules/cost/tests/test_waiting_time.py`（4 tests，含 pinned equivalence）
- `work-logs/2026-05/2026-05-04-waiting-time-migration.md`（本檔）

### 修改檔案

- `modules/cost/data/demo/.gitkeep`（被 K13 檔覆蓋；目錄已有實檔）
- `ISSUES.md`（WMOM-20260504-02 done；統計表 +1 done）
- `STATUS.yaml`（M2 progress 10→25）

## 4. 下次怎麼接手

下一個 issue：**WMOM-20260504-03 — `engine/cost_cal/` 移植**

SOP 沿用本 issue 模式：

1. Copy `../ECN/backend/app/engine/cost_cal/*.py` (8 檔) → `modules/cost/engine/cost_cal/`
2. `sed -i 's|from app\.engine\.|from modules.cost.engine.|g'` 全檔
3. grep `from app\.` 找剩餘 ECN-specific 依賴 → stub or migrate
4. 適配 `test_cost_cal_engine.py` → `modules/cost/tests/test_k13_equivalence.py`
5. 加 `test_migration_equivalence_pinned`：把 §2.1 的 5 個 metric（availability_time/energy、revenue_loss、repair_cost、total_effort）pin 進來，用 `repr()` 取精度
6. pytest 全 pass（含 pinned equivalence）

估時：1-1.5 天（檔案多 + cost_cal 是 K13 主驗證）。

阻擋項：無（waiting_time 完成、K13 data 已就位）。

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| Copy 檔案 + sed 改 import | 10% |
| 找 + stub `app.models` 依賴 | 10% |
| 寫 test 適配（path / assert / xfail） | 30% |
| 第一輪 pin 精度不夠的 debug | 15% |
| 寫 migration equivalence test + 重 pin 數字 | 20% |
| 收尾（ISSUES / STATUS / work-log / commit） | 15% |

## 6. 學到的事

- **`repr()` 抓 float64 完整精度** — `:12.6f` 印出來夠人讀，不夠 pin 用。Migration 等價驗證一定要用 `repr()`
- **ECN 用 `return True/False` 寫 test** — pytest 不會 fail，要轉 assert 才能真的驗證；migration 順便修這個 quality gate
- **Engine vs Storage 邊界**：data_processor 的 `preprocess_metocean_data()` 有
  function-level 的 `app.models` lazy import — 不影響 module 載入，但 windMindOM
  用不到，stub 出來才算乾淨
- **xfail 比 skip 好** — pre-existing ECN issue 用 xfail with reason 保留診斷且不阻塞 CI；下次有人重跑 test 還能看到具體 deviation 數字

## 7. Open questions（park）

- ECN test_all_seasons_ww3 的 spring/summer deviation 是 K13 JSON 有問題還是
  ECN compute 有問題？→ 屬於 ECN repo 的事，未來可開 issue 給 ECN repo 但與
  windMindOM migration 脫鉤
- 是否要 enforce 全 module pinned equivalence？目前 waiting_time 只 pin 了
  WW3 × 4 seasons 的 c0/c1 — 夠抓 drift；後續 cost_cal 要 pin 5 個 top-level
  metric + 4 季 breakdown
