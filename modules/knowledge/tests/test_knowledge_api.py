"""FastAPI knowledge router tests（WMOM-20260603-01，M5-6）— 3 endpoints。

涵蓋：
- ``POST /api/knowledge/alert`` — 警報 → RAG（命中 / 未知碼 / naive timestamp 422）
- ``POST /api/knowledge/query`` — 手動檢索
- ``GET  /api/knowledge/info``  — RAG 來源 / baseline 標示
- DI：``set_handler_factory`` 注入自訂 handler + None 清快取
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.knowledge import build_baseline_alert_handler  # noqa: E402
from modules.knowledge.routers.knowledge_router import (  # noqa: E402
    router as knowledge_router,
    set_handler_factory,
)


@pytest.fixture(autouse=True)
def _reset_handler_singleton():
    """每個 test 前後重置 module-level singleton handler / factory。

    must-fix #3：以 autouse fixture 明確保證 test 隔離，不依賴 ``client``
    fixture 的 setup/teardown 時序，也不受 test class / 執行順序影響。
    """
    set_handler_factory(None)
    yield
    set_handler_factory(None)


@pytest.fixture
def client():
    """以預設 baseline handler 掛載 router 的 TestClient。

    singleton reset 由 ``_reset_handler_singleton`` autouse fixture 負責，
    本 fixture 只管掛 router + 提供 TestClient（職責分離）。
    """
    app = FastAPI()
    app.include_router(knowledge_router)
    with TestClient(app) as c:
        yield c


# ─────────────────────────────────────────────────────────────────────────
# POST /api/knowledge/alert
# ─────────────────────────────────────────────────────────────────────────


class TestAlertEndpoint:
    def test_converter_cooling_alert_hits_sop(self, client):
        """變頻器冷卻警報（碼 21）→ top1 命中變頻器冷卻 SOP。"""
        resp = client.post(
            "/api/knowledge/alert",
            json={
                "alarm_code": 21,
                "alarm_level": "T1",
                "turbine_id": "WTG07",
                "scenario_id": "converter_cooling_fault",
                "abnormal_tags": ["WCNV_IGCTWtrTmp", "WCNV_IGCTWtrPres1"],
                "description": "變頻器要求跳機，水溫持續上升",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_baseline"] is True
        assert body["retriever"] == "baseline_keyword"
        assert body["strategy_name"] == "z72_manual_baseline"
        assert body["chunks"], "應至少命中一筆 SOP"
        top = body["chunks"][0]
        assert top["chunk"]["id"] == "z72-sop-converter-cooling"
        assert "命中告警碼 21" in top["match_reason"]
        # 受策略 top_k=3 限制
        assert len(body["chunks"]) <= 3

    def test_unknown_alarm_code_no_strong_hit(self, client):
        """未知告警碼 → 200、不丟例外、無告警碼等級強命中。"""
        resp = client.post(
            "/api/knowledge/alert",
            json={"alarm_code": 88888, "turbine_id": "WTG01", "description": "zzz"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_baseline"] is True
        assert all("命中告警碼" not in c["match_reason"] for c in body["chunks"])

    def test_naive_timestamp_rejected_422(self, client):
        """naive datetime timestamp → 422（schema validator 拒絕，CLAUDE.md §B）。"""
        resp = client.post(
            "/api/knowledge/alert",
            json={
                "alarm_code": 21,
                "turbine_id": "WTG01",
                "timestamp": "2026-06-03T12:00:00",  # 無時區
            },
        )
        assert resp.status_code == 422

    def test_aware_timestamp_accepted(self, client):
        """timezone-aware timestamp → 200。"""
        resp = client.post(
            "/api/knowledge/alert",
            json={
                "alarm_code": 21,
                "turbine_id": "WTG01",
                "timestamp": "2026-06-03T12:00:00+00:00",
            },
        )
        assert resp.status_code == 200

    def test_missing_required_field_422(self, client):
        """缺 turbine_id（必填）→ 422。"""
        resp = client.post("/api/knowledge/alert", json={"alarm_code": 21})
        assert resp.status_code == 422

    def test_invalid_alarm_code_422(self, client):
        """非正整數告警碼（ge=1）→ 422（nice-to-have #11）。"""
        resp = client.post(
            "/api/knowledge/alert", json={"alarm_code": 0, "turbine_id": "WTG01"}
        )
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────
# POST /api/knowledge/query
# ─────────────────────────────────────────────────────────────────────────


class TestQueryEndpoint:
    def test_manual_query_by_code_and_text(self, client):
        """手動檢索（告警碼 + 文字）→ 命中對應 SOP，回傳含 total / retriever。"""
        resp = client.post(
            "/api/knowledge/query",
            json={"text": "變頻器 冷卻 水溫", "alarm_codes": [21], "model": "Z72"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["retriever"] == "baseline_keyword"
        assert body["is_baseline"] is True
        assert body["total"] == len(body["items"])
        assert body["items"], "應至少命中一筆"
        # score 由高到低排序
        scores = [it["score"] for it in body["items"]]
        assert scores == sorted(scores, reverse=True)

    def test_query_respects_top_k_override(self, client):
        """query 帶 top_k=1 → 至多回 1 筆。"""
        resp = client.post(
            "/api/knowledge/query",
            json={"text": "變頻器", "alarm_codes": [21], "top_k": 1},
        )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) <= 1

    def test_query_missing_text_422(self, client):
        """缺必填 text → 422。"""
        resp = client.post("/api/knowledge/query", json={"alarm_codes": [21]})
        assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────
# GET /api/knowledge/info
# ─────────────────────────────────────────────────────────────────────────


class TestInfoEndpoint:
    def test_info_reports_baseline_source(self, client):
        """info → baseline 策略 / retriever / top_k。"""
        resp = client.get("/api/knowledge/info")
        assert resp.status_code == 200
        body = resp.json()
        assert body["strategy_name"] == "z72_manual_baseline"
        assert body["retriever"] == "baseline_keyword"
        assert body["is_baseline"] is True
        assert body["oem"] == "Bachmann"
        assert body["model"] == "Z72"
        assert body["top_k"] >= 1


# ─────────────────────────────────────────────────────────────────────────
# DI / 快取
# ─────────────────────────────────────────────────────────────────────────


class TestHandlerFactoryDI:
    def test_injected_factory_is_used(self, client):
        """注入自訂 factory → endpoint 改用注入的 handler。"""
        calls = {"n": 0}

        def factory():
            calls["n"] += 1
            return build_baseline_alert_handler()

        set_handler_factory(factory)  # 注入 + 清快取，確保下一個請求觸發 factory
        # 兩次請求只應建立一次 handler（singleton 快取）
        client.get("/api/knowledge/info")
        client.get("/api/knowledge/info")
        assert calls["n"] == 1

    def test_set_factory_none_resets_cache(self, client):
        """set_handler_factory(None) → 清快取，後續請求重建（不殘留）。"""
        sentinel = {"built": 0}

        def factory():
            sentinel["built"] += 1
            return build_baseline_alert_handler()

        set_handler_factory(factory)
        client.get("/api/knowledge/info")
        assert sentinel["built"] == 1

        set_handler_factory(None)
        # 回到 default 工廠，不再呼叫被清掉的 factory
        resp = client.get("/api/knowledge/info")
        assert resp.status_code == 200
        assert sentinel["built"] == 1

    def test_broken_factory_returns_503(self, client):
        """handler 初始化失敗（factory 拋例外）→ 503，而非洩漏 traceback 的 500。

        must-fix #4：覆蓋 error path（策略 yaml 損毀 / 知識庫 JSON 損毀的代理）。
        """

        def bad_factory():
            raise RuntimeError("corpus 損毀")

        set_handler_factory(bad_factory)
        resp = client.get("/api/knowledge/info")
        assert resp.status_code == 503

    def test_broken_factory_not_cached_retries(self, client):
        """失敗的 handler 不快取 → 修好 factory 後下次請求即恢復（不需重啟）。"""
        attempts = {"n": 0}

        def flaky_factory():
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("第一次故意失敗")
            return build_baseline_alert_handler()

        set_handler_factory(flaky_factory)
        first = client.get("/api/knowledge/info")
        assert first.status_code == 503
        # 失敗未快取，第二次重試成功
        second = client.get("/api/knowledge/info")
        assert second.status_code == 200
        assert attempts["n"] == 2
