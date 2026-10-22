# Z72 RAG 維修助手 starter kit

給學生專題用的入門包：windMindOM 模擬 Z72 風場產生的**範例資料包**、讀取程式、一個陽春的**基準助手**，
以及**評分程式**。介面規格以 [資料介面合約 v1.3](../../docs/integration/rag_assistant_data_contract_v1.md) 為準。
資料有三種拿法：**資料包檔案**（離線）、**WebSocket 回放**（即時，見下方「即時回放」）與 **OPC UA**
（像接真實 PLC，見「OPC UA」）。

## 內容

```
rag_starter_kit/
  packs/                      範例資料包（盲測版，跟正式評測拿到的格式一樣）
    z72-starter-01/  02/  03/
  answers/                    範例的標準答案（劇透！先別看，跑完再拿來評分）
  vocabulary.json             元件 / 類別 / 事件種類詞彙（預測的 component 必須用這裡的 ID）
  pack_reader.py              讀資料包（pandas）：raw、10 分鐘統計、事件、「只看當下以前」的工具（raw_until / stats_until / events_until）
  baseline_assistant.py       基準助手：看到警報才用關鍵字猜元件（要超越它）
  score.py                    評分程式（只用標準函式庫）
  stream_client.py            WebSocket 回放的範例客戶端：基準助手的即時版
  opcua_client.py             OPC UA 的範例客戶端：讀 Z72 tag 的目前值，事件碼陣列有新碼就判斷、經 WS 送出
  requirements.txt
```

## 快速開始

```bash
pip install -r requirements.txt

# 1. 看一個資料包裡有什麼（會先核對 sha256）
python pack_reader.py packs/z72-starter-01

# 2. 跑基準助手，產生 predictions.jsonl
python baseline_assistant.py packs/ -o predictions/baseline.jsonl

# 3. 評分
python score.py --answers answers/ --predictions predictions/baseline.jsonl
```

## 範例資料包

| 資料包 | 機組 | 長度 | 風況 | 難度 | 重點 |
|---|---|---|---|---|---|
| `z72-starter-01` | 3 | 4 h | 額定（~13 m/s） | 入門 | 一台機組的元件慢慢劣化，約 40 分鐘後才出警報、接著跳機 |
| `z72-starter-02` | 4 | 6 h | 強風（~18 m/s） | 中等 | 兩台機組先後出問題；其中一個的手冊條目只寫 See [ABB] |
| `z72-starter-03` | 5 | 6 h | 陣風（紊流 0.30） | 有干擾 | 兩台機組有問題，其中一個是**感測器**故障；陣風讓每台機組（包括健康的）頻繁低風速停機 / 重啟，200+ 筆正常的狀態轉換混在事件裡 |
| `z72-starter-04` | 4 | 5 h | 額定（~13 m/s） | 感測器 vs 真故障 | 兩台機組送出**一模一樣**的主軸承溫度警報 / 跳機（262 / 240），一台是軸承真的壞了、一台只是溫度量測回路壞了；另一台的壓力感測器斷線 |

每個資料包都是每 10 s 一筆、102 個 tag（47 個真實 Bachmann tag、55 個自創，見 `tag_dictionary.json` 的 `source`）。
故障都是從某個時刻開始「慢慢變嚴重」：**警報出現前**，相關訊號已經跟同風場其他機組不一樣了。

範例是**開發集**：只涵蓋 16 種故障中的 7 種，每個都會出警報。正式評測會有沒看過的故障（合約 §10.1）。

**感測器故障**（`category: sensor_fault`）：機器本身是好的，只有某支感測器讀錯，處置完全不同（修感測器，不是換元件）。
- 有專屬故障碼的（例：229 壓力感測器斷線、242 軸承溫度 1 斷線、326 葉片 1 編碼器）看警報文字就知道。
- **讀值像真故障的**才是難題：例如軸承溫度 1 的量測回路劣化，送出的是和真的軸承磨耗一樣的 262 / 240。
  要比對同元件的第二支感測器（`WGEN_GnBrgTmp2`、`WGEN_GnStaTmp2`）、振動與負載：真故障通常好幾個訊號一起變，
  感測器故障只有那一支讀值不對。標準答案的 `component` 填被量測的元件（同真故障），`category` 才分得出來。

## 基準助手的成績

```
case：8　偵測到：8（100.0 %）

  元件正確率           87.5 %
  元件群組正確率      100.0 %
  類別正確率           75.0 %
  手冊引用 hit@1      100.0 %
  手冊引用 hit@3      100.0 %
  手冊引用 MRR@10       1.000
  延遲（中位 / 平均） +0 s / +0 s（7 個 case；相對第一個預期警報，負值＝提前）
  早期預警            0 個 case
  誤診（對到 case 但元件錯）1 筆
  誤報                0 次（0 筆、0 台機組）
  干擾判定（不評分）  0 筆，其中 0 筆在故障期間
```

它在範例上看起來不錯，因為範例的警報都很「乾淨」。它做不到的才是專題的重點：

- **早期預警**：它只看事件，一定等警報出來才反應。用時序訊號（例：跟同風場其他機組比、看趨勢）在警報前就找出問題。
- **感測器故障**：它只在警報文字點名感測器（sensor / encoder / temperature fault）時判 `sensor_fault`。風向標漂移、溫度量測回路劣化這種讀值像真故障的，它都判成 `real_fault`；機器本身是好的，處置完全不同。
- **元件定位**：「Discrepancy blade 1-3」它只猜到變槳系統，答案是葉片 1 的變槳系統（只拿到群組分）。
- **檢索**：它的手冊引用只是把出現過的警報碼列出來；警報出現前，要靠 RAG 判斷該查哪些條目。

## 寫自己的助手

1. 依時間往前走（例如每 10 分鐘一步）：用 `Pack.raw_until(t, ...)` / `Pack.stats_until(t)` / `Pack.events_until(t)` 取得 **t 以前**的資料——不要偷看未來（合約 §6）。時間可給 ISO 字串或 datetime，不帶時區者視為 UTC。
2. 找異常：跟同風場其他機組比、看趨勢、看 10 分鐘統計的 std 等。
3. 檢索：Z72 手冊（Appendix C）、`alarm_catalog.json` 的原因 / 處置、tag 字典的說明。
4. 每做出一次判斷就輸出一行 prediction（格式見合約 §6；`component` 用 `vocabulary.json` 的 ID）：

```json
{"pack_id": "z72-starter-01", "turbine_id": "WT002", "ts": "2026-03-02T01:40:00Z", "category": "real_fault",
 "component": "main_bearing", "manual_refs": [262, 240], "root_cause": "…", "actions": ["…"]}
```

5. `python score.py --answers answers/ --predictions your_predictions.jsonl --json report.json`

評分規則（合約 §8）：
- 每個 case 以**最後一次**判斷評元件 / 類別 / 手冊引用。
- 延遲從「最後一段連續正確」的第一筆算起：中途猜錯的元件記為誤診，狂猜換不到早期預警。
- 對不到任何故障的判斷算誤報。
- 預測檔請存成 UTF-8（PowerShell 5 的 `>` 會存成 UTF-16）。

## 即時回放（WebSocket）

老師開一個回放、給你 **token**。資料依模擬時鐘播出：
- 讀值、事件、10 分鐘統計，內容與資料包逐筆相同。
- 你在同一條連線送出判斷。
- 伺服器以「收到判斷時的模擬時間」蓋 `ts`。你不用（也不能）自己填時間，這樣才保證沒有偷看未來。

```bash
python stream_client.py ws://<伺服器>:8000/ws/replay --token <token> --check    # 先確認 token（不開始計時）
python stream_client.py ws://<伺服器>:8000/ws/replay --token <token>
python stream_client.py ws://<伺服器>:8000/ws/replay --token <token> --record received.jsonl   # 另存收到的訊息
```

- **兩種回放**：
  - **練習**：每次連線從頭播，寫程式時用。
  - **正式（evaluation）**：單次直播，從第一次連線開始計時，不能暫停或倒帶。斷線重連會補送已過去的資料，但時間不會倒回。
    想先確認 token 能用，請加 `--check`（`?check=true`），不會開始計時。
- **速度**由老師決定（例：60 倍＝ 1 秒運算對應 1 分鐘模擬時間）。回放不會等你：收得慢或想得久，判斷時間就晚。
  `stream_client.py` 示範「一個工作只收訊息、另一個做判斷」。
- 判斷的格式同 `predictions.jsonl` 的一行，加上 `"type": "prediction"`。可以帶 `id`，伺服器回 `ack` 時原樣附上：
  ```json
  {"type": "prediction", "id": 1, "turbine_id": "WT002", "category": "real_fault", "component": "main_bearing", "manual_refs": [262]}
  ```
  格式錯的會被退回（`ack` 的 `accepted: false` 與 `errors`）。情境播完後送的判斷不收。
- **連不上或被拒絕**：`stream_client.py` 會印出關閉碼與伺服器的說明。常見的有：
  - 4401：token 錯。
  - 4403：回放已撤銷或過期。
  - 4410：正式回放已結束。
  - 4412：練習回放用 `stream=false`，但老師還沒以 OPC UA 播出。
- **被斷線**：伺服器每 20 秒 ping 一次。程式整段卡在同步的大模型呼叫裡太久，會被斷線。判斷請放到另一個執行緒，或用非同步呼叫。
- **proxy**：`stream_client.py` 預設直連伺服器，不經過環境變數設定的 proxy；需要時加 `--use-env-proxy`。
- 訊息種類、欄位與關閉碼見合約 §12。

## OPC UA（像接真實 PLC）

老師用 `tools/opcua_server.py` 把回放以 OPC UA 播出（真實 Z72 PLC 走 OPC，這是最接近現場的接法）：
- 節點 ID 就是真實 PLC 的 item ID：`Z72.H01.WTUR.Z72PLC__UI_Loc_WTUR_State_TurSt`、
  `Z72.H01.Z72PLC__ActiveAlarm[0]` …（namespace `urn:windmindom:z72sim`，字串 NodeId `ns=<idx>;s=<item ID>`）。
  也可以從 `Objects/Z72/H01/WTUR/...` 瀏覽。匿名、唯讀。
- **只有目前值**：讀到的是各機組最新一筆讀值（`SourceTimestamp`＝那筆的模擬時間）與目前成立的警報 / 跳機碼
  （`ActiveAlarm` / `ActiveTrip1` / `ActiveTrip2`，各 21 格，依成立順序、空位 0）。兩次讀之間出現又消失的警報看不到；
  要每一筆讀值與 10 分鐘統計，用 WebSocket 回放或資料包。
- 合成 tag（真實 PLC 沒有的）一樣掛著，節點說明寫 `synthetic`；`WSpeedNacAvg10m` 由 server 從 `WSpeedNac` 算 10 分鐘平均。
- 模擬器狀態在 `WindMindOM.*`（`Status`：`running` / `finished` / `revoked` …、`SimTime`、`PackId`）。
- **判斷照樣經 WebSocket 送**：同一個 token 連 `ws://<伺服器>:8000/ws/replay?stream=false`（只收判斷、不再送資料），
  伺服器一樣蓋 `ts`，時鐘與 OPC UA 相同：正式回放在老師啟動 OPC UA server 時就開始計時；練習回放用老師這次啟動
  OPC UA server 的時間（還沒啟動會被拒絕，關閉碼 4412）。

```bash
python opcua_client.py opc.tcp://<伺服器>:4840/windmindom/ --ws ws://<伺服器>:8000/ws/replay --token <token>
python opcua_client.py opc.tcp://<伺服器>:4840/windmindom/          # 只看（不送判斷）
```

細節見合約 §13。

## 正式評測

老師會給新的盲測版資料包（格式相同，但沒有 `answers/`），或一個正式回放的 token。
- **用資料包**：你交 `predictions.jsonl`。
- **用回放**：判斷已經在伺服器上，老師直接下載（`tools/replay_runs.py <db> predictions <回放 id>`）。

老師用同一個 `score.py` 評分：

```bash
# 評分端：--answers 可直接給評分端版資料包目錄（內含 ground_truth.json）或答案目錄
python score.py --answers graded_packs/ --predictions student_predictions.jsonl --json report.json
```

## 維護者：重新產生範例

```bash
python tools/build_rag_starter_kit.py          # 在 repo 根目錄執行；固定起點與排程，資料可重產
python tools/build_rag_starter_kit.py --probe  # 只看事件與答案摘要（挑情境用）
```

同一份程式碼、同版 numpy / pyarrow 重跑，資料檔逐位元相同；manifest 的 `reproducibility.note` 是匯出器的通用說明（從 API 生成的情境無法重產），範例資料包請以本工具為準。
`.gitattributes` 讓 git 不轉換資料包的換行（Windows `core.autocrlf` 會讓 sha256 對不上）。
