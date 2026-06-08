"""ChromaVectorRetriever 測試（M5-2 / WMOM-20260608-01）。

需要 chromadb + sentence-transformers + 已 ship 的 Z72_WT_embed_small 模型。
任一缺失則 skip（CI / 無 GPU 環境不阻擋 baseline 測試），但 fallback 行為
（缺依賴 → 退回 baseline）有獨立、必跑的測試。
"""

from __future__ import annotations

import pytest

from modules.knowledge import build_chroma_alert_handler
from modules.knowledge.embedder import resolve_model_dir
from modules.knowledge.schemas import AlertEvent, RetrievalQuery
from modules.knowledge.strategy_loader import default_strategy

# chromadb 缺 → 整檔 skip（fallback 測試另放在不需 chromadb 的段落見下）。
chromadb = pytest.importorskip("chromadb")
pytest.importorskip("sentence_transformers")

# 模型未 ship（deploy artifact，gitignore）→ skip 真檢索測試。
_MODEL_DIR = resolve_model_dir()
_MODEL_AVAILABLE = _MODEL_DIR.is_dir()
_needs_model = pytest.mark.skipif(
    not _MODEL_AVAILABLE, reason=f"嵌入模型未 ship：{_MODEL_DIR}"
)


@pytest.fixture(scope="module")
def retriever():
    """建一次 ChromaVectorRetriever（載 92MB 模型較慢，module 內共用）。"""
    if not _MODEL_AVAILABLE:
        pytest.skip(f"嵌入模型未 ship：{_MODEL_DIR}")
    from modules.knowledge.chroma_retrieve import ChromaVectorRetriever

    return ChromaVectorRetriever.build(strategy=default_strategy())


# ─────────────────────────────────────────────────────────────────────────
# 契約屬性
# ─────────────────────────────────────────────────────────────────────────


@_needs_model
def test_retriever_contract(retriever) -> None:
    """實作 Retriever 契約：runtime_checkable Protocol + name + is_baseline=False。"""
    from modules.knowledge.retrieve import Retriever

    assert isinstance(retriever, Retriever)  # 結構契約（name/is_baseline/retrieve）
    assert retriever.name == "chroma_vector"
    assert retriever.is_baseline is False


# ─────────────────────────────────────────────────────────────────────────
# 語意檢索
# ─────────────────────────────────────────────────────────────────────────


@_needs_model
def test_semantic_query_returns_relevant_chunk(retriever) -> None:
    """語意查「emergency pitch system」應命中手冊 pitch 相關段落（語意，非關鍵字硬比對）。"""
    result = retriever.retrieve(
        RetrievalQuery(text="emergency pitch system drive train", top_k=5)
    )
    assert result, "應有命中"
    # 完整 Z72 手冊單一 doc_id；改驗 top-5 內有段落文字命中 pitch 主題。
    assert any("pitch" in rc.chunk.chunk_text.lower() for rc in result), (
        f"top-5 文字未命中 pitch；scores={[round(r.score, 2) for r in result]}"
    )


@_needs_model
def test_scores_sorted_and_in_range(retriever) -> None:
    """分數 0..1 且降冪（最相關在前）。"""
    result = retriever.retrieve(RetrievalQuery(text="pitch 變槳控制", top_k=5))
    scores = [rc.score for rc in result]
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert scores == sorted(scores, reverse=True)
    # match_reason 為繁中語意說明。
    assert all("語意相似度" in rc.match_reason for rc in result)


@_needs_model
def test_top_k_respected(retriever) -> None:
    """top_k 限制回傳筆數。"""
    assert len(retriever.retrieve(RetrievalQuery(text="gearbox 齒輪箱", top_k=2))) <= 2
    assert len(retriever.retrieve(RetrievalQuery(text="gearbox 齒輪箱", top_k=5))) <= 5


@_needs_model
def test_where_filter_unknown_model_empty(retriever) -> None:
    """query 限定不存在的機型 → metadata 過濾後無命中（語料皆 Z72）。"""
    result = retriever.retrieve(
        RetrievalQuery(text="軸承", model="NONEXISTENT_MODEL", top_k=3)
    )
    assert result == []


@_needs_model
def test_query_encoded_dim_matches_corpus(retriever) -> None:
    """query 向量維度與語料一致（512），確保 cosine 可比對。"""
    vec = retriever._embedder.encode("測試 query")
    assert vec.shape == (512,)


# ─────────────────────────────────────────────────────────────────────────
# AlertHandler 整合（需模型；fallback 必跑測試見 test_knowledge_fallback.py）
# ─────────────────────────────────────────────────────────────────────────


@_needs_model
def test_alert_handler_with_chroma(retriever) -> None:
    """build_chroma_alert_handler 串起來：警報 → 語意檢索結果（非 baseline）。"""
    handler = build_chroma_alert_handler()
    # 模型在則應拿到 chroma retriever。
    assert handler.retriever.name == "chroma_vector"
    res = handler.on_alert(
        AlertEvent(alarm_code=201, turbine_id="WT001", description="軸承溫度異常")
    )
    assert res.is_baseline is False
    assert res.retriever == "chroma_vector"
