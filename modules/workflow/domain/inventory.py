"""Inventory + MaterialRequest pure-domain entities for windMindOM workflow module。

對應 [DN-03](../../../docs/design-notes/m3/DN-03-inventory-material-request.md)
+ [WMOM-20260509-01](../../../ISSUES.md)。

實作邊界（A1）：
- 純 dataclass + Enum；不接 SQLAlchemy / FastAPI
- ORM mapping 與雙寫交易在 ``repository/inventory_repository.py`` (A2)
- API 層在 ``routers/{material_request_router, inventory_router}.py`` (A3 / A4)

Walkthrough 確認的設計（劉老師 2026-05-05 / DN-03）：
- D3-Q1: 4 欄位庫存 → **3 欄位**（NEW / USED / REPAIRING）
- D3-Q2: 系統做請領→出庫→簽收→工單關聯；歸還由庫管員紙本管，系統側用 inventory adjustment endpoint
- D3-Q3: 估計 vs 實際領料都記（estimated_qty + actual_qty）
- D3-Q4: 退料 4 種分類（SURPLUS / WRONG_PART / FAILED_INSTALL / OTHER）
- D3-Q5: 多倉預留（warehouse_id 欄位），M3-M4 預設 single default warehouse
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Literal
from uuid import UUID, uuid4


def _utc_now() -> datetime:
    """timezone-aware UTC now（與 work_order._utc_now 一致；不直接 import 避免循環）。"""
    return datetime.now(tz=timezone.utc)


# ─────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────


class StockKind(str, Enum):
    """庫存 3 欄位（D3-Q1：從 etech 4 欄位簡化 — 「待檢驗」併入 REPAIRING）。

    若客戶堅持要「待檢驗」獨立，再加 ``PENDING_INSPECTION``。
    """

    NEW = "new"              # 全新未拆
    USED = "used"            # 良品 / 維修後可用（previously refurbished）
    REPAIRING = "repairing"  # 維修中 / 拆下送修 / 進貨待檢


class MaterialRequestStatus(str, Enum):
    """領料單狀態機 9 個 state（DN-03 §2.2）。

    Lifecycle：
        DRAFT → AWAITING_APPROVAL → APPROVED → DISPATCHED → RECEIVED → USED → CLOSED

    旁路（任一階段都可能）：
    - CANCELLED：DRAFT / AWAITING_APPROVAL / APPROVED 階段操作員取消（未出庫，不影響庫存）
    - REJECTED：簽核 chain 被駁回（DN-02）；採終態語意 — 操作員需建新 MR，不就地 resubmit
                （與 DN-02 D2-Q3「領料單回 DRAFT」設計差異點，walkthrough 可再確認；
                 終態 + 新 MR 較有清楚 audit / KPI 軌跡）

    Note：DISPATCHED 之後不允許 cancel — 物料已離庫，須走 ``MaterialReturn`` 流程。
    """

    DRAFT = "draft"                          # 申請人剛建未送
    AWAITING_APPROVAL = "awaiting_approval"  # DN-02 chain 跑中（3 階：employee/leader/treasury）
    APPROVED = "approved"                    # 簽核通過，待出庫
    DISPATCHED = "dispatched"                # 已出庫，待簽收
    RECEIVED = "received"                    # 領料人簽收（actual_qty 填入）
    USED = "used"                            # 工單完工 hook 觸發
    CLOSED = "closed"                        # 完工 + 退料 / 報廢處理完
    CANCELLED = "cancelled"                  # 操作員取消（未出庫）
    REJECTED = "rejected"                    # 簽核 chain 駁回（DN-02 D2-Q3）


class ReturnReason(str, Enum):
    """退料原因分類（D3-Q4 確認 4 種；給 KPI 統計用）。"""

    SURPLUS = "surplus"                # 用剩
    WRONG_PART = "wrong_part"          # 拿錯料件
    FAILED_INSTALL = "failed_install"  # 試裝失敗 / 不適用
    OTHER = "other"                    # 其他（如報廢；KPI 細分留 F2 future）


# ─────────────────────────────────────────────────────────────────────────
# Sub-entities
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class Warehouse:
    """倉庫主檔（D3-Q5：M3-M4 預設 single default warehouse；多倉 schema 預留）。"""

    name: str
    farm_id: str
    location_kind: Literal["onshore_base", "vessel_storage", "offshore_platform"]
    id: UUID = field(default_factory=uuid4)
    is_default: bool = False


@dataclass
class InventoryItem:
    """料件主檔。

    3 個 stock 欄位（NEW / USED / REPAIRING）+ safety_stock 警示閾值。
    ``unit_cost`` 為 ``Decimal`` 避免浮點誤差（給 cost ledger 計算用）。
    """

    sku: str                              # 業務料號
    name: str
    description: str
    unit: str                             # "個" / "公升" / "公斤" / "套"
    farm_id: str
    warehouse_id: UUID
    unit_cost: Decimal                    # EUR — 給 cost ledger 用
    id: UUID = field(default_factory=uuid4)
    stock_new: int = 0
    stock_used: int = 0
    stock_repairing: int = 0
    safety_stock: int = 0                 # 低於此值觸發 safety_stock 警示
    last_received_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def total_available(self) -> int:
        """可派發庫存總和（不含維修中）。"""
        return self.stock_new + self.stock_used

    def is_below_safety(self) -> bool:
        """``stock_new + stock_used < safety_stock`` 視為警示。"""
        return self.total_available() < self.safety_stock

    def get_stock(self, kind: StockKind) -> int:
        """取單一 stock kind 數量（給 dispatch 雙寫 transaction lock 後讀用）。"""
        if kind is StockKind.NEW:
            return self.stock_new
        if kind is StockKind.USED:
            return self.stock_used
        return self.stock_repairing


@dataclass
class MaterialRequestItem:
    """單一料件請領明細（一張 MR 可帶多筆）。

    ``estimated_qty`` 是建單時的估計、``actual_qty`` 是簽收時填入的實際領用數
    （D3-Q3：兩個都記，給 cost ledger estimated → confirmed flow 用）。
    """

    request_id: UUID                          # FK to MaterialRequest
    item_id: UUID                             # FK to InventoryItem
    estimated_qty: int                        # 建單時估計
    id: UUID = field(default_factory=uuid4)
    actual_qty: int | None = None             # 實際領用（簽收時填）
    stock_kind: StockKind = StockKind.NEW     # 領哪個 stock 欄位（預設新品優先）

    # ── 顯示用 metadata（WMOM-20260518-01）─────────────────────────────────
    # 由 repository `_to_domain` 透過 ORM relationship join InventoryItem 補值；
    # 純 informational，不參與 state machine / dispatch / domain invariant。
    # raw dataclass 構造（test fixture / wizard preview）時保持 None。
    sku: str | None = None
    name: str | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        # invariant：estimated_qty 嚴格正
        if self.estimated_qty <= 0:
            raise ValueError(
                f"MaterialRequestItem.estimated_qty must be > 0 (got {self.estimated_qty})"
            )


@dataclass
class MaterialRequest:
    """領料申請單主實體 — 對應 etech ``materialsForm``（DN-03 §2.2）。

    Naming convention：
    - ``id`` 為 surrogate UUID（系統 FK 用）
    - ``business_key`` 為人類可讀 ``MR-{farm_id_short}-{YYYYMM}-{NN}``
    """

    farm_id: str
    requester_id: UUID                        # 申請人
    business_key: str
    id: UUID = field(default_factory=uuid4)

    # ── 關聯（可選 — 預備庫存補貨可獨立發）─────────────────────────────
    work_order_id: UUID | None = None         # 關聯工單

    # ── status ─────────────────────────────────────────────────────────
    status: MaterialRequestStatus = MaterialRequestStatus.DRAFT

    # ── 明細 ────────────────────────────────────────────────────────────
    items: list[MaterialRequestItem] = field(default_factory=list)

    # ── 簽核（DN-02）─────────────────────────────────────────────────────
    signoff_chain_id: UUID | None = None

    # ── timeline ────────────────────────────────────────────────────────
    requested_at: datetime = field(default_factory=_utc_now)
    submitted_at: datetime | None = None       # → AWAITING_APPROVAL 時刻
    approved_at: datetime | None = None
    dispatched_at: datetime | None = None
    received_at: datetime | None = None
    used_at: datetime | None = None
    closed_at: datetime | None = None
    cancelled_at: datetime | None = None
    rejected_at: datetime | None = None

    # ── 取消 / 駁回原因 ─────────────────────────────────────────────────
    cancel_reason: str | None = None
    reject_reason: str | None = None

    # ── audit ───────────────────────────────────────────────────────────
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def compute_returnable_upper_bound(self, item_id: UUID) -> int:
        """累計可退數量上限（WMOM-20260519-01）— pure domain invariant。

        公式：``max(0, dispatched_total - consumed_total)``。其中
        - ``dispatched_total`` = Σ ``estimated_qty``  for items matching ``item_id``
          （dispatch 時實際扣 stock 的量；當前資料模型 dispatched == estimated_qty）
        - ``consumed_total``   = Σ ``actual_qty``     for items matching ``item_id``
          AND ``actual_qty is not None``（receive 時填的實用量，None 視為 0）

        Caller（repository ``add_return``）應再扣掉 ``already_returned`` 累計值才得到
        「現在還可退多少」，並以此 guard ``MaterialRequestRuleViolation``。

        Cross-kind 處理：不 group by ``stock_kind`` — 物理上同一料件（``item_id``）的
        進出總帳；dispatch NEW、退 USED 屬同一進出帳。

        ⚠ pure-domain（不查 DB）— ``already_returned`` 不在此計算範圍。
        """
        dispatched_total = sum(
            it.estimated_qty for it in self.items if it.item_id == item_id
        )
        consumed_total = sum(
            it.actual_qty
            for it in self.items
            if it.item_id == item_id and it.actual_qty is not None
        )
        return max(0, dispatched_total - consumed_total)


@dataclass
class MaterialReturn:
    """退料記錄（D3-Q4：4 種分類 + 退回哪一欄 stock）。"""

    request_id: UUID                          # 對應領料單
    item_id: UUID                             # 退哪個料件
    qty: int
    reason: ReturnReason
    return_to_kind: StockKind                 # 退回哪一欄（new / used / repairing）
    returned_by: UUID
    id: UUID = field(default_factory=uuid4)
    note: str | None = None
    returned_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if self.qty <= 0:
            raise ValueError(f"MaterialReturn.qty must be > 0 (got {self.qty})")


@dataclass
class MaterialRequestNotification:
    """簽核 / 出庫 / 庫存 低於安全閾值的通知（取代 etech 兩個 notic collection）。

    依 ``recipient_role`` 對應 DN-02 ``SignoffLevel``（leader 看組長、treasury 看總務、
    employee 看一般員工 — RAG 後續擴 recipient_user_id 直接指人）。
    """

    request_id: UUID
    recipient_role: str                       # SignoffLevel.value（不直接 import 避免循環）
    notification_type: Literal[
        "awaiting_signoff",
        "stock_low",
        "received_pending",
        "dispatched_to_field",
    ]
    id: UUID = field(default_factory=uuid4)
    read_at: datetime | None = None
    created_at: datetime = field(default_factory=_utc_now)


@dataclass
class InventoryAdjustmentLog:
    """手動 +/- 調整 audit log（D3-Q2：庫管員紙本管理，系統側 endpoint + log）。

    每次 ``POST /api/workflow/inventory/{item_id}/adjust`` 必須寫此 log。
    歸還 / 報廢 / 盤盈虧都走這條 path（不用另開 entity）。
    """

    item_id: UUID
    delta_kind: StockKind                     # 異動哪個 stock 欄位
    delta: int                                # 正值 = 加、負值 = 扣（不限正負）
    reason: str                               # 必填：「歸還良品」/「盤盈」/「客戶換貨」等
    actor_id: UUID                            # 庫管員身分
    id: UUID = field(default_factory=uuid4)
    note: str | None = None
    occurred_at: datetime = field(default_factory=_utc_now)
