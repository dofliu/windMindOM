"""CostLedgerRepository — query + confirm 介面（WMOM-20260509-05）。

責任：
1. ORM ↔ dataclass round-trip
2. Query：``get`` / ``list`` / ``find_for_mr_item`` / ``summary_by_category``
3. Confirm：``confirm_entry`` / ``confirm_entries_for_subject`` — flip estimated → confirmed
4. **不負責** insert — 那條走 ``cost_ledger.insert_in_session()``（atomic transaction
   擁有者來呼叫，例如 ``MaterialRequestRepository.dispatch_request`` 的雙寫）

A5 ledger module 對 reporting (A8 monthly_report.py) 是主要 consumer：
``summary_by_category(farm_id, from, to)`` 直接拿 4 大類 confirmed cost 拼月報。
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from .cost_ledger import (
    CostLedgerCategory,
    CostLedgerEntry,
    CostLedgerEntryORM,
    CostLedgerSourceType,
    CostLedgerStatus,
)

_logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    from datetime import timezone

    return datetime.now(tz=timezone.utc)


# ─────────────────────────────────────────────────────────────────────────
# Repository factory
# ─────────────────────────────────────────────────────────────────────────


def get_cost_ledger_repository(db_path: str) -> "CostLedgerRepository":
    """Factory — 共用 workflow engine cache + Base.metadata.create_all。

    Lazy import workflow internals 避免 circular import（cost_ledger_repository
    被 workflow material_request_repository 透過 insert_in_session 間接 import）。
    """
    from modules.workflow.repository.orm_models import Base
    from modules.workflow.repository.work_order_repository import (
        _ENGINE_LOCK,
        _SCHEMA_INITIALIZED,
        _get_engine,
    )

    engine = _get_engine(db_path)
    abs_path = str(Path(db_path).resolve())
    with _ENGINE_LOCK:
        if abs_path not in _SCHEMA_INITIALIZED:
            Base.metadata.create_all(engine)
            _SCHEMA_INITIALIZED.add(abs_path)
    return CostLedgerRepository(engine)


# ─────────────────────────────────────────────────────────────────────────
# Repository
# ─────────────────────────────────────────────────────────────────────────


class CostLedgerRepository:
    """SQLAlchemy 2.0 repository for cost_ledger_entries — read + confirm。"""

    def __init__(self, engine: Engine):
        self._engine = engine
        self._sessionmaker = sessionmaker(engine, expire_on_commit=False, future=True)

    # ── Query ──────────────────────────────────────────────────────────

    def get(self, entry_id: UUID) -> CostLedgerEntry | None:
        with self._sessionmaker() as sess:
            orm = sess.get(CostLedgerEntryORM, str(entry_id))
            return self._to_domain(orm) if orm else None

    def list(
        self,
        *,
        farm_id: str,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        category: CostLedgerCategory | None = None,
        status: CostLedgerStatus | None = None,
        source_type: CostLedgerSourceType | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[CostLedgerEntry], int]:
        """List + filter — 給月報 / dashboard / KPI 用。"""
        with self._sessionmaker() as sess:
            base = select(CostLedgerEntryORM).where(
                CostLedgerEntryORM.farm_id == farm_id
            )
            if from_date is not None:
                base = base.where(CostLedgerEntryORM.recorded_at >= from_date)
            if to_date is not None:
                base = base.where(CostLedgerEntryORM.recorded_at < to_date)
            if category is not None:
                base = base.where(CostLedgerEntryORM.category == category.value)
            if status is not None:
                base = base.where(CostLedgerEntryORM.status == status.value)
            if source_type is not None:
                base = base.where(CostLedgerEntryORM.source_type == source_type.value)

            count_stmt = base.with_only_columns(CostLedgerEntryORM.id)
            total = len(sess.execute(count_stmt).scalars().all())

            paged = (
                base.order_by(CostLedgerEntryORM.recorded_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return (
                [self._to_domain(orm) for orm in sess.execute(paged).scalars().all()],
                total,
            )

    def find_for_mr_item(
        self, material_request_id: UUID, item_id: UUID
    ) -> CostLedgerEntry | None:
        """精確找 MR 某個 line item 對應的 dispatch ledger entry（A5 confirm flow 用）。

        WMOM-20260509-F1：filter ``amount >= 0`` 排除退料負金額 entry，避免
        當 MR 同 line item 已有退料時 ``scalar_one_or_none`` raise MultipleResultsFound。
        Dispatch entry 即使被 confirm 成 amount=0（actual_qty=0 case）仍 ≥ 0 可被選中。
        """
        with self._sessionmaker() as sess:
            stmt = select(CostLedgerEntryORM).where(
                CostLedgerEntryORM.source_event_id == str(material_request_id),
                CostLedgerEntryORM.source_item_id == str(item_id),
                CostLedgerEntryORM.source_type
                == CostLedgerSourceType.MATERIAL_REQUEST.value,
                CostLedgerEntryORM.amount >= 0,
            )
            orm = sess.execute(stmt).scalar_one_or_none()
            return self._to_domain(orm) if orm else None

    def list_for_subject(
        self,
        subject_id: UUID,
        subject_type: CostLedgerSourceType,
    ) -> list[CostLedgerEntry]:
        """List 一個 subject (MR / WO / fault) 對應的所有 ledger entries。"""
        with self._sessionmaker() as sess:
            stmt = select(CostLedgerEntryORM).where(
                CostLedgerEntryORM.source_event_id == str(subject_id),
                CostLedgerEntryORM.source_type == subject_type.value,
            )
            return [
                self._to_domain(orm)
                for orm in sess.execute(stmt).scalars().all()
            ]

    def summary_by_category(
        self,
        *,
        farm_id: str,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        status: CostLedgerStatus | None = None,
    ) -> dict[CostLedgerCategory, Decimal]:
        """4 大類 cost 加總（給 monthly_report A8 用）。

        預設 ``status=None`` 加總全部（estimated + confirmed）；要算 actual 報表
        傳 ``CostLedgerStatus.CONFIRMED``。
        """
        with self._sessionmaker() as sess:
            stmt = select(
                CostLedgerEntryORM.category,
                func.sum(CostLedgerEntryORM.amount).label("total"),
            ).where(CostLedgerEntryORM.farm_id == farm_id)
            if from_date is not None:
                stmt = stmt.where(CostLedgerEntryORM.recorded_at >= from_date)
            if to_date is not None:
                stmt = stmt.where(CostLedgerEntryORM.recorded_at < to_date)
            if status is not None:
                stmt = stmt.where(CostLedgerEntryORM.status == status.value)
            stmt = stmt.group_by(CostLedgerEntryORM.category)

            result: dict[CostLedgerCategory, Decimal] = {}
            for category_str, total in sess.execute(stmt).all():
                cat = CostLedgerCategory(category_str)
                result[cat] = Decimal(str(total)) if total is not None else Decimal("0")
            return result

    # ── Confirm ─────────────────────────────────────────────────────────

    def confirm_entry(
        self,
        entry_id: UUID,
        *,
        new_amount: Decimal,
        actor_id: UUID | None = None,
    ) -> CostLedgerEntry:
        """Estimated → Confirmed flip + 更新 amount（給 wo finish hook 用）。

        - 已 confirmed → no-op return（idempotent，避免 wo 重 finish 重複觸發）
        - entry 不存在 → ``LookupError``
        - new_amount 必須非負

        Note：actor_id 寫進 entry.actor_id（覆蓋 dispatch 時的 actor，因為 confirm 是
        新事件）；保留原 entry.id 不換。
        """
        if new_amount < 0:
            raise ValueError(f"new_amount must be >= 0 (got {new_amount})")

        with self._sessionmaker() as sess:
            orm = sess.get(CostLedgerEntryORM, str(entry_id))
            if orm is None:
                raise LookupError(f"cost_ledger_entry {entry_id} not found")

            # idempotent：已 confirmed 不重做（避免 amount 被改回）
            if orm.status == CostLedgerStatus.CONFIRMED.value:
                return self._to_domain(orm)

            orm.amount = new_amount
            orm.status = CostLedgerStatus.CONFIRMED.value
            orm.confirmed_at = _utc_now()
            if actor_id is not None:
                orm.actor_id = str(actor_id)
            sess.commit()
            sess.refresh(orm)
            return self._to_domain(orm)

    # ── ORM → domain ────────────────────────────────────────────────────

    @staticmethod
    def _to_domain(orm: CostLedgerEntryORM) -> CostLedgerEntry:
        # lazy import for circular import 防護
        from modules.workflow.repository._helpers import ensure_utc, str_to_uuid

        return CostLedgerEntry(
            id=UUID(orm.id),
            farm_id=orm.farm_id,
            category=CostLedgerCategory(orm.category),
            amount=Decimal(str(orm.amount)) if orm.amount is not None else Decimal("0"),
            source_event_id=UUID(orm.source_event_id),
            source_item_id=str_to_uuid(orm.source_item_id),
            locked_unit_cost=(
                Decimal(str(orm.locked_unit_cost))
                if orm.locked_unit_cost is not None
                else None
            ),
            source_type=CostLedgerSourceType(orm.source_type),
            status=CostLedgerStatus(orm.status),
            actor_id=str_to_uuid(orm.actor_id),
            note=orm.note,
            recorded_at=ensure_utc(orm.recorded_at) or _utc_now(),
            confirmed_at=ensure_utc(orm.confirmed_at),
        )
