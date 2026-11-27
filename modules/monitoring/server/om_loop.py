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

import asyncio
import logging
import queue
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Dict, List, NamedTuple, Optional, Set, Tuple
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
from simulator.time_utils import iso_utc, parse_iso, utc_now

if TYPE_CHECKING:
    from modules.cost.services.failure_rates import FailureObservations
    from modules.cost.services.simulation_costs import FixedCosts
    from server.crew import MaintenanceCrew
    from server.inspection_plan import InspectionPlan
    from server.data_broker import DataBroker
    from server.live_history import LiveHistory
    from server.storage import Storage

logger = logging.getLogger(__name__)
# 故障率回饋的預設起點：從有紀錄開始全部算（WMOM-20261127-07）
HISTORY_START = datetime(2000, 1, 1, tzinfo=timezone.utc)

# 自動重啟被封鎖（手冊 A039）：等級是警報，但機組要有人復位才會再啟動
RESTART_BLOCKED_CODE = 39
# 還沒完工的工單才補產生出發前準備卡：完工之後機組已經修好，補出來的卡與答案都不是出發前的樣子
_BRIEFABLE_STATUSES = frozenset({WorkOrderStatus.DRAFT, WorkOrderStatus.DISPATCHED, WorkOrderStatus.IN_PROGRESS,
                                 WorkOrderStatus.REOPENED})
# 同一張工單的卡連續做不出來幾次之後，定期檢查就不再替它排（管理端仍可用 POST 手動補）
_MAX_BRIEFING_ATTEMPTS = 3


class _BriefingJob(NamedTuple):
    """一張待做的出發前準備卡。排進去當下就把要用的東西都記下來：做的時候風場可能已經換了。"""

    turbine_id: str
    work_order: WorkOrder
    cutoff: datetime                 # 資料截止點（風場時鐘）
    answer: Dict[str, object]        # 評分用的答案（當下這台機組實際的故障）
    late: bool                       # 是否事後補產生
    farm_id: str
    storage: "Storage"
    history: "LiveHistory"
    turbines: Tuple[str, ...]


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
        # 出發前準備卡的背景工作：不能停下來等的執行緒（即時模擬、事件迴圈）開單時，卡片排到這裡做
        self._briefing_jobs: "queue.Queue[_BriefingJob]" = queue.Queue()
        self._briefing_worker: Optional[threading.Thread] = None
        self._briefing_lock = threading.Lock()
        self._briefing_queued: Set[str] = set()         # 已經排進去、還沒做完的工單 id
        self._briefing_failures: Dict[str, int] = {}    # 工單 id → 做不出來的次數
        # 等下一批讀值寫進歷史才做的卡：工單 id →（機組, 工單, 建單當下的答案）
        self._briefing_awaiting: Dict[str, Tuple[str, WorkOrder, Dict[str, object]]] = {}
        self._crew: Optional["MaintenanceCrew"] = None
        self._inspection_plan: Optional["InspectionPlan"] = None

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
        self.ensure_briefings()   # 批次期間建立的工單當下沒有風場時鐘、沒有卡：現在補
        return len(pending)

    @property
    def crew(self) -> "MaintenanceCrew":
        """模擬維修班（``server/crew.py``，WMOM-20261125-06-d）；預設關。"""
        if self._crew is None:
            from server.crew import MaintenanceCrew
            self._crew = MaintenanceCrew(self)
        return self._crew

    @property
    def inspection_plan(self) -> "InspectionPlan":
        """自動定檢計畫（``server/inspection_plan.py``，WMOM-20261127-03）；預設關。"""
        if self._inspection_plan is None:
            from server.inspection_plan import InspectionPlan
            self._inspection_plan = InspectionPlan(self)
        return self._inspection_plan

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
        if self._has_open_corrective(farm_id, turbine_id):
            # 這台機組已經有未結案的故障維修工單：不為同一次停機再開一張。
            # - A039 是「同一個跳機碼一小時內跳太多次」：那個跳機碼的工單還開著
            # - 同一個故障常同時送出兩個跳機碼（例：冷卻水流量 439 ＋ 變頻器跳機要求 021），各開一張的話，
            #   一張完工修好故障之後，另一張還會把機組再停下來修一次（WMOM-20261126-01）
            # 開著的那張修不到的故障，完工後機組仍鎖著：PLC 會再跳（那時已沒有未結案工單，照常開單），
            # 或由 ensure_work_orders 補開
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
        if action == "create":
            # 出發前準備卡（WMOM-20261125-05）：故障維修工單建立當下，把看得到的證據整理成一張卡；
            # 定檢 / 預防保養工單是例行巡檢卡（WMOM-20261126-05）
            from server.briefing import card_kind_for

            if card_kind_for(work_order) is not None and self._live():
                turbine_id = self._turbine(work_order)
                if turbine_id is not None:
                    self._brief_on_create(turbine_id, work_order)
            return
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

    def _has_open_corrective(self, farm_id: str, turbine_id: str) -> bool:
        """這台機組有沒有未結案的故障維修工單。查不到當成沒有（寧可多開一張）。"""
        try:
            for name in self.turbine_names(turbine_id):
                orders, _total = self._repository().list(farm_id=farm_id, turbine_id=name, only_open=True, limit=10)
                if any(order.type is WorkOrderType.CORRECTIVE for order in orders):
                    return True
        except Exception:  # noqa: BLE001
            logger.exception("運維閉環：查不到 %s 的未結案工單", turbine_id)
        return False

    def turbine_names(self, turbine_id: str) -> List[str]:
        """一台機組在工單上可能用的名稱：模擬器的 ID 與畫面上的名稱。"""
        names = [turbine_id]
        if turbine_id.startswith("WT") and turbine_id[2:].isdigit():
            names.append(f"WTG-{int(turbine_id[2:]):02d}")
        return names

    def _on_live_thread(self) -> bool:
        """現在是不是在即時模擬的執行緒上。"""
        simulator = self._broker.simulator
        return simulator is not None and getattr(simulator, "_thread", None) is threading.current_thread()

    def _must_not_block(self) -> bool:
        """現在這條執行緒是不是不能停下來做卡：即時模擬的執行緒、asyncio 事件迴圈的執行緒。

        一張卡要讀同場每台機組幾小時的讀值。在即時模擬的執行緒上做，整場一起跳機時模擬會停好幾秒；在事件
        迴圈上做（``async def`` 的建單路由直接呼叫 repository），整個伺服器的請求都要等它。
        """
        if self._on_live_thread():
            return True
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return False
        return True

    def _brief_on_create(self, turbine_id: str, work_order: WorkOrder) -> None:
        """工單剛建立：歷史裡的讀值已經涵蓋到現在就馬上做卡，否則等下一批讀值寫進去再做。

        讀值每 10 秒才存一筆，跳機卻可能發生在兩筆之間。馬上做的話，卡上最後一筆讀值是跳機之前的——
        量測回路斷線這種幾秒內就跳機的故障，異常的讀值根本還沒進歷史，卡上每個訊號都是「相近」
        （2026-11-26 情境測試）。所以資料截止點取「建單之後第一批寫進歷史的讀值」的時間，最多晚一個
        取樣週期；評分用的答案仍在建單當下取。
        """
        from server import briefing

        broker = self._broker
        clock = broker.live_clock()
        simulator = broker.simulator
        if clock is None or simulator is None:
            return
        stored = {tid: stamp for tid, stamp, _values in broker.latest_stored_readings()}.get(turbine_id)
        if stored is not None and parse_iso(stored) >= clock:
            self.make_briefing(turbine_id, work_order)
            return
        with self._briefing_lock:
            self._briefing_awaiting[str(work_order.id)] = (
                turbine_id, work_order, briefing.capture_answer(simulator, turbine_id))

    def _flush_awaiting(self, moment: datetime) -> None:
        """一批讀值剛寫進歷史：把等著的卡做掉，資料截止點＝這批讀值的時間。"""
        with self._briefing_lock:
            waiting, self._briefing_awaiting = self._briefing_awaiting, {}
        for turbine_id, work_order, answer in waiting.values():
            self.make_briefing(turbine_id, work_order, cutoff=moment, answer=answer)

    def make_briefing(self, turbine_id: str, work_order: WorkOrder, late: bool = False,
                      wait: Optional[bool] = None, cutoff: Optional[datetime] = None,
                      answer: Optional[Dict[str, object]] = None) -> Optional[Dict[str, object]]:
        """替一張工單產生出發前準備卡並存起來（故障維修：故障出勤卡；定檢 / 預防保養：例行巡檢卡）。已經有卡的
        工單不會被換掉。

        資料截止點（風場時鐘）與評分用的答案（這台機組當下實際的故障）在呼叫當下取；卡片只含可觀測資料，
        答案另外存、不在卡片裡。

        Args:
            turbine_id: 模擬器的機組 ID。
            work_order: 工單。
            late: 不是在工單建立當下產生的（之後補產生）。
            wait: True＝現在做完並回傳卡片；False＝排到背景執行緒；None＝看這條執行緒能不能停下來等
                （:meth:`_must_not_block`）。
            cutoff: 資料截止點；None＝現在的風場時鐘。
            answer: 評分用的答案；None＝現在取。

        Returns:
            卡片；排到背景、即時模擬沒在跑或產生失敗時為 None（不影響工單）。
        """
        from server import briefing

        broker = self._broker
        simulator = broker.simulator
        clock = cutoff or broker.live_clock()
        farm_id = self._farm_id()
        if simulator is None or clock is None or not farm_id or work_order.farm_id != farm_id:
            return None
        job = _BriefingJob(
            turbine_id=turbine_id, work_order=work_order, cutoff=clock,
            answer=answer if answer is not None else briefing.capture_answer(simulator, turbine_id),
            late=late, farm_id=farm_id,
            storage=broker.storage, history=broker.live_history, turbines=tuple(simulator.turbines))
        if wait is None:
            wait = not self._must_not_block()
        if wait:
            return self._build_briefing(job)
        key = str(work_order.id)
        with self._briefing_lock:
            if key in self._briefing_queued:
                return None   # 已經在排了：定期檢查不要把同一張工單一排再排
            self._briefing_queued.add(key)
            self._briefing_jobs.put(job)
            if self._briefing_worker is None or not self._briefing_worker.is_alive():
                self._briefing_worker = threading.Thread(target=self._briefing_loop, daemon=True,
                                                         name="briefing-cards")
                self._briefing_worker.start()
        return None

    def _briefing_loop(self) -> None:
        """背景執行緒：把排著的卡做完就結束（下次有工作再起一條），不留著佔連線。"""
        while True:
            with self._briefing_lock:
                try:
                    job = self._briefing_jobs.get_nowait()
                except queue.Empty:
                    self._briefing_worker = None
                    return
            try:
                self._build_briefing(job)
            finally:
                with self._briefing_lock:
                    self._briefing_queued.discard(str(job.work_order.id))
                self._briefing_jobs.task_done()

    def wait_briefings(self) -> None:
        """等背景的卡片都做完（測試用）。"""
        self._briefing_jobs.join()

    def _build_briefing(self, job: _BriefingJob) -> Optional[Dict[str, object]]:
        """做一張卡並存起來；失敗只記 log。讀寫都用排進去當下記下的那座風場。"""
        from server import briefing

        work_order = job.work_order
        if self._broker.storage is not job.storage or self._farm_id() != job.farm_id:
            # 排著的時候風場換了：不做。換回這座風場之後，定期檢查會補一張（標 generated_late）
            logger.info("運維閉環：風場已經換了，不做工單 %s 的出發前準備卡", work_order.business_key)
            return None
        try:
            past = briefing.past_orders(
                get_repository(str(job.storage.db_path)), job.farm_id, self.turbine_names(job.turbine_id),
                work_order, before=None if job.late else work_order.created_at)
            common = dict(storage=job.storage, history=job.history, work_order=work_order,
                          turbine_id=job.turbine_id, turbines=list(job.turbines), cutoff=job.cutoff,
                          past_work_orders=past, generated_late=job.late)
            if briefing.card_kind_for(work_order) == briefing.KIND_ROUTINE_INSPECTION:
                # 未結案的工單當證據：不受「以前的工單」最多 10 張的限制
                repository = get_repository(str(job.storage.db_path))
                still_open = [o for name in self.turbine_names(job.turbine_id)
                              for o in repository.list(farm_id=job.farm_id, turbine_id=name, only_open=True,
                                                       limit=50)[0]]
                card = briefing.build_inspection_card(**common, open_work_orders=still_open)  # type: ignore[arg-type]
            else:
                card = briefing.build_fault_card(**common)  # type: ignore[arg-type]
            job.storage.save_briefing(str(work_order.id), work_order.business_key, job.turbine_id,
                                      str(card["kind"]), iso_utc(job.cutoff), card, job.answer)
        except Exception:  # noqa: BLE001  卡片做不出來不能影響工單或即時模擬
            logger.exception("運維閉環：工單 %s 的出發前準備卡產生失敗", work_order.business_key)
            with self._briefing_lock:
                key = str(work_order.id)
                self._briefing_failures[key] = self._briefing_failures.get(key, 0) + 1
            return None
        return card

    def backfill_briefing(self, work_order_id: UUID) -> Tuple[str, Optional[Dict[str, object]]]:
        """替一張還沒完工、也還沒有卡的工單補一張卡（管理端手動補；現在做完才回來）。

        Args:
            work_order_id: 工單 id。

        Returns:
            （結果, 卡片）。結果：``ok``、``not_found``（沒有這張工單）、``not_corrective``（不是對得到機組的
            故障維修 / 定檢 / 預防保養工單）、``finished``（已經完工：補出來的不是出發前的樣子）、``not_live``（即時模擬沒在跑）、
            ``failed``（卡片做不出來，看伺服器的 log）。
        """
        from server.briefing import card_kind_for

        order = self._repository().get(work_order_id)
        if order is None:
            return "not_found", None
        turbine_id = self._turbine(order)
        if card_kind_for(order) is None or turbine_id is None:
            return "not_corrective", None
        if order.status not in _BRIEFABLE_STATUSES:
            return "finished", None
        if not self._live():
            return "not_live", None
        card = self.make_briefing(turbine_id, order, late=True, wait=True)
        return ("ok", card) if card is not None else ("failed", None)

    def ensure_briefings(self) -> int:
        """還沒完工、有卡種的工單（故障維修、定檢、預防保養）都要有準備卡：沒有的排到背景補（標 ``generated_late``）。

        會沒有卡的情況：工單在產生情境的批次期間建立（那時即時模擬暫停，沒有風場時鐘）、建立當下卡片做
        失敗、排著的時候風場換了。已經完工的不補：機組修好之後補出來的不是出發前的樣子。已經在排的不重複
        排；連續做不出來 ``_MAX_BRIEFING_ATTEMPTS`` 次的不再排。

        未結案的工單每台機組最多三張（工單模組的規則），這裡一次取 500 張足夠。

        Returns:
            這次排了幾張。
        """
        simulator = self._broker.simulator
        farm_id = self._farm_id()
        if not self._live() or simulator is None or not farm_id:
            return 0
        try:
            orders, _total = self._repository().list(farm_id=farm_id, only_open=True, limit=500)
            from server.briefing import card_kind_for

            wanted = [o for o in orders if card_kind_for(o) is not None and o.status in _BRIEFABLE_STATUSES]
            have = self._broker.storage.briefing_work_order_ids([str(o.id) for o in wanted])
        except Exception:  # noqa: BLE001  查不到下次再試
            logger.exception("運維閉環：查不到哪些工單缺出發前準備卡")
            return 0
        with self._briefing_lock:
            skip = set(self._briefing_queued) | set(self._briefing_awaiting) | {key for key, count in self._briefing_failures.items()
                                                 if count >= _MAX_BRIEFING_ATTEMPTS}
        made = 0
        known = list(simulator.turbines)
        for order in wanted:
            turbine_id = sim_turbine_id(order.turbine_id, known)
            if str(order.id) in have or str(order.id) in skip or turbine_id is None:
                continue
            self.make_briefing(turbine_id, order, late=True, wait=False)
            made += 1
        return made

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
            # 故障紀錄要知道是哪張工單修的（不對外）
            simulator.fault_engine.clear(turbine_id=turbine_id, scenario_id=scenario_id)
            self._broker.fault_records.on_fault_cleared(turbine_id, scenario_id, work_order.business_key)
        # 換了零件：那個零件的耗損從現在起算，故障產生器的發生率跟著降（WMOM-20261127-07）
        clock = self._broker.live_clock()
        simulator.fault_generator.record_replacement(turbine_id, repaired, model,
                                                     at=iso_utc(clock) if clock is not None else None)
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
        self._post_costs(work_order, repaired)

    def _post_costs(self, work_order: WorkOrder, repaired: List[str]) -> None:
        """工單完工的支出寫進成本帳本（人工、料件；WMOM-20260504-11）。每張工單只寫一次，時間用風場時鐘。

        帳本只給管理端；備註只寫工單編號、工時與修復等級，不寫故障情境。出錯只記 log，不影響完工。
        只在即時模擬裡完工的工單入帳（閉環沒跑時完工的不補）；簽核退回後再完工不重寫（DEC-20261127-02）。
        """
        farm_id = self._farm_id()
        if not farm_id:
            return
        try:
            from modules.cost.repository.cost_ledger import CostLedgerCategory, CostLedgerSourceType
            from modules.cost.repository.cost_ledger_repository import get_cost_ledger_repository
            from modules.cost.services.simulation_costs import farm_rates, repair_class, work_order_cost_entries
            from modules.workflow.repository.material_request_repository import get_material_request_repository

            moment = self._broker.live_clock()
            if moment is None:
                logger.warning("運維閉環：工單 %s 完工時沒有風場時鐘，支出不入帳", work_order.business_key)
                return
            db_path = str(self._broker.storage.db_path)
            classes = [repair_class(sid, FAULT_SCENARIOS[sid].category if sid in FAULT_SCENARIOS else None)
                       for sid in repaired]
            ledger = get_cost_ledger_repository(db_path)
            # 料件已經由領料出庫入帳的才不另算（草稿、退回、取消的領料單沒有入帳）
            has_requests = any(
                entry.category is CostLedgerCategory.MATERIAL
                for request in get_material_request_repository(db_path).list_for_work_order(work_order.id)
                for entry in ledger.list_for_subject(request.id, CostLedgerSourceType.MATERIAL_REQUEST))
            entries = work_order_cost_entries(
                farm_id=farm_id, work_order_id=work_order.id, business_key=work_order.business_key or "",
                actual_hours=work_order.actual_hours, crew_size=work_order.crew_size, repaired=classes,
                has_material_requests=has_requests, rates=farm_rates(farm_id, self._broker.farm_registry),
                moment=moment)
            ledger.add_once_for_subject(work_order.id, CostLedgerSourceType.WORK_ORDER, entries)
        except Exception:  # noqa: BLE001  帳本寫不進去不能讓完工失敗
            logger.exception("運維閉環：工單 %s 的支出寫不進成本帳本", work_order.business_key)

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
        with self._briefing_lock:
            self._briefing_failures.clear()
            self._briefing_awaiting.clear()
        if self._crew is not None:
            self._crew.reset()
        if self._inspection_plan is not None:
            self._inspection_plan.reset()
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
        self.ensure_briefings()
        opened: List[WorkOrder] = []
        for turbine_id, model in simulator.turbines.items():
            if not (model.maintenance_lock or model.plc.restart_inhibited):
                continue
            try:
                repo = self._repository()
                if any(repo.count_open_for_turbine(farm_id, name) for name in self.turbine_names(turbine_id)):
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
            # 帶著故障重啟、還沒再跳的那幾分鐘機組在發電：照實算發電（WMOM-20261125-06-a）
            if model.plc.restart_inhibited or (model.maintenance_lock and state != _PRODUCTION_STATE):
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
            latest = max(moment for _, moment, _, _ in rows)
            self._flush_awaiting(latest)   # 等這批讀值的準備卡現在可以做了
            self.ensure_work_orders(latest)
            if self._inspection_plan is not None:
                self._inspection_plan.step(latest)   # 自動定檢計畫：到期開定檢工單（先開單，維修班同一步就看得到）
            if self._crew is not None:
                self._crew.step(latest)    # 模擬維修班（沒開就什麼都不做）

    def fixed_costs(self, farm_id: str, availability: Dict[str, object]) -> "FixedCosts":
        """這座風場的固定成本（WMOM-20261127-02）：收支端點與月報共用，兩邊不會對不上。

        機組數依序看風場登錄的、即時模擬的、有運轉紀錄的——先看登錄的，即時模擬有沒有在跑都得到同一個答案
        （code review）。

        Args:
            farm_id: 風場 ID。
            availability: ``availability`` 的結果（登錄與即時模擬都沒有時才用它的機組數）。

        Returns:
            固定成本。
        """
        from modules.cost.services.simulation_costs import fixed_costs

        registry = self._broker.farm_registry
        farm = registry.get_farm(farm_id)
        simulator = self._broker.simulator
        if farm is not None and farm.turbine_count:
            turbines = int(farm.turbine_count)
        elif simulator is not None:
            turbines = len(simulator.turbines)
        else:
            turbines = len(availability.get("turbines") or [])  # type: ignore[arg-type]
        return fixed_costs(farm_id, turbines, registry)

    def failure_observations(self, start: datetime, end: datetime) -> "FailureObservations":
        """一段時間裡本風場的維修紀錄（故障率回饋，WMOM-20261127-07）：由工單修好的故障與運轉機組年。

        修了哪些故障來自不對外的故障紀錄，只給主管的成本試算。

        Args:
            start: 時間下限（含，tz-aware）。
            end: 時間上限（不含）。

        Returns:
            維修紀錄。
        """
        from modules.cost.services.failure_rates import HOURS_PER_YEAR, FailureObservations

        storage = self._broker.storage
        repairs = storage.repaired_fault_counts(iso_utc(start), iso_utc(end), origin="generator")
        # 手動注入的故障是題目或展示：不算進故障率，只回報幾筆
        manual = sum(storage.repaired_fault_counts(iso_utc(start), iso_utc(end), origin="manual").values())
        farm = self.availability(start, end)["farm"]
        hours = float(farm.get("recorded_hours", 0.0) or 0.0)  # type: ignore[union-attr]
        return FailureObservations(repairs=repairs, turbine_years=hours / HOURS_PER_YEAR,
                                   start=iso_utc(start), end=iso_utc(end), excluded_manual=manual,
                                   farm_registry=self._broker.farm_registry)

    def history_window(self) -> Tuple[datetime, datetime]:
        """從有紀錄開始到資料時鐘的下一個整點（故障率回饋的預設時間窗）。

        資料時鐘：即時模擬在跑時是模擬時鐘，否則是最近寫入的 Live 讀值時間（同保留期），不看實際時間——
        時間倍率大於 1 之後兩者對不上，修好的時間記的是風場時鐘。
        """
        clock = self._broker._retention_clock(self._broker.storage) or utc_now()
        end = (clock + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        return HISTORY_START, end

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
