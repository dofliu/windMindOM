"""WMOM-20260509-01 — inventory domain pure-dataclass / enum 測試。

Acceptance：
- 所有 dataclass 走 type hint + invariant（建立非法 instance 要 raise）
- enum 有預期 value / 數量
- 純 domain：不可 import SQLAlchemy / FastAPI
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from modules.workflow.domain.inventory import (
    InventoryAdjustmentLog,
    InventoryItem,
    MaterialRequest,
    MaterialRequestItem,
    MaterialRequestNotification,
    MaterialRequestStatus,
    MaterialReturn,
    ReturnReason,
    StockKind,
    Warehouse,
)


# ─────────────────────────────────────────────────────────────────────────
# Enum sanity
# ─────────────────────────────────────────────────────────────────────────


def test_stock_kind_values():
    """3 欄位（D3-Q1 簡化）— 不該是 4 欄位。"""
    assert {k.value for k in StockKind} == {"new", "used", "repairing"}
    assert len(StockKind) == 3


def test_material_request_status_has_9_states():
    """DN-03 §2.2 lifecycle + 旁路 = 9 個 status。"""
    expected = {
        "draft",
        "awaiting_approval",
        "approved",
        "dispatched",
        "received",
        "used",
        "closed",
        "cancelled",
        "rejected",
    }
    assert {s.value for s in MaterialRequestStatus} == expected
    assert len(MaterialRequestStatus) == 9


def test_return_reason_4_categories():
    """D3-Q4：退料 4 種分類。"""
    assert {r.value for r in ReturnReason} == {
        "surplus",
        "wrong_part",
        "failed_install",
        "other",
    }
    assert len(ReturnReason) == 4


# ─────────────────────────────────────────────────────────────────────────
# Warehouse
# ─────────────────────────────────────────────────────────────────────────


def test_warehouse_default_id_and_is_default():
    w = Warehouse(
        name="Changhua onshore base",
        farm_id="changhua_offshore",
        location_kind="onshore_base",
    )
    assert isinstance(w.id, UUID)
    assert w.is_default is False


def test_warehouse_location_kind_literal():
    """location_kind Literal 三選一 — Python type checker 抓，runtime 不擋。
    這個 test 只確認三個 valid value 都接受。"""
    for kind in ("onshore_base", "vessel_storage", "offshore_platform"):
        w = Warehouse(name="x", farm_id="f", location_kind=kind)  # type: ignore
        assert w.location_kind == kind


# ─────────────────────────────────────────────────────────────────────────
# InventoryItem
# ─────────────────────────────────────────────────────────────────────────


def _make_item(**overrides) -> InventoryItem:
    base = dict(
        sku="GBR-001",
        name="Gearbox bearing 4040",
        description="Main shaft bearing for Z72",
        unit="piece",
        farm_id="changhua",
        warehouse_id=uuid4(),
        unit_cost=Decimal("450.00"),
    )
    base.update(overrides)
    return InventoryItem(**base)  # type: ignore


def test_inventory_item_default_stock_zero():
    item = _make_item()
    assert item.stock_new == 0
    assert item.stock_used == 0
    assert item.stock_repairing == 0
    assert item.safety_stock == 0


def test_inventory_item_total_available_excludes_repairing():
    """``total_available`` = new + used；維修中不算。"""
    item = _make_item(stock_new=5, stock_used=3, stock_repairing=10)
    assert item.total_available() == 8


def test_inventory_item_below_safety():
    item = _make_item(stock_new=2, stock_used=1, safety_stock=5)
    assert item.is_below_safety() is True


def test_inventory_item_not_below_safety():
    item = _make_item(stock_new=3, stock_used=3, safety_stock=5)
    assert item.is_below_safety() is False


def test_inventory_item_get_stock_per_kind():
    item = _make_item(stock_new=4, stock_used=2, stock_repairing=1)
    assert item.get_stock(StockKind.NEW) == 4
    assert item.get_stock(StockKind.USED) == 2
    assert item.get_stock(StockKind.REPAIRING) == 1


def test_inventory_item_unit_cost_is_decimal():
    """避免 float 誤差（cost ledger 用）。"""
    item = _make_item(unit_cost=Decimal("123.45"))
    assert isinstance(item.unit_cost, Decimal)
    # Decimal 算術精確
    total = item.unit_cost * 3
    assert total == Decimal("370.35")


def test_inventory_item_timestamps_utc():
    item = _make_item()
    assert item.created_at.tzinfo == timezone.utc
    assert item.updated_at.tzinfo == timezone.utc


# ─────────────────────────────────────────────────────────────────────────
# MaterialRequestItem
# ─────────────────────────────────────────────────────────────────────────


def test_material_request_item_estimated_qty_must_be_positive():
    with pytest.raises(ValueError, match="estimated_qty must be > 0"):
        MaterialRequestItem(request_id=uuid4(), item_id=uuid4(), estimated_qty=0)


def test_material_request_item_negative_qty_rejected():
    with pytest.raises(ValueError, match="estimated_qty must be > 0"):
        MaterialRequestItem(request_id=uuid4(), item_id=uuid4(), estimated_qty=-1)


def test_material_request_item_default_stock_kind_new():
    item = MaterialRequestItem(request_id=uuid4(), item_id=uuid4(), estimated_qty=2)
    assert item.stock_kind is StockKind.NEW
    assert item.actual_qty is None


# ─────────────────────────────────────────────────────────────────────────
# MaterialRequest
# ─────────────────────────────────────────────────────────────────────────


def test_material_request_initial_state_is_draft():
    mr = MaterialRequest(
        farm_id="changhua",
        requester_id=uuid4(),
        business_key="MR-cha-202608-01",
    )
    assert mr.status is MaterialRequestStatus.DRAFT
    assert mr.items == []
    assert mr.signoff_chain_id is None
    assert mr.work_order_id is None


def test_material_request_optional_work_order_link():
    """work_order_id 可空（預備庫存補貨）也可填（工單關聯）。"""
    wo_id = uuid4()
    mr = MaterialRequest(
        farm_id="changhua",
        requester_id=uuid4(),
        business_key="MR-cha-202608-02",
        work_order_id=wo_id,
    )
    assert mr.work_order_id == wo_id


def test_material_request_audit_timestamps():
    mr = MaterialRequest(
        farm_id="changhua",
        requester_id=uuid4(),
        business_key="MR-cha-202608-03",
    )
    assert isinstance(mr.requested_at, datetime)
    assert mr.requested_at.tzinfo == timezone.utc
    assert mr.submitted_at is None
    assert mr.approved_at is None


# ─────────────────────────────────────────────────────────────────────────
# MaterialReturn
# ─────────────────────────────────────────────────────────────────────────


def test_material_return_qty_must_be_positive():
    with pytest.raises(ValueError, match="qty must be > 0"):
        MaterialReturn(
            request_id=uuid4(),
            item_id=uuid4(),
            qty=0,
            reason=ReturnReason.SURPLUS,
            return_to_kind=StockKind.NEW,
            returned_by=uuid4(),
        )


def test_material_return_records_reason_and_kind():
    ret = MaterialReturn(
        request_id=uuid4(),
        item_id=uuid4(),
        qty=2,
        reason=ReturnReason.WRONG_PART,
        return_to_kind=StockKind.USED,
        returned_by=uuid4(),
        note="Wrong bearing model — supplier swap",
    )
    assert ret.reason is ReturnReason.WRONG_PART
    assert ret.return_to_kind is StockKind.USED
    assert ret.note == "Wrong bearing model — supplier swap"


# ─────────────────────────────────────────────────────────────────────────
# Notification + Adjustment log
# ─────────────────────────────────────────────────────────────────────────


def test_notification_default_unread():
    n = MaterialRequestNotification(
        request_id=uuid4(),
        recipient_role="leader",
        notification_type="awaiting_signoff",
    )
    assert n.read_at is None


def test_inventory_adjustment_log_signed_delta():
    """delta 可正可負（庫管員手動 +/- 都記）。"""
    pos = InventoryAdjustmentLog(
        item_id=uuid4(),
        delta_kind=StockKind.NEW,
        delta=+5,
        reason="歸還良品",
        actor_id=uuid4(),
    )
    neg = InventoryAdjustmentLog(
        item_id=uuid4(),
        delta_kind=StockKind.USED,
        delta=-2,
        reason="盤虧 — 客戶換貨",
        actor_id=uuid4(),
    )
    assert pos.delta == 5
    assert neg.delta == -2


def test_inventory_adjustment_log_timestamp_utc():
    log = InventoryAdjustmentLog(
        item_id=uuid4(),
        delta_kind=StockKind.NEW,
        delta=1,
        reason="盤盈",
        actor_id=uuid4(),
    )
    assert log.occurred_at.tzinfo == timezone.utc


# ─────────────────────────────────────────────────────────────────────────
# 隔離驗證：domain 層不可 import SQLAlchemy / FastAPI
# ─────────────────────────────────────────────────────────────────────────


def _module_imports(mod) -> set[str]:
    """以 AST 解析 module 真實 import 名稱（避開 docstring 內的 false positive）。"""
    import ast

    src = open(mod.__file__, encoding="utf-8").read()
    tree = ast.parse(src)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def test_domain_layer_has_no_sqlalchemy_or_fastapi_import():
    """純 domain 不可碰 ORM / web framework；CI 防 regression。"""
    import modules.workflow.domain.inventory as mod

    forbidden = {"sqlalchemy", "fastapi", "pydantic"}
    found = forbidden & _module_imports(mod)
    assert not found, f"domain layer must not import {found!r} in inventory.py"


def test_state_machine_layer_has_no_sqlalchemy_or_fastapi_import():
    import modules.workflow.domain.inventory_state_machine as mod

    forbidden = {"sqlalchemy", "fastapi", "pydantic"}
    found = forbidden & _module_imports(mod)
    assert not found, (
        f"state machine layer must not import {found!r} in inventory_state_machine.py"
    )
