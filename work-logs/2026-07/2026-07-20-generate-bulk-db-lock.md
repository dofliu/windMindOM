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
- **#2 未選風場就產生情境 → 無法啟用**：待釐清。理論上「產生新情境」→ activate_simulation 會
  `ensure_default_farm`，不需先選風場。需使用者補充「無法啟用」的具體樣子（按鈕 disabled？錯誤訊息？）
  再對症。**本 PR 先修已確認的 crash（#4）。**

## 卡在哪 / 下次怎麼接手

- **本 PR**：draft + `hold` 待 review（concurrency 改動）→ 收 review → 移除 hold → 自動合。
- 追：#2 farm-context UX（待使用者補充）；view 模式可考慮隱藏註定 400 的 nav。
