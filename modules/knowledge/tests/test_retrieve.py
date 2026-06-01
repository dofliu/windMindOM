"""retrieve 測試 — BaselineKeywordRetriever 評分、排序、過濾、top_k（M5-1）。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.knowledge.corpus import KnowledgeCorpus  # noqa: E402
from modules.knowledge.retrieve import (  # noqa: E402
    BaselineKeywordRetriever,
    Retriever,
    tokenize,
)
from modules.knowledge.schemas import (  # noqa: E402
    KnowledgeChunk,
    RagStrategy,
    RetrievalQuery,
)


def _chunk(
    cid: str,
    text: str = "",
    codes: list[int] | None = None,
    keywords: list[str] | None = None,
    model: str = "Z72",
    oem: str = "Bachmann",
) -> KnowledgeChunk:
    return KnowledgeChunk(
        id=cid,
        document_source="m.pdf",
        chunk_text=text,
        alarm_codes=codes or [],
        keywords=keywords or [],
        model=model,
        oem=oem,
    )


def _retriever(chunks: list[KnowledgeChunk], top_k: int = 3) -> BaselineKeywordRetriever:
    strategy = RagStrategy.model_validate({"retrieval": {"top_k": top_k}})
    return BaselineKeywordRetriever(corpus=KnowledgeCorpus(chunks), strategy=strategy)


# ── tokenizer ──────────────────────────────────────────────────────────


class TestTokenize:
    def test_ascii_words_and_underscore_tag(self) -> None:
        """英數 token 含底線（SCADA tag 風格）。"""
        toks = tokenize("Check WCNV_IGCTWtrTmp now")
        assert "wcnv_igctwtrtmp" in toks
        assert "check" in toks

    def test_cjk_bigram(self) -> None:
        """中文切相鄰二字 bigram。"""
        toks = tokenize("變頻器")
        assert "變頻" in toks
        assert "頻器" in toks


# ── retriever 介面 ───────────────────────────────────────────────────────


def test_baseline_retriever_satisfies_protocol() -> None:
    """BaselineKeywordRetriever 為 Retriever 介面實例（runtime_checkable）。"""
    r = _retriever([])
    assert isinstance(r, Retriever)
    assert r.name == "baseline_keyword"
    # 契約屬性：baseline retriever 須標 is_baseline=True（handler 據此設旗標）。
    assert r.is_baseline is True


# ── 評分 ────────────────────────────────────────────────────────────────


def test_alarm_code_hit_dominates() -> None:
    """命中告警碼的 chunk 分數遠高於只關鍵字命中者，且排前面。"""
    chunks = [
        _chunk("code_hit", text="變頻器冷卻", codes=[21], keywords=["變頻器"]),
        _chunk("kw_only", text="其他段落", codes=[999], keywords=["冷卻"]),
    ]
    r = _retriever(chunks)
    results = r.retrieve(RetrievalQuery(text="變頻器 冷卻", alarm_codes=[21]))
    assert results[0].chunk.id == "code_hit"
    assert results[0].score >= 0.6
    assert "命中告警碼 21" in results[0].match_reason


def test_keyword_fraction_scoring() -> None:
    """關鍵字命中比例越高分數越高。"""
    chunks = [
        _chunk("all_kw", keywords=["變頻器", "冷卻", "水冷"]),
        _chunk("half_kw", keywords=["變頻器", "電網", "電壓", "頻率"]),
    ]
    r = _retriever(chunks)
    results = r.retrieve(RetrievalQuery(text="變頻器 冷卻 水冷"))
    by_id = {rc.chunk.id: rc.score for rc in results}
    assert by_id["all_kw"] > by_id["half_kw"]


def test_zero_score_chunks_dropped() -> None:
    """完全不相關的 chunk（無碼、無關鍵字、無文字重疊）不回傳。"""
    chunks = [_chunk("irrelevant", text="zzz", codes=[1], keywords=["foo"])]
    r = _retriever(chunks)
    results = r.retrieve(RetrievalQuery(text="變頻器", alarm_codes=[21]))
    assert results == []


def test_score_clamped_to_one() -> None:
    """碼 + 全關鍵字 + 高文字重疊也不超過 1.0。"""
    chunks = [
        _chunk("strong", text="變頻器冷卻水冷", codes=[21], keywords=["變頻器", "冷卻", "水冷"])
    ]
    r = _retriever(chunks)
    results = r.retrieve(
        RetrievalQuery(text="變頻器冷卻水冷", alarm_codes=[21])
    )
    assert results[0].score <= 1.0


# ── 排序 / top_k / 確定性 ─────────────────────────────────────────────────


def test_top_k_from_strategy() -> None:
    """無 query.top_k 時用策略 top_k 截斷。"""
    chunks = [_chunk(f"c{i}", codes=[21]) for i in range(5)]
    r = _retriever(chunks, top_k=2)
    results = r.retrieve(RetrievalQuery(text="x", alarm_codes=[21]))
    assert len(results) == 2


def test_query_top_k_overrides_strategy() -> None:
    """query.top_k 覆寫策略值。"""
    chunks = [_chunk(f"c{i}", codes=[21]) for i in range(5)]
    r = _retriever(chunks, top_k=2)
    results = r.retrieve(RetrievalQuery(text="x", alarm_codes=[21], top_k=4))
    assert len(results) == 4


def test_tie_break_is_deterministic() -> None:
    """同分時以 chunk.id 穩定排序（可重現）。"""
    chunks = [_chunk("c_b", codes=[21]), _chunk("c_a", codes=[21])]
    r = _retriever(chunks)
    results = r.retrieve(RetrievalQuery(text="x", alarm_codes=[21]))
    assert [rc.chunk.id for rc in results] == ["c_a", "c_b"]


# ── 過濾 ────────────────────────────────────────────────────────────────


def test_model_filter_excludes_other_models() -> None:
    """query 限定 model 時，不同機型 chunk 不參與。"""
    chunks = [
        _chunk("z72", codes=[21], model="Z72"),
        _chunk("v236", codes=[21], model="V236"),
    ]
    r = _retriever(chunks)
    results = r.retrieve(RetrievalQuery(text="x", alarm_codes=[21], model="Z72"))
    assert [rc.chunk.id for rc in results] == ["z72"]


def test_empty_corpus_returns_empty() -> None:
    """空知識庫回空結果（不丟例外）。"""
    r = _retriever([])
    assert r.retrieve(RetrievalQuery(text="x", alarm_codes=[21])) == []


# ── 與真 baseline corpus 串接 ─────────────────────────────────────────────


def test_against_real_baseline_corpus() -> None:
    """用內建 baseline corpus + 策略，碼 21 應檢索到變頻器冷卻段落。"""
    from modules.knowledge.strategy_loader import load_strategy

    corpus = KnowledgeCorpus.load()
    strategy = load_strategy()
    r = BaselineKeywordRetriever(corpus=corpus, strategy=strategy)
    results = r.retrieve(
        RetrievalQuery(text="變頻器 冷卻 水溫過高", alarm_codes=[21], model="Z72")
    )
    assert results
    assert results[0].chunk.id == "z72-sop-converter-cooling"
    # 策略 top_k=3 → 至多 3 筆。
    assert len(results) <= 3
