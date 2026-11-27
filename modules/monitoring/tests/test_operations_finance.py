"""仿真風場的收支（WMOM-20260504-11，DEC-20261127-02）。

1. 修復等級表涵蓋全部故障情境；費率從成本設定讀。
2. 工單完工 → 帳本的人工與料件；每張工單只寫一次；有領料單時料件不另算；備註不寫故障情境。
3. 收入與少收的錢由運轉狀態紀錄 × 電價；``/api/operations/finance`` 只給主管。
4. 月報的發電收入區塊。
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterator
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.cost.repository.cost_ledger import CostLedgerCategory, CostLedgerSourceType, CostLedgerStatus
from modules.cost.repository.cost_ledger_repository import get_cost_ledger_repository
from modules.cost.services.simulation_costs import (
    FarmRates,
    FixedCosts,
    crane_cost,
    fixed_costs,
    repair_class,
    revenue,
    summarize,
    work_order_cost_entries,
)
from modules.workflow import hooks
from modules.workflow.repository import work_order_repository as wo_repo
from server.routers import operations as ops
from simulator.physics.fault_engine import FAULT_SCENARIOS

from .test_om_loop import FARM, WIRE_BREAK, Farm

RATES = FarmRates(farm_id=FARM, currency="EUR", kwh_price=0.1, hourly_labour_rate=40.0, source="test")
MOMENT = datetime(2026, 11, 27, 6, 0, tzinfo=timezone.utc)


@pytest.fixture
def farm(tmp_path) -> Iterator[Farm]:
    f = Farm(tmp_path, turbines=3)
    try:
        yield f
    finally:
        hooks.clear_work_order_listeners()
        wo_repo.clear_engine_cache_for_test()


def _ledger(farm: Farm):
    return get_cost_ledger_repository(str(farm.broker.storage.db_path))


# ── 1. 表與費率 ───────────────────────────────────────────────────────────


def test_every_fault_scenario_has_a_repair_class() -> None:
    import json

    from modules.cost.services.simulation_costs import REPAIR_CLASSES_PATH

    listed = set(json.loads(REPAIR_CLASSES_PATH.read_text(encoding="utf-8"))["scenarios"])
    assert listed == set(FAULT_SCENARIOS), "新增故障情境要補修復等級（modules/cost/data/z72_repair_classes.json）"
    assert repair_class("bearing_wear").material_cost > repair_class("converter_cooling_pump_wear").material_cost \
        > repair_class("anemometer_fault").material_cost > 0
    assert repair_class("blade_icing").material_cost == 0
    assert repair_class("no_such_fault", "sensor_fault").ftc == 2, "表上沒有的依類別給預設"


def test_farm_rates_come_from_the_cost_settings(farm: Farm) -> None:
    from modules.cost.services.simulation_costs import farm_rates

    k13 = farm_rates("no-such-farm", farm.broker.farm_registry)
    assert (k13.currency, k13.kwh_price, k13.source) == ("EUR", 0.13, "k13_fallback")
    assert k13.hourly_labour_rate == pytest.approx(150000 / 1800), "K13 只給年薪：年薪 ÷ 1800 小時"
    taichung = farm_rates("台中港曲風場", farm.broker.farm_registry)
    assert (taichung.kwh_price, taichung.source) == (0.1, "farm_overlay")
    assert taichung.hourly_labour_rate == pytest.approx(70000 / 1800)


# ── 2. 工單完工 → 帳本 ────────────────────────────────────────────────────


def test_cost_entries_for_a_finished_work_order() -> None:
    order_id = uuid4()
    pump = repair_class("converter_cooling_pump_wear")
    entries = work_order_cost_entries(farm_id=FARM, work_order_id=order_id, business_key="WO-1", actual_hours=4.0,
                                      crew_size=1, repaired=[pump], has_material_requests=False, rates=RATES,
                                      moment=MOMENT)
    by = {e.category: e for e in entries}
    assert set(by) == {CostLedgerCategory.LABOUR, CostLedgerCategory.MATERIAL}
    assert by[CostLedgerCategory.LABOUR].amount == Decimal("480.00"), "4 小時 × 3 人（修復等級的人數）× 40"
    assert by[CostLedgerCategory.MATERIAL].amount == Decimal("5000.00")
    assert all(e.status is CostLedgerStatus.CONFIRMED and e.recorded_at == MOMENT for e in entries)
    assert all(e.source_type is CostLedgerSourceType.WORK_ORDER and e.source_event_id == order_id for e in entries)
    # 只有復位、沒修到東西：至少兩人的人工，沒有料件
    reset_only = work_order_cost_entries(farm_id=FARM, work_order_id=order_id, business_key="WO-2", actual_hours=1.0,
                                         crew_size=None, repaired=[], has_material_requests=False, rates=RATES,
                                         moment=MOMENT)
    assert [(e.category, e.amount) for e in reset_only] == [(CostLedgerCategory.LABOUR, Decimal("80.00"))]
    # 有領料單：料件已由領料出庫入帳
    with_requests = work_order_cost_entries(farm_id=FARM, work_order_id=order_id, business_key="WO-3",
                                            actual_hours=None, crew_size=2, repaired=[pump],
                                            has_material_requests=True, rates=RATES, moment=MOMENT)
    assert with_requests == []


def test_finishing_a_work_order_posts_its_costs_once(farm: Farm) -> None:
    farm.drive(300)
    farm.inject(WIRE_BREAK)
    farm.drive(60)
    (order,) = farm.orders()
    farm.start(order)
    farm.drive(5)
    farm.finish(order)
    assert farm.faults() == []
    entries = _ledger(farm).list_for_subject(order.id, CostLedgerSourceType.WORK_ORDER)
    by = {e.category: e for e in entries}
    assert set(by) == {CostLedgerCategory.LABOUR, CostLedgerCategory.MATERIAL}
    assert by[CostLedgerCategory.MATERIAL].amount == Decimal("500.00"), "量測回路斷線：修復等級 2（耗材）"
    assert by[CostLedgerCategory.LABOUR].amount == Decimal(str(round(2.0 * 3 * 150000 / 1800, 2)))
    clock = farm.broker.live_clock()
    assert all(e.recorded_at == clock for e in entries), "入帳時間用風場時鐘（和收入同一個時間基準）"
    for entry in entries:
        assert WIRE_BREAK not in (entry.note or "") and "wire" not in (entry.note or "").lower()
    # 再呼叫一次完工的處理：不重寫
    farm.loop._post_costs(farm.repo.get(order.id), [WIRE_BREAK])
    assert len(_ledger(farm).list_for_subject(order.id, CostLedgerSourceType.WORK_ORDER)) == len(entries)


def test_material_is_skipped_only_when_a_material_request_has_posted(farm: Farm, monkeypatch) -> None:
    """領料單出庫時已寫過料件的才不另算；草稿、退回、取消的領料單沒有入帳，料件照算（code review）。"""
    from types import SimpleNamespace

    import modules.workflow.repository.material_request_repository as mr_repo
    from modules.cost.repository.cost_ledger import CostLedgerEntry, insert_in_session

    request = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(mr_repo, "get_material_request_repository",
                        lambda _path: SimpleNamespace(list_for_work_order=lambda _wo: [request]))
    farm.drive(300)
    farm.inject(WIRE_BREAK)
    farm.drive(60)
    (order,) = farm.orders()
    farm.start(order)
    farm.finish(order)
    categories = {e.category for e in _ledger(farm).list_for_subject(order.id, CostLedgerSourceType.WORK_ORDER)}
    assert CostLedgerCategory.MATERIAL in categories, "領料單還沒出庫：料件照算"

    ledger = _ledger(farm)
    with ledger._sessionmaker() as sess, sess.begin():
        insert_in_session(sess, CostLedgerEntry(
            farm_id=FARM, category=CostLedgerCategory.MATERIAL, amount=Decimal("123"),
            source_event_id=request.id, source_type=CostLedgerSourceType.MATERIAL_REQUEST))
    entries = []
    from modules.cost.services import simulation_costs as costs
    monkeypatch.setattr(costs, "work_order_cost_entries",
                        lambda **kwargs: entries.append(kwargs["has_material_requests"]) or [])
    farm.loop._post_costs(farm.repo.get(order.id), [WIRE_BREAK])
    assert entries == [True], "領料單已經入帳：料件不另算"


def test_a_ledger_failure_does_not_break_the_finish(farm: Farm, monkeypatch) -> None:
    import modules.cost.services.simulation_costs as costs

    farm.drive(300)
    farm.inject(WIRE_BREAK)
    farm.drive(60)
    (order,) = farm.orders()
    farm.start(order)

    def boom(*_args, **_kwargs):
        raise RuntimeError("ledger down")

    monkeypatch.setattr(costs, "farm_rates", boom)
    farm.finish(order)
    assert farm.faults() == [], "帳本寫不進去，完工照樣修好"


# ── 3. 收入與端點 ─────────────────────────────────────────────────────────


def test_revenue_and_summary() -> None:
    farm_row = {"energy_kwh": 10000.0, "lost_planned_kwh": 200.0, "lost_unplanned_kwh": 1000.0}
    assert revenue(farm_row, RATES) == {"revenue": 1000.0, "lost_planned": 20.0, "lost_unplanned": 100.0}
    expenses = {CostLedgerCategory.LABOUR: Decimal("300"), CostLedgerCategory.MATERIAL: Decimal("500"),
                CostLedgerCategory.REVENUE_LOSS: Decimal("999")}
    out = summarize({"farm": farm_row, "turbines": [{"turbine_id": "WT001", **farm_row}]}, expenses, RATES)
    assert out["expenses"]["total"] == 800.0, "帳本的 revenue_loss 不算支出（少收的錢由運轉狀態紀錄算）"
    assert out["net"] == 200.0 and out["lost_revenue"] == {"planned": 20.0, "unplanned": 100.0}
    assert out["turbines"][0]["revenue"] == 1000.0


def test_finance_endpoint(farm: Farm, monkeypatch) -> None:
    monkeypatch.setattr(ops, "get_broker", lambda: farm.broker)
    farm.drive_slow(60)          # 10 分鐘的運轉狀態紀錄
    farm.inject(WIRE_BREAK)
    farm.drive(60)
    (order,) = farm.orders()
    farm.start(order)
    farm.finish(order)
    clock = farm.broker.live_clock()
    result = asyncio.run(ops.finance(start=(clock - timedelta(days=1)).isoformat(),
                                     end=(clock + timedelta(hours=1)).isoformat()))
    availability = farm.loop.availability(clock - timedelta(days=1), clock + timedelta(hours=1))["farm"]
    assert result["energy_kwh"] == pytest.approx(availability["energy_kwh"], abs=0.1) and result["energy_kwh"] > 0
    assert result["revenue"] == pytest.approx(availability["energy_kwh"] * 0.13, abs=0.01)
    assert result["expenses"]["material"] == 500.0 and result["expenses"]["labour"] > 0
    assert result["net"] == pytest.approx(result["revenue"] - result["expenses"]["total"], abs=0.01)
    assert {row["turbine_id"] for row in result["turbines"]} == {"WT001", "WT002", "WT003"}
    with pytest.raises(Exception):
        asyncio.run(ops.finance(start=clock.isoformat(), end=(clock - timedelta(hours=1)).isoformat()))


def test_finance_is_for_supervisors_only_even_without_enforced_login(farm: Farm, monkeypatch) -> None:
    monkeypatch.setattr(ops, "get_broker", lambda: farm.broker)
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)
    app = FastAPI()
    app.include_router(ops.router)
    assert TestClient(app).get("/api/operations/finance").status_code in (401, 403)


# ── 4. 月報 ───────────────────────────────────────────────────────────────


def test_monthly_report_shows_generation_revenue(farm: Farm) -> None:
    from modules.reporting.services.kpi_calculator import compute_monthly_report_data
    from modules.reporting.services.monthly_report import render_html

    farm.drive_slow(60)
    farm.inject(WIRE_BREAK)
    farm.drive(60)
    (order,) = farm.orders()
    farm.start(order)
    farm.finish(order)
    clock = farm.broker.live_clock()

    def provider(farm_id, start, end):
        row = farm.loop.availability(start, end)["farm"]
        return {"currency": "EUR", "kwh_price": 0.13, "energy_kwh": row["energy_kwh"], **revenue(
            row, FarmRates(farm_id=farm_id, currency="EUR", kwh_price=0.13, hourly_labour_rate=1.0, source="t"))}

    data = compute_monthly_report_data(ledger_repo=_ledger(farm), wo_repo=farm.repo, farm_id=FARM,
                                       year=clock.year, month=clock.month, revenue_provider=provider)
    generation = data.generation
    assert generation is not None and generation.revenue > 0
    assert generation.operating_expense > 500, "這張工單的料件 500 ＋ 人工"
    assert generation.net == pytest.approx(generation.revenue - generation.operating_expense, abs=0.01)
    assert "發電收入與淨額" in render_html(data)
    without = compute_monthly_report_data(ledger_repo=_ledger(farm), wo_repo=farm.repo, farm_id=FARM,
                                          year=clock.year, month=clock.month)
    assert without.generation is None and "發電收入與淨額" not in render_html(without)



# ── 5. 設備與固定成本（WMOM-20261127-02）─────────────────────────────────


def test_major_repairs_are_charged_a_crane_once_per_work_order() -> None:
    crane = crane_cost()
    assert crane.per_job() == 40000 + 12000 * 2 and {8, 11} <= crane.ftc
    bearing, stator, pump = (repair_class("bearing_wear"), repair_class("stator_winding_degradation"),
                             repair_class("converter_cooling_pump_wear"))
    entries = work_order_cost_entries(farm_id=FARM, work_order_id=uuid4(), business_key="WO-9", actual_hours=24.0,
                                      crew_size=4, repaired=[bearing, stator], has_material_requests=True,
                                      rates=RATES, moment=MOMENT)
    (lift,) = [e for e in entries if e.category is CostLedgerCategory.EQUIPMENT]
    assert lift.amount == Decimal("64000.00") and "吊車" in lift.note and "8、11" in lift.note, "兩個大件只動員一次"
    small = work_order_cost_entries(farm_id=FARM, work_order_id=uuid4(), business_key="WO-10", actual_hours=4.0,
                                    crew_size=2, repaired=[pump], has_material_requests=False, rates=RATES,
                                    moment=MOMENT)
    assert not any(e.category is CostLedgerCategory.EQUIPMENT for e in small), "小件不用吊車"


def test_fixed_costs_use_onshore_defaults_or_the_farm_settings(farm: Farm) -> None:
    from modules.cost.services.simulation_costs import farm_rates

    onshore = fixed_costs("no-such-farm", 14, farm.broker.farm_registry)
    assert (onshore.technicians, onshore.yearly_salary, onshore.source) == (5, 60000.0, "onshore_default")
    assert onshore.staff_per_year == 300000 and onshore.equipment_per_year == 50000
    assert fixed_costs("no-such-farm", 3, farm.broker.farm_registry).technicians == 4, "至少 4 人"
    taichung = fixed_costs("台中港曲風場", 14, farm.broker.farm_registry)
    assert (taichung.technicians, taichung.yearly_salary, taichung.source) == (8, 70000.0, "farm_overlay")
    # 監控登錄的風場（仿真的 Z72 陸域）沒有自己的成本設定：時薪也用陸域的年薪，不用 K13 離岸的 15 萬
    farm.broker.farm_registry.create_farm("sim-farm", "仿真風場", turbine_count=14)
    derived = farm_rates("sim-farm", farm.broker.farm_registry)
    assert derived.source == "registry_derived" and derived.hourly_labour_rate == pytest.approx(60000 / 1800)


def test_fixed_costs_are_spread_over_the_recorded_days_and_work_order_labour_is_not_counted_twice() -> None:
    fixed = FixedCosts(technicians=4, yearly_salary=36500.0, equipment=(("工程車", 3650.0),), source="test")
    farm_row = {"energy_kwh": 10000.0, "lost_planned_kwh": 0.0, "lost_unplanned_kwh": 0.0, "recorded_hours": 48.0}
    availability = {"farm": farm_row, "turbines": [{"turbine_id": "WT001"}, {"turbine_id": "WT002"}]}
    expenses = {CostLedgerCategory.LABOUR: Decimal("300"), CostLedgerCategory.MATERIAL: Decimal("500"),
                CostLedgerCategory.EQUIPMENT: Decimal("64000")}
    out = summarize(availability, expenses, RATES, fixed=fixed, work_order_labour=Decimal("300"))
    assert out["fixed_costs"]["days"] == 1.0, "兩台機組 48 機組小時＝1 天"
    assert out["fixed_costs"]["staff"] == 400.0 and out["fixed_costs"]["equipment"] == 10.0
    assert out["expenses"] == {"material": 500.0, "labour": 400.0, "equipment": 64010.0, "total": 64910.0}
    assert out["work_order_labour"] == {"amount": 300.0, "counted": False}
    assert out["net"] == round(1000.0 - 64910.0, 2)
    # 手動記的人工（例：外包）照算：只扣工單的那部分
    with_contractor = summarize(availability, {**expenses, CostLedgerCategory.LABOUR: Decimal("1300")}, RATES,
                                fixed=fixed, work_order_labour=Decimal("300"))
    assert with_contractor["expenses"]["labour"] == 1400.0
    # 沒給固定成本：照舊（工單人工算進去）
    plain = summarize(availability, expenses, RATES)
    assert plain["fixed_costs"] is None and plain["work_order_labour"]["counted"] is True
    assert plain["expenses"]["labour"] == 300.0


def test_finance_endpoint_includes_fixed_costs_and_the_crane(farm: Farm, monkeypatch) -> None:
    from modules.workflow.domain import WorkOrderType

    monkeypatch.setattr(ops, "get_broker", lambda: farm.broker)
    farm.drive_slow(60)
    farm.inject("bearing_wear", "WT002", severity=0.3)
    order = farm.repo.create(farm_id=FARM, turbine_id="WT002", type=WorkOrderType.CORRECTIVE, title="x",
                             description="", source_alarm_code="240")
    farm.start(order)
    farm.drive(5)
    farm.finish(order)
    assert farm.faults("WT002") == []
    entries = {e.category: e for e in _ledger(farm).list_for_subject(order.id, CostLedgerSourceType.WORK_ORDER)}
    assert entries[CostLedgerCategory.EQUIPMENT].amount == Decimal("64000.00"), "主軸承：吊車動員"
    clock = farm.broker.live_clock()
    result = asyncio.run(ops.finance(start=(clock - timedelta(days=1)).isoformat(),
                                     end=(clock + timedelta(hours=1)).isoformat()))
    fixed = result["fixed_costs"]
    assert fixed["technicians"] == 4 and fixed["days"] > 0 and fixed["source"] == "onshore_default"
    assert result["work_order_labour"]["amount"] > 0 and result["work_order_labour"]["counted"] is False
    assert result["expenses"]["labour"] == pytest.approx(fixed["staff"], abs=0.01), "工單工時已含在年薪裡"
    assert result["expenses"]["equipment"] == pytest.approx(64000 + fixed["equipment"], abs=0.01)
    assert result["net"] == pytest.approx(result["revenue"] - result["expenses"]["total"], abs=0.01)


def test_monthly_report_counts_fixed_costs_instead_of_work_order_labour(farm: Farm) -> None:
    from modules.reporting.services.kpi_calculator import compute_monthly_report_data
    from modules.reporting.services.monthly_report import render_html

    farm.drive_slow(60)
    farm.inject(WIRE_BREAK)
    farm.drive(60)
    (order,) = farm.orders()
    farm.start(order)
    farm.finish(order)
    clock = farm.broker.live_clock()
    labour = float(_ledger(farm).summary_by_category(
        farm_id=FARM, source_type=CostLedgerSourceType.WORK_ORDER)[CostLedgerCategory.LABOUR])

    def provider(farm_id, start, end):
        row = farm.loop.availability(start, end)["farm"]
        return {"currency": "EUR", "kwh_price": 0.13, "energy_kwh": row["energy_kwh"], **revenue(
            row, FarmRates(farm_id=farm_id, currency="EUR", kwh_price=0.13, hourly_labour_rate=1.0, source="t")),
            "fixed_costs": 1234.5, "work_order_labour": labour}

    data = compute_monthly_report_data(ledger_repo=_ledger(farm), wo_repo=farm.repo, farm_id=FARM,
                                       year=clock.year, month=clock.month, revenue_provider=provider)
    generation = data.generation
    assert generation is not None and generation.fixed_costs == 1234.5
    assert generation.operating_expense == pytest.approx(500 + 1234.5, abs=0.01), "料件 500 ＋ 固定成本，工單人工不另算"
    assert "其中固定成本" in render_html(data)


def test_the_report_provider_of_the_server_includes_fixed_costs(farm: Farm, monkeypatch) -> None:
    from server import app as server_app

    monkeypatch.setattr(server_app, "broker", farm.broker)
    farm.drive_slow(60)
    farm.inject(WIRE_BREAK)
    farm.drive(60)
    (order,) = farm.orders()
    farm.start(order)
    farm.finish(order)
    clock = farm.broker.live_clock()
    out = server_app._revenue_for_report(FARM, clock - timedelta(days=1), clock + timedelta(hours=1))
    assert out is not None and out["revenue"] > 0
    assert out["fixed_costs"] > 0 and out["work_order_labour"] > 0
    assert server_app._revenue_for_report("other-farm", clock - timedelta(days=1), clock) is None
