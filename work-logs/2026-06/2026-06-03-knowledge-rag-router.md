# 2026-06-03 — Knowledge RAG FastAPI router（WMOM-20260603-01，M5-6）

> Autonomous daily worker session（cron 20:00 Asia/Taipei）。
> Branch：`claude/gifted-maxwell-rv1eq`。Issue：**WMOM-20260603-01**。
> Epic：**EPIC-M5（Knowledge / RAG + 現場 mobile UI）** 的 **M5-6**「Alert → RAG auto query」。

---

## 1. 開工 / 決策

- Preflight baseline 全綠：backend `pytest modules/{workflow,cost,reporting}/tests/` → **570 passed / 1 xfailed**；
  knowledge module（M5-1）54 tests 也綠。無 blocker、main 無 regression（決策樹第 1、2 條不觸發）。
- 最新 handoff（6/01 M5-1 knowledge baseline）明確建議下一步 = **M5-6 FastAPI knowledge router**：
  🔵 autonomous、單 session 可完工、為 M5-5 `/field/alerts/{id}` 前端鋪路。設計規範在 MVP_ARCHITECTURE §3.5、
  M5-1 已備好 `build_baseline_alert_handler()` 工廠 + `AlertHandler` + `Retriever` Protocol，無歧義 → 認領。

## 2. 範圍（M5-6，本 session）

| 檔案 | 內容 |
|---|---|
| `modules/knowledge/routers/knowledge_router.py`（新） | 3 endpoints + DI factory + lazy 快取 singleton handler |
| `modules/knowledge/routers/__init__.py`（新） | 匯出 `router`（對齊 reporting/workflow routers 慣例） |
| `modules/knowledge/alert_handler.py` | 加 `retriever` / `strategy` 唯讀 property（讓 router 做直接檢索 + 讀 retriever 契約屬性，不碰私有狀態） |
| `modules/knowledge/schemas.py` | 加 `KnowledgeQueryResponse` / `KnowledgeInfoResponse` 回傳包裝 |
| `modules/monitoring/server/app.py` | `include_router(knowledge_router)` 註冊 |
| `modules/knowledge/tests/test_knowledge_api.py`（新） | 11 tests |

**3 endpoints**：
- `POST /api/knowledge/alert` — body `AlertEvent` → `AlertRagResult`（**killer feature**：SCADA 警報事件即時檢索手冊處置段落）
- `POST /api/knowledge/query` — body `RetrievalQuery` → `KnowledgeQueryResponse`（現場工程師手動關鍵字/告警碼查手冊）
- `GET  /api/knowledge/info` — `KnowledgeInfoResponse`（前端標示 RAG 來源 / baseline 模式 badge）

**不做**（留後續 issue）：M5-5 `/field/` mobile 前端（串本 router）、M5-2 ChromaDB、M5-3 RAG_Ultimate 真向量檔。

## 3. 設計要點

- **DI pattern 對齊 reporting_router**：`set_handler_factory(factory|None)`；`None` 同時清快取（test 隔離，
  對齊 reporting/workflow routers 的 reset 行為）。
- **lazy 快取 singleton handler**：baseline corpus / 策略檔在程序生命週期內不變，每請求重讀 JSON + yaml 浪費 →
  首次建立後快取複用（測試 `test_injected_factory_is_used` 驗證兩次請求只建一次）。
- **不碰 handler 私有狀態**：在 `AlertHandler` 加 `retriever` / `strategy` 唯讀 property，router 透過契約屬性
  （`name` / `is_baseline`）標示來源，符合 MVP_ARCHITECTURE §3.5 升級契約（換 retriever 不改 router）。
- **timestamp UTC-aware 防線延伸到 API 邊界**：naive datetime 經 schema validator → FastAPI 回 422
  （`test_naive_timestamp_rejected_422`）。

## 4. Verify（zero regression）

| 項目 | 結果 |
|---|---|
| 新增 `test_knowledge_api.py` | **14 passed**（11 初版 + 3 review 回歸） |
| knowledge 全套 | **68 passed**（54 M5-1 + 14 M5-6） |
| backend 全套 `pytest modules/{workflow,cost,reporting,knowledge}/tests/` | **638 passed / 1 xfailed**（570 baseline + 54 M5-1 + 14 新；零 regression） |
| app router 掛載驗證 | `/api/knowledge/{alert,query,info}` 3 routes 正確註冊 |
| computed `total` 序列化 | `query` 回應 `total == len(items)` ✅ |
| `Any` 使用 | 0（CLAUDE.md §7） |

frontend 未動（backend-only），vitest 59 baseline 不受影響、未重跑。

## 5. Code review

`code-reviewer` subagent 對 staged diff（6 檔）：**4 must / 5 should / 3 nice，verdict Needs revision**。
處置：**must 全採納 + 便宜 should/nice 採納；should-fix #8（sys.path→conftest）不採納**（理由見下）。

| # | 級別 | 內容 | 處置 |
|---|---|---|---|
| M1 | **must** | `HTTPException` import 但未用 + endpoint 無例外處理 → corpus 載入失敗會洩漏 traceback 的 500 | **採納**：`_get_handler()` 包 try/except，handler 初始化失敗 → log.exception + 回有語意可 retry 的 **503** |
| M2 | **must** | `_get_handler()` 無例外防護，yaml parse error 穿透到 500 + 明文 traceback | **採納**：同 M1，失敗不快取（`_handler` 仍 None）→ 下次請求重試 |
| M3 | **must** | DI singleton test 隔離依賴 fixture 時序 / test 順序（未來 xdist 風險） | **採納**：改 `autouse` fixture `_reset_handler_singleton`，`client` fixture 只管掛 router（職責分離） |
| M4 | **must** | 無 error-path 測試（全 happy path / 422） | **採納**：加 `test_broken_factory_returns_503` + `test_broken_factory_not_cached_retries`（驗證失敗不快取、修好即恢復） |
| S5 | should | `Optional[X]` 與 module 其他檔 `X\|None` 不一致 | **採納**：改 `X \| None` + `collections.abc.Callable` |
| S6 | should | `async def` 內跑同步 CPU 工作，語料大時 block event loop | **採納**：module docstring 註明 baseline 數十筆可忽略 + M5-2 升級 await 的契約（保留 async 與 reporting_router 一致） |
| S7 | should | DI test `set_handler_factory(factory)` 二次清快取意圖不明 | **採納**：inline comment + setter docstring 補說明 |
| S9 | should | `KnowledgeQueryResponse.total` 可能與 `items` 不一致 | **採納**：`total` 改 `@computed_field`（永遠 = `len(items)`），router 不再手動帶 |
| NTH10 | nice | endpoint docstring 缺 `Raises` | **採納**：`_get_handler` docstring 補 `Raises: HTTPException 503` |
| NTH11 | nice | `AlertEvent.alarm_code` 無下界，接受負值 | **採納**：`Field(ge=1)`（Bachmann 有效碼自 1 起）+ `test_invalid_alarm_code_422` |
| NTH12 | nice | `_logger` 宣告但未用 | **採納**：handler 初始化成功記 info、失敗記 exception |
| **S8** | should | `sys.path.insert` 應移 conftest.py / pyproject `pythonpath` | **不採納**：全 repo test 檔（test_alert_handler 等）皆用此 pattern，單獨改本檔反造成不一致；統一 conftest 屬獨立測試基建 issue（記 backlog，不在本 PR 範圍） |

採納後重跑：knowledge 54→**68 tests**（M5-6 11→14：+invalid_alarm_code / +broken_factory_503 / +broken_factory_retries）、
backend 全套 **638 passed / 1 xfailed**、`Any` 0、computed `total` 序列化驗證通過、503 error path 驗證通過。

## 6. 下次 session 接手建議

- **M5-6 後端 router 已完成**：3 endpoints + DI + 快取 + 11 tests。純 simulator 模式可從 HTTP 端
  demo「警報碼 → top-k 手冊處置段落 + 可解釋命中原因」。
- **下一步候選**（依 ISSUES.md 🎯 EPIC-M5）：
  - **M5-5** `/field/` mobile-first frontend（alerts list / alert detail with RAG / my work orders）—— 🔵 串本 router
    的 `POST /api/knowledge/alert` + `GET /api/knowledge/info`（baseline badge）。PMF 關鍵。
  - **M5-2** ChromaDB 整合（新增 `ChromaVectorRetriever` 實作 `Retriever` 介面，`is_baseline=False`）—— 🔵
    但需加 `chromadb` 依賴，建議獨立 session 評估部署影響。
  - **M5-3 / M5-4** 接 RAG_Ultimate Phase 3 真策略檔 + `z72_manual.parquet` —— 🟡 需研究端產出。
- router 用 `build_baseline_alert_handler()` 預設工廠；M5-2/M5-3 上線後只需把 factory 換成建 `ChromaVectorRetriever`
  的版本（`set_handler_factory`），endpoints / schema 不動。
