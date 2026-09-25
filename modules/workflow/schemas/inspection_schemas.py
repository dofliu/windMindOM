"""Pydantic request / response schemas for inspection-schedule router（WMOM-20260505-22）。

設計沿襲 ``work_order_schemas`` 模式：Response 用 ``ConfigDict(from_attributes=True)``
直接對映 dataclass；str-Enum / UUID / datetime 由 pydantic v2 預設處理。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from modules.workflow.domain import Recurrence


# ─────────────────────────────────────────────────────────────────────────
# Request bodies
# ─────────────────────────────────────────────────────────────────────────


class CreateInspectionScheduleRequest(BaseModel):
    """``POST /api/workflow/inspection-schedules`` body — 建立定檢計畫。

    ``interval_days`` 只有 ``recurrence=custom_days`` 時必填（domain 層
    ``recurrence_interval_days`` 會驗證，這裡先做一層 HTTP 層檢查提早給 422，
    訊息更明確好懂）。``first_due_at`` 未帶 → repository 預設「現在起算一個週期後」。
    """

    farm_id: str = Field(min_length=1, max_length=128)
    turbine_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=256)
    description: str = ""
    recurrence: Recurrence
    interval_days: Optional[int] = Field(default=None, gt=0, le=3650)
    first_due_at: Optional[datetime] = None
    created_by: Optional[UUID] = None

    @model_validator(mode="after")
    def _check_custom_days_interval(self) -> "CreateInspectionScheduleRequest":
        if self.recurrence is Recurrence.CUSTOM_DAYS and self.interval_days is None:
            raise ValueError("recurrence=custom_days 必須帶 interval_days")
        return self


class UpdateInspectionScheduleRequest(BaseModel):
    """``PATCH /api/workflow/inspection-schedules/{id}`` — 改計畫內容（不含到期時間）。

    全部選填，未帶的欄位維持原值（repository 層 ``update_metadata`` 逐欄判斷）。
    """

    title: Optional[str] = Field(default=None, min_length=1, max_length=256)
    description: Optional[str] = None
    recurrence: Optional[Recurrence] = None
    interval_days: Optional[int] = Field(default=None, gt=0, le=3650)


# ─────────────────────────────────────────────────────────────────────────
# Response
# ─────────────────────────────────────────────────────────────────────────


class InspectionScheduleResponse(BaseModel):
    """完整定檢計畫視圖（list / detail / CRUD 後共用）。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    farm_id: str
    turbine_id: str
    title: str
    description: str
    recurrence: Recurrence
    interval_days: Optional[int] = None
    next_due_at: datetime
    active: bool = True

    last_spawned_at: Optional[datetime] = None
    last_spawned_work_order_id: Optional[UUID] = None

    created_at: datetime
    created_by: Optional[UUID] = None
    updated_at: datetime


class InspectionScheduleListResponse(BaseModel):
    """``GET /api/workflow/inspection-schedules`` 回應 — 帶 total + items。"""

    total: int
    items: list[InspectionScheduleResponse]


class SpawnedInspectionResponse(BaseModel):
    """``run-scheduler`` 回應內單筆 spawn 結果。"""

    model_config = ConfigDict(from_attributes=True)

    schedule_id: UUID
    work_order_id: UUID
    turbine_id: str
    next_due_at: datetime


class RunSchedulerResponse(BaseModel):
    """``POST /api/workflow/inspection-schedules/run-scheduler`` 回應。"""

    spawned: list[SpawnedInspectionResponse]
