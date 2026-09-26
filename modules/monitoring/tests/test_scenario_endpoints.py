"""情境保存/調閱：orchestration / endpoint 層（WMOM-20260719-02，code review 補強）。

storage 層由 ``test_scenario_persistence.py`` 覆蓋；本檔補 `config.generate-bulk` 的情境收尾
與 `scenarios` router 的實際程式路徑——兩個 code review Must-fix 都活在這層：
1. offset=0 的排定故障事件必須落在情境時間窗內（可被調閱撈到）。
2. 生成中途失敗，情境 session 必須被收尾（不得卡未結束、被 get_active_session 誤認成 Live）。

以最小 fake broker 直呼 async endpoint（繞過 HTTP/auth——Must-fix 在 business logic、不在 gate）。
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, List, Optional

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

from server.storage import Storage  # noqa: E402
from simulator.engine import WindFarmSimulator  # noqa: E402
from server.routers import config as config_ep  # noqa: E402
from server.routers import faults as faults_ep  # noqa: E402
from server.routers import scenarios as scenarios_ep  # noqa: E402


class _FakeBroker:
    """只實作 endpoint 用到的表面（storage / simulator / session / 事件與歷史委派）。"""

    def __init__(self, storage: Storage, simulator: WindFarmSimulator, session_id: int):
        self.storage = storage
        self.simulator = simulator
        self._session_id = session_id

    @contextmanager
    def pause_live_for_batch(self) -> Iterator[bool]:
        """對齊真 DataBroker：批次期間暫停 Live（實呼引擎的 stop/restore）。本 fake 的 sim 從未
        start() 故無 thread → 等同 no-op pass-through，但仍走過真正的退場/恢復程式路徑。"""
        was_running = self.simulator.stop_live_loop()
        try:
            yield was_running
        finally:
            self.simulator.restore_live_loop(was_running, 1.0)

    def record_event(self, **kwargs) -> None:
        self.storage.record_event(**kwargs)

    def get_history(self, turbine_id: str, start: Optional[str] = None,
                    end: Optional[str] = None, limit: int = 1000,
                    session_id: Optional[int] = None) -> List[dict]:
        return self.storage.query_history(turbine_id, start, end, limit, session_id=session_id)

    def get_history_events(self, turbine_id: Optional[str] = None, start: Optional[str] = None,
                           end: Optional[str] = None, limit: int = 500) -> List[dict]:
        return self.storage.query_events(turbine_id, start, end, limit)


@pytest.fixture
def broker(tmp_path, monkeypatch):
    storage = Storage(db_path=str(tmp_path / "ep.db"))
    sim = WindFarmSimulator(turbine_count=3)
    sim._running = True
    live_sid = storage.create_session(data_source="simulation", turbine_count=3)
    b = _FakeBroker(storage, sim, live_sid)
    monkeypatch.setattr(config_ep, "get_broker", lambda: b)
    monkeypatch.setattr(scenarios_ep, "get_broker", lambda: b)
    return b


def test_generate_bulk_saves_scenario_with_offset0_event_in_window(broker):
    """Must-fix #2：offset=0 注入的故障事件應落在情境時間窗內、可被調閱撈到。"""
    res = asyncio.run(config_ep.generate_bulk({
        "duration_hours": 0.02, "time_step": 10.0, "name": "情境A", "wind_profile": "moderate",
        "fault_schedule": [{"scenario_id": "hydraulic_leak", "turbine_id": "WT002",
                            "offset_seconds": 0}],
    }))
    sid = res["scenario_id"]
    assert sid is not None and res["faults_injected"] == 1

    hist = asyncio.run(scenarios_ep.get_scenario_turbine_history(sid, "WT002", 2000))
    assert len(hist["readings"]) > 0, "情境資料應可調閱"
    assert hist["events_by_time_window"] is True, "應標明 events 走時間窗、非 session 隔離"
    fault_events = [e for e in hist["events"] if e.get("event_type") == "fault"]
    assert fault_events, "offset=0 的故障事件應落在情境時間窗內、被調閱撈到（Must-fix #2）"


def test_generate_bulk_isolates_scenario_from_live_and_ends_it(broker):
    """情境資料寫專屬 session、不融進 Live；情境結束後 active 仍是 Live。"""
    res = asyncio.run(config_ep.generate_bulk({
        "duration_hours": 0.02, "time_step": 10.0, "name": "情境B"}))
    sid = res["scenario_id"]

    assert len(broker.storage.query_history("WT001", session_id=sid)) > 0
    assert broker.storage.query_history("WT001", session_id=broker._session_id) == [], \
        "情境資料不得寫進 Live session"

    active = broker.storage.get_active_session()
    assert active is not None and active["id"] == broker._session_id, "情境已 end → active 仍是 Live"


def test_generate_bulk_failure_finalizes_scenario_session(broker, monkeypatch):
    """Must-fix #1：生成中途失敗，情境 session 必須被收尾（ended + status=error），
    不得卡未結束、被 get_active_session 誤認成 Live。"""
    def boom(*args, **kwargs):
        raise RuntimeError("physics diverged mid-scenario")

    monkeypatch.setattr(broker.simulator, "generate_bulk", boom)

    with pytest.raises(RuntimeError):
        asyncio.run(config_ep.generate_bulk({
            "duration_hours": 0.02, "time_step": 10.0, "name": "壞情境"}))

    failed = [s for s in broker.storage.list_scenarios() if s["config"]["name"] == "壞情境"]
    assert failed, "失敗的情境 session 仍應存在（可追溯）"
    assert failed[0]["ended_at"] is not None, "失敗情境必須被 end_session（Must-fix #1）"
    assert failed[0]["config"].get("status") == "error", "失敗情境應標記 status=error"

    # 防禦：get_active_session 不得回情境（Should-fix #1）
    active = broker.storage.get_active_session()
    assert active is not None and active["id"] == broker._session_id
    assert active.get("config", {}).get("kind") != "scenario"


def test_generate_bulk_without_name_writes_to_live(broker):
    """回歸：不帶 name 沿用舊行為（寫 Live session、不建情境）。"""
    res = asyncio.run(config_ep.generate_bulk({"duration_hours": 0.02, "time_step": 10.0}))
    assert res["scenario_id"] is None
    assert broker.storage.list_scenarios() == []
    assert len(broker.storage.query_history("WT001", session_id=broker._session_id)) > 0


def test_run_test_plan_stops_live_thread_during_batch_and_restores(tmp_path, monkeypatch):
    """Must-fix（姊妹端點）：faults.py::run_test_plan 與 generate-bulk 同模式，也必須在批次期間
    停 Live thread（避免併發 writer 撞 DB-lock）、事後恢復。用**真 thread** 守住——若哪天 run_test_plan
    的 pause_live_for_batch 包裹被拿掉，此測試會轉紅（mutation test 已證原本無任何測試會抓到）。"""
    from server.routers.faults import TEST_PLANS

    storage = Storage(db_path=str(tmp_path / "rtp.db"))
    sim = WindFarmSimulator(turbine_count=3)
    sim.start(time_step=0.02)  # 真的起 Live 背景 thread
    sid = storage.create_session(data_source="simulation", turbine_count=3)
    b = _FakeBroker(storage, sim, sid)
    monkeypatch.setattr(faults_ep, "get_broker", lambda: b)

    seen: dict = {}
    # spy：於 generate_bulk 被呼叫的當下（即 pause context 內）記錄 Live thread 是否已停。
    # 回傳 0 不真的生成，加速（本測試只驗證 pause 包裹，非生成內容）。
    def spy(*args, **kwargs):
        seen["alive_inside"] = sim._thread.is_alive()
        return 0

    monkeypatch.setattr(sim, "generate_bulk", spy)

    try:
        plan_id = next(iter(TEST_PLANS))  # 任一內建 plan
        asyncio.run(faults_ep.run_test_plan(plan_id, {"time_step": 60.0}))
        assert seen.get("alive_inside") is False, "批次進行時 Live thread 必須已停（無並行 writer）"
        assert sim.is_running and sim._thread.is_alive(), "run_test_plan 後 Live 應恢復（新 thread）"
    finally:
        sim.stop()


# ─── 情境摘要端點 A0（DEC-20260720-02 / WMOM-20260720-09）─────────────────────

def test_scenario_summary_endpoint_reports_per_turbine_and_farm(broker):
    """端點整合：以 generate_bulk 建真情境（真物理）→ get_scenario_summary → 驗回傳結構、
    每台機組指標合理（樣本>0、max≥avg、生產佔比∈[0,1]、RUL/DEL 型別正確）、風場 rollup 與各機組一致。

    RUL/DEL 的「取末列而非 MIN/MAX」語意由 storage 層合成資料測（deterministic）精確守住；此整合測
    只驗端點把真情境正確接起來（欄位存在、型別對、rollup 自洽），不依賴不確定的物理數值。"""
    res = asyncio.run(config_ep.generate_bulk({
        "duration_hours": 0.05, "time_step": 10.0, "name": "摘要情境", "wind_profile": "moderate",
    }))
    sid = res["scenario_id"]
    # Should-fix：generate_bulk 應把機型額定功率釘進情境 session（預設 Z72 spec 2000 kW）。
    assert broker.storage.get_scenario(sid)["rated_power_kw"] == pytest.approx(2000.0)

    summary = asyncio.run(scenarios_ep.get_scenario_summary(sid))
    assert summary.scenarioId == sid
    assert summary.name == "摘要情境"
    assert summary.status == "ok"
    assert summary.timeStepSeconds == 10.0
    assert summary.ratedPowerKw == 2000.0          # 由 session 帶出（generate_bulk 釘入）
    assert summary.eventsByTimeWindow is True
    assert len(summary.turbines) == 3
    for t in summary.turbines:
        assert t.samples > 0
        assert t.maxPowerKw >= t.avgPowerKw        # rounding 單調 → 恆成立
        assert 0.0 <= t.capacityFactor
        assert 0.0 <= t.productionRate <= 1.0
        assert t.estopSteps >= 0
        assert t.rulHours is None or isinstance(t.rulHours, float)
        assert t.damageEquivalentLoad.towerFa is None or isinstance(
            t.damageEquivalentLoad.towerFa, float)

    # 風場 rollup 與各機組一致
    assert summary.farm.turbineCount == 3
    assert summary.farm.totalEnergyKwh == pytest.approx(
        round(sum(t.energyKwh for t in summary.turbines), 2))
    assert summary.farm.totalFaultEvents == sum(t.faultEvents for t in summary.turbines)
    assert summary.farm.maxTurbinePowerKw == pytest.approx(
        round(max(t.maxPowerKw for t in summary.turbines), 2))


def test_scenario_summary_404_for_unknown_scenario(broker):
    """未知情境 id → 404（比照 get_scenario）。"""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        asyncio.run(scenarios_ep.get_scenario_summary(999_999))
    assert ei.value.status_code == 404


# ─── 純函式聚合換算（mutation-verify 商業數學，不經 DB/HTTP）───────────────────

def _agg(turbine_id: str, n: int, avg_mw: float, max_mw: float, production_steps: int,
         rul: float, worst_dmg_edge: float, estop: int = 0) -> dict:
    """給純函式測的最小聚合列（dmg_blade_edge 設成最大部位以驗 worstDamage；rul/del 已是末值）。"""
    return {
        "turbine_id": turbine_id, "n": n, "avg_power_mw": avg_mw, "max_power_mw": max_mw,
        "rul_hours": rul, "prod_hours": 1.5,
        "dmg_tower_fa": 0.001, "dmg_tower_ss": 0.002,
        "dmg_blade_flap": 0.003, "dmg_blade_edge": worst_dmg_edge,
        "max_tower_fa_moment": 500.0, "max_tower_ss_moment": 550.0,
        "max_blade_flap_moment": 600.0, "max_blade_edge_moment": 650.0,
        "del_tower_fa": 100.0, "del_tower_ss": 110.0,
        "del_blade_flap": 120.0, "del_blade_edge": 130.0,
        "production_steps": production_steps, "estop_steps": estop,
    }


def test_build_turbine_summary_math():
    """換算數學：MW×1000＝kW、能量＝平均功率×總時數、容量因數＝平均/額定、生產佔比＝生產步數/樣本、
    worstDamage＝四部位取最大、estopSteps/rulHours 帶出。mutation：任一公式改壞即轉紅。"""
    s = scenarios_ep._build_turbine_summary(
        _agg("WT001", n=360, avg_mw=1.8, max_mw=2.0, production_steps=300,
             rul=12345.6, worst_dmg_edge=0.004, estop=5),
        time_step_s=10.0, rated_power_kw=2000.0, fault_events=2,
    )
    assert s.turbineId == "WT001"
    assert s.samples == 360
    assert s.avgPowerKw == 1800.0                       # 1.8 MW ×1000
    assert s.maxPowerKw == 2000.0
    # 總時數 = 360×10/3600 = 1.0 h → 能量 = 1800 kW × 1.0 h = 1800 kWh
    assert s.energyKwh == 1800.0
    assert s.capacityFactor == 0.9                      # 1800/2000
    assert s.productionRate == round(300 / 360, 4)      # 0.8333
    assert s.estopSteps == 5
    assert s.worstDamage == pytest.approx(0.004)        # max(0.001,0.002,0.003,0.004)
    assert s.rulHours == pytest.approx(12345.6)
    assert s.faultEvents == 2
    assert s.cumulativeDamage.bladeEdge == pytest.approx(0.004)
    assert s.extremeLoad.bladeEdge == pytest.approx(650.0)
    assert s.damageEquivalentLoad.towerFa == pytest.approx(100.0)


def test_build_turbine_summary_handles_zero_samples_and_missing_physics():
    """空/缺值防護：n=0 不除零（能量/生產佔比=0）；缺物理鍵 → None（不炸）。"""
    s = scenarios_ep._build_turbine_summary(
        {"turbine_id": "WT009", "n": 0, "avg_power_mw": None, "max_power_mw": None,
         "production_steps": 0},
        time_step_s=10.0, rated_power_kw=2000.0, fault_events=0,
    )
    assert s.samples == 0 and s.energyKwh == 0.0 and s.productionRate == 0.0
    assert s.avgPowerKw == 0.0 and s.capacityFactor == 0.0
    assert s.estopSteps == 0
    assert s.worstDamage is None and s.rulHours is None
    assert s.cumulativeDamage.towerFa is None


def test_build_farm_summary_rolls_up_and_picks_worst():
    """風場 rollup：總能量 Σ、平均容量因數/生產佔比、故障數 Σ、最嚴重損傷/最小 RUL 取極值並附機組 id。"""
    t1 = scenarios_ep._build_turbine_summary(
        _agg("WT001", 360, 1.8, 2.0, 360, rul=1000.0, worst_dmg_edge=0.004),
        10.0, 2000.0, fault_events=1)
    t2 = scenarios_ep._build_turbine_summary(
        _agg("WT002", 360, 0.9, 1.0, 180, rul=500.0, worst_dmg_edge=0.010),
        10.0, 2000.0, fault_events=3)

    farm = scenarios_ep._build_farm_summary([t1, t2], turbine_count=2)
    assert farm.turbineCount == 2
    assert farm.totalEnergyKwh == pytest.approx(round(t1.energyKwh + t2.energyKwh, 2))
    assert farm.avgCapacityFactor == round((t1.capacityFactor + t2.capacityFactor) / 2, 4)
    assert farm.avgProductionRate == round((t1.productionRate + t2.productionRate) / 2, 4)
    assert farm.totalFaultEvents == 4
    assert farm.maxTurbinePowerKw == pytest.approx(2000.0)
    assert farm.worstDamage == pytest.approx(0.010) and farm.worstDamageTurbineId == "WT002"
    assert farm.minRulHours == pytest.approx(500.0) and farm.minRulTurbineId == "WT002"


def test_build_farm_summary_empty_turbines():
    """無機組資料 → 全 0、極值欄位 None（不炸）。"""
    farm = scenarios_ep._build_farm_summary([], turbine_count=5)
    assert farm.turbineCount == 5 and farm.totalEnergyKwh == 0.0
    assert farm.worstDamage is None and farm.minRulTurbineId is None


# ─── 跨情境比較端點 A2 Part 1（DEC-20260720-02 / WMOM-20260922-03）───────────────

def test_compare_scenarios_returns_summaries_in_requested_order(broker):
    """整合：建 2 個真情境 → compare_scenarios 依請求 ids 順序並排回傳兩份摘要。"""
    res_a = asyncio.run(config_ep.generate_bulk({
        "duration_hours": 0.02, "time_step": 10.0, "name": "比較情境A"}))
    res_b = asyncio.run(config_ep.generate_bulk({
        "duration_hours": 0.02, "time_step": 10.0, "name": "比較情境B"}))
    sid_a, sid_b = res_a["scenario_id"], res_b["scenario_id"]

    result = asyncio.run(scenarios_ep.compare_scenarios(f"{sid_b},{sid_a}"))
    assert [s.scenarioId for s in result.scenarios] == [sid_b, sid_a]
    assert [s.name for s in result.scenarios] == ["比較情境B", "比較情境A"]
    for s in result.scenarios:
        assert len(s.turbines) == 3


def test_compare_scenarios_dedupes_repeated_ids(broker):
    """重複的 id 只回傳一次，保留首次出現的位置。"""
    res_a = asyncio.run(config_ep.generate_bulk({
        "duration_hours": 0.02, "time_step": 10.0, "name": "去重情境A"}))
    res_b = asyncio.run(config_ep.generate_bulk({
        "duration_hours": 0.02, "time_step": 10.0, "name": "去重情境B"}))
    sid_a, sid_b = res_a["scenario_id"], res_b["scenario_id"]

    result = asyncio.run(scenarios_ep.compare_scenarios(f"{sid_a},{sid_b},{sid_a}"))
    assert [s.scenarioId for s in result.scenarios] == [sid_a, sid_b]


def test_compare_scenarios_404_for_unknown_id_among_valid(broker):
    """混入不存在的 id → 404（比照單情境摘要端點的行為，不靜默略過壞 id）。"""
    from fastapi import HTTPException

    res_a = asyncio.run(config_ep.generate_bulk({
        "duration_hours": 0.02, "time_step": 10.0, "name": "含壞 id 的情境"}))
    sid_a = res_a["scenario_id"]

    with pytest.raises(HTTPException) as ei:
        asyncio.run(scenarios_ep.compare_scenarios(f"{sid_a},999999"))
    assert ei.value.status_code == 404


def test_parse_compare_ids_dedupes_and_preserves_order():
    """純函式：逗號分隔字串解析、去重、保留首次出現順序、忽略空白/空段落。"""
    assert scenarios_ep._parse_compare_ids(" 3, 7,3 , 12") == [3, 7, 12]


def test_parse_compare_ids_rejects_non_integer():
    """純函式：含非整數段落 → 400。"""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        scenarios_ep._parse_compare_ids("1,abc")
    assert ei.value.status_code == 400


def test_parse_compare_ids_rejects_too_few():
    """純函式：去重後不足 2 個（含只給 1 個、或給 2 個但其中重複）→ 400。"""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        scenarios_ep._parse_compare_ids("5")
    assert ei.value.status_code == 400

    with pytest.raises(HTTPException):
        scenarios_ep._parse_compare_ids("5,5")


def test_parse_compare_ids_rejects_too_many():
    """純函式：去重後超過上限（5）→ 400；恰好等於上限則放行（邊界）。"""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        scenarios_ep._parse_compare_ids("1,2,3,4,5,6")
    assert ei.value.status_code == 400

    assert scenarios_ep._parse_compare_ids("1,2,3,4,5") == [1, 2, 3, 4, 5]


def test_compare_route_is_reachable_over_real_http_routing(tmp_path, monkeypatch):
    """路由順序守門：直呼 ``compare_scenarios()``（上方測試）繞過了 FastAPI 實際的路由匹配，
    不會抓到「``/compare`` 註冊在 ``/{scenario_id}`` 之後 → 被攔截、因無法解析成 int 而 422」
    這類路由順序 bug（compare_scenarios docstring 的路由順序注意事項）。本測試掛真 ``router``
    到最小 app、真的打 HTTP GET ``/api/scenarios/compare``，確認它落地在 compare_scenarios、
    不是被 ``/{scenario_id}`` 攔截。

    mutation-verify：若把本檔 router 內 ``/compare`` 路由搬到 ``/{scenario_id}`` 之後（重現當初
    差點犯的錯），本測試會從 200 轉成 422（scenario_id="compare" 無法轉 int）。
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    storage = Storage(db_path=str(tmp_path / "http.db"))
    sim = WindFarmSimulator(turbine_count=2)
    sim._running = True
    live_sid = storage.create_session(data_source="simulation", turbine_count=2)
    b = _FakeBroker(storage, sim, live_sid)
    monkeypatch.setattr(config_ep, "get_broker", lambda: b)
    monkeypatch.setattr(scenarios_ep, "get_broker", lambda: b)

    res_a = asyncio.run(config_ep.generate_bulk({
        "duration_hours": 0.02, "time_step": 10.0, "name": "HTTP 路由情境A"}))
    res_b = asyncio.run(config_ep.generate_bulk({
        "duration_hours": 0.02, "time_step": 10.0, "name": "HTTP 路由情境B"}))
    sid_a, sid_b = res_a["scenario_id"], res_b["scenario_id"]

    app = FastAPI()
    app.include_router(scenarios_ep.router)
    client = TestClient(app)

    resp = client.get(f"/api/scenarios/compare?ids={sid_a},{sid_b}")
    assert resp.status_code == 200, (
        f"GET /api/scenarios/compare 應落地在 compare_scenarios（200），實得 "
        f"{resp.status_code}：{resp.text}——若為 422 代表被 /{{scenario_id}} 攔截，路由順序回歸"
    )
    body = resp.json()
    assert [s["scenarioId"] for s in body["scenarios"]] == [sid_a, sid_b]

    # 對照組：單一情境端點本身不受影響，仍正常運作。
    resp_single = client.get(f"/api/scenarios/{sid_a}")
    assert resp_single.status_code == 200


def test_compare_route_returns_400_over_real_http_for_invalid_ids(tmp_path, monkeypatch):
    """`_parse_compare_ids` 的驗證錯誤（純函式測試已覆蓋）在真實 HTTP 請求管線裡也要能正確浮現成
    400（而非被吞掉或變成其他狀態碼）——走真 TestClient，補足「整條請求路徑」層級的驗證。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    storage = Storage(db_path=str(tmp_path / "http400.db"))
    sim = WindFarmSimulator(turbine_count=2)
    sim._running = True
    live_sid = storage.create_session(data_source="simulation", turbine_count=2)
    b = _FakeBroker(storage, sim, live_sid)
    monkeypatch.setattr(scenarios_ep, "get_broker", lambda: b)

    app = FastAPI()
    app.include_router(scenarios_ep.router)
    client = TestClient(app)

    assert client.get("/api/scenarios/compare?ids=5").status_code == 400        # 不足 2 個
    assert client.get("/api/scenarios/compare?ids=1,abc").status_code == 400    # 非整數


# ─── 情境掛載唯讀端點（PR C Phase 1，DEC-20260926-01 / WMOM-20260926-03）─────────

def test_scenario_turbines_endpoint_returns_latest_reading_per_turbine(broker):
    """整合：以 generate_bulk 建真情境 → get_scenario_turbines 回每台機組最後一筆讀數，
    格式對齊 TurbineReading（status 是合法列舉值、非原始 operational_state 字串）。"""
    from server.models import TurbineStatus

    res = asyncio.run(config_ep.generate_bulk({
        "duration_hours": 0.02, "time_step": 10.0, "name": "掛載情境A"}))
    sid = res["scenario_id"]

    readings = asyncio.run(scenarios_ep.get_scenario_turbines(sid))
    assert [r.turbineId for r in readings] == ["WT001", "WT002", "WT003"]
    for r in readings:
        assert isinstance(r.status, TurbineStatus)
        assert r.name.startswith("WTG-")


def test_scenario_turbines_404_for_unknown_scenario(broker):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        asyncio.run(scenarios_ep.get_scenario_turbines(999_999))
    assert ei.value.status_code == 404


def test_scenario_farm_status_endpoint_aggregates_latest_readings(broker):
    """整合：farm-status 的彙整需與同一批 /turbines 端點回傳的末筆讀數自洽
    （totalTurbines/計數分桶/totalPowerMW 皆由同一份資料算出）。"""
    res = asyncio.run(config_ep.generate_bulk({
        "duration_hours": 0.02, "time_step": 10.0, "name": "掛載情境B"}))
    sid = res["scenario_id"]

    readings = asyncio.run(scenarios_ep.get_scenario_turbines(sid))
    status = asyncio.run(scenarios_ep.get_scenario_farm_status(sid))

    assert status.totalTurbines == len(readings) == 3
    assert (status.operatingCount + status.idleCount
            + status.faultCount + status.offlineCount) == status.totalTurbines
    assert status.totalPowerMW == pytest.approx(
        round(sum(r.powerOutput for r in readings), 2))


def test_scenario_farm_status_404_for_unknown_scenario(broker):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        asyncio.run(scenarios_ep.get_scenario_farm_status(999_999))
    assert ei.value.status_code == 404


# ─── FAULT 狀態重算（DEC-20260926-01 must-fix，code review 抓到）──────────────
# storage 的 `status` 欄位存的是 operational_state（RUNNING/IDLE/...），結構上永遠不是
# "FAULT"（`simulator.engine._tur_state_to_str` 映射表沒有 FAULT 分支）——即時路徑的 FAULT
# 覆寫靠記憶體內 FaultEngine 當下狀態，情境批次生成完那份記憶體狀態就消失了。若不修，情境掛載
# 永遠無法回報 FAULT，示範一個刻意注入故障的情境會整面顯示「健康」。修法：對已持久化的故障注入
# 事件（history_events）依 FaultEngine.step() 相同公式離線重算 tripped 狀態。

def test_scenario_turbines_reports_fault_for_tripped_injected_fault(broker):
    """整合：注入 initial_severity=0.95（遠高於 hydraulic_leak 預設 auto_trip_severity=0.85）
    的故障 → 該機組末筆讀數的 status 必須是 FAULT，其餘機組不受影響（must-fix 修復前，
    無論注入多嚴重的故障，這裡永遠會是 IDLE/OPERATING，此測試在修復前會失敗）。"""
    from server.models import TurbineStatus
    res = asyncio.run(config_ep.generate_bulk({
        "duration_hours": 0.02, "time_step": 10.0, "name": "已跳機情境",
        "fault_schedule": [{"scenario_id": "hydraulic_leak", "turbine_id": "WT002",
                            "offset_seconds": 0, "initial_severity": 0.95}],
    }))
    sid = res["scenario_id"]

    readings = asyncio.run(scenarios_ep.get_scenario_turbines(sid))
    by_id = {r.turbineId: r for r in readings}
    assert by_id["WT002"].status == TurbineStatus.FAULT
    assert by_id["WT001"].status != TurbineStatus.FAULT
    assert by_id["WT003"].status != TurbineStatus.FAULT

    status = asyncio.run(scenarios_ep.get_scenario_farm_status(sid))
    assert status.faultCount == 1


def test_scenario_turbines_not_fault_when_severity_below_trip_threshold(broker):
    """整合：低 initial_severity + 極短情境（成長量可忽略）→ 尚未 tripped，不應強制 FAULT。"""
    from server.models import TurbineStatus
    res = asyncio.run(config_ep.generate_bulk({
        "duration_hours": 0.02, "time_step": 10.0, "name": "未跳機情境",
        "fault_schedule": [{"scenario_id": "hydraulic_leak", "turbine_id": "WT002",
                            "offset_seconds": 0, "initial_severity": 0.05}],
    }))
    sid = res["scenario_id"]

    readings = asyncio.run(scenarios_ep.get_scenario_turbines(sid))
    by_id = {r.turbineId: r for r in readings}
    assert by_id["WT002"].status != TurbineStatus.FAULT


def test_scenario_turbines_no_fault_schedule_never_forces_fault(broker):
    """回歸：沒有故障排程的一般情境（既有 baseline 測試涵蓋的路徑）不應被本次修復意外
    強制 FAULT——`_tripped_fault_turbine_ids` 收到空事件清單時回空集合。"""
    from server.models import TurbineStatus
    res = asyncio.run(config_ep.generate_bulk({
        "duration_hours": 0.02, "time_step": 10.0, "name": "無故障情境"}))
    sid = res["scenario_id"]

    readings = asyncio.run(scenarios_ep.get_scenario_turbines(sid))
    assert all(r.status != TurbineStatus.FAULT for r in readings)


def _fault_event(turbine_id: str, scenario_id: str, timestamp: str,
                  severity_rate: float = 0.0002, initial_severity: float = 0.0,
                  event_type: str = "fault") -> dict:
    """`history_events` 查詢結果格式的最小故障事件（含已解析 payload），供
    `_tripped_fault_turbine_ids` 純函式測試用。"""
    return {
        "event_type": event_type,
        "turbine_id": turbine_id,
        "timestamp": timestamp,
        "payload": {
            "scenarioId": scenario_id,
            "turbineId": turbine_id,
            "severityRate": severity_rate,
            "initialSeverity": initial_severity,
        },
    }


def test_tripped_fault_turbine_ids_computes_severity_growth():
    """純函式：severity = initial + rate*elapsed，達到 auto_trip_severity 才算 tripped。
    hydraulic_leak 預設 auto_trip_severity=0.85（未在 FAULT_SCENARIOS 覆寫）。"""
    events = [_fault_event("WT001", "hydraulic_leak",
                           "2026-01-01T00:00:00", severity_rate=0.01, initial_severity=0.0)]
    # elapsed=10s → severity=0.1，未達 0.85
    early = scenarios_ep._tripped_fault_turbine_ids(
        events, datetime.fromisoformat("2026-01-01T00:00:10"))
    assert early == set()
    # elapsed=100s → severity=1.0（clamp）≥ 0.85
    later = scenarios_ep._tripped_fault_turbine_ids(
        events, datetime.fromisoformat("2026-01-01T00:01:40"))
    assert later == {"WT001"}


def test_tripped_fault_turbine_ids_ignores_injection_after_as_of():
    """尚未發生（注入時間晚於 as_of）的事件不應計入——防禦性檢查。"""
    events = [_fault_event("WT001", "hydraulic_leak",
                           "2026-01-01T01:00:00", initial_severity=0.99)]
    assert scenarios_ep._tripped_fault_turbine_ids(
        events, datetime.fromisoformat("2026-01-01T00:00:00")) == set()


def test_tripped_fault_turbine_ids_ignores_non_fault_events_and_unknown_scenario():
    events = [
        {"event_type": "grid", "turbine_id": "WT001", "timestamp": "2026-01-01T00:00:00",
         "payload": {"scenarioId": "hydraulic_leak", "severityRate": 1.0, "initialSeverity": 1.0}},
        _fault_event("WT002", "not_a_real_scenario_id", "2026-01-01T00:00:00", initial_severity=1.0),
    ]
    assert scenarios_ep._tripped_fault_turbine_ids(
        events, datetime.fromisoformat("2026-01-01T00:00:00")) == set()


def test_tripped_fault_turbine_ids_dedupes_keeping_latest_injection():
    """同一台機組同一 scenario_id 被注入兩次（比照 FaultEngine.inject() 的 dedup 語意：
    後一次取代前一次）——只有『最後一次注入』的 initial_severity 生效。第一次 initial=0.99
    若未被正確取代，會被誤判 tripped；第二次 initial=0.0 + 慢速成長，同一時刻不應 tripped。"""
    events = [
        _fault_event("WT001", "hydraulic_leak", "2026-01-01T00:00:00", initial_severity=0.99),
        _fault_event("WT001", "hydraulic_leak", "2026-01-01T00:00:05",
                     severity_rate=0.0002, initial_severity=0.0),
    ]
    assert scenarios_ep._tripped_fault_turbine_ids(
        events, datetime.fromisoformat("2026-01-01T00:00:10")) == set()


def test_tripped_fault_turbine_ids_defaults_missing_payload_fields():
    """payload 缺 severityRate/initialSeverity → 比照 `_parse_fault_schedule` 的預設值
    （0.0002/0.0），不應炸 KeyError/TypeError。"""
    event = {
        "event_type": "fault", "turbine_id": "WT001", "timestamp": "2026-01-01T00:00:00",
        "payload": {"scenarioId": "hydraulic_leak"},
    }
    # elapsed 極大但 rate 用預設 0.0002 → 仍可能 trip，只驗證不拋錯 + 型別正確
    result = scenarios_ep._tripped_fault_turbine_ids(
        [event], datetime.fromisoformat("2026-01-02T00:00:00"))
    assert isinstance(result, set)


def test_scenario_row_to_reading_maps_operational_state_not_raw_string():
    """Must-fix 對應防線：row['status'] 是原始 operational_state 字串，必須經 _map_state 轉換，
    否則會塞進只接受 4 種列舉值的 TurbineReading.status 炸 ValidationError（mutation：拔掉
    _map_state()、直接餵 row['status'] 給 TurbineReading，RUNNING/STARTING/STOPPING 這些不在
    TurbineStatus 列舉裡的原始字串會讓 pydantic 驗證失敗，此測試會轉紅）。"""
    from server.models import TurbineStatus

    def row(status: str) -> dict:
        return {"turbine_id": "WT002", "timestamp": "2026-03-01T00:00:00",
                "status": status, "tur_state": 6}

    assert scenarios_ep._scenario_row_to_reading(row("RUNNING")).status == TurbineStatus.OPERATING
    assert scenarios_ep._scenario_row_to_reading(row("STARTING")).status == TurbineStatus.OPERATING
    assert scenarios_ep._scenario_row_to_reading(row("STOPPING")).status == TurbineStatus.IDLE
    assert scenarios_ep._scenario_row_to_reading(row("IDLE")).status == TurbineStatus.IDLE
    assert scenarios_ep._scenario_row_to_reading(row("FAULT")).status == TurbineStatus.FAULT
    assert scenarios_ep._scenario_row_to_reading(row("SOMETHING_UNKNOWN")).status == \
        TurbineStatus.OFFLINE


def test_scenario_row_to_reading_derives_name_from_turbine_id():
    row = {"turbine_id": "WT007", "timestamp": "2026-03-01T00:00:00",
           "status": "RUNNING", "tur_state": 6}
    reading = scenarios_ep._scenario_row_to_reading(row)
    assert reading.turbineId == "WT007"
    assert reading.name == "WTG-07"


def test_scenario_row_to_reading_preserves_genuine_zero_tur_state():
    """code review should-fix：`tur_state=0` 是 storage._insert_reading 真實會存的值
    （scada 缺 WTUR_TurSt tag 時的預設），`row.get(...) or 6` 會把它誤判成缺值、silently
    捏造成 6（正常發電）。改用 `is not None` 判斷才能保留真實 0。"""
    row = {"turbine_id": "WT001", "timestamp": "2026-03-01T00:00:00",
           "status": "IDLE", "tur_state": 0}
    reading = scenarios_ep._scenario_row_to_reading(row)
    assert reading.turState == 0


def test_scenario_row_to_reading_defaults_tur_state_when_missing():
    row = {"turbine_id": "WT001", "timestamp": "2026-03-01T00:00:00", "status": "IDLE"}
    reading = scenarios_ep._scenario_row_to_reading(row)
    assert reading.turState == 6


def test_aggregate_scenario_farm_status_empty_turbines_all_zero():
    """無讀數（清單為空）→ 全 0，不炸（比照 _build_farm_summary_empty 既有慣例）。"""
    status = scenarios_ep._aggregate_scenario_farm_status([])
    assert status.totalTurbines == 0
    assert status.operatingCount == 0
    assert status.totalPowerMW == 0
    assert status.avgWindSpeed == 0


def test_scenario_rated_power_default_and_override():
    """額定功率：session 未存/0/None → 預設 Z72 2000 kW；有正值 → 採用。"""
    assert scenarios_ep._scenario_rated_power_kw({}) == scenarios_ep.DEFAULT_RATED_POWER_KW
    assert scenarios_ep._scenario_rated_power_kw({"rated_power_kw": None}) == \
        scenarios_ep.DEFAULT_RATED_POWER_KW
    assert scenarios_ep._scenario_rated_power_kw({"rated_power_kw": 0}) == \
        scenarios_ep.DEFAULT_RATED_POWER_KW
    assert scenarios_ep._scenario_rated_power_kw({"rated_power_kw": 5500.0}) == 5500.0
