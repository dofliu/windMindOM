"""ingest 單元測試（WMOM-20260601-01）。

涵蓋：jsonl 載入、空行略過、缺檔 / 壞 JSON / schema 錯誤帶行號、依策略建
檢索器、不支援格式拒絕、以及 repo 內 baseline 語料的健全性。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.knowledge.ingest import build_retriever, load_chunks_from_jsonl
from modules.knowledge.retrieve import BaselineLexicalRetriever
from modules.knowledge.strategy_loader import (
    BASELINE_STRATEGY_PATH,
    RagStrategy,
    default_strategy,
    load_strategy,
)

_BASELINE_DIR = BASELINE_STRATEGY_PATH.parent


def test_load_baseline_corpus_nonempty() -> None:
    """repo 內 baseline 語料能載入且非空。"""
    chunks = load_chunks_from_jsonl(_BASELINE_DIR / "z72_manual_baseline.jsonl")
    assert len(chunks) >= 10
    assert all(c.chunk_id for c in chunks)
    assert all(c.oem_model == "Z72" for c in chunks)


def test_baseline_chunk_ids_unique() -> None:
    """語料 chunk_id 全域唯一（避免檢索去重與引用混淆）。"""
    chunks = load_chunks_from_jsonl(_BASELINE_DIR / "z72_manual_baseline.jsonl")
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))


def test_load_skips_blank_lines(tmp_path: Path) -> None:
    """空行 / 純空白行被略過。"""
    corpus = tmp_path / "c.jsonl"
    corpus.write_text(
        '{"chunk_id": "a", "source": "s", "text": "hello"}\n'
        "\n"
        "   \n"
        '{"chunk_id": "b", "source": "s", "text": "world"}\n',
        encoding="utf-8",
    )
    chunks = load_chunks_from_jsonl(corpus)
    assert [c.chunk_id for c in chunks] == ["a", "b"]


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_chunks_from_jsonl(tmp_path / "nope.jsonl")


def test_load_bad_json_reports_line_number(tmp_path: Path) -> None:
    """壞 JSON 行的錯誤訊息帶行號。"""
    corpus = tmp_path / "c.jsonl"
    corpus.write_text(
        '{"chunk_id": "a", "source": "s", "text": "ok"}\n'
        "{not valid json}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="第 2 行"):
        load_chunks_from_jsonl(corpus)


def test_load_schema_error_reports_line_number(tmp_path: Path) -> None:
    """缺必填欄位（text）的行報 schema 錯誤帶行號。"""
    corpus = tmp_path / "c.jsonl"
    corpus.write_text('{"chunk_id": "a", "source": "s"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="第 1 行"):
        load_chunks_from_jsonl(corpus)


def test_build_retriever_from_baseline_strategy() -> None:
    """依 baseline 策略 + base_dir 建出可用檢索器。"""
    strategy = load_strategy(BASELINE_STRATEGY_PATH)
    retriever = build_retriever(strategy, _BASELINE_DIR)
    assert isinstance(retriever, BaselineLexicalRetriever)
    assert retriever.size >= 10


def test_unsupported_corpus_format_rejected_at_schema() -> None:
    """非 jsonl 格式在 schema 層即被拒絕（CorpusConfig.format = Literal["jsonl"]）。"""
    with pytest.raises(ValueError, match="jsonl"):
        RagStrategy.model_validate(
            {
                "version": "x",
                "corpus": {"source": "x.parquet", "format": "parquet"},
            }
        )


def test_build_retriever_propagates_min_score() -> None:
    """策略檔 retrieval.min_score 被帶入檢索器（不再是死配置）。"""
    strategy = RagStrategy.model_validate(
        {
            "version": "x",
            "retrieval": {"top_k": 3, "min_score": 2.5},
            "corpus": {"source": "z72_manual_baseline.jsonl", "format": "jsonl"},
        }
    )
    retriever = build_retriever(strategy, _BASELINE_DIR)
    assert retriever.min_score == 2.5


def test_build_retriever_default_strategy_resolves_corpus() -> None:
    """default_strategy 的相對 corpus 能在 baseline 目錄解析並載入。"""
    retriever = build_retriever(default_strategy(), _BASELINE_DIR)
    assert retriever.size >= 10
