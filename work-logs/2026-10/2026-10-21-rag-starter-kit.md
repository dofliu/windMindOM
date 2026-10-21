# 2026-10-21 — WMOM-20261021-09：RAG 學生專題 starter kit + 介面合約 v1（EPIC-DS Phase 3d）

> Session 類型：實作
> Session 長度：中
> 主導：Claude（劉老師選定「繼續做 -09」，評分欄位由劉老師確認）
> 結果：WMOM-20261021-09 done

---

## 1. Session 目標

學生專題要開發外部 RAG 維修助手，需要：
- 穩定的介面合約：v0 草案定稿為 v1。
- 2–3 個範例資料包：簡單、中等、有干擾。
- 讀取與評分範例程式。

issue 註明合約定稿前要劉老師確認欄位，尤其是 ground truth 的評分欄位。

## 2. 劉老師的決定（開工時確認）

| 問題 | 決定 |
|---|---|
| 診斷用什麼自動評分 | 元件（封閉詞彙）＋類別；`root_cause` 留給人工 / LLM |
| 手冊引用怎麼評 | 事件碼（Appendix C 條目）hit@k / MRR |
| 時效 | 延遲＋早期預警 |
| 總分 | 各項指標分列，不合成 |

記錄於 DEC-20261021-04。

## 3. 實際完成

### 3.1 合約 v1

`docs/integration/rag_assistant_data_contract_v1.md`：
- 角色與流程、版本規則。
- 資料包 / 事件 / 標準答案的欄位表、時間慣例。
- 受測端 `predictions.jsonl`、評分規則與指標定義、詞彙、模擬與真實的差異、開發集 vs 正式評測。

`CONTRACT_VERSION` 0.1 → 1.0；0.1 時存下的答案欄位相同，匯出時只把這個舊標籤轉成 1.0。

### 3.2 starter kit（`examples/rag_starter_kit/`）

- **`vocabulary.json`**：11 元件 / 8 群組 / 類別 / 事件種類 / 停機原因。
- **`pack_reader.py`**（pandas）：
  - sha256 核對。
  - `raw_until` / `stats_until` / `events_until`：只看當下以前的資料。
- **`baseline_assistant.py`**（只用標準函式庫）：看到警報才用關鍵字猜元件。
- **`score.py`**（只用標準函式庫）：評分程式。
- **README**（繁中）。
- **範例資料包**：3 個盲測版（共約 4 MB），答案另放 `answers/`。

| 資料包 | 機組 / 長度 / 風況 | 故障（onset → 第一個警報） |
|---|---|---|
| 01 | 3 / 4 h / rated | 主軸承磨耗（40 分鐘） |
| 02 | 4 / 6 h / strong | 偏航煞車液壓洩漏（6.5 分鐘）、變頻器冷卻（14 分鐘，See [ABB]） |
| 03 | 5 / 6 h / gusty | 風向標漂移 sensor_fault（15 分鐘）、葉片 1 變槳不平衡（16 分鐘）；238 筆啟停狀態轉換 |

- 挑情境用 `--probe`。第一版嚴重度增長太快（警報在 onset 後數分鐘內），早期預警沒有意義，所以降低增長率。
- 檢查過 key signal 確實在警報前就偏離同風場其他機組。

### 3.3 重產工具 `tools/build_rag_starter_kit.py`

- 每個範例從全新模擬器、各自的暫存 DB 生成。
- **踩到的坑**：
  - 只釘住 `simulator.engine.utc_now` 時，兩次產生的資料從第一筆就不同。
  - 原因是 `wind_model.set_override` 從「現在」的自動風況平滑過渡，用的是 `wind_model` 自己的 `utc_now`。
  - 兩處都釘住後，兩個獨立行程產生的資料檔 sha256 相同。

### 3.4 匯出器

- `export_scenario_pack(pack_id=...)`：pack_id 嚴格驗證。
- `export_ground_truth()`：把答案寫在資料包之外。

### 3.5 Code review（code-reviewer：Needs revision → 全修）

Must-fix：
- **M1 早期預警可被狂猜換到**：審查者實測，警報前把 11 個元件都猜一遍、最後才答對，5/5 case 都拿到早期預警。
  - 改為「最後一段連續正確」的起點才算診斷出來；最後錯就沒有時效分。
  - 加「誤診」計數（對到 case 但元件錯）。
- **M2 superseded / pre_existing 時間窗**：
  - superseded 原本直接丟掉，再注入前的正確診斷變成誤報。改為併進取代它的 case（最早的 onset 與第一個警報）。
  - pre_existing 開始時間不明，原本任何正確診斷都算早期預警。改為不評時效。
- **M3 評分程式碰到壞行會整個中斷**：時間溢位、極深巢狀 JSON、UTF-16 檔（PowerShell 5 的 `>`）、BOM、list 型的 component。改為列出原因後繼續評分，或回 exit 2 加說明。
- **M4 流程產物**：本 work-log、DEC-20261021-04、狀態檔一起 commit；新增重產性測試。

Should-fix：
- **S1** `--answers` 可直接給評分端版資料包目錄（`ground_truth.json`）。
- **S2** `nuisance` 明定 v1 不評分；修正合約「低風速停機列在 unattributed_events」的錯誤說法。
- **S3** 誤報改以次數計（同機組同元件 30 分鐘內算一次）。
- **S4** 新增 `stats_until`（只回已結束的窗）。
- **S5** 延遲報樣本數。
- **S6** 合約標籤只轉換 0.1：將來 1.1 時，1.0 的答案不能冒充 1.1。
- **S7** `pack_id` 改用 fullmatch，頭尾必須是英數。
- **S8** `.gitattributes`：Windows `core.autocrlf` 會改 JSON 換行，讓 sha256 對不上。
- **S9** 文件註明 v1 元件與類別一對一。
- **S10** 文件同步、錯誤訊息改繁中、文字報告列出全部格式錯誤行（最多 20 行）。
- **S11** case 明細改用 ASCII 標記：cp950 主控台導向檔案時 `✓` 會出錯。
- **S12** 每個範例用獨立 DB（scenario_id 與建置順序無關）、`--only` 驗證 id、文件註明 pyarrow 版本與其他時鐘。
- **S13** 補測（見 §4）。
- **S14** mypy 乾淨。

Nice-to-have 採用：
- MRR@10（列一長串碼換不到分數）。
- `raw_until` 把時間條件推進 Parquet 讀取、欄位去重。
- 合約加「開發集只涵蓋 5/11 種故障」、只給受測端 kit 目錄。
- 基準程式找不到資料包時回 exit 2。

## 4. 驗證

### 4.1 自動測試

- **`tests/test_rag_starter_kit.py`（31 項）**：
  - 詞彙涵蓋故障庫。
  - commit 的資料包完整、盲測、與目前匯出器一致；答案與資料包對得上。
  - 評分規則：完美診斷、最後 / 連續正確、狂猜、superseded、pre_existing、誤報次數、hit@k 邊界與 @10、時間邊界與同時刻、壞行、BOM / UTF-16、重複答案、評分端版目錄。
  - 基準成績（README / 合約引用的數字）。
  - 讀取器不回未來資料。
  - 小情境的產生工具可重產。
- **mutation**：35 項全部被抓到。第一輪 4 項存活：hit@3 邊界、重複答案（測試順序讓 UTF-16 先擋掉）、基準重複碼、時鐘只釘一處。補測後全抓到。
- **完整 backend**：1772 passed / 7 skipped / 1 xfailed（原 1741）。
- **frontend**：未改動；tsc、vitest 1512、build 都通過。

### 4.2 端對端功能測試（真實伺服器，隔離 DB）

流程：
1. 啟動伺服器、選情境模式、設風況。
2. 生成 2 h 情境（2 個故障）。
3. 下載 `/pack` 與 `/pack/full`；確認權限：未登入 401、employee 403、主管 200。
4. 用 starter kit 核對、讀取、跑基準與評分。
5. 答案卷端點與資料包答案一致。
6. CLI 與 HTTP 匯出的資料檔 sha256 相同。

結果：15 / 15 通過。

## 5. 產出清單

### 新增檔案

- `docs/integration/rag_assistant_data_contract_v1.md`
- `examples/rag_starter_kit/`（README、vocabulary.json、pack_reader.py、baseline_assistant.py、score.py、requirements.txt、.gitignore、packs/、answers/）
- `tools/build_rag_starter_kit.py`
- `tests/test_rag_starter_kit.py`
- `.gitattributes`
- 本 work-log

### 修改檔案

- `modules/monitoring/server/scenario_pack.py`（pack_id、export_ground_truth、合約標籤）
- `modules/monitoring/simulator/ground_truth.py`（CONTRACT_VERSION 1.0）
- `modules/monitoring/tests/test_scenario_pack.py`、`test_scenario_endpoints.py`
- 文件：
  - `docs/product/EPIC-DS_realistic_data_source.md`（§5 指向 v1、§6.9）
  - `docs/product/decision_log.md`（DEC-20261021-04）
  - `ISSUES.md`、`STATUS.yaml`、`CLAUDE.md`、`TODO.md`

### 動了狀態的 issue

- WMOM-20261021-09：open → done

## 6. 下次怎麼接手

- **把 kit 交給學生**：只給 `examples/rag_starter_kit/`。正式評測用另外生成的盲測版資料包（`/pack` 或 CLI），答案留在評分端。
- **-12**：健康機組偶發 T2 336（小題）。
- **-06 WS 回放**：事件與預測格式沿用合約 v1，`ts` 改以收到資料的時刻為準。
- **-08**：加故障要同步加詞彙（次版本）；加入 nuisance / healthy case 時，評分要補上 `nuisance` 的計分規則。
