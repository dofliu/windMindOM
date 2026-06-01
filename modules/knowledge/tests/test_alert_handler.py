"""alert_handler 單元測試（WMOM-20260601-01）。

涵蓋：query 文字組裝、handle 端到端（警報 → 回應）、top_k 覆寫、注入時鐘
決定性、metadata（strategy_version / total_candidates）、以及對 baseline
語料的真實警報情境命中。
"""

from __future__ import annotations

from datetime import datetime, timezone

from modules.knowledge.alert_handler import AlertHandler, build_query_text
from modules.knowledge.ingest import build_retriever
from modules.knowledge.schemas.knowledge_schemas import AlertContext, KnowledgeQuery
from modules.knowledge.strategy_loader import BASELINE_STRATEGY_PATH, load_strategy

_BASELINE_DIR = BASELINE_STRATEGY_PATH.parent
_FIXED_TIME = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


def _handler(top_k: int = 3) -> AlertHandler:
    strategy = load_strategy(BASELINE_STRATEGY_PATH)
    strategy.retrieval.top_k = top_k
    retriever = build_retriever(strategy, _BASELINE_DIR)
    return AlertHandler(retriever, strategy, clock=lambda: _FIXED_TIME)


# ── query 文字組裝 ────────────────────────────────────────────────────


def test_build_query_text_joins_nonempty() -> None:
    alert = AlertContext(
        alert_code="A-262", message="主軸承溫度高", subsystem="generator"
    )
    text = build_query_text(alert)
    assert "主軸承溫度高" in text
    assert "generator" in text
    assert "A-262" in text


def test_build_query_text_skips_empty_fields() -> None:
    alert = AlertContext(alert_code="A-262")
    assert build_query_text(alert) == "A-262"


# ── handle 端到端 ─────────────────────────────────────────────────────


def test_handle_bearing_alert_hits_manual() -> None:
    """軸承高溫警報 → 命中 bearing_wear 手冊段落。"""
    handler = _handler()
    alert = AlertContext(
        alert_code="A-262",
        severity="alarm",
        message="主軸承1溫度高",
        turbine_id="WT003",
        subsystem="generator",
    )
    resp = handler.handle(alert)
    assert resp.chunks
    assert resp.chunks[0].chunk.chunk_id == "z72-bearing_wear-01"
    assert resp.query.startswith("主軸承1溫度高")
    assert resp.strategy_version == "baseline-0.1"
    assert resp.oem_model == "Z72"
    assert resp.retrieved_at == _FIXED_TIME


def test_handle_respects_strategy_top_k() -> None:
    """未覆寫時用策略預設 top_k。"""
    handler = _handler(top_k=2)
    alert = AlertContext(alert_code="A-262", message="軸承 偏航 變頻器 機艙 電網")
    resp = handler.handle(alert)
    assert len(resp.chunks) <= 2


def test_handle_top_k_override() -> None:
    """top_k 參數覆寫策略預設。"""
    handler = _handler(top_k=3)
    alert = AlertContext(alert_code="A-262", message="軸承 偏航 變頻器 機艙 電網")
    resp = handler.handle(alert, top_k=1)
    assert len(resp.chunks) == 1


def test_handle_total_candidates_reflects_corpus() -> None:
    """total_candidates 反映機型語料總數（過濾前）。"""
    handler = _handler()
    resp = handler.handle(AlertContext(alert_code="A-262", message="軸承"))
    assert resp.total_candidates >= 10


def test_query_passthrough() -> None:
    """直接以 KnowledgeQuery 查詢亦可，metadata 一致。"""
    handler = _handler()
    resp = handler.query(KnowledgeQuery(text="偏航煞車液壓壓力低", fault_code="A-260"))
    assert resp.chunks[0].chunk.chunk_id == "z72-hydraulic_leak-01"
    assert resp.retrieved_at == _FIXED_TIME


def test_handle_unknown_code_still_lexical_match() -> None:
    """未知警報碼但訊息有語意時，仍能靠 lexical 命中（不致全空）。"""
    handler = _handler()
    resp = handler.handle(
        AlertContext(alert_code="X-999", message="變頻器冷卻水溫度上升")
    )
    assert resp.chunks
    assert resp.chunks[0].chunk.chunk_id == "z72-converter_cooling-01"
