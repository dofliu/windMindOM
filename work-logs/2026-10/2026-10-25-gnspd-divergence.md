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
  - `test_direct_drive_generator_tracks_rotor_at_batch_substep`：14 種子 × dt 1 / 2.5 / 5 s，30 分鐘後的 2 分鐘每一步差 < 1 %。
    舊程式 6 組失敗（seed 1 / 2 / 6 × dt 2.5 / 5）。
  - `test_direct_drive_torsion_stable_at_stiff_end_of_individuality`：`DrivetrainModel` 剛性 +16 % / 阻尼 +18 % 在 dt 5 s 收斂。舊程式失敗。
- 範例資料包 01–06 重建（`tools/build_rag_starter_kit.py`）；基準成績與 kit 測試期望見 §5。
- 程式註解與 029 的處置備註拿掉「有的健康機組長期偏離」（`plc_protection.py`、`fault_engine.py`）；029 仍比變頻器轉速。

## 5. 收尾

（見下方補記）
