"""Pydantic request / response schemas for workflow router（WMOM-20260504-17）。

設計：
- Response 直接從 dataclass 對映；用 ``ConfigDict(from_attributes=True)``
- str-Enum 透明序列化（pydantic v2 直接支援）
- UUID / datetime 由 pydantic v2 預設處理
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# 完工佐證大小上限（WMOM-20260608-02 follow-up / review must#3：防 base64 炸 body+DB）。
# 簽名 PNG 通常 < 100 KB；單張照片 base64 ≈ 原圖 × 1.37，限 ~7.5 MB（容 5–6 MP 手機照）。
_MAX_SIGNATURE_LEN = 3_000_000   # ~2.2 MB base64
_MAX_PHOTO_LEN = 10_000_000      # ~7.5 MB base64/張
_MAX_PHOTO_COUNT = 8             # 一張工單最多 8 張佐證照片
# 單張照片字串（帶長度上限）。
_PhotoDataUrl = Annotated[str, Field(max_length=_MAX_PHOTO_LEN)]

from modules.workflow.domain import (
    FollowupKind,
    Priority,
    WorkOrderStatus,
    WorkOrderType,
)


# ─────────────────────────────────────────────────────────────────────────
# Sub-models
# ─────────────────────────────────────────────────────────────────────────


class ProgressNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    actor_id: UUID
    note: str


# ─────────────────────────────────────────────────────────────────────────
# Request bodies
# ─────────────────────────────────────────────────────────────────────────


class CreateWorkOrderRequest(BaseModel):
    """``POST /api/workflow/work-orders`` body — 建立 DRAFT 工單。"""

    farm_id: str = Field(min_length=1, max_length=128)
    turbine_id: str = Field(min_length=1, max_length=64)
    type: WorkOrderType
    title: str = Field(min_length=1, max_length=256)
    description: str
    priority: Priority = Priority.NORMAL
    source_alarm_id: Optional[UUID] = None
    source_alarm_code: Optional[str] = Field(default=None, max_length=64)
    assignee_id: Optional[UUID] = None
    crew_size: int = Field(default=1, ge=1, le=20)
    estimated_hours: Optional[float] = Field(default=None, ge=0)
    created_by: Optional[UUID] = None


class DispatchRequest(BaseModel):
    """``POST /api/workflow/work-orders/{id}/dispatch`` — 派工。

    actor_id 必填（誰派工的，給 audit）；
    assignee_id 為選填 — 若工單建立時沒指派被派者，可在派工時補帶；
    若兩處皆無，state machine 拒絕（dispatch 必須有被派工的人）。
    """

    actor_id: UUID
    assignee_id: Optional[UUID] = None


class StartWorkRequest(BaseModel):
    """``/start-work`` — 開始維修。

    onshore 場景：``require_weather_window=False`` 即可，``weather_window_id`` 省略。
    offshore 場景：``require_weather_window=True``，必須帶 ``weather_window_id``
    （或工單上已綁定，本欄省略也可）— WMOM-20260510-01 Part D 合併「綁 + 開工」單一步驟。
    """

    require_weather_window: bool = False
    weather_window_id: Optional[UUID] = None


class UpdateProgressRequest(BaseModel):
    """``/update-progress`` — 進行中加 progress note。"""

    actor_id: UUID
    note: str = Field(min_length=1, max_length=2000)


class FinishRequest(BaseModel):
    """``/finish`` — 完工，工單進 AWAITING_SIGNOFF。

    WMOM-20260608-02：加完工佐證（簽名 + 照片）。schema 設 **optional** —
    既有 office finish path 不破壞；「現場工程師完工須簽名+拍照」的強制在
    ``/field/`` 前端那層（DEC-20260608-02）。
    """

    actual_hours: float = Field(ge=0)
    followup_kind: FollowupKind
    work_summary: Optional[str] = Field(default=None, max_length=4000)
    unfinished_items: Optional[str] = Field(default=None, max_length=4000)
    followup_note: Optional[str] = Field(default=None, max_length=4000)
    completion_signature: Optional[str] = Field(
        default=None,
        max_length=_MAX_SIGNATURE_LEN,
        description="簽名 base64 data URL（現場完工帶）",
    )
    completion_photos: list[_PhotoDataUrl] = Field(
        default_factory=list,
        max_length=_MAX_PHOTO_COUNT,
        description="佐證照片 base64 data URL 清單（每張 ≤ 7.5 MB，最多 8 張）",
    )


class RejectRequest(BaseModel):
    """``/reject`` — 簽核 reject，工單回 IN_PROGRESS。"""

    reject_reason: str = Field(min_length=1, max_length=2000)


class CancelRequest(BaseModel):
    """``/cancel`` — 取消工單。可在 DRAFT / DISPATCHED / IN_PROGRESS 階段呼叫。"""

    cancel_reason: str = Field(min_length=1, max_length=2000)


class ReopenRequest(BaseModel):
    """``/reopen`` — 從 CLOSED 重開（``followup_kind=FOLLOWUP_NEEDED`` 或人工）。"""

    reopen_reason: str = Field(min_length=1, max_length=2000)


# ─────────────────────────────────────────────────────────────────────────
# Response
# ─────────────────────────────────────────────────────────────────────────


class WorkOrderResponse(BaseModel):
    """完整工單視圖（list / detail / 任何 transition 後共用）。"""

    model_config = ConfigDict(from_attributes=True)

    # identity
    id: UUID
    business_key: str

    # core
    farm_id: str
    turbine_id: str
    type: WorkOrderType
    status: WorkOrderStatus
    priority: Priority
    title: str
    description: str

    # 來源
    source_alarm_id: Optional[UUID] = None
    source_alarm_code: Optional[str] = None

    # 派工
    assignee_id: Optional[UUID] = None
    crew_size: int = 1
    estimated_hours: Optional[float] = None
    dispatched_at: Optional[datetime] = None
    dispatched_by: Optional[UUID] = None

    # offshore
    vessel_id: Optional[UUID] = None
    weather_window_id: Optional[UUID] = None
    logistic_hours: Optional[float] = None

    # 進行
    started_at: Optional[datetime] = None
    progress_notes: list[ProgressNoteResponse] = Field(default_factory=list)

    # 完工
    finished_at: Optional[datetime] = None
    actual_hours: Optional[float] = None
    work_summary: Optional[str] = None
    unfinished_items: Optional[str] = None
    followup_kind: FollowupKind = FollowupKind.NONE
    followup_note: Optional[str] = None
    completion_signature: Optional[str] = None
    completion_photos: list[str] = Field(default_factory=list)

    # 簽核
    signoff_chain_id: Optional[UUID] = None

    # 取消 / 駁回 / 結案 / 重開
    closed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    rejected_at: Optional[datetime] = None
    reject_reason: Optional[str] = None
    reopened_at: Optional[datetime] = None
    reopen_reason: Optional[str] = None

    # audit
    created_at: datetime
    created_by: Optional[UUID] = None
    updated_at: datetime


class WorkOrderListResponse(BaseModel):
    """``GET /api/workflow/work-orders`` 回應 — 帶 total + items。"""

    total: int
    items: list[WorkOrderResponse]
