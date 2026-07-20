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
    # FarmRegistry 隔離到 tmp（比照 test_farm_registry_is_offshore 慣例，不碰共用 data/farms.db）。
    # 不手動覆蓋 .storage——否則會遮蔽 select_view_only 的 storage re-point（Must-fix регресія）。
    return DataBroker(farm_registry=FarmRegistry(data_dir=tmp_path))


def test_view_only_reads_active_farm_scenarios(tmp_path):
    """Must-fix：開機後第一個動作就是「調閱過去情境」時，storage 必須指向 active farm 的 DB
    （而非 __init__ 預設的 legacy 路徑），否則已存在的情境 list 不出來——即 #4「情境調不回來」
    以新根因重現。"""
    reg = FarmRegistry(data_dir=tmp_path)
    farm_id = reg.ensure_default_farm()
    farm_db = str(reg.get_farm_db_path(farm_id))

    # 直接在 active farm 的 DB 塞一個情境
    farm_storage = Storage(db_path=farm_db)
    sid = farm_storage.create_session(
        data_source="simulation", turbine_count=3,
        config={"kind": Storage.SCENARIO_KIND, "name": "颱風接近測試"},
    )

    # 全新 broker，第一動作即調閱過去情境
    b = DataBroker(farm_registry=reg)
    b.select_view_only()

    assert b.storage._db_path == farm_db, "view 後 storage 必須指向 active farm DB（非 legacy 預設）"
    assert any(s["id"] == sid for s in b.storage.list_scenarios()), "已存在的情境必須調得回來"


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


def test_select_live_requires_supervisor(client, monkeypatch):
    """實際對接（live）比照 farm-activate 需 SUPERVISOR 以上——employee 被擋（在啟動前就 403）。"""
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    from modules.auth.tokens import create_access_token

    tok = create_access_token(subject="u1", role="employee", name="E")
    r = client.post(
        "/api/source/select",
        json={"mode": "live"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 403


def test_select_live_allows_supervisor(client, monkeypatch):
    """positive path：SUPERVISOR 通過角色閘門（activate_live 以 no-op mock，避免真 OPC 連線）。

    守住「角色判斷若被寫壞成連 SUPERVISOR 都擋，測試會抓到」——與 negative test 成對。
    """
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    monkeypatch.setattr("server.app.activate_live", lambda: None)
    from modules.auth.tokens import create_access_token

    tok = create_access_token(subject="u2", role="supervisor", name="S")
    r = client.post(
        "/api/source/select",
        json={"mode": "live"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
