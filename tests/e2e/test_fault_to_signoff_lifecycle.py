"""**WMOM-20260509-10 — E2E fault → signoff full lifecycle test**.

把整條 demo flow（建工單 → 派工 → 領料簽核 → 庫存扣帳 → 完工 → ledger confirm →
工單簽核 → CLOSED）一次串起來測，避免 2026-05-10 那種 hotfix 風暴重演。

涵蓋：
- **Happy paths**（3 條）：CORRECTIVE（alarm-driven）/ PREVENTIVE / INSPECTION
- **Unhappy paths**（2 條）：
    A. signoff reject → retry path（WO 第二階 leader reject → 回 IN_PROGRESS →
       重新 finish → 新 chain → 重新 approve → CLOSED）
    B. dispatch under insufficient stock（MR 完成 3 階 approve 後 final approve
       回 200 但帶 ``transition_error="insufficient stock..."`` — MR 留 APPROVED
       不進 DISPATCHED；stock 不變）

Mock 範圍：A10 issue 原始描述含「啟動 simulator + 注入 fault scenario」— 真接
simulator 牽涉 monitoring module 跨層整合（M5 才做）；今日把那段 mock 成「建立
corrective WO 時帶 source_alarm_code」。Follow-up：WMOM-20260513-02。
"""

from __future__ import annotations

import time
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# repo root path setup 由 tests/e2e/conftest.py 統一處理；此模組不重複 sys.path.insert

from modules.cost.repository import (
    CostLedgerCategory,
    CostLedgerSourceType,
    CostLedgerStatus,
    get_cost_ledger_repository,
)
from modules.workflow.domain import (
    FollowupKind,
    Priority,
    SignoffStatus,
    SignoffSubjectType,
    WorkOrder,
    WorkOrderStatus,
    WorkOrderType,
)
from modules.workflow.domain.inventory import StockKind
from modules.workflow.repository import (
    get_inventory_repository,
    get_material_request_repository,
    get_repository,
    get_signoff_repository,
)
from modules.workflow.repository.work_order_repository import (
    clear_engine_cache_for_test,
)
from modules.workflow.routers import (
    approval_router,
    inventory_router,
    material_request_router,
    router as workflow_router,
)
from modules.workflow.routers.approval_router import set_signoff_factories
from modules.workflow.routers.inventory_router import set_inventory_factory
from modules.workflow.routers.material_request_router import (
    set_material_request_factories,
)
from modules.workflow.routers.work_order_router import (
    set_finish_hook_db_path,
    set_repository_factory,
)


FARM_ID = "changhua"
TURBINE_ID = "WT001"
ITEM_SKU = "GBR-001"
ITEM_UNIT_COST = Decimal("450.00")


# ─────────────────────────────────────────────────────────────────────────
# Fixture：完整 workflow stack + 預建 farm / warehouse / item
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def e2e_setup(tmp_path):
    """完整 E2E 環境：4 個 router + 共用 db_path + 庫存 stock_new=10。"""
    clear_engine_cache_for_test()
    db_path = str(tmp_path / "wind_farm.db")

    def wo_factory(_: str):
        return get_repository(db_path)

    def sg_factory(_: str):
        return get_signoff_repository(db_path)

    def mr_factory(_: str):
        return get_material_request_repository(db_path)

    def inv_factory(_: str):
        return get_inventory_repository(db_path)

    set_repository_factory(wo_factory)
    set_signoff_factories(sg_factory, wo_factory, mr_factory)
    set_material_request_factories(mr_factory, sg_factory)
    set_inventory_factory(inv_factory)
    set_finish_hook_db_path(db_path)

    app = FastAPI(title="e2e-lifecycle-test")
    app.include_router(workflow_router)
    app.include_router(approval_router)
    app.include_router(material_request_router)
    app.include_router(inventory_router)
    client = TestClient(app)

    inv_repo = get_inventory_repository(db_path)
    wh = inv_repo.create_warehouse(
        farm_id=FARM_ID, name="main-warehouse", is_default=True
    )
    item = inv_repo.create_item(
        sku=ITEM_SKU,
        name="Gearbox bearing",
        description="Z72 main shaft",
        unit="piece",
        farm_id=FARM_ID,
        warehouse_id=wh.id,
        unit_cost=ITEM_UNIT_COST,
        stock_new=10,
    )

    yield {
        "client": client,
        "db_path": db_path,
        "item_id": item.id,
        "warehouse_id": wh.id,
        "inv_repo": inv_repo,
        "ledger_repo": get_cost_ledger_repository(db_path),
        "wo_repo": get_repository(db_path),
        "sg_repo": get_signoff_repository(db_path),
    }

    # teardown：3 個 factory 參數對稱清空（與 setup 帶 3 個對齊）
    set_repository_factory(None)
    set_signoff_factories(None, None, None)
    set_material_request_factories(None, None)
    set_inventory_factory(None)
    set_finish_hook_db_path(None)
    clear_engine_cache_for_test()


# ─────────────────────────────────────────────────────────────────────────
# Helpers — chain approval / lifecycle macros
# ─────────────────────────────────────────────────────────────────────────


def _approve_chain(
    client: TestClient,
    chain_id: str,
    levels: tuple[str, ...],
    actor_id: str | None = None,
) -> dict:
    """依序 approve 每一階；回最後一階 approve response（含 transition_error）。

    WMOM-20260510-01 Part A：separation-of-duties → 每階用不同 actor（除非 caller
    傳 ``actor_id`` 強制單一 actor，用於 only-1-level 場景如 reject-retry 的 employee 階）。
    """
    last_resp: dict = {}
    for level in levels:
        actor = actor_id if actor_id is not None else str(uuid4())
        pending = client.get(
            "/api/workflow/approvals/pending",
            params={"farm_id": FARM_ID, "level": level},
        ).json()
        step = next(
            (it for it in pending["items"] if it["chain"]["id"] == chain_id),
            None,
        )
        assert step is not None, (
            f"no pending step found for chain={chain_id} level={level}; "
            f"all pending={pending['items']}"
        )
        resp = client.post(
            f"/api/workflow/approvals/{step['step']['id']}/approve",
            params={"farm_id": FARM_ID},
            json={"actor_id": actor, "comment": f"approve {level}"},
        )
        assert resp.status_code == 200, resp.text
        last_resp = resp.json()
    return last_resp


def _reject_chain_at_level(
    client: TestClient,
    chain_id: str,
    level: str,
    reason: str,
    actor_id: str | None = None,
) -> dict:
    """在指定 level 階駁回；caller 須先 approve 前面所有 level。"""
    actor = actor_id or str(uuid4())
    pending = client.get(
        "/api/workflow/approvals/pending",
        params={"farm_id": FARM_ID, "level": level},
    ).json()
    step = next(
        (it for it in pending["items"] if it["chain"]["id"] == chain_id), None
    )
    assert step is not None, f"no pending step at level={level} for chain={chain_id}"
    resp = client.post(
        f"/api/workflow/approvals/{step['step']['id']}/reject",
        params={"farm_id": FARM_ID},
        json={"actor_id": actor, "reason": reason},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_work_order(
    wo_repo,
    *,
    wo_type: WorkOrderType,
    priority: Priority = Priority.NORMAL,
    title: str = "test wo",
    source_alarm_code: str | None = None,
    actor: UUID | None = None,
) -> WorkOrder:
    """建工單 + 預設 actor（建單者 = assignee）。回 domain object。

    Note: ``source_alarm_code`` 目前是純字串 placeholder（mock simulator fault
    trigger）；M5 整合 monitoring layer 時要替換成 canonical Z72 alarm schema
    （見 ``modules/monitoring/simulator/physics/fault_engine.py`` 的 ``T1/T2/A`` 結構），
    並抽 shared constant 給 test + monitoring 共用 — follow-up: WMOM-20260513-02。
    """
    actor = actor or uuid4()
    return wo_repo.create(
        farm_id=FARM_ID,
        turbine_id=TURBINE_ID,
        type=wo_type,
        title=title,
        description="E2E lifecycle test",
        priority=priority,
        source_alarm_code=source_alarm_code,
        assignee_id=actor,
        crew_size=2,
        estimated_hours=4.0,
        created_by=actor,
    )


def _submit_material_request(
    client: TestClient,
    *,
    wo_id: UUID,
    item_id: UUID,
    estimated_qty: int,
    actor: UUID,
) -> dict:
    """建 MR + submit-for-approval。回 ``{"mr": ..., "chain_id": ...}``。"""
    create_resp = client.post(
        "/api/workflow/material-requests",
        json={
            "farm_id": FARM_ID,
            "requester_id": str(actor),
            "items": [
                {
                    "item_id": str(item_id),
                    "estimated_qty": estimated_qty,
                    "stock_kind": "new",
                },
            ],
            "work_order_id": str(wo_id),
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    mr = create_resp.json()

    submit = client.post(
        f"/api/workflow/material-requests/{mr['id']}/submit-for-approval",
        params={"farm_id": FARM_ID},
        json={"actor_id": str(actor)},
    )
    assert submit.status_code == 200, submit.text
    return {"mr": mr, "chain_id": submit.json()["signoff_chain_id"]}


def _walk_happy_lifecycle(
    setup: dict,
    *,
    wo_type: WorkOrderType,
    priority: Priority = Priority.NORMAL,
    source_alarm_code: str | None = None,
    estimated_qty: int = 2,
    actual_qty: int = 2,
) -> dict:
    """完整 happy lifecycle：建單 → dispatch → start → MR → 3 階 → receive → finish →
    WO 自動建 chain → 2 階 approve → CLOSED。回完整 step trail。"""
    client = setup["client"]
    wo_repo = setup["wo_repo"]
    sg_repo = setup["sg_repo"]
    actor = uuid4()

    # ── Step 1-2：建工單 + dispatch + start_work ──
    wo = _create_work_order(
        wo_repo,
        wo_type=wo_type,
        priority=priority,
        title=f"{wo_type.value} lifecycle",
        source_alarm_code=source_alarm_code,
        actor=actor,
    )
    wo_repo.transition(wo.id, "dispatch", actor_id=actor)
    wo_repo.transition(wo.id, "start_work")

    # ── Step 3：建 MR + 3 階 approve ──
    mr_bundle = _submit_material_request(
        client,
        wo_id=wo.id,
        item_id=setup["item_id"],
        estimated_qty=estimated_qty,
        actor=actor,
    )
    pre_stock = setup["inv_repo"].get_item(setup["item_id"]).stock_new
    final_approve = _approve_chain(
        client, mr_bundle["chain_id"], ("employee", "leader", "treasury"),
    )

    # ── 中間狀態驗證（A10 核心：擋 dispatch guard / atomic 雙寫 regression）──
    # 3 階 approve 完成後，approval_router 自動觸發 mr.dispatch_request →
    # MR 進 DISPATCHED + stock 扣 estimated_qty + ledger 建 ESTIMATED entry
    assert final_approve["chain_completed"] is True
    assert final_approve["subject_status_changed"] is True, (
        f"3 階 approve 後 MR 應自動 dispatch；transition_error="
        f"{final_approve.get('subject_transition_error')}"
    )
    mid_mr = client.get(
        f"/api/workflow/material-requests/{mr_bundle['mr']['id']}",
        params={"farm_id": FARM_ID},
    ).json()
    assert mid_mr["status"] == "dispatched", (
        f"3 階 approve 後 MR 應進 DISPATCHED，got {mid_mr['status']}"
    )
    mid_stock = setup["inv_repo"].get_item(setup["item_id"]).stock_new
    assert mid_stock == pre_stock - estimated_qty, (
        f"dispatch 後 stock 應扣 {estimated_qty}：{pre_stock} → "
        f"{pre_stock - estimated_qty}，got {mid_stock}"
    )
    mid_entries, mid_total = setup["ledger_repo"].list(farm_id=FARM_ID)
    assert mid_total == 1, f"dispatch 後應有 1 筆 ledger entry，got {mid_total}"
    mid_entry = mid_entries[0]
    assert mid_entry.status is CostLedgerStatus.ESTIMATED, (
        f"dispatch 完成尚未 finish — ledger 應留 ESTIMATED，got {mid_entry.status}"
    )
    assert mid_entry.amount == Decimal(estimated_qty) * ITEM_UNIT_COST

    # ── Step 4：receive MR ──
    fresh_mr = client.get(
        f"/api/workflow/material-requests/{mr_bundle['mr']['id']}",
        params={"farm_id": FARM_ID},
    ).json()
    receive_resp = client.post(
        f"/api/workflow/material-requests/{fresh_mr['id']}/receive",
        params={"farm_id": FARM_ID},
        json={
            "actor_id": str(actor),
            "actual_quantities": {fresh_mr["items"][0]["id"]: actual_qty},
        },
    )
    assert receive_resp.status_code == 200, receive_resp.text

    # ── Step 5：finish WO → auto-build WO signoff chain ──
    finish_resp = client.post(
        f"/api/workflow/work-orders/{wo.id}/finish",
        params={"farm_id": FARM_ID},
        json={
            "actual_hours": 3.5,
            "followup_kind": FollowupKind.NONE.value,
            "work_summary": "E2E lifecycle work summary",
        },
    )
    assert finish_resp.status_code == 200, finish_resp.text

    # ── Step 6：WO chain approve 2 階 → CLOSED ──
    wo_chain = sg_repo.get_chain_for_subject(
        SignoffSubjectType.WORK_ORDER, wo.id,
    )
    assert wo_chain is not None, "WO finish 應該自動建 signoff chain"
    # WMOM-20260510-01 Part A：每階用不同 actor（不再強制 actor=作業員 actor）
    wo_final = _approve_chain(
        client, str(wo_chain.id), ("employee", "leader"),
    )

    return {
        "wo_id": wo.id,
        "mr_id": fresh_mr["id"],
        "mr_chain_id": mr_bundle["chain_id"],
        "wo_chain_id": str(wo_chain.id),
        "final_mr_approve": final_approve,
        "final_wo_approve": wo_final,
        "actor": actor,
    }


# ─────────────────────────────────────────────────────────────────────────
# Happy path 1：CORRECTIVE（alarm-driven）
# ─────────────────────────────────────────────────────────────────────────


def test_corrective_alarm_to_signoff_full_lifecycle(e2e_setup):
    """
    完整鏈路：alarm 觸發（mock source_alarm_code）→ 建 corrective WO →
    派工 → 開始 → 領料簽核（3 階）→ 庫存扣帳 → receive → finish →
    工單簽核（2 階）→ CLOSED。
    """
    setup = e2e_setup
    trail = _walk_happy_lifecycle(
        setup,
        wo_type=WorkOrderType.CORRECTIVE,
        priority=Priority.HIGH,
        source_alarm_code="GBT_TEMP_HIGH",
        estimated_qty=2,
        actual_qty=2,
    )

    wo = setup["wo_repo"].get(trail["wo_id"])
    assert wo is not None
    assert wo.status is WorkOrderStatus.CLOSED
    assert wo.source_alarm_code == "GBT_TEMP_HIGH"
    assert wo.type is WorkOrderType.CORRECTIVE

    wo_chain = setup["sg_repo"].get_chain(UUID(trail["wo_chain_id"]))
    assert wo_chain is not None
    assert wo_chain.overall_status is SignoffStatus.APPROVED

    mr_chain = setup["sg_repo"].get_chain(UUID(trail["mr_chain_id"]))
    assert mr_chain is not None
    assert mr_chain.overall_status is SignoffStatus.APPROVED

    # 庫存：10 - 2 = 8（atomic dispatch 扣的）
    assert setup["inv_repo"].get_item(setup["item_id"]).stock_new == 8

    # Ledger：1 entry CONFIRMED，amount = 2 × 450 = 900
    entries, total = setup["ledger_repo"].list(farm_id=FARM_ID)
    assert total == 1
    e = entries[0]
    assert e.status is CostLedgerStatus.CONFIRMED
    assert e.amount == Decimal("900.00")
    assert e.source_type is CostLedgerSourceType.MATERIAL_REQUEST
    assert e.category is CostLedgerCategory.MATERIAL


# ─────────────────────────────────────────────────────────────────────────
# Happy path 2：PREVENTIVE（計畫性維護，無告警）
# ─────────────────────────────────────────────────────────────────────────


def test_preventive_planned_full_lifecycle(e2e_setup):
    """PREVENTIVE 工單沒有 source_alarm_code（計畫性）；其餘 lifecycle 同 CORRECTIVE。"""
    setup = e2e_setup
    trail = _walk_happy_lifecycle(
        setup,
        wo_type=WorkOrderType.PREVENTIVE,
        priority=Priority.NORMAL,
        source_alarm_code=None,
        estimated_qty=1,
        actual_qty=1,
    )

    wo = setup["wo_repo"].get(trail["wo_id"])
    assert wo is not None
    assert wo.status is WorkOrderStatus.CLOSED
    assert wo.type is WorkOrderType.PREVENTIVE
    assert wo.source_alarm_code is None  # 計畫性無告警

    # 庫存：10 - 1 = 9
    assert setup["inv_repo"].get_item(setup["item_id"]).stock_new == 9

    # Ledger amount = 1 × 450 = 450 confirmed
    entries, _ = setup["ledger_repo"].list(farm_id=FARM_ID)
    assert len(entries) == 1
    assert entries[0].status is CostLedgerStatus.CONFIRMED
    assert entries[0].amount == Decimal("450.00")


# ─────────────────────────────────────────────────────────────────────────
# Happy path 3：INSPECTION（巡檢，actual == estimated 基準路徑）
# ─────────────────────────────────────────────────────────────────────────


def test_inspection_same_qty_lifecycle(e2e_setup):
    """INSPECTION 工單 estimated=actual=1 基準 happy path。

    TODO(WMOM-20260513-02)：另加 ``test_inspection_actual_exceeds_estimated``
    變體驗證「receive 超出 dispatch 量」的業務規則（cap at estimated vs allow
    over-use），目前 receive endpoint 未定義 cap 行為 — 等 product decision。
    """
    setup = e2e_setup
    trail = _walk_happy_lifecycle(
        setup,
        wo_type=WorkOrderType.INSPECTION,
        priority=Priority.LOW,
        source_alarm_code=None,
        estimated_qty=1,
        actual_qty=1,
    )

    wo = setup["wo_repo"].get(trail["wo_id"])
    assert wo is not None
    assert wo.status is WorkOrderStatus.CLOSED
    assert wo.type is WorkOrderType.INSPECTION
    assert wo.priority is Priority.LOW

    # 庫存：10 - 1 = 9
    assert setup["inv_repo"].get_item(setup["item_id"]).stock_new == 9

    # Ledger 1 entry CONFIRMED，amount = 1 × 450 = 450
    entries, _ = setup["ledger_repo"].list(farm_id=FARM_ID)
    assert len(entries) == 1
    assert entries[0].status is CostLedgerStatus.CONFIRMED
    assert entries[0].amount == Decimal("450.00")


# ─────────────────────────────────────────────────────────────────────────
# Unhappy path A：WO signoff reject → retry → CLOSED
# ─────────────────────────────────────────────────────────────────────────


def test_wo_signoff_reject_then_resubmit_to_closed(e2e_setup):
    """
    WO finish → chain step 1 (employee) approve → step 2 (leader) **reject** →
    WO 回 IN_PROGRESS → 重新 finish → 新 chain → 2 階 approve → CLOSED。
    驗 DB 內有 2 個 chain（first REJECTED + second APPROVED）。
    """
    setup = e2e_setup
    client = setup["client"]
    wo_repo = setup["wo_repo"]
    sg_repo = setup["sg_repo"]
    actor = uuid4()

    # 建 + dispatch + start
    wo = _create_work_order(
        wo_repo,
        wo_type=WorkOrderType.CORRECTIVE,
        priority=Priority.NORMAL,
        title="reject-retry test",
        actor=actor,
    )
    wo_repo.transition(wo.id, "dispatch", actor_id=actor)
    wo_repo.transition(wo.id, "start_work")

    # 不領料簡化，直接 finish
    finish_resp = client.post(
        f"/api/workflow/work-orders/{wo.id}/finish",
        params={"farm_id": FARM_ID},
        json={
            "actual_hours": 2.0,
            "followup_kind": FollowupKind.NONE.value,
            "work_summary": "first attempt",
        },
    )
    assert finish_resp.status_code == 200, finish_resp.text

    # Approve employee step（第一階先通過，用 helper 確保 HTTP status assertion）
    first_chain = sg_repo.get_chain_for_subject(SignoffSubjectType.WORK_ORDER, wo.id)
    assert first_chain is not None
    _approve_chain(client, str(first_chain.id), ("employee",), actor_id=str(actor))

    # Leader step reject → WO 回 IN_PROGRESS
    reject_resp = _reject_chain_at_level(
        client, str(first_chain.id), "leader",
        reason="work summary 不完整，請補拆解步驟",
    )
    assert reject_resp["subject_status_changed"] is True
    wo_after_reject = wo_repo.get(wo.id)
    assert wo_after_reject is not None
    assert wo_after_reject.status is WorkOrderStatus.IN_PROGRESS
    assert wo_after_reject.reject_reason == "work summary 不完整，請補拆解步驟"

    # 重新 finish → 自動建新 chain
    finish_resp_2 = client.post(
        f"/api/workflow/work-orders/{wo.id}/finish",
        params={"farm_id": FARM_ID},
        json={
            "actual_hours": 2.5,
            "followup_kind": FollowupKind.NONE.value,
            "work_summary": "retry: gearbox bearing replaced, vibration checked, recordings attached",
        },
    )
    assert finish_resp_2.status_code == 200, finish_resp_2.text

    # 新 chain = 不同 chain_id
    second_chain = sg_repo.get_chain_for_subject(SignoffSubjectType.WORK_ORDER, wo.id)
    assert second_chain is not None
    assert second_chain.id != first_chain.id, "重新 finish 應建新 chain，非 reuse"

    # 2 階 approve → CLOSED
    _approve_chain(client, str(second_chain.id), ("employee", "leader"))

    wo_closed = wo_repo.get(wo.id)
    assert wo_closed is not None
    assert wo_closed.status is WorkOrderStatus.CLOSED

    # 驗 DB 兩個 chain：first REJECTED + second APPROVED
    first_refresh = sg_repo.get_chain(first_chain.id)
    assert first_refresh is not None
    assert first_refresh.overall_status is SignoffStatus.REJECTED

    second_refresh = sg_repo.get_chain(second_chain.id)
    assert second_refresh is not None
    assert second_refresh.overall_status is SignoffStatus.APPROVED


# ─────────────────────────────────────────────────────────────────────────
# Unhappy path B：MR final approve 撞 insufficient stock → transition_error
# ─────────────────────────────────────────────────────────────────────────


def test_mr_final_approve_under_insufficient_stock(e2e_setup):
    """
    Setup：把 stock 改成 1（從 fixture 預設 10）。
    建 MR estimated_qty=3 → 3 階全部 approve。Final approve 撞 insufficient stock：
    - HTTP 仍 200（chain 已 APPROVED 落地不能 retry）
    - response.transition_error 含 "insufficient"
    - MR 留在 APPROVED（沒進 DISPATCHED）
    - stock 不變
    - ledger 沒有 entry
    """
    setup = e2e_setup
    client = setup["client"]
    inv_repo = setup["inv_repo"]
    wo_repo = setup["wo_repo"]
    actor = uuid4()

    # 把 stock 從 10 調到 1（用 -9 delta + audit log）
    inv_repo.adjust(
        setup["item_id"],
        delta_kind=StockKind.NEW,
        delta=-9,
        reason="seed: tighten stock for insufficient-stock test",
        actor_id=actor,
    )
    assert inv_repo.get_item(setup["item_id"]).stock_new == 1

    # 建工單 + dispatch + start
    wo = _create_work_order(
        wo_repo,
        wo_type=WorkOrderType.CORRECTIVE,
        priority=Priority.HIGH,
        title="insufficient-stock test",
        source_alarm_code="GBT_VIB_HIGH",
        actor=actor,
    )
    wo_repo.transition(wo.id, "dispatch", actor_id=actor)
    wo_repo.transition(wo.id, "start_work")

    # 建 MR estimated_qty=3（stock 只剩 1）+ submit
    mr_bundle = _submit_material_request(
        client,
        wo_id=wo.id,
        item_id=setup["item_id"],
        estimated_qty=3,
        actor=actor,
    )

    # 走 3 階 approve；final approve 撞 insufficient
    # WMOM-20260510-01 Part A：每階用不同 actor（不再強制 actor=fixture actor）
    final_resp = _approve_chain(
        client, mr_bundle["chain_id"], ("employee", "leader", "treasury"),
    )

    # ── 關鍵 assertions ──
    assert final_resp["chain_completed"] is True
    assert final_resp["subject_status_changed"] is False
    assert final_resp["subject_transition_error"] is not None
    assert "insufficient" in final_resp["subject_transition_error"].lower()

    # MR 留 APPROVED（沒進 DISPATCHED）
    fresh_mr = client.get(
        f"/api/workflow/material-requests/{mr_bundle['mr']['id']}",
        params={"farm_id": FARM_ID},
    ).json()
    assert fresh_mr["status"] == "approved"

    # Stock 不變 = 1
    assert inv_repo.get_item(setup["item_id"]).stock_new == 1

    # Ledger 沒有 entry（dispatch 是 ledger entry 來源）
    _, total = setup["ledger_repo"].list(farm_id=FARM_ID)
    assert total == 0


# ─────────────────────────────────────────────────────────────────────────
# Extra：A10 acceptance 之外的健康度檢查 — 完整 lifecycle 跑完總耗時
# ─────────────────────────────────────────────────────────────────────────


def test_corrective_lifecycle_under_60s(e2e_setup):
    """A10 acceptance：Layer A 跑完 < 60 秒（in-memory SQLite + 不寫真 DB）。

    雖然全套 5 個 test 已經很快（< 5s）但留這個健康度 sentinel test，
    將來若有人加 sleep / 同步阻塞會立刻被它擋下來。
    """
    setup = e2e_setup
    t0 = time.monotonic()
    _walk_happy_lifecycle(
        setup,
        wo_type=WorkOrderType.CORRECTIVE,
        priority=Priority.NORMAL,
        source_alarm_code="GBT_TEMP_HIGH",
        estimated_qty=1,
        actual_qty=1,
    )
    elapsed = time.monotonic() - t0
    assert elapsed < 60.0, f"lifecycle 耗時 {elapsed:.2f}s 超過 60s 上限"
