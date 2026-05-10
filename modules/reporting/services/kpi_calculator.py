"""KPI calculator — 純資料聚合層（WMOM-20260509-08）。

責任：
1. 從 ``CostLedgerRepository`` + ``WorkOrderRepository`` 拉資料
2. 算出月報所需 4 區塊（KPI / cost / work orders / availability）
3. **不**負責 render（HTML / PDF），給 monthly_report.py 拿結構化 dict 餵 template

設計重點：
- Pure function 為主，便於 unit test
- ``compute_monthly_report_data`` 一次給齊 ``MonthlyReportData``
- Availability 預設用 work order ``actual_hours`` 推算 (downtime hours)；留 hook
  給未來物理模擬注入精確值（``availability_provider`` callable）
- 月份區間採半開區間 ``[period_start, period_end)``，與 ledger query 一致

Period boundary（重要 — 給後續維護）：
- 每月區間以 UTC 計算：``period_start = datetime(year, month, 1, tz=UTC)``
- 結算邊界：work order 是否「當月 finished」用 ``finished_at`` 落在區間內判斷
- 「期間結尾仍 in_progress」用 status snapshot 抓 — 因 list 結果是當下狀態
  （無時光機 query），這是合理近似；要嚴格期間 snapshot 須走 event_log 還原
  → 留 follow-up
"""

from __future__ import annotations

import logging
from calendar import monthrange
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Optional

from modules.cost.repository.cost_ledger import (
    CostLedgerCategory,
    CostLedgerStatus,
)
from modules.cost.repository.cost_ledger_repository import CostLedgerRepository
from modules.workflow.domain import open_states
from modules.workflow.domain.work_order import WorkOrder, WorkOrderType
from modules.workflow.repository.work_order_repository import WorkOrderRepository

from modules.reporting.schemas.reporting_schemas import (
    AvailabilityMetrics,
    CostBreakdownItem,
    CostSummary,
    KpiHighlights,
    MonthlyReportData,
    NotableEvent,
    WorkOrderSummary,
    WorkOrderTypeStats,
)

_logger = logging.getLogger(__name__)

# 單農場單月份工單數量上限預期 << 1000；超過時走分頁延伸補完
_WO_FETCH_PAGE_SIZE: int = 1000


# ─────────────────────────────────────────────────────────────────────────
# Period helpers
# ─────────────────────────────────────────────────────────────────────────


def month_period(year: int, month: int) -> tuple[datetime, datetime]:
    """回傳 ``(period_start, period_end)`` UTC 半開區間 ``[start, end)``。

    Raises:
        ValueError: month 不在 1-12
    """
    if not (1 <= month <= 12):
        raise ValueError(f"month must be 1-12, got {month}")
    period_start = datetime(year, month, 1, tzinfo=timezone.utc)
    last_day = monthrange(year, month)[1]
    if month == 12:
        period_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        period_end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    _ = last_day  # 留作未來人工 sanity
    return period_start, period_end


def hours_in_period(period_start: datetime, period_end: datetime) -> float:
    """回傳區間總時數（小時）。"""
    delta = period_end - period_start
    return delta.total_seconds() / 3600.0


# ─────────────────────────────────────────────────────────────────────────
# Cost aggregation
# ─────────────────────────────────────────────────────────────────────────


def compute_cost_summary(
    ledger_repo: CostLedgerRepository,
    *,
    farm_id: str,
    period_start: datetime,
    period_end: datetime,
) -> CostSummary:
    """聚合 4 大類成本（estimated + confirmed 分開）。

    呼叫 ``summary_by_category`` 兩次（estimated / confirmed），合成每類 breakdown。
    """
    estimated_map = ledger_repo.summary_by_category(
        farm_id=farm_id,
        from_date=period_start,
        to_date=period_end,
        status=CostLedgerStatus.ESTIMATED,
    )
    confirmed_map = ledger_repo.summary_by_category(
        farm_id=farm_id,
        from_date=period_start,
        to_date=period_end,
        status=CostLedgerStatus.CONFIRMED,
    )

    by_category: list[CostBreakdownItem] = []
    estimated_total = Decimal("0")
    confirmed_total = Decimal("0")

    # 永遠輸出全 4 類（即使某類為 0），讓月報排版穩定
    for cat in CostLedgerCategory:
        est = estimated_map.get(cat, Decimal("0"))
        con = confirmed_map.get(cat, Decimal("0"))
        by_category.append(
            CostBreakdownItem(
                category=cat.value,
                estimated=est,
                confirmed=con,
                total=est + con,
            )
        )
        estimated_total += est
        confirmed_total += con

    return CostSummary(
        by_category=by_category,
        estimated_total=estimated_total,
        confirmed_total=confirmed_total,
        grand_total=estimated_total + confirmed_total,
    )


# ─────────────────────────────────────────────────────────────────────────
# Work order stats
# ─────────────────────────────────────────────────────────────────────────


def _is_in_period(
    when: Optional[datetime],
    period_start: datetime,
    period_end: datetime,
) -> bool:
    """Repo `_to_domain` 已 ensure_utc，這裡不再防禦性處理 tz。"""
    if when is None:
        return False
    return period_start <= when < period_end


def fetch_all_work_orders(
    wo_repo: WorkOrderRepository,
    *,
    farm_id: str,
    page_size: int = _WO_FETCH_PAGE_SIZE,
) -> list[WorkOrder]:
    """拉某 farm 全部 WO（分頁補完）— 給 summary + notable_events 共享一份 snapshot。

    Review fix #4：避免兩次獨立 query 造成 DB I/O 雙倍 + 中間有寫入時拿到不一致資料。
    """
    items, total = wo_repo.list(farm_id=farm_id, limit=page_size, offset=0)
    if total > page_size:
        offset = page_size
        while offset < total:
            more, _ = wo_repo.list(farm_id=farm_id, limit=page_size, offset=offset)
            items.extend(more)
            offset += page_size
    return items


def compute_work_order_summary(
    wo_items: list[WorkOrder],
    *,
    period_start: datetime,
    period_end: datetime,
) -> WorkOrderSummary:
    """聚合工單統計：按 type 分類 + 期間 finished / closed / in_progress + actual_hours。

    取得 ``wo_items`` 透過 ``fetch_all_work_orders``（caller 拉好給 notable_events 共用）。

    Review fix #1（must）：
    - 用 ``open_states()`` 對齊 workflow domain，含 DRAFT / REOPENED / DISPATCHED /
      IN_PROGRESS / AWAITING_SIGNOFF（之前漏了 DRAFT / REOPENED）
    - in_progress 加上下界 ``closed_at >= period_start or closed_at is None``
      避免「2025-03 建單、目前仍 dispatched」的工單在每月月報都被計一次
    """
    # 初始化每 type 的 stats
    stats_map: dict[str, WorkOrderTypeStats] = {
        t.value: WorkOrderTypeStats(type=t.value) for t in WorkOrderType
    }

    total_finished = 0
    total_closed = 0
    total_in_progress = 0
    total_actual_hours = 0.0

    open_state_values = {s.value for s in open_states()}

    for wo in wo_items:
        type_key = wo.type.value
        stat = stats_map.get(type_key)
        if stat is None:
            # 新增的 enum 值：動態追加
            stat = WorkOrderTypeStats(type=type_key)
            stats_map[type_key] = stat

        if _is_in_period(wo.finished_at, period_start, period_end):
            stat.finished += 1
            total_finished += 1
            if wo.actual_hours is not None:
                total_actual_hours += float(wo.actual_hours)

        if _is_in_period(wo.closed_at, period_start, period_end):
            stat.closed += 1
            total_closed += 1

        # Review fix #1：期間結尾仍 in_progress 必須 (a) 仍是 open state、
        # (b) 在 period_end 前建立、(c) 在 period_start 前還沒關閉
        # → 避免跨月工單在每個月都被重複計。
        is_open_at_period_end = (
            wo.status.value in open_state_values
            and wo.created_at is not None
            and wo.created_at < period_end
            and (wo.closed_at is None or wo.closed_at >= period_start)
        )
        if is_open_at_period_end:
            stat.in_progress += 1
            total_in_progress += 1

    return WorkOrderSummary(
        by_type=list(stats_map.values()),
        total_finished=total_finished,
        total_closed=total_closed,
        total_in_progress=total_in_progress,
        total_actual_hours=total_actual_hours,
    )


# ─────────────────────────────────────────────────────────────────────────
# Availability
# ─────────────────────────────────────────────────────────────────────────


# 預設物理 availability provider（callable），caller 可注入精確值
AvailabilityProvider = Callable[
    [str, datetime, datetime],  # farm_id, period_start, period_end
    Optional[tuple[float, float]],  # (time_avail, energy_avail) or None to fallback
]


def compute_availability(
    *,
    farm_id: str,
    period_start: datetime,
    period_end: datetime,
    work_order_summary: WorkOrderSummary,
    provider: Optional[AvailabilityProvider] = None,
) -> AvailabilityMetrics:
    """算 time / energy availability。

    優先順序：
    1. ``provider`` 給出精確值（M5+ 物理模擬注入）→ source=physics_simulator
    2. 從 work order ``total_actual_hours`` 推 ``time_availability``→ source=work_order_derived
       - ``time_availability = max(0, 1 - downtime_hours / total_hours)``
       - ``energy_availability`` 預設 = ``time_availability``（無物理資料）

    Note：actual_hours 是維修工時，不完全等於 downtime（一台機被吊船 8h 才修 2h，
    停機 8h），目前先用 actual_hours 做近似；M5+ 物理模擬 hook 上線後改寫。
    """
    total_hours = hours_in_period(period_start, period_end)
    downtime_hours = work_order_summary.total_actual_hours

    # provider 優先
    if provider is not None:
        result = provider(farm_id, period_start, period_end)
        if result is not None:
            time_avail, energy_avail = result
            return AvailabilityMetrics(
                time_availability=max(0.0, min(1.0, time_avail)),
                energy_availability=max(0.0, min(1.0, energy_avail)),
                total_hours_in_period=total_hours,
                downtime_hours=downtime_hours,
                source="physics_simulator",
            )

    # fallback：work_order 推算
    if total_hours <= 0:
        time_avail = 1.0
    else:
        time_avail = max(0.0, 1.0 - downtime_hours / total_hours)
    return AvailabilityMetrics(
        time_availability=time_avail,
        energy_availability=time_avail,
        total_hours_in_period=total_hours,
        downtime_hours=downtime_hours,
        source="work_order_derived",
    )


# ─────────────────────────────────────────────────────────────────────────
# KPI highlights
# ─────────────────────────────────────────────────────────────────────────


def compute_kpi(
    *,
    cost: CostSummary,
    work_orders: WorkOrderSummary,
    availability: AvailabilityMetrics,
) -> KpiHighlights:
    """月報首頁摘要 KPI（4 個關鍵數）。"""
    grand = cost.grand_total
    if grand > 0:
        confirmed_ratio = float(cost.confirmed_total / grand)
    else:
        confirmed_ratio = 0.0

    if work_orders.total_finished > 0:
        avg_repair = work_orders.total_actual_hours / work_orders.total_finished
    else:
        avg_repair = 0.0

    return KpiHighlights(
        grand_total_cost=grand,
        confirmed_cost_ratio=max(0.0, min(1.0, confirmed_ratio)),
        work_orders_finished=work_orders.total_finished,
        average_repair_hours=avg_repair,
        time_availability=availability.time_availability,
    )


# ─────────────────────────────────────────────────────────────────────────
# Notable events
# ─────────────────────────────────────────────────────────────────────────


def compute_notable_events(
    wo_items: list[WorkOrder],
    *,
    period_start: datetime,
    period_end: datetime,
    limit: int = 10,
) -> list[NotableEvent]:
    """挑出當月「重大事件」（高優先 corrective WO + 期間建立或關閉）。

    Review fix #4：接受已 fetch 好的 ``wo_items``，避免重複 query。
    M5 可改加 alarm log / signoff reject 整合。
    """
    events: list[NotableEvent] = []
    for wo in wo_items:
        # 高優先且當月建立或完工
        is_high = wo.priority.value in {"high", "critical"}
        if not is_high:
            continue
        if _is_in_period(wo.created_at, period_start, period_end):
            events.append(
                NotableEvent(
                    occurred_at=wo.created_at,
                    event_type="work_order_created",
                    title=f"[{wo.priority.value.upper()}] {wo.business_key} — {wo.title}",
                    detail=f"turbine={wo.turbine_id}, type={wo.type.value}",
                )
            )
        if _is_in_period(wo.finished_at, period_start, period_end):
            events.append(
                NotableEvent(
                    occurred_at=wo.finished_at,
                    event_type="work_order_finished",
                    title=f"[{wo.priority.value.upper()}] {wo.business_key} 完工",
                    detail=(
                        f"actual_hours={wo.actual_hours}"
                        if wo.actual_hours is not None
                        else None
                    ),
                )
            )

    events.sort(key=lambda e: e.occurred_at)
    return events[:limit]


# ─────────────────────────────────────────────────────────────────────────
# Top-level：拼出 MonthlyReportData
# ─────────────────────────────────────────────────────────────────────────


def compute_monthly_report_data(
    *,
    ledger_repo: CostLedgerRepository,
    wo_repo: WorkOrderRepository,
    farm_id: str,
    year: int,
    month: int,
    farm_name: Optional[str] = None,
    availability_provider: Optional[AvailabilityProvider] = None,
    notable_event_limit: int = 10,
) -> MonthlyReportData:
    """A8 主入口 — 拼出整份月報結構化資料（給 render 用）。

    Raises:
        ValueError: month 不在 1-12
    """
    period_start, period_end = month_period(year, month)

    cost = compute_cost_summary(
        ledger_repo,
        farm_id=farm_id,
        period_start=period_start,
        period_end=period_end,
    )
    # Review fix #4：拉一次 WO snapshot 共用 — summary + notable_events 不再各拉一次
    wo_items = fetch_all_work_orders(wo_repo, farm_id=farm_id)
    work_orders = compute_work_order_summary(
        wo_items,
        period_start=period_start,
        period_end=period_end,
    )
    availability = compute_availability(
        farm_id=farm_id,
        period_start=period_start,
        period_end=period_end,
        work_order_summary=work_orders,
        provider=availability_provider,
    )
    kpi = compute_kpi(cost=cost, work_orders=work_orders, availability=availability)
    notable_events = compute_notable_events(
        wo_items,
        period_start=period_start,
        period_end=period_end,
        limit=notable_event_limit,
    )

    return MonthlyReportData(
        farm_id=farm_id,
        farm_name=farm_name,
        year=year,
        month=month,
        period_start=period_start,
        period_end=period_end,
        generated_at=datetime.now(tz=timezone.utc),
        kpi=kpi,
        cost=cost,
        work_orders=work_orders,
        availability=availability,
        notable_events=notable_events,
    )
