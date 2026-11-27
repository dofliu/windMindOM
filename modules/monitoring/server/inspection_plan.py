"""仿真風場的自動定檢計畫（WMOM-20261127-03，DEC-20261127-05）。

仿真風場自己運轉時沒有人建定檢排程，潛伏的故障（劣化到頂、在當下條件到不了警報門檻，DEC-20261127-01）
就一直沒有人發現。自動定檢計畫替每台機組維持一個定檢排程，依**風場時鐘**到期、開定檢工單：

- 每台機組一個排程（workflow 的 ``InspectionSchedule``，``created_by=PLAN_ACTOR``），週期 ``interval_days``
  天，第一次到期在 ``interval_days × (i + 1) ÷ 機組數`` 天後（錯開，不會整個風場同一天停機）。之後每次開單
  從開單當下再算一個週期。
- 到期時開一張定檢工單（``WorkOrderType.INSPECTION``）。工單建立時運維閉環產生例行巡檢卡；開工讓機組進維修
  模式（計畫停機）；完工修掉那台機組所有的故障（``OmLoop._repair_targets``），包括潛伏的。
- 那台機組已經有未結案的定檢 / 預防保養工單：不再開一張，這一期算那張（排程推進到下一期）。不然沒有人處理
  的定檢工單會一期一張堆起來，佔滿每台三張的上限，跳機開不了單。
- 每台機組三張未結案工單的上限擋下時不推進，下次檢查再試。

排程用 workflow 現成的資料表，所以定檢排程的畫面看得到、人也可以暫停某一台。自動計畫只在設定改變（開關、
週期、機組清單）時整理排程，人對個別排程的暫停會留著，直到下次改設定。workflow 的人工排程器（實際時間）跳過
這些排程（``automated_schedule_owner``），兩個時鐘不混在一起。

只作用在即時模擬：批次期間、還原存檔後的重跑段不跑（``OmLoop.account`` 只在寫進歷史時呼叫）。設定存在風場
DB（``farm_settings`` 的 ``inspection_plan``），預設關。工單上只寫看得到的東西（標題、週期），不寫故障。
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Tuple
from uuid import UUID

from modules.workflow.domain import Priority, WorkOrderType
from modules.workflow.domain.inspection_schedule import InspectionSchedule, Recurrence
from modules.workflow.domain.work_order import WorkOrder
from modules.workflow.repository.inspection_repository import (
    InspectionScheduleRepository,
    get_inspection_repository,
)
from modules.workflow.repository.work_order_repository import BusinessRuleViolation
from modules.workflow.services.inspection_scheduler import automated_schedule_owner

if TYPE_CHECKING:
    from server.om_loop import OmLoop

logger = logging.getLogger(__name__)

# 自動定檢計畫在排程與工單上留下的身分（模擬維修班是 ...c0e1 / c0e2）
PLAN_ACTOR = UUID("00000000-0000-4000-8000-00000000c0e3")
PLAN_TITLE = "例行巡檢（自動排程）"
automated_schedule_owner(PLAN_ACTOR)   # workflow 的人工排程器（實際時間）不跑這些排程
_PLANNED_OPEN = (WorkOrderType.INSPECTION, WorkOrderType.PREVENTIVE)
MAX_INTERVAL_DAYS = 730


def _description(interval_days: int) -> str:
    return f"仿真風場的自動定檢計畫：每 {interval_days} 天（風場時鐘）一次例行巡檢。"


@dataclass
class InspectionPlanConfig:
    """自動定檢計畫的設定。

    Attributes:
        enabled: 開不開。
        interval_days: 每台機組幾天（風場時鐘）定檢一次。
    """

    enabled: bool = False
    interval_days: int = 182

    def to_dict(self) -> Dict[str, object]:
        """可直接轉成 JSON 的 dict。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "InspectionPlanConfig":
        """由 dict 建立並檢查；不認得的欄位或不合理的值丟 ``ValueError``。"""
        unknown = sorted(set(data) - set(cls.__dataclass_fields__))
        if unknown:
            raise ValueError(f"不認得的設定：{unknown}")
        config = cls(**dict(data))  # type: ignore[arg-type]  # 型別在下面逐欄檢查
        if not isinstance(config.enabled, bool):
            raise ValueError("enabled 要是 true / false")
        days = config.interval_days
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_INTERVAL_DAYS:
            raise ValueError(f"interval_days 要是 1–{MAX_INTERVAL_DAYS} 的整數")
        return config


class InspectionPlan:
    """自動定檢計畫。由運維閉環在每批讀值寫進歷史之後呼叫 :meth:`step`。"""

    CHECK_INTERVAL_S = 900.0   # 風場時鐘每過這麼久看一次有沒有到期的排程

    def __init__(self, loop: "OmLoop") -> None:
        self._loop = loop
        self.config = InspectionPlanConfig()
        self._last_check: Optional[datetime] = None
        # 上次整理排程時的（storage、風場、開關、週期、機組）：不同就重新整理
        self._synced: Optional[Tuple[int, str, bool, int, Tuple[str, ...]]] = None

    def configure(self, config: InspectionPlanConfig) -> None:
        """換設定；下一步重新整理排程（開了就建 / 啟用、關了就暫停、週期變了就重新錯開）。"""
        self.config = config
        self._synced = None
        self._last_check = None

    def reset(self) -> None:
        """換風場或即時模擬重新啟動：下一步重新整理排程。"""
        self._synced = None
        self._last_check = None

    def _schedules(self) -> InspectionScheduleRepository:
        return get_inspection_repository(str(self._loop._broker.storage.db_path))

    def schedules(self) -> List[InspectionSchedule]:
        """這座風場自動計畫的排程（含暫停的），依下一次到期排序。"""
        farm_id = self._loop._farm_id()
        if not farm_id:
            return []
        items, _total = self._schedules().list(farm_id=farm_id, limit=1000)
        return [s for s in items if s.created_by == PLAN_ACTOR]

    def step(self, now: datetime) -> List[str]:
        """設定改了就整理排程；到期的開定檢工單。

        Args:
            now: 現在的風場時鐘。

        Returns:
            這一次做了什麼（``"<機組>:<動作>"``），給測試與 log 用。
        """
        if not self._loop._live():
            return []
        farm_id = self._loop._farm_id()
        simulator = self._loop._broker.simulator
        if not farm_id or simulator is None:
            return []
        turbines = tuple(simulator.turbines)
        config = self.config
        key = (id(self._loop._broker.storage), farm_id, config.enabled, config.interval_days, turbines)
        done: List[str] = []
        try:
            if self._synced != key:
                done += self._sync(farm_id, list(turbines), now)
                self._synced = key
            if not config.enabled:
                return done
            if self._last_check is not None and (now - self._last_check).total_seconds() < self.CHECK_INTERVAL_S:
                return done
            self._last_check = now
            done += self._spawn(farm_id, now)
        except Exception:  # noqa: BLE001  定檢排程出錯不能讓即時模擬停下來；下次再試
            logger.exception("自動定檢計畫：排程或開單失敗")
        return done

    def _stagger(self, now: datetime, index: int, count: int) -> datetime:
        """第 ``index`` 台機組（共 ``count`` 台）的第一次到期時間。"""
        return now + timedelta(days=self.config.interval_days * (index + 1) / max(1, count))

    def _sync(self, farm_id: str, turbines: List[str], now: datetime) -> List[str]:
        """讓排程符合設定：開著時每台機組一個啟用的排程、週期一致；關著時全部暫停。"""
        repository = self._schedules()
        days = self.config.interval_days
        mine = self.schedules()
        done: List[str] = []
        if not self.config.enabled:
            for schedule in mine:
                if schedule.active:
                    repository.set_active(schedule.id, False)
                    done.append(f"{schedule.turbine_id}:paused")
            return done
        by_turbine: Dict[str, InspectionSchedule] = {}
        for schedule in mine:   # 依到期排序；同一台有多個時留啟用的那個
            current = by_turbine.get(schedule.turbine_id)
            if current is None or (schedule.active and not current.active):
                by_turbine[schedule.turbine_id] = schedule
        keep = {schedule.id for schedule in by_turbine.values() if schedule.turbine_id in turbines}
        for schedule in mine:
            if schedule.active and schedule.id not in keep:
                repository.set_active(schedule.id, False)   # 機組不在了、或同一台多出來的
                done.append(f"{schedule.turbine_id}:paused")
        for index, turbine_id in enumerate(turbines):
            schedule = by_turbine.get(turbine_id)
            first_due = self._stagger(now, index, len(turbines))
            if schedule is None:
                repository.create(farm_id=farm_id, turbine_id=turbine_id, title=PLAN_TITLE,
                                  description=_description(days), recurrence=Recurrence.CUSTOM_DAYS,
                                  interval_days=days, first_due_at=first_due, created_by=PLAN_ACTOR)
                done.append(f"{turbine_id}:scheduled")
                continue
            if schedule.recurrence is not Recurrence.CUSTOM_DAYS or schedule.interval_days != days:
                # 週期變了：重新錯開（update_metadata 不動到期日）
                repository.update_metadata(schedule.id, description=_description(days),
                                           recurrence=Recurrence.CUSTOM_DAYS, interval_days=days)
                repository.reschedule(schedule.id, first_due)
                done.append(f"{turbine_id}:rescheduled")
            elif not schedule.active and schedule.next_due_at <= now:
                # 暫停期間過了到期日：重新錯開，不讓整個風場一打開就同時到期
                repository.reschedule(schedule.id, first_due)
            if not schedule.active:
                repository.set_active(schedule.id, True)
                done.append(f"{turbine_id}:resumed")
        return done

    def _spawn(self, farm_id: str, now: datetime) -> List[str]:
        """到期的排程開定檢工單；那台機組已經有未結案的定檢 / 預防保養工單就算那張。"""
        repository = self._schedules()
        due, _total = repository.list(farm_id=farm_id, active_only=True, due_only=True, as_of=now, limit=1000)
        due = [schedule for schedule in due if schedule.created_by == PLAN_ACTOR]
        if not due:
            return []
        orders = self._loop._repository()
        open_orders, _total = orders.list(farm_id=farm_id, only_open=True, limit=1000)
        planned: Dict[str, WorkOrder] = {}
        for order in open_orders:
            if order.type in _PLANNED_OPEN:
                planned.setdefault(order.turbine_id, order)
        done: List[str] = []
        for schedule in due:
            existing = planned.get(schedule.turbine_id)
            if existing is not None:
                repository.record_spawn(schedule.id, work_order_id=existing.id, spawned_at=now)
                done.append(f"{schedule.turbine_id}:covered")
                continue
            try:
                work_order = orders.create(
                    farm_id=farm_id, turbine_id=schedule.turbine_id, type=WorkOrderType.INSPECTION,
                    title=f"定檢：{schedule.title}"[:200], description=schedule.description,
                    priority=Priority.NORMAL, created_by=PLAN_ACTOR,
                )
            except BusinessRuleViolation as exc:
                # 這台機組的未結案工單滿了：不推進，下次再試
                logger.debug("自動定檢計畫：%s 這次不開單（%s）", schedule.turbine_id, exc)
                continue
            repository.record_spawn(schedule.id, work_order_id=work_order.id, spawned_at=now)
            planned[schedule.turbine_id] = work_order
            done.append(f"{schedule.turbine_id}:opened")
        return done
