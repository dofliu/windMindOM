"""strategy_loader 測試 — RAG 策略檔載入契約（M5-1）。

測試重點：
1. example 策略檔（隨 repo 交付）載得進來且欄位正確 → 契約檔不會悄悄壞掉
2. from_yaml_str / from_dict 的 happy path 與預設值
3. 嚴格 schema：未知 key 被擋（extra=forbid）
4. 約束驗證：overlap < size、top_k >= 1、dimension > 0、rerank 需 rerank_model
5. 例外階層：檔案不存在 / YAML 壞掉 / 頂層非 mapping / schema 不合 各自獨立
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pydantic
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.knowledge.strategy_loader import (  # noqa: E402
    ChunkingStrategy,
    RagStrategy,
    RetrievalStrategy,
    StrategyFileNotFoundError,
    StrategyLoadError,
    StrategyParseError,
    StrategyReadError,
    StrategyValidationError,
    load_strategy,
)

MODULE_DIR = Path(__file__).resolve().parents[1]
EXAMPLE_STRATEGY = MODULE_DIR / "strategies" / "rag_strategy_z72_manual.example.yaml"


# ─────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────


def _minimal_dict() -> dict:
    """符合 schema 的最小策略 dict（無 meta、用 rerank 預設）。"""
    return {
        "chunking": {"method": "fixed", "size": 256},
        "embedding": {"model": "test-embed", "dimension": 768},
        "retrieval": {"algorithm": "vector", "top_k": 3},
    }


# ─────────────────────────────────────────────────────────────────────────
# 1. example 契約檔
# ─────────────────────────────────────────────────────────────────────────


def test_example_strategy_file_exists() -> None:
    """隨 repo 交付的 example 策略檔必須存在（demo + 測試前提）。"""
    assert EXAMPLE_STRATEGY.is_file()


def test_load_example_strategy_fields() -> None:
    """載入 example 檔並逐欄位驗證 —— 鎖住 Z72 策略契約不被誤改。"""
    strategy = load_strategy(EXAMPLE_STRATEGY)

    assert strategy.chunking.method == "semantic"
    assert strategy.chunking.size == 512
    assert strategy.chunking.overlap == 50

    assert strategy.embedding.model == "BAAI/bge-large-zh-v1.5"
    assert strategy.embedding.dimension == 1024

    assert strategy.retrieval.algorithm == "hybrid_bm25_vector"
    assert strategy.retrieval.top_k == 5
    assert strategy.retrieval.rerank is True
    assert strategy.retrieval.rerank_model == "bge-reranker-v2-m3"

    assert strategy.meta is not None
    assert strategy.meta.oem_model == "Z72"
    assert strategy.meta.vector_store_file == "z72_manual_v2026-05.parquet"


def test_load_strategy_accepts_str_path() -> None:
    """load_strategy 接受 str 路徑（非只 Path），方便從 settings 字串傳入。"""
    strategy = load_strategy(str(EXAMPLE_STRATEGY))
    assert isinstance(strategy, RagStrategy)


# ─────────────────────────────────────────────────────────────────────────
# 2. happy path + 預設值
# ─────────────────────────────────────────────────────────────────────────


def test_from_dict_minimal_defaults() -> None:
    """最小 dict：overlap 預設 0、rerank 預設 False、rerank_model 預設 None、meta 預設 None。"""
    strategy = RagStrategy.from_dict(_minimal_dict())
    assert strategy.chunking.overlap == 0
    assert strategy.retrieval.rerank is False
    assert strategy.retrieval.rerank_model is None
    assert strategy.meta is None


def test_from_yaml_str_round_trip() -> None:
    """from_yaml_str 與 from_dict 等價（同一份內容）。"""
    text = (
        "chunking:\n"
        "  method: recursive\n"
        "  size: 400\n"
        "  overlap: 40\n"
        "embedding:\n"
        "  model: m\n"
        "  dimension: 512\n"
        "retrieval:\n"
        "  algorithm: bm25\n"
        "  top_k: 8\n"
    )
    strategy = RagStrategy.from_yaml_str(text)
    assert strategy.chunking.method == "recursive"
    assert strategy.chunking.overlap == 40
    assert strategy.retrieval.top_k == 8


# ─────────────────────────────────────────────────────────────────────────
# 3. 嚴格 schema：未知 key
# ─────────────────────────────────────────────────────────────────────────


def test_unknown_top_level_key_rejected() -> None:
    """頂層未知 key（典型 typo）→ StrategyValidationError。"""
    data = _minimal_dict()
    data["chunkign"] = {}  # typo of "chunking"
    with pytest.raises(StrategyValidationError):
        RagStrategy.from_dict(data)


def test_unknown_nested_key_rejected() -> None:
    """子區塊未知 key 也要擋（extra=forbid 套用到所有子 model）。"""
    data = _minimal_dict()
    data["chunking"]["windows_size"] = 9  # typo / 不存在的欄位
    with pytest.raises(StrategyValidationError):
        RagStrategy.from_dict(data)


# ─────────────────────────────────────────────────────────────────────────
# 4. 約束驗證
# ─────────────────────────────────────────────────────────────────────────


def test_overlap_must_be_less_than_size() -> None:
    """overlap >= size → 驗證失敗（model_validator）。"""
    with pytest.raises(StrategyValidationError):
        RagStrategy.from_dict(
            {
                "chunking": {"method": "fixed", "size": 100, "overlap": 100},
                "embedding": {"model": "m", "dimension": 8},
                "retrieval": {"algorithm": "vector", "top_k": 1},
            }
        )


def test_chunking_overlap_validator_direct() -> None:
    """直接建構子 model 也擋 overlap >= size（不只透過頂層）。

    注意：直接走建構子（繞過 from_dict 包裝層）拋的是 pydantic.ValidationError，
    而非應用層的 StrategyValidationError —— 此測試鎖的是「最底層 validator 確實有效」。
    """
    with pytest.raises(pydantic.ValidationError):
        ChunkingStrategy(method="fixed", size=50, overlap=60)


@pytest.mark.parametrize("bad_top_k", [0, -1])
def test_top_k_must_be_positive(bad_top_k: int) -> None:
    """top_k <= 0 → 驗證失敗。"""
    data = _minimal_dict()
    data["retrieval"]["top_k"] = bad_top_k
    with pytest.raises(StrategyValidationError):
        RagStrategy.from_dict(data)


def test_dimension_must_be_positive() -> None:
    """embedding.dimension <= 0 → 驗證失敗。"""
    data = _minimal_dict()
    data["embedding"]["dimension"] = 0
    with pytest.raises(StrategyValidationError):
        RagStrategy.from_dict(data)


def test_invalid_chunking_method_rejected() -> None:
    """method 不在 Literal 範圍 → 驗證失敗。"""
    data = _minimal_dict()
    data["chunking"]["method"] = "magic"
    with pytest.raises(StrategyValidationError):
        RagStrategy.from_dict(data)


def test_rerank_true_requires_rerank_model() -> None:
    """rerank=True 但沒給 rerank_model → 驗證失敗（直接建構子拋 pydantic.ValidationError）。"""
    with pytest.raises(pydantic.ValidationError):
        RetrievalStrategy(algorithm="vector", top_k=5, rerank=True)


def test_rerank_true_with_model_ok() -> None:
    """rerank=True 且有 rerank_model → 通過。"""
    r = RetrievalStrategy(algorithm="vector", top_k=5, rerank=True, rerank_model="rr")
    assert r.rerank_model == "rr"


@pytest.mark.parametrize("bad_model", ["", "   "])
def test_rerank_true_with_blank_model_rejected(bad_model: str) -> None:
    """rerank=True 但 rerank_model 是空字串 / 純空白（去空白後為空）→ 驗證失敗。

    純空白靠 str_strip_whitespace 先去成空字串，再被 _rerank_needs_model 擋下，
    避免「看似有值」的無效設定延遲到 retrieve 才爆。
    """
    data = _minimal_dict()
    data["retrieval"]["rerank"] = True
    data["retrieval"]["rerank_model"] = bad_model
    with pytest.raises(StrategyValidationError):
        RagStrategy.from_dict(data)


@pytest.mark.parametrize("bad_model", ["", "   "])
def test_embedding_model_blank_rejected(bad_model: str) -> None:
    """embedding.model 空字串 / 純空白 → 驗證失敗（min_length + str_strip_whitespace）。"""
    data = _minimal_dict()
    data["embedding"]["model"] = bad_model
    with pytest.raises(StrategyValidationError):
        RagStrategy.from_dict(data)


def test_meta_ignores_unknown_keys() -> None:
    """meta 是 extra=ignore（與核心三段不同）：RAG_Ultimate 未來加新 meta 欄位不應觸發部署失敗。"""
    data = _minimal_dict()
    data["meta"] = {"name": "x", "created_at": "2026-05-29", "checksum": "abc"}
    strategy = RagStrategy.from_dict(data)
    assert strategy.meta is not None
    assert strategy.meta.name == "x"


def test_meta_vector_store_file_must_be_parquet_filename() -> None:
    """vector_store_file 限純檔名 .parquet，路徑穿越字串被擋（預防 ingest 端 Path 誤用）。"""
    data = _minimal_dict()
    data["meta"] = {"vector_store_file": "../../etc/passwd"}
    with pytest.raises(StrategyValidationError):
        RagStrategy.from_dict(data)


def test_missing_required_section_rejected() -> None:
    """缺必填區塊（如 embedding）→ 驗證失敗。"""
    data = _minimal_dict()
    del data["embedding"]
    with pytest.raises(StrategyValidationError):
        RagStrategy.from_dict(data)


# ─────────────────────────────────────────────────────────────────────────
# 5. 例外階層
# ─────────────────────────────────────────────────────────────────────────


def test_file_not_found_raises() -> None:
    """不存在的路徑 → StrategyFileNotFoundError（且為 StrategyLoadError 子類）。"""
    with pytest.raises(StrategyFileNotFoundError):
        load_strategy(MODULE_DIR / "strategies" / "does_not_exist.yaml")


def test_file_not_found_is_load_error() -> None:
    """上層只 catch 基底 StrategyLoadError 也接得到。"""
    with pytest.raises(StrategyLoadError):
        load_strategy("/nonexistent/path/strategy.yaml")


def test_directory_path_raises_not_found() -> None:
    """傳資料夾路徑（非檔案）→ StrategyFileNotFoundError。"""
    with pytest.raises(StrategyFileNotFoundError):
        load_strategy(MODULE_DIR / "strategies")


def test_permission_denied_raises_read_error(tmp_path: Path) -> None:
    """檔案存在但讀不到（權限）→ StrategyReadError（且為 StrategyLoadError 子類）。

    部署環境（docker volume / NFS mount）權限問題是真實錯誤；root 跑測試可能繞過 chmod，
    遇到時 skip 而非誤判。
    """
    f = tmp_path / "no_read.yaml"
    f.write_text("chunking: {}\n", encoding="utf-8")
    f.chmod(0o000)
    try:
        if os.access(f, os.R_OK):  # 例如 root 無視權限 → 此測試在該環境無意義
            pytest.skip("目前使用者可繞過檔案權限（如 root），略過權限測試")
        with pytest.raises(StrategyReadError):
            load_strategy(f)
    finally:
        f.chmod(0o644)  # 還原以利 tmp_path 清理


def test_utf8_bom_strategy_loads(tmp_path: Path) -> None:
    """帶 UTF-8 BOM 的策略檔（Windows 端常見）能正常載入，BOM 不污染頂層 key。"""
    f = tmp_path / "bom.yaml"
    f.write_bytes(
        b"\xef\xbb\xbf"
        + (
            "chunking:\n  method: fixed\n  size: 256\n"
            "embedding:\n  model: m\n  dimension: 8\n"
            "retrieval:\n  algorithm: vector\n  top_k: 1\n"
        ).encode("utf-8")
    )
    strategy = load_strategy(f)
    assert strategy.chunking.size == 256


def test_invalid_yaml_raises_parse_error(tmp_path: Path) -> None:
    """YAML 語法錯誤 → StrategyParseError。"""
    bad = tmp_path / "bad.yaml"
    bad.write_text("chunking: [unclosed\n", encoding="utf-8")
    with pytest.raises(StrategyParseError):
        load_strategy(bad)


def test_empty_yaml_raises_parse_error(tmp_path: Path) -> None:
    """空檔（YAML 解析為 None）→ StrategyParseError。"""
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(StrategyParseError):
        load_strategy(empty)


def test_non_mapping_top_level_raises_parse_error() -> None:
    """頂層是 list 而非 mapping → StrategyParseError。"""
    with pytest.raises(StrategyParseError):
        RagStrategy.from_yaml_str("- a\n- b\n")


def test_from_dict_non_dict_raises_parse_error() -> None:
    """from_dict 收到非 dict → StrategyParseError。"""
    with pytest.raises(StrategyParseError):
        RagStrategy.from_dict(["not", "a", "dict"])


def test_schema_violation_raises_validation_error() -> None:
    """語法對但 schema 不合 → StrategyValidationError（非 ParseError）。"""
    with pytest.raises(StrategyValidationError):
        RagStrategy.from_yaml_str("chunking: {}\nembedding: {}\nretrieval: {}\n")
