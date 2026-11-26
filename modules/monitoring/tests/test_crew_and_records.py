"""模擬維修班與不對外的故障紀錄（WMOM-20261125-06-c / -d）。

1. 故障紀錄：發生、第一次警報、跳機、被哪張工單修好；只在即時模擬記；不進可觀測的東西。
2. 模擬維修班：過了反應時間沒人處理才接手、同時幾組、優先級、人開工的不碰、完工後結案、重啟後接著算。
3. 產生器＋閉環＋維修班一起：風場自己故障、開單、修復，不會一台一台停下來。
4. 設定存在風場 DB；端點只給主管。
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from modules.workflow import hooks
from modules.workflow.domain import Priority, WorkOrderStatus, WorkOrderType
from modules.workflow.repository import work_order_repository as wo_repo
from server.crew import CREW_TECH, CrewConfig
from server.routers import operations as ops
from server.storage import is_observable_event
from simulator.fault_generator import FaultGeneratorConfig

from .test_om_loop import FARM, WIRE_BREAK, Farm


@pytest.fixture
def farm(tmp_path) -> Iterator[Farm]:
    f = Farm(tmp_path, turbines=5)
    sim = f.broker.simulator
    assert sim is not None
    sim.retrip_after_restart = True
    try:
        yield f
    finally:
        hooks.clear_work_order_listeners()
        wo_repo.clear_engine_cache_for_test()


def _crew(farm: Farm, **changes) -> None:
    farm.loop.crew.configure(CrewConfig.from_dict(
        {"enabled": True, "response_minutes": 10, "repair_minutes": 20, "inspection_minutes": 15, **changes}))


def _status(farm: Farm, order) -> WorkOrderStatus:
    return farm.repo.get(order.id).status


# ── 1. 故障紀錄 ───────────────────────────────────────────────────────────


def test_record_follows_a_fault_from_onset_to_repair(farm: Farm) -> None:
    farm.drive_slow(60)
    farm.inject("bearing_wear", "WT002", severity=0.55)
    for _ in range(2000):
        farm.drive(1)
    (case,) = farm.broker.fault_records.cases()
    assert (case["turbine_id"], case["fault_id"], case["source"]) == ("WT002", "bearing_wear", "manual")
    assert case["first_alarm_code"] == 262 and case["trip_code"] == 240 and case["trip_count"] == 2
    assert case["onset_ts"] < case["first_alarm_ts"] < case["trip_ts"] and case["cleared_ts"] is None
    assert case["root_cause"] and case["expected_alarm_codes"] == [262, 240] and case["key_signals"]
    assert {o["code"] for o in case["observed"]} >= {262, 240, 39}
    assert [o["expected"] for o in case["observed"] if o["code"] == 39] == [False]
    order = farm.orders()[0]
    farm.start(order)
    farm.finish(order)
    farm.drive(20)
    (case,) = farm.broker.fault_records.cases()
    assert case["cleared_by"] == f"work_order:{order.business_key}" and case["cleared_ts"] > case["trip_ts"]
    assert farm.broker.fault_records.cases(open_only=True) == []
    # 管理端直接清除的記成 manual
    farm.inject(WIRE_BREAK, "WT003")
    farm.drive(30)
    sim = farm.broker.simulator
    sim.fault_engine.clear(turbine_id="WT003")
    farm.drive(20)
    latest = farm.broker.fault_records.cases(turbine_id="WT003")[0]
    assert latest["cleared_by"] == "manual" and latest["trip_code"] == 242


def test_records_stay_out_of_everything_observable(farm: Farm) -> None:
    farm.drive_slow(30)
    farm.inject(WIRE_BREAK, "WT001")
    farm.drive(60)
    assert farm.broker.fault_records.cases()
    events = farm.broker.storage.live_events(after_id=0, limit=2000)
    visible = [e for e in events if is_observable_event(e)]
    blob = json.dumps(visible, ensure_ascii=False, default=str)
    assert WIRE_BREAK not in blob and "sensor_fault" not in blob and "root_cause" not in blob
    # 批次情境不記（那邊的答案是 scenario_ground_truth）
    sim = farm.broker.simulator
    sim._bulk_running = True
    farm.inject("bearing_wear", "WT004", severity=0.9)
    farm.drive(30)
    assert [c["turbine_id"] for c in farm.broker.fault_records.cases()] == ["WT001"]


# ── 2. 模擬維修班 ─────────────────────────────────────────────────────────


def test_crew_is_off_by_default_and_waits_for_the_response_time(farm: Farm) -> None:
    farm.drive_slow(30)
    farm.inject(WIRE_BREAK, "WT001")
    farm.drive_slow(120)   # 20 分鐘：維修班沒開
    order = farm.orders()[0]
    assert _status(farm, order) is WorkOrderStatus.DRAFT and farm.loop.crew.config.enabled is False
    _crew(farm)
    farm.drive_slow(54)    # 第一次看到之後 9 分鐘：還在反應時間內，留給人處理
    assert _status(farm, order) is WorkOrderStatus.DRAFT
    farm.drive_slow(12)    # 滿 10 分鐘：維修班接手
    assert _status(farm, order) is WorkOrderStatus.IN_PROGRESS and farm.model().service_mode is True
    assert farm.repo.get(order.id).assignee_id == CREW_TECH
    farm.drive_slow(108)   # 開工後 19 分鐘
    assert _status(farm, order) is WorkOrderStatus.IN_PROGRESS and farm.faults() == [WIRE_BREAK]
    farm.drive_slow(12)
    assert _status(farm, order) is WorkOrderStatus.CLOSED, "完工後直接結案"
    assert farm.faults() == [] and farm.until_producing() is not None
    (case,) = farm.broker.fault_records.cases()
    assert case["cleared_by"] == f"work_order:{order.business_key}"


def test_crew_takes_urgent_orders_first_and_respects_its_size(farm: Farm) -> None:
    farm.drive_slow(30)
    make = lambda turbine, priority: farm.repo.create(   # noqa: E731
        farm_id=FARM, turbine_id=turbine, type=WorkOrderType.CORRECTIVE, title="x", description="",
        priority=priority)
    low, normal, high = make("WT001", Priority.LOW), make("WT002", Priority.NORMAL), make("WT003", Priority.HIGH)
    second = make("WT003", Priority.CRITICAL)   # 同一台機組的第二張
    _crew(farm, crews=2)
    farm.drive_slow(72)
    states = {name: _status(farm, o) for name, o in (("low", low), ("normal", normal), ("high", high),
                                                   ("second", second))}
    assert states["second"] is WorkOrderStatus.IN_PROGRESS, "最急的先做"
    assert states["high"] is not WorkOrderStatus.IN_PROGRESS, "同一台機組一次一張"
    assert states["normal"] is WorkOrderStatus.IN_PROGRESS and states["low"] is WorkOrderStatus.DRAFT, "只有兩組"
    farm.drive_slow(140)
    assert _status(farm, second) is WorkOrderStatus.CLOSED and _status(farm, normal) is WorkOrderStatus.CLOSED
    farm.drive_slow(140)
    assert _status(farm, high) is WorkOrderStatus.CLOSED and _status(farm, low) is WorkOrderStatus.CLOSED


def test_crew_leaves_orders_people_are_working_on(farm: Farm) -> None:
    farm.drive_slow(30)
    mine = farm.repo.create(farm_id=FARM, turbine_id="WT001", type=WorkOrderType.INSPECTION, title="定檢",
                            description="")
    _crew(farm)
    farm.start(mine)                 # 人自己開工
    farm.drive_slow(400)
    assert _status(farm, mine) is WorkOrderStatus.IN_PROGRESS, "人開工的工單維修班不完工"
    farm.finish(mine)                # 人完工，沒有人簽核
    farm.drive_slow(30)
    assert _status(farm, mine) is WorkOrderStatus.AWAITING_SIGNOFF
    farm.drive_slow(40)
    assert _status(farm, mine) is WorkOrderStatus.CLOSED, "等簽核超過反應時間：維修班結案"
    # 有簽核鏈的（人從畫面完工的）留給簽核流程：直接結案會留下一條沒人簽的鏈
    from uuid import uuid4

    from modules.workflow.repository.orm_models import WorkOrderORM
    from sqlalchemy import update

    chained = farm.repo.create(farm_id=FARM, turbine_id="WT003", type=WorkOrderType.INSPECTION, title="定檢",
                               description="")
    farm.start(chained)
    farm.finish(chained)
    with farm.repo._sessionmaker() as session:
        session.execute(update(WorkOrderORM).where(WorkOrderORM.id == str(chained.id))
                        .values(signoff_chain_id=str(uuid4())))
        session.commit()
    farm.drive_slow(200)
    assert _status(farm, chained) is WorkOrderStatus.AWAITING_SIGNOFF
    # close_after_finish 關掉：完工後留在等簽核
    _crew(farm, close_after_finish=False)
    other = farm.repo.create(farm_id=FARM, turbine_id="WT002", type=WorkOrderType.INSPECTION, title="定檢",
                             description="")
    farm.drive_slow(220)
    assert _status(farm, other) is WorkOrderStatus.AWAITING_SIGNOFF


def test_crew_lets_go_when_a_person_takes_over(farm: Farm) -> None:
    """維修班開工之後人接手完工、被退回重做：那張工單不再算維修班的，維修班不會替人完工。"""
    farm.drive_slow(30)
    order = farm.repo.create(farm_id=FARM, turbine_id="WT001", type=WorkOrderType.CORRECTIVE, title="x",
                             description="")
    _crew(farm, close_after_finish=False)
    farm.drive_slow(72)
    assert _status(farm, order) is WorkOrderStatus.IN_PROGRESS
    farm.finish(order)               # 人接手完工
    farm.drive_slow(12)
    assert farm.loop.crew._jobs[str(order.id)]["started"] is None
    farm.repo.transition(order.id, "reject", actor_id=CREW_TECH, reject_reason="重做")   # 退回 → 施工中
    farm.drive_slow(300)
    assert _status(farm, order) is WorkOrderStatus.IN_PROGRESS, "現在是人的工單"
    # 由關轉開：積壓的工單從現在起算反應時間
    waiting = farm.repo.create(farm_id=FARM, turbine_id="WT002", type=WorkOrderType.CORRECTIVE, title="x",
                               description="")
    farm.drive_slow(12)              # 維修班先看到它（開始算反應時間）
    farm.loop.crew.configure(CrewConfig())
    farm.drive_slow(200)             # 關著的這段時間早就超過反應時間
    _crew(farm)
    farm.drive_slow(48)
    assert _status(farm, waiting) is WorkOrderStatus.DRAFT, "不會一打開就接手"
    farm.drive_slow(24)
    assert _status(farm, waiting) is WorkOrderStatus.IN_PROGRESS


def test_crew_does_not_fill_in_day_work_forms(farm: Farm) -> None:
    from modules.workflow.repository import work_order_repository as repo_module

    assert CREW_TECH in repo_module._NO_DAY_FORM_ASSIGNEES
    farm.drive_slow(30)
    order = farm.repo.create(farm_id=FARM, turbine_id="WT001", type=WorkOrderType.CORRECTIVE, title="x",
                             description="")
    _crew(farm)
    calls: list = []
    original = repo_module.WorkOrderRepository._record_completed_wo_activity

    def spy(self, wo):
        calls.append(wo.assignee_id)
        return original(self, wo)

    repo_module.WorkOrderRepository._record_completed_wo_activity = spy
    try:
        farm.drive_slow(200)
    finally:
        repo_module.WorkOrderRepository._record_completed_wo_activity = original
    assert _status(farm, order) is WorkOrderStatus.CLOSED and calls == [CREW_TECH]
    from modules.workflow.repository.day_work_form_repository import DayWorkFormORM

    with farm.repo._sessionmaker() as session:
        assert session.query(DayWorkFormORM).count() == 0, "模擬維修班不是真人：不寫當日工作表"


def test_crew_timing_survives_a_restart(farm: Farm) -> None:
    farm.drive_slow(30)
    order = farm.repo.create(farm_id=FARM, turbine_id="WT001", type=WorkOrderType.CORRECTIVE, title="x",
                             description="")
    _crew(farm)
    farm.drive_slow(72)
    assert _status(farm, order) is WorkOrderStatus.IN_PROGRESS
    saved = farm.broker.storage.get_setting("crew_state")
    assert saved["jobs"][str(order.id)]["started"]
    farm.loop.crew.reset()           # 重啟：記憶體裡的狀態沒了
    farm.drive_slow(54)
    assert _status(farm, order) is WorkOrderStatus.IN_PROGRESS, "還沒滿 20 分鐘"
    farm.drive_slow(60)
    assert _status(farm, order) is WorkOrderStatus.CLOSED, "開工時間從風場 DB 讀回來：沒讀回來的話維修班不會完工它"


# ── 3. 一起跑 ─────────────────────────────────────────────────────────────


def test_farm_fails_and_recovers_on_its_own(farm: Farm) -> None:
    """產生器＋閉環＋維修班：風場自己故障、開單、修復。跑完之後沒有機組一直停著。"""
    sim = farm.broker.simulator
    sim.fault_generator.configure(FaultGeneratorConfig.from_dict({
        "enabled": True, "mean_days_between_faults": 0.02, "min_hours_to_full": 0.05, "max_hours_to_full": 0.2,
        # 只用很快就跳機的情境，測試才跑得完
        "scenario_weights": {sid: (1.0 if sid in (WIRE_BREAK, "yaw_brake_pressure_sensor_fault",
                                                  "blade1_pitch_encoder_fault") else 0.0)
                             for sid in sim.fault_engine.get_scenarios()}}))
    _crew(farm, response_minutes=5, repair_minutes=10, crews=2)
    farm.drive_slow(60 * 30)   # 5 小時
    cases = farm.broker.fault_records.cases()
    assert len(cases) >= 5 and {c["source"] for c in cases} == {"generator"}
    repaired = [c for c in cases if c["cleared_ts"]]
    assert len(repaired) >= len(cases) - 5 and all(c["cleared_by"].startswith("work_order:") for c in repaired)
    assert all(c["severity_rate"] for c in cases)
    farm.broker.simulator.fault_generator.configure(FaultGeneratorConfig())   # 關掉，讓維修班收尾
    farm.drive_slow(60 * 6)
    assert farm.broker.fault_records.cases(open_only=True) == []
    assert [m.tur_state for m in sim.turbines.values()] == [6] * 5, "全部回到發電"
    orders, _ = farm.repo.list(farm_id=FARM, only_open=True, limit=100)
    assert orders == []


# ── 4. 設定與端點 ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad", [{"crews": 0}, {"response_minutes": -1}, {"repair_minutes": "x"}, {"nope": 1},
                                 {"crews": 1.5}, {"enabled": "false"}, {"close_after_finish": 0}])
def test_bad_crew_settings_are_rejected(bad: dict) -> None:
    with pytest.raises(ValueError):
        CrewConfig.from_dict(bad)


def test_settings_are_stored_with_the_farm_and_applied_on_start(farm: Farm, monkeypatch) -> None:
    monkeypatch.setattr(ops, "get_broker", lambda: farm.broker)
    farm.drive(5)
    body = asyncio.run(ops.set_fault_generator_settings({"enabled": True, "mean_days_between_faults": 12,
                                                         "turbine_weights": {"WT002": 3}}))
    assert body["config"]["mean_days_between_faults"] == 12.0 and body["generated"] == 0
    assert body["scenarios"]["blade_icing"] == 0.0 and body["scenarios"]["bearing_wear"] == 1.0
    asyncio.run(ops.set_crew_settings({"enabled": True, "crews": 3}))
    assert farm.broker.simulator.fault_generator.config.enabled and farm.loop.crew.config.crews == 3
    # 存進風場 DB：重新套用（即時模擬重新啟動時）拿得回來
    farm.broker.simulator.fault_generator.configure(FaultGeneratorConfig())
    farm.loop.crew.configure(CrewConfig())
    farm.broker.apply_live_settings()
    assert farm.broker.simulator.fault_generator.config.turbine_weights == {"WT002": 3.0}
    assert farm.loop.crew.config.crews == 3 and asyncio.run(ops.crew_settings())["config"]["enabled"] is True
    for call in (ops.set_fault_generator_settings({"mean_days_between_faults": 0}),
                 ops.set_fault_generator_settings({"enabled": "false"}),
                 ops.set_fault_generator_settings({"turbine_weights": {"WT099": 1}}),
                 ops.set_crew_settings({"crews": 0})):
        with pytest.raises(HTTPException) as caught:
            asyncio.run(call)
        assert caught.value.status_code == 422
    # 沒存過的風場用啟動時的預設
    farm.broker.storage._get_conn().execute("DELETE FROM farm_settings")
    farm.broker.storage._get_conn().commit()
    farm.broker.default_live_settings = {"fault_generator": {"enabled": True}, "crew": {"enabled": True}}
    farm.broker.apply_live_settings()
    assert farm.broker.simulator.fault_generator.config.enabled and farm.loop.crew.config.enabled
    assert farm.broker.simulator.fault_generator.config.mean_days_between_faults == 30.0


def test_endpoints_are_for_supervisors_only_even_without_enforced_login(farm: Farm, monkeypatch) -> None:
    monkeypatch.setattr(ops, "get_broker", lambda: farm.broker)
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)
    farm.drive(5)
    farm.inject(WIRE_BREAK, "WT001")
    farm.drive(30)
    cases = asyncio.run(ops.fault_records())["cases"]
    assert cases and cases[0]["fault_id"] == WIRE_BREAK
    assert asyncio.run(ops.fault_records(turbine_id="WT002"))["cases"] == []
    app = FastAPI()
    app.include_router(ops.router)
    client = TestClient(app)
    for method, path in (("get", "/fault-records"), ("get", "/fault-generator"), ("put", "/fault-generator"),
                         ("get", "/crew"), ("put", "/crew")):
        response = getattr(client, method)("/api/operations" + path, **({"json": {}} if method == "put" else {}))
        assert response.status_code in (401, 403), (method, path, response.status_code)


def test_records_are_not_double_counted_while_replaying_after_a_hard_kill(farm: Farm, monkeypatch) -> None:
    """伺服器被強制關閉後重跑最後幾秒：同一筆跳機不能在故障紀錄裡再算一次。"""
    farm.drive_slow(30)
    farm.inject(WIRE_BREAK, "WT001")
    farm.drive(30)
    (case,) = farm.broker.fault_records.cases()
    assert case["trip_count"] == 1 and len(case["observed"]) == 1
    from simulator.physics.plc_protection import PlcEvent

    again = PlcEvent(sim_time=1.0, kind="trip", code=242, level="T1", text="x", plc_tag=None, event_id="T_242",
                     value=None, setpoint=None, source="signal")
    for name in ("_deduping", "_replaying"):
        with monkeypatch.context() as patched:
            patched.setattr(farm.broker, name, lambda: True)
            assert farm.broker._recording_faults() is False
            farm.broker._record_plc_event("WT001", again)
    (case,) = farm.broker.fault_records.cases()
    assert case["trip_count"] == 1 and len(case["observed"]) == 1
    farm.broker._record_plc_event("WT001", again)
    assert farm.broker.fault_records.cases()[0]["trip_count"] == 2, "對照：平常會算"


def test_settings_are_reapplied_after_a_batch(farm: Farm) -> None:
    """批次結束時即時模擬的狀態會還原成批次前的：產生器的設定要再從風場 DB 套一次。"""
    farm.drive(5)
    broker = farm.broker
    broker.storage.set_setting(broker.SETTING_FAULT_GENERATOR,
                               FaultGeneratorConfig.from_dict({"enabled": True, "seed": 3}).to_dict())
    import inspect

    source = inspect.getsource(type(broker).pause_live_for_batch)
    assert "apply_live_settings" in source
    broker.apply_live_settings()
    assert broker.simulator.fault_generator.config.seed == 3
