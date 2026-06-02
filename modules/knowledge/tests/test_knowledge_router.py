"""FastAPI knowledge router tests（WMOM-20260602-01 / EPIC-M5 M5-6）。

驗證 ``POST /api/knowledge/alert`` 與 ``GET /api/knowledge/info``：
- 警報事件 → AlertRagResult（含 top-k chunks + 可解釋 match_reason）
- timestamp naive → 422（pydantic validator 在 request 階段擋下）
- DI：``set_handler`` 注入自訂語料 handler / ``None`` reset 回 baseline
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
from modules.knowledge.schemas import KnowledgeChunk, RagStrategy
from modules.knowledge.routers.knowledge_router import (
    router as knowledge_router,
    set_handler,
)


@pytest.fixture
def client():
    """每個 test 用乾淨 baseline handler，結束後 reset DI singleton。"""
    set_handler(None)  # 確保由 lazy baseline default 起步
    app = FastAPI(title="knowledge-test")
    app.include_router(knowledge_router)
    yield TestClient(app)
    set_handler(None)


# ─────────────────────────────────────────────────────────────────────────
# POST /api/knowledge/alert
# ─────────────────────────────────────────────────────────────────────────


def test_alert_returns_ranked_chunks(client):
    """變頻器告警碼 21 → top1 命中變頻器冷卻 SOP，含可解釋原因。"""
    resp = client.post(
        "/api/knowledge/alert",
        json={
            "alarm_code": 21,
            "turbine_id": "WT01",
            "description": "變頻器冷卻水溫過高",
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    assert body["retriever"] == "baseline_keyword"
    assert body["strategy_name"] == "z72_manual_baseline"
    assert body["is_baseline"] is True
    assert body["alert"]["alarm_code"] == 21
    assert body["query"]["alarm_codes"] == [21]

    chunks = body["chunks"]
    assert len(chunks) >= 1
    # 驗 router 行為：top1 是「對應告警碼 21」的 chunk，不綁特定語料 id
    # （具體 chunk id 的正確性由 test_retrieve.py 負責，避免語料異動誤爆 router test）
    assert 21 in chunks[0]["chunk"]["alarm_codes"]
    assert 0.0 < chunks[0]["score"] <= 1.0
    # 命中原因含告警碼（前端透明度）
    assert "21" in chunks[0]["match_reason"]
    # 依分數降冪
    scores = [c["score"] for c in chunks]
    assert scores == sorted(scores, reverse=True)


def test_alert_unknown_code_degrades_gracefully(client):
    """不存在的告警碼 → 200，不丟 500，且沒有任何 chunk 因該碼被命中。

    baseline retriever 仍可能因 query 文字（「Z72 告警 ...」）與語料有微弱
    Jaccard 重疊而回極低分 chunk —— 這是刻意的 graceful degrade，重點是
    「不 crash + 不會假裝命中不存在的告警碼」。
    """
    resp = client.post(
        "/api/knowledge/alert",
        json={"alarm_code": 99999, "turbine_id": "WT09"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_baseline"] is True
    for c in body["chunks"]:
        assert 99999 not in c["chunk"]["alarm_codes"]
        assert "命中告警碼 99999" not in c["match_reason"]


def test_alert_accepts_tz_aware_timestamp(client):
    """timezone-aware timestamp → 200。"""
    resp = client.post(
        "/api/knowledge/alert",
        json={
            "alarm_code": 21,
            "turbine_id": "WT01",
            "timestamp": datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc).isoformat(),
        },
    )
    assert resp.status_code == 200


def test_alert_rejects_naive_timestamp(client):
    """naive datetime（無時區）→ 422（SCADA 事件一律 UTC-aware）。"""
    resp = client.post(
        "/api/knowledge/alert",
        json={
            "alarm_code": 21,
            "turbine_id": "WT01",
            "timestamp": "2026-06-02T12:00:00",  # 無 tz
        },
    )
    assert resp.status_code == 422
    # 422 根因可見（前端 / debug 可辨識是 timestamp 驗證失敗，非泛用 422）
    assert "timestamp" in str(resp.json()).lower()


def test_alert_missing_required_field_returns_422(client):
    """缺必填 turbine_id → 422（pydantic 驗證）。"""
    resp = client.post("/api/knowledge/alert", json={"alarm_code": 21})
    assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────
# GET /api/knowledge/info
# ─────────────────────────────────────────────────────────────────────────


def test_info_reports_baseline_metadata(client):
    """/info 回 baseline retriever / 策略名 / is_baseline=True。"""
    resp = client.get("/api/knowledge/info")
    assert resp.status_code == 200
    body = resp.json()
    assert body["retriever"] == "baseline_keyword"
    assert body["strategy_name"] == "z72_manual_baseline"
    assert body["is_baseline"] is True


# ─────────────────────────────────────────────────────────────────────────
# DI：set_handler 注入 / reset
# ─────────────────────────────────────────────────────────────────────────


def test_set_handler_injects_custom_corpus(client):
    """注入自訂語料 handler → /alert 命中注入的 chunk。"""
    chunk = KnowledgeChunk(
        id="custom-sop-1",
        document_source="custom.pdf",
        chunk_text="自訂處置：請重啟控制器。",
        alarm_codes=[777],
        keywords=["控制器", "重啟"],
    )
    strategy = RagStrategy(name="custom_strategy")
    retriever = BaselineKeywordRetriever(
        corpus=KnowledgeCorpus(chunks=[chunk]), strategy=strategy
    )
    set_handler(AlertHandler(retriever=retriever, strategy=strategy))

    resp = client.post(
        "/api/knowledge/alert",
        json={"alarm_code": 777, "turbine_id": "WT02", "description": "控制器異常"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["strategy_name"] == "custom_strategy"
    assert body["chunks"][0]["chunk"]["id"] == "custom-sop-1"


def test_set_handler_none_resets_to_baseline(client):
    """set_handler(None) → 清掉非 baseline 的自訂 handler，下次請求 lazy 重建 baseline。"""

    # 先注入一個 retriever_name 明顯不同的「非 baseline」handler
    class _StubRetriever:
        name = "stub_vector"
        is_baseline = False

        def retrieve(self, query):  # noqa: ANN001, ANN201 — test stub
            return []

    strategy = RagStrategy(name="stub_strategy")
    set_handler(AlertHandler(retriever=_StubRetriever(), strategy=strategy))
    assert client.get("/api/knowledge/info").json()["retriever"] == "stub_vector"

    # reset → 下次請求應 lazy 重建 baseline default
    set_handler(None)
    resp = client.get("/api/knowledge/info")
    assert resp.status_code == 200
    body = resp.json()
    assert body["retriever"] == "baseline_keyword"
    assert body["is_baseline"] is True


def test_alert_empty_corpus_returns_200_empty_chunks(client):
    """注入空 corpus 的 handler → 200 + chunks 為空（M5-2/3 前語料未就緒的真實場景）。"""
    strategy = RagStrategy(name="empty_strategy")
    retriever = BaselineKeywordRetriever(
        corpus=KnowledgeCorpus(chunks=[]), strategy=strategy
    )
    set_handler(AlertHandler(retriever=retriever, strategy=strategy))

    resp = client.post(
        "/api/knowledge/alert",
        json={"alarm_code": 21, "turbine_id": "WT01", "description": "變頻器冷卻水溫過高"},
    )
    assert resp.status_code == 200
    assert resp.json()["chunks"] == []


def test_alert_returns_503_when_handler_init_fails(client):
    """handler lazy init 失敗（策略檔/語料異常）→ 503，且不洩漏內部 traceback。"""
    from unittest.mock import patch

    set_handler(None)  # 清 singleton，強迫走 lazy init
    with patch(
        "modules.knowledge.routers.knowledge_router.build_baseline_alert_handler",
        side_effect=RuntimeError("corpus 載入失敗：/secret/path/corpus.json"),
    ):
        resp = client.post(
            "/api/knowledge/alert",
            json={"alarm_code": 21, "turbine_id": "WT01"},
        )
    assert resp.status_code == 503
    # 不洩漏內部錯誤訊息 / 路徑到 client
    assert "/secret/path" not in resp.text
    assert "corpus 載入失敗" not in resp.text
