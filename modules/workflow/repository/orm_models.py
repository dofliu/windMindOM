"""SQLAlchemy 2.0 ORM models for workflow module（WMOM-20260504-17）。

設計準則：
- 與 ``modules/workflow/domain/work_order.py`` 的 dataclass **欄位一一對應**，
  名稱完全相同；轉換層放在 ``work_order_repository.py``
- UUID 存成 string（SQLite 沒 native UUID type；PostgreSQL 將來再改 UUID type）
- Enum 存成 ``str``（已是 ``str`` Enum，``WorkOrderStatus("draft").value`` 直接寫入）
- Timestamps 存成 ISO8601 字串（SQLite ``TEXT``）— ``DateTime`` type 在 SQLite 仍走
  ISO8601，無 native datetime 型別，但 SQLAlchemy 處理 round-trip 時會帶 tzinfo
- Multi-WO constraint（一台風機 ≤ 3 OPEN + 不同 alarm_code 才可多張）由 repository
  層在 application-level 強制（DB unique index 在 SQLite 對 partial index 支援不一致，
  保險起見跳過 DB-level，全靠 repository check）
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Workflow ORM 共用 base — 與 monitoring (raw sqlite3) 並存於同一 DB file。"""


# ─────────────────────────────────────────────────────────────────────────
# work_orders
# ─────────────────────────────────────────────────────────────────────────


class WorkOrderORM(Base):
    """ORM mapping 對齊 ``modules.workflow.domain.work_order.WorkOrder`` dataclass。

    一台風機 ≤ 3 OPEN + 不同 alarm_code unique 由 repository 層強制（見
    ``WorkOrderRepository.create``），不放 DB-level constraint 以避免 SQLite
    partial index 跨版本行為差異。
    """

    __tablename__ = "work_orders"

    # ── identity ─────────────────────────────────────────────────────
    id: Mapped[str] = mapped_column(String(36), primary_key=True)            # UUID str
    business_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # ── core ─────────────────────────────────────────────────────────
    farm_id: Mapped[str] = mapped_column(String(128), index=True)
    turbine_id: Mapped[str] = mapped_column(String(64), index=True)
    type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    priority: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text)

    # ── 來源 ─────────────────────────────────────────────────────────
    source_alarm_id: Mapped[Optional[str]] = mapped_column(String(36))
    source_alarm_code: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    # ── 派工 ─────────────────────────────────────────────────────────
    assignee_id: Mapped[Optional[str]] = mapped_column(String(36))
    crew_size: Mapped[int] = mapped_column(Integer, default=1)
    estimated_hours: Mapped[Optional[float]] = mapped_column()
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    dispatched_by: Mapped[Optional[str]] = mapped_column(String(36))

    # ── offshore ─────────────────────────────────────────────────────
    vessel_id: Mapped[Optional[str]] = mapped_column(String(36))
    weather_window_id: Mapped[Optional[str]] = mapped_column(String(36))
    logistic_hours: Mapped[Optional[float]] = mapped_column()

    # ── 進行 ─────────────────────────────────────────────────────────
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # ── 完工 ─────────────────────────────────────────────────────────
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    actual_hours: Mapped[Optional[float]] = mapped_column()
    work_summary: Mapped[Optional[str]] = mapped_column(Text)
    unfinished_items: Mapped[Optional[str]] = mapped_column(Text)
    followup_kind: Mapped[str] = mapped_column(String(32), default="none")
    followup_note: Mapped[Optional[str]] = mapped_column(Text)

    # ── 簽核 ─────────────────────────────────────────────────────────
    signoff_chain_id: Mapped[Optional[str]] = mapped_column(String(36))

    # ── 取消 / 駁回 / 結案 / 重開 ────────────────────────────────────
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[Optional[str]] = mapped_column(Text)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reject_reason: Mapped[Optional[str]] = mapped_column(Text)
    reopened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reopen_reason: Mapped[Optional[str]] = mapped_column(Text)

    # ── audit ────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[Optional[str]] = mapped_column(String(36))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # ── relationships ────────────────────────────────────────────────
    progress_notes: Mapped[list["ProgressNoteORM"]] = relationship(
        back_populates="work_order",
        cascade="all, delete-orphan",
        order_by="ProgressNoteORM.timestamp",
    )
    event_log: Mapped[list["WorkOrderEventLogORM"]] = relationship(
        back_populates="work_order",
        cascade="all, delete-orphan",
        order_by="WorkOrderEventLogORM.occurred_at",
    )

    # 索引：常用查詢 — list by farm + status + turbine
    __table_args__ = (
        Index(
            "ix_work_orders_farm_status_turbine",
            "farm_id", "status", "turbine_id",
        ),
        Index(
            "ix_work_orders_farm_turbine_alarm",
            "farm_id", "turbine_id", "source_alarm_code",
        ),
    )


# ─────────────────────────────────────────────────────────────────────────
# progress notes
# ─────────────────────────────────────────────────────────────────────────


class ProgressNoteORM(Base):
    """維修進行中員工多次更新（取代 etech 原地 PUT 覆寫）。"""

    __tablename__ = "work_order_progress_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("work_orders.id", ondelete="CASCADE"), index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[str] = mapped_column(String(36))
    note: Mapped[str] = mapped_column(Text)

    work_order: Mapped["WorkOrderORM"] = relationship(back_populates="progress_notes")


# ─────────────────────────────────────────────────────────────────────────
# event log（取代 etech allForm ad-hoc audit）
# ─────────────────────────────────────────────────────────────────────────


class WorkOrderEventLogORM(Base):
    """≡ DN-01 §2.4 WorkOrderEventLog — state transition + actor + payload audit。"""

    __tablename__ = "work_order_event_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("work_orders.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64))         # "created" | "dispatched" | ...
    from_status: Mapped[Optional[str]] = mapped_column(String(32))
    to_status: Mapped[Optional[str]] = mapped_column(String(32))
    actor_id: Mapped[Optional[str]] = mapped_column(String(36))
    payload_json: Mapped[str] = mapped_column(Text, default="{}")  # JSON-serialised dict
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    work_order: Mapped["WorkOrderORM"] = relationship(back_populates="event_log")


# ─────────────────────────────────────────────────────────────────────────
# Approval signoff（WMOM-20260504-18 / DN-02）
# ─────────────────────────────────────────────────────────────────────────


class SignoffChainORM(Base):
    """≡ DN-02 SignoffChain — 整個簽核流程實體。"""

    __tablename__ = "signoff_chains"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)        # UUID str
    subject_type: Mapped[str] = mapped_column(String(32), index=True)    # "work_order" | "material_request"
    subject_id: Mapped[str] = mapped_column(String(36), index=True)
    farm_id: Mapped[str] = mapped_column(String(128), index=True)
    levels_json: Mapped[str] = mapped_column(Text)                       # JSON list of SignoffLevel.value
    current_level_index: Mapped[int] = mapped_column(Integer, default=0)
    overall_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejected_at_level: Mapped[Optional[str]] = mapped_column(String(32))
    rejected_reason: Mapped[Optional[str]] = mapped_column(Text)

    steps: Mapped[list["SignoffStepORM"]] = relationship(
        back_populates="chain",
        cascade="all, delete-orphan",
        order_by="SignoffStepORM.sequence",
    )
    history: Mapped[list["SignoffHistoryORM"]] = relationship(
        back_populates="chain",
        cascade="all, delete-orphan",
        order_by="SignoffHistoryORM.id",
    )


class SignoffStepORM(Base):
    """≡ DN-02 SignoffStep — chain 內每個 level 對應一筆。"""

    __tablename__ = "signoff_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)        # UUID str
    chain_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("signoff_chains.id", ondelete="CASCADE"), index=True
    )
    level: Mapped[str] = mapped_column(String(32), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    parallel_group_id: Mapped[Optional[str]] = mapped_column(String(36))
    assignee_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[Optional[str]] = mapped_column(String(36))
    comment: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    chain: Mapped["SignoffChainORM"] = relationship(back_populates="steps")

    __table_args__ = (
        Index(
            "ix_signoff_steps_chain_status",
            "chain_id", "status",
        ),
    )


class SignoffHistoryORM(Base):
    """≡ DN-02 SignoffHistoryEntry — 完整事件 log（給 KPI 用）。"""

    __tablename__ = "signoff_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chain_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("signoff_chains.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[Optional[str]] = mapped_column(String(36))     # None = chain-level event
    event_type: Mapped[str] = mapped_column(String(64))            # "chain_created" | "step_approved" | ...
    actor_id: Mapped[Optional[str]] = mapped_column(String(36))
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    chain: Mapped["SignoffChainORM"] = relationship(back_populates="history")
