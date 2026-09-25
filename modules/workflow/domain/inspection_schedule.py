"""Inspection schedule pure-domain entities for windMindOM workflow module。

對應 [DN-01](../../../docs/design-notes/m3/DN-01-work-order-lifecycle.md) §3.3 +
walkthrough Q7（2026-05-05 劉老師確認，見 ``WMOM-20260505-22``）。

實作邊界：
- 純 dataclass + Enum + 純函式；不接 SQLAlchemy / FastAPI
- 定檢清單（``InspectionSchedule``）與工單（``WorkOrder``）是不同 entity：排程只描述
  「多久要檢查一次」，到期時由 scheduler service（見 ``services/inspection_scheduler.py``）
  spawn 一張 ``WorkOrder(type=INSPECTION)``，兩者用 ``last_spawned_work_order_id`` 弱連結
  （非 FK cascade，工單本身生命週期獨立）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import UUID, uuid4


def _utc_now() -> datetime:
    """timezone-aware UTC now（windMindOM 一律 UTC 進 DB）。"""
    return datetime.now(tz=timezone.utc)


class Recurrence(str, Enum):
    """定檢週期。

    四種固定週期取近似天數（非月曆精確月份，避免「每月一次」在 2 月/大月之間漂移
    造成的邊界爭議——與 cost 模組月結不同，定檢週期只需「大約多久」）；
    ``CUSTOM_DAYS`` 讓劉老師 / 現場自訂任意天數（例如「每 45 天」）。
    """

    MONTHLY = "monthly"          # 約 30 天
    QUARTERLY = "quarterly"      # 約 91 天
    SEMI_ANNUAL = "semi_annual"  # 約 182 天
    ANNUAL = "annual"            # 約 365 天
    CUSTOM_DAYS = "custom_days"  # 見 InspectionSchedule.interval_days


# 固定週期 → 天數對照（CUSTOM_DAYS 不在此表，走 interval_days）。
_FIXED_RECURRENCE_DAYS: dict[Recurrence, int] = {
    Recurrence.MONTHLY: 30,
    Recurrence.QUARTERLY: 91,
    Recurrence.SEMI_ANNUAL: 182,
    Recurrence.ANNUAL: 365,
}


def recurrence_interval_days(
    recurrence: Recurrence, interval_days: int | None
) -> int:
    """把 ``Recurrence`` 換算成天數。

    ``CUSTOM_DAYS`` 必須帶正整數 ``interval_days``，否則 ``ValueError``；
    其餘固定週期忽略 ``interval_days``（即使有值也不用，呼叫端不需先清空）。
    """
    if recurrence is Recurrence.CUSTOM_DAYS:
        if interval_days is None or interval_days <= 0:
            raise ValueError(
                "Recurrence.CUSTOM_DAYS 需要正整數 interval_days"
            )
        return interval_days
    return _FIXED_RECURRENCE_DAYS[recurrence]


def compute_next_due(
    from_dt: datetime, recurrence: Recurrence, interval_days: int | None
) -> datetime:
    """從 ``from_dt`` 起算下一次到期時間（``from_dt`` 必須 UTC-aware）。"""
    if from_dt.tzinfo is None:
        raise ValueError("from_dt must be timezone-aware (UTC)")
    days = recurrence_interval_days(recurrence, interval_days)
    return from_dt + timedelta(days=days)


@dataclass
class InspectionSchedule:
    """定檢計畫主實體（walkthrough Q7：清單獨立 entity，到期由 scheduler auto-spawn 工單）。

    Naming convention 沿用 work_order.py：``id`` 為系統 FK 用 surrogate UUID，
    無獨立人類可讀 business_key（定檢計畫本身不對外流通列印，不同於工單）。
    """

    # ── primary identity ─────────────────────────────────────────────
    farm_id: str
    turbine_id: str
    title: str
    description: str
    recurrence: Recurrence
    next_due_at: datetime
    id: UUID = field(default_factory=uuid4)

    # ── 週期參數（僅 CUSTOM_DAYS 使用）───────────────────────────────
    interval_days: int | None = None

    # ── 狀態 ─────────────────────────────────────────────────────────
    active: bool = True  # False = 暫停（不再被 scheduler 挑中，但保留歷史）

    # ── 最近一次 spawn 紀錄（弱連結，非 FK cascade）───────────────────
    last_spawned_at: datetime | None = None
    last_spawned_work_order_id: UUID | None = None

    # ── audit ────────────────────────────────────────────────────────
    created_at: datetime = field(default_factory=_utc_now)
    created_by: UUID | None = None
    updated_at: datetime = field(default_factory=_utc_now)

    # ─────────────────────────────────────────────────────────────────
    # Convenience helpers — 不改狀態，純 query
    # ─────────────────────────────────────────────────────────────────

    def is_due(self, as_of: datetime) -> bool:
        """是否已到期（給 scheduler 用；``active=False`` 永遠不算到期）。"""
        if not self.active:
            return False
        return self.next_due_at <= as_of
