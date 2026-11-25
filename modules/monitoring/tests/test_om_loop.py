"""運維閉環（WMOM-20261125-04）：即時模擬的風場和工單接起來。

1. 跳機自動開故障維修工單（帶警報碼）；同機組同碼不重複開；工單只寫看得到的東西。
2. 工單開工：機組進維修模式；定檢算計畫停機、故障維修算非計畫停機。
3. 工單完工才修好：清故障、復位、重新發電。操作員復位不等於修好的規則不變。
4. 運轉狀態紀錄：可用率、停機時數、停機少發的電。
5. 閉環沒開、別座風場的工單、重跑段：不做事。
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterator, List
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import pytest

from modules.workflow import hooks
from modules.workflow.domain import FollowupKind, Priority, WorkOrderStatus, WorkOrderType
from modules.workflow.domain.work_order import WorkOrder
from modules.workflow.repository import work_order_repository as wo_repo
from server.data_broker import DataBroker
from server.farm_registry import FarmRegistry
from server.om_loop import OmLoop, sim_turbine_id
from server.storage import Storage, is_observable_event
from simulator.engine import WindFarmSimulator

T0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
FARM = "farm-a"
WIRE_BREAK = "main_bearing_temp_sensor_wire_break"   # 量測回路斷線：幾秒內鎖存跳機 242
TECH, BOSS = uuid4(), uuid4()


class Farm:
    """測試用的風場：broker＋手動推進的即時模擬＋工單 repository。"""

    def __init__(self, tmp_path: Path, enabled: bool = True, turbines: int = 3) -> None:
        self.broker = DataBroker(farm_registry=FarmRegistry(data_dir=tmp_path))
        self.broker.storage = Storage(db_path=str(tmp_path / "farm.db"))
        self.broker.simulator = WindFarmSimulator(turbine_count=turbines)
        self.broker._session_id = self.broker.storage.create_session(data_source="simulation", turbine_count=turbines)
        self.broker._source_active, self.broker._source_kind = True, "simulation"
        self.broker._active_farm_id = FARM
        self.broker.simulator._running = True   # 視同即時模擬在跑（測試自己一步一步推）
        if enabled:
            self.broker.om_loop.enabled = True
            hooks.add_work_order_listener(self.broker.om_loop.on_work_order)
        self.repo = wo_repo.get_repository(str(self.broker.storage.db_path))
        self._step = 0

    @property
    def loop(self) -> OmLoop:
        return self.broker.om_loop

    def drive(self, seconds: int) -> None:
        sim = self.broker.simulator
        assert sim is not None
        for _ in range(seconds):
            self._step += 1
            sim._sim_clock = T0 + timedelta(seconds=self._step)
            self.broker._on_sim_data(sim._run_one_step(sim._sim_clock, 1.0))

    def drive_slow(self, steps: int) -> None:
        """每步 10 秒（快速累積歷史用；每一步都會寫進歷史）。"""
        sim = self.broker.simulator
        assert sim is not None
        for _ in range(steps):
            self._step += 10
            sim._sim_clock = T0 + timedelta(seconds=self._step)
            self.broker._on_sim_data(sim._run_one_step(sim._sim_clock, 10.0))

    def model(self, turbine_id: str = "WT001"):
        sim = self.broker.simulator
        assert sim is not None
        return sim.turbines[turbine_id]

    def faults(self, turbine_id: str = "WT001") -> List[str]:
        sim = self.broker.simulator
        assert sim is not None
        return [f.scenario_id for f in sim.fault_engine.active_faults if f.turbine_id == turbine_id]

    def inject(self, scenario_id: str, turbine_id: str = "WT001", severity: float = 1.0) -> None:
        sim = self.broker.simulator
        assert sim is not None
        assert sim.fault_engine.inject(scenario_id, turbine_id, severity_rate=0.05, initial_severity=severity)

    def orders(self) -> List[WorkOrder]:
        return sorted(self.repo.list(farm_id=FARM)[0], key=lambda o: o.business_key)

    def start(self, order: WorkOrder) -> WorkOrder:
        self.repo.transition(order.id, "dispatch", actor_id=BOSS, assignee_id=TECH)
        return self.repo.transition(order.id, "start_work", actor_id=TECH)

    def finish(self, order: WorkOrder) -> WorkOrder:
        return self.repo.transition(order.id, "finish", actor_id=TECH, actual_hours=2.0,
                                    followup_kind=FollowupKind.NONE)

    def until_producing(self, turbine_id: str = "WT001", limit: int = 900) -> int:
        for waited in range(0, limit, 10):
            if self.model(turbine_id).tur_state == 6:
                return waited
            self.drive(10)
        raise AssertionError(f"{turbine_id} 在 {limit} 秒內沒有回到發電")

    def workflow_events(self) -> List[str]:
        return [e["title"] for e in reversed(self.broker.storage.query_events(limit=200)) if e["source"] == "workflow"]


@pytest.fixture
def farm(tmp_path) -> Iterator[Farm]:
    f = Farm(tmp_path)
    try:
        yield f
    finally:
        hooks.clear_work_order_listeners()
        wo_repo.clear_engine_cache_for_test()


@pytest.fixture
def tripped(farm: Farm) -> Farm:
    """WT001 已經因為量測回路斷線跳機 242、開了工單。"""
    farm.drive(300)
    assert farm.model().tur_state == 6, "測試前提：健康時在發電"
    farm.inject(WIRE_BREAK)
    farm.drive(60)
    assert farm.model().plc.active_lists.snapshot()["T1"] == [242] and farm.model().maintenance_lock
    return farm


# ── 1. 跳機開單 ────────────────────────────────────────────────────────────


def test_a_trip_opens_one_corrective_work_order(tripped: Farm) -> None:
    orders = tripped.orders()
    assert len(orders) == 1
    order = orders[0]
    assert (order.farm_id, order.turbine_id, order.type, order.status) == (
        FARM, "WT001", WorkOrderType.CORRECTIVE, WorkOrderStatus.DRAFT)
    assert order.source_alarm_code == "242" and order.priority is Priority.NORMAL and order.created_by is None
    assert "T_242" in order.title and "242" in order.description
    tripped.drive(120)   # 跳機還鎖著、工單還沒結案：不重複開
    assert len(tripped.orders()) == 1
    assert tripped.workflow_events() == [f"Work order opened: {order.business_key}"]


def test_auto_work_orders_carry_no_answer(tripped: Farm) -> None:
    """自動開的工單之後會給外部（對外 API、準備卡）：只能寫看得到的東西，不能有故障情境。"""
    order = tripped.orders()[0]
    text = (order.title + order.description).lower()
    for leak in (WIRE_BREAK, "wire_break", "sensor", "scenario", "inject", "斷線", "注入", "情境"):
        assert leak not in text, leak
    stored = tripped.broker.storage.query_events(limit=200)
    workflow = [e for e in stored if e["source"] == "workflow"]
    assert workflow and not any(is_observable_event(e) for e in workflow), "閉環自己的事件不是可觀測事件"


def test_emergency_trips_and_blocked_restarts_get_high_priority(farm: Farm) -> None:
    from simulator.physics.plc_protection import PlcEvent

    def event(kind: str, code: int, level: str) -> PlcEvent:
        return PlcEvent(sim_time=1.0, kind=kind, code=code, level=level, text="text", plc_tag=None,
                        event_id=f"{level[0]}_{code:03d}", value=None, setpoint=None, source="signal")

    farm.drive(1)
    assert farm.loop.on_plc_event("WT002", event("alarm_raised", 262, "A")) is None, "一般警報不開單"
    assert farm.loop.on_plc_event("WT002", event("trip_cleared", 242, "T1")) is None
    emergency = farm.loop.on_plc_event("WT002", event("trip", 336, "T2"))
    blocked = farm.loop.on_plc_event("WT002", event("alarm_raised", 39, "A"))
    normal = farm.loop.on_plc_event("WT002", event("trip", 242, "T1"))
    assert emergency is not None and blocked is not None and normal is not None
    assert (emergency.priority, blocked.priority, normal.priority) == (Priority.HIGH, Priority.HIGH, Priority.NORMAL)
    assert farm.loop.on_plc_event("WT002", event("trip", 240, "T1")) is None, "一台機組最多三張未結案工單"
    assert farm.loop.on_plc_event("WT002", event("trip", 336, "T2")) is None, "同碼不重複開"


# ── 2、3. 開工進維修模式、完工修復 ─────────────────────────────────────────


def test_reset_does_not_repair_but_finishing_the_work_order_does(tripped: Farm) -> None:
    order = tripped.orders()[0]
    tripped.model().cmd_reset()   # 操作員復位：故障還在，馬上再跳
    tripped.drive(60)
    assert tripped.faults() == [WIRE_BREAK] and tripped.model().tur_state != 6, "復位不等於修好"

    tripped.start(order)
    tripped.drive(5)
    assert tripped.model().service_mode is True and tripped.loop.classify("WT001", 9) == "unplanned"
    finished = tripped.finish(order)
    assert finished.status is WorkOrderStatus.AWAITING_SIGNOFF, "修復發生在現場完工，不等簽核"
    assert tripped.faults() == [] and tripped.model().service_mode is False
    waited = tripped.until_producing()
    assert waited <= 300, f"修好後 {waited} 秒才回到發電"
    assert tripped.model().maintenance_lock is False and tripped.model().plc.active_lists.snapshot()["T1"] == []
    assert tripped.workflow_events() == [
        f"Work order opened: {order.business_key}", f"Work started: {order.business_key}",
        f"Work finished: {order.business_key}"]
    done = tripped.broker.storage.query_events(limit=50)
    payload = next(e["payload"] for e in done if e["title"].startswith("Work finished"))
    assert payload["repaired"] == [WIRE_BREAK] and payload["alarmCode"] == "242"

    tripped.drive(120)
    assert len(tripped.orders()) == 1, "修好之後不再跳機、不再開單"


def test_a_work_order_for_another_code_does_not_repair_the_fault(tripped: Farm) -> None:
    """帶警報碼的故障維修工單只修預期會送出那個碼的故障：碼對不上（誤報、外部原因）就只復位。"""
    other = tripped.repo.create(farm_id=FARM, turbine_id="WT001", type=WorkOrderType.CORRECTIVE, title="其他警報",
                                description="", source_alarm_code="482")
    tripped.start(other)
    tripped.finish(other)
    assert tripped.faults() == [WIRE_BREAK], "故障還在"
    tripped.drive(60)
    assert tripped.model().tur_state != 6 and tripped.model().maintenance_lock is True
    payload = next(e["payload"] for e in tripped.broker.storage.query_events(limit=50)
                   if e["title"].startswith("Work finished"))
    assert payload["repaired"] == []


def test_manual_corrective_and_inspection_orders_repair_everything_on_the_turbine(farm: Farm) -> None:
    farm.drive(120)
    farm.inject("bearing_wear", "WT002", severity=0.2)    # 還沒到警報：沒有工單會自己出現
    farm.inject("bearing_wear", "WT003", severity=0.2)
    farm.drive(30)
    assert farm.orders() == []
    manual = farm.repo.create(farm_id=FARM, turbine_id="WTG-02", type=WorkOrderType.CORRECTIVE, title="異音",
                              description="現場回報")   # 管理端手動開的工單用畫面上的機組名稱
    inspection = farm.repo.create(farm_id=FARM, turbine_id="WT003", type=WorkOrderType.INSPECTION, title="定檢：半年",
                                  description="")
    farm.start(manual)
    farm.start(inspection)
    farm.drive(30)
    assert farm.model("WT002").service_mode and farm.model("WT003").service_mode
    assert farm.model("WT003").tur_state != 6, "定檢期間機組停機"
    assert farm.loop.classify("WT002", 9) == "unplanned" and farm.loop.classify("WT003", 9) == "planned"
    farm.finish(manual)
    farm.finish(inspection)
    assert farm.faults("WT002") == [] and farm.faults("WT003") == []
    assert farm.until_producing("WT002") <= 300 and farm.until_producing("WT003") <= 300


def test_turbine_stays_in_service_until_the_last_work_order_finishes(farm: Farm) -> None:
    farm.drive(60)
    first = farm.repo.create(farm_id=FARM, turbine_id="WT001", type=WorkOrderType.INSPECTION, title="定檢",
                             description="")
    second = farm.repo.create(farm_id=FARM, turbine_id="WT001", type=WorkOrderType.CORRECTIVE, title="順便修",
                              description="")
    farm.start(first)
    farm.start(second)
    assert farm.loop.classify("WT001", 9) == "unplanned", "有一張是故障維修：算非計畫停機"
    farm.finish(second)
    farm.drive(20)
    assert farm.model().service_mode is True and farm.loop.classify("WT001", 9) == "planned"
    farm.finish(first)
    assert farm.model().service_mode is False
    assert farm.until_producing() <= 300


def test_cancelling_work_in_progress_releases_the_turbine_without_repair(tripped: Farm) -> None:
    order = tripped.orders()[0]
    tripped.start(order)
    assert tripped.model().service_mode is True
    tripped.repo.transition(order.id, "cancel", actor_id=BOSS, cancel_reason="誤派")
    assert tripped.model().service_mode is False and tripped.faults() == [WIRE_BREAK], "撤單不修"
    draft = tripped.repo.create(farm_id=FARM, turbine_id="WT002", type=WorkOrderType.INSPECTION, title="定檢",
                                description="")
    tripped.model("WT002").cmd_stop()     # 操作員另外把這台停下來
    tripped.repo.transition(draft.id, "cancel", actor_id=BOSS, cancel_reason="改期")
    assert tripped.model("WT002").service_mode is False
    assert tripped.model("WT002").operator_stop is True, "還沒開工的工單撤掉：不動機組（不會把操作員停的機組啟動）"


def test_rejected_signoff_puts_the_turbine_back_in_service_and_refinishing_does_not_reset_it(tripped: Farm) -> None:
    """簽核退回＝技師回現場：機組再進維修模式。完工不會把一台正常在發電、沒被這張工單佔著的機組重置
    （code review must-fix：復位會把發電機轉速與併網狀態歸零）。"""
    order = tripped.orders()[0]
    tripped.start(order)
    tripped.finish(order)
    tripped.until_producing()
    tripped.drive(120)
    power = float(tripped.broker.simulator.latest_data["WT001"]["scada"]["WTUR_TotPwrAt"])  # type: ignore[union-attr]
    assert power > 100, "測試前提：修好後在發電"

    # 沒被佔著、正在發電：直接再收到一次完工（例：開工時閉環沒在跑）不動機組
    tripped.loop._finish("WT001", order)
    tripped.drive(2)
    after = float(tripped.broker.simulator.latest_data["WT001"]["scada"]["WTUR_TotPwrAt"])  # type: ignore[union-attr]
    assert after > 0.8 * power and tripped.model().tur_state == 6, f"功率 {power:.0f} → {after:.0f} kW：機組被重置了"

    rejected = tripped.repo.transition(order.id, "reject", actor_id=BOSS, reject_reason="照片不清楚")
    assert rejected.status is WorkOrderStatus.IN_PROGRESS
    assert tripped.model().service_mode is True and tripped.loop.classify("WT001", 9) == "unplanned"
    tripped.drive(30)
    assert tripped.model().tur_state != 6
    tripped.finish(order)
    assert tripped.model().service_mode is False and tripped.until_producing() <= 300
    assert [t.split(":")[0] for t in tripped.workflow_events()] == [
        "Work order opened", "Work started", "Work finished", "Work finished", "Work resumed", "Work finished"]


def test_blocked_restart_work_order_repairs_the_faults_that_tripped(tripped: Farm) -> None:
    """A039（自動重啟被封鎖）不是獨立的故障：它開的工單修掉已經跳機鎖住機組的故障。"""
    blocked = tripped.repo.create(farm_id=FARM, turbine_id="WT001", type=WorkOrderType.CORRECTIVE, title="A039",
                                  description="", source_alarm_code="39")
    tripped.inject("bearing_wear", "WT001", severity=0.1)   # 還沒跳機的另一個故障：不歸這張工單
    tripped.start(blocked)
    tripped.finish(blocked)
    assert tripped.faults() == ["bearing_wear"], "修掉跳機鎖住的那個，還沒跳機的留著"
    assert tripped.until_producing() <= 300


def test_a_locked_turbine_always_gets_a_work_order_again(tripped: Farm) -> None:
    """工單被撤掉之後機組還鎖著，PLC 不會再送一次跳機：定期檢查補開一張。"""
    from server import om_loop

    order = tripped.orders()[0]
    tripped.repo.transition(order.id, "cancel", actor_id=BOSS, cancel_reason="誤撤")
    assert [o.status for o in tripped.orders()] == [WorkOrderStatus.CANCELLED]
    tripped.drive(int(om_loop.ENSURE_INTERVAL_S) + 20)
    orders = tripped.orders()
    assert [o.status for o in orders] == [WorkOrderStatus.CANCELLED, WorkOrderStatus.DRAFT]
    reopened = orders[1]
    assert reopened.source_alarm_code == "242" and "停機待修" in reopened.title
    assert WIRE_BREAK not in (reopened.title + reopened.description) and "斷線" not in reopened.description
    tripped.drive(int(om_loop.ENSURE_INTERVAL_S) * 2)
    assert len(tripped.orders()) == 2, "已經有未結案的工單：不再補開"
    tripped.start(reopened)
    tripped.finish(reopened)
    assert tripped.faults() == [] and tripped.until_producing() <= 300
    tripped.drive(int(om_loop.ENSURE_INTERVAL_S) * 2)
    assert len(tripped.orders()) == 2, "機組沒有鎖著：不補開"


def _tripping_scenarios() -> List[str]:
    from simulator.physics.fault_engine import FAULT_SCENARIOS

    return sorted(sid for sid, scenario in FAULT_SCENARIOS.items()
                  if scenario.category != "nuisance"
                  and any(str(item.get("type")) in ("T1", "T2") for item in scenario.alarm_codes))


@pytest.mark.parametrize("scenario_id", _tripping_scenarios())
def test_every_fault_that_trips_can_be_repaired_through_its_work_orders(tmp_path, scenario_id: str) -> None:
    """每一個會跳機的故障情境：跳機 → 自動開的工單逐張開工、完工 → 故障清掉、機組回到發電。"""
    farm = Farm(tmp_path, turbines=2)
    try:
        farm.drive(300)
        farm.inject(scenario_id, "WT001")
        for _ in range(60):          # 最多等 30 分鐘（風場時鐘）讓它跳機
            farm.drive(30)
            if farm.model().maintenance_lock:
                break
        if not farm.model().maintenance_lock:
            pytest.skip(f"{scenario_id} 在這個風況下 30 分鐘內沒有鎖住機組")
        farm.drive(30)
        orders = [o for o in farm.orders() if o.turbine_id == "WT001"]
        assert orders, "鎖住機組的跳機一定有工單"
        for order in orders:
            farm.start(order)
            farm.finish(order)
        assert farm.faults() == [], f"工單 {[o.source_alarm_code for o in orders]} 都完工了，故障還在"
        assert farm.until_producing(limit=1800) <= 1800
    finally:
        hooks.clear_work_order_listeners()
        wo_repo.clear_engine_cache_for_test()


def test_in_service_map_is_rebuilt_from_open_work_orders(farm: Farm) -> None:
    """伺服器重啟：機組的維修模式在狀態存檔裡，「因為哪張工單」要從工單重建。"""
    farm.drive(30)
    order = farm.repo.create(farm_id=FARM, turbine_id="WT002", type=WorkOrderType.PREVENTIVE, title="保養",
                             description="")
    farm.start(order)
    farm.loop._in_service.clear()
    assert farm.loop.classify("WT002", 9) == "planned", "沒有工單的維修模式（操作員手動切）算計畫停機"
    # 沒有還原存檔（風場從頭開始）：機組不在維修模式，但工單還在進行中
    farm.model("WT002").cmd_start()
    farm.until_producing("WT002")
    assert farm.loop.classify("WT002", 6) == "producing"
    farm.loop.rebuild()
    assert farm.loop.classify("WT002", 6) == "planned"
    assert farm.model("WT002").service_mode is True, "進行中的工單佔著的機組重新進維修模式"
    farm.drive(60)
    assert farm.model("WT002").tur_state != 6
    farm.finish(order)
    assert farm.loop.classify("WT002", 6) == "producing" and farm.until_producing("WT002") <= 300


# ── 4. 運轉狀態紀錄 ────────────────────────────────────────────────────────


def test_availability_comes_from_the_operating_state_record(tripped: Farm) -> None:
    order = tripped.orders()[0]
    tripped.drive(600)          # 沒有人處理：一直是非計畫停機
    tripped.start(order)
    tripped.drive(120)
    tripped.finish(order)
    tripped.until_producing()
    tripped.drive(300)
    report = tripped.loop.availability(T0, T0 + timedelta(hours=2))
    by_turbine = {t["turbine_id"]: t for t in report["turbines"]}
    down, healthy = by_turbine["WT001"], by_turbine["WT002"]
    assert down["planned_downtime_hours"] == 0.0
    assert 0.20 <= down["unplanned_downtime_hours"] <= 0.25, "跳機到完工約 13 分鐘"
    assert healthy["unplanned_downtime_hours"] == 0.0 and healthy["time_availability"] == 1.0
    assert 0.0 < down["time_availability"] < 0.75
    assert down["lost_unplanned_kwh"] > 0 and down["energy_availability"] < 1.0
    assert down["recorded_hours"] == pytest.approx(healthy["recorded_hours"])
    total = sum(t["recorded_hours"] for t in report["turbines"])
    farm_total = report["farm"]
    assert farm_total["recorded_hours"] == pytest.approx(total)
    assert farm_total["time_availability"] == pytest.approx(1 - down["unplanned_downtime_hours"] / total)
    assert farm_total["energy_kwh"] == pytest.approx(sum(t["energy_kwh"] for t in report["turbines"]))
    # 停機少發的電＝同一時刻發電中的機組的平均功率
    assert down["lost_unplanned_kwh"] == pytest.approx(
        down["unplanned_downtime_hours"] * healthy["energy_kwh"] / healthy["producing_hours"], rel=0.25)

    empty = tripped.loop.availability(T0 + timedelta(days=5), T0 + timedelta(days=6))
    assert empty["turbines"] == [] and empty["farm"]["time_availability"] is None


def test_planned_downtime_is_counted_separately(farm: Farm) -> None:
    farm.drive(60)
    order = farm.repo.create(farm_id=FARM, turbine_id="WT002", type=WorkOrderType.INSPECTION, title="定檢",
                             description="")
    farm.start(order)
    farm.drive(360)
    farm.finish(order)
    farm.drive(60)
    turbine = {t["turbine_id"]: t for t in farm.loop.availability(T0, T0 + timedelta(hours=1))["turbines"]}["WT002"]
    assert turbine["planned_downtime_hours"] == pytest.approx(0.1, abs=0.01)
    assert turbine["unplanned_downtime_hours"] == 0.0 and turbine["lost_planned_kwh"] > 0


def test_availability_endpoint_and_report_provider(tripped: Farm, monkeypatch) -> None:
    from server import app as app_module
    from server.routers import operations as ops

    tripped.drive(600)
    monkeypatch.setattr(ops, "get_broker", lambda: tripped.broker)
    monkeypatch.setattr(app_module, "broker", tripped.broker)
    body = asyncio.run(ops.availability(start="2026-01-01T00:00:00Z", end="2026-01-01T02:00:00Z"))
    assert body["enabled"] is True and len(body["turbines"]) == 3
    assert body["farm"]["unplanned_downtime_hours"] > 0.15
    default = asyncio.run(ops.availability())   # 預設：風場時鐘往前 24 小時
    assert default["farm"]["recorded_hours"] == pytest.approx(body["farm"]["recorded_hours"])
    for bad in ({"start": "nope"}, {"start": "2026-01-02T00:00:00Z", "end": "2026-01-01T00:00:00Z"},
                {"start": "2020-01-01T00:00:00Z", "end": "2026-01-01T00:00:00Z"}):
        with pytest.raises(Exception) as caught:
            asyncio.run(ops.availability(**bad))
        assert getattr(caught.value, "status_code", None) == 422

    # 報表的可用率改由運轉狀態紀錄提供；別座風場或沒有紀錄時回 None（報表退回由工單工時推估）
    start, end = T0, T0 + timedelta(hours=2)
    provided = app_module._availability_for_report(FARM, start, end)
    assert provided is not None and provided[0] == pytest.approx(body["farm"]["time_availability"])
    assert 0 < provided[1] < 1
    assert app_module._availability_for_report("other-farm", start, end) is None
    assert app_module._availability_for_report(FARM, T0 + timedelta(days=9), T0 + timedelta(days=10)) is None
    tripped.loop.enabled = False
    assert app_module._availability_for_report(FARM, start, end) is None


# ── 5. 不該動的時候不動 ────────────────────────────────────────────────────


def test_disabled_loop_does_nothing(tmp_path) -> None:
    farm = Farm(tmp_path, enabled=False)
    try:
        assert farm.broker._om_loop is None, "沒開閉環的 broker 不載入工單模組"
        farm.drive(120)
        farm.inject(WIRE_BREAK)
        farm.drive(60)
        assert farm.model().maintenance_lock is True
        assert farm.orders() == []
        assert farm.broker.storage.availability_totals("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z") == []
        hooks.add_work_order_listener(farm.broker.om_loop.on_work_order)   # 接了線、但沒開
        order = farm.repo.create(farm_id=FARM, turbine_id="WT001", type=WorkOrderType.CORRECTIVE, title="x",
                                 description="")
        farm.start(order)
        farm.finish(order)
        assert farm.faults() == [WIRE_BREAK] and farm.model().service_mode is False
        sim = farm.broker.simulator
        assert sim is not None
        farm.loop.account(sim._run_one_step(T0 + timedelta(hours=1), 1.0), 10.0)   # 直接呼叫也不記
        assert farm.broker.storage.availability_totals("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z") == []
    finally:
        hooks.clear_work_order_listeners()
        wo_repo.clear_engine_cache_for_test()


def test_work_orders_of_other_farms_and_unknown_turbines_are_ignored(tripped: Farm) -> None:
    for farm_id, turbine_id in (("other-farm", "WT001"), (FARM, "WT099"), (FARM, "葉片倉庫")):
        order = tripped.repo.create(farm_id=farm_id, turbine_id=turbine_id, type=WorkOrderType.CORRECTIVE,
                                    title="x", description="")
        tripped.start(order)
        tripped.finish(order)
    assert tripped.faults() == [WIRE_BREAK] and tripped.model().service_mode is False
    assert sim_turbine_id("WTG-07", ["WT007"]) == "WT007" and sim_turbine_id("WT007", ["WT007"]) == "WT007"
    assert sim_turbine_id("WTG-08", ["WT007"]) is None and sim_turbine_id("wtg-07", ["WT007"]) is None


def test_loop_only_acts_on_the_live_simulation(tripped: Farm) -> None:
    """產生情境（批次）與重跑段不開單、不修機組：批次有自己的故障排程，重跑段的事在重啟前做過了。"""
    from simulator.physics.plc_protection import PlcEvent

    trip = PlcEvent(sim_time=1.0, kind="trip", code=336, level="T2", text="t", plc_tag=None, event_id="T_336",
                    value=None, setpoint=None, source="signal")
    sim = tripped.broker.simulator
    assert sim is not None
    sim._bulk_running = True
    assert tripped.loop.on_plc_event("WT002", trip) is None
    sim._bulk_running = False

    tripped.broker._replay_local.active = True     # 重跑段：事件偵測照跑，但不開單
    try:
        tripped.broker._record_plc_event("WT002", trip)
    finally:
        tripped.broker._replay_local.active = False
    assert [o.source_alarm_code for o in tripped.orders()] == ["242"]
    tripped.broker._record_plc_event("WT002", trip)
    assert sorted(o.source_alarm_code for o in tripped.orders()) == ["242", "336"]
    # 去重段（伺服器被強制關閉後重跑最後幾秒）：同一筆跳機再來一次，事件不重記、工單也不重開。
    # 這裡不擋開單：開單那一刻被強制關閉的話，工單可能沒寫進去，重跑時要補上；已有未結案的同碼工單就不會重複
    tripped.broker._replay_local.dedupe = True
    try:
        tripped.broker._record_plc_event("WT002", trip)
    finally:
        tripped.broker._replay_local.dedupe = False
    assert sorted(o.source_alarm_code for o in tripped.orders()) == ["242", "336"]


def test_work_order_actions_during_a_batch_apply_after_live_is_restored(tmp_path) -> None:
    """產生情境的批次結束後 Live 的狀態會被還原：批次期間的完工若直接動機組會被蓋掉，要等還原之後才套用。"""
    from server.models import DataSourceConfig, DataSourceMode, SimulationConfig

    broker = DataBroker(farm_registry=FarmRegistry(data_dir=tmp_path))
    broker.om_loop.enabled = True
    hooks.add_work_order_listener(broker.om_loop.on_work_order)
    broker.start(DataSourceConfig(mode=DataSourceMode.SIMULATION), SimulationConfig(turbineCount=2, timeStep=1.0))
    try:
        sim = broker.simulator
        assert sim is not None
        farm_id = broker._active_farm_id
        repo = wo_repo.get_repository(str(broker.storage.db_path))
        sim.stop_live_loop()
        assert sim.fault_engine.inject("bearing_wear", "WT001", severity_rate=0.0, initial_severity=0.3)
        sim.restore_live_loop(True)
        order = repo.create(farm_id=farm_id, turbine_id="WT001", type=WorkOrderType.CORRECTIVE, title="異音",
                            description="")
        repo.transition(order.id, "dispatch", actor_id=BOSS, assignee_id=TECH)
        repo.transition(order.id, "start_work", actor_id=TECH)
        assert sim.turbines["WT001"].service_mode is True

        with broker.pause_live_for_batch():
            sim.start_clean_scenario()       # 批次會清掉故障、重設機組
            repo.transition(order.id, "finish", actor_id=TECH, actual_hours=1.0, followup_kind=FollowupKind.NONE)
            assert len(broker.om_loop._pending) == 1 and broker.om_loop._batch_paused, "批次期間先記著"
        # 批次結束：Live 的狀態還原（故障與維修模式都回來），然後才套用完工
        assert broker.om_loop._pending == [] and broker.om_loop._batch_paused is False
        assert [f.scenario_id for f in sim.fault_engine.active_faults] == [], "完工的修復沒有被還原蓋掉"
        assert sim.turbines["WT001"].service_mode is False
        titles = [e["title"] for e in broker.storage.query_events(limit=50) if e["source"] == "workflow"]
        assert any(t.startswith("Work finished") for t in titles)
    finally:
        broker.stop()
        hooks.clear_work_order_listeners()
        wo_repo.clear_engine_cache_for_test()


def test_listener_failures_never_break_the_work_order_operation(farm: Farm) -> None:
    calls: List[str] = []

    def broken(work_order: WorkOrder, action: str, from_status) -> None:
        calls.append(action)
        raise RuntimeError("listener exploded")

    hooks.add_work_order_listener(broken)
    hooks.add_work_order_listener(broken)   # 重複登記只算一次
    order = farm.repo.create(farm_id=FARM, turbine_id="WT001", type=WorkOrderType.INSPECTION, title="定檢",
                             description="")
    started = farm.start(order)
    assert started.status is WorkOrderStatus.IN_PROGRESS and calls == ["create", "dispatch", "start_work"]
    hooks.remove_work_order_listener(broken)
    farm.finish(order)
    assert calls == ["create", "dispatch", "start_work"]


def test_app_wiring_follows_the_environment(tmp_path, monkeypatch) -> None:
    from server import app as app_module

    broker = DataBroker(farm_registry=FarmRegistry(data_dir=tmp_path))
    monkeypatch.setattr(app_module, "broker", broker)
    monkeypatch.delenv("WMOM_AUTOSTART_SOURCE", raising=False)
    try:
        monkeypatch.setenv("WMOM_OM_LOOP", "false")
        app_module._apply_continuous_run_settings("farm")
        assert broker._om_loop is None and broker._om_loop_if_enabled() is None
        monkeypatch.delenv("WMOM_OM_LOOP")
        app_module._apply_continuous_run_settings("farm")
        assert broker.om_loop.enabled is True, "伺服器預設開"
        monkeypatch.setenv("WMOM_OM_LOOP", "off")
        app_module._apply_continuous_run_settings("farm")
        assert broker.om_loop.enabled is False and broker._om_loop_if_enabled() is None
        routes: Dict[str, object] = app_module.app.openapi()["paths"]
        assert "/api/operations/availability" in routes
        assert not any(path.startswith("/api/ext/") and "availability" in path for path in routes), "可用率不對外"
    finally:
        broker.stop()
        wo_repo.clear_engine_cache_for_test()
