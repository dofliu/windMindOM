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

即時模擬的風場事件（電網擾動、風向快速變化，WMOM-20261126-07）也記在這裡：每台機組一筆、情境欄位是事件種類、
``origin="farm_event"``，答案是 nuisance。事件期間到結束後 ``RECORD_GRACE_S`` 內的事件碼算這個事件的，之後紀錄
結束（``cleared_by="farm_event_end"``，不是工單修好的，不算進故障率）。開與關依產生器現在的狀態對帳
（:meth:`reconcile_farm_events`），不靠「這一步開始 / 結束」的通知——重啟、去重的那幾步或程式更新之後，
沒關掉的紀錄照樣會被關掉。

時間一律是風場時鐘。任何一步出錯都只記 log，不影響模擬。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Set

from simulator.farm_events import FARM_EVENT_KINDS
from simulator.ground_truth import farm_event_answer, scenario_answer
from simulator.physics.fault_engine import FAULT_SCENARIOS
from simulator.physics.plc_protection import PlcEvent
from simulator.time_utils import iso_utc, parse_iso

if TYPE_CHECKING:
    from server.data_broker import DataBroker
    from simulator.farm_event_generator import LiveFarmEvent

logger = logging.getLogger(__name__)

ORIGIN_GENERATOR = "generator"   # 機率式故障產生器
ORIGIN_MANUAL = "manual"         # 管理端手動注入
ORIGIN_FARM_EVENT = "farm_event"  # 即時模擬的風場事件（nuisance，WMOM-20261126-07）
CLEARED_BY_FARM_EVENT_END = "farm_event_end"
_COUNTED_KINDS = frozenset({"alarm_raised", "trip"})


def _expected_codes(scenario_id: str) -> Optional[Set[int]]:
    """這筆紀錄的預期碼：故障情境的 ``alarm_codes``，或風場事件的 ``event_codes``；都不是時 None。"""
    scenario = FAULT_SCENARIOS.get(scenario_id)
    if scenario is not None:
        return {int(a["code"]) for a in scenario.alarm_codes}
    kind = FARM_EVENT_KINDS.get(scenario_id)
    return set(kind.event_codes) if kind is not None else None


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
                expected = _expected_codes(str(record["scenario_id"]))
                if expected is None:
                    continue
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

    def reconcile_farm_events(self, recording: Sequence["LiveFarmEvent"], expired: Sequence["LiveFarmEvent"],
                              turbines: Sequence[str], now: datetime) -> None:
        """風場事件的紀錄和產生器現在的狀態對帳（WMOM-20261126-07）。

        - 還在記錄期間的事件：每台機組要有一筆開著的紀錄、發生時間是事件開始的時刻（已經有就不重開）。
        - 開著、但對不到記錄期間的事件的紀錄（事件的記錄期間過了；或程式更新、重啟之後產生器裡已經沒有它）：
          結束。結束時間是事件結束的時刻；不知道是哪個事件的用現在。

        Args:
            recording: 產生器裡還在記錄期間的事件（一種事件最多一個）。
            expired: 這一步記錄期間剛結束的事件（取結束時間用）。
            turbines: 全場機組。
            now: 風場時鐘。
        """
        try:
            storage = self._broker.storage
            live = {event.kind: event for event in recording}
            ended = {event.kind: event for event in expired}
            for record in storage.open_fault_records():
                if record["origin"] != ORIGIN_FARM_EVENT:
                    continue
                kind = str(record["scenario_id"])
                event = live.get(kind)
                if event is not None and parse_iso(str(record["onset_ts"])) == event.start:
                    continue
                gone = ended.get(kind)
                cleared = iso_utc(gone.end if gone is not None else now)
                storage.update_fault_record(int(record["id"]), cleared_ts=cleared,
                                            cleared_by=CLEARED_BY_FARM_EVENT_END)
            for event in live.values():
                onset = iso_utc(event.start)
                for turbine_id in turbines:
                    storage.open_fault_record(turbine_id, event.kind, ORIGIN_FARM_EVENT, onset)
        except Exception:  # noqa: BLE001
            logger.exception("故障紀錄：風場事件對帳失敗")

    def cases(self, turbine_id: Optional[str] = None, open_only: bool = False,
              limit: int = 500, source: Optional[str] = None) -> List[Dict[str, object]]:
        """故障紀錄加上答案欄位（根因、元件、處置、重點訊號），新的在前。

        Args:
            turbine_id: 只取這台機組；None＝全部。
            open_only: 只取還沒修好的。
            limit: 最多幾筆。
            source: 只取這個來源（``generator`` / ``manual`` / ``farm_event``）；None＝全部。風場事件每次每台
                機組一筆，看故障時可以用它濾掉。
        """
        out: List[Dict[str, object]] = []
        for record in self._broker.storage.fault_records(turbine_id=turbine_id, open_only=open_only,
                                                         limit=limit, newest_first=True, origin=source):
            scenario_id = str(record["scenario_id"])
            scenario = FAULT_SCENARIOS.get(scenario_id)
            if scenario is not None:
                answer = dict(scenario_answer(scenario))
            elif scenario_id in FARM_EVENT_KINDS:
                # 風場事件：nuisance，預期碼是這台機組實際出現的事件碼
                seen = [int(o["code"]) for o in record["observed"] if o.get("expected")]
                answer = dict(farm_event_answer(scenario_id, list(dict.fromkeys(seen))))
            else:
                answer = {}
            out.append({
                "case_id": f"live-{record['id']}",
                "turbine_id": record["turbine_id"],
                "source": record["origin"],   # generator / manual / farm_event（答案欄位另有情境的 origin）
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
