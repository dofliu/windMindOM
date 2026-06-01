"""警報 → RAG 自動檢索（M5-1）。

對應 MVP_ARCHITECTURE §3.5「Alert handler 流程」：
SCADA 監控觸發警報 → ``AlertHandler.on_alert(event)`` → 構造 query
（告警碼 + 機型 + 異常 tag）→ retrieve top-k → 回 ``AlertRagResult``
給 ``/field/alerts/{id}`` view（M5-5 / M5-6）。

設計邊界：只負責「事件 → query → 呼叫 retriever → 組結果」，不綁定
特定 retriever 實作（依賴 ``Retriever`` 介面），baseline / 未來 ChromaDB
皆適用。
"""

from __future__ import annotations

from modules.knowledge.retrieve import Retriever
from modules.knowledge.schemas import (
    AlertEvent,
    AlertRagResult,
    RagStrategy,
    RetrievalQuery,
)


class AlertHandler:
    """把警報事件轉成 RAG 檢索結果。"""

    def __init__(self, retriever: Retriever, strategy: RagStrategy) -> None:
        """以 retriever + 策略建立 handler。

        Args:
            retriever: 任一實作 ``Retriever`` 介面者（baseline / ChromaDB）。
            strategy: RAG 策略（提供策略名 + top_k）。
        """
        self._retriever = retriever
        self._strategy = strategy

    def build_query(self, event: AlertEvent) -> RetrievalQuery:
        """由警報事件構造檢索 query。

        query 文字串接「機型 + 告警碼 + 描述 + 異常 tag」，並把告警碼帶進
        ``alarm_codes`` 作為檢索主信號；oem / model 用於過濾知識庫。
        """
        parts: list[str] = [f"{event.model} 告警 {event.alarm_code}"]
        if event.description:
            parts.append(event.description)
        if event.abnormal_tags:
            parts.append("異常 tag: " + " ".join(event.abnormal_tags))

        return RetrievalQuery(
            text=" ".join(parts),
            oem=event.oem,
            model=event.model,
            alarm_codes=[event.alarm_code],
            top_k=self._strategy.retrieval.top_k,
        )

    def on_alert(self, event: AlertEvent) -> AlertRagResult:
        """警報事件進來 → 回傳含手冊處置段落的 ``AlertRagResult``。"""
        query = self.build_query(event)
        chunks = self._retriever.retrieve(query)

        # 只依賴 Retriever 介面契約屬性（name / is_baseline），不認得任何
        # 具體實作 —— 符合 MVP_ARCHITECTURE §3.5「換 retriever 不需改 handler」。
        # getattr 保留 default 作為防呆（實作未遵守契約時不致 crash）。
        retriever_name = getattr(self._retriever, "name", type(self._retriever).__name__)
        is_baseline = getattr(self._retriever, "is_baseline", False)

        return AlertRagResult(
            alert=event,
            query=query,
            chunks=chunks,
            strategy_name=self._strategy.name,
            retriever=retriever_name,
            is_baseline=is_baseline,
        )
