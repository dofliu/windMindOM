"""retrieve（BaselineLexicalRetriever）單元測試（WMOM-20260601-01）。

涵蓋：term 抽取（中英 / 代碼）、警報碼加權、關鍵詞 > 內文 權重、top_k 邊界、
機型過濾、決定性排序、無命中不回傳，以及對 baseline 語料的端到端命中。
"""

from __future__ import annotations

from modules.knowledge.ingest import load_chunks_from_jsonl
from modules.knowledge.retrieve import (
    BaselineLexicalRetriever,
    _extract_terms,
    _normalize_code,
)
from modules.knowledge.schemas.knowledge_schemas import KnowledgeQuery, ManualChunk
from modules.knowledge.strategy_loader import BASELINE_STRATEGY_PATH

_BASELINE_CORPUS = BASELINE_STRATEGY_PATH.parent / "z72_manual_baseline.jsonl"


# ── term 抽取 ──────────────────────────────────────────────────────────


def test_extract_terms_ascii_lowercased() -> None:
    terms = _extract_terms("Bearing WGEN_GnBrgTmp1 262")
    assert "bearing" in terms
    assert "wgen_gnbrgtmp1" in terms
    assert "262" in terms


def test_extract_terms_cjk_bigrams() -> None:
    terms = _extract_terms("軸承溫度")
    assert "軸承" in terms
    assert "承溫" in terms
    assert "溫度" in terms


def test_extract_terms_single_cjk_kept() -> None:
    assert "冰" in _extract_terms("冰")


def test_extract_terms_drops_single_ascii_char() -> None:
    """A-262 拆出的單字母 a 屬雜訊，不應成為 term（避免誤命中）。"""
    terms = _extract_terms("A-262 溫度")
    assert "a" not in terms
    assert "262" in terms


def test_normalize_code_variants_collapse() -> None:
    assert _normalize_code("A-262") == _normalize_code("a 262") == "a262"
    assert _normalize_code("262") == "262"


# ── 計分 / 權重 ───────────────────────────────────────────────────────


def _toy_corpus() -> list[ManualChunk]:
    return [
        ManualChunk(
            chunk_id="c1",
            source="m",
            text="軸承溫度過高請檢查潤滑",
            keywords=["軸承", "潤滑"],
            fault_codes=["A-262", "262"],
        ),
        ManualChunk(
            chunk_id="c2",
            source="m",
            text="偏航煞車液壓壓力低",
            keywords=["偏航", "液壓"],
            fault_codes=["A-260", "260"],
        ),
    ]


def test_fault_code_match_dominates() -> None:
    """帶 fault_code 時，對應 chunk 因高權重排第一。"""
    r = BaselineLexicalRetriever(_toy_corpus())
    res = r.retrieve(KnowledgeQuery(text="壓力", fault_code="A-262", top_k=2))
    assert res[0].chunk.chunk_id == "c1"
    assert res[0].score >= 10.0
    assert "A-262" in res[0].matched_terms


def test_keyword_weighs_more_than_text() -> None:
    """命中 keyword 的 chunk 分數高於只命中內文的。"""
    chunks = [
        ManualChunk(chunk_id="kw", source="m", text="無關內容", keywords=["潤滑"]),
        ManualChunk(chunk_id="txt", source="m", text="這裡提到潤滑兩字", keywords=[]),
    ]
    r = BaselineLexicalRetriever(chunks)
    res = r.retrieve(KnowledgeQuery(text="潤滑", top_k=2))
    assert res[0].chunk.chunk_id == "kw"
    assert res[0].score > res[1].score


def test_no_match_returns_empty() -> None:
    """完全無命中不硬塞結果。"""
    r = BaselineLexicalRetriever(_toy_corpus())
    res = r.retrieve(KnowledgeQuery(text="xyzzy 完全無關", top_k=3))
    assert res == []


def test_top_k_zero_returns_empty() -> None:
    r = BaselineLexicalRetriever(_toy_corpus())
    assert r.retrieve(KnowledgeQuery(text="軸承", top_k=0)) == []


def test_top_k_caps_results() -> None:
    r = BaselineLexicalRetriever(_toy_corpus())
    res = r.retrieve(KnowledgeQuery(text="軸承 偏航", top_k=1))
    assert len(res) == 1


def test_matched_terms_sorted_and_deduped() -> None:
    r = BaselineLexicalRetriever(_toy_corpus())
    res = r.retrieve(KnowledgeQuery(text="軸承 軸承 潤滑", top_k=1))
    assert res[0].matched_terms == sorted(res[0].matched_terms)


def test_deterministic_tiebreak_by_chunk_id() -> None:
    """同分時以 chunk_id 字典序穩定排序。"""
    chunks = [
        ManualChunk(chunk_id="zzz", source="m", text="潤滑", keywords=[]),
        ManualChunk(chunk_id="aaa", source="m", text="潤滑", keywords=[]),
    ]
    r = BaselineLexicalRetriever(chunks)
    res = r.retrieve(KnowledgeQuery(text="潤滑", top_k=2))
    assert [rc.chunk.chunk_id for rc in res] == ["aaa", "zzz"]


# ── 機型過濾 ──────────────────────────────────────────────────────────


def test_oem_model_filter() -> None:
    chunks = [
        ManualChunk(chunk_id="z", source="m", text="潤滑", oem_model="Z72"),
        ManualChunk(chunk_id="v", source="m", text="潤滑", oem_model="V164"),
    ]
    r = BaselineLexicalRetriever(chunks)
    res = r.retrieve(KnowledgeQuery(text="潤滑", oem_model="Z72", top_k=5))
    assert [rc.chunk.chunk_id for rc in res] == ["z"]


def test_candidate_count_per_model() -> None:
    chunks = [
        ManualChunk(chunk_id="z1", source="m", text="x", oem_model="Z72"),
        ManualChunk(chunk_id="z2", source="m", text="x", oem_model="Z72"),
        ManualChunk(chunk_id="v1", source="m", text="x", oem_model="V164"),
    ]
    r = BaselineLexicalRetriever(chunks)
    assert r.candidate_count("Z72") == 2
    assert r.candidate_count("v164") == 1
    assert r.candidate_count("NONE") == 0


# ── 端到端：baseline 語料 ─────────────────────────────────────────────


def test_baseline_corpus_bearing_query() -> None:
    """以實際 baseline 語料查『軸承高溫』命中 bearing_wear chunk。"""
    r = BaselineLexicalRetriever(load_chunks_from_jsonl(_BASELINE_CORPUS))
    res = r.retrieve(KnowledgeQuery(text="軸承溫度高", fault_code="A-262", top_k=3))
    assert res
    assert res[0].chunk.chunk_id == "z72-bearing_wear-01"


def test_baseline_corpus_numeric_code_matches() -> None:
    """純數字警報碼（262）也能命中（語料同時收錄帶/不帶前綴兩式）。"""
    r = BaselineLexicalRetriever(load_chunks_from_jsonl(_BASELINE_CORPUS))
    res = r.retrieve(KnowledgeQuery(text="高溫", fault_code="262", top_k=1))
    assert res[0].chunk.chunk_id == "z72-bearing_wear-01"
