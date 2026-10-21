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

> 「真實警報目錄」「模擬器警報碼」兩列已由 Phase 1a（WMOM-20261021-02）處理，現況見 §6.1。

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

```
{pack_id}/
  manifest.json          # contract_version、pack_id、機型、機組清單、sim_start/sim_end（UTC）、
                         # 原始取樣週期、seed、風況、產生器版本、各檔 sha256
  tag_dictionary.json    # tag → 單位、說明、source: bachmann_real | synthetic
  alarm_catalog.json     # 本包使用的 Z72 警報目錄快照（code、level、text、plc_tag、cause、recovery）
  timeseries_raw.parquet # timestamp(UTC), turbine_id, <真實 tag 名>...
  stats_10min.parquet    # window_start(UTC), turbine_id, <tag>_avg/_min/_max/_std
  events.jsonl           # 可觀測事件流（不含答案）
  ground_truth.json      # 標準答案（只給評分端）
```

`events.jsonl` 一行一事件：

```json
{"ts": "2026-03-01T03:12:40Z", "turbine_id": "WT003", "event_type": "alarm_raised",
 "alarm_code": 262, "alarm_level": "A", "alarm_text": "Main bearing 1 temperature high",
 "plc_tag": "Z72PLC__ActiveAlarm"}
```

`event_type` ∈ `alarm_raised` / `alarm_cleared` / `trip` / `reset` / `state_change` / `operator`。

`ground_truth.json`：

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
| 1b-c | WMOM-20261021-03-c | **UTC tz-aware 時間戳** |
| 2 | WMOM-20261021-04 | **標準答案 + 情境事件**：故障情境 metadata（根因/元件/預期警報序列/手冊條目/處置）；bulk 路徑產生事件；`history_events` 加 `session_id`；ground truth 落庫 |
| 3a | WMOM-20261021-05 | **① 檔案**：情境資料包匯出（含 10-min stats）；修或移除 `farms.py` 壞端點 |
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
- 物理層既有保護停機補事件碼：軟體 / 硬體超速 → 351 / 320；LVRT band 1（0.80–0.90 p.u.）→ 481 + 021、band ≥ 2（< 0.80 p.u.）→ 482 + 021；HVRT → 475 + 021；`grid_protection` / `grid_trip` 依量測電壓 < 0.81 → 482、< 0.90 → 481、> 1.08 → 475、其餘（頻率越界）→ 489（+ 021）；切出風速 → I 201（600 s 去重）。這類停機的重啟仍由物理層狀態機處理，不在 PLC 層鎖存；同一停機週期只記一次，機組再次起動後重新計。

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

1. **物理層保護停機的停機模式未依手冊等級**：軟體超速 351 在手冊是 T1，但物理層仍走緊急停機；切出風速也走緊急停機。
2. **切出風速用瞬間風速**：手冊 201 是 10 分鐘平均 > 25 m/s 或 5 秒平均 > 35 m/s；目前物理層看瞬間有效風速，高紊流高風速時會頻繁切出（另開 WMOM-20261021-10）。
3. **預期碼可能不出現**：低負載或嚴重度不足時情境不會跳機（上表嚴重度 0.8 的 4 個情境），ground truth（-04）必須允許「預期碼未出現」。
4. **事件順序由物理決定**：converter_cooling_fault 的 T021 與 T437 同一步送出；hydraulic_leak 壓力在偏航後的判定窗內一次跌破兩個設定值時，T228（延時 5 s）會先於 A260（延時 10 s）。
5. **`faults.py` 的 `run_test_plan` 不記錄 trip 事件**（不是情境 session），只有 `/api/config` 情境排程會記。
6. **每小時計數在條件解除時判定**：手冊只寫「Max #/hr」，未說明是跳機當下或重啟當下計數；目前在解除（要重啟）時看最近一小時的跳機次數。
7. **實測時點有約 ±1 分鐘的差異**：上表是同一程序依序跑 22 個情境的結果；前面情境的跳機時點會透過程序層級的共享狀態影響後面情境（例：converter_cooling_fault 0.8 單獨跑為 13.2 分、在序列中曾量到 12.8 分），屬量測條件差異，不是物理改變。

## 7. 不做的事

- 不在 windMindOM 內實作 RAG 維修助手（學生專題負責；windMindOM 只提供資料與合約）
- 不追高保真物理（BEM、Kaimal/Mann 風場、氣彈 FEM）——留在 ISSUES.md parking lot
- 不支援 Z72 以外機型作為資料源（直到 `update_spec` 補完）
- 不做真實風場 / 真實 PLC 介接（DEC-20261021-01 暫緩）
