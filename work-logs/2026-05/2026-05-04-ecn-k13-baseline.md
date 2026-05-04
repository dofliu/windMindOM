# 2026-05-04 — ECN K13 baseline + 移植規劃（WMOM-20260504-01）

> Session 類型：discovery / 取材
> Session 長度：短
> 主導：Claude（劉老師指示「進M2 → 路 A」）
> 結果：K13 baseline 跑通 + 4 engine submodule inventory + modules/cost/ skeleton 就位；M2 第二個 issue 解鎖

---

## 1. Session 目標

WMOM-20260504-01（M2 第一個 issue，discovery-first 路線）— 在動 cost engine 移植
程式碼**之前**先做：

1. 在 ECN 裡跑 K13 baseline，記下黃金數字（後續移植用來驗證 numerical equivalence）
2. 盤 4 個 engine submodule（cost_cal / waiting_time / monte_carlo / var_fluct）的內容、
   依賴、migration mapping
3. 在 windMindOM `modules/cost/` 建空 skeleton 對齊 ECN 結構
4. **不**真的移程式 — 那是下一個 issue（WMOM-20260504-02 或其他）

理由：ROADMAP 寫「ECN 計算結果如果跟原 tool 對不上，第一週就要發現並修；
不能拖到 Month 5; 解法：第一週內把 K13 demo 跑通，數字一致才繼續」— 沒
baseline number 怎麼驗證後續移植正確？

## 2. 實際完成

### 2.1 主要工作

- ✅ 跑 ECN 既有 4 支 test，全 pass：
  - `test_cost_cal_engine.py::test_k13_cost_calculation` — K13 完整 cost calculation
  - `test_waiting_time_engine.py` — 3 tests，weather window + polynomial coefficients
  - `test_monte_carlo.py::test_monte_carlo_lcoe` — n=100 Monte Carlo + LCOE
  - `test_user_data_parse.py` — 0 tests collected（沒測試 case）
- ✅ 抓到 K13 黃金數字（包括跟 ECN V5 reference 的 deviation）→ 寫進
  [`docs/legacy/ecn_k13_baseline.md`](../../docs/legacy/ecn_k13_baseline.md)
- ✅ 寫 [`docs/legacy/ecn_engine_inventory.md`](../../docs/legacy/ecn_engine_inventory.md)
  — 4 engine submodule 內容 + 跨模組依賴 + 移植 mapping + 風險評估
- ✅ 在 windMindOM 建 `modules/cost/{engine,models,routers,schemas}/` skeleton +
  各層 `__init__.py`
- ✅ 開新 issue WMOM-20260504-01（M2 第一個）→ done

### 2.2 卡住或延後的事

- ECN V5 reference 與當前 ECN backend 的數字有偏差（availability 較高、revenue
  loss 較低、total effort 較低）— 已在 baseline doc 標註，**不在本 issue 修**，
  屬於 ECN repo 的 calibration issue
- Monte Carlo p10/p50/p90 細節數字、waiting_time polynomial 細節係數沒抓 —
  暫只記 Monte Carlo summary（deterministic 與 LCOE）；移植真正動到細節時再展開

### 2.3 重大決策

- 無新 DEC（discovery 性質的工作不動架構面決策）
- 一個小 design 決定：windMindOM `modules/cost/` 結構**鏡像 ECN backend/app/**
  （engine / models / routers / schemas 四層），不重新設計 — 降低移植 risk

## 3. 產出清單

### 新增檔案

- `docs/legacy/ecn_k13_baseline.md`（K13 黃金數字 + reference vs computed 偏差 + 重跑指引）
- `docs/legacy/ecn_engine_inventory.md`（4 submodule inventory + dependency map + migration plan）
- `modules/cost/__init__.py`（更新 docstring）
- `modules/cost/engine/__init__.py`
- `modules/cost/engine/{cost_cal,waiting_time,monte_carlo,var_fluct}/__init__.py`
- `modules/cost/models/__init__.py`
- `modules/cost/routers/__init__.py`
- `modules/cost/schemas/__init__.py`
- `work-logs/2026-05/2026-05-04-ecn-k13-baseline.md`（本檔）

### 修改檔案

- `ISSUES.md`（新增 M2 區塊 + WMOM-20260504-01 done；統計表 +1 done）
- `STATUS.yaml`（M2 progress 0→10、issue_stats、last_updated、next_milestone）

### 動了狀態的 issue

- WMOM-20260504-01: 新建 + done

## 4. 下次怎麼接手

下一個 issue 候選（依優先序）：

1. **WMOM-20260504-02 — `engine/cost_cal/` 移植 + K13 numerical equivalence 驗證**
   （估 1-1.5 天；移程式 + 改 import path + cross-test ECN baseline 與
   modules/cost engine 的 K13 結果完全一致）
2. **WMOM-20260504-03 — `engine/waiting_time/` 移植 + ECN test 沿用**（估 0.5 天，相對獨立）
3. **WMOM-20260504-04 — `engine/monte_carlo/` 移植**（估 0.5 天，依賴 cost_cal）
4. **WMOM-20260504-05 — `engine/var_fluct/` 移植**（估 0.5 天，最簡單）
5. ECN models / routers / schemas 移植 — 暫不動，windMindOM 用自己的 schema
   （見 inventory.md §migration boundary 討論）

阻擋項：無（baseline + skeleton 都 ready）

## 5. 時間統計（粗估）

| 類別 | 比例 |
|------|------|
| 跑 ECN tests + 抓 baseline numbers | 25% |
| 寫 ecn_k13_baseline.md | 25% |
| 寫 ecn_engine_inventory.md（4 submodule × 內容/依賴/migration） | 30% |
| 建 skeleton | 10% |
| 收尾（ISSUES / STATUS / commit） | 10% |

## 6. 學到的事

- **ECN 自帶 K13 reference test** — 不用自己挖數字，test docstring 就有 ECN V5 reference values
- **Test 已經 fail-soft**（return result 而非 assert）— migration 時可以直接用同樣
  pattern 餵 windMindOM engine 比對
- **Engine vs Storage 邊界**：ECN engine 是 pure compute（吃 dataclass，吐 dataclass），
  models / routers 是 storage / API 層。windMindOM 移植 engine（純函數庫），
  自己做 schema / API — 邊界清楚才不會混到 ECN 的 SQLAlchemy
- **ECN reference vs computed 有偏差**（availability 94% vs 92.6%；revenue loss 15M vs 21M）
  — 是 ECN repo 既有 calibration 問題，不是本次 migration 引入。先記在 baseline doc，
  讓未來 owner 決定是否 backport 修正

## 7. Open questions（park）

- ECN V5 vs current calibration 偏差是不是 known issue？要不要查 ECN STATUS.yaml /
  README 有沒有記錄？暫不動，等真正移植時再評估
- ECN 的 `extract_k13_data.py`（root level）做什麼？沒看，可能只是 dev tool
- M2 結束後 cost API 的長相 — 等 cost_cal 移完才能設計
