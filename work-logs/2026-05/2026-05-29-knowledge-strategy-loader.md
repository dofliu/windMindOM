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

### `modules/knowledge/tests/test_strategy_loader.py`（+264 行，24 tests）

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
| + `modules/knowledge/tests/` | （無） | **+24 passed** → 合計 594 passed / 1 xfailed |
| frontend | 59 passed | **未動**（純 backend 新增，零 frontend 變更） |

---

## 4. Code review

跑 `code-reviewer` subagent 對 staged diff —— 處置見下方 commit 前更新。

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
