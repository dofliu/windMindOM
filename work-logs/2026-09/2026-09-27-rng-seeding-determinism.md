# 2026-09-27 — WMOM-20260927-01：全域未種子化 RNG 造成模擬結果非決定性修正

## Claim

`ISSUES.md` open issue `WMOM-20260927-01`，前一 session（WMOM-20260505-24）修復
data quality individuality spread 時發現的 follow-up：`priority: low`、估時
15-30 分鐘，acceptance 明確（同一 seed 兩次 `generate_data` 應逐位元重現）。

之所以挑這個 issue：檢查 stack-aware 狀態（`mcp__github__list_pull_requests` 回傳
空陣列）確認沒有上個 session 留下的未合併 PR，可以挑新工作。M6 critical path 剩餘項
（PostgreSQL row-lock、HTTPS 部署）皆需劉老師先決策；情境比較分析 epic 剩 A2/PR C
皆已於前幾個 session 收尾（詳見 STATUS.yaml）；`WMOM-20260505-25~28` 物理強化屬
多日工作，非單 session 可完工。`WMOM-20260927-01`/`-02` 是本次僅有的兩個「單 session
可完工、無設計歧義」候選，選 `-01`（RNG 種子化）而非 `-02`（stale tag 改名）：前者
是更完整的技術債（影響模擬結果可重現性），後者是純字串替換、價值較低，`-02` 留給下次
session。

## Implement

先讀過 `docs/legacy/digiwt_project_notes.md`——本次改動不涉及物理模型參數本身
（不動 `power_curve.py`/`turbine_physics.py` 的任何物理公式），只是把既有噪聲項的
RNG 來源從全域改成種子化實例，不影響既有 18/21（現 20/20）物理一致性 check。

### 根因確認

`grep -rn "np\.random\." modules/monitoring/simulator` 排除 `self._rng` 後，只剩
`grid_model.py`（`get_frequency`/`get_voltage` 各 3 處噪聲項）與
`physics/yaw_model.py`（`_output()` 內 `brake_pressure` 噪聲 1 處）直接呼叫全域
`np.random.normal(...)`；其餘全部（`turbine_physics.py`/`vibration_model.py`/
`fatigue_model.py`/`wind_field.py`/`vibration_spectral.py`）皆已用
`np.random.RandomState(seed)` 建立各自 `self._rng`，與 issue 描述一致。

### 修法

- `grid_model.py`：`GridEnvironmentModel.__init__` 新增 `seed: Optional[int] = None`
  參數 + `self._rng = np.random.RandomState(seed)`；`get_frequency`/`get_voltage`
  內 6 處 `np.random.normal` 全改 `self._rng.normal`。
- `physics/yaw_model.py`：`YawModel.__init__` 新增同款 `seed`/`self._rng`；
  `_output()` 的 `brake_pressure` 噪聲改用 `self._rng.normal`。
- `physics/turbine_physics.py`：`self.yaw = YawModel()` → `self.yaw =
  YawModel(seed=_seed)`（`_seed` 是既有 `VibrationModel(seed=_seed)`/
  `SpectralVibrationModel(seed=_seed)`/`FatigueModel(seed=_seed)` 共用的
  per-turbine seed，沿用既有慣例，非新設計）。
- `simulator/engine.py`：`self.grid_model = GridEnvironmentModel()` →
  `GridEnvironmentModel(seed=7)`——`grid_model` 是單一 farm-level 共用模型（非
  逐風機），比照同一 `__init__` 內幾行後既有的 `TurbulenceGenerator(seed=42)`/
  `PerTurbineWind(turbine_count, seed=99)` 硬編碼 farm-level seed 慣例，選一個
  未被佔用的整數。

### 範圍外但誠實揭露的發現：`recovery` grid profile 仍依賴 `datetime.now()`

寫測試時發現 `GridEnvironmentModel.set_profile("recovery")`/`set_override(...)`
把 `self._profile_start_time = datetime.now()`（真實牆鐘時間），`get_frequency`/
`get_voltage` 在 `_active_profile == "recovery"` 分支用
`(timestamp - self._profile_start_time).total_seconds()` 算 `elapsed`——這個
`elapsed` 跟呼叫當下的真實牆鐘時間有關，即使 RNG 完全種子化，兩次獨立呼叫
`set_profile("recovery")` 因為牆鐘時間本身不同，`elapsed` 也會不同，其餘欄位
仍會不可重現。這是與本 issue（RNG 種子化）**完全獨立**的非決定性來源（`recovery`
profile 本身設計上就是模擬「距離 grid event 開始已過多少真實時間」，用牆鐘時間
可能本來就是刻意設計，不像 RNG 種子化是明確的一致性缺口）——判斷為範圍外，
**未修**，測試刻意排除 `recovery` 分支避免誤判（見下方 Verify 章節）。未另開新
issue（過於邊緣，若之後有人需要「連 recovery 分支也逐位元可重現」的保證再開）。

## Verify

**Mutation-verified**：把 `grid_model.py`/`yaw_model.py` 內全部 `self._rng.normal`
用 `sed` 改回 `np.random.normal`（未動其他邏輯），重跑
`test_rng_seeding_determinism.py`：3 個「seeded determinism」測試（grid/yaw/
farm-level）如預期 fail，2 個「different seed diverges」測試維持 pass（這兩個
本來就不依賴種子化，是設計上如此，非退化）；確認測試真的鎖住本次修復。用
scratchpad 備份的檔案內容（非 `git checkout`，因為當時未 commit）逐一還原，
還原後重跑全綠。

新增 `modules/monitoring/tests/test_rng_seeding_determinism.py`（5 測）：
- `test_grid_model_seeded_determinism` / `test_grid_model_different_seed_diverges`
- `test_yaw_model_seeded_determinism`（含觸發 cable-unwind 分支）/
  `test_yaw_model_different_seed_diverges`
- `test_farm_level_readings_are_byte_reproducible_across_instances`——驗收條件
  本體：兩個獨立 `WindFarmSimulator(turbine_count=2)` 對同一序列 `sim_time`
  跑 `_run_one_step()`（`_loop`/`generate_bulk` 共用的單步核心，不需要真的跑
  數小時 `generate_data()`）10 步，全部 readings 逐欄逐列 `==`。

- backend 全套：`pytest modules/workflow/tests/ modules/cost/tests/
  modules/reporting/tests/ modules/knowledge/tests/ modules/monitoring/tests/
  modules/auth/tests/ tests/` → 1280→**1285 passed**（+5，7 skipped, 1 xfailed，
  零 regression）
- frontend：本次未動任何前端檔案，`npx tsc --noEmit` + `npx vitest run` + `npx vite
  build` → 1477 passed（70 files）不變、tsc 0、build OK（零 regression）。
  vitest 過程中出現 1 個既有的 uncaught exception 警告（`TurbineDetail.test.tsx`
  teardown 後的 `setTimeout` 殘留計時器觸發 `window is not defined`），exit code 0、
  測試數不變，非本次改動引入，非本次範圍。

## Review

`code-reviewer` subagent review：**Approve，0 must-fix，1 should-fix 已採納，
2 nice-to-have（1 個採納、1 個登記新 follow-up）**：

1. 🟡 **should-fix**：原本選的 farm-level 共用 `GridEnvironmentModel(seed=7)`
   落在 `add_turbine()` 逐風機 seed 範圍（`1..turbine_count`，預設上限 14）內，
   跟 `WT007` 的 seed 撞號——雖然實際不影響功能（不同類別各自獨立 `RandomState`
   不會因為 seed 數值相同就產生相關輸出，reviewer 有明確驗證這點），但違反我在
   commit 訊息裡自己寫的「比照 seed=42/99 慣例、刻意避開風機 index 範圍」設計
   意圖，是個 latent foot-gun（之後如果有人依 seed 數值 grep/filter debug，或
   farm-level seed 機制被擴充，可能誤踩）。已改成具名常數
   `WindFarmSimulator._GRID_MODEL_SEED = 1042` 並加註解明講「必須落在風機 seed
   範圍外」的不變量，避免之後 `turbine_count` 長大時再次矇著頭撞號。
2. 🟢 **nice-to-have（已採納）**：`ISSUES.md` acceptance 原文寫「同一組 seed
   連續兩次 `generate_data(...)` 產生的 DataFrame 逐欄逐列數值相同」，但
   `WindFarmSimulator` 根本沒有 `generate_data` 方法（那是
   `examples/data_quality_analysis.py` 頂層函式，不是 simulator 的方法）——已在
   ISSUES.md 該行加註更正為實際使用的 `_run_one_step()`，避免以後讀者對著不存在
   的方法名摸不著頭緒。
3. 🟢 **nice-to-have（登記新 follow-up，未修）**：`modules/monitoring/
   subsystems.py` 219/234 行（legacy `WindTurbine`/`main.py` 路徑，非本 issue
   針對的 `simulator/engine.py`/`TurbinePhysicsModel`）仍有同款未種子化
   `np.random.normal`。Reviewer 已確認這是完全獨立的 code path（`main.py` 用
   `WindTurbine`，不被 `WindFarmSimulator` 引用），不在本次驗收範圍——登記
   **WMOM-20260927-03** 追蹤。

Reviewer 額外針對我在 prompt 裡提出的具體問題給出獨立驗證（非我自己聲稱）：
- 確認 `test_farm_level_readings_are_byte_reproducible_across_instances`
  是有意義的測試、修復前必定會 fail（追蹤 `_run_one_step()` 內
  `grid_model.get_frequency`/`get_voltage` 與 `YawModel._output()` 每步都會
  被呼叫到，即使 `not is_producing` 的 early-return 分支也會呼叫 `_output()`），
  不是「反正早就種子化過、這次測試巧合會過」。
- 確認排除 `recovery` profile 分支是合理的範圍判斷、非隱瞞問題。
- 全域 grep `modules/monitoring/simulator/` 內所有隨機函式呼叫，確認種子化鏈條
  在 `_run_one_step()` 觸及的範圍內完整無遺漏。
- 本次改動不涉及任何 SCADA tag/ECN/Z72 setpoint 語意，純屬可重現性技術債，無
  windMindOM 領域特定疑慮。

## Verify（should-fix 修復後複驗）

- `test_rng_seeding_determinism.py` 5 測仍全數 pass（`_GRID_MODEL_SEED` 改名
  不影響任何斷言邏輯，純命名變更）。
- backend 全套重跑：`pytest modules/workflow/tests/ modules/cost/tests/
  modules/reporting/tests/ modules/knowledge/tests/ modules/monitoring/tests/
  modules/auth/tests/ tests/` → **1285 passed**（7 skipped, 1 xfailed，與
  should-fix 修復前一致，零 regression）。
- frontend：未改動任何前端檔案，維持 1477 passed（70 files）/ tsc 0 / build OK。

## Wrap-up

- 本次改動範圍：只動 RNG 來源（`grid_model.py`/`yaw_model.py`/
  `turbine_physics.py`/`engine.py`），**沒有改動任何物理模型參數或噪聲幅度**
  （0.01/0.02/0.03 Hz、`nom*0.001` V、0.5 bar brake pressure 數值本身皆不變，
  只是改變它們的隨機數來源），不影響既有 20/20 物理一致性 check。
- **未修範圍（誠實揭露）**：
  1. `GridEnvironmentModel` 的 `recovery` profile 分支依賴 `datetime.now()`
     真實牆鐘時間，是與本 issue 完全獨立的非決定性來源，未修（可能是刻意設計）。
  2. `WMOM-20260927-02`（`fetch_scada_data.py` 殘留 stale tag）仍是 open，
     本次未處理（優先選 -01 而非 -02，見上方 Claim 章節）。
  3. **新登記 WMOM-20260927-03**（`subsystems.py` legacy 路徑同款未種子化
     RNG），open，未修。
- ISSUES.md：`WMOM-20260927-01` → done（含完整 completion summary）；新增
  `WMOM-20260927-03`（open）；統計表 open 9→9（-01 done、+03 open 互相抵銷）、
  done 138→139。
- STATUS.yaml：`last_updated`/`issue_stats`/`test_baseline` 已同步（發現
  `STATUS.yaml` 本身其實不是合法 YAML——`python -c "import yaml;
  yaml.safe_load(...)"` 在編輯前就已經 fail，非本次改動造成的 regression，
  本次未展開處理，純粹記錄供劉老師參考：這個檔案目前是「人類可讀的 Markdown-in-
  YAML 混合格式」，不能真的被程式化 parse）。
- TODO.md：已同步本次完成摘要 + 下個 session 建議。
- 下個 session 可從 `WMOM-20260927-02`/`WMOM-20260927-03`（皆 <30 分鐘小修）、
  `WMOM-20260505-25~28`（逐一看 priority）、或 M6 critical path 剩餘項（皆需
  劉老師決策）中挑選。
