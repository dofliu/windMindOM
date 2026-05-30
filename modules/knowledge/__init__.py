"""knowledge module — 警報手冊 RAG（M5）。

核心模型：策略檔 + 預計算向量檔由 RAG_Ultimate 研究端提供，本 module 只負責
載入 + query，不重新 embed（見 ``docs/product/MVP_ARCHITECTURE.md`` §3.5）。

M5 (2026-09) 逐步填入：
- ``strategy_loader.py``  ✅ M5-1 Part 1：載入 / 驗證 RAG 策略檔（本 session 完成）
- ``ingest.py``           ⬜ M5-1：PDF/csv → chunk → embed → vector store
- ``retrieve.py``         ⬜ M5-1：query → top-k chunks
- ``alert_handler.py``    ⬜ M5-1：警報事件 → 自動 retrieve
整合 ChromaDB（嵌入式模式）屬 M5-2。
"""

from modules.knowledge.strategy_loader import (
    ChunkingStrategy,
    EmbeddingStrategy,
    RagStrategy,
    RetrievalStrategy,
    StrategyError,
    baseline_strategy,
    load_strategy,
    load_strategy_or_baseline,
    parse_strategy,
)

__all__ = [
    "ChunkingStrategy",
    "EmbeddingStrategy",
    "RagStrategy",
    "RetrievalStrategy",
    "StrategyError",
    "baseline_strategy",
    "load_strategy",
    "load_strategy_or_baseline",
    "parse_strategy",
]
