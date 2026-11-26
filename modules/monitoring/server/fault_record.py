"""不對外的故障紀錄（WMOM-20261125-06-c，EPIC-SF 第 5 項）。

即時風場的 Live 版標準答案：每一筆故障什麼時候發生、第一次送出預期碼是什麼時候、什麼時候跳機、跳了幾次、
什麼時候被哪張工單修好。批次情境的答案是 ``scenario_ground_truth``（``simulator/ground_truth.py``）；
這裡記的是持續運轉的風場，答案欄位（根因、元件、處置、重點訊號）用同一個 ``scenario_answer``。

**只給評分端**：存在風場 DB 的 ``fault_records``，由永遠強制的主管端點讀。不進對外 API、準備卡、
可觀測事件（盲測守則）。

三個時機由 ``DataBroker`` 呼叫：

- 故障出現（產生器或手動注入）→ :meth:`on_fault_started`
- PLC 事件 → :meth:`on_plc_event`（預期碼第一次出現、跳機、其他碼）
- 故障消失（工單完工修掉、或管理端清除）→ :meth:`on_fault_cleared`

時間一律是風場時鐘。任何一步出錯都只記 log，不影響模擬。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Optional

from simulator.ground_truth import scenario_answer
from simulator.physics.fault_engine import FAULT_SCENARIOS
from simulator.physics.plc_protection import PlcEvent
from simulator.time_utils import iso_utc

if TYPE_CHECKING:
    from server.data_broker import DataBroker

logger = logging.getLogger(__name__)

ORIGIN_GENERATOR = "generator"   # 機率式故障產生器
ORIGIN_MANUAL = "manual"         # 管理端手動注入
_COUNTED_KINDS = frozenset({"alarm_raised", "trip"})


class FaultRecorder:
    """把即時風場的故障記進 ``fault_records``。"""

    def __init__(self, broker: "DataBroker") -> None:
        self._broker = broker

    def _now(self) -> Optional[str]:
        clock = self._broker.live_clock()
        return iso_utc(clock) if clock is not None else None

    def on_fault_started(self, turbine_id: str, scenario_id: str, origin: str,
                         severity_rate: Optional[float] = None) -> None:
        """故障出現。同一台機組的同一個情境已經有還沒結束的紀錄時不重複開（重啟後重跑的那幾步）。"""
        now = self._now()
        if now is None or scenario_id not in FAULT_SCENARIOS:
            return
        try:
            self._broker.storage.open_fault_record(turbine_id, scenario_id, origin, now, severity_rate)
        except Exception:  # noqa: BLE001
            logger.exception("故障紀錄：開不了 %s / %s", turbine_id, scenario_id)

    def on_plc_event(self, turbine_id: str, event: PlcEvent, timestamp: Optional[str] = None) -> None:
        """PLC 事件：更新這台機組還沒結束的紀錄。"""
        if event.kind not in _COUNTED_KINDS:
            return
        stamp = timestamp or self._now()
        if stamp is None:
            return
        try:
            storage = self._broker.storage
            for record in storage.open_fault_records(turbine_id):
                scenario = FAULT_SCENARIOS.get(str(record["scenario_id"]))
                if scenario is None:
                    continue
                expected = {int(a["code"]) for a in scenario.alarm_codes}
                changes: Dict[str, object] = {}
                observed: List[Dict[str, object]] = list(record["observed"])
                if len(observed) < 200:
                    observed.append({"ts": stamp, "code": event.code, "level": event.level, "kind": event.kind,
                                     "expected": event.code in expected})
                    changes["observed"] = observed
                if event.code in expected:
                    if record["first_alarm_ts"] is None:
                        changes.update(first_alarm_ts=stamp, first_alarm_code=event.code)
                    if event.kind == "trip":
                        changes["trip_count"] = int(record["trip_count"] or 0) + 1
                        if record["trip_ts"] is None:
                            changes.update(trip_ts=stamp, trip_code=event.code)
                if changes:
                    storage.update_fault_record(int(record["id"]), **changes)
        except Exception:  # noqa: BLE001
            logger.exception("故障紀錄：更新不了 %s 的事件 %s", turbine_id, event.code)

    def on_fault_cleared(self, turbine_id: str, scenario_id: str, work_order_key: Optional[str] = None) -> None:
        """故障消失：結束紀錄。

        運維閉環完工修掉故障時直接帶工單編號呼叫；broker 之後偵測到故障消失再呼叫一次時，紀錄已經結束、
        不會被改成「管理端清除」。

        Args:
            turbine_id: 機組 ID。
            scenario_id: 故障情境 ID。
            work_order_key: 修掉它的工單編號；None＝管理端清除。
        """
        now = self._now()
        by = work_order_key
        if now is None:
            return
        try:
            storage = self._broker.storage
            for record in storage.open_fault_records(turbine_id):
                if record["scenario_id"] == scenario_id:
                    storage.update_fault_record(int(record["id"]), cleared_ts=now,
                                                cleared_by=f"work_order:{by}" if by else "manual")
        except Exception:  # noqa: BLE001
            logger.exception("故障紀錄：結束不了 %s / %s", turbine_id, scenario_id)

    def cases(self, turbine_id: Optional[str] = None, open_only: bool = False,
              limit: int = 500) -> List[Dict[str, object]]:
        """故障紀錄加上答案欄位（根因、元件、處置、重點訊號），新的在前。

        Args:
            turbine_id: 只取這台機組；None＝全部。
            open_only: 只取還沒修好的。
            limit: 最多幾筆。
        """
        out: List[Dict[str, object]] = []
        for record in self._broker.storage.fault_records(turbine_id=turbine_id, open_only=open_only,
                                                         limit=limit, newest_first=True):
            scenario = FAULT_SCENARIOS.get(str(record["scenario_id"]))
            answer = dict(scenario_answer(scenario)) if scenario is not None else {}
            out.append({
                "case_id": f"live-{record['id']}",
                "turbine_id": record["turbine_id"],
                "source": record["origin"],   # generator / manual（答案欄位另有情境的 origin）
                "onset_ts": record["onset_ts"],
                "first_alarm_ts": record["first_alarm_ts"],
                "first_alarm_code": record["first_alarm_code"],
                "trip_ts": record["trip_ts"],
                "trip_code": record["trip_code"],
                "trip_count": record["trip_count"],
                "observed": record["observed"],
                "cleared_ts": record["cleared_ts"],
                "cleared_by": record["cleared_by"],
                "severity_rate": record["severity_rate"],
                **answer,
            })
        return out
