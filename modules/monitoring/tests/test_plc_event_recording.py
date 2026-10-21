"""broker 記錄 PLC 事件（WMOM-20261021-03-b）。

即時路徑每步 ``drain_events()``，把 PLC 事件寫成 ``event_type="fault"``、``source="plc"`` 的歷史事件：

1. payload 帶事件碼 / 等級 / PLC tag / 觸發值與設定值
2. 時間戳依 reading 的模擬時間回推（加速模式一個 tick 跑多步，不能用牆鐘）
3. PLC 判定的停機（``shutdown_cause="plc:<碼>"``）分類為故障停機
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import pytest

from server.data_broker import DataBroker
from server.farm_registry import FarmRegistry
from server.storage import Storage
from simulator.engine import WindFarmSimulator

T0 = datetime(2026, 1, 1, 0, 0, 0)
DT = 5.0


@pytest.fixture
def broker(tmp_path) -> DataBroker:
    b = DataBroker(farm_registry=FarmRegistry(data_dir=tmp_path))
    b.storage = Storage(db_path=str(tmp_path / "plc.db"))
    b.simulator = WindFarmSimulator(turbine_count=1)
    return b


def _plc_events(broker: DataBroker) -> list:
    return [e for e in broker.storage.query_events("WT001", limit=500) if e.get("source") == "plc"]


def test_plc_event_is_recorded_with_code_and_simulation_timestamp(broker: DataBroker) -> None:
    sim = broker.simulator
    model = sim.turbines["WT001"]
    readings = []
    for i in range(1, 4):
        readings = sim._run_one_step(T0 + timedelta(seconds=i * DT), DT)
    model.plc.drain_events()
    # 物理層超速停機發生在最後一個 reading 之前 10 s（同一 tick 的較早子步）
    model.plc.note_protection_stop("overspeed_software", model._sim_time - 10.0)

    broker._detect_sim_events(readings)

    (event,) = _plc_events(broker)
    assert event["event_type"] == "fault"
    assert event["timestamp"] == (T0 + timedelta(seconds=3 * DT - 10.0)).isoformat()
    payload = event["payload"]
    assert (payload["kind"], payload["code"], payload["level"], payload["origin"]) == (
        "trip", 351, "T1", "protection")
    assert payload["eventId"] and payload["plcTag"]
    assert model.plc.drain_events() == [], "broker 應已取走事件"


def test_plc_stop_is_classified_as_fault_stop(broker: DataBroker) -> None:
    broker._record_state_transition_event("WT001", 6, 9, "plc:240")
    (event,) = [e for e in broker.storage.query_events("WT001", limit=50) if e.get("source") == "simulator"]
    assert event["event_type"] == "fault"
    assert event["title"] == "Automatic fault stop: PLC event 240"
