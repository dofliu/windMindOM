"""Pydantic request / response schemas for day-work-form router（WMOM-20260505-21）。

設計沿襲 ``inspection_schemas`` 模式：Response 用 ``ConfigDict(from_attributes=True)``
直接對映 dataclass；str-Enum / UUID / datetime 由 pydantic v2 預設處理。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from modules.workflow.domain.day_work_form import ActivityKind

# 每種 kind 對應的必填欄位（與 domain ``_REQUIRED_FIELDS`` 刻意各自維護一份——
# schema 層是提早給明確 422 訊息的第一道關卡，domain ``validate_activity_entry``
# 才是最終防線，兩層各自獨立驗證同一組規則，同 ``inspection_schemas`` 的
# custom_days 檢查慣例）。
_REQUIRED_FIELDS: dict[ActivityKind, tuple[str, ...]] = {
    ActivityKind.COMPLETED_WO: ("wo_id",),
    ActivityKind.INSPECTION_ITEM: ("item_id", "result"),
    ActivityKind.PATROL: ("area",),
    ActivityKind.TRAINING: ("topic",),
}


# ─────────────────────────────────────────────────────────────────────────
# Request bodies
# ─────────────────────────────────────────────────────────────────────────


class CreateDayWorkFormRequest(BaseModel):
    """``POST /api/workflow/day-work-forms`` body — 取得或建立當天日誌（idempotent）。

    ``employee_id`` 過渡期（``WMOM_AUTH_ENFORCE=false``）可由 body 帶；enforce 開啟後
    一律由已驗證 token 決定（router ``_employee_uuid`` 雙模式解析，同其他 workflow
    router 慣例），body 值被忽略。
    """

    farm_id: str = Field(min_length=1, max_length=128)
    work_date: date
    employee_id: Optional[UUID] = None


class AppendActivityRequest(BaseModel):
    """``POST /api/workflow/day-work-forms/{id}/activities`` body — 新增一筆活動。

    必填欄位依 ``kind`` 不同（見 domain ``_REQUIRED_FIELDS``），這裡先做一層 HTTP
    層檢查提早給 422（domain ``validate_activity_entry`` 仍是最終防線，repository
    直接呼叫端一樣受保護）。
    """

    kind: ActivityKind
    wo_id: Optional[UUID] = None
    item_id: Optional[UUID] = None
    result: Optional[str] = None
    area: Optional[str] = None
    topic: Optional[str] = None
    note: str = ""

    @model_validator(mode="after")
    def _check_required_fields(self) -> "AppendActivityRequest":
        missing = [
            name
            for name in _REQUIRED_FIELDS[self.kind]
            if getattr(self, name) in (None, "")
        ]
        if missing:
            raise ValueError(
                f"ActivityKind.{self.kind.value} 缺必填欄位: {', '.join(missing)}"
            )
        return self


# ─────────────────────────────────────────────────────────────────────────
# Response
# ─────────────────────────────────────────────────────────────────────────


class ActivityEntryResponse(BaseModel):
    """日誌內單筆活動視圖。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: ActivityKind
    wo_id: Optional[UUID] = None
    item_id: Optional[UUID] = None
    result: Optional[str] = None
    area: Optional[str] = None
    topic: Optional[str] = None
    note: str = ""
    logged_at: datetime


class DayWorkFormResponse(BaseModel):
    """完整日誌視圖（list / detail / CRUD 後共用）。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    farm_id: str
    employee_id: UUID
    work_date: date
    activities: list[ActivityEntryResponse]
    notes: str = ""

    created_at: datetime
    created_by: Optional[UUID] = None
    updated_at: datetime


class DayWorkFormListResponse(BaseModel):
    """``GET /api/workflow/day-work-forms`` 回應 — 帶 total + items。"""

    total: int
    items: list[DayWorkFormResponse]
