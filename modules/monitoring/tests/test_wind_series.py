"""實測風況匯入（WMOM-20261125-07，DEC-20261127-03）。

1. 讀 CSV：自動辨識欄位、沒有時區的時間是風場時區、超出範圍當缺值、重複的時間、標準差換紊流強度、換算到輪轂
   高度、錯誤訊息。
2. 取值：線性內插、風向走較短的一邊、過長的缺口回到模型、循環的接縫、停在最後一筆、播完回到模型、絕對時間。
3. 風況模型：下一步開始播（漸變、不跳）、手動設定優先、停掉回到模型、亂數抽樣次數和模型一樣、存檔還原後接著播、
   實測的氣溫與紊流強度進到物理。
4. API：匯入、列出、套用、停止、刪除；只給主管；情境記下的風況是 null。
"""

from __future__ import annotations

import pickle
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import numpy as np
import pytest

from simulator.engine import WindFarmSimulator
from simulator.wind_series import MAX_ROWS, MeasuredWindPlayback, MeasuredWindSeries, WindSeriesError, parse_csv
from wind_model import WindEnvironmentModel

UTC = timezone.utc
T0 = datetime(2026, 3, 1, tzinfo=UTC)
K13_METOCEAN = PROJECT_ROOT / "modules" / "cost" / "data" / "demo" / "k13_metocean.csv"


def _csv(rows: List[str], header: str = "timestamp,wind_speed,wind_direction,ambient_temp,ti") -> str:
    return "\n".join([header, *rows])


def _ramp_series(hours: int = 6, step_min: int = 10) -> MeasuredWindSeries:
    """每 10 分鐘一筆：風速 5 → 15 m/s 線性上升，風向 250°，氣溫 8 °C，TI 0.2。"""
    n = hours * 60 // step_min + 1
    rows = [f"{(T0 + timedelta(minutes=step_min * i)).isoformat()},{5 + 10 * i / (n - 1):.4f},250,8,0.2"
            for i in range(n)]
    return parse_csv(_csv(rows), timezone_name="UTC")


# ── 1. 讀 CSV ─────────────────────────────────────────────────────────────


def test_parse_detects_columns_and_reads_naive_times_in_the_farm_time_zone() -> None:
    text = "﻿Time,WS,Dir,Temperature,WS_Std,RH,Pressure\n" \
           "2026-03-01 08:00,10,350,15,1.5,80,1010\n" \
           "2026-03-01 08:10,12,10,15.5,2.4,82,1009\n"
    series = parse_csv(text, timezone_name="Asia/Taipei")
    assert series.times[0] == datetime(2026, 3, 1, 0, 0, tzinfo=UTC).timestamp(), "沒有時區＝風場時區（UTC+8）"
    assert set(series.values) == {"wind_speed", "wind_direction", "ambient_temp", "turbulence_intensity",
                                  "humidity", "pressure_hpa"}
    assert series.values["turbulence_intensity"].tolist() == pytest.approx([0.15, 0.2]), "標準差 ÷ 風速"
    assert series.step_s == 600 and series.summary["rows"] == 2


def test_parse_cleans_bad_values_and_reports_them() -> None:
    speeds = ["8", "-3", "", "200"] + ["9"] * 26
    rows = [f"{(T0 + timedelta(minutes=10 * i)).isoformat()},{v},250,8,0.1" for i, v in enumerate(speeds)]
    rows.append(rows[0])          # 重複的時間
    rows.insert(2, "not-a-time,8,250,8,0.1")
    series = parse_csv(_csv(rows), timezone_name="UTC")
    summary = series.summary
    assert summary["rows"] == 30 and summary["duplicates_dropped"] == 1 and summary["unreadable_times"] == 1
    assert summary["out_of_range"] == {"wind_speed": 2} and summary["missing"]["wind_speed"] == 3
    assert np.isnan(series.values["wind_speed"][1:4]).all()
    assert summary["warnings"] == [], "零星超出範圍不警告"


def test_parse_rejects_a_file_whose_times_are_mostly_unreadable() -> None:
    """日在前（5/1/2024）讀不懂：超過 5% 的列讀不懂就整份不收，不是悄悄丟掉。"""
    rows = [f"{(T0 + timedelta(minutes=10 * i)).isoformat()},8" for i in range(20)]
    rows += [f"{d}/3/2026 08:00,8" for d in range(13, 18)]
    with pytest.raises(WindSeriesError, match="年在前"):
        parse_csv(_csv(rows, "timestamp,wind_speed"), timezone_name="UTC")


def test_parse_reads_common_export_layouts() -> None:
    """日期與時間分兩欄、沒補零的斜線日期帶秒、分號分隔、單位不對時警告。"""
    split = "Date;Time;WS;Pressure\n2026/3/1;0:00:00;8;101300\n2026/3/1;0:10:00;9;101250\n2026/3/1;0:20:00;10;101200\n"
    series = parse_csv(split, timezone_name="UTC")
    assert series.times[0] == T0.timestamp() and series.times[2] - series.times[0] == 1200
    assert "pressure_hpa" not in series.values, "氣壓用 Pa：全部超出範圍"
    assert series.summary["warnings"] and "pressure_hpa" in series.summary["warnings"][0]


def test_parse_scales_the_wind_speed_to_hub_height() -> None:
    rows = [f"{T0.isoformat()},10", f"{(T0 + timedelta(minutes=10)).isoformat()},10"]
    series = parse_csv(_csv(rows, "timestamp,wind_speed"), timezone_name="UTC", height_m=10, hub_height_m=64,
                       shear_exponent=0.14)
    assert series.values["wind_speed"][0] == pytest.approx(10 * (64 / 10) ** 0.14)
    assert series.summary["height_scale"] == pytest.approx((64 / 10) ** 0.14, abs=1e-4)


@pytest.mark.parametrize(("text", "kwargs", "message"), [
    ("", {}, "空"),
    ("a,b\n1,2\n", {}, "時間"),
    ("timestamp,foo\n2026-03-01T00:00,1\n", {}, "風速"),
    (f"timestamp,wind_speed\n{T0.isoformat()},5\n", {}, "兩筆"),
    (f"timestamp,wind_speed\n{T0.isoformat()},5\n", {"timezone_name": "Mars/Base"}, "時區"),
    ("timestamp,wind_speed\n", {"columns": {"wind_speed": "nope"}}, "nope"),
    ("timestamp,wind_speed\n", {"columns": {"gust": "x"}}, "不認得"),
])
def test_parse_errors_say_what_is_wrong(text: str, kwargs: dict, message: str) -> None:
    with pytest.raises(WindSeriesError, match=message):
        parse_csv(text, **{"timezone_name": "UTC", **kwargs})


def test_parse_reads_the_k13_metocean_sample() -> None:
    """repo 裡就有的實測資料：K13 平台 1995–2004 每 3 小時的風速（成本模組的天候窗資料）。"""
    series = parse_csv(K13_METOCEAN.read_text(encoding="utf-8"), columns={"wind_speed": "vw"}, timezone_name="UTC")
    assert series.summary["rows"] == 29224 and series.step_s == 3 * 3600
    assert series.summary["long_gaps"] == 0 and 5 < series.summary["wind_speed_mean"] < 10
    assert series.summary["rows"] < MAX_ROWS


# ── 2. 取值 ───────────────────────────────────────────────────────────────


def test_interpolation_direction_and_gaps() -> None:
    rows = [f"{T0.isoformat()},10,350,10,0.1", f"{(T0 + timedelta(minutes=10)).isoformat()},20,10,20,0.1",
            f"{(T0 + timedelta(minutes=20)).isoformat()},20,10,20,0.1",
            f"{(T0 + timedelta(minutes=30)).isoformat()},20,10,20,0.1",
            f"{(T0 + timedelta(hours=10)).isoformat()},5,90,5,0.1"]
    series = parse_csv(_csv(rows), timezone_name="UTC", max_gap_minutes=60)
    mid = T0.timestamp() + 300
    assert series.value_at("wind_speed", mid) == pytest.approx(15.0)
    assert series.value_at("ambient_temp", mid) == pytest.approx(15.0)
    assert series.value_at("wind_direction", mid) == pytest.approx(0.0, abs=1e-9) or \
        series.value_at("wind_direction", mid) == pytest.approx(360.0, abs=1e-9), "350° 與 10° 之間是 0°，不是 180°"
    assert series.value_at("wind_speed", T0.timestamp() + 5 * 3600) is None, "缺了 10 小時：回到模型的風況"
    assert series.value_at("wind_speed", T0.timestamp() - 1) is None


@pytest.mark.parametrize("at_end", ["loop", "hold", "auto"])
def test_what_happens_after_the_series_ends(at_end: str) -> None:
    series = _ramp_series(hours=1)       # 7 筆：5 → 15 m/s，一個小時
    playback = MeasuredWindPlayback(series=series, at_end=at_end)
    start = 1_900_000_000.0
    playback.anchor(start)
    assert playback.value("wind_speed", start) == pytest.approx(5.0)
    assert playback.value("wind_speed", start + 3600) == pytest.approx(15.0)
    after = playback.value("wind_speed", start + 3600 + 300)    # 播完之後 5 分鐘
    if at_end == "loop":
        assert after == pytest.approx(10.0), "接縫：最後一筆 15 到第一筆 5 之間，一個取樣間隔內插"
        assert playback.value("wind_speed", start + 3600 + 600) == pytest.approx(5.0), "從頭再播"
    elif at_end == "hold":
        assert after == pytest.approx(15.0)
    else:
        assert after is None


def test_loop_seam_does_not_bridge_a_quantity_missing_at_the_edges() -> None:
    rows = [f"{(T0 + timedelta(minutes=10 * i)).isoformat()},8,{250 if i < 20 else ''},8,0.1" for i in range(60)]
    series = parse_csv(_csv(rows), timezone_name="UTC", max_gap_minutes=60)
    playback = MeasuredWindPlayback(series=series)
    playback.anchor(0.0)
    seam = series.end - series.start + 300
    assert playback.value("wind_speed", seam) == pytest.approx(8.0)
    assert playback.value("wind_direction", seam) is None, "風向最後 6 小時都缺：接縫不接，回到模型"


def test_replay_offset_and_absolute_alignment() -> None:
    series = _ramp_series(hours=6)
    replay = MeasuredWindPlayback(series=series, start_offset_s=3 * 3600)
    replay.anchor(1_900_000_000.0)
    assert replay.value("wind_speed", 1_900_000_000.0) == pytest.approx(10.0), "從序列的第 3 小時開始播"
    absolute = MeasuredWindPlayback(series=series, alignment="absolute", at_end="auto")
    assert absolute.value("wind_speed", (T0 + timedelta(hours=6)).timestamp()) == pytest.approx(15.0)
    assert absolute.value("wind_speed", 1_900_000_000.0) is None
    with pytest.raises(WindSeriesError):
        MeasuredWindPlayback(series=series, start_offset_s=7 * 3600)
    with pytest.raises(WindSeriesError):
        MeasuredWindPlayback(series=series, alignment="sideways")


def test_series_round_trips_through_the_database_format() -> None:
    series = _ramp_series()
    again = MeasuredWindSeries.from_npz(series.to_npz(), series.summary)
    assert again.times.tolist() == series.times.tolist() and again.step_s == series.step_s
    assert all(np.array_equal(again.values[k], series.values[k], equal_nan=True) for k in series.values)


# ── 3. 風況模型 ───────────────────────────────────────────────────────────


def _steps(model: WindEnvironmentModel, start: datetime, seconds: int) -> List[float]:
    out = []
    for i in range(seconds):
        moment = start + timedelta(seconds=i)
        out.append(model.get_wind_speed(moment))
        model.get_wind_direction(moment)
        model.get_ambient_temp(moment)
        model.get_ambient_humidity(moment)
    return out


def _rng_state(model: WindEnvironmentModel) -> tuple:
    main, weather = model._rng.get_state(), model._weather._rng.get_state()
    return (main[1].tobytes(), main[2:], weather[1].tobytes(), weather[2:], model._mesoscale_state)  # type: ignore[index]


def test_measured_wind_drives_the_model_after_a_smooth_transition() -> None:
    model, twin = WindEnvironmentModel(seed=4), WindEnvironmentModel(seed=4)
    _steps(model, T0, 60)
    _steps(twin, T0, 60)
    start = T0 + timedelta(seconds=60)
    model.set_measured(MeasuredWindPlayback(series=_ramp_series()))
    assert model.get_status()["mode"] == "measured" and model.get_status()["measured"]["pending"] is True
    speeds = _steps(model, start, 600)
    auto = _steps(twin, start, 600)
    assert abs(speeds[0] - auto[0]) < 0.05, "第一步緊接著上一步的風速，不跳"
    playback = model.measured
    assert playback is not None and playback.anchor_sim == start.timestamp(), "開始播＝套用後的下一步（模擬時間）"
    assert speeds[-1] == pytest.approx(playback.value("wind_speed", (start + timedelta(seconds=599)).timestamp()))
    assert speeds[-1] == pytest.approx(5 + 10 * 599 / (6 * 3600), abs=1e-3)
    assert _rng_state(model) == _rng_state(twin), "亂數抽樣次數和模型的風況一樣"
    moment = start + timedelta(seconds=600)
    assert abs(model.get_ambient_temp(moment) - 8.0) < 2.0 and abs(model.get_wind_direction(moment) - 250) < 10


def test_manual_settings_take_precedence_and_clear_returns_to_the_model() -> None:
    model, twin = WindEnvironmentModel(seed=8), WindEnvironmentModel(seed=8)
    model.set_measured(MeasuredWindPlayback(series=_ramp_series()))
    _steps(model, T0, 60)
    model.set_override(wind_speed=20.0)
    assert _steps(model, T0 + timedelta(seconds=60), 60)[-1] == 20.0, "手動覆寫優先"
    model.clear_override()
    back = _steps(model, T0 + timedelta(seconds=120), 60)
    assert back[-1] == pytest.approx(model.measured.value(  # type: ignore[union-attr]
        "wind_speed", (T0 + timedelta(seconds=179)).timestamp())), "清掉覆寫：回到實測序列"
    model.clear_measured()
    _steps(model, T0 + timedelta(seconds=180), 60)
    assert model.measured is None and model.get_status()["mode"] == "auto"
    # 對照：同樣的手動設定、沒有實測序列（覆寫期間模型的風況本來就不前進，兩邊要經歷一樣的設定）
    _steps(twin, T0, 60)
    twin.set_override(wind_speed=20.0)
    _steps(twin, T0 + timedelta(seconds=60), 60)
    twin.clear_override()
    _steps(twin, T0 + timedelta(seconds=120), 120)
    assert model.get_wind_speed(T0 + timedelta(seconds=240)) == twin.get_wind_speed(T0 + timedelta(seconds=240)), \
        "停掉之後就是模型的風況"


def test_apply_and_clear_before_the_next_step_both_take_effect_in_order() -> None:
    """API 執行緒連續兩次設定（套用又停掉）：兩個都依序套用，不會有一個被蓋掉（code review）。"""
    model = WindEnvironmentModel(seed=2)
    _steps(model, T0, 10)
    model.set_measured(MeasuredWindPlayback(series=_ramp_series()))
    model.clear_measured()
    assert model.get_status()["mode"] == "auto", "最後一個待套用的是停掉"
    _steps(model, T0 + timedelta(seconds=10), 5)
    assert model.measured is None and not model._measured_changes
    model.set_measured(MeasuredWindPlayback(series=_ramp_series(), at_end="hold"))
    model.set_measured(MeasuredWindPlayback(series=_ramp_series(), at_end="auto"))
    _steps(model, T0 + timedelta(seconds=15), 1)
    assert model.measured is not None and model.measured.at_end == "auto"


def test_a_batch_replays_the_series_from_its_own_start(monkeypatch) -> None:
    """即時模擬已經播了一段的序列，批次裡從序列的開頭重新播：批次播到序列的哪裡不看 Live 跑了多久（code review）。"""
    import simulator.engine as engine_mod

    batch_start = T0 + timedelta(days=30)
    monkeypatch.setattr(engine_mod, "utc_now", lambda: batch_start)
    anchors = []
    for live_seconds in (10, 400):
        sim = WindFarmSimulator(turbine_count=2)
        sim.wind_model.set_measured(MeasuredWindPlayback(series=_ramp_series()))
        for i in range(live_seconds):
            sim._run_one_step(T0 + timedelta(seconds=i), 1.0)
        assert sim.wind_model.measured is not None and sim.wind_model.measured.anchor_sim == T0.timestamp()
        seen: List[float] = []
        sim.generate_bulk(0.05, time_step=10.0, callback=lambda rows: seen.append(
            sim.wind_model.measured.value(  # type: ignore[union-attr]
                "wind_speed", datetime.fromisoformat(str(rows[0]["timestamp"])).timestamp())))
        anchor = sim.wind_model.measured.anchor_sim
        assert anchor is not None and batch_start.timestamp() <= anchor < batch_start.timestamp() + 60
        anchors.append(anchor)
        assert seen[0] == pytest.approx(5.0, abs=0.01), "批次的第一步在序列的開頭"
    assert anchors[0] == anchors[1]


def test_playback_survives_a_checkpoint_round_trip() -> None:
    sim = WindFarmSimulator(turbine_count=2)
    sim.wind_model.set_measured(MeasuredWindPlayback(series=_ramp_series()))
    for i in range(30):
        sim._run_one_step(T0 + timedelta(seconds=i), 1.0)
    state = sim.checkpoint_state()
    restored = WindFarmSimulator(turbine_count=2)
    restored.restore_state(state)
    tail = [sim._run_one_step(T0 + timedelta(seconds=30 + i), 1.0) for i in range(20)]
    again = [restored._run_one_step(T0 + timedelta(seconds=30 + i), 1.0) for i in range(20)]
    assert pickle.dumps(tail) == pickle.dumps(again), "還原後接著播，逐位元相同"
    assert restored.wind_model.measured is not None and restored.wind_model.measured.anchor_sim == T0.timestamp()


def test_measured_temperature_and_turbulence_reach_the_physics() -> None:
    sim = WindFarmSimulator(turbine_count=2)
    sim.wind_model.set_measured(MeasuredWindPlayback(series=_ramp_series()))
    readings = []
    for i in range(120):
        readings = sim._run_one_step(T0 + timedelta(seconds=i), 1.0)
    assert abs(readings[0]["scada"]["WMET_TmpOutside"] - 8.0) < 2.0
    assert sim.wind_model.effective_turbulence(T0 + timedelta(seconds=119), 1.4) == pytest.approx(0.2), \
        "實測的紊流強度不再乘穩定度的倍數"
    sim.wind_model.set_override(turbulence=0.05, wind_speed=9.0)
    assert sim.wind_model.effective_turbulence(T0, 1.4) == pytest.approx(0.05 * 1.4), "手動設定時用設定的"


# ── 4. API ────────────────────────────────────────────────────────────────


def test_api_import_apply_and_clear(tmp_path, monkeypatch) -> None:
    import asyncio

    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    from server.models import WindSeriesApplyRequest, WindSeriesImportRequest
    from server.routers import config as config_router
    from server.storage import Storage

    class _Broker:
        def __init__(self) -> None:
            self.storage = Storage(db_path=str(tmp_path / "farm.db"))
            self.simulator = WindFarmSimulator(turbine_count=2)
            self.events: List[dict] = []

        def close_open_events(self, *_args, **_kwargs) -> None:
            return None

        def record_event(self, **kwargs) -> None:
            self.events.append(kwargs)

    broker = _Broker()
    monkeypatch.setattr(config_router, "get_broker", lambda: broker)
    rows = [f"{(T0 + timedelta(minutes=10 * i)).isoformat()},{8 + i % 3},270,10,0.1" for i in range(12)]
    made = asyncio.run(config_router.import_wind_series(
        WindSeriesImportRequest(name="站 A 三月", csv=_csv(rows), heightM=10)))
    assert made["summary"]["rows"] == 12 and made["summary"]["hub_height_m"] == 64.0, "預設用機組的輪轂高度"
    listed = asyncio.run(config_router.list_wind_series())["series"]
    assert [s["name"] for s in listed] == ["站 A 三月"] and "data" not in listed[0]
    status = asyncio.run(config_router.apply_wind_series(made["id"], WindSeriesApplyRequest(atEnd="hold")))
    assert status["mode"] == "measured" and status["measured"]["at_end"] == "hold"
    assert broker.events[-1]["source"] == "config", "設定事件不是可觀測事件"
    assert config_router._applied_wind_profile(status) is None, "情境記下的風況：依實測序列是 null（合約）"
    with pytest.raises(HTTPException) as bad:
        asyncio.run(config_router.apply_wind_series(made["id"], WindSeriesApplyRequest(alignment="nope")))
    assert bad.value.status_code == 422
    with pytest.raises(HTTPException) as broken:
        asyncio.run(config_router.import_wind_series(WindSeriesImportRequest(name="x", csv="a,b\n1,2")))
    assert broken.value.status_code == 422
    broker.simulator = None
    with pytest.raises(HTTPException) as no_hub:
        asyncio.run(config_router.import_wind_series(
            WindSeriesImportRequest(name="x", csv=_csv(rows), heightM=10)))
    assert no_hub.value.status_code == 422 and "輪轂" in no_hub.value.detail, "不能換算時不悄悄當成換算過"
    broker.simulator = WindFarmSimulator(turbine_count=2)
    asyncio.run(config_router.apply_wind_series(made["id"], WindSeriesApplyRequest()))
    asyncio.run(config_router.clear_wind())
    broker.simulator._run_one_step(T0, 1.0)
    assert broker.simulator.wind_model.get_status()["mode"] == "auto", "回到自動：實測序列也停"
    assert asyncio.run(config_router.delete_wind_series(made["id"]))["status"] == "ok"
    with pytest.raises(HTTPException):
        asyncio.run(config_router.delete_wind_series(made["id"]))

    monkeypatch.setenv("WMOM_AUTH_ENFORCE", "true")
    app = FastAPI()
    app.include_router(config_router.router)
    client = TestClient(app)
    assert client.post("/api/config/wind/series", json={"name": "x", "csv": "a"}).status_code in (401, 403)
    assert client.post("/api/config/wind/series/1/apply", json={}).status_code in (401, 403)
    assert client.delete("/api/config/wind/series/1").status_code in (401, 403)
