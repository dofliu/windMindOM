# 2026-10-25 — WMOM-20261023-01：直驅 `WGEN_GnSpd` 偏離轉子轉速

> Session 類型：修 bug
> Session 長度：中
> 主導：Claude（劉老師指定「接著修 WMOM-20261023-01」）
> 結果：WMOM-20261023-01 done；DEC-20261025-01；範例資料包重建

---

## 1. Session 目標

-08-c 的 code review 查到範例資料包裡有健康機組的 `WGEN_GnSpd` 是轉子轉速的 2.5–2.7 倍（05 的 WT001：57.9 對 22.0 rpm）
或接近 0（06 的 WT002：0.4 對 22.1）。Z72 是直驅，兩者剛性連接。找根因、修、加守門測試、重建範例資料包。

## 2. 調查

- ISSUES 的猜測是「傳動鏈 slip / coupling 積分、子步長」。先重現：`TurbinePhysicsModel(seed)` 固定 13 m/s 跑 30 分鐘。
  - dt 1 s：14 個種子 gen ＝ rotor（差 0）。
  - dt 5 s（批次子步 `_MAX_PHYSICS_DT`）：seed 1 gen 60.3 對 22.3、seed 2 47.2、seed 6 0.0 對 22.9；其他正常。
    與範例 05 / 06 的 WT001 / WT002 / WT006 吻合（`add_turbine` 的種子＝機組編號）。
- 逐步印出：seed 1 在 dt 5 s 是**二週期振盪**——gen 0.0 ↔ 60.3、rotor 22.94 ↔ 22.29、`_lss_twist` −13.3 ↔ +10.7，
  每一步翻一次。資料包每 10 s 取樣（每兩個子步）剛好看到同一相位，才像穩定的偏離。
- 線性化：直驅的 LSS 扭轉＋發電機轉速是二階系統 `dg/dt = −0.48K·g + 0.725L + …`、`dL/dt = −0.12K·g − D·L + …`，
  K 0.36 / D 0.24 時特徵值 −0.21 ± 0.17i（阻尼振盪、週期約 36 s）。顯式 Euler 放大率 |1 + λ·dt|：dt 1 s 約 0.82；
  dt 5 s 名義值 0.87，但剛性 / 阻尼抽得高（`drivetrain_stiffness_scale` ≳ 1.09、`shaft_damping_scale` ≳ 1.1）就超過 1。
  不穩定後被 `max(0, …)` 與轉子夾住 → 有限振幅的二週期軌道。出問題的三個種子剛好是 K、D 都抽得高的。
- 所以不是模型的穩態偏差：連續系統的平衡點只有 gen ＝ rotor。

## 3. 修正（`simulator/physics/drivetrain_model.py`）

- `DrivetrainModel.step` 把扭轉（LSS / HSS）＋發電機轉速（含停機的減速夾值）以 ≤ `_TORSION_MAX_DT` = 1 s 的子步積分；
  步內的輸入（氣動轉速、煞車扭矩、嚙合激振）不變，轉子轉速用最後的扭轉算。
- dt ≤ 1 s 子步數為 1、`h = dt / 1` 與原算式逐位元相同。
- 其他選項（DEC-20261025-01）：降 `_MAX_PHYSICS_DT` 到 1 s 批次慢 5 倍；改隱式離散化連 dt 1 s 的輸出都變。

## 4. 驗證

- **逐位元比對**（seed 1 / 7 / 42 × 1500 步、變動風速與風向）：dt 1 s 全部相同；dt 5 s 改變 52–59 個 tag
  （發電機轉速進電氣頻率、功率、熱模型），所有種子都變，不只出問題的三個。
- **修正後**：14 個種子 × dt 1 / 2.5 / 5 / 10 s，每一步 |gen − rotor| / rotor 最大 0.013 %。
- **守門測試**（`tests/physics/test_invariants.py`）：
  - `test_direct_drive_generator_tracks_rotor_at_batch_substep`：14 種子 × dt 2.5 / 5 s，30 分鐘後的 2 分鐘每一步差 < 1 %。
    舊程式 dt 5 s 有 6 個種子失敗（1 / 2 / 6 / 9 / 10 / 14；dt 2.5 s 都過）。
  - `test_direct_drive_torsion_stable_at_stiff_end_of_individuality`：`DrivetrainModel` 剛性 +16 % / 阻尼 +18 % 在 dt 5 s 收斂。舊程式失敗。
- 範例資料包 01–06 重建（`tools/build_rag_starter_kit.py`）；基準成績與 kit 測試期望見 §5。
- 程式註解與 029 的處置備註拿掉「有的健康機組長期偏離」（`plc_protection.py`、`fault_engine.py`）；029 仍比變頻器轉速。

## 5. Code review（code-reviewer subagent）

Needs revision → 全修：

| 等級 | 發現 | 處理 |
|---|---|---|
| M1 | `test_plc_integration.py::test_other_presets_run_healthy_without_plc_events[vestas_v90_3mw]` 失敗：修正後 V90 停在 TurSt 5 不併網。併網門檻要求發電機機械頻率在電網 ±0.25 Hz 內，V90 轉子上限 16.7 rpm × 104.5 × 4 / 2 / 60 = 58.2 Hz 對 60 Hz 永遠併不上；舊程式只因傳動鏈數值不穩定讓轉速掃過那個窗才碰巧併網（dt 1 s 本來就併不上）。 | 齒輪箱機型視為 DFIG：轉差帶 0.7–1.3 × 電網頻率。Z72 走直驅分支不受影響。 |
| S1 | 齒輪箱 spec 在 dt 5 s 比直驅更糟：預設個體差異就在 28–98 rpm 振盪、剛性 / 阻尼上限發散到 1e72（V90 全模型 rotor 1e39）；放大率 h 5 s 為 1.07–1.08、h 1 s 為 0.77–0.84。 | 寫進 DEC-20261025-01 與 physics_model_status。 |
| S2 | 沒有齒輪箱的守門測試。 | `test_geared_torsion_stable_at_batch_substep`（三組 scale，最後 20 步 gen ≈ rotor × ratio 1 %）＋ `test_geared_preset_generator_tracks_rotor_in_full_model`（V90 併網、gen ≈ rotor × 104.5）。 |
| S3 | 守門測試多 55 s；dt 1 / 2.5 是舊程式也過的控制組。 | 只留 dt 2.5 / 5。 |
| N | 減速夾值改為每子步套一次（dt 5 s 停機暫態不再一步歸零）、子步數沒有上限、`test_plc_protection.py` 註解仍寫「會偏離」。 | DEC 補一句；註解改掉。 |

Reviewer 另做了逐位元檢查（直驅＋齒輪箱、3 種子、3000 步含起停 / 煞車、dt 0.05 / 0.2 / 0.5 / 1.0）：相同。

## 6. 收尾

- **backend 全套**：2191 → 2224 passed / 7 skipped / 1 xfailed（新增守門測試 33 個）。frontend 沒動。
- 範例資料包兩次重建逐位元相同；事件碼不變、時間差 5–10 s（01 / 04 / 06）；基準助手成績不變；kit 測試 42 passed。
- ruff：沒有新 finding（既有的 I001 / UP006 / UP035 / UP045 照舊）。
- PR #235；ISSUES / STATUS / CLAUDE.md / DEC-20261025-01 / EPIC-DS §6.18 / physics_model_status 已更新。

## 7. 下次怎麼接手

- -08 只剩最後一個子項：多重故障＋早期徵兆。先請劉老師定同機組多 case 的評分規則。
- 非 Z72 機型的批次資料此前是壞的（齒輪箱 spec 在 dt 5 s 發散）；若之後要用非 Z72 機型做情境，先把它們的 PLC 設定值與警報目錄從 Z72 的簡化分開（現在共用）。
