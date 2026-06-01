"""knowledge module — 警報手冊 RAG（EPIC-M5）。

M5-1（WMOM-20260601-01）已落地「simulator-first baseline 檢索層」：
- ``schemas``：RagStrategy / KnowledgeChunk / RetrievalQuery / RetrievedChunk /
  AlertEvent / AlertRagResult
- ``strategy_loader``：載入 RAG 策略檔（缺失 → baseline default）
- ``corpus``：載入知識庫（baseline JSON）+ by_alarm_code / filter
- ``retrieve``：``Retriever`` 介面 + ``BaselineKeywordRetriever``（無外部依賴）
- ``alert_handler``：警報事件 → query → retrieve → ``AlertRagResult``

「RAG_Ultimate 提供策略檔 + 預計算向量檔，windMindOM 只載入 + query，
不重新 embed」（CLAUDE.md §15）。M5-2 加 ChromaDB、M5-3 接 RAG_Ultimate
真向量檔前，baseline retriever 讓純 simulator 模式即可 demo「警報→處置」。
"""

from __future__ import annotations

from pathlib import Path

from modules.knowledge.alert_handler import AlertHandler
from modules.knowledge.corpus import KnowledgeCorpus, load_chunks
from modules.knowledge.retrieve import BaselineKeywordRetriever, Retriever
from modules.knowledge.schemas import (
    AlertEvent,
    AlertRagResult,
    KnowledgeChunk,
    RagStrategy,
    RetrievalQuery,
    RetrievedChunk,
)
from modules.knowledge.strategy_loader import default_strategy, load_strategy


def build_baseline_alert_handler(
    corpus_path: str | Path | None = None,
    strategy_path: str | Path | None = None,
) -> AlertHandler:
    """便捷工廠：載入 baseline 策略 + 知識庫，組出可用的 ``AlertHandler``。

    純 simulator 模式 / demo / 測試的一行起手。

    Args:
        corpus_path: 知識庫 JSON 路徑；``None`` 時用內建 baseline corpus。
        strategy_path: RAG 策略檔路徑；``None`` 時用內建 baseline 策略。

    Returns:
        以 ``BaselineKeywordRetriever`` 組好、可直接 ``on_alert`` 的 handler。
    """
    strategy = load_strategy(strategy_path)
    corpus = KnowledgeCorpus.load(corpus_path)
    retriever = BaselineKeywordRetriever(corpus=corpus, strategy=strategy)
    return AlertHandler(retriever=retriever, strategy=strategy)


__all__ = [
    "AlertEvent",
    "AlertHandler",
    "AlertRagResult",
    "BaselineKeywordRetriever",
    "KnowledgeChunk",
    "KnowledgeCorpus",
    "RagStrategy",
    "RetrievalQuery",
    "RetrievedChunk",
    "Retriever",
    "build_baseline_alert_handler",
    "default_strategy",
    "load_chunks",
    "load_strategy",
]
