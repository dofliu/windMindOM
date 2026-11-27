# wind_model.py
"""
Multi-scale wind environment model for realistic long-term simulation.

Layers (from slowest to fastest):
  1. Seasonal — Weibull shape/scale vary by month
  2. Weather system — multi-day synoptic patterns (high/low pressure)
  3. Diurnal — daily thermal cycle (afternoon peak)
  4. Mesoscale — hour-scale ramps and lulls
  5. Turbulence — second-scale fluctuations (handled by TurbulenceGenerator)

Supports:
  - Auto mode: realistic multi-month patterns with no repetition
  - Manual override with configurable transition ramp
  - Predefined profiles (calm, moderate, rated, storm, etc.)
  - Accelerated time (time_scale > 1 for bulk data generation)

Time of day / month (diurnal and seasonal layers) are read in the wind farm's local time
(``site_timezone``, default Asia/Taipei — WMOM-20261021-11): the simulator passes tz-aware UTC
timestamps (WMOM-20261021-03-c), which every getter converts with ``to_site_naive``. The same UTC
instant gives the same cycle phase on any server, so generated data is reproducible.

This model has no clock of its own (WMOM-20261126-03): the only time it knows is the simulation
time the engine passes to the getters. ``set_override`` / ``set_profile`` do not look up "the
current auto wind" themselves — they mark it as pending, and the next ``get_wind_speed`` call
resolves it with that step's simulation time. Do not import ``utc_now`` here: a batch generated
with the same settings must be bit-identical whatever the wall-clock time is.

Measured series (WMOM-20261125-07): ``set_measured`` makes a measured wind series
(``simulator/wind_series.py``) replace the model's base wind speed — and, where the series has them,
direction, temperature, turbulence intensity, humidity and pressure. Precedence: manual override /
profile > measured series > model. The model layers keep running underneath (``_get_auto_wind`` is
still called once per step) so the random-draw count is the same as in auto mode; the series is
applied at the next ``get_wind_speed`` with that step's simulation time, as a single object swap, so
the API thread never leaves half a change for the Live thread to read.
"""

import math
from collections import deque
import numpy as np
from datetime import datetime, timedelta
from typing import Optional

from simulator.time_utils import DEFAULT_SITE_TIMEZONE, site_timezone, to_site_naive, to_utc
from dataclasses import replace

from simulator.wind_series import MeasuredWindPlayback


class _MeasuredChange:
    """``set_measured`` / ``clear_measured`` 的待套用變更（一次指派，Live 執行緒在下一步套用）。"""

    def __init__(self, playback: Optional[MeasuredWindPlayback]) -> None:
        self.playback = playback


# ─── Seasonal wind parameters (typical coastal/onshore site) ─────────
# month: (weibull_scale_m_s, weibull_shape_k)
# Higher scale = windier month, shape ~2 = Rayleigh distribution
SEASONAL_PARAMS = {
    1:  (10.5, 2.1),   # January — windy
    2:  (10.2, 2.0),   # February
    3:  (9.8,  2.0),   # March — spring transition
    4:  (8.5,  2.1),   # April
    5:  (7.5,  2.2),   # May — calmer
    6:  (7.0,  2.3),   # June — summer calm
    7:  (6.8,  2.3),   # July — lightest winds
    8:  (7.2,  2.2),   # August
    9:  (8.0,  2.1),   # September — autumn ramp
    10: (9.5,  2.0),   # October
    11: (10.0, 1.9),   # November — stormy
    12: (10.8, 1.9),   # December — peak winter
}


class WeatherSystem:
    """Simulates multi-day synoptic weather patterns."""

    def __init__(self, seed: int = 0):
        self._rng = np.random.RandomState(seed)
        # Current weather state
        self._pressure_state = 0.0     # normalized: -1 (low/stormy) to +1 (high/calm)
        self._front_timer = 0.0        # time until next front passage
        self._front_duration = 0.0     # how long the current front lasts
        self._in_front = False
        self._next_front()

    def _next_front(self):
        """Schedule next weather front passage."""
        # Fronts every 2-7 days
        self._front_timer = self._rng.uniform(2 * 86400, 7 * 86400)
        self._front_duration = self._rng.uniform(6 * 3600, 24 * 3600)
        self._in_front = False

    def step(self, dt: float) -> float:
        """Return wind speed multiplier (0.5 to 1.8) based on weather system."""
        self._front_timer -= dt

        if self._front_timer <= 0 and not self._in_front:
            self._in_front = True
            self._front_timer = self._front_duration

        if self._in_front:
            self._front_timer -= dt
            if self._front_timer <= 0:
                self._next_front()
                self._in_front = False

        # Pressure evolves slowly with mean reversion
        target = -0.5 if self._in_front else 0.3
        tau = 7200.0  # 2-hour time constant
        alpha = 1.0 - math.exp(-dt / tau)
        self._pressure_state += (target - self._pressure_state) * alpha
        self._pressure_state += self._rng.normal(0, 0.003 * math.sqrt(dt))
        self._pressure_state = max(-1.0, min(1.0, self._pressure_state))

        # Map pressure to wind multiplier
        # Low pressure (negative) → stronger wind
        # High pressure (positive) → calmer
        return 1.0 - self._pressure_state * 0.4


class WindEnvironmentModel:
    """Multi-scale wind environment model for realistic long-term simulation."""

    def __init__(self, seed: int = 0, site_timezone_name: str = DEFAULT_SITE_TIMEZONE):
        self._rng = np.random.RandomState(seed)
        self.turbulence_intensity = 0.10
        self.set_site_timezone(site_timezone_name)
        self.base_ambient_temp = 25.0

        # Sub-models
        self._weather = WeatherSystem(seed=seed + 1)
        self._mesoscale_state = 0.0  # hour-scale ramp state

        # Simulation time tracking (for accelerated mode)
        self._sim_time_offset: Optional[timedelta] = None
        self.time_scale = 1.0  # 1.0 = real-time, 60.0 = 1min per second

        # Manual override
        self._override_wind_speed: Optional[float] = None
        self._override_wind_direction: Optional[float] = None
        self._override_ambient_temp: Optional[float] = None
        self._active_profile: Optional[str] = None
        # ramp profile 的起點（模擬時間，UTC）；設定 profile 時先標記待定，下一步的模擬時間才是起點
        self._profile_start_time: Optional[datetime] = None
        self._profile_start_pending = False

        # Transition ramp for smooth profile switching
        self._transition_from: Optional[float] = None
        # 漸變起點是「漸變開始那一步的自動風況」、還沒取：下一次 get_wind_speed 用那一步的模擬時間取
        self._transition_from_pending = False
        self._transition_to: Optional[float] = None
        self._transition_start: Optional[float] = None
        self._transition_duration: float = 30.0  # 30 seconds default ramp
        # get_wind_speed 被呼叫的次數（每個物理步一次，名稱是舊的）；漸變的進度依它計算，不讀實際時間
        self._elapsed_real = 0.0

        # Weather system state (for deterministic long-term)
        self._last_weather_update = 0.0

        # 實測風況序列（WMOM-20261125-07）：套用中的、待套用的變更、上一步輸出的基準風速（切換時從它漸變）
        self._measured: Optional[MeasuredWindPlayback] = None
        # API 執行緒 append、Live 執行緒 popleft（deque 的這兩個操作是原子的）：先後兩次設定都會依序套用，
        # 不會有一方把另一方剛放進來的變更蓋掉
        self._measured_changes: deque = deque()
        self._last_base: Optional[float] = None

    def set_site_timezone(self, name: str) -> None:
        """Set the wind farm's IANA time zone used for diurnal / seasonal cycles (WMOM-20261021-11).

        Args:
            name: IANA time zone name, e.g. ``Asia/Taipei``.

        Raises:
            ValueError: Unknown time zone.
        """
        self.site_tz = site_timezone(name)
        self.site_timezone_name = name

    # ─── Override control ──────────────────────────────────────────────

    def set_override(self, wind_speed: Optional[float] = None,
                     wind_direction: Optional[float] = None,
                     ambient_temp: Optional[float] = None,
                     turbulence: Optional[float] = None):
        """Set manual wind conditions with smooth transition."""
        if wind_speed is not None and self._override_wind_speed != wind_speed:
            # Start transition ramp from current conditions
            self._begin_transition(wind_speed)

        self._override_wind_speed = wind_speed
        self._override_wind_direction = wind_direction
        self._override_ambient_temp = ambient_temp
        if turbulence is not None:
            self.turbulence_intensity = turbulence
        self._active_profile = "manual" if any(
            v is not None for v in [wind_speed, wind_direction, ambient_temp]
        ) else None

    def clear_override(self):
        """Return to automatic mode with smooth transition."""
        if self._override_wind_speed is not None:
            self._transition_from = self._override_wind_speed
            self._transition_from_pending = False
            self._transition_to = None  # will use auto
            self._transition_start = self._elapsed_real
        self._override_wind_speed = None
        self._override_wind_direction = None
        self._override_ambient_temp = None
        self._active_profile = None

    def set_measured(self, playback: MeasuredWindPlayback) -> None:
        """改由實測序列提供風況（下一步套用，從當時的風速漸變過去）。

        Args:
            playback: 序列與播放方式；開始播的時刻由下一步的模擬時間定。
        """
        self._measured_changes.append(_MeasuredChange(playback))

    def clear_measured(self) -> None:
        """停止實測序列，回到模型的風況（下一步套用、漸變過去）。沒有在播、也沒有待套用的時不做事。"""
        if self._measured is not None or self._measured_changes:
            self._measured_changes.append(_MeasuredChange(None))

    def restart_measured_replay(self) -> None:
        """批次開始時：``replay`` 的序列從批次的第一步重新開始播（開始的時刻改由下一步的模擬時間定）。

        即時模擬裡套用的序列已經用 Live 的時間定了開始的時刻；不重新定的話，批次裡播到序列的哪裡要看 Live
        跑了多久，同樣的設定產生的批次就不同。批次前後 Live 的狀態會存檔 / 還原，這裡改了不影響 Live。
        """
        playback = self._measured
        if playback is not None and playback.alignment == "replay":
            # 換一個新的物件（Live 的那一個會在批次後隨狀態還原），開始的時刻由批次的第一步定（_resolve_pending）
            self._measured = replace(playback, anchor_sim=None)

    @property
    def measured(self) -> Optional[MeasuredWindPlayback]:
        """套用中的實測序列（待套用的不算）。"""
        return self._measured

    def _manual(self) -> bool:
        return self._override_wind_speed is not None or self._active_profile is not None

    def _measured_value(self, quantity: str, ts_utc: datetime) -> Optional[float]:
        """實測序列在這個時刻的某個量；沒有在播、序列沒有這個量或這個時刻沒有值時回 None。"""
        playback = self._measured
        if playback is None:
            return None
        return playback.value(quantity, ts_utc.timestamp())

    def _free_wind(self, site_time: datetime, ts_utc: datetime) -> float:
        """沒有手動設定時的基準風速：實測序列有值就用它，否則是模型的。模型每次都算（亂數抽樣次數不變）。"""
        auto = self._get_auto_wind(site_time)
        measured = self._measured_value("wind_speed", ts_utc)
        return measured if measured is not None else auto

    def set_profile(self, profile: str):
        """Activate a predefined wind scenario with smooth transition.

        Profiles:
          'calm'        — 2 m/s, low turbulence
          'moderate'    — 8 m/s, normal turbulence
          'rated'       — 13 m/s, at rated power
          'strong'      — 18 m/s, pitch regulation
          'storm'       — 26 m/s, above cut-out
          'gusty'       — 10 m/s, high turbulence (0.30)
          'ramp_up'     — gradual increase 3→18 m/s over 10 minutes
          'ramp_down'   — gradual decrease 18→3 m/s over 10 minutes
          'auto'        — return to natural pattern
        """
        profiles = {
            'calm':     (2.0,  270, 20.0, 0.05),
            'moderate': (8.0,  270, 25.0, 0.10),
            'rated':    (13.0, 270, 25.0, 0.10),
            'strong':   (18.0, 285, 22.0, 0.12),
            'storm':    (26.0, 300, 18.0, 0.20),
            'gusty':    (10.0, 260, 25.0, 0.30),
        }

        if profile == 'auto':
            self.clear_override()
            return

        if profile in ('ramp_up', 'ramp_down'):
            self._active_profile = profile
            # profile 的起點＝下一步的模擬時間（不讀實際時間，WMOM-20261126-03）
            self._profile_start_pending = True
            self._override_wind_direction = 270.0
            self._override_ambient_temp = 25.0
            self.turbulence_intensity = 0.12
            # Start transition
            self._transition_duration = 120.0  # 2 minute ramp
            self._begin_transition(18.0 if profile == 'ramp_up' else 3.0)
            return

        if profile in profiles:
            ws, wd, temp, turb = profiles[profile]
            self.set_override(ws, wd, temp, turb)
            self._active_profile = profile

    def get_status(self) -> dict:
        measured_on = self._measured_status() is not None
        return {
            "mode": "manual" if self._active_profile else ("measured" if measured_on else "auto"),
            "profile": self._active_profile,
            "override_wind_speed": self._override_wind_speed,
            "override_wind_direction": self._override_wind_direction,
            "override_ambient_temp": self._override_ambient_temp,
            "turbulence_intensity": self.turbulence_intensity,
            "time_scale": self.time_scale,
            "weather_pressure": self._weather._pressure_state,
            "weather_in_front": self._weather._in_front,
            "measured": self._measured_status(),
        }

    def _measured_status(self) -> Optional[dict]:
        try:
            pending: Optional[_MeasuredChange] = self._measured_changes[-1]   # 最後一個待套用的變更
        except IndexError:
            pending = None
        if pending is not None:
            return {**pending.playback.status(), "pending": True} if pending.playback is not None else None
        current = self._measured   # 只讀一次：Live 執行緒可能同時把它換掉
        return {**current.status(), "pending": False} if current is not None else None

    def _begin_transition(self, target: float) -> None:
        """從目前的風況開始漸變到 ``target``（m/s）。

        目前有風速覆寫時起點就是覆寫值；沒有時起點是自動風況——自動風況隨模擬時間變，這裡不取（這個模型
        沒有自己的時鐘），標記待定，由下一次 ``get_wind_speed`` 用那一步的模擬時間取（WMOM-20261126-03）。

        即時模擬時這裡在 API 的執行緒、``get_wind_speed`` 在 Live 的執行緒（這個物件會進狀態存檔，不能放鎖）。
        這裡先寫待定旗標、才寫終點與開始；``get_wind_speed`` 先讀開始與終點、再定一次起點、最後才讀起點——
        它讀到新的漸變時起點一定已經定下來，不會拿新的漸變去配還沒定的起點（寫入順序不要改）。

        Args:
            target: 漸變的終點風速（m/s）。
        """
        if self._override_wind_speed:  # 0.0 的覆寫視同沒有（沿用原本 ``or`` 的語意）
            self._transition_from = self._override_wind_speed
            self._transition_from_pending = False
        else:
            self._transition_from_pending = True
        self._transition_to = target
        self._transition_start = self._elapsed_real

    def _resolve_pending(self, site_time: datetime, ts_utc: datetime) -> None:
        """把設定風況時待定的量用這一步的模擬時間定下來：漸變起點的自動風況、ramp profile 的起點。

        取自動風況會讓天氣系統與中尺度狀態各前進一步（與原本在 ``set_override`` 裡取時相同的亂數抽樣）。

        Args:
            site_time: 這一步的模擬時間（風場當地時間，naive）。
            ts_utc: 同一個時刻（tz-aware UTC）。
        """
        if self._transition_from_pending:
            self._transition_from_pending = False
            self._transition_from = self._free_wind(site_time, ts_utc)
        if self._profile_start_pending:
            self._profile_start_pending = False
            self._profile_start_time = ts_utc
        current = self._measured
        if current is not None and current.anchor_sim is None:
            current.anchor(ts_utc.timestamp())   # 批次重新開始播（restart_measured_replay）：從這一步開始
        changes = self._measured_changes
        while changes:
            # 實測序列的開始 / 停止：依放進來的順序一個一個套用。沒有手動設定時，從上一步輸出的風速漸變到新的
            # 來源（進行中的漸變也從現在的風速重新開始，免得終點突然換成新來源的值；有手動設定時新的來源暫時
            # 看不到，不必漸變）
            change = changes.popleft()
            if change.playback is not None:
                change.playback.anchor(ts_utc.timestamp())
            if not self._manual() and self._last_base is not None:
                self._transition_from = self._last_base
                self._transition_from_pending = False
                self._transition_to = None
                self._transition_start = self._elapsed_real
            self._measured = change.playback

    # ─── Core getters ──────────────────────────────────────────────────

    def get_wind_speed(self, timestamp: datetime) -> float:
        """Get wind speed at given timestamp (includes all layers)."""
        ts_utc = to_utc(timestamp)  # ramp profile 經過時間用 UTC 相減（_profile_start_time 是 UTC）
        timestamp = to_site_naive(timestamp, self.site_tz)
        self._elapsed_real += 1.0  # approximate
        self._resolve_pending(timestamp, ts_utc)  # 不在漸變分支裡做：沒有進行中的漸變時待定的量也要定下來

        # Check for active transition ramp
        transition_start = self._transition_start
        if transition_start is not None:
            elapsed = self._elapsed_real - transition_start
            progress = min(1.0, elapsed / self._transition_duration)
            # Smooth S-curve transition
            smooth = 0.5 - 0.5 * math.cos(progress * math.pi)

            if progress >= 1.0:
                self._transition_start = None  # transition complete

            transition_to = self._transition_to
            # 另一條執行緒的設定若落在這一步的中間：先讀開始與終點、再定一次起點、最後才讀起點。設定的一方先寫
            # 待定旗標才寫終點與開始，所以上面讀到新的漸變時旗標一定已經立起來。平常這一行不做事
            self._resolve_pending(timestamp, ts_utc)
            from_val = self._transition_from or 0.0
            to_val = transition_to if transition_to is not None else self._free_wind(timestamp, ts_utc)
            base = from_val + (to_val - from_val) * smooth
        elif self._active_profile in ('ramp_up', 'ramp_down') and self._profile_start_time:
            elapsed = (ts_utc - self._profile_start_time).total_seconds()
            if self._active_profile == 'ramp_up':
                base = 3.0 + min(15.0, elapsed / 120.0 * 15.0)
            else:
                base = max(3.0, 18.0 - elapsed / 120.0 * 15.0)
        elif self._override_wind_speed is not None:
            base = self._override_wind_speed
        else:
            base = self._free_wind(timestamp, ts_utc)

        self._last_base = max(0, base)
        return max(0, base)

    def _get_auto_wind(self, timestamp: datetime) -> float:
        """Multi-layer automatic wind speed model."""
        timestamp = to_site_naive(timestamp, self.site_tz)
        month = timestamp.month
        hour = timestamp.hour + timestamp.minute / 60.0

        # Layer 1: Seasonal baseline (Weibull mean)
        scale, shape = SEASONAL_PARAMS.get(month, (8.5, 2.1))
        seasonal_mean = scale * math.gamma(1.0 + 1.0 / shape)

        # Layer 2: Weather system (multi-day patterns)
        # Advance weather model (approximately, using 1s steps)
        weather_mult = self._weather.step(1.0)

        # Layer 3: Diurnal cycle (thermal effects)
        # Afternoon peak (14:00-16:00), overnight lull
        diurnal = 1.0 + 0.15 * math.sin((hour - 5) * math.pi / 12)

        # Layer 4: Mesoscale ramps (1-4 hour scale)
        self._mesoscale_state += self._rng.normal(0, 0.002)
        self._mesoscale_state *= 0.9995  # slow decay
        self._mesoscale_state = max(-0.3, min(0.3, self._mesoscale_state))
        mesoscale = 1.0 + self._mesoscale_state

        base = seasonal_mean * weather_mult * diurnal * mesoscale
        return max(0.5, base)

    def get_wind_direction(self, timestamp: datetime) -> float:
        ts_utc = to_utc(timestamp)   # 和 get_wind_speed 同一種換算
        timestamp = to_site_naive(timestamp, self.site_tz)
        if self._override_wind_direction is not None:
            return (self._override_wind_direction + self._rng.normal(0, 3)) % 360

        measured = self._measured_value("wind_direction", ts_utc)
        if measured is not None:
            # 實測的是 10 分鐘（等）平均：加上和模型一樣的小擺動（同一次抽樣）
            return (measured + self._rng.normal(0, 2.0)) % 360

        # Auto: slow drift with weather-driven backing/veering
        hour = timestamp.hour + timestamp.minute / 60
        base_direction = 270
        seasonal_shift = 20 * math.sin((timestamp.month - 1) * math.pi / 6)  # winter NW, summer SW
        diurnal_shift = 15 * math.sin((hour - 6) * math.pi / 12)  # sea breeze effect
        weather_shift = self._weather._pressure_state * 30  # fronts shift direction
        return (base_direction + seasonal_shift + diurnal_shift + weather_shift +
                self._rng.normal(0, 2.0)) % 360

    def get_ambient_temp(self, timestamp: datetime) -> float:
        ts_utc = to_utc(timestamp)
        timestamp = to_site_naive(timestamp, self.site_tz)
        if self._override_ambient_temp is not None:
            return self._override_ambient_temp + self._rng.normal(0, 0.3)
        measured = self._measured_value("ambient_temp", ts_utc)
        if measured is not None:
            return measured + self._rng.normal(0, 0.3)

        month = timestamp.month
        hour = timestamp.hour + timestamp.minute / 60.0

        # Seasonal base temperature
        seasonal_temps = {
            1: 12, 2: 13, 3: 16, 4: 20, 5: 24, 6: 27,
            7: 29, 8: 28, 9: 26, 10: 22, 11: 17, 12: 13,
        }
        base = seasonal_temps.get(month, 22)

        # Diurnal: peak at 14:00, minimum at 05:00
        diurnal = 5.0 * math.sin((hour - 5) * math.pi / 12)

        # Weather: fronts bring temperature changes
        weather = -3.0 * self._weather._pressure_state

        return base + diurnal + weather + self._rng.normal(0, 0.3)

    # ─── Atmospheric stability (Monin-Obukhov diurnal coupling) ────────
    #
    # Realistic offshore/onshore boundary layers go through a strong diurnal
    # stability cycle that drives both the vertical wind-shear exponent α and
    # the turbulence intensity. We summarise it with a single continuous score
    # s ∈ [−1, +1]:
    #     −1 ⇒ strongly stable (nocturnal radiative cooling dominates)
    #      0 ⇒ neutral
    #     +1 ⇒ strongly unstable (daytime convective mixing)
    #
    # s = solar(t) · wind_damping(V) · cloud_damping(pressure)
    #
    #     solar(t)      = sin(π · (hour − 6)/12)       # +1 noon, 0 dawn/dusk, −1 midnight
    #     wind_damping  = 1 / (1 + (V/8)²)              # high wind → mechanical mixing
    #     cloud_damping = 1 − 0.5 · max(0, −pressure)   # low-pressure / fronts → clouds
    #
    # Manual override (profile / set_override) forces neutral to avoid
    # surprising users who fix wind conditions during demos.

    def get_atmospheric_stability(self, timestamp: datetime) -> float:
        """Continuous atmospheric stability score in [-1, +1].

        Negative = stable (night, clear sky, low wind → high α, low TI).
        Positive = unstable (convective afternoon → low α, high TI).
        Returns 0.0 (neutral) when any manual wind override is active.

        Uses the weather model's current state (no side effects) so this can be
        called multiple times per step without advancing RNG state.
        """
        ts_utc = to_utc(timestamp)
        timestamp = to_site_naive(timestamp, self.site_tz)
        if self._override_wind_speed is not None or self._active_profile is not None:
            return 0.0

        hour = timestamp.hour + timestamp.minute / 60.0
        solar = math.sin((hour - 6.0) * math.pi / 12.0)
        measured = self._measured_value("wind_speed", ts_utc)
        if measured is not None:
            # 實測序列在播：機械混合用實測的風速估
            wind_damping = 1.0 / (1.0 + (max(0.5, measured) / 8.0) ** 2)
            cloud_damping = 1.0 - 0.5 * max(0.0, -self._weather._pressure_state)
            return max(-1.0, min(1.0, solar * wind_damping * cloud_damping))

        # Wind damping: use seasonal baseline × current weather multiplier
        # (mirrors _get_auto_wind but without advancing weather.step).
        month = timestamp.month
        scale, shape = SEASONAL_PARAMS.get(month, (8.5, 2.1))
        seasonal_mean = scale * math.gamma(1.0 + 1.0 / shape)
        # pressure_state already reflects current synoptic state
        weather_mult = 1.0 - self._weather._pressure_state * 0.4
        v = max(0.5, seasonal_mean * weather_mult)
        wind_damping = 1.0 / (1.0 + (v / 8.0) ** 2)

        # Cloud damping: low pressure / fronts suppress both extremes
        cloud_damping = 1.0 - 0.5 * max(0.0, -self._weather._pressure_state)

        s = solar * wind_damping * cloud_damping
        return max(-1.0, min(1.0, s))

    def get_shear_exponent(self, timestamp: datetime,
                           stability: Optional[float] = None) -> float:
        """Farm-level wind shear exponent α (power-law V(h)=V_hub·(h/h_hub)^α).

        α = clamp(0.14 − 0.10·s, 0.04, 0.30). Neutral value 0.14 follows
        common offshore measurements (e.g. FINO1, Lillgrund).

        Pass `stability` to avoid re-computing and re-mutating internal state.
        """
        s = stability if stability is not None else self.get_atmospheric_stability(timestamp)
        return max(0.04, min(0.30, 0.14 - 0.10 * s))

    def get_turbulence_multiplier(self, timestamp: datetime,
                                  stability: Optional[float] = None) -> float:
        """Multiplier applied on top of `turbulence_intensity` base (0.5 – 1.6).

        At very stable night ≈ 0.5× base TI; at convective afternoon ≈ 1.5× base TI.

        Pass `stability` to avoid re-computing and re-mutating internal state.
        """
        s = stability if stability is not None else self.get_atmospheric_stability(timestamp)
        return max(0.5, min(1.6, 1.0 + 0.5 * s))

    def effective_turbulence(self, timestamp: datetime, multiplier: float) -> float:
        """這一步的紊流強度：實測序列有紊流強度（或風速標準差）時用實測的——它已經含大氣穩定度的影響，
        不再乘穩定度的倍數；否則是 ``turbulence_intensity × multiplier``（原本的算法）。手動設定時一律用後者。

        Args:
            timestamp: 模擬時間。
            multiplier: 穩定度給的倍數（``get_turbulence_multiplier``）。

        Returns:
            紊流強度。
        """
        if not self._manual():
            measured = self._measured_value("turbulence_intensity", to_utc(timestamp))
            if measured is not None:
                return measured
        return self.turbulence_intensity * multiplier

    def get_ambient_humidity(self, timestamp: datetime) -> float:
        """Relative humidity (%) with seasonal/diurnal/weather modulation.

        Offshore wind sites sit in the marine boundary layer where RH is high
        year-round and peaks during rainy season and overnight.
        """
        ts_utc = to_utc(timestamp)
        timestamp = to_site_naive(timestamp, self.site_tz)
        if self._override_ambient_temp is not None:
            # During manual override we keep humidity stable to avoid surprising
            # coolant behavior during demos; still add a little sensor noise.
            return 65.0 + self._rng.normal(0, 1.0)
        measured = self._measured_value("humidity", ts_utc)
        if measured is not None:
            return max(15.0, min(100.0, measured + self._rng.normal(0, 0.8)))

        month = timestamp.month
        hour = timestamp.hour + timestamp.minute / 60.0

        # Seasonal baseline — higher during East-Asian rainy / typhoon season
        seasonal_rh = {
            1: 72, 2: 74, 3: 76, 4: 78, 5: 82, 6: 85,
            7: 82, 8: 83, 9: 80, 10: 74, 11: 70, 12: 70,
        }
        base = seasonal_rh.get(month, 75)

        # Diurnal: overnight/near-dawn peak, mid-afternoon trough (≈±8%)
        diurnal = -8.0 * math.sin((hour - 5) * math.pi / 12)

        # Low-pressure fronts pull humidity up by ~10%
        weather = -10.0 * self._weather._pressure_state

        rh = base + diurnal + weather + self._rng.normal(0, 0.8)
        return max(15.0, min(100.0, rh))

    def get_ambient_pressure(self, timestamp: datetime) -> float:
        """Ambient atmospheric pressure P (Pa) from synoptic weather state (#106).

        Maps the continuous weather pressure state [-1, +1] to physical Pa
        with mid-latitude amplitude ±1500 Pa (≈ ±15 hPa). Matches typical
        temperate-zone frontal swings (1 σ ≈ 8 hPa, 2 σ ≈ 15 hPa).

        Manual overrides lock P at the ISA sea-level reference (101325 Pa) so
        demos are not disturbed by synthetic weather drift.
        """
        if self._override_wind_speed is not None or self._active_profile is not None:
            return 101325.0
        measured = self._measured_value("pressure_hpa", to_utc(timestamp))
        if measured is not None:
            return measured * 100.0
        p = 101325.0 + self._weather._pressure_state * 1500.0
        return max(90000.0, min(105000.0, p))

    def get_air_density(self, timestamp: datetime,
                        ambient_temp: Optional[float] = None,
                        humidity: Optional[float] = None,
                        pressure_pa: Optional[float] = None) -> float:
        """Moist air density ρ (kg/m³) from ideal gas law + Magnus correction.

        ρ_dry   = P / (R_d · T_K)                R_d = 287.058 J/(kg·K)
        e_s(T)  = 611.2 · exp(17.67·T_C/(T_C+243.5))   (Pa, Buck/Magnus)
        ρ_moist = ρ_dry · (1 − 0.378·e/P)        e = (RH/100)·e_s

        Typical range: ~1.15 (32 °C / 95% RH) to ~1.34 (−10 °C / 50% RH).
        Pass `ambient_temp` / `humidity` / `pressure_pa` to avoid recomputing
        those upstream; when omitted they default to the current weather state
        (includes synoptic P swings, #106).
        """
        t_c = ambient_temp if ambient_temp is not None else self.get_ambient_temp(timestamp)
        rh = humidity if humidity is not None else self.get_ambient_humidity(timestamp)
        p_atm = pressure_pa if pressure_pa is not None else self.get_ambient_pressure(timestamp)
        t_k = t_c + 273.15
        e_s = 611.2 * math.exp(17.67 * t_c / (t_c + 243.5))
        e = max(0.0, min(1.0, rh / 100.0)) * e_s
        rho_dry = p_atm / (287.058 * t_k)
        rho = rho_dry * (1.0 - 0.378 * e / p_atm)
        return max(0.95, min(1.35, rho))
