"""向量檔載入 + schema adapter 測試（M5-2 / WMOM-20260608-01）。

只依賴 numpy + json，不需 chromadb / torch —— 驗證「格式對齊」這層在無重依賴
環境也能跑。真實向量檔走 repo 內 shipped 副本（modules/knowledge/data/
wind_farm_vectors，RAG_Ultimate 2026-06-08 交付）。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from modules.knowledge.schemas import KnowledgeChunk
from modules.knowledge.vector_loader import (
    DEFAULT_EXPORT_DIR,
    VectorExport,
    VectorExportError,
    _adapt_chunk,
    load_vector_export,
    resolve_export_dir,
)


# ─────────────────────────────────────────────────────────────────────────
# 真實 shipped 向量檔
# ─────────────────────────────────────────────────────────────────────────


def test_load_shipped_export_basic() -> None:
    """載入 repo 內 shipped 向量檔：完整 Z72 手冊 531 chunks / dim 512 / 逐列對齊。"""
    export = load_vector_export()
    assert isinstance(export, VectorExport)
    assert len(export) == 531  # 完整 Z72 手冊（M5-3/4，取代 27-chunk fixture）
    assert export.dim == 512
    assert export.vectors.shape == (531, 512)
    assert export.vectors.dtype == np.float32
    # chunks 與 vectors 列數一致。
    assert len(export.chunks) == export.vectors.shape[0]


def test_shipped_vectors_are_l2_normalized() -> None:
    """manifest 宣告 normalized=true —— 每列 L2 norm 應為 1（cosine = dot）。"""
    export = load_vector_export()
    norms = np.linalg.norm(export.vectors, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-4)


def test_shipped_manifest_contract() -> None:
    """manifest 契約欄位齊全且與實際向量一致（完整 Z72 手冊）。"""
    export = load_vector_export()
    assert export.manifest["vector_dim"] == 512
    assert export.manifest["normalized"] is True
    assert export.manifest["num_chunks"] == 531
    assert export.manifest["embedding_model"] == "Z72_WT_embed_small"
    assert export.manifest["documents"] == ["z72_user_manual"]


def test_adapter_maps_rag_ultimate_to_knowledge_chunk() -> None:
    """adapter：doc_id→document_source、id→embedding_vector_id、碼/關鍵字留空。"""
    export = load_vector_export()
    chunk = export.chunks[0]
    assert isinstance(chunk, KnowledgeChunk)
    assert chunk.document_source  # 來自 doc_id，非空
    assert chunk.chunk_text  # 正文非空
    assert chunk.embedding_vector_id == chunk.id  # 同 id 對齊 chroma 向量
    # 向量檢索不靠告警碼 / 關鍵字 → 留空。
    assert chunk.alarm_codes == []
    assert chunk.keywords == []
    # 策略帶入的 OEM / 機型。
    assert chunk.oem == "Bachmann"
    assert chunk.model == "Z72"


def test_adapter_section_from_chunk_index() -> None:
    """chunk_index 轉成 section 'chunk N'。"""
    raw = {"id": "abc", "doc_id": "scada_alarm_codes", "chunk_index": 3, "text": "x"}
    chunk = _adapt_chunk(raw, oem="Bachmann", model="Z72")
    assert chunk.section == "chunk 3"
    assert chunk.document_source == "scada_alarm_codes"


def test_adapter_missing_id_raises() -> None:
    """chunk 缺 id（None）→ VectorExportError（無法對齊向量）。"""
    with pytest.raises(VectorExportError, match="缺 id"):
        _adapt_chunk({"doc_id": "d", "text": "t"}, oem="Bachmann", model="Z72")


def test_adapter_id_zero_not_rejected() -> None:
    """id=0（整數 falsy）不該被誤判為缺 id（must-fix #1）。"""
    chunk = _adapt_chunk(
        {"id": 0, "doc_id": "d", "chunk_index": 0, "text": "t"},
        oem="Bachmann",
        model="Z72",
    )
    assert chunk.id == "0"
    assert chunk.embedding_vector_id == "0"


def test_adapter_empty_string_id_rejected() -> None:
    """id 為空字串 → VectorExportError。"""
    with pytest.raises(VectorExportError, match="空字串"):
        _adapt_chunk(
            {"id": "", "doc_id": "d", "text": "t"}, oem="Bachmann", model="Z72"
        )


def test_oem_model_override() -> None:
    """load 時可指定 oem / model（策略帶入），套到每個 chunk。"""
    export = load_vector_export(oem="Vestas", model="V164")
    assert all(c.oem == "Vestas" and c.model == "V164" for c in export.chunks)


# ─────────────────────────────────────────────────────────────────────────
# 路徑解析
# ─────────────────────────────────────────────────────────────────────────


def test_resolve_export_dir_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    """明確參數 > env > 預設。"""
    # 明確參數優先。
    assert resolve_export_dir("/explicit/path") == Path("/explicit/path")
    # 無參數 + env。
    monkeypatch.setenv("WMOM_VECTOR_EXPORT_DIR", "/env/path")
    assert resolve_export_dir() == Path("/env/path")
    # 無參數無 env → 預設 shipped。
    monkeypatch.delenv("WMOM_VECTOR_EXPORT_DIR", raising=False)
    assert resolve_export_dir() == DEFAULT_EXPORT_DIR


# ─────────────────────────────────────────────────────────────────────────
# 錯誤路徑（合成 tmp 目錄）
# ─────────────────────────────────────────────────────────────────────────


def test_missing_dir_raises() -> None:
    """目錄不存在 → VectorExportError。"""
    with pytest.raises(VectorExportError, match="缺失"):
        load_vector_export("/no/such/export/dir")


def _write_export(
    tmp: Path, chunks: list[dict], vectors: np.ndarray, manifest: dict
) -> None:
    """在 tmp 目錄寫出一份合成向量檔三件套。"""
    (tmp / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp / "chunks.jsonl").write_text(
        "\n".join(json.dumps(c) for c in chunks), encoding="utf-8"
    )
    np.save(tmp / "vectors.npy", vectors)


def test_row_count_mismatch_raises(tmp_path: Path) -> None:
    """chunks 列數 ≠ vectors 列數 → VectorExportError。"""
    _write_export(
        tmp_path,
        chunks=[{"id": "a", "doc_id": "d", "chunk_index": 0, "text": "x"}],
        vectors=np.zeros((2, 4), dtype=np.float32),  # 2 列 vs 1 chunk
        manifest={"vector_dim": 4},
    )
    with pytest.raises(VectorExportError, match="逐列對齊"):
        load_vector_export(tmp_path)


def test_dim_mismatch_with_manifest_raises(tmp_path: Path) -> None:
    """manifest vector_dim 與實際維度不符 → VectorExportError。"""
    _write_export(
        tmp_path,
        chunks=[{"id": "a", "doc_id": "d", "chunk_index": 0, "text": "x"}],
        vectors=np.zeros((1, 4), dtype=np.float32),
        manifest={"vector_dim": 512},  # 宣告 512，實際 4
    )
    with pytest.raises(VectorExportError, match="不符"):
        load_vector_export(tmp_path)


def test_non_2d_vectors_raises(tmp_path: Path) -> None:
    """vectors 非 2D → VectorExportError。"""
    _write_export(
        tmp_path,
        chunks=[{"id": "a", "doc_id": "d", "chunk_index": 0, "text": "x"}],
        vectors=np.zeros((4,), dtype=np.float32),  # 1D
        manifest={"vector_dim": 4},
    )
    with pytest.raises(VectorExportError, match="2D"):
        load_vector_export(tmp_path)


def test_vector_dim_float_in_manifest_accepted(tmp_path: Path) -> None:
    """manifest vector_dim 寫成 float（512.0）仍正確比對維度（should-fix #3）。"""
    _write_export(
        tmp_path,
        chunks=[{"id": "a", "doc_id": "d", "chunk_index": 0, "text": "x"}],
        vectors=np.ones((1, 4), dtype=np.float32),
        manifest={"vector_dim": 4.0},  # float 而非 int
    )
    export = load_vector_export(tmp_path)  # 不應拋例外
    assert export.dim == 4


def test_vector_dim_non_numeric_raises(tmp_path: Path) -> None:
    """manifest vector_dim 非數值 → VectorExportError。"""
    _write_export(
        tmp_path,
        chunks=[{"id": "a", "doc_id": "d", "chunk_index": 0, "text": "x"}],
        vectors=np.ones((1, 4), dtype=np.float32),
        manifest={"vector_dim": "四"},
    )
    with pytest.raises(VectorExportError, match="不可轉為整數"):
        load_vector_export(tmp_path)


def test_dtype_coerced_to_float32(tmp_path: Path) -> None:
    """float64 向量載入後被轉成 float32（與 cosine / chroma 對齊）。"""
    _write_export(
        tmp_path,
        chunks=[{"id": "a", "doc_id": "d", "chunk_index": 0, "text": "x"}],
        vectors=np.ones((1, 4), dtype=np.float64),
        manifest={"vector_dim": 4},
    )
    export = load_vector_export(tmp_path)
    assert export.vectors.dtype == np.float32
