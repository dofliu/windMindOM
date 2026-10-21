# 2026-10-21 — WMOM-20261021-05：情境資料包匯出（EPIC-DS Phase 3a ① 檔案）

> Session 類型：實作
> Session 長度：中
> 主導：Claude（劉老師選定「-05 資料包匯出」）
> 結果：WMOM-20261021-05 done

---

## 1. Session 目標

把凍結情境（-04 起有可觀測事件與標準答案）匯出成設計文件 §5.1 的資料包，給外部 RAG 維修助手（學生專題）離線使用。

issue 的要求：
- manifest、tag 字典、警報目錄快照、raw Parquet、10 分鐘 avg / min / max / std、events.jsonl、ground_truth.json。
- 現有 10 分鐘聚合不適用，改從 raw 直接算。
- 順帶處理壞掉的 `routers/farms.py::generate_dataset`。

-04 另留下幾件 -05 要處理的事：
- manifest 不帶 `fault_schedule`。
- 事件以 `is_observable_event` 過濾。
- 事件 kind 對應到合約的 event_type。
- 時間戳用 `Z` 後綴。
- 停機原因詞彙正規化。

## 2. 實際完成

### 2.1 盤點

- **SCADA tag**：註冊表 116 個 tag 全部出現在物理輸出，Bachmann 名稱（`opc_tag` 去掉分組前綴）沒有重複，可直接當欄名。
- **真實 / 自創判定**：註冊表沒有這個欄位。xlsx 全部 sheet 共有 1811 個 `Z72PLC__*` 名稱，比對結果是 45 個真實、71 個自創，與設計文件 §3 的「40 + -03-a 補的 5」一致。
- **`farms.py::generate_dataset`**：自寫一套步進迴圈，檢查從未啟動的 `sim._running`，永遠產出 0 筆，也不記事件與標準答案；前端沒有呼叫端。
- **pyarrow**：環境沒裝，`requirements.txt` 也沒有。

### 2.2 實作

- `tools/build_z72_plc_tags.py` → `shared/data/z72_plc_tags.json`（含每個 tag 出現的 sheet），`shared/plc_tags.py::is_real_plc_tag`。
- `server/scenario_pack.py::export_scenario_pack(storage, scenario_id, out_dir, include_ground_truth)`：
  - **raw Parquet**：`timestamp[us, UTC]`、`turbine_id`，加上 116 個 tag 欄。欄名＝Bachmann tag 名，型別依 PLC 資料型別：REAL32 → float32、SINT16 → int16、UINT16、BOOL。分批讀 DB、以 `ParquetWriter` 串流寫出。
  - **10 分鐘統計**：串流時逐窗計算，窗對齊 UTC 的 10 分鐘，記憶體與情境長度無關。類比 tag 給 avg / min / max / std（ddof 1），離散 tag 只給 min / max，另有 `n_samples` 欄。
  - **events.jsonl**：`is_observable_event` 過濾後轉成合約格式，時間戳 `Z`，不帶模擬器內部的製程值 / 設定值。停機原因正規化成 `plc_trip` / `high_wind` / `low_wind` / `grid` / `overspeed` / `operator`，只在進入停機狀態時給。
  - **manifest**：不帶情境名稱（出題者自訂，可能寫明故障）、故障排程、注入數；`pack_id` 為 `z72-scenario-NNNNN`。
  - **ground_truth.json**：只在評分端版附上，時間戳轉 `Z`、加 `pack_id`。重匯出成盲測版時刪掉舊的答案檔。
  - **拒絕匯出**：-04 之前生成（事件沒有 session 隔離）、生成未成功、沒有讀值、非情境 session。
- **端點**：`GET /api/scenarios/{id}/pack`（盲測版，任何登入者）、`/pack/full`（含答案，`require_roles(SUPERVISOR)`）。匯出在 thread 裡做，回應送出後刪掉暫存目錄。
- **CLI**：`tools/export_scenario_pack.py`，支援 `--list` / `--ground-truth` / `--zip`。
- **移除** `POST /api/farms/{id}/datasets/generate` 與它的 -11 測試；資料集改用命名情境 + 資料包。
- `requirements.txt` 加 `pyarrow>=15.0`。

### 2.3 驗證

- `test_scenario_pack.py`（29 項）：固定起點、14 m/s、2 h 情境（WT001 主軸承磨耗、WT002 超速）。
  - **manifest**：sha256、時間窗、計數正確。
  - **盲測**：manifest、事件、tag 字典都不含故障 ID 與情境名稱，Parquet 沒有 metadata。
  - **raw**：欄名、型別與落庫值一致，排序正確。
  - **10 分鐘統計**：與 raw 重算一致，含第一窗 59 筆、最後一窗 1 筆的 std 為 null。
  - **事件**：合約格式，PLC 碼對得上目錄，停機原因正確。
  - **標準答案**：評分端版附上；盲測版與評分端版的資料檔 hash 相同。
  - **其他**：決定性、拒絕匯出的情境、端點、CLI。
- `tests/test_plc_tags.py`（3 項）：已知真實 / 自創、45 / 71 分布、JSON 與 xlsx 一致。
- `test_monitoring_routers_auth.py` +2：`/pack/full` 未登入 401、employee 403；`/pack` 依讀取 gate。
- mutation 16 項全部被抓到。「可觀測過濾」一開始存活：情境標記在 `pack_event` 又會被丟掉，所以拿掉過濾也測不出來。補一個「非可觀測來源、卻長得像狀態轉換」的事件後就抓到了。
- 效能：14 機 × 6 h（3 萬列）匯出 3.7 s，生成同一情境要 98 s。

### 2.4 Code review（code-reviewer subagent：Needs revision → 全修）

Must-fix：
- **M1 events.jsonl 欄位不齊**：PLC 事件與狀態轉換的欄位不同，polars 依前幾行推 schema 會掉 `alarm_code`。改成每行都有 `EVENT_KEYS` 全部欄位，不適用者 null。
- **M2 無法串流**：`ORDER BY timestamp, turbine_id` 讓 SQLite 先把整個 session 排序（43 萬筆時第一批 7.7 s，記憶體也跟著長）。改成依 id 讀；先用 `LAG` 視窗查詢確認 id 順序就是時間順序（批次生成都是），不是才退回時間排序。
- **M3 殘缺窗**：頭尾窗與資料缺口和整窗分不出來。加 `window_end`、`is_partial`（`n_samples < floor(600 / 取樣週期)`），manifest 加 `stats_convention`（窗邊界、ddof、離散 / 圓統計、缺值）。

Should-fix：
- **S1 暫存目錄**：固定放 `{tmp}/wmom-packs/`，每次下載清掉超過 1 小時的殘骸；匯出失敗當場清。
- **S2 資源**：同時 2 個匯出（429）、raw 200 萬筆上限（413 → CLI）、Parquet 進 zip 不再壓縮、row group 5 萬列。
- **S3 盲測交付**：任何登入者都看得到情境清單（名稱）與 `fault_schedule`，擋端點沒用 → 盲測版以檔案交付、受測端不開帳號（DEC-20261021-03）；`wind_profile` 只輸出已知 profile 名。
- **S4 內部量**：16 個模擬器內部量（尾流 / 大氣模型狀態、疲勞損傷 / 壽命 / 疲勞警報、不平衡力、齒面磨耗指數）不匯出（DEC-20261021-03）。原本想連彎矩 / DEL 一起排除，但它們是 yaw_sensor_drift、hydraulic_leak 的 key signal，保留；測試守住「排除的不能是真實 tag、不能是 key signal」。`WSpeedNac` / `WDirAbs` 的模擬語意寫進 tag 字典 `note`。
- **S5 LF**：文字檔固定 `\n`，Windows 匯出的 sha256 與 Linux 相同。
- **S6 圓統計**：`WDirAbs` 的 10 分鐘 avg 用圓平均、std 用 Yamartino（RulHours 的 -1 哨兵值隨 S4 排除）。
- **S7 原子寫入**：寫到同層暫存目錄，全部成功才搬、manifest 最後搬。
- **S8 CLI**：開 DB 用 `migrate_timestamps=False`。
- **S9 文件**：設計文件 §5.1 改成實際格式、§6.8、§6.6 / §6.7 限制更新；API_GUIDE。
- **S10**：統計以 float32 保存、docstring 改寫記憶體說明、取樣週期由資料推得、`events_dropped`、`exporter_version`。

另外：
- 標準答案的 `sim_start` 比 manifest 早一步（含 offset 0 的注入時刻）。這是刻意的：manifest 若跟著改，就透露了「第一筆讀值前發生了事」。
- `requirements-dev.txt` 加 `openpyxl`，CI 也跑 xlsx 一致性測試。

補測（審查列出的缺口）：
- 批次 / row group 邊界不改變資料
- 非對齊起點、缺值（NULL / 缺 key / 非數值 / inf）、寫入順序不是時間順序
- 取樣週期以資料為準
- zip 失敗清理、舊暫存目錄清理
- 413 / 429
- 原子寫入失敗不動舊包
- 標準答案各處時間戳轉換
- 同時刻跳機在停機之前
- 每行欄位相同
- 圓統計（含 Yamartino 修正量）
- HTTP 主管 200

mutation 24 項全部被抓到（含自我審查後補的 3 項：筆數上限在情境檢查之後、名額在 thread 裡歸還）。`events_dropped` 計數一度存活（沒有白名單內、卻沒有合約格式的事件），補一個新 PLC 事件種類的測試後抓到。阻塞式 acquire 的 mutant 會讓 429 測試卡住，也算抓到。

效能（審查者的 43.6 萬筆 DB）：id 順序檢查 1.3 s，之後第一批立即可讀（原 7.7 s）；整包 32 s、峰值記憶體 220 MB。

## 3. 產出清單

### 新增檔案

- `modules/monitoring/server/scenario_pack.py`
- `shared/plc_tags.py`、`shared/data/z72_plc_tags.json`
- `tools/build_z72_plc_tags.py`、`tools/export_scenario_pack.py`
- `modules/monitoring/tests/test_scenario_pack.py`、`tests/test_plc_tags.py`
- 本 work-log

### 修改檔案

- `modules/monitoring/server/storage.py`（`iter_session_readings`、`session_events`）、`routers/scenarios.py`（資料包端點）、`routers/farms.py`（移除資料集端點）
- `modules/monitoring/tests/test_farm_timezone.py`（移除資料集測試）、`test_monitoring_routers_auth.py`
- `requirements.txt`、`requirements-dev.txt`
- 文件：`docs/product/EPIC-DS_realistic_data_source.md`、`docs/API_GUIDE.md`、`docs/product/decision_log.md`（DEC-20261021-03）、`ISSUES.md`、`STATUS.yaml`、`CLAUDE.md`、`TODO.md`

### 動了狀態的 issue

- WMOM-20261021-05：open → done

## 4. 下次怎麼接手

- **-09 學生 starter kit**：
  - 合約 v1 定稿：以本次實際輸出的格式為準（設計文件 §5.1）。
  - 範例資料包：用 CLI 匯出，盲測版給學生、評分端版給評分。
  - 讀取範例：pandas / pyarrow 讀 Parquet、逐行讀 events.jsonl。
- **-06 WS 回放**：讀資料包或直接讀 session，事件格式沿用 `scenario_pack.pack_event`。
