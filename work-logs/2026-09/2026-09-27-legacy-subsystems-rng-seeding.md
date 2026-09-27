# 2026-09-27 — WMOM-20260927-03：legacy `subsystems.py` 未種子化 RNG 修正

## Claim

Preflight：`git checkout main && git pull` 後本機自我測試全綠，與 baseline 完全
一致（backend 1285 passed/7 skipped/1 xfailed；frontend 1477 passed/70
files/tsc 0/build OK）。Stack-aware 檢查：`mcp__github__list_pull_requests`
（state=open）回傳空陣列，無上個 session 留下的未合併 PR，可挑新工作。

`ISSUES.md` open issue `WMOM-20260927-01` 讀完的 work-log 建議下個 session 可從
`WMOM-20260927-02`（`fetch_scada_data.py` 殘留 stale tag）、`WMOM-20260927-03`
（本 issue）、`WMOM-20260505-25~28`（物理強化，多日工作）、或 M6 critical path
剩餘項（皆需劉老師決策）中挑選。選 `-03` 而非 `-02`：`-03` 是更完整的技術債
（同一 issue -01 的姊妹問題，涉及可重現性保證），`-02` 純字串替換、價值較低且更
瑣碎；`-25~28` 皆為多日工作非單 session 候選；M6 剩餘項皆卡在需要劉老師決策
（PostgreSQL row-lock 需 docker、HTTPS 部署配置需先定部署目標）。

## Implement

先確認死碼範圍（issue acceptance 要求：修 RNG 或判定死碼二選一）。全庫 grep
`main.py`/`turbine_model.py`/`subsystems.py` 這條 legacy `WindFarmSimulator`
（與 `simulator/engine.py::WindFarmSimulator` 同名但完全不同實作、是歷史原型）
鏈路：

- 沒有任何其他 `.py` 檔 import `modules/monitoring/main.py`（唯一命中是
  `openopc2/gateway_service.py` 的無關字串巧合 `from ... import main as ...`）
- `docker-compose.yml`/`Dockerfile` 的 `CMD` 是 `python run.py`，`run.py`/`api/`
  皆未 import 這條鏈路
- `modules/monitoring/tests/` 沒有任何測試檔案引用 `turbine_model`/`subsystems`

確認是完全死碼。但這條 legacy 檔案樹共 8 檔（`main.py`/`turbine_model.py`/
`subsystems.py`/`wind_model.py`/`opcua_interface.py`/`scada_system.py`/
`dashboard.py`/`main_architecture.py`），全部刪除是遠超出本 issue「修 RNG 種子化」
範圍的大動作（風險/工作量與本 issue 15-20 分鐘估時不成比例，且不確定劉老師是否
要保留這份原型程式碼作參考）——選擇 acceptance 允許的另一條路：比照 -01 的修法，
只做種子化，不動其他 7 個檔案，也不動 `main.py`。

### 修法

- `subsystems.py`：`GearboxSystem.__init__`/`HydraulicSystem.__init__` 新增
  `seed: Optional[int] = None` 參數 + `self._rng = np.random.RandomState(seed)`；
  `vibration_level`/`pressure` 兩處噪聲改用 `self._rng.normal`。
- `turbine_model.py`：`WindTurbine.__init__` 新增同款 `seed` 參數，往下傳給
  `GearboxSystem`/`HydraulicSystem`。
- `main.py::add_turbine()` **刻意不動**——`WindTurbine(turbine_id)` 不傳
  `seed`，`seed=None` 預設值保留既有（未種子化）行為，不影響任何既有呼叫端。

## Verify（初版）

新增 `modules/monitoring/tests/test_legacy_subsystems_rng_seeding.py`（初版 6
測）：`GearboxSystem`/`HydraulicSystem` 各自 seeded-determinism + different-seed-
diverges，`GearboxSystem` 額外補 default `seed=None` 仍隨機的測試，加上
`WindTurbine.simulate_step()` 端到端可重現測試。

**Mutation-verified**：`sed` 把 `self._rng.normal` 改回 `np.random.normal`，重跑
確認 3 個 determinism 測試如預期 fail（3 個 diverge/default 測試維持 pass，符合
預期——這些本就不依賴種子化）；用 scratchpad 備份還原後重跑全綠。

- backend 全套：1285→**1291 passed**（+6，零 regression）
- frontend：本次未動任何前端檔案，維持 1477 passed（70 files）/tsc 0/build OK

## Review

`code-reviewer` subagent review：**Approve，0 must-fix，1 should-fix 已採納，
1 nice-to-have 已採納**：

1. 🟡 **should-fix**：`WindTurbine.__init__` 把同一個 `seed` 值同時傳給
   `GearboxSystem(seed=seed)` 與 `HydraulicSystem(seed=seed)`。Reviewer 用
   `np.random.RandomState(99)` 兩個獨立實例各自 `.normal(0, 0.1)`/
   `.normal(0, 0.5)` 實測出**固定比例 5.0**（= sigma_hydraulic/sigma_gearbox）
   ——本 session 獨立重跑同一段程式碼確認無誤：兩個獨立 `RandomState` 用同一
   seed、且建構後都沒有消耗任何 RNG state 就立刻呼叫 `.normal()`，會導致兩條
   物理上完全無關的噪聲（齒輪箱振動 vs 液壓壓力）彼此鎖死成固定比例，是比
   「完全不種子化」更糟的合成資料假象（若這條 legacy 路徑未來被拿來做 demo 或
   參考，噪聲看起來會明顯是假的、彼此連動）。並非本次修法新發明的問題——
   `simulator/physics/turbine_physics.py`（**live** 路徑，非本 issue 範圍）現有
   `VibrationModel(seed=_seed)`/`YawModel(seed=_seed)` 也共用同一 `_seed`，只是
   `VibrationModel.__init__` 建構時剛好先消耗 2 次 `self._rng.uniform(...)`
   才使兩者的 RNG stream 意外錯開、屬於脆弱的巧合而非刻意解耦。`simulator/
   physics/wind_field.py` 早有明確的 `seed+1000`/`seed+2000`/`seed+3000`/
   `seed+4000` 偏移慣例可循解耦多個噪聲來源。已改成 `gearbox_seed = seed if
   seed is None else seed + 1`、`hydraulic_seed = seed if seed is None else
   seed + 2` 比照該慣例（`seed=None` 時維持不偏移，保留未種子化語意）。新增
   `test_wind_turbine_different_seeds_diverge_end_to_end`（`WindTurbine`
   層級的 different-seed-diverges，reviewer nice-to-have）+
   `test_gearbox_and_hydraulic_noise_are_not_correlated_when_sharing_one_wind_turbine_seed`
   （鎖住本次 should-fix：用 `input_speed=0`/`input_torque=0` 分離出
   `GearboxSystem` 純噪聲項、比對與 `HydraulicSystem` 第一次噪聲項的比例是否
   固定為 5.0）。**Mutation-verified**：暫時把 `gearbox_seed`/`hydraulic_seed`
   改回都等於 `seed`（重現共用同一 seed 的 bug），重跑精準抓到
   `assert 5.0 != 5.0` fail（實測值 `-0.071179.../-0.014235... = 5.0`，
   與 reviewer 預測完全吻合）；已還原確認全綠。
2. 🟢 **nice-to-have（已採納）**：補 `WindTurbine` 層級 different-seed-diverges
   測試（見上方，與 should-fix 修復一併補上）。

Reviewer 額外獨立驗證：`subsystems.py` 修復後只剩 `self._rng.normal` 兩處呼叫，
grep 確認無遺漏；`RotorSystem`/`GeneratorSystem`/`PitchControlSystem`/
`YawSystem`/`ControlSystem` 本就不含任何 `np.random` 呼叫，正確未觸碰；獨立
grep 全庫確認 `main.py`/`turbine_model.py` 除本次新測試檔外無任何其他引用，死碼
判斷成立；`main.py` 未修改、`seed=None` 預設值保留既有行為的判斷正確。

## Verify（should-fix 修復後複驗）

新增 2 測後，`test_legacy_subsystems_rng_seeding.py` 共 8 測全數 pass。

- backend 全套：`pytest modules/workflow/tests/ modules/cost/tests/
  modules/reporting/tests/ modules/knowledge/tests/ modules/monitoring/tests/
  modules/auth/tests/ tests/` → 1285→**1293 passed**（+8，7 skipped, 1
  xfailed，零 regression）
- frontend：本次未動任何前端檔案，維持 1477 passed（70 files）/tsc 0/build OK
  不變

## Wrap-up

- 本次改動範圍：只動 legacy `subsystems.py`/`turbine_model.py` 的 RNG 來源，
  **未刪除、未修改** `main.py` 或其餘 6 個 legacy 檔案（`wind_model.py`/
  `opcua_interface.py`/`scada_system.py`/`dashboard.py`/
  `main_architecture.py`），也**未改動**任何物理模型參數（噪聲幅度 0.1/0.5 皆
  不變，只改變其隨機數來源）。
- **未修範圍（誠實揭露）**：
  1. `simulator/physics/turbine_physics.py`（**live** 路徑）現有
     `VibrationModel(seed=_seed)`/`YawModel(seed=_seed)` 共用同一 `_seed` 的
     latent 風險（見上方 Review §1 說明：目前靠 `VibrationModel.__init__`
     建構時消耗 2 次 RNG state 的巧合才錯開，非刻意解耦）——reviewer 判定非
     本 issue 範圍（本 issue 是 legacy `subsystems.py`，非 `turbine_physics.py`），
     本次未動、未另開新 issue（屬於觀察記錄層級：目前無任何已知的錯誤輸出或
     測試失敗，只是脆弱的實作巧合，若之後有人調整 `VibrationModel.__init__`
     的建構邏輯可能意外暴露這個問題，留供未來 session 或劉老師參考）。
  2. `WMOM-20260927-02`（`fetch_scada_data.py` 殘留 stale tag）仍是 open，
     本次未處理。
  3. 整條 legacy 檔案樹（`main.py` 等 8 檔）是否要直接刪除是產品/repo 衛生
     決策（非本 issue 範圍，也非本 session 判斷可完全自主決定——不確定是否有
     教學/參考價值），留給劉老師評估是否要開新 issue 處理。
- ISSUES.md：`WMOM-20260927-03` → done（含完整 completion summary）；頂部統計表
  open 9→8、done 135→136（total 146 不變）。
- STATUS.yaml：`last_updated`/`issue_stats`/`milestones` M6 進度已同步。
- TODO.md：已同步本次完成摘要 + 下個 session 建議。
- 下個 session 可從 `WMOM-20260927-02`（`fetch_scada_data.py` stale tag，10
  分鐘小修）、`WMOM-20260505-25~28`（物理強化，逐一看 priority，皆多日工作）、
  或 M6 critical path 剩餘項（PostgreSQL row-lock 需 docker、HTTPS 部署配置需先
  定部署目標，皆需劉老師決策）中挑選。
