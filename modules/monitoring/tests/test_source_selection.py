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


# ─── 產生情境不自由跑（WMOM-20260720-07 / DEC-20260720-01 PR B）──────────────────

def test_start_scenario_mode_creates_simulator_without_freerun_loop(broker):
    """產生情境（run_loop=False）：建 simulator 供批次生成，但**不起自由跑迴圈**（不持續產資料）；
    source_kind=scenario。這是「情境＝凍結資料集」的核心——選了不會一直產新資料。"""
    from server.models import DataSourceConfig, DataSourceMode

    broker.start(DataSourceConfig(mode=DataSourceMode.SIMULATION), run_loop=False)
    try:
        assert broker.simulator is not None, "情境模式仍需 simulator 供批次生成"
        assert broker.simulator.is_running is False, "情境模式不該有自由跑迴圈"
        assert broker.source_kind == "scenario"
        assert broker.source_active is True
    finally:
        broker.stop()


def test_start_simulation_mode_runs_freerun_loop(broker):
    """即時模擬（run_loop=True，預設）：起自由跑迴圈、source_kind=simulation（與情境對照）。"""
    from server.models import DataSourceConfig, DataSourceMode

    broker.start(DataSourceConfig(mode=DataSourceMode.SIMULATION), run_loop=True)
    try:
        assert broker.simulator is not None and broker.simulator.is_running is True
        assert broker.source_kind == "simulation"
    finally:
        broker.stop()


def test_get_all_turbines_empty_in_scenario_before_first_generate(broker):
    """Must-fix（PR #147 review）：scenario 模式下 simulator 已建但**尚未跑過任何 step**時，
    engine 的 latest_data 是「每台機組→空 dict」佔位。get_all_turbines() 必須跳過空 output 回空清單，
    而非讓 _sim_output_to_reading({}) 把每台 turbine_id 都 fallback 成常數 'WT001'、回 N 筆重複假資料
    （會餵給 /api/turbines、farm-status、WS 廣播）。turbineCount=3 → 少了防線會回 3 筆假 WT001。"""
    from server.models import DataSourceConfig, DataSourceMode, SimulationConfig

    broker.start(
        DataSourceConfig(mode=DataSourceMode.SIMULATION),
        SimulationConfig(turbineCount=3),
        run_loop=False,
    )
    try:
        assert broker.simulator is not None and broker.simulator.is_running is False
        assert broker.get_all_turbines() == [], "尚未生成前不該回任何（更不該回重複假 WT001）資料"
        # 與 get_turbine() 既有 `if output:` 防線一致：單機查詢空 output 亦回 None。
        assert broker.get_turbine("WT001") is None
    finally:
        broker.stop()


def test_stop_returns_promptly_after_maintenance_started(broker):
    """Should-fix（PR #147 review）：maintenance thread 的週期睡眠改為可中斷（Event.wait）後，
    start() 過一次再 stop() 應近乎瞬間完成，而非固定卡到 join timeout（舊 time.sleep(300) 害每次
    切換來源的 stop() 都卡滿 5 秒）。門檻取 3 秒：舊 bug 精確 5.0s、修好後 ~0s，區隔充裕。"""
    import time as _t
    from server.models import DataSourceConfig, DataSourceMode

    broker.start(DataSourceConfig(mode=DataSourceMode.SIMULATION), run_loop=False)
    t0 = _t.time()
    broker.stop()
    elapsed = _t.time() - t0
    assert elapsed < 3.0, f"stop() 應近乎瞬間（maintenance 睡眠可中斷）；實測 {elapsed:.2f}s"


# ─── pause_live_for_batch（WMOM-20260720-01：批次期間暫停 Live 的共用 context）──────

def test_pause_live_for_batch_noop_without_simulator(broker):
    """view / idle（simulator 為 None）→ context 安全 no-op（yield False、不拋）。
    對應 generate-bulk 在無 simulator 時由端點自身回 400 的分支。"""
    assert broker.simulator is None
    with broker.pause_live_for_batch() as was:
        assert was is False


def test_pause_live_for_batch_stops_during_and_restores_after(broker):
    """有在跑的 Live simulator → 進 context 時 thread 停掉、離開 context 時恢復（新 thread）。
    這是 config.py/faults.py 批次端點賴以「批次全程無第二個 writer」的共用機制。"""
    from simulator.engine import WindFarmSimulator

    sim = WindFarmSimulator(turbine_count=1)
    broker.simulator = sim
    sim.start(time_step=0.02)
    assert sim.is_running and sim._thread.is_alive()

    with broker.pause_live_for_batch() as was:
        inside_alive = sim._thread.is_alive()
    assert was is True
    assert inside_alive is False, "context 內 Live thread 應已停（無並行 writer）"
    assert sim.is_running and sim._thread.is_alive(), "離開 context 應恢復 Live 自由跑"
    sim.stop()


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


def test_select_scenario_activates_simulation_without_freerun(client, monkeypatch):
    """mode=scenario → activate_simulation(run_loop=False)（產生情境不自由跑）。"""
    called = {}
    monkeypatch.setattr(
        "server.app.activate_simulation",
        lambda run_loop=True: called.__setitem__("run_loop", run_loop),
    )
    r = client.post("/api/source/select", json={"mode": "scenario"})
    assert r.status_code == 200
    assert called.get("run_loop") is False


def test_select_simulation_activates_freerun(client, monkeypatch):
    """mode=simulation → activate_simulation(run_loop=True)（即時模擬自由跑；與 scenario 對照）。"""
    called = {}
    monkeypatch.setattr(
        "server.app.activate_simulation",
        lambda run_loop=True: called.__setitem__("run_loop", run_loop),
    )
    r = client.post("/api/source/select", json={"mode": "simulation"})
    assert r.status_code == 200
    assert called.get("run_loop") is True


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


# ─── Modbus 選配起不來時的降級（WMOM-20260720-01）───────────────────────────

class _FakeSim:
    """activate_simulation 用到的最小 simulator 表面：modbus_server 槽 + turbines dict。"""

    def __init__(self):
        self.modbus_server = None
        self.turbines = {"WT001": object()}


def test_start_modbus_degrades_when_construction_fails(monkeypatch):
    """pymodbus 版本不相容 / 未裝 → ModbusSimServer 建構丟例外時，_start_modbus_for 應吞掉、
    把 modbus_server 設回 None（降級為無 Modbus 模擬），而**不**讓 activate 500。"""
    from server import app as app_module

    class _BoomModbus:
        def __init__(self, *a, **k):
            raise RuntimeError("pymodbus 3.14 incompatible: 0 <= address < 65535")

    monkeypatch.setattr("simulator.modbus_server.ModbusSimServer", _BoomModbus)
    sim = _FakeSim()
    app_module._start_modbus_for(sim)  # 不應拋
    assert sim.modbus_server is None


def test_start_modbus_sets_server_on_success(monkeypatch):
    """成功路徑：ModbusSimServer 建得起來 → 綁到 simulator 並呼叫 start()。
    與降級 test 成對，守住「降級分支不會誤吞正常啟動」。"""
    from server import app as app_module

    started = {"v": False}

    class _OKModbus:
        def __init__(self, *a, **k):
            pass

        def start(self):
            started["v"] = True

    monkeypatch.setattr("simulator.modbus_server.ModbusSimServer", _OKModbus)
    sim = _FakeSim()
    app_module._start_modbus_for(sim)
    assert sim.modbus_server is not None and started["v"] is True


def test_start_modbus_noop_when_already_started(monkeypatch):
    """已有 modbus_server（重入切換來源）→ 不重複建構。"""
    from server import app as app_module

    sim = _FakeSim()
    sentinel = object()
    sim.modbus_server = sentinel

    def _should_not_construct(*a, **k):
        raise AssertionError("已存在 modbus_server 時不應再建構")

    monkeypatch.setattr("simulator.modbus_server.ModbusSimServer", _should_not_construct)
    app_module._start_modbus_for(sim)
    assert sim.modbus_server is sentinel


# ─── activate_simulation：scenario 不起 Modbus 的整合覆蓋（PR #147 review）──────────

@pytest.fixture
def app_broker(tmp_path, monkeypatch):
    """把 server.app 的 module-global broker/farm_registry 換成 tmp 隔離實例，讓
    activate_simulation（直接引用 module global，非經 get_broker()）能安全在測試中真跑其函式體。"""
    from server import app as app_module

    reg = FarmRegistry(data_dir=tmp_path)
    b = DataBroker(farm_registry=reg)
    monkeypatch.setattr(app_module, "broker", b)
    monkeypatch.setattr(app_module, "farm_registry", reg)
    try:
        yield app_module, b
    finally:
        b.stop()


def test_activate_simulation_scenario_skips_modbus(app_broker, monkeypatch):
    """產生情境（run_loop=False）：activate_simulation 走真正函式體，`if run_loop:` guard 應
    **不呼叫 _start_modbus_for**（情境無連續即時值可供外部 Modbus client 讀），且 source_kind=scenario、
    simulator 不自由跑。守住「拿掉 guard 讓 Modbus 永遠嘗試啟動」的 mutation 會被抓。"""
    app_module, b = app_broker
    calls = []
    monkeypatch.setattr(app_module, "_start_modbus_for", lambda sim: calls.append(sim))

    app_module.activate_simulation(run_loop=False)

    assert calls == [], "產生情境不該起 Modbus"
    assert b.source_kind == "scenario"
    assert b.simulator is not None and b.simulator.is_running is False


def test_activate_simulation_freerun_starts_modbus(app_broker, monkeypatch):
    """即時模擬（run_loop=True）：對照組——應呼叫 _start_modbus_for 一次、source_kind=simulation、
    simulator 自由跑。與 scenario test 成對，守住「guard 不會誤吞正常的 Modbus 啟動」。"""
    app_module, b = app_broker
    calls = []
    monkeypatch.setattr(app_module, "_start_modbus_for", lambda sim: calls.append(sim))

    app_module.activate_simulation(run_loop=True)

    assert len(calls) == 1, "即時模擬應起 Modbus 一次"
    assert b.source_kind == "simulation"
    assert b.simulator is not None and b.simulator.is_running is True


# ─── 切走 live 的角色檢查（WMOM-20260720-04 (2)）───────────────────────────────
# 起 live 需 SUPERVISOR，但切走 live（回 simulation/scenario/view）之前無角色檢查——
# 前端 #144 的二次確認只防手滑，不防任何登入者直接呼叫 API 斷現場連線。切走與起 live 對稱。

def test_switch_away_from_live_requires_supervisor(client, broker, monkeypatch):
    """目前來源是 live，employee 想切回 simulation → 403（在真的呼叫 activate_simulation 前就擋）。"""
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    broker._source_active = True
    broker._source_kind = "live"
    called = {"v": False}
    monkeypatch.setattr("server.app.activate_simulation", lambda run_loop=True: called.__setitem__("v", True))
    from modules.auth.tokens import create_access_token

    tok = create_access_token(subject="u3", role="employee", name="E")
    r = client.post(
        "/api/source/select",
        json={"mode": "simulation"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 403
    assert called["v"] is False, "被角色閘門擋下前不該真的切換來源"
    assert broker.source_kind == "live", "403 時來源不該被動到"


def test_switch_away_from_live_to_view_requires_supervisor(client, broker, monkeypatch):
    """切到 view（僅調閱過去情境）一樣算「切走 live」，同等敏感，同樣需 SUPERVISOR。"""
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    broker._source_active = True
    broker._source_kind = "live"
    from modules.auth.tokens import create_access_token

    tok = create_access_token(subject="u4", role="employee", name="E")
    r = client.post(
        "/api/source/select",
        json={"mode": "view"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 403
    assert broker.source_kind == "live"


def test_switch_away_from_live_allows_supervisor(client, broker, monkeypatch):
    """positive path：SUPERVISOR 切走 live 應成功——守住「角色判斷被寫壞成連 SUPERVISOR 都擋」。"""
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    broker._source_active = True
    broker._source_kind = "live"
    monkeypatch.setattr("server.app.activate_simulation", lambda run_loop=True: None)
    from modules.auth.tokens import create_access_token

    tok = create_access_token(subject="u5", role="supervisor", name="S")
    r = client.post(
        "/api/source/select",
        json={"mode": "simulation"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200


def test_switch_between_non_live_sources_does_not_require_supervisor(client, broker, monkeypatch):
    """對照組：目前不是 live（如 simulation）時切到 view，一般登入者即可——不該被新檢查誤擋。"""
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    broker._source_active = True
    broker._source_kind = "simulation"
    from modules.auth.tokens import create_access_token

    tok = create_access_token(subject="u6", role="employee", name="E")
    r = client.post(
        "/api/source/select",
        json={"mode": "view"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200
