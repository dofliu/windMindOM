"""風況覆寫 / 風況 profile 的漸變只用模擬時間，不讀實際時間（WMOM-20261126-03）。

風況模型沒有自己的時鐘：``set_override`` / ``set_profile`` 把「漸變起點的自動風況」與 ramp profile 的起點標記為
待定，由下一步的 ``get_wind_speed`` 用那一步的模擬時間定下來。修正前這兩個量在設定的當下用 ``utc_now()`` 取，
批次的模擬時間固定、起點卻跟著實際時間變。

1. 守門：同樣的設定、不同的實際時間，批次產生的資料逐位元相同
2. 漸變起點＝那一步模擬時間的自動風況（從當下的風況接著漸變、不跳一下），亂數抽樣次數不變；設定之後、
   下一步之前又改設定的各種順序；另一條執行緒的設定落在一步的中間時不會讀到還沒定的起點
3. ramp profile 的起點是模擬時間：模擬時間與實際時間差很遠時，漸變完成後風速停在目標值
4. 待定的狀態跟著存檔 / 還原（重啟續跑）

「實際時間」以替換 ``simulator.time_utils`` 裡的 ``datetime`` 來設定：所有經 ``utc_now()`` 讀時鐘的地方都讀到
測試給的時刻（monitoring 一律經 ``time_utils`` 讀時鐘——時間戳守則），不只風況模型。批次的起點另外釘住
（``generate_bulk`` 以引擎的 ``utc_now()`` 為起點）。
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import pytest

import simulator.engine as engine_mod
import simulator.grid_model as grid_model_mod
import simulator.time_utils as time_utils
from simulator.engine import WindFarmSimulator
from wind_model import WindEnvironmentModel

UTC = timezone.utc
T0 = datetime(2026, 3, 1, tzinfo=UTC)  # 批次起點（模擬時間）


class _RealClock(datetime):
    """替換 ``time_utils`` 裡的 ``datetime``：``utc_now()`` 讀到的「實際時間」由測試決定。"""

    fake_now: datetime = T0

    @classmethod
    def now(cls, tz: Optional[tzinfo] = None) -> datetime:
        return cls.fake_now.astimezone(tz) if tz is not None else cls.fake_now.replace(tzinfo=None)


def _set_real_time(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    monkeypatch.setattr(time_utils, "datetime", _RealClock)
    monkeypatch.setattr(_RealClock, "fake_now", moment)
    # 前提：以名稱匯入 utc_now 的模組也讀到這個時刻（否則下面的比對沒有比到東西）
    assert time_utils.utc_now() == grid_model_mod.utc_now() == moment


# 會用到漸變的每一種設定方式（風速覆寫、固定 profile、ramp profile、設了又清掉）
def _override(wm: WindEnvironmentModel) -> None:
    wm.set_override(wind_speed=13.0, wind_direction=250.0, ambient_temp=25.0)


def _override_then_auto(wm: WindEnvironmentModel) -> None:
    wm.set_override(wind_speed=13.0)
    wm.clear_override()


def _override_twice(wm: WindEnvironmentModel) -> None:
    wm.set_override(wind_speed=13.0)
    wm.set_override(wind_speed=9.0)


def _ramp_then_rated(wm: WindEnvironmentModel) -> None:
    wm.set_profile("ramp_up")
    wm.set_profile("rated")


def _profile(name: str) -> Callable[[WindEnvironmentModel], None]:
    return lambda wm: wm.set_profile(name)


def _measured(alignment: str) -> Callable[[WindEnvironmentModel], None]:
    """實測風況序列（WMOM-20261125-07）：開始播的時刻由下一步的模擬時間定，不讀實際時間。"""
    def apply(wm: WindEnvironmentModel) -> None:
        from simulator.wind_series import MeasuredWindPlayback, parse_csv

        lines = ["timestamp,wind_speed,wind_direction,ambient_temp,ti"]
        for i in range(48):
            moment = T0 + timedelta(minutes=10 * i)
            lines.append(f"{moment.isoformat()},{6 + 6 * ((i % 12) / 12):.2f},{(250 + 5 * i) % 360},{12 + i % 5},0.12")
        series = parse_csv("\n".join(lines), timezone_name="UTC")
        wm.set_measured(MeasuredWindPlayback(series=series, alignment=alignment))
    return apply


SETTINGS: Dict[str, Callable[[WindEnvironmentModel], None]] = {
    "measured_replay": _measured("replay"),
    "measured_absolute": _measured("absolute"),
    "override": _override,
    "override_then_auto": _override_then_auto,
    "override_twice": _override_twice,
    "rated": _profile("rated"),
    "gusty": _profile("gusty"),
    "ramp_up": _profile("ramp_up"),
    "ramp_down": _profile("ramp_down"),
    "ramp_then_rated": _ramp_then_rated,
}
# 實際時間：基準、同一分鐘內、跨過整分鐘、另一個季節（比模擬時間晚）、比模擬時間早
REAL_TIMES = (
    datetime(2026, 7, 4, 9, 30, 5, tzinfo=UTC),
    datetime(2026, 7, 4, 9, 30, 55, tzinfo=UTC),
    datetime(2026, 7, 4, 9, 31, 5, tzinfo=UTC),
    datetime(2026, 12, 24, 21, 0, 0, tzinfo=UTC),
    datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC),
)


def _bulk(monkeypatch: pytest.MonkeyPatch, real_now: datetime, apply: Callable[[WindEnvironmentModel], None],
          hours: float, start: datetime = T0) -> List[dict]:
    monkeypatch.setattr(engine_mod, "utc_now", lambda: start)
    _set_real_time(monkeypatch, real_now)
    sim = WindFarmSimulator(turbine_count=2)
    apply(sim.wind_model)
    rows: List[dict] = []
    sim.generate_bulk(hours, time_step=10.0, callback=rows.extend)
    return rows


# ── 1. 守門：批次不隨實際時間變 ───────────────────────────────────────────────


@pytest.mark.parametrize("setting", sorted(SETTINGS))
def test_batch_with_a_wind_setting_is_bit_identical_whatever_the_real_time(
        setting: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """同樣的設定、同樣的批次起點，在任何實際時間產生的資料都相同。

    0.2 小時＝144 個物理子步：涵蓋 30 步的覆寫漸變，也涵蓋 ramp profile 的 120 步漸變與之後依經過時間算的那一段。
    """
    runs = [_bulk(monkeypatch, real_now, SETTINGS[setting], hours=0.2) for real_now in REAL_TIMES]
    assert len(runs[0]) == 2 * 72
    for real_now, rows in zip(REAL_TIMES[1:], runs[1:]):
        assert rows == runs[0], f"實際時間 {real_now.isoformat()} 產生的資料與 {REAL_TIMES[0].isoformat()} 不同"


def test_the_batch_does_depend_on_its_simulation_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """反向確認：漸變起點跟著模擬時間（批次起點換一個季節，前幾分鐘的風速就不同），不是固定值。"""
    winter = _bulk(monkeypatch, REAL_TIMES[0], _override, hours=0.02, start=datetime(2026, 1, 10, 12, tzinfo=UTC))
    summer = _bulk(monkeypatch, REAL_TIMES[0], _override, hours=0.02, start=datetime(2026, 7, 10, 20, tzinfo=UTC))
    first = [rows[0]["scada"]["WMET_WSpeedNac"] for rows in (winter, summer)]
    assert abs(first[0] - first[1]) > 1.0, first


# ── 2. 漸變起點＝那一步模擬時間的自動風況 ─────────────────────────────────────


def _random_state(model: WindEnvironmentModel) -> Tuple[object, ...]:
    """風況模型裡會隨亂數抽樣前進的狀態（兩個亂數產生器、天氣系統、中尺度狀態）。"""
    main, weather = model._rng.get_state(), model._weather._rng.get_state()
    return (main[1].tobytes(), main[2:], weather[1].tobytes(), weather[2:],  # type: ignore[index]  # legacy tuple
            model._weather._pressure_state, model._weather._front_timer, model._mesoscale_state)


@pytest.mark.parametrize("sim_start", [
    datetime(2026, 1, 10, 12, tzinfo=UTC),   # 冬季、台灣晚上
    datetime(2026, 7, 10, 20, tzinfo=UTC),   # 夏季、台灣清晨
])
def test_transition_starts_from_the_auto_wind_at_the_simulation_time(
        sim_start: datetime, monkeypatch: pytest.MonkeyPatch) -> None:
    """模擬時鐘與實際時間不同（加速運轉、補跑、批次）時，覆寫仍從模擬當下的風況接著漸變，不跳一下。"""
    _set_real_time(monkeypatch, datetime(2026, 4, 1, 6, tzinfo=UTC))  # 實際時間在別的季節、別的時刻
    model, twin = WindEnvironmentModel(seed=3), WindEnvironmentModel(seed=3)
    for i in range(1, 61):
        assert model.get_wind_speed(sim_start + timedelta(seconds=i)) == twin.get_wind_speed(
            sim_start + timedelta(seconds=i))

    model.set_override(wind_speed=13.0)
    assert _random_state(model) == _random_state(twin), "設定的當下不取自動風況、不抽亂數"

    step = sim_start + timedelta(seconds=61)
    auto_now = twin.get_wind_speed(step)          # 沒有覆寫時，這一步的風速
    first = model.get_wind_speed(step)
    assert model._transition_from == auto_now, "起點＝這一步模擬時間的自動風況"
    assert abs(first - auto_now) < 0.05, "漸變的第一步緊接著當下的風況"
    assert _random_state(model) == _random_state(twin), "取起點的亂數抽樣＝自動風況走一步"

    speeds = [first] + [model.get_wind_speed(step + timedelta(seconds=i)) for i in range(1, 40)]
    gaps = [abs(v - 13.0) for v in speeds]   # 與覆寫值的距離只減不增（自動風況高於或低於覆寫值都成立）
    assert speeds[-1] == 13.0 and all(b <= a for a, b in zip(gaps, gaps[1:])), "單調漸變到覆寫值"


def test_changing_an_override_starts_from_the_previous_override() -> None:
    """已有風速覆寫時起點是覆寫值，不取自動風況（沒有待定的量）。"""
    model, twin = WindEnvironmentModel(seed=5), WindEnvironmentModel(seed=5)
    for wm in (model, twin):
        wm.set_override(wind_speed=13.0)
        for i in range(1, 41):
            wm.get_wind_speed(T0 + timedelta(seconds=i))
    model.set_override(wind_speed=9.0)
    assert model._transition_from == 13.0 and not model._transition_from_pending
    model.get_wind_speed(T0 + timedelta(seconds=41))
    assert _random_state(model) == _random_state(twin), "覆寫之間的漸變不抽亂數"


@pytest.mark.parametrize(("setting", "start_is_auto", "target"), [
    ("override", True, 13.0),              # 沒有覆寫 → 起點待定
    ("override_twice", False, 9.0),        # 第二次設定時已有覆寫 13 → 起點＝13，待定取消
    ("override_then_auto", False, None),   # 清掉覆寫：起點＝覆寫值 13，終點＝自動風況
    ("ramp_up", True, 18.0),
    ("ramp_then_rated", True, 13.0),       # ramp 還沒走第一步就換 profile：起點仍待定，終點換成 13
])
def test_settings_made_before_the_next_step_resolve_to_the_right_start(
        setting: str, start_is_auto: bool, target: Optional[float]) -> None:
    """設定之後、下一步之前又改設定：起點與亂數抽樣次數都對（待定的量不會殘留成錯的起點）。"""
    model, twin = WindEnvironmentModel(seed=7), WindEnvironmentModel(seed=7)
    fresh = _random_state(twin)
    SETTINGS[setting](model)
    assert _random_state(model) == fresh, "設定的當下不抽亂數"
    assert model._transition_from_pending is start_is_auto and model._transition_to == target

    step = T0 + timedelta(seconds=1)
    auto_now = twin.get_wind_speed(step)   # 自動風況走一步
    model.get_wind_speed(step)
    assert not model._transition_from_pending
    assert model._transition_from == (auto_now if start_is_auto else 13.0)
    # 這一步抽不抽亂數：起點取自動風況（待定）或終點是自動風況（清掉覆寫）才抽，各一步
    assert _random_state(model) == (_random_state(twin) if start_is_auto or target is None else fresh)


def test_start_is_resolved_in_the_site_time_zone() -> None:
    """起點用風場當地時刻取（與自動風況同一套），換風場時區起點跟著變。"""
    step = datetime(2026, 3, 1, 3, 0, 1, tzinfo=UTC)
    starts = []
    for zone in ("Asia/Taipei", "America/Los_Angeles"):
        model = WindEnvironmentModel(seed=7, site_timezone_name=zone)
        twin = WindEnvironmentModel(seed=7, site_timezone_name=zone)
        model.set_override(wind_speed=13.0)
        model.get_wind_speed(step)
        assert model._transition_from == twin.get_wind_speed(step)
        starts.append(model._transition_from)
    assert starts[0] != starts[1]


def test_a_setting_that_lands_mid_step_is_never_paired_with_an_unresolved_start() -> None:
    """即時模擬：API 執行緒的設定剛好落在 Live 那一步的中間（這一步的待定已經處理過之後）。

    那一步仍從當下的自動風況開始漸變——不會拿新的漸變去配還沒定的起點（第一次設定時起點是 None，會算成 0 m/s）。
    以包住 ``_resolve_pending`` 來重現這個時序：它第一次被呼叫完之後才做設定。
    """
    model, twin = WindEnvironmentModel(seed=3), WindEnvironmentModel(seed=3)
    original = model._resolve_pending
    landed: List[bool] = []

    def resolve_then_the_api_call_lands(site_time: datetime, ts_utc: datetime) -> None:
        original(site_time, ts_utc)
        if not landed:
            landed.append(True)
            model.set_override(wind_speed=13.0)

    model._resolve_pending = resolve_then_the_api_call_lands  # type: ignore[method-assign]  # 測試用的時序
    step = T0 + timedelta(seconds=1)
    first = model.get_wind_speed(step)
    auto_now = twin.get_wind_speed(step)
    assert landed and first == auto_now, "漸變的第 0 步＝當下的自動風況"
    assert model._transition_from == auto_now and not model._transition_from_pending


# ── 3. ramp profile 的起點是模擬時間 ──────────────────────────────────────────


def test_profile_start_is_resolved_even_when_the_transition_was_lost() -> None:
    """另一條執行緒剛好在寫上一個漸變的結束，把新漸變的開始蓋掉（既有的競態）：待定的量仍在下一步定下來，
    ramp profile 從那一步的模擬時間起算，不會卡在待定。"""
    model = WindEnvironmentModel(seed=1)
    model.set_profile("ramp_up")
    model._transition_start = None
    speeds = [model.get_wind_speed(T0 + timedelta(seconds=i)) for i in range(1, 4)]
    assert model._profile_start_time == T0 + timedelta(seconds=1) and not model._transition_from_pending
    assert speeds == [3.0, 3.125, 3.25]


@pytest.mark.parametrize("real_offset_days", [300, -300])
@pytest.mark.parametrize(("profile", "target"), [("ramp_up", 18.0), ("ramp_down", 3.0)])
def test_ramp_profile_counts_from_the_simulation_time(profile: str, target: float, real_offset_days: int,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    """120 步的漸變完成後風速停在目標值——修正前 profile 起點是實際時間，與模擬時間相減得到的經過時間
    是負的或大得離譜（ramp_up 掉到 0 m/s）。"""
    _set_real_time(monkeypatch, T0 + timedelta(days=real_offset_days))
    model = WindEnvironmentModel(seed=1)
    model.set_profile(profile)
    assert model._profile_start_time is None, "起點要等下一步的模擬時間"
    speeds = [model.get_wind_speed(T0 + timedelta(seconds=i)) for i in range(1, 181)]
    assert model._profile_start_time == T0 + timedelta(seconds=1)
    assert speeds[120:] == [target] * 60, speeds[118:124]


# ── 4. 待定的狀態跟著存檔 / 還原 ──────────────────────────────────────────────


@pytest.mark.parametrize("setting", ["override", "ramp_up"])
def test_a_setting_made_just_before_a_checkpoint_resumes_bit_identically(setting: str) -> None:
    """設定風況之後、下一步之前存檔：還原後接著跑，與沒有中斷的那一份逐位元相同。"""
    original = WindFarmSimulator(turbine_count=2)
    for i in range(1, 11):
        original._run_one_step(T0 + timedelta(seconds=i), 1.0)
    SETTINGS[setting](original.wind_model)
    assert original.wind_model._transition_from_pending

    restored = WindFarmSimulator(turbine_count=2)
    restored.restore_state(original.checkpoint_state())
    assert restored.wind_model._transition_from_pending
    for i in range(11, 151):
        a = original._run_one_step(T0 + timedelta(seconds=i), 1.0)
        b = restored._run_one_step(T0 + timedelta(seconds=i), 1.0)
        assert [r["scada"] for r in a] == [r["scada"] for r in b], f"第 {i} 步開始不同"
