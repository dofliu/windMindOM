"""WorkOrderRepository test — SQLAlchemy CRUD + business_key + multi-WO constraint。

對應 [WMOM-20260504-17](../../../ISSUES.md)。
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.workflow.domain import (
    FollowupKind,
    Priority,
    WorkOrderStatus,
    WorkOrderType,
)
from modules.workflow.repository import (
    BusinessRuleViolation,
    WorkOrderRepository,
    get_repository,
)
from modules.workflow.repository.work_order_repository import (
    clear_engine_cache_for_test,
    _farm_id_short,
)


# ─────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def repo(tmp_path) -> WorkOrderRepository:
    """Fresh repository on tmp DB（每個 test 一個全新 schema + clean cache）。"""
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")
    yield get_repository(db_path)
    clear_engine_cache_for_test()


def _make(repo, **overrides):
    """Helper：建單，可覆寫任意欄位。"""
    base = dict(
        farm_id="台中港曲風場",
        turbine_id="WT001",
        type=WorkOrderType.CORRECTIVE,
        title="軸承過熱",
        description="主軸承溫度 75°C",
    )
    base.update(overrides)
    return repo.create(**base)


# ─────────────────────────────────────────────────────────────────────────
# CRUD basics
# ─────────────────────────────────────────────────────────────────────────


def test_create_and_get_by_id(repo):
    wo = _make(repo)
    assert wo.status == WorkOrderStatus.DRAFT
    assert wo.priority == Priority.NORMAL
    assert wo.business_key.startswith("WO-")

    fetched = repo.get(wo.id)
    assert fetched is not None
    assert fetched.id == wo.id
    assert fetched.business_key == wo.business_key
    assert fetched.title == "軸承過熱"


def test_get_by_business_key(repo):
    wo = _make(repo)
    fetched = repo.get_by_business_key(wo.business_key)
    assert fetched is not None
    assert fetched.id == wo.id


def test_get_returns_none_for_missing(repo):
    assert repo.get(uuid4()) is None


def test_list_filters_by_farm(repo):
    _make(repo, farm_id="台中港曲風場", turbine_id="WT001")
    _make(repo, farm_id="彰化離岸風場台電", turbine_id="WT001",
          source_alarm_code="X")  # 不同 farm 故無 constraint

    items, total = repo.list(farm_id="台中港曲風場")
    assert len(items) == 1
    assert total == 1
    assert items[0].farm_id == "台中港曲風場"


def test_list_returns_real_total_unaffected_by_limit(repo):
    """nice-to-have #1：limit 不影響 total，給前端正確分頁資訊。"""
    for i in range(5):
        _make(repo, turbine_id=f"WT{i:03d}", source_alarm_code=f"A{i}")

    items, total = repo.list(farm_id="台中港曲風場", limit=2)
    assert len(items) == 2
    assert total == 5  # 真實總數，不受 limit 截斷


def test_list_filters_by_status(repo):
    """status filter 只回對應 status 的工單。"""
    actor = uuid4()
    a = _make(repo, source_alarm_code="A001", assignee_id=actor)
    _make(repo, source_alarm_code="B002")  # 留 DRAFT

    # a → DISPATCHED
    repo.transition(a.id, "dispatch", actor_id=actor)

    drafts, total_d = repo.list(status=WorkOrderStatus.DRAFT)
    dispatched, total_dis = repo.list(status=WorkOrderStatus.DISPATCHED)
    assert (len(drafts), total_d) == (1, 1)
    assert (len(dispatched), total_dis) == (1, 1)
    assert drafts[0].source_alarm_code == "B002"
    assert dispatched[0].source_alarm_code == "A001"


def test_list_only_open_excludes_terminal(repo):
    a = _make(repo, source_alarm_code="A")
    b = _make(repo, turbine_id="WT002", source_alarm_code="B")
    # cancel a
    repo.transition(a.id, "cancel", cancel_reason="not needed")

    open_only, total = repo.list(only_open=True)
    open_ids = {w.id for w in open_only}
    assert b.id in open_ids
    assert a.id not in open_ids  # CANCELLED 為終態
    assert total == 1


# ─────────────────────────────────────────────────────────────────────────
# Business key generation
# ─────────────────────────────────────────────────────────────────────────


def test_business_key_format(repo):
    wo = _make(repo, farm_id="台中港曲風場")
    # WO-{short}-{YYYYMM}-{NNN} — review fix #3：03d 三位零填補
    parts = wo.business_key.split("-")
    assert parts[0] == "WO"
    assert len(parts) == 4
    assert parts[3] == "001"


def test_business_key_increments_within_same_farm(repo):
    a = _make(repo, source_alarm_code="A")
    b = _make(repo, turbine_id="WT002", source_alarm_code="B")
    c = _make(repo, turbine_id="WT003", source_alarm_code="C")

    n_a = int(a.business_key.split("-")[-1])
    n_b = int(b.business_key.split("-")[-1])
    n_c = int(c.business_key.split("-")[-1])
    assert (n_a, n_b, n_c) == (1, 2, 3)


def test_business_key_separate_per_farm(repo):
    a = _make(repo, farm_id="台中港曲風場")
    b = _make(repo, farm_id="彰化離岸風場台電")

    # 兩 farm 各自 NN=001（review fix #3：03d 格式）
    assert a.business_key.endswith("-001")
    assert b.business_key.endswith("-001")
    # short 不同
    assert a.business_key != b.business_key


def test_business_key_format_remains_3digit_above_99(repo, monkeypatch):
    """review fix #3：第 100+ 張工單的 NN 仍應 3 位零填補（不破格式）。"""
    from modules.workflow.repository import work_order_repository as wo_module

    # 用 monkeypatch override _next_business_key 模擬「已有 99 張」場景，
    # 不需真的建 99 張單（會撞 max-3-OPEN constraint）
    real_next = wo_module.WorkOrderRepository._next_business_key

    n_calls = {"i": 99}

    def fake_next(self, sess, farm_id):
        # 第一次呼叫返回 NN=100 的 key
        prefix = real_next(self, sess, farm_id).rsplit("-", 1)[0]
        return f"{prefix}-{n_calls['i'] + 1:03d}"

    monkeypatch.setattr(wo_module.WorkOrderRepository, "_next_business_key", fake_next)
    wo = _make(repo, source_alarm_code="A100")
    # NN 應為 100（3 位零填補時實際 = 100，不是 0100；但仍 3 位）
    assert wo.business_key.endswith("-100")
    assert len(wo.business_key.rsplit("-", 1)[1]) == 3


def test_farm_id_short_ascii():
    assert _farm_id_short("offshore_001") == "OFFSH"
    assert _farm_id_short("WT_FARM") == "WTFAR"


def test_farm_id_short_chinese_falls_back_to_hash():
    s = _farm_id_short("台中港曲風場")
    assert s.startswith("H")
    assert len(s) == 6  # H + 5 hex


def test_farm_id_short_deterministic():
    s1 = _farm_id_short("台中港曲風場")
    s2 = _farm_id_short("台中港曲風場")
    assert s1 == s2


# ─────────────────────────────────────────────────────────────────────────
# Multi-WO constraint（walkthrough Q3）
# ─────────────────────────────────────────────────────────────────────────


def test_max_3_open_per_turbine_enforced(repo):
    """一台風機 ≤ 3 OPEN（不同 alarm 才可多張）。"""
    _make(repo, source_alarm_code="A001")
    _make(repo, source_alarm_code="A002")
    _make(repo, source_alarm_code="A003")

    with pytest.raises(BusinessRuleViolation, match="3 OPEN"):
        _make(repo, source_alarm_code="A004")


def test_max_3_only_counts_open_states(repo):
    """已 cancel 的不計入 ≤ 3 限制。"""
    a = _make(repo, source_alarm_code="A001")
    _make(repo, source_alarm_code="A002")
    _make(repo, source_alarm_code="A003")

    # cancel 一張 → 應可再建第 4 張（其實是新 #4，但 OPEN 仍 3 張）
    repo.transition(a.id, "cancel", cancel_reason="not needed")
    # 現在 OPEN 是 2 張，可再建
    _make(repo, source_alarm_code="A004")


def test_same_alarm_code_blocks_duplicate(repo):
    """同 turbine + 同 alarm_code 不可有 OPEN 工單（DB unique 替代 enforcement）。"""
    _make(repo, source_alarm_code="ALARM_X")
    with pytest.raises(BusinessRuleViolation, match="alarm_code"):
        _make(repo, source_alarm_code="ALARM_X")


def test_no_alarm_code_does_not_block(repo):
    """不帶 alarm_code 的工單彼此互不衝突（手動建單場景）。"""
    _make(repo, source_alarm_code=None)
    _make(repo, source_alarm_code=None)  # OK
    _make(repo, source_alarm_code=None)  # OK
    # 第 4 張會踩 ≤ 3 限制
    with pytest.raises(BusinessRuleViolation, match="3 OPEN"):
        _make(repo, source_alarm_code=None)


def test_different_turbines_independent(repo):
    """不同台風機各算 ≤ 3。"""
    for i in range(3):
        _make(repo, turbine_id="WT001", source_alarm_code=f"A{i}")
    for i in range(3):
        _make(repo, turbine_id="WT002", source_alarm_code=f"B{i}")
    # 都 OK


def test_count_open_for_turbine(repo):
    _make(repo, source_alarm_code="A")
    _make(repo, source_alarm_code="B")
    assert repo.count_open_for_turbine("台中港曲風場", "WT001") == 2
    assert repo.count_open_for_turbine("台中港曲風場", "WT002") == 0


# ─────────────────────────────────────────────────────────────────────────
# State machine wrapping（transition）
# ─────────────────────────────────────────────────────────────────────────


def test_transition_dispatch_persists(repo):
    actor = uuid4()
    wo = _make(repo, assignee_id=uuid4())
    updated = repo.transition(wo.id, "dispatch", actor_id=actor)
    assert updated.status == WorkOrderStatus.DISPATCHED
    assert updated.dispatched_by == actor
    assert updated.dispatched_at is not None

    # Re-fetch from DB 驗 persisted
    refetch = repo.get(wo.id)
    assert refetch.status == WorkOrderStatus.DISPATCHED
    assert refetch.dispatched_by == actor


def test_transition_invalid_action_raises(repo):
    from modules.workflow.domain import InvalidTransition

    wo = _make(repo)
    with pytest.raises(InvalidTransition):
        repo.transition(wo.id, "fly_to_moon")


def test_transition_lookup_error_for_missing(repo):
    with pytest.raises(LookupError):
        repo.transition(uuid4(), "dispatch", actor_id=uuid4())


def test_transition_full_lifecycle_persists(repo):
    actor = uuid4()
    wo = _make(repo, assignee_id=actor)

    repo.transition(wo.id, "dispatch", actor_id=actor)
    repo.transition(wo.id, "start_work")
    repo.transition(wo.id, "update_progress", actor_id=actor, note="拆下軸承")
    final = repo.transition(
        wo.id, "finish",
        actual_hours=3.5,
        followup_kind=FollowupKind.NONE,
        work_summary="完成",
    )
    repo.transition(final.id, "approve_all")

    refetch = repo.get(wo.id)
    assert refetch.status == WorkOrderStatus.CLOSED
    assert refetch.closed_at is not None
    assert len(refetch.progress_notes) == 1
    assert refetch.progress_notes[0].note == "拆下軸承"
    assert refetch.actual_hours == 3.5
    assert refetch.work_summary == "完成"


def test_transition_reject_back_to_in_progress_persists(repo):
    actor = uuid4()
    wo = _make(repo, assignee_id=actor)
    repo.transition(wo.id, "dispatch", actor_id=actor)
    repo.transition(wo.id, "start_work")
    repo.transition(
        wo.id, "finish",
        actual_hours=2.0,
        followup_kind=FollowupKind.NONE,
    )
    repo.transition(wo.id, "reject", reject_reason="缺照片")
    refetch = repo.get(wo.id)
    assert refetch.status == WorkOrderStatus.IN_PROGRESS
    assert refetch.reject_reason == "缺照片"


def test_transition_reopen_with_independent_reason_field(repo):
    """walkthrough fix #7：reopen_reason 走獨立欄位，不污染 followup_note。"""
    actor = uuid4()
    wo = _make(repo, assignee_id=actor)
    repo.transition(wo.id, "dispatch", actor_id=actor)
    repo.transition(wo.id, "start_work")
    repo.transition(
        wo.id, "finish",
        actual_hours=2.0,
        followup_kind=FollowupKind.NONE,
        followup_note="完工觀察一週",
    )
    repo.transition(wo.id, "approve_all")
    repo.transition(wo.id, "reopen", reopen_reason="同部件再故障")

    refetch = repo.get(wo.id)
    assert refetch.status == WorkOrderStatus.REOPENED
    assert refetch.reopen_reason == "同部件再故障"
    # followup_note 不被 reopen 污染
    assert refetch.followup_note == "完工觀察一週"


# ─────────────────────────────────────────────────────────────────────────
# Event log 驗證
# ─────────────────────────────────────────────────────────────────────────


def test_event_log_records_transitions(repo):
    """每個 transition 都應寫一筆 event log。"""
    from modules.workflow.repository.orm_models import WorkOrderEventLogORM
    from sqlalchemy import select

    actor = uuid4()
    wo = _make(repo, assignee_id=actor)
    repo.transition(wo.id, "dispatch", actor_id=actor)
    repo.transition(wo.id, "start_work")
    repo.transition(wo.id, "cancel", cancel_reason="測試")

    # 直接查 event log
    with repo._sessionmaker() as sess:
        stmt = select(WorkOrderEventLogORM).where(
            WorkOrderEventLogORM.work_order_id == str(wo.id)
        ).order_by(WorkOrderEventLogORM.id)
        events = list(sess.execute(stmt).scalars())

    # created + dispatch + start_work + cancel = 4 條
    assert len(events) == 4
    assert [e.event_type for e in events] == ["created", "dispatch", "start_work", "cancel"]
    # status transitions 紀錄
    assert events[1].from_status == "draft" and events[1].to_status == "dispatched"
    assert events[3].from_status == "in_progress" and events[3].to_status == "cancelled"


# ─────────────────────────────────────────────────────────────────────────
# UTC timestamp roundtrip
# ─────────────────────────────────────────────────────────────────────────


def test_timestamps_are_utc_after_roundtrip(repo):
    """SQLite DateTime roundtrip 後 _ensure_utc 補 tzinfo（fix #5）。"""
    wo = _make(repo)
    refetch = repo.get(wo.id)
    assert refetch.created_at.tzinfo is not None
    # offset 為 UTC（0）
    assert refetch.created_at.utcoffset().total_seconds() == 0


# ─────────────────────────────────────────────────────────────────────────
# UTC validation on write path（fix #2）
# ─────────────────────────────────────────────────────────────────────────


def test_apply_domain_to_orm_rejects_naive_datetime(repo):
    """fix #2：write 路徑強制 UTC-aware；naive datetime 應 raise ValueError。"""
    from datetime import datetime as dt
    from modules.workflow.repository.work_order_repository import (
        WorkOrderRepository,
    )

    wo = _make(repo)
    wo.dispatched_at = dt(2026, 5, 5, 10, 0, 0)  # naive
    with pytest.raises(ValueError, match="dispatched_at.*timezone-aware"):
        WorkOrderRepository._assert_utc("dispatched_at", wo.dispatched_at)


def test_apply_domain_to_orm_rejects_non_utc_offset():
    """non-UTC offset（如 +08:00）也應 raise（fix #2）。"""
    from datetime import datetime as dt, timezone, timedelta
    from modules.workflow.repository.work_order_repository import (
        WorkOrderRepository,
    )

    taipei = dt(2026, 5, 5, 18, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    with pytest.raises(ValueError, match="dispatched_at.*UTC"):
        WorkOrderRepository._assert_utc("dispatched_at", taipei)


# ─────────────────────────────────────────────────────────────────────────
# Business key collision retry（fix #1）
# ─────────────────────────────────────────────────────────────────────────


def test_business_key_collision_retried_then_unique(repo, monkeypatch):
    """fix #1：兩個 create 同 millisecond 算到同 NN，第一個 commit OK，第二個
    被 IntegrityError 攔下後 retry 取下一個 NN，得到 unique business_key。"""
    # 第一張正常
    a = _make(repo, source_alarm_code="A1")
    # 強制下次 _next_business_key 回 a 的 key（模擬同 NN race）
    original_next = repo._next_business_key
    call_count = {"n": 0}

    def fake_next(sess, farm_id):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return a.business_key  # 撞重複
        return original_next(sess, farm_id)

    monkeypatch.setattr(repo, "_next_business_key", fake_next)

    b = _make(repo, source_alarm_code="A2")
    # 第一次 IntegrityError → retry 取真正的下一個 NN
    assert b.business_key != a.business_key
    assert call_count["n"] == 2  # 確實 retry 了一次


def test_business_key_collision_after_retry_raises_business_rule(repo, monkeypatch):
    """連兩次都撞 → 回 BusinessRuleViolation（caller 拿到 409，非 500）。"""
    a = _make(repo, source_alarm_code="A1")
    monkeypatch.setattr(repo, "_next_business_key", lambda sess, farm_id: a.business_key)

    with pytest.raises(BusinessRuleViolation, match="business_key collision"):
        _make(repo, source_alarm_code="A2")
