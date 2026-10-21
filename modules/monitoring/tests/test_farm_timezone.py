"""風場時區（WMOM-20261021-11）。

-03-c 起時間戳一律 UTC，但日夜 / 季節循環原本以「伺服器本地時區」取 hour / month：同一情境在 UTC 的 CI
與 UTC+8 的開發機上相位差 8 小時，資料包不可重現。改為風場時區（預設 Asia/Taipei）：

1. 同一個 UTC 時刻在任何伺服器時區下得到同一個風況（可重現）
2. 風況模型、模擬器依設定的時區換算；無效時區名稱 raise
3. 風場設定 ``timezone`` 欄：預設值、建立 / 更新時驗證、舊 DB 自動補欄
4. broker 以目前風場的時區建立模擬器；情境 session 記下所用時區
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
from simulator.time_utils import DEFAULT_SITE_TIMEZONE
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
