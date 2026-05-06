# 2026-05-06 — Physics 自我驗證框架 Layer 1-7 全完成

> Session 類型：實作（全天，連 7 層 + review + fix + 報告系統）
> Session 長度：長
> 主導：劉老師 + Claude
> 結果：**WMOM-23 close** — 121 pytest tests pass in 25 s + health check CLI + 報告紀錄系統就位

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
- `tests/physics/conftest.py`（sys.path + Layer 7 pytest_sessionfinish hook + baseline drift compute）
- `tests/physics/test_invariants.py`（Layer 1 — 6 大守恆 36 cases，含 sentinel）
- `tests/physics/test_benchmarks.py`（Layer 2 — 7 大文獻 benchmark 35 cases）
- `tests/physics/test_envelope.py`（Layer 3 — 7 大操作邊界 18 cases）
- `tests/physics/test_consistency.py`（Layer 4 — 5 大跨模組一致性 9 cases）
- `tests/physics/test_fault_signature.py`（Layer 5 — 11 fault scenarios + 3 baseline 23 cases）
- `tools/physics_health_check.py`（Layer 6 — 一鍵體檢 CLI）
- `tests/physics/reports/README.md`（資料夾用途 + retention 說明）
- `tests/physics/reports/.gitkeep`
- `tests/physics/reports/_baseline/pytest_baseline.{md,json}`（Layer 7 — 初始 baseline）
- `tests/physics/reports/2026/05/2026-05-06-1203-pytest.{md,json}`（Layer 7 — 第一份 sample 報告）

### 修改檔案

- `ISSUES.md`（WMOM-23 status: open → in_progress，Layer 1 deliverable 標記）
- `STATUS.yaml`（next_milestone 更新到 Layer 2）
- `work-logs/2026-05/2026-05-06-physics-validation-layer1.md`（本檔）

### 動了狀態的 issue

- WMOM-20260505-23: open → **done**（Layer 1-7 全部完成，含 code review fixes）

---

## 4. 下次怎麼接手

WMOM-23 已全部完成。下一個建議任務：

**選項 A**：WMOM-24（Data quality 3 項 fail 修正）— Layer 4 已埋了 spread/CV 結構性 bound（容差寬鬆），WMOM-24 完成後可把 Layer 4 容差收緊到 [10%, 25%] / [3%, 8%]，把整個 framework 變更鋒利。0.5-1 工作天。

**選項 B**：WMOM-19 frontend 接力 — 之前暫緩，現在 backend 與物理驗證都鎖好，回頭做 frontend 風險低。

跑體檢：`python tools/physics_health_check.py`（pytest 121 + short sim + 4 health checks，~50 s 全程）

每次改 physics 後跑一次體檢、commit 進 reports/，方便追溯漂移。
