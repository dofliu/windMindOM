"""DayWorkFormRepository — 員工當天日誌 get-or-create + append-activity + query（WMOM-20260505-21）。

責任：
1. ORM ↔ dataclass round-trip（``_to_domain`` / activities JSON 序列化）
2. ``get_or_create_for_date``：一天一位員工只建立一次（natural key idempotent）
3. ``append_activity``：日誌內累加一筆 activity（``validate_activity_entry`` 先擋）
4. ``get`` / ``get_by_date`` / ``list``：查詢

與 ``WorkOrderRepository`` 共用 engine cache（``_get_engine`` / ``_ENGINE_LOCK`` /
``_SCHEMA_INITIALIZED``），避免同一 farm DB 開兩條 connection pool（沿襲
``InspectionScheduleRepository`` 的做法）。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from modules.workflow.domain.day_work_form import (
    ActivityEntry,
    ActivityKind,
    DayWorkForm,
    _utc_now,
    validate_activity_entry,
)

from ._helpers import ensure_utc, json_safe, str_to_uuid, uuid_to_str
from .day_work_form_orm import DayWorkFormORM
from .orm_models import Base
from .work_order_repository import _ENGINE_LOCK, _SCHEMA_INITIALIZED, _get_engine


def get_day_work_form_repository(db_path: str) -> "DayWorkFormRepository":
    """Factory — 共用 work_order_repository 的 engine cache。"""
    engine = _get_engine(db_path)
    abs_path = str(Path(db_path).resolve())
    with _ENGINE_LOCK:
        if abs_path not in _SCHEMA_INITIALIZED:
            Base.metadata.create_all(engine)
            _SCHEMA_INITIALIZED.add(abs_path)
    return DayWorkFormRepository(engine)


class DayWorkFormRepository:
    """SQLAlchemy 2.0 repository for ``wmom_day_work_forms``。"""

    def __init__(self, engine: Engine):
        self._engine = engine
        self._sessionmaker = sessionmaker(engine, expire_on_commit=False, future=True)

    # ── get-or-create ────────────────────────────────────────────────

    def get_or_create_for_date(
        self,
        *,
        farm_id: str,
        employee_id: UUID,
        work_date: date,
        created_by: UUID | None = None,
    ) -> DayWorkForm:
        """取得當天日誌，不存在則建立空日誌（一天一位員工僅一份，natural key idempotent）。

        BEGIN IMMEDIATE（見 ``work_order_repository._get_engine``）已讓每個
        transaction 一開始就取得寫鎖，select-then-insert 之間理論上不會被其他
        transaction 插隊；仍保留 ``IntegrityError`` fallback 作防禦（沿襲
        ``WorkOrderRepository.create`` 的 business_key retry 慣例），並非本次
        主要風險點。
        """
        with self._sessionmaker() as sess:
            existing = self._select_by_natural_key(sess, farm_id, employee_id, work_date)
            if existing is not None:
                return self._to_domain(existing)

            now = _utc_now()
            orm = DayWorkFormORM(
                id=str(uuid4()),
                farm_id=farm_id,
                employee_id=uuid_to_str(employee_id),
                work_date=work_date,
                activities_json="[]",
                notes="",
                created_at=now,
                created_by=uuid_to_str(created_by),
                updated_at=now,
            )
            sess.add(orm)
            try:
                sess.commit()
            except IntegrityError:
                sess.rollback()
                existing = self._select_by_natural_key(
                    sess, farm_id, employee_id, work_date
                )
                if existing is None:
                    raise
                return self._to_domain(existing)
            sess.refresh(orm)
            return self._to_domain(orm)

    @staticmethod
    def _select_by_natural_key(
        sess: Session, farm_id: str, employee_id: UUID, work_date: date
    ) -> DayWorkFormORM | None:
        stmt = select(DayWorkFormORM).where(
            DayWorkFormORM.farm_id == farm_id,
            DayWorkFormORM.employee_id == uuid_to_str(employee_id),
            DayWorkFormORM.work_date == work_date,
        )
        return sess.execute(stmt).scalar_one_or_none()

    # ── activity ─────────────────────────────────────────────────────

    def append_activity(self, form_id: UUID, entry: ActivityEntry) -> DayWorkForm:
        """新增一筆 activity 到日誌（依 ``kind`` 驗證必填欄位，未通過 raise ``ValueError``）。"""
        validate_activity_entry(entry)
        with self._sessionmaker() as sess:
            orm = sess.get(DayWorkFormORM, str(form_id))
            if orm is None:
                raise LookupError(f"day_work_form {form_id} not found")
            activities = json.loads(orm.activities_json)
            activities.append(_activity_to_dict(entry))
            orm.activities_json = json.dumps(
                activities, default=json_safe, ensure_ascii=False
            )
            orm.updated_at = _utc_now()
            sess.commit()
            sess.refresh(orm)
            return self._to_domain(orm)

    # ── query ────────────────────────────────────────────────────────

    def get(self, form_id: UUID) -> DayWorkForm | None:
        with self._sessionmaker() as sess:
            orm = sess.get(DayWorkFormORM, str(form_id))
            return self._to_domain(orm) if orm else None

    def get_by_date(
        self, *, farm_id: str, employee_id: UUID, work_date: date
    ) -> DayWorkForm | None:
        """「我今天做了什麼」query——純讀取，不存在回 ``None``（不side-effect 建立）。"""
        with self._sessionmaker() as sess:
            orm = self._select_by_natural_key(sess, farm_id, employee_id, work_date)
            return self._to_domain(orm) if orm else None

    def list(
        self,
        *,
        farm_id: str,
        employee_id: UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[DayWorkForm], int]:
        """List 日誌，依 ``work_date`` 降冪（最新在前）。"""
        with self._sessionmaker() as sess:
            base = select(DayWorkFormORM).where(DayWorkFormORM.farm_id == farm_id)
            if employee_id is not None:
                base = base.where(
                    DayWorkFormORM.employee_id == uuid_to_str(employee_id)
                )
            if date_from is not None:
                base = base.where(DayWorkFormORM.work_date >= date_from)
            if date_to is not None:
                base = base.where(DayWorkFormORM.work_date <= date_to)
            count_stmt = select(func.count()).select_from(base.subquery())
            total = int(sess.execute(count_stmt).scalar_one())
            paged = (
                base.order_by(DayWorkFormORM.work_date.desc())
                .limit(limit)
                .offset(offset)
            )
            items = [
                self._to_domain(orm) for orm in sess.execute(paged).scalars().all()
            ]
            return items, total

    # ── ORM ↔ domain conversion ─────────────────────────────────────

    @staticmethod
    def _to_domain(orm: DayWorkFormORM) -> DayWorkForm:
        return DayWorkForm(
            farm_id=orm.farm_id,
            employee_id=UUID(orm.employee_id),
            work_date=orm.work_date,
            id=UUID(orm.id),
            activities=[
                _activity_from_dict(d) for d in json.loads(orm.activities_json)
            ],
            notes=orm.notes,
            created_at=ensure_utc(orm.created_at),  # type: ignore[arg-type]
            created_by=str_to_uuid(orm.created_by),
            updated_at=ensure_utc(orm.updated_at),  # type: ignore[arg-type]
        )


def _activity_to_dict(entry: ActivityEntry) -> dict:
    return {
        "id": str(entry.id),
        "kind": entry.kind.value,
        "wo_id": uuid_to_str(entry.wo_id),
        "item_id": uuid_to_str(entry.item_id),
        "result": entry.result,
        "area": entry.area,
        "topic": entry.topic,
        "note": entry.note,
        "logged_at": entry.logged_at.isoformat(),
    }


def _activity_from_dict(d: dict) -> ActivityEntry:
    return ActivityEntry(
        kind=ActivityKind(d["kind"]),
        id=UUID(d["id"]),
        wo_id=str_to_uuid(d.get("wo_id")),
        item_id=str_to_uuid(d.get("item_id")),
        result=d.get("result"),
        area=d.get("area"),
        topic=d.get("topic"),
        note=d.get("note", ""),
        logged_at=ensure_utc(datetime.fromisoformat(d["logged_at"])),  # type: ignore[arg-type]
    )
