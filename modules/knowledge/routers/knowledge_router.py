"""FastAPI knowledge router（WMOM-20260602-01 / EPIC-M5 M5-6）。

把 M5-1 baseline 檢索層（``build_baseline_alert_handler`` → ``AlertHandler``）
接成 HTTP endpoint，給前端「警報 → 手冊處置段落」用：

- ``POST /api/knowledge/alert`` — 收 ``AlertEvent`` → ``on_alert`` → ``AlertRagResult``
  （M5-5 ``/field/alerts/{id}`` 顯示 top-k chunks 的後端）
- ``GET  /api/knowledge/info``  — 回目前 retriever / 策略中繼資料
  （前端可標示「目前為 baseline 檢索，非真向量」）

設計邊界（對齊 MVP_ARCHITECTURE §3.5）：router 只依賴 ``AlertHandler`` /
``Retriever`` 介面，不認得具體實作。M5-2 換 ``ChromaVectorRetriever`` 後，
只需換注入的 handler，router / schema / 前端皆不需改動。

DI pattern：與 cost / reporting routers 一致，提供 ``set_handler`` setter
讓 test 注入自訂語料的 handler；``None`` 時 reset 回 lazy baseline default。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from modules.knowledge import build_baseline_alert_handler
from modules.knowledge.alert_handler import AlertHandler
from modules.knowledge.schemas import (
    AlertEvent,
    AlertRagResult,
    KnowledgeInfoResponse,
)

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


# ─────────────────────────────────────────────────────────────────────────
# DI：handler factory（lazy singleton + test 可覆寫）
# ─────────────────────────────────────────────────────────────────────────


_handler: AlertHandler | None = None


def set_handler(handler: AlertHandler | None) -> None:
    """注入 ``AlertHandler``（test 用自訂語料；``None`` reset 回 baseline default）。"""
    global _handler
    _handler = handler


def _get_handler() -> AlertHandler:
    """取得 handler；未注入時 lazy 建立 baseline default（載入內建 Z72 語料）。

    lazy init 會讀策略 yaml + 語料 json；若策略檔語法錯誤（``yaml.YAMLError``）
    或語料 schema 不符（pydantic ``ValidationError``）會在此拋例外。這些屬
    server-side 設定問題（非 client input），轉成 503 並記 error log，避免
    未攔截 traceback 洩漏到 response（review must-fix）。

    note：endpoint 為同步 ``def``，FastAPI 會在 threadpool 執行，故此處的
    阻斷式檔案 I/O 不會卡住 event loop（M5-3 接 RAG_Ultimate 大語料後亦然）。
    """
    global _handler
    if _handler is None:
        try:
            _handler = build_baseline_alert_handler()
            _logger.info("knowledge handler 已初始化（retriever=%s）", _handler.retriever_name)
        except Exception as exc:  # noqa: BLE001 — 任何初始化失敗都轉 503，並記錄根因
            _logger.exception("knowledge handler 初始化失敗：%s", exc)
            raise HTTPException(
                status_code=503,
                detail="knowledge module 尚未就緒（策略檔 / 語料設定異常），請聯絡管理員",
            ) from exc
    return _handler


# ─────────────────────────────────────────────────────────────────────────
# Endpoints
#
# 刻意用同步 ``def``（非 ``async def``）：``on_alert`` 內含 corpus 全掃描 +
# tokenize（CPU-bound），lazy init 另含阻斷式檔案 I/O。FastAPI 會把同步
# endpoint 丟進 threadpool 執行，避免阻斷 event loop —— 比在 ``async def``
# 內直接呼叫同步重運算更正確（review must-fix；M5-3 大語料後尤其重要）。
# ─────────────────────────────────────────────────────────────────────────


@router.post("/alert", response_model=AlertRagResult)
def query_alert(event: AlertEvent) -> AlertRagResult:
    """警報事件 → 檢索手冊處置段落。

    前端在警報詳情頁帶入 ``AlertEvent``（告警碼 + 機型 + 異常 tag + 描述），
    後端構造 query → retrieve top-k → 回 ``AlertRagResult``（含可解釋
    ``match_reason`` 與 ``is_baseline`` 標記）。

    ``AlertEvent.timestamp`` 若為 naive datetime，pydantic validator 會在
    request 解析階段直接回 422（SCADA 事件一律 UTC-aware）。
    """
    handler = _get_handler()
    return handler.on_alert(event)


@router.get("/info", response_model=KnowledgeInfoResponse)
def knowledge_info() -> KnowledgeInfoResponse:
    """回目前檢索層中繼資料（retriever / 策略名 / 是否 baseline）。

    前端用來判斷是否顯示「目前為 baseline placeholder 檢索」橫幅。
    直接讀 handler 的契約屬性，不依賴具體 retriever 實作、不觸發檢索。
    """
    handler = _get_handler()
    return KnowledgeInfoResponse(
        retriever=handler.retriever_name,
        strategy_name=handler.strategy_name,
        is_baseline=handler.is_baseline,
    )
