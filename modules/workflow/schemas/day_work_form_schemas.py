"""Pydantic request / response schemas for day-work-form router（WMOM-20260505-21）。

設計沿襲 ``inspection_schemas`` 模式：Response 用 ``ConfigDict(from_attributes=True)``
直接對映 dataclass；str-Enum / UUID / datetime 由 pydantic v2 預設處理。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from modules.workflow.domain.day_work_form import ACTIVITY_REQUIRED_FIELDS, ActivityKind


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

    必填欄位依 ``kind`` 不同（見 domain ``ACTIVITY_REQUIRED_FIELDS``，schema 與
    domain 共用同一份表——單一真實來源），這裡先做一層 HTTP 層檢查提早給 422
    （domain ``validate_activity_entry`` 仍是最終防線，repository 直接呼叫端一樣
    受保護）。

    ``employee_id`` 過渡期（``WMOM_AUTH_ENFORCE=false``）可由 body 帶，同
    ``CreateDayWorkFormRequest``；enforce 開啟後一律由已驗證 token 決定，body
    值被忽略。router 會再比對此身分與日誌本人是否一致（不支援代填），見
    ``day_work_form_router.append_day_work_form_activity`` docstring。

    非本 ``kind`` 相關的欄位（例如 ``kind=patrol`` 卻夾帶 ``wo_id``）不會被清空，
    會原樣持久化；下游讀取（報表 / cost ledger）須自行以 ``kind`` 過濾，不可假設
    其餘欄位為 ``None``。
    """

    kind: ActivityKind
    wo_id: Optional[UUID] = None
    item_id: Optional[UUID] = None
    result: Optional[str] = None
    area: Optional[str] = None
    topic: Optional[str] = None
    note: str = ""
    employee_id: Optional[UUID] = None

    @model_validator(mode="after")
    def _check_required_fields(self) -> "AppendActivityRequest":
        missing = [
            name
            for name in ACTIVITY_REQUIRED_FIELDS[self.kind]
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
