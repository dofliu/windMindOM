"""DayWorkForm SQLAlchemy 2.0 ORM model（WMOM-20260505-21）。

設計準則（沿襲 inspection_schedule ORM 模式）：
- 與 ``modules/workflow/domain/day_work_form.py`` dataclass 欄位一一對應
- UUID 存成 string（SQLite 沒 native UUID）
- ``activities`` 用 JSON 字串存（``Text`` 欄位，序列化慣例沿襲
  ``WorkOrderORM.completion_photos`` / ``WorkOrderEventLogORM.payload_json``）——
  一份日誌內活動數量少（單日單人），不需要獨立子表
- ``(farm_id, employee_id, work_date)`` 唯一索引：一天一位員工只有一份日誌
  （walkthrough Q6 natural key）
- Timestamps ``DateTime(timezone=True)``；SQLite roundtrip 後在 ``_helpers.ensure_utc``
  補回 tzinfo（與 work_order / inspection_schedule ORM 一致）
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .orm_models import Base


class DayWorkFormORM(Base):
    """≡ DN-01 §3.3 DayWorkForm — 員工當天工作日誌。"""

    __tablename__ = "wmom_day_work_forms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID str

    farm_id: Mapped[str] = mapped_column(String(128), index=True)
    employee_id: Mapped[str] = mapped_column(String(36), index=True)  # UUID str
    work_date: Mapped[date] = mapped_column(Date, index=True)

    activities_json: Mapped[str] = mapped_column(Text, default="[]")
    notes: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[Optional[str]] = mapped_column(String(36))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # 一天一位員工只有一份日誌（get_or_create 用此約束擋重複建立）。
        Index(
            "uq_day_work_form_employee_date",
            "farm_id", "employee_id", "work_date",
            unique=True,
        ),
        # 前端「今天做了什麼」列表用 farm_id + work_date 範圍查詢。
        Index(
            "ix_day_work_form_farm_date",
            "farm_id", "work_date",
        ),
    )
