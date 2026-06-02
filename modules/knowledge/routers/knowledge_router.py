"""FastAPI knowledge router（WMOM-20260602-01）— Alert → RAG auto query（M5-6）。

對應 EPIC-M5 M5-6「Alert → RAG auto query：警報事件觸發即 retrieve，前端顯示
top-3 chunks」（串 M5-1 baseline 檢索層 + monitoring 告警）。

| Method | Path                  | Body / Query | Response       |
|--------|-----------------------|--------------|----------------|
| POST   | /api/knowledge/alert  | AlertEvent   | AlertRagResult |
| GET    | /api/knowledge/status | —            | KnowledgeStatus|

設計邊界：
- 只把 HTTP 請求轉成 ``AlertHandler.on_alert`` 呼叫，不含任何檢索邏輯（檢索在
  M5-1 的 ``Retriever`` 實作）。
- DI pattern 與 4 個 workflow / cost routers 一致：模組級 handler singleton +
  ``set_alert_handler`` setter 供測試注入（``None`` 同時清 singleton）。
- handler 預設用 ``build_baseline_alert_handler()``（純 simulator 模式，無外部
  依賴）；M5-2 ChromaDB / M5-3 真向量檔就緒後只需換注入的 handler，本 router
  不需改動（MVP_ARCHITECTURE §3.5 升級契約）。
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from modules.knowledge import build_baseline_alert_handler
from modules.knowledge.alert_handler import AlertHandler
from modules.knowledge.schemas import AlertEvent, AlertRagResult, KnowledgeStatus

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


# ─────────────────────────────────────────────────────────────────────────
# DI：模組級 handler singleton（測試可注入；None → 清掉重新 lazy build）
# ─────────────────────────────────────────────────────────────────────────


_handler: Optional[AlertHandler] = None


def set_alert_handler(handler: Optional[AlertHandler]) -> None:
    """注入 ``AlertHandler``（測試用）；``None`` 清掉 singleton。

    與 reporting / cost / workflow routers 的 setter 行為對齊：傳 ``None``
    時還原為「下次請求 lazy 重建 baseline handler」，避免測試間殘留。

    Note:
        knowledge handler 目前不依賴 ``FarmRegistry``（不像 reporting router
        的 setter 需呼叫 ``reset_farm_registry()``），故 ``None`` 只需清自己
        的 ``_handler``。M5-2 若引入共用 ChromaDB client singleton，須在此補上
        對應清理。
    """
    global _handler
    _handler = handler


def _get_handler() -> AlertHandler:
    """取得目前 handler；未注入時 lazy 建立 baseline handler（純 simulator）。

    Note:
        此 lazy init 為 check-then-set，僅保證在「單一事件迴圈 + 同步
        ``on_alert``」（baseline 場景）下安全。M5-2 把 ``on_alert`` 改為
        async（ChromaDB I/O）時，須改用 ``asyncio.Lock`` 或 startup lifespan
        預先初始化，避免並發 double-init。
    """
    global _handler
    if _handler is None:
        _handler = build_baseline_alert_handler()
    return _handler


# ─────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────


@router.post("/alert", response_model=AlertRagResult)
async def query_by_alert(event: AlertEvent) -> AlertRagResult:
    """警報事件進來 → 自動檢索手冊處置段落，回 ``AlertRagResult``。

    M5-6 核心：monitoring 偵測到 fault / 前端 ``/field/alerts/{id}`` 都可 POST
    一筆 ``AlertEvent``，立即拿到「告警碼對應的 SOP top-k chunks + 可解釋命中
    原因 + is_baseline 標記」。

    ``AlertEvent.timestamp`` 若帶 naive datetime，pydantic 會自動回 422
    （CLAUDE.md §B：SCADA 事件一律 UTC-aware）。

    ``on_alert`` 目前為同步純 Python（baseline）；M5-2 換 ChromaDB（I/O bound）
    後，正確升級路徑是 ``await asyncio.to_thread(handler.on_alert, event)``，
    故此處 endpoint 預留 ``async def``。

    檢索層（corpus / 策略檔載入或 retriever）拋例外時，回 500 + 可讀診斷訊息
    （對齊 cost_router 的防禦性寫法），而非裸露的預設 Internal Server Error。
    """
    try:
        return _get_handler().on_alert(event)
    except Exception as exc:  # noqa: BLE001 — 任何檢索層錯誤都轉可讀 500
        _logger.exception("knowledge/alert 檢索失敗：%s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"RAG 檢索失敗（{type(exc).__name__}），請確認知識庫與策略檔狀態",
        ) from exc


@router.get("/status", response_model=KnowledgeStatus)
async def get_status() -> KnowledgeStatus:
    """回傳目前檢索層狀態（retriever / is_baseline / 策略名）。

    前端用 ``is_baseline`` 決定是否顯示「目前為 baseline 檢索（非真向量）」提示，
    對齊 M5-1 的設計意圖。handler 初始化失敗時同 ``/alert`` 回可讀 500。
    """
    try:
        handler = _get_handler()
        return KnowledgeStatus(
            retriever=handler.retriever.name,
            is_baseline=handler.retriever.is_baseline,
            strategy_name=handler.strategy.name,
        )
    except Exception as exc:  # noqa: BLE001 — 初始化失敗轉可讀 500
        _logger.exception("knowledge/status 取得失敗：%s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"knowledge 狀態取得失敗（{type(exc).__name__}），請確認知識庫與策略檔狀態",
        ) from exc
