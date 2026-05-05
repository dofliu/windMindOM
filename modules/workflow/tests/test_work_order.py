"""Work order domain dataclass / Enum sanity tests（WMOM-20260504-16）。

純 domain 層測試 — 不接 SQLAlchemy / FastAPI。狀態機行為見 ``test_state_machine.py``。
"""

from __future__ import annotations

import sys
from dataclasses import is_dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.workflow.domain import (  # noqa: E402
    FollowupKind,
    Priority,
    ProgressNote,
    WorkOrder,
    WorkOrderFollowup,
    WorkOrderStatus,
    WorkOrderType,
    open_states,
    terminal_states,
)


# ─────────────────────────────────────────────────────────────────────────
# Enum sanity
# ─────────────────────────────────────────────────────────────────────────


def test_work_order_status_has_seven_states():
    """walkthrough Q1 確認：CANCELLED 取代 etech removeFrom；總計 7 個 state。"""
    expected = {
        "draft", "dispatched", "in_progress",
        "awaiting_signoff", "closed", "cancelled", "reopened",
    }
    assert {s.value for s in WorkOrderStatus} == expected


def test_work_order_type_has_four_kinds():
    """walkthrough Q4 確認：4 種 type 完整涵蓋。"""
    expected = {"corrective", "preventive", "inspection", "commissioning"}
    assert {t.value for t in WorkOrderType} == expected


def test_followup_kind_is_binary():
    """walkthrough Q2：縮成二元（NONE / FOLLOWUP_NEEDED）。"""
    assert {k.value for k in FollowupKind} == {"none", "followup_needed"}


def test_priority_has_four_levels():
    """walkthrough Q2：取代 followup「嚴重度」的獨立 4 級 priority。"""
    assert {p.value for p in Priority} == {"low", "normal", "high", "critical"}


def test_status_string_serialization():
    """str(Enum) 可直接給 JSON 用（str-based Enum 子類）。"""
    assert WorkOrderStatus.IN_PROGRESS.value == "in_progress"
    # str-Enum 等同字串，方便比對
    assert WorkOrderStatus.DRAFT == "draft"


# ─────────────────────────────────────────────────────────────────────────
# State helpers
# ─────────────────────────────────────────────────────────────────────────


def test_open_states_is_5_pre_terminal():
    """open_states = 所有非終態（不含 CLOSED / CANCELLED）。"""
    assert open_states() == frozenset({
        WorkOrderStatus.DRAFT,
        WorkOrderStatus.DISPATCHED,
        WorkOrderStatus.IN_PROGRESS,
        WorkOrderStatus.AWAITING_SIGNOFF,
        WorkOrderStatus.REOPENED,
    })


def test_terminal_states_is_closed_and_cancelled():
    assert terminal_states() == frozenset(
        {WorkOrderStatus.CLOSED, WorkOrderStatus.CANCELLED}
    )


def test_open_and_terminal_are_disjoint():
    """open / terminal 不應重疊（state 機沒有「半終結」）。"""
    assert open_states().isdisjoint(terminal_states())


# ─────────────────────────────────────────────────────────────────────────
# WorkOrder dataclass
# ─────────────────────────────────────────────────────────────────────────


def _make_min_wo(**overrides) -> WorkOrder:
    """Helper：建構最小可用的 WO instance（給多 test 共用）。"""
    base = dict(
        farm_id="台中港曲風場",
        turbine_id="WT001",
        type=WorkOrderType.CORRECTIVE,
        title="Bearing temperature alarm",
        description="主軸承溫度 75°C，需檢查",
        business_key="WO-Z72TC-202607-01",
    )
    base.update(overrides)
    return WorkOrder(**base)


def test_work_order_is_dataclass():
    assert is_dataclass(WorkOrder)


def test_work_order_minimal_construction():
    """最小欄位（farm_id / turbine_id / type / title / description / business_key）即可建。"""
    wo = _make_min_wo()
    assert wo.farm_id == "台中港曲風場"
    assert wo.turbine_id == "WT001"
    assert wo.type == WorkOrderType.CORRECTIVE
    # 預設值
    assert wo.status == WorkOrderStatus.DRAFT
    assert wo.priority == Priority.NORMAL
    assert wo.followup_kind == FollowupKind.NONE
    assert wo.crew_size == 1
    # UUID 自動生
    assert isinstance(wo.id, UUID)
    # 時間戳自動填
    assert isinstance(wo.created_at, datetime)
    assert isinstance(wo.updated_at, datetime)
    # 集合預設空 list
    assert wo.progress_notes == []
    assert wo.material_request_ids == []


def test_work_order_offshore_fields_default_none():
    """walkthrough Q5 確認：offshore 欄位 onshore 不需，預設全 None。"""
    wo = _make_min_wo()
    assert wo.vessel_id is None
    assert wo.weather_window_id is None
    assert wo.logistic_hours is None


def test_is_open_helper_for_open_state():
    wo = _make_min_wo()  # status=DRAFT
    assert wo.is_open() is True
    assert wo.is_terminal() is False


def test_is_terminal_helper_for_closed():
    wo = _make_min_wo(status=WorkOrderStatus.CLOSED)
    assert wo.is_open() is False
    assert wo.is_terminal() is True


def test_is_terminal_helper_for_cancelled():
    wo = _make_min_wo(status=WorkOrderStatus.CANCELLED)
    assert wo.is_terminal() is True


def test_to_dict_contains_all_fields():
    wo = _make_min_wo()
    d = wo.to_dict()
    assert d["farm_id"] == "台中港曲風場"
    assert d["turbine_id"] == "WT001"
    # Enum 會被 asdict 保留為 Enum 物件（str-Enum 序列化由 caller 處理）
    assert d["status"] == WorkOrderStatus.DRAFT
    # 巢狀 list 仍存在（不 unpack ProgressNote 內部）
    assert "progress_notes" in d


# ─────────────────────────────────────────────────────────────────────────
# WorkOrderFollowup
# ─────────────────────────────────────────────────────────────────────────


def test_workorder_followup_minimal():
    wo_id = uuid4()
    f = WorkOrderFollowup(
        parent_work_order_id=wo_id,
        problem="未確認的二次振動",
    )
    assert f.parent_work_order_id == wo_id
    assert f.kind == FollowupKind.FOLLOWUP_NEEDED  # 預設值（trackFrom 場景必帶）
    assert f.resolved is False
    assert f.read_by == []
    assert isinstance(f.created_at, datetime)


# ─────────────────────────────────────────────────────────────────────────
# ProgressNote
# ─────────────────────────────────────────────────────────────────────────


def test_progress_note_construction():
    actor = uuid4()
    now = datetime.now()
    n = ProgressNote(timestamp=now, actor_id=actor, note="拆螺栓 5 顆")
    assert n.actor_id == actor
    assert n.timestamp == now
    assert n.note == "拆螺栓 5 顆"


# ─────────────────────────────────────────────────────────────────────────
# UTC datetime（review fix #5）
# ─────────────────────────────────────────────────────────────────────────


def test_default_timestamps_are_utc_aware():
    """walkthrough fix #5：所有 default_factory 產的 timestamp 必須 timezone-aware UTC。

    避免 naive datetime 進 DB 後跟 cost ledger 的 alarm timestamp（assumed UTC）混用。
    """
    wo = _make_min_wo()
    # tzinfo 非 None 表示 timezone-aware
    assert wo.created_at.tzinfo is not None
    assert wo.updated_at.tzinfo is not None
    # 並且 offset 為 UTC
    assert wo.created_at.utcoffset().total_seconds() == 0


def test_followup_default_created_at_is_utc():
    f = WorkOrderFollowup(parent_work_order_id=uuid4())
    assert f.created_at.tzinfo is not None
    assert f.created_at.utcoffset().total_seconds() == 0


# ─────────────────────────────────────────────────────────────────────────
# WorkOrderFollowup parent FK（review fix #1）
# ─────────────────────────────────────────────────────────────────────────


def test_workorder_followup_parent_id_is_required_kwarg():
    """walkthrough fix #1：``parent_work_order_id`` 為 kw_only 必填，
    不可呼叫無參數建構造成「孤兒 followup」。"""
    with pytest.raises(TypeError, match="parent_work_order_id"):
        WorkOrderFollowup()  # type: ignore[call-arg]
