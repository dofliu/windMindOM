"""仿真風場的自動定檢計畫（WMOM-20261127-03，DEC-20261127-05）。

1. 每台機組一個排程、錯開到期；依風場時鐘開定檢工單，實際時間的人工排程器不碰這些排程。
2. 不重複：同一期只開一次、重啟後不重建、已有未結案的定檢工單就算那張、上限擋下時下次再試。
3. 和閉環、維修班一起：潛伏的故障（沒有警報）由自動定檢找到、修掉。
4. 停用 / 改週期、只作用在即時模擬、設定存在風場 DB、端點只給主管。
"""

from __future__ import annotations

import asyncio
import sys
from datetime import timedelta
from pathlib import Path
from typing import Iterator, List

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
from modules.workflow.domain import WorkOrderStatus, WorkOrderType
from modules.workflow.domain.inspection_schedule import InspectionSchedule, Recurrence
from modules.workflow.domain.work_order import WorkOrder
from modules.workflow.repository import work_order_repository as wo_repo
from modules.workflow.repository.inspection_repository import get_inspection_repository
from modules.workflow.services.inspection_scheduler import run_inspection_scheduler
from server.crew import CrewConfig
from server.inspection_plan import PLAN_ACTOR, PLAN_TITLE, InspectionPlanConfig
from server.routers import operations as ops

from .test_om_loop import FARM, Farm

DAY = 86400


@pytest.fixture
def farm(tmp_path) -> Iterator[Farm]:
    f = Farm(tmp_path, turbines=3)
    try:
        yield f
    finally:
        hooks.clear_work_order_listeners()
        wo_repo.clear_engine_cache_for_test()


def _plan(farm: Farm, **changes) -> None:
    farm.loop.inspection_plan.configure(InspectionPlanConfig.from_dict({"enabled": True, "interval_days": 3,
                                                                        **changes}))


def _jump(farm: Farm, seconds: int) -> None:
    """風場時鐘往前跳（不模擬中間那段；之後的步從新的時刻接著走）。"""
    farm._step += seconds


def _clock(farm: Farm):
    clock = farm.broker.live_clock()
    assert clock is not None
    return clock


def _schedules(farm: Farm) -> List[InspectionSchedule]:
    return sorted(farm.loop.inspection_plan.schedules(), key=lambda s: s.turbine_id)


def _inspections(farm: Farm) -> List[WorkOrder]:
    return [o for o in farm.orders() if o.type is WorkOrderType.INSPECTION]


# ── 1. 排程與開單 ─────────────────────────────────────────────────────────


def test_each_turbine_gets_a_staggered_schedule_on_the_farm_clock(farm: Farm) -> None:
    farm.drive_slow(1)
    assert _schedules(farm) == [], "預設關：不建排程"
    _plan(farm)
    farm.drive_slow(1)
    now = _clock(farm)
    schedules = _schedules(farm)
    assert [s.turbine_id for s in schedules] == ["WT001", "WT002", "WT003"]
    assert all(s.active and s.created_by == PLAN_ACTOR and s.title == PLAN_TITLE for s in schedules)
    assert all(s.recurrence is Recurrence.CUSTOM_DAYS and s.interval_days == 3 for s in schedules)
    assert [round((s.next_due_at - now).total_seconds() / DAY, 3) for s in schedules] == [1.0, 2.0, 3.0], "錯開"
    # workflow 的人工排程器用實際時間（比這座測試風場的時鐘晚了快一年）：自動計畫的排程它不跑
    inspections = get_inspection_repository(str(farm.broker.storage.db_path))
    assert run_inspection_scheduler(inspections, farm.repo, FARM) == []
    assert _inspections(farm) == []


def test_due_schedules_open_inspection_orders_once_per_period(farm: Farm) -> None:
    _plan(farm)
    farm.drive_slow(1)
    _jump(farm, DAY)
    farm.drive_slow(1)
    (order,) = _inspections(farm)
    assert (order.turbine_id, order.title, order.created_by) == ("WT001", f"定檢：{PLAN_TITLE}", PLAN_ACTOR)
    assert order.status is WorkOrderStatus.DRAFT and order.source_alarm_code is None
    spawned_at = _clock(farm)
    first = _schedules(farm)[0]
    assert first.last_spawned_work_order_id == order.id and first.next_due_at == spawned_at + timedelta(days=3)
    farm.drive_slow(200)   # 半小時多：每 15 分鐘看一次，同一期不再開
    assert len(_inspections(farm)) == 1
    # 工單建立時產生例行巡檢卡
    stored = farm.broker.storage.get_briefing(work_order_id=str(order.id))
    assert stored is not None and stored["kind"] == "routine_inspection"
    _jump(farm, DAY)
    farm.drive_slow(1)
    assert [o.turbine_id for o in _inspections(farm)] == ["WT001", "WT002"]


def test_an_open_inspection_covers_the_next_period(farm: Farm) -> None:
    """沒有人處理的定檢工單不會一期一張堆起來（會佔滿每台三張的上限，跳機開不了單）。"""
    _plan(farm, interval_days=1)
    farm.drive_slow(1)
    _jump(farm, DAY // 3 + 60)
    farm.drive_slow(1)
    (order,) = _inspections(farm)
    _jump(farm, DAY + 60)
    farm.drive_slow(1)
    assert [o.turbine_id for o in _inspections(farm)].count("WT001") == 1
    first = _schedules(farm)[0]
    assert first.last_spawned_work_order_id == order.id and first.next_due_at > _clock(farm), "這一期算那張"


def test_a_full_turbine_is_retried_later(farm: Farm, monkeypatch) -> None:
    monkeypatch.setattr(ops, "get_broker", lambda: farm.broker)
    for code in ("101", "102", "103"):
        farm.repo.create(farm_id=FARM, turbine_id="WT001", type=WorkOrderType.CORRECTIVE, title="x",
                         description="", source_alarm_code=code)
    _plan(farm)
    farm.drive_slow(1)
    _jump(farm, DAY)
    farm.drive_slow(1)
    assert _inspections(farm) == []
    due = _schedules(farm)[0].next_due_at
    assert due <= _clock(farm), "上限擋下：不推進"
    view = ops._inspection_plan_view(farm.loop.inspection_plan)
    assert [s["overdue"] for s in view["schedules"]] == [True, False, False], "管理端看得到卡住的"
    for order in farm.orders()[:1]:
        farm.repo.transition(order.id, "cancel", actor_id=PLAN_ACTOR, cancel_reason="測試")
    _jump(farm, 900)
    farm.drive_slow(1)
    assert [o.turbine_id for o in _inspections(farm)] == ["WT001"]


def test_a_restart_does_not_duplicate_schedules_or_orders(farm: Farm) -> None:
    _plan(farm)
    farm.drive_slow(1)
    _jump(farm, DAY)
    farm.drive_slow(1)
    ids = [s.id for s in _schedules(farm)]
    farm.loop.inspection_plan.reset()   # 重啟：記憶體裡的狀態沒了
    farm.loop.rebuild()
    farm.drive_slow(5)
    assert [s.id for s in _schedules(farm)] == ids and len(_inspections(farm)) == 1
    # 還原存檔後從比開單早的時刻接著跑：排程已經推進到下一期，不再開
    farm.loop.inspection_plan.reset()
    assert farm.loop.inspection_plan.step(_clock(farm) - timedelta(minutes=30)) == []
    assert len(_inspections(farm)) == 1


def test_a_person_paused_schedule_stays_paused_until_the_settings_change(farm: Farm) -> None:
    """重啟、批次結束（設定從風場 DB 再套一次）、存了同樣的設定都不算改設定。"""
    farm.broker.storage.set_setting(farm.broker.SETTING_INSPECTION_PLAN, {"enabled": True, "interval_days": 3})
    farm.broker.apply_live_settings()
    farm.drive_slow(1)
    schedules = _schedules(farm)
    get_inspection_repository(str(farm.broker.storage.db_path)).set_active(schedules[1].id, False)
    for again in (farm.loop.inspection_plan.reset, farm.loop.rebuild, farm.broker.apply_live_settings,
                  lambda: _plan(farm)):
        again()
        farm.drive_slow(1)
        assert [s.active for s in _schedules(farm)] == [True, False, True], again
    assert [s.id for s in _schedules(farm)] == [s.id for s in schedules], "不重建"
    _plan(farm, interval_days=4)   # 改了設定：全部依新設定
    farm.drive_slow(1)
    assert [s.active for s in _schedules(farm)] == [True] * 3


def test_a_missing_schedule_is_added_back_without_touching_the_others(farm: Farm) -> None:
    _plan(farm)
    farm.drive_slow(1)
    repository = get_inspection_repository(str(farm.broker.storage.db_path))
    first, second, third = _schedules(farm)
    repository.set_active(second.id, False)
    # 別的 created_by 的排程不算計畫的：例如資料庫被改過、計畫的排程不見了
    with farm.broker.storage._get_conn() as conn:
        conn.execute("UPDATE wmom_inspection_schedules SET created_by = NULL WHERE id = ?", (str(third.id),))
    farm.loop.inspection_plan.reset()
    farm.drive_slow(1)
    after = _schedules(farm)
    assert [s.turbine_id for s in after] == ["WT001", "WT002", "WT003"] and after[2].id != third.id
    assert [s.active for s in after] == [True, False, True]


def test_a_failing_sync_is_retried_later_not_every_step(farm: Farm, monkeypatch) -> None:
    calls: List[int] = []

    def broken(*_args, **_kwargs):
        calls.append(1)
        raise RuntimeError("資料庫壞了")

    _plan(farm)
    monkeypatch.setattr(farm.loop.inspection_plan, "_sync", broken)
    farm.drive_slow(60)   # 10 分鐘
    assert len(calls) == 1
    farm.drive_slow(31)
    assert len(calls) == 2, "15 分鐘後再試"
    monkeypatch.undo()
    _jump(farm, 900)
    farm.drive_slow(1)
    assert len(_schedules(farm)) == 3


def test_an_inspection_a_person_opened_under_the_screen_name_covers_the_period(farm: Farm) -> None:
    _plan(farm)
    farm.drive_slow(1)
    order = farm.repo.create(farm_id=FARM, turbine_id="WTG-01", type=WorkOrderType.INSPECTION, title="人開的",
                             description="")
    _jump(farm, DAY)
    farm.drive_slow(1)
    assert [o.id for o in _inspections(farm)] == [order.id]
    assert _schedules(farm)[0].last_spawned_work_order_id == order.id


# ── 2. 和維修班一起：潛伏的故障被找到 ─────────────────────────────────────


def test_a_latent_fault_is_found_by_the_automatic_inspection(farm: Farm) -> None:
    """變壓器過熱到頂、沒有警報：沒有跳機就沒有工單，只有定檢會修到它。"""
    farm.drive_slow(30)
    farm.inject("transformer_overheat", "WT001", severity=1.0)
    farm.loop.crew.configure(CrewConfig.from_dict({"enabled": True, "response_minutes": 10,
                                                   "inspection_minutes": 15}))
    _plan(farm)
    farm.drive_slow(360)
    assert not any(e["source"] == "plc" for e in farm.broker.storage.query_events("WT001", limit=200)), \
        "測試前提：沒有警報"
    assert farm.faults() == ["transformer_overheat"] and farm.orders() == []
    _jump(farm, DAY)
    farm.drive_slow(1)
    (order,) = _inspections(farm)
    farm.drive_slow(60 + 6 + 90 + 12)   # 反應時間 10 分鐘＋施工 15 分鐘（含 60 秒的檢查間隔）
    assert farm.repo.get(order.id).status is WorkOrderStatus.CLOSED
    assert farm.faults() == [], "定檢完工修掉潛伏的故障"
    (case,) = farm.broker.fault_records.cases()
    assert case["cleared_by"] == f"work_order:{order.business_key}"
    assert farm.until_producing() is not None


# ── 3. 設定 ───────────────────────────────────────────────────────────────


def test_disabling_pauses_and_a_new_interval_restaggers(farm: Farm) -> None:
    _plan(farm)
    farm.drive_slow(1)
    farm.loop.inspection_plan.configure(InspectionPlanConfig())
    farm.drive_slow(1)
    assert [s.active for s in _schedules(farm)] == [False] * 3
    _jump(farm, 5 * DAY)
    farm.drive_slow(1)
    assert _inspections(farm) == [], "暫停的不開單"
    _plan(farm, interval_days=30)
    farm.drive_slow(1)
    now = _clock(farm)
    schedules = _schedules(farm)
    assert [s.active for s in schedules] == [True] * 3 and {s.interval_days for s in schedules} == {30}
    assert [round((s.next_due_at - now).total_seconds() / DAY, 3) for s in schedules] == [10.0, 20.0, 30.0]
    assert "每 30 天" in schedules[0].description
    # 人暫停某一台：設定沒改就留著
    get_inspection_repository(str(farm.broker.storage.db_path)).set_active(schedules[1].id, False)
    farm.drive_slow(200)
    assert [s.active for s in _schedules(farm)] == [True, False, True]


def test_only_the_live_farm_runs_the_plan(farm: Farm) -> None:
    farm.drive_slow(1)
    _plan(farm)
    sim = farm.broker.simulator
    assert sim is not None
    now = _clock(farm)
    sim._bulk_running = True   # 產生情境的批次期間
    assert farm.loop.inspection_plan.step(now) == [] and _schedules(farm) == []
    sim._bulk_running = False
    assert farm.loop.inspection_plan.step(now) == ["WT001:scheduled", "WT002:scheduled", "WT003:scheduled"]
    farm.loop.enabled = False
    farm.loop.inspection_plan.configure(InspectionPlanConfig())
    assert farm.loop.inspection_plan.step(now) == [], "閉環關著：不動排程"


@pytest.mark.parametrize("bad", [{"interval_days": 0}, {"interval_days": 731}, {"interval_days": 1.5},
                                 {"interval_days": True}, {"enabled": "true"}, {"nope": 1}])
def test_bad_settings_are_rejected(bad: dict) -> None:
    with pytest.raises(ValueError):
        InspectionPlanConfig.from_dict(bad)


def test_settings_are_stored_with_the_farm_and_reported(farm: Farm, monkeypatch) -> None:
    monkeypatch.setattr(ops, "get_broker", lambda: farm.broker)
    farm.drive_slow(1)
    body = asyncio.run(ops.set_inspection_plan_settings({"enabled": True, "interval_days": 90}))
    assert body["config"] == {"enabled": True, "interval_days": 90} and body["schedules"] == []
    farm.drive_slow(1)   # 排程由即時模擬的下一批整理
    body = asyncio.run(ops.inspection_plan_settings())
    assert body["clock"] and [s["turbine_id"] for s in body["schedules"]] == ["WT001", "WT002", "WT003"]
    assert set(body["schedules"][0]) == {"turbine_id", "active", "next_due_at", "last_spawned_at",
                                         "last_work_order_id", "overdue"}
    farm.loop.inspection_plan.configure(InspectionPlanConfig())
    farm.broker.apply_live_settings()
    assert farm.loop.inspection_plan.config.interval_days == 90 and farm.loop.inspection_plan.config.enabled
    with pytest.raises(HTTPException) as caught:
        asyncio.run(ops.set_inspection_plan_settings({"interval_days": 0}))
    assert caught.value.status_code == 422
    # 沒存過的風場用啟動時的預設
    farm.broker.storage._get_conn().execute("DELETE FROM farm_settings")
    farm.broker.storage._get_conn().commit()
    farm.broker.default_live_settings = {"inspection_plan": {"enabled": True}}
    farm.broker.apply_live_settings()
    assert farm.loop.inspection_plan.config == InspectionPlanConfig(enabled=True, interval_days=182)


def test_endpoints_are_for_supervisors_only(farm: Farm, monkeypatch) -> None:
    monkeypatch.setattr(ops, "get_broker", lambda: farm.broker)
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)
    app = FastAPI()
    app.include_router(ops.router)
    client = TestClient(app)
    for method in ("get", "put"):
        response = getattr(client, method)("/api/operations/inspection-plan",
                                           **({"json": {}} if method == "put" else {}))
        assert response.status_code in (401, 403), (method, response.status_code)
