"""風場時區（WMOM-20261021-11）。

-03-c 起時間戳一律 UTC，但日夜 / 季節循環原本以「伺服器本地時區」取 hour / month：同一情境在 UTC 的 CI
與 UTC+8 的開發機上相位差 8 小時，資料包不可重現。改為風場時區（預設 Asia/Taipei）：

1. 同一個 UTC 時刻在任何伺服器時區下得到同一個風況（可重現）
2. 風況模型、模擬器依設定的時區換算；無效時區名稱 raise
3. 風場設定 ``timezone`` 欄：預設值、建立 / 更新時驗證、舊 DB 自動補欄
4. broker 以目前風場的時區建立模擬器（切換風場、批次資料集同樣）；session config 記下所用時區
5. code review 補強：跨月邊界、clone、``localtime``、非字串、存了無效時區時 fallback
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, List

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import pytest
from fastapi import HTTPException

from server.data_broker import DataBroker
from server.farm_registry import DEFAULT_FARM_TIMEZONE, FarmRegistry
from server.models import DataSourceConfig, DataSourceMode
from server.routers import farms as farms_ep
from simulator.engine import WindFarmSimulator
from server.storage import Storage
from simulator.time_utils import DEFAULT_SITE_TIMEZONE, site_timezone, to_site_naive
from wind_model import WindEnvironmentModel

T0 = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)


def _with_process_tz(name: str) -> None:
    os.environ["TZ"] = name
    time.tzset()


@pytest.fixture
def restore_tz() -> Iterator[None]:
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset 不可用（Windows）")
    previous = os.environ.get("TZ")
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()


def _day_of_weather(model: WindEnvironmentModel) -> List[float]:
    """一天每小時的溫度、濕度、穩定度、風向、風速（依序呼叫，包含 RNG 消耗）。"""
    values: List[float] = []
    for hour in range(24):
        ts = T0 + timedelta(hours=hour)
        values += [model.get_ambient_temp(ts), model.get_ambient_humidity(ts),
                   model.get_atmospheric_stability(ts), model.get_wind_direction(ts),
                   model.get_wind_speed(ts)]
    return values


# ── 可重現：與伺服器時區無關 ────────────────────────────────────────────────


def test_same_utc_instants_give_same_weather_on_any_server_timezone(restore_tz: None) -> None:
    runs = []
    for process_tz in ("UTC", "Asia/Taipei", "America/New_York"):
        _with_process_tz(process_tz)
        runs.append(_day_of_weather(WindEnvironmentModel(seed=7)))
    assert runs[0] == runs[1] == runs[2]


def test_simulator_bulk_data_is_independent_of_server_timezone(restore_tz: None) -> None:
    def run() -> List[dict]:
        sim = WindFarmSimulator(turbine_count=1)
        return [sim._run_one_step(T0 + timedelta(seconds=10 * i), 10.0)[0]["scada"] for i in range(60)]

    _with_process_tz("UTC")
    utc_run = run()
    _with_process_tz("Asia/Taipei")
    assert run() == utc_run


# ── 風況模型 / 模擬器的時區設定 ──────────────────────────────────────────────


def test_site_timezone_shifts_the_diurnal_phase() -> None:
    taipei = WindEnvironmentModel(seed=3)
    utc_site = WindEnvironmentModel(seed=3, site_timezone_name="UTC")
    ts = datetime(2026, 7, 1, 6, 0, tzinfo=timezone.utc)                  # 台北 14:00、UTC 06:00
    assert taipei.site_timezone_name == DEFAULT_SITE_TIMEZONE == "Asia/Taipei"
    assert taipei.get_atmospheric_stability(ts) == \
        WindEnvironmentModel(seed=3).get_atmospheric_stability(datetime(2026, 7, 1, 14, 0))
    assert taipei.get_atmospheric_stability(ts) != utc_site.get_atmospheric_stability(ts)


def test_unknown_site_timezone_is_rejected() -> None:
    with pytest.raises(ValueError):
        WindEnvironmentModel(site_timezone_name="Mars/Olympus_Mons")
    sim = WindFarmSimulator(turbine_count=1, site_timezone="Europe/Berlin")
    assert sim.wind_model.site_timezone_name == "Europe/Berlin"


# ── 風場設定 ────────────────────────────────────────────────────────────────


def test_farm_timezone_defaults_validates_and_updates(tmp_path: Path) -> None:
    registry = FarmRegistry(data_dir=tmp_path)
    assert registry.create_farm("a", "A").timezone == DEFAULT_FARM_TIMEZONE == DEFAULT_SITE_TIMEZONE
    assert registry.create_farm("b", "B", timezone="Europe/Berlin").timezone == "Europe/Berlin"
    with pytest.raises(ValueError):
        registry.create_farm("c", "C", timezone="Not/AZone")
    assert registry.update_farm("a", timezone="UTC").timezone == "UTC"
    with pytest.raises(ValueError):
        registry.update_farm("a", timezone="Not/AZone")
    assert FarmRegistry(data_dir=tmp_path).get_farm("b").timezone == "Europe/Berlin"


def test_legacy_farms_db_gets_default_timezone(tmp_path: Path) -> None:
    conn = sqlite3.connect(str(tmp_path / "farms.db"))
    conn.execute("""CREATE TABLE farms (
        farm_id TEXT PRIMARY KEY, name TEXT NOT NULL, turbine_count INTEGER NOT NULL DEFAULT 14,
        turbine_spec_json TEXT, wind_profile_json TEXT, grid_profile_json TEXT, layout_json TEXT,
        location TEXT, description TEXT, created_at TEXT NOT NULL, last_active_at TEXT,
        is_active INTEGER NOT NULL DEFAULT 0)""")
    conn.execute("INSERT INTO farms (farm_id, name, created_at) VALUES ('old', 'Old', '2026-10-01T00:00:00')")
    conn.commit()
    conn.close()
    assert FarmRegistry(data_dir=tmp_path).get_farm("old").timezone == DEFAULT_FARM_TIMEZONE


def test_farms_api_rejects_unknown_timezone_with_400(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry = FarmRegistry(data_dir=tmp_path)
    monkeypatch.setattr(farms_ep, "_get_registry", lambda: registry)
    created = asyncio.run(farms_ep.create_farm({"name": "Berlin", "farm_id": "berlin", "timezone": "Europe/Berlin"}))
    assert created["farm"]["timezone"] == "Europe/Berlin"
    with pytest.raises(HTTPException) as exc:
        asyncio.run(farms_ep.create_farm({"name": "Bad", "farm_id": "bad", "timezone": "Not/AZone"}))
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        asyncio.run(farms_ep.update_farm("berlin", {"timezone": "Not/AZone"}))
    assert exc.value.status_code == 400


# ── broker：以目前風場的時區建立模擬器 ───────────────────────────────────────


def test_broker_creates_simulator_with_active_farm_timezone(tmp_path: Path) -> None:
    registry = FarmRegistry(data_dir=tmp_path)
    registry.create_farm("berlin", "Berlin", timezone="Europe/Berlin")
    registry.set_active_farm("berlin")
    broker = DataBroker(farm_registry=registry)
    broker.start(DataSourceConfig(mode=DataSourceMode.SIMULATION), run_loop=False)
    try:
        assert broker.simulator is not None
        assert broker.simulator.wind_model.site_timezone_name == "Europe/Berlin"
    finally:
        broker.stop()


# ── code review 補強 ─────────────────────────────────────────────────────────


def test_to_site_naive_converts_aware_and_keeps_naive_wall_clock() -> None:
    taipei = site_timezone("Asia/Taipei")
    assert to_site_naive(datetime(2026, 6, 30, 20, 0, tzinfo=timezone.utc), taipei) == datetime(2026, 7, 1, 4, 0)
    assert to_site_naive(datetime(2026, 7, 1, 4, 0), taipei) == datetime(2026, 7, 1, 4, 0)


def test_seasonal_layers_use_the_site_month_across_a_month_boundary() -> None:
    aware = datetime(2026, 6, 30, 20, 0, tzinfo=timezone.utc)            # 台北 7/1 04:00
    site_wall_clock = datetime(2026, 7, 1, 4, 0)
    for getter in ("get_ambient_temp", "get_ambient_humidity", "get_wind_direction"):
        assert getattr(WindEnvironmentModel(seed=5), getter)(aware) == \
            getattr(WindEnvironmentModel(seed=5), getter)(site_wall_clock), getter
    # UTC 風場在同一時刻還是 6 月
    assert WindEnvironmentModel(seed=5, site_timezone_name="UTC").get_ambient_temp(aware) == \
        WindEnvironmentModel(seed=5).get_ambient_temp(datetime(2026, 6, 30, 20, 0))


def test_localtime_is_rejected_because_it_is_the_server_zone(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        site_timezone("localtime")
    with pytest.raises(ValueError):
        FarmRegistry(data_dir=tmp_path).create_farm("a", "A", timezone="localtime")


def test_clone_keeps_the_source_farm_timezone(tmp_path: Path) -> None:
    registry = FarmRegistry(data_dir=tmp_path)
    registry.create_farm("berlin", "Berlin", timezone="Europe/Berlin")
    assert registry.clone_farm("berlin", "berlin2", "Berlin 2").timezone == "Europe/Berlin"


def test_failed_timezone_update_leaves_the_database_writable(tmp_path: Path) -> None:
    registry = FarmRegistry(data_dir=tmp_path)
    registry.create_farm("a", "A")
    with pytest.raises(ValueError):
        registry.update_farm("a", name="Renamed", timezone="Not/AZone")
    assert registry.get_farm("a").name == "A"                           # 先驗證：其他欄位也沒寫入
    conn = sqlite3.connect(str(tmp_path / "farms.db"), timeout=0)          # 不等鎖：殘留交易會立刻失敗
    try:
        conn.execute("UPDATE farms SET description = 'x' WHERE farm_id = 'a'")
        conn.commit()
    finally:
        conn.close()


def test_farms_api_timezone_defaults_rejects_non_strings_and_patches(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry = FarmRegistry(data_dir=tmp_path)
    monkeypatch.setattr(farms_ep, "_get_registry", lambda: registry)
    created = asyncio.run(farms_ep.create_farm({"name": "Default", "farm_id": "default_tz"}))
    assert created["farm"]["timezone"] == DEFAULT_FARM_TIMEZONE
    for bad in (0, False, ["Asia/Taipei"]):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(farms_ep.create_farm({"name": "Bad", "farm_id": f"bad_{bad!s}", "timezone": bad}))
        assert exc.value.status_code == 400
    patched = asyncio.run(farms_ep.update_farm("default_tz", {"timezone": "America/New_York"}))
    assert patched["farm"]["timezone"] == "America/New_York"
    assert registry.get_farm("default_tz").timezone == "America/New_York"


def test_dataset_generation_uses_the_farm_timezone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry = FarmRegistry(data_dir=tmp_path)
    registry.create_farm("berlin", "Berlin", turbine_count=1, timezone="Europe/Berlin")
    monkeypatch.setattr(farms_ep, "_get_registry", lambda: registry)
    seen: List[str] = []
    real_init = WindFarmSimulator.__init__

    def spy_init(self: WindFarmSimulator, *args: object, **kwargs: object) -> None:
        real_init(self, *args, **kwargs)  # type: ignore[arg-type]  # 原樣轉交
        seen.append(self.wind_model.site_timezone_name)

    monkeypatch.setattr(WindFarmSimulator, "__init__", spy_init)
    result = asyncio.run(farms_ep.generate_dataset("berlin", {"duration_hours": 0.01, "time_step": 10.0}))
    assert seen == ["Europe/Berlin"]
    sessions = Storage(db_path=str(registry.get_farm_db_path("berlin"))).get_sessions()
    assert [s["config"]["site_timezone"] for s in sessions if s["id"] == result["session_id"]] == ["Europe/Berlin"]


def test_switch_farm_rebuilds_the_simulator_with_the_new_timezone(tmp_path: Path) -> None:
    registry = FarmRegistry(data_dir=tmp_path)
    registry.create_farm("taipei", "Taipei")
    registry.create_farm("berlin", "Berlin", timezone="Europe/Berlin")
    registry.set_active_farm("taipei")
    broker = DataBroker(farm_registry=registry)
    broker.start(DataSourceConfig(mode=DataSourceMode.SIMULATION), run_loop=False)
    try:
        assert broker.simulator.wind_model.site_timezone_name == "Asia/Taipei"
        assert broker.switch_farm("berlin")
        assert broker.simulator.wind_model.site_timezone_name == "Europe/Berlin"
        live = [s for s in broker.storage.get_sessions() if s["id"] == broker._session_id]
        assert [s["config"]["site_timezone"] for s in live] == ["Europe/Berlin"]
    finally:
        broker.stop()


def test_broker_falls_back_to_default_for_an_invalid_stored_timezone(tmp_path: Path) -> None:
    registry = FarmRegistry(data_dir=tmp_path)
    registry.create_farm("broken", "Broken")
    conn = sqlite3.connect(str(tmp_path / "farms.db"))
    conn.execute("UPDATE farms SET timezone = 'Not/AZone' WHERE farm_id = 'broken'")  # 手改 DB / 缺 tzdata
    conn.commit()
    conn.close()
    registry.set_active_farm("broken")
    broker = DataBroker(farm_registry=registry)
    broker.start(DataSourceConfig(mode=DataSourceMode.SIMULATION), run_loop=False)
    try:
        assert broker.simulator.wind_model.site_timezone_name == DEFAULT_SITE_TIMEZONE
    finally:
        broker.stop()
