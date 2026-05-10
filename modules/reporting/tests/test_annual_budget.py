"""Annual budget service tests（WMOM-20260509-08）。"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.cost.repository.cost_ledger import (
    CostLedgerCategory,
    CostLedgerEntry,
    CostLedgerSourceType,
    CostLedgerStatus,
    insert_in_session,
)
from modules.cost.repository.cost_ledger_repository import (
    get_cost_ledger_repository,
)
from modules.workflow.repository.work_order_repository import (
    clear_engine_cache_for_test,
)

from modules.reporting.services.annual_budget import (
    compute_annual_budget,
    render_annual_budget_pdf,
)


FARM = "changhua"


@pytest.fixture
def ledger_repo(tmp_path):
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")
    repo = get_cost_ledger_repository(db_path)
    yield repo
    clear_engine_cache_for_test()


def _insert(repo, *, year, month, amount=Decimal("100"),
            category=CostLedgerCategory.MATERIAL,
            status=CostLedgerStatus.CONFIRMED):
    """Insert ledger entry on day 15 of given month。"""
    entry = CostLedgerEntry(
        farm_id=FARM,
        category=category,
        amount=amount,
        source_event_id=uuid4(),
        source_type=CostLedgerSourceType.MATERIAL_REQUEST,
        status=status,
        recorded_at=datetime(year, month, 15, tzinfo=timezone.utc),
    )
    with repo._sessionmaker() as sess:
        insert_in_session(sess, entry)
        sess.commit()
    return entry


# ─────────────────────────────────────────────────────────────────────────
# compute_annual_budget
# ─────────────────────────────────────────────────────────────────────────


def test_annual_budget_returns_12_months(ledger_repo):
    data = compute_annual_budget(
        ledger_repo=ledger_repo, farm_id=FARM, year=2026, current_month=1,
    )
    assert len(data.months) == 12
    assert [m.month for m in data.months] == list(range(1, 13))


def test_annual_budget_past_months_use_actual_data(ledger_repo):
    # 2026-03 confirmed material 500
    _insert(ledger_repo, year=2026, month=3, amount=Decimal("500"))
    data = compute_annual_budget(
        ledger_repo=ledger_repo, farm_id=FARM, year=2026, current_month=4,
    )
    march = data.months[2]
    assert march.actual_total == Decimal("500")
    assert march.method == "actual"
    assert march.forecast_by_category["material"] == Decimal("500")


def test_annual_budget_future_months_forecast_from_history(ledger_repo):
    # 2025-10 / 11 / 12 各 confirmed material 100, 200, 300（窗口=3 平均=200）
    _insert(ledger_repo, year=2025, month=10, amount=Decimal("100"))
    _insert(ledger_repo, year=2025, month=11, amount=Decimal("200"))
    _insert(ledger_repo, year=2025, month=12, amount=Decimal("300"))
    data = compute_annual_budget(
        ledger_repo=ledger_repo, farm_id=FARM, year=2026, current_month=1,
        history_window=3,
    )
    # 1 月（current_month=1）→ 用 actual（無資料 = 0）
    # 2 月起為 future → forecast = avg(history)
    feb = data.months[1]
    assert feb.actual_total is None
    # 2 月 forecast：歷史 buffer = [Oct=100, Nov=200, Dec=300, Jan=0] (Jan 已被 push 進去)
    # window=3 → avg 後 3 個 = (200+300+0)/3 ≈ 166.67
    assert feb.forecast_by_category["material"] == pytest.approx(Decimal("166.6667"), abs=Decimal("0.01"))


def test_annual_budget_annual_actual_total_only_counts_actual(ledger_repo):
    _insert(ledger_repo, year=2026, month=2, amount=Decimal("100"))
    _insert(ledger_repo, year=2026, month=3, amount=Decimal("200"))
    data = compute_annual_budget(
        ledger_repo=ledger_repo, farm_id=FARM, year=2026, current_month=3,
    )
    # 1-3 月為 actual，其中 2/3 月有 confirmed = 100+200=300
    assert data.annual_actual_total == Decimal("300")
    # forecast_total 至少 >= actual
    assert data.annual_forecast_total >= data.annual_actual_total


def test_annual_budget_rejects_unknown_method(ledger_repo):
    with pytest.raises(ValueError, match="Unsupported method"):
        compute_annual_budget(
            ledger_repo=ledger_repo, farm_id=FARM, year=2026,
            method="ml_lstm", current_month=1,
        )


def test_annual_budget_rejects_invalid_current_month(ledger_repo):
    with pytest.raises(ValueError, match="current_month must be 1-12"):
        compute_annual_budget(
            ledger_repo=ledger_repo, farm_id=FARM, year=2026, current_month=13,
        )


def test_annual_budget_current_month_marked_as_actual_partial(ledger_repo):
    """Review fix (must-fix #2)：current_month 那筆 method='actual_partial'，
    actual_total 是截至今日的部分值，forecast_total 走歷史平均（與 actual 解耦）。
    """
    # 歷史：去年 10/11/12 各 confirmed 600 EUR
    _insert(ledger_repo, year=2025, month=10, amount=Decimal("600"))
    _insert(ledger_repo, year=2025, month=11, amount=Decimal("600"))
    _insert(ledger_repo, year=2025, month=12, amount=Decimal("600"))
    # 5 月為當月（截至產出日只 confirmed 100）
    _insert(ledger_repo, year=2026, month=5, amount=Decimal("100"))

    data = compute_annual_budget(
        ledger_repo=ledger_repo, farm_id=FARM, year=2026, current_month=5,
    )
    may = data.months[4]
    assert may.method == "actual_partial"
    assert may.actual_total == Decimal("100")
    # 核心：forecast 與 actual 解耦（不再像 bug 版本兩者相同）
    # 之前 bug：method="actual" + forecast=actual_total=100，月報誤導以為已結帳
    # 修正後：forecast 走歷史平均算出獨立值，跟 partial actual 不一樣
    assert may.forecast_total != may.actual_total


def test_annual_budget_past_months_still_use_actual_method(ledger_repo):
    """Past months（month < current_month）method 仍是 'actual'，不是 partial。"""
    _insert(ledger_repo, year=2026, month=2, amount=Decimal("200"))
    data = compute_annual_budget(
        ledger_repo=ledger_repo, farm_id=FARM, year=2026, current_month=5,
    )
    feb = data.months[1]
    assert feb.method == "actual"
    assert feb.actual_total == Decimal("200")
    assert feb.forecast_total == feb.actual_total  # past month: forecast=actual


def test_annual_budget_rejects_invalid_history_window(ledger_repo):
    """Review fix (should-fix #1)：history_window > 12 必須給明確錯誤而非崩潰。"""
    with pytest.raises(ValueError, match="history_window must be 1-12"):
        compute_annual_budget(
            ledger_repo=ledger_repo, farm_id=FARM, year=2026,
            history_window=15, current_month=1,
        )


def test_annual_budget_with_no_history_forecasts_zero(ledger_repo):
    """完全沒歷史資料 → forecast = 0（不應該掛）。"""
    data = compute_annual_budget(
        ledger_repo=ledger_repo, farm_id=FARM, year=2026, current_month=1,
    )
    # 12 月（最後一個 future month）forecast 該為 0
    dec = data.months[11]
    assert dec.forecast_total == Decimal("0")


# ─────────────────────────────────────────────────────────────────────────
# PDF render
# ─────────────────────────────────────────────────────────────────────────


def test_render_annual_budget_pdf_returns_pdf_bytes(ledger_repo):
    _insert(ledger_repo, year=2025, month=12, amount=Decimal("500"))
    data = compute_annual_budget(
        ledger_repo=ledger_repo, farm_id=FARM, year=2026, current_month=1,
        farm_name="Changhua Farm",
    )
    pdf = render_annual_budget_pdf(data)
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1000


def test_render_annual_budget_pdf_with_zero_data(ledger_repo):
    data = compute_annual_budget(
        ledger_repo=ledger_repo, farm_id=FARM, year=2026, current_month=1,
    )
    pdf = render_annual_budget_pdf(data)
    assert pdf.startswith(b"%PDF-")
