# windMindOM × RAG 維修助手：資料介面合約 v1.0

> **版本**：1.0（2026-10-21，WMOM-20261021-09）。取代設計文件 [`EPIC-DS_realistic_data_source.md`](../product/EPIC-DS_realistic_data_source.md) §5 的 v0 草案。
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
- **評分端**以標準答案（`GET /api/scenarios/{id}/pack/full` 或 CLI `--ground-truth`）和 `score.py` 評分。
- v1 的交付管道是**檔案**。之後的 WebSocket 回放（WMOM-20261021-06）與 OPC UA（-07）沿用本合約的事件（§4）與預測（§6）格式。

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
  alarm_catalog.json       Z72 警報目錄快照（314 碼，含手冊原因 / 處置 / 頁碼）
  timeseries_raw.parquet   原始時序（每台機組每個取樣週期一列）
  stats_10min.parquet      10 分鐘統計
  events.jsonl             可觀測事件（§4）
```

`pack_id` 為小寫英數與 `-`（例 `z72-scenario-00012`、`z72-starter-01`），不含情境名稱。盲測版沒有 `ground_truth.json`。

### 3.2 manifest.json

| 欄位 | 型別 | 說明 |
|---|---|---|
| `contract_version` | str | `"1.0"` |
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
| `source` | `bachmann_real`（真實 Z72 PLC 有這個 tag，45 個）或 `synthetic`（依命名規則自創，55 個） |
| `note` | 模擬語意與真實不同之處；多數為 null |

**回答時的注意**：`synthetic` tag 在真實 Z72 上不存在（振動頻帶、負載彎矩、無功功率…），助手的建議不能假設現場讀得到。

### 3.4 alarm_catalog.json

`{"turbine_model", "source", "events": [...]}`，每碼：`code`、`event_id`（例 `A_262`）、`level`（`A` 警報 / `T1` 正常停機 / `T2` 緊急停機 / `I` 資訊）、`text`、`plc_tag`、`cause`、`rectification`、`max_per_hour`（每小時自動重啟上限）、`manual_page`（Z72 手冊頁碼）。手冊對變頻器 / 變壓器事件只寫 `See [ABB]`，答案在 ABB 變頻器手冊。

### 3.5 timeseries_raw.parquet

| 欄 | 型別 | 說明 |
|---|---|---|
| `timestamp` | `timestamp[us, tz=UTC]` | 取樣時間 |
| `turbine_id` | string | 機組 |
| `<Bachmann tag 名>` × 100 | 依 PLC 型別：REAL32 → float32、SINT16 → int16、UINT16 → uint16、BOOL → bool | 讀值；缺值為 null |

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

## 4. events.jsonl

一行一個 JSON 物件，依時間排序（同一時刻依發生順序：跳機在它造成的停機之前）。**每行都有下列全部欄位**，不適用者為 `null`：

| 欄位 | 說明 |
|---|---|
| `ts` | 時間（`YYYY-MM-DDTHH:MM:SS.ffffffZ`） |
| `turbine_id` | 機組 |
| `event_type` | `alarm_raised` 警報成立、`alarm_cleared` 警報解除、`trip` 跳機（T1 / T2）、`trip_cleared` 跳機解除、`restart_blocked` 超過重啟上限、`reset` 操作員復位、`info` 資訊事件、`state_change` 運轉狀態轉換 |
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

**時間因果**：離線評分無法檢查助手有沒有偷看 `ts` 之後的資料，請自律（`pack_reader.Pack.raw_until` / `events_until` 示範「只看當下以前」）。WebSocket 回放（-06）上線後，以收到資料的時刻為準。

格式錯誤的行（缺必填欄位、類別不在清單、故障診斷的元件不在詞彙內）不計分，評分報告會列出行號與原因。

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
| `category` | ✓ | `real_fault` / `sensor_fault`（`nuisance` / `healthy` 保留給 -08） |
| `component` | ✓ | 元件（詞彙見 §9） |
| `expected_alarm_codes` | ✓ | 這個故障預期的事件碼（手冊引用的正解） |
| `onset_ts` | ✓ | 故障開始（注入）時刻；`pre_existing` case 為 null（以 `sim_start` 起算） |
| `first_alarm_ts` / `first_alarm_code` | ✓ | 第一個預期碼成立或跳機的時刻 / 碼；整段都沒出現為 null |
| `trip_ts` / `trip_code` | | 故障造成的跳機 |
| `superseded` | ✓ | 同機組同故障再注入時，舊 case 為 true（不評分） |
| `fault_id` / `fault_name_en` / `fault_name_zh` | | 模擬器的故障情境（不用於自動評分） |
| `root_cause` / `root_cause_en` | | 根因（人工 / LLM 評用） |
| `expected_alarm_sequence` | | 預期碼的等級與文字（A 在前、T 在後） |
| `manual_refs` | | 預期碼的手冊條目（頁碼、原因、處置、`see_abb`） |
| `manual_coverage` | | `z72_manual` / `abb_manual` / `mixed` |
| `expected_actions` / `expected_actions_en` | | 建議處置（標「（手冊）」者出自 Appendix C） |
| `key_signals` | | 偏離健康機組的訊號（tag 字典的 `id`） |
| `simulation_notes` / `_en` | | 模擬與真實不同之處 |
| `observed_alarm_codes` / `other_observed_codes` | | 實際出現的預期碼 / 同機組其他碼 |
| `origin` / `difficulty` / `injection` / `final_severity` / `pre_existing` | | 出題資訊 |

## 8. 評分（`examples/rag_starter_kit/score.py`）

**對應規則**
1. 只評 `superseded` 為 false 的 case。case 的時間窗＝`[onset_ts, sim_end]`（`onset_ts` 為 null 時從 `sim_start` 起）。
2. **故障診斷**＝`category` 為 `real_fault` / `sensor_fault` 的預測。依 `pack_id`、`turbine_id` 與 `ts` 落在哪個 case 的時間窗對到 case；同時落在多個 case 時，優先元件相同者，否則取最近開始的。
3. 對不到任何 case 的故障診斷是**誤報**（健康機組、或故障開始之前）。
4. `nuisance` 預測不對 case；落在某 case 時間窗內的另計「把故障當干擾」。
5. 每個 case 以**最後一筆**對到的診斷評元件、類別與手冊引用；時效以**第一筆元件正確**的診斷計。

**指標**（每個 case 權重相同；沒偵測到的 case 在各項都算 0）

| 指標 | 定義 |
|---|---|
| 偵測率 | 有任何故障診斷對到的 case / 全部 case |
| 元件正確率 | 最後診斷的 `component` 與答案相同 |
| 元件群組正確率 | 最後診斷的元件與答案同一群組（`vocabulary.json` 的 `group`，例 `pitch_control_system` 與 `pitch_system_blade_1` 同屬 `pitch`） |
| 類別正確率 | 最後診斷的 `category` 與答案相同（重點：`sensor_fault` vs `real_fault`） |
| 手冊引用 hit@1 / hit@3 | 最後診斷的 `manual_refs` 前 1 / 3 個中有任何一個在 `expected_alarm_codes` |
| 手冊引用 MRR | 第一個命中的名次倒數，平均 |
| 延遲 | 第一筆元件正確的診斷 `ts` − `first_alarm_ts`（秒，負值＝提前）；報中位數與平均 |
| 早期預警 | 第一筆元件正確的診斷早於 `first_alarm_ts`，或該 case 整段都沒有預期警報 |
| 誤報 | 對不到 case 的故障診斷筆數，與涉及的機組數 |

各項分開列，不合成總分（如何加權由課程評分決定）。`root_cause` 與 `actions` 不自動評分。

**基準**：`baseline_assistant.py`（看到警報才用關鍵字猜元件）在三個範例資料包上：偵測率 100 %、元件 80 %、群組 100 %、類別 80 %、手冊 hit@1 100 %、早期預警 0。手冊引用很容易拿高分（引用已出現的警報碼就對了）；真正的考驗是**警報出現前**從訊號看出問題、分辨感測器故障，以及引用尚未出現的相關條目。

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

## 10. 模擬與真實的差異（受測端須知）

- 資料由 windMindOM 的 Z72 物理模型與 PLC 保護層產生：警報 / 跳機由訊號越過真實 Z72 保護設定值觸發，事件碼與手冊條目都是真的；物理是簡化模型（不是氣彈 FEM），10 分鐘 std 由 10 s 取樣算出，比真實 PLC 偏低。
- `synthetic` tag 是真實 Z72 沒有的訊號（§3.3）。`WMET_WSpeedNac` 在模擬裡是自由流風速（真實是風速計讀值），見 tag 字典的 `note`。
- 標準答案 case 的 `simulation_notes` 列出個別故障與真實不同之處（例：超速在 351 跳機後故障凍結、不會出現 320）。
- 健康機組也可能有事件（低風速停機、偶發跳機，列在 `unattributed_events`）——助手要能分辨。

## 11. 版本歷史

| 版本 | 日期 | 內容 |
|---|---|---|
| 0.1 | 2026-10-21 | 設計文件 §5 草案；-04 標準答案、-05 資料包實作 |
| 1.0 | 2026-10-21 | 定稿（WMOM-20261021-09）：資料包 / 事件 / 標準答案格式沿用 -05；新增受測端輸出（§6）、評分定義（§8）、詞彙檔（§9）；`contract_version` 改為 `"1.0"`（0.1 的標準答案匯出時一併標成 1.0，欄位相同） |
