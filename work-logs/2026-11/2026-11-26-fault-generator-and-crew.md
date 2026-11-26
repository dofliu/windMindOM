# 2026-11-26 — 第 5 項：機率式故障、故障紀錄、模擬維修班（WMOM-20261125-06）

> Session 類型：實作
> 主導：Claude（劉老師：「同意，照這個方向開始第五項」）
> 這一項拆成幾段，各自測試、各自開 PR。本檔隨每一段補上。

---

## -06-a　鎖存解除後機組重啟再跳（done）

**做了什麼**

- `simulator/engine.py`：`retrip_after_restart`。只在即時模擬生效（批次時無效）。
- `simulator/physics/fault_engine.py`：`keep_tripped_active`——跳過機的故障照樣作用在機組上。
- `simulator/physics/turbine_physics.py`：`lock_blocks_restart`——維護鎖擋不擋重啟。
- `server/data_broker.py`、`server/app.py`：`live_retrip`；伺服器依 `WMOM_LIVE_RETRIP` 預設開。
- `server/om_loop.py`：A039 在那台機組已有未結案的故障維修工單時不另開一張；帶著故障重啟、還在發電的那幾分鐘算發電。

**實測**（測試用的風場，軸承磨耗）：發電 → 跳機 240 → 80 秒後鎖存解除 → 重啟、發電約 5 分鐘 → 再跳 240 → 75 秒後 A039，機組停在 SHUTDOWN、240 保持鎖存。工單一張（240）。復位之後又跳；工單完工後 10 分鐘內沒有再跳。量測回路斷線：242 一直鎖著，行為和以前一樣。

**測試**：`test_a_faulty_turbine_restarts_and_trips_again_until_the_work_order_is_finished`、`test_batch_scenarios_keep_the_maintenance_lock`；`test_emergency_trips_and_blocked_restarts_get_high_priority` 依新的 A039 規則更新。backend 全部（本機）：2505 passed / 7 skipped / 1 xfailed。

**決策**：DEC-20261126-07。

**沒有做**：批次情境（題庫）維持跳機後停到維護清除，沒有改。
