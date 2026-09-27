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

`code-reviewer` subagent review 進行中（async，結果將於下方補上或另行處理，若
review 抓到 must-fix/should-fix 會在本節更新後再收尾）。

## Wrap-up

（review 完成後補充：must-fix/should-fix 處理結果、最終測試數字）
