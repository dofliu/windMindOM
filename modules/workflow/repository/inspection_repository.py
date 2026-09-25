"""InspectionScheduleRepository — CRUD + due-item query + spawn 紀錄（WMOM-20260505-22）。

責任：
1. ORM ↔ dataclass round-trip（``_to_domain``）
2. CRUD：create / get / list / update_metadata / set_active
3. ``record_spawn``：scheduler spawn 工單後回寫 ``last_spawned_*`` + 推進 ``next_due_at``

與 ``WorkOrderRepository`` 共用 engine cache（``_get_engine`` / ``_ENGINE_LOCK`` /
``_SCHEMA_INITIALIZED``），避免同一 farm DB 開兩條 connection pool（沿襲
``InventoryRepository`` 的做法）。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import sessionmaker

from modules.workflow.domain.inspection_schedule import (
    InspectionSchedule,
    Recurrence,
    _utc_now,
    compute_next_due,
    recurrence_interval_days,
)

from ._helpers import assert_utc, ensure_utc, str_to_uuid, uuid_to_str
from .inspection_orm import InspectionScheduleORM
from .orm_models import Base
from .work_order_repository import _ENGINE_LOCK, _SCHEMA_INITIALIZED, _get_engine


def get_inspection_repository(db_path: str) -> "InspectionScheduleRepository":
    """Factory — 共用 work_order_repository 的 engine cache。"""
    engine = _get_engine(db_path)
    abs_path = str(Path(db_path).resolve())
    with _ENGINE_LOCK:
        if abs_path not in _SCHEMA_INITIALIZED:
            Base.metadata.create_all(engine)
            _SCHEMA_INITIALIZED.add(abs_path)
    return InspectionScheduleRepository(engine)


class InspectionScheduleRepository:
    """SQLAlchemy 2.0 repository for ``wmom_inspection_schedules``。"""

    def __init__(self, engine: Engine):
        self._engine = engine
        self._sessionmaker = sessionmaker(engine, expire_on_commit=False, future=True)

    # ── CRUD ────────────────────────────────────────────────────────

    def create(
        self,
        *,
        farm_id: str,
        turbine_id: str,
        title: str,
        description: str,
        recurrence: Recurrence,
        interval_days: int | None = None,
        first_due_at: datetime | None = None,
        created_by: UUID | None = None,
    ) -> InspectionSchedule:
        """建立定檢計畫。

        ``first_due_at`` 未帶 → 預設「從現在起算一個週期後」（``compute_next_due``），
        即新排程不會一建立就立刻到期。``interval_days`` 只在
        ``recurrence=CUSTOM_DAYS`` 時使用，換算 raise ``ValueError``（非正整數）
        會直接往上拋給 caller（router 層轉 422）。

        Review must-fix：``recurrence_interval_days`` 驗證改成**無條件**呼叫（不管
        有沒有帶 ``first_due_at``）——舊寫法只在算 ``compute_next_due`` 分支（即
        ``first_due_at is None``）才會驗證，若呼叫端帶了明確 ``first_due_at`` 卻
        給無效組合（``CUSTOM_DAYS`` + ``interval_days=None``），repository 會靜默
        接受，之後排程到期時才在 ``record_spawn`` 炸開（見 ``services/
        inspection_scheduler.py`` docstring 的三層防禦說明）。repository 是可被
        直接呼叫的公開元件（tests 就是直接呼叫），不該依賴呼叫端（HTTP schema）
        已經擋過一次。
        """
        recurrence_interval_days(recurrence, interval_days)  # 提早驗證，不管 due_at 怎麼算
        now = _utc_now()
        if first_due_at is not None:
            assert_utc("first_due_at", first_due_at)
        due_at = first_due_at or compute_next_due(now, recurrence, interval_days)

        with self._sessionmaker() as sess:
            sched_id = uuid4()
            orm = InspectionScheduleORM(
                id=str(sched_id),
                farm_id=farm_id,
                turbine_id=turbine_id,
                title=title,
                description=description,
                recurrence=recurrence.value,
                interval_days=interval_days,
                next_due_at=due_at,
                active=True,
                created_at=now,
                created_by=uuid_to_str(created_by),
                updated_at=now,
            )
            sess.add(orm)
            sess.commit()
            sess.refresh(orm)
            return self._to_domain(orm)

    def get(self, schedule_id: UUID) -> InspectionSchedule | None:
        with self._sessionmaker() as sess:
            orm = sess.get(InspectionScheduleORM, str(schedule_id))
            return self._to_domain(orm) if orm else None

    def list(
        self,
        *,
        farm_id: str,
        turbine_id: str | None = None,
        active_only: bool = False,
        due_only: bool = False,
        as_of: datetime | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[InspectionSchedule], int]:
        """List 定檢計畫。

        ``due_only=True`` 時必須帶 ``as_of``（scheduler 用「此刻是否到期」過濾，
        呼叫端沒帶 raise ``ValueError`` 提早失敗，避免誤用回傳全部）；一般前端列表
        查詢不需要 ``due_only``。回傳依 ``next_due_at`` 升冪（最快到期排前面）。
        """
        if due_only and as_of is None:
            raise ValueError("due_only=True requires as_of")
        with self._sessionmaker() as sess:
            base = select(InspectionScheduleORM).where(
                InspectionScheduleORM.farm_id == farm_id
            )
            if turbine_id is not None:
                base = base.where(InspectionScheduleORM.turbine_id == turbine_id)
            if active_only:
                base = base.where(InspectionScheduleORM.active == True)  # noqa: E712
            if due_only:
                base = base.where(
                    InspectionScheduleORM.active == True,  # noqa: E712
                    InspectionScheduleORM.next_due_at <= as_of,
                )
            count_stmt = select(func.count()).select_from(base.subquery())
            total = int(sess.execute(count_stmt).scalar_one())
            paged = (
                base.order_by(InspectionScheduleORM.next_due_at)
                .limit(limit)
                .offset(offset)
            )
            items = [
                self._to_domain(orm) for orm in sess.execute(paged).scalars().all()
            ]
            return items, total

    def update_metadata(
        self,
        schedule_id: UUID,
        *,
        title: str | None = None,
        description: str | None = None,
        recurrence: Recurrence | None = None,
        interval_days: int | None = None,
    ) -> InspectionSchedule:
        """改計畫內容（標題 / 說明 / 週期）。

        改 ``recurrence`` / ``interval_days`` **不會**自動重算 ``next_due_at``
        ——下一次到期時間維持不變，新週期從下一次 ``record_spawn`` 才生效。此為
        刻意設計：避免改週期當下就讓已排定的下一次檢查提早或延後，造成現場排班
        混亂（如需立即改到期時間，另呼叫調整 API，本次範圍未做）。

        Review must-fix：commit 前驗證**改完後的最終狀態**（``recurrence`` +
        ``interval_days`` 合併後的組合）合法——舊寫法完全沒有這層檢查，若把一個
        原本 ``MONTHLY``（``interval_days=None``）的排程 PATCH 成
        ``recurrence=custom_days`` 卻不帶 ``interval_days``，會靜默寫入一個無效
        狀態；等到 scheduler 下次 ``record_spawn`` 才會 raise，且此時
        ``WorkOrder`` 已經建好、``next_due_at`` 卻沒推進——變成每次呼叫
        ``run-scheduler`` 都重複 spawn 一張新工單（見 review 報告的實測 repro）。
        這裡在 commit 前用合併後的 ``orm`` 欄位驗證，擋在寫入當下，Schema 層
        （``UpdateInspectionScheduleRequest``）看不到資料庫現有狀態故無法單獨擋
        （PATCH 只帶 ``interval_days`` 沿用既有 ``recurrence=custom_days`` 是合法
        的，schema 層必須知道「合併後」才能判斷），只能在這裡防。
        """
        with self._sessionmaker() as sess:
            orm = sess.get(InspectionScheduleORM, str(schedule_id))
            if orm is None:
                raise LookupError(f"inspection_schedule {schedule_id} not found")
            if title is not None:
                orm.title = title
            if description is not None:
                orm.description = description
            if recurrence is not None:
                orm.recurrence = recurrence.value
            if interval_days is not None:
                orm.interval_days = interval_days
            # 提早驗證合併後的最終狀態（見上方 docstring）；ValueError 在 commit 前
            # raise，orm 改動隨 session 關閉自動丟棄，不會留下半套髒資料。
            recurrence_interval_days(Recurrence(orm.recurrence), orm.interval_days)
            orm.updated_at = _utc_now()
            sess.commit()
            sess.refresh(orm)
            return self._to_domain(orm)

    def set_active(self, schedule_id: UUID, active: bool) -> InspectionSchedule:
        """暫停 / 恢復排程（軟刪除慣例，比照其他 workflow entity 不做硬刪）。"""
        with self._sessionmaker() as sess:
            orm = sess.get(InspectionScheduleORM, str(schedule_id))
            if orm is None:
                raise LookupError(f"inspection_schedule {schedule_id} not found")
            orm.active = active
            orm.updated_at = _utc_now()
            sess.commit()
            sess.refresh(orm)
            return self._to_domain(orm)

    def record_spawn(
        self,
        schedule_id: UUID,
        *,
        work_order_id: UUID,
        spawned_at: datetime,
    ) -> InspectionSchedule:
        """Scheduler spawn 工單成功後呼叫：回寫 spawn 紀錄 + 推進 ``next_due_at``。

        推進基準用 ``spawned_at``（呼叫當下時間），不是原本的 ``next_due_at`` ——
        避免排程長期停用後重新啟用時，``next_due_at`` 一路用舊基準往前推導致還是
        過期（例如週期 30 天但暫停了 100 天，若從舊到期日累加只會再過期兩次）。
        """
        assert_utc("spawned_at", spawned_at)
        with self._sessionmaker() as sess:
            orm = sess.get(InspectionScheduleORM, str(schedule_id))
            if orm is None:
                raise LookupError(f"inspection_schedule {schedule_id} not found")
            recurrence = Recurrence(orm.recurrence)
            orm.last_spawned_at = spawned_at
            orm.last_spawned_work_order_id = uuid_to_str(work_order_id)
            orm.next_due_at = compute_next_due(
                spawned_at, recurrence, orm.interval_days
            )
            orm.updated_at = spawned_at
            sess.commit()
            sess.refresh(orm)
            return self._to_domain(orm)

    # ── ORM ↔ domain conversion ─────────────────────────────────────

    @staticmethod
    def _to_domain(orm: InspectionScheduleORM) -> InspectionSchedule:
        return InspectionSchedule(
            farm_id=orm.farm_id,
            turbine_id=orm.turbine_id,
            title=orm.title,
            description=orm.description,
            recurrence=Recurrence(orm.recurrence),
            next_due_at=ensure_utc(orm.next_due_at),  # type: ignore[arg-type]
            id=UUID(orm.id),
            interval_days=orm.interval_days,
            active=orm.active,
            last_spawned_at=ensure_utc(orm.last_spawned_at),
            last_spawned_work_order_id=str_to_uuid(orm.last_spawned_work_order_id),
            created_at=ensure_utc(orm.created_at),  # type: ignore[arg-type]
            created_by=str_to_uuid(orm.created_by),
            updated_at=ensure_utc(orm.updated_at),  # type: ignore[arg-type]
        )
