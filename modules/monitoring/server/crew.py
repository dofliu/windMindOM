"""模擬維修班（WMOM-20261125-06-d，EPIC-SF 第 5 項）。

沒有人處理工單時，跳機的機組會一直停著，風場會一台一台停下來。模擬維修班在即時風場裡扮演
「一直沒有人來處理的那些工單」的處理者：

- 工單建立之後過了**反應時間**還沒有人開工 → 維修班派工、開工（機組進維修模式）。
- 開工之後過了**修復時間** → 完工（運維閉環在這一刻修掉故障、復位、啟動），然後直接結案。
- 同時最多 ``crews`` 組在施工；優先級高的先做，同級的先開的先做。
- 人已經開工的工單維修班不碰，也不算進 ``crews``。等簽核、沒有簽核鏈的工單過了反應時間沒有人簽，維修班
  結案——否則它一直算未結案，那台機組的工單會卡在每台三張的上限。有簽核鏈的（人從畫面完工的）留給簽核流程。
- 工單沒有排定日期的欄位：定檢 / 保養工單一樣是建立之後過了反應時間就開工。
- 工單上的時間（建立、完工）是實際時間；維修班的反應時間與修復時間算的是風場時鐘。

時間一律是**風場時鐘**（模擬時鐘），所以時間倍率加速時維修班跟著快。哪張工單什麼時候第一次看到、
什麼時候開工，存在風場 DB 的設定表裡，重啟之後接著算。

維修班走的是工單 repository 的狀態機，和人從畫面操作是同一條路：開工 / 完工對機組的作用由運維閉環的
掛鉤處理（``server/om_loop.py``），這裡不直接動模擬器。結案是直接呼叫 ``approve_all``，不走多階簽核。
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional
from uuid import UUID

from modules.workflow.domain import Priority, WorkOrderStatus, WorkOrderType
from modules.workflow.domain.work_order import FollowupKind, WorkOrder
from modules.workflow.repository.work_order_repository import skip_day_form_for
from simulator.time_utils import iso_utc, parse_iso

if TYPE_CHECKING:
    from server.om_loop import OmLoop

logger = logging.getLogger(__name__)

# 維修班在工單上留下的身分（固定的 UUID，畫面與稽核看得出是模擬維修班）
CREW_LEAD = UUID("00000000-0000-4000-8000-00000000c0e1")     # 派工、結案
CREW_TECH = UUID("00000000-0000-4000-8000-00000000c0e2")     # 開工、完工
_SETTING_STATE = "crew_state"
_MAX_FINISH_ATTEMPTS = 3   # 完工連續失敗幾次就放手（不再佔著一組）
skip_day_form_for(CREW_TECH)   # 模擬維修班不是真人：結案時不寫當日工作表
_PRIORITY_ORDER = {Priority.CRITICAL: 0, Priority.HIGH: 1, Priority.NORMAL: 2, Priority.LOW: 3}
_WAITING = (WorkOrderStatus.DRAFT, WorkOrderStatus.DISPATCHED, WorkOrderStatus.REOPENED)
_PLANNED = (WorkOrderType.INSPECTION, WorkOrderType.PREVENTIVE, WorkOrderType.COMMISSIONING)


@dataclass
class CrewConfig:
    """模擬維修班的設定。

    Attributes:
        enabled: 開不開。
        response_minutes: 工單建立到維修班開工，幾分鐘（風場時鐘）。這段時間內人可以自己處理。
        repair_minutes: 故障維修開工到完工，幾分鐘。
        inspection_minutes: 定檢 / 保養 / 試運轉開工到完工，幾分鐘。
        crews: 同時幾組在施工。
        close_after_finish: 完工之後是否直接結案（不留在等簽核）。
    """

    enabled: bool = False
    response_minutes: float = 120.0
    repair_minutes: float = 240.0
    inspection_minutes: float = 240.0
    crews: int = 2
    close_after_finish: bool = True

    def to_dict(self) -> Dict[str, object]:
        """可直接轉成 JSON 的 dict。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "CrewConfig":
        """由 dict 建立並檢查；不認得的欄位或不合理的數字丟 ``ValueError``。"""
        unknown = sorted(set(data) - set(cls.__dataclass_fields__))
        if unknown:
            raise ValueError(f"不認得的設定：{unknown}")
        config = cls(**dict(data))  # type: ignore[arg-type]  # 型別在下面逐欄檢查
        if not isinstance(config.enabled, bool) or not isinstance(config.close_after_finish, bool):
            raise ValueError("enabled、close_after_finish 要是 true / false")
        for name in ("response_minutes", "repair_minutes", "inspection_minutes"):
            value = getattr(config, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
                    or value < 0:
                raise ValueError(f"{name} 要是 ≥ 0 的數字")
            setattr(config, name, float(value))
        if isinstance(config.crews, bool) or not isinstance(config.crews, int) or config.crews < 1:
            raise ValueError("crews 要是 ≥ 1 的整數")
        return config


class MaintenanceCrew:
    """模擬維修班。由運維閉環在每批讀值寫進歷史之後呼叫 :meth:`step`。"""

    CHECK_INTERVAL_S = 60.0   # 風場時鐘每過這麼久看一次工單

    def __init__(self, loop: "OmLoop") -> None:
        self._loop = loop
        self.config = CrewConfig()
        self._last_check: Optional[datetime] = None
        # 工單 id →｛"seen": 第一次看到、"started": 維修班開工、"awaiting": 開始等簽核｝（風場時鐘，ISO）
        self._jobs: Dict[str, Dict[str, Optional[str]]] = {}
        self._loaded_from: Optional[object] = None
        self._restart_waiting = False

    def configure(self, config: CrewConfig) -> None:
        """換設定。由關轉開時，積壓的工單從現在起算反應時間（不會一打開就全部接手）。"""
        if config.enabled and not self.config.enabled:
            self._restart_waiting = True
        self.config = config

    def reset(self) -> None:
        """換風場或即時模擬重新啟動：忘掉記憶體裡的狀態，下次從風場 DB 讀回來。"""
        self._last_check = None
        self._jobs = {}
        self._loaded_from = None

    def _load(self) -> None:
        storage = self._loop._broker.storage
        if self._loaded_from is storage:
            return
        saved = storage.get_setting(_SETTING_STATE) or {}
        jobs = saved.get("jobs")
        self._jobs = {str(k): dict(v) for k, v in jobs.items()} if isinstance(jobs, dict) else {}
        self._loaded_from = storage

    def _save(self) -> None:
        self._loop._broker.storage.set_setting(_SETTING_STATE, {"jobs": self._jobs})

    @staticmethod
    def _minutes_since(stamp: Optional[str], now: datetime) -> float:
        return (now - parse_iso(stamp)).total_seconds() / 60.0 if stamp else 0.0

    def step(self, now: datetime) -> List[str]:
        """看一次工單，該做的做掉。

        Args:
            now: 現在的風場時鐘。

        Returns:
            這一次做了什麼（``"<工單編號>:<動作>"``），給測試與 log 用。
        """
        if not self.config.enabled or not self._loop._live():
            return []
        if self._last_check is not None and (now - self._last_check).total_seconds() < self.CHECK_INTERVAL_S:
            return []
        self._last_check = now
        farm_id = self._loop._farm_id()
        if not farm_id:
            return []
        try:
            self._load()
            repository = self._loop._repository()
            orders, _total = repository.list(farm_id=farm_id, only_open=True, limit=500)
        except Exception:  # noqa: BLE001  查不到下次再看
            logger.exception("模擬維修班：讀不到未結案的工單")
            return []
        done: List[str] = []
        changed = False
        stamp = iso_utc(now)
        known = {str(order.id) for order in orders}
        for gone in [key for key in self._jobs if key not in known]:
            del self._jobs[gone]   # 已經結案或撤掉的
            changed = True
        for order in orders:
            job = self._jobs.get(str(order.id))
            if job is None:
                job = self._jobs[str(order.id)] = {"seen": stamp, "started": None, "awaiting": None}
                changed = True
            # 什麼時候開始等簽核（人完工的工單也算）：從這時起算反應時間
            if self._restart_waiting and not job.get("started"):
                job["seen"] = stamp
                job["awaiting"] = stamp if order.status is WorkOrderStatus.AWAITING_SIGNOFF else None
                changed = True
            # 維修班開工的工單離開了施工中（人接手完工、撤單、退回之後重來）：不再算是維修班的
            if job.get("started") and order.status is not WorkOrderStatus.IN_PROGRESS:
                job["started"] = None
                job["attempts"] = 0
                changed = True
            if order.status is WorkOrderStatus.AWAITING_SIGNOFF and not job.get("awaiting"):
                job["awaiting"] = stamp
                changed = True
            elif order.status is not WorkOrderStatus.AWAITING_SIGNOFF and job.get("awaiting"):
                job["awaiting"] = None
                changed = True

        def act(order: WorkOrder, action: str, **kwargs: object) -> bool:
            try:
                repository.transition(order.id, action, **kwargs)
            except Exception:  # noqa: BLE001  這張做不了不影響別張，下次再試
                logger.exception("模擬維修班：工單 %s 的 %s 沒有成功", order.business_key, action)
                return False
            done.append(f"{order.business_key}:{action}")
            return True

        self._restart_waiting = False
        config = self.config
        # 1. 維修班自己開工的：時間到就完工、結案
        working = 0
        for order in orders:
            job = self._jobs[str(order.id)]
            if order.status is not WorkOrderStatus.IN_PROGRESS or not job.get("started"):
                continue
            needed = config.inspection_minutes if order.type in _PLANNED else config.repair_minutes
            if self._minutes_since(job["started"], now) < needed:
                working += 1
                continue
            if act(order, "finish", actor_id=CREW_TECH, actual_hours=round(needed / 60.0, 2),
                   followup_kind=FollowupKind.NONE, work_summary="模擬維修班完工"):
                changed = True
                job["started"] = None
                if config.close_after_finish:
                    act(order, "approve_all", actor_id=CREW_LEAD)
            else:
                # 完工做不了（例：狀態機擋下）：試幾次就放手，不讓這一組一直被佔著
                job["attempts"] = int(job.get("attempts") or 0) + 1
                changed = True
                if job["attempts"] >= _MAX_FINISH_ATTEMPTS:
                    job["started"] = None
                else:
                    working += 1
        # 2. 等簽核太久沒有人簽的：結案
        if config.close_after_finish:
            for order in orders:
                job = self._jobs[str(order.id)]
                # 有簽核鏈的（人從畫面完工的）留給簽核流程：直接結案會留下一條沒人簽的鏈
                if (order.status is WorkOrderStatus.AWAITING_SIGNOFF and f"{order.business_key}:finish" not in done
                        and order.signoff_chain_id is None
                        and self._minutes_since(job.get("awaiting"), now) >= config.response_minutes):
                    changed = act(order, "approve_all", actor_id=CREW_LEAD) or changed
        # 3. 還沒有人開工、等了超過反應時間的：有空的組就去開工
        waiting = [order for order in orders if order.status in _WAITING
                   and self._minutes_since(self._jobs[str(order.id)].get("seen"), now) >= config.response_minutes]
        waiting.sort(key=lambda o: (_PRIORITY_ORDER.get(o.priority, 9), o.created_at, o.business_key))
        busy_turbines = {order.turbine_id for order in orders if order.status is WorkOrderStatus.IN_PROGRESS}
        for order in waiting:
            if working >= config.crews:
                break
            if order.turbine_id in busy_turbines:
                continue   # 那台機組已經有人在施工：等那張做完
            if order.status is WorkOrderStatus.DRAFT:
                if not act(order, "dispatch", actor_id=CREW_LEAD, assignee_id=CREW_TECH):
                    continue
            if act(order, "start_work", actor_id=CREW_TECH):
                self._jobs[str(order.id)]["started"] = stamp
                busy_turbines.add(order.turbine_id)
                working += 1
            changed = True
        if changed:
            try:
                self._save()
            except Exception:  # noqa: BLE001
                logger.exception("模擬維修班：狀態存不進去")
        return done
