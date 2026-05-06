# 2026-05-06 — Physics 自我驗證框架 Layer 1（守恆律）

> Session 類型：實作
> Session 長度：中
> 主導：劉老師 + Claude
> 結果：Layer 1 conservation laws 6 大守恆驗證 + tests/physics/ 骨架就位，pytest 全 pass

---

## 1. Session 目標

WMOM-20260505-23 Layer 1 — Conservation Laws / 物理上限。
建立 `tests/physics/` 骨架（為後續 Layer 2-7 鋪路），實作 6 大守恆驗證：

1. Betz 限：Cp ≤ 0.593 across (V, λ, β) grid
2. 能量守恆：P_aero formula consistency + P_elec ≤ P_aero（loss-only 方向性）
3. 動量平衡：thrust 公式 T = ½ρACtV² 一致性
4. 角動量：rotor_speed × gear_ratio ≈ gen_speed（含 direct-drive 與 geared 兩種）
5. 熱平衡：ThermalElement 穩態 T - T_amb = Q × R_th
6. 質量守恆：冷卻液 level decay 與 leak rate 對得上

加上**負向測試**（故意把 Betz 上限改錯，驗 framework 真的能 catch）。

---

## 2. 實際完成

### 2.1 主要工作

- 探索 `modules/monitoring/simulator/physics/` 全 14 模組，確認 API 切入點：
  - `CpSurfaceModel.get_cp(tsr, pitch_deg)` → Cp 直接取
  - `CpSurfaceModel.get_aero_thrust_kn(...)` → thrust 公式驗證
  - `TurbinePhysicsModel.rotor_speed` / `.drivetrain.generator_speed` → 角動量
  - `ThermalElement` (`thermal_model.py`) → 熱平衡
  - `WaterCoolingLoop._coolant_level_pct` (`cooling_model.py`) → 質量守恆
- 建立 `tests/physics/` 骨架：`__init__.py` / `conftest.py` / `reports/README.md`
- conftest.py 內含 `sys.path` 設定（指向 modules/monitoring）+ Layer 7 報告 hook 預留位
- 6 個守恆 test class 共 ~25 個 test cases
- **負向測試**：刻意把 cp_max 設為 0.7（高於 Betz）驗證 Layer 1 fail 出來

### 2.2 卡住或延後的事

- Layer 7（測試紀錄保存）conftest.py hook 只留 skeleton，等之後完整 Layer 7 issue 再實作 markdown/JSON 自動產出
- gear_ratio 角動量測試用 `DrivetrainSpec.for_geared(ratio=104.5)` 直接測 model，不走 full TurbinePhysicsModel — 因為 Z72 預設 direct-drive

### 2.3 重大決策（如有）

無新 ADR。沿用 issue 描述的 6 層 framework 設計。

---

## 3. 產出清單

### 新增檔案

- `tests/physics/__init__.py`
- `tests/physics/conftest.py`（sys.path + Layer 7 hook skeleton）
- `tests/physics/test_invariants.py`（Layer 1 — 6 大守恆 ~25 test cases）
- `tests/physics/reports/README.md`（資料夾用途 + retention 政策說明）
- `tests/physics/reports/.gitkeep`（保證資料夾在 git 中）

### 修改檔案

- `ISSUES.md`（WMOM-23 status: open → in_progress，Layer 1 deliverable 標記）
- `STATUS.yaml`（next_milestone 更新到 Layer 2）
- `work-logs/2026-05/2026-05-06-physics-validation-layer1.md`（本檔）

### 動了狀態的 issue

- WMOM-20260505-23: open → in_progress（Layer 1/7 完成，Layer 2-6 排隊中）

---

## 4. 下次怎麼接手

下一個 session 從 Layer 2（Literature / Standard Benchmarks）開始：

- IEC 61400-1 Kaimal：σ_v / V_mean ≈ TI（強風下）
- Bastankhah wake：Ct=0.82, TI=8%, x=5D → deficit 25-35%
- Glauert NTF：Region 2 a≈0.33 → V_raw/V_∞ ≈ 0.84
- BPFO/BPFI：Tedric Harris formula
- ISO 10816-3 Class III：vibration RMS zone boundaries
- Walther viscosity decay
- ISA air density 1.2250 kg/m³

檔案：`tests/physics/test_benchmarks.py`

跑驗證：`cd modules/monitoring && python -m pytest ../../tests/physics/ -v`
