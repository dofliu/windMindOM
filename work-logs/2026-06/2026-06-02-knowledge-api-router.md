# 2026-06-02 — Knowledge FastAPI router：Alert → RAG auto query（WMOM-20260602-01）

> Autonomous daily worker session（cron 20:00 Asia/Taipei）。
> Branch：`claude/gifted-maxwell-fLNLG`。Issue：**WMOM-20260602-01**。
> Epic：**EPIC-M5（Knowledge / RAG + 現場 mobile UI）** 的 **M5-6**（Alert → RAG auto query）。

---

## 1. 開工 / 決策

- Preflight baseline 全綠：`git pull` 後 main 上 backend `pytest modules/{workflow,cost,reporting,knowledge}/tests/`
  → **624 passed / 1 xfailed**（含 6/1 落地的 knowledge baseline 54 tests）；無 blocker、main 無 regression
  （決策樹第 1、2 條不觸發）。
- 最新 handoff（6/1 `2026-06-01-knowledge-rag-foundation.md`）明確建議下一步候選：**M5-6 FastAPI knowledge router 串前端**
  —— 標 🔵 autonomous、單 session 可完工、無設計歧義（M5-1 已備妥 `Retriever` 介面 + `build_baseline_alert_handler` 工廠）。
  認領為 **WMOM-20260602-01**。

## 2. 範圍（M5-6 本 session）

把 M5-1 純 Python baseline 檢索層接上 HTTP，讓 monitoring 告警 / 前端 `/field/alerts/{id}` 可直接呼叫。

| 檔案 | 內容 |
|---|---|
| `modules/knowledge/routers/knowledge_router.py`（新） | FastAPI router，prefix `/api/knowledge`，2 endpoints |
| `modules/knowledge/routers/__init__.py`（新） | export `router` / `set_alert_handler` / `KnowledgeStatus` |
| `modules/knowledge/alert_handler.py`（改） | 加 `retriever` / `strategy` 唯讀 property（供 status endpoint 取契約屬性） |
| `modules/monitoring/server/app.py`（改） | `include_router(knowledge_router)` |
| `modules/knowledge/tests/test_knowledge_api.py`（新） | 9 個 pytest |

**Endpoints**

| Method | Path | Body / Query | Response |
|---|---|---|---|
| POST | `/api/knowledge/alert` | `AlertEvent` | `AlertRagResult`（top-k SOP chunks + 可解釋 match_reason + is_baseline） |
| GET | `/api/knowledge/status` | — | `KnowledgeStatus`（retriever / is_baseline / strategy_name） |

**不做**（留後續 epic 子目標）：ChromaDB（M5-2）、RAG_Ultimate 真向量檔（M5-3 🟡）、
`/field/` mobile UI（M5-5）、manual 全文搜尋 endpoint（M5-5 前端落地時再開 issue）。

## 3. 設計要點

- **DI pattern 對齊既有 4 個 workflow / cost routers**：模組級 `_handler` singleton +
  `set_alert_handler(handler)` setter；傳 `None` 還原為「下次請求 lazy 重建 baseline handler」，避免測試間殘留。
- **升級契約（MVP_ARCHITECTURE §3.5）**：router 只把 HTTP 請求轉成 `AlertHandler.on_alert` 呼叫，
  不含檢索邏輯；M5-2 ChromaDB / M5-3 真向量檔就緒後只需 `set_alert_handler(注入新 handler)`，router / schema 不需改。
- **`is_baseline` 透傳前端**：`/status` 回 `is_baseline`，前端可顯示「目前為 baseline 檢索（非真向量）」badge
  —— 對齊 M5-1 設計意圖。
- **UTC-aware 防線延續**：`AlertEvent.timestamp` naive datetime 經 pydantic field_validator 自動回 **422**
  （CLAUDE.md §B：SCADA 事件一律 UTC），router 不需額外處理。
- **top_k=3**：baseline 策略 `z72_manual_baseline` 的 `retrieval.top_k=3`，恰對齊 M5-6 epic「前端顯示 top-3 chunks」。
- `KnowledgeStatus` response model 放在 router（API 形狀），不污染 `schemas.py`（其刻意與 FastAPI 無關）。

## 4. Verify（zero regression）

| 項目 | 結果 |
|---|---|
| 新增 `test_knowledge_api.py`（review 後 10 tests） | **10 passed** |
| backend 全套 `pytest modules/{workflow,cost,reporting,knowledge}/tests/` | **634 passed / 1 xfailed**（624 原 baseline + 10 新；零 regression） |
| `Any` 使用 | 0（CLAUDE.md §7） |
| app 註冊 smoke | `server.app:app` 載入 OK，`/api/knowledge/alert` + `/api/knowledge/status` 出現在 109 routes 中 |
| 端到端 smoke | `POST /alert {alarm_code:21}` → 200，top1 = `z72-sop-converter-cooling`，match_reason 含「命中告警碼 21」，is_baseline=True |

frontend 未動（backend-only），vitest 59 baseline 不受影響、未重跑。

## 5. Code review

`code-reviewer` subagent 對 staged diff（5 檔）：**3 must / 5 should / 2 nice，verdict Needs revision**。
處置：**must 全採納 + should 全採納 + 便宜 nice（NTH9）採納；NTH10（global 冗餘）reviewer 自評 OK、不採納**。

| # | 級別 | 內容 | 處置 |
|---|---|---|---|
| M1 | **must** | `/alert` `/status` 無 try/except，retriever / 載入拋錯 → 裸 500，與 cost_router 慣例不一致 | **採納**：兩 endpoint 包 try/except → `HTTPException(500, 可讀 detail)` + `logger.exception` |
| M2 | **must** | test docstring 寫「策略預設 5」實際 top_k=3，文件誤導 | **採納**：改「從策略物件動態取值，不硬編碼」 |
| M3 | **must** | `_get_handler` check-then-set lazy init，M5-2 改 async 後並發 double-init | **採納（comment）**：docstring 註明「僅單事件迴圈同步安全，M5-2 async 須加 asyncio.Lock / lifespan 預初始化」 |
| S4 | should | `KnowledgeStatus` 放 router 違反分層；`__init__` re-export 違反依賴方向 | **採納**：移到 `schemas.py`，router import；`routers/__init__` 不再 export（消費者從 schemas 取） |
| S5 | should | `/status` lazy build 失敗無保護 | **採納**：try/except（同 M1）；不加 `initialized` 欄位（baseline lazy build 便宜、過度設計） |
| S6 | should | 缺 error path 測試（retriever 拋錯 → 500） | **採納**：加 `test_alert_retriever_exception_returns_500`（注入 `_BrokenRetriever`） |
| S7 | should | `set_alert_handler(None)` 未清 shared singleton，與 reporting 慣例不一致 | **採納**：docstring 註明「knowledge handler 不依賴 FarmRegistry，M5-2 引入共用 ChromaDB client 須補」 |
| S8 | should | 既有 `_StubRetriever` 缺 `is_baseline`，未完整實作 Protocol | **採納**：加 `is_baseline = False` + 註解 |
| NTH9 | nice | `async def` 呼叫同步 `on_alert`，M5-2 升級意圖未註明 | **採納**：docstring 註明「M5-2 ChromaDB 用 `await asyncio.to_thread(...)`」 |
| NTH10 | nice | `global` 宣告在 getter/setter 重複（輕微冗餘） | **不採納**：reviewer 自評符合 Python 語意、OK |

採納後重跑：knowledge 54→**64 tests**（+10：API endpoints + error path）、backend 全套 **634 passed / 1 xfailed**、`Any` 0、
app 註冊 smoke 通過（2 routes + `KnowledgeStatus` 從 schemas import OK）。

## 6. 下次 session 接手建議

- **M5-6 後端串接完成**：`/api/knowledge/alert` + `/api/knowledge/status` 已可被 monitoring / 前端呼叫。
- **下一步候選**（依 ISSUES.md 🎯 EPIC-M5）：
  - **M5-5** `/field/` mobile-first frontend：alerts list / alert detail（呼叫 `POST /api/knowledge/alert` 顯示 top-3 SOP）
    / my work orders / completion —— 🔵 autonomous，PMF 關鍵，是 M5-6 的天然下游。
  - **M5-2** ChromaDB 整合（新增 `ChromaVectorRetriever` 實作 `Retriever`，`is_baseline=False`，
    再 `set_alert_handler` 注入）—— 🔵 但需 `chromadb` 依賴，建議獨立 session 評估部署影響。
  - **M5-3 / M5-4** 接 RAG_Ultimate Phase 3 真策略檔 + `z72_manual.parquet` —— 🟡 需研究端產出。
- **可選技術債**：manual 全文搜尋 endpoint（非告警驅動）目前未做，建議等 M5-5 前端確定 UX 後再開 issue，避免猜 API 形狀。
