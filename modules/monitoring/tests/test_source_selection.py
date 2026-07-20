"""資料來源選擇（WMOM-20260719-04, DEC-20260719-01 #3）。

開機不再自動啟動來源；使用者登入後選定才啟動。本檔驗證：
1. broker 狀態機：fresh=未選、select_view_only=已選但不起來源、stop=清空。
2. /api/source 端點：status 反映狀態、select view/未知 mode、enforce 下需登入。

不觸發真 simulation/live 啟動（會起背景執行緒 + Modbus port）——那兩條只驗 broker 狀態轉移
與端點路由，實際 activate_* 於 app 整合層運行。
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

from server.data_broker import DataBroker  # noqa: E402
from server.farm_registry import FarmRegistry  # noqa: E402
from server.storage import Storage  # noqa: E402
from server.routers import source as source_module  # noqa: E402
from server.routers.source import router as source_router  # noqa: E402


@pytest.fixture
def broker(tmp_path):
    b = DataBroker(farm_registry=FarmRegistry())
    b.storage = Storage(db_path=str(tmp_path / "src.db"))
    return b


# ─── broker 狀態機 ─────────────────────────────────────────────────────────

def test_fresh_broker_has_no_active_source(broker):
    """開機（未選）：source_active False、kind None → 前端會顯示選擇頁。"""
    assert broker.source_active is False
    assert broker.source_kind is None


def test_select_view_only_marks_active_without_starting_a_source(broker):
    """調閱過去情境：標記已選、但**不**起任何來源（simulator 保持 None、不產資料）。"""
    broker.select_view_only()
    assert broker.source_active is True
    assert broker.source_kind == "view"
    assert broker.simulator is None


def test_stop_clears_source_flags(broker):
    broker.select_view_only()
    broker.stop()
    assert broker.source_active is False
    assert broker.source_kind is None


# ─── 端點 ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client(broker, monkeypatch):
    monkeypatch.setattr(source_module, "get_broker", lambda: broker)
    app = FastAPI()
    app.include_router(source_router)
    return TestClient(app)


def test_status_reports_idle_before_selection(client):
    r = client.get("/api/source/status")
    assert r.status_code == 200
    assert r.json()["active"] is False


def test_select_view_activates_view_only(client, broker):
    r = client.post("/api/source/select", json={"mode": "view"})
    assert r.status_code == 200
    body = r.json()
    assert body["active"] is True and body["kind"] == "view"
    assert broker.simulator is None
    assert client.get("/api/source/status").json() == {"active": True, "kind": "view", "mode": None}


def test_select_unknown_mode_returns_400(client):
    assert client.post("/api/source/select", json={"mode": "banana"}).status_code == 400


def test_status_enforced_requires_auth(client, monkeypatch):
    """enforce 開 + 無 token → 401（來源選擇端點確實掛了 require_authenticated）。"""
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    assert client.get("/api/source/status").status_code == 401
