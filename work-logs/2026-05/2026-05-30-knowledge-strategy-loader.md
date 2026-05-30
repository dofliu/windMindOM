# 2026-05-30 — Knowledge module M5-1 第一塊：RAG 策略檔載入器 strategy_loader

> Autonomous daily worker session（2026-05-30 20:00 Asia/Taipei，雲端 sandbox）。
> Issue：**WMOM-20260530-01**（新開）。Branch：`claude/gifted-maxwell-3pMce`。

---

## 1. 為什麼做這個

Preflight baseline 完全綠（backend `pytest modules/{workflow,cost,reporting}/tests/`
→ **570 passed / 1 xfailed**；frontend vitest **59 passed**；working tree clean、無 blocker、
無 regression）—— 決策樹第 1、2 條不觸發。

掃 5/29 兩份 handoff（docs-reorg / mockusers）+ ISSUES.md 頂部「🎯 未來大目標」：
- 5/26→5/29 已連四 session 推「frontend 測試覆蓋」；下一階段「真 component render 測試」
  需先補 `vitest.config.ts` jsdom setupFiles + `@testing-library/jest-dom`，5/28、5/29 handoff
  都標記**脆弱、建議獨立 session**——非今日最佳 ROI。
- 剩餘 open issue 多為 🟡（需劉老師決策：退料 guard 會計語意 / demo orchestrator product
  decision / UI v2）或 M6 環境（F6 PostgreSQL 需 docker）或物理模型（高風險）。

選 **EPIC-M5-1（Knowledge module 後端）標 🔵 autonomous-friendly** 開第一塊。M5 是 PMF
關鍵（警報→30 秒 RAG），但整個 M5-1（ingest/retrieve/strategy_loader/alert_handler）+ M5-2
（ChromaDB）太大、且 M5-3/M5-4 灌手冊需 RAG_Ultimate Phase 3 artifact（🟡 未 ready）。

**切入點挑 `strategy_loader.py`**——M5 最底層 contract，理由：
- **零外部依賴可完工**：只解析 / 驗證 yaml，不碰 ChromaDB / sentence-transformers /
  GPU / 向量檔 → sandbox 可完整單元測試、零脆弱。
- **defines the contract**：把 RAG_Ultimate 交付的 `rag_strategy_*.yaml` 變成 typed +
  validated + immutable 的 `RagStrategy`，供之後 ingest/retrieve/alert_handler 共用。
- **直接解一個已知風險**：MVP_ARCHITECTURE 風險表「Phase 3 strategy 還沒 ready 就要交
  artifact → 先用 baseline placeholder」→ 本檔的 `baseline_strategy()` +
  `load_strategy_or_baseline()` 即為此設。
- 設計**無歧義**：MVP_ARCHITECTURE.md §3.5 已給完整 strategy.yaml schema 範例。

---

## 2. 完成內容

### `modules/knowledge/strategy_loader.py`（新，~316 行）

- **4 個 frozen dataclass**：`ChunkingStrategy`（method/size/overlap）、`EmbeddingStrategy`
  （model/dimension）、`RetrievalStrategy`（algorithm/top_k/rerank/rerank_model）、
  `RagStrategy`（三者 + 選填 name/version/source_path）。全 frozen → 載入後不可變。
- **`StrategyError(ValueError)`**：統一領域例外，訊息一律繁中指出哪個欄位出錯。
- **型別收窄 helper**：`_require_mapping/_require_str/_require_int/_require_bool/_optional_str`
  把 PyYAML `safe_load` 的 `Any` 收窄到精確型別（避免 `Any` 外洩，符合 CLAUDE.md §7）。
  `_require_int` 特別拒絕 `bool`（Python bool 是 int 子類，易誤判）。
- **驗證規則**：size>0、overlap>=0 且 overlap<size、dimension>0、top_k>0、
  rerank=true 必須有 rerank_model、各必填字串非空。
- **`parse_strategy(raw, *, source_path)`**：解析已 load 的 dict（與檔案 IO 解耦，方便測試
  / 未來從 DB 來源重用）。
- **`load_strategy(path)`**：檔案層（缺檔 / 空檔 / 非法 yaml 全轉 `StrategyError`）。
- **`baseline_strategy()`**：placeholder 退路（小、CPU 友善、多語：
  `paraphrase-multilingual-MiniLM-L12-v2` dim 384、fixed 512/50、vector top_k 5、無 rerank）。
- **`load_strategy_or_baseline(path)`**：載入失敗 log warning 後退回 baseline——保證 knowledge
  module 永遠有可用策略可開機。

### `config/rag_strategy_z72_manual.yaml`（新，reference 樣本）

對齊 MVP_ARCHITECTURE §3.5 範例（semantic 512/50、bge-large-zh-v1.5 dim 1024、
hybrid_bm25_vector top_k 5 + bge-reranker-v2-m3）。Phase 3 正式策略檔就位直接覆蓋即可（schema 不變）。

### `modules/knowledge/tests/test_strategy_loader.py`（新，38 tests）

- parse happy path 6（全欄位映射 / 選填缺省 / **數字 version coerce 成字串+warning** / **容器型 metadata 拒絕** / rerank=false 免 rerank_model / frozen 不可變）
- 結構紅線 3（非 mapping root / 三區塊各自缺漏 parametrize / section 非 mapping）
- chunking 驗證 6（缺欄 / bool 非 int / size>0 / overlap>=0 / overlap<size / method 非空）
- embedding 驗證 2（dimension>0 / model 必填）
- retrieval 驗證 5（top_k>0 / rerank 非 bool / rerank=true 無 model / rerank_model 空字串 / **rerank=false 帶 rerank_model→丟棄+warning**）
- load_strategy 檔案層 7（載入 repo reference 樣本守 schema drift / 寫入 yaml / 缺檔 / 空檔 / 壞 yaml / **超大檔拒絕** / **OSError 包成 StrategyError** / **非 UTF-8 包成 StrategyError**）
- baseline 2（自洽且通過自身驗證 / round-trip 回 parse 等價）
- load_strategy_or_baseline 4（有效檔回原策略 / 缺檔退 baseline+warning / 內容非法退 baseline+warning / **OSError 也能退 baseline**）

### `modules/knowledge/__init__.py`

從空殼改為 re-export strategy_loader 公開 API + 更新 module roadmap 註解（✅ strategy_loader / ⬜ ingest/retrieve/alert_handler）。

### requirements

- `requirements.txt`：加 `pyyaml>=6.0`（runtime；strategy_loader 解析策略檔）。
- `requirements-dev.txt`：加 `types-PyYAML>=6.0`（type check 用 stub）。

---

## 3. Verify（zero regression）

| 項目 | 改前 | 改後 |
|---|---|---|
| `pytest modules/knowledge/tests/` | （無此檔） | **38 passed**（含 code review 後補的 7 條 regression test） |
| `pytest modules/{workflow,cost,reporting,knowledge}/tests/` | 570 passed / 1 xfailed | **608 passed / 1 xfailed**（+38 新，零 regression） |
| frontend | 59 passed | **未動**（純 backend 新增） |

mypy 非本專案 verify gate（無 mypy 設定檔；routine backend gate = pytest）。source 模組僅
yaml stub 解析 noise（已加 types-PyYAML）；test 檔的 mypy note 來自刻意對 `object` 型 dict
做變異以驗證 validation（pytest 31/31 綠）。

---

## 4. Code review

跑 `code-reviewer` subagent 對 staged diff（兩次回合一致）：**2 must / 4 should / 2-3 nice，Needs revision → 採納後可 approve**。處置：

| # | 級別 | 內容 | 處置 |
|---|---|---|---|
| 1+2 | **must** | `load_strategy` 的 `read_text()` 可拋 `OSError`/`PermissionError`/`UnicodeDecodeError`，不是 `yaml.YAMLError`→ 穿透破壞 docstring「Raises: StrategyError」契約，連帶讓 `load_strategy_or_baseline` 的「永遠有 baseline 可開機」保證在磁碟異常時失守（同一根因） | **採納**：`read_text` 包 `except (OSError, UnicodeDecodeError)` → `StrategyError`；+2 regression test（mock PermissionError / 非 UTF-8）+ or_baseline 退路 test |
| 3 | should | RAG_Ultimate 常把 `version: 2026`/`3.0` 寫成未加引號數字→ PyYAML 解成 int/float → 嚴格 `_optional_str` 拒絕 → 一份合法策略檔靜默退回 baseline | **採納**：新增 `_optional_meta_str`（僅 name/version 用），對 int/float scalar 寬鬆 coerce 成字串 + warning 提醒加引號；容器型別仍拒絕；+2 test |
| 4 | should | `rerank=false` 卻帶 `rerank_model` → 靜默保留成矛盾狀態，下游 retrieve.py 會混淆 | **採納**：丟棄該欄位 + log warning；+1 test |
| 5 | should | invalid-content fallback test 未斷言 warning log（與 missing-file test 不對稱） | **採納**：補 caplog 斷言 |
| 6 | should | test `_REPO_ROOT = parents[3]` 路徑脆弱 | **未採納**：repo 結構固定（`modules/knowledge/tests/` 深度確定），且 `test_loads_repo_reference_sample` 的本意正是**守 schema drift**，pytest.skip 反而會讓樣本不見時無聲略過——留現狀更符合測試意圖 |
| 7 | should→nice | 加 64 KB file size guard（一份 agent 評 must：`/admin/settings` 路徑攻擊面） | **採納**：cheap defensive guard `_MAX_STRATEGY_FILE_BYTES`；+1 test |
| 8 | nice | `StrategyError(ValueError)` 易被 broad `except ValueError` 吞 | **未採納**：刻意繼承 ValueError 換取呼叫端 ergonomics；FastAPI route 應明確 `except StrategyError`，留註解 |
| 9 | nice | `baseline_strategy()` 每次 new object，可 cache/常數化 | **未採納**：frozen dataclass 不可變、alloc 微不足道；保留函式形式語意較清楚 |

採納後重跑：knowledge 31→**38 tests**、全 backend **608 passed / 1 xfailed**、零 regression。

---

## 5. 下次 session 接手建議

- **M5-1 續做**：`retrieve.py`（query → top-k chunks）需 ChromaDB（M5-2），sandbox 可能未裝
  → 建議先確認 `chromadb` 是否可在 sandbox pip install；若可，下一塊做 `ingest.py` 的純切塊
  邏輯（chunk 切分可純函式測，embed/寫 vector store 再 stub）。
- **alert_handler.py**：警報事件 → 構造 query（警報碼 + 機型 + 異常 tag）→ 呼叫 retrieve。
  query 構造是純函式，可先做 + 測，retrieve 用 fake。
- `strategy_loader` 已就緒可被上述模組直接 import 使用。
- 其他候選不變：frontend component render 測試（需 jsdom setupFiles，獨立 session）/
  🟡 需劉老師決策的 issue。

---

## 6. 檔案異動清單

```
新  modules/knowledge/strategy_loader.py        （載入 + 驗證 RAG 策略 → typed frozen dataclass + baseline 退路）
新  modules/knowledge/tests/__init__.py
新  modules/knowledge/tests/test_strategy_loader.py（38 tests，含 code review 後 7 條 regression）
新  config/rag_strategy_z72_manual.yaml          （reference 樣本，對齊 MVP_ARCHITECTURE §3.5）
改  modules/knowledge/__init__.py                （空殼 → re-export 公開 API + roadmap 註解）
改  requirements.txt                             （+pyyaml）
改  requirements-dev.txt                         （+types-PyYAML）
改  ISSUES.md / STATUS.yaml / 本 work-log
```
