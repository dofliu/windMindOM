"""corpus 測試 — baseline 知識庫載入 + 查詢輔助（M5-1）。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.knowledge.corpus import (  # noqa: E402
    DEFAULT_CORPUS_PATH,
    KnowledgeCorpus,
    load_chunks,
)
from modules.knowledge.schemas import KnowledgeChunk  # noqa: E402


# baseline corpus 必含的 11 個 Z72 fault scenario SOP（對齊
# modules/monitoring/simulator/physics/fault_engine.py 的 FAULT_SCENARIOS）。
# 用 subset 而非精確相等 —— 容許 M5-3 接 RAG_Ultimate 後補充新 chunk。
_EXPECTED_BASELINE_IDS = {
    "z72-sop-bearing-wear",
    "z72-sop-generator-overspeed",
    "z72-sop-converter-cooling",
    "z72-sop-transformer-overheat",
    "z72-sop-pitch-imbalance",
    "z72-sop-yaw-sensor-drift",
    "z72-sop-stator-winding",
    "z72-sop-hydraulic-leak",
    "z72-sop-blade-icing",
    "z72-sop-grid-voltage-sag",
    "z72-sop-nacelle-cooling",
}


def test_load_builtin_baseline_corpus() -> None:
    """內建 baseline corpus 應含 11 個 fault scenario chunk（對齊 fault_engine）。"""
    chunks = load_chunks()
    assert DEFAULT_CORPUS_PATH.is_file()
    # 至少含 11 個 baseline scenario（容許未來增長，不鎖死精確數量）。
    assert len(chunks) >= 11
    assert all(isinstance(c, KnowledgeChunk) for c in chunks)
    # 每塊都有告警碼與關鍵字（baseline retriever 仰賴）。
    assert all(c.alarm_codes for c in chunks)
    assert all(c.keywords for c in chunks)
    # chunk id 不重複。
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))
    # 11 個 fault scenario SOP 都在。
    assert _EXPECTED_BASELINE_IDS.issubset(set(ids))


def test_corpus_len_and_chunks_copy() -> None:
    """len 正確；chunks property 回 copy（外部 append 不影響內部）。"""
    corpus = KnowledgeCorpus.load()
    n = len(corpus)
    exported = corpus.chunks
    exported.append(
        KnowledgeChunk(id="x", document_source="m", chunk_text="t")
    )
    assert len(corpus) == n  # 內部未被汙染


def test_by_alarm_code_hits() -> None:
    """converter 冷卻碼 21 應命中變頻器冷卻 chunk。"""
    corpus = KnowledgeCorpus.load()
    hits = corpus.by_alarm_code(21)
    assert hits
    assert any("變頻器" in c.chunk_text for c in hits)


def test_by_alarm_code_miss_returns_empty() -> None:
    """不存在的碼回空 list（非 None）。"""
    corpus = KnowledgeCorpus.load()
    assert corpus.by_alarm_code(99999) == []


def test_filter_by_model() -> None:
    """全 baseline corpus 皆 Z72；filter Z72 不變、filter 其他機型變空。"""
    corpus = KnowledgeCorpus.load()
    assert len(corpus.filter(model="Z72")) == len(corpus)
    assert len(corpus.filter(model="V236")) == 0


def test_filter_none_is_unconstrained() -> None:
    """filter(None, None) 不限，回全部。"""
    corpus = KnowledgeCorpus.load()
    assert len(corpus.filter()) == len(corpus)


def test_filter_returns_new_corpus() -> None:
    """filter 回新 KnowledgeCorpus（不改原物件）。"""
    corpus = KnowledgeCorpus.load()
    filtered = corpus.filter(oem="Bachmann")
    assert isinstance(filtered, KnowledgeCorpus)
    assert filtered is not corpus


def test_missing_file_returns_empty(tmp_path: Path) -> None:
    """corpus 檔缺失 → 回空 corpus（平台仍可啟動）。"""
    corpus = KnowledgeCorpus.load(tmp_path / "nope.json")
    assert corpus.is_empty()
    assert len(corpus) == 0


def test_empty_corpus_is_empty() -> None:
    """空 chunk 清單 → is_empty True。"""
    assert KnowledgeCorpus([]).is_empty()


def test_partial_corrupt_chunk_skipped(tmp_path: Path) -> None:
    """單筆 chunk 損毀 → skip 該筆、仍載入其餘（平台不因一筆壞資料中止）。"""
    import json

    bad_corpus = tmp_path / "partial.json"
    bad_corpus.write_text(
        json.dumps(
            {
                "chunks": [
                    {"id": "ok", "document_source": "m.pdf", "chunk_text": "good"},
                    {"id": "bad-missing-required"},  # 缺 document_source / chunk_text
                ]
            }
        ),
        encoding="utf-8",
    )
    chunks = load_chunks(bad_corpus)
    assert [c.id for c in chunks] == ["ok"]
