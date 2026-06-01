"""strategy_loader 測試 — 真檔載入 + baseline fallback 契約（M5-1）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.knowledge.strategy_loader import (  # noqa: E402
    DEFAULT_STRATEGY_PATH,
    default_strategy,
    load_strategy,
)


def test_default_strategy_is_baseline() -> None:
    """default_strategy 不讀檔，回 baseline。"""
    s = default_strategy()
    assert s.name == "baseline"
    assert s.retrieval.top_k == 5


def test_load_builtin_z72_strategy() -> None:
    """載入內建 Z72 baseline 策略檔，數值對齊 yaml。"""
    s = load_strategy()  # None → DEFAULT_STRATEGY_PATH
    assert DEFAULT_STRATEGY_PATH.is_file()
    assert s.name == "z72_manual_baseline"
    assert s.oem == "Bachmann"
    assert s.model == "Z72"
    assert s.retrieval.top_k == 3
    assert s.retrieval.rerank is True
    assert s.embedding.model == "BAAI/bge-large-zh-v1.5"


def test_missing_file_falls_back_to_baseline(tmp_path: Path) -> None:
    """檔案不存在 → 不丟例外，回 baseline default（placeholder 契約）。"""
    s = load_strategy(tmp_path / "does_not_exist.yaml")
    assert s.name == "baseline"
    assert s.retrieval.top_k == 5


def test_non_mapping_yaml_falls_back(tmp_path: Path) -> None:
    """yaml 內容非 mapping（如 list）→ 回 baseline default。"""
    bad = tmp_path / "bad.yaml"
    bad.write_text("- a\n- b\n", encoding="utf-8")
    s = load_strategy(bad)
    assert s.name == "baseline"


def test_empty_yaml_falls_back(tmp_path: Path) -> None:
    """空檔（yaml → None）→ 回 baseline default。"""
    empty = tmp_path / "empty.yaml"
    empty.write_text("", encoding="utf-8")
    s = load_strategy(empty)
    assert s.name == "baseline"


def test_custom_yaml_parsed(tmp_path: Path) -> None:
    """自訂策略檔正確解析。"""
    custom = tmp_path / "custom.yaml"
    custom.write_text(
        "name: custom\nmodel: V236\nretrieval:\n  top_k: 7\n", encoding="utf-8"
    )
    s = load_strategy(custom)
    assert s.name == "custom"
    assert s.model == "V236"
    assert s.retrieval.top_k == 7


def test_malformed_yaml_raises(tmp_path: Path) -> None:
    """語法錯誤的 yaml 不該被靜默吞掉 —— 原樣拋出。"""
    broken = tmp_path / "broken.yaml"
    broken.write_text("name: [unclosed\n", encoding="utf-8")
    with pytest.raises(Exception):
        load_strategy(broken)
