"""CORS preflight 回歸測試（WMOM-20260718-07）。

背景：情境模擬「生成情境」（JSON POST /api/config/simulation/generate-bulk）在某些環境
被瀏覽器 CORS 擋下（`No Access-Control-Allow-Origin`），後端 log 顯示 `OPTIONS ... 400`。
根因：舊版 Starlette（< 0.19）不會把 `allow_methods=["*"]` 展開成實際 methods，POST 的
preflight 在 method 檢查落空 → 400（GET 不觸發 preflight 故正常）。修法：CORS methods/headers
改**明列**（見 `server.app.CORS_ALLOW_METHODS/HEADERS`），跨 Starlette 版本穩定。

本檔以最小 app + 明列常數重現 preflight，守住「JSON POST 的 preflight 必須放行」。
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "modules" / "monitoring"))

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from server.app import CORS_ALLOW_METHODS, CORS_ALLOW_HEADERS  # noqa: E402

_ORIGIN = "http://localhost:3100"


def _preflight_app() -> FastAPI:
    """最小 app，套用與正式 app 相同的 CORS methods/headers 常數 + 一個 JSON POST 路由。"""
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[_ORIGIN],
        allow_credentials=True,
        allow_methods=CORS_ALLOW_METHODS,
        allow_headers=CORS_ALLOW_HEADERS,
    )

    @app.post("/api/config/simulation/generate-bulk")
    async def _gen(body: dict):  # pragma: no cover - 只為讓路由存在
        return {"ok": True}

    return app


def test_json_post_preflight_is_allowed():
    """核心：JSON POST 的 preflight（OPTIONS + Access-Control-Request-Method: POST）→ 200 + ACAO。

    這正是「生成情境」失敗的那一步；preflight 被擋（400 / 無 ACAO）→ 瀏覽器擋下整個 POST。
    """
    client = TestClient(_preflight_app())
    resp = client.options(
        "/api/config/simulation/generate-bulk",
        headers={
            "Origin": _ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,authorization",
        },
    )
    assert resp.status_code == 200, f"preflight 應放行，實得 {resp.status_code}"
    assert resp.headers.get("access-control-allow-origin") == _ORIGIN
    assert "POST" in resp.headers.get("access-control-allow-methods", "")


def test_cors_methods_include_post_and_options_not_wildcard():
    """回歸：methods 必含 POST/OPTIONS 且不可退回 ['*']（舊 Starlette 會令 preflight 落空）。"""
    assert "POST" in CORS_ALLOW_METHODS
    assert "OPTIONS" in CORS_ALLOW_METHODS
    assert "*" not in CORS_ALLOW_METHODS


def test_cors_headers_cover_content_type_and_authorization():
    """前端 JSON POST 帶 Content-Type；登入後 authFetch 帶 Authorization——兩者都要在允許清單。"""
    lowered = {h.lower() for h in CORS_ALLOW_HEADERS}
    assert "content-type" in lowered
    assert "authorization" in lowered
