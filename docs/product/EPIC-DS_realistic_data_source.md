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

## 5. 介面合約 v0（草案，Phase 3 定稿為 v1）

> v0 是給學生專題提早規劃用的草案；欄位可能調整，定稿前以本節為準。

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

- `ws://{host}/ws/replay/{scenario_id}?speed=1`（speed = 1 為實時，>1 加速）
- 訊息：`{"type": "reading", ...}`、`{"type": "event", ...同 events.jsonl}`、
  `{"type": "control", "status": "started|paused|finished", "sim_ts": ...}`
- 不推送 ground truth。

### 5.3 OPC UA：模仿 Bachmann Z72 tag

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
| 3b | WMOM-20261021-06 | **② 串流**：凍結情境回放器 + WS 回放端點（含事件通道） |
| 3c | WMOM-20261021-07 | **③ OPC UA server**：模仿 Bachmann tag（`asyncua`），接 3b 回放器 |
| 3d | WMOM-20261021-09 | **學生專題 starter kit**：介面合約 v1 定稿 + 範例資料包 + 讀取範例程式 |
| 4 | WMOM-20261021-08 | **難度與多樣性**：警報連鎖與重啟限制、感測器故障（標記）、多重故障、誤報、健康負樣本、早期徵兆案例；故障庫往 Z72 常見事件擴充 |
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
- **葉片差異需要時間窗**：健康機組在紊流風下瞬間差異可達約 1.16°（> 1°），PLC 判定必須用手冊的 5 s / 3 s / 瞬間三段，不可看瞬間值。
- **風向標 233 用 25 s 濾波值**：真實 tag `YwVn1/2AlgnAvg25s` 存在，本模擬只輸出 5 s 版本，濾波由 PLC 層做。
- **yaw_sensor_drift 的語意**：控制器跟隨風向標 1，所以風向標 1 讀數仍接近 0、風向標 2 顯示真實偏航誤差（−drift），疲勞 / 偏航斜流 / 尾流轉向都用真實誤差。
- **電壓驟降的副作用**：端電壓降低會啟動既有的電壓降載，嚴重度 0.3 時功率已降到約 1720 kW（健康約 2000 kW），遠早於跳機。

### 6.3 Phase 1b-b PLC 保護層（2026-10-21）

`modules/monitoring/simulator/physics/plc_protection.py`，每台機組一個 `PlcProtection`（`TurbinePhysicsModel.plc`），在每個物理步結束時判定。

**判定對象是製程值（感測器模型之前）**：感測器模型的雜訊、漂移、卡值是為 SCADA 趨勢的視覺真實度調的，幅度對保護判定太大（例：葉片角度漂移上限 ±0.8°，健康機組約兩天一次葉片同步 T2 誤跳）。感測器故障造成的跳機留給 Phase 4（-08）以有標註的方式建模。

**規則**（設定值全部來自 `TurbineSpec`）：溫度警報延時 10 s、跳機延時 5 s，皆有遲滯。延時從第一個越限樣本起算，連續越限的經過時間 ≥ 延時才成立——批次 5 s 子步下，有延時的規則（含葉片 3 s）至少要兩個連續樣本，單一樣本不算「持續」。成立後只依遲滯解除；判定窗（偏航煞車、穩定發電、只在發電時）關閉只禁止新的成立，不等於條件解除。

| 事件碼 | 訊號 | 條件 |
|---|---|---|
| A262 / T240 | 主軸承溫度 | > 85 / 95 °C |
| A264 / T244 | 定子溫度 | > 140 / 150 °C |
| A273 / T256 | 機艙空氣 / 機艙控制櫃溫度 | > 46 / 50 °C |
| A417 / T444 | 變壓器鐵心溫度 | > 80 / 90 °C |
| A420 / T437 + T021 | 變頻器冷卻水溫 | > 51 / 56 °C |
| A421 / T438 + T021 | 變頻器機櫃溫度 | > 62 / 67 °C |
| A432 | 冷卻水靜水壓 | < 2.5 bar，只在發電時判定（停機時泵停，本來就低） |
| A260 / T228 | 偏航煞車液壓 | < 180 / 150 bar，只在煞車施加 90 s 後判定（偏航時煞車鬆開，壓力本來就低） |
| A261 | 偏航煞車油封洩漏 | BOOL |
| T233 | 風向標 1−2 差 | 25 s 濾波值差 > 15°，且 10 分鐘平均風速 > 4.5 m/s |
| T335 / T336 / T337 | 葉片兩兩角度差 | 瞬間 > 8°、3 s > 3°、5 s > 1°；只在穩定發電 60 s 後判定（啟動大幅變槳時各葉片暫態差異可達 ~6.6°） |
| T236 | 機艙振動 max(X, Y) | > 7 mm/s 持續 10 s |

**跳機語意**：

- A 級只送 `alarm_raised` / `alarm_cleared`，不停機。
- T1 → 正常伺服停機（TurSt 9）；T2 → 緊急變槳（TurSt 7）。已排定的緊急停機不會被後到的正常停機要求降級。
- 跳機鎖存到條件解除（停機減速中葉片差異仍在、偏航中煞車鬆開都不算解除）；解除時若該碼一小時內的跳機次數 ≤ 目錄 `max_per_hour` → `trip_cleared`，機組自動重啟；超過 → `restart_blocked`，需操作員復位（事件 008）。復位後條件仍成立會立即再跳。
- 物理層既有保護停機補事件碼：軟體 / 硬體超速 → 351 / 320；LVRT band 1（0.80–0.90 p.u.）→ 481 + 021、band ≥ 2（< 0.80 p.u.）→ 482 + 021；HVRT → 475 + 021；`grid_protection` / `grid_trip` 依量測電壓 < 0.81 → 482、< 0.90 → 481、> 1.08 → 475、其餘（頻率越界）→ 489（+ 021）；切出風速 → I 201（每個停機週期一次；-10 前為 600 s 時間窗去重）。這類停機的重啟仍由物理層狀態機處理，不在 PLC 層鎖存；同一停機週期只記一次，機組再次起動後重新計。

**故障引擎連動**：`FaultEngine` 的嚴重度只驅動物理；`alarm_codes` 改為情境的**預期碼**（ground truth metadata，無門檻）。PLC 以情境預期的 T 碼跳機時，引擎呼叫 `mark_tripped` 把故障轉為 tripped（記 `trip_code`）；tripped 期間引擎設 `model.maintenance_lock` 阻擋重啟，取代原本每步 `cmd_emergency_stop`——**7↔3 擺盪已修**。「復位不等於修好」不變量（WMOM-20260719-01）不變：復位解除 PLC 鎖存，但維修鎖仍擋住重啟；只有維護清除（`/api/faults/clear`）會解除。維修鎖解除時引擎代技師清除 PLC 的每小時跳機計數與封鎖（`maintenance_release`，事件 008）——不論走哪條清除路徑（不帶機組的清除、情境批次、測試計畫都不會 reset 機組），否則一小時內第二次跳機留下的 `restart_blocked` 會讓修好的機組永遠停機。

**事件輸出**：即時路徑由 broker 每步 `drain_events()`，記為 `event_type="fault"`、`source="plc"`，payload 含 `kind / code / level / text / plcTag / eventId / value / setpoint / origin`；value / setpoint 取實際成立的那條規則（同碼多規則時，例：葉片 5 s 1° 規則、021 的機櫃溫度來源）；時間戳由 reading 的模擬時間回推（加速模式一個 tick 跑多步）。PLC 判定的停機原因為 `plc:<碼>`，broker 分類為 `Automatic fault stop: PLC event <碼>`。批次路徑（`generate_bulk`）尚未收事件（-04），結束時清空佇列，避免 Live 恢復後被當成新事件；情境排程的 tripped 轉換以 `kind="trip"` 事件記錄，供情境端點判斷「故障已跳機」。

**實測**（15 m/s、25 °C、注入後 3 h、dt 5 s）：

| 情境 | 嚴重度 1.0 事件序列（注入後分鐘） | 嚴重度 0.8 |
|---|---|---|
| bearing_wear | A262 7.8 → T240 10.0 | A262 28.0，3 h 未跳機 |
| stator_winding_degradation | A264 8.5 → T244 10.1 | 3 h 無事件 |
| transformer_overheat | A417 33.3 → T444 49.6 | A417 91.6，3 h 未跳機 |
| converter_cooling_fault | A420 2.7 → T437 + T021 3.4 | A420 6.4 → T437 + T021 13.2 |
| nacelle_cooling_failure | T256 61.2（無先行警報） | 3 h 無事件 |
| hydraulic_leak | A261 0.2 → T228 2.3 | 同左 |
| yaw_sensor_drift | T233 0.7 | T233 1.8 |
| pitch_imbalance | T335 0.2 | T335 0.6 |
| blade_icing | T236 0.2 | T236 0.2 |
| grid_voltage_sag | T481 + T021 0.8（物理層 LVRT） | 同左 |
| generator_overspeed | T351 + T320 0.2（物理層超速） | T351 0.2 |

健康 3 機風場（自動風況，含紊流與偏航）2 h 內沒有任何訊號判定的事件（`test_plc_integration.py`）；健康機組既有 111 tag 輸出與 -03-a 之前逐位元相同。

**已知限制**：

1. **物理層保護停機的停機模式未依手冊等級**：軟體超速 351 在手冊是 T1，但物理層仍走緊急停機（切出風速已於 -10 改為正常停機）。
2. ~~**切出風速用瞬間風速**~~ → WMOM-20261021-10 已解（§6.5）。
3. **預期碼可能不出現**：低負載或嚴重度不足時情境不會跳機（上表嚴重度 0.8 的 4 個情境），ground truth（-04）必須允許「預期碼未出現」。
4. **事件順序由物理決定**：converter_cooling_fault 的 T021 與 T437 同一步送出；hydraulic_leak 壓力在偏航後的判定窗內一次跌破兩個設定值時，T228（延時 5 s）會先於 A260（延時 10 s）。
5. **`faults.py` 的 `run_test_plan` 不記錄 trip 事件**（不是情境 session），只有 `/api/config` 情境排程會記。
6. **每小時計數在條件解除時判定**：手冊只寫「Max #/hr」，未說明是跳機當下或重啟當下計數；目前在解除（要重啟）時看最近一小時的跳機次數。
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
- `unattributed_events`：沒有任何 case 以預期碼解釋的警報 / 跳機 / 資訊事件，例如健康機組的偶發跳機（見 WMOM-20261021-12）、切出風速 I201、故障連帶的其他碼。評分端因此知道 RAG 面對的每一筆事件有沒有答案。

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

## 7. 不做的事

- 不在 windMindOM 內實作 RAG 維修助手（學生專題負責；windMindOM 只提供資料與合約）
- 不追高保真物理（BEM、Kaimal/Mann 風場、氣彈 FEM）——留在 ISSUES.md parking lot
- 不支援 Z72 以外機型作為資料源（直到 `update_spec` 補完）
- 不做真實風場 / 真實 PLC 介接（DEC-20261021-01 暫緩）
