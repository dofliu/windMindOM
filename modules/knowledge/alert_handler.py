"""警報 → 知識檢索編排（WMOM-20260601-01）。

呼應 ROADMAP M5-1（``alert_handler.py``）+ M5-6（Alert → RAG auto query）。

``AlertHandler`` 把一筆 monitoring 警報（``AlertContext``）轉成知識查詢，
呼叫 baseline 檢索器，並包裝成前端可直接渲染的 ``KnowledgeResponse``。

設計重點：
- **不耦合 monitoring**：只吃 ``AlertContext`` schema，不 import simulator，
  讓本模組能獨立單元測試（simulator-first）。
- **時間可注入**：``clock`` 參數讓 ``retrieved_at`` 在測試中可決定性。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from modules.knowledge.retrieve import BaselineLexicalRetriever
from modules.knowledge.schemas.knowledge_schemas import (
    AlertContext,
    KnowledgeQuery,
    KnowledgeResponse,
)
from modules.knowledge.strategy_loader import RagStrategy


def _utc_now() -> datetime:
    """預設 clock：UTC 當下時間。"""
    return datetime.now(timezone.utc)


def build_query_text(alert: AlertContext) -> str:
    """把警報情境組成檢索查詢文字。

    串接 message + subsystem + alert_code，讓 lexical 檢索同時吃到自然語言
    描述與結構化線索；空欄位自動略過。

    Args:
        alert: 警報情境。

    Returns:
        供 ``KnowledgeQuery.text`` 使用的查詢字串。
    """
    parts = [alert.message, alert.subsystem or "", alert.alert_code]
    return " ".join(p for p in parts if p).strip()


class AlertHandler:
    """警報 → RAG 查詢編排器。"""

    def __init__(
        self,
        retriever: BaselineLexicalRetriever,
        strategy: RagStrategy,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        """建構編排器。

        Args:
            retriever: baseline 檢索器（已載入語料）。
            strategy: 檢索策略（提供 top_k 預設與版本標記）。
            clock: 取得當下時間的函式，預設 UTC now；測試可注入固定時鐘。
        """
        self._retriever = retriever
        self._strategy = strategy
        self._clock = clock

    def query(self, query: KnowledgeQuery) -> KnowledgeResponse:
        """直接以 ``KnowledgeQuery`` 檢索並包裝回應。

        Args:
            query: 查詢請求。

        Returns:
            ``KnowledgeResponse``（top-k chunks + metadata）。
        """
        chunks = self._retriever.retrieve(query)
        return KnowledgeResponse(
            query=query.text,
            oem_model=query.oem_model,
            strategy_version=self._strategy.version,
            chunks=chunks,
            total_candidates=self._retriever.candidate_count(query.oem_model),
            retrieved_at=self._clock(),
        )

    def handle(self, alert: AlertContext, top_k: int | None = None) -> KnowledgeResponse:
        """處理一筆警報：組查詢 → 檢索 → 回應。

        Args:
            alert: monitoring 警報情境。
            top_k: 覆寫回傳筆數；``None`` 時用策略預設 ``retrieval.top_k``。

        Returns:
            ``KnowledgeResponse``，現場工程師端可直接渲染 top-3 手冊段落。
        """
        effective_top_k = (
            self._strategy.retrieval.top_k if top_k is None else top_k
        )
        query = KnowledgeQuery(
            text=build_query_text(alert),
            top_k=effective_top_k,
            fault_code=alert.alert_code,
            oem_model=alert.oem_model,
        )
        return self.query(query)
