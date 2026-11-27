"""實測風況序列（WMOM-20261125-07，DEC-20261127-03）。

把一份實測的風速 / 風向 / 氣溫 / 紊流強度（等）時間序列讀進來，讓風況模型照它走。

- **讀檔**（:func:`parse_csv`）：CSV，一列一個時刻。欄位名稱自動辨識常見的寫法，也可以自己對應。時間沒有
  時區的視為風場當地時間。超出合理範圍的值當成缺值；風速換算到輪轂高度（冪次律）。
- **取值**（:class:`MeasuredWindPlayback`）：任一個模擬時刻 → 序列裡的位置 → 線性內插（風向用單位向量內插）。
  兩種對時方式：``replay``（套用那一刻從序列的起點〔或指定的位置〕開始播）、``absolute``（模擬時間就是序列
  的時間，給回填歷史或指定日期的批次用）。播到底之後：``loop`` 從頭再播、``hold`` 停在最後一筆、``auto``
  回到模型的風況。兩筆之間缺太久（``max_gap_s``）的那一段也回到模型的風況。

這個模組不讀實際時間（風況設定守則）：它只知道呼叫端給的模擬時間。物件會跟著即時模擬的狀態存檔
（pickle），所以只放 numpy 陣列與基本型別。
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from simulator.time_utils import site_timezone

# 一份序列最多幾筆（10 分鐘一筆約 5.7 年；存檔每 30 秒寫一次，陣列不能太大）
MAX_ROWS = 300_000
# 欄位 → 常見的欄名（小寫比對）
COLUMN_ALIASES: Dict[str, Tuple[str, ...]] = {
    "time": ("timestamp", "time", "datetime", "date_time", "date", "ts"),
    "wind_speed": ("wind_speed", "windspeed", "ws", "vw", "speed", "wind_speed_mean", "ws_mean"),
    "wind_direction": ("wind_direction", "winddirection", "wd", "dir", "direction", "wind_dir"),
    "ambient_temp": ("ambient_temp", "temperature", "temp", "air_temp", "t_air"),
    "turbulence_intensity": ("turbulence_intensity", "ti"),
    "wind_speed_std": ("wind_speed_std", "ws_std", "std", "wind_speed_sd", "ws_sd"),
    "humidity": ("humidity", "rh", "relative_humidity"),
    "pressure_hpa": ("pressure_hpa", "pressure", "p", "air_pressure"),
}
# 合理範圍（超出的當成缺值）
VALID_RANGES: Dict[str, Tuple[float, float]] = {
    "wind_speed": (0.0, 70.0),
    "wind_direction": (0.0, 360.0),
    "ambient_temp": (-40.0, 60.0),
    "turbulence_intensity": (0.0, 1.0),
    "wind_speed_std": (0.0, 20.0),
    "humidity": (0.0, 100.0),
    "pressure_hpa": (800.0, 1100.0),
}
# 序列裡可以有的量（風速之外都可以沒有）
QUANTITIES = ("wind_speed", "wind_direction", "ambient_temp", "turbulence_intensity", "humidity", "pressure_hpa")
ALIGNMENTS = ("replay", "absolute")
AT_END = ("loop", "hold", "auto")


class WindSeriesError(ValueError):
    """序列讀不進來（格式、欄位、筆數）。訊息直接給使用者看。"""


@dataclass
class MeasuredWindSeries:
    """讀好的實測序列。時間是 UTC 的 epoch 秒，依時間排序、不重複。

    Attributes:
        times: 每一筆的時間。
        values: 量 → 每一筆的值（缺值是 NaN）；只放序列裡有的量。風速已換算到輪轂高度。
        step_s: 取樣間隔（相鄰兩筆時間差的中位數）。
        max_gap_s: 兩筆有效值之間超過這麼久就不內插（那一段回到模型的風況）。
        summary: 讀檔的摘要（筆數、起訖、缺值、過長的缺口、換算的高度等），給 API 回報。
    """

    times: np.ndarray
    values: Dict[str, np.ndarray]
    step_s: float
    max_gap_s: float
    summary: Dict[str, object] = field(default_factory=dict)

    @property
    def start(self) -> float:
        return float(self.times[0])

    @property
    def end(self) -> float:
        return float(self.times[-1])

    def has(self, quantity: str) -> bool:
        return quantity in self.values

    def to_npz(self) -> bytes:
        """存進資料庫用（numpy npz）。"""
        buffer = io.BytesIO()
        arrays = {"times": self.times, **{f"v_{k}": v for k, v in self.values.items()},
                  "meta": np.array([self.step_s, self.max_gap_s])}
        np.savez_compressed(buffer, **arrays)
        return buffer.getvalue()

    @classmethod
    def from_npz(cls, data: bytes, summary: Optional[Dict[str, object]] = None) -> "MeasuredWindSeries":
        """由 :meth:`to_npz` 的結果還原。"""
        with np.load(io.BytesIO(data)) as loaded:
            times = loaded["times"].astype(np.float64)
            values = {name[2:]: loaded[name].astype(np.float64) for name in loaded.files if name.startswith("v_")}
            step_s, max_gap_s = (float(x) for x in loaded["meta"])
        return cls(times=times, values=values, step_s=step_s, max_gap_s=max_gap_s, summary=dict(summary or {}))

    # ── 取值 ────────────────────────────────────────────────────────────

    def __getstate__(self) -> Dict[str, object]:
        state = dict(self.__dict__)
        state.pop("_valid_cache", None)   # 存檔不帶快取（還原後再算）
        return state

    def _valid(self, quantity: str) -> Tuple[np.ndarray, np.ndarray]:
        """某個量的有效點（時間、值），算一次就記著。"""
        cache: Dict[str, Tuple[np.ndarray, np.ndarray]] = self.__dict__.setdefault("_valid_cache", {})
        found = cache.get(quantity)
        if found is None:
            values = self.values[quantity]
            keep = ~np.isnan(values)
            found = (self.times[keep], values[keep])
            cache[quantity] = found
        return found

    def value_at(self, quantity: str, t: float) -> Optional[float]:
        """序列時間 ``t``（epoch 秒）的值：前後兩筆有效值線性內插；超出範圍、或兩筆相隔超過 ``max_gap_s``
        回 None。"""
        if quantity not in self.values:
            return None
        times, values = self._valid(quantity)
        if len(times) == 0 or t < times[0] or t > times[-1]:
            return None
        i = int(np.searchsorted(times, t, side="right"))   # times[i-1] <= t < times[i]
        if i >= len(times) or times[i - 1] == t:
            return float(values[i - 1])
        t0, t1 = float(times[i - 1]), float(times[i])
        if t1 - t0 > self.max_gap_s:
            return None
        w = (t - t0) / (t1 - t0)
        a, b = float(values[i - 1]), float(values[i])
        if quantity == "wind_direction":
            return _blend_direction(a, b, w)
        return a + (b - a) * w

    def first_value(self, quantity: str) -> Optional[float]:
        if quantity not in self.values:
            return None
        _, values = self._valid(quantity)
        return float(values[0]) if len(values) else None

    def last_value(self, quantity: str) -> Optional[float]:
        if quantity not in self.values:
            return None
        _, values = self._valid(quantity)
        return float(values[-1]) if len(values) else None


def _blend_direction(a: float, b: float, w: float) -> float:
    """兩個風向（度）之間依權重內插：走較短的那一邊（單位向量內插）。"""
    ra, rb = math.radians(a), math.radians(b)
    x = (1 - w) * math.cos(ra) + w * math.cos(rb)
    y = (1 - w) * math.sin(ra) + w * math.sin(rb)
    if abs(x) < 1e-12 and abs(y) < 1e-12:
        return a if w < 0.5 else b
    return math.degrees(math.atan2(y, x)) % 360.0


@dataclass
class MeasuredWindPlayback:
    """一份序列怎麼播：對時方式、播到底之後、從序列的哪裡開始。

    ``anchor_sim`` 是開始播的那一刻（模擬時間，epoch 秒）——套用時還不知道，由風況模型在下一步用那一步的模擬
    時間定下來（:meth:`anchor`），和其他風況設定一樣不讀實際時間。

    Attributes:
        series: 序列。
        series_id: 序列在資料庫的 ID（狀態顯示用）。
        name: 序列的名稱（狀態顯示用；不對外）。
        alignment: ``replay`` / ``absolute``。
        at_end: ``loop`` / ``hold`` / ``auto``。
        start_offset_s: ``replay`` 時從序列起點之後多久開始播（秒）。
        anchor_sim: 開始播的模擬時間；None＝還沒定。
    """

    series: MeasuredWindSeries
    series_id: Optional[int] = None
    name: str = ""
    alignment: str = "replay"
    at_end: str = "loop"
    start_offset_s: float = 0.0
    anchor_sim: Optional[float] = None

    def __post_init__(self) -> None:
        if self.alignment not in ALIGNMENTS:
            raise WindSeriesError(f"alignment 要是 {ALIGNMENTS} 之一")
        if self.at_end not in AT_END:
            raise WindSeriesError(f"at_end 要是 {AT_END} 之一")
        span = self.series.end - self.series.start
        if not (0.0 <= self.start_offset_s <= span):
            raise WindSeriesError(f"start_offset_s 要在 0 到 {span:g} 秒之間")

    def anchor(self, sim_epoch: float) -> None:
        """定下開始播的模擬時間（只定一次）。"""
        if self.anchor_sim is None:
            self.anchor_sim = sim_epoch

    def series_time(self, sim_epoch: float) -> Optional[float]:
        """模擬時刻 → 序列裡的時間（已處理播到底）。``auto`` 播完之後、還沒開始之前回 None。"""
        series = self.series
        if self.alignment == "absolute":
            t = sim_epoch
        else:
            anchor = self.anchor_sim if self.anchor_sim is not None else sim_epoch
            t = series.start + self.start_offset_s + (sim_epoch - anchor)
        if series.start <= t <= series.end:
            return t
        if self.at_end == "hold":
            return min(max(t, series.start), series.end)
        if self.at_end == "loop":
            period = series.end - series.start + series.step_s
            return series.start + math.fmod(t - series.start, period) % period
        return None

    def value(self, quantity: str, sim_epoch: float) -> Optional[float]:
        """模擬時刻的某個量；這個時刻序列沒有值（沒有這個量、播完回到模型、過長的缺口）回 None。"""
        if not self.series.has(quantity):
            return None
        t = self.series_time(sim_epoch)
        if t is None:
            return None
        series = self.series
        if t > series.end:
            # 循環播放的接縫：最後一筆到第一筆之間（一個取樣間隔）內插
            last, first = series.last_value(quantity), series.first_value(quantity)
            if last is None or first is None:
                return None
            w = (t - series.end) / series.step_s
            if quantity == "wind_direction":
                return _blend_direction(last, first, w)
            return last + (first - last) * w
        return series.value_at(quantity, t)

    def status(self) -> Dict[str, object]:
        """給 ``WindEnvironmentModel.get_status`` 用。"""
        return {"series_id": self.series_id, "name": self.name, "alignment": self.alignment,
                "at_end": self.at_end, "start_offset_s": self.start_offset_s,
                "started_at": (datetime.fromtimestamp(self.anchor_sim, tz=timezone.utc).isoformat()
                               if self.anchor_sim is not None else None),
                "quantities": sorted(self.series.values)}


# ── 讀檔 ─────────────────────────────────────────────────────────────────


def _resolve_columns(header: Sequence[str], columns: Optional[Mapping[str, str]]) -> Dict[str, int]:
    lowered = [h.strip().lower() for h in header]
    out: Dict[str, int] = {}
    for key, aliases in COLUMN_ALIASES.items():
        if columns and key in columns and columns[key]:
            name = str(columns[key]).strip().lower()
            if name not in lowered:
                raise WindSeriesError(f"找不到欄位 {columns[key]!r}（{key}）；檔案的欄位：{list(header)}")
            out[key] = lowered.index(name)
            continue
        for alias in aliases:
            if alias in lowered:
                out[key] = lowered.index(alias)
                break
    unknown = sorted(set(columns or {}) - set(COLUMN_ALIASES))
    if unknown:
        raise WindSeriesError(f"不認得的欄位對應：{unknown}；可用：{sorted(COLUMN_ALIASES)}")
    for required in ("time", "wind_speed"):
        if required not in out:
            raise WindSeriesError(f"找不到{'時間' if required == 'time' else '風速'}欄（{required}）；"
                                  f"檔案的欄位：{list(header)}，可以用 columns 指定")
    return out


def _parse_time(text: str, tz) -> float:
    value = text.strip()
    if not value:
        raise ValueError("空的時間")
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00").replace("/", "-"))
    except ValueError:
        moment = datetime.strptime(value, "%Y-%m-%d %H:%M")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=tz)
    return moment.timestamp()


def _float(text: str) -> float:
    value = text.strip()
    if value == "" or value.lower() in ("nan", "na", "n/a", "null", "-", "--"):
        return math.nan
    return float(value)


def parse_csv(text: str, *, columns: Optional[Mapping[str, str]] = None, timezone_name: str = "Asia/Taipei",
              height_m: Optional[float] = None, hub_height_m: Optional[float] = None,
              shear_exponent: float = 0.14, max_gap_minutes: float = 180.0) -> MeasuredWindSeries:
    """讀一份實測風況的 CSV。

    Args:
        text: CSV 內容（第一列是欄名，逗號分隔）。
        columns: 欄位對應（``time`` / ``wind_speed`` / ``wind_direction`` / ``ambient_temp`` /
            ``turbulence_intensity`` / ``wind_speed_std`` / ``humidity`` / ``pressure_hpa`` → 檔案裡的欄名）；
            沒給的依常見欄名自動辨識。
        timezone_name: 沒有時區的時間視為這個時區（預設風場時區）。
        height_m: 風速的量測高度；和 ``hub_height_m`` 都給、而且不同時，用冪次律換算到輪轂高度。
        hub_height_m: 機組的輪轂高度。
        shear_exponent: 換算用的冪次律指數（中性大氣約 0.14）。
        max_gap_minutes: 兩筆有效值之間超過這麼久就不內插。

    Returns:
        序列。

    Raises:
        WindSeriesError: 格式錯誤、找不到欄位、有效的風速少於兩筆、筆數超過上限。
    """
    try:
        tz = site_timezone(timezone_name)
    except Exception as exc:  # noqa: BLE001  時區名稱錯了直接告訴使用者
        raise WindSeriesError(f"不認得的時區 {timezone_name!r}") from exc
    if max_gap_minutes <= 0:
        raise WindSeriesError("max_gap_minutes 要大於 0")
    if not (0.0 <= shear_exponent <= 0.6):
        raise WindSeriesError("shear_exponent 要在 0 到 0.6 之間")
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise WindSeriesError("檔案是空的") from exc
    index = _resolve_columns(header, columns)
    rows: List[Tuple[float, Dict[str, float]]] = []
    bad_time = 0
    for line_no, row in enumerate(reader, start=2):
        if not row or all(not cell.strip() for cell in row):
            continue
        if len(rows) >= MAX_ROWS:
            raise WindSeriesError(f"超過 {MAX_ROWS} 筆（10 分鐘一筆約 5.7 年）；請分段匯入")
        try:
            t = _parse_time(row[index["time"]], tz)
        except (ValueError, IndexError):
            bad_time += 1
            if bad_time > 10 and not rows:
                cell = row[index["time"]] if index["time"] < len(row) else ""
                raise WindSeriesError(f"第 {line_no} 列的時間讀不懂：{cell!r}")
            continue
        values: Dict[str, float] = {}
        for key, col in index.items():
            if key == "time":
                continue
            try:
                values[key] = _float(row[col]) if col < len(row) else math.nan
            except ValueError:
                values[key] = math.nan
        rows.append((t, values))
    if not rows:
        raise WindSeriesError("沒有讀到任何一筆")
    rows.sort(key=lambda item: item[0])
    times_list: List[float] = []
    kept: List[Dict[str, float]] = []
    duplicates = 0
    for t, values in rows:
        if times_list and t == times_list[-1]:
            duplicates += 1
            continue
        times_list.append(t)
        kept.append(values)
    times = np.array(times_list, dtype=np.float64)
    raw: Dict[str, np.ndarray] = {}
    out_of_range: Dict[str, int] = {}
    for key in index:
        if key == "time":
            continue
        column = np.array([v.get(key, math.nan) for v in kept], dtype=np.float64)
        lo, hi = VALID_RANGES[key]
        bad = ~np.isnan(column) & ((column < lo) | (column > hi))
        if bad.any():
            out_of_range[key] = int(bad.sum())
            column[bad] = math.nan
        raw[key] = column
    values: Dict[str, np.ndarray] = {}
    for key in ("wind_speed", "wind_direction", "ambient_temp", "humidity", "pressure_hpa"):
        if key in raw and not np.isnan(raw[key]).all():
            values[key] = raw[key]
    if "turbulence_intensity" in raw and not np.isnan(raw["turbulence_intensity"]).all():
        values["turbulence_intensity"] = raw["turbulence_intensity"]
    elif "wind_speed_std" in raw and "wind_speed" in raw:
        speed = raw["wind_speed"]
        with np.errstate(divide="ignore", invalid="ignore"):
            ti = np.where(speed > 1.0, raw["wind_speed_std"] / speed, np.nan)
        ti[(ti < 0) | (ti > 1)] = np.nan
        if not np.isnan(ti).all():
            values["turbulence_intensity"] = ti
    speed = values.get("wind_speed")
    if speed is None or int((~np.isnan(speed)).sum()) < 2:
        raise WindSeriesError("有效的風速少於兩筆")
    if len(times) < 2:
        raise WindSeriesError("至少要兩個不同的時間")
    scale = 1.0
    if height_m is not None and hub_height_m is not None:
        if height_m <= 0 or hub_height_m <= 0:
            raise WindSeriesError("高度要大於 0")
        scale = (hub_height_m / height_m) ** shear_exponent
        values["wind_speed"] = speed * scale
    step_s = float(np.median(np.diff(times)))
    max_gap_s = max(float(max_gap_minutes) * 60.0, 2.0 * step_s)   # 少一筆不算缺口
    valid_times = times[~np.isnan(values["wind_speed"])]
    gaps = np.diff(valid_times)
    long_gaps = int((gaps > max_gap_s).sum())
    summary: Dict[str, object] = {
        "rows": int(len(times)),
        "start": datetime.fromtimestamp(times[0], tz=timezone.utc).isoformat(),
        "end": datetime.fromtimestamp(times[-1], tz=timezone.utc).isoformat(),
        "step_s": step_s,
        "quantities": sorted(values),
        "missing": {k: int(np.isnan(v).sum()) for k, v in values.items()},
        "out_of_range": out_of_range,
        "duplicates_dropped": duplicates,
        "unreadable_times": bad_time,
        "long_gaps": long_gaps,
        "longest_gap_s": float(gaps.max()) if len(gaps) else 0.0,
        "max_gap_s": max_gap_s,
        "height_scale": round(scale, 4),
        "wind_speed_mean": round(float(np.nanmean(values["wind_speed"])), 3),
        "wind_speed_max": round(float(np.nanmax(values["wind_speed"])), 3),
        "timezone": timezone_name,
    }
    return MeasuredWindSeries(times=times, values=values, step_s=step_s, max_gap_s=max_gap_s, summary=summary)
