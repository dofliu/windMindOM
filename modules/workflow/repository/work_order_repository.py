"""WorkOrderRepository — persist + load + state transition wrapping（WMOM-20260504-17）。

主要責任：
1. ORM ↔ dataclass round-trip（``_to_domain`` / ``_to_orm``）
2. CRUD：create / get / list / update
3. State machine wrapping：``transition`` 呼叫 domain 層的 ``WorkOrderStateMachine``，
   驗證後 persist + 寫 event log
4. Multi-WO constraint enforcement（一台風機 ≤ 3 OPEN + 不同 alarm_code 才可多張）
5. Business key 自動生成 ``WO-{farm_id_short}-{YYYYMM}-{NN}``

Repository 是 stateless wrapper — engine cache 在 module-level（per farm_id）。
Caller 用 ``get_repository(db_path)`` 拿，不直接 new。
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, create_engine, event as sa_event, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from modules.workflow.domain import (
    FollowupKind,
    InvalidTransition,
    Priority,
    ProgressNote,
    WorkOrder,
    WorkOrderStateMachine,
    WorkOrderStatus,
    WorkOrderType,
    open_states,
)
from modules.workflow.domain.work_order import _utc_now

from ._helpers import (
    assert_utc as _assert_utc_helper,
    ensure_utc,
    json_safe,
    str_to_uuid,
    uuid_to_str,
)
from .orm_models import (
    Base,
    ProgressNoteORM,
    WorkOrderEventLogORM,
    WorkOrderORM,
)


# ─────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────


class BusinessRuleViolation(Exception):
    """違反 multi-WO constraint 等業務規則（不是 state machine 層的）。

    Caller 通常 catch 之後轉 409 Conflict（HTTP）。
    """


# ─────────────────────────────────────────────────────────────────────────
# Engine cache
# ─────────────────────────────────────────────────────────────────────────


_ENGINE_CACHE: dict[str, Engine] = {}
_SCHEMA_INITIALIZED: set[str] = set()  # 已跑過 create_all 的 db_path（避免每次 API call 重跑）
_ENGINE_LOCK = threading.Lock()


def _set_sqlite_pragmas(dbapi_conn, _record) -> None:
    """SQLAlchemy connect event — 主動設 WAL + busy_timeout（fix #5）。

    與 monitoring/server/sqlite_utils.open_sqlite 行為一致；workflow 第一個開 connection
    時也會把 DB 切到 WAL（與 monitoring 並存的 raw sqlite3 共用 WAL journal）。

    另把 pysqlite 的 isolation_level 設 None（autocommit）關掉 driver 自動發 BEGIN，
    交由下方 ``_begin_immediate`` listener 改發 ``BEGIN IMMEDIATE`` — 見該函式 docstring。
    """
    dbapi_conn.isolation_level = None  # 關掉 pysqlite 自動 BEGIN，交給 _begin_immediate
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()


def _begin_immediate(conn: Connection) -> None:
    """SQLAlchemy begin event — 每個 transaction 改用 ``BEGIN IMMEDIATE`` 起頭。

    pysqlite 預設 ``BEGIN DEFERRED``：寫鎖延後到 transaction 內**第一次寫**才取得。
    這讓「先 SELECT 讀庫存 → 計算 → UPDATE 扣庫存」的 read-modify-write 在並發下會
    lost update —— 兩個 ``dispatch_request`` 同時 SELECT 到同一份 stock，各自扣完都
    commit，造成超扣（double-spend）。``with_for_update()`` 在 SQLite 是 no-op，擋不住。

    改 ``BEGIN IMMEDIATE`` 後，transaction 一開始就取得 RESERVED 寫鎖：第二個並發
    transaction 的 BEGIN 會被 busy_timeout（5s）擋住，等第一個 commit/rollback 後才放行，
    屆時讀到的是已扣減的最新 stock → 正確 raise ``InsufficientStock``。WAL 仍允許並發讀，
    只序列化寫入，符合 single-farm 單機部署的正確性需求。

    （PostgreSQL 部署改用真實 ``SELECT FOR UPDATE`` row-lock，見 WMOM-20260509-F6。）
    """
    conn.exec_driver_sql("BEGIN IMMEDIATE")


def _get_engine(db_path: str) -> Engine:
    """Cache engine per absolute db_path 避免每次 API call 重建。

    第一次建 engine 時 attach connect listener 主動設 WAL + busy_timeout + autocommit，
    並 attach begin listener 改發 ``BEGIN IMMEDIATE`` 序列化寫入（避免並發 read-modify-write
    lost update），避免 workflow standalone 場景下 DB 還在 DELETE journal mode 撞鎖。
    """
    abs_path = str(Path(db_path).resolve())
    with _ENGINE_LOCK:
        eng = _ENGINE_CACHE.get(abs_path)
        if eng is None:
            eng = create_engine(
                f"sqlite:///{abs_path}",
                future=True,
                connect_args={"check_same_thread": False, "timeout": 5.0},
            )
            sa_event.listen(eng, "connect", _set_sqlite_pragmas)
            sa_event.listen(eng, "begin", _begin_immediate)
            _ENGINE_CACHE[abs_path] = eng
        return eng


def clear_engine_cache_for_test() -> None:
    """For test use only — 清掉 engine cache + schema-initialized 記錄。"""
    with _ENGINE_LOCK:
        for eng in _ENGINE_CACHE.values():
            eng.dispose()
        _ENGINE_CACHE.clear()
        _SCHEMA_INITIALIZED.clear()


# 兼容舊名（既有 tests 用了 _clear_..._test）— 內部 alias 不擴大公開面
_clear_engine_cache_for_test = clear_engine_cache_for_test


def get_repository(db_path: str) -> "WorkOrderRepository":
    """Factory — 拿一個 repository instance（每次 API call 用完即丟）。

    DB schema 用 ``create_all()`` 建立，但只在第一次見到該 db_path 時跑（fix #7）；
    之後同 db_path 跳過 SELECT-IF-EXISTS 開銷。
    """
    engine = _get_engine(db_path)
    abs_path = str(Path(db_path).resolve())
    with _ENGINE_LOCK:
        if abs_path not in _SCHEMA_INITIALIZED:
            Base.metadata.create_all(engine)
            _migrate_completion_columns(engine)
            _SCHEMA_INITIALIZED.add(abs_path)
    return WorkOrderRepository(engine)


def _migrate_completion_columns(engine: Engine) -> None:
    """補既有 wmom_work_orders 表缺的完工佐證欄（WMOM-20260608-02）。

    ``create_all`` 不會對既有表加欄；既有 farm DB 的 wmom_work_orders 沒有
    ``completion_signature`` / ``completion_photos`` 會在 SELECT 全欄時報
    「no such column」。用 SQLite ``ALTER TABLE ADD COLUMN``（冪等：先查
    PRAGMA table_info）補上，避免破壞既有部署。
    """
    with engine.begin() as conn:
        existing = {
            row[1]  # PRAGMA table_info: (cid, name, type, ...)
            for row in conn.exec_driver_sql("PRAGMA table_info(wmom_work_orders)").fetchall()
        }
        for col in ("completion_signature", "completion_photos"):
            if col not in existing:
                try:
                    conn.exec_driver_sql(
                        f"ALTER TABLE wmom_work_orders ADD COLUMN {col} TEXT"
                    )
                except OperationalError:
                    # multi-worker 啟動競態：另一 worker 已搶先加同欄（duplicate column）
                    # 或瞬時 lock。欄最終會存在 → 安全吞掉，不讓 worker 啟動失敗。
                    pass


def _load_completion_photos(raw: str | None) -> list[str]:
    """把 DB 存的 photos JSON array 字串還原為 list[str]（壞 / 空 → []）。"""
    if not raw:
        return []
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return []
    # 防呆：只收 list of str（非預期結構回空，不讓壞資料污染 domain）。
    if isinstance(loaded, list):
        return [str(x) for x in loaded]
    return []


# ─────────────────────────────────────────────────────────────────────────
# Helpers — UUID round-trip / business key / farm_id short
# ─────────────────────────────────────────────────────────────────────────


# Backward-compat aliases — review fix #5：helpers 抽到 _helpers.py 後保留舊名
# 給既有 caller import 不破。新 code 應直接用 _helpers 版本。
_ensure_utc = ensure_utc
_uuid_to_str = uuid_to_str
_str_to_uuid = str_to_uuid
_json_safe = json_safe


def _farm_id_short(farm_id: str) -> str:
    """從 farm_id 取短碼：英數字保留前 5 碼；中文 farm_id 走 hash。

    ``台中港曲風場`` → ``H{5位 hash}``；``offshore_001`` → ``OFFSH``。
    """
    ascii_chars = re.sub(r"[^a-zA-Z0-9]", "", farm_id).upper()
    if ascii_chars:
        return ascii_chars[:5]
    digest = hashlib.md5(farm_id.encode("utf-8")).hexdigest().upper()
    return f"H{digest[:5]}"


# ─────────────────────────────────────────────────────────────────────────
# Repository
# ─────────────────────────────────────────────────────────────────────────


class WorkOrderRepository:
    """SQLAlchemy 2.0 repository for wmom_work_orders + progress notes + event log。"""

    MAX_OPEN_PER_TURBINE = 3  # walkthrough Q3：可由 farm config 覆寫，目前 hard-code

    def __init__(self, engine: Engine):
        self._engine = engine
        self._sessionmaker = sessionmaker(engine, expire_on_commit=False, future=True)

    # ── CRUD ────────────────────────────────────────────────────────

    def create(
        self,
        *,
        farm_id: str,
        turbine_id: str,
        type: WorkOrderType,
        title: str,
        description: str,
        priority: Priority = Priority.NORMAL,
        source_alarm_id: UUID | None = None,
        source_alarm_code: str | None = None,
        assignee_id: UUID | None = None,
        crew_size: int = 1,
        estimated_hours: float | None = None,
        created_by: UUID | None = None,
    ) -> WorkOrder:
        """建立新工單（status=DRAFT）。

        強制 multi-WO constraint（walkthrough Q3）：
        - 同一台風機 OPEN 工單 ≤ 3 → 否則 ``BusinessRuleViolation``
        - 同一台風機同 ``source_alarm_code`` 不可有 OPEN 工單 → 否則 ``BusinessRuleViolation``
        - 不同 alarm_code 才能多張 OPEN

        對 ``business_key`` 並發碰撞（兩個 request 同 millisecond 同月各算 NN+1）做最多
        一次 retry（fix #1）— 若仍碰撞 raise ``BusinessRuleViolation`` 給 caller 看到 409。
        """
        last_err: Exception | None = None
        for _attempt in range(2):  # max 1 retry on business_key collision
            try:
                return self._create_once(
                    farm_id=farm_id,
                    turbine_id=turbine_id,
                    type=type,
                    title=title,
                    description=description,
                    priority=priority,
                    source_alarm_id=source_alarm_id,
                    source_alarm_code=source_alarm_code,
                    assignee_id=assignee_id,
                    crew_size=crew_size,
                    estimated_hours=estimated_hours,
                    created_by=created_by,
                )
            except IntegrityError as e:
                last_err = e
                # business_key UNIQUE 撞 → retry 一次取下一個 NN
                if "business_key" not in str(e).lower():
                    raise
                continue
        # 第二次仍撞 — 拋業務錯誤給 caller
        raise BusinessRuleViolation(
            f"business_key collision after retry, please retry: {last_err}"
        )

    def _create_once(
        self,
        *,
        farm_id: str,
        turbine_id: str,
        type: WorkOrderType,
        title: str,
        description: str,
        priority: Priority,
        source_alarm_id: UUID | None,
        source_alarm_code: str | None,
        assignee_id: UUID | None,
        crew_size: int,
        estimated_hours: float | None,
        created_by: UUID | None,
    ) -> WorkOrder:
        with self._sessionmaker() as sess:
            self._enforce_multi_wo_constraint(
                sess, farm_id=farm_id, turbine_id=turbine_id,
                source_alarm_code=source_alarm_code,
            )
            wo_id = uuid4()
            business_key = self._next_business_key(sess, farm_id)
            now = _utc_now()
            orm = WorkOrderORM(
                id=str(wo_id),
                business_key=business_key,
                farm_id=farm_id,
                turbine_id=turbine_id,
                type=type.value,
                status=WorkOrderStatus.DRAFT.value,
                priority=priority.value,
                title=title,
                description=description,
                source_alarm_id=_uuid_to_str(source_alarm_id),
                source_alarm_code=source_alarm_code,
                assignee_id=_uuid_to_str(assignee_id),
                crew_size=crew_size,
                estimated_hours=estimated_hours,
                followup_kind=FollowupKind.NONE.value,
                created_at=now,
                created_by=_uuid_to_str(created_by),
                updated_at=now,
            )
            sess.add(orm)
            self._append_event_log(
                sess, work_order_id=str(wo_id),
                event_type="created", from_status=None, to_status="draft",
                actor_id=created_by,
                payload={"business_key": business_key, "type": type.value},
                occurred_at=now,
            )
            sess.commit()
            sess.refresh(orm)
            return self._to_domain(orm)

    def get(self, work_order_id: UUID) -> WorkOrder | None:
        with self._sessionmaker() as sess:
            orm = sess.get(WorkOrderORM, str(work_order_id))
            return self._to_domain(orm) if orm else None

    def set_signoff_chain_id(self, work_order_id: UUID, chain_id: UUID) -> None:
        """Wire signoff chain id 進工單（給 approval router 在建 chain 後 backlink 用）。

        不走 state machine（純 metadata link，不影響 status / business rule）。
        WMOM-20260504-18 整合點。
        """
        with self._sessionmaker() as sess:
            orm = sess.get(WorkOrderORM, str(work_order_id))
            if orm is None:
                raise LookupError(f"work_order {work_order_id} not found")
            orm.signoff_chain_id = str(chain_id)
            orm.updated_at = _utc_now()
            sess.commit()

    def get_by_business_key(self, business_key: str) -> WorkOrder | None:
        with self._sessionmaker() as sess:
            stmt = select(WorkOrderORM).where(WorkOrderORM.business_key == business_key)
            orm = sess.execute(stmt).scalar_one_or_none()
            return self._to_domain(orm) if orm else None

    def list(
        self,
        *,
        farm_id: str | None = None,
        turbine_id: str | None = None,
        status: WorkOrderStatus | None = None,
        assignee_id: UUID | None = None,
        only_open: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[WorkOrder], int]:
        """Returns (items, total) — total 是真實 DB count（不受 limit/offset 截斷）。

        Review fix #11：加 ``offset`` 支援分頁（前端能跳第 N 頁）。
        WMOM-20260608-02：加 ``assignee_id`` 過濾，給 ``/field/`` 現場工程師
        看「我的工單」（只列指派給自己的單）。
        """
        with self._sessionmaker() as sess:
            base = select(WorkOrderORM)
            if farm_id is not None:
                base = base.where(WorkOrderORM.farm_id == farm_id)
            if turbine_id is not None:
                base = base.where(WorkOrderORM.turbine_id == turbine_id)
            if status is not None:
                base = base.where(WorkOrderORM.status == status.value)
            if assignee_id is not None:
                base = base.where(WorkOrderORM.assignee_id == uuid_to_str(assignee_id))
            if only_open:
                base = base.where(
                    WorkOrderORM.status.in_([s.value for s in open_states()])
                )
            total_stmt = select(func.count()).select_from(base.subquery())
            total = int(sess.execute(total_stmt).scalar_one())
            page_stmt = (
                base.order_by(WorkOrderORM.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            items = [self._to_domain(o) for o in sess.execute(page_stmt).scalars()]
            return items, total

    # ── State machine wrapping ──────────────────────────────────────

    def transition(
        self,
        work_order_id: UUID,
        action: str,
        *,
        actor_id: UUID | None = None,
        **kwargs: Any,
    ) -> WorkOrder:
        """跑 domain state machine + persist + 寫 event log。

        Raises:
            ``InvalidTransition``: state machine 拒絕（404 → frontend 422 / 409）
            ``LookupError``: work order 不存在
        """
        with self._sessionmaker() as sess:
            orm = sess.get(WorkOrderORM, str(work_order_id))
            if orm is None:
                raise LookupError(f"work_order {work_order_id} not found")

            wo = self._to_domain(orm)
            from_status = wo.status

            # 跑 state machine — 失敗 raise InvalidTransition，不 persist
            WorkOrderStateMachine.transition(wo, action, actor_id=actor_id, **kwargs)

            # 把改動寫回 ORM
            self._apply_domain_to_orm(wo, orm)

            # 新 progress note：直接從 kwargs 重建（不依賴 wo.progress_notes[-1]）。
            # state machine 已驗過 actor_id + note 非空。fix #6.
            if action == "update_progress":
                assert actor_id is not None  # state machine guard 已驗
                sess.add(ProgressNoteORM(
                    work_order_id=str(wo.id),
                    timestamp=wo.updated_at,
                    actor_id=str(actor_id),
                    note=kwargs["note"].strip(),
                ))

            self._append_event_log(
                sess, work_order_id=str(wo.id),
                event_type=action,
                from_status=from_status.value,
                to_status=wo.status.value,
                actor_id=actor_id,
                payload=kwargs,
                occurred_at=wo.updated_at,
            )
            sess.commit()
            sess.refresh(orm)
            return self._to_domain(orm)

    # ── Constraint helpers ──────────────────────────────────────────

    def count_open_for_turbine(self, farm_id: str, turbine_id: str) -> int:
        with self._sessionmaker() as sess:
            return self._count_open_for_turbine(sess, farm_id, turbine_id)

    def _count_open_for_turbine(self, sess: Session, farm_id: str, turbine_id: str) -> int:
        stmt = select(func.count(WorkOrderORM.id)).where(
            WorkOrderORM.farm_id == farm_id,
            WorkOrderORM.turbine_id == turbine_id,
            WorkOrderORM.status.in_([s.value for s in open_states()]),
        )
        return int(sess.execute(stmt).scalar_one())

    def _find_open_with_alarm_code(
        self, sess: Session, farm_id: str, turbine_id: str, alarm_code: str
    ) -> WorkOrderORM | None:
        stmt = select(WorkOrderORM).where(
            WorkOrderORM.farm_id == farm_id,
            WorkOrderORM.turbine_id == turbine_id,
            WorkOrderORM.source_alarm_code == alarm_code,
            WorkOrderORM.status.in_([s.value for s in open_states()]),
        )
        return sess.execute(stmt).scalar_one_or_none()

    def _enforce_multi_wo_constraint(
        self, sess: Session, *, farm_id: str, turbine_id: str,
        source_alarm_code: str | None,
    ) -> None:
        n_open = self._count_open_for_turbine(sess, farm_id, turbine_id)
        if n_open >= self.MAX_OPEN_PER_TURBINE:
            raise BusinessRuleViolation(
                f"turbine {turbine_id} already has {n_open} OPEN work orders "
                f"(max {self.MAX_OPEN_PER_TURBINE})"
            )
        if source_alarm_code:
            existing = self._find_open_with_alarm_code(
                sess, farm_id, turbine_id, source_alarm_code
            )
            if existing is not None:
                raise BusinessRuleViolation(
                    f"turbine {turbine_id} already has an OPEN work order for "
                    f"alarm_code={source_alarm_code!r} "
                    f"(business_key={existing.business_key})"
                )

    # ── Business key generation ─────────────────────────────────────

    def _next_business_key(self, sess: Session, farm_id: str) -> str:
        """Generate next ``WO-{short}-{YYYYMM}-{NNN}`` for farm in current month.

        Review fix #3：用 ``MAX(business_key)`` 取最後一筆的 NN segment 而非 ``COUNT``，
        避免 DB DELETE 導致 count < max 撞 unique。同時改 ``03d`` 三位零填補（M3 客戶
        每月可能 ≥ 100 張單，``02d`` 從第 100 張起變 3-char 數字，破壞格式一致性）。
        """
        short = _farm_id_short(farm_id)
        ym = datetime.now(tz=timezone.utc).strftime("%Y%m")
        prefix = f"WO-{short}-{ym}-"
        stmt = (
            select(func.max(WorkOrderORM.business_key))
            .where(WorkOrderORM.farm_id == farm_id)
            .where(WorkOrderORM.business_key.like(f"{prefix}%"))
        )
        last_key: str | None = sess.execute(stmt).scalar_one_or_none()
        if last_key is None:
            n = 0
        else:
            try:
                n = int(last_key[len(prefix):])
            except ValueError:
                # 萬一有 legacy 格式 NN segment 不是純數字 → fallback to COUNT
                count_stmt = (
                    select(func.count(WorkOrderORM.id))
                    .where(WorkOrderORM.farm_id == farm_id)
                    .where(WorkOrderORM.business_key.like(f"{prefix}%"))
                )
                n = int(sess.execute(count_stmt).scalar_one())
        return f"{prefix}{n + 1:03d}"

    # ── Event log ───────────────────────────────────────────────────

    def _append_event_log(
        self, sess: Session, *,
        work_order_id: str,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        actor_id: UUID | None,
        payload: dict[str, Any],
        occurred_at: datetime,
    ) -> None:
        # payload 內可能含 enum / UUID / datetime — 統一序列化成 JSON-friendly
        sess.add(WorkOrderEventLogORM(
            work_order_id=work_order_id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            actor_id=_uuid_to_str(actor_id),
            payload_json=json.dumps(payload, default=_json_safe, ensure_ascii=False),
            occurred_at=occurred_at,
        ))

    # ── ORM ↔ domain conversion ─────────────────────────────────────

    @staticmethod
    def _to_domain(orm: WorkOrderORM) -> WorkOrder:
        # SQLite roundtrip 會丟 tzinfo — 讀回時 attach UTC（見 _ensure_utc 註）
        wo = WorkOrder(
            farm_id=orm.farm_id,
            turbine_id=orm.turbine_id,
            type=WorkOrderType(orm.type),
            title=orm.title,
            description=orm.description,
            business_key=orm.business_key,
            id=UUID(orm.id),
            status=WorkOrderStatus(orm.status),
            priority=Priority(orm.priority),
            source_alarm_id=_str_to_uuid(orm.source_alarm_id),
            source_alarm_code=orm.source_alarm_code,
            assignee_id=_str_to_uuid(orm.assignee_id),
            crew_size=orm.crew_size,
            estimated_hours=orm.estimated_hours,
            dispatched_at=_ensure_utc(orm.dispatched_at),
            dispatched_by=_str_to_uuid(orm.dispatched_by),
            vessel_id=_str_to_uuid(orm.vessel_id),
            weather_window_id=_str_to_uuid(orm.weather_window_id),
            logistic_hours=orm.logistic_hours,
            started_at=_ensure_utc(orm.started_at),
            finished_at=_ensure_utc(orm.finished_at),
            actual_hours=orm.actual_hours,
            work_summary=orm.work_summary,
            unfinished_items=orm.unfinished_items,
            followup_kind=FollowupKind(orm.followup_kind),
            followup_note=orm.followup_note,
            completion_signature=orm.completion_signature,
            completion_photos=_load_completion_photos(orm.completion_photos),
            material_request_ids=[],  # M4 補
            signoff_chain_id=_str_to_uuid(orm.signoff_chain_id),
            closed_at=_ensure_utc(orm.closed_at),
            cancelled_at=_ensure_utc(orm.cancelled_at),
            cancel_reason=orm.cancel_reason,
            rejected_at=_ensure_utc(orm.rejected_at),
            reject_reason=orm.reject_reason,
            reopened_at=_ensure_utc(orm.reopened_at),
            reopen_reason=orm.reopen_reason,
            created_at=_ensure_utc(orm.created_at),  # type: ignore[arg-type]
            created_by=_str_to_uuid(orm.created_by),
            updated_at=_ensure_utc(orm.updated_at),  # type: ignore[arg-type]
        )
        # progress_notes 從 ORM relationship 拉
        wo.progress_notes = [
            ProgressNote(
                timestamp=_ensure_utc(p.timestamp),  # type: ignore[arg-type]
                actor_id=UUID(p.actor_id),
                note=p.note,
            )
            for p in orm.progress_notes
        ]
        return wo

    @staticmethod
    def _assert_utc(name: str, dt: datetime | None) -> None:
        """Write 路徑 UTC validation — delegate 給 ``_helpers.assert_utc``。

        Review fix #5：原本兩個 repository 各複製此函式，現統一抽到 _helpers.py。
        保留 staticmethod 是讓 test 用 ``WorkOrderRepository._assert_utc(...)`` 不破。
        """
        _assert_utc_helper(name, dt)

    @staticmethod
    def _apply_domain_to_orm(wo: WorkOrder, orm: WorkOrderORM) -> None:
        """把 dataclass 改動 flush 回 ORM（不含 progress_notes — caller 端額外 add）。

        所有 datetime 欄位先過 ``_assert_utc`` 確認是 UTC-aware（fix #2）。
        ``id / farm_id / turbine_id / type`` 為「建立後不可改」欄位，本函式刻意不寫
        （保護 contract，避免 silent identity update — nice-to-have #2）。
        """
        # 寫前 timestamp validation
        WorkOrderRepository._assert_utc("dispatched_at", wo.dispatched_at)
        WorkOrderRepository._assert_utc("started_at", wo.started_at)
        WorkOrderRepository._assert_utc("finished_at", wo.finished_at)
        WorkOrderRepository._assert_utc("closed_at", wo.closed_at)
        WorkOrderRepository._assert_utc("cancelled_at", wo.cancelled_at)
        WorkOrderRepository._assert_utc("rejected_at", wo.rejected_at)
        WorkOrderRepository._assert_utc("reopened_at", wo.reopened_at)
        WorkOrderRepository._assert_utc("updated_at", wo.updated_at)

        orm.status = wo.status.value
        orm.priority = wo.priority.value
        orm.type = wo.type.value
        orm.assignee_id = _uuid_to_str(wo.assignee_id)
        orm.crew_size = wo.crew_size
        orm.estimated_hours = wo.estimated_hours
        orm.dispatched_at = wo.dispatched_at
        orm.dispatched_by = _uuid_to_str(wo.dispatched_by)
        orm.vessel_id = _uuid_to_str(wo.vessel_id)
        orm.weather_window_id = _uuid_to_str(wo.weather_window_id)
        orm.logistic_hours = wo.logistic_hours
        orm.started_at = wo.started_at
        orm.finished_at = wo.finished_at
        orm.actual_hours = wo.actual_hours
        orm.work_summary = wo.work_summary
        orm.unfinished_items = wo.unfinished_items
        orm.followup_kind = wo.followup_kind.value
        orm.followup_note = wo.followup_note
        orm.completion_signature = wo.completion_signature
        # photos 以 JSON array 字串存；空清單存 None（與「未拍照」一致，省空間）。
        orm.completion_photos = (
            json.dumps(wo.completion_photos, ensure_ascii=False)
            if wo.completion_photos
            else None
        )
        orm.signoff_chain_id = _uuid_to_str(wo.signoff_chain_id)
        orm.closed_at = wo.closed_at
        orm.cancelled_at = wo.cancelled_at
        orm.cancel_reason = wo.cancel_reason
        orm.rejected_at = wo.rejected_at
        orm.reject_reason = wo.reject_reason
        orm.reopened_at = wo.reopened_at
        orm.reopen_reason = wo.reopen_reason
        orm.updated_at = wo.updated_at


# review fix #5：原 _json_safe 移到 _helpers.py 統一管理。本檔頂部已 alias
# `_json_safe = json_safe` 給內部 import 用。
