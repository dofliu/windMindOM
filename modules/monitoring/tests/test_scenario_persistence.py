"""情境保存/調閱：storage 層（WMOM-20260719-02, DEC-20260718-01 #4）。

背景：使用者實測回報「產生過的情境調不回來、融進歷史了」。根因＝``generate-bulk`` 把資料
寫進當前 active session、無情境識別；``query_history`` 也不依 session 過濾。修法把「情境」
建模成一個以 ``config_json.kind == "scenario"`` 標記的專屬 session，資料寫進該 session_id，
並讓 ``query_history`` 能依 session 隔離調閱。

本檔驗證 storage 層的四塊（純 SQLite，不需 broker/HTTP/simulator）：
1. 情境 session 建立 + ``list_scenarios`` / ``get_scenario`` 只認情境、不誤收 Live session。
2. ``query_history(session_id=...)`` 真的把情境資料與 Live/其他歷史隔離。
3. ``update_session_config`` 併入生成後統計（原鍵保留）。
4. ``delete_scenario`` 連資料列一起刪、且只作用在情境 session（不誤刪 Live）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))


@pytest.fixture
def storage(tmp_path):
    """Fresh Storage on temp DB."""
    from server.storage import Storage

    yield Storage(db_path=str(tmp_path / "test_scenarios.db"))


def _reading(turbine_id: str, ts: str, power_w: float = 1_500_000.0, wind: float = 8.0) -> dict:
    """store_reading 能吃的最小 reading（帶模擬時間戳）。"""
    return {
        "timestamp": ts,
        "turbine_id": turbine_id,
        "operational_state": "PRODUCING",
        "wind_speed": wind,
        "total_power": power_w,
        "scada": {"WTUR_TurSt": 6, "WTUR_TotPwrAt": power_w / 1000.0},
    }


def _scenario(storage, name: str, **cfg) -> int:
    """建一個情境 session，回 id。"""
    config = {"kind": storage.SCENARIO_KIND, "name": name}
    config.update(cfg)
    return storage.create_session(data_source="SIMULATION", turbine_count=3, config=config)


# ─── 建立 / list / get / 隔離 ──────────────────────────────────────────────

def test_scenario_saved_listed_and_isolated_from_live(storage):
    live_sid = storage.create_session(data_source="SIMULATION", turbine_count=3)
    storage.store_readings([_reading("WT001", "2026-03-01T00:00:00", power_w=1_000_000)], live_sid)

    sc_sid = _scenario(storage, "颱風測試", wind_profile="storm", duration_hours=1.0)
    storage.store_readings([
        _reading("WT001", "2026-03-01T01:00:00", power_w=2_000_000),
        _reading("WT001", "2026-03-01T01:00:10", power_w=2_100_000),
    ], sc_sid)

    # list_scenarios 只回情境、config 已解析
    scs = storage.list_scenarios()
    assert [s["id"] for s in scs] == [sc_sid], "Live session 不該被當成情境列出"
    assert scs[0]["config"]["name"] == "颱風測試"
    assert scs[0]["config"]["kind"] == "scenario"

    # get_scenario：命中情境；Live session id / 不存在 → None
    assert storage.get_scenario(sc_sid)["id"] == sc_sid
    assert storage.get_scenario(live_sid) is None
    assert storage.get_scenario(10_000_000) is None

    # query_history(session_id=) 隔離
    assert len(storage.query_history("WT001", session_id=sc_sid)) == 2
    assert len(storage.query_history("WT001", session_id=live_sid)) == 1
    # 不帶 session_id → 融在一起（3 筆），證明隔離確實靠 session_id
    assert len(storage.query_history("WT001")) == 3


def test_list_scenarios_newest_first_and_limit(storage):
    ids = [_scenario(storage, f"s{i}") for i in range(3)]
    assert [s["id"] for s in storage.list_scenarios()] == list(reversed(ids))
    assert len(storage.list_scenarios(limit=2)) == 2


def test_list_scenarios_empty_when_only_live_sessions(storage):
    storage.create_session(data_source="SIMULATION", turbine_count=3)
    storage.create_session(data_source="MODBUS_TCP", turbine_count=3)
    assert storage.list_scenarios() == []


# ─── update_session_config 回填 ────────────────────────────────────────────

def test_update_session_config_merges_keeping_existing(storage):
    sid = _scenario(storage, "x", wind_profile="calm")
    storage.update_session_config(sid, {
        "total_readings": 42, "faults_injected": 1,
        "sim_start": "2026-03-01T00:00:00", "sim_end": "2026-03-01T01:00:00",
    })
    cfg = storage.get_scenario(sid)["config"]
    assert cfg["name"] == "x"                # 原鍵保留
    assert cfg["wind_profile"] == "calm"     # 原鍵保留
    assert cfg["total_readings"] == 42       # 新鍵併入
    assert cfg["sim_end"] == "2026-03-01T01:00:00"


def test_update_session_config_missing_session_is_noop(storage):
    storage.update_session_config(10_000_000, {"x": 1})  # 不存在 → 不炸


# ─── delete ────────────────────────────────────────────────────────────────

def _count_session_rows(storage, table: str, session_id: int) -> int:
    return storage._get_conn().execute(
        f"SELECT COUNT(*) FROM {table} WHERE session_id = ?", (session_id,)
    ).fetchone()[0]


def test_delete_scenario_removes_session_and_all_five_tables(storage):
    """delete_scenario 要連 turbine_data / _1m / _10m / snapshots + sessions 全清。

    1m/10m 沒有便捷公開寫入路徑（需等 run_downsampling），故直接以原生 SQL 塞 session 列，
    守住「宣稱刪五張表」不因日後漏掉某張表名而破功（漏刪仍是合法 SQL，不會 raise）。
    """
    sc_sid = _scenario(storage, "del")
    storage.store_readings([
        _reading("WT001", "2026-03-01T00:00:00"),
        _reading("WT002", "2026-03-01T00:00:10"),
    ], sc_sid)
    storage.store_snapshot(_reading("WT001", "2026-03-01T00:00:01"), "ev:del:1", sc_sid)
    conn = storage._get_conn()
    for tbl in ("turbine_data_1m", "turbine_data_10m"):
        conn.execute(
            f"INSERT INTO {tbl} (timestamp, turbine_id, session_id) VALUES (?, ?, ?)",
            ("2026-03-01T00:00:00", "WT001", sc_sid),
        )
    conn.commit()

    for tbl in ("turbine_data", "turbine_data_1m", "turbine_data_10m", "turbine_snapshots"):
        assert _count_session_rows(storage, tbl, sc_sid) > 0, f"{tbl} 前置應有列"

    assert storage.delete_scenario(sc_sid) is True
    assert storage.get_scenario(sc_sid) is None
    for tbl in ("turbine_data", "turbine_data_1m", "turbine_data_10m", "turbine_snapshots"):
        assert _count_session_rows(storage, tbl, sc_sid) == 0, f"{tbl} 應被清空"
    # 已不存在 → 再刪回 False
    assert storage.delete_scenario(sc_sid) is False


def test_delete_scenario_refuses_live_session(storage):
    live_sid = storage.create_session(data_source="SIMULATION", turbine_count=1)
    storage.store_readings([_reading("WT001", "2026-03-01T00:00:00")], live_sid)

    assert storage.delete_scenario(live_sid) is False, "delete_scenario 不得動 Live session"
    assert len(storage.query_history("WT001", session_id=live_sid)) == 1, "Live 資料不得被誤刪"


# ─── 情境物理聚合（A0 摘要，DEC-20260720-02 / WMOM-20260720-09）─────────────────

def _phys_reading(tid: str, ts: str, power_w: float, tur_st: int,
                  rul: float, prod: float, dmg: float, mom: float, dl: float) -> dict:
    """帶完整 WLOD 物理量的情境 reading；四部位以固定乘/加偏移區分，抓 SQL column 錯置。"""
    return {
        "timestamp": ts, "turbine_id": tid, "operational_state": "PRODUCING",
        "wind_speed": 8.0, "total_power": power_w,
        "scada": {
            "WTUR_TurSt": tur_st, "WTUR_TotPwrAt": power_w / 1000.0,
            "WLOD_RulHours": rul, "WLOD_ProdHours": prod,
            "WLOD_DmgTwrFa": dmg, "WLOD_DmgTwrSs": dmg * 2,
            "WLOD_DmgBldFlap": dmg * 3, "WLOD_DmgBldEdge": dmg * 4,
            "WLOD_TwrFaMom": mom, "WLOD_TwrSsMom": mom + 50,
            "WLOD_BldFlapMom": mom + 100, "WLOD_BldEdgeMom": mom + 150,
            "WLOD_DelTwrFa": dl, "WLOD_DelTwrSs": dl + 10,
            "WLOD_DelBldFlap": dl + 20, "WLOD_DelBldEdge": dl + 30,
        },
    }


def test_scenario_turbine_aggregates_computes_per_turbine_physics(storage):
    """A0 聚合：每台機組一列。**累積量（損傷/生產時數）與峰值（極限負載）用 MAX；RUL/DEL 非單調 →
    取情境結束（最後一列）真實值**。四部位偏移抓 column 錯置。

    刻意讓 RUL/DEL 非單調，且末值≠MIN/MAX，以直接證明「取末列」而非 MIN/MAX（PR #148 review Must-fix）：
    RUL 1000→500→900（末值 900、MIN 500）；DEL 100→599→344（末值 344、MAX 599）。
    彎矩 500→700→600（極限負載＝MAX 700，非末值 600）。
    """
    sid = _scenario(storage, "聚合測試", duration_hours=1.0, time_step=10.0)
    storage.store_readings([
        _phys_reading("WT001", "2026-03-01T00:00:00", 1_000_000, 6, 1000, 0.1, 0.001, 500, 100),
        _phys_reading("WT001", "2026-03-01T00:00:10", 2_000_000, 6, 500,  0.2, 0.002, 700, 599),
        _phys_reading("WT001", "2026-03-01T00:00:20", 3_000_000, 7, 900,  0.2, 0.003, 600, 344),
    ], sid)
    # WT002：單步，供「分組正確」與跨機組對照。
    storage.store_readings([
        _phys_reading("WT002", "2026-03-01T00:00:00", 500_000, 6, 2000, 0.05, 0.0005, 300, 90),
    ], sid)

    aggs = storage.scenario_turbine_aggregates(sid)
    by_id = {a["turbine_id"]: a for a in aggs}
    assert list(by_id) == ["WT001", "WT002"], "應依 turbine_id 排序、每台一列"

    a1 = by_id["WT001"]
    assert a1["n"] == 3
    assert a1["avg_power_mw"] == pytest.approx(2.0)          # (1+2+3)/3
    assert a1["max_power_mw"] == pytest.approx(3.0)
    assert a1["prod_hours"] == pytest.approx(0.2)            # MAX（單調累積末值）
    assert a1["dmg_tower_fa"] == pytest.approx(0.003)        # MAX＝結束時累積末值
    assert a1["dmg_tower_ss"] == pytest.approx(0.006)        # 0.003×2 → 抓 column 錯置
    assert a1["dmg_blade_flap"] == pytest.approx(0.009)
    assert a1["dmg_blade_edge"] == pytest.approx(0.012)
    assert a1["max_tower_fa_moment"] == pytest.approx(700)   # MAX（極限負載）非末值 600
    assert a1["max_tower_ss_moment"] == pytest.approx(750)
    assert a1["max_blade_edge_moment"] == pytest.approx(850)  # 700+150
    # RUL/DEL 取末列（00:00:20），非 MIN/MAX：
    assert a1["rul_hours"] == pytest.approx(900), "RUL 應取情境結束末值 900，非 MIN 500"
    assert a1["del_tower_fa"] == pytest.approx(344), "DEL 應取情境結束末值 344，非 MAX 599"
    assert a1["del_blade_edge"] == pytest.approx(374)        # 末列 344+30
    assert a1["production_steps"] == 2                       # 兩步 tur_state==6
    assert a1["estop_steps"] == 1

    a2 = by_id["WT002"]
    assert a2["n"] == 1
    assert a2["rul_hours"] == pytest.approx(2000)
    assert a2["production_steps"] == 1


def test_scenario_aggregates_rul_sentinel_maps_to_none(storage):
    """RUL sentinel（-1.0，暖機不足無法估計）在末列時應映射為 None，不得污染成「最低 RUL」。"""
    sid = _scenario(storage, "sentinel", duration_hours=0.01, time_step=10.0)
    storage.store_readings([
        _phys_reading("WT001", "2026-03-01T00:00:00", 1_000_000, 6, 500,  0.05, 0.001, 400, 50),
        _phys_reading("WT001", "2026-03-01T00:00:10", 1_000_000, 6, -1.0, 0.05, 0.001, 400, 50),
    ], sid)
    a = storage.scenario_turbine_aggregates(sid)[0]
    assert a["rul_hours"] is None, "末列 RUL 為 sentinel -1.0 → None（非 -1.0、非 500）"


def test_scenario_turbine_aggregates_empty_for_unknown_session(storage):
    """不存在的 session → 空 list（不炸）。"""
    assert storage.scenario_turbine_aggregates(99_999) == []


def test_count_scenario_fault_events_by_window(storage):
    """時間窗內每台機組 fault 事件數：只計有 turbine_id 的 fault，排除非 fault 與 farm-wide；無 LIMIT。"""
    storage.record_event(event_type="fault", source="scenario", title="f1",
                         turbine_id="WT001", timestamp="2026-03-01T00:00:05")
    storage.record_event(event_type="fault", source="scenario", title="f2",
                         turbine_id="WT001", timestamp="2026-03-01T00:00:15")
    storage.record_event(event_type="fault", source="scenario", title="f3",
                         turbine_id="WT002", timestamp="2026-03-01T00:00:20")
    storage.record_event(event_type="state", source="scenario", title="s1",
                         turbine_id="WT001", timestamp="2026-03-01T00:00:06")  # 非 fault
    storage.record_event(event_type="fault", source="scenario", title="farm",
                         turbine_id=None, timestamp="2026-03-01T00:00:07")     # farm-wide
    storage.record_event(event_type="fault", source="scenario", title="outside",
                         turbine_id="WT001", timestamp="2026-03-01T01:00:00")  # 窗外

    counts = storage.count_scenario_fault_events(
        start="2026-03-01T00:00:00", end="2026-03-01T00:00:30")
    assert counts == {"WT001": 2, "WT002": 1}
