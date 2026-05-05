"""SignoffRepository test — chain creation + approve / reject + pending list（WMOM-20260504-18）。"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.workflow.domain import (
    DEFAULT_WORK_ORDER_CHAIN,
    SignoffLevel,
    SignoffStatus,
    SignoffSubjectType,
    build_chain_levels,
    user_group_to_level,
)
from modules.workflow.repository import (
    SignoffActionError,
    SignoffRepository,
    get_signoff_repository,
)
from modules.workflow.repository.work_order_repository import (
    clear_engine_cache_for_test,
)


# ─────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def repo(tmp_path) -> SignoffRepository:
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")
    yield get_signoff_repository(db_path)
    clear_engine_cache_for_test()


# ─────────────────────────────────────────────────────────────────────────
# build_chain_levels / user_group_to_level
# ─────────────────────────────────────────────────────────────────────────


def test_build_chain_levels_work_order_default():
    levels = build_chain_levels(SignoffSubjectType.WORK_ORDER)
    assert levels == [SignoffLevel.EMPLOYEE, SignoffLevel.LEADER]


def test_build_chain_levels_material_request_default():
    levels = build_chain_levels(SignoffSubjectType.MATERIAL_REQUEST)
    assert levels == [
        SignoffLevel.EMPLOYEE,
        SignoffLevel.LEADER,
        SignoffLevel.TREASURY,
    ]


def test_build_chain_levels_escalate_to_supervisor():
    levels = build_chain_levels(
        SignoffSubjectType.WORK_ORDER, escalate_to_supervisor=True
    )
    assert levels == [
        SignoffLevel.EMPLOYEE,
        SignoffLevel.LEADER,
        SignoffLevel.SUPERVISOR,
    ]


def test_build_chain_levels_disabled_level():
    """farm config 關掉 LEADER → chain 只剩 EMPLOYEE。"""
    levels = build_chain_levels(
        SignoffSubjectType.WORK_ORDER,
        farm_config={"signoff_disabled_levels": [SignoffLevel.LEADER]},
    )
    assert levels == [SignoffLevel.EMPLOYEE]


def test_build_chain_levels_disabled_accepts_string_list():
    """review fix #11：disabled 從 JSON 來時是 list[str]，應自動 coerce 為 SignoffLevel。"""
    levels = build_chain_levels(
        SignoffSubjectType.WORK_ORDER,
        farm_config={"signoff_disabled_levels": ["leader"]},
    )
    assert levels == [SignoffLevel.EMPLOYEE]


def test_build_chain_levels_all_disabled_raises():
    """review fix #3：farm config 把所有 default level 都關 → ValueError（不 silent fallback）。"""
    with pytest.raises(ValueError, match="不可關閉所有層級"):
        build_chain_levels(
            SignoffSubjectType.WORK_ORDER,
            farm_config={"signoff_disabled_levels": [
                SignoffLevel.EMPLOYEE, SignoffLevel.LEADER,
            ]},
        )


def test_build_chain_levels_escalate_idempotent():
    """SUPERVISOR 已在 chain → escalate 不重複加。"""
    levels = build_chain_levels(
        SignoffSubjectType.WORK_ORDER,
        farm_config={
            "signoff_disabled_levels": []
        },
        escalate_to_supervisor=True,
    )
    assert levels.count(SignoffLevel.SUPERVISOR) == 1


@pytest.mark.parametrize("group,level", [
    (100, SignoffLevel.EMPLOYEE),
    (300, SignoffLevel.LEADER),
    (500, SignoffLevel.SUPERVISOR),
    (666, SignoffLevel.TREASURY),
])
def test_user_group_to_level(group, level):
    assert user_group_to_level(group) == level


def test_user_group_to_level_unknown():
    assert user_group_to_level(999) is None  # 系統管理員不屬簽核角色


# ─────────────────────────────────────────────────────────────────────────
# create_chain_for_work_order
# ─────────────────────────────────────────────────────────────────────────


def test_create_chain_for_work_order_default(repo):
    wo_id = uuid4()
    chain = repo.create_chain_for_work_order(
        work_order_id=wo_id, farm_id="台中港曲風場"
    )
    assert chain.subject_type == SignoffSubjectType.WORK_ORDER
    assert chain.subject_id == wo_id
    assert chain.farm_id == "台中港曲風場"
    assert chain.levels == [SignoffLevel.EMPLOYEE, SignoffLevel.LEADER]
    assert chain.current_level_index == 0
    assert chain.overall_status == SignoffStatus.PENDING

    steps = repo.get_steps(chain.id)
    assert len(steps) == 2
    assert [s.level for s in steps] == [SignoffLevel.EMPLOYEE, SignoffLevel.LEADER]
    assert all(s.status == SignoffStatus.PENDING for s in steps)


def test_create_chain_with_escalate(repo):
    wo_id = uuid4()
    chain = repo.create_chain_for_work_order(
        work_order_id=wo_id, farm_id="x", escalate_to_supervisor=True
    )
    assert chain.levels == [
        SignoffLevel.EMPLOYEE,
        SignoffLevel.LEADER,
        SignoffLevel.SUPERVISOR,
    ]


def test_get_chain_for_subject_returns_latest(repo, monkeypatch):
    """若同一 work_order reject 後重送會有多個 chain，取最新的。

    review fix #5+#13：原本 sleep(0.01) 是 timing-dependent；改 monkey-patch
    ``_utc_now`` 給確定不同時間，避免 CI scheduler granularity 撞到。
    取「started_at desc, id desc」雙 sort 確保 latest 穩定。
    """
    from datetime import datetime, timedelta, timezone
    from modules.workflow.repository import signoff_repository as sg_mod

    base_time = datetime(2026, 5, 5, 12, 0, 0, tzinfo=timezone.utc)
    times = [base_time, base_time + timedelta(seconds=10)]
    idx = {"i": 0}

    def fake_now():
        t = times[min(idx["i"], len(times) - 1)]
        idx["i"] += 1
        return t

    monkeypatch.setattr(sg_mod, "_utc_now", fake_now)

    wo_id = uuid4()
    a = repo.create_chain_for_work_order(work_order_id=wo_id, farm_id="x")
    b = repo.create_chain_for_work_order(work_order_id=wo_id, farm_id="x")

    latest = repo.get_chain_for_subject(SignoffSubjectType.WORK_ORDER, wo_id)
    assert latest is not None
    # b 的 started_at 比 a 晚 10s — latest 必是 b
    assert latest.id == b.id


# ─────────────────────────────────────────────────────────────────────────
# approve_step / reject_step
# ─────────────────────────────────────────────────────────────────────────


def test_approve_first_step_advances_chain(repo):
    actor = uuid4()
    chain = repo.create_chain_for_work_order(
        work_order_id=uuid4(), farm_id="x"
    )
    step1 = repo.get_steps(chain.id)[0]

    updated, is_last = repo.approve_step(step1.id, actor_id=actor, comment="ok")
    assert is_last is False  # 還有第 2 階
    assert updated.current_level_index == 1
    assert updated.overall_status == SignoffStatus.PENDING

    # step1 變 APPROVED
    steps = repo.get_steps(chain.id)
    assert steps[0].status == SignoffStatus.APPROVED
    assert steps[0].decided_by == actor
    assert steps[0].comment == "ok"
    assert steps[1].status == SignoffStatus.PENDING


def test_approve_last_step_completes_chain(repo):
    actor = uuid4()
    chain = repo.create_chain_for_work_order(
        work_order_id=uuid4(), farm_id="x"
    )
    steps = repo.get_steps(chain.id)
    repo.approve_step(steps[0].id, actor_id=actor)

    updated, is_last = repo.approve_step(steps[1].id, actor_id=actor)
    assert is_last is True
    assert updated.overall_status == SignoffStatus.APPROVED
    assert updated.completed_at is not None


def test_reject_first_step_terminates_chain(repo):
    actor = uuid4()
    chain = repo.create_chain_for_work_order(
        work_order_id=uuid4(), farm_id="x"
    )
    step1 = repo.get_steps(chain.id)[0]

    updated = repo.reject_step(step1.id, actor_id=actor, reason="缺照片")
    assert updated.overall_status == SignoffStatus.REJECTED
    assert updated.rejected_at_level == SignoffLevel.EMPLOYEE
    assert updated.rejected_reason == "缺照片"
    assert updated.completed_at is not None

    # step1 → REJECTED；step2 仍 PENDING（不再走）
    steps = repo.get_steps(chain.id)
    assert steps[0].status == SignoffStatus.REJECTED
    assert steps[1].status == SignoffStatus.PENDING


def test_cannot_approve_step_after_chain_terminal(repo):
    actor = uuid4()
    chain = repo.create_chain_for_work_order(
        work_order_id=uuid4(), farm_id="x"
    )
    steps = repo.get_steps(chain.id)
    repo.reject_step(steps[0].id, actor_id=actor, reason="x")

    # chain 已 REJECTED
    with pytest.raises(SignoffActionError, match="already rejected"):
        repo.approve_step(steps[1].id, actor_id=actor)


def test_cannot_skip_levels(repo):
    """對非當前 level 的 step approve → 錯誤。"""
    actor = uuid4()
    chain = repo.create_chain_for_work_order(
        work_order_id=uuid4(), farm_id="x"
    )
    steps = repo.get_steps(chain.id)
    # 直接 approve step 2（chain.current_level_index=0）
    with pytest.raises(SignoffActionError, match="not the current step"):
        repo.approve_step(steps[1].id, actor_id=actor)


def test_cannot_re_decide_step(repo):
    """已 approved 的 step 不可再被 approve / reject。"""
    actor = uuid4()
    chain = repo.create_chain_for_work_order(
        work_order_id=uuid4(), farm_id="x"
    )
    steps = repo.get_steps(chain.id)
    repo.approve_step(steps[0].id, actor_id=actor)

    with pytest.raises(SignoffActionError, match="already approved"):
        repo.approve_step(steps[0].id, actor_id=actor)


def test_reject_requires_reason(repo):
    chain = repo.create_chain_for_work_order(
        work_order_id=uuid4(), farm_id="x"
    )
    step = repo.get_steps(chain.id)[0]
    with pytest.raises(SignoffActionError, match="non-empty reason"):
        repo.reject_step(step.id, actor_id=uuid4(), reason="")


def test_step_with_parallel_group_id_raises_not_implemented(repo):
    """review fix #6：parallel_group_id 是 D2-Q4 預留欄位，現階段未實作。

    若 step 帶非 None parallel_group_id（理論上 _create_chain 不會設，但人工塞測試），
    approve / reject 應該 fail loudly 而非靜默走序列邏輯。
    """
    from sqlalchemy import update
    from modules.workflow.repository.orm_models import SignoffStepORM

    chain = repo.create_chain_for_work_order(work_order_id=uuid4(), farm_id="x")
    steps = repo.get_steps(chain.id)
    # 直接 SQL 把 step 設 parallel_group_id（模擬未來不正當配置）
    with repo._sessionmaker() as sess:
        sess.execute(update(SignoffStepORM)
                    .where(SignoffStepORM.id == str(steps[0].id))
                    .values(parallel_group_id=str(uuid4())))
        sess.commit()

    with pytest.raises(NotImplementedError, match="parallel signoff is not implemented"):
        repo.approve_step(steps[0].id, actor_id=uuid4())


# ─────────────────────────────────────────────────────────────────────────
# pending list query
# ─────────────────────────────────────────────────────────────────────────


def test_list_pending_only_returns_current_step(repo):
    """應只回 chain.current_level_index 對應的 step。"""
    actor = uuid4()
    repo.create_chain_for_work_order(work_order_id=uuid4(), farm_id="x")  # chain A
    chain_b = repo.create_chain_for_work_order(work_order_id=uuid4(), farm_id="x")
    # 把 chain_b 第一階 approve 掉，current_level_index 進 1
    steps_b = repo.get_steps(chain_b.id)
    repo.approve_step(steps_b[0].id, actor_id=actor)

    # 現在 EMPLOYEE 待簽：只有 chain A 的 step1（chain_b 已過 EMPLOYEE 階段）
    # review fix #6：list_pending_for_level 回 (items, total)
    employee_pending, employee_total = repo.list_pending_for_level(
        farm_id="x", level=SignoffLevel.EMPLOYEE
    )
    assert len(employee_pending) == 1
    assert employee_total == 1

    leader_pending, leader_total = repo.list_pending_for_level(
        farm_id="x", level=SignoffLevel.LEADER
    )
    assert leader_total == 1
    # chain_b 的 leader step 才會出現
    assert leader_pending[0][1].id == chain_b.id


def test_list_pending_excludes_terminal_chain(repo):
    """已 reject 的 chain 不應出現在 pending list。"""
    actor = uuid4()
    chain = repo.create_chain_for_work_order(
        work_order_id=uuid4(), farm_id="x"
    )
    repo.reject_step(
        repo.get_steps(chain.id)[0].id,
        actor_id=actor, reason="X",
    )

    pending, total = repo.list_pending_for_level(
        farm_id="x", level=SignoffLevel.EMPLOYEE
    )
    assert pending == []
    assert total == 0


def test_list_pending_filters_by_farm(repo):
    repo.create_chain_for_work_order(work_order_id=uuid4(), farm_id="A")
    repo.create_chain_for_work_order(work_order_id=uuid4(), farm_id="B")

    a_pending, a_total = repo.list_pending_for_level(
        farm_id="A", level=SignoffLevel.EMPLOYEE
    )
    b_pending, b_total = repo.list_pending_for_level(
        farm_id="B", level=SignoffLevel.EMPLOYEE
    )
    assert (a_total, b_total) == (1, 1)
    assert a_pending[0][1].farm_id == "A"


def test_list_pending_real_total_unaffected_by_limit(repo):
    """review fix #6：list 回的 total 是真實 DB count（不受 limit 截斷）。"""
    actor = uuid4()
    for _ in range(5):
        repo.create_chain_for_work_order(work_order_id=uuid4(), farm_id="x")

    items, total = repo.list_pending_for_level(
        farm_id="x", level=SignoffLevel.EMPLOYEE, limit=2,
    )
    assert len(items) == 2
    assert total == 5


def test_list_pending_offset_pagination(repo):
    """review fix #11：offset 跳過前 N 筆。"""
    actor = uuid4()
    chains = [
        repo.create_chain_for_work_order(work_order_id=uuid4(), farm_id="x")
        for _ in range(3)
    ]

    # offset=1 跳第一個
    items_off, total = repo.list_pending_for_level(
        farm_id="x", level=SignoffLevel.EMPLOYEE, limit=10, offset=1,
    )
    assert total == 3
    assert len(items_off) == 2  # 跳掉一個


def test_list_pending_subject_type_filter(repo):
    """review fix #12：subject_type filter — M4 領料單上線後預留。

    M3 還沒 material_request domain，本 test 直接 SQL 塞一個 subject_type=
    material_request 的 chain，驗 filter 能區分。
    """
    from sqlalchemy import insert
    from modules.workflow.repository.orm_models import SignoffChainORM, SignoffStepORM
    from datetime import datetime, timezone
    import json
    from uuid import uuid4 as _uuid4

    # 先建一個正常 work_order chain
    repo.create_chain_for_work_order(work_order_id=uuid4(), farm_id="x")

    # 直接塞一個 material_request chain（M3 schema 已預留）
    with repo._sessionmaker() as sess:
        mr_chain_id = str(_uuid4())
        mr_step_id = str(_uuid4())
        now = datetime.now(tz=timezone.utc)
        sess.add(SignoffChainORM(
            id=mr_chain_id,
            subject_type="material_request",
            subject_id=str(_uuid4()),
            farm_id="x",
            levels_json=json.dumps(["employee", "leader", "treasury"]),
            current_level_index=0,
            overall_status="pending",
            started_at=now,
        ))
        sess.add(SignoffStepORM(
            id=mr_step_id,
            chain_id=mr_chain_id,
            level="employee",
            sequence=0,
            status="pending",
            created_at=now,
        ))
        sess.commit()

    # 不 filter — 兩個都看到
    _, total_all = repo.list_pending_for_level(
        farm_id="x", level=SignoffLevel.EMPLOYEE
    )
    assert total_all == 2

    # filter work_order — 只看到一個
    _, total_wo = repo.list_pending_for_level(
        farm_id="x", level=SignoffLevel.EMPLOYEE,
        subject_type=SignoffSubjectType.WORK_ORDER,
    )
    assert total_wo == 1


# ─────────────────────────────────────────────────────────────────────────
# History audit log
# ─────────────────────────────────────────────────────────────────────────


def test_history_records_chain_lifecycle(repo):
    """chain_created + step_approved + step_approved + chain_completed = 4 條 history。"""
    from modules.workflow.repository.orm_models import SignoffHistoryORM
    from sqlalchemy import select

    actor = uuid4()
    chain = repo.create_chain_for_work_order(
        work_order_id=uuid4(), farm_id="x"
    )
    steps = repo.get_steps(chain.id)
    repo.approve_step(steps[0].id, actor_id=actor)
    repo.approve_step(steps[1].id, actor_id=actor)

    with repo._sessionmaker() as sess:
        events = list(sess.execute(
            select(SignoffHistoryORM)
            .where(SignoffHistoryORM.chain_id == str(chain.id))
            .order_by(SignoffHistoryORM.id)
        ).scalars())

    types = [e.event_type for e in events]
    assert types == ["chain_created", "step_approved", "step_approved", "chain_completed"]


def test_history_records_reject(repo):
    from modules.workflow.repository.orm_models import SignoffHistoryORM
    from sqlalchemy import select

    actor = uuid4()
    chain = repo.create_chain_for_work_order(work_order_id=uuid4(), farm_id="x")
    repo.reject_step(
        repo.get_steps(chain.id)[0].id,
        actor_id=actor, reason="缺照片",
    )

    with repo._sessionmaker() as sess:
        events = list(sess.execute(
            select(SignoffHistoryORM)
            .where(SignoffHistoryORM.chain_id == str(chain.id))
            .order_by(SignoffHistoryORM.id)
        ).scalars())

    types = [e.event_type for e in events]
    assert types == ["chain_created", "step_rejected", "chain_completed"]
