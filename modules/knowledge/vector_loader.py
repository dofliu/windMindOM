"""RAG_Ultimate 預算向量檔載入 + schema adapter（M5-2）。

對應 DEC-20260608-01：windMindOM **不自己 re-embed 語料**，只載入 RAG_Ultimate
交付的預算向量檔（`exports/wind_farm_vectors/`）。本 module 負責把那份匯出
讀進記憶體，並把 RAG_Ultimate 的 chunk 形狀 adapt 成 windMindOM 的
``KnowledgeChunk``，供 ``ChromaVectorRetriever`` 灌進 ChromaDB。

設計邊界（刻意）：**只依賴 numpy + json**，不 import chromadb / torch /
sentence-transformers —— 讓「向量檔格式對齊」這層可在無重依賴環境下單獨測試，
也讓 import 成本低。實際向量檢索在 ``chroma_retrieve``。

匯出格式契約（manifest.json 宣告）：
- ``vectors.npy``：float32 ``(N, dim)``，已 L2 normalize（cosine = dot），逐列對齊 chunks.jsonl
- ``chunks.jsonl``：每列 ``{row, id, doc_id, chunk_index, text, ...}``
- ``manifest.json``：``{embedding_model, vector_dim, normalized, num_chunks, ...}``
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from modules.knowledge.schemas import KnowledgeChunk

logger = logging.getLogger(__name__)

# 預設向量檔位置：repo 內 shipped 副本（RAG_Ultimate 交付物複製進來，244KB）。
# 可用 env ``WMOM_VECTOR_EXPORT_DIR`` 覆寫（指向 RAG_Ultimate 原始匯出 / 客戶部署路徑）。
DEFAULT_EXPORT_DIR = (
    Path(__file__).resolve().parent / "data" / "wind_farm_vectors"
)
_ENV_EXPORT_DIR = "WMOM_VECTOR_EXPORT_DIR"


class VectorExportError(RuntimeError):
    """向量檔缺失 / 格式不符 / 列數維度對不上時拋出。

    呼叫端（``build_chroma_alert_handler``）攔此例外即可 graceful fallback
    回 baseline retriever，不讓平台啟動失敗。
    """


@dataclass(frozen=True)
class VectorExport:
    """載入後的預算向量檔（chunks 與 vectors 逐列對齊）。"""

    chunks: list[KnowledgeChunk]
    vectors: np.ndarray  # float32 (N, dim)
    manifest: dict[str, object]

    @property
    def dim(self) -> int:
        """向量維度（query encoder 必須輸出相同維度才能比對）。"""
        return int(self.vectors.shape[1])

    def __len__(self) -> int:
        """chunk 數（= 向量列數）。"""
        return len(self.chunks)


def resolve_export_dir(export_dir: str | Path | None = None) -> Path:
    """決定向量檔目錄：明確參數 > env > 預設 shipped 位置。"""
    if export_dir is not None:
        return Path(export_dir)
    env = os.environ.get(_ENV_EXPORT_DIR)
    if env:
        return Path(env)
    return DEFAULT_EXPORT_DIR


def _adapt_chunk(raw: dict[str, object], *, oem: str, model: str) -> KnowledgeChunk:
    """把 RAG_Ultimate 一筆 chunk 轉成 windMindOM ``KnowledgeChunk``。

    映射（DEC-20260608-01）：
    - ``doc_id`` → ``document_source``
    - ``chunk_index`` → ``section``（"chunk N"）；RAG_Ultimate 無章節欄位
    - ``id`` → ``id`` 兼 ``embedding_vector_id``（ChromaDB 內以同 id 存向量）
    - ``alarm_codes`` / ``keywords`` 留空：向量檢索靠語意相似度，不靠碼/關鍵字
      （baseline retriever 才用那兩者）

    oem / model 由 manifest 推不出，故由上層（策略檔）帶入，預設 Bachmann / Z72。
    """
    # 用 `is None` 而非 `or ""`：避免 id=0（整數 falsy）被誤判為缺 id
    # —— RAG_Ultimate 未明定 id 必為 UUID，未來可能改用 row int。
    chunk_id_raw = raw.get("id")
    if chunk_id_raw is None:
        raise VectorExportError("chunk 缺 id 欄位，無法對齊向量")
    chunk_id = str(chunk_id_raw)
    if not chunk_id:
        raise VectorExportError("chunk id 為空字串，無法對齊向量")

    text = str(raw.get("text") or "")
    doc_id = str(raw.get("doc_id") or "unknown")
    chunk_index = raw.get("chunk_index")
    section = f"chunk {chunk_index}" if chunk_index is not None else None

    return KnowledgeChunk(
        id=chunk_id,
        document_source=doc_id,
        section=section,
        chunk_text=text,
        oem=oem,
        model=model,
        alarm_codes=[],
        keywords=[],
        embedding_vector_id=chunk_id,
    )


def load_vector_export(
    export_dir: str | Path | None = None,
    *,
    oem: str = "Bachmann",
    model: str = "Z72",
) -> VectorExport:
    """載入 RAG_Ultimate 預算向量檔並回傳對齊好的 ``VectorExport``。

    Args:
        export_dir: 匯出目錄；``None`` 時依 ``resolve_export_dir`` 解析。
        oem / model: adapt 後 chunk 的 OEM / 機型（manifest 無此資訊，由策略帶入）。

    Returns:
        ``VectorExport``（chunks 與 vectors 逐列對齊、維度一致）。

    Raises:
        VectorExportError: 目錄/檔案缺失、JSON 壞、列數或維度對不上、向量非 2D。
    """
    base = resolve_export_dir(export_dir)
    manifest_path = base / "manifest.json"
    chunks_path = base / "chunks.jsonl"
    vectors_path = base / "vectors.npy"

    for p in (manifest_path, chunks_path, vectors_path):
        if not p.is_file():
            raise VectorExportError(f"向量檔缺失：{p}（預期 RAG_Ultimate 匯出三件套齊全）")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise VectorExportError(f"manifest.json 解析失敗：{exc}") from exc

    try:
        vectors = np.load(vectors_path)
    except (ValueError, OSError) as exc:
        raise VectorExportError(f"vectors.npy 載入失敗：{exc}") from exc

    if vectors.ndim != 2:
        raise VectorExportError(f"vectors.npy 應為 2D (N, dim)，實得 shape={vectors.shape}")
    # ChromaDB / cosine 比對統一用 float32，避免 dtype 不一致。
    vectors = np.ascontiguousarray(vectors, dtype=np.float32)

    # 逐列讀 chunks.jsonl（與 vectors 第 i 列對齊）。
    chunks: list[KnowledgeChunk] = []
    for line_no, line in enumerate(
        chunks_path.read_text(encoding="utf-8").splitlines()
    ):
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            # 同時報「檔案行號」與「第幾個非空 chunk」，方便 jq / 編輯器對位。
            raise VectorExportError(
                f"chunks.jsonl 第 {line_no} 行（第 {len(chunks)} 個非空 chunk）JSON 壞：{exc}"
            ) from exc
        chunks.append(_adapt_chunk(raw, oem=oem, model=model))

    if len(chunks) != vectors.shape[0]:
        raise VectorExportError(
            f"chunks 列數（{len(chunks)}）≠ vectors 列數（{vectors.shape[0]}），無法逐列對齊"
        )

    # manifest 宣告的維度若與實際不符，提早擋下（避免 query encoder 維度錯配）。
    # 用 int() 轉型容忍 JSON 寫成 512.0（float），不可轉型則視為格式錯。
    declared_dim = manifest.get("vector_dim")
    if declared_dim is not None:
        try:
            declared_dim_int = int(declared_dim)  # type: ignore[arg-type]  # 下方 except 接非數值
        except (TypeError, ValueError) as exc:
            raise VectorExportError(
                f"manifest vector_dim 不可轉為整數：{declared_dim!r}"
            ) from exc
        if declared_dim_int != vectors.shape[1]:
            raise VectorExportError(
                f"manifest vector_dim={declared_dim} 與 vectors 實際維度 {vectors.shape[1]} 不符"
            )

    logger.info(
        "載入向量檔：%d chunks / dim=%d / model=%s",
        len(chunks),
        vectors.shape[1],
        manifest.get("embedding_model", "?"),
    )
    return VectorExport(chunks=chunks, vectors=vectors, manifest=manifest)
