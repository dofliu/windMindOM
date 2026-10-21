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
- `requirements.txt`
- 文件：`docs/product/EPIC-DS_realistic_data_source.md`、`docs/API_GUIDE.md`、`ISSUES.md`、`STATUS.yaml`、`CLAUDE.md`、`TODO.md`

### 動了狀態的 issue

- WMOM-20261021-05：open → done

## 4. 下次怎麼接手

- **-09 學生 starter kit**：
  - 合約 v1 定稿：以本次實際輸出的格式為準（設計文件 §5.1）。
  - 範例資料包：用 CLI 匯出，盲測版給學生、評分端版給評分。
  - 讀取範例：pandas / pyarrow 讀 Parquet、逐行讀 events.jsonl。
- **-06 WS 回放**：讀資料包或直接讀 session，事件格式沿用 `scenario_pack.pack_event`。
