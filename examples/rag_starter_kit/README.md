# Z72 RAG 維修助手 starter kit

給學生專題用的入門包：windMindOM 模擬 Z72 風場產生的**範例資料包**、讀取程式、一個陽春的**基準助手**，
以及**評分程式**。介面規格以 [資料介面合約 v1](../../docs/integration/rag_assistant_data_contract_v1.md) 為準。

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

每個資料包都是每 10 s 一筆、100 個 tag（45 個真實 Bachmann tag、55 個自創，見 `tag_dictionary.json` 的 `source`）。
故障都是從某個時刻開始「慢慢變嚴重」：**警報出現前**，相關訊號已經跟同風場其他機組不一樣了。

範例是**開發集**：只涵蓋 11 種故障中的 5 種，每個都會出警報。正式評測會有沒看過的故障（合約 §10.1）。

## 基準助手的成績

```
case：5　偵測到：5（100.0 %）

  元件正確率           80.0 %
  元件群組正確率      100.0 %
  類別正確率           80.0 %
  手冊引用 hit@1      100.0 %
  手冊引用 hit@3      100.0 %
  手冊引用 MRR@10       1.000
  延遲（中位 / 平均） +0 s / +0 s（4 個 case；相對第一個預期警報，負值＝提前）
  早期預警            0 個 case
  誤診（對到 case 但元件錯）1 筆
  誤報                0 次（0 筆、0 台機組）
  干擾判定（不評分）  0 筆，其中 0 筆在故障期間
```

它在範例上看起來不錯，因為範例的警報都很「乾淨」。它做不到的才是專題的重點：

- **早期預警**：它只看事件，一定等警報出來才反應。用時序訊號（例：跟同風場其他機組比、看趨勢）在警報前就找出問題。
- **感測器故障**：它一律判 `real_fault`。風向標讀值錯誤時，機器本身是好的，處置完全不同。
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

## 正式評測

老師會給新的盲測版資料包（格式相同，但沒有 `answers/`）。你交 `predictions.jsonl`，老師用同一個 `score.py` 評分：

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
