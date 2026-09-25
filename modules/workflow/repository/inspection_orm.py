"""InspectionSchedule SQLAlchemy 2.0 ORM model（WMOM-20260505-22）。

設計準則（沿襲 work_order ORM 模式）：
- 與 ``modules/workflow/domain/inspection_schedule.py`` dataclass 欄位一一對應
- UUID 存成 string（SQLite 沒 native UUID）；Enum 存成 string value
- Timestamps ``DateTime(timezone=True)``；SQLite roundtrip 後在 ``_helpers.ensure_utc``
  補回 tzinfo（與 work_order / inventory ORM 一致）
- 與 monitoring (raw sqlite3) + work_order / inventory ORM 共用 ``Base``（同一個
  ``wind_farm.db``）
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .orm_models import Base


class InspectionScheduleORM(Base):
    """≡ DN-01 §3.3 InspectionSchedule — 定檢清單，到期由 scheduler service spawn 工單。"""

    __tablename__ = "wmom_inspection_schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID str

    farm_id: Mapped[str] = mapped_column(String(128), index=True)
    turbine_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text)

    recurrence: Mapped[str] = mapped_column(String(32))
    interval_days: Mapped[Optional[int]] = mapped_column(Integer)
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    last_spawned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_spawned_work_order_id: Mapped[Optional[str]] = mapped_column(String(36))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[Optional[str]] = mapped_column(String(36))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # 常用查詢：scheduler 用 farm_id + active + next_due_at 找到期項；
    # 前端列表用 farm_id + turbine_id 篩單一風機的定檢計畫。
    __table_args__ = (
        Index(
            "ix_inspection_schedules_farm_active_due",
            "farm_id", "active", "next_due_at",
        ),
        Index(
            "ix_inspection_schedules_farm_turbine",
            "farm_id", "turbine_id",
        ),
    )
