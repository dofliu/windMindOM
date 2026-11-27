"""機率式故障產生器（WMOM-20261125-06-b，EPIC-SF 第 5 項）。

讓持續運轉的即時風場自己發生故障，不用人手動注入。每台機組的故障是一個卜瓦松過程：

- 基本發生率＝``1 / mean_days_between_faults``（每台機組平均幾天一次）。
- 乘上機組權重（``turbine_weights``，沒列的是 1）。
- 耗損提高發生率：每個故障情境看一種耗損——冷卻類看熱交換器結垢、其餘機械類看疲勞累積損傷——
  情境的權重乘上 ``1 + wear_gain × 耗損（0–1）``。耗損高的機組整體更常故障，而且更常抽到和那種耗損
  有關的故障。
- 發生時依權重抽一個情境，劣化速度在 ``min_hours_to_full``–``max_hours_to_full`` 之間取對數均勻。

亂數用自己的 stream（``random.Random``），不碰模擬器既有的任何 RNG（物理改動守則）；每次檢查每台機組固定
抽三個數，不論有沒有發生、設定怎麼改，抽樣次數都一樣。整個物件可以 pickle，跟著即時模擬的狀態存檔，
重啟續跑之後接著同一條亂數序列。關著的時候完全不抽樣。

只作用在即時模擬：批次情境（題庫）的故障由排程決定，引擎在批次期間不呼叫它。

產生的故障和手動注入的走同一條路（``FaultEngine.inject``），之後的警報、跳機、開單、修復都一樣。
哪台機組什麼時候發生了什麼，是答案：只進不對外的故障紀錄，不進可觀測事件。
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Dict, List, Mapping, Tuple

from .physics.fault_engine import FAULT_SCENARIOS

if TYPE_CHECKING:
    from .physics.fault_engine import ActiveFault, FaultEngine
    from .physics.turbine_physics import TurbinePhysicsModel

# 預設不自動產生的情境：
# - blade_icing：結冰要看天氣，不是機組自己會壞的東西
# - yaw_misalignment：沒有任何警報，不會有工單，只有定檢修得掉——預設不產生，免得它無聲無息地累積
# - grid_voltage_sag：電網的事件，不是單一機組的故障
# - nuisance（接點鬆動）：機組自己會恢復，多半不會留下工單；它會一直佔著那台機組的名額
DEFAULT_EXCLUDED = frozenset({"blade_icing", "yaw_misalignment", "grid_voltage_sag"} | {
    sid for sid, scenario in FAULT_SCENARIOS.items() if scenario.category == "nuisance"})
# 看結垢的元件（冷卻類）；其餘看疲勞
_FOULING_COMPONENTS = frozenset({"converter_cooling_system", "nacelle_ventilation", "transformer"})


def default_weight(scenario_id: str) -> float:
    """情境的預設權重：預設不產生的是 0，其餘是 1。"""
    return 0.0 if scenario_id in DEFAULT_EXCLUDED else 1.0


@dataclass
class FaultGeneratorConfig:
    """故障產生器的設定。

    Attributes:
        enabled: 開不開。
        mean_days_between_faults: 每台機組平均幾天發生一次故障（耗損為 0、權重為 1 時）。
        scenario_weights: 情境 ID → 權重；沒列的用預設（:func:`default_weight`）。0＝不產生。
        turbine_weights: 機組 ID → 權重；沒列的是 1。0＝這台不產生。
        wear_gain: 耗損（0–1）對發生率的放大：權重乘上 ``1 + wear_gain × 耗損``。0＝耗損不影響。
        min_hours_to_full: 故障從開始到最嚴重最快幾小時。
        max_hours_to_full: 最慢幾小時。
        max_active_per_turbine: 一台機組同時最多幾個故障；到了就不再產生。潛伏的故障不算（:func:`is_latent`）。
        seed: 亂數種子。改了它，之後的故障序列就不同。
        fatigue_reference: 疲勞累積損傷（Miner 總和）到這個值算耗損 1。實測約每年 0.4（視風況），預設 0.1
            約是三個月。
        fouling_reference: 冷卻結垢係數到這個值算耗損 1。結垢約每年 0.044，預設 0.02 約是半年。
    """

    enabled: bool = False
    mean_days_between_faults: float = 30.0
    scenario_weights: Dict[str, float] = field(default_factory=dict)
    turbine_weights: Dict[str, float] = field(default_factory=dict)
    wear_gain: float = 4.0
    min_hours_to_full: float = 0.5
    max_hours_to_full: float = 48.0
    max_active_per_turbine: int = 1
    seed: int = 20261126
    fatigue_reference: float = 0.1
    fouling_reference: float = 0.02

    def to_dict(self) -> Dict[str, object]:
        """可直接轉成 JSON 的 dict。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "FaultGeneratorConfig":
        """由 dict 建立並檢查；不認得的欄位、情境、不合理的數字都丟 ``ValueError``。

        Args:
            data: 設定；沒給的欄位用預設值。

        Returns:
            設定。
        """
        known = set(cls.__dataclass_fields__)
        unknown = sorted(set(data) - known)
        if unknown:
            raise ValueError(f"不認得的設定：{unknown}")
        config = cls(**dict(data))  # type: ignore[arg-type]  # 型別在下面逐欄檢查
        if not isinstance(config.enabled, bool):
            raise ValueError("enabled 要是 true / false")
        for name in ("mean_days_between_faults", "wear_gain", "min_hours_to_full", "max_hours_to_full",
                     "fatigue_reference", "fouling_reference"):
            value = getattr(config, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} 要是數字")
            setattr(config, name, float(value))
        if config.mean_days_between_faults <= 0:
            raise ValueError("mean_days_between_faults 要大於 0")
        if config.fatigue_reference <= 0 or config.fouling_reference <= 0:
            raise ValueError("fatigue_reference、fouling_reference 要大於 0")
        if config.wear_gain < 0:
            raise ValueError("wear_gain 不能是負的")
        if not 0 < config.min_hours_to_full <= config.max_hours_to_full:
            raise ValueError("要 0 < min_hours_to_full ≤ max_hours_to_full")
        if isinstance(config.max_active_per_turbine, bool) or not isinstance(config.max_active_per_turbine, int) \
                or config.max_active_per_turbine < 1:
            raise ValueError("max_active_per_turbine 要是 ≥ 1 的整數")
        if isinstance(config.seed, bool) or not isinstance(config.seed, int):
            raise ValueError("seed 要是整數")
        for name in ("scenario_weights", "turbine_weights"):
            weights = getattr(config, name)
            if not isinstance(weights, dict):
                raise ValueError(f"{name} 要是 {{ID: 權重}}")
            cleaned: Dict[str, float] = {}
            for key, value in weights.items():
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
                        or value < 0:
                    raise ValueError(f"{name}[{key}] 要是 ≥ 0 的數字")
                cleaned[str(key)] = float(value)
            setattr(config, name, cleaned)
        strangers = sorted(set(config.scenario_weights) - set(FAULT_SCENARIOS))
        if strangers:
            raise ValueError(f"沒有這些故障情境：{strangers}")
        return config


@dataclass(frozen=True)
class GeneratedFault:
    """產生器這一步注入的一個故障。"""

    turbine_id: str
    scenario_id: str
    severity_rate: float


def turbine_wear(model: "TurbinePhysicsModel", config: FaultGeneratorConfig | None = None) -> Dict[str, float]:
    """一台機組的耗損（0–1）：疲勞累積損傷與冷卻結垢，各除以設定的參考值。

    Args:
        model: 機組的物理模型。
        config: 產生器的設定（取參考值）；None＝預設。

    Returns:
        ``{"fatigue": 0–1, "fouling": 0–1}``。
    """
    fatigue = model.fatigue
    damage = max(fatigue.damage_tower_fa, fatigue.damage_tower_ss, fatigue.damage_blade_flap,
                 fatigue.damage_blade_edge)
    config = config or FaultGeneratorConfig()
    damage = float(damage) / config.fatigue_reference
    fouling = model.cooling.water_loop.fouling / config.fouling_reference
    return {"fatigue": min(1.0, max(0.0, float(damage))), "fouling": min(1.0, max(0.0, float(fouling)))}


def is_latent(fault: "ActiveFault") -> bool:
    """潛伏的故障：嚴重度已經到頂，卻從沒跳過機、現在也沒有預期碼成立。

    在目前的條件下（季節、負載）它的訊號到不了警報門檻，沒有警報就沒有工單、修不掉。它不佔機組的故障
    名額，那台機組照樣會發生別的故障（WMOM-20261126-09，72 小時長跑裡 14 個故障有 5 個這樣卡住機組）。
    條件變了開始報警時，它又算回名額裡（只影響之後要不要再產生，不會移掉已經有的故障）。

    Args:
        fault: 故障引擎裡的故障。

    Returns:
        是不是潛伏。
    """
    return (fault.severity >= fault.max_severity - 1e-9 and not fault.tripped and not fault.active_alarms)


class FaultGenerator:
    """機率式故障產生器。掛在 ``WindFarmSimulator`` 底下，每一步呼叫 :meth:`step`。"""

    CHECK_INTERVAL_S = 60.0   # 每累積這麼多模擬秒檢查一次（不必每一步都抽）

    def __init__(self, config: FaultGeneratorConfig | None = None) -> None:
        self.config = config or FaultGeneratorConfig()
        self._rng = random.Random(self.config.seed)
        self._accumulated = 0.0
        self.generated = 0   # 開始以來產生了幾個

    def configure(self, config: FaultGeneratorConfig) -> None:
        """換設定。種子變了才重設亂數序列；只改發生率或權重時序列接著走。"""
        reseed = config.seed != self.config.seed
        self.config = config
        if reseed:
            self._rng = random.Random(config.seed)

    def scenario_weights(self, wear: Mapping[str, float]) -> List[Tuple[str, float]]:
        """各情境在某個耗損下的權重（含耗損的放大），依情境 ID 排序。"""
        config = self.config
        out: List[Tuple[str, float]] = []
        for scenario_id in sorted(FAULT_SCENARIOS):
            base = config.scenario_weights.get(scenario_id, default_weight(scenario_id))
            if base <= 0:
                continue
            component = FAULT_SCENARIOS[scenario_id].component
            source = "fouling" if component in _FOULING_COMPONENTS else "fatigue"
            out.append((scenario_id, base * (1.0 + config.wear_gain * wear.get(source, 0.0))))
        return out

    def hazard_per_second(self, turbine_id: str, wear: Mapping[str, float]) -> float:
        """一台機組現在的故障發生率（每秒）。"""
        config = self.config
        weighted = self.scenario_weights(wear)
        plain = self.scenario_weights({})
        if not weighted or not plain:
            return 0.0
        # 耗損的放大：各情境放大後的權重總和 ÷ 沒有耗損時的總和
        boost = sum(w for _, w in weighted) / sum(w for _, w in plain)
        base = 1.0 / (config.mean_days_between_faults * 86400.0)
        return base * config.turbine_weights.get(turbine_id, 1.0) * boost

    def step(self, dt: float, turbines: Mapping[str, "TurbinePhysicsModel"],
             fault_engine: "FaultEngine") -> List[GeneratedFault]:
        """推進 ``dt`` 秒；到了檢查的時候替每台機組擲一次，發生就注入。

        Args:
            dt: 這一步多長（模擬秒）。
            turbines: 機組 ID → 物理模型。
            fault_engine: 故障引擎（注入用）。

        Returns:
            這一步注入的故障。
        """
        if not self.config.enabled:
            return []
        self._accumulated += dt
        if self._accumulated < self.CHECK_INTERVAL_S:
            return []
        elapsed, self._accumulated = self._accumulated, 0.0
        config = self.config
        made: List[GeneratedFault] = []
        active: Dict[str, List[str]] = {}     # 機組上全部的故障（不重複產生同一種）
        holding: Dict[str, int] = {}          # 佔名額的（潛伏的不算）
        for fault in fault_engine.active_faults:
            active.setdefault(fault.turbine_id, []).append(fault.scenario_id)
            if not is_latent(fault):
                holding[fault.turbine_id] = holding.get(fault.turbine_id, 0) + 1
        log_min, log_max = math.log(config.min_hours_to_full), math.log(config.max_hours_to_full)
        for turbine_id in sorted(turbines):
            # 每台機組固定抽三個數：有沒有發生、哪一種、多快。抽樣次數不隨結果或設定改變
            happens, which, speed = self._rng.random(), self._rng.random(), self._rng.random()
            wear = turbine_wear(turbines[turbine_id], config)
            probability = 1.0 - math.exp(-self.hazard_per_second(turbine_id, wear) * elapsed)
            if happens >= probability:
                continue
            existing = active.get(turbine_id, [])
            if holding.get(turbine_id, 0) >= config.max_active_per_turbine:
                continue
            choices = [(sid, w) for sid, w in self.scenario_weights(wear) if sid not in existing]
            total = sum(w for _, w in choices)
            if total <= 0:
                continue
            mark, scenario_id = which * total, choices[-1][0]
            for candidate, weight in choices:
                mark -= weight
                if mark < 0:
                    scenario_id = candidate
                    break
            hours = math.exp(log_min + speed * (log_max - log_min))
            rate = 1.0 / (hours * 3600.0)
            if fault_engine.inject(scenario_id, turbine_id, severity_rate=rate, initial_severity=0.0):
                active.setdefault(turbine_id, []).append(scenario_id)
                holding[turbine_id] = holding.get(turbine_id, 0) + 1
                made.append(GeneratedFault(turbine_id=turbine_id, scenario_id=scenario_id, severity_rate=rate))
                self.generated += 1
        return made
