"""ChromaDB 語意向量檢索器（M5-2）。

對應 DEC-20260608-01。``ChromaVectorRetriever`` 實作既有 ``Retriever`` Protocol
（``is_baseline=False``），把 RAG_Ultimate 預算向量灌進嵌入式 ChromaDB
collection，query 端用 ``Z72_WT_embed_small`` encode 後做 cosine top-k。

``AlertHandler`` / schema / 前端只依賴 ``Retriever`` 介面，故換上本 retriever
不需改動上層（MVP_ARCHITECTURE §3.5 升級契約）。

依賴 chromadb（重）+ sentence-transformers（透過 ``embedder``）。import 階段
不載重套件 / 不建 collection；建構 retriever 才實際拉起，失敗拋例外讓上層
fallback baseline。
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from modules.knowledge.embedder import QueryEmbedder
from modules.knowledge.schemas import (
    KnowledgeChunk,
    RagStrategy,
    RetrievalQuery,
    RetrievedChunk,
)
from modules.knowledge.vector_loader import VectorExport, load_vector_export

logger = logging.getLogger(__name__)

# ChromaDB collection 命名限制：3-512 字元、[a-zA-Z0-9._-]、頭尾為英數。
# 多個 EphemeralClient() 共用同一記憶體後端，同名 collection 會撞 —— 每個
# retriever 實例用唯一後綴隔離（uuid hex 為英數，符合命名規則）。
_COLLECTION_PREFIX = "z72_knowledge"


class ChromaVectorRetriever:
    """語意向量檢索器（實作 ``Retriever`` 介面）。"""

    name = "chroma_vector"
    # 真向量檢索（非 placeholder），前端 badge 標示「語意檢索」而非 baseline。
    is_baseline = False

    def __init__(
        self,
        export: VectorExport,
        embedder: QueryEmbedder,
        strategy: RagStrategy,
    ) -> None:
        """以預算向量檔 + query 嵌入器 + 策略建立 retriever。

        建構時即把向量灌進 in-memory ChromaDB collection（語料小、程序生命週期
        內不變，啟動一次即可）。

        Args:
            export: 已載入並對齊的 ``VectorExport``（chunks ⇄ vectors 逐列對齊）。
            embedder: query 端嵌入器（須與語料同模型同維度）。
            strategy: RAG 策略（提供預設 top_k）。

        Raises:
            ImportError: 未安裝 chromadb。
            ValueError: 語料為空（無法建 collection）。
        """
        self._embedder = embedder
        self._strategy = strategy
        # id → KnowledgeChunk：query 回 id 後直接還原原始 chunk（不靠 chroma metadata
        # 序列化，避開「metadata 不能存 list / None」限制，也保留完整型別）。
        self._by_id: dict[str, KnowledgeChunk] = {c.id: c for c in export.chunks}

        if not export.chunks:
            raise ValueError("向量檔語料為空，無法建立 ChromaVectorRetriever")

        # lazy import：未裝 chromadb 時 module 仍可被 import（baseline 路徑不受影響）。
        import chromadb

        # Ephemeral（純記憶體）client：語料由 RAG_Ultimate 預算，不需 persist；
        # 每個 retriever 實例獨立 client，避免 collection 同名衝突。
        self._client = chromadb.EphemeralClient()
        self._collection = self._client.create_collection(
            name=f"{_COLLECTION_PREFIX}_{uuid.uuid4().hex}",
            metadata={"hnsw:space": "cosine"},  # cosine：向量已 L2 normalize
        )
        self._collection.add(
            ids=[c.id for c in export.chunks],
            embeddings=export.vectors.tolist(),
            documents=[c.chunk_text for c in export.chunks],
            # 只存過濾用得到的維度；本體還原走 self._by_id。
            metadatas=[{"oem": c.oem, "model": c.model} for c in export.chunks],
        )
        logger.info("ChromaVectorRetriever 就緒：%d chunks / dim=%d", len(export), export.dim)

    @classmethod
    def build(
        cls,
        strategy: RagStrategy,
        export_dir: str | Path | None = None,
        model_dir: str | Path | None = None,
    ) -> "ChromaVectorRetriever":
        """便捷工廠：載入向量檔 + 建嵌入器 + 組 retriever。

        Raises:
            VectorExportError: 向量檔缺失 / 格式不符。
            ImportError: 未安裝 chromadb。
            （embedder 的模型缺失要到首次 ``retrieve`` 才會觸發 ``EmbedderUnavailable``）
        """
        export = load_vector_export(export_dir, oem=strategy.oem, model=strategy.model)
        embedder = QueryEmbedder(model_dir)
        return cls(export=export, embedder=embedder, strategy=strategy)

    @staticmethod
    def _build_where(query: RetrievalQuery) -> dict[str, object] | None:
        """依 query 的 oem / model 組 ChromaDB metadata 過濾條件（None 表不限）。"""
        conditions: list[dict[str, object]] = []
        if query.oem is not None:
            conditions.append({"oem": query.oem})
        if query.model is not None:
            conditions.append({"model": query.model})
        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    def retrieve(self, query: RetrievalQuery) -> list[RetrievedChunk]:
        """encode query → cosine top-k → 還原為 ``RetrievedChunk``（依相關度排序）。

        Raises:
            EmbedderUnavailable: 模型 / 套件缺失（首次 encode 觸發）。
        """
        top_k = (
            query.top_k if query.top_k is not None else self._strategy.retrieval.top_k
        )
        query_vec = self._embedder.encode(query.text)

        result = self._collection.query(
            query_embeddings=[query_vec.tolist()],
            n_results=top_k,
            where=self._build_where(query),
            include=["distances"],  # 只要距離；本體走 self._by_id（ids 預設一定回）
        )

        # 對稱取值：兩者都用 `or [[]]` 防 None，避免 distances 缺失時 zip 靜默
        # 截斷成空結果（前端顯示「無命中」卻無錯）。distances 因 include 一定回。
        ids = (result["ids"] or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        if len(ids) != len(distances):
            raise RuntimeError(
                f"ChromaDB 回傳 ids/distances 長度不一致：{len(ids)} vs {len(distances)}"
            )

        retrieved: list[RetrievedChunk] = []
        for chunk_id, distance in zip(ids, distances):
            chunk = self._by_id.get(chunk_id)
            if chunk is None:  # pragma: no cover — id 一定來自加入時的集合
                continue
            # cosine distance d = 1 - cos；normalized 向量下 cos = 1 - d。
            # clamp 0..1 對齊 RetrievedChunk.score 約束（負相關歸 0）。
            similarity = max(0.0, min(1.0, 1.0 - float(distance)))
            retrieved.append(
                RetrievedChunk(
                    chunk=chunk,
                    score=similarity,
                    match_reason=f"語意相似度 {similarity:.2f}",
                )
            )
        # chroma 已依距離升冪（最相近在前）回傳；score 降冪等價，無需再排。
        return retrieved
