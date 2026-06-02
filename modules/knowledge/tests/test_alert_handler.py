"""alert_handler 測試 — 警報→query→檢索 端到端（M5-1）。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.knowledge import build_baseline_alert_handler  # noqa: E402
from modules.knowledge.alert_handler import AlertHandler  # noqa: E402
from modules.knowledge.corpus import KnowledgeCorpus  # noqa: E402
from modules.knowledge.retrieve import BaselineKeywordRetriever  # noqa: E402
from modules.knowledge.schemas import (  # noqa: E402
    AlertEvent,
    RagStrategy,
    RetrievalQuery,
    RetrievedChunk,
)
from modules.knowledge.strategy_loader import load_strategy  # noqa: E402


class _StubRetriever:
    """測 handler 不依賴特定實作：記錄收到的 query。"""

    name = "stub"
    # 完整實作 Retriever Protocol 契約屬性（name + is_baseline）；
    # stub 非真向量，故 is_baseline=False。
    is_baseline = False

    def __init__(self) -> None:
        self.last_query: RetrievalQuery | None = None

    def retrieve(self, query: RetrievalQuery) -> list[RetrievedChunk]:
        self.last_query = query
        return []


def _strategy(top_k: int = 3) -> RagStrategy:
    return RagStrategy.model_validate({"name": "s", "retrieval": {"top_k": top_k}})


class TestBuildQuery:
    def test_query_carries_code_model_oem(self) -> None:
        """build_query 把告警碼帶進 alarm_codes、機型 / oem 帶進過濾欄位。"""
        handler = AlertHandler(retriever=_StubRetriever(), strategy=_strategy(3))
        event = AlertEvent(
            alarm_code=21,
            turbine_id="WTG01",
            description="變頻器跳機",
            abnormal_tags=["WCNV_IGCTWtrTmp"],
        )
        q = handler.build_query(event)
        assert q.alarm_codes == [21]
        assert q.model == "Z72"
        assert q.oem == "Bachmann"
        assert q.top_k == 3
        assert "21" in q.text
        assert "變頻器跳機" in q.text
        assert "WCNV_IGCTWtrTmp" in q.text

    def test_query_without_optional_fields(self) -> None:
        """無 description / abnormal_tags 仍能組出 query。"""
        handler = AlertHandler(retriever=_StubRetriever(), strategy=_strategy())
        q = handler.build_query(AlertEvent(alarm_code=42, turbine_id="WTG02"))
        assert q.alarm_codes == [42]
        assert "42" in q.text


class TestOnAlert:
    def test_passes_built_query_to_retriever(self) -> None:
        """on_alert 真的把 build_query 的結果送進 retriever。"""
        stub = _StubRetriever()
        handler = AlertHandler(retriever=stub, strategy=_strategy())
        handler.on_alert(AlertEvent(alarm_code=21, turbine_id="WTG01"))
        assert stub.last_query is not None
        assert stub.last_query.alarm_codes == [21]

    def test_result_metadata(self) -> None:
        """結果帶策略名 + retriever 名；stub 非 baseline → is_baseline False。"""
        handler = AlertHandler(retriever=_StubRetriever(), strategy=_strategy())
        result = handler.on_alert(AlertEvent(alarm_code=21, turbine_id="WTG01"))
        assert result.strategy_name == "s"
        assert result.retriever == "stub"
        assert result.is_baseline is False

    def test_baseline_retriever_sets_is_baseline_true(self) -> None:
        """用 BaselineKeywordRetriever 時 is_baseline 為 True。"""
        strategy = _strategy()
        retriever = BaselineKeywordRetriever(
            corpus=KnowledgeCorpus([]), strategy=strategy
        )
        handler = AlertHandler(retriever=retriever, strategy=strategy)
        result = handler.on_alert(AlertEvent(alarm_code=21, turbine_id="WTG01"))
        assert result.is_baseline is True
        assert result.retriever == "baseline_keyword"


class TestFactoryEndToEnd:
    def test_build_baseline_alert_handler_retrieves_converter_sop(self) -> None:
        """便捷工廠 + 變頻器冷卻警報 → 端到端命中變頻器冷卻 SOP。"""
        handler = build_baseline_alert_handler()
        event = AlertEvent(
            alarm_code=21,
            alarm_level="T1",
            turbine_id="WTG07",
            scenario_id="converter_cooling_fault",
            abnormal_tags=["WCNV_IGCTWtrTmp", "WCNV_IGCTWtrPres1"],
            description="變頻器要求跳機，水溫持續上升",
        )
        result = handler.on_alert(event)
        assert result.is_baseline is True
        assert result.chunks
        top = result.chunks[0]
        assert top.chunk.id == "z72-sop-converter-cooling"
        assert "命中告警碼 21" in top.match_reason
        # 回傳筆數受策略 top_k=3 限制。
        assert len(result.chunks) <= 3

    def test_factory_handler_handles_unknown_code(self) -> None:
        """未知告警碼（無對應 SOP）→ 端到端不丟例外、無強命中。

        baseline keyword 檢索是模糊比對：query 文字含「告警」等通用詞時，
        可能對每塊 SOP 產生極弱的文字重疊命中。重點是「不該出現
        code/keyword 等級的強命中」（分數遠低於關鍵字權重、無告警碼命中
        原因），避免對未知碼給出假性自信的處置建議。
        """
        from modules.knowledge.retrieve import _KEYWORD_WEIGHT

        handler = build_baseline_alert_handler()
        result = handler.on_alert(
            AlertEvent(alarm_code=88888, turbine_id="WTG01", description="zzz")
        )
        assert result.is_baseline is True
        # 無任何 chunk 達到關鍵字 / 告警碼等級的強命中。
        assert all(rc.score < _KEYWORD_WEIGHT for rc in result.chunks)
        assert all("命中告警碼" not in rc.match_reason for rc in result.chunks)

    def test_strategy_name_propagates(self) -> None:
        """工廠用內建策略，結果 strategy_name 應為 z72_manual_baseline。"""
        handler = build_baseline_alert_handler()
        result = handler.on_alert(AlertEvent(alarm_code=21, turbine_id="WTG01"))
        assert result.strategy_name == load_strategy().name == "z72_manual_baseline"
