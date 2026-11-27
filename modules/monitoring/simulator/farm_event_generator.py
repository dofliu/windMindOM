"""即時模擬的風場事件產生器（WMOM-20261126-07，DEC-20261127-10）。

電網電壓驟降、電網頻率越界、風向快速變化（``simulator/farm_events.py``）原本只在批次情境依排程套用；這裡讓
持續運轉的風場也會遇到。和故障產生器同一套機制（``simulator/fault_generator.py``）：

- 每種事件是一個全場的卜瓦松過程：發生率＝``1 / mean_days_between``（整座風場平均幾天一次）。
- 每 ``CHECK_INTERVAL_S`` 模擬秒檢查一次；每次檢查每種事件**固定抽三個數**（有沒有發生、強度、時長），不論
  有沒有發生、設定怎麼改——抽樣次數不隨結果改變。關著的時候完全不抽。
- 亂數用自己的 ``random.Random``，不借用模擬器的任何 RNG（故障產生器守則、物理改動守則）。
- 同一種事件進行中、以及結束後的記錄期間（``RECORD_GRACE_S``）都不再開同一種（照樣抽三個數）：故障紀錄裡一種
  事件同時只有一筆，兩個事件的事件碼不會混在一起。

產生的事件由引擎在即時模擬的每一步套用（``WindFarmSimulator._apply_live_farm_events``）：電網事件覆寫電網模型
（``apply_event_override``，亂數抽樣次數不變）、風向事件加風向偏移；事件結束就復原。批次期間不呼叫——批次的
風場事件由排程決定。

事件的種類、強度、時間是答案：只進不對外的故障紀錄（記成 nuisance，``FaultRecorder.reconcile_farm_events``）
與準備卡評分用的答案，不進可觀測事件、對外 API、準備卡（盲測守則）。物件可以 pickle，跟著即時模擬的狀態
存檔，重啟續跑之後接著同一條亂數序列。
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Mapping, Optional, Tuple

from .farm_events import FARM_EVENT_KINDS, FarmEvent

# 事件結束後這段時間內各機組的事件碼仍算這個事件的（同批次標準答案的 NUISANCE_WINDOW_GRACE_S）
RECORD_GRACE_S = 1800.0


@dataclass
class FarmEventKindConfig:
    """一種風場事件的發生率與強度、時長範圍。

    Attributes:
        mean_days_between: 整座風場平均幾天發生一次；None＝不產生這種事件。
        magnitude_min / magnitude_max: 強度範圍（單位見 ``FarmEventKind.magnitude_unit``）。電網頻率越界的強度是
            偏移的絕對值（Hz），正負各半。
        duration_min_s / duration_max_s: 時長範圍（秒），取對數均勻。
    """

    mean_days_between: Optional[float]
    magnitude_min: float
    magnitude_max: float
    duration_min_s: float
    duration_max_s: float


def default_kinds() -> Dict[str, FarmEventKindConfig]:
    """預設：電壓驟降約兩個月一次、頻率越界約半年一次、風向快速變化約一個半月一次（全場）。

    強度與時長參考批次情境的測試（0.7 p.u. 20 秒、±1.8 Hz 40 秒、40–60° 擺 15–25 分鐘）。
    """
    return {
        "grid_voltage_dip": FarmEventKindConfig(60.0, 0.5, 0.85, 2.0, 30.0),
        "grid_frequency_excursion": FarmEventKindConfig(180.0, 0.8, 2.0, 10.0, 60.0),
        "rapid_wind_direction_change": FarmEventKindConfig(45.0, 30.0, 90.0, 600.0, 1800.0),
    }


@dataclass
class FarmEventGeneratorConfig:
    """風場事件產生器的設定。

    Attributes:
        enabled: 開不開。
        kinds: 事件種類 → 發生率與範圍；沒列的種類用預設（:func:`default_kinds`）。
        seed: 亂數種子。改了它，之後的事件序列就不同。
    """

    enabled: bool = False
    kinds: Dict[str, FarmEventKindConfig] = field(default_factory=default_kinds)
    seed: int = 20261127

    def to_dict(self) -> Dict[str, object]:
        """給 API 與存檔用的 dict。"""
        return {"enabled": self.enabled, "seed": self.seed,
                "kinds": {kind: asdict(cfg) for kind, cfg in sorted(self.kinds.items())}}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "FarmEventGeneratorConfig":
        """由 dict 建立並檢查；沒給的欄位用預設。

        Raises:
            ValueError: 欄位不認得、型別不對或範圍不合法。
        """
        unknown = sorted(set(data) - {"enabled", "kinds", "seed"})
        if unknown:
            raise ValueError(f"不認得的設定：{unknown}")
        enabled = data.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ValueError("enabled 要是 true / false")
        seed = data.get("seed", cls.seed)
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("seed 要是整數")
        kinds = default_kinds()
        raw_kinds = data.get("kinds", {})
        if not isinstance(raw_kinds, Mapping):
            raise ValueError("kinds 要是 {事件種類: 設定}")
        for kind_id, raw in raw_kinds.items():
            if kind_id not in FARM_EVENT_KINDS:
                raise ValueError(f"沒有這種風場事件：{kind_id}")
            if not isinstance(raw, Mapping):
                raise ValueError(f"kinds[{kind_id}] 要是物件")
            kinds[str(kind_id)] = _kind_config(str(kind_id), raw, kinds[str(kind_id)])
        return cls(enabled=enabled, kinds=kinds, seed=seed)


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} 要是數字")
    return float(value)


def _kind_config(kind_id: str, raw: Mapping[str, object], base: FarmEventKindConfig) -> FarmEventKindConfig:
    """檢查一種事件的設定（沒給的欄位沿用 ``base``）。"""
    allowed = set(FarmEventKindConfig.__dataclass_fields__)
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(f"kinds[{kind_id}] 不認得的設定：{unknown}")
    values = asdict(base)
    values.update(raw)
    mean = values["mean_days_between"]
    if mean is not None:
        mean = _number(mean, f"{kind_id}.mean_days_between")
        if mean <= 0:
            raise ValueError(f"{kind_id}.mean_days_between 要大於 0（不產生請給 null）")
    lo = _number(values["magnitude_min"], f"{kind_id}.magnitude_min")
    hi = _number(values["magnitude_max"], f"{kind_id}.magnitude_max")
    d_lo = _number(values["duration_min_s"], f"{kind_id}.duration_min_s")
    d_hi = _number(values["duration_max_s"], f"{kind_id}.duration_max_s")
    allowed_lo, allowed_hi = FARM_EVENT_KINDS[kind_id].magnitude_range
    if kind_id == "grid_frequency_excursion":
        allowed_lo, allowed_hi = 0.0, max(abs(allowed_lo), abs(allowed_hi))   # 絕對值，正負各半
    if not allowed_lo <= lo <= hi <= allowed_hi:
        raise ValueError(f"{kind_id} 的強度要在 {allowed_lo}–{allowed_hi} 之間、而且 min ≤ max")
    if not 0 < d_lo <= d_hi <= 6 * 3600:
        raise ValueError(f"{kind_id} 的時長要 0 < min ≤ max ≤ 21600 秒")
    return FarmEventKindConfig(mean, lo, hi, d_lo, d_hi)


@dataclass(frozen=True)
class LiveFarmEvent:
    """即時模擬裡發生的一個風場事件。

    Attributes:
        kind: ``FARM_EVENT_KINDS`` 的 ID。
        start: 開始時刻（風場時鐘，tz-aware）。
        duration_s: 持續秒數。
        magnitude: 強度。
    """

    kind: str
    start: datetime
    duration_s: float
    magnitude: float

    @property
    def end(self) -> datetime:
        """結束時刻。"""
        return self.start + timedelta(seconds=self.duration_s)

    def as_farm_event(self) -> FarmEvent:
        """換成批次用的 ``FarmEvent``（起點＝0），拿它算風向偏移。"""
        return FarmEvent(self.kind, 0.0, self.duration_s, self.magnitude)

    def to_dict(self) -> Dict[str, object]:
        """給畫面與答案用的 dict。"""
        from simulator.time_utils import iso_utc

        return {"kind": self.kind, "start": iso_utc(self.start), "end": iso_utc(self.end),
                "duration_s": round(self.duration_s, 1), "magnitude": round(self.magnitude, 3)}


class FarmEventGenerator:
    """即時模擬的風場事件產生器。掛在 ``WindFarmSimulator`` 底下，引擎每一步呼叫 :meth:`step`。"""

    CHECK_INTERVAL_S = 60.0

    def __init__(self, config: FarmEventGeneratorConfig | None = None) -> None:
        self.config = config or FarmEventGeneratorConfig()
        self._rng = random.Random(self.config.seed)
        self._accumulated = 0.0
        self.generated = 0
        # 開始過、還在記錄期間（結束後 RECORD_GRACE_S 內）的事件；只由 Live 執行緒改
        self.events: List[LiveFarmEvent] = []

    def configure(self, config: FarmEventGeneratorConfig) -> None:
        """換設定。種子變了才重設亂數序列。進行中的事件照樣跑完。

        API 執行緒呼叫、Live 執行緒正在檢查時，那一次檢查可能一半用舊的設定 / 亂數、一半用新的——只影響那一次，
        之後照新的走（故障產生器也是這樣）。
        """
        reseed = config.seed != self.config.seed
        self.config = config
        if reseed:
            self._rng = random.Random(config.seed)

    def step(self, dt: float, step_start: datetime) -> List[LiveFarmEvent]:
        """推進 ``dt`` 秒；到了檢查的時候替每種事件擲一次，發生就從 ``step_start`` 開始。

        Args:
            dt: 這一步多長（模擬秒）。
            step_start: 這一步開始的風場時鐘。

        Returns:
            這一步開始的事件。
        """
        if not self.config.enabled:
            return []
        self._accumulated += dt
        if self._accumulated < self.CHECK_INTERVAL_S:
            return []
        elapsed, self._accumulated = self._accumulated, 0.0
        made: List[LiveFarmEvent] = []
        grace = timedelta(seconds=RECORD_GRACE_S)
        running = {e.kind for e in self.events if e.end + grace > step_start}
        for kind_id in sorted(FARM_EVENT_KINDS):
            # 每種事件固定抽三個數：有沒有發生、強度、時長。抽樣次數不隨結果或設定改變
            happens, size, length = self._rng.random(), self._rng.random(), self._rng.random()
            cfg = self.config.kinds.get(kind_id)
            if cfg is None or cfg.mean_days_between is None or kind_id in running:
                continue
            probability = 1.0 - math.exp(-elapsed / (cfg.mean_days_between * 86400.0))
            if happens >= probability:
                continue
            if kind_id == "grid_frequency_excursion":
                # 強度的那個數同時決定正負：前一半往下、後一半往上
                sign, size = (-1.0, size * 2.0) if size < 0.5 else (1.0, (size - 0.5) * 2.0)
            else:
                sign = 1.0
            magnitude = sign * (cfg.magnitude_min + size * (cfg.magnitude_max - cfg.magnitude_min))
            log_lo, log_hi = math.log(cfg.duration_min_s), math.log(cfg.duration_max_s)
            duration = math.exp(log_lo + length * (log_hi - log_lo))
            event = LiveFarmEvent(kind=kind_id, start=step_start, duration_s=duration, magnitude=magnitude)
            self.events.append(event)
            made.append(event)
            self.generated += 1
        return made

    def active(self, step_start: datetime, dt: float) -> List[LiveFarmEvent]:
        """和 ``[step_start, step_start + dt)`` 重疊的事件（套用到這一步）。"""
        step_end = step_start + timedelta(seconds=dt)
        return [e for e in self.events if e.start < step_end and e.end > step_start]

    def expire(self, now: datetime) -> List[LiveFarmEvent]:
        """拿掉記錄期間已過（結束後 ``RECORD_GRACE_S``）的事件並回傳它們。"""
        grace = timedelta(seconds=RECORD_GRACE_S)
        done = [e for e in self.events if e.end + grace <= now]
        if done:
            self.events = [e for e in self.events if e.end + grace > now]
        return done

    def recording(self, now: datetime) -> List[LiveFarmEvent]:
        """``now`` 時還在記錄期間（開始之後、結束後 ``RECORD_GRACE_S`` 之前）的事件。"""
        grace = timedelta(seconds=RECORD_GRACE_S)
        return [e for e in self.events if e.start <= now < e.end + grace]


def grid_override(events: List[LiveFarmEvent]) -> Tuple[Optional[float], Optional[float]]:
    """進行中的電網事件要覆寫的（頻率偏移 Hz、電壓比例 p.u.）；沒有就是 None。

    同批次的規則：電壓驟降取最深的、頻率越界加總。
    """
    dips = [e.magnitude for e in events if e.kind == "grid_voltage_dip"]
    shifts = [e.magnitude for e in events if e.kind == "grid_frequency_excursion"]
    return (sum(shifts) if shifts else None, min(dips) if dips else None)
