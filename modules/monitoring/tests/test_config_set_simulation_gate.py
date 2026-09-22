"""`POST /api/config/simulation` 在非即時模擬來源時應拒絕，而非靜默切換來源
（WMOM-20260720-04 (3)，#146 review 殘留的 definitive fix）。

背景：前端 SettingsPage 的來源 gate（#146）只能 best-effort——設定頁 ≤5s 輪詢窗蓋不到
「編輯到一半來源被切走」的空隙。active source 非即時模擬（view/live/scenario）時，
若本端點照舊往下跑，「turbine count 改變」分支會呼叫 ``switch_mode(SIMULATION)``，悄悄
把 live 斷線，或打斷情境調閱／產生情境的凍結資料集語意。definitive fix 落在後端：
source_kind 非 None/simulation 時直接 409，不讓它有機會走到 switch_mode。
"""

from __future__ import annotations

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
from server.routers import config as config_module  # noqa: E402
from server.routers.config import router as config_router  # noqa: E402


@pytest.fixture
def broker(tmp_path):
    return DataBroker(farm_registry=FarmRegistry(data_dir=tmp_path))


@pytest.fixture
def client(broker, monkeypatch):
    monkeypatch.setattr(config_module, "get_broker", lambda: broker)
    app = FastAPI()
    app.include_router(config_router)
    return TestClient(app)


@pytest.mark.parametrize("source_kind", ["view", "live", "scenario"])
def test_set_simulation_rejects_when_source_not_running_sim(client, broker, source_kind):
    """view/live/scenario 時直接 409，不落到 switch_mode(SIMULATION)。"""
    broker._source_active = True
    broker._source_kind = source_kind

    r = client.post("/api/config/simulation", json={"turbineCount": 20})

    assert r.status_code == 409
    assert broker.source_kind == source_kind, "被拒絕時來源種類不該被動到"
    assert broker.simulator is None, "不該悄悄建 simulator / switch_mode"


def test_set_simulation_allows_when_source_is_simulation(client, broker, monkeypatch):
    """對照組：來源本來就是 simulation（即時模擬）時，正常放行——不該被新檢查誤擋。"""
    broker._source_active = True
    broker._source_kind = "simulation"
    called = {"v": False}
    monkeypatch.setattr(broker, "switch_mode", lambda *a, **k: called.__setitem__("v", True))

    r = client.post("/api/config/simulation", json={"turbineCount": 20})

    assert r.status_code == 200
    assert called["v"] is True


def test_set_simulation_allows_when_no_source_selected_yet(client, broker, monkeypatch):
    """未選來源（source_kind=None，開機 idle）：維持既有行為，不被新檢查誤擋。
    真的 switch_mode 會起背景 thread，這裡 mock 掉只驗證有沒有放行到那一步。
    """
    assert broker.source_kind is None
    called = {"v": False}
    monkeypatch.setattr(broker, "switch_mode", lambda *a, **k: called.__setitem__("v", True))

    r = client.post("/api/config/simulation", json={"turbineCount": 3})

    assert r.status_code == 200
    assert called["v"] is True
