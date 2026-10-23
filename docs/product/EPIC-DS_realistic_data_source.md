# EPIC-DS — 擬真資料源（供外部 RAG 即時維修助手驗證）

> 版本：v0.1（2026-10-21）　決策依據：[`decision_log.md`](decision_log.md) DEC-20261021-01
> 狀態：設計定案、Phase 1 開工
> 外部消費端：**RAG 即時維修助手**（尚未建立，交由學生專題完成）

---

## 1. 目標一句話

讓 windMindOM 的模擬器產生**「看起來像真實 Z72 風場、而且附標準答案」**的運轉資料，
透過 **檔案、串流、OPC UA** 三種管道餵給外部的 RAG 維修助手，作為它驗證 RAG 功能的資料來源。

## 2. 「真實」的定義（對 RAG 驗證而言）

RAG 助手實際看得到的是：**警報（碼 / 文字 / 等級）+ 機組狀態 + 異常前後的 SCADA 趨勢**。
它拿警報去查 Z72 手冊。因此擬真的優先順序是：

| 優先 | 擬真項目 | 理由 |
|:---:|---|---|
| 1 | **警報碼、文字、等級、PLC tag 與真實 Z72 完全一致** | 碼對不上，RAG 答對了反而會被判錯；驗證失去意義 |
| 2 | **每筆異常都有標準答案（ground truth），且與可觀測資料分離** | 真實資料沒有答案卷；模擬器知道根因是它當驗證資料源的最大價值 |
| 3 | **可觀測資料長得像真實 SCADA** | 真實 tag 名、UTC 時間戳、10-min avg/min/max/std、感測器雜訊/漂移/卡值 |
| 4 | **警報行為像真實 PLC** | 連鎖（A → T1 → 跳機）、遲滯、reset、每小時重啟次數限制 |
| 5 | **情境有難度與多樣性** | 感測器故障 vs 真故障、多重故障、誤報、健康負樣本、警報前的早期徵兆 |
| 6 | 物理精度（僅限會改變特徵訊號者） | BEM / Kaimal / 多模態結構對 RAG 看到的東西影響小，留 parking lot |

**範圍限定 Z72**：手冊與真實警報清單都是 Z72；`update_spec` 對非 Z72 機型只重建一半子模型
（見 2026-10-20 物理層盤點），在修好前其他機型不列入資料源。

## 3. 現況盤點（2026-10-20 / 21 調查結果，Phase 1a 之前的快照）

> 「真實警報目錄」「模擬器警報碼」兩列已由 Phase 1a（WMOM-20261021-02）處理，現況見 §6.1；
> 「情境事件」「標準答案」兩列已由 Phase 2（WMOM-20261021-04）處理，見 §6.7。

| 需求 | 現況 | 證據 |
|---|---|---|
| 真實警報目錄 | 真實清單 314 筆在 `docs/1040610-Z72_PLC_OPC_TAG_1040510.xlsx`「警告訊息列表」（T1 207 / A 62 / I 24 / T2 21）；手冊 Appendix C（原因、處置提示、每小時重啟次數）只以 raw text 存在 `modules/knowledge/data/wind_farm_vectors/chunks.jsonl`。程式裡沒有目錄模組（`shared/alarm_codes.py` 曾規劃未建） | ISSUES.md 舊規劃段 |
| 模擬器警報碼 | 24 個碼散在 11 個 `FAULT_SCENARIOS`；多個與真實不符：350（模擬＝變壓器溫度高；真實＝DC battery maintenance switch，變壓器溫度高是 417）、351/311/30/32/241 意義不同、41/42/43 不存在、223/256/273 等級錯 | `modules/monitoring/simulator/physics/fault_engine.py:58-280` |
| 警報行為 | 只有 `severity >= threshold`；無連鎖、遲滯、ack；故障期間狀態 7↔3 跳動；`TurbineSpec` 溫度門檻未接 | `fault_engine.py:387-396`、`turbine_physics.py:66-79` |
| 情境事件 | `generate_bulk` 不跑 `_detect_sim_events` → 情境內沒有警報/跳機/狀態事件；`history_events` 無 `session_id` | `engine.py:351-434`、`data_broker.py:483`、`storage.py:168-179` |
| 標準答案 | 故障情境無根因、元件、手冊章節、處置欄位；情境只存注入排程 | `fault_engine.py`、`routers/config.py:338-346` |
| 對外管道 | WS 每 2 s 推讀值、無事件通道、無凍結情境回放；無 Parquet；`farms.py` 資料集端點產出 0 筆；OPC 只有 DA client（legacy OPC UA server 未接線） | `app.py:256-297`、`routers/farms.py:344`、`modules/monitoring/opcua_interface.py` |
| tag 名稱 | 111 個中 40 個是真實 Bachmann `Z72PLC__UI_Loc_*`，71 個依命名規則自創 | `scada_registry.py:37-446` |
| 時間戳 | 全部 naive local `datetime.now()`；knowledge `AlertEvent` 卻要求 tz-aware | `storage.py`、`modules/knowledge/schemas.py` |
| 評估集 | 無 | — |

## 4. 架構：一份凍結情境、三條輸出管道

```
             ┌──────────── windMindOM ─────────────┐
 wind profile│  simulator (Z72)                     │
 fault plan ─┤   ├─ physics + sensor model          │
 seed        │   ├─ alarm engine（真實 Z72 目錄）    │
             │   └─ ground-truth recorder            │
             │            │                          │
             │   frozen scenario（SQLite session）    │
             │      │          │            │       │
             │  ① pack 匯出  ② WS 回放   ③ OPC UA   │
             └──────┼──────────┼────────────┼───────┘
                    ▼          ▼            ▼
             檔案（離線評估） 串流（即時）  模仿 Bachmann tag
                    └──────────┴────────────┘
                     外部 RAG 即時維修助手（學生專題）
                     ground_truth.json 只給評分端
```

設計原則：

1. **同一份凍結情境驅動三條管道**，結果可重現（seed + manifest）。
2. **盲測**：可觀測資料（讀值、事件）**不含**任何 `fault_id` / 根因；答案只在 `ground_truth.json`。
3. **真實優先**：真實存在的 tag / 警報一律用真名；自創 tag 在 tag 字典標 `source: synthetic`。
4. **介面合約版本化**（`contract_version`），學生端依版本開發；windMindOM 不實作 RAG 助手本身。
5. 外部系統未接上前，可用 repo 內 `modules/knowledge` 當 smoke consumer 跑通管線
   （注意：其 Chroma retriever 目前忽略警報碼）。

## 5. 介面合約 v0（草案，已定稿為 v1）

> **v1 已定稿**（WMOM-20261021-09）：[`docs/integration/rag_assistant_data_contract_v1.md`](../integration/rag_assistant_data_contract_v1.md) 為準，包含受測端輸出與評分定義；本節保留為設計脈絡。

### 5.1 檔案：情境資料包（scenario pack）

> 以下是 -05 實作的 v0.1 格式（2026-10-21）；細節與已知限制見 §6.8。

```
{pack_id}/                 # pack_id = z72-scenario-{session id 5 位數}（不帶情境名稱）
  manifest.json            # contract_version、pack_id、turbine_model、turbines、sim_start / sim_end
                           # （第一 / 最後一筆讀值，UTC）、sample_period_s（由資料推得）、stats_window_s、
                           # stats_convention、duration_hours、site_timezone、wind_profile、rated_power_kw、
                           # ground_truth_included、generator（含 exporter_version）、reproducibility、
                           # counts、files（各檔 sha256 / bytes）、exported_at
  tag_dictionary.json      # tag → opc_path、id、subsystem、data_type、unit、label_en / label_zh、
                           # source: bachmann_real | synthetic、note（模擬語意與真實不同之處）
  alarm_catalog.json       # Z72 警報目錄快照（全部 314 碼：code、event_id、level、text、plc_tag、cause、
                           # rectification、max_per_hour、manual_page）
  timeseries_raw.parquet   # timestamp(UTC), turbine_id, <Bachmann tag 名>×100（型別依 PLC：REAL32→float32、
                           # SINT16→int16、UINT16→uint16、BOOL→bool；缺值為 null）
  stats_10min.parquet      # window_start / window_end(UTC), turbine_id, n_samples, is_partial,
                           # 類比 tag 的 _avg/_min/_max/_std、離散 tag 的 _min/_max
  events.jsonl             # 可觀測事件流（不含答案），每行欄位相同
  ground_truth.json        # 標準答案（只在評分端版本）
```

- **時間戳**：JSON 一律 `YYYY-MM-DDTHH:MM:SS.ffffffZ`；Parquet 為 `timestamp[us, tz=UTC]`。每筆讀值是該模擬步結束時的狀態。
- **欄名**：真實 Bachmann tag 名（不含 OPC 分組前綴），例 `Z72PLC__UI_Loc_WTUR_Analogue_TotPwrAt`；`Z72PLC__UI_Mbus_Contact[2]` 這類含方括號的名稱在 SQL（duckdb 等）要加引號。
- **不在資料包內的 tag**：16 個模擬器內部量（尾流 / 大氣模型狀態、疲勞累積損傷 / 剩餘壽命 / 疲勞警報等級、轉子不平衡力、齒面磨耗指數），見 DEC-20261021-03。
- **10 分鐘統計**：窗對齊 UTC 整 10 分鐘，左閉右開 `[window_start, window_end)`；std ddof 1；`is_partial` = `n_samples < floor(600 / sample_period_s)`（頭尾窗與資料缺口）；風向（`WDirAbs`）的 avg 為圓平均、std 為 Yamartino，min / max 為線性值；缺值不計入，整窗無值為 null。慣例也寫在 manifest 的 `stats_convention`。

`events.jsonl` 一行一事件，每行都有同一組欄位（不適用者為 `null`）：

```json
{"ts": "2026-03-01T03:12:40.000000Z", "turbine_id": "WT003", "event_type": "alarm_raised",
 "alarm_code": 262, "alarm_level": "A", "alarm_text": "Main bearing 1 temperature high",
 "event_id": "A_262", "plc_tag": "Z72PLC__ActiveAlarm",
 "from_state": null, "to_state": null, "from_state_name": null, "to_state_name": null, "stop_reason": null}
```

`event_type` ∈ `alarm_raised` / `alarm_cleared` / `trip` / `trip_cleared` / `restart_blocked` / `reset` / `info` / `state_change`（v0 草案的 `operator` 尚未產生）。`state_change` 帶 `from_state` / `to_state`（Bachmann TurSt 1–9）與名稱；進入停機（7 / 9）時帶 `stop_reason` ∈ `plc_trip` / `high_wind` / `low_wind` / `grid` / `overspeed` / `operator` / `null`。同一時刻的事件依發生順序（跳機在它造成的停機之前）。

`ground_truth.json`（v0 範例；實際欄位更多，見 §6.7，時間戳轉成 `Z` 並加 `pack_id`）：

```json
{"contract_version": "0.1", "pack_id": "...",
 "cases": [{
   "case_id": "C001", "turbine_id": "WT003",
   "category": "real_fault",
   "fault_id": "main_bearing_wear", "component": "main_bearing",
   "root_cause": "主軸承潤滑劣化導致磨耗、溫升",
   "onset_ts": "...", "first_alarm_ts": "...", "trip_ts": "...",
   "expected_alarm_codes": [262, 240],
   "manual_refs": [{"doc": "Z72 User Manual", "section": "Appendix C", "event_code": 262}],
   "expected_actions": ["..."],
   "difficulty": "medium"}]}
```

`category` ∈ `real_fault` / `sensor_fault` / `nuisance` / `healthy`。

### 5.2 串流：WebSocket 回放

> **已實作**（WMOM-20261021-06，§6.11）：實際介面見合約 v1.2 §12。和草案不同的地方：
> - 端點是 `ws://{host}/ws/replay`，以回放 token 選情境，不帶 scenario_id。
> - 速度由出題端建回放時決定。
> - 受測端在同一條連線送預測，伺服器蓋 `ts`。

- `ws://{host}/ws/replay/{scenario_id}?speed=1`（speed = 1 為實時，>1 加速）
- 訊息：`{"type": "reading", ...}`、`{"type": "event", ...同 events.jsonl}`、
  `{"type": "control", "status": "started|paused|finished", "sim_ts": ...}`
- 不推送 ground truth。

### 5.3 OPC UA：模仿 Bachmann Z72 tag

> **已實作**（WMOM-20261021-07，§6.12）：實際介面見合約 v1.2 §13。和草案不同的地方：
> - 事件碼陣列是 `[0..20]`（PLC 的 SINT16[21]，真實讀取腳本只讀前 10 個）。
> - 另有 `WSpeedNacAvg10m`（server 算的 10 分鐘平均）與 `WindMindOM.*` 狀態節點。
> - 預測經 WS `?stream=false` 送；正式評測在出題端啟動 server 時開播。

- Endpoint：`opc.tcp://{host}:4840/windmindom/`，namespace URI `urn:windmindom:z72sim`
- 節點路徑對齊真實 PLC 讀取腳本（`shared/plc_clients/bachmann/opc_data_reader.py`）：
  `Z72.H{n}.{group}.Z72PLC__UI_Loc_*`（例 `Z72.H01.WMET.Z72PLC__UI_Loc_WMET_Analogue_WSpeedNac`）、
  `Z72.H{n}.Z72PLC__ActiveAlarm[0..9]`、`Z72PLC__ActiveTrip1[0..9]`、`Z72PLC__ActiveTrip2[0..9]`
- 資料來源：凍結情境回放（與 5.2 共用回放器）或 live 模擬
- 目的：外部系統寫的 OPC 介接層，將來換成真實 PLC 時不必重寫

### 5.4 評估建議（給學生端）

- 檢索：`manual_refs` hit@k、MRR
- 診斷：`root_cause` / `component` 正確率；`sensor_fault` vs `real_fault` 辨識率
- 時效：從 `alarm_raised` 到給出建議的延遲
- 早期徵兆：`first_alarm_ts` 之前能否提出預警（加分項）

## 6. 分階段計畫（不設日期）

| Phase | Issue | 內容 |
|---|---|---|
| 1a ✅ | WMOM-20261021-02 | **Z72 真實警報目錄**：xlsx 314 筆 → `shared/alarm_codes.py`（+ 手冊 Appendix C 原因/處置/重啟次數）；11 個故障情境改用真實碼（2026-10-21 done） |
| 1b-a ✅ | WMOM-20261021-03-a | **故障物理校正**：各情境量測訊號在物理上能越過真實保護設定值（2026-10-21 done） |
| 1b-b ✅ | WMOM-20261021-03-b | **PLC 保護層**：警報 / 跳機改由訊號觸發、T1/T2 停機、鎖存與重啟上限、修 7↔3 狀態跳動（2026-10-21 done） |
| 1b-c ✅ | WMOM-20261021-03-c | **UTC tz-aware 時間戳**（2026-10-21 done） |
| 2 ✅ | WMOM-20261021-04 | **標準答案 + 情境事件**：故障情境 metadata（根因/元件/預期警報序列/手冊條目/處置）；bulk 路徑產生事件；`history_events` 加 `session_id`；ground truth 落庫（2026-10-21 done，§6.7） |
| 3a ✅ | WMOM-20261021-05 | **① 檔案**：情境資料包匯出（含 10-min stats）；移除 `farms.py` 壞端點（2026-10-21 done，§6.8） |
| 3b ✅ | WMOM-20261021-06 | **② 串流**：凍結情境回放器 + WS 回放端點（含事件通道）（2026-10-22 done，§6.11） |
| 3c ✅ | WMOM-20261021-07 | **③ OPC UA server**：模仿 Bachmann tag（`asyncua`），接 3b 回放器與即時模擬（2026-10-22 done，§6.12） |
| 3d ✅ | WMOM-20261021-09 | **學生專題 starter kit**：介面合約 v1 定稿 + 範例資料包 + 讀取範例程式（2026-10-21 done，§6.9） |
| 4 | WMOM-20261021-08 | **難度與多樣性**：警報連鎖與重啟限制、感測器故障（標記）、多重故障、誤報、健康負樣本、早期徵兆案例；故障庫往 Z72 常見事件擴充。拆子項分 PR：-08-a 感測器故障 vs 真故障 ✅（2026-10-22，§6.13）、-08-b 誤報 / 健康負樣本 ✅（2026-10-23，§6.16） |
| 檢查 ✅ | WMOM-20261022-01 | **全面程式碼檢查 + 功能驗證**（-08 其餘子項前）：三路 code review、真伺服器端到端三條管道；修正與四個設計決策（DEC-20261022-05，§6.14） |
| 4（保真度）✅ | WMOM-20261022-02 | **手冊保真度**：Appendix D 延遲 / 範圍、A039、`yaw_sensor_drift` 不跳 233（2026-10-23 done，DEC-20261023-01，§6.15） |
| 5 | （parking lot） | 只修會改變特徵訊號的物理：10-min std 合理化、yaw error → 發電損失等；高保真物理不做 |

建議順序：1a → 1b → 2 → 3a → 3d（先讓學生拿到檔案）→ 3b → 3c → 4。

### 6.1 Phase 1a 定案與已知限制

~~**警報門檻慣例**：A 級警報門檻 < `auto_trip_severity`；T1 / T2 跳機碼門檻 == `auto_trip_severity`。~~
-03-b 起已移除 severity 門檻，警報 / 跳機由 PLC 保護層依訊號判定（§6.3）；`alarm_codes` 只是情境的預期碼。

**已知限制（留給 Phase 1b / 2）**：

1. ~~**警報由 severity 觸發，不是由物理訊號越過真實門檻觸發**~~ → -03-b 已解（§6.3）。
2. **5 個情境在跳機前沒有任何警報**（pitch_imbalance、yaw_sensor_drift、generator_overspeed、blade_icing、grid_voltage_sag）。這符合真實 Z72 事件清單（沒有對應的 A 級警報），但 ground truth 的 `first_alarm_ts` 會等於 `trip_ts`，「早期徵兆」評分只能靠 SCADA 趨勢。
3. ~~**跳機一律走 emergency stop**~~ → -03-b 已解：PLC 判定的 T1 走正常伺服停機（TurSt 9）、T2 走緊急變槳（TurSt 7）。
4. **變頻器事件（400-700）手冊只寫「See [ABB]」**：只靠 Z72 手冊的 RAG 查不到細節，ground truth 應標註預期答案僅能指向 ABB 手冊。
5. ~~物理層自有跳機只寫 `shutdown_cause` 字串，沒有事件碼~~ → -03-b 已解：對應到 351 / 320 / 481 / 482 / 475 / 489（+021）與 I 201。

### 6.2 Phase 1b-a 故障物理校正結果（2026-10-21）

保護設定值在 `TurbineSpec`（manual = 手冊 Appendix C；assumed = 手冊只寫「See [ABB]」，取高於本模型健康機組在天氣模型最熱日——37 °C、額定負載——的最大值）。
下表為 14 m/s、25 °C、3 h 定嚴重度的量測值（`tests/physics/test_fault_threshold_reach.py` 鎖住「滿嚴重度越過、0.5 未到、健康機組 30 °C 與 37 °C 不越」）：

| 情境 | 訊號 | 設定值（事件） | 嚴重度 0.6 | 0.8 | 1.0 |
|---|---|---|---|---|---|
| bearing_wear | `WGEN_GnBrgTmp1` | 85 A262 / 95 T240（manual） | 68 | 89 | 135 |
| stator_winding_degradation | `WGEN_GnStaTmp1` | 140 A264 / 150 T244（manual） | 102 | 132 | 180¹ |
| nacelle_cooling_failure | `WNAC_NacTmp` / `WNAC_NacCabTmp` | 46 A273（assumed）/ 50 T256（manual） | 37 / 44 | 42 / 49 | 49 / 57 |
| transformer_overheat | `WGDC_TrfCoreTmp` | 80 A417 / 90 T444（assumed） | 67 | 83 | 107 |
| converter_cooling_fault | `WCNV_IGCTWtrTmp` | 51 A420 / 56 T437（assumed） | 46 | 56 | 81 |
| hydraulic_leak | `WYAW_YwBrkHyPrs` | 180 A260 / 150 T228（manual） | 162 | 146 | 130 |
| yaw_sensor_drift | 風向標 1−2 差 | 15° T233（manual） | 10.9 | 14.5 | 18.1 |
| pitch_imbalance | 葉片角度差 | 1° / 5 s T335（manual） | 0.9 | 1.2 | 1.4 |
| blade_icing | 機艙振動 max(X, Y) | 7 mm/s T236（assumed） | 6.0 | 7.4 | 8.7 |
| grid_voltage_sag | `WCNV_VtgMsCnvGd1`（kV 相電壓） | LVRT band 1（< 0.90 p.u. 過久）跳機 | 正常（已降載） | 跳機（約 0.7 起） | 跳機 |
| generator_overspeed | `WROT_RotSpd` | 26.5 rpm（manual，物理層軟體超速停機） | 約 0.45 起停機 | — | — |

¹ 180 是感測器量程上限（`_get_sensor_config` 的 Tmp max），不是物理值。

負載相依：同樣滿嚴重度，9 m/s 時 stator 只到 97 °C、不會警報；generator_overspeed 也不會超速。

注意事項（給 -03-b / -04）：
- **事件順序由物理決定**：nacelle_cooling_failure 的機艙控制櫃（T256，50 °C）通常比機艙空氣（A273，46 °C）先到，跳機可能先於警報出現。
- **37 °C 健康機組會碰到手冊的 T256（50 °C）**：真機在同樣條件也會跳，是合理的環境性跳機，不調整手冊值。
- **洩漏是隨時間累積的**：converter 冷卻液位跌破 70 % 才會壓降（A432），嚴重度 0.3 約 7 h、0.1 約 30 h；ground truth 不能只看嚴重度。
- **葉片差異需要時間窗**：健康機組在紊流風下瞬間差異可達約 1.16°（> 1°；-12 修正葉片同步誤差後，Live 1 s 步長下變槳速率受限的陣風中仍可達約 0.9°），PLC 判定必須用手冊的 5 s / 3 s / 瞬間三段，不可看瞬間值。
- **風向標 233 用 25 s 濾波值**：真實 tag `YwVn1/2AlgnAvg25s` 存在，本模擬只輸出 5 s 版本，濾波由 PLC 層做。
- **yaw_sensor_drift 的語意**：控制器跟隨風向標 1，所以風向標 1 讀數仍接近 0、風向標 2 顯示真實偏航誤差（−drift），疲勞 / 偏航斜流 / 尾流轉向都用真實誤差。
- **電壓驟降的副作用**：端電壓降低會啟動既有的電壓降載，嚴重度 0.3 時功率已降到約 1720 kW（健康約 2000 kW），遠早於跳機。

### 6.3 Phase 1b-b PLC 保護層（2026-10-21）

`modules/monitoring/simulator/physics/plc_protection.py`，每台機組一個 `PlcProtection`（`TurbinePhysicsModel.plc`），在每個物理步結束時判定。

**判定對象是製程值（感測器模型之前）**：感測器模型的雜訊、漂移、卡值是為 SCADA 趨勢的視覺真實度調的，幅度對保護判定太大（例：葉片角度漂移上限 ±0.8°，健康機組約兩天一次葉片同步 T2 誤跳）。感測器故障造成的跳機留給 Phase 4（-08）以有標註的方式建模。

**規則**（設定值全部來自 `TurbineSpec`；-02 起手冊 Appendix C / D 不一致時以 D 為準，§6.15）：PLC 自己的溫度（Pt100：主軸承、定子、機艙）以 10 s 時間常數濾波後判定、沒有事件延時（`CDTauPT100`；-02 前是假設的警報延時 10 s、跳機延時 5 s）；ABB 的變壓器 / 變頻器溫度沿用假設的 10 s / 5 s；皆有遲滯。延時從第一個越限樣本起算，連續越限的經過時間 ≥ 延時才成立——批次 5 s 子步下，有延時的規則（含葉片 3 s）至少要兩個連續樣本，單一樣本不算「持續」。成立後只依遲滯解除；判定窗（偏航煞車、穩定發電、只在發電時）關閉只禁止新的成立，不等於條件解除。

| 事件碼 | 訊號 | 條件 |
|---|---|---|
| A262 / T240 | 主軸承溫度 | > 85 / 95 °C |
| A264 / T244 | 定子溫度 | > 140 / 150 °C |
| A273 / T256 | 機艙空氣 / 機艙控制櫃溫度 | > 45 / 50 °C（-02 前 273 為假設的 46） |
| A417 / T444 | 變壓器鐵心溫度 | > 80 / 90 °C |
| A420 / T437 + T021 | 變頻器冷卻水溫 | > 51 / 56 °C |
| A421 / T438 + T021 | 變頻器機櫃溫度 | > 62 / 67 °C |
| A432 | 冷卻水靜水壓 | < 2.5 bar，只在發電時判定（停機時泵停，本來就低） |
| A260 / T228 | 偏航煞車液壓 | < 170 / 150 bar 持續 30 s、> 190 bar 才解除（Appendix D；-02 前 260 為 Appendix C 的 180、延時 10 / 5 s），只在煞車施加 90 s 後判定（偏航時煞車鬆開，壓力本來就低） |
| A261 | 偏航煞車油封洩漏 | BOOL |
| T233 | 風向標 1−2 差 | 25 s 濾波值差 > 15° 持續 60 s，且 60 s 平均風速 > 4.5 m/s（判定窗：已鎖存的不因風速低而解除；Appendix D；-02 前無延時、10 分鐘平均） |
| T335 / T336 / T337 | 葉片兩兩角度差 | 瞬間 > 8°、3 s > 3°、5 s > 1°；只在穩定發電 60 s 後判定（啟動大幅變槳時各葉片暫態差異可達 ~6.6°） |
| T236 | 機艙振動 max(X, Y) | > 7 mm/s 持續 10 s |

**跳機語意**：

- A 級只送 `alarm_raised` / `alarm_cleared`，不停機。
- T1 → 正常伺服停機（TurSt 9）；T2 → 緊急變槳（TurSt 7）。已排定的緊急停機不會被後到的正常停機要求降級。
- 跳機鎖存到條件解除（停機減速中葉片差異仍在、偏航中煞車鬆開都不算解除）；解除時若該碼一小時內的跳機次數 ≤ 目錄 `max_per_hour` → `trip_cleared`，機組自動重啟；超過 → 保持鎖存並送 **A039「Auto restart blocked」**、機組進 SHUTDOWN（TurSt 1），需操作員復位（事件 008，A039 解除）。復位後條件仍成立會立即再跳。（-02 前送自創的 `restart_blocked`，§6.15。）
- 物理層既有保護停機補事件碼：軟體 / 硬體超速 → 351 / 320；LVRT band 1（0.80–0.90 p.u.）→ 481 + 021、band ≥ 2（< 0.80 p.u.）→ 482 + 021；HVRT → 475 + 021；`grid_protection` / `grid_trip` 依量測電壓 < 0.81 → 482、< 0.90 → 481、> 1.08 → 475、其餘（頻率越界）→ 489（+ 021）；切出風速 → I 201（每個停機週期一次；-10 前為 600 s 時間窗去重）。這類停機的重啟仍由物理層狀態機處理，不在 PLC 層鎖存；同一停機週期只記一次，機組再次起動後重新計。跳機次數與訊號判定的跳機同一套每碼計數，超過上限時在跳機當下封鎖、送 A039（-02 前靠物理層全域的「每小時 3 次啟動」上限、沒有事件）。

**故障引擎連動**：`FaultEngine` 的嚴重度只驅動物理；`alarm_codes` 改為情境的**預期碼**（ground truth metadata，無門檻）。PLC 以情境預期的 T 碼跳機時，引擎呼叫 `mark_tripped` 把故障轉為 tripped（記 `trip_code`）；tripped 期間引擎設 `model.maintenance_lock` 阻擋重啟，取代原本每步 `cmd_emergency_stop`——**7↔3 擺盪已修**。「復位不等於修好」不變量（WMOM-20260719-01）不變：復位解除 PLC 鎖存，但維修鎖仍擋住重啟；只有維護清除（`/api/faults/clear`）會解除。維修鎖解除時引擎代技師清除 PLC 的每小時跳機計數與封鎖（`maintenance_release`，事件 008）——不論走哪條清除路徑（不帶機組的清除、情境批次、測試計畫都不會 reset 機組），否則一小時內第二次跳機留下的封鎖（A039）會讓修好的機組永遠停機。

**事件輸出**：即時路徑由 broker 每步 `drain_events()`，記為 `event_type="fault"`、`source="plc"`，payload 含 `kind / code / level / text / plcTag / eventId / value / setpoint / origin`；value / setpoint 取實際成立的那條規則（同碼多規則時，例：葉片 5 s 1° 規則、021 的機櫃溫度來源）；時間戳由 reading 的模擬時間回推（加速模式一個 tick 跑多步）。PLC 判定的停機原因為 `plc:<碼>`，broker 分類為 `Automatic fault stop: PLC event <碼>`。批次路徑（`generate_bulk`）尚未收事件（-04），結束時清空佇列，避免 Live 恢復後被當成新事件；情境排程的 tripped 轉換以 `kind="trip"` 事件記錄，供情境端點判斷「故障已跳機」。

**實測**（15 m/s、25 °C、注入後 3 h、dt 5 s；-02 後重量，每個情境用新的模擬器單獨跑）：

| 情境 | 嚴重度 1.0 事件序列（注入後分鐘） | 嚴重度 0.8 |
|---|---|---|
| bearing_wear | A262 7.8 → T240 10.1 | A262 27.9，3 h 未跳機 |
| stator_winding_degradation | A265 8.2 → A264 8.5 → T245 9.9（-08-a 起第二支 Pt100 先到） | 3 h 無事件 |
| transformer_overheat | A417 33.3 → T444 49.6 | A417 92.8，3 h 未跳機 |
| converter_cooling_fault | A420 2.7 → T021 + T437 3.4 | A420 6.4 → T021 + T437 13.2 |
| nacelle_cooling_failure | T256 61.3（無先行警報） | 3 h 無事件 |
| hydraulic_leak | A261 0.2 → T228 + A260 2.8（兩者都延時 30 s，同一步） | 同左 |
| yaw_sensor_drift | T233 1.4（延時 60 s） | T233 2.1 |
| pitch_imbalance | T335 + T336 0.2 | T335 0.6 |
| blade_icing | T236 0.2 | T236 0.2 |
| grid_voltage_sag | T481 + T021 0.8（物理層 LVRT） | 同左 |
| generator_overspeed | T351 + T320 0.2（物理層超速） | T351 0.2 |

-02 前的差異：hydraulic_leak 的 T228 2.3 分（延時 5 s、A260 在 180 bar 時更早）；yaw_sensor_drift 0.7 / 1.8 分（無延時，0.8 時漂移是線性 14.4°＋偏差）；溫度事件 ±0.1 分內（濾波約落後 10 s，與原本的延時相近）。

健康 3 機風場（自動風況，含紊流與偏航）2 h 內沒有任何訊號判定的事件（`test_plc_integration.py`）；健康機組既有 111 tag 輸出與 -03-a 之前逐位元相同（-12 之後葉片角度 3 個與葉片揮舞彎矩 / DEL / 損傷除外）。2 h 不夠：長時間下健康機組仍會偶發葉片同步 T2 336，-12 修正並加上 12 h × 3 個起點的守門測試（§6.10）。

**已知限制**：

1. **物理層保護停機的停機模式未依手冊等級**：軟體超速 351 在手冊是 T1，但物理層仍走緊急停機（切出風速已於 -10 改為正常停機）。
2. ~~**切出風速用瞬間風速**~~ → WMOM-20261021-10 已解（§6.5）。
3. **預期碼可能不出現**：低負載或嚴重度不足時情境不會跳機（上表嚴重度 0.8 的 4 個情境），ground truth（-04）必須允許「預期碼未出現」。
4. **事件順序由物理決定**：converter_cooling_fault 的 T021 與 T437 同一步送出；hydraulic_leak 壓力在偏航後的判定窗內一次跌破兩個設定值時，T228 與 A260 同一步送出（-02 起兩者都延時 30 s；之前 T228 延時 5 s 先於 A260 的 10 s）。
5. **`faults.py` 的 `run_test_plan` 不記錄 trip 事件**（不是情境 session），只有 `/api/config` 情境排程會記。
6. **每小時計數在條件解除時判定**：手冊 §8.3 寫「restarts within the last hour」，未說明是跳機當下或重啟當下計數；訊號判定的跳機在解除（要重啟）時看最近一小時的跳機次數，物理層保護停機（條件由物理層處理）在跳機當下判定（-02）。
7. **實測時點有約 ±1 分鐘的差異**：上表是同一程序依序跑 22 個情境的結果；前面情境的跳機時點會透過程序層級的共享狀態影響後面情境（例：converter_cooling_fault 0.8 單獨跑為 13.2 分、在序列中曾量到 12.8 分），屬量測條件差異，不是物理改變。

### 6.4 Phase 1b-c UTC 時間戳（2026-10-21）

**慣例**（`modules/monitoring/simulator/time_utils.py`）：

- 內部一律 tz-aware UTC（`utc_now()`）；模擬時間（Live、`generate_bulk`）、事件、session、工單、OPC 即時讀值都是 UTC。
- 落庫與 API 的字串格式固定為 `YYYY-MM-DDTHH:MM:SS.ffffff+00:00`（`iso_utc`）。SQLite 以字串字典序比較時間，長度與後綴一致才保證字典序＝時間序；不用 `Z`（`Z` 的字元碼大於 `.` 與數字，同一秒內順序會顛倒）。Pydantic 回應中的 `datetime` 欄位（`TurbineReading.timestamp`、`FarmStatus.timestamp`）序列化為 `...Z`，兩者都是 RFC 3339 UTC。
- 外部傳入的時間字串（前端 `toISOString()` 的 `Z`、任意時區後綴）在 storage 邊界正規化；**naive 字串視為伺服器本地時間**——這是本次之前所有資料與舊 API 呼叫端的語意。
- **既有 DB**：開檔時依 `PRAGMA user_version` 一次性把 naive 本地時間轉成 UTC（10 個時間戳欄位 + 情境 `config.sim_start/sim_end`；`farms.db` 的 `created_at` / `last_active_at` 同樣處理）。只轉沒有時區後綴的值；整秒部分用 SQLite `'utc'` 修飾詞換算、小數秒原樣保留（與 Python 換算的 `sim_start` 逐微秒一致，情境時間窗邊界的事件不會被排除）；依 rowid 區段每 2 萬列一批 commit（WAL 峰值約一批大小，中斷後下次開檔接著轉），全部完成才更新版本號。換算用本機時區，啟動 log 會印出所用時區；`tools/vacuum_db.py` 以 `migrate_timestamps=False` 開檔，先清理不轉換。
- **日夜 / 季節循環**（`wind_model.py`）：-03-c 時仍以伺服器本地時間計；**WMOM-20261021-11 起改用風場時區**（§6.6）。

**順帶修好的既有 bug**：

- 前端歷史查詢以 `toISOString()`（UTC）送範圍、DB 存本地時間，伺服器在 UTC+8 時查詢窗整整偏 8 小時；兩邊統一成 UTC 後正確。
- `/api/turbines/farm-trend` 的 12 h / 1 d 範圍用 `strftime('%%s', ...)` 分桶，參數化查詢不經 `%` 格式化，SQLite 收到字面 `%%s` 回傳 `'%s'`，全部資料落進同一桶、只回 1 點；改為 `'%s'`。
- URL query 裡未編碼的 `+00:00` 會被解成空格，`parse_iso` 把結尾的 `␣HH:MM` 視為 `+HH:MM`。

**已知限制**：

1. ~~日夜循環依「伺服器本地時區」而非「風場所在時區」~~ → WMOM-20261021-11 已解（§6.6）。
2. 資料包（-05）的對外格式可再選 `Z` 後綴（合約 v0 的範例用 `Z`）；兩者等價，匯出時統一即可。
3. **舊 DB 換算假設「在寫入它的同一時區開啟」**：例如把 Windows（台北）寫的 DB 掛進 UTC 的 Docker 容器啟動，會整整偏 8 小時且不報錯（啟動 log 會印出換算用的時區）。有 DST 的時區在空窗 / 重複的那一小時可能差 1 小時（台灣無 DST）。
4. **轉換只跑一次**：`user_version` 升為 1 後若退回舊版執行、再升回新版，退回期間寫入的 naive 列不會再被轉換。
5. **legacy 獨立腳本不在範圍**：`modules/monitoring/main.py`、`dashboard.py`、`scada_system.py`、`turbine_model.py` 是 digiWT 的獨立腳本，不寫入 storage、不被 server 匯入，仍用 naive 本地時間。

### 6.5 切出風速改用平均風速（WMOM-20261021-10，2026-10-21）

**規則**（手冊事件 201，設定值在 `TurbineSpec`）：10 分鐘平均 > 25 m/s 或 5 秒平均 > 35 m/s → **正常停機**（原本是瞬間風速 > 25 m/s 就緊急停機）；10 分鐘平均 < 20 m/s 才可重啟（手冊處置：Wait until V wind,10 < 20.0 m/s）。平均以時間加權的移動平均計算，**累積滿一個窗長才判定**：開機 / reset 後的前 10 分鐘沒有「10 分鐘平均」，由 5 秒平均保護——否則第一個陣風樣本就等於平均值，平均風速介於 20-25 m/s 時機組會永遠停在暴風停機。啟動條件也不再看瞬間風速上限。

**氣動模型**：`PowerCurveModel` 原本在瞬間風速 > 25 m/s 時直接回傳 0（瞬間功率歸零）。切出是控制器的決定，氣動模型對機組正在面對的任何風速都照算——運轉中 25-35 m/s 的陣風維持額定轉速 22.5 rpm、額定功率、槳距約 30°（實測，無超速）。

**實測**（1 機、2 h、dt 1 s，風況 override + 指定 TI）：

| 平均風速 / TI | 發電時間比例（改前 → 改後） | 切出停機次數 | I201 事件數 |
|---|---|---|---|
| 16 m/s / 0.18 | 31.5 % → **99.8 %** | 1 → 0 | 7 → 0 |
| 22 m/s / 0.15 | 3.4 % → 5.7 % | 1 → 1 | 12 → 1 |
| 24 m/s / 0.12 | 1.7 % → 5.6 % | 3 → 1 | 12 → 1 |
| 27 m/s / 0.12 | 0.2 % → 1.9 % | 1 → 1 | 12 → 1 |

健康機組既有 111 tag 輸出逐位元不變（測試工況風速 < 25 m/s）；`data_quality_analysis.py` 20 / 0。

**已知限制**：

1. **高風速時陣風模型偏強**：`wind_field.py` 的自然陣風事件頻率與振幅都隨平均風速放大（22 m/s 時約每 3 分鐘一次、振幅最大 4 × V / 12 ≈ 7 m/s），疊加農場與單機兩層紊流，22-24 m/s、TI 0.12-0.15 時 5 秒平均約 7 分鐘內就會越過 35 m/s 而切出，之後因 10 分鐘平均 > 20 m/s 一直不重啟。切出規則本身照手冊；若 -08 要做「暴風前後」情境，需再檢視陣風模型的高風速校準。
2. 判定用的是自由流有效風速（含紊流、陣風事件），不是機艙風速計讀值（`WMET_WSpeedRaw` 有轉子感應修正，運轉中約低 4-16 %）；真實 PLC 一般依機艙風速計判定。
3. 開機後前 10 分鐘只有 5 秒平均（35 m/s）保護：冷啟動就在暴風中（10 分鐘平均 > 25、5 秒平均 < 35）時，機組最多會發電 10 分鐘才切出。`reset()` / `update_spec()` **不清除**平均值與暴風停機旗標（風速歷史是環境量；否則暴風停機中的機組被維護 reset 後會立刻在暴風中重啟），只有窗長設定改變才重建該平均。
4. **批次模式（子步 dt 5 s）的陣風規則比 Live（dt 1 s）敏感**：5 秒平均在 dt = 5 s 時就是單一樣本值，等於用 5 秒取樣的瞬間值判定；同一風況下批次資料的陣風切出會略多於 Live。移動平均本身對任何 dt 都恰好涵蓋最近一個窗長（部分剔除最舊樣本）。
5. 判定風速含單機個體差（`wind_sensor_scale` ±2.5 %）與故障的 `wind_scale`（偏航誤差等的 cos 損失）：偏航誤差大的機組以較低的有效風速判定、切出較晚。
6. 預設功率曲線表拿掉了「25.5 / 26 m/s → 0 kW」兩點（切出改由控制器決定，曲線末端夾在 2000 kW）。查表只用在起動同步爬升與 Cp 模型無輸出時的 fallback（發電中走 Cp 模型）；自訂功率曲線若仍帶高風速歸零點，起動中遇到陣風時爬升功率會歸零（使用者自己的曲線，照算）。
7. **前端待跟進**：`TurbineDetail.tsx` 的不發電原因仍以「瞬間風速 > 25 m/s」顯示「切出風速」——現在風速 25-35 m/s 時機組可能仍在發電，或 10 分鐘平均 > 20 m/s 時以較低風速停著；應改看停機原因（`cut_out`）或 I201 事件。不影響資料源，列入 -08 或前端整理時處理。

**Code review（code-reviewer subagent）修正**：移動平均窗精確化（原本最舊樣本整筆丟、dt 不整除窗長時窗長偏短）；I201 由 600 s 時間窗去重改為「每個停機週期一次」（時間窗會吞掉 600 s 內真實的第二次暴風停機）；`reset()` / `update_spec()` 不再清空平均值。每項都有 mutation 驗證的測試（`tests/physics/test_envelope.py` `TestCutOutBehavior` 13 項 + 移動平均 / 功率曲線表、`test_plc_protection.py`）。

### 6.6 風場時區（WMOM-20261021-11，2026-10-21）

- **設定**：`FarmConfig.timezone`（IANA 名稱，`farms.db` 新欄，既有風場補預設值 `Asia/Taipei`——Z72 參考風場在台灣海峽）；`POST /api/farms`、`PATCH /api/farms/{id}` 可設，無效名稱回 400。
- **模擬器**：broker 以目前風場的時區建立 `WindFarmSimulator(site_timezone=...)`；`wind_model.py` 各 getter 以 `to_site_naive(ts, site_tz)` 換成風場當地時刻再取 hour / month。naive 輸入視為已是風場牆鐘時間（舊呼叫端與測試）。
- **可重現**：同一組 UTC 時刻在 UTC、Asia/Taipei、America/New_York 的伺服器時區下得到逐位元相同的風況；模擬器全部 SCADA tag 輸出在 UTC 與 Asia/Taipei 下逐位元相同（`test_farm_timezone.py`）。資料包（-05）可在任何機器上重產。
- **情境 metadata**：情境 session 的 `config.site_timezone` 記下所用時區，-05 manifest 可直接取用。
- **行為改變**：伺服器本地時區不是 Asia/Taipei 的機器（例如 UTC 的 CI、Docker），日夜相位比改動前移動（UTC 機器上 +8 小時）；台北時區的開發機不變。`data_quality_analysis.py` 仍 20 / 0。
- **其他 session**：Live session（broker 啟動 / 切換風場）同樣記 `config.site_timezone`，以風場時區建立模擬器；`clone` 保留來源風場的時區。（原本的 `POST /api/farms/{id}/datasets/generate` 已於 -05 移除，見 §6.8。）
- **防呆**：`localtime`（＝伺服器時區，失去可重現性）、非字串、空字串一律拒絕；`farms.db` 存的名稱在本機無效時（手改 DB、換到缺 tz 資料的機器），broker 印警告並退回預設 `Asia/Taipei`，不讓模擬起不來。
- **已知限制**：
  1. **改時區要重啟模擬才生效**：`PATCH` 只改設定；目前執行中的模擬器沿用建立時的時區，`activate` / 重啟模擬後才換。
  2. **時區固定的是「相位」，不是「內容」**：Live 與資料集產生都以 `utc_now()` 當起點，內容仍隨執行時刻不同；-05 資料包要可重產還需固定起始時刻（情境模式已有 `sim_start`）。
  3. 有日光節約時間的時區，日夜循環依當地民用時間（換時日一天 23 / 25 小時，循環跟著跳一小時）——與真實風場的 SCADA 本地時間一致，Z72 預設的台灣沒有 DST。
  4. Windows 與精簡容器沒有系統 tz 資料庫：`requirements.txt` 已加 `tzdata`（純 Python 套件；workflow 模組的 `ZoneInfo("Asia/Taipei")` 也需要）。

### 6.7 Phase 2 標準答案 + 情境事件（WMOM-20261021-04，2026-10-21）

**故障情境 metadata**（`FaultScenario` 新欄位，只寫進標準答案）：`component`、`root_cause_zh/en`、`category`、`origin`、`difficulty`、`key_signals`、`expected_actions_zh/en`、`simulation_notes_zh/en`。根因與處置只寫真實世界的答案；處置中出自手冊 Appendix C 的標「（手冊）」（每個情境至少一條），其餘為工程實務。模擬與真實不同之處寫在 `simulation_notes`（例：超速在 351 跳機後故障凍結、不會出現 320；結冰情境的環境溫度不耦合；電網下陷只作用在被注入的機組）。預期警報序列沿用 `alarm_codes`（A 在前、T 在後，測試會擋）；手冊條目由 Z72 警報目錄組出（`simulator/ground_truth.py::manual_refs`，含頁碼、原因、處置提示），Z72 手冊只寫「See [ABB]」者標 `see_abb`，case 的 `manual_coverage` 為 `z72_manual` / `abb_manual` / `mixed`。

| 情境 | component | category / origin | 難度 | 手冊 |
|---|---|---|---|---|
| bearing_wear | main_bearing | real_fault / internal | easy | z72_manual |
| generator_overspeed | pitch_control_system | real_fault / internal | easy | z72_manual |
| converter_cooling_fault | converter_cooling_system | real_fault / internal | medium | abb_manual |
| transformer_overheat | transformer | real_fault / internal | easy | abb_manual |
| pitch_imbalance | pitch_system_blade_1 | real_fault / internal | hard | z72_manual |
| yaw_sensor_drift | wind_vane_1 | **sensor_fault** / internal | hard | z72_manual |
| stator_winding_degradation | generator_stator | real_fault / internal | medium | z72_manual |
| hydraulic_leak | yaw_brake_hydraulics | real_fault / internal | medium | z72_manual |
| blade_icing | blades | real_fault / **environmental** | medium | z72_manual |
| grid_voltage_sag | grid_connection | real_fault / **external_grid** | medium | abb_manual |
| nacelle_cooling_failure | nacelle_ventilation | real_fault / internal | hard | z72_manual |

`key_signals` 依探測選定（高負載滿嚴重度 vs 健康機組的偏離），並有物理測試守住（`tests/physics/test_fault_threshold_reach.py`：每個 key signal 都要偏離超過健康的 3σ 與 2 %；超速 / 電網用還在發電的嚴重度 0.3 / 0.5）。探測中值得一提的：**風向標漂移的訊號在風向標 2**——偏航依漂移的風向標 1 追風，風向標 1 讀值看似正常，真實偏航誤差出現在風向標 2。

**批次事件**：`generate_bulk(on_events=...)` 每個物理子步收集 PLC 事件（時刻依機組 `_sim_time` 回推，與 Live 的 `_plc_event_timestamp` 同換算）與 `WTUR_TurSt` 轉換（含停機原因），每個輸出步回呼一次；批次開始前先清掉 Live 留在佇列的事件。收集只讀狀態：同起點、同排程的兩次生成讀值逐位元相同（有測試）。寫入走 `DataBroker.record_bulk_events`，格式與 Live 相同（`_plc_event_fields` / `_state_transition_fields` 共用），一次 commit。實測 14 機、6 h、stress_test 前 8 個故障：62 筆事件（狀態轉換 50、警報 5、跳機 4…），生成時間與不收事件相同（77.6 s vs 81.6 s，雜訊內）。

**事件 session 隔離**（DEC-20261021-02）：
- `history_events.session_id`（舊 DB 自動補欄，舊列 NULL）。命名情境的事件記在情境 session、不帶 name 的批次與 Live 事件記在 Live session（`DataBroker.record_event` 預設）。
- 情境 config 帶 `events_session_isolated: true` → 調閱 / 摘要依 session 查（`events_by_time_window` / `eventsByTimeWindow` = false，前端的「可能混入重疊情境」提醒自然消失）；舊情境退回時間窗。
- Live 端（不指定 session）的查詢排除情境 session 的事件：情境以模擬時間寫入，不排除會擠進 Live 時間軸。
- 摘要的 `faultEvents` 在 session 模式只數 PLC 的警報成立與跳機；前端趨勢圖也只標這些與情境標記（`frontend/utils/scenarioEvents.ts`），解除、I201、停機狀態轉換不畫成「故障」線。
- 掛載的 FAULT 重算只撈 `source="scenario"` 的注入 / 跳機標記（PLC 事件可能數千筆，不篩會被 LIMIT 擠掉）。
- 刪除情境一併刪事件與標準答案；情境的 raw 讀值不受 3 天 retention 清除（凍結資料集）。
- 同一時刻的事件依寫入順序排（跳機在它造成的停機狀態之前）。

**標準答案**：`scenario_ground_truth` 表（一情境一列 JSON），`GET /api/scenarios/{id}/ground-truth`（主管）。每次故障注入一個 case：`onset_ts`（注入時刻）、`first_alarm_ts` / `first_alarm_code`（該故障**預期碼**第一次成立或跳機）、`trip_ts` / `trip_code`、`observed_alarm_codes`（實際出現的預期碼）、`other_observed_codes`（同機組其他 A / T 碼）、`injection`、`final_severity`、`superseded`（同機組同情境再注入時舊 case 標記）、`pre_existing`，加上上述答案欄位。

頂層欄位：
- `healthy_turbines`：未注入故障的機組。
- `unattributed_events`：沒有任何 case 以預期碼解釋的警報 / 跳機 / 資訊事件，例如切出風速 I201、故障連帶的其他碼（健康機組的偶發葉片同步跳機已於 -12 修正，§6.10）。評分端因此知道 RAG 面對的每一筆事件有沒有答案。

命名情境一律先清掉 Live 殘留的故障。結束時若仍有沒有注入紀錄的故障，列成 `pre_existing` case（onset 未知），不靜默略過。stress_test 6 h 實例：hydraulic_leak `260 → 261 → 228`（13:02 首警、14:03 跳機）；yaw_sensor_drift / pitch_imbalance / blade_icing 首次警報＝跳機（§6.1 限制 2）；stator / nacelle 6 h 內未達警報。

**盲測分離**：
- 根因只在標準答案表，端點 `GET /api/scenarios/{id}/ground-truth` 永遠需要主管（`require_roles`，不受 `WMOM_AUTH_ENFORCE` 過渡開關影響）。
- `storage.is_observable_event` 以**白名單**定義可觀測事件：PLC 事件與運轉狀態轉換；情境 / 測試計畫標記、`fault_lifecycle`、Live 的 FaultEngine 跳機 / 解除、操作 / 設定紀錄一律不算，新來源預設不可觀測。
- 情境調閱端點加 `observable_only=true` 給盲測消費端；整合測試檢查情境的可觀測事件不含任何故障 ID。

**已知限制**：

1. **情境 config 的 `fault_schedule` 寫明注入的故障**：`GET /api/scenarios/{id}`（任何登入者）、摘要的 `faultsInjected` 與前端情境頁都看得到——那是出題者 / 操作端的資訊；-05 資料包的 manifest 不得帶出 `fault_schedule`，事件必須以 `is_observable_event` 過濾。
2. **Live 路徑不是盲測資料源**：沒有標準答案，`Automatic fault trip` / `fault_lifecycle` 事件帶故障 ID（操作端展示用）。資料源一律走批次情境。
3. 測試計畫（`/api/faults/test-plans/{id}/run`）會記事件與跳機標記，但寫進 Live session、不產生標準答案。
4. 健康機組只列在 `healthy_turbines`，沒有 `category: healthy` 的 case；`nuisance` / 健康負樣本 case 留給 -08（事件已列在 `unattributed_events`）。
5. 歸屬只靠事件碼：`first_alarm_ts` 只看該故障的預期碼；兩個故障共用的碼（例：021）兩邊都記；同機組多故障時，物理耦合造成的碼可能被另一個 case 認領（例：機艙冷卻失效讓軸承升溫，262 會算進同機組 bearing_wear 的首警）。
6. 本變更之前生成的情境沒有標準答案（404），事件也沒有 session（退回時間窗）。
7. ~~`routers/farms.py::generate_dataset` 仍不記事件與標準答案~~ → -05 移除（它從未產出資料，§6.8）。
8. 調閱端點仍有 1000 筆事件上限（最新在前）：很長的情境在單機歷史頁可能看不到最早的事件（-05 匯出直接讀表，不受影響）。
9. ISSUES 原描述 (5)「T1/T2 不再一律稱為 alarm threshold reached」已於 -03-b 達成：PLC 事件 title 為 `Trip: T_240 …`、payload 帶 `code` / `level`；本次未改格式。
10. 標準答案欄位比 §5.1 的 v0 範例多（`root_cause_en`、`origin`、`observed_alarm_codes`、`other_observed_codes`、`key_signals`、`manual_coverage`、`injection`、`simulation_notes`、`unattributed_events`…），合約 v1 於 -09 定稿。
11. **留給 -05 的可重現性與匯出事項**（-05 處理結果見 §6.8；seed / `TurbineSpec` / 模型狀態重置仍未做）：
    - 情境 config / 標準答案沒記 seed、`TurbineSpec`、模擬器版本。
    - 批次沿用 Live 模擬器的模型狀態（未重置），「seed + manifest 可重現」目前不成立。
    - `generated_at` 是 wall-clock。
    - 事件的 `kind` 要對應到合約的 `event_type`（`trip_cleared`、`restart_blocked`、`info` 合約尚未定義）。
    - 時間戳後綴 `+00:00` vs 合約範例 `Z`。
    - 狀態事件的停機原因是模擬器內部詞彙（例：`maintenance_lock`、`overspeed_software`），匯出時可正規化。
12. 不帶 name 的批次與測試計畫把事件寫進 Live session（時間戳從生成當下往未來展開，與它們的讀值同一時間軸，沿用舊行為）。

### 6.8 Phase 3a 情境資料包匯出（WMOM-20261021-05，2026-10-21）

**格式**見 §5.1（v0.1）。匯出器 `modules/monitoring/server/scenario_pack.py::export_scenario_pack`；交付管道兩條：

- **端點**：`GET /api/scenarios/{id}/pack`（盲測版，任何登入者）、`GET /api/scenarios/{id}/pack/full`（評分端版，含 `ground_truth.json`，永遠需主管）。回 zip（Parquet 直接存、JSON DEFLATE），匯出在 thread 裡做；暫存目錄在 `{tmp}/wmom-packs/`，回應送出後刪除，送出前伺服器中斷留下的目錄由下一次下載清掉（超過 1 小時）。上限：同時 2 個匯出（超過回 429）、raw 200 萬筆（超過回 413，改用 CLI）。
- **CLI**：`tools/export_scenario_pack.py <db> [scenario_id] --out <dir> [--ground-truth] [--zip] [--list]`，開 DB 不做時間戳轉換（`migrate_timestamps=False`）。

**真實 / 自創 tag**：`tools/build_z72_plc_tags.py` 從 xlsx 全部 sheet 擷取 1811 個 `Z72PLC__*` 名稱 → `shared/data/z72_plc_tags.json`，`shared/plc_tags.py::is_real_plc_tag` 判定。模擬器 116 個 tag 中 45 個真實、71 個自創；資料包排除 16 個模擬器內部量（DEC-20261021-03），留 100 欄（45 真實 + 55 自創，`source` 標明）。`WMET_WSpeedNac`（模擬的是自由流風速，真實 Z72 是機艙風速計讀值；風速計近似在 `WSpeedRaw`）與 `WMET_WDirAbs`（風場真實風向）在 tag 字典帶 `note`。

**盲測**：
- manifest 不帶情境名稱、故障排程、注入數；`wind_profile` 只輸出已知的 profile 名（出題者自訂的文字不輸出）；`pack_id` 只用 session id。
- 事件以 `is_observable_event` 白名單過濾後轉成合約格式，不帶模擬器的製程值 / 設定值；停機原因正規化（`maintenance_lock` 等內部詞彙不輸出）。
- manifest 的 `sim_start` 是第一筆讀值；標準答案的 `sim_start` 可能早一步（含 offset 0 的注入時刻）——manifest 刻意不跟，否則透露「第一筆讀值前發生了事」。
- 盲測版重匯出到同一目錄時刪掉舊的答案檔；Parquet 不帶 metadata。
- **盲測版以檔案交給受測端**，受測端不該有本系統帳號：任何登入者都看得到情境清單（含出題者的情境名稱）與 `fault_schedule`。

**串流與一致性**：
- raw 依 id 順序分批讀（批次生成的寫入順序就是時間順序；先以 `LAG` 視窗查詢確認，不是才退回 `ORDER BY timestamp`，避免 SQLite 先排序整個 session），Parquet 每 5 萬列一個 row group。
- 10 分鐘統計逐窗計算，不保留 raw；取樣週期由資料推得（最常見的相鄰間隔），設定的 `time_step` 只當後備。
- 先寫到同層暫存目錄，全部成功才搬進輸出目錄、manifest 最後搬：失敗不留半套，舊資料包原封不動。
- 文字檔固定 LF，Windows 與 Linux 匯出的 sha256 相同。
- 盲測版與評分端版的資料檔 sha256 相同（只差答案檔與 manifest）。

**code review 修正**（同 PR）：events 每行欄位相同（polars 等逐行推斷 schema 不會掉 `alarm_code`）；raw 改 id 順序串流（原 `ORDER BY timestamp` 在 43 萬筆時第一批要 7.7 s）；統計加 `window_end`、`is_partial` 與 manifest 的 `stats_convention`；暫存目錄清理、匯出上限、原子寫入、LF、圓統計、排除內部量、`wind_profile` 白名單、`events_dropped` 計數、`exporter_version`。

**實測**：43.6 萬筆 raw 的情境（DB 1.8 GB）：id 順序檢查 1.3 s，之後第一批立即可讀（原 `ORDER BY timestamp` 要 7.7 s 才出第一批）；整包匯出 32 s、峰值記憶體 220 MB，raw Parquet 18.8 MB、統計 0.36 MB。14 機 × 6 h（3 萬筆）約 2–4 s，生成同一情境要 98 s。

**已知限制**：

1. **不可重現**：manifest 的 `reproducibility.seed` 為 null——批次沿用 Live 模擬器的模型狀態、起點是 wall-clock、情境沒記 seed / `TurbineSpec`。同一份資料包可重複分發，但無法由 manifest 重產；-08 擴充難度時一併處理。
2. **10 分鐘統計來自 10 s（或設定的）取樣**：真實 PLC 的 10 分鐘 std 由高頻取樣算出，這裡樣本少、std 偏低（Phase 5 parking lot 的「10-min std 合理化」）。
3. **統計表在記憶體組**：每窗每 tag 16 bytes，14 機 × 30 天（1 分鐘步長也一樣，只與窗數有關）約 100 MB；年長度情境要分段匯出（未做）。HTTP 上限擋在 200 萬筆 raw 內。
4. 合約版本仍是 `0.1`（與標準答案同一個 `CONTRACT_VERSION`）；-09 定稿 v1。`event_type` 的 `operator`（操作員動作）尚未產生——情境裡沒有操作員。
5. 自創 tag 仍有 55 個（振動頻帶 / CMS 特徵、負載與 DEL、無功 / 視在功率、冷卻液位…）：受測端應以 `source` 區分，回答時不能假設真實 Z72 有這些 tag。
6. 欄名含方括號（`Z72PLC__UI_Mbus_Contact[2]`），SQL 引擎要加引號。

### 6.9 Phase 3d 學生專題 starter kit（WMOM-20261021-09，2026-10-21）

**合約 v1**：[`docs/integration/rag_assistant_data_contract_v1.md`](../integration/rag_assistant_data_contract_v1.md)。資料包、事件、標準答案沿用 -05 的格式（`CONTRACT_VERSION` 0.1 → 1.0；-04 起存的答案匯出時一併標成 1.0）。新增兩部分：
- **受測端輸出 `predictions.jsonl`**：每次判斷一行，帶 `pack_id` / `turbine_id` / `ts`（模擬時間，只能用 ts 以前的資料）/ `category` / `component` / `manual_refs`，`root_cause` 與 `actions` 不自動評分。
- **評分**（劉老師確認，DEC-20261021-04）：
  - 故障診斷依機組與時間對到 case，對不到算誤報（以次數計，與輸出頻率無關）。
  - 每個 case 以最後一次判斷評元件、元件群組、類別與手冊引用（事件碼 hit@1 / hit@3 / MRR@10）。
  - 延遲與早期預警以「最後一段連續正確」的起點計，中途猜錯的元件記為誤診。
  - 各項指標分列，不合成總分。

**元件詞彙**：11 個元件、8 個群組（`examples/rag_starter_kit/vocabulary.json`）；測試守住故障庫的每個元件 / 類別都在詞彙內——-08 加新故障要同步加詞彙（次版本）。

**starter kit**：`examples/rag_starter_kit/`
- **範例資料包**：3 個盲測版，答案另放 `answers/`。

  | 資料包 | 機組 / 長度 / 風況 | 故障 |
  |---|---|---|
  | 01 | 3 機 / 4 h / 額定 | 主軸承磨耗（onset 後約 40 分鐘警報） |
  | 02 | 4 機 / 6 h / 強風 | 偏航煞車液壓洩漏、變頻器冷卻（See [ABB]） |
  | 03 | 5 機 / 6 h / 陣風 | 風向標漂移（sensor_fault）、葉片 1 變槳不平衡；238 筆狀態轉換當干擾 |

  共約 4 MB，故障都是「慢慢變嚴重」，key signal 在警報前就偏離同風場其他機組（已檢查：主軸承溫度、偏航煞車壓力、變頻器水溫都在警報前的 10 分鐘窗就看得出來）。
- **程式**：
  - `pack_reader.py`（pandas；核對 sha256、`raw_until` / `events_until` 只看當下以前）
  - `baseline_assistant.py`（看到警報才用關鍵字猜元件）
  - `score.py`（只用標準函式庫）
- **基準成績**：偵測 100 %、元件 80 %、群組 100 %、類別 80 %、手冊 hit@1 100 %、早期預警 0、誤診 1、誤報 0。基準刻意示範「容易的部分」，把早期預警、感測器故障、元件定位、警報前的檢索留給學生。

**重產**：`tools/build_rag_starter_kit.py` 以固定起點、風況、排程從全新模擬器生成。
- **時鐘要釘兩處**：`generate_bulk` 用 `simulator.engine.utc_now` 當起點；`wind_model.set_profile` / `set_override` 會從「現在」的自動風況平滑過渡，用的是 `wind_model.utc_now`。實作時只釘前者，兩次產生的資料就不同（第一筆讀值就分歧）。兩處都釘住後，兩個獨立行程產生的資料檔 sha256 相同。
- **匯出器**：`export_scenario_pack` 加 `pack_id` 參數；`export_ground_truth` 把答案寫在資料包之外。

**code review**（Needs revision → 全修）：
- **早期預警可被狂猜換到**：原以「第一筆正確」計，實測 5/5。改為「最後一段連續正確」，並加誤診計數。
- **superseded / pre_existing 窗不對**：superseded 改為併進取代它的 case；pre_existing 不評時效。
- **評分程式碰到壞行會中斷**：時間溢位、極深巢狀 JSON、UTF-16 檔、BOM 都改為列出原因、照常評分。
- **其他**：
  - 答案目錄可直接給評分端版資料包。
  - 誤報改以次數計，延遲報樣本數，MRR 只看前 10 個。
  - 新增 `stats_until`。
  - 合約標籤只轉換 0.1。
  - `pack_id` 改為嚴格驗證。
  - `.gitattributes` 防 Windows 換行轉換。
  - 每個範例用獨立 DB；`--only` 驗證 id。
  - 文件與型別同步修正。

**已知限制**：
1. **手冊引用容易拿高分**：引用已出現的警報碼就對了。評分只看最後一次判斷的引用，無法區分「警報前就查對」與「警報後照抄」；警報前的檢索品質要靠早期預警與人工評 `root_cause`。
2. **類別與元件一對一**：v1 故障庫只有 `wind_vane_1` 是感測器故障，類別正確率暫時等於元件正確率（-08 擴充）。
3. 範例只有 5 個 case、都會出警報；沒有 nuisance / healthy case（-08），`nuisance` 預測不評分。（-08-b 起有 nuisance case 與健康負樣本，`nuisance` 預測評辨識率與準確率，§6.16）
4. **離線評分無法檢查時間因果**：助手有沒有偷看 `ts` 之後的資料只能自律；-06 WS 回放上線後才由收到資料的時刻保證。
5. 範例資料隨物理模型改變：物理改動後若要讓範例跟上，要重跑產生工具並 commit（測試只檢查格式與 tag 字典一致，不檢查數值）。

### 6.10 健康機組葉片同步（WMOM-20261021-12，2026-10-22）

**現象**：健康 3 機風場、時鐘釘在 2026-04-10T09:00Z、`generate_bulk(time_step=60)`（5 s 物理子步）跑 12 h，WT002 在 16:04:45 跳 T2 336（葉片 1–3 差異 5 s > 1°，訊號值 1.01°）。-03-b 的守門測試只跑 2 h，抓不到。

**排查**：
1. **延時判定**：不是「單一樣本就成立」。-03-b 起延時從第一個越限樣本起算，5 s 子步要兩個連續樣本。重現中 WT002 葉片 1–3 有 77 個樣本 > 1°，只有一次連續兩個，就是那次跳機。
2. **手冊語意**：335–337 是 T2（每小時最多 3 次），原因是葉片間同步喪失（瞬間 > 8°、3 s > 3°、5 s > 1°），處置是檢查變槳驅動、軸承、潤滑、I2t。手冊把「5 s > 1°」當成故障，所以健康機組的同步誤差應遠小於 1°。
3. **根因在物理**：
   - 各葉片零點校正誤差 σ 0.12°（WT002 葉片 1 與 3 相差 0.62°）。
   - 伺服死區 0.18°、編碼器雜訊 0.08°，追蹤誤差在死區內隨機漂移。
   - 兩者相加，尾端碰到 1°。

**定案**（DEC-20261022-01）：修物理，PLC 規則不動，也不把它當成真實的 nuisance。

**修正**（`turbine_physics.py`）：

| 參數 | 修正前 | 修正後 |
|---|---|---|
| 葉片零點校正誤差 σ | 0.12° | 0.06° |
| 起動 / 緊急順槳以外的伺服死區 / 雜訊 | 0.18° / 0.08° | 0.10° / 0.04° |
| 起動（5）/ 緊急順槳（7）的死區 / 雜訊 | 0.18° / 0.18° | 不變 |

只改 σ、不改抽樣次數，主 `_rng` 序列不位移。健康輸出只有葉片角度 3 個 tag 與葉片揮舞彎矩及其 DEL / 損傷改變，其餘 110 個 tag 逐位元不變；data quality 20/0。

**結果**：

| 量測 | 修正前 | 修正後 |
|---|---|---|
| 14 機 × 12 h，葉片差異「連續 5 s」最大值（批次 5 s） | 1.02° | 0.49° |
| 同上（Live 1 s） | 0.84° | 0.43° |
| 瞬間峰值（Live 1 s、TI 12%，變槳速率受限時） | 1.26° | 0.86° |
| 原始重現點 12 h 的訊號判定事件 | T2 336 一次 | 無 |

另外驗證：14 機 12 h（2026-10-01 起）、Live 1 s 步長 4 h（原始重現點）都沒有訊號判定事件。

**對故障情境的影響**：`pitch_imbalance`（15 m/s、25 °C、固定嚴重度）的跳機時點：
- 嚴重度 1.0 / 0.8：不變（0.2 / 0.6 分鐘，§6.3 的表仍成立）。
- 嚴重度 0.7：7.2 → 19.6 分鐘。健康的追蹤誤差不再幫忙把差異推過 1°。
-03-a 的 11 情境門檻測試、滿嚴重度跳機碼測試都通過。
- 給 -08：嚴重度 < 約 0.85 時是否跳機依機組而定（code review：0.7 固定 40 分鐘，30 支種子中 14 支不跳；0.9 以上全部跳）。做難度變體時，最終嚴重度低於這個範圍的情境不保證出現預期碼 335 / 336。

**守門測試**（`modules/monitoring/tests/test_healthy_blade_sync.py`，6 項；修正前失敗 4 項：機制 2 項、零點、原始重現點）：
- **機制**：14 支種子（預設風場大小）× 12 h，風速 6 → 24 → 6 m/s 加強紊流，Live 1 s 與批次 5 s 兩種步長。用 PLC 的延時算法量葉片差異：5 s 持續 < 0.7°、3 s 持續 < 1.5°、峰值 < 2°。
- **零點校正誤差**：50 支種子任兩片相差 < 0.4°。
- **整合**：健康 3 機，原始重現點 12 h（約 38 s）＋ 冬季夜間 / 夏季清晨各 6 h（約 18 s），釘住引擎起點，不得有訊號判定事件。
- **起點長度的取捨**（code review）：葉片誤差是各機組種子的隨機漫步，與起點、風況幾乎無關。修正前三個起點都在 +7:04:45 由 WT002 跳同一次 336，三個 12 h 只是同一個樣本、CI 多花約 2 分鐘。葉片同步的覆蓋由 14 種子的機制測試負責；另兩個起點看的是季節 / 日夜風況與氣溫下其他規則（溫度、偏航煞車、風向標）也不誤跳。

**starter kit**：重產後只有資料包 03 改變。
- WT005 葉片不平衡故障的 336 跳機早 5 s。
- 原本 1.5 h 後的 `trip_cleared` 消失。那是停機後雜訊讓差異短暫低於解除值（0.7°），故障其實沒修。
- 基準成績、lead time、238 筆狀態轉換都不變。

**已知限制**：各葉片伺服速率仍差 0.92 / 0.95 / 0.98 倍。Live 1 s 步長下，共同指令以最大速率移動時，葉片會短暫相差：TI 12% 約 0.5–0.9°，陣風 TI 30% 約 1.2–1.8°（code review 實測；修正前 1.5–2.0°）。1 s 內追上，不會持續 3 s / 5 s（連續 5 s 最大值不論紊流都約 0.5°）。

### 6.11 Phase 3b WebSocket 回放（WMOM-20261021-06，2026-10-22）

**定案**（劉老師確認，DEC-20261022-02）：

| 項目 | 決定 |
|---|---|
| 回放方式 | 單次直播（evaluation）＋ 練習模式（practice） |
| 速度 | 出題端建回放時固定 |
| 預測 | 走同一條 WS，伺服器以收到時的模擬時間蓋 `ts` |
| 受測端身分 | 回放 token（不開帳號） |

合約升為 v1.1（新增 §12），資料包與標準答案格式不變。

**回放器** `modules/monitoring/server/replay.py`（-07 OPC UA server 共用）：
- `ScenarioReplay`：可匯出資料包的情境才能回放（同 `load_exportable_scenario` 的條件）。
  - 讀值依時間分頁取：先取 `(id, timestamp)` 索引，每頁再以 id 取 500 筆。每頁一個短查詢，可以在 `asyncio.to_thread` 的不同執行緒呼叫。
  - 事件以 `is_observable_event` 過濾後全部載入。
  - 10 分鐘統計逐窗計算：與匯出器同一個 `StatsBuilder`，新增 `close_before` / `close_all`。
- **訊息順序**：依模擬時間。同一時刻：結束於此刻的統計 → 事件 → 讀值。最後的殘缺窗在資料結束時送。
- **內容與盲測版資料包逐筆相同**：讀值的 REAL32 取 float32 的最短十進位表示，讀回 float32 與 Parquet 逐位元相同。測試逐筆比對 raw / stats / events。
- `ReplayClock`：模擬時間＝`sim_start` +（實際經過秒數 × 速度）。

**端點** `server/routers/replay.py`：
- **REST（主管）**：
  - 建回放：`POST /api/scenarios/{id}/replay-runs`。token 只回一次。
  - 列表 / 狀態：`GET` 同路徑，狀態為 ready / not_started / running / finished / expired / revoked。
  - 撤銷：`DELETE /api/replay-runs/{id}`。
  - 下載預測：`GET /api/replay-runs/{id}/predictions`。
- **CLI** `tools/replay_runs.py`：同樣的四個動作，直接操作風場 DB。
- **WS** `/ws/replay`：token 放 `Authorization: Bearer` 或 `?token=`。
  - 送訊息與收預測是兩個 task，送訊息有鎖。
  - 單次回放在第一次連線時原子地寫入 `started_at`。
  - 拒絕連線時先送 `error` 再以 44xx 關閉。
  - 播完送 `finished`，連線再開 10 秒讓途中的預測拿到 ack。
- **DB**：
  - `replay_runs`（token 只存 sha256、模式、速度、到期、`started_at`、連線數、撤銷時間）。
  - `replay_predictions`（回放、連線序號、收到時間、模擬時間、預測）。
  - 刪除情境時一併刪除。

**時間因果**：
- `ts`＝收到預測時的模擬時間，不會早於受測端看到的資料。伺服器照時鐘送、不等受測端，收得慢就晚。
- 情境結束後的預測退回（評分時也對不到 case）。
- 單次回放中途加入：`?backfill=false` 只從「現在」開始；預設補送過去的資料，但時鐘仍是直播的現在。

**starter kit**：
- `stream_client.py`：基準助手的即時版，一個 task 收、一個 task 判斷，等所有預測都有 ack 才離開。
- README 新增「即時回放」，`requirements.txt` 加 `websockets>=13`。
- 範例資料包重產：只有 `contract_version` 改成 1.1，資料檔逐位元不變。

**code review**（Needs revision → 全修）：
- **M1 詞彙檢查在 Docker 裡失效**：詞彙檔在 `examples/`，映像不含，找不到時原本直接略過。
  - 唯一來源移到 `shared/data/rag_assistant_vocabulary.json`，kit 的 `vocabulary.json` 是副本（`build_rag_starter_kit` 同步、測試比對）。
  - 找不到就匯入失敗。
- **M2 單次回放的連線上限有競態**：實測同時 16 條連線收進 9 條。改為檢查與佔位之間沒有 await，鍵含 DB 路徑。
- **S1 極端數值讓連線以 1011 斷線**：超長整數、巨大的 `confidence`。改為每則訊息的處理失敗只回 `error`。
- **S2 撤銷 / 到期不影響已開的連線**：串流中每 5 秒重讀，撤銷或到期就以 4403 關閉。
- **S3 同情境的練習回放可以先偷看**：建回放時預設拒絕兩種模式並存（409，`allow_overlap` 才放行）；新增 `?check=true` 試 token 而不開始計時。
- **S4 每條連線都重載整個情境**：
  - 索引改為 `array('q')` 的 id（寫入順序已是時間順序時不排序），依情境快取。
  - 4409 / 4410 先擋。
  - 讀值上限 200 萬筆。
- **S5 測試沒守住傳送端的時間因果**：新增假時鐘驅動 `stream()` 的測試，逐則確認送出時 `due ≤ 現在`。
- **S6 預測與訊息的保護**：每則 64 → 16 KB；每個回放總量 20 MB；uvicorn `ws_max_size` 1 MiB。
- **S7 串流落後時鐘**：
  - 預取下一頁；讀值轉換加速約 2 倍（約 3,800 筆 / 秒）。
  - 正式評測限制「機組數 × 速度 ÷ 取樣週期 ≤ 1000 筆 / 秒」。
  - 600× 時落後中位數 0.03 s。
- **S8 刪除情境會連帶刪掉評測結果**：有預測時 `DELETE /api/scenarios/{id}` 預設 409，要 `force`。前端提示先下載。
- **S9 kit 客戶端被拒絕時只吐 traceback**：改為印出關閉碼與伺服器說明；預設不走環境變數的 proxy；`--check`。
- **S10 文件**：4401 / 4404 的語意、20 秒 keepalive、ISSUES 描述等。
- **Nice-to-have 採用**：
  - 蓋章不早於已送出的資料（時鐘被調回也一樣）。
  - 不用 `UPDATE … RETURNING`（SQLite < 3.35 也可用）。
  - handler 被取消時一併取消子 task。
  - 建回放的回應 `Cache-Control: no-store`。
  - 基準助手的單步邏輯抽成 `BaselineAssistant` 共用。

**測試** `modules/monitoring/tests/test_replay.py`（54 項；以下為初版 40 項，review 補測見下）：
- 與資料包逐筆相同、順序與統計的因果、不含答案。
- 時鐘、預測檢查。
- WS：
  - 練習模式完整播完。
  - 預測蓋章、受測端填的 ts / pack_id 不採用；下載後 `score.py` 評得到。
  - 單次回放：第一次連線定開始時間、中途加入不倒帶、播完不能再連。
  - token：缺 / 無效 / 撤銷 / 到期。
  - 撤銷後不收預測、壞訊息、連線上限、情境結束後的預測、關閉碼。
- REST 權限與參數、刪除情境連帶刪回放。
- kit 客戶端對真的 uvicorn 伺服器跑完一次（1200×）。
- CLI。
- **review 補測**：
  - 假時鐘下傳送端逐則 `due ≤ 現在`。
  - 串流中撤銷 5 秒內斷線。
  - 時鐘調回時 `ts` 不早於已送資料。
  - 兩種模式並存防呆（含 REST 409）、`?check=true` 不開始計時。
  - 正式評測的連線上限、預測筆數 / 位元組上限、4404。
  - 二進位 / 超長整數 / 巨大 confidence / 超長訊息 / sensor_fault。
  - 索引快取、詞彙檔缺失、刪除情境要 `force`、正式評測的速度上限。
  - kit 客戶端被拒絕時的關閉碼與 `--check`。

**已知限制**：
1. **回放存在風場 DB**：伺服器以目前風場查 token；切換風場後，其他風場的回放連不上。
2. **連線數上限每個程序各算**（每個回放 4 條）。
3. **兩種模式並存的防呆可以用 `allow_overlap` 關掉**：關掉後，正式評測的情境若同時開練習回放，學生可以先看完。
4. **沒有前端頁面**：建回放用 REST 或 CLI；Docker 映像不含 `tools/`，容器內用 REST。
5. **受測端慢就晚**：高速回放（例：10000×）時，受測端每慢 0.1 秒就晚 1000 秒模擬時間。正式評測的速度要依受測端的運算時間選。
6. **取樣週期的來源**：回放的 `sample_period_s` 取情境設定的 `time_step`；資料包取資料推得的值，沒有才用 `time_step`。批次生成的情境兩者相同；人工寫入的 session 若不同，`is_partial` 可能不一致。

### 6.12 Phase 3c OPC UA server（WMOM-20261021-07，2026-10-22）

**定案**（劉老師確認，DEC-20261022-03）：

| 項目 | 決定 |
|---|---|
| 資料來源 | 回放（CLI 綁一個 §6.11 的回放，正式評測與 WS 共用時鐘）＋ 即時模擬（主程式 `WMOM_OPCUA_ENABLE=true`） |
| 合成 tag | 全部掛上，節點說明標示 `synthetic` |
| 連線身分 | 匿名唯讀 |
| 正式評測開播 | 出題端啟動 server 時（節點建好、開始監聽後） |

合約升為 v1.2（新增 §13；WS 加 `?stream=false`、開播訊息加 `stream.data`），資料包與標準答案格式不變。

**server** `modules/monitoring/server/opcua_server.py`（`asyncua`）：
- `Z72OpcUaServer`：namespace `urn:windmindom:z72sim`，字串 NodeId＝真實 OPC DA 的 item ID。
  - 讀值 `Z72.H{nn}.{group}.Z72PLC__UI_Loc_*`：欄位與資料包同一組，型別依 PLC（REAL32 → Float …），缺值 `BadNoData`、開播前 `BadWaitingForInitialData`，`SourceTimestamp`＝模擬時間。
  - `WMET.Z72PLC__UI_Loc_WMET_Analogue_WSpeedNacAvg10m`：真實讀取腳本會讀、模擬器沒有輸出的真實 tag，由 server 以 `WSpeedNac` 的 10 分鐘移動平均（`RollingMean`）算出。
  - 事件碼陣列 `Z72PLC__ActiveAlarm[0..20]` / `ActiveTrip1` / `ActiveTrip2`（Int16，只寫有變動的元素）。
  - `WindMindOM.*` 狀態：`Source`、`Status`、`SimTime`、`PackId`、`Mode`、`Speed`。
- 只收匿名 identity token、關閉 asyncua 內建 admin、唯讀 user manager：任何 session 都不能寫值或加刪節點。
- `ReplayFeeder`：依時鐘每「取樣週期 ÷ 速度」實際秒（夾在 0.05–0.2 s）推進，各機組只寫最新一筆讀值；事件流重建事件碼陣列（第一次推進寫入全部機組）。每 5 秒重讀回放，撤銷 / 到期 / 刪除就停止；單次更新失敗只記錄、下一輪再試。
- `LiveFeeder`：每秒讀 simulator 的 `get_current_data()` 與 `model.plc.active_lists`；不是即時模擬（產生情境 / 真實 OPC）或批次正在跑時只標示 `idle`；跑過批次或換了 simulator 就重來（批次留下的讀值不發布、10 分鐘平均重新累積、不見的機組改 `BadNoData`）。
- `start_live_from_env`（`server/opcua_config.py` 判斷開關，沒開不載入 asyncua）：選配，預設只聽 `127.0.0.1`，起不來（埠被占用等）只記警告。

**事件碼陣列** `simulator/physics/plc_protection.py` 的 `ActiveEventLists`：依成立順序、同一個碼只出現一次；`alarm_raised` / `alarm_cleared` 增刪 A，`trip` 依等級加入 T1 / T2、`trip_cleared` 移除；超過每小時上限時跳機碼留著（鎖存），A039 加入 A（-02 前送 `restart_blocked`，不動清單）。操作員復位本身不動清單：`PlcProtection.operator_reset` 為每個解除的鎖存另送 `trip_cleared`（維護清除故障的復位不解除鎖存）。`PlcProtection._emit` 送事件時同步更新；回放用同一個類別從事件流重建。清單每一步都等於 `PlcProtection.active_codes()`（測試逐步檢查）。

**CLI** `tools/opcua_server.py <db> <回放 id>`：`load_run` 檢查回放（不存在 / 撤銷 / 到期 / 單次已播完）→ 建好全部機組的節點並開始監聽 → `start_clock`（正式評測寫入 `started_at`、已開始就沿用；練習把這次的起點寫進 `started_at`）→ 播到結束（`--exit-when-finished` 結束，預設保留最後的值）。撤銷 / 到期 / 刪除時狀態節點保留 10 秒再關；埠被占用回 exit 1。

**WS** `/ws/replay?stream=false`：只收預測、不送資料，等到情境結束送 `finished`；期間照樣每 5 秒重讀回放。練習回放的時鐘用 OPC UA 這次開播的起點（還沒播出 4412、這次已播完 4410）。

**starter kit**：
- `opcua_client.py`：用字串 NodeId 讀目前值與事件碼陣列（一個 Read 請求），比較前後兩次的陣列得到事件、交給基準助手，經 WS `?stream=false` 送預測。
- `stream_client.py` 抽出 `with_params` / `connect_options` 共用。README 新增「OPC UA」；`requirements.txt` 加 `asyncua>=1.1`。
- 範例資料包重產：只有 `contract_version` 改成 1.2，資料檔逐位元不變。

**測試** `modules/monitoring/tests/test_opcua_server.py`（20 項，一律用 asyncua client 讀回；初版 12 項如下，review 補測見下）：
- `ActiveEventLists` 規則、`RollingMean`、站號與 item ID。
- 回放：節點型別、合成 tag 標示、瀏覽路徑；6 個檢查點的讀值（float32 比對）/ `SourceTimestamp` / 10 分鐘平均 / 事件碼陣列 / 狀態節點與回放訊息一致；真實讀取腳本（`BASE_TAGS`）的每個 item ID 都讀得到；寫入被拒。
- 撤銷時停止更新；正式評測：載入不開播、啟動時寫入開始時間、重啟沿用、WS `stream=false` 加入同一個時鐘且只收 ack；播完 / 撤銷 / 不存在都擋。
- 即時模擬：讀值與 PLC 清單、復位、非即時模擬標 idle；即時模擬的清單與回放重建的清單一致（同一次批次生成）；環境變數開關與埠被占用。
- CLI；kit 客戶端對真的 OPC UA + uvicorn WS 伺服器跑完一次（600×），預測含 `main_bearing`。

**code review**（Needs revision → 全修）：
- **M1 帳號填 admin 就能寫**：asyncua 預設的 user manager 把帳號名 admin 當管理員（不檢查密碼），可以改值、加刪節點。改為只收匿名 identity token、關閉 `allow_remote_admin`、自訂唯讀 user manager；測試 admin 登入被拒、匿名寫值 / 加節點被拒。
- **M2 即時 OPC UA 會播出產生中的考題**：批次與即時模擬共用 simulator，`latest_data` / PLC 清單是批次的未來時間與注入的故障。改為批次期間 `idle`、批次後先略過留著的讀值；預設只聽本機；文件寫明批次的故障會留在即時模擬裡。
- **M3 練習回放的 OPC UA 與 WS 時鐘不同**：練習的 WS 連線各自從連上起算，與 OPC UA 的開播時間差多久、預測時間就錯多少。改為 OPC UA 開播時把起點記在回放上，`stream=false` 的練習連線用它（還沒播出 4412）。
- **S4 移動平均假設時間不倒退**：批次後回到現在，未來的樣本永遠移不出去。時間倒退就清空；換 simulator / 跑過批次時 LiveFeeder 重來，不見的機組改 `BadNoData`。
- **S5 事件碼陣列與 PLC 鎖存不一致**：維護清除故障的復位（`maintenance_release`）也送 `operator_reset`，舊規則把跳機陣列清空，但鎖存還在；操作員復位不解除物理層保護停機（351）卻也被清掉。改為操作員復位為每個解除的鎖存送 `trip_cleared`、清單不再在復位時清空；新增「每一步陣列＝`active_codes()`」測試（含操作員復位與維護清除）。
- **S6–S7、S10 CLI**：撤銷時狀態節點保留 10 秒；停止原因改用代碼（`missing` / `revoked` / `expired`）；埠被占用 exit 1；`0.0.0.0` 時提示用主機名稱連線。
- **S8 kit 客戶端**：判斷改在另一個執行緒（換成同步的大模型呼叫也不卡）；送預測時連線已關、WS 握手失敗、回放結束時 OPC UA server 剛好關掉都不吐 traceback；讀值改用 dataclass。
- **S9、S11–S14**：`LiveFeeder` 改用 `get_current_data()`（有鎖）與 Protocol 型別；`_z72` / 樣本的型別；即時 OPC UA 預設 `127.0.0.1`；主程式關機時 `try/finally`、開關判斷集中在 `opcua_config.py`、`LiveOpcUa.stop` 不吞掉呼叫端的取消；`utc_now()`、docstring；測試不再改模組共用的 fixture。
- **Nice-to-have 採用**：更新間隔依取樣週期與速度；單次更新失敗不中斷播出；站號衝突（`WT01` 與 `WT001`）明確報錯；事件碼陣列開播前也是 `BadWaitingForInitialData`；文件寫明 OPC UA 與 WS 要同一台電腦（或時鐘對準）；asyncua 版本限定 `>=2.1,<3`。
- **review 補測**：admin 登入、批次期間與批次後、機組不見、站號衝突、每一步陣列＝PLC 狀態、練習回放的 `stream=false` 對時與 4412 / 4410、CLI 撤銷中途停止與埠被占用、更新間隔。

**已知限制**：
1. **只有目前值**：回放每「取樣週期 ÷ 速度」更新一次（夾在 0.05–0.2 s）；速度越快，越多短暫的警報讀不到（3000× 時約 150 模擬秒）。
2. **陣列排列是模擬的約定**：手冊沒寫真實 PLC 陣列的排法。
3. **一個 server 播一個回放**；正式評測從出題端啟動起算，受測端晚連就少看一段。
4. **匿名、不加密**：只給教室 / 實驗室網路；沒有 session 數上限。
6. **即時模擬延續批次的故障**：產生情境與即時模擬共用模型，批次注入的故障之後仍在即時模擬裡（既有行為）。有受測端連著即時 OPC UA 時不要在同一個主程式出題。
5. **舊的 `modules/monitoring/opcua_interface.py`**（python-opcua、自訂路徑）沒有接線，維持不動。

### 6.13 Phase 4-a 感測器故障 vs 真故障（WMOM-20261021-08-a，2026-10-22）

**定案**（劉老師確認，DEC-20261022-04）：

| 項目 | 決定 |
|---|---|
| 先做的子項 | 感測器故障 vs 真故障 |
| PLC 看什麼 | 只對被注入感測器故障的那支感測器改看量測值（其他照舊看製程值） |
| 故障種類 | 讀值像真故障（漂移）＋ 有專屬感測器故障碼（斷線 / 編碼器） |
| component | 被量測的元件，`category` 區分 |

**機制**（`turbine_physics.py`）：`_get_fault_physics` 多一個 `sensor_faults`（`{tag: ("offset", Δ) | ("pinned", 讀值)}`）。`step()` 先算製程值，`_apply_sensor_faults` 產生量測值（沒有感測器故障時就是同一個 dict），PLC 判定量測值、感測器模型也吃量測值；`pinned` 讀值在感測器模型之後再蓋一次（斷線讀值固定、沒有雜訊）。製程、控制、其他感測器的雜訊完全不變。

**情境**（`fault_engine.py`，全部 `category: sensor_fault`）：

| 情境 | component | 碼 | 難度 | 讀值 |
|---|---|---|---|---|
| `main_bearing_temp_sensor_drift` | main_bearing | 262 / 240 | hard | `WGEN_GnBrgTmp1` + 60 °C × 嚴重度 |
| `stator_temp_sensor_drift` | generator_stator | 264 / 244 | hard | `WGEN_GnStaTmp1` + 100 °C × 嚴重度 |
| `main_bearing_temp_sensor_wire_break` | main_bearing | 242 | easy | 嚴重度 ≥ 0.5 時固定 850 °C |
| `blade1_pitch_encoder_fault` | pitch_system_blade_1 | 326（T2） | easy | 嚴重度 ≥ 0.5 時固定 135° |
| `yaw_brake_pressure_sensor_fault` | yaw_brake_hydraulics | 229 | easy | 嚴重度 ≥ 0.5 時固定 −62.5 bar |

- 漂移的偏移量讓「滿嚴重度在 14 m/s 越過跳機設定、嚴重度 0.5 還不到警報」（同真故障的校正方式）；物理上是 Pt100 量測回路接觸電阻增加。
- **新增真實 tag**：`WGEN_GnBrgTmp2`（軸承 2 熱節點：同樣的摩擦熱；主軸承磨耗的故障熱與潤滑劣化分到 40 %，升溫約軸承 1 的三成）、`WGEN_GnStaTmp2`（同一繞組另一個槽，固定偏移 ±2 °C 以內；繞組劣化時一起升）。雜訊與偏移走獨立的 `_rtd_rng`（主 `_rng` 與既有 aux 感測器逐位元不變）；116 → 118 個 tag（真實 45 → 47），資料包 100 → 102 欄。Modbus 502 / 510 原本的預留位改對到這兩個 tag。真故障因此「兩支一起變」：主軸承磨耗的 key signal 加上 `WGEN_GnBrgTmp2`；定子繞組劣化加上 `WGEN_GnStaTmp2` 與預期碼 265 / 245（同一繞組的兩支 Pt100 都可能先越過設定）。

**PLC**（`plc_protection.py`）：
- 第二支感測器的規則：263 / 241（軸承 2）、265 / 245（定子 2），設定值同第一支。
- 感測器故障碼：讀值超出有效範圍（`TurbineSpec`：Pt100 −40–250 °C、偏航壓力 −5–260 bar、葉片角度 −10–100°）持續 2 s → 242 / 243、250 / 251、229、326-328。
- 失效的讀值不再參與越限判定：`ProtectionRule.valid`（讀值有效旗標；無效時規則**立即**不成立，連已成立的也解除——與「判定窗關閉不等於條件解除」的 `gate` 分開）。溫度規則、偏航低壓、葉片差異（依每一對葉片的編碼器）都帶 `valid`。

**標準答案、語料、kit**：
- 5 個情境的答案欄位齊全（根因寫明哪些訊號正常、怎麼分辨；處置含手冊條目）。
- knowledge baseline 語料補 242 / 326 / 229 三個段落（測試要求語料碼＝情境碼）。
- starter kit 加 `z72-starter-04`（4 台、5 h、額定風）：WT001 主軸承磨耗、WT003 軸承溫度 1 量測回路劣化（同樣的 262 / 240，感測器先跳）、WT004 偏航壓力感測器斷線（229）。
- 基準助手：警報文字點名感測器才判 `sensor_fault`。四個範例上元件 87.5 %、類別 75 %，類別錯的兩個 case 都是讀值像真故障的。
- 合約 v1.3：§3.3 數量、§7 / §8 類別說明、§9 同元件兩種答案的對照表、§10 感測器故障須知、§10.1 開發集。

**測試**：
- `modules/monitoring/tests/test_sensor_faults.py`（12 項）：每個感測器故障只送自己的碼（不連帶送出同元件真故障或越限的碼）、漂移先警報後跳機且第二支感測器正常、真故障不送感測器故障碼、PLC 斷線規則（確認延時、修好解除、低於範圍、gate）。
- `tests/physics/test_fault_threshold_reach.py`：健康炎熱天第二支感測器不越限；漂移滿嚴重度越過跳機、0.5 還沒；**故障機組除了那支感測器，每個 tag 每一步都逐位元等於健康機組**；斷線讀值固定、嚴重度 0.4 還正常；第二支感測器跟著同元件（定子 2 與 1 一起升、軸承 2 只升一點）。
- 既有守門（新感測器只用 `_aux_rng`、健康風場無訊號事件、每個情境都會跳機、key signal 偏離健康）自動涵蓋新情境；範例資料包 01-03 的事件逐筆不變。

**code review**（Needs revision → 全修）：
- **M1 軸承溫度 2 分不出真故障與感測器故障**：原本主軸承磨耗只讓軸承 2 升 1.8 °C，「軸承 2 正常 → 感測器故障」對兩者都成立，答案寫的分辨依據資料裡沒有。改為軸承 2 分到 40 % 的故障熱與潤滑劣化（滿嚴重度 +28 °C、跳機當下約 +13 °C，仍低於警報）；範例 04 跳機時 WT001（真故障）軸承 2 為 56 °C、WT003（感測器）42.7 °C。測試改為比較兩者在跳機當下的軸承 2 升溫。
- **S1 新感測器讓既有 aux 感測器的雜訊位移**：改用獨立的 `_rtd_rng`；與 main 比對，健康機組既有 116 個 tag 逐位元相同；新增守門測試。
- **S2 已成立的規則不受讀值失效影響**：新增 `ProtectionRule.valid`；測試「262 成立 → 斷線 → 262 解除、改報 242」。
- **S3 漂移先警報後跳機的測試靠 1 °C 的巧合**：改從嚴重度 0 慢慢漂。
- **Nice-to-have 採用**：葉片差異依每一對葉片判定（葉片 1 編碼器壞了仍判 2-3）；斷線後的卡值不再重播被截斷的讀值；`evaluate` / `_in_range` docstring；語料不把模擬假設寫成事實；匯出 CSV 加兩個新 tag；補測試（跳機 → 維修鎖 → 清除 → 復機、嚴重度剛好 0.5）。
- **修 review 時發現**：定子 2 與定子 1 同繞組，定子繞組劣化時定子 2 可能先越過設定（245）；原本預期碼只有 264 / 244，故障沒被標成跳機、機組反覆重啟到封鎖。預期碼補上 265 / 245（語料同步）。

**已知限制**：
1. 斷線 / 編碼器故障一次發生，之前看不到（沒有間歇性斷線、沒有早期預警空間）。
2. 斷線讀值與有效範圍是模擬假設（手冊沒有數字）。
3. 只做了五種；卡值、其他溫度感測器（機艙 274、外氣 235）、轉速感測器 029 留給後續子項。
4. 控制邏輯不受感測器故障影響（例：編碼器壞了，變槳控制仍照實際角度運作）——真機的控制器可能會被錯誤讀值帶偏；這裡 PLC 立即跳機，影響有限。
5. **同一台機組的多重故障**（-08 後續子項）：`GroundTruthRecorder` 與引擎的跳機連結以「預期碼」對應故障；同一台同時有主軸承磨耗與軸承溫度感測器漂移時，兩個 case 都會認領 262 / 240。做多重故障前要先定歸屬規則。
6. 同一個 tag 有兩個感測器故障時，後注入的覆蓋前一個。
7. （2026-10-22 全面檢查補記）限制 2 不完全正確：手冊 Appendix D 有編碼器範圍（0–90°、容差 5°）等設定值，對照與修正見 WMOM-20261022-02（§6.14）。

### 6.14 EPIC-DS 全面程式碼檢查與功能驗證（WMOM-20261022-01，2026-10-22）

劉老師在做 -08 其餘子項前要求的整體檢查。各 issue 合併前都個別 review 過，這次找跨模組、跨 issue 才看得出來的問題。

**做法**：
- 三路 code review 平行：模擬器 / PLC / 故障情境、伺服器 / 資料包 / 回放、OPC UA / starter kit / 合約。每項要有重現路徑，多數以腳本證實。
- 完整 backend 1949 passed（修正後 1963）、frontend vitest 1513 / tsc / build；ruff（E9 / F / B）沒有 EPIC-DS 新問題；mypy 12 → 0（只改型別標註）。
- 真伺服器（隔離 DB、`WMOM_OPCUA_ENABLE`、`WMOM_AUTH_ENFORCE`）端到端 47 項：即時 OPC UA → 批次情境（2.5 h、14 台、真故障 + 兩種感測器故障）→ 答案卷 / 資料包 / CLI → WS 練習回放 → 正式評測（OPC UA 回放 + WS `stream=false`）→ 評分 → 撤銷 / 刪除守門。三條管道逐筆 / 逐位元相同（WS 12600 筆讀值、43 筆事件、224 窗統計；OPC UA 4896 格 float32），三條管道的評分結果相同。

**修正（不需決策）**：
- 非 Z72 機型（前端可選的 SG 8MW）健康機組約 5 分鐘被 Z72 的溫度保護跳機並 `restart_blocked`：熱模型以額定功率正規化（電氣發熱與附加熱 × Z72 額定 ÷ 本機額定），Z72 係數 1.0、輸出與 PLC 事件逐位元不變。
- Live 殘留的 PLC 狀態（鎖存、維護鎖、停機中、重啟上限已滿）漏進命名情境：情境開頭出現沒有 `trip` 的 `trip_cleared` / `operator_reset`，答案卻寫健康。`WindFarmSimulator.start_clean_scenario()` 重設帶殘留狀態的機組（乾淨的不動，範例資料包重建後資料不變）。`reset()` 一併清啟動時間戳（模擬時間歸零後舊時間戳讓重啟上限一直成立）。
- 正式評測的 WS `?stream=false` 可在 OPC UA server 開播前搶先開始計時：改回 4412。
- `wind_profile` 非字串時資料包 500、回放在開始計時之後才出錯（用掉單次回放）：生成時驗證型別、讀取端容錯、開播訊息的內容在開始計時前先算。資料包 / 回放輸出生成時實際套用的風況（`wind_profile_applied`），不信標籤。
- 情境 / 回放路由的 id 與 `limit` 範圍檢查（超出 SQLite 整數 → 422、負數 limit 不再等於不限）；`history?observable_only=true` 改用資料包事件格式；CLI 評分端版改放 `<pack_id>-full/`；正式評測進行中不能切換風場（回放與 token 存在目前風場的 DB）。
- starter kit：`stream_client` 斷線 / 網址錯不再是 traceback；`opcua_client` 看得到晚出現的機組；JSONL 只以 `\n` 分行（U+2028 是合法字元）；OPC UA 回放的回放狀態檢查失敗不中斷播出。
- 文件：合約 §3.5 tag 數、§13.2 `Status` 的 `missing`、4410 寬限期、README 範例清單。

**設計決策**（劉老師確認，DEC-20261022-05）：正式評測要伺服器強制登入；批次生成移到背景執行緒（同時一個、批次期間改模擬器的請求 409；實測生成期間查狀態最慢 0.10 s，原本 31.4 s）；建立正式評測時檢查整台伺服器的總速率；手冊保真度另開 WMOM-20261022-02。

**留給後續**：
1. ~~**WMOM-20261022-02（手冊保真度）**~~ → 2026-10-23 done（§6.15）：Appendix D 的延遲 / 範圍（液壓壓力低 30 s、風向標差異 60 s、編碼器 −5–95°、機艙 45 °C、Pt100 10 s 濾波；液壓 170 / 190 bar 與 Appendix C 的 180 bar 手冊自相矛盾，註明取捨）；自動重啟被擋時送 A039；`yaw_sensor_drift` 在 bias 差 < −3° 的機組永遠不跳 233（種子 33 / 34 / 119…），守門測試擴到多種子。
2. **-08 多重故障**：同一台機組多個 case 時，「每個元件猜一遍」可拿到 (k−1)/k 元件正確率、誤報 0（誤診全算在最晚開始的 case）；做多重故障時一起定評分規則。
3. Nice-to-have（記錄，不修）：批次（5 s 子步）與即時（1 s）的部分判定對 dt 敏感（電網欠壓累加器、`generator_overspeed` / `blade_icing` 的跳機嚴重度）；T2 不會升級進行中的 T1 正常停機、已停機時 PLC 跳機仍走一次 Normal Stop；`nacelle_cooling_failure` 的 273、`converter_cooling_fault` 的 421 / 432 實務上不出現（補 `simulation_notes`）；規則型與保護型 T021 重疊時事件碼陣列與 `active_codes()` 短暫不一致；`generator_overspeed_rpm`（027）沒有消費者；`update_spec` 重建 PLC 會丟掉鎖存；預測的儲存成本隨筆數線性成長；`POST /api/farms/{id}/export` 一直 500（既有問題）；正式評測開始後 token 到期仍會中斷（不可恢復）。

### 6.15 手冊保真度（WMOM-20261022-02，2026-10-23）

-01 的模擬器 review 對照手冊找到的不一致。三個決策由劉老師確認（DEC-20261023-01）。

**手冊自相矛盾的取捨：以 Appendix D 為準**。Appendix D 是「控制系統最重要的可設定值及其實際設定」，Appendix C 是事件清單的說明文字：

| 項目 | Appendix C | Appendix D（採用） | -02 前的模擬器 |
|---|---|---|---|
| 液壓壓力低 260 | < 180 bar（額定 −10 %） | `SDHyPres_L` 170 bar、`SDHyPres_H` 190 bar 解除 | 180 bar、遲滯 5 bar |
| 液壓壓力過低 228 | < 150 bar | `SDHyPres_LL` 150 bar、190 bar 解除 | 150 bar、遲滯 5 bar |
| 液壓事件延時 | — | `SDYwHyBrkTm` 30 s | 10 s / 5 s（假設） |
| 233 延時 | — | `SDWndVnDiscrTm` 60 s | 0 s |
| 233 風速條件 | 10 分鐘平均 > 4.5 m/s | `SDVw60sWndVnDiscr`（60 s 平均） | 10 分鐘（一階濾波近似） |
| 切出陣風 201 | 5 秒平均 > 35 m/s | `SDVwind_hi_3s` 3 秒 | 5 秒 |
| 機艙 273 | 未給數字 | `SDNacTmp_H` 45 °C | 46 °C（假設） |
| PLC 溫度 | — | `CDTauPT100` 10 s 濾波 | 無濾波、延時 10 s / 5 s（假設） |
| 編碼器 326-328 | 「outside range」 | 0–90° ± `SDVaneLimitTolerance` 5° | −10–100°（假設） |
| 重啟上限 | Max #/hr 欄（1、2、5、10…） | §11.3：出廠設定每碼 0 | 沿用 Appendix C（本機組的設定） |

Pt100 濾波：越限判定用濾波值；斷線判定（242 / 243 / 250 / 251）用未濾波讀值，斷線讀值不進濾波器，接回後從讀值重新起算（否則修好斷線會殘留 850 °C 的濾波值而誤跳 240）。健康機組最熱日（37 °C、20 m/s）機艙空氣最高 43.3 °C，低於 45。

**自動重啟被封鎖送 A039**（手冊 §6.8.1 / §8.3、Appendix C p.106）：同一跳機碼一小時內超過 `max_per_hour` → 保持鎖存、送 A 級 **A039「Auto restart blocked」**（多個碼封鎖只送一次），機組進 SHUTDOWN（TurSt 1）；操作員復位（008）或維護清除時 `alarm_cleared`。A039 是手冊獨有碼（xlsx 事件清單沒有），收進警報目錄並標 `manual_only`（`tools/build_z72_alarm_catalog.py`，目錄 315 碼）。合約 v1.4：不再送 `restart_blocked`（列舉值保留給舊資料包）；A039 出現在標準答案 case 的 `other_observed_codes`。

**拿掉全域「每小時 3 次啟動」上限**：digiWT 留下的 `max_restarts_per_hour` 把所有啟動都算進去，手冊沒有這個機制。實測風速在切入風速附近以 5 / 10 / 20 分鐘週期擺動時，健康機組 3 h 內有 2.5 / 2.0 / 1.0 h 卡在待機、沒有事件。現在物理層保護停機（超速、電網）照目錄每碼計數：`generator_overspeed` 滿嚴重度第 6 次 351 封鎖（上限 5）、`grid_voltage_sag` 第 2 次 481 / 021 封鎖（上限 1），都送 A039、停在 SHUTDOWN，操作員復位後恢復發電（`test_plc_integration.py`）。

**`yaw_sensor_drift`**：PLC 看到的差異＝漂移 + (風向標 1 − 2 的安裝偏差)，偏差差落在 ±4.5°（風向標 1 ±2.5°、風向標 2 ±2°）。線性 18° 在偏差差 < −3° 的機組永遠到不了 15°（種子 33 / 34 / 119…）。改為漂移 = 24° × 嚴重度²：滿嚴重度 ≥ 19.5°、嚴重度 0.5 ≤ 10.5°，對任何偏差都成立；守門測試對 300 個種子驗證偏差範圍，並對偏差最負 / 最正與原始重現種子端到端跑 PLC（`tests/physics/test_fault_threshold_reach.py`）。

**既有風場的 turbine_spec**：風場建立時存的是當時完整的 `to_dict()`，會把舊的 180 bar 帶回來。載入風場（啟動、切換）改用 `TurbineSpec.from_farm_dict`：Z72 PLC 設定值（`Z72_PLC_SETPOINT_FIELDS`）一律用程式的值，機型參數照存檔；spec 更新 API 仍可明確修改。

**範例資料包重建**：01 / 02 / 04 的事件不變；03（低風速陣風、6 h）的 PLC 事件也與 -02 前相同，只有 WT001 / WT002 多了低風速起停（不再被全域上限卡在待機，240 → 291 筆事件）。

**code review 修正**：(S1) 命名情境開頭的乾淨機組也清每小時跳機計數，否則 Live 一小時內自動恢復過的保護停機會讓情境的第一次同碼跳機就送 A039；(S2) 233 的風速條件改為判定窗（`gate`），不再把差異訊號歸零——原本跳機後風速低谷會解除鎖存、風回來再跳，範例資料包 03 的 WT003 因此跳 4 次、停機中還出現 Shutdown → Normal Stop；(S5) 每個碼的狀態在 reset 時建好，保護停機不在執行中新增鍵（API 執行緒的操作員復位迭代時不會遇到字典變大）。021 不分成因一起計數、兩條路徑的判定時點不同，記在 DEC-20261023-01。

**仍未對上手冊（留給後續）**：236 塔架加速度——手冊 `SDNacVibR_HH` 1.75 m/s² 看合成加速度 `VibMsNacR`，模型的機艙振動是速度（mm/s），沿用假設值 7 mm/s；Appendix D 的暴風等級（`SDVwind_Storm_10m` 27 m/s → 204 Storm park）沒有模擬；233 的 60 s 平均風速以一階濾波近似。

### 6.16 Phase 4-b 誤報 / 健康負樣本（WMOM-20261021-08-b，2026-10-23）

到 v1.4 標準答案只有故障 case，看到警報就報故障不會被扣分。-08-b 讓「不是故障的警報 / 跳機」也有答案、評分量得到誤報。設計三個選項由劉老師確認（DEC-20261023-02）。

**干擾來源**

| 來源 | 機制 | 事件碼 | 標準答案 |
|---|---|---|---|
| 電網電壓驟降 | 風場事件 `grid_voltage_dip`：事件期間風場電網模型的電壓固定在 `magnitude` p.u.（照樣加量測雜訊，亂數抽樣次數不變），各機組依個體差的保護裕度停機，恢復後自動重啟 | 482 / 481 + 021 | 每台有反應的機組一個 nuisance case（`grid_disturbance`） |
| 電網頻率越界 | 風場事件 `grid_frequency_excursion`：頻率偏移 `magnitude` Hz | 489 + 021 | 同上 |
| 風向快速變化 | 風場事件 `rapid_wind_direction_change`：風向以 180 s 週期正弦擺動（振幅 `magnitude`°，頭尾各 60 s 漸強 / 漸弱），偏航追不上 | 223 | 同上（`wind_direction_change`） |
| Pt100 接點鬆動 | nuisance 情境 `main_bearing_temp_loose_contact`（手冊 §11.3）：注入後 5–20 分鐘第一次、之後每 15–45 分鐘瞬斷 10–30 s，瞬斷時讀值＝斷線值 | 242（一小時內超過上限 → A039） | 每次注入一個 case（`loose_contact`，`component: main_bearing`） |
| 環境 / 運轉條件 | 沒有注入：暴風切出、極端氣溫等模擬自己產生的事件 | 201、256 / 273… | 沒有故障的機組（或故障開始前）其餘沒被認領的事件，同機組 30 分鐘內一個（`environment`） |

一個電壓驟降（0.70 p.u.、20 s）讓 4 台發電中的機組同一個取樣步跳 482 + 021、約 45 s 後全部自動重啟；風向擺動 ±60°、25 分鐘讓 3 台機組各跳 2–3 次 223、每次 5 s 後重啟（第 4 台已因 Pt100 鬆線送 A039、停在 Shutdown 等操作員復位）。

**偏航逾時 223（新 PLC 規則）**：Appendix D `SDYawTmOutFact` / `SDYawTmOutOffs`——對風（不含解纜）開始時依當下的偏航誤差算允許時間＝factor × max(|誤差|, 2°) ÷ 偏航速度 + offset（5、0 s、0.5 °/s），這一段對風超過就跳機；偏航停下就重算。健康偏航實測：最長 55 s，實際用時最多約為「誤差 ÷ 偏航速度」的 1.4 倍、允許時間的 0.29（約 3.5 倍裕度）；單向的風向轉變偏航追得上，不會逾時，所以風場事件用來回擺動。範例資料包 01–04 的資料逐位元不變。

**標準答案**（合約 v1.5 §7.1）：case 加 `nuisance_cause`、`window_end_ts`、`farm_event_id`，頂層 `farm_events`。風場事件 case 的時間窗＝事件開始到「事件結束與最後一個相關事件較晚者 + 30 分鐘」；環境性 case 從第一個事件到最後一個 + 30 分鐘，不跨進同機組故障開始之後。跟在 nuisance 跳機之後的 A039 歸給同一個 case；故障開始後同機組其他沒被認領的碼仍是 `unattributed_events`（故障連帶）。`healthy_turbines`＝沒有故障 case 的機組。nuisance 情境不鎖機組（`FaultEngine.mark_tripped` 不轉 tripped，`on_fault_tripped` 不會來），case 的 `trip_ts` 取第一個預期碼的跳機事件。

**評分**（`score.py`，合約 §8）：故障指標只算故障 case、規則不變；新增干擾辨識率（時間窗內有 `nuisance` 預測）、把干擾當故障（時間窗內的誤報，已算進誤報）、誤報率（誤報次數 ÷ 沒有故障的機組時數 × 100）。沒有故障的機組時數＝每台機組的情境長度扣掉故障 case 時間窗——誤報只會發生在這段時間。

**範例資料包 05（健康負樣本）**：4 台、6 h、額定風速、7 月：0.5 h 注入 WT003 Pt100 鬆線、1 h 電壓驟降 0.70 p.u. 20 s、2.5 h 頻率 −1.8 Hz 40 s、4 h 風向擺動 ±60° 25 分鐘。12 個 nuisance case、0 個故障；187 筆事件。基準助手（加了「同一個碼 60 秒內已在另一台機組出現 → nuisance」）認出 8 個，誤報 4 次（全場一起跳的第一台、Pt100 鬆線當感測器故障），誤報率 5.46 / 100 機組小時。

**code review 修正**（沒有 must-fix）：
- **歸屬規則**：
  - 同種事件一小時內兩次時，碼歸給涵蓋它、最晚開始的事件（S1）。
  - 事件進行中到結束後 10 分鐘的任何碼都歸事件，事件碼這段時間不讓故障 case 認領（S2）。
  - A039 跟著同機組前一次跳機（S6）。
  - `build()` 可重複呼叫（S5）。
- **評分**：加干擾判定的落空筆數與準確率（S4）。
- **合約維持 v1.5**（S3）：`nuisance` 從 v1.0 起就是保留類別，見 DEC-20261023-02。
- **物理修正**（S2 的重現）：頻率 +1 Hz、未達 1.4 Hz 跳機時，下垂降載少送出的功率被算成變頻器發熱，冷卻水溫一分鐘升 18 °C、三台都送 420。
  - 改為只算效率損失：沒有降載時這一項恰為 0，健康資料逐位元不變。
  - 範例資料包 01–05 的讀值都沒變：05 的頻率事件是 −1.8 Hz，低頻不降載。

**沒有做進 05 的**：極端氣溫——額定風速、38 °C 的機艙控制櫃最高 49.7 °C（256 設定值 50 °C），要 39 °C 以上才會跳，台灣沿海不切實際；暴風切出——24 m/s 以上全場切出後一直停著（回切要 20 m/s），會蓋掉其他干擾。這兩種在情境裡出現時照樣標成環境性 case（`test_nuisance_events.py`、`test_fault_ground_truth.py` 以合成事件驗證）。

## 7. 不做的事

- 不在 windMindOM 內實作 RAG 維修助手（學生專題負責；windMindOM 只提供資料與合約）
- 不追高保真物理（BEM、Kaimal/Mann 風場、氣彈 FEM）——留在 ISSUES.md parking lot
- 不支援 Z72 以外機型作為資料源（直到 `update_spec` 補完）
- 不做真實風場 / 真實 PLC 介接（DEC-20261021-01 暫緩）
