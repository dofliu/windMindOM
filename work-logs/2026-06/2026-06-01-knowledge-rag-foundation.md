# 2026-06-01 — Knowledge module RAG 基礎層（WMOM-20260601-01）

> Autonomous daily worker session（cron 20:00 Asia/Taipei）。
> Branch：`claude/gifted-maxwell-1CWqk`。Issue：**WMOM-20260601-01**。
> Epic：**EPIC-M5（Knowledge / RAG + 現場 mobile UI）** 的 M5-1 起手。

---

## 1. 開工 / 決策

- Preflight baseline 全綠：backend `pytest modules/{workflow,cost,reporting}/tests/` → **570 passed / 1 xfailed**；
  無 blocker、main 無 regression（決策樹第 1、2 條不觸發）。
- 最新 handoff（5/29 docs-reorg + mockusers）：M1-M4 100%、剩餘 open 多需劉老師決策或 M6 環境。
  ISSUES.md 頂部「🎯 未來大目標」標 **🔵 autonomous-friendly** 的最高價值項是 **M5-1 Knowledge module 後端**
  （PMF 關鍵）。設計規範已在 `docs/product/MVP_ARCHITECTURE.md` §3.5，無設計歧義 → 認領。
- **Simulator-first 切法**（CLAUDE.md §15）：M5-1 先做「不依賴 ChromaDB / 不依賴 RAG_Ultimate Phase 3 向量檔」
  的純 Python 基礎層 —— schema + strategy loader + **baseline keyword retriever** + alert handler。
  這樣純 simulator 模式即可 demo「警報 → 手冊處置段落」，等 M5-2 ChromaDB / M5-3 真向量檔 ready 再升級
  （與 MVP_ARCHITECTURE §3.5 升級表一致：retrieval 換 retriever class，schema / handler 不動）。

## 2. 範圍（M5-1 基礎層，本 session）

| 檔案 | 內容 |
|---|---|
| `modules/knowledge/schemas.py` | pydantic v2 模型：RagStrategy(+sub) / KnowledgeChunk / RetrievalQuery / RetrievedChunk / AlertEvent / AlertRagResult |
| `modules/knowledge/strategy_loader.py` | 載入 `rag_strategy_*.yaml` → RagStrategy；檔案缺失 → baseline default（M5-3 placeholder 契約） |
| `modules/knowledge/corpus.py` | 載入 baseline 知識庫 JSON → KnowledgeCorpus（by_alarm_code / filter(oem,model)） |
| `modules/knowledge/retrieve.py` | `Retriever` Protocol + `BaselineKeywordRetriever`（純 Python，告警碼命中 + 關鍵字 + 文字 overlap 加權，無外部依賴） |
| `modules/knowledge/alert_handler.py` | `AlertHandler.on_alert(event)`：警報事件 → 構造 query → retrieve top-k → AlertRagResult |
| `modules/knowledge/config/rag_strategy_z72_manual.yaml` | baseline 策略檔（對齊 MVP_ARCHITECTURE §3.5 範例） |
| `modules/knowledge/data/baseline_corpus_z72.json` | baseline 知識庫 placeholder —— 對齊 `fault_engine.FAULT_SCENARIOS` 11 個真實 Z72/Bachmann 告警碼的處置 SOP 段落 |
| `modules/knowledge/tests/*` | pytest：schemas / strategy_loader / corpus / retrieve / alert_handler |

**不做**（留後續 issue）：ChromaDB 整合（M5-2）、真向量檔載入（M5-3 🟡 需 RAG_Ultimate）、
FastAPI knowledge router（M5-6 串前端）、`/field/` mobile UI（M5-5）。

## 3. 設計要點

- baseline corpus 的告警碼直接取自 `modules/monitoring/simulator/physics/fault_engine.py` 的
  `FAULT_SCENARIOS`（11 scenario，含 Z72 Event 021/027/041 等真實 Bachmann 告警碼），確保
  「警報 → RAG」demo 用的是模擬器真的會觸發的碼。
- `BaselineKeywordRetriever` 評分 = 告警碼命中（強 boost）+ chunk 關鍵字命中比例 + query/chunk 文字 token overlap，
  clamp 0..1，依 oem/model 過濾，依 strategy top_k 截斷，丟棄零分；`match_reason` 繁中可解釋（前端透明度）。
- `is_baseline=True` 標記在 AlertRagResult，讓前端 / 未來 router 知道目前是 placeholder 檢索（非真向量）。

## 4. Verify（zero regression）

| 項目 | 結果 |
|---|---|
| 新增 `modules/knowledge/tests/`（5 檔） | **54 passed** |
| backend 全套 `pytest modules/{workflow,cost,reporting,knowledge}/tests/` | **624 passed / 1 xfailed**（570 原 baseline + 54 新；零 regression） |
| `Any` 使用 | 0（CLAUDE.md §7） |
| 端到端 smoke | 警報碼 21 + 變頻器描述 → top1 = `z72-sop-converter-cooling`，match_reason「命中告警碼 21；關鍵字命中：變頻器；文字重疊（Jaccard 0.04）」 |

frontend 未動（backend-only），vitest 59 baseline 不受影響、未重跑。

## 5. Code review

`code-reviewer` subagent 對 staged diff（15 檔）：**2 must / 7 should / 4 nice，verdict Needs revision**。
處置：**must + should 全採納 + 便宜 nice（NTH2/3/4）採納；NTH1（預算 alarm_codes set）判定為 baseline 階段過早優化、不採納**。

| # | 級別 | 內容 | 處置 |
|---|---|---|---|
| M1 | **must** | `alert_handler` 用 `isinstance(BaselineKeywordRetriever)` 設 is_baseline，違反 DIP + MVP_ARCHITECTURE §3.5「換 retriever 不改 handler」升級契約 | **採納**：`Retriever` Protocol 加 `name` / `is_baseline` 契約屬性；`BaselineKeywordRetriever.is_baseline=True`；handler 改 `getattr` 取契約屬性、移除具體 import |
| M2 | **must** | `AlertEvent.timestamp` 接受 naive datetime，違反 CLAUDE.md §B（SCADA 一律 UTC） | **採納**：加 `field_validator` 拒 naive datetime + 3 個回歸測試（naive 拒 / aware 收 / None ok） |
| S1 | should | 工廠 `corpus_path: str\|None` 比底層 `str\|Path\|None` 窄 | **採納**：放寬為 `str\|Path\|None` |
| S2 | should | `top_k = query.top_k or ...` 對 0 短路（未來放寬約束會誤 fallback） | **採納**：改 `is not None` 顯式判斷 + 註解 |
| S3 | should | Jaccard 有貢獻但 match_reason 只在孤立時記錄（前端透明度與分數不符） | **採納**：改「有貢獻就記錄 `文字重疊（Jaccard x.xx）`」 |
| S4 | should | `Retriever` Protocol 未宣告 `name`（隱式契約） | **採納**：Protocol 加 `name: str`（與 M1 一併） |
| S5 | should | `test_corpus` 硬編碼 `== 11` 脆弱 | **採納**：改 `>= 11` + 11 個 scenario id subset 驗證 |
| S6 | should | test 直接 import 私有 `_tokenize` | **採納**：升為公開 `tokenize`（合理可重用工具）+ 更新 import |
| S7 | should | 單筆 chunk 損毀使整份 corpus 載入中止（與 docstring「graceful」矛盾） | **採納**：per-chunk try/except skip + warning + 回歸測試 |
| NTH2 | nice | `_CJK_RE` 僅 BMP 主塊 | **採納**：加註解說明刻意限制 |
| NTH3 | nice | 工廠 docstring 缺 Args/Returns | **採納**：補 Google style |
| NTH4 | nice | 空檔與非-mapping 共用 warning | **採納**：`None` 走獨立「空檔」warning |
| NTH1 | nice | 每次評分重建 `set(chunk.alarm_codes)` | **不採納**：baseline 11 筆可忽略，預計算屬過早優化 |

採納後重跑：knowledge 50→**54 tests**（+4 回歸：timestamp naive/aware/none、corpus partial-load skip）、
backend 全套 **624 passed / 1 xfailed**、`Any` 0、端到端 smoke 通過（match_reason 現含 Jaccard 透明度）。

## 6. 下次 session 接手建議

- **M5-1 baseline 檢索層已完成**（schema + strategy_loader + corpus + baseline retriever + alert_handler + 工廠 + 54 tests）。
  純 simulator 模式可 demo「警報碼 → Z72 手冊處置段落 + 可解釋命中原因」。
- **升級契約已就緒**：`Retriever` Protocol（`name` / `is_baseline` / `retrieve`）讓後續可無痛換實作。
- **下一步候選**（依 ISSUES.md 🎯 EPIC-M5）：
  - **M5-6** `Alert → RAG auto query` 串前端：FastAPI knowledge router（`POST /api/knowledge/alert` →
    `build_baseline_alert_handler().on_alert()` → `AlertRagResult`）—— 🔵 autonomous，可單 session 完工，
    為 M5-5 `/field/alerts/{id}` 前端鋪路。
  - **M5-2** ChromaDB 整合（新增 `ChromaVectorRetriever` 實作 `Retriever` 介面，`is_baseline=False`）—— 🔵
    但需加 `chromadb` 依賴，建議獨立 session 評估部署影響。
  - **M5-3 / M5-4** 接 RAG_Ultimate Phase 3 真策略檔 + `z72_manual.parquet` —— 🟡 需研究端產出，未 ready 前 baseline 撐著。
- baseline corpus（`data/baseline_corpus_z72.json`）的告警碼對齊 `fault_engine.FAULT_SCENARIOS` 11 scenario；
  若 monitoring 端新增 fault scenario，記得補對應 SOP chunk（test 用 subset 驗證，不會擋新增）。

