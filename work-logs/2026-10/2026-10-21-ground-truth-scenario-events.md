# 2026-10-21 — WMOM-20261021-04：標準答案 + 情境事件（EPIC-DS Phase 2）

> Session 類型：實作
> Session 長度：中-長
> 主導：Claude（劉老師指示「繼續做 -04 標準答案 + 情境事件」）
> 結果：WMOM-20261021-04 done

---

## 1. Session 目標

批次情境原本只有讀值與「注入 / 跳機」標記：沒有警報 / 跳機 / 狀態事件（`generate_bulk` 不跑事件偵測、還把 PLC 事件丟掉）、`history_events` 沒有 `session_id`（情境事件靠時間窗比對，會混入重疊情境）、沒有標準答案。issue 要求：(1) 故障情境 metadata；(2) bulk 路徑產生事件；(3) `history_events.session_id`；(4) ground truth 隨情境落庫且與可觀測事件分離；(5) 警報事件 title / payload 帶事件碼與等級。

## 2. 實際完成

### 2.1 盤點

- Live 路徑的事件來自 broker `_detect_sim_events`（狀態轉換、PLC 事件、故障生命週期、疲勞警報、快照）：用 wall-clock、會觸發快照、故障生命週期 / `Automatic fault trip` 事件帶故障 ID——不適合直接拿來給批次用，也不是盲測資料。
- (5) 已在 -03-b 達成：PLC 事件 title `Trip: T_240 …`、payload 帶 `code` / `level`；本次不改格式。
- 前端情境頁顯示 `eventsByTimeWindow` 提醒；情境掛載的 FAULT 重算靠 `source="scenario"` 的注入 / 跳機標記。

### 2.2 故障情境 metadata

`FaultScenario` 加 `component`、`root_cause_zh/en`、`category`、`origin`、`difficulty`、`key_signals`、`expected_actions_zh/en`；手冊條目由警報目錄組出（`ground_truth.manual_refs`，See [ABB] 標 `see_abb`）。

key signals 先探測再選：每個情境在 14 m/s、25 °C 滿嚴重度 vs 健康，列出偏離最大的 tag。值得記的發現：

- **風向標漂移的訊號在風向標 2**：偏航依漂移的風向標 1 追風，風向標 1 讀值看似正常；真實偏航誤差出現在風向標 2（−22.6° vs 健康 −4.6°），塔架側向彎矩 ×4。
- 超速 / 電網故障滿嚴重度在取樣窗前就跳機：key signals 驗證改用還在發電的嚴重度（超速 0.3：轉速 25.1 vs 22.5 rpm；電網 0.5）。
- 液壓洩漏的洩漏偵測（`WYAW_YwBrkSealsLeak`）只在高嚴重度出現；塔架側向 DEL ×13 是最明顯的訊號。

### 2.3 批次事件與 session 隔離

- `simulator/bulk_events.py`：`BulkEvent`（PLC 事件或狀態轉換，模擬時間戳）。
- `generate_bulk(on_events=...)`：每個物理子步收集（狀態可能只維持一個子步），每個輸出步回呼一次；批次前先清掉 Live 留在佇列的事件。
- `storage`：`history_events.session_id`（`_migrate_columns` 補欄 + 索引）、`record_events` 批次寫入、`query_events(session_id, source)`、`count_scenario_fault_events(session_id)`、刪情境一併刪事件與標準答案、`is_observable_event`。
- `DataBroker`：`_plc_event_fields` / `_state_transition_fields` 抽出給 Live 與批次共用；`record_bulk_events`；`record_event` 的 `session_id` 預設目前 Live session。
- `routers/config.py`：情境 config 加 `events_session_isolated: true`；注入 / 跳機標記與批次事件都記情境 session；`routers/faults.py` 測試計畫也記事件與跳機標記（-03-b 留下的缺口）。
- `routers/scenarios.py`：調閱 / 摘要依 session 查、舊情境退回時間窗；掛載 FAULT 重算只撈 `source="scenario"`（PLC 事件可能上千筆，不篩會被 LIMIT 擠掉注入標記）。

### 2.4 標準答案

`simulator/ground_truth.py::GroundTruthRecorder`：注入 → case（`onset_ts`）；事件 → 預期碼的 `first_alarm_ts` / `observed_alarm_codes`、其他碼 `other_observed_codes`；跳機回呼 → `trip_ts` / `trip_code`；同機組同情境再注入時舊 case `superseded`。存 `scenario_ground_truth` 表，`GET /api/scenarios/{id}/ground-truth`（主管）。

stress_test 前 6 h（14 機）實例：hydraulic_leak `260 → 261 → 228`（13:02 首警、14:03 跳機）；yaw_sensor_drift / pitch_imbalance / blade_icing 首次警報＝跳機；bearing_wear 首警 262 未跳機；stator / nacelle 6 h 內未達警報。共 62 筆事件，生成時間與不收事件相同（77.6 s vs 81.6 s）。

### 2.5 驗證

- `test_fault_ground_truth.py`（42）：metadata 完整 / 值域、A 在 T 前、手冊條目與目錄一致、ABB 標記、紀錄器（onset 前事件不算、解除不算首警、其他碼、共用碼雙邊歸屬、再注入取代、未知情境）。
- `test_bulk_events.py`（18）：收事件不改讀值（固定起點兩次生成逐位元相同）、跳機與停機狀態順序、狀態轉換串接與末筆讀值一致、子步解析度（2→4→5 間隔 5 s）、批次前 Live 事件不算、舊 DB 補欄、批次寫入與篩選、刪情境、標準答案存取、可觀測判定、broker 預設 session 與批次格式。
- `test_scenario_endpoints.py` +8：標準答案內容與 PLC 跳機同刻、事件隔離與盲測（可觀測事件不含任何故障 ID、情境 config 不含根因）、調閱 / 摘要 session 隔離與舊情境 fallback、鄰居情境不混入、1200 筆 PLC 事件下仍判得出 FAULT、標準答案 404、刪除、不帶 name 的批次、測試計畫事件。
- `test_monitoring_routers_auth.py` +3：標準答案端點 401 / employee 403 / supervisor 過 gate。
- `tests/physics/test_fault_threshold_reach.py` +11：每個情境的 key signals 偏離健康 > 3σ 且 > 2 %。
- mutation 16 項（批次前清佇列、每子步收集、PLC 時刻回推、onset 篩選、首警不覆寫、取代、broker 預設 session、刪事件、session 計數、可觀測 payload 鍵、掛載來源篩選、調閱 session、端點權限、隔離旗標、注入 session、測試計畫跳機）皆被抓到；「調閱 session」一開始存活（鄰居情境在 WT001 沒有事件），補鄰居故障後抓到。
- 健康機組輸出逐位元不變；`data_quality_analysis.py` 20 / 0。

### 2.6 Code review（code-reviewer subagent）

結論 Needs revision：2 must-fix、8 should-fix、6 組 nice-to-have。reviewer 用 scratchpad 複本實跑、做 mutation，repo 未被改動。

**must-fix**

- **M1 測試依 wall-clock**：端點測試的批次從 `utc_now()` 起算，風況隨季節 / 時刻變化，低風時超速不跳機。reviewer 在 10:32 UTC 實測有 1 支失敗，固定時鐘也重現了 4 支。修法：fixture 固定批次起點（`engine.utc_now`）；超速測試用 `set_override(14 m/s)`。
- **M2 殘留故障**：命名情境不帶排程時不清故障，Live 殘留的 bearing_wear 會在資料裡跳機，答案卷卻列為健康。修法：命名情境一律先清故障。`build()` 另加安全網：結束時仍在、卻沒有注入紀錄的故障，列成 `pre_existing` case。

**should-fix**

- **S1 Live 查詢**：Live 端的查詢（`/api/turbines/{id}/history`、事件匯出、維護比較）原本會混進情境事件，現在排除情境 session。農場備份（`farms.py` 的 events.json）是全量備份，維持全量。
- **S2 沒有答案的事件**：答案卷加 `unattributed_events`。reviewer 實測健康 14 機 12 h 出現 T2 336，我重現（WT002 16:04:45，1.01° / 1.0°），開 **WMOM-20261021-12**。
- **S3 `faultEvents` 語意**：session 模式改只數 PLC 的警報成立 / 跳機。前端 `ScenarioTrendView` 原本對每筆 `fault` 事件畫參考線（I201、解除、停機狀態都畫），改用 `utils/scenarioEvents.ts::isScenarioFaultMarker`（+ vitest 10 項）。
- **S4 盲測**：
  - `is_observable_event` 改白名單。原本的黑名單會漏掉 Live 的 `Fault trip cleared in simulator`。
  - 答案卷端點改 `require_roles`：`require_role` 在 enforce 預設關閉時放行，等於答案卷公開。
  - 情境調閱加 `observable_only`。
- **S5 答案文字**：
  - 處置標「（手冊）」，並補齊手冊條目：超速補「峰值轉速重設 / 參數調整 / 320 檢查輪轂」，定子補「外氣溫 + 高產能 / 聯絡 Harakosan」。
  - 模擬與真實的差異移到 `simulation_notes`：320 在模擬中不可達、結冰的氣溫不耦合、電網下陷只作用於單機。
  - 電網處置改為「比對本機 / 鄰機 / 變電站」。
  - 液壓碼順序改為 260 → 261 → 228。
  - 根因不放模擬器說明，有測試擋。
- **S6 測試缺口**（reviewer 的存活 mutant）：
  - Live 快照觸發條件 8 組參數化。
  - PLC 時刻回推。
  - 跳機只歸對應故障且只一次。
  - 只有成立 / 跳機算首警。
  - onset 當刻含。
  - `record_events` 跨連線可見。
  - session 索引的查詢計畫。
  - 同時刻依 id 排序。
- **S7 retention**：情境 raw 讀值不受 3 天 retention 清除。
- **S8 文件**：補 DEC-20261021-02，修過時 docstring，STATUS 佔位字串在收尾時替換。

**nice-to-have（記為 §6.7 限制 11，留給 -05）**：可重現性（seed / spec / 模型狀態未重置）、`generated_at`、事件 kind 對合約的對應、`Z` 後綴、停機原因詞彙；歸屬受物理耦合影響（限制 5）。

**驗證**：review 修正的 18 個 mutant 中 17 個被抓到；存活的 1 個是等價的冗餘 level 過濾（`alarm_raised` / `trip` 一定是 A / T 級），已移除。

**全套測試時另發現**：既有的 `test_generate_bulk_fault_schedule.py::test_scheduled_fault_progresses_to_trip` 也依 wall-clock 風況：3 分鐘超速只在風夠大時跳機，10/21 的 12-18 UTC 都不會跳（逐小時實測）。同樣改固定 14 m/s，24 個時刻都通過。

**結果**：backend 1574 → **1687 passed** / 7 skipped / 1 xfailed；frontend vitest 1502 → 1512、tsc 0；健康機組輸出逐位元不變；`data_quality_analysis.py` 20 / 0。

**途中**：快照測試的 broker 沒有 `start()`，storage 指向預設的 `wind_farm_data.db`（gitignored），失敗的測試寫進 10 筆 session 4242 的事件。已刪除；測試改用暫存 DB。

## 3. 產出清單

### 新增檔案

- `modules/monitoring/simulator/bulk_events.py`、`simulator/ground_truth.py`
- `modules/monitoring/tests/test_fault_ground_truth.py`、`tests/test_bulk_events.py`
- `frontend/utils/scenarioEvents.ts`、`frontend/utils/__tests__/scenarioEvents.test.ts`（review）
- 本 work-log

### 修改檔案

- `modules/monitoring/simulator/physics/fault_engine.py`、`simulator/engine.py`
- `modules/monitoring/server/storage.py`、`data_broker.py`、`routers/config.py`、`routers/faults.py`、`routers/scenarios.py`、`routers/maintenance.py`（review）
- `frontend/components/ScenarioTrendView.tsx`（review）
- `modules/monitoring/tests/test_scenario_endpoints.py`、`test_monitoring_routers_auth.py`、`tests/physics/test_fault_threshold_reach.py`
- 文件：`docs/product/EPIC-DS_realistic_data_source.md`（§3 註記、§6 表、新增 §6.7）、`docs/product/decision_log.md`（DEC-20261021-02）、`docs/API_GUIDE.md`、`ISSUES.md`、`STATUS.yaml`、`CLAUDE.md`、`TODO.md`

### 動了狀態的 issue

- WMOM-20261021-04：open → done
- WMOM-20261021-12：新增 open（健康機組長時間偶發 T2 336，review 實測）

## 4. 下次怎麼接手

**WMOM-20261021-05**：情境資料包匯出。

- 事件：`storage.query_events(session_id=...)` 再以 `storage.is_observable_event` 過濾。
- 標準答案：`storage.get_ground_truth(...)`。
- manifest **不得**帶情境 config 的 `fault_schedule`（含故障 ID）。
- `site_timezone`：讀情境 config。
- `farms.py::generate_dataset` 要修或移除。
