"""FarmRegistry `is_offshore` 屬性 + legacy DB ALTER migration test。

WMOM-20260510-01 Part C — Farm `is_offshore` 欄位驅動 work_order start_work
weather_window 檢查。本 test 涵蓋：

1. 新建風場預設 onshore（is_offshore=False）
2. 新建風場顯式 offshore（is_offshore=True）
3. update_farm 切換 offshore flag 雙向
4. legacy DB（無 is_offshore 欄位）開檔自動 ALTER TABLE 補欄位，既有 row 預設 false
5. from_row 對舊 DB（row 不含此欄）的容錯
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "modules" / "monitoring"))

from server.farm_registry import FarmRegistry  # noqa: E402


@pytest.fixture
def tmp_registry(tmp_path: Path) -> FarmRegistry:
    """獨立 tmp data dir 的 FarmRegistry。"""
    return FarmRegistry(data_dir=tmp_path)


def test_create_farm_default_onshore(tmp_registry: FarmRegistry) -> None:
    """未指定 is_offshore → 預設 False（陸上風場）。"""
    farm = tmp_registry.create_farm(farm_id="onshore_a", name="陸上 A")
    assert farm.is_offshore is False
    fetched = tmp_registry.get_farm("onshore_a")
    assert fetched is not None
    assert fetched.is_offshore is False
    # to_dict 也要帶
    assert fetched.to_dict()["is_offshore"] is False


def test_create_farm_explicit_offshore(tmp_registry: FarmRegistry) -> None:
    """明確指定 is_offshore=True → 持久化讀回仍為 True。"""
    farm = tmp_registry.create_farm(
        farm_id="offshore_b", name="彰化離岸 B", is_offshore=True
    )
    assert farm.is_offshore is True
    fetched = tmp_registry.get_farm("offshore_b")
    assert fetched is not None
    assert fetched.is_offshore is True


def test_update_farm_toggle_offshore(tmp_registry: FarmRegistry) -> None:
    """update_farm(is_offshore=...) 雙向切換 — onshore → offshore → onshore。"""
    tmp_registry.create_farm(farm_id="toggle_c", name="切換 C")
    # onshore → offshore
    updated = tmp_registry.update_farm("toggle_c", is_offshore=True)
    assert updated is not None and updated.is_offshore is True
    # offshore → onshore
    updated2 = tmp_registry.update_farm("toggle_c", is_offshore=False)
    assert updated2 is not None and updated2.is_offshore is False


def test_update_farm_is_offshore_does_not_affect_other_fields(
    tmp_registry: FarmRegistry,
) -> None:
    """只改 is_offshore 不應影響 name / location / description。"""
    tmp_registry.create_farm(
        farm_id="iso_d",
        name="原名 D",
        location="台中",
        description="陸上測試風場",
    )
    updated = tmp_registry.update_farm("iso_d", is_offshore=True)
    assert updated is not None
    assert updated.name == "原名 D"
    assert updated.location == "台中"
    assert updated.description == "陸上測試風場"
    assert updated.is_offshore is True


def test_legacy_db_migration_adds_is_offshore(tmp_path: Path) -> None:
    """既有 DB 沒 is_offshore 欄位 → FarmRegistry 開檔自動 ALTER TABLE 補欄位。

    重現流程：
    1. 手動建一個沒 is_offshore 的 farms table（模擬 5/17 之前的 DB）
    2. 插入一筆 row
    3. 用 FarmRegistry 開這個 dir → _init_db ALTER TABLE
    4. get_farm 應回 is_offshore=False（DEFAULT 0）
    """
    data_dir = tmp_path / "legacy"
    data_dir.mkdir()
    (data_dir / "farms").mkdir()
    legacy_db = data_dir / "farms.db"

    # 建舊 schema（無 is_offshore）
    conn = sqlite3.connect(str(legacy_db))
    conn.execute("""
        CREATE TABLE farms (
            farm_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            turbine_count INTEGER NOT NULL DEFAULT 14,
            turbine_spec_json TEXT,
            wind_profile_json TEXT,
            grid_profile_json TEXT,
            layout_json TEXT,
            location TEXT,
            description TEXT,
            created_at TEXT NOT NULL,
            last_active_at TEXT,
            is_active INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute(
        "INSERT INTO farms (farm_id, name, turbine_count, created_at) "
        "VALUES ('legacy_e', '舊風場 E', 14, '2026-05-01T00:00:00')"
    )
    conn.commit()
    conn.close()

    # 開 FarmRegistry → 應自動 ALTER TABLE
    reg = FarmRegistry(data_dir=data_dir)
    farm = reg.get_farm("legacy_e")
    assert farm is not None
    assert farm.is_offshore is False  # ALTER DEFAULT 0 應該帶值

    # 再次 init 應冪等 — 不重複 ALTER（會 raise duplicate column）
    # 直接重 new 一個 instance 走 _init_db 流程
    reg2 = FarmRegistry(data_dir=data_dir)
    farm2 = reg2.get_farm("legacy_e")
    assert farm2 is not None
    assert farm2.is_offshore is False


def test_list_farms_includes_is_offshore(tmp_registry: FarmRegistry) -> None:
    """list_farms 回傳的每個 FarmConfig 都應帶 is_offshore（serialization sanity）。"""
    tmp_registry.create_farm(farm_id="ls_a", name="A", is_offshore=False)
    tmp_registry.create_farm(farm_id="ls_b", name="B", is_offshore=True)
    farms = {f.farm_id: f.is_offshore for f in tmp_registry.list_farms()}
    assert farms == {"ls_a": False, "ls_b": True}


def test_clone_farm_preserves_is_offshore(tmp_registry: FarmRegistry) -> None:
    """code-review fix：clone offshore farm 應保留 is_offshore=True，否則靜默變陸上。"""
    tmp_registry.create_farm(
        farm_id="src_offshore", name="原離岸風場", is_offshore=True
    )
    cloned = tmp_registry.clone_farm(
        source_farm_id="src_offshore",
        new_farm_id="dst_offshore",
        new_name="複製離岸風場",
    )
    assert cloned is not None
    assert cloned.is_offshore is True
    # 跨 registry 重讀也應持久化
    fetched = tmp_registry.get_farm("dst_offshore")
    assert fetched is not None
    assert fetched.is_offshore is True


def test_update_farm_is_offshore_persisted_across_reads(tmp_path: Path) -> None:
    """code-review should-fix：update_farm 後另起一個 registry 重讀確認持久化。"""
    reg1 = FarmRegistry(data_dir=tmp_path)
    reg1.create_farm(farm_id="persist_f", name="持久化 F", is_offshore=False)
    reg1.update_farm("persist_f", is_offshore=True)
    # 重新開 registry 模擬 process 重啟
    reg2 = FarmRegistry(data_dir=tmp_path)
    farm = reg2.get_farm("persist_f")
    assert farm is not None
    assert farm.is_offshore is True


def test_update_farm_is_offshore_rejects_non_bool_string(tmp_registry: FarmRegistry) -> None:
    """code-review fix：PATCH body 若傳字串 "false"，Python truthiness 會錯把它當 True。

    `update_farm` 應只接受 Python bool（或無視非 bool 輸入），不要走 truthy 轉換。
    """
    tmp_registry.create_farm(farm_id="strguard_g", name="字串 guard", is_offshore=False)
    # 傳 "false" 字串應該被拒絕（raise TypeError）或留原值；不能變 True
    with pytest.raises((TypeError, ValueError)):
        tmp_registry.update_farm("strguard_g", is_offshore="false")  # type: ignore[arg-type]
    farm = tmp_registry.get_farm("strguard_g")
    assert farm is not None
    assert farm.is_offshore is False  # 未被字串污染
