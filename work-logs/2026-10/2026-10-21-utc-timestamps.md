# 2026-10-21 — Phase 1b-c：monitoring 時間戳改 UTC tz-aware

> Session 類型：實作
> Session 長度：中
> 主導：Claude（劉老師指示「繼續做 -03-c UTC 時間戳」）
> 結果：WMOM-20261021-03-c done → 母 issue WMOM-20261021-03 done（Phase 1b 三段完成）

---

## 1. Session 目標

WMOM-20261021-03-c：monitoring 全面使用 naive local `datetime.now()`；改為 UTC tz-aware（storage 寫入 / 讀取、事件、情境 sim time），並處理既有 SQLite 資料的相容讀取。

## 2. 實際完成

### 2.1 先盤點

- 後端：storage（19 處）、broker（14 處）、engine、routers、farm registry、OPC adapter、故障引擎、電網模型共約 60 處時間戳產生 / 比較 / 解析。SQLite 以**字串字典序**比較時間（`timestamp >= ?`），聚合用 `strftime('%s', ...)`。
- 前端（Explore agent 盤點）：所有後端時間戳都經過 `new Date()` 解析，沒有字串切片或字串比較；送給後端的查詢範圍都是 `toISOString()`（UTC `Z`）——**也就是前端早就假設後端存 UTC**，現況 DB 存本地時間，伺服器在 UTC+8 時歷史查詢窗整整偏 8 小時（既有 bug）。唯一直接印後端字串的是 `HistoryPage` 資料預覽表的時間欄。
- 風況模型 `wind_model.py` 從時間戳取 hour / month 驅動日夜與季節循環：直接改 UTC 會讓循環位移（UTC+8 時偏 8 小時）。

### 2.2 慣例（`modules/monitoring/simulator/time_utils.py`）

- 內部一律 `utc_now()`（tz-aware UTC）。
- 落庫 / API 字串固定 `YYYY-MM-DDTHH:MM:SS.ffffff+00:00`（`iso_utc`，長度固定 32）：字典序＝時間序。不用 `Z`——`Z`（0x5A）大於 `.` 與數字，同一秒內「無小數」與「有小數」的順序會顛倒。SQLite `strftime('%s')` 認得 `+00:00`（實測）。
- 外部字串（`Z`、任意時區後綴）在 storage 邊界正規化；**naive＝伺服器本地時間**（本次之前所有資料與舊呼叫端的語意，也是 Python `astimezone()` 對 naive 的預設）。
- 放在 `simulator/`（最底層）：simulator 與 server 都能匯入；storage 用「相對匯入 → sys.path 匯入」兩段 try，與既有 `sqlite_utils` 同模式。

### 2.3 改動

- **寫入 UTC**：engine Live / bulk 模擬時間與 reading 時間戳、故障 `started_at`、電網 profile 起點、broker（reading 解析、事件 ref、`FarmStatus`、PLC 事件時間戳）、routers（scenarios / turbines farm-trend / config / faults / farms dataset）、farm registry、OPC adapter、`examples/data_quality_analysis.py`。
- **storage**：session / 事件 / reading / snapshot / 工單寫入、downsampling 與 cleanup 的截止時間、四個查詢函式的 start/end 正規化。
- **既有 DB 一次性轉換**：`PRAGMA user_version` 0 → 1。10 個時間戳欄位以 SQL `strftime('%Y-%m-%dT%H:%M:%f', col, 'utc') || '000+00:00'` 轉換（只轉沒有時區後綴、SQLite 可解析的值），情境 `config.sim_start/sim_end` 用 Python 轉。可重入：中途中斷時版本號不更新、下次接著轉剩下的列。新建 DB 直接標新版本。實測 `time.tzset()` 後 SQLite 的 'utc' 修飾詞跟著程序時區走（Asia/Taipei 13:00 → 05:00Z）。
- **風況模型**：6 個讀 hour / month 或做時間差的 getter 先 `to_local_naive`，循環相位與改動前相同。
- **情境 tripped 重算**：`_parse_scenario_timestamp` 一律回 aware、`as_of` 正規化（否則 naive 與 aware 混比 `TypeError`——既有 8 個純函式測試以 naive 呼叫，首跑即抓到）。
- **前端**：`HistoryPage` 預覽表時間欄改 `toLocaleString()`。

### 2.4 驗證

- `test_utc_timestamps.py`（7）：時區相關的測試把程序時區設成 Asia/Taipei（CI 是 UTC，naive 與 UTC 相同、測不出差異）；mutation：拿掉 DB 轉換 / 查詢正規化 / 風況本地時間轉換，各對應 1 項失敗
- `HistoryPage.test.tsx` +1：mutation（還原成直接印字串）→ 失敗
- 既有測試只改了 `test_plc_event_recording.py` 的時間戳斷言（改用 aware T0 與固定格式）
- backend 全套：1521 → **1528 passed** / 7 skipped / 1 xfailed；frontend：tsc 0、vitest 1501 → 1502
- `examples/data_quality_analysis.py`：20 通過 / 0 待改善（不變）

### 2.5 卡住或延後的事

- 日夜循環依「伺服器本地時區」而非「風場時區」：同一情境在 UTC 的 CI 與 UTC+8 的開發機上相位差 8 小時。要固定需 farm 層級時區設定（目前沒有，未開 issue；做 -05 資料包若要可重現再評估）。
- `farms.py` 匯出 zip 的檔名仍用本地時間（給人看的檔名，不參與比較）。
- 資料包（-05）對外格式可選 `Z` 後綴（合約 v0 範例用 `Z`），匯出時統一即可。

## 3. 產出清單

### 新增檔案

- `modules/monitoring/simulator/time_utils.py`
- `modules/monitoring/tests/test_utc_timestamps.py`（7）
- 本 work-log

### 修改檔案

- `modules/monitoring/simulator/engine.py`、`grid_model.py`、`physics/fault_engine.py`、`modules/monitoring/wind_model.py`
- `modules/monitoring/server/storage.py`、`data_broker.py`、`farm_registry.py`、`opc_adapter.py`
- `modules/monitoring/server/routers/scenarios.py`、`turbines.py`、`config.py`、`faults.py`、`farms.py`
- `modules/monitoring/examples/data_quality_analysis.py`
- `modules/monitoring/tests/test_plc_event_recording.py`
- `frontend/components/HistoryPage.tsx`、`frontend/components/__tests__/HistoryPage.test.tsx`
- 文件：`docs/product/EPIC-DS_realistic_data_source.md`（§6 表、新增 §6.4）、`docs/API_GUIDE.md`、`ISSUES.md`、`STATUS.yaml`、`CLAUDE.md`（時間戳守則）、`TODO.md`

### 動了狀態的 issue

- WMOM-20261021-03-c：open → done
- WMOM-20261021-03（母）：in_progress → done

## 4. 下次怎麼接手

1. **WMOM-20261021-10**：切出風速改用平均風速判定（小題）。
2. **WMOM-20261021-04**：標準答案 + 情境事件。時間戳都已是 UTC，ground truth 的 `onset_ts` / `first_alarm_ts` / `trip_ts` 直接用 `iso_utc`；PLC 事件的 `sim_time` 要換算成絕對時間（broker 的 `_plc_event_timestamp` 是範例）。
