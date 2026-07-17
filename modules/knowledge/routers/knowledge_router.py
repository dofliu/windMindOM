"""FastAPI knowledge router（WMOM-20260603-01，EPIC-M5 M5-6）— 警報 → RAG。

對應 MVP_ARCHITECTURE §3.5「Alert → RAG auto query」：SCADA 監控觸發警報
事件 → 即時檢索手冊處置段落，前端（M5-5 ``/field/alerts/{id}``）顯示 top-k
chunks + 可解釋命中原因。

3 endpoints：
- ``POST /api/knowledge/alert``  — body ``AlertEvent`` → ``AlertRagResult``（killer feature）
- ``POST /api/knowledge/query``  — body ``RetrievalQuery`` → ``KnowledgeQueryResponse``（手動檢索）
- ``GET  /api/knowledge/info``   — ``KnowledgeInfoResponse``（前端標示 RAG 來源 / baseline 模式）

DI pattern：與 reporting_router 一致，提供 ``set_handler_factory`` 給 test
注入自訂 handler；預設用 ``build_baseline_alert_handler()`` 並快取為 singleton
（避免每次請求重讀策略 yaml + 知識庫 JSON）。

效能備註（should-fix #6）：baseline keyword retriever 為純同步 CPU 計算
（O(corpus 筆數 × token 數)）。baseline 語料庫僅數十筆，event loop blocking
可忽略，故沿用 ``async def``（與 reporting_router 慣例一致）。M5-2 接 ChromaDB
改 async I/O 後，endpoint 應加 ``await`` / ``asyncio.to_thread`` 升級。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException

from modules.auth.dependencies import require_authenticated
from modules.knowledge import (
    build_baseline_alert_handler,
    build_chroma_alert_handler,
)
from modules.knowledge.alert_handler import AlertHandler
from modules.knowledge.schemas import (
    AlertEvent,
    AlertRagResult,
    KnowledgeInfoResponse,
    KnowledgeQueryResponse,
    RetrievalQuery,
)

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


# ─────────────────────────────────────────────────────────────────────────
# DI factory + 快取（singleton handler，避免每請求重讀策略 / 知識庫）
# ─────────────────────────────────────────────────────────────────────────


_handler_factory: Callable[[], AlertHandler] | None = None
_handler: AlertHandler | None = None

# 預設 retriever 選擇（env 開關）。設 ``WMOM_KNOWLEDGE_RETRIEVER=chroma`` 啟用
# M5-2 語意檢索；其餘值 / 未設 → baseline keyword。chroma 工廠本身在向量檔 /
# 模型 / chromadb 任一缺失時會自動 fallback baseline，故此開關安全（DEC-20260608-01）。
_ENV_RETRIEVER = "WMOM_KNOWLEDGE_RETRIEVER"


def _default_factory() -> AlertHandler:
    """依 env 選預設 handler 工廠：chroma（語意）或 baseline（關鍵字）。"""
    if os.environ.get(_ENV_RETRIEVER, "").strip().lower() == "chroma":
        return build_chroma_alert_handler()
    return build_baseline_alert_handler()


def set_handler_factory(factory: Callable[[], AlertHandler] | None) -> None:
    """注入 AlertHandler factory（測試用）。

    傳 ``factory`` 或 ``None`` 都會清掉已快取的 handler：``None`` 還原成內建
    baseline 工廠、``factory`` 則確保下一次請求用新 factory 重建 handler，
    避免 test 間殘留（與 reporting / workflow routers 的 reset 行為對齊）。
    """
    global _handler_factory, _handler
    _handler_factory = factory
    _handler = None


def _get_handler() -> AlertHandler:
    """取得 handler（lazy + 快取）。

    優先用注入的 factory；否則用內建 baseline 工廠。首次建立後快取，
    後續請求直接複用（baseline corpus / 策略檔在程序生命週期內不變）。

    Raises:
        HTTPException: 503，當 handler 初始化失敗（例：策略 yaml 格式錯誤、
            知識庫 JSON 損毀）。對 mobile 前端回可 retry 的 503 而非洩漏
            traceback 的 500（must-fix #1 / #2）。
    """
    global _handler
    if _handler is None:
        factory = _handler_factory if _handler_factory is not None else _default_factory
        try:
            _handler = factory()
        except Exception as exc:
            # 不快取失敗結果（_handler 仍為 None），下次請求會重試；
            # 但本次請求回有語意的 503，並記 log 供 ops 排查。
            _logger.exception("AlertHandler 初始化失敗")
            raise HTTPException(
                status_code=503, detail="知識庫 RAG 服務暫時不可用（handler 初始化失敗）"
            ) from exc
        _logger.info("AlertHandler 初始化完成（retriever=%s）", _handler.retriever.name)
    return _handler


# ─────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────


@router.post(
    "/alert",
    response_model=AlertRagResult,
    # WMOM-20260716-05h：警報 RAG＝任何登入者（現場工程師必需）。enforce=false 放行。
    dependencies=[Depends(require_authenticated())],
)
async def query_by_alert(event: AlertEvent) -> AlertRagResult:
    """警報事件 → 自動檢索手冊處置段落（M5-6 核心）。

    SCADA 監控偵測到告警後 POST 此 endpoint，回傳含 top-k 手冊段落 +
    繁中可解釋命中原因的 ``AlertRagResult``，供現場工程師手機端顯示。
    """
    handler = _get_handler()
    return handler.on_alert(event)


@router.post(
    "/query",
    response_model=KnowledgeQueryResponse,
    dependencies=[Depends(require_authenticated())],
)
async def query_knowledge(query: RetrievalQuery) -> KnowledgeQueryResponse:
    """手動檢索（現場工程師自行打關鍵字 / 告警碼查手冊）。"""
    handler = _get_handler()
    retriever = handler.retriever
    chunks = retriever.retrieve(query)
    # ``total`` 是 computed_field（= len(items)），不必手動帶入（should-fix #9）。
    return KnowledgeQueryResponse(
        items=chunks,
        retriever=retriever.name,
        is_baseline=retriever.is_baseline,
    )


@router.get(
    "/info",
    response_model=KnowledgeInfoResponse,
    dependencies=[Depends(require_authenticated())],
)
async def knowledge_info() -> KnowledgeInfoResponse:
    """回報目前 RAG 策略 / retriever 來源（前端標示 baseline 模式用）。"""
    handler = _get_handler()
    strategy = handler.strategy
    retriever = handler.retriever
    return KnowledgeInfoResponse(
        strategy_name=strategy.name,
        oem=strategy.oem,
        model=strategy.model,
        retriever=retriever.name,
        is_baseline=retriever.is_baseline,
        top_k=strategy.retrieval.top_k,
    )
