# 2026-07-20 — 情境=凍結資料集 PR B：產生情境不自由跑｜WMOM-20260720-07

> Session 類型：DEC-20260720-01 的 PR B（承 PR A #146 merged）
> 產出：本 PR（選「產生新情境」不再自由跑）+ DEC-20260720-02（情境比較分析 epic 立案）
> 對應 issue：WMOM-20260720-07

---

## 背景

DEC-20260720-01 定「情境＝凍結資料集」。現況：選「產生新情境」＝ `activate_simulation` → simulator
**起自由跑背景迴圈**，持續把資料寫進 live session——不符「情境不該一直產新資料」。

## 做了什麼

**後端（run_loop 貫穿）**
- `data_broker._start_simulator(run_loop=True)`：`run_loop=False` 時只建 simulator（供批次生成），
  **不呼叫 `simulator.start()`**（不起自由跑 thread）。
- `data_broker.start / switch_mode` 加 `run_loop`；SIMULATION 時 `source_kind = 'simulation' if run_loop
  else 'scenario'`。
- `app.activate_simulation(run_loop=True)`：傳給 switch_mode；`run_loop=False` 時**不起 Modbus**（無連續
  即時值可讀）。
- `source.py`：`mode=='scenario'` → `activate_simulation(run_loop=False)`；`mode=='simulation'` →
  `run_loop=True`。

**前端（scenario 來源種類）**
- `SourceMode` 加 `'scenario'`；App「產生新情境」卡 → `mode='scenario'`（原本誤送 'simulation'）。
- `ScenarioPage`：生成 gate 放行 `scenario`（`simActive = simulation || scenario`）；一鍵啟動改走
  `mode='scenario'`（要批次生成，不需自由跑）。
- `SettingsPage`：`liveTuningBlocked` 一併擋 `scenario`——情境風況於生成時（情境頁）設定，且與 view/live
  同理避免「改 sim 參數儲存 → 後端 switch_mode 切回即時模擬」（延續 #146 Must-fix 防線）。

## 驗證

- **backend**：`broker.start(run_loop=False)` → simulator 存在但 `is_running=False`、`source_kind='scenario'`；
  `run_loop=True` → 自由跑、`simulation`；endpoint `mode=scenario/simulation` → `activate_simulation` 收到
  正確 `run_loop`。+4 backend 測；monitoring 112→116、physics+e2e 全綠（243 passed）。
- **frontend**：ScenarioPage scenario→生成啟用、一鍵啟動送 `mode:scenario`；SettingsPage scenario→擋。
  +4 前端測；全前端 **937** passed、tsc/build 綠。

## DEC-20260720-02 立案（情境比較分析 epic）

Explore 確認**所有物理輸出已落地在 `scada_json`**（含累積損傷/DEL/RUL/齒面磨耗），極限負載可由瞬時彎矩
`MAX()` 求得 → 此 epic 是**讀取/聚合/對齊/UI**工作，不需重新落地。拆 A0 摘要 → A1 同情境內 → A2 跨情境
（相對時間對齊）→ A3。順序 **B → A0 → C 與 A1/A2 並進**。

## 卡在哪 / 下次怎麼接手

- 本 PR：draft + `hold` 待 review → 移除 → 合。
- 下一步：**A0 情境摘要端點**（DEC-20260720-02，資料已備、可獨立出價值）；PR C 前寫 broker 子設計。
