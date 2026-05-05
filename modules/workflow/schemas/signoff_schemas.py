"""Pydantic schemas for signoff API（WMOM-20260504-18）。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from modules.workflow.domain import (
    SignoffLevel,
    SignoffStatus,
    SignoffSubjectType,
)


# ─────────────────────────────────────────────────────────────────────────
# Request bodies
# ─────────────────────────────────────────────────────────────────────────


class ApproveStepRequest(BaseModel):
    """``POST /approvals/{step_id}/approve``"""

    actor_id: UUID
    comment: Optional[str] = Field(default=None, max_length=2000)


class RejectStepRequest(BaseModel):
    """``POST /approvals/{step_id}/reject``"""

    actor_id: UUID
    reason: str = Field(min_length=1, max_length=2000)


# ─────────────────────────────────────────────────────────────────────────
# Response
# ─────────────────────────────────────────────────────────────────────────


class SignoffStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chain_id: UUID
    level: SignoffLevel
    sequence: int
    parallel_group_id: Optional[UUID] = None
    assignee_id: Optional[UUID] = None
    status: SignoffStatus
    decided_at: Optional[datetime] = None
    decided_by: Optional[UUID] = None
    comment: Optional[str] = None
    created_at: datetime


class SignoffChainResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subject_type: SignoffSubjectType
    subject_id: UUID
    farm_id: str
    levels: list[SignoffLevel]
    current_level_index: int
    overall_status: SignoffStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    rejected_at_level: Optional[SignoffLevel] = None
    rejected_reason: Optional[str] = None


class PendingSignoffItem(BaseModel):
    """`GET /approvals/pending` 的單筆元素 — step + 其 chain 摘要。"""

    step: SignoffStepResponse
    chain: SignoffChainResponse


class PendingSignoffListResponse(BaseModel):
    total: int
    items: list[PendingSignoffItem]


class ApprovalResultResponse(BaseModel):
    """簽核 / 駁回後回應 — 含更新後的 chain + 是否觸發 subject closure 的 flag。"""

    chain: SignoffChainResponse
    chain_completed: bool      # True = chain 已 approved 或 rejected
    subject_status_changed: bool  # True 表示對應 work_order 也被 approve_all / reject 了
    # review fix #1/#2：如 work_order transition 失敗（罕見），chain 已落地但 subject
    # 未跟上；caller 看到此欄非 None → 知道要走 backfill / 回報 ops
    subject_transition_error: Optional[str] = None
