# 2026-06-02 — Knowledge FastAPI router（WMOM-20260602-01）

> Autonomous daily worker session（cron 20:00 Asia/Taipei）。
> Branch：`claude/gifted-maxwell-TpwQT`。Issue：**WMOM-20260602-01**。
> Epic：**EPIC-M5（Knowledge / RAG + 現場 mobile UI）** 的 **M5-6**（Alert → RAG auto query，串前端）。

---

## 1. 開工 / 決策

- Preflight baseline 全綠：`pytest modules/{workflow,cost,reporting}/tests/` → **570 passed / 1 xfailed**；
  main 無 regression、無 blocker（決策樹第 1、2 條不觸發）。
- 讀最新 handoff（6/01 `2026-06-01-knowledge-rag-foundation.md`）：M5-1 baseline 檢索層已完成
  （schema + strategy_loader + corpus + `BaselineKeywordRetriever` + `AlertHandler` + 工廠 + 54 tests）。
  明確列下一步候選最高價值 🔵 = **M5-6** FastAPI knowledge router
  （`POST /api/knowledge/alert → build_baseline_alert_handler().on_alert() → AlertRagResult`），
  單 session 可完工、無設計歧義 → 認領 **WMOM-20260602-01**。
- M5-6 是把 M5-1 純 Python 檢索層接成 HTTP，給 M5-5 `/field/alerts/{id}` 前端鋪路。

## 2. 範圍（本 session）

| 檔案 | 內容 |
|---|---|
| `modules/knowledge/routers/knowledge_router.py` | `POST /api/knowledge/alert`（AlertEvent → AlertRagResult）+ `GET /api/knowledge/info`（retriever/strategy/is_baseline 中繼資料）+ `set_handler` DI setter |
| `modules/knowledge/routers/__init__.py` | router export |
| `modules/knowledge/alert_handler.py`（改） | 加 `strategy_name` / `retriever_name` / `is_baseline` 唯讀 property；`on_alert` 共用（消重複契約屬性邏輯） |
| `modules/monitoring/server/app.py`（改） | import + `include_router(knowledge_router)` 接入主 app |
| `modules/knowledge/tests/test_knowledge_router.py` | 8 個 router 測試 |

**不做**（留後續 issue）：自由文字查詢 endpoint（M5-5 前端搜尋）、ChromaDB（M5-2）、
真向量檔（M5-3 🟡）、`/field/` mobile UI（M5-5）。

## 3. 設計要點

- **升級契約**（MVP_ARCHITECTURE §3.5「換 retriever 不需改 handler / router」）：router 只依賴
  `AlertHandler` / `Retriever` 介面，不認得具體實作。M5-2 換 `ChromaVectorRetriever` 後只需換注入的
  handler（`set_handler`），router / schema / 前端皆不需改動。
- **`/info` 不觸發檢索**：原本想用「探測事件 on_alert」取中繼資料（hacky 且重複契約屬性邏輯），
  改為在 `AlertHandler` 加 `strategy_name` / `retriever_name` / `is_baseline` 唯讀 property，
  `on_alert` 與 `/info` 共用同一份契約屬性邏輯（single source of truth）。
- **timestamp UTC 防線延伸到 HTTP 邊界**：`AlertEvent.timestamp` 的 tz-aware validator（M5-1 埋）
  在 FastAPI request 解析階段即生效，naive datetime 直接回 422（無需 router 再寫驗證）。
- **DI pattern 對齊**：`set_handler(handler|None)` 與 cost/reporting routers 的 setter 風格一致，
  `None` reset 回 lazy baseline default。

## 4. Verify（zero regression）

| 項目 | 結果 |
|---|---|
| 新增 `test_knowledge_router.py` | **10 passed**（8 初版 + 2 review 補：空 corpus、init 503） |
| `modules/knowledge/tests/` 全套 | **64 passed**（54 原 + 10 新） |
| backend 全套 `pytest modules/{workflow,cost,reporting,knowledge}/tests/` | **634 passed / 1 xfailed**（570 原 baseline + 64 knowledge；零 regression） |
| 主 app 接線 | `server.app` import OK，`/api/knowledge/alert`、`/api/knowledge/info` 兩 route 已註冊 |
| `Any` 使用 | 0（CLAUDE.md §7） |
| 端到端 smoke | `POST /alert` 告警碼 21 + 變頻器描述 → top1 `z72-sop-converter-cooling`（score 0.692）；`/info` → baseline_keyword / z72_manual_baseline / is_baseline=True |

frontend 未動（backend-only），vitest 59 baseline 不受影響、未重跑。

## 5. Code review

兩輪 `code-reviewer` subagent 對 staged diff（合併去重後）：**3 must / 多項 should / nice，verdict Needs revision**。
處置：**must 全採納 + should 全採納 + 便宜 nice 採納；1 項 should 判定保留前次 session 決策不採納**。

| 級別 | 內容 | 處置 |
|---|---|---|
| **must** | `pyyaml` 未列 `requirements.txt`（strategy_loader 依賴；新環境第一個請求會爆） | **採納**：`requirements.txt` 補 `pyyaml>=6.0` |
| **must** | `_get_handler` lazy init 無例外保護（`yaml.YAMLError` / pydantic `ValidationError` 穿透成未攔截 500 + 洩漏 traceback） | **採納**：try/except → 503 + safe message + `_logger.exception`（同時消除 `_logger` dead code，成功時 `_logger.info`） |
| **must** | `query_alert` 的 `ValueError→422` 是死碼且語意錯（on_alert 鏈不丟 ValueError；真有業務例外應 5xx 非 4xx） | **採納**：移除 try/except，endpoint 簡化 |
| **must** | `async def` endpoint 內同步呼叫 CPU/IO-bound（lazy init 阻斷 event loop，M5-3 大語料放大） | **採納**：endpoint 改同步 `def`（FastAPI 自動 threadpool）+ 註解說明 |
| should | `turbine_id` 無 `min_length`（空字串靜默通過，與 workflow 約束不一致） | **採納**：`schemas.py` 加 `min_length=1, max_length=64` |
| should | `KnowledgeInfoResponse` 定義在 router 層，違反 schema 分層 | **採納**：移到 `schemas.py` + `__init__` 匯出 |
| should | 缺 error-path 測試（init 失敗 503） | **採納**：加 `test_alert_returns_503_when_handler_init_fails`（驗 503 + 不洩漏內部路徑/訊息） |
| should | `docs/API_GUIDE.md` 未記錄新 endpoint | **採納**：補 Knowledge / RAG API 區段（request/response/error/curl） |
| should | router test 硬編碼 chunk id `z72-sop-converter-cooling`（語料異動誤爆） | **採納**：改驗 `alarm_codes` 含 21（具體 id 由 test_retrieve 負責） |
| should | naive timestamp test 只驗 422、未驗根因 | **採納**：加 `assert "timestamp" in str(resp.json()).lower()` |
| should | `set_handler` 未在 routers `__init__` re-export | **採納**：`__all__` 加 `set_handler` |
| should | reset test 為空轉（未先注入非 baseline handler） | **採納**：先注入 `stub_vector`（is_baseline=False）handler 再 reset，真正覆蓋語意 |
| nice | `alarm_code` 無下界（負數/0 通過） | **採納**：`schemas.py` 加 `ge=1` |
| nice | 缺空 corpus edge case 測試 | **採納**：加 `test_alert_empty_corpus_returns_200_empty_chunks` |
| should | `retriever_name`/`is_baseline` 用 `getattr` 防呆 vs Protocol 契約（建議直接存取 fail-fast） | **不採納**：前次 session（M5-1）刻意以 getattr 防呆為 must-fix 決策；`is_baseline=False` / classname fallback 是安全預設（不誤稱 baseline），保留 belt-and-suspenders，不反轉前次決策 |
| nice | `global _handler` 冗餘 / Protocol runtime_checkable 屬性限制 | **不採納**：非真問題（`global` 在賦值 branch 必要）/ 已知 Python 限制，與保留 getattr 一致 |

採納後重跑：knowledge **64 tests**（+2：空 corpus、init 503）、backend 全套 **634 passed / 1 xfailed**（570 原 baseline + 64 新，零 regression）、`Any` 0、端到端 smoke + app 接線（`/api/knowledge/alert`、`/info`）通過。

## 6. 下次 session 接手建議

- **M5-6 已完成**：knowledge module 對外有 HTTP API（`/api/knowledge/alert`、`/api/knowledge/info`），
  純 simulator 模式即可讓前端打「警報碼 → 手冊處置段落 + 可解釋命中原因 + is_baseline 標記」。
- **下一步候選**（依 ISSUES.md 🎯 EPIC-M5）：
  - **M5-5** `/field/` mobile-first frontend：alerts list / alert detail（打 `/api/knowledge/alert`
    顯示 top-k chunks + `is_baseline` 橫幅）/ my work orders / completion —— 🔵 PMF 關鍵，可單 session 起一塊。
  - **自由文字查詢 endpoint**：若 M5-5 需手動搜手冊（非警報觸發），可加 `POST /api/knowledge/query`
    （收 `RetrievalQuery`）—— 本 session 刻意未做（避免 scope creep），可開子 issue。
  - **M5-2** ChromaDB 整合（新增 `ChromaVectorRetriever` 實作 `Retriever`，`set_handler` 注入）—— 🔵
    需加 `chromadb` 依賴，建議獨立 session 評估部署影響。
  - **M5-3 / M5-4** 接 RAG_Ultimate Phase 3 真策略檔 + `z72_manual.parquet` —— 🟡 需研究端產出。
