"""``modules.knowledge.strategy_loader`` 單元測試。

涵蓋：
- ``parse_strategy`` happy path + 每條驗證規則的紅線
- ``load_strategy`` 檔案層（含真實 repo 內的 reference 樣本 yaml）
- ``baseline_strategy`` placeholder 契約
- ``load_strategy_or_baseline`` 失敗退路

刻意只測純解析 / 驗證——不碰 ChromaDB / embedding 推論（屬 M5-2 / retrieve.py）。
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from modules.knowledge.strategy_loader import (
    RagStrategy,
    StrategyError,
    baseline_strategy,
    load_strategy,
    load_strategy_or_baseline,
    parse_strategy,
)

# repo 內 reference 樣本（與 MVP_ARCHITECTURE §3.5 範例對齊）
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SAMPLE_STRATEGY = _REPO_ROOT / "config" / "rag_strategy_z72_manual.yaml"


def _valid_raw() -> dict[str, object]:
    """產生一份合法的策略 dict（各 test 可就地改某欄位測紅線）。"""
    return {
        "name": "z72_manual",
        "version": "2026-05",
        "chunking": {"method": "semantic", "size": 512, "overlap": 50},
        "embedding": {"model": "BAAI/bge-large-zh-v1.5", "dimension": 1024},
        "retrieval": {
            "algorithm": "hybrid_bm25_vector",
            "top_k": 5,
            "rerank": True,
            "rerank_model": "bge-reranker-v2-m3",
        },
    }


# ─────────────────────────────────────────────────────────────────────────
# parse_strategy — happy path
# ─────────────────────────────────────────────────────────────────────────


class TestParseStrategyHappyPath:
    def test_full_strategy_fields_mapped(self) -> None:
        strategy = parse_strategy(_valid_raw(), source_path="x.yaml")
        assert isinstance(strategy, RagStrategy)
        assert strategy.name == "z72_manual"
        assert strategy.version == "2026-05"
        assert strategy.source_path == "x.yaml"
        assert strategy.chunking.method == "semantic"
        assert strategy.chunking.size == 512
        assert strategy.chunking.overlap == 50
        assert strategy.embedding.model == "BAAI/bge-large-zh-v1.5"
        assert strategy.embedding.dimension == 1024
        assert strategy.retrieval.algorithm == "hybrid_bm25_vector"
        assert strategy.retrieval.top_k == 5
        assert strategy.retrieval.rerank is True
        assert strategy.retrieval.rerank_model == "bge-reranker-v2-m3"

    def test_optional_name_version_absent_become_none(self) -> None:
        raw = _valid_raw()
        del raw["name"]
        del raw["version"]
        strategy = parse_strategy(raw)
        assert strategy.name is None
        assert strategy.version is None
        assert strategy.source_path is None

    def test_numeric_version_coerced_to_string_with_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """RAG_Ultimate 常把 version 寫成未加引號的數字（int/float）→ 寬鬆 coerce 成字串，
        不讓一份其實合法的策略檔因此靜默退回 baseline。"""
        raw = _valid_raw()
        raw["version"] = 2026  # yaml 未加引號的整數
        raw["name"] = 3.0      # 未加引號的浮點
        with caplog.at_level("WARNING"):
            strategy = parse_strategy(raw)
        assert strategy.version == "2026"
        assert strategy.name == "3.0"
        assert any("加引號" in rec.message for rec in caplog.records)

    def test_container_metadata_rejected(self) -> None:
        """name/version 給 list/dict 等容器型別仍視為錯誤（只對 scalar 寬鬆）。"""
        raw = _valid_raw()
        raw["version"] = ["1", "2"]
        with pytest.raises(StrategyError, match="策略檔.version 若提供則必須是字串或數字"):
            parse_strategy(raw)

    def test_rerank_false_allows_missing_rerank_model(self) -> None:
        raw = _valid_raw()
        raw["retrieval"] = {"algorithm": "vector", "top_k": 3, "rerank": False}
        strategy = parse_strategy(raw)
        assert strategy.retrieval.rerank is False
        assert strategy.retrieval.rerank_model is None

    def test_result_is_immutable(self) -> None:
        strategy = parse_strategy(_valid_raw())
        with pytest.raises((AttributeError, TypeError)):
            strategy.chunking.size = 999  # type: ignore[misc] — frozen dataclass 應拒絕


# ─────────────────────────────────────────────────────────────────────────
# parse_strategy — 結構 / 型別紅線
# ─────────────────────────────────────────────────────────────────────────


class TestParseStrategyStructure:
    def test_non_mapping_root_rejected(self) -> None:
        with pytest.raises(StrategyError, match="最外層"):
            parse_strategy(["not", "a", "mapping"])

    @pytest.mark.parametrize("missing", ["chunking", "embedding", "retrieval"])
    def test_missing_required_section_rejected(self, missing: str) -> None:
        raw = _valid_raw()
        del raw[missing]
        with pytest.raises(StrategyError, match=missing):
            parse_strategy(raw)

    def test_section_not_mapping_rejected(self) -> None:
        raw = _valid_raw()
        raw["chunking"] = "oops"
        with pytest.raises(StrategyError, match="chunking 必須是 mapping"):
            parse_strategy(raw)


class TestParseStrategyChunkingValidation:
    def test_missing_field_rejected(self) -> None:
        raw = _valid_raw()
        del raw["chunking"]["size"]  # type: ignore[union-attr]
        with pytest.raises(StrategyError, match="chunking 缺少必填欄位 'size'"):
            parse_strategy(raw)

    def test_size_must_be_int_not_bool(self) -> None:
        raw = _valid_raw()
        raw["chunking"]["size"] = True  # type: ignore[index] — bool 不可當整數
        with pytest.raises(StrategyError, match="chunking.size 必須是整數"):
            parse_strategy(raw)

    def test_size_must_be_positive(self) -> None:
        raw = _valid_raw()
        raw["chunking"]["size"] = 0  # type: ignore[index]
        with pytest.raises(StrategyError, match="chunking.size 必須 > 0"):
            parse_strategy(raw)

    def test_overlap_negative_rejected(self) -> None:
        raw = _valid_raw()
        raw["chunking"]["overlap"] = -1  # type: ignore[index]
        with pytest.raises(StrategyError, match="chunking.overlap 必須 >= 0"):
            parse_strategy(raw)

    def test_overlap_must_be_less_than_size(self) -> None:
        raw = _valid_raw()
        raw["chunking"]["size"] = 100  # type: ignore[index]
        raw["chunking"]["overlap"] = 100  # type: ignore[index]
        with pytest.raises(StrategyError, match="必須小於 size"):
            parse_strategy(raw)

    def test_method_must_be_non_empty_string(self) -> None:
        raw = _valid_raw()
        raw["chunking"]["method"] = "   "  # type: ignore[index]
        with pytest.raises(StrategyError, match="chunking.method 必須是非空字串"):
            parse_strategy(raw)


class TestParseStrategyEmbeddingValidation:
    def test_dimension_must_be_positive(self) -> None:
        raw = _valid_raw()
        raw["embedding"]["dimension"] = 0  # type: ignore[index]
        with pytest.raises(StrategyError, match="embedding.dimension 必須 > 0"):
            parse_strategy(raw)

    def test_model_required(self) -> None:
        raw = _valid_raw()
        del raw["embedding"]["model"]  # type: ignore[union-attr]
        with pytest.raises(StrategyError, match="embedding 缺少必填欄位 'model'"):
            parse_strategy(raw)


class TestParseStrategyRetrievalValidation:
    def test_top_k_must_be_positive(self) -> None:
        raw = _valid_raw()
        raw["retrieval"]["top_k"] = 0  # type: ignore[index]
        with pytest.raises(StrategyError, match="retrieval.top_k 必須 > 0"):
            parse_strategy(raw)

    def test_rerank_must_be_bool(self) -> None:
        raw = _valid_raw()
        raw["retrieval"]["rerank"] = "yes"  # type: ignore[index]
        with pytest.raises(StrategyError, match="retrieval.rerank 必須是布林值"):
            parse_strategy(raw)

    def test_rerank_true_without_model_rejected(self) -> None:
        raw = _valid_raw()
        raw["retrieval"] = {"algorithm": "vector", "top_k": 5, "rerank": True}
        with pytest.raises(StrategyError, match="rerank=true 時必須提供"):
            parse_strategy(raw)

    def test_rerank_model_empty_string_rejected(self) -> None:
        raw = _valid_raw()
        raw["retrieval"]["rerank_model"] = ""  # type: ignore[index]
        with pytest.raises(StrategyError, match="retrieval.rerank_model 若提供則必須是非空字串"):
            parse_strategy(raw)

    def test_rerank_false_with_rerank_model_drops_and_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """rerank=false 卻帶 rerank_model 是矛盾狀態 → 丟棄該欄位 + warning（下游 retrieve 不致混淆）。"""
        raw = _valid_raw()
        raw["retrieval"] = {
            "algorithm": "vector",
            "top_k": 5,
            "rerank": False,
            "rerank_model": "stale-model",
        }
        with caplog.at_level("WARNING"):
            strategy = parse_strategy(raw)
        assert strategy.retrieval.rerank is False
        assert strategy.retrieval.rerank_model is None
        assert any("rerank_model" in rec.message for rec in caplog.records)


# ─────────────────────────────────────────────────────────────────────────
# load_strategy — 檔案層
# ─────────────────────────────────────────────────────────────────────────


class TestLoadStrategyFromFile:
    def test_loads_repo_reference_sample(self) -> None:
        """repo 內 reference 樣本 yaml 必須永遠是合法策略（守護 schema drift）。"""
        strategy = load_strategy(_SAMPLE_STRATEGY)
        assert strategy.name == "z72_manual"
        assert strategy.embedding.dimension == 1024
        assert strategy.retrieval.rerank is True
        assert strategy.source_path == str(_SAMPLE_STRATEGY)

    def test_loads_written_yaml(self, tmp_path: Path) -> None:
        yaml_text = textwrap.dedent(
            """
            name: tmp
            chunking:
              method: semantic
              size: 256
              overlap: 20
            embedding:
              model: some-model
              dimension: 768
            retrieval:
              algorithm: vector
              top_k: 4
              rerank: false
            """
        )
        path = tmp_path / "s.yaml"
        path.write_text(yaml_text, encoding="utf-8")
        strategy = load_strategy(path)
        assert strategy.chunking.size == 256
        assert strategy.embedding.dimension == 768
        assert strategy.retrieval.rerank is False

    def test_missing_file_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(StrategyError, match="策略檔不存在"):
            load_strategy(tmp_path / "nope.yaml")

    def test_empty_file_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.yaml"
        path.write_text("", encoding="utf-8")
        with pytest.raises(StrategyError, match="策略檔為空"):
            load_strategy(path)

    def test_malformed_yaml_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("chunking: [unclosed\n", encoding="utf-8")
        with pytest.raises(StrategyError, match="不是合法 yaml"):
            load_strategy(path)

    def test_oversized_file_rejected(self, tmp_path: Path) -> None:
        """超過大小上限的策略檔直接拒絕（防誤指巨大檔案撐爆記憶體）。"""
        path = tmp_path / "huge.yaml"
        path.write_text("# pad\n" + "x" * 70_000, encoding="utf-8")
        with pytest.raises(StrategyError, match="策略檔過大"):
            load_strategy(path)

    def test_os_error_wrapped_in_strategy_error(self, tmp_path: Path) -> None:
        """讀檔 OS 層例外（如權限不足）統一轉成 StrategyError，兌現 Raises 契約。"""
        path = tmp_path / "s.yaml"
        path.write_text("ok\n", encoding="utf-8")
        with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
            with pytest.raises(StrategyError, match="策略檔讀取失敗"):
                load_strategy(path)

    def test_non_utf8_file_wrapped_in_strategy_error(self, tmp_path: Path) -> None:
        """非 UTF-8 編碼檔案（UnicodeDecodeError）也轉成 StrategyError。"""
        path = tmp_path / "latin.yaml"
        path.write_bytes("name: café\n".encode("latin-1"))  # 0xe9 非合法 UTF-8
        with pytest.raises(StrategyError, match="策略檔讀取失敗"):
            load_strategy(path)


# ─────────────────────────────────────────────────────────────────────────
# baseline_strategy / load_strategy_or_baseline
# ─────────────────────────────────────────────────────────────────────────


class TestBaselineStrategy:
    def test_baseline_is_valid_and_self_consistent(self) -> None:
        baseline = baseline_strategy()
        # baseline 必須能通過自身驗證規則（small / CPU 友善 / 無 rerank）
        assert baseline.name == "baseline-placeholder"
        assert baseline.source_path is None
        assert baseline.retrieval.rerank is False
        assert baseline.retrieval.rerank_model is None
        assert baseline.chunking.overlap < baseline.chunking.size
        assert baseline.embedding.dimension > 0
        assert baseline.retrieval.top_k > 0

    def test_baseline_round_trips_through_validation(self) -> None:
        """baseline 序列化回 dict 再 parse 應等價（防止 placeholder 自我矛盾）。"""
        b = baseline_strategy()
        raw: dict[str, object] = {
            "name": b.name,
            "version": b.version,
            "chunking": {
                "method": b.chunking.method,
                "size": b.chunking.size,
                "overlap": b.chunking.overlap,
            },
            "embedding": {
                "model": b.embedding.model,
                "dimension": b.embedding.dimension,
            },
            "retrieval": {
                "algorithm": b.retrieval.algorithm,
                "top_k": b.retrieval.top_k,
                "rerank": b.retrieval.rerank,
            },
        }
        reparsed = parse_strategy(raw)
        assert reparsed.chunking == b.chunking
        assert reparsed.embedding == b.embedding
        assert reparsed.retrieval == b.retrieval


class TestLoadStrategyOrBaseline:
    def test_returns_file_strategy_when_valid(self) -> None:
        strategy = load_strategy_or_baseline(_SAMPLE_STRATEGY)
        assert strategy.name == "z72_manual"
        assert strategy.source_path == str(_SAMPLE_STRATEGY)

    def test_falls_back_to_baseline_on_missing_file(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level("WARNING"):
            strategy = load_strategy_or_baseline(tmp_path / "nope.yaml")
        assert strategy.name == "baseline-placeholder"
        assert any("baseline" in rec.message for rec in caplog.records)

    def test_falls_back_to_baseline_on_invalid_content(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("chunking: {}\nembedding: {}\nretrieval: {}\n", encoding="utf-8")
        with caplog.at_level("WARNING"):
            strategy = load_strategy_or_baseline(path)
        assert strategy.name == "baseline-placeholder"
        assert any("baseline" in rec.message for rec in caplog.records)

    def test_falls_back_to_baseline_on_os_error(self, tmp_path: Path) -> None:
        """OS 例外經 load_strategy 包成 StrategyError 後，or_baseline 仍能退回 baseline。"""
        path = tmp_path / "s.yaml"
        path.write_text("ok\n", encoding="utf-8")
        with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
            strategy = load_strategy_or_baseline(path)
        assert strategy.name == "baseline-placeholder"
