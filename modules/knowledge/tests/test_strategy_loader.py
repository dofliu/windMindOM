"""strategy_loader 單元測試（WMOM-20260601-01）。

涵蓋：baseline 預設、合法 YAML 載入、路徑解析、缺檔 / 壞 YAML / schema
錯誤的失敗路徑、以及 load_strategy_or_baseline 的回退語意。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.knowledge.strategy_loader import (
    BASELINE_STRATEGY_PATH,
    RagStrategy,
    default_strategy,
    load_strategy,
    load_strategy_or_baseline,
)


def test_default_strategy_is_baseline() -> None:
    """default_strategy 不讀檔即回傳可用的 baseline placeholder。"""
    strategy = default_strategy()
    assert strategy.version == "baseline-0.1"
    assert strategy.oem_model == "Z72"
    assert strategy.embedding.provider == "baseline-lexical"
    assert strategy.retrieval.top_k == 3
    assert strategy.corpus.format == "jsonl"
    assert strategy.corpus.source.endswith(".jsonl")


def test_baseline_strategy_yaml_loads() -> None:
    """repo 內附的 baseline strategy.yaml 能被解析成 RagStrategy。"""
    strategy = load_strategy(BASELINE_STRATEGY_PATH)
    assert isinstance(strategy, RagStrategy)
    assert strategy.version == "baseline-0.1"
    assert strategy.corpus.source == "z72_manual_baseline.jsonl"


def test_resolve_corpus_path_relative() -> None:
    """相對 corpus 路徑以 base_dir 解析為絕對路徑。"""
    strategy = default_strategy()
    base = Path("/tmp/some/strategy/dir")
    resolved = strategy.resolve_corpus_path(base)
    assert resolved.is_absolute()
    assert resolved.name == "z72_manual_baseline.jsonl"
    assert str(resolved).startswith("/tmp/some/strategy/dir")


def test_resolve_corpus_path_absolute_preserved(tmp_path: Path) -> None:
    """絕對 corpus 路徑不被 base_dir 改寫。"""
    abs_corpus = tmp_path / "elsewhere" / "corpus.jsonl"
    strategy = RagStrategy.model_validate(
        {
            "version": "x",
            "corpus": {"source": str(abs_corpus), "format": "jsonl"},
        }
    )
    assert strategy.resolve_corpus_path(Path("/unused")) == abs_corpus


def test_load_strategy_missing_file_raises(tmp_path: Path) -> None:
    """缺檔顯性拋 FileNotFoundError。"""
    with pytest.raises(FileNotFoundError):
        load_strategy(tmp_path / "nope.yaml")


def test_load_strategy_bad_yaml_raises(tmp_path: Path) -> None:
    """YAML 內容非 mapping 時拋 ValueError。"""
    bad = tmp_path / "bad.yaml"
    bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_strategy(bad)


def test_load_strategy_schema_error_raises(tmp_path: Path) -> None:
    """缺必填欄位（corpus）時拋 ValueError。"""
    incomplete = tmp_path / "incomplete.yaml"
    incomplete.write_text("version: x\noem_model: Z72\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_strategy(incomplete)


def test_load_or_baseline_none_returns_baseline() -> None:
    """path=None 直接回 baseline，不拋例外。"""
    assert load_strategy_or_baseline(None).version == "baseline-0.1"


def test_load_or_baseline_missing_falls_back(tmp_path: Path) -> None:
    """指定路徑不存在時回退 baseline（不中斷流程）。"""
    strategy = load_strategy_or_baseline(tmp_path / "ghost.yaml")
    assert strategy.version == "baseline-0.1"


def test_load_or_baseline_schema_error_still_raises(tmp_path: Path) -> None:
    """存在但 schema 壞的策略檔仍顯性失敗（屬策略檔 bug，不該被靜默吞掉）。"""
    broken = tmp_path / "broken.yaml"
    broken.write_text("version: x\n", encoding="utf-8")  # 缺 corpus
    with pytest.raises(ValueError):
        load_strategy_or_baseline(broken)
