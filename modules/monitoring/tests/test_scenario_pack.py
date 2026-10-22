"""情境資料包匯出（WMOM-20261021-05，EPIC-DS Phase 3a ① 檔案）。

一個固定起點、固定風速的 2 h 情境（WT001 主軸承磨耗、WT002 超速），匯出後檢查：

1. 檔案齊全、manifest 的 sha256 / 計數 / 時間窗正確，盲測版不含答案、不帶情境名稱與故障排程
2. raw Parquet：欄位＝Bachmann tag 名（註冊表順序）、型別依 PLC 資料型別、值與落庫的讀值一致
3. 10 分鐘統計與 raw 重算一致（avg / min / max / std、n_samples、窗對齊、殘缺窗、類比 vs 離散欄、圓統計）
4. events.jsonl：只有可觀測事件、合約格式、每行欄位相同、不含任何故障 ID、停機原因正規化
5. 評分端版的 ground_truth.json；重匯出、決定性、原子性、錯誤情境
6. 端點（暫存目錄清理、上限）與 CLI
7. 人工 session：非對齊起點、缺值、寫入順序不是時間順序、取樣週期由資料推得
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import math
import os
import secrets
import sys
import time
import zipfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
for _p in (PROJECT_ROOT, MONITORING_ROOT, PROJECT_ROOT / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import numpy as np  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
import pytest  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import export_scenario_pack as pack_cli  # noqa: E402
import simulator.engine as engine_mod  # noqa: E402
from server import scenario_pack as sp  # noqa: E402
from server.data_broker import DataBroker  # noqa: E402
from server.routers import config as config_ep  # noqa: E402
from server.routers import scenarios as scenarios_ep  # noqa: E402
from modules.auth.tokens import create_access_token  # noqa: E402
from server.storage import Storage, is_observable_event  # noqa: E402
from shared.plc_tags import is_real_plc_tag  # noqa: E402
from shared.alarm_codes import all_alarms, get_alarm  # noqa: E402
from simulator.engine import WindFarmSimulator  # noqa: E402
from simulator.ground_truth import CONTRACT_VERSION  # noqa: E402
from simulator.physics.fault_engine import FAULT_SCENARIOS  # noqa: E402
from simulator.physics.scada_registry import SCADA_REGISTRY  # noqa: E402
from simulator.time_utils import parse_iso  # noqa: E402

T0 = datetime(2026, 1, 15, 3, 0, tzinfo=timezone.utc)
SCENARIO_NAME = "考題：主軸承 + 超速"
PACK_TAGS = [t for t in SCADA_REGISTRY.all_tags if t.id not in sp.MODEL_INTERNAL_TAGS]
POWER = "Z72PLC__UI_Loc_WTUR_Analogue_TotPwrAt"
WIND_DIR = "Z72PLC__UI_Loc_WMET_Analogue_WDirAbs"


class _FakeBroker:
    """情境生成端點用到的 broker 表面（批次事件寫入沿用真 DataBroker 的實作）。"""

    _PLC_EVENT_TITLES = DataBroker._PLC_EVENT_TITLES
    _plc_event_fields = DataBroker._plc_event_fields
    _state_transition_fields = DataBroker._state_transition_fields
    _state_name = DataBroker._state_name
    record_bulk_events = DataBroker.record_bulk_events

    def __init__(self, storage: Storage, simulator: WindFarmSimulator) -> None:
        self.storage = storage
        self.simulator = simulator
        self._session_id = storage.create_session(data_source="simulation", turbine_count=3)

    @contextmanager
    def pause_live_for_batch(self) -> Iterator[bool]:
        yield False

    def record_event(self, session_id: Optional[int] = None, **kwargs: object) -> None:
        self.storage.record_event(session_id=session_id if session_id is not None else self._session_id,
                                  **kwargs)  # type: ignore[arg-type]  # 轉交 record_event 的關鍵字參數


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Dict[str, object]:
    """生成一次情境（模組共用，生成約數秒）。"""
    tmp = tmp_path_factory.mktemp("pack")
    storage = Storage(db_path=str(tmp / "farm.db"))
    sim = WindFarmSimulator(turbine_count=3)
    sim.wind_model.set_override(wind_speed=14.0)
    broker = _FakeBroker(storage, sim)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(engine_mod, "utc_now", lambda: T0)
        mp.setattr(config_ep, "get_broker", lambda: broker)
        result = asyncio.run(config_ep.generate_bulk({
            "duration_hours": 2.0, "time_step": 10.0, "name": SCENARIO_NAME, "wind_profile": "rated",
            "fault_schedule": [
                {"scenario_id": "bearing_wear", "turbine_id": "WT001", "offset_seconds": 0, "severity_rate": 0.002},
                {"scenario_id": "generator_overspeed", "turbine_id": "WT002", "offset_seconds": 1800,
                 "severity_rate": 0.01},
            ],
        }))
    scenario_id = int(result["scenario_id"])
    blind_dir = tmp / "blind"
    full_dir = tmp / "full"
    blind = sp.export_scenario_pack(storage, scenario_id, blind_dir)
    full = sp.export_scenario_pack(storage, scenario_id, full_dir, include_ground_truth=True)
    return {"storage": storage, "scenario_id": scenario_id, "blind_dir": blind_dir, "blind": blind,
            "full_dir": full_dir, "full": full, "broker": broker, "tmp": tmp}


def _events(pack_dir: Path) -> List[dict]:
    return [json.loads(line) for line in (pack_dir / sp.FILE_EVENTS).read_text(encoding="utf-8").splitlines()]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── 1. manifest 與盲測 ────────────────────────────────────────────────────────


def test_blind_pack_files_and_manifest(generated: Dict[str, object]) -> None:
    pack_dir: Path = generated["blind_dir"]  # type: ignore[assignment]
    manifest = json.loads((pack_dir / sp.FILE_MANIFEST).read_text(encoding="utf-8"))
    assert manifest == generated["blind"]
    expected = {sp.FILE_TAGS, sp.FILE_ALARMS, sp.FILE_RAW, sp.FILE_STATS, sp.FILE_EVENTS}
    assert set(manifest["files"]) == expected
    assert {p.name for p in pack_dir.iterdir()} == expected | {sp.FILE_MANIFEST}
    for name, info in manifest["files"].items():
        assert info == {"sha256": _sha256(pack_dir / name), "bytes": (pack_dir / name).stat().st_size}
    sid = generated["scenario_id"]
    assert manifest["pack_id"] == f"z72-scenario-{sid:05d}" and manifest["contract_version"] == CONTRACT_VERSION
    assert manifest["turbines"] == ["WT001", "WT002", "WT003"]
    assert (manifest["sim_start"], manifest["sim_end"]) == ("2026-01-15T03:00:10.000000Z", "2026-01-15T05:00:00.000000Z")
    assert manifest["sample_period_s"] == 10.0 and manifest["stats_window_s"] == 600
    assert manifest["site_timezone"] == "Asia/Taipei" and manifest["ground_truth_included"] is False
    assert manifest["wind_profile"] == "rated" and manifest["generator"]["exporter_version"] == sp.EXPORTER_VERSION
    assert manifest["counts"] == {"raw_rows": 720 * 3, "stats_rows": 13 * 3, "partial_windows": 2 * 3,
                                  "events": len(_events(pack_dir)), "events_dropped": 0}
    convention = manifest["stats_convention"]
    assert convention["interval"].startswith("left-closed") and convention["std_ddof"] == 1
    assert convention["circular_tags"] == [WIND_DIR]


def test_blind_pack_never_names_the_faults(generated: Dict[str, object]) -> None:
    """盲測：manifest / 事件 / tag 字典都不含故障 ID、情境名稱、故障排程。"""
    pack_dir: Path = generated["blind_dir"]  # type: ignore[assignment]
    manifest = generated["blind"]
    for key in ("name", "fault_schedule", "faults_injected", "scenario_name"):
        assert key not in manifest  # type: ignore[operator]
    for name in (sp.FILE_MANIFEST, sp.FILE_EVENTS, sp.FILE_TAGS):
        text = (pack_dir / name).read_text(encoding="utf-8")
        assert SCENARIO_NAME not in text
        leaked = [fid for fid in FAULT_SCENARIOS if fid in text]
        assert leaked == [], f"{name} 含故障 ID {leaked}"
    for name in (sp.FILE_RAW, sp.FILE_STATS):
        assert not pq.read_schema(pack_dir / name).metadata, "Parquet 不帶任何額外 metadata"


# ── 2. raw Parquet ───────────────────────────────────────────────────────────


def test_raw_parquet_schema_uses_bachmann_names_and_plc_types(generated: Dict[str, object]) -> None:
    schema = pq.read_schema(generated["blind_dir"] / sp.FILE_RAW)  # type: ignore[operator]
    tags = PACK_TAGS
    assert len(tags) == 116 - 16
    assert schema.names == ["timestamp", "turbine_id"] + [t.opc_tag.split(".", 1)[1] for t in tags]
    assert schema.field("timestamp").type == pa.timestamp("us", tz="UTC")
    types = {"REAL32": pa.float32(), "SINT16": pa.int16(), "UINT16": pa.uint16(), "BOOL": pa.bool_()}
    for tag in tags:
        assert schema.field(tag.opc_tag.split(".", 1)[1]).type == types[tag.data_type], tag.id


def test_raw_parquet_values_match_the_stored_readings(generated: Dict[str, object]) -> None:
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    table = pq.read_table(generated["blind_dir"] / sp.FILE_RAW).to_pylist()  # type: ignore[operator]
    stored = [row for batch in storage.iter_session_readings(generated["scenario_id"]) for row in batch]  # type: ignore[arg-type]
    assert len(table) == len(stored)
    keys = [(r["timestamp"], r["turbine_id"]) for r in table]
    assert keys == sorted(keys), "依時間、機組排序"
    for i in (0, 1, len(stored) // 2, len(stored) - 1):
        row, src = table[i], stored[i]
        assert row["timestamp"] == parse_iso(src["timestamp"]) and row["turbine_id"] == src["turbine_id"]
        scada = json.loads(src["scada_json"])
        for tag in PACK_TAGS:
            value = row[tag.opc_tag.split(".", 1)[1]]
            if tag.data_type == "REAL32":
                assert value == pytest.approx(scada[tag.id], rel=1e-6, abs=1e-6), tag.id
            elif tag.data_type == "BOOL":
                assert value == bool(scada[tag.id]), tag.id
            else:
                assert value == int(round(scada[tag.id])), tag.id


# ── 3. 10 分鐘統計 ───────────────────────────────────────────────────────────


def test_stats_match_a_recomputation_from_raw(generated: Dict[str, object]) -> None:
    raw = pq.read_table(generated["blind_dir"] / sp.FILE_RAW).to_pandas()  # type: ignore[operator]
    stats = pq.read_table(generated["blind_dir"] / sp.FILE_STATS).to_pandas()  # type: ignore[operator]
    assert len(stats) == 13 * 3, "03:00-04:50 共 12 個整窗 + 05:00 的 1 筆，各 3 台"
    assert all(ts.minute % 10 == 0 and ts.second == 0 for ts in stats["window_start"])
    assert ((stats["window_end"] - stats["window_start"]) == np.timedelta64(600, "s")).all()
    first = stats[stats["window_start"] == stats["window_start"].min()]
    assert set(first["n_samples"]) == {59}, "03:00:10 起：第一窗少一筆"
    last = stats[stats["window_start"] == stats["window_start"].max()]
    assert set(last["n_samples"]) == {1}
    assert first["is_partial"].all() and last["is_partial"].all(), "頭尾殘缺窗要標出來"
    assert not stats[stats["n_samples"] == 60]["is_partial"].any()

    window = stats[(stats["turbine_id"] == "WT001") & (stats["n_samples"] == 60)].iloc[3]
    start = window["window_start"]
    rows = raw[(raw["turbine_id"] == "WT001") & (raw["timestamp"] >= start)
               & (raw["timestamp"] < start + np.timedelta64(600, "s"))]
    assert len(rows) == 60
    for tag in ("Z72PLC__UI_Loc_WGEN_Analogue_GnBrgTmp1", "Z72PLC__UI_Loc_WTUR_Analogue_TotPwrAt"):
        values = rows[tag].to_numpy(dtype=float)
        assert window[f"{tag}_avg"] == pytest.approx(values.mean(), rel=1e-5)
        assert window[f"{tag}_min"] == pytest.approx(values.min(), rel=1e-6)
        assert window[f"{tag}_max"] == pytest.approx(values.max(), rel=1e-6)
        assert window[f"{tag}_std"] == pytest.approx(values.std(ddof=1), rel=1e-4, abs=1e-5)
    # 離散 tag（運轉狀態）只有 min / max
    state = "Z72PLC__UI_Loc_WTUR_State_TurSt"
    assert f"{state}_min" in stats and f"{state}_max" in stats and f"{state}_avg" not in stats
    assert window[f"{state}_max"] == rows[state].max()


def test_single_sample_window_has_null_std(generated: Dict[str, object]) -> None:
    stats = pq.read_table(generated["blind_dir"] / sp.FILE_STATS).to_pylist()  # type: ignore[operator]
    last = [r for r in stats if r["n_samples"] == 1]
    assert last and all(r["Z72PLC__UI_Loc_WTUR_Analogue_TotPwrAt_std"] is None for r in last)
    assert all(r["Z72PLC__UI_Loc_WTUR_Analogue_TotPwrAt_avg"] is not None for r in last)


# ── 4. 事件 ──────────────────────────────────────────────────────────────────


def test_events_are_the_observable_events_in_contract_format(generated: Dict[str, object]) -> None:
    pack_dir: Path = generated["blind_dir"]  # type: ignore[assignment]
    events = _events(pack_dir)
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    observable = [e for e in storage.session_events(generated["scenario_id"]) if is_observable_event(e)]  # type: ignore[arg-type]
    assert len(events) == len(observable)
    assert [e["ts"] for e in events] == sorted(e["ts"] for e in events)
    assert all(e["ts"].endswith("Z") and len(e["ts"]) == 27 for e in events)
    allowed = {"alarm_raised", "alarm_cleared", "trip", "trip_cleared", "restart_blocked", "reset", "info",
               "state_change"}
    assert {e["event_type"] for e in events} <= allowed
    assert not any("value" in e or "setpoint" in e for e in events), "不輸出模擬器內部的製程值"

    trips = {(e["turbine_id"], e["alarm_code"]) for e in events if e["event_type"] == "trip"}
    assert ("WT001", 240) in trips and ("WT002", 351) in trips
    alarm = next(e for e in events if e["event_type"] == "alarm_raised" and e["alarm_code"] == 262)
    catalog = get_alarm(262)
    assert (alarm["alarm_level"], alarm["alarm_text"], alarm["event_id"], alarm["plc_tag"]) == \
        (catalog.level, catalog.text, catalog.event_id, catalog.plc_tag)

    stops = {(e["turbine_id"], e["to_state"]): e for e in events if e["event_type"] == "state_change"}
    assert stops[("WT001", 9)]["stop_reason"] == "plc_trip" and stops[("WT001", 9)]["to_state_name"] == "Normal Stop"
    assert stops[("WT002", 7)]["stop_reason"] == "overspeed"
    starts = [e for e in events if e["event_type"] == "state_change" and e["to_state"] == 6]
    assert starts and all(e["stop_reason"] is None for e in starts)


@pytest.mark.parametrize("cause, reason", [
    ("plc:240", "plc_trip"), ("cut_out", "high_wind"), ("low_wind", "low_wind"), ("below_cut_in", "low_wind"),
    ("grid_trip", "grid"), ("grid_protection", "grid"), ("ride_through:lvrt_band1", "grid"),
    ("overspeed_software", "overspeed"), ("operator", "operator"), ("service", "operator"),
    ("maintenance_lock", None), ("idle", None), (None, None),
])
def test_stop_reason_hides_simulator_vocabulary(cause: Optional[str], reason: Optional[str]) -> None:
    assert sp.stop_reason(cause) == reason


def test_pack_event_maps_plc_kinds_and_drops_unknown() -> None:
    def plc(kind: str) -> dict:
        return {"timestamp": "2026-01-15T03:00:00.000000+00:00", "turbine_id": "WT001", "source": "plc",
                "payload": {"kind": kind, "code": 8, "level": "I", "text": "Operator reset", "eventId": "I_008"}}
    assert sp.pack_event(plc("operator_reset"))["event_type"] == "reset"  # type: ignore[index]
    assert sp.pack_event(plc("something_new")) is None
    state = {"timestamp": "2026-01-15T03:00:00+00:00", "turbine_id": "WT001", "source": "simulator",
             "payload": {"fromState": 9, "toState": 3, "shutdownCause": "plc:240"}}
    packed = sp.pack_event(state)
    assert packed is not None and packed["stop_reason"] is None, "只有進入停機狀態才帶停機原因"


def test_state_names_match_the_broker() -> None:
    assert sp.STATE_NAMES == {s: DataBroker._state_name(s) for s in range(1, 10)}


# ── 5. 其他檔案、標準答案、重匯出 ─────────────────────────────────────────────


def test_tag_dictionary_and_alarm_catalog(generated: Dict[str, object]) -> None:
    pack_dir: Path = generated["blind_dir"]  # type: ignore[assignment]
    tags = json.loads((pack_dir / sp.FILE_TAGS).read_text(encoding="utf-8"))["tags"]
    assert [t["tag"] for t in tags] == pq.read_schema(pack_dir / sp.FILE_RAW).names[2:]
    by_id = {t["id"]: t for t in tags}
    assert by_id["WTUR_TotPwrAt"]["source"] == "bachmann_real" and by_id["WTUR_TotPwrAt"]["unit"] == "kW"
    assert by_id["WMET_WSpeedRaw"]["source"] == "synthetic"
    assert sum(t["source"] == "bachmann_real" for t in tags) == 45 and len(tags) == 100
    assert not set(by_id) & sp.MODEL_INTERNAL_TAGS
    assert "WSpeedRaw" in by_id["WMET_WSpeedNac"]["note"] and by_id["WTUR_TotPwrAt"]["note"] is None
    catalog = json.loads((pack_dir / sp.FILE_ALARMS).read_text(encoding="utf-8"))["events"]
    assert len(catalog) == len(all_alarms())
    assert next(e for e in catalog if e["code"] == 240)["rectification"] == get_alarm(240).rectification


def test_full_pack_carries_the_ground_truth(generated: Dict[str, object]) -> None:
    full_dir: Path = generated["full_dir"]  # type: ignore[assignment]
    manifest = generated["full"]
    assert manifest["ground_truth_included"] is True  # type: ignore[index]
    assert sp.FILE_GROUND_TRUTH in manifest["files"]  # type: ignore[operator]
    gt = json.loads((full_dir / sp.FILE_GROUND_TRUTH).read_text(encoding="utf-8"))
    stored = generated["storage"].get_ground_truth(generated["scenario_id"])  # type: ignore[attr-defined]
    assert gt["pack_id"] == manifest["pack_id"] and gt["scenario_name"] == SCENARIO_NAME  # type: ignore[index]
    assert [c["fault_id"] for c in gt["cases"]] == ["bearing_wear", "generator_overspeed"]
    for packed, original in zip(gt["cases"], stored["cases"]):
        for key in ("onset_ts", "first_alarm_ts", "trip_ts"):
            assert (packed[key] is None) == (original[key] is None)
            if packed[key] is not None:
                assert packed[key].endswith("Z") and parse_iso(packed[key]) == parse_iso(original[key])
    # 盲測版與評分端版的資料檔一致，只差答案
    blind = generated["blind"]
    for name in (sp.FILE_RAW, sp.FILE_STATS, sp.FILE_EVENTS, sp.FILE_TAGS, sp.FILE_ALARMS):
        assert manifest["files"][name]["sha256"] == blind["files"][name]["sha256"]  # type: ignore[index]


def test_reexport_is_deterministic_and_drops_a_stale_answer_file(generated: Dict[str, object], tmp_path: Path) -> None:
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    sid: int = generated["scenario_id"]  # type: ignore[assignment]
    again = sp.export_scenario_pack(storage, sid, tmp_path / "pack", include_ground_truth=True)
    blind_again = sp.export_scenario_pack(storage, sid, tmp_path / "pack")
    assert not (tmp_path / "pack" / sp.FILE_GROUND_TRUTH).exists(), "盲測版不得留下舊的答案檔"
    assert blind_again["files"] == generated["blind"]["files"]  # type: ignore[index]
    assert again["files"] == generated["full"]["files"]  # type: ignore[index]


def test_unexportable_scenarios_are_refused(generated: Dict[str, object], tmp_path: Path) -> None:
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    with pytest.raises(sp.ScenarioPackError) as exc:
        sp.export_scenario_pack(storage, 99999, tmp_path / "x")
    assert exc.value.status_code == 404
    live_sid = generated["broker"]._session_id  # type: ignore[attr-defined]
    with pytest.raises(sp.ScenarioPackError) as exc:
        sp.export_scenario_pack(storage, live_sid, tmp_path / "x")
    assert exc.value.status_code == 404, "Live session 不是情境"

    legacy = storage.create_session("simulation", 3, config={"kind": storage.SCENARIO_KIND, "name": "舊",
                                                            "status": "ok"})
    with pytest.raises(sp.ScenarioPackError) as exc:
        sp.export_scenario_pack(storage, legacy, tmp_path / "x")
    assert exc.value.status_code == 409 and "WMOM-20261021-04" in str(exc.value)
    failed = storage.create_session("simulation", 3, config={"kind": storage.SCENARIO_KIND, "status": "error",
                                                            "events_session_isolated": True})
    with pytest.raises(sp.ScenarioPackError):
        sp.export_scenario_pack(storage, failed, tmp_path / "x")
    empty = storage.create_session("simulation", 3, config={"kind": storage.SCENARIO_KIND, "status": "ok",
                                                           "events_session_isolated": True})
    with pytest.raises(sp.ScenarioPackError, match="no readings"):
        sp.export_scenario_pack(storage, empty, tmp_path / "x")


# ── 6. 端點與 CLI ────────────────────────────────────────────────────────────


def _zip_names(response: object) -> List[str]:
    with zipfile.ZipFile(response.path) as archive:  # type: ignore[attr-defined]
        return sorted(archive.namelist())


def test_pack_endpoints_return_blind_and_full_zips(generated: Dict[str, object], monkeypatch: pytest.MonkeyPatch,
                                                  tmp_path: Path) -> None:
    monkeypatch.setattr(scenarios_ep, "get_broker", lambda: generated["broker"])
    monkeypatch.setattr(scenarios_ep, "PACK_TMP_ROOT", tmp_path / "packs")
    sid: int = generated["scenario_id"]  # type: ignore[assignment]
    prefix = sp.pack_id_for(sid)
    blind = asyncio.run(scenarios_ep.download_scenario_pack(sid))
    try:
        assert _zip_names(blind) == sorted(f"{prefix}/{n}" for n in sp.pack_file_names(False))
        assert [p.name for p in Path(blind.path).parent.iterdir()] == [Path(blind.path).name], "暫存目錄只留 zip"
        with zipfile.ZipFile(blind.path) as archive:  # type: ignore[attr-defined]
            kinds = {info.filename.rsplit("/", 1)[1]: info.compress_type for info in archive.infolist()}
        assert kinds[sp.FILE_RAW] == zipfile.ZIP_STORED and kinds[sp.FILE_EVENTS] == zipfile.ZIP_DEFLATED
    finally:
        blind.background.func(*blind.background.args, **blind.background.kwargs)  # type: ignore[union-attr]
    assert not Path(blind.path).parent.exists(), "回應送出後刪掉暫存目錄"
    full = asyncio.run(scenarios_ep.download_scenario_pack_full(sid))
    try:
        assert f"{prefix}/{sp.FILE_GROUND_TRUTH}" in _zip_names(full)
    finally:
        full.background.func(*full.background.args, **full.background.kwargs)  # type: ignore[union-attr]
    with pytest.raises(HTTPException) as exc:
        asyncio.run(scenarios_ep.download_scenario_pack(99999))
    assert exc.value.status_code == 404


def test_cli_lists_and_exports(generated: Dict[str, object], tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = str(generated["storage"]._db_path)  # type: ignore[attr-defined]
    sid: int = generated["scenario_id"]  # type: ignore[assignment]
    assert pack_cli.main([db, "--list"]) == 0
    assert "可匯出" in capsys.readouterr().out
    assert pack_cli.main([db, str(sid), "--out", str(tmp_path), "--ground-truth", "--zip"]) == 0
    pack_id = sp.pack_id_for(sid)
    assert (tmp_path / pack_id / sp.FILE_GROUND_TRUTH).exists()
    with zipfile.ZipFile(tmp_path / f"{pack_id}-full.zip") as archive:
        assert f"{pack_id}/{sp.FILE_GROUND_TRUTH}" in archive.namelist()
    assert pack_cli.main([db, "99999", "--out", str(tmp_path)]) == 1
    assert pack_cli.main([str(tmp_path / "missing.db"), "--list"]) == 2


def test_only_allow_listed_events_are_exported(generated: Dict[str, object], tmp_path: Path) -> None:
    """白名單是唯一的閘門：非可觀測來源的事件即使長得像狀態轉換也不能進資料包。"""
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    sid: int = generated["scenario_id"]  # type: ignore[assignment]
    storage.record_event("operator", "operator", "Manual stop", turbine_id="WT003", session_id=sid,
                         timestamp="2026-01-15T04:00:00+00:00",
                         payload={"fromState": 6, "toState": 9, "shutdownCause": "operator"})
    try:
        sp.export_scenario_pack(storage, sid, tmp_path / "pack")
        assert not [e for e in _events(tmp_path / "pack")
                    if e["turbine_id"] == "WT003" and e["ts"].startswith("2026-01-15T04:00:00")]
    finally:
        conn = storage._get_conn()
        conn.execute("DELETE FROM history_events WHERE session_id = ? AND title = 'Manual stop'", (sid,))
        conn.commit()


# ── 7. code review 補測（M1–M3、S1–S7）───────────────────────────────────────


def test_every_event_line_has_the_same_keys(generated: Dict[str, object]) -> None:
    """逐行推斷 schema 的讀取器（polars 等）只看前幾行：每行欄位要相同，不適用者為 null。"""
    events = _events(generated["blind_dir"])  # type: ignore[arg-type]
    assert events and all(list(e) == list(sp.EVENT_KEYS) for e in events)
    assert {e["event_type"] for e in events} >= {"alarm_raised", "trip", "state_change"}


def test_same_instant_events_keep_cause_before_effect(generated: Dict[str, object]) -> None:
    """同一時刻的跳機與停機狀態轉換：跳機（原因）在前。"""
    events = _events(generated["blind_dir"])  # type: ignore[arg-type]
    trip = next(e for e in events if e["event_type"] == "trip" and e["alarm_code"] == 351)
    stop = next(e for e in events if e["event_type"] == "state_change" and e["turbine_id"] == trip["turbine_id"]
                and e["to_state"] == 7)
    assert trip["ts"] == stop["ts"] and events.index(trip) < events.index(stop)


def test_model_internal_tags_are_synthetic_and_never_key_signals() -> None:
    """排除的模擬器內部量不能是真實 tag，也不能是任何故障情境的 key signal（答案指向資料包沒有的欄位）。"""
    registry = {t.id: t for t in SCADA_REGISTRY.all_tags}
    assert sp.MODEL_INTERNAL_TAGS <= set(registry)
    assert not [t for t in sp.MODEL_INTERNAL_TAGS if is_real_plc_tag(registry[t].opc_tag)]
    columns = {c.tag.id for c in sp.pack_columns()}
    for fault_id, scenario in FAULT_SCENARIOS.items():
        missing = set(scenario.key_signals) - columns
        assert not missing, f"{fault_id} 的 key signal {missing} 不在資料包"
    assert sp.CIRCULAR_TAGS <= columns and set(sp.TAG_NOTES) <= columns


@pytest.mark.parametrize("degrees, mean, std", [
    ([350.0, 10.0, 350.0, 10.0], 0.0, 10.0),
    ([0.0, 90.0], 45.0, 47.4613),  # ε = 0.707：Yamartino 修正 +5.5 %（只取 asin(ε) 會是 45°）
    ([0.0, 120.0, 240.0], 0.0, 103.923),  # ε = 1：Yamartino 上限 90° × 1.1547（均勻分布，平均無意義）
    ([90.0, 90.0, 90.0], 90.0, 0.0),
    ([359.0, 1.0, math.nan], 0.0, 1.0),
    ([200.0], 200.0, math.nan),
    ([math.nan, math.nan], math.nan, math.nan),
])
def test_circular_mean_and_yamartino_std(degrees: List[float], mean: float, std: float) -> None:
    got_mean, got_std = sp._circular_mean_std(np.array(degrees))
    if std > 100:
        pass  # 合向量為 0，平均方向沒有定義
    elif math.isnan(mean):
        assert math.isnan(got_mean)
    else:
        assert min(abs(got_mean - mean), 360 - abs(got_mean - mean)) < 1e-6 and 0 <= got_mean < 360
    if math.isnan(std):
        assert math.isnan(got_std)
    else:
        assert got_std == pytest.approx(std, rel=2e-3, abs=1e-6)


def test_batch_and_row_group_boundaries_do_not_change_the_data(generated: Dict[str, object], tmp_path: Path,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sp, "_READ_BATCH_ROWS", 7)
    monkeypatch.setattr(sp, "_ROW_GROUP_ROWS", 50)
    sid: int = generated["scenario_id"]  # type: ignore[assignment]
    small = sp.export_scenario_pack(generated["storage"], sid, tmp_path / "small")  # type: ignore[arg-type]
    blind_dir: Path = generated["blind_dir"]  # type: ignore[assignment]
    assert pq.ParquetFile(tmp_path / "small" / sp.FILE_RAW).num_row_groups > 1
    for name in (sp.FILE_RAW, sp.FILE_STATS):
        assert pq.read_table(tmp_path / "small" / name).equals(pq.read_table(blind_dir / name)), name
    for name in (sp.FILE_EVENTS, sp.FILE_TAGS, sp.FILE_ALARMS):
        assert small["files"][name] == generated["blind"]["files"][name], name  # type: ignore[index]


def test_failed_export_leaves_the_existing_pack_untouched(generated: Dict[str, object], tmp_path: Path,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    storage: Storage = generated["storage"]  # type: ignore[assignment]
    sid: int = generated["scenario_id"]  # type: ignore[assignment]
    pack_dir = tmp_path / "pack"
    sp.export_scenario_pack(storage, sid, pack_dir, include_ground_truth=True)
    before = {p.name: _sha256(p) for p in pack_dir.iterdir()}
    original = sp._write_pack_files

    def write_then_fail(*args: object, **kwargs: object) -> Dict[str, object]:
        original(*args, **kwargs)  # type: ignore[arg-type]
        raise RuntimeError("disk full")

    monkeypatch.setattr(sp, "_write_pack_files", write_then_fail)
    with pytest.raises(RuntimeError):
        sp.export_scenario_pack(storage, sid, pack_dir)
    assert {p.name: _sha256(p) for p in pack_dir.iterdir()} == before, "失敗時連舊答案檔都不動"
    assert [p.name for p in tmp_path.iterdir()] == ["pack"], "暫存目錄要清掉"


def test_ground_truth_timestamps_are_converted_everywhere() -> None:
    gt = {"contract_version": "0.1", "sim_start": "2026-01-15T11:00:00+08:00", "sim_end": None,
          "generated_at": "2026-01-15T03:00:00+00:00",
          "cases": [{"onset_ts": "2026-01-15T03:00:00+00:00", "first_alarm_ts": None, "trip_ts": ""}],
          "unattributed_events": [{"ts": "2026-01-15T03:05:00+00:00", "code": 336}]}
    out = sp.ground_truth_for_pack(gt, "z72-scenario-00001")
    assert out["contract_version"] == "1.0", "-04 起存的答案就是 v1.0 格式：舊的 0.1 標籤匯出時標成 1.0"
    assert out["sim_start"] == "2026-01-15T03:00:00.000000Z" and out["sim_end"] is None
    assert out["cases"][0] == {"onset_ts": "2026-01-15T03:00:00.000000Z", "first_alarm_ts": None, "trip_ts": ""}
    assert out["unattributed_events"][0]["ts"] == "2026-01-15T03:05:00.000000Z"
    assert gt["sim_start"] == "2026-01-15T11:00:00+08:00", "不改動輸入"


def test_pack_tmp_dirs_are_removed_on_error_and_swept_when_stale(generated: Dict[str, object], tmp_path: Path,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "packs"
    monkeypatch.setattr(scenarios_ep, "PACK_TMP_ROOT", root)
    old = time.time() - scenarios_ep.PACK_TMP_MAX_AGE_S - 60
    stale, fresh = root / "pack-stale", root / "pack-fresh"
    for path in (stale, fresh):
        path.mkdir(parents=True)
    os.utime(stale, (old, old))

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("export failed")

    monkeypatch.setattr(sp, "export_scenario_pack", boom)
    with pytest.raises(RuntimeError):
        scenarios_ep._build_pack_zip(generated["storage"], generated["scenario_id"], False)  # type: ignore[arg-type]
    # 本次的暫存目錄失敗即清；送出前重啟留下的舊目錄由下一次下載清掉；別的請求還在用的不動
    assert [p.name for p in root.iterdir()] == ["pack-fresh"]


def test_pack_endpoint_limits(generated: Dict[str, object], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(scenarios_ep, "get_broker", lambda: generated["broker"])
    sid: int = generated["scenario_id"]  # type: ignore[assignment]
    monkeypatch.setattr(scenarios_ep, "MAX_PACK_ROWS_HTTP", 100)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(scenarios_ep.download_scenario_pack(sid))
    assert exc.value.status_code == 413 and "export_scenario_pack.py" in str(exc.value.detail)

    # 筆數上限在情境檢查之後：資料很多的非情境 session（Live）仍是 404，不是叫人改用 CLI
    other = Storage(db_path=str(tmp_path / "live.db"))
    live = other.create_session("simulation", 1)
    other._get_conn().executemany(
        "INSERT INTO turbine_data (timestamp, turbine_id, session_id, scada_json) VALUES (?, 'WT001', ?, '{}')",
        [(f"2026-01-15T03:{m:02d}:00.000000+00:00", live) for m in range(60)])
    other._get_conn().commit()
    monkeypatch.setattr(scenarios_ep, "MAX_PACK_ROWS_HTTP", 10)
    monkeypatch.setattr(scenarios_ep, "get_broker", lambda: type("B", (), {"storage": other})())
    with pytest.raises(HTTPException) as exc:
        asyncio.run(scenarios_ep.download_scenario_pack(live))
    assert exc.value.status_code == 404
    monkeypatch.setattr(scenarios_ep, "get_broker", lambda: generated["broker"])

    held = [scenarios_ep._pack_slots.acquire(blocking=False) for _ in range(scenarios_ep.MAX_CONCURRENT_PACKS)]
    try:
        assert all(held)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(scenarios_ep.download_scenario_pack(sid))
        assert exc.value.status_code == 429
    finally:
        for _ in held:
            scenarios_ep._pack_slots.release()
    # 失敗的匯出（413 / 404）都在 thread 裡歸還名額
    again = [scenarios_ep._pack_slots.acquire(blocking=False) for _ in range(scenarios_ep.MAX_CONCURRENT_PACKS)]
    for ok in again:
        if ok:
            scenarios_ep._pack_slots.release()
    assert all(again)


def test_full_pack_over_http_for_a_supervisor(generated: Dict[str, object], monkeypatch: pytest.MonkeyPatch,
                                              tmp_path: Path) -> None:
    monkeypatch.setenv("WMOM_JWT_SECRET", secrets.token_hex(16))
    monkeypatch.delenv("WMOM_DEV_MODE", raising=False)
    monkeypatch.delenv("WMOM_AUTH_ENFORCE", raising=False)
    monkeypatch.setattr(scenarios_ep, "get_broker", lambda: generated["broker"])
    monkeypatch.setattr(scenarios_ep, "PACK_TMP_ROOT", tmp_path / "packs")
    app = FastAPI()
    app.include_router(scenarios_ep.router)
    client = TestClient(app)
    sid: int = generated["scenario_id"]  # type: ignore[assignment]

    def bearer(role: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(subject='u1', role=role, name='U')}"}

    resp = client.get(f"/api/scenarios/{sid}/pack/full", headers=bearer("supervisor"))
    assert resp.status_code == 200 and resp.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        names = archive.namelist()
        gt = json.loads(archive.read(f"{sp.pack_id_for(sid)}/{sp.FILE_GROUND_TRUTH}"))
    assert len(names) == len(sp.pack_file_names(True)) and gt["pack_id"] == sp.pack_id_for(sid)
    assert list((tmp_path / "packs").iterdir()) == [], "回應送出後背景刪掉暫存目錄"
    assert client.get(f"/api/scenarios/{sid}/pack/full", headers=bearer("employee")).status_code == 403


# ── 8. 人工 session：非對齊起點、缺值、亂序寫入、取樣週期由資料推得 ─────────────────


def _synthetic_scenario(storage: Storage, rows: List[tuple], **config: object) -> int:
    sid = storage.create_session("simulation", 2, config={
        "kind": storage.SCENARIO_KIND, "status": "ok", "events_session_isolated": True,
        "duration_hours": 1.0, "site_timezone": "Asia/Taipei", **config,
    })
    conn = storage._get_conn()
    conn.executemany("INSERT INTO turbine_data (timestamp, turbine_id, session_id, scada_json) VALUES (?, ?, ?, ?)",
                     [(ts, tid, sid, scada) for ts, tid, scada in rows])
    conn.commit()
    return sid


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory: pytest.TempPathFactory) -> Dict[str, object]:
    """2 台 × 100 筆、03:03:20 起每 10 s（非對齊）；WT002 先寫（id 順序≠時間順序）；WT002 有 4 筆壞值。"""
    tmp = tmp_path_factory.mktemp("synthetic")
    storage = Storage(db_path=str(tmp / "farm.db"))
    start = datetime(2026, 1, 15, 3, 3, 20, tzinfo=timezone.utc).timestamp()
    rows: List[tuple] = []
    for tid in ("WT002", "WT001"):
        for i in range(100):
            ts = datetime.fromtimestamp(start + 10 * i, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
            scada: Dict[str, object] = {"WTUR_TotPwrAt": float(i), "WMET_WDirAbs": 355.0 if i % 2 else 5.0,
                                        "WTUR_TurSt": 6}
            text: Optional[str] = json.dumps(scada)
            if tid == "WT002" and i == 50:
                text = None
            elif tid == "WT002" and i == 51:
                text = json.dumps({"WTUR_TurSt": 6})
            elif tid == "WT002" and i == 52:
                text = json.dumps({"WTUR_TotPwrAt": "n/a", "WTUR_TurSt": 6})
            elif tid == "WT002" and i == 53:
                text = json.dumps({"WTUR_TotPwrAt": float("inf"), "WTUR_TurSt": 6})
            rows.append((ts, tid, text))
    # 設定的 time_step 故意與資料不符：manifest 的取樣週期以資料為準
    sid = _synthetic_scenario(storage, rows, time_step=30.0, wind_profile="主軸承考題")
    manifest = sp.export_scenario_pack(storage, sid, tmp / "pack")
    return {"storage": storage, "sid": sid, "dir": tmp / "pack", "manifest": manifest}


def test_out_of_order_writes_fall_back_to_time_order(synthetic: Dict[str, object],
                                                     generated: Dict[str, object]) -> None:
    storage: Storage = synthetic["storage"]  # type: ignore[assignment]
    assert storage.session_readings_in_id_order(synthetic["sid"]) is False  # type: ignore[arg-type]
    assert generated["storage"].session_readings_in_id_order(generated["scenario_id"]) is True  # type: ignore[attr-defined]
    raw = pq.read_table(synthetic["dir"] / sp.FILE_RAW).to_pylist()  # type: ignore[operator]
    keys = [(r["timestamp"], r["turbine_id"]) for r in raw]
    assert len(keys) == 200 and keys == sorted(keys)


def test_synthetic_manifest_uses_the_data(synthetic: Dict[str, object]) -> None:
    manifest = synthetic["manifest"]
    assert manifest["sample_period_s"] == 10.0, "取樣週期由資料推得，不信設定"  # type: ignore[index]
    assert manifest["wind_profile"] is None, "自訂風況文字可能寫明故障，不輸出"  # type: ignore[index]
    assert manifest["sim_start"] == "2026-01-15T03:03:20.000000Z"  # type: ignore[index]
    assert manifest["counts"]["events"] == 0 and manifest["counts"]["partial_windows"] == 2  # type: ignore[index]
    assert (synthetic["dir"] / sp.FILE_EVENTS).read_bytes() == b""  # type: ignore[operator]
    for name in (sp.FILE_MANIFEST, sp.FILE_TAGS, sp.FILE_ALARMS):
        assert b"\r\n" not in (synthetic["dir"] / name).read_bytes()  # type: ignore[operator]


def test_synthetic_stats_windows_and_missing_values(synthetic: Dict[str, object]) -> None:
    stats = {(r["window_start"].strftime("%H:%M"), r["turbine_id"]): r
             for r in pq.read_table(synthetic["dir"] / sp.FILE_STATS).to_pylist()}  # type: ignore[operator]
    assert sorted(stats) == [("03:00", "WT001"), ("03:00", "WT002"), ("03:10", "WT001"), ("03:10", "WT002")]
    head, full = stats[("03:00", "WT001")], stats[("03:10", "WT001")]
    assert (head["n_samples"], head["is_partial"]) == (40, True), "03:03:20 起：窗仍對齊整 10 分鐘"
    assert (full["n_samples"], full["is_partial"]) == (60, False)
    assert full["window_end"] - full["window_start"] == timedelta(minutes=10)
    assert (full[f"{POWER}_avg"], full[f"{POWER}_min"], full[f"{POWER}_max"]) == (69.5, 40.0, 99.0)
    # 圓統計：355 / 5 交替的平均是 0°（線性平均會是 180°），min / max 仍是線性值
    assert min(full[f"{WIND_DIR}_avg"], 360 - full[f"{WIND_DIR}_avg"]) < 1e-3
    assert full[f"{WIND_DIR}_std"] == pytest.approx(5.0, rel=2e-3)
    assert (full[f"{WIND_DIR}_min"], full[f"{WIND_DIR}_max"]) == (5.0, 355.0)
    # 缺值（NULL scada、缺 key、非數值、非有限值）不算進統計，但讀值筆數照算
    bad = stats[("03:10", "WT002")]
    valid = [float(i) for i in range(40, 100) if i not in (50, 51, 52, 53)]
    assert bad["n_samples"] == 60 and bad[f"{POWER}_avg"] == pytest.approx(sum(valid) / len(valid), rel=1e-6)
    assert bad[f"{POWER}_std"] == pytest.approx(float(np.std(valid, ddof=1)), rel=1e-5)
    # 整窗都沒有值的 tag → null
    assert full["Z72PLC__UI_Loc_WGEN_Analogue_GnSpd_avg"] is None
    raw = {(r["timestamp"].strftime("%H:%M:%S"), r["turbine_id"]): r
           for r in pq.read_table(synthetic["dir"] / sp.FILE_RAW).to_pylist()}  # type: ignore[operator]
    assert all(raw[("03:11:40", "WT002")][c] is None for c in (POWER, WIND_DIR, "Z72PLC__UI_Loc_WTUR_State_TurSt"))
    assert raw[("03:11:50", "WT002")][POWER] is None and raw[("03:11:50", "WT002")]["Z72PLC__UI_Loc_WTUR_State_TurSt"] == 6


def test_full_export_without_ground_truth_is_refused_before_writing(synthetic: Dict[str, object],
                                                                     tmp_path: Path) -> None:
    with pytest.raises(sp.ScenarioPackError, match="no ground truth"):
        sp.export_scenario_pack(synthetic["storage"], synthetic["sid"], tmp_path / "pack",  # type: ignore[arg-type]
                                include_ground_truth=True)
    assert list(tmp_path.iterdir()) == []


def test_allow_listed_events_without_a_contract_format_are_counted(tmp_path: Path) -> None:
    """白名單內、但合約還沒有對應格式的事件（新 PLC 事件種類）不輸出，manifest 記下丟了幾筆。"""
    storage = Storage(db_path=str(tmp_path / "farm.db"))
    rows = [("2026-01-15T03:00:10.000000+00:00", "WT001", json.dumps({"WTUR_TotPwrAt": 1.0}))]
    sid = _synthetic_scenario(storage, rows, time_step=10.0)
    for kind in ("alarm_raised", "brand_new_kind"):
        storage.record_event("fault", "plc", f"PLC {kind}", turbine_id="WT001", session_id=sid,
                             timestamp="2026-01-15T03:00:10+00:00",
                             payload={"kind": kind, "code": 262, "level": "A", "text": "x"})
    manifest = sp.export_scenario_pack(storage, sid, tmp_path / "pack")
    assert manifest["counts"]["events"] == 1 and manifest["counts"]["events_dropped"] == 1  # type: ignore[index]
    assert [e["event_type"] for e in _events(tmp_path / "pack")] == ["alarm_raised"]
