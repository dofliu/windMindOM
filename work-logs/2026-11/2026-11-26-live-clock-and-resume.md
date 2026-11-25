# 2026-11-26 — Live 時鐘、固定取樣間隔、重啟續跑（WMOM-20261125-03-a / -03-b）

> Session 類型：實作
> Session 長度：長
> 主導：Claude（劉老師指示「開始第 2+3+4 項」）
> 結果：即時模擬的時鐘只往前走、讀值對齊 10 秒；伺服器重啟（含強制關閉）後風場接著原本的狀態跑；產生情境不再弄亂即時風場。第 2 項還剩保留期與分層儲存（-03-c）。

---

## 1. Session 目標

劉老師指示開始第 2、3、4 項。這份紀錄是第 2 項（WMOM-20261125-03）的前兩段：

- -03-a：-02 實測發現的取樣間隔約 10.15 秒、時間倍率改變時時間戳前後跳、加速時資料變稀疏。
- -03-b：伺服器重啟後風場狀態歸零、要有人登入選來源；產生情境會重設即時風場。

## 2. 實際完成

### 2.1 -03-a Live 時鐘與取樣間隔

- `simulator/engine.py` 的 Live 迴圈改寫：
  - 模擬時鐘 `sim_clock` 每步推進剛好一個 `time_step`，起點對齊整秒，只往前走。原本每步讀一次實際時間、dt 卻固定 1 秒，每步約 16 毫秒的計算時間讓模擬慢慢落後。
  - 實際時間走到下一步的時間才算那一步；落後時不等待、全速補跑；落後超過 6 小時（`MAX_CATCH_UP_S`）跳到現在。
  - 時間倍率大於 1 之後調回 1：維持領先的量繼續走。
  - callback 每一步都呼叫（原本加速時每個實際秒只呼叫一次）。
- `data_broker.py`：
  - 寫入依讀值的模擬時間對齊 10 秒時段（`_write_slot`）。啟動後第一筆立刻寫，之後每個時段寫進入該時段的第一筆。
  - Live 的事件沒給時間時用模擬時鐘（`live_clock()`）；指定 session 的事件（情境）不套用。
  - `live_sample_period_s` 固定回 10，不再乘時間倍率。

### 2.2 -03-b 重啟續跑

- `WindFarmSimulator.checkpoint_state()` / `restore_state()`：以 pickle 打包機組物理模型與 PLC、故障引擎、風況 / 電網模型、亂數狀態、模擬時鐘、最新讀值。不含執行緒與鎖、callback、Modbus server、一小時的讀值歷史、批次計數。
- `simulator/checkpoint.py`：存檔檔案 `live_checkpoint.pkl`（與風場 DB 同目錄）。前面是一段 JSON 檔頭，帶格式版本與模擬器程式 / 警報目錄的 sha256；對不上、壞檔、截斷、機組或時區不同都回 None，不解開後面的 pickle。先寫暫存檔再換名。
- broker：
  - `checkpoint_enabled`（伺服器依 `WMOM_LIVE_RESUME` 開）。開了才還原與存檔；產生情境模式不還原也不存。
  - 存檔時機：Live 迴圈每 30 秒在兩步之間存；操作員動過風場的 Live 事件（來源 `faults` / `control` / `config` / `maintenance` / `workflow` / `test_plan`）之後下一步就存；正常停止時再存。
  - 還原後，`_last_write_slot` 接在上次已寫入的時段之後；存檔點比上次寫入早時（伺服器被強制關閉），設重跑段 `_replay_until`：模擬時鐘走到那個時間之前，事件偵測照跑但不寫讀值、事件與快照。重跑段之後到下一個 10 秒時段開始是去重段 `_dedupe_until`：事件逐筆對 storage 查重（`storage.live_event_exists`）。最後一筆讀值離存檔點超過 120 秒就不設這兩段。
  - 還原時把已經開著的故障補進生命週期的基準（不再記一次「故障開始」）；存檔時若在加速，時間倍率回到 1。
  - `start` / `switch_mode` / `POST /api/source/select` 多一個 `fresh`：開了續跑也從頭開始。
  - `pause_live_for_batch`：批次前把 Live 的狀態留在記憶體、批次後還原（不必開存檔）。
  - `live_epoch`：這份狀態從頭開始的那個 session 的 id，寫在存檔裡，還原沿用。
- `server/app.py`：讀 `WMOM_LIVE_RESUME`；`WMOM_AUTOSTART_SOURCE=simulation` 時開機就啟動即時模擬（啟動失敗不讓伺服器起不來）。套用風場規格時，規格相同就不呼叫 `update_spec`（它會重建 PLC 保護層，清掉還原的鎖存）。
- 對外 API：`/status` 的 `live_epoch` 改用 broker 的；端點與欄位沒有變。`external_api_v1.md` §5 改寫。

### 2.3 驗證

- 新測試 56 項：`test_live_clock.py` 14 項、`test_live_resume.py` 27 項、`test_source_selection.py` 多 15 項（環境變數、開機自動啟動、`fresh`）。
- 還原的正確性：注入故障並跳機後存檔，還原到另一個模擬器，兩邊接著跑 120 步，每一步所有機組的 SCADA 值逐位元相同。
- 變異檢查：第一輪 3 項（不設重跑段、批次後不還原、事件不跟模擬時鐘），code review 之後再 12 項（見 §2.5），都被測試抓到。
- 量測（14 台）：存檔 1.2–1.5 MB、打包 26 毫秒、還原 26 毫秒；Live 一步約 13 毫秒，補跑約 75 倍速（量測時另有測試在跑）。
- **真伺服器**（`WMOM_AUTH_ENFORCE=true`、`WMOM_LIVE_RESUME=true`、`WMOM_AUTOSTART_SOURCE=simulation`、資料目錄指到暫存位置）：
  - 沒有人登入，啟動後 `live` 即為 true；讀值時間落在 `:10 / :20 / :30`，間隔全是 10 秒。
  - 注入 WT003 量測回路斷線，跳機 242 鎖存。`kill -9`，40 秒後重啟：log 印出已還原；`/alarms/active` 仍有 WT003 的 242；`live_epoch` 不變；242 的跳機事件只有一筆。
  - 第一次重啟後看到重複的讀值（存檔點 18:03:31、強制關閉前已寫到 18:03:50，重跑時又寫了一次）。加了重跑段之後重做：`kill -9` 前後共 9 筆，間隔全是 10 秒、沒有重複，42 筆事件沒有重複。
  - 正常停止（SIGTERM）再重啟：同樣還原。
  - 中途我改了 `engine.py`，再啟動時 log 印出「存檔不還原（模擬器程式或警報目錄改過），從頭開始」，風場從頭開始、`live_epoch` 改變——這是設計的行為，也表示模擬器程式每更新一次，風場狀態會重來一次。
- 回歸與 code review 見 §2.5。

### 2.4 卡住或延後的事

- -03-c（保留期可設定、分層儲存）還沒做，原始讀值仍只留 3 天。
- 72 小時連續運轉測試沒有做（一個 session 內做不了）；這次最長只連續跑幾分鐘。
- 企劃 v0.1 記的「雲端長跑約 57 分停止寫入」「十分鐘彙整重疊計數」沒有重現：原始紀錄不在 repo，這次也沒有碰到。`storage.run_downsampling` 的 1 分鐘 / 10 分鐘彙整沒有改。
- 風場狀態重來時（沒開續跑、程式更新、機組數改變），前一段鎖存的跳機沒有解除事件，只以 `live_epoch` 改變標示。
- 產生情境仍與即時模擬共用同一個模擬器物件（批次前後保存 / 還原狀態），沒有改成另建一個。
- 補跑上限 6 小時是我定的；伺服器停超過 6 小時，重啟後中間是缺口。

### 2.5 回歸測試與 code review

`code-reviewer` 子代理審了整份 diff。沒有發現資料損毀，找出三個必須修的問題與一批該補強的地方，都修了：

| 審查意見 | 處理 |
|---|---|
| 正常重啟時故障還開著，重啟後會再記一次「故障開始」 | 還原時把開著的故障補進基準 |
| 來源種類在起迴圈之後才設，第一步的事件拿到實際時間 | 先設來源種類再起迴圈 |
| 強制關閉前最後幾秒的事件（最後一筆讀值之後記的）重啟後會重複 | 去重段：事件逐筆對 storage 查重 |
| 重跑段沒有上限，遠處的列會讓即時資料很久不寫 | 最後一筆讀值離存檔點超過 120 秒就不當依據 |
| 故障移除時直接呼叫 storage 關事件：重跑段會誤關、結束時間用實際時間 | 改走 broker 的 `close_open_events`（重跑段不關、時間跟模擬時鐘） |
| 快照視窗用實際時間算，補跑 / 加速時一次事件會存下幾十萬列 | 視窗與冷卻改用模擬時間；事件參照的時間字串也跟模擬時鐘 |
| 還原途中出錯、存檔檔頭欄位讀不懂、自動啟動出錯會讓伺服器起不來 | 都包起來：當成沒有存檔 / 留在未選來源 |
| 批次會洗掉走勢小圖的一小時歷史 | 批次前後保留 |
| 批次端點回報的「結束時故障狀態」是在還原 Live 之後才取的 | 移到 `pause_live_for_batch` 區塊裡 |
| 批次後還原失敗時 `live_epoch` 沒變 | 還原失敗就換一個編號 |
| callback 出錯被靜靜吞掉；迴圈出錯時用不能中斷的 `time.sleep` | 第一次與之後每 600 次印一行；改用可喚醒的等待 |
| 存檔失敗要等 30 秒才再試 | 5 秒後重試 |
| 外層用 pickle | 改成 JSON 檔頭＋pickle 內容 |

沒有照做的：審查建議把去重做成資料庫的唯一索引。事件表沒有自然的唯一鍵（同一時刻同標題的事件在情境 session 是合法的），所以只在重啟後的那幾步查重。

變異檢查 12 項（拿掉一個防護、確認對應的測試轉紅）：不補生命週期基準、去重段不查重、重跑段不設上限、來源種類晚設、兩個批次端點的故障狀態晚取、快照視窗用實際時間、關閉事件用實際時間、`fresh` 也還原、時間倍率不調回、走勢歷史不放回、還原失敗不換編號——全部被抓到。

回歸測試與真伺服器複驗的結果見 §2.7。

### 2.7 修完之後的回歸與真伺服器複驗

- backend 全部：2369 passed / 1 skipped / 1 xfailed（本機；前一次是 2313，多的 56 項就是這次新增的）。前端沒有動。
- 真伺服器（另一個乾淨的資料目錄，設定同 §2.3）：
  - 注入 WT003 斷線、跳機後約 1 分鐘 `kill -9`，重啟：log 印出已還原；242 仍在 `/alarms/active`；`live_epoch` 不變；讀值間隔全是 10 秒（啟動後第一筆除外）、沒有重複；47 筆事件沒有重複；「故障開始」只有一筆。
  - **去重段的情況**：在 10 秒時段的第 1 秒注入 WT005 斷線（存檔在 18:42:41，最後一筆讀值 18:42:40），跳機在 18:42:44，18:42:45 `kill -9`。重啟後 242 跳機、「故障開始」、自動跳機事件都仍只有一筆，53 筆事件沒有重複，讀值接著每 10 秒一筆；WT003 與 WT005 的 242 都還鎖存著。
  - 正常停止（SIGTERM）再重啟：還原、沒有新的重複事件、`live_epoch` 不變。
  - `POST /api/source/select` 帶 `{"mode": "simulation", "fresh": true}`：`live_epoch` 由 1 變 5，`/alarms/active` 沒有任何鎖存。

### 2.6 重大決策

- DEC-20261126-02。

## 3. 產出清單

### 新增檔案

- `modules/monitoring/simulator/checkpoint.py`
- `modules/monitoring/tests/test_live_clock.py`、`modules/monitoring/tests/test_live_resume.py`
- `work-logs/2026-11/2026-11-26-live-clock-and-resume.md`

### 修改檔案

- `modules/monitoring/simulator/engine.py`、`modules/monitoring/server/data_broker.py`、`modules/monitoring/server/app.py`、`modules/monitoring/server/routers/external.py`
- `.gitignore`（存檔檔案）、`README.md`（兩個環境變數）
- `docs/integration/external_api_v1.md`、`docs/product/decision_log.md`、`docs/product/ROADMAP.md`、`docs/architecture/research-framework.md`
- `CLAUDE.md`、`ISSUES.md`、`STATUS.yaml`、`TODO.md`

### 動了狀態的 issue

- WMOM-20261125-03：open → in_progress
- WMOM-20261125-03-a、-03-b：新開 → done

### 寫進 decision_log 的決策

- DEC-20261126-02

## 4. 下次怎麼接手

- 接著做 -03-c：保留期由設定決定；較舊的 Live 讀值轉成每日 Parquet 檔（依機組分 row group），清理只刪已經歸檔的；對外 API 的讀值與統計跨兩層查。
- 要讓風場持續運轉：伺服器開 `WMOM_LIVE_RESUME=true` 與 `WMOM_AUTOSTART_SOURCE=simulation`。
- 會隨時間演變的新狀態要掛在 `_CHECKPOINT_FIELDS` 列的物件底下、要能 pickle；`test_live_resume.py` 的逐位元比對會抓到漏掉的。
