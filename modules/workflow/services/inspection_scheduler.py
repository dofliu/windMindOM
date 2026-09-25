"""定檢排程 scheduler service（WMOM-20260505-22 / DN-01 §3.3）。

把「到期 ``InspectionSchedule`` → spawn ``WorkOrder(type=INSPECTION)``」的組合邏輯
從 repository CRUD 抽出來，因為它同時碰兩個 repository（``InspectionScheduleRepository``
+ ``WorkOrderRepository``），不屬於任一方單獨的職責。

呼叫時機（本次範圍）：由 ``inspection_router.py`` 的
``POST /api/workflow/inspection-schedules/run-scheduler`` 觸發（人工 / 外部 cron 呼叫）。
repo 目前沒有背景排程框架（無 APScheduler，見 CLAUDE.md 現況），故不在本次新增
背景 thread / asyncio loop——避免重蹈 WMOM-20260720-04/-08 那類「多一條背景執行緒
就多一類生命週期硬化債」的覆轍，且 reporting/cost 模組既有的週期性彙總也都是
on-demand 觸發模式，此設計與既有慣例一致。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from modules.workflow.domain import Priority, WorkOrderType
from modules.workflow.domain.inspection_schedule import (
    _utc_now,
    recurrence_interval_days,
)
from modules.workflow.repository.inspection_repository import (
    InspectionScheduleRepository,
)
from modules.workflow.repository.work_order_repository import (
    BusinessRuleViolation,
    WorkOrderRepository,
)

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpawnedInspection:
    """一筆成功 spawn 的結果（給 router response 用）。"""

    schedule_id: UUID
    work_order_id: UUID
    turbine_id: str
    next_due_at: datetime


def run_inspection_scheduler(
    inspection_repo: InspectionScheduleRepository,
    work_order_repo: WorkOrderRepository,
    farm_id: str,
    *,
    as_of: datetime | None = None,
) -> list[SpawnedInspection]:
    """找出 ``farm_id`` 內已到期的排程 → spawn 工單 → 推進 ``next_due_at``。

    冪等設計：每筆排程 spawn 成功後 ``next_due_at`` 立刻推進到下一週期
    （``InspectionScheduleRepository.record_spawn``），同一到期週期內重複呼叫本函式
    不會對同一筆排程重複 spawn。若某筆排程因 multi-WO constraint 撞到
    ``BusinessRuleViolation``（該風機 OPEN 工單已滿 3 張，或同 alarm_code 已有
    OPEN 工單——定檢工單目前不帶 source_alarm_code，故只可能是前者），會記
    warning 並跳過，``next_due_at`` **維持不變**，下次呼叫會重試同一筆，不會
    悄悄漏掉這次定檢。

    Args:
        inspection_repo: 定檢排程 repository（同一 farm DB）。
        work_order_repo: 工單 repository（同一 farm DB，caller 負責確保同 farm）。
        farm_id: 要跑排程的風場。
        as_of: 判斷到期的基準時間；未帶預設現在（UTC）。

    Returns:
        本次成功 spawn 的清單（依排程 ``next_due_at`` 升冪，與 list 查詢順序一致）。
    """
    as_of = as_of or _utc_now()
    due_schedules, _total = inspection_repo.list(
        farm_id=farm_id, active_only=True, due_only=True, as_of=as_of, limit=1000
    )

    spawned: list[SpawnedInspection] = []
    for sched in due_schedules:
        # Review must-fix 防禦第三層：在建工單之前先驗證排程本身的
        # recurrence/interval_days 組合合法——正常路徑下 create()/update_metadata()
        # 已經擋過這個 invariant（見 repository docstring），這裡是最後一道防線，
        # 避免任何未來繞過 repository 寫入的路徑（如直接改 DB）造成「先建了真實
        # 工單、才在 record_spawn 炸開」的半套狀態（工單建好但 next_due_at 沒推進，
        # 導致每次呼叫都重複 spawn）。無效組合直接跳過，不建工單、不推進，等
        # 排程被修正後自然會重試。
        try:
            recurrence_interval_days(sched.recurrence, sched.interval_days)
        except ValueError as e:
            _logger.warning(
                "inspection scheduler: skip schedule %s (turbine %s) — invalid "
                "recurrence config: %s",
                sched.id, sched.turbine_id, e,
            )
            continue

        try:
            wo = work_order_repo.create(
                farm_id=sched.farm_id,
                turbine_id=sched.turbine_id,
                type=WorkOrderType.INSPECTION,
                title=f"定檢：{sched.title}",
                description=sched.description,
                priority=Priority.NORMAL,
            )
        except BusinessRuleViolation as e:
            _logger.warning(
                "inspection scheduler: skip schedule %s (turbine %s): %s",
                sched.id, sched.turbine_id, e,
            )
            continue

        updated = inspection_repo.record_spawn(
            sched.id, work_order_id=wo.id, spawned_at=as_of
        )
        spawned.append(
            SpawnedInspection(
                schedule_id=updated.id,
                work_order_id=wo.id,
                turbine_id=updated.turbine_id,
                next_due_at=updated.next_due_at,
            )
        )
    return spawned
