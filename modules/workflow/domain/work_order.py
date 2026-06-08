"""Work order pure-domain entities for windMindOM workflow module。

對應 [DN-01](../../../docs/design-notes/m3/DN-01-work-order-lifecycle.md)。

實作邊界（WMOM-20260504-16）：
- 純 dataclass + Enum；不接 SQLAlchemy / FastAPI
- 狀態機放在 ``state_machine.py``（同 package），這個檔案只描述「形狀」
- ``WorkOrder.id`` 為 surrogate UUID（FK 用）；``business_key`` 為人類可讀
  ``WO-{farm_id_short}-{YYYYMM}-{NN}``，給 UI / 列印用
- Onshore baseline + offshore 延伸欄位並存（``vessel_id`` / ``weather_window_id`` /
  ``logistic_hours``），onshore 場景全留 ``None``

Walkthrough Q&A（2026-05-05）已整合進 DN-01 §5；本模組對應的決策：

- Q2 ``FollowupKind`` 縮成二元 + 新增 ``Priority`` enum 取代「嚴重度」
- Q3 一台風機 ≤ 3 張 OPEN 工單（DB unique on ``(turbine_id, source_alarm_code)`` +
  application-level count check；本檔不做 enforcement，留給 repository / service 層）
- Q4 ``WorkOrderType`` 4 種完整涵蓋
- Q5 ``weather_window_id`` 可為 ``None``（onshore farm 永遠不用）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


def _utc_now() -> datetime:
    """timezone-aware UTC now（windMindOM 一律 UTC 進 DB / 給 cost ledger 算時差）。"""
    return datetime.now(tz=timezone.utc)


# ─────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────


class WorkOrderStatus(str, Enum):
    """工單狀態機 7 個 state。

    Walkthrough Q1 確認：``CANCELLED`` 為 etech ``removeFrom`` 的取代方案，
    不另開 collection；``cancel_reason`` 為選填欄位。
    """

    DRAFT = "draft"                          # 開單但還沒派工
    DISPATCHED = "dispatched"                # 已派工，等待人 / 船 / 天氣窗
    IN_PROGRESS = "in_progress"              # 維修進行中
    AWAITING_SIGNOFF = "awaiting_signoff"    # 完工等簽核（DN-02）
    CLOSED = "closed"                        # 完整關閉
    CANCELLED = "cancelled"                  # 取消（取代 etech removeFrom）
    REOPENED = "reopened"                    # 已關但因 followup 重開


class WorkOrderType(str, Enum):
    """工單類型（walkthrough Q4 確認預留 4 種完整涵蓋）。"""

    CORRECTIVE = "corrective"        # 故障維修
    PREVENTIVE = "preventive"        # 預防性保養（PM）
    INSPECTION = "inspection"        # 定檢
    COMMISSIONING = "commissioning"  # 試運轉


class FollowupKind(str, Enum):
    """完工後續處理（walkthrough Q2：縮成二元）。

    etech 原本的 ``chooseschange ∈ {完成, 追蹤觀察, 需改善}`` 三分類，walkthrough
    確認 SLA 沒有實質差異 → 縮為 ``NONE`` / ``FOLLOWUP_NEEDED``；嚴重度走獨立
    ``Priority`` enum。
    """

    NONE = "none"                          # 完工無後續
    FOLLOWUP_NEEDED = "followup_needed"    # 需追蹤（自動建 ``WorkOrderFollowup``）


class Priority(str, Enum):
    """工單優先級（walkthrough Q2：取代 followup 三分類的「嚴重度」）。"""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


# ─────────────────────────────────────────────────────────────────────────
# Sub-entities
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class ProgressNote:
    """維修進行中員工多次更新（取代 etech 原地 PUT 覆寫，留追蹤）。"""

    timestamp: datetime
    actor_id: UUID
    note: str


@dataclass
class WorkOrderFollowup:
    """≡ etech ``trackFrom``，但用真 FK 連到 parent work_order。

    ``parent_work_order_id`` 為必填（kw_only）— followup 永遠隸屬一張 parent 工單，
    不存在「孤兒 followup」。
    """

    parent_work_order_id: UUID = field(kw_only=True)
    problem: str = ""                                 # ≡ trackFrom.problem (= parent.unfinished_items)
    id: UUID = field(default_factory=uuid4)
    kind: FollowupKind = FollowupKind.FOLLOWUP_NEEDED
    read_by: list[UUID] = field(default_factory=list)  # ≡ trackFrom.readname
    resolved: bool = False
    resolved_at: datetime | None = None
    spawned_work_order_id: UUID | None = None         # 若需重做，連到後續新工單
    created_at: datetime = field(default_factory=_utc_now)


# ─────────────────────────────────────────────────────────────────────────
# Main entity
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class WorkOrder:
    """工單主實體（onshore baseline + offshore 延伸並存）。

    Naming convention：
    - ``id`` 為 surrogate UUID（系統 FK 用）
    - ``business_key`` 為人類可讀 ``WO-{farm_id_short}-{YYYYMM}-{NN}``
      （UI / 列印 / report 用，與 etech ``totalformnumber`` 設計同源）

    Required vs optional：
    - dataclass 沒有 frozen / kw_only，但實務上 ``id`` / ``farm_id`` /
      ``turbine_id`` / ``type`` 應視為「建立後不可改」（state machine 不會動）
    """

    # ── primary identity ─────────────────────────────────────────────
    farm_id: str
    turbine_id: str
    type: WorkOrderType
    title: str
    description: str
    business_key: str
    id: UUID = field(default_factory=uuid4)

    # ── status ───────────────────────────────────────────────────────
    status: WorkOrderStatus = WorkOrderStatus.DRAFT
    priority: Priority = Priority.NORMAL

    # ── 來源（可選 — alarm-driven 時填）──────────────────────────────
    source_alarm_id: UUID | None = None
    source_alarm_code: str | None = None  # SCADA 警報碼（給 RAG / multi-WO constraint key 用）

    # ── 派工 ─────────────────────────────────────────────────────────
    assignee_id: UUID | None = None
    crew_size: int = 1
    estimated_hours: float | None = None
    dispatched_at: datetime | None = None
    dispatched_by: UUID | None = None

    # ── offshore 延伸（onshore 永遠 None）────────────────────────────
    # walkthrough Q5 確認：onshore farm 不需 weather_window；
    # ``state_machine.start_work`` guard 會看 farm config 是否要求
    vessel_id: UUID | None = None
    weather_window_id: UUID | None = None
    logistic_hours: float | None = None

    # ── 進行 ─────────────────────────────────────────────────────────
    started_at: datetime | None = None
    progress_notes: list[ProgressNote] = field(default_factory=list)

    # ── 完工 ─────────────────────────────────────────────────────────
    finished_at: datetime | None = None
    actual_hours: float | None = None
    work_summary: str | None = None             # ≡ etech workfinish
    unfinished_items: str | None = None         # ≡ etech nofinish
    followup_kind: FollowupKind = FollowupKind.NONE  # ≡ etech chooseschange (縮二元)
    followup_note: str | None = None

    # ── 完工佐證（WMOM-20260608-02 / DEC-20260608-02）─────────────────
    # 現場工程師完工須簽名 + 拍照。domain 設 optional（office finish 不強制、
    # 既有 path 不破壞）；「現場必須」的強制在 /field/ 前端那層。
    # 儲存：base64 data URL（簽名單張 PNG / 照片多張），demo-first（M6 前可改物件儲存）。
    completion_signature: str | None = None       # canvas 簽名 base64 data URL
    completion_photos: list[str] = field(default_factory=list)  # 佐證照片 base64 data URL 清單

    # ── 領料（DN-03 主，placeholder 給工單 ←→ 領料單關聯）───────────
    material_request_ids: list[UUID] = field(default_factory=list)

    # ── 簽核（DN-02）─────────────────────────────────────────────────
    signoff_chain_id: UUID | None = None

    # ── 取消 / 結案 ──────────────────────────────────────────────────
    closed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    rejected_at: datetime | None = None
    reject_reason: str | None = None

    # ── reopen（≡ etech「需改善」場景觸發；與 followup_note 分離以利 audit）──
    reopened_at: datetime | None = None
    reopen_reason: str | None = None

    # ── audit ────────────────────────────────────────────────────────
    created_at: datetime = field(default_factory=_utc_now)
    created_by: UUID | None = None
    updated_at: datetime = field(default_factory=_utc_now)

    # ─────────────────────────────────────────────────────────────────
    # Convenience helpers — 不改 state，純 query
    # ─────────────────────────────────────────────────────────────────

    def is_open(self) -> bool:
        """是否為 OPEN 狀態（給 multi-WO constraint 用）。"""
        from .state_machine import open_states

        return self.status in open_states()

    def is_terminal(self) -> bool:
        """是否已到終態（CLOSED / CANCELLED）— 不可再 transition。"""
        from .state_machine import terminal_states

        return self.status in terminal_states()

    def to_dict(self) -> dict[str, Any]:
        """淺度 dict（給 router / serialization 層用；不處理巢狀 progress_notes）。"""
        from dataclasses import asdict

        return asdict(self)
