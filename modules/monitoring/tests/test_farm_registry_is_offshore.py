"""Farm registry ``is_offshore`` field tests (WMOM-20260510-01 Part C)。

驗證：
- ``create_farm`` 接受 ``is_offshore=True/False`` 並持久化
- ``get_farm`` / ``list_farms`` 回傳 ``is_offshore``
- ``update_farm`` 可切換 ``is_offshore``
- ``clone_farm`` 帶上 source 的 ``is_offshore``
- 既有舊 DB（無此欄）migrate 後 default False（idempotent）
- ``to_dict`` 包含 ``is_offshore``
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "modules" / "monitoring"))


@pytest.fixture
def registry(tmp_path):
    from server.farm_registry import FarmRegistry

    return FarmRegistry(data_dir=tmp_path)


def test_create_farm_default_onshore(registry):
    """預設 is_offshore=False（陸上）— 既有 caller 不改也安全。"""
    farm = registry.create_farm(farm_id="f1", name="陸上 1")
    assert farm.is_offshore is False
    refetched = registry.get_farm("f1")
    assert refetched is not None
    assert refetched.is_offshore is False


def test_create_farm_offshore_true(registry):
    farm = registry.create_farm(
        farm_id="changhua",
        name="彰化離岸",
        is_offshore=True,
        location="台灣海峽",
    )
    assert farm.is_offshore is True
    refetched = registry.get_farm("changhua")
    assert refetched is not None
    assert refetched.is_offshore is True


def test_list_farms_includes_is_offshore(registry):
    registry.create_farm(farm_id="onshore_a", name="陸上 A", is_offshore=False)
    registry.create_farm(farm_id="offshore_b", name="離岸 B", is_offshore=True)
    farms = registry.list_farms()
    by_id = {f.farm_id: f for f in farms}
    assert by_id["onshore_a"].is_offshore is False
    assert by_id["offshore_b"].is_offshore is True


def test_to_dict_includes_is_offshore(registry):
    farm = registry.create_farm(farm_id="f1", name="A", is_offshore=True)
    d = farm.to_dict()
    assert "is_offshore" in d
    assert d["is_offshore"] is True


def test_update_farm_flip_is_offshore(registry):
    registry.create_farm(farm_id="f1", name="A", is_offshore=False)
    updated = registry.update_farm("f1", is_offshore=True)
    assert updated is not None
    assert updated.is_offshore is True
    # 再翻回 False
    updated = registry.update_farm("f1", is_offshore=False)
    assert updated is not None
    assert updated.is_offshore is False


def test_update_farm_other_fields_does_not_clobber_is_offshore(registry):
    """只更新 name 時不應動到 is_offshore（既有 PATCH 行為相容性）。"""
    registry.create_farm(farm_id="f1", name="A", is_offshore=True)
    updated = registry.update_farm("f1", name="A2")
    assert updated is not None
    assert updated.name == "A2"
    assert updated.is_offshore is True


def test_update_farm_is_offshore_rejects_non_bool(registry):
    """code review fix（MUST-FIX #3）：is_offshore 嚴格 bool 型別 — 字串 / 數字應拒絕。"""
    registry.create_farm(farm_id="f1", name="A", is_offshore=False)
    with pytest.raises(ValueError, match="is_offshore must be bool"):
        registry.update_farm("f1", is_offshore="true")
    with pytest.raises(ValueError, match="is_offshore must be bool"):
        registry.update_farm("f1", is_offshore=1)


def test_clone_farm_carries_is_offshore(registry):
    registry.create_farm(farm_id="src", name="Src", is_offshore=True)
    cloned = registry.clone_farm("src", "dst", "Dst Clone")
    assert cloned is not None
    assert cloned.is_offshore is True


def test_legacy_db_migrate_idempotent(tmp_path):
    """既有 DB 無 is_offshore 欄：第一次 _init_db 補加，第二次不重複。"""
    from server.farm_registry import FarmRegistry, open_sqlite

    data_dir = tmp_path
    (data_dir / "farms").mkdir(parents=True, exist_ok=True)
    farms_db = data_dir / "farms.db"

    # 手建一個「舊版」schema 的 farms table（無 is_offshore）
    conn = open_sqlite(farms_db)
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
        "INSERT INTO farms (farm_id, name, created_at) VALUES (?, ?, ?)",
        ("legacy_farm", "Legacy", "2026-01-01T00:00:00"),
    )
    conn.commit()
    conn.close()

    # 第一次初始化 — 應觸發 ALTER TABLE
    reg = FarmRegistry(data_dir=data_dir)
    legacy = reg.get_farm("legacy_farm")
    assert legacy is not None
    assert legacy.is_offshore is False  # 既有資料 default 0

    # 第二次初始化 — idempotent，不應 raise
    reg2 = FarmRegistry(data_dir=data_dir)
    assert reg2.get_farm("legacy_farm") is not None


def test_from_row_handles_row_without_is_offshore_column():
    """from_row 對舊版 row 物件（無 is_offshore key）回 False，不 KeyError。"""
    from server.farm_registry import FarmConfig

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE farms_old (
            farm_id TEXT, name TEXT, turbine_count INTEGER,
            turbine_spec_json TEXT, wind_profile_json TEXT,
            grid_profile_json TEXT, layout_json TEXT,
            location TEXT, description TEXT,
            created_at TEXT, last_active_at TEXT
        )
    """)
    conn.execute(
        "INSERT INTO farms_old VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("f1", "Legacy", 14, "{}", "{}", "{}", "{}", "loc", "desc", "2026-01-01", ""),
    )
    row = conn.execute("SELECT * FROM farms_old").fetchone()
    cfg = FarmConfig.from_row(row)
    assert cfg.is_offshore is False
