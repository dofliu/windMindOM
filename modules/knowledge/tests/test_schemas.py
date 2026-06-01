"""schemas 測試 — 預設值、欄位約束、round-trip（M5-1）。"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.knowledge.schemas import (  # noqa: E402
    AlertEvent,
    AlertRagResult,
    KnowledgeChunk,
    RagStrategy,
    RetrievalQuery,
    RetrievedChunk,
)


class TestRagStrategy:
    """RagStrategy 預設與巢狀結構。"""

    def test_defaults_match_mvp_spec(self) -> None:
        """不給任何參數時，sub-model 預設對齊 MVP_ARCHITECTURE §3.5 範例。"""
        s = RagStrategy()
        assert s.name == "baseline"
        assert s.oem == "Bachmann"
        assert s.model == "Z72"
        assert s.chunking.size == 512
        assert s.chunking.overlap == 50
        assert s.embedding.dimension == 1024
        assert s.retrieval.top_k == 5
        assert s.retrieval.rerank is True

    def test_parse_full_strategy(self) -> None:
        """從 dict 解析完整策略檔。"""
        s = RagStrategy.model_validate(
            {
                "name": "z72_v3",
                "retrieval": {"top_k": 3, "rerank": False},
            }
        )
        assert s.name == "z72_v3"
        assert s.retrieval.top_k == 3
        assert s.retrieval.rerank is False
        # 未指定的 sub-field 仍走 default。
        assert s.chunking.size == 512

    def test_top_k_must_be_positive(self) -> None:
        """top_k 必須 > 0。"""
        with pytest.raises(ValidationError):
            RagStrategy.model_validate({"retrieval": {"top_k": 0}})


class TestKnowledgeChunk:
    """KnowledgeChunk 欄位。"""

    def test_minimal_chunk(self) -> None:
        """只給必填欄位，其餘走預設（baseline 無向量）。"""
        c = KnowledgeChunk(id="c1", document_source="m.pdf", chunk_text="x")
        assert c.embedding_vector_id is None
        assert c.alarm_codes == []
        assert c.keywords == []
        assert c.oem == "Bachmann"
        assert c.model == "Z72"

    def test_full_chunk_round_trip(self) -> None:
        """完整 chunk 可序列化再還原。"""
        c = KnowledgeChunk(
            id="c1",
            document_source="m.pdf",
            section="§4.3",
            page=53,
            chunk_text="變頻器冷卻",
            alarm_codes=[21, 32],
            keywords=["變頻器", "冷卻"],
        )
        restored = KnowledgeChunk.model_validate(c.model_dump())
        assert restored == c


class TestRetrievalQuery:
    """RetrievalQuery 欄位與約束。"""

    def test_defaults(self) -> None:
        """oem / model / top_k 預設 None，alarm_codes 預設空。"""
        q = RetrievalQuery(text="hello")
        assert q.oem is None
        assert q.model is None
        assert q.top_k is None
        assert q.alarm_codes == []

    def test_top_k_override_must_be_positive(self) -> None:
        """覆寫 top_k 時仍須 > 0。"""
        with pytest.raises(ValidationError):
            RetrievalQuery(text="x", top_k=0)


class TestRetrievedChunk:
    """RetrievedChunk score 約束。"""

    def _chunk(self) -> KnowledgeChunk:
        return KnowledgeChunk(id="c1", document_source="m.pdf", chunk_text="x")

    @pytest.mark.parametrize("bad_score", [-0.1, 1.1])
    def test_score_bounds(self, bad_score: float) -> None:
        """score 必須落在 0..1。"""
        with pytest.raises(ValidationError):
            RetrievedChunk(chunk=self._chunk(), score=bad_score, match_reason="r")


class TestAlertEvent:
    """AlertEvent 預設與約束。"""

    def test_defaults(self) -> None:
        """oem / model 預設 Bachmann / Z72，level 預設 A。"""
        e = AlertEvent(alarm_code=21, turbine_id="WTG01")
        assert e.oem == "Bachmann"
        assert e.model == "Z72"
        assert e.alarm_level == "A"
        assert e.abnormal_tags == []

    def test_invalid_level_rejected(self) -> None:
        """alarm_level 僅允許 A / T1 / T2。"""
        with pytest.raises(ValidationError):
            AlertEvent(alarm_code=21, turbine_id="WTG01", alarm_level="T9")

    def test_severity_bounds(self) -> None:
        """severity 若給定須落在 0..1。"""
        with pytest.raises(ValidationError):
            AlertEvent(alarm_code=21, turbine_id="WTG01", severity=1.5)

    def test_timestamp_naive_rejected(self) -> None:
        """naive datetime 被拒（CLAUDE.md §B：SCADA 事件一律 UTC aware）。"""
        with pytest.raises(ValidationError):
            AlertEvent(
                alarm_code=21,
                turbine_id="WTG01",
                timestamp=datetime(2026, 6, 1, 12, 0, 0),  # naive
            )

    def test_timestamp_aware_accepted(self) -> None:
        """timezone-aware datetime 正常接受。"""
        ts = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        e = AlertEvent(alarm_code=21, turbine_id="WTG01", timestamp=ts)
        assert e.timestamp == ts

    def test_timestamp_none_ok(self) -> None:
        """timestamp 可省略（None）。"""
        e = AlertEvent(alarm_code=21, turbine_id="WTG01")
        assert e.timestamp is None


class TestAlertRagResult:
    """AlertRagResult 組合。"""

    def test_is_baseline_default_true(self) -> None:
        """is_baseline 預設 True（placeholder 階段）。"""
        r = AlertRagResult(
            alert=AlertEvent(alarm_code=21, turbine_id="WTG01"),
            query=RetrievalQuery(text="x"),
            strategy_name="baseline",
            retriever="baseline_keyword",
        )
        assert r.is_baseline is True
        assert r.chunks == []
