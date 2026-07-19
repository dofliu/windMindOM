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
