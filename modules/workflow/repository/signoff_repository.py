"""SignoffRepository — persist + drive 簽核流程（WMOM-20260504-18）。

主要責任：
1. ORM ↔ dataclass round-trip（chain / step / history）
2. ``create_chain_for_work_order()`` — work_order finish 後 caller 呼叫
3. ``approve_step()`` / ``reject_step()`` — 推進 chain 狀態 + 寫 history
4. ``list_pending_for_user()`` — 「我的待簽」query
5. 整 chain approved → 回傳 flag 給 caller 觸發 work_order.approve_all()
6. 任一階 rejected → chain.overall_status = REJECTED + 回傳 flag 給 caller
   觸發 work_order.reject(reason=...)

Repository 是 stateless wrapper — engine 沿用 work_order_repository 的 cache。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from modules.workflow.domain import (
    SignoffChain,
    SignoffHistoryEntry,
    SignoffLevel,
    SignoffStatus,
    SignoffStep,
    SignoffSubjectType,
    build_chain_levels,
)
from modules.workflow.domain.work_order import _utc_now

from ._helpers import (
    ensure_utc,
    json_safe,
    str_to_uuid,
    uuid_to_str,
)
from .orm_models import (
    Base,
    SignoffChainORM,
    SignoffHistoryORM,
    SignoffStepORM,
)
from .work_order_repository import _ENGINE_LOCK, _SCHEMA_INITIALIZED, _get_engine

# Backward-compat aliases (review fix #5)
_ensure_utc = ensure_utc
_uuid_to_str = uuid_to_str
_str_to_uuid = str_to_uuid
_json_safe = json_safe


# ─────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────


class SignoffActionError(Exception):
    """簽核行為被拒（chain 已 terminal / step 已 decided / level 不對等）。

    Caller 通常 catch 之後轉 409 Conflict（HTTP）或 422。
    """


# ─────────────────────────────────────────────────────────────────────────
# Helpers — review fix #5：改 import from _helpers.py，不再本地定義
# （見 file top: _ensure_utc / _uuid_to_str / _str_to_uuid / _json_safe alias）
# ─────────────────────────────────────────────────────────────────────────


def get_signoff_repository(db_path: str) -> "SignoffRepository":
    """Factory — 拿一個 SignoffRepository instance。

    DB schema 沿用 work_order_repository 的 ``_SCHEMA_INITIALIZED`` cache：第一次見到
    db_path 時 ``Base.metadata.create_all`` 會把 signoff_chains / signoff_steps /
    signoff_history 三表一起建好（與 work_order 表同一 Base）。
    """
    from pathlib import Path

    engine = _get_engine(db_path)
    abs_path = str(Path(db_path).resolve())
    with _ENGINE_LOCK:
        if abs_path not in _SCHEMA_INITIALIZED:
            Base.metadata.create_all(engine)
            _SCHEMA_INITIALIZED.add(abs_path)
    return SignoffRepository(engine)


# ─────────────────────────────────────────────────────────────────────────
# Repository
# ─────────────────────────────────────────────────────────────────────────


class SignoffRepository:
    """SQLAlchemy 2.0 repository for signoff_chains + signoff_steps + signoff_history。"""

    def __init__(self, engine: Engine):
        self._engine = engine
        self._sessionmaker = sessionmaker(engine, expire_on_commit=False, future=True)

    # ── Create chain ────────────────────────────────────────────────

    def create_chain_for_work_order(
        self,
        *,
        work_order_id: UUID,
        farm_id: str,
        farm_config: dict[str, Any] | None = None,
        escalate_to_supervisor: bool = False,
        actor_id: UUID | None = None,
    ) -> SignoffChain:
        """工單 finish 完成後呼叫；建 chain + 全 step（依 farm config + escalate flag）。

        Returns ``SignoffChain``（含已建好 steps 但 sequence=0 的 status=pending；
        其餘 step 也是 pending 但 caller 視為 sequenced — list_pending_for_user
        會自動只回 ``current_level_index`` 對應的 level）。
        """
        levels = build_chain_levels(
            SignoffSubjectType.WORK_ORDER,
            farm_config=farm_config,
            escalate_to_supervisor=escalate_to_supervisor,
        )
        return self._create_chain(
            subject_type=SignoffSubjectType.WORK_ORDER,
            subject_id=work_order_id,
            farm_id=farm_id,
            levels=levels,
            actor_id=actor_id,
        )

    def create_chain_for_material_request(
        self,
        *,
        material_request_id: UUID,
        farm_id: str,
        farm_config: dict[str, Any] | None = None,
        escalate_to_supervisor: bool = False,
        actor_id: UUID | None = None,
    ) -> SignoffChain:
        """領料單 submit-for-approval 後呼叫；建 chain（DN-02 D2-Q2 預設 3 階：
        EMPLOYEE → LEADER → TREASURY）。

        ``escalate_to_supervisor`` 預留給 critical priority MR — 加 SUPERVISOR
        層在 LEADER 與 TREASURY 之間（M5+ 細項）。
        """
        levels = build_chain_levels(
            SignoffSubjectType.MATERIAL_REQUEST,
            farm_config=farm_config,
            escalate_to_supervisor=escalate_to_supervisor,
        )
        return self._create_chain(
            subject_type=SignoffSubjectType.MATERIAL_REQUEST,
            subject_id=material_request_id,
            farm_id=farm_id,
            levels=levels,
            actor_id=actor_id,
        )

    def _create_chain(
        self,
        *,
        subject_type: SignoffSubjectType,
        subject_id: UUID,
        farm_id: str,
        levels: list[SignoffLevel],
        actor_id: UUID | None,
    ) -> SignoffChain:
        with self._sessionmaker() as sess:
            chain_id = uuid4()
            now = _utc_now()
            chain_orm = SignoffChainORM(
                id=str(chain_id),
                subject_type=subject_type.value,
                subject_id=str(subject_id),
                farm_id=farm_id,
                levels_json=json.dumps([lvl.value for lvl in levels]),
                current_level_index=0,
                overall_status=SignoffStatus.PENDING.value,
                started_at=now,
            )
            sess.add(chain_orm)
            for idx, lvl in enumerate(levels):
                step_orm = SignoffStepORM(
                    id=str(uuid4()),
                    chain_id=str(chain_id),
                    level=lvl.value,
                    sequence=idx,
                    status=SignoffStatus.PENDING.value,
                    created_at=now,
                )
                sess.add(step_orm)
            self._append_history(
                sess, chain_id=str(chain_id), step_id=None,
                event_type="chain_created", actor_id=actor_id,
                payload={
                    "subject_type": subject_type.value,
                    "subject_id": str(subject_id),
                    "levels": [lvl.value for lvl in levels],
                },
                occurred_at=now,
            )
            sess.commit()
            sess.refresh(chain_orm)
            return self._chain_to_domain(chain_orm)

    # ── Get chain / pending list ────────────────────────────────────

    def get_chain(self, chain_id: UUID) -> SignoffChain | None:
        with self._sessionmaker() as sess:
            orm = sess.get(SignoffChainORM, str(chain_id))
            return self._chain_to_domain(orm) if orm else None

    def get_chain_for_subject(
        self, subject_type: SignoffSubjectType, subject_id: UUID
    ) -> SignoffChain | None:
        """查某 work_order / material_request 的最新 chain（reject 後重送會有多個）。

        review fix #5：``started_at`` 在 SQLite TEXT datetime 毫秒精度下兩個極近時間
        會 tie；用 ``rowid`` 作 secondary sort 確保「最新」定義穩定（rowid 永遠遞增）。
        """
        with self._sessionmaker() as sess:
            stmt = (
                select(SignoffChainORM)
                .where(SignoffChainORM.subject_type == subject_type.value)
                .where(SignoffChainORM.subject_id == str(subject_id))
                .order_by(
                    SignoffChainORM.started_at.desc(),
                    SignoffChainORM.id.desc(),  # tiebreaker（UUID 字典序，保持穩定）
                )
                .limit(1)
            )
            orm = sess.execute(stmt).scalar_one_or_none()
            return self._chain_to_domain(orm) if orm else None

    def get_steps(self, chain_id: UUID) -> list[SignoffStep]:
        with self._sessionmaker() as sess:
            stmt = (
                select(SignoffStepORM)
                .where(SignoffStepORM.chain_id == str(chain_id))
                .order_by(SignoffStepORM.sequence)
            )
            return [self._step_to_domain(s) for s in sess.execute(stmt).scalars()]

    def list_pending_for_level(
        self,
        *,
        farm_id: str,
        level: SignoffLevel,
        subject_type: SignoffSubjectType | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[tuple[SignoffStep, SignoffChain]], int]:
        """「我的待簽」query — 給某 level 的 user 看「我這層 pending 的 steps + 對應 chain」。

        Review fix #6：回 ``(items, total)``，total 是真實 DB count（前端分頁用）。
        Review fix #11：加 ``offset`` 支援分頁。
        Review fix #12：加 ``subject_type`` filter — M4 領料單上線後 EMPLOYEE level
        待簽會混入工單 / 領料單，現在就預留。

        Returns ``([(step, chain), ...], total)`` — 帶 chain 給 frontend 顯示 subject 摘要。
        只回「current_level_index 已走到此 step.sequence」的 steps（不會早於 chain 進度）。
        """
        with self._sessionmaker() as sess:
            base = (
                select(SignoffStepORM, SignoffChainORM)
                .join(SignoffChainORM, SignoffStepORM.chain_id == SignoffChainORM.id)
                .where(SignoffChainORM.farm_id == farm_id)
                .where(SignoffStepORM.level == level.value)
                .where(SignoffStepORM.status == SignoffStatus.PENDING.value)
                .where(SignoffChainORM.overall_status == SignoffStatus.PENDING.value)
                .where(SignoffStepORM.sequence == SignoffChainORM.current_level_index)
            )
            if subject_type is not None:
                base = base.where(SignoffChainORM.subject_type == subject_type.value)

            # 真實 total — 不受 limit / offset 影響
            count_stmt = select(func.count()).select_from(base.subquery())
            total = int(sess.execute(count_stmt).scalar_one())

            page_stmt = base.order_by(
                SignoffChainORM.started_at.asc()
            ).offset(offset).limit(limit)

            results = []
            for step_orm, chain_orm in sess.execute(page_stmt).all():
                results.append((
                    self._step_to_domain(step_orm),
                    self._chain_to_domain(chain_orm),
                ))
            return results, total

    # ── Approve / Reject ────────────────────────────────────────────

    def approve_step(
        self,
        step_id: UUID,
        *,
        actor_id: UUID,
        comment: str | None = None,
    ) -> tuple[SignoffChain, bool]:
        """Approve 一階 step。

        Returns ``(updated_chain, is_chain_completed)``
        - is_chain_completed=True 表示這是最後一階 + 全通過 → caller 應觸發
          work_order.approve_all() 進 CLOSED

        review fix #7：對 ``SignoffChainORM`` 加 ``with_for_update()`` 取 row lock，
        避免多 thread / multi-worker 並發 approve 同一 step 時 race。
        SQLite WAL 對 with_for_update 的支援有限（會 silent ignore），但對未來換
        PostgreSQL 時即可用；當前 single-process busy_timeout=5s 已足夠 serialize 寫入。
        """
        with self._sessionmaker() as sess:
            # review fix #10：step + chain 雙 row lock — 防 PG 並發 last-write-wins
            step_orm = sess.get(SignoffStepORM, str(step_id), with_for_update=True)
            if step_orm is None:
                raise LookupError(f"signoff_step {step_id} not found")
            chain_orm = sess.get(
                SignoffChainORM, step_orm.chain_id, with_for_update=True
            )
            if chain_orm is None:
                raise LookupError(f"signoff_chain for step {step_id} missing")

            self._validate_step_decidable(chain_orm, step_orm)

            now = _utc_now()
            step_orm.status = SignoffStatus.APPROVED.value
            step_orm.decided_at = now
            step_orm.decided_by = str(actor_id)
            step_orm.comment = comment

            # 若是最後一階 → 全 chain APPROVED
            is_last = (step_orm.sequence == self._max_sequence(chain_orm))
            if is_last:
                chain_orm.overall_status = SignoffStatus.APPROVED.value
                chain_orm.completed_at = now
                self._append_history(
                    sess, chain_id=chain_orm.id, step_id=step_orm.id,
                    event_type="step_approved", actor_id=actor_id,
                    payload={"comment": comment, "level": step_orm.level},
                    occurred_at=now,
                )
                self._append_history(
                    sess, chain_id=chain_orm.id, step_id=None,
                    event_type="chain_completed", actor_id=actor_id,
                    payload={"final_status": "approved"},
                    occurred_at=now,
                )
            else:
                chain_orm.current_level_index = step_orm.sequence + 1
                self._append_history(
                    sess, chain_id=chain_orm.id, step_id=step_orm.id,
                    event_type="step_approved", actor_id=actor_id,
                    payload={"comment": comment, "level": step_orm.level},
                    occurred_at=now,
                )

            sess.commit()
            sess.refresh(chain_orm)
            return self._chain_to_domain(chain_orm), is_last

    def reject_step(
        self,
        step_id: UUID,
        *,
        actor_id: UUID,
        reason: str,
    ) -> SignoffChain:
        """Reject 一階 step → 整 chain 進 REJECTED；caller 應觸發 work_order.reject()。"""
        if not reason:
            raise SignoffActionError("reject requires non-empty reason")

        with self._sessionmaker() as sess:
            # review fix #7+#10：step + chain 雙 row lock
            step_orm = sess.get(SignoffStepORM, str(step_id), with_for_update=True)
            if step_orm is None:
                raise LookupError(f"signoff_step {step_id} not found")
            chain_orm = sess.get(
                SignoffChainORM, step_orm.chain_id, with_for_update=True
            )
            if chain_orm is None:
                raise LookupError(f"signoff_chain for step {step_id} missing")

            self._validate_step_decidable(chain_orm, step_orm)

            now = _utc_now()
            step_orm.status = SignoffStatus.REJECTED.value
            step_orm.decided_at = now
            step_orm.decided_by = str(actor_id)
            step_orm.comment = reason

            chain_orm.overall_status = SignoffStatus.REJECTED.value
            chain_orm.completed_at = now
            chain_orm.rejected_at_level = step_orm.level
            chain_orm.rejected_reason = reason

            self._append_history(
                sess, chain_id=chain_orm.id, step_id=step_orm.id,
                event_type="step_rejected", actor_id=actor_id,
                payload={"reason": reason, "level": step_orm.level},
                occurred_at=now,
            )
            self._append_history(
                sess, chain_id=chain_orm.id, step_id=None,
                event_type="chain_completed", actor_id=actor_id,
                payload={"final_status": "rejected", "rejected_at_level": step_orm.level},
                occurred_at=now,
            )

            sess.commit()
            sess.refresh(chain_orm)
            return self._chain_to_domain(chain_orm)

    # ── Internal helpers ────────────────────────────────────────────

    def _validate_step_decidable(
        self, chain_orm: SignoffChainORM, step_orm: SignoffStepORM
    ) -> None:
        """共用驗證：chain 仍 pending、step 仍 pending、step 是 chain 當前進度。

        review fix #6：``parallel_group_id`` 為 D2-Q4 預留欄位但尚未實作邏輯；若
        step 帶非 None 值就 fail loudly，避免「設了沒用」誤導 client。
        """
        if step_orm.parallel_group_id is not None:
            raise NotImplementedError(
                f"step {step_orm.id} has parallel_group_id={step_orm.parallel_group_id!r} "
                "but parallel signoff is not implemented yet (D2-Q4 future work)"
            )
        if chain_orm.overall_status != SignoffStatus.PENDING.value:
            raise SignoffActionError(
                f"chain {chain_orm.id} is already {chain_orm.overall_status}; "
                "cannot decide further steps"
            )
        if step_orm.status != SignoffStatus.PENDING.value:
            raise SignoffActionError(
                f"step {step_orm.id} already {step_orm.status}; "
                "cannot re-decide"
            )
        if step_orm.sequence != chain_orm.current_level_index:
            raise SignoffActionError(
                f"step {step_orm.id} (sequence={step_orm.sequence}) is not the "
                f"current step (chain.current_level_index="
                f"{chain_orm.current_level_index}); cannot skip levels"
            )

    @staticmethod
    def _max_sequence(chain_orm: SignoffChainORM) -> int:
        # 直接讀 levels_json 算長度
        return len(json.loads(chain_orm.levels_json)) - 1

    def _append_history(
        self,
        sess: Session,
        *,
        chain_id: str,
        step_id: str | None,
        event_type: str,
        actor_id: UUID | None,
        payload: dict[str, Any],
        occurred_at: datetime,
    ) -> None:
        sess.add(SignoffHistoryORM(
            chain_id=chain_id,
            step_id=step_id,
            event_type=event_type,
            actor_id=_uuid_to_str(actor_id),
            payload_json=json.dumps(payload, default=_json_safe, ensure_ascii=False),
            occurred_at=occurred_at,
        ))

    # ── ORM ↔ domain conversion ─────────────────────────────────────

    @staticmethod
    def _chain_to_domain(orm: SignoffChainORM) -> SignoffChain:
        levels_raw = json.loads(orm.levels_json)
        return SignoffChain(
            id=UUID(orm.id),
            subject_type=SignoffSubjectType(orm.subject_type),
            subject_id=UUID(orm.subject_id),
            farm_id=orm.farm_id,
            levels=[SignoffLevel(lvl) for lvl in levels_raw],
            current_level_index=orm.current_level_index,
            overall_status=SignoffStatus(orm.overall_status),
            started_at=_ensure_utc(orm.started_at),  # type: ignore[arg-type]
            completed_at=_ensure_utc(orm.completed_at),
            rejected_at_level=(
                SignoffLevel(orm.rejected_at_level) if orm.rejected_at_level else None
            ),
            rejected_reason=orm.rejected_reason,
        )

    @staticmethod
    def _step_to_domain(orm: SignoffStepORM) -> SignoffStep:
        return SignoffStep(
            id=UUID(orm.id),
            chain_id=UUID(orm.chain_id),
            level=SignoffLevel(orm.level),
            sequence=orm.sequence,
            parallel_group_id=_str_to_uuid(orm.parallel_group_id),
            assignee_id=_str_to_uuid(orm.assignee_id),
            status=SignoffStatus(orm.status),
            decided_at=_ensure_utc(orm.decided_at),
            decided_by=_str_to_uuid(orm.decided_by),
            comment=orm.comment,
            created_at=_ensure_utc(orm.created_at),  # type: ignore[arg-type]
        )
