# windMindOM × RAG 維修助手：資料介面合約 v1.4

> **版本**：1.4（2026-10-23，WMOM-20261022-02：手冊保真度、自動重啟封鎖改送 A039）；1.3（2026-10-22，WMOM-20261021-08-a：感測器故障情境、新增軸承 / 定子溫度 2）；1.2（2026-10-22，WMOM-20261021-07：新增 §13 OPC UA）；1.1（2026-10-22，WMOM-20261021-06：新增 §12 WebSocket 回放）；1.0（2026-10-21，WMOM-20261021-09）。取代設計文件 [`EPIC-DS_realistic_data_source.md`](../product/EPIC-DS_realistic_data_source.md) §5 的 v0 草案。
> **評分欄位**經劉老師確認（2026-10-21）：診斷以「元件 + 類別」自動評分、手冊引用以事件碼評、時效報延遲與早期預警、各項指標分列不合成總分。
> **範例與工具**：[`examples/rag_starter_kit/`](../../examples/rag_starter_kit/)（範例資料包、讀取程式、基準助手、評分程式）。

---

## 1. 角色與流程

```
windMindOM（出題 / 評分端）                         學生專題（受測端：RAG 維修助手）
─────────────────────────                          ─────────────────────────────
生成情境（Z72 物理 + PLC 保護 + 故障排程）
  ├─ 盲測版資料包（§3–§5）  ───── 檔案交付 ─────▶  讀資料包、查 Z72 手冊、診斷
  └─ 標準答案（§7，留在評分端）                       │
                                                    ▼
評分程式（§8）  ◀───────── predictions.jsonl（§6）──┘
```

- **出題端**以 `GET /api/scenarios/{id}/pack` 或 CLI `tools/export_scenario_pack.py` 匯出盲測版資料包，**以檔案交給受測端**。受測端不開 windMindOM 帳號：系統內的情境清單看得到出題者取的情境名稱與故障排程（DEC-20261021-03）。
- **受測端**只拿得到資料包（加上 Z72 手冊與本合約）；輸出 `predictions.jsonl`。
- **評分端**以標準答案（`GET /api/scenarios/{id}/pack/full` 或 CLI `--ground-truth`）和 `score.py` 評分：`python score.py --answers <評分端版資料包目錄或答案目錄> --predictions predictions.jsonl`（目錄下的 `ground_truth.json` / `*.ground_truth.json` 都會讀）。
- **給受測端的只有** `examples/rag_starter_kit/` 目錄與盲測版資料包。不要給整個 repo：故障庫（`fault_engine.py`）、產生工具與標準答案都在裡面。
- **交付管道**：
  - **檔案**（v1.0）：資料包。
  - **WebSocket 回放**（v1.1，§12）：同一份資料依模擬時鐘即時播出，受測端在同一條連線送預測，`ts` 由伺服器以收到時的模擬時間蓋上，時間因果由伺服器保證。
  - **OPC UA**（v1.2，§13）：模仿 Bachmann Z72 PLC 的 tag，受測端像接真實 PLC 一樣讀「目前值」；預測照樣經 WebSocket 送（`?stream=false`）。

## 2. 版本規則

- `contract_version` 為 `"主版本.次版本"`。**加欄位、加列舉值** → 次版本 +1；**改名、刪欄位、改語意** → 主版本 +1。
- 讀取端必須**忽略不認得的欄位**；遇到不認得的列舉值（新的元件、事件種類、停機原因）要能略過，不可整包拒讀。
- 資料包、標準答案、詞彙檔（[`vocabulary.json`](../../examples/rag_starter_kit/vocabulary.json)）都帶 `contract_version`。讀取端只需檢查主版本（`pack_reader.verify_pack` 示範）。

## 3. 資料包

### 3.1 目錄

```
{pack_id}/
  manifest.json            資料包說明與各檔 sha256
  tag_dictionary.json      每個欄位（tag）的單位、說明、真實 / 自創
  alarm_catalog.json       Z72 警報目錄快照（315 碼：xlsx 314 碼＋手冊獨有的 A039，含手冊原因 / 處置 / 頁碼）
  timeseries_raw.parquet   原始時序（每台機組每個取樣週期一列）
  stats_10min.parquet      10 分鐘統計
  events.jsonl             可觀測事件（§4）
```

`pack_id` 為 3–63 字的小寫英數與 `-`，頭尾為英數（例 `z72-scenario-00012`、`z72-starter-01`），不含情境名稱。盲測版沒有 `ground_truth.json`。

### 3.2 manifest.json

| 欄位 | 型別 | 說明 |
|---|---|---|
| `contract_version` | str | `"1.4"`（讀取端只檢查主版本） |
| `pack_id` | str | 資料包 ID |
| `turbine_model` | str | `"Z72"` |
| `turbines` | list[str] | 機組 ID（`WT001`…） |
| `sim_start` / `sim_end` | str | 第一筆 / 最後一筆讀值的時間（UTC，§5） |
| `sample_period_s` | float | 原始取樣週期（由資料推得，通常 10） |
| `stats_window_s` | int | 600 |
| `stats_convention` | object | 10 分鐘統計的窗邊界、ddof、殘缺窗、圓統計等慣例（§3.6） |
| `duration_hours` | float | 情境長度 |
| `site_timezone` | str | 風場時區（IANA，例 `Asia/Taipei`；日夜循環依此） |
| `wind_profile` | str \| null | 風況 profile（`calm` / `moderate` / `rated` / `strong` / `storm` / `gusty` / `ramp_up` / `ramp_down` / `auto`），其他為 null |
| `rated_power_kw` | float | 額定功率 |
| `ground_truth_included` | bool | 盲測版為 false |
| `generator` | object | `name`、`exporter_version`、`simulator` |
| `reproducibility` | object | `seed`（目前為 null）、說明 |
| `counts` | object | `raw_rows`、`stats_rows`、`partial_windows`、`events`、`events_dropped` |
| `files` | object | 檔名 → `{sha256, bytes}`（不含 manifest 自己） |
| `exported_at` | str | 匯出時間（UTC） |

### 3.3 tag_dictionary.json

`{"turbine_model": "Z72", "tags": [...]}`，順序與 Parquet 欄位相同。每個 tag：

| 欄位 | 說明 |
|---|---|
| `tag` | 欄名＝Bachmann PLC tag 名（例 `Z72PLC__UI_Loc_WTUR_Analogue_TotPwrAt`） |
| `opc_path` | 含 OPC 分組前綴的路徑（例 `WTUR.Z72PLC__…`） |
| `id` | 模擬器內部 ID（例 `WTUR_TotPwrAt`；標準答案的 `key_signals` 用這個） |
| `subsystem` | `WTUR` / `WGEN` / `WROT` / `WNAC` / `WYAW` / `WMET` / `WCNV` / `WGDC` / `WCOL` / `WDRV` / `WVIB` / `WLOD` / `WSRV` / `MBUS` |
| `data_type` | `REAL32` / `SINT16` / `UINT16` / `BOOL` |
| `unit` | 單位（無因次為空字串） |
| `label_en` / `label_zh` | 說明 |
| `source` | `bachmann_real`（真實 Z72 PLC 有這個 tag，47 個）或 `synthetic`（依命名規則自創，55 個） |
| `note` | 模擬語意與真實不同之處；多數為 null |

**回答時的注意**：`synthetic` tag 在真實 Z72 上不存在（振動頻帶、負載彎矩、無功功率…），助手的建議不能假設現場讀得到。

### 3.4 alarm_catalog.json

`{"turbine_model", "source", "events": [...]}`，每碼：`code`、`event_id`（例 `A_262`）、`level`（`A` 警報 / `T1` 正常停機 / `T2` 緊急停機 / `I` 資訊）、`text`、`plc_tag`、`cause`、`rectification`、`max_per_hour`（每小時自動重啟上限）、`manual_page`（Z72 手冊頁碼）。手冊對變頻器 / 變壓器事件只寫 `See [ABB]`，答案在 ABB 變頻器手冊。

### 3.5 timeseries_raw.parquet

| 欄 | 型別 | 說明 |
|---|---|---|
| `timestamp` | `timestamp[us, tz=UTC]` | 取樣時間 |
| `turbine_id` | string | 機組 |
| `<Bachmann tag 名>` × 102 | 依 PLC 型別：REAL32 → float32、SINT16 → int16、UINT16 → uint16、BOOL → bool | 讀值；缺值為 null |

依 `(timestamp, turbine_id)` 排序。欄名含方括號者（`Z72PLC__UI_Mbus_Contact[2]`）在 SQL 引擎要加引號。運轉狀態欄 `Z72PLC__UI_Loc_WTUR_State_TurSt` 為 Bachmann TurSt：1 Shutdown、2 Standby、3 Wait Restart、4 Pre-Production、5 Synchronization、6 Production、7 Emergency Stop、8 Restart、9 Normal Stop。

### 3.6 stats_10min.parquet

| 欄 | 說明 |
|---|---|
| `window_start` / `window_end` | 窗的起訖（UTC，對齊整 10 分鐘，左閉右開 `[start, end)`） |
| `turbine_id` | 機組 |
| `n_samples` | 窗內讀值筆數 |
| `is_partial` | `n_samples < floor(600 / sample_period_s)`：頭尾窗與資料缺口 |
| `<tag>_avg` / `_min` / `_max` / `_std` | 類比（REAL32）tag；std 為樣本標準差（ddof 1），單筆窗為 null |
| `<tag>_min` / `_max` | 離散 tag（狀態、旗標）只有這兩欄，型別同 raw |

風向 `WDirAbs` 的 `_avg` 為圓平均（0–360°）、`_std` 為 Yamartino；`_min` / `_max` 為線性值。缺值不計入；整窗無值為 null。

**時間因果**：在時間 t 只能用 `window_end <= t` 的窗——還沒結束的窗含有 t 之後的讀值（`pack_reader.Pack.stats_until`）。

## 4. events.jsonl

一行一個 JSON 物件，依時間排序（同一時刻依發生順序：跳機在它造成的停機之前）。**每行都有下列全部欄位**，不適用者為 `null`：

| 欄位 | 說明 |
|---|---|
| `ts` | 時間（`YYYY-MM-DDTHH:MM:SS.ffffffZ`） |
| `turbine_id` | 機組 |
| `event_type` | `alarm_raised` 警報成立、`alarm_cleared` 警報解除、`trip` 跳機（T1 / T2）、`trip_cleared` 跳機解除、`reset` 操作員復位、`info` 資訊事件、`state_change` 運轉狀態轉換。超過每小時重啟上限以 A039 的 `alarm_raised` / `alarm_cleared` 表示（§10）；`restart_blocked`（超過重啟上限）是 v1.4 之前的值，現在不再送出，讀取端遇到舊資料包仍要能讀 |
| `alarm_code` / `alarm_level` / `alarm_text` / `event_id` / `plc_tag` | PLC 事件的事件碼（對應 `alarm_catalog.json`）、等級、文字、事件 ID、PLC tag |
| `from_state` / `to_state` | `state_change`：Bachmann TurSt 1–9 |
| `from_state_name` / `to_state_name` | 狀態名稱 |
| `stop_reason` | 進入停機（7 / 9）時：`plc_trip` / `high_wind` / `low_wind` / `grid` / `overspeed` / `operator`，其他為 null |

範例：

```json
{"ts": "2026-03-02T02:00:10.000000Z", "turbine_id": "WT002", "event_type": "alarm_raised", "alarm_code": 262, "alarm_level": "A", "alarm_text": "Main bearing 1 temperature high", "event_id": "A_262", "plc_tag": "Z72PLC__ActiveAlarm", "from_state": null, "to_state": null, "from_state_name": null, "to_state_name": null, "stop_reason": null}
{"ts": "2026-03-02T02:02:50.000000Z", "turbine_id": "WT002", "event_type": "state_change", "alarm_code": null, "alarm_level": null, "alarm_text": null, "event_id": null, "plc_tag": null, "from_state": 6, "to_state": 9, "from_state_name": "Production", "to_state_name": "Normal Stop", "stop_reason": "plc_trip"}
```

事件只包含現場 SCADA 看得到的資訊：沒有故障名稱、沒有模擬器內部的製程值或設定值。

## 5. 時間、單位與慣例

- 所有時間都是 **UTC**。JSON 為 `...Z` 結尾的 ISO 8601（微秒）；Parquet 為 `timestamp[us, tz=UTC]`。風場當地時間＝UTC 換到 `site_timezone`。
- 每筆讀值是該模擬步**結束時**的狀態；`sim_start` 是第一筆讀值，不是故障注入或情境開始的時刻。
- 單位見 tag 字典（kW、rpm、°C、bar、m/s、deg…）。
- 情境結束時故障仍在（不會自己好）；跳機後機組停在停機狀態，直到情境結束。

## 6. 受測端輸出：predictions.jsonl

助手每做出一次判斷就輸出一行（可以邊看資料邊修正，同一個問題輸出多次）：

| 欄位 | 必填 | 型別 | 說明 |
|---|---|---|---|
| `pack_id` | ✓ | str | 資料包 ID |
| `turbine_id` | ✓ | str | 機組 |
| `ts` | ✓ | str | 做出判斷的**模擬時間**（ISO 8601，UTC）。助手只能用 `ts` 以前（含）的資料 |
| `category` | ✓ | str | `real_fault`（元件劣化 / 故障）、`sensor_fault`（感測器讀值錯、機器本身正常）、`nuisance`（沒有實際故障的事件：環境性停機、誤跳機） |
| `component` | 故障時 ✓ | str | `vocabulary.json` 的元件 ID；`nuisance` 可為 null |
| `manual_refs` | | list[int] | 依相關程度排序的 Z72 事件碼（Appendix C 條目），最相關的在前；預設 `[]` |
| `root_cause` | | str | 根因說明（不自動評分；保留給人工 / LLM 評） |
| `actions` | | list[str] | 建議處置（不自動評分） |
| `confidence` | | float | 0–1（不評分） |

```json
{"pack_id": "z72-starter-01", "turbine_id": "WT002", "ts": "2026-03-02T01:40:00Z", "category": "real_fault", "component": "main_bearing", "manual_refs": [262, 240], "root_cause": "主軸承溫度相對同風場機組持續上升，疑潤滑劣化", "actions": ["檢查主軸承潤滑與油脂"], "confidence": 0.7}
```

**時間因果**：
- **檔案**：離線評分無法檢查助手有沒有偷看 `ts` 之後的資料，請自律（`pack_reader.Pack.raw_until` / `stats_until` / `events_until` 示範「只看當下以前」）。正式評測可要求繳交程式、由評分端重跑。
- **WebSocket 回放**（§12）：`ts` 由伺服器以收到預測時的模擬時間蓋上，受測端不用填（填了也不採用）。

**檔案**：UTF-8（可帶 BOM）。PowerShell 5 的 `>` 會存成 UTF-16，評分程式會拒絕。

**格式錯誤的行**不計分，評分報告列出行號與原因：不是 JSON 物件、缺必填欄位或不是字串、`ts` 不是 ISO 8601 時間、`category` 不在清單、故障診斷的 `component` 不在詞彙內（多半是拼錯）、`manual_refs` 不是整數清單（含 `true` / `"262"` 這類值，整行無效）。

## 7. 標準答案 ground_truth.json（評分端）

頂層：

| 欄位 | 說明 |
|---|---|
| `contract_version` / `pack_id` / `turbine_model` / `turbines` / `site_timezone` | 同資料包 |
| `kind` | `"scenario_ground_truth"` |
| `scenario_id` / `scenario_name` | 出題端的情境 session 與名稱 |
| `sim_start` / `sim_end` | 情境時間窗（`sim_start` 可能比資料包的第一筆讀值早一步：含 offset 0 的故障注入時刻） |
| `generated_at` | 生成時間（wall-clock） |
| `healthy_turbines` | 沒有注入故障的機組（仍可能有環境性停機） |
| `cases` | 每次故障注入一個 case（下表） |
| `unattributed_events` | 沒有任何 case 以預期碼解釋的警報 / 跳機 / 資訊事件（`ts`、`turbine_id`、`kind`、`code`、`level`、`text`）：干擾或故障連帶事件 |

case：

| 欄位 | 用於評分 | 說明 |
|---|---|---|
| `case_id` | | `C001`… |
| `turbine_id` | ✓ | 機組 |
| `category` | ✓ | `real_fault` / `sensor_fault`（`nuisance` / `healthy` 保留給 -08 後續子項）；同一個元件可能有真故障也有感測器故障（§9） |
| `component` | ✓ | 元件（詞彙見 §9） |
| `expected_alarm_codes` | ✓ | 這個故障預期的事件碼（手冊引用的正解） |
| `onset_ts` | ✓ | 故障開始（注入）時刻；`pre_existing` case 為 null（以 `sim_start` 起算，不評時效） |
| `first_alarm_ts` / `first_alarm_code` | ✓ | 第一個預期碼成立或跳機的時刻 / 碼；整段都沒出現為 null |
| `trip_ts` / `trip_code` | | 故障造成的跳機 |
| `superseded` | ✓ | 同機組同故障再注入時，舊 case 為 true：併進取代它的 case 一起評（§8） |
| `fault_id` / `fault_name_en` / `fault_name_zh` | | 模擬器的故障情境（不用於自動評分） |
| `root_cause` / `root_cause_en` | | 根因（人工 / LLM 評用） |
| `expected_alarm_sequence` | | 預期碼的等級與文字（A 在前、T 在後） |
| `manual_refs` | | 預期碼的手冊條目（頁碼、原因、處置、`see_abb`） |
| `manual_coverage` | | `z72_manual` / `abb_manual` / `mixed` |
| `expected_actions` / `expected_actions_en` | | 建議處置（標「（手冊）」者出自 Appendix C） |
| `key_signals` | | 偏離健康機組的訊號（tag 字典的 `id`） |
| `simulation_notes` / `_en` | | 模擬與真實不同之處 |
| `observed_alarm_codes` / `other_observed_codes` | | 實際出現的預期碼 / 同機組其他碼 |
| `pre_existing` | ✓ | 情境開始前就存在的故障（開始時間不明） |
| `origin` / `difficulty` / `injection` / `final_severity` | | 出題資訊 |

## 8. 評分（`examples/rag_starter_kit/score.py`）

**對應規則**
1. 每個 case 的時間窗＝`[故障開始, sim_end]`。故障開始＝`onset_ts`；同機組同故障再注入時（舊 case 標 `superseded`），舊 case 併進取代它的 case，從最早那次注入起算、第一個預期警報也取最早的。`pre_existing` case（`onset_ts` 為 null）從 `sim_start` 起算。
2. **故障診斷**＝`category` 為 `real_fault` / `sensor_fault` 的預測。依 `pack_id`、`turbine_id` 與 `ts` 落在哪個 case 的時間窗對到 case；同時落在多個 case 時，優先元件相同者，否則取最近開始的。同一時刻的預測依檔案行號排先後。
3. 對不到任何 case 的故障診斷是**誤報**（健康機組、故障開始之前、或情境結束之後）。
4. `nuisance` 預測 v1 **不評分**（-08 才有干擾 / 健康 case），只統計筆數；它也不會撤回之前的故障診斷。
5. 每個 case 以**最後一筆**對到的診斷評元件、類別與手冊引用（助手可以邊看邊修正）。
6. **時效**看「最後一段連續正確」：最後一筆診斷的元件正確時，往前找到連續都正確的第一筆，以它的 `ts` 為「診斷出來的時刻」。最後一筆錯就沒有時效分；中途改口過，從改回正確那筆算起。

**指標**（每個 case 權重相同；比例類指標中沒偵測到的 case 算 0）

| 指標 | 定義 |
|---|---|
| 偵測率 | 有任何故障診斷對到的 case / 全部 case |
| 元件正確率 | 最後診斷的 `component` 與答案相同 |
| 元件群組正確率 | 最後診斷的元件與答案同一群組（`vocabulary.json` 的 `group`，例 `pitch_control_system` 與 `pitch_system_blade_1` 同屬 `pitch`） |
| 類別正確率 | 最後診斷的 `category` 與答案相同。v1.3 起同一個元件可能有真故障也有感測器故障，且警報碼可能相同（例：主軸承磨耗與主軸承溫度量測回路劣化都送 262 / 240），只看元件或警報碼分不出類別 |
| 手冊引用 hit@1 / hit@3 | 最後診斷的 `manual_refs`（去重）前 1 / 3 個中有任何一個在 `expected_alarm_codes` |
| 手冊引用 MRR@10 | 前 10 個中第一個命中的名次倒數，平均（第 11 個以後不看：列一長串碼換不到分數） |
| 延遲 | 診斷出來的時刻 − 第一個預期警報（秒，負值＝提前）；報中位數、平均與**樣本數**（只有元件正確、有預期警報、開始時間已知的 case 才有延遲） |
| 早期預警 | 診斷出來的時刻早於第一個預期警報，或該 case 整段都沒有預期警報；`pre_existing` case 不評 |
| 誤診 | 對到 case 但元件錯的診斷筆數（狂猜各種元件會在這裡現形） |
| 誤報 | 對不到 case 的故障診斷：次數（同機組、同元件相隔 30 分鐘內算同一次，與輸出頻率無關）、筆數、機組數 |

各項分開列，不合成總分（如何加權由課程評分決定）；早期預警要與誤報、誤診一起看。`root_cause` 與 `actions` 不自動評分。

**基準**：`baseline_assistant.py`（看到警報才用關鍵字猜元件；警報文字點名感測器才判 `sensor_fault`）在四個範例資料包上：偵測率 100 %、元件 87.5 %、群組 100 %、類別 75 %、手冊 hit@1 100 %、早期預警 0、誤診 1、誤報 0。類別錯的兩個 case 都是讀值像真故障的感測器故障。手冊引用很容易拿高分（引用已出現的警報碼就對了）；真正的考驗是**警報出現前**從訊號看出問題、分辨感測器故障，以及引用尚未出現的相關條目。

## 9. 詞彙

機器可讀版：[`examples/rag_starter_kit/vocabulary.json`](../../examples/rag_starter_kit/vocabulary.json)。

| 元件 `component` | 群組 `group` | 說明 |
|---|---|---|
| `blades` | rotor | 葉片 |
| `pitch_control_system` | pitch | 變槳控制系統（全部葉片） |
| `pitch_system_blade_1` | pitch | 葉片 1 變槳系統 |
| `main_bearing` | drivetrain | 主軸承 |
| `generator_stator` | generator | 發電機定子繞組 |
| `converter_cooling_system` | converter | 變頻器冷卻系統 |
| `transformer` | grid_electrical | 變壓器 |
| `grid_connection` | grid_electrical | 電網連接（外部電網） |
| `yaw_brake_hydraulics` | yaw | 偏航煞車液壓 |
| `wind_vane_1` | yaw | 風向標 1 |
| `nacelle_ventilation` | nacelle | 機艙通風 / 冷卻 |

類別：`real_fault`、`sensor_fault`、`nuisance`（預測可用）、`healthy`（只在標準答案）。詞彙會隨故障庫擴充而增加（次版本），既有 ID 不改。

**感測器故障的 `component`**（v1.3）：填**被量測的元件**，類別填 `sensor_fault`。所以同一個元件會有真故障與感測器故障兩種答案：

| 元件 | 真故障（`real_fault`） | 感測器故障（`sensor_fault`） |
|---|---|---|
| `main_bearing` | 主軸承磨耗（262 / 240，軸承溫度 2 也升溫） | 軸承溫度 1 量測回路劣化（262 / 240，讀值像真故障）、軸承溫度 1 斷線（242） |
| `generator_stator` | 定子繞組劣化（264 / 265 / 244 / 245，兩支定子溫度一起升） | 定子溫度 1 量測回路劣化（264 / 244，讀值像真故障） |
| `pitch_system_blade_1` | 葉片 1 變槳不平衡（335 / 336） | 葉片 1 編碼器故障（326） |
| `yaw_brake_hydraulics` | 偏航煞車液壓洩漏（260 / 261 / 228） | 壓力感測器斷線（229） |
| `wind_vane_1` | — | 風向標 1 漂移（233） |

## 10. 模擬與真實的差異（受測端須知）

- 資料由 windMindOM 的 Z72 物理模型與 PLC 保護層產生：警報 / 跳機由訊號越過真實 Z72 保護設定值觸發，事件碼與手冊條目都是真的；物理是簡化模型（不是氣彈 FEM），10 分鐘 std 由 10 s 取樣算出，比真實 PLC 偏低。
- `synthetic` tag 是真實 Z72 沒有的訊號（§3.3）。`WMET_WSpeedNac` 在模擬裡是自由流風速（真實是風速計讀值），見 tag 字典的 `note`。
- 標準答案 case 的 `simulation_notes` 列出個別故障與真實不同之處（例：超速在 351 跳機後故障凍結、不會出現 320）。
- 健康機組也有事件：低風速 / 陣風造成的啟停是 `state_change`（`stop_reason` 為 `low_wind` 等）；偶發的警報 / 跳機 / 資訊事件沒有 case 能解釋時列在標準答案的 `unattributed_events`。助手要能分辨。
- **手冊 Appendix C 與 D 不一致時以 Appendix D 為準**（v1.4，DEC-20261023-01）：Appendix D 是控制系統的實際設定值。事件時間點因此是：液壓壓力低 170 bar（260）/ 150 bar（228）、延時 30 s、回到 190 bar 以上才解除；風向標差異（233）延時 60 s、風速條件是 60 s 平均（只決定能不能新判定，已跳機的不因風速低而解除）；溫度（Pt100）以 10 s 時間常數濾波後判定；切出陣風是 3 s 平均；機艙溫度 273 為 45 °C；編碼器範圍 −5–95°。Appendix C 的事件說明文字寫的是 180 bar、5 秒、10 分鐘平均——RAG 查到 Appendix C 時，數字可能和資料差幾 bar / 幾秒。
- **自動重啟被封鎖**（v1.4）：手冊 §8.3，同一個跳機碼一小時內的跳機次數超過目錄的每小時上限（`max_per_hour`）時，PLC 不再自動重啟、送 **A039「Auto restart blocked」**（手冊 p.106；xlsx 事件清單沒有這個碼，資料包的 `alarm_catalog.json` 照常列出、`manual_page` 為 106），機組停在 Shutdown，操作員復位（`reset`）才解除（A039 隨之 `alarm_cleared`）。物理層保護停機（超速、電網）也照同一套每碼計數。同一個碼不分成因算同一種跳機（例：021 伴隨所有變頻器跳機）。A039 是重複跳機的結果、不是根因：標準答案裡列在該機組 case 的 `other_observed_codes`，也列進 `unattributed_events`（沒有 case 以它為預期碼）。低風速的正常啟停不算跳機、不受次數限制。
- **感測器故障**（v1.3）只改那支感測器的讀值，機器本身與其他訊號都正常。分辨的線索：同元件的第二支感測器（`WGEN_GnBrgTmp2`、`WGEN_GnStaTmp2`）、振動、讀值與負載的關係。斷線 / 編碼器故障的讀值是固定的超出範圍值（模擬假設：Pt100 850 °C、壓力 −62.5 bar、編碼器 135°），PLC 送專屬故障碼、不再拿這支讀值判斷溫度過高 / 壓力過低 / 葉片差異。

### 10.1 開發集與正式評測

- starter kit 的範例資料包是**開發集**（附答案），只涵蓋 16 種故障中的 7 種（含 3 種感測器故障），而且每個故障都會出警報。
- 正式評測的資料包會有開發集沒有的故障、更長的情境，-08 之後還有干擾與健康負樣本；只靠「警報碼 → 元件」對照表拿不到好成績。
- 正式評測的盲測版資料包與開發集同格式，但沒有 `answers/`；答案只在評分端。

## 11. 版本歷史

| 版本 | 日期 | 內容 |
|---|---|---|
| 0.1 | 2026-10-21 | 設計文件 §5 草案；-04 標準答案、-05 資料包實作 |
| 1.0 | 2026-10-21 | 定稿（WMOM-20261021-09，DEC-20261021-04）：資料包 / 事件 / 標準答案格式沿用 -05；新增受測端輸出（§6）、評分定義（§8）、詞彙檔（§9）；`contract_version` 改為 `"1.0"`。0.1 時存下的標準答案欄位相同，**匯出成資料包時**標成 1.0（只轉換 0.1 這個舊標籤）；`GET /api/scenarios/{id}/ground-truth` 回傳存下的原值 |
| 1.1 | 2026-10-22 | 新增 WebSocket 回放（§12，WMOM-20261021-06，DEC-20261022-02）：讀值 / 事件 / 10 分鐘統計與資料包逐筆相同，受測端在同一條連線送預測、`ts` 由伺服器蓋上。資料包與標準答案格式不變（只有 `contract_version` 標成 1.1） |
| 1.2 | 2026-10-22 | 新增 OPC UA（§13，WMOM-20261021-07，DEC-20261022-03）：模仿 Bachmann Z72 tag 的目前值介面（回放或即時模擬）；WebSocket 回放加 `?stream=false`（只收預測、不送資料）與開播訊息的 `stream.data`。資料包與標準答案格式不變（只有 `contract_version` 標成 1.2） |
| 1.3 | 2026-10-22 | 感測器故障情境（WMOM-20261021-08-a，DEC-20261022-04）：資料包新增兩個真實 tag `WGEN_GnBrgTmp2`、`WGEN_GnStaTmp2`（102 個欄位）；同元件可有真故障與感測器故障（§9 對照表）；新增可能出現的事件碼 241 / 242 / 243 / 245 / 250 / 251 / 263 / 265 / 229 / 326-328；第四個範例資料包。格式不變 |
| 1.4 | 2026-10-23 | 手冊保真度（WMOM-20261022-02，DEC-20261023-01）：自動重啟被封鎖改送 A039 `alarm_raised` / `alarm_cleared`（手冊獨有碼，警報目錄快照 315 碼），不再送 `restart_blocked`（列舉值保留，舊資料包仍合法）；PLC 設定值以手冊 Appendix D 為準（§10），事件時間點與 1.3 不同；不再有全域「每小時 3 次啟動」上限，物理層保護停機改照每碼上限；`yaw_sensor_drift` 每台機組滿嚴重度都會跳 233。範例資料包重建。欄位不變 |
| 1.3（修訂） | 2026-10-22 | EPIC-DS 全面檢查（WMOM-20261022-01，DEC-20261022-05），格式與版本號不變：正式評測要伺服器強制登入（§12.1、§13.1）；正式評測總速率上限是整台伺服器的（§12.1）；正式評測的 `?stream=false` 在 OPC UA 開播前也回 4412（不再搶先開始計時）；`manifest.wind_profile` 改寫生成時實際套用的風況；文字更正（§3.5 tag 數、§13.2 `Status` 的 `missing`、4410 的寬限期） |

## 12. WebSocket 回放（v1.1）

### 12.1 流程

```
出題端                                   受測端（RAG 維修助手）
──────                                   ────────────────────
建回放（REST / CLI）→ 拿到 token ── 交付 ──▶ 連 ws://{host}:{port}/ws/replay
                                          ◀── control started（說明、tag 字典、警報目錄）
                                          ◀── reading / event / stats（依模擬時鐘）
                                          ──▶ prediction（隨時）
                                          ◀── ack（蓋上的 ts）
                                          ◀── control finished
下載 predictions.jsonl → score.py
```

- **建回放**（主管）：`POST /api/scenarios/{id}/replay-runs`，或 CLI `python tools/replay_runs.py <風場 DB> create <情境 id>`。回應中的 `token` 只出現這一次。參數：
  - `mode`：
    - `evaluation`（預設）：單次直播。時鐘從第一次連線起算，所有連線共用同一個「現在」，不能暫停或倒帶。斷線重連時預設補送已過去的資料（`?backfill=false` 不補），時間不會倒回。播完後不能再連（4410；播完後的 `close_grace_s` 秒內仍連得上，只會收到 `finished`，給途中的判斷拿 ack）。**要先試 token 請用 `?check=true`**：只回報回放狀態，不開始計時。
    - `practice`：每次連線各自從頭播，給受測端開發用。
    - **用 OPC UA 讀資料時**（§13）：正式評測在出題端啟動 OPC UA server 時就開始計時，WebSocket 連線加入同一個時鐘。
    - **同一個情境不能同時有兩種模式**（未撤銷的回放）：練習回放可以先看完正式評測的整段資料。伺服器預設拒絕（409），確定要並存才帶 `allow_overlap: true`。
  - `speed`：模擬秒 / 實際秒。
    - 範圍 0.1–10000，預設 60（1 秒運算＝1 分鐘模擬時間）。
    - 由出題端決定，受測端不能改：每個受測者每模擬秒的運算時間相同。
    - 正式評測另有上限：機組數 × 速度 ÷ 取樣週期 ≤ 1000 筆讀值 / 秒。例：14 台、每 10 秒一筆 → 714×。伺服器跟不上時，落後的時間會算在受測端頭上，所以超過上限就拒絕（422）。
    - 上限是整台伺服器的：這一個加上所有未結束（還沒開播 / 進行中、未撤銷未到期）的正式評測，總和超過 1000 筆 / 秒就拒絕（409，列出佔用的回放）。還沒開播的也算：考前再建、或縮短 `expires_in_hours`、撤銷沒在用的評測。練習回放不計。
  - `expires_in_hours`：token 有效時數（預設 7 天）；`label`：備註（受測端看不到）。
- **正式評測要伺服器強制登入**（`WMOM_AUTH_ENFORCE=true`，DEC-20261022-05）：沒開時任何連得到伺服器的人不用帳號就能從 API 讀到情境清單與故障排程，所以建立正式評測回 409（CLI 與 `tools/opcua_server.py` 結束碼 1）。練習回放照建，回應帶 `warning`。CLI 讀同一個環境變數，請在與伺服器相同的設定下執行。
- **受測端連線**：token 放 `Authorization: Bearer <token>` 標頭（建議），或 `?token=<token>`（會留在伺服器的存取紀錄）。受測端不開 windMindOM 帳號，token 只能連這一個回放（DEC-20261021-03）。
- **只送預測**（v1.2）：`?stream=false` 不送 `reading` / `event` / `stats`，只收預測（資料改從 OPC UA 讀，§13）。照樣先送 `control started`（`stream.data` 為 `false`），資料播完時送 `control finished`；預測的規則與 `ts` 相同。
  - 正式評測：同一個時鐘（OPC UA server 啟動時開播）。OPC UA server 還沒開播時拒絕（4412）：只收預測的連線不會開始計時，稍後再連。
  - 練習：時鐘用 OPC UA server 這次開播時記下的起點（不是各連線從頭播）；還沒以 OPC UA 播出時拒絕（4412），這次播出已結束也拒絕（4410）。一般的練習連線（送資料）照舊各自從頭播。
- **評分**：`GET /api/replay-runs/{run_id}/predictions` 或 `tools/replay_runs.py <db> predictions <run_id> -o predictions.jsonl` 下載 `predictions.jsonl`（請用 `-o` 寫檔：Windows 主控台的編碼印不出部分字元），與評分端版資料包（`pack_id` 相同）一起給 `score.py`。練習模式每次連線各自從頭播，評分時用 `?connection=` / `--connection` 只取一次連線。
- **撤銷**：`DELETE /api/replay-runs/{run_id}` 或 `tools/replay_runs.py <db> revoke <run_id>`。之後不能再連線、送預測；開著的連線幾秒內以 4403 關閉。token 到期同樣處理。
- **刪除情境**：刪除時一併刪除它的回放與預測。回放收過預測（評測結果）時，`DELETE /api/scenarios/{id}` 預設拒絕（409），先下載預測再帶 `force=true`。
- 範例程式：[`examples/rag_starter_kit/stream_client.py`](../../examples/rag_starter_kit/stream_client.py)（基準助手的即時版）。

### 12.2 伺服器 → 受測端

每則訊息是一個 JSON 物件，`type` 決定種類：

| `type` | 何時 | 內容 |
|---|---|---|
| `control`（`status: "started"`） | 連上後第一則 | `sim_ts`：目前模擬時間；`stream`：`contract_version`、`pack_id`、`turbine_model`、`turbines`、`sim_start` / `sim_end`、`sample_period_s`、`stats_window_s`、`stats_convention`、`duration_hours`、`site_timezone`、`wind_profile`、`rated_power_kw`（同 manifest，§3.2）與 `mode`、`speed`、`connection_no`、`backfill`、`data`（v1.2：是否送資料，`?stream=false` 時 `false`）、`close_grace_s`；`tag_dictionary`：同 `tag_dictionary.json` 的 `tags`；`alarm_catalog`：同 `alarm_catalog.json` |
| `control`（`status: "checked"`） | `?check=true` 時的唯一一則，隨後關閉（1000） | `run`：`pack_id`、`mode`、`speed`、`status`（`ready` / `not_started` / `running` / `finished` / `expired` / `revoked`）、`expires_at`、`started_at`、`ends_at` |
| `reading` | 每台機組每次取樣 | `ts`、`turbine_id`、`values`：`{Bachmann tag 名: 值}`，型別同 Parquet（§3.5；REAL32 為 float32 的最短十進位表示，缺值 null） |
| `event` | 事件發生時 | `events.jsonl` 的全部欄位（§4） |
| `stats` | 10 分鐘窗結束時（最後的殘缺窗在資料結束時） | `window_start`、`window_end`、`turbine_id`、`n_samples`、`is_partial`、`values`：`{<tag>_avg / _min / _max / _std: 值}`（同 §3.6） |
| `control`（`status: "finished"`） | 資料播完 | `sim_ts`；`closing_in_s`：伺服器幾秒後關閉連線 |
| `ack` | 收到 `prediction` | `accepted`、`ts`（伺服器蓋上的模擬時間）、`errors`（退回原因）、`ref`（受測端給的 `id`） |
| `pong` | 收到 `ping` | `sim_ts` |
| `error` | 訊息格式錯；或連線被拒（帶 `code`，隨後關閉） | `message` |

- **順序**：依模擬時間。同一時刻：先送結束於此刻的 10 分鐘統計，再送事件，最後送讀值。
- **內容與資料包逐筆相同**（`reading` ↔ `timeseries_raw.parquet`、`event` ↔ `events.jsonl`、`stats` ↔ `stats_10min.parquet`），不含任何標準答案。

**關閉碼**：

| 碼 | 意義 |
|---|---|
| 1000 | 正常結束（`finished` 後 `closing_in_s` 秒） |
| 4401 | 缺 token 或 token 無效（情境被刪除時回放一併刪除，也是這個碼） |
| 4403 | 回放已撤銷或 token 已到期（連線中撤銷 / 到期也會在幾秒內以此碼關閉） |
| 4404 | 情境不能回放（例：資料不完整、讀值超過 200 萬筆） |
| 4409 | 這個回放的連線已滿（每個回放最多 4 條） |
| 4410 | 單次回放已結束（練習回放用 `stream=false` 時：這次 OPC UA 播出已結束） |
| 4412 | 用 `stream=false`，但還沒以 OPC UA 播出（v1.2；正式評測也適用，見 §12.1） |
| 1011 | 伺服器錯誤 |

### 12.3 受測端 → 伺服器

- **`prediction`**：§6 的欄位加上 `"type": "prediction"`，可另帶 `id`（`ack` 原樣回傳）。`ts` 與 `pack_id` 不用填（填了也不採用）。
  ```json
  {"type": "prediction", "id": 17, "turbine_id": "WT002", "category": "real_fault", "component": "main_bearing", "manual_refs": [262, 240], "root_cause": "...", "actions": ["..."], "confidence": 0.7}
  ```
  伺服器當場檢查，格式錯的退回（`ack` 的 `accepted: false` 與 `errors`）、不存：
  - `turbine_id` 必須是這次回放的機組。
  - 故障診斷的 `component` 必須在詞彙內（§9）。
  - `manual_refs` 最多 50 個整數；`actions` 最多 20 項；文字最多 4000 字；`component` 最多 64 字；`confidence` 0–1。
- **`ping`**：伺服器回 `pong` 與目前模擬時間。
- **限制**：
  - 每則訊息最多 16 KB。
  - 每個回放最多收 20000 筆預測、總共 20 MB。
  - 格式錯、不是 JSON、二進位訊息都只回 `error`，不會斷線。

### 12.4 時間因果與時效

- `ts`＝伺服器**收到**預測時的模擬時間＝`sim_start` +（經過的實際秒數 × `speed`）。
  - 伺服器照時鐘送資料，不會等受測端。收得慢或想得久，`ts` 就晚（延遲變大、早期預警變少）。
  - `ts` 不會早於這條連線已送出的資料：伺服器時鐘被調回也一樣。
- **建議**：
  - 一個工作只負責收訊息，另一個做判斷（`stream_client.py` 示範）。判斷時阻塞了接收，訊息會堆在連線裡，看到的資料就落後於「現在」。
  - 伺服器每 20 秒 ping 一次。event loop 被同步呼叫（例：大模型 API）卡住太久會被斷線（1011），要放到另一個執行緒或用非同步呼叫。
- **情境結束後的預測不收**：模擬時間超過 `sim_end` 後收到的預測一律退回。評分時它們也對不到任何 case（§8 規則 3）。
- 檔案與回放的評分規則相同（§8）。差別只在 `ts` 由誰決定。

## 13. OPC UA（v1.2）

模仿 Bachmann Z72 PLC 的 OPC tag：受測端像接真實 PLC 一樣讀**目前值**。真實 Z72 走 OPC DA（`shared/plc_clients/bachmann/opc_data_reader.py`）；這裡用 OPC UA，**節點 ID＝真實的 item ID**，換成 DA client 時 tag 不用改。

### 13.1 連線與資料來源

- **端點**：`opc.tcp://{host}:{port}/windmindom/`（預設埠 4840）。只接受匿名登入（帳號密碼登入一律拒絕）、唯讀（寫值、加刪節點一律拒絕）、不加密：只開在教室 / 實驗室網路。
- **namespace**：`urn:windmindom:z72sim`。NodeId 是字串：`ns=<namespace index>;s=<item ID>`。
- **回放**（評測 / 練習）：出題端以 CLI 播出一個回放（§12 建立的同一個回放）：
  ```bash
  python tools/opcua_server.py <風場 DB> <回放 id> [--host 0.0.0.0] [--port 4840] [--exit-when-finished]
  ```
  - 正式評測（`evaluation`）：server 建好節點、開始監聽時就開播（寫入回放的開始時間）；之後的 WebSocket 連線加入同一個時鐘。server 重啟會接著播（不重來）；播完後不能再開。同 §12.1，要在 `WMOM_AUTH_ENFORCE=true` 的設定下執行，否則不開播。
  - 練習（`practice`）：每次啟動都從頭播，並把起點記在回放上（WebSocket `?stream=false` 用它對時，§12.1）。
  - 回放被撤銷、到期或刪除：幾秒內停止更新，`WindMindOM.Status` 改為 `revoked` / `expired` / `missing`，再過 10 秒關閉 server。
  - OPC UA server 與 WebSocket 伺服器要在同一台電腦（或時鐘對準）：開始時間是絕對時間，兩台電腦差 Δ 秒，資料與預測的時間就差 Δ × 速度。
- **即時模擬**：主程式以環境變數 `WMOM_OPCUA_ENABLE=true` 開啟，每秒寫入即時模擬的最新讀值與 PLC 狀態。沒有標準答案，給開發與展示用。
  - 預設只聽本機（`WMOM_OPCUA_HOST` 預設 `127.0.0.1`）；要給其他電腦連須明確設定（例 `0.0.0.0`），`WMOM_OPCUA_PORT` 預設 4840。
  - 產生情境（批次）期間不更新（`Status`＝`idle`），批次最後一步的讀值也不發布。但批次與即時模擬共用模型：批次注入的故障之後仍留在即時模擬裡（維護中心清除前都看得到）。**有受測端連著即時 OPC UA 時，不要在同一個主程式產生考題。**

### 13.2 節點

| 節點（item ID） | 型別 | 內容 |
|---|---|---|
| `Z72.H{nn}.{group}.Z72PLC__UI_Loc_*` | 依 PLC：REAL32 → Float、SINT16 → Int16、UINT16 → UInt16、BOOL → Boolean | 讀值。欄位與資料包的 tag 字典（§3.3）同一組；`synthetic` tag 一樣掛著，節點說明（Description）寫明 `synthetic` |
| `Z72.H{nn}.WMET.Z72PLC__UI_Loc_WMET_Analogue_WSpeedNacAvg10m` | Float | 真實 tag，模擬器沒有輸出：server 以 `WSpeedNac` 的 10 分鐘移動平均算出（節點說明寫明 derived） |
| `Z72.H{nn}.Z72PLC__ActiveAlarm[0..20]` | Int16 | 目前成立的警報碼（A） |
| `Z72.H{nn}.Z72PLC__ActiveTrip1[0..20]` / `ActiveTrip2[0..20]` | Int16 | 目前成立的跳機碼（T1 / T2；鎖存中的也在） |
| `WindMindOM.Source` / `Status` / `SimTime` / `PackId` / `Mode` / `Speed` | String / String / DateTime / String / String / Double | 模擬器狀態（不是真實 PLC 的 tag）：`Source`＝`replay` / `live`；`Status`＝`running` / `finished` / `revoked` / `expired` / `missing`（回放被刪除）/ `idle`；`SimTime`＝目前模擬時間（UTC） |

- **站號**：`H{nn}` 是機組 ID 的數字補兩位（`WT001` → `H01`，同真實讀取腳本），對應 WebSocket 開播訊息的 `turbines`。
- **瀏覽**：`Objects/Z72/H01/WTUR/Z72PLC__UI_Loc_WTUR_State_TurSt`（BrowseName＝tag 名），事件碼陣列在 `Objects/Z72/H01/` 底下。
- **讀值**：每次更新寫入各機組**最新一筆**讀值；`SourceTimestamp`＝該筆的模擬時間，`ServerTimestamp`＝寫入的實際時間。缺值的 StatusCode 為 `BadNoData`；開播前（事件碼陣列也是）為 `BadWaitingForInitialData`；即時模擬換了風場、某台機組不見時，它的節點改為 `BadNoData`。值與 WebSocket `reading` / `timeseries_raw.parquet` 相同（REAL32 讀回 float32 逐位元相同）。
- **事件碼陣列**（SINT16[21]，同真實 PLC）：依成立順序排列、空位為 0。規則（與 `events.jsonl` 一致）：
  - `alarm_raised`（A）加入 `ActiveAlarm`、`alarm_cleared` 移除。
  - `trip` 依等級加入 `ActiveTrip1` / `ActiveTrip2`、`trip_cleared` 移除。超過每小時重啟上限時跳機碼留在陣列（鎖存），A039 加入 `ActiveAlarm`，操作員復位時移除。
  - 操作員復位（`reset`）本身不改陣列：被解除的跳機各有一筆 `trip_cleared`（條件仍成立的會再 `trip`）；維護清除故障時的復位不解除鎖存，跳機陣列照舊（有 A039 時 `alarm_cleared`，從 `ActiveAlarm` 移除）。資訊事件（I）不在任何陣列。
  - 陣列＝PLC 目前成立的警報與鎖存中的跳機（即時模擬每一步都與 PLC 狀態一致，回放由事件流重建、規則相同）。
  - 真實 PLC 陣列的排列方式手冊沒有寫；這是模擬的約定。

### 13.3 與 WebSocket / 資料包的差別

- **只有目前值**：兩次讀取之間出現又消失的警報、每一筆讀值、10 分鐘統計、`state_change` 事件都讀不到。要完整資料用 WebSocket 回放或資料包（內容相同）。
- 更新間隔：回放每「一個取樣週期 ÷ 速度」實際秒，夾在 0.05–0.2 秒（60× 時約 0.17 秒＝一筆取樣；3000× 時 0.05 秒＝150 模擬秒）；即時模擬每 1 秒。速度越快，越多短暫的警報讀不到。
- **預測**：連 WebSocket `?stream=false`（同一個 token），格式與 `ts` 規則同 §12.3–12.4。判斷的時間依據是伺服器收到預測時的模擬時間，與受測端讀到的 `SourceTimestamp` 無關。
- 範例程式：[`examples/rag_starter_kit/opcua_client.py`](../../examples/rag_starter_kit/opcua_client.py)（讀目前值、比較前後兩次的事件碼陣列，新的碼交給基準助手、經 WebSocket 送出）。
