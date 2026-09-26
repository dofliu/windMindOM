"""DayWorkForm domain 純函式 + dataclass 測試（WMOM-20260505-21）。

對應 [DN-01](../../../docs/design-notes/m3/DN-01-work-order-lifecycle.md) §3.3 walkthrough Q6。
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.workflow.domain.day_work_form import (
    ActivityEntry,
    ActivityKind,
    DayWorkForm,
    validate_activity_entry,
)


# ─────────────────────────────────────────────────────────────────────────
# validate_activity_entry — 每種 kind 的必填欄位
# ─────────────────────────────────────────────────────────────────────────


def test_completed_wo_requires_wo_id():
    entry = ActivityEntry(kind=ActivityKind.COMPLETED_WO, wo_id=uuid4())
    validate_activity_entry(entry)  # 不 raise


def test_completed_wo_missing_wo_id_raises():
    entry = ActivityEntry(kind=ActivityKind.COMPLETED_WO)
    with pytest.raises(ValueError, match="wo_id"):
        validate_activity_entry(entry)


def test_inspection_item_requires_item_id_and_result():
    entry = ActivityEntry(
        kind=ActivityKind.INSPECTION_ITEM, item_id=uuid4(), result="正常"
    )
    validate_activity_entry(entry)  # 不 raise


def test_inspection_item_missing_result_raises():
    entry = ActivityEntry(kind=ActivityKind.INSPECTION_ITEM, item_id=uuid4())
    with pytest.raises(ValueError, match="result"):
        validate_activity_entry(entry)


def test_inspection_item_missing_both_lists_both_in_message():
    entry = ActivityEntry(kind=ActivityKind.INSPECTION_ITEM)
    with pytest.raises(ValueError, match="item_id.*result"):
        validate_activity_entry(entry)


def test_patrol_requires_area():
    entry = ActivityEntry(kind=ActivityKind.PATROL, area="機艙")
    validate_activity_entry(entry)  # 不 raise


def test_patrol_missing_area_raises():
    entry = ActivityEntry(kind=ActivityKind.PATROL)
    with pytest.raises(ValueError, match="area"):
        validate_activity_entry(entry)


def test_patrol_empty_string_area_raises():
    """空字串視同未帶（不是 None 就放行）。"""
    entry = ActivityEntry(kind=ActivityKind.PATROL, area="")
    with pytest.raises(ValueError, match="area"):
        validate_activity_entry(entry)


def test_training_requires_topic():
    entry = ActivityEntry(kind=ActivityKind.TRAINING, topic="高空作業安全")
    validate_activity_entry(entry)  # 不 raise


def test_training_missing_topic_raises():
    entry = ActivityEntry(kind=ActivityKind.TRAINING)
    with pytest.raises(ValueError, match="topic"):
        validate_activity_entry(entry)


# ─────────────────────────────────────────────────────────────────────────
# DayWorkForm dataclass 預設值
# ─────────────────────────────────────────────────────────────────────────


def _make_form(**overrides) -> DayWorkForm:
    base = dict(
        farm_id="changhua",
        employee_id=uuid4(),
        work_date=date(2026, 5, 5),
    )
    base.update(overrides)
    return DayWorkForm(**base)


def test_default_activities_empty_list():
    form = _make_form()
    assert form.activities == []


def test_default_activities_lists_are_independent():
    """dataclass ``field(default_factory=list)`` 確保不同實例不共用同一個 list。"""
    a = _make_form()
    b = _make_form()
    a.activities.append(ActivityEntry(kind=ActivityKind.PATROL, area="機艙"))
    assert b.activities == []


def test_default_notes_empty_string():
    assert _make_form().notes == ""


def test_activities_can_hold_multiple_kinds():
    form = _make_form(
        activities=[
            ActivityEntry(kind=ActivityKind.COMPLETED_WO, wo_id=uuid4()),
            ActivityEntry(kind=ActivityKind.PATROL, area="機艙"),
        ]
    )
    assert len(form.activities) == 2
    assert form.activities[0].kind is ActivityKind.COMPLETED_WO
    assert form.activities[1].kind is ActivityKind.PATROL
