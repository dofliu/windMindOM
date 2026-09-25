"""InspectionSchedule domain 純函式 + dataclass 測試（WMOM-20260505-22）。

對應 [DN-01](../../../docs/design-notes/m3/DN-01-work-order-lifecycle.md) §3.3。
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.workflow.domain.inspection_schedule import (
    InspectionSchedule,
    Recurrence,
    compute_next_due,
    recurrence_interval_days,
)


UTC = timezone.utc


# ─────────────────────────────────────────────────────────────────────────
# recurrence_interval_days
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "recurrence, expected_days",
    [
        (Recurrence.MONTHLY, 30),
        (Recurrence.QUARTERLY, 91),
        (Recurrence.SEMI_ANNUAL, 182),
        (Recurrence.ANNUAL, 365),
    ],
)
def test_fixed_recurrence_days(recurrence, expected_days):
    assert recurrence_interval_days(recurrence, None) == expected_days


def test_fixed_recurrence_ignores_interval_days():
    """固定週期即使帶了 interval_days 也不使用（呼叫端不需要先清空）。"""
    assert recurrence_interval_days(Recurrence.MONTHLY, 999) == 30


def test_custom_days_uses_interval_days():
    assert recurrence_interval_days(Recurrence.CUSTOM_DAYS, 45) == 45


def test_custom_days_none_raises():
    with pytest.raises(ValueError, match="interval_days"):
        recurrence_interval_days(Recurrence.CUSTOM_DAYS, None)


def test_custom_days_zero_raises():
    with pytest.raises(ValueError, match="interval_days"):
        recurrence_interval_days(Recurrence.CUSTOM_DAYS, 0)


def test_custom_days_negative_raises():
    with pytest.raises(ValueError, match="interval_days"):
        recurrence_interval_days(Recurrence.CUSTOM_DAYS, -5)


# ─────────────────────────────────────────────────────────────────────────
# compute_next_due
# ─────────────────────────────────────────────────────────────────────────


def test_compute_next_due_monthly():
    from_dt = datetime(2026, 1, 1, tzinfo=UTC)
    next_due = compute_next_due(from_dt, Recurrence.MONTHLY, None)
    assert next_due == from_dt + timedelta(days=30)


def test_compute_next_due_custom_days():
    from_dt = datetime(2026, 1, 1, tzinfo=UTC)
    next_due = compute_next_due(from_dt, Recurrence.CUSTOM_DAYS, 45)
    assert next_due == from_dt + timedelta(days=45)


def test_compute_next_due_naive_datetime_raises():
    naive = datetime(2026, 1, 1)  # 無 tzinfo
    with pytest.raises(ValueError, match="timezone-aware"):
        compute_next_due(naive, Recurrence.MONTHLY, None)


# ─────────────────────────────────────────────────────────────────────────
# InspectionSchedule.is_due
# ─────────────────────────────────────────────────────────────────────────


def _make_schedule(**overrides) -> InspectionSchedule:
    base = dict(
        farm_id="changhua",
        turbine_id="WT-01",
        title="塔筒螺栓檢查",
        description="每月一次塔筒螺栓扭力檢查",
        recurrence=Recurrence.MONTHLY,
        next_due_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    base.update(overrides)
    return InspectionSchedule(**base)


def test_is_due_true_when_past_due():
    sched = _make_schedule(next_due_at=datetime(2026, 1, 1, tzinfo=UTC))
    as_of = datetime(2026, 2, 1, tzinfo=UTC)
    assert sched.is_due(as_of) is True


def test_is_due_true_when_exactly_at_boundary():
    """<= 比較：as_of 恰好等於 next_due_at 也算到期（不是嚴格 <）。"""
    boundary = datetime(2026, 2, 1, tzinfo=UTC)
    sched = _make_schedule(next_due_at=boundary)
    assert sched.is_due(boundary) is True


def test_is_due_false_when_future():
    sched = _make_schedule(next_due_at=datetime(2026, 3, 1, tzinfo=UTC))
    as_of = datetime(2026, 2, 1, tzinfo=UTC)
    assert sched.is_due(as_of) is False


def test_is_due_false_when_inactive_even_if_past_due():
    """active=False 的排程即使 next_due_at 已過期也不算到期（給 scheduler 用）。"""
    sched = _make_schedule(
        next_due_at=datetime(2026, 1, 1, tzinfo=UTC), active=False
    )
    as_of = datetime(2026, 2, 1, tzinfo=UTC)
    assert sched.is_due(as_of) is False


def test_default_active_true():
    sched = _make_schedule()
    assert sched.active is True
