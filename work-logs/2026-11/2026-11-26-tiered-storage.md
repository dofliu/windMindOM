# 2026-11-26 — 保留期可設定、分層儲存（WMOM-20261125-03-c）

> Session 類型：實作
> Session 長度：長（與 -03-a / -03-b 同一個 session）
> 主導：Claude（劉老師指示「開始第 2+3+4 項」）
> 結果：10 秒原始讀值預設留半年。最近 3 天在 SQLite，較舊的在每日 Parquet 檔，對外 API 用同一個游標查兩層。第 2 項的三段都完成。

---

## 1. Session 目標

第 2 項（WMOM-20261125-03）的第三段：原始讀值原本只留 3 天（寫死）。目標是半年（DEC-20261125-01），而且準備卡（第 4 項）要回看 7 到 30 天。

## 2. 實際完成

### 2.1 量測

一整天、14 台機組、10 秒取樣（120,960 列）：

| | 大小 | 每列 |
|---|---|---|
| SQLite（`turbine_data`） | 505 MB | 4.2 KB |
| 每日 Parquet 檔（zstd、每台機組一個 row group） | 15.9 MB | 131 bytes |

半年：只用 SQLite 約 91 GB；兩層約 4.4 GB（歸檔 2.9 GB＋SQLite 3 天 1.5 GB）。

### 2.2 做了什麼

- `server/live_archive.py`（新）：`LiveArchive`。
  - `sync`：把資料時鐘已經過完的 UTC 日寫成日檔；之後才寫進來的列（列數或最大 id 變了）會重寫那一天；中途出錯就停在那一天之前。
  - 索引 `index.json` 記 `archived_through`（這之前都已在日檔裡）與 `hot_from`（SQLite 已刪到這裡），兩個都只往前。
  - `prune`：刪最舊的日檔。`readings`：依 id 讀，日檔的 id 範圍重疊時會合併。
  - 整數超出 PLC 型別範圍的值存成缺值，不讓一筆壞值卡住整天的歸檔。
- `server/live_history.py`（新）：`LiveHistory.readings` 兩層查詢，以 `hot_from` 分界、依 id 合併；查到一半界線被推動就照新的索引重查。
- `server/plc_types.py`（新）：`typed_column` / `plc_typed`，兩層共用的型別轉換（REAL＝float32、整數取整、超出型別範圍＝缺值）。
- `server/storage.py`：`reading_turbine_ids`、`earliest_live_reading_timestamp`、`reading_id_sequence`、`live_span`、`delete_archived_live_readings`（每一天只刪 id 不大於該日檔最大 id 的列，逐台機組各一個交易）、`delete_live_readings_before`（超過總保留期的），`run_cleanup` 加 `raw_tiered`（分層儲存時不動 raw）。這些查詢都帶機組：`turbine_data` 只有 `(turbine_id, timestamp)` 索引，不帶機組的時間範圍查詢會掃整張表。
- `server/data_broker.py`：`raw_hot_days` / `archive_days`；`run_retention`（歸檔 → 記界線 → 清 SQLite → 循環保存），maintenance 執行緒每小時呼叫；`live_history` / `live_archive`；`_continue_after_stored_data`。
- `simulator/engine.py`：`start_clock_after`。
- `server/routers/external.py`：`/readings`、`/stats-10min` 改走 `live_history`；`/status` 加 `raw_retention_days`；`EXTERNAL_API_VERSION` 1.1。
- `server/routers/config.py`：`/storage/stats` 回報總天數、熱資料天數與歸檔摘要；`/storage/maintenance` 走 `run_retention`（放到背景執行緒）。
- `server/app.py`：`WMOM_RAW_RETENTION_DAYS`（預設 183，0＝不歸檔）、`WMOM_RAW_HOT_DAYS`（預設 3）。

### 2.3 做到一半改掉的設計

- **兩層的分界原本用 id**（比 SQLite 最小的 Live id 還小的由歸檔給）。id 的順序不一定等於時間的順序：沒有命名的批次會把未來時間的列先寫進 Live session。改成以時間 `hot_from` 分界、兩層依 id 合併。
- **清理的界線原本對齊整天**。整天一次刪 12 萬列（約 0.5 GB）；改成每小時推進一點，並且逐台機組各一個交易。
- **歸檔的查詢原本不帶機組**。`turbine_data` 沒有純時間的索引，會掃整張表；改成逐台機組走 `(turbine_id, timestamp)` 索引。
- **統計在兩層算出來不同**：歸檔是 float32，SQLite 的 JSON 是 float64，同一個 10 分鐘窗的平均值最後一位有效數字會差。改成 SQLite 那一層先轉成 PLC 型別（`plc_typed`），兩層給的值相同。`/stats-10min` 個別值的最後一位可能因此和 API 1.0 不同。
- **即時模擬從頭開始時時鐘會跳回實際時間**（之前用過時間倍率的話）。同一段時間會有兩份讀值，每日歸檔與依時間的查詢都會混在一起。改成時鐘接在已存的 Live 讀值之後。

### 2.4 驗證

驗證結果、code review 與回歸測試見 §2.6（收尾時補上）。

### 2.5 卡住或延後的事

- 72 小時連續運轉測試沒有做，另開 WMOM-20261126-01。
- 歷史回填（先用批次補出一段歷史，再接著 Live 運轉）沒有做，另開 WMOM-20261126-02。現在的做法下，時間早於 `hot_from` 的列若之後才寫進 Live，不會進歸檔，回填要另外處理。
- 1 分鐘彙整（留 90 天）與事件快照（留 7 天）仍照實際時間清理；10 分鐘彙整與事件永久保留，沒有動。
- 沒有命名的批次仍會把模擬時間的列寫進 Live session（既有行為）。持續運轉的風場不該這樣用，這次沒有擋。
- 管理端畫面（前端）沒有顯示歸檔的摘要；`/api/config/storage/stats` 已經有資料。
- SQLite 檔刪除後不會縮小（空間重複使用），沒有做 `VACUUM`。

### 2.6 驗證、code review 與回歸測試

**量測**（一整天 14 台、0.5 GB 的 DB，修完 code review 之後）：

| | 時間 |
|---|---|
| 歸檔一天（`sync`） | 5.2 秒 |
| 沒有變動時再檢查一次 | 0.16 秒 |
| 記界線＋清掉一整天（12 萬列）＋循環保存 | 4.3 秒 |
| 清理期間另一條執行緒照 Live 節奏寫入 | 最久等 0.39 秒，中位數 1 毫秒 |
| 從歸檔讀一頁 1000 筆 | 0.04 秒 |
| 從歸檔掃一台機組 24 小時（統計用） | 0.08 秒 |
| 輪詢最新資料（游標在最後） | 不開日檔 |
| 索引壞掉後從日檔重建 | 0.01 秒 |

清理前後查到的內容相同（id、時間、每個欄位的值）。

**code review**（`code-reviewer` 子代理）：盲測邊界沒有破——對外 API 只把 `pack_columns()` 的欄位傳給歸檔，內部量與 `session_id` 只在日檔裡。找出 3 項必須修與 8 項該補強的：

| 審查意見 | 處理 |
|---|---|
| 索引讀不出來被當成「沒有歸檔」：下一次 `sync` 把舊日檔從索引丟掉，查詢少了一段（重現：864 列剩 576 列） | 讀不出來就報錯；`sync` 從日檔重建索引；對外 API 回 503 |
| maintenance 執行緒與手動維護可以同時跑，互相蓋掉日檔與索引 | `run_retention` 加鎖 |
| 整數超出 PLC 型別範圍時，SQLite 給原值、歸檔給缺值 | 兩層共用 `plc_types.py`：超出範圍一律缺值 |
| 查到一半界線被推動，中間那一段兩邊都沒給 | 同一次查詢用同一份索引，查完發現界線變了就重查 |
| 界線之前的列查完才濾掉，一頁變短，被當成最後一頁 | 被濾掉的不算數，不夠一頁就接著拿 |
| 資料時鐘和 storage 可能不是同一座風場的 | 傳同一個 storage 進去 |
| 重寫日檔失敗時界線沒退，那天後來才寫進來的列會被刪 | 失敗時界線退到那一天；刪除改成每一天只刪 id 不大於日檔最大 id 的列 |
| 界線之前才補寫進來的列被靜默刪掉 | 不在日檔裡的不刪，留到超過總保留期 |
| 一筆時間在未來的列會帶走資料時鐘，半年的日檔被當成過期 | 即時模擬在跑時用它的模擬時鐘 |
| `_last_write_slot` 在還原失敗時被清掉、往回只看 20 個 session、時鐘向下取整 | 接時鐘改在還原之後、往回看 200 個、向上取整 |
| 維護端點在批次期間可以呼叫 | 原本就掛了 `reject_during_batch`，沒有改 |
| `sync` 每次從含情境列的最早時間開始 | 改成只看 Live 的最早時間 |
| DB 被重建、歸檔卻留著，id 會撞 | `sync` 檢查並拒絕 |
| 歸檔那一段出錯時其他表的清理被跳過 | 包起來，其他表照做 |

**變異檢查** 25 項（拿掉一個防護、確認對應的測試轉紅）全部被抓到，清單在 scratchpad 的 `mut4_list.py`（沒有進 repo）；其中一項（超過總保留期的殘留列要清）原本沒有測試守著，補了。

**測試**：`test_live_archive.py` 31 項（新）、`test_external_api.py` 多 2 項、`test_source_selection.py` 多 7 項。backend 全部的結果見 §2.8。

### 2.7 重大決策

- DEC-20261126-03。

### 2.8 回歸測試與真伺服器

- backend 全部：2409 passed / 1 skipped / 1 xfailed（本機；前一次 2369，多的 40 項是這次新增的：歸檔 31、對外 API 2、來源選擇 7）。前端沒有動。
- 真伺服器（`WMOM_AUTH_ENFORCE=true`、`WMOM_RAW_RETENTION_DAYS=365`、`WMOM_RAW_HOT_DAYS=2`，風場 DB 先放進一整天 14 台的讀值，日期 2026-03-01）：
  - `/status` 回 `api_version` 1.1、`raw_retention_days` 365。
  - `POST /api/config/storage/maintenance`：歸檔 2026-03-01 與 03-02、SQLite 刪掉 121,044 列，10.7 秒（當時另有整套測試在跑）。
  - 維護前後各打一次：`/readings`（時間範圍、從頭 2000 筆）與 `/stats-10min`（6 個窗）的回應逐位元相同。
  - 用金鑰從頭翻到最新：8,652 筆、9 頁、1.1 秒，3 月的 8,646 筆來自日檔、其餘來自 SQLite，時間遞增、沒有重複。
  - `/api/config/storage/stats` 看得到日檔數與兩個保留期。
- 這次順手發現：伺服器第一次在一個新的資料目錄啟動時，會把 repo 裡預設位置的 `wind_farm_data.db` 搬成 `legacy` 風場的 DB（既有行為，`migrate_legacy_db`），蓋掉我事先放在那裡的檔案。測試時要等風場目錄建好再放資料。

## 3. 產出清單

### 新增檔案

- `modules/monitoring/server/live_archive.py`、`modules/monitoring/server/live_history.py`、`modules/monitoring/server/plc_types.py`
- `modules/monitoring/tests/test_live_archive.py`
- `work-logs/2026-11/2026-11-26-tiered-storage.md`

### 修改檔案

- `modules/monitoring/server/storage.py`、`data_broker.py`、`app.py`、`routers/external.py`、`routers/config.py`
- `modules/monitoring/simulator/engine.py`
- `modules/monitoring/tests/test_external_api.py`、`test_source_selection.py`
- `.gitignore`（`live_archive/`）、`README.md`
- `docs/integration/external_api_v1.md`（v1.1）、`docs/product/decision_log.md`、`docs/product/ROADMAP.md`、`docs/architecture/research-framework.md`
- `CLAUDE.md`、`ISSUES.md`、`STATUS.yaml`、`TODO.md`

### 動了狀態的 issue

- WMOM-20261125-03-c：新開 → done
- WMOM-20261125-03：in_progress → done
- WMOM-20261126-01（72 小時連續運轉測試）、WMOM-20261126-02（歷史回填）：新開，open

### 寫進 decision_log 的決策

- DEC-20261126-03

## 4. 下次怎麼接手

- 第 3 項 WMOM-20261125-04（運維閉環）。
- 要讓風場像真實風場一樣持續運轉：`WMOM_LIVE_RESUME=true`、`WMOM_AUTOSTART_SOURCE=simulation`；保留期預設就是半年，不必另外設。
- 要讀 Live 的歷史（不論多舊）：用 `broker.live_history.readings(...)`，不要直接查 `storage.live_readings`——後者只有最近幾天。
- 改 `turbine_data` 的查詢時先看有沒有帶機組：不帶機組的時間範圍查詢會掃整張表（一天約 0.5 GB）。
