"""Approval signoff pure-domain entities for windMindOM workflow module。

對應 [DN-02](../../../docs/design-notes/m3/DN-02-approval-multilevel.md)。

實作邊界（WMOM-20260504-18）：
- 純 dataclass + Enum + chain policy；不接 SQLAlchemy / FastAPI
- ORM mapping 與 persistence 在 ``repository/signoff_repository.py``
- API 層在 ``routers/approval_router.py``

Walkthrough 確認的設計（劉老師 2026-05-05）：
- D2-Q1: 4 階 ``EMPLOYEE / LEADER / SUPERVISOR / TREASURY``，可由 farm config 關某層
- D2-Q2: 工單 chain = [EMPLOYEE, LEADER]（2 階）；領料 chain = [EMPLOYEE, LEADER, TREASURY]（3 階）
- D2-Q3: reject → 工單回 IN_PROGRESS（給機會修正）；領料單回 DRAFT
- D2-Q4: 線性簽核為主；schema 預留 ``parallel_group_id`` 給未來
- D2-Q5: 完整 ``signoff_history`` 紀錄給 KPI 用（誰被退最多 / 哪類常被退）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable
from uuid import UUID, uuid4

from .work_order import _utc_now


# ─────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────


class SignoffLevel(str, Enum):
    """簽核層級（D2-Q1：4 階對應 etech user group 100/300/500/666）。

    可由 farm config ``signoff_disabled_levels`` 關某層（如某客戶不要組長層）。
    """

    EMPLOYEE = "employee"        # group 100 — 派工簽收 / 完工申報
    LEADER = "leader"            # group 300 — 組長
    SUPERVISOR = "supervisor"    # group 500 — 主管
    TREASURY = "treasury"        # group 666 — 總務 / 庫管


class SignoffStatus(str, Enum):
    """單一 step 與整 chain 共用的 status。"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"          # farm config 關閉某層時設此


class SignoffSubjectType(str, Enum):
    """簽核對象類型（D2-Q2：兩種 subject 不同 chain，但同一 signoff 表）。"""

    WORK_ORDER = "work_order"
    MATERIAL_REQUEST = "material_request"  # M4 才會用


# ─────────────────────────────────────────────────────────────────────────
# Domain entities
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class SignoffChain:
    """整個簽核流程實體 — 一張工單 / 領料單對應一個 chain。"""

    subject_type: SignoffSubjectType
    subject_id: UUID
    farm_id: str
    levels: list[SignoffLevel]                     # 此 chain 要走的層級順序
    id: UUID = field(default_factory=uuid4)
    current_level_index: int = 0                   # 走到第幾階（0-based）
    overall_status: SignoffStatus = SignoffStatus.PENDING
    started_at: datetime = field(default_factory=_utc_now)
    completed_at: datetime | None = None            # all approved / first reject 才設
    rejected_at_level: SignoffLevel | None = None   # reject 時記是被誰擋下
    rejected_reason: str | None = None

    def is_terminal(self) -> bool:
        """整 chain 已結束（approved or rejected），不可再 mutate。"""
        return self.overall_status in (SignoffStatus.APPROVED, SignoffStatus.REJECTED)


@dataclass
class SignoffStep:
    """單一階段的簽核任務 — chain 內每個 level 對應一筆。"""

    chain_id: UUID
    level: SignoffLevel
    sequence: int                                  # chain 內順序（0, 1, 2...）
    id: UUID = field(default_factory=uuid4)
    parallel_group_id: UUID | None = None          # D2-Q4 預留：同層級多人並行簽
    assignee_id: UUID | None = None                # 指派給誰（None = 任一同 level user 可簽）
    status: SignoffStatus = SignoffStatus.PENDING
    decided_at: datetime | None = None
    decided_by: UUID | None = None
    comment: str | None = None                     # approve / reject 留言
    created_at: datetime = field(default_factory=_utc_now)


@dataclass
class SignoffHistoryEntry:
    """完整簽核歷史（D2-Q5：保留 reject 歷史給 KPI 用）。

    每個有意義的事件（chain created / step assigned / approved / rejected / skipped /
    chain completed）寫一筆。

    ``id`` 對齊 ORM 走 ``int`` autoincrement（history 是 insert-only audit log，UUID
    非必要 — review fix #9）。
    """

    chain_id: UUID
    event_type: str                                # "chain_created" | "step_approved" | ...
    occurred_at: datetime
    id: int | None = None                          # SQLite autoincrement int；None 表示尚未 persist
    step_id: UUID | None = None                    # 對應 step（若 chain-level event 則 None）
    actor_id: UUID | None = None                   # 操作者
    payload: dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────
# Chain policy
# ─────────────────────────────────────────────────────────────────────────


# 預設 chain levels — 由 farm config 客製化
DEFAULT_WORK_ORDER_CHAIN: list[SignoffLevel] = [
    SignoffLevel.EMPLOYEE,
    SignoffLevel.LEADER,
]

DEFAULT_MATERIAL_REQUEST_CHAIN: list[SignoffLevel] = [
    SignoffLevel.EMPLOYEE,
    SignoffLevel.LEADER,
    SignoffLevel.TREASURY,
]


def build_chain_levels(
    subject_type: SignoffSubjectType,
    *,
    farm_config: dict[str, Any] | None = None,
    escalate_to_supervisor: bool = False,
) -> list[SignoffLevel]:
    """依 farm config 客製化 chain。

    Args:
        subject_type: WORK_ORDER 或 MATERIAL_REQUEST
        farm_config: 可選 dict；含 ``signoff_disabled_levels`` key 時對應 level 從
                     chain 移除（如某客戶不需 leader 階）。值可為 ``list[SignoffLevel]``
                     或 ``list[str]``（從 JSON 讀進來時自動 coerce — review fix #11）
        escalate_to_supervisor: 若 True 加 SUPERVISOR 為最後一階。
                                典型觸發條件：高金額 / 跨組 / priority=critical 工單

    Returns:
        ordered ``list[SignoffLevel]`` — chain 走訪順序

    Raises:
        ``ValueError``：farm_config 把所有 level 都關掉（無 chain 不該存在）— review fix #3
    """
    if subject_type is SignoffSubjectType.WORK_ORDER:
        base = DEFAULT_WORK_ORDER_CHAIN[:]
    elif subject_type is SignoffSubjectType.MATERIAL_REQUEST:
        base = DEFAULT_MATERIAL_REQUEST_CHAIN[:]
    else:
        raise ValueError(f"unknown subject_type: {subject_type}")

    # review fix #11：disabled 可能是 list[str]（JSON config）— coerce 成 SignoffLevel
    raw_disabled = (farm_config or {}).get("signoff_disabled_levels", [])
    disabled: list[SignoffLevel] = [
        SignoffLevel(d) if isinstance(d, str) else d for d in raw_disabled
    ]
    base = [lvl for lvl in base if lvl not in disabled]

    if escalate_to_supervisor and SignoffLevel.SUPERVISOR not in base:
        base.append(SignoffLevel.SUPERVISOR)

    if not base:
        # review fix #3：farm_config 把所有 default level 都關 → loud failure
        raise ValueError(
            f"farm_config.signoff_disabled_levels 不可關閉所有層級；"
            f"subject_type={subject_type.value} 至少要保留一階"
        )

    return base


# ─────────────────────────────────────────────────────────────────────────
# Helper：user_group → SignoffLevel
# ─────────────────────────────────────────────────────────────────────────


_GROUP_TO_LEVEL: dict[int, SignoffLevel] = {
    100: SignoffLevel.EMPLOYEE,
    300: SignoffLevel.LEADER,
    500: SignoffLevel.SUPERVISOR,
    666: SignoffLevel.TREASURY,
}


def user_group_to_level(group: int) -> SignoffLevel | None:
    """etech user group code（100/300/500/666）→ SignoffLevel。

    Returns ``None`` 表示該 group 不屬於簽核角色（如 999 系統管理員）。
    """
    return _GROUP_TO_LEVEL.get(group)
