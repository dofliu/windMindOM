"""運維閉環（WMOM-20261125-04）：把即時模擬的風場和工單接起來。

1. **跳機開單**：即時模擬的 PLC 送出跳機（T1 / T2）或自動重啟被封鎖（A039）時，替那台機組開一張故障維修
   工單，帶警報碼。同一台機組同一個警報碼已經有未結案的工單時不重複開（工單模組既有的規則）。
2. **開工＝機組進維修模式**：工單開工時機組以正常停機進維修模式；定檢 / 預防保養的停機算計畫停機，故障維修
   的算非計畫停機。
3. **完工＝修好**：工單完工時清掉該機組的故障、操作員復位、重新啟動。第一版是「完工即修好」，不看現場做了
   什麼處置：
   - 帶警報碼的故障維修工單：修掉預期會送出這個警報碼的故障。沒有這樣的故障（誤報、外部原因）就只復位。
   - A039（自動重啟被封鎖）開的工單：修掉該機組已經跳機鎖住的故障——A039 不是獨立的故障，是某個跳機碼
     超過每小時重啟上限。
   - 沒帶警報碼的故障維修、定檢、預防保養、試運轉：修掉該機組全部的故障（檢查時發現並處理）。
   簽核退回（``reject``）視同重新開工：機組再進維修模式，等再次完工。
   **鎖著的機組一定有一張未結案的工單**：工單被撤、開單當下已達上限、或開單那一刻伺服器被強制關閉時，
   定期檢查會補開一張（``ensure_work_orders``）。
4. **運轉狀態紀錄**：每次寫入讀值時，記下每台機組這段時間處於哪一種狀態（發電中 / 可發電但沒在發電 /
   計畫停機 / 非計畫停機）、發了多少電、停機時少發了多少電。可用率由這份紀錄計算。

盲測邊界：自動開的工單只寫看得到的東西（事件碼、PLC 文字、訊號值與設定值），不寫故障情境。完工時修了哪些
故障記在 ``source="workflow"`` 的事件裡，那不是可觀測事件，不會給外部。

「復位不等於修好」的規則不變（WMOM-20260719-01）：操作員復位仍然修不好帶故障的機組，要有工單完工。
管理端的故障注入 / 清除（``/api/faults/*``）是出題用的後門，照舊。
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple
from uuid import UUID

from modules.workflow.domain import Priority, WorkOrderStatus, WorkOrderType
from modules.workflow.domain.work_order import WorkOrder
from modules.workflow.repository.work_order_repository import (
    BusinessRuleViolation,
    WorkOrderRepository,
    get_repository,
)
from simulator.physics.fault_engine import FAULT_SCENARIOS
from simulator.physics.plc_protection import PlcEvent
from simulator.time_utils import iso_utc, parse_iso

if TYPE_CHECKING:
    from server.data_broker import DataBroker

logger = logging.getLogger(__name__)

# 自動重啟被封鎖（手冊 A039）：等級是警報，但機組要有人復位才會再啟動
RESTART_BLOCKED_CODE = 39
# 這些工單類型的停機算計畫停機
PLANNED_TYPES = frozenset({WorkOrderType.INSPECTION, WorkOrderType.PREVENTIVE, WorkOrderType.COMMISSIONING})
_POWER_TAG = "WTUR_TotPwrAt"   # 併網有效功率（kW）
_STATE_TAG = "WTUR_TurSt"
_PRODUCTION_STATE = 6
# 每隔多久（風場時鐘的秒數）檢查一次「鎖著的機組有沒有未結案的工單」
ENSURE_INTERVAL_S = 600.0
_UI_TURBINE_NAME = re.compile(r"^WTG-(\d+)$")


def sim_turbine_id(turbine_id: str, known: List[str]) -> Optional[str]:
    """工單上的機組名稱 → 模擬器的機組 ID；對不上回 None。

    自動開的工單用模擬器的 ID（``WT003``）；管理端手動開的工單用畫面上的名稱（``WTG-03``）。

    Args:
        turbine_id: 工單的 ``turbine_id``。
        known: 模擬器裡的機組 ID。

    Returns:
        模擬器的機組 ID，或 None。
    """
    if turbine_id in known:
        return turbine_id
    match = _UI_TURBINE_NAME.match(turbine_id.strip())
    if match:
        candidate = f"WT{int(match.group(1)):03d}"
        if candidate in known:
            return candidate
    return None


class OmLoop:
    """一個 ``DataBroker`` 的運維閉環。``enabled`` 為 False 時所有入口都不做事。"""

    def __init__(self, broker: "DataBroker") -> None:
        """建立（預設關：伺服器依 ``WMOM_OM_LOOP`` 開，測試與一次性的 broker 不會因為跳機去寫工單）。

        Args:
            broker: 所屬的 broker。
        """
        self._broker = broker
        self.enabled = False
        # 機組 → {工單 id: 是否計畫停機}：哪些機組因為哪張工單在維修模式。記憶體裡的，啟動時由工單重建
        self._in_service: Dict[str, Dict[UUID, bool]] = {}
        # 即時模擬暫停期間（產生情境的批次）收到的工單動作：批次結束、Live 的狀態還原之後才套用
        self._pending: List[Tuple[WorkOrder, str, Optional[WorkOrderStatus]]] = []
        self._batch_paused = False
        self._last_ensure: Optional[datetime] = None
        self._lock = threading.Lock()

    # ── 取用 ───────────────────────────────────────────────────────────────

    def _live(self) -> bool:
        """即時模擬是否在跑（閉環只作用在即時模擬；產生情境與批次不算）。"""
        return self.enabled and self._broker.live_clock() is not None

    def pause(self) -> None:
        """產生情境的批次要用模擬器了：之後收到的工單動作先記著（``DataBroker.pause_live_for_batch`` 呼叫）。"""
        self._batch_paused = True

    def resume(self) -> int:
        """批次結束、即時風場的狀態已經還原：套用暫停期間收到的工單動作。

        Returns:
            套用了幾筆。
        """
        self._batch_paused = False
        with self._lock:
            pending, self._pending = self._pending, []
        for work_order, action, from_status in pending:
            self.on_work_order(work_order, action, from_status)
        return len(pending)

    def _farm_id(self) -> Optional[str]:
        return self._broker._active_farm_id

    def _repository(self) -> WorkOrderRepository:
        return get_repository(str(self._broker.storage.db_path))

    def _turbine(self, work_order: WorkOrder) -> Optional[str]:
        simulator = self._broker.simulator
        if simulator is None or work_order.farm_id != self._farm_id():
            return None
        return sim_turbine_id(work_order.turbine_id, list(simulator.turbines))

    # ── 1. 跳機開單 ────────────────────────────────────────────────────────

    def on_plc_event(self, turbine_id: str, event: PlcEvent) -> Optional[WorkOrder]:
        """即時模擬記下一筆 PLC 事件之後呼叫：跳機或自動重啟被封鎖就開一張故障維修工單。

        Args:
            turbine_id: 機組 ID。
            event: PLC 事件。

        Returns:
            新開的工單；不必開、已經有同碼的未結案工單、或開單失敗時為 None。
        """
        if not self._live():
            return None
        blocked = event.kind == "alarm_raised" and event.code == RESTART_BLOCKED_CODE
        if event.kind != "trip" and not blocked:
            return None
        farm_id = self._farm_id()
        if not farm_id:
            return None
        detail = f"{event.level} {event.code:03d} {event.text}"
        if event.value is not None and event.setpoint is not None:
            detail += f"（訊號值 {event.value}、設定值 {event.setpoint}）"
        clock = self._broker.live_clock()
        try:
            work_order = self._repository().create(
                farm_id=farm_id,
                turbine_id=turbine_id,
                type=WorkOrderType.CORRECTIVE,
                title=f"{turbine_id} {event.event_id} {event.text}"[:200],
                description=(f"PLC 事件自動開單。{detail}。"
                             f"發生時間（風場時鐘）：{iso_utc(clock) if clock else '不明'}。"),
                priority=Priority.HIGH if event.level == "T2" or blocked else Priority.NORMAL,
                source_alarm_code=str(event.code),
            )
        except BusinessRuleViolation as exc:
            # 同機組同碼已經有未結案的工單，或這台機組的未結案工單已經滿了：不重複開
            logger.debug("運維閉環：%s 的事件 %s 不開單（%s）", turbine_id, event.event_id, exc)
            return None
        except Exception:  # noqa: BLE001  開單失敗不能讓即時模擬停下來
            logger.exception("運維閉環：替 %s 的事件 %s 開單失敗", turbine_id, event.event_id)
            return None
        self._note(f"Work order opened: {work_order.business_key}", turbine_id, detail,
                   {"workOrderId": str(work_order.id), "businessKey": work_order.business_key,
                    "alarmCode": event.code, "auto": True})
        return work_order

    def _note(self, title: str, turbine_id: str, detail: Optional[str], payload: Dict[str, object]) -> None:
        """記一筆閉環自己的事件（``source="workflow"``：不是可觀測事件，不會給外部）；記不進去只記 log。"""
        try:
            self._broker.record_event(event_type="maintenance", source="workflow", title=title,
                                      turbine_id=turbine_id, detail=detail, payload=payload)
        except Exception:  # noqa: BLE001  事件記不進去不能讓即時模擬或工單的操作失敗
            logger.exception("運維閉環：事件記錄失敗（%s）", title)

    # ── 2、3. 開工進維修模式、完工修復 ─────────────────────────────────────

    def on_work_order(self, work_order: WorkOrder, action: str, from_status: Optional[WorkOrderStatus]) -> None:
        """工單建立或狀態改變之後由 workflow 的掛鉤呼叫。

        Args:
            work_order: 變更後的工單。
            action: ``create`` 或狀態機的 action 名稱。
            from_status: 變更前的狀態。
        """
        if action not in ("start_work", "finish", "cancel", "reject"):
            return
        if self.enabled and self._batch_paused:
            # 批次正在用模擬器，結束後 Live 的狀態會被還原：現在動機組會被還原蓋掉，先記著
            with self._lock:
                self._pending.append((work_order, action, from_status))
            return
        if not self._live():
            return
        turbine_id = self._turbine(work_order)
        if turbine_id is None:
            return
        if action == "start_work":
            self._start_work(turbine_id, work_order)
        elif action == "reject":
            # 簽核退回：工單回到進行中，技師要回現場——機組再進維修模式
            if work_order.status is WorkOrderStatus.IN_PROGRESS:
                self._start_work(turbine_id, work_order, resumed=True)
        elif action == "finish":
            self._finish(turbine_id, work_order)
        elif action == "cancel":
            with self._lock:
                holding = work_order.id in self._in_service.get(turbine_id, {})
            if not holding:
                return  # 還沒開工就撤單：這張工單沒有佔著機組，不動它
            self._leave_service(turbine_id, work_order, restart=True)
            self._note(f"Work cancelled: {work_order.business_key}", turbine_id, None,
                       {"workOrderId": str(work_order.id)})

    def _start_work(self, turbine_id: str, work_order: WorkOrder, resumed: bool = False) -> None:
        """這張工單開始佔著機組：機組以正常停機進維修模式。"""
        simulator = self._broker.simulator
        if simulator is None:
            return
        planned = work_order.type in PLANNED_TYPES
        with self._lock:
            self._in_service.setdefault(turbine_id, {})[work_order.id] = planned
        simulator.turbines[turbine_id].cmd_service(True)
        self._note(f"Work {'resumed' if resumed else 'started'}: {work_order.business_key}", turbine_id,
                   f"{turbine_id} 進入維修模式（{'計畫' if planned else '非計畫'}停機）",
                   {"workOrderId": str(work_order.id), "type": work_order.type.value, "planned": planned})

    def _repair_targets(self, turbine_id: str, work_order: WorkOrder) -> List[str]:
        """這張工單完工時要修掉哪些故障（情境 ID）。"""
        simulator = self._broker.simulator
        if simulator is None:
            return []
        faults = [f for f in simulator.fault_engine.active_faults if f.turbine_id == turbine_id]
        active = [f.scenario_id for f in faults]
        code = work_order.source_alarm_code
        if work_order.type is WorkOrderType.CORRECTIVE and code:
            try:
                wanted = int(code)
            except ValueError:
                return []
            if wanted == RESTART_BLOCKED_CODE:
                # A039 不是獨立的故障：修掉已經跳機鎖住機組的那些
                return [f.scenario_id for f in faults if f.tripped]
            return [sid for sid in active
                    if sid in FAULT_SCENARIOS
                    and any(int(item.get("code", -1)) == wanted for item in FAULT_SCENARIOS[sid].alarm_codes)]
        return active

    def _finish(self, turbine_id: str, work_order: WorkOrder) -> None:
        """現場完工：修掉該修的故障；機組不再被任何工單佔著時復位、啟動。"""
        simulator = self._broker.simulator
        if simulator is None:
            return
        model = simulator.turbines[turbine_id]
        with self._lock:
            holding = work_order.id in self._in_service.get(turbine_id, {})
        repaired = self._repair_targets(turbine_id, work_order)
        for scenario_id in repaired:
            simulator.fault_engine.clear(turbine_id=turbine_id, scenario_id=scenario_id)
        still_in_service = self._leave_service(turbine_id, work_order, restart=False)
        # 復位會把發電機轉速、併網狀態歸零：只對停著或鎖著的機組做。這張工單沒有佔著機組、機組又正常在發電時
        # （簽核退回後直接再完工、開工時閉環沒在跑），不能把它重置
        stopped = (holding or model.service_mode or model.maintenance_lock or model.plc.restart_inhibited
                   or model.tur_state != _PRODUCTION_STATE)
        if not still_in_service and stopped:
            # 修好後技師復位、啟動。還有別的故障鎖著（另一個警報碼的）的話，引擎下一步會再擋住重啟
            model.cmd_reset()
            model.cmd_start()
        # 修了哪些故障是標準答案：這筆事件的來源不在可觀測的白名單裡，不會給外部
        self._note(f"Work finished: {work_order.business_key}", turbine_id,
                   f"修復 {', '.join(repaired)}" if repaired else "沒有對應的故障，只做復位",
                   {"workOrderId": str(work_order.id), "type": work_order.type.value, "repaired": repaired,
                    "alarmCode": work_order.source_alarm_code})

    def _leave_service(self, turbine_id: str, work_order: WorkOrder, restart: bool) -> bool:
        """這張工單不再佔著機組。回傳機組是否還因為別的工單在維修模式。"""
        simulator = self._broker.simulator
        with self._lock:
            holders = self._in_service.get(turbine_id, {})
            holders.pop(work_order.id, None)
            remaining = bool(holders)
            if not remaining:
                self._in_service.pop(turbine_id, None)
        if not remaining and restart and simulator is not None:
            simulator.turbines[turbine_id].cmd_service(False)
            simulator.turbines[turbine_id].cmd_start()
        return remaining

    def rebuild(self) -> None:
        """由進行中的工單重建「哪些機組因為哪張工單在維修模式」（即時模擬啟動、換風場之後呼叫）。

        機組的維修模式在狀態存檔裡；沒有還原存檔（風場從頭開始）時，進行中的工單佔著的機組要重新進維修模式。
        """
        with self._lock:
            self._in_service.clear()
            self._pending.clear()
        self._batch_paused = False
        self._last_ensure = None
        simulator = self._broker.simulator
        farm_id = self._farm_id()
        if not self.enabled or simulator is None or not farm_id:
            return
        try:
            orders, _total = self._repository().list(farm_id=farm_id, status=WorkOrderStatus.IN_PROGRESS, limit=500)
        except Exception:  # noqa: BLE001  讀不到就當成沒有進行中的工單
            logger.exception("運維閉環：讀不到進行中的工單")
            return
        known = list(simulator.turbines)
        held: List[str] = []
        with self._lock:
            for order in orders:
                turbine_id = sim_turbine_id(order.turbine_id, known)
                if turbine_id is not None:
                    self._in_service.setdefault(turbine_id, {})[order.id] = order.type in PLANNED_TYPES
                    held.append(turbine_id)
        for turbine_id in sorted(set(held)):
            model = simulator.turbines[turbine_id]
            if not model.service_mode:
                model.cmd_service(True)

    def ensure_work_orders(self, clock: datetime) -> List[WorkOrder]:
        """鎖著的機組一定要有一張未結案的工單：沒有就補開。每 ``ENSURE_INTERVAL_S``（風場時鐘）最多檢查一次。

        會沒有工單的情況：工單被撤掉、跳機當下那台機組的未結案工單已經滿了、開單那一刻伺服器被強制關閉。
        PLC 的跳機事件不會再送一次，所以要定期補。

        Args:
            clock: 風場時鐘的現在。

        Returns:
            這次補開的工單。
        """
        if not self._live():
            return []
        if self._last_ensure is not None and (clock - self._last_ensure).total_seconds() < ENSURE_INTERVAL_S:
            return []
        self._last_ensure = clock
        simulator = self._broker.simulator
        farm_id = self._farm_id()
        if simulator is None or not farm_id:
            return []
        opened: List[WorkOrder] = []
        for turbine_id, model in simulator.turbines.items():
            if not (model.maintenance_lock or model.plc.restart_inhibited):
                continue
            try:
                repo = self._repository()
                known_ids = {turbine_id, f"WTG-{int(turbine_id[2:]):02d}"} if turbine_id[2:].isdigit() else {turbine_id}
                if any(repo.count_open_for_turbine(farm_id, name) for name in known_ids):
                    continue
                trips = sorted(code for code, level in model.plc.active_codes().items() if level in ("T1", "T2"))
                code = trips[0] if trips else None
                order = repo.create(
                    farm_id=farm_id, turbine_id=turbine_id, type=WorkOrderType.CORRECTIVE,
                    title=f"{turbine_id} 停機待修" + (f"（鎖存中的跳機 {code:03d}）" if code is not None else ""),
                    description=(f"機組停機中、沒有未結案的工單，系統補開。"
                                 f"檢查時間（風場時鐘）：{iso_utc(clock)}。"),
                    priority=Priority.NORMAL, source_alarm_code=str(code) if code is not None else None)
            except Exception:  # noqa: BLE001  補開失敗下次再試，不能讓即時模擬停下來
                logger.exception("運維閉環：替停機中的 %s 補開工單失敗", turbine_id)
                continue
            opened.append(order)
            self._note(f"Work order opened: {order.business_key}", turbine_id, "機組停機中、沒有未結案的工單",
                       {"workOrderId": str(order.id), "businessKey": order.business_key, "alarmCode": code,
                        "auto": True, "reason": "no_open_work_order"})
        return opened

    # ── 4. 運轉狀態紀錄 ────────────────────────────────────────────────────

    def classify(self, turbine_id: str, state: int) -> str:
        """一台機組現在算哪一種運轉狀態。

        - ``planned`` / ``unplanned``：因為工單在維修模式（依工單類型）；或沒有工單、但操作員把機組切到
          維修模式（算計畫）。
        - ``unplanned``：PLC 有鎖存的跳機、自動重啟被封鎖，或故障跳機後等待維修。
        - ``producing``：發電中。
        - ``ready``：其餘（待機、起動中、風太小或太大而停機）——機組本身可以發電。

        Args:
            turbine_id: 機組 ID。
            state: 運轉狀態碼（``WTUR_TurSt``）。

        Returns:
            ``Storage.AVAILABILITY_STATES`` 之一。
        """
        with self._lock:
            holders = dict(self._in_service.get(turbine_id, {}))
        if holders:
            return "planned" if all(holders.values()) else "unplanned"
        simulator = self._broker.simulator
        model = simulator.turbines.get(turbine_id) if simulator is not None else None
        if model is not None:
            if model.service_mode:
                return "planned"
            if model.maintenance_lock or model.plc.restart_inhibited:
                return "unplanned"
        return "producing" if state == _PRODUCTION_STATE else "ready"

    def account(self, readings: List[Dict[str, object]], seconds: float) -> None:
        """把這一批讀值代表的時間記進運轉狀態紀錄（每次把讀值寫進歷史時呼叫一次）。

        停機時少發的電以「同一時刻發電中的機組的平均功率」估計；沒有機組在發電（沒風或風太大）就算 0。

        Args:
            readings: 這一批各機組的讀值。
            seconds: 這一批代表多久（寫入的時段長度）。
        """
        if not self.enabled or seconds <= 0:
            return
        rows: List[Tuple[str, datetime, str, float]] = []
        for reading in readings:
            turbine_id = reading.get("turbine_id")
            stamp = reading.get("timestamp")
            if not turbine_id or not stamp:
                continue
            scada = reading.get("scada", {})
            try:
                moment = stamp if isinstance(stamp, datetime) else parse_iso(str(stamp))
                state = int(scada.get(_STATE_TAG, 0) or 0)
                power = max(0.0, float(scada.get(_POWER_TAG, 0.0) or 0.0))
            except (TypeError, ValueError):
                continue
            rows.append((str(turbine_id), moment, self.classify(str(turbine_id), state), power))
        producing = [power for _, _, kind, power in rows if kind == "producing"]
        potential = sum(producing) / len(producing) if producing else 0.0
        hours = seconds / 3600.0
        samples = []
        for turbine_id, moment, kind, power in rows:
            hour = moment.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
            down = kind in ("planned", "unplanned")
            samples.append((turbine_id, iso_utc(hour), kind, seconds,
                            power * hours if kind == "producing" else 0.0, potential * hours if down else 0.0))
        try:
            self._broker.storage.add_availability(samples)
        except Exception:  # noqa: BLE001  記不進去不能讓讀值的寫入失敗
            logger.exception("運維閉環：運轉狀態紀錄寫入失敗")
        if rows:
            self.ensure_work_orders(max(moment for _, moment, _, _ in rows))

    def availability(self, start: datetime, end: datetime) -> Dict[str, object]:
        """一段時間的可用率、停機時數與損失發電量（由運轉狀態紀錄計算）。

        - 時間可用率＝1 −（計畫＋非計畫停機時間）÷ 有紀錄的時間。
        - 發電量可用率＝發電量 ÷（發電量＋停機少發的電）。

        Args:
            start: 時間下限（含，tz-aware）。以小時為單位：算進小時起點落在範圍內的紀錄。
            end: 時間上限（不含）。

        Returns:
            ``{"turbines": [...每台機組], "farm": {...全場合計}}``；沒有紀錄時 ``farm`` 的可用率為 None。
        """
        totals = self._broker.storage.availability_totals(iso_utc(start), iso_utc(end))
        turbines = [self._metrics(row, str(row["turbine_id"])) for row in totals]
        farm_row: Dict[str, float] = {}
        for row in totals:
            for key, value in row.items():
                if key != "turbine_id":
                    farm_row[key] = farm_row.get(key, 0.0) + float(value or 0.0)
        return {"turbines": turbines, "farm": self._metrics(farm_row, None)}

    @staticmethod
    def _metrics(row: Dict[str, object], turbine_id: Optional[str]) -> Dict[str, object]:
        seconds = {state: float(row.get(f"{state}_s", 0.0) or 0.0)
                   for state in ("producing", "ready", "planned", "unplanned")}
        total = sum(seconds.values())
        energy = float(row.get("energy_kwh", 0.0) or 0.0)
        lost_planned = float(row.get("lost_planned_kwh", 0.0) or 0.0)
        lost_unplanned = float(row.get("lost_unplanned_kwh", 0.0) or 0.0)
        down = seconds["planned"] + seconds["unplanned"]
        possible = energy + lost_planned + lost_unplanned
        out: Dict[str, object] = {
            "recorded_hours": total / 3600.0,
            "producing_hours": seconds["producing"] / 3600.0,
            "ready_hours": seconds["ready"] / 3600.0,
            "planned_downtime_hours": seconds["planned"] / 3600.0,
            "unplanned_downtime_hours": seconds["unplanned"] / 3600.0,
            "energy_kwh": energy,
            "lost_planned_kwh": lost_planned,
            "lost_unplanned_kwh": lost_unplanned,
            "time_availability": (1.0 - down / total) if total > 0 else None,
            "energy_availability": (energy / possible) if possible > 0 else (1.0 if total > 0 else None),
        }
        if turbine_id is not None:
            out = {"turbine_id": turbine_id, **out}
        return out
