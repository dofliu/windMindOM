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

import logging
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

logger = logging.getLogger(__name__)


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


def build_chroma_alert_handler(
    strategy_path: str | Path | None = None,
    export_dir: str | Path | None = None,
    model_dir: str | Path | None = None,
    corpus_path: str | Path | None = None,
) -> AlertHandler:
    """便捷工廠：用 ChromaDB 語意向量檢索組 ``AlertHandler``（M5-2）。

    對應 DEC-20260608-01：載入 RAG_Ultimate 預算向量檔 + 內嵌 query encoder。
    **任一環節失敗（向量檔缺 / chromadb 未裝 / 語料空）即 graceful fallback
    回 baseline keyword retriever**，確保平台不因 RAG 升級而啟動失敗
    （simulator-first 不被破壞）。

    嵌入模型缺失（``EmbedderUnavailable``）原本要到首次 ``retrieve`` 才觸發；
    本工廠在組好後做一次 **warmup retrieve** 強制提前載入模型，把該失敗一併
    納入 fallback —— 確保「向量檔在、模型缺」也是啟動期退回 baseline，而非
    現場工程師第一次查詢才炸 500。

    Args:
        strategy_path: RAG 策略檔路徑；``None`` 時用內建 baseline 策略。
        export_dir: 向量檔目錄；``None`` 時依 env / 預設 shipped 位置解析。
        model_dir: 嵌入模型目錄；``None`` 時依 env / 預設 shipped 位置解析。
        corpus_path: fallback 用 baseline 知識庫 JSON 路徑。

    Returns:
        以 ``ChromaVectorRetriever`` 組好的 handler；失敗則回 baseline handler。
    """
    strategy = load_strategy(strategy_path)
    try:
        # lazy import：未裝 chromadb 時不影響 baseline 路徑可用性。
        from modules.knowledge.chroma_retrieve import ChromaVectorRetriever

        retriever = ChromaVectorRetriever.build(
            strategy=strategy, export_dir=export_dir, model_dir=model_dir
        )
        # warmup：強制首次載入嵌入模型，把 lazy 的 EmbedderUnavailable 提前到
        # 此處觸發 → 落入下方 except 一併 fallback baseline。
        retriever.retrieve(RetrievalQuery(text="warmup"))
        return AlertHandler(retriever=retriever, strategy=strategy)
    except Exception as exc:  # noqa: BLE001 — 任何升級失敗都退回 baseline，不阻啟動
        logger.warning(
            "ChromaVectorRetriever 建立失敗（%s），fallback 回 baseline keyword retriever。",
            exc,
        )
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
    "build_chroma_alert_handler",
    "default_strategy",
    "load_chunks",
    "load_strategy",
]
