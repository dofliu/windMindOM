"""FastAPI knowledge router tests（WMOM-20260602-01）— Alert → RAG（M5-6）。

涵蓋：
- POST /api/knowledge/alert：告警碼命中 SOP、is_baseline 標記、naive timestamp 422、
  無命中仍 200、top_k 不超過策略值。
- GET /api/knowledge/status：baseline retriever / is_baseline / 策略名。
- DI：``set_alert_handler`` 注入自訂 handler、``None`` 還原 lazy baseline。
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.knowledge import build_baseline_alert_handler
from modules.knowledge.alert_handler import AlertHandler
from modules.knowledge.corpus import KnowledgeCorpus
from modules.knowledge.retrieve import BaselineKeywordRetriever
from modules.knowledge.routers.knowledge_router import (
    router as knowledge_router,
    set_alert_handler,
)
from modules.knowledge.schemas import KnowledgeChunk, RagStrategy


@pytest.fixture
def client():
    """乾淨的 TestClient；每次測試前後還原 handler singleton（None → lazy baseline）。"""
    set_alert_handler(None)
    app = FastAPI(title="knowledge-test")
    app.include_router(knowledge_router)
    yield TestClient(app)
    set_alert_handler(None)


# ─────────────────────────────────────────────────────────────────────────
# POST /api/knowledge/alert
# ─────────────────────────────────────────────────────────────────────────


def test_alert_matches_converter_cooling_sop(client):
    """告警碼 21（變頻器）→ top1 命中變頻器冷卻 SOP，且標記 baseline。"""
    resp = client.post(
        "/api/knowledge/alert",
        json={
            "alarm_code": 21,
            "alarm_level": "T1",
            "turbine_id": "WTG-07",
            "description": "變頻器跳機",
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["is_baseline"] is True
    assert body["retriever"] == "baseline_keyword"
    assert body["alert"]["alarm_code"] == 21
    assert len(body["chunks"]) >= 1

    top = body["chunks"][0]
    # top1 應對應變頻器冷卻 SOP；告警碼命中要寫進可解釋 match_reason。
    assert top["chunk"]["id"] == "z72-sop-converter-cooling"
    assert 21 in top["chunk"]["alarm_codes"]
    assert "命中告警碼 21" in top["match_reason"]
    assert 0.0 < top["score"] <= 1.0


def test_alert_naive_timestamp_rejected_422(client):
    """naive datetime timestamp 違反 UTC-aware 約束 → 422（pydantic 驗證）。"""
    resp = client.post(
        "/api/knowledge/alert",
        json={
            "alarm_code": 21,
            "turbine_id": "WTG-07",
            "timestamp": "2026-06-02T12:00:00",  # 無時區 → naive
        },
    )
    assert resp.status_code == 422


def test_alert_aware_timestamp_accepted(client):
    """timezone-aware timestamp → 200。"""
    ts = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc).isoformat()
    resp = client.post(
        "/api/knowledge/alert",
        json={"alarm_code": 21, "turbine_id": "WTG-07", "timestamp": ts},
    )
    assert resp.status_code == 200


def test_alert_unknown_code_has_no_code_hit(client):
    """未知告警碼（無對應 SOP）→ 仍 200，不報錯；沒有任何 chunk 因告警碼命中。

    baseline 仍可能因 query 文字（如「告警」）有微弱 Jaccard overlap 而回低分
    chunk，這是預期行為；關鍵不變量是「未知碼不會誤觸發告警碼命中」。
    """
    resp = client.post(
        "/api/knowledge/alert",
        json={"alarm_code": 99999, "turbine_id": "WTG-07"},
    )
    assert resp.status_code == 200
    chunks = resp.json()["chunks"]
    # 沒有任一 chunk 的 alarm_codes 命中 99999，也不該出現「命中告警碼」原因。
    for rc in chunks:
        assert 99999 not in rc["chunk"]["alarm_codes"]
        assert "命中告警碼" not in rc["match_reason"]


def test_alert_respects_strategy_top_k(client):
    """回傳 chunk 數不超過策略 top_k（從策略物件動態取值，不硬編碼）。"""
    strategy = build_baseline_alert_handler().strategy
    resp = client.post(
        "/api/knowledge/alert",
        json={"alarm_code": 21, "turbine_id": "WTG-07", "description": "變頻器 冷卻 溫度"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["chunks"]) <= strategy.retrieval.top_k


def test_alert_missing_required_field_422(client):
    """缺必填 turbine_id → 422。"""
    resp = client.post("/api/knowledge/alert", json={"alarm_code": 21})
    assert resp.status_code == 422


def test_alert_retriever_exception_returns_500(client):
    """retriever 拋例外（如 ChromaDB 連線失敗）→ 500 + 可讀錯誤訊息（非裸 500）。"""

    class _BrokenRetriever:
        name = "broken"
        is_baseline = False

        def retrieve(self, query):  # noqa: ANN001, ANN201 — 測試 stub
            raise RuntimeError("模擬 ChromaDB 連線失敗")

    strategy = RagStrategy(name="broken_strategy")
    set_alert_handler(AlertHandler(retriever=_BrokenRetriever(), strategy=strategy))

    resp = client.post(
        "/api/knowledge/alert",
        json={"alarm_code": 21, "turbine_id": "WTG-07"},
    )
    assert resp.status_code == 500
    assert "RAG 檢索失敗" in resp.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────
# GET /api/knowledge/status
# ─────────────────────────────────────────────────────────────────────────


def test_status_reports_baseline(client):
    """預設 lazy baseline handler → status 標 baseline_keyword + is_baseline True。"""
    resp = client.get("/api/knowledge/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["retriever"] == "baseline_keyword"
    assert body["is_baseline"] is True
    assert isinstance(body["strategy_name"], str) and body["strategy_name"]


# ─────────────────────────────────────────────────────────────────────────
# DI：set_alert_handler 注入 / 還原
# ─────────────────────────────────────────────────────────────────────────


def test_injected_handler_is_used(client):
    """注入自訂 handler（自訂 corpus + 策略名）→ 端點走注入的 handler。"""
    chunk = KnowledgeChunk(
        id="custom-chunk",
        document_source="custom.pdf",
        chunk_text="自訂處置段落：測試齒輪箱潤滑。",
        alarm_codes=[777],
        keywords=["齒輪箱"],
    )
    strategy = RagStrategy(name="custom_strategy")
    retriever = BaselineKeywordRetriever(
        corpus=KnowledgeCorpus([chunk]), strategy=strategy
    )
    set_alert_handler(AlertHandler(retriever=retriever, strategy=strategy))

    status = client.get("/api/knowledge/status").json()
    assert status["strategy_name"] == "custom_strategy"

    alert = client.post(
        "/api/knowledge/alert",
        json={"alarm_code": 777, "turbine_id": "WTG-01"},
    ).json()
    assert alert["strategy_name"] == "custom_strategy"
    assert len(alert["chunks"]) == 1
    assert alert["chunks"][0]["chunk"]["id"] == "custom-chunk"


def test_set_handler_none_restores_lazy_baseline(client):
    """注入後設回 None → 下次請求重新 lazy build baseline handler。"""
    strategy = RagStrategy(name="custom_strategy")
    retriever = BaselineKeywordRetriever(
        corpus=KnowledgeCorpus([]), strategy=strategy
    )
    set_alert_handler(AlertHandler(retriever=retriever, strategy=strategy))
    assert client.get("/api/knowledge/status").json()["strategy_name"] == "custom_strategy"

    set_alert_handler(None)
    body = client.get("/api/knowledge/status").json()
    assert body["retriever"] == "baseline_keyword"
    assert body["is_baseline"] is True
