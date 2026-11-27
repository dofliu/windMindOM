"""本風場修過的故障回饋到成本模型的故障率（WMOM-20261127-07，DEC-20261127-09）。

成本引擎（K13）每個元件有一個年故障率（每台機組每年幾次，``annual_failure_freq``），蒙地卡羅在它的
±30% 之間取三角分布（``freq_min/ml/max``，``adapter.load_engine_params_from_farm(stochastic=True)``）。
這些是離岸參考值；仿真風場跑久了，自己的維修紀錄比參考值更能代表這座風場。

**可信度加權**（credibility weighting）::

    本風場的故障率 = (K13 故障率 × 先驗機組年 + 修過的次數) ÷ (先驗機組年 + 運轉機組年)

- 先驗機組年（``prior_turbine_years``，預設 14）：把 K13 的故障率當成這麼多機組年的經驗。14 台的風場
  運轉一年時，本風場的紀錄與 K13 各佔一半。
- 修過的次數：運維閉環裡由工單修好、故障產生器產生的故障（不對外的故障紀錄；手動注入的是題目或展示，
  不算，另外回報幾筆），依情境對到 K13 元件（``data/z72_repair_classes.json`` 的 ``k13_components``，假設值）。
- 運轉機組年：運轉狀態紀錄的時數合計 ÷ 8766。

只更新模擬器有對應情境的元件：塔架、輪轂、吊車這類模擬器不會讓它壞的元件，「沒修過」不是證據，維持 K13。
三角分布的相對寬度不變（照 adapter 給的比例），只移動中心；確定性的試算（``annual_failure_freq``）一起改。

這只用在主管看的成本試算；修了什麼是答案，不會出現在對外 API 或準備卡。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Dict, List, Mapping, Optional, Sequence

from modules.cost.engine.cost_cal.data_classes import ComponentParams

REPAIR_CLASSES_PATH = Path(__file__).resolve().parent.parent / "data" / "z72_repair_classes.json"

# 14 台的風場運轉一年，本風場的紀錄與 K13 各佔一半
DEFAULT_PRIOR_TURBINE_YEARS = 14.0
HOURS_PER_YEAR = 8766.0


@lru_cache(maxsize=1)
def component_map() -> Mapping[str, Optional[str]]:
    """故障情境 → K13 元件代碼（None＝不是元件故障，不算進故障率）。讀一次就留著（唯讀）。"""
    data = json.loads(REPAIR_CLASSES_PATH.read_text(encoding="utf-8"))
    return MappingProxyType({str(k): (str(v) if v else None) for k, v in data["k13_components"].items()})


def k13_component(scenario_id: str) -> Optional[str]:
    """這個故障情境算哪一個 K13 元件；不是元件故障或表上沒有的是 None。"""
    return component_map().get(scenario_id)


@dataclass(frozen=True)
class FailureObservations:
    """一段時間裡本風場的維修紀錄。

    Attributes:
        repairs: 故障情境 → 由工單修好的次數（故障產生器產生的）。
        turbine_years: 運轉機組年（運轉狀態紀錄的時數合計 ÷ 8766）。
        start: 時間下限（ISO 8601，給畫面看）。
        end: 時間上限。
        excluded_manual: 由工單修好、但是手動注入的故障有幾筆（不算進故障率）。
        farm_registry: 讀風場成本設定用的 registry（監控伺服器的那一個）；None＝成本模組預設的。
    """

    repairs: Mapping[str, int]
    turbine_years: float
    start: Optional[str] = None
    end: Optional[str] = None
    excluded_manual: int = 0
    farm_registry: object = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class RateUpdate:
    """一個 K13 元件的故障率回饋。

    Attributes:
        code: 元件代碼（``MDK10``）。
        name: 元件名稱。
        modelled: 模擬器有沒有會讓它壞的情境；沒有的不更新。
        k13_rate: K13 的年故障率（每台機組每年）。
        repairs: 這段時間修過幾次。
        turbine_years: 運轉機組年。
        prior_turbine_years: 先驗機組年。
        rate: 回饋後的年故障率。
        weight: 本風場紀錄佔的比重（運轉機組年 ÷（先驗＋運轉））；沒更新的是 0。
        scenarios: 對到這個元件的故障情境。
    """

    code: str
    name: str
    modelled: bool
    k13_rate: float
    repairs: int
    turbine_years: float
    prior_turbine_years: float
    rate: float
    weight: float
    scenarios: tuple[str, ...] = field(default_factory=tuple)

    @property
    def observed_rate(self) -> Optional[float]:
        """只看本風場的年故障率（修過的次數 ÷ 運轉機組年）；沒有運轉紀錄時是 None。"""
        return self.repairs / self.turbine_years if self.turbine_years > 0 else None

    def to_dict(self) -> Dict[str, object]:
        """給 API 用的 dict。"""
        observed = self.observed_rate
        return {"code": self.code, "name": self.name, "modelled": self.modelled,
                "k13_rate": round(self.k13_rate, 6), "repairs": self.repairs,
                "observed_rate": round(observed, 6) if observed is not None else None,
                "rate": round(self.rate, 6), "weight": round(self.weight, 4), "scenarios": list(self.scenarios)}


def empirical_rates(components: Sequence[ComponentParams], observations: FailureObservations,
                    prior_turbine_years: float = DEFAULT_PRIOR_TURBINE_YEARS) -> List[RateUpdate]:
    """各 K13 元件回饋後的年故障率（可信度加權，見模組說明）。

    Args:
        components: 成本引擎的元件（``EngineParams.components``）。
        observations: 本風場的維修紀錄。
        prior_turbine_years: 先驗機組年（> 0）。

    Returns:
        每個元件一筆，順序同 ``components``。

    Raises:
        ValueError: ``prior_turbine_years`` 不是正數，或運轉機組年是負的。
    """
    if not prior_turbine_years > 0:
        raise ValueError("prior_turbine_years 要大於 0")
    exposure = float(observations.turbine_years)
    if exposure < 0:
        raise ValueError("turbine_years 不能是負的")
    by_code: Dict[str, List[str]] = {}
    for scenario_id, code in sorted(component_map().items()):
        if code is not None:
            by_code.setdefault(code, []).append(scenario_id)
    out: List[RateUpdate] = []
    for comp in components:
        scenarios = tuple(by_code.get(comp.component_code, ()))
        k13_rate = float(comp.annual_failure_freq)
        repairs = sum(int(observations.repairs.get(sid, 0)) for sid in scenarios)
        if scenarios:
            rate = (k13_rate * prior_turbine_years + repairs) / (prior_turbine_years + exposure)
            weight = exposure / (prior_turbine_years + exposure)
        else:
            rate, weight = k13_rate, 0.0
        out.append(RateUpdate(code=comp.component_code, name=comp.component_name, modelled=bool(scenarios),
                              k13_rate=k13_rate, repairs=repairs, turbine_years=exposure,
                              prior_turbine_years=float(prior_turbine_years), rate=rate, weight=weight,
                              scenarios=scenarios))
    return out


def apply_rate_updates(components: Sequence[ComponentParams], updates: Sequence[RateUpdate]) -> None:
    """把回饋後的故障率寫進元件（就地改）：確定性的 ``annual_failure_freq`` 與蒙地卡羅的三角分布。

    三角分布的相對寬度不變（``freq_min / freq_ml``、``freq_max / freq_ml`` 照原本的比例），只移動中心。

    Args:
        components: 成本引擎的元件；只改有對應情境的。
        updates: :func:`empirical_rates` 的結果。
    """
    by_code = {update.code: update for update in updates if update.modelled}
    for comp in components:
        update = by_code.get(comp.component_code)
        if update is None:
            continue
        comp.annual_failure_freq = update.rate
        if comp.freq_ml:
            low = (comp.freq_min / comp.freq_ml) if comp.freq_min is not None else None
            high = (comp.freq_max / comp.freq_ml) if comp.freq_max is not None else None
            comp.freq_ml = update.rate
            comp.freq_min = update.rate * low if low is not None else None
            comp.freq_max = update.rate * high if high is not None else None


def unmapped_repairs(observations: FailureObservations) -> Dict[str, int]:
    """修過、但不算進故障率的情境（不是元件故障，或表上沒有）。"""
    return {sid: int(n) for sid, n in sorted(observations.repairs.items()) if k13_component(sid) is None and n}


# ── 本風場維修紀錄的來源（監控的伺服器在開機時登記；成本模組不 import 監控） ────────────────────────

ObservationProvider = Callable[[str], Optional[FailureObservations]]
_provider: Optional[ObservationProvider] = None


def set_observation_provider(provider: Optional[ObservationProvider]) -> None:
    """登記維修紀錄的來源：風場 ID → 那座風場的維修紀錄（不是仿真風場、沒有紀錄時回 None）。"""
    global _provider
    _provider = provider


def get_observation_provider() -> Optional[ObservationProvider]:
    """目前登記的來源；沒有登記是 None。"""
    return _provider
