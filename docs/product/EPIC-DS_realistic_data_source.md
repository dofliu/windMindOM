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
| 1b | WMOM-20261021-03 | **警報與時間戳擬真**：接上 `TurbineSpec` 溫度門檻、修 7↔3 狀態跳動、時間戳改 UTC tz-aware |
| 2 | WMOM-20261021-04 | **標準答案 + 情境事件**：故障情境 metadata（根因/元件/預期警報序列/手冊條目/處置）；bulk 路徑產生事件；`history_events` 加 `session_id`；ground truth 落庫 |
| 3a | WMOM-20261021-05 | **① 檔案**：情境資料包匯出（含 10-min stats）；修或移除 `farms.py` 壞端點 |
| 3b | WMOM-20261021-06 | **② 串流**：凍結情境回放器 + WS 回放端點（含事件通道） |
| 3c | WMOM-20261021-07 | **③ OPC UA server**：模仿 Bachmann tag（`asyncua`），接 3b 回放器 |
| 3d | WMOM-20261021-09 | **學生專題 starter kit**：介面合約 v1 定稿 + 範例資料包 + 讀取範例程式 |
| 4 | WMOM-20261021-08 | **難度與多樣性**：警報連鎖與重啟限制、感測器故障（標記）、多重故障、誤報、健康負樣本、早期徵兆案例；故障庫往 Z72 常見事件擴充 |
| 5 | （parking lot） | 只修會改變特徵訊號的物理：10-min std 合理化、yaw error → 發電損失等；高保真物理不做 |

建議順序：1a → 1b → 2 → 3a → 3d（先讓學生拿到檔案）→ 3b → 3c → 4。

### 6.1 Phase 1a 定案與已知限制

**警報門檻慣例**（`fault_engine.py` docstring，`test_fault_alarm_codes.py` 強制）：
A 級警報門檻 < `auto_trip_severity`；T1 / T2 跳機碼門檻 == `auto_trip_severity`。
跳機碼只在跳機當下出現，不會有「跳機碼已觸發但機組仍在發電」的資料。

**已知限制（留給 Phase 1b / 2）**：

1. **警報由 severity 觸發，不是由物理訊號越過真實門檻觸發**。以下情境的物理量級與真實判定條件不一致：
   - `pitch_imbalance`：葉片偏差 = 3°·severity；真實 335/336 在持續 5 秒 > 1° 就跳機（約 severity 0.33），模擬器到 0.90 才跳
   - `yaw_sensor_drift`：風向標偏差 = 12°·severity，最大仍低於 233 的 15° 判定
   - `generator_overspeed`：351 / 320 應分別在轉速越過 26.5 / 28.5 rpm 時觸發
   - `grid_voltage_sag`：物理層只有變頻器發熱與降載，沒有電壓下降訊號，卻送出 ARU 欠壓碼
   - `hydraulic_leak` 已把 260 門檻對齊 180 bar（severity 0.4）；228（< 150 bar）對應 severity 0.75，但仍在 auto-trip 0.85 才跳
2. **5 個情境在跳機前沒有任何警報**（pitch_imbalance、yaw_sensor_drift、generator_overspeed、blade_icing、grid_voltage_sag）。這符合真實 Z72 事件清單（沒有對應的 A 級警報），但 ground truth 的 `first_alarm_ts` 會等於 `trip_ts`，「早期徵兆」評分只能靠 SCADA 趨勢。
3. **跳機一律走 emergency stop**（`simulator/engine.py` 對 tripped fault 呼叫 `cmd_emergency_stop`），但 T1 定義為正常伺服停機、T2 才是緊急變槳。
4. **變頻器事件（400-700）手冊只寫「See [ABB]」**：只靠 Z72 手冊的 RAG 查不到細節，ground truth 應標註預期答案僅能指向 ABB 手冊。
5. 物理層自有跳機（overspeed / cut-out / grid / ride-through）只寫 `shutdown_cause` 字串，沒有事件碼。

## 7. 不做的事

- 不在 windMindOM 內實作 RAG 維修助手（學生專題負責；windMindOM 只提供資料與合約）
- 不追高保真物理（BEM、Kaimal/Mann 風場、氣彈 FEM）——留在 ISSUES.md parking lot
- 不支援 Z72 以外機型作為資料源（直到 `update_spec` 補完）
- 不做真實風場 / 真實 PLC 介接（DEC-20261021-01 暫緩）
