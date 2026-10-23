"""風場層級事件（WMOM-20261021-08-b，EPIC-DS Phase 4-b）：看起來像故障、其實不是機組故障的干擾。

故障情境（``FaultEngine``）作用在單一機組；這裡的事件作用在整個風場，由 ``WindFarmSimulator.generate_bulk``
依排程套用：

- ``grid_voltage_dip``：電網電壓驟降（風場電網模型的電壓暫時改為 ``magnitude`` p.u.）。夠深夠久時各機組的
  電網保護 / LVRT 停機（481 / 482 + 021），電壓回來後自動重啟。
- ``grid_frequency_excursion``：電網頻率越界（偏移 ``magnitude`` Hz）→ 489 + 021。
- ``rapid_wind_direction_change``：風向在短時間內來回擺動（振幅 ``magnitude`` 度、週期
  ``WIND_SWING_PERIOD_S``），偏航追不上而逾時（手冊 §11.3：風向變化快的場址會有偏航逾時 223 這類
  nuisance 跳機）。

標準答案把這些事件造成的警報 / 跳機標成 ``nuisance`` case（``simulator/ground_truth.py``），答案文字集中在
``FARM_EVENT_KINDS``；事件排程只進標準答案與出題端的情境設定，不進給受測端的資料（盲測）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple

# 風向來回擺動的週期（秒）：峰值變化率 = 振幅 × 2π / 週期，60° 振幅約 2°/s，超過偏航最快約 0.9°/s
WIND_SWING_PERIOD_S = 180.0
# 擺動在事件開頭 / 結尾各花這麼久漸強 / 漸弱（避免風向瞬間跳動）
WIND_SWING_RAMP_S = 60.0


@dataclass(frozen=True)
class FarmEventKind:
    """一種風場層級事件的定義與標準答案文字。

    Attributes:
        id: 事件種類 ID。
        nuisance_cause: 標準答案 nuisance case 的成因分類（``rag_assistant_vocabulary.json`` 的
            ``nuisance_causes``）。
        origin: 成因來源（標準答案的 ``origin``）。
        event_codes: 這種事件會讓機組送出的事件碼：事件期間（含之後的寬限）出現、沒被故障 case 認領的
            這些碼歸給本事件的 nuisance case。
        key_signals: 看得出這個事件的 tag。
        difficulty: 對 RAG 判斷而言的難度（easy / medium / hard）。
        magnitude_unit: ``magnitude`` 的單位說明。
        magnitude_range: ``magnitude`` 的合法範圍（含端點）。
        name_zh / name_en: 名稱。
        root_cause_zh / root_cause_en: 根因（評分端看）。
        expected_actions_zh / expected_actions_en: 建議處置（標「（手冊）」者出自手冊）。
        simulation_notes_zh / simulation_notes_en: 模擬與真實的差異。
    """

    id: str
    nuisance_cause: str
    origin: str
    event_codes: Tuple[int, ...]
    key_signals: Tuple[str, ...]
    difficulty: str
    magnitude_unit: str
    magnitude_range: Tuple[float, float]
    name_zh: str
    name_en: str
    root_cause_zh: str
    root_cause_en: str
    expected_actions_zh: Tuple[str, ...]
    expected_actions_en: Tuple[str, ...]
    simulation_notes_zh: Tuple[str, ...] = ()
    simulation_notes_en: Tuple[str, ...] = ()


FARM_EVENT_KINDS: Dict[str, FarmEventKind] = {
    "grid_voltage_dip": FarmEventKind(
        id="grid_voltage_dip",
        nuisance_cause="grid_disturbance",
        origin="external_grid",
        # 欠壓（481 / 482）＋ 變頻器跳機要求（021）；過壓（475）在電壓恢復的暫態也可能出現
        event_codes=(481, 482, 475, 21),
        key_signals=("WCNV_VtgMsCnvGd1", "WCNV_VtgMsCnvGd2", "WCNV_VtgMsCnvGd3"),
        difficulty="easy",
        magnitude_unit="p.u.（電網電壓，額定 = 1.0）",
        magnitude_range=(0.0, 0.95),
        name_zh="電網電壓驟降",
        name_en="Grid voltage dip",
        root_cause_zh="電網側電壓驟降（外部電網事件，不是機組故障）：全場機組幾乎同時以電網保護 / 欠壓停機，電壓恢復後自動重啟。",
        root_cause_en="A grid-side voltage dip (external grid event, not a turbine fault): the turbines trip on grid protection / undervoltage almost simultaneously and restart automatically once the voltage is back.",
        expected_actions_zh=(
            "比對全場機組：同一時刻多台跳同樣的電網碼，是電網事件而不是機組故障",
            "向電網調度 / 變電站確認事件紀錄，確認電壓已恢復",
            "機組自動重啟即可；一小時內多次封鎖重啟（A039）時由操作員復位（手冊）",
        ),
        expected_actions_en=(
            "Compare across the farm: several turbines tripping on the same grid event at the same moment points to the grid, not a turbine fault.",
            "Confirm the event with the grid operator / substation log and that the voltage has recovered.",
            "Let the turbines restart automatically; if auto restart is blocked (A039) after repeated trips, reset by an operator (manual).",
        ),
        simulation_notes_zh=("風場電網模型在事件期間把電壓固定在設定值（加量測雜訊）；各機組依個體差的保護裕度決定停不停。",),
        simulation_notes_en=("The farm grid model holds the voltage at the set value (plus measurement noise) during the event; each turbine trips or rides through according to its individual protection margin.",),
    ),
    "grid_frequency_excursion": FarmEventKind(
        id="grid_frequency_excursion",
        nuisance_cause="grid_disturbance",
        origin="external_grid",
        event_codes=(489, 21),
        key_signals=("WCNV_CnvGnFrq",),
        difficulty="easy",
        magnitude_unit="Hz（相對額定頻率的偏移，可正可負）",
        magnitude_range=(-3.0, 3.0),
        name_zh="電網頻率越界",
        name_en="Grid frequency excursion",
        root_cause_zh="電網頻率越界（外部電網事件，不是機組故障）：全場機組以頻率越界停機，頻率恢復後自動重啟。",
        root_cause_en="A grid frequency excursion (external grid event, not a turbine fault): the turbines trip on frequency out of bounds and restart automatically once the frequency is back.",
        expected_actions_zh=(
            "比對全場機組：多台同時跳頻率越界，是電網事件",
            "向電網調度確認頻率事件，確認已恢復",
            "機組自動重啟即可；重啟被封鎖（A039）時由操作員復位（手冊）",
        ),
        expected_actions_en=(
            "Compare across the farm: several turbines tripping on frequency out of bounds at once is a grid event.",
            "Confirm the frequency event with the grid operator and that it has recovered.",
            "Let the turbines restart automatically; reset by an operator if auto restart is blocked (A039) (manual).",
        ),
    ),
    "rapid_wind_direction_change": FarmEventKind(
        id="rapid_wind_direction_change",
        nuisance_cause="wind_direction_change",
        origin="environmental",
        event_codes=(223,),
        key_signals=("WMET_WDirAbs", "WYAW_YwVn1AlgnAvg5s"),
        difficulty="medium",
        magnitude_unit="度（風向來回擺動的振幅）",
        magnitude_range=(5.0, 120.0),
        name_zh="風向快速變化",
        name_en="Rapid wind direction change",
        root_cause_zh="風向在短時間內大幅來回變化（環境因素，不是偏航系統故障）：偏航追不上而逾時跳機（223），風向穩定後自動重啟；手冊 §11.3 列為已知無害的 nuisance 跳機。",
        root_cause_en="The wind direction swings strongly within a short time (environmental, not a yaw system fault): the yaw cannot keep up and times out (223), restarting automatically once the direction settles; the manual (§11.3) lists this as a known harmless nuisance trip.",
        expected_actions_zh=(
            "比對風向趨勢與同風場其他機組：多台在風向劇烈變化時偏航逾時，是環境造成",
            "確認偏航馬達、煞車與齒輪沒有異常（逾時只在風向劇變時出現）",
            "此場址常見時，可依手冊把偏航逾時的自動重啟次數設高（手冊 §11.3），問題排除後再改回",
        ),
        expected_actions_en=(
            "Compare the wind direction trend and the other turbines: several yaw time-outs while the direction swings point to the environment.",
            "Confirm the yaw motors, brakes and gears are fine (the time-outs only happen during the swings).",
            "Where this is common at the site, raise the auto-restart setting for the yaw time-out as the manual describes (§11.3), and set it back afterwards.",
        ),
        simulation_notes_zh=(
            f"風向以 {int(WIND_SWING_PERIOD_S)} 秒週期正弦擺動（開頭 / 結尾各 {int(WIND_SWING_RAMP_S)} 秒漸強 / 漸弱），全場同一個擺動；真實的風向變化不規則、各機組略有時差。",
            "振幅約 26° 以下時風向變化率不超過偏航最快速度，偏航追得上、不會逾時（事件照樣記在標準答案，但沒有 case）。",
            "模擬器假設偏航逾時的自動重啟已開啟（上限照手冊 Appendix C 的每小時次數；手冊 §11.3 的出廠設定是 0）。",
        ),
        simulation_notes_en=(
            f"The direction swings sinusoidally with a {int(WIND_SWING_PERIOD_S)} s period (ramped in / out over {int(WIND_SWING_RAMP_S)} s) and is identical across the farm; real direction changes are irregular and reach the turbines at slightly different times.",
            "Below an amplitude of about 26° the direction changes no faster than the yaw can turn, so it never times out (the event is still listed in the answer key, with no cases).",
            "The simulator assumes auto restart is enabled for the yaw time-out (limited per hour as in the manual's Appendix C; the factory setting in §11.3 is 0).",
        ),
    ),
}


@dataclass(frozen=True)
class FarmEvent:
    """一筆排定的風場層級事件。

    Attributes:
        kind: ``FARM_EVENT_KINDS`` 的 ID。
        offset_seconds: 相對批次起點的開始時間（秒）。
        duration_s: 持續秒數。
        magnitude: 強度（單位見 ``FarmEventKind.magnitude_unit``）。
    """

    kind: str
    offset_seconds: float
    duration_s: float
    magnitude: float

    @property
    def end_seconds(self) -> float:
        """結束時間（相對批次起點，秒）。"""
        return self.offset_seconds + self.duration_s

    def is_active(self, elapsed_s: float) -> bool:
        """``elapsed_s``（相對批次起點）時事件是否進行中（含開始、不含結束）。"""
        return self.offset_seconds <= elapsed_s < self.end_seconds

    def wind_direction_offset(self, elapsed_s: float) -> float:
        """``rapid_wind_direction_change`` 在 ``elapsed_s`` 的風向偏移（度；不在事件內為 0）。"""
        if self.kind != "rapid_wind_direction_change" or not self.is_active(elapsed_s):
            return 0.0
        t = elapsed_s - self.offset_seconds
        envelope = min(1.0, t / WIND_SWING_RAMP_S, (self.duration_s - t) / WIND_SWING_RAMP_S)
        return self.magnitude * max(0.0, envelope) * math.sin(2.0 * math.pi * t / WIND_SWING_PERIOD_S)
