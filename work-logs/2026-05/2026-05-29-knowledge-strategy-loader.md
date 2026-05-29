# Work Log — 2026-05-29 — Knowledge RAG 策略檔載入器（M5-1 第一塊）

- **Issue**: WMOM-20260529-03
- **Milestone**: M5（Knowledge / RAG + 現場 mobile UI）
- **Branch**: claude/gifted-maxwell-1S0YV
- **Session 類型**: autonomous daily worker（cron 20:00 Asia/Taipei）

---

## 1. 為什麼做這個（決策樹）

Preflight baseline 完全綠：backend **570 passed / 1 xfailed**、git clean、無 blocker / 無 regression
→ 決策樹第 1、2 條不觸發。

最新 handoff（5/29 docs-reorg + mockusers）指向：M1-M4 100%，下一個大局是 **EPIC-M5（RAG + mobile UI）**。
ISSUES.md 頂部 M5-1「Knowledge module 後端 ingest/retrieve/strategy_loader/alert_handler」標 🔵 autonomous。

挑 **strategy_loader.py** 作為 M5 第一塊，理由（無設計歧義 + 完全 autonomous + 單 session 可完工）：
- **schema 已完整 spec**：`docs/product/MVP_ARCHITECTURE.md` §3.5 給了 strategy.yaml 完整範例
  （chunking / embedding / retrieval），零設計歧義。
- **零外部依賴**：純 YAML 解析 + pydantic 驗證，不需 ChromaDB（M5-2）、不需 RAG_Ultimate 真實
  artifact（M5-3 🟡 等劉老師 / research 端）、不需 embedding model 下載。
- **是整個 M5-1 的地基**：ingest / retrieve / alert_handler 都要共用這份「載入 + 查詢用同一組參數」
  的契約物件，先把契約鎖死，後續模組才有型別安全的依賴。

knowledge module 此前只有空的 `__init__.py`，這是 M5 第一次寫 code。

---

## 2. 做了什麼

### `modules/knowledge/strategy_loader.py`（+219 行）

- **例外階層**（讓 service 啟動 / settings 切換能精準回報）：
  `StrategyLoadError`（基底）→ `StrategyFileNotFoundError` / `StrategyParseError` / `StrategyValidationError`。
- **pydantic v2 schema**（全部 `extra="forbid"` 嚴格契約 — 策略檔 typo 在啟動時就炸，不留到 retrieve）：
  - `ChunkingStrategy`：method（Literal semantic/fixed/recursive）/ size(>0) / overlap(>=0)；
    model_validator 鎖 **overlap < size**。
  - `EmbeddingStrategy`：model(非空) / dimension(>0) —— query 端必須與灌庫相同。
  - `RetrievalStrategy`：algorithm（Literal vector/bm25/hybrid_bm25_vector）/ top_k(>0) /
    rerank / rerank_model；model_validator 鎖 **rerank=True ⇒ 必須有 rerank_model**。
  - `StrategyMeta`（可選）：name / version / oem_model / vector_store_file / source ——
    讓前端 / settings 顯示「現在載入哪份策略、對應哪個 OEM、哪個向量檔」。
  - `RagStrategy`：chunking + embedding + retrieval 必填、meta 可選；`from_dict` / `from_yaml_str` 類方法。
- **`load_strategy(path)`** 主入口：檔案不存在→FileNotFound、IO 失敗→LoadError、空檔/語法錯→Parse、
  schema 不合→Validation。

### `modules/knowledge/strategies/rag_strategy_z72_manual.example.yaml`（+28 行）

Z72 手冊策略 example placeholder（M5-3 真實檔 ready 前用），對齊 §3.5 範例值
（semantic/512/50、bge-large-zh-v1.5/1024、hybrid/top_k 5/rerank bge-reranker-v2-m3）。
供 loader 測試與本機 demo；真實檔由 RAG_Ultimate Phase 3 交付（🟡）。

### `modules/knowledge/tests/test_strategy_loader.py`（31 tests，含 review 後補的邊界 / IO / meta 測試）

- example 契約檔存在 + 逐欄位鎖值（防誤改）
- happy path + 預設值（overlap 0 / rerank False / meta None）+ from_yaml_str↔from_dict 等價
- 嚴格 schema：頂層 typo + 子區塊 typo 都被擋
- 約束：overlap<size / top_k>=1 / dimension>0 / method Literal / rerank 需 model / 缺必填區塊
- 例外階層：FileNotFound（含目錄路徑）/ 基底可 catch / 壞 YAML / 空檔 / 頂層非 mapping / schema 不合

---

## 3. Verify（zero regression）

| 項目 | 改前 | 改後 |
|---|---|---|
| backend `pytest modules/{workflow,cost,reporting}/tests/` | 570 passed / 1 xfailed | **570 passed / 1 xfailed**（未動既有） |
| + `modules/knowledge/tests/` | （無） | **+31 passed / 1 skipped** → 合計 601 passed / 1 skipped / 1 xfailed |
| frontend | 59 passed | **未動**（純 backend 新增，零 frontend 變更） |

---

## 4. Code review

跑 `code-reviewer` subagent 兩輪對 diff review，**兩輪獨立都判 Needs revision** 且核心 must-fix 高度重疊
（例外契約誠實性 + `pytest.raises(Exception)` 不鎖型別）。彙整處置：

| 級別 | finding | 處置 |
|---|---|---|
| **must** | `rerank_model="   "` / `embedding.model=" "` 空白繞過非空驗證，延遲到 runtime 才爆 | **採納**：embedding/retrieval model 改用 `str_strip_whitespace=True` config，去空白後被 min_length / validator 擋；補 4 個邊界 test（空字串 + 純空白 × 兩欄位） |
| **must** | `load_strategy` 的 OSError 路徑 raise 基底 `StrategyLoadError`，與 docstring「三子類精準分流」矛盾 | **採納**：新增 `StrategyReadError(StrategyLoadError)` 專表「有檔但讀不到」，docstring Raises 補上；加權限 denied test（root 環境 skip） |
| **must** | 兩個 test 用 `pytest.raises(Exception)` 遮蓋實際型別，例外契約形同虛設 | **採納**：改 `pytest.raises(pydantic.ValidationError)` 並加註解說明「直接建構子拋 pydantic 原生例外、非應用層 StrategyValidationError」 |
| **should** | `StrategyMeta` 套 `extra="forbid"` 與前向相容矛盾（RAG_Ultimate meta schema 演進快） | **採納**：meta 改 `extra="ignore"` + docstring 說明刻意與核心三段不同；加 test 驗未知 meta key 被忽略 |
| **should** | `_STRICT` 命名誤導（私有常數 vs 共用設定） | **採納**：rename `_STRICT_CONFIG` + 新增 `_STRICT_STRIP_CONFIG` |
| **should** | module docstring「不重新 embed」與 §3.5「SOP 文件自己 chunk+embed」矛盾 | **採納**：改寫 docstring 區分「手冊預計算交付 vs SOP 由 ingest 用同策略 embed」 |
| **should** | `vector_store_file` 無格式驗證，M5-3 直接 `Path()` 有穿越風險 | **採納**：加 `pattern=^[A-Za-z0-9_\-.]+\.parquet$` 限純檔名 + test |
| **should** | test `sys.path.insert` hack（建議改 pyproject pythonpath） | **不採納（本 session）**：repo 既有 9 個 test 檔全用此慣例，只改本檔反不一致；屬獨立 infra issue（pytest rootdir 設定）留待專門 session |
| **nice** | utf-8-sig 容 BOM / example YAML 欄位順序 / 補 OSError test | **採納**：read 改 `utf-8-sig`、example 改 chunking→embedding→retrieval→meta、加 BOM 載入 test |
| **nice** | schema_version 前向相容欄位 / `_minimal_dict` 改 fixture / `data: object` 型別 | **不採納**：schema_version 屬投機（meta.version 已在），fixture 現回傳新 dict 行為正確，`object` 對 isinstance guard 是最誠實型別 —— 皆留意但不動 |

採納後重跑：knowledge 24→**31 passed / 1 skipped**（skip=root 繞過 chmod 的權限 test）、
backend 合計 **601 passed / 1 skipped / 1 xfailed**，既有零 regression。

---

## 5. 下次 session 接手建議

- **M5-1 續做**：strategy_loader 已就位（契約地基）。下一塊建議 `ingest.py` 或 `retrieve.py`，
  但兩者都需 **ChromaDB（M5-2）依賴**（`chromadb` 未在 requirements.txt，需先 `pip install` 並加進
  requirements）。若要保持「零新依賴 autonomous」，可先做 `alert_handler.py` 的**純邏輯部分**
  （警報事件 → 構造 query 字串：警報碼 + 機型 + 異常 tag），把 retrieve 串接留 interface stub。
- **M5-3（🟡）**：真實 strategy.yaml + parquet 向量檔需 RAG_Ultimate Phase 3 產出 → 等劉老師 / research 端。
  目前用 example placeholder 跑通 loader 契約。
- 其他既有候選不變：真 component render 測試（需 jsdom setupFiles + npm i @testing-library/jest-dom）/
  WMOM-20260519-01（需劉老師會計語意決策 🟡）/ WMOM-20260513-02 demo orchestrator（含 product decision 🟡）/
  WMOM-20260509-F6（PostgreSQL，M6，需 docker postgres 🔵）。

---

## 6. 檔案異動清單

```
新  modules/knowledge/strategy_loader.py                              （載入器 + pydantic schema + 例外階層）
新  modules/knowledge/strategies/rag_strategy_z72_manual.example.yaml （Z72 策略 example placeholder）
新  modules/knowledge/tests/__init__.py
新  modules/knowledge/tests/test_strategy_loader.py                   （24 tests）
改  work-logs/2026-05/2026-05-29-knowledge-strategy-loader.md（本檔）
改  ISSUES.md / STATUS.yaml
```
