"""Service/Maintenance state SCADA tag 測試（WMOM-20260505-26-a）。

新增兩個 ``WSRV_*`` tag，皆「直接映射」``TurbinePhysicsModel`` 既有真實狀態，
不引入新的獨立布林旗標（劉老師 2026-10-06 核准的降低版 acceptance）：

- ``WSRV_ManualOverride`` ← ``operator_stop``（``cmd_stop()`` 設、``cmd_start()``/
  ``cmd_reset()``/``cmd_service(True)`` 清）
- ``WSRV_LockoutState`` ← ``tur_state == 7``（emergency stop 狀態機狀態）

驗證：① registry schema 正確；② 呼叫既有真實控制路徑時 tag 值同步翻轉；
③ 引擎層故障跳機路徑（``cmd_emergency_stop``）下 tag 與 ``tur_state`` 逐步一致；
④ 走 integer-tag 路徑，不被 sensor model 加雜訊（值恆為 0/1）。
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

from server.routers.export import SCADA_CSV_COLUMNS  # noqa: E402
from simulator.engine import WindFarmSimulator  # noqa: E402
from simulator.physics.scada_registry import SCADA_REGISTRY  # noqa: E402
from simulator.physics.turbine_physics import TurbinePhysicsModel  # noqa: E402

NEW_TAGS = ("WSRV_ManualOverride", "WSRV_LockoutState")
EMERGENCY_STOP = 7  # tur_state：緊急停機
PRODUCING = 6  # tur_state：併網發電


def _step(model: TurbinePhysicsModel) -> Dict[str, float]:
    return model.step(10.0, 0.0, dt=1.0)


def _producing_model() -> TurbinePhysicsModel:
    """建一台在 10 m/s 下已併網發電的機組（前置條件）。"""
    model = TurbinePhysicsModel(seed=45)
    for _ in range(300):
        _step(model)
    assert model.tur_state == PRODUCING, "前置條件：機組應已併網發電"
    return model


# ── ① registry schema ────────────────────────────────────────────────────


def test_new_tags_registered_with_wsrv_schema() -> None:
    """兩個新 tag 皆註冊於 registry，subsystem/type/範圍對齊既有 WSRV_SrvOn。"""
    for tag_id in NEW_TAGS:
        tag = SCADA_REGISTRY[tag_id]
        assert tag.subsystem == "WSRV"
        assert tag.data_type == "SINT16"
        assert tag.opc_tag.startswith("WSRV.Z72PLC__UI_Srv_State_")
        assert (tag.sim_min, tag.sim_max) == (0, 1)
        assert tag.label_en and tag.label_zh


def test_by_subsystem_wsrv_includes_new_tags() -> None:
    """by_subsystem('WSRV') 應同時含既有 SrvOn 與兩個新 tag。"""
    ids = {t.id for t in SCADA_REGISTRY.by_subsystem("WSRV")}
    assert ids == {"WSRV_SrvOn", *NEW_TAGS}


def test_new_tags_present_in_step_output() -> None:
    """step() 輸出必須帶兩個新 tag（registry 宣告的 tag 要真的有值）。"""
    out = _step(TurbinePhysicsModel(seed=45))
    for tag_id in NEW_TAGS:
        assert tag_id in out


def test_new_tags_in_csv_export_columns() -> None:
    """歷史 CSV 匯出欄位要含兩個新 tag，且皆為 registry 已註冊 tag。"""
    for tag_id in NEW_TAGS:
        assert tag_id in SCADA_CSV_COLUMNS
    assert all(c in SCADA_REGISTRY for c in SCADA_CSV_COLUMNS)


# ── ② 真實控制路徑翻轉 WSRV_ManualOverride ───────────────────────────────


def test_manual_override_follows_cmd_stop_and_cmd_start() -> None:
    """cmd_stop() → 1；cmd_start() → 0；且值恆等於 operator_stop。"""
    model = _producing_model()
    assert _step(model)["WSRV_ManualOverride"] == 0

    model.cmd_stop()
    for _ in range(3):
        out = _step(model)
        assert out["WSRV_ManualOverride"] == 1
        assert model.operator_stop is True

    model.cmd_start()
    out = _step(model)
    assert out["WSRV_ManualOverride"] == 0
    assert model.operator_stop is False


def test_manual_override_cleared_by_cmd_reset() -> None:
    """cmd_reset() 會清 operator_stop → tag 回 0。"""
    model = _producing_model()
    model.cmd_stop()
    assert _step(model)["WSRV_ManualOverride"] == 1
    model.cmd_reset()
    assert _step(model)["WSRV_ManualOverride"] == 0


def test_service_mode_is_distinct_from_manual_override() -> None:
    """進維護模式走 WSRV_SrvOn，不誤報為人工停機（cmd_service 會清 operator_stop）。"""
    model = _producing_model()
    model.cmd_stop()
    assert _step(model)["WSRV_ManualOverride"] == 1
    model.cmd_service(True)
    out = _step(model)
    assert out["WSRV_SrvOn"] == 1
    assert out["WSRV_ManualOverride"] == 0


# ── ② 真實控制路徑翻轉 WSRV_LockoutState ─────────────────────────────────


def test_lockout_state_follows_cmd_emergency_stop() -> None:
    """cmd_emergency_stop() 後進 state 7 → tag 1；離開 state 7 → tag 0。

    每步逐一比對 ``tag == (tur_state == 7)``，並確認兩種值都真的出現過，
    避免「恆為 0」或「恆為 1」的實作也能通過。
    """
    model = _producing_model()
    assert _step(model)["WSRV_LockoutState"] == 0

    model.cmd_emergency_stop()
    seen = set()
    for _ in range(40):
        out = _step(model)
        expected = 1 if model.tur_state == EMERGENCY_STOP else 0
        assert out["WSRV_LockoutState"] == expected
        seen.add(expected)
    assert seen == {0, 1}, "40 步內應先進 state 7 再離開"


def test_lockout_state_on_engine_fault_trip_path() -> None:
    """引擎層：故障 tripped → 引擎每步 cmd_emergency_stop → tag 與 tur_state 逐步一致。

    已知行為（非本 issue 範圍，記錄於 work-log）：故障持續時 state 在 7↔3 間擺盪，
    故 tag 也隨之擺盪，而非持續 latch 為 1。
    """
    sim = WindFarmSimulator(turbine_count=2)
    sim._running = True
    tid = next(iter(sim.turbines))
    assert sim.fault_engine.inject("generator_overspeed", tid, severity_rate=0.05)

    t0 = datetime(2026, 1, 1)
    seen = set()
    for i in range(8):
        readings = sim._run_one_step(t0 + timedelta(seconds=i * 10), 10.0)
        reading = next(r for r in readings if r["turbine_id"] == tid)
        expected = 1 if sim.turbines[tid].tur_state == EMERGENCY_STOP else 0
        assert reading["scada"]["WSRV_LockoutState"] == expected
        seen.add(expected)
    assert 1 in seen, "故障跳機後應至少有一步處於緊急停機閉鎖"


# ── ④ integer tag：不加 sensor 雜訊 ──────────────────────────────────────


def test_new_tags_are_noise_free_integers() -> None:
    """新 tag 走 _integer_tags 路徑：多步、多狀態下值恆為精確的 0 或 1。"""
    model = _producing_model()
    values = set()
    for cmd in (model.cmd_stop, model.cmd_start, model.cmd_emergency_stop):
        cmd()
        for _ in range(10):
            out = _step(model)
            for tag_id in NEW_TAGS:
                values.add(out[tag_id])
    assert values <= {0, 1}
