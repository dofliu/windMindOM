# 2026-07-20 — 修 generate-bulk「database is locked」+ Modbus 起不來降級｜WMOM-20260720-01

> Session 類型：#3 上線後實測 bug（使用者於 Windows 實機回報 500）
> 產出：本 PR（Live 迴圈於批次期間退場 + 批次單一 transaction + Modbus 降級）
> 對應 issue：WMOM-20260720-01

---

## 使用者回報

選「即時模擬 / 產生新情境」後（Live 自由跑迴圈啟動），在 Live 跑著時產生情境，Windows 上
`generate-bulk` 500：`sqlite3.OperationalError: database is locked`（且 except 內的
`update_session_config({"status":"error"})` 收尾寫入**也**再撞一次 lock）。

## 根因

`_running` 同時是 Live `_loop` thread 與 `generate_bulk` 的「續跑」旗標，選模擬後兩者並行：
1. Live thread 與批次**同時 step 同一組物理模型**（race）。
2. **兩個 writer 並寫同一 SQLite 檔** → 寫鎖競爭。加上 `store_reading` **逐列 commit**（一批
   2000+ 筆＝2000+ 次寫鎖取得），Windows SQLite 較嚴格 → busy_timeout(5s) 被耗盡 → locked。

## 做了什麼

1. **Live 迴圈於批次期間退場**（`engine.stop_live_loop()` / `restore_live_loop()` +
   `config.py` generate-bulk）：批次前停 Live thread（以 thread 是否 alive 判斷，非 `_running`）、
   保持 `_running=True` 供批次；**情境收尾寫入趁 Live 仍停時做**（修好 except 收尾也撞 lock 的
   二次崩）；`finally` 恢復 Live。→ 批次全程無並行 writer，也順帶消掉物理 race。
2. **批次單一 transaction**（`storage.store_readings`）：抽 `_insert_reading`（不 commit），批次
   整批一次 commit（失敗整批 rollback）——把逐列 commit 的鎖取得降到 1 次、且更快。
3. **Modbus 起不來降級**（`app.activate_simulation`）：Modbus TCP 是選配（外部 client 用），
   版本/port 問題起不來時 try/except 降級為「無 Modbus 的模擬」而非讓整個來源啟動 500。

## 驗證

- **端到端 verify（真 app + HTTP）**：選 simulation（Live thread 起）→ 在 Live 跑著時
  generate-bulk → **200**（原崩點）、情境 252 筆存入且可調閱、Live 事後恢復。
- **機制 verify**：Live 寫 24 筆→`stop_live_loop`（thread 停）→批次 54 筆寫情境 session→
  `restore_live_loop`（thread 恢復），情境/ Live 資料隔離。
- +3 tests（stop/restore 無 thread 安全、批次原子寫入）；monitoring **102** + physics **121** 全綠。

## 使用者其餘幾點

- **#1 選「調閱過去情境」但無情境 → 完全沒資料**：**預期**。view 模式不起任何來源、只讀
  storage 的過去情境；第一次用沒有情境就是空（ScenarioPage 已有「還沒有保存的情境」空狀態）。
- **#2 未選風場就產生情境 → 無法啟用**：**已定位根因（非風場問題）**。使用者從「調閱過去情境」
  進來 → `select_view_only()` 把 `simulator=None`（view 只讀 storage、不起模擬）。此時到情境頁按
  「生成」→ `generate-bulk` 命中 `if not b.simulator: raise 400 "Simulator not running"`
  （config.py:288）→ 前端顯示「生成失敗：Simulator not running」＝使用者說的「無法啟用」。
  之後「選某個風場」→ `switch_farm()` → `start()` → `_start_simulator()` **順帶起了 live 迴圈**
  → 才能生成（#3），**但那個 live 迴圈正是害 #4 撞 db-lock 的併發 writer**（本 PR #142 修）。
  → **本 PR（#142）先修已確認的 crash（#4）**；#2 留作 follow-up：情境頁若尚未起模擬，給明確
  提示 +「一鍵啟動模擬以生成」按鈕（呼叫 `/api/source/select {mode:simulation}`），讓「產生情境」
  不必繞「先 activate 一個 farm 順帶起 live 迴圈」這條會撞 #4 的路。待 #142 合併後接著做。

## Code review 補強（第一輪 review 收斂）

code-reviewer 對本 PR 找到 3 Must-fix（皆用 scratch 實驗 + git-worktree mutation test 佐證），已全數修正：

1. **Must-fix #1 姊妹端點漏保護**：`faults.py::run_test_plan`（`/api/faults/test-plans/{id}/run`）
   與 generate-bulk 同一套「同步 generate_bulk + store_readings」模式，也可在 Live 跑著時被叫，
   卻沒停 Live → 同樣會撞 lock。→ 抽共用 context manager **`DataBroker.pause_live_for_batch()`**，
   config.py 與 faults.py 都改用它（集中一處、避免未來第三個呼叫點漏套）。
2. **Must-fix #2 借屍還魂 + thread 洩漏**：舊 `stop_live_loop` 把**共用**的 `_running` 設回 True，
   若 `stop()` 的 `join(timeout=5)` 逾時（Live 單步在鎖競爭下 >5s，正是本 bug 情境），尚未退出的
   舊 thread 會續跑成第二個 writer，`restore_live_loop` 又 `start()` 新 thread → 舊 thread + 其
   SQLite connection 洩漏。→ (a) 批次改用**獨立** `_bulk_running` 旗標與 `_running` **解耦**；
   (b) `stop_live_loop` 於 `stop()` 後**阻塞式再 join** 保證舊 thread 死透才返回。
   已用 slow-step（單步 6s）scratch 驗證：stop 耗 5.8s、舊 thread `is_alive()=False`、0 洩漏。
3. **Must-fix #3 假綠測試**：舊測試只用「沒 start() 過」的 sim（`_thread=None`），mutation test 證實
   `was_running=True` 主流程完全沒蓋到。→ 補**真 thread** 測試（start → stop_live_loop 斷言 thread
   真的死 → restore 斷言起新 thread）+ store_readings **中途失敗 rollback** 測試 + 解耦旗標回歸測試。

順帶收斂的 Should-fix：`fault_engine.clear()` 挪到停 Live 之後（消去與 Live `fault_engine.step()`
的物理狀態 race）；config.py 過時 docstring 更新；`restore_live_loop` 補 `-> None` + Args；
app.py Modbus 降級抽成可測的 `_start_modbus_for()`（+3 test）並修正註解（實際攔的是 pymodbus 建構
失敗，非 port 佔用）；storage 三個簽名補 `Optional[int]`。

**測試**：monitoring **109** passed（102 + 7 新）、physics + e2e **127** passed；ruff 全綠。

### 第二輪 focused re-review 收斂

re-review 確認**production 邏輯正確**（無 deadlock、無正確性 bug、旗標解耦/reorder/阻塞 join 皆逐行驗過），
但用 mutation test 抓到我**新測試仍有假綠**（正是第一輪 Must-fix #3 要根除的）：3 個並發安全性質有 2 個
沒被 pin、`run_test_plan` 端點根本無測試。全數補上並**自行 mutation 驗證**每個測試都真的會抓退化：

1. **姊妹端點 run_test_plan 無測試** → 補真 thread 測試（spy 於批次當下斷言 Live thread 已停、事後恢復）。
   MUTANT-C（拿掉 pause 包裹）→ 轉紅 ✓。
2. **`_bulk_running` 中止語意未被證** → 補「生成途中清旗標應即停」測試。MUTANT-B（旗標永不 break）→
   `assert 360 == 2` 轉紅 ✓。
3. **阻塞 join 未被 join-timeout 情境證**（原測試 time_step 太短，第一個 join(5) 根本不逾時）→ 補
   monkeypatch join(timeout)→0.05s + gate 卡住單步的測試。MUTANT-A（拿掉阻塞 join）→ thread 仍 alive
   轉紅 ✓。

順帶收 Should-fix / nits：`_start_modbus_for` 補型別（TYPE_CHECKING guard）；`Iterator[bool]` 去引號；
config.py `sim.fault_engine.clear()`；`SimulationConfig.timeStep` 加上界 `Field(gt=0, le=60)`（消掉阻塞
join 的「理論無上界等待」；UI 從不送此值，僅直呼 API 可達）；docstring 補述 maintenance thread 不受暫停。

**測試（第二輪後）**：monitoring **112** passed（+3 Must-fix 測試，皆 mutation 驗證會抓退化）、
physics + e2e **127** passed；ruff 全綠。

## 卡在哪 / 下次怎麼接手

- **本 PR**：兩輪 review 皆收斂（production 邏輯經第二輪逐行確認正確，測試假綠已補齊並自驗）。
  移除 `hold` → CI 綠自動合。
- **#2 follow-up（已定approach）**：使用者選「一鍵啟動提示」——情境頁若尚未起模擬，顯示明確提示 +
  「啟動模擬以生成」按鈕（呼叫 `/api/source/select {mode:simulation}`），不繞會撞 #4 的 farm-activate。
  待 #142 合併後接著做（避免與本 PR 改到的 generate_bulk 衝突）。
- 追：view 模式可考慮隱藏註定 400 的 nav（Faults/Settings）。
