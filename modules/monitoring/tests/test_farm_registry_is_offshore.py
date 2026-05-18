"""FarmRegistry `is_offshore` 欄位 + schema migration 測試 (WMOM-20260510-01 Part C).

驗證:
1. 新 DB 含 is_offshore column 且 default 0
2. 舊 DB (缺欄位) 觸發 _migrate_schema → ALTER TABLE ADD COLUMN
3. create_farm(is_offshore=True/False) round-trip 正確
4. update_farm 接受 is_offshore (bool / int 0/1 — 字串 boolean 不支援,router 端應先正規化)
5. clone_farm 繼承來源 farm 的 is_offshore
6. list_farms / get_farm 還原成 Python bool 而非 int
7. to_dict() 含 is_offshore 欄位 (給 API JSON 序列化用)
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
def tmp_registry(tmp_path):
    """每個 test 用獨立 tmp_path,避免互相污染。"""
    from server.farm_registry import FarmRegistry

    return FarmRegistry(data_dir=tmp_path)


# ─────────────────────────────────────────────────────────────────────────
# 1. Schema migration
# ─────────────────────────────────────────────────────────────────────────


def test_new_db_has_is_offshore_column(tmp_registry):
    """新 DB 經 _init_db() 後 farms 表必含 is_offshore column。"""
    conn = tmp_registry._get_conn()
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(farms)")}
    conn.close()
    assert "is_offshore" in columns


def test_migrate_schema_adds_missing_column(tmp_path):
    """模擬「舊 DB 缺 is_offshore」場景:預先建只含舊 schema 的 farms.db,
    然後 FarmRegistry 初始化應自動 ALTER TABLE 補欄位。
    """
    farms_db = tmp_path / "farms.db"
    farms_db.parent.mkdir(parents=True, exist_ok=True)
    # 1) 預先建立舊版 schema (沒有 is_offshore)
    old_conn = sqlite3.connect(str(farms_db))
    old_conn.execute("""
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
    old_conn.execute("""
        INSERT INTO farms (farm_id, name, turbine_count, created_at, is_active)
        VALUES ('legacy_farm', '舊風場', 14, '2026-01-01T00:00:00', 0)
    """)
    old_conn.commit()
    old_conn.close()

    # 2) FarmRegistry 初始化 → 應自動 migrate
    # 延遲 import:FarmRegistry.__init__ 會立刻跑 _init_db(),
    # 必須等預先建好的「舊 schema DB」就位之後才 import,migration 路徑才會被觸發。
    from server.farm_registry import FarmRegistry

    reg = FarmRegistry(data_dir=tmp_path)

    # 3) 驗證欄位已補上 + 既有 row 仍可讀 + is_offshore default false
    conn = reg._get_conn()
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(farms)")}
    conn.close()
    assert "is_offshore" in columns

    farm = reg.get_farm("legacy_farm")
    assert farm is not None
    assert farm.is_offshore is False
    assert farm.name == "舊風場"


def test_migrate_schema_idempotent(tmp_registry):
    """重複呼叫 _init_db() 不應再次嘗試 ALTER TABLE (會 sqlite OperationalError)。"""
    # 第一次 init 已在 fixture 跑過,再 init 不應 raise
    tmp_registry._init_db()
    tmp_registry._init_db()
    # 沒 exception 就算 pass


# ─────────────────────────────────────────────────────────────────────────
# 2. CRUD round-trip
# ─────────────────────────────────────────────────────────────────────────


def test_create_farm_default_is_offshore_false(tmp_registry):
    """create_farm 不傳 is_offshore → default False。"""
    farm = tmp_registry.create_farm(farm_id="onshore_a", name="陸上 A")
    assert farm.is_offshore is False

    reloaded = tmp_registry.get_farm("onshore_a")
    assert reloaded.is_offshore is False


def test_create_farm_with_is_offshore_true(tmp_registry):
    """create_farm(is_offshore=True) → DB 儲存 1 → 還原回 True。"""
    farm = tmp_registry.create_farm(
        farm_id="offshore_a", name="彰化離岸", is_offshore=True
    )
    assert farm.is_offshore is True

    reloaded = tmp_registry.get_farm("offshore_a")
    assert reloaded.is_offshore is True
    assert isinstance(reloaded.is_offshore, bool)  # 確認是 bool 不是 int


def test_list_farms_returns_bool_not_int(tmp_registry):
    """list_farms 還原的 is_offshore 必為 Python bool,避免 JSON serialize 成 0/1 害前端。"""
    tmp_registry.create_farm(farm_id="a", name="A", is_offshore=False)
    tmp_registry.create_farm(farm_id="b", name="B", is_offshore=True)

    farms = {f.farm_id: f for f in tmp_registry.list_farms()}
    assert farms["a"].is_offshore is False
    assert farms["b"].is_offshore is True
    assert isinstance(farms["a"].is_offshore, bool)
    assert isinstance(farms["b"].is_offshore, bool)


def test_update_farm_toggles_is_offshore(tmp_registry):
    """update_farm(is_offshore=...) 兩個方向都應生效。"""
    tmp_registry.create_farm(farm_id="t", name="T", is_offshore=False)

    updated = tmp_registry.update_farm("t", is_offshore=True)
    assert updated.is_offshore is True

    updated = tmp_registry.update_farm("t", is_offshore=False)
    assert updated.is_offshore is False


def test_update_farm_accepts_int_0_1(tmp_registry):
    """update_farm 應接受 int 0/1 與 Python bool (FastAPI 解 JSON body 後的真實型別)。

    字串 boolean (例如 "false") 不在支援範圍 — Python `bool("false") is True`
    會誤判,因此 router 必須在傳入前正規化成真 bool。本 test 只覆蓋 registry
    層真正支援的 input shape。
    """
    tmp_registry.create_farm(farm_id="t", name="T", is_offshore=False)

    # int 1 → True
    assert tmp_registry.update_farm("t", is_offshore=1).is_offshore is True
    # int 0 → False
    assert tmp_registry.update_farm("t", is_offshore=0).is_offshore is False
    # Python bool round-trip
    assert tmp_registry.update_farm("t", is_offshore=True).is_offshore is True
    assert tmp_registry.update_farm("t", is_offshore=False).is_offshore is False


def test_update_farm_ignores_none_does_not_clear_offshore(tmp_registry):
    """既有 router 邏輯:val is None 不寫入。is_offshore=None 應保持原值。"""
    tmp_registry.create_farm(farm_id="t", name="T", is_offshore=True)
    # 傳 None 不應把 True 變 False
    tmp_registry.update_farm("t", is_offshore=None, location="新北")
    farm = tmp_registry.get_farm("t")
    assert farm.is_offshore is True
    assert farm.location == "新北"


# ─────────────────────────────────────────────────────────────────────────
# 3. Clone 繼承
# ─────────────────────────────────────────────────────────────────────────


def test_clone_farm_inherits_is_offshore(tmp_registry):
    """clone 出來的新 farm 應繼承 source 的 is_offshore 屬性。"""
    tmp_registry.create_farm(farm_id="src_offshore", name="離岸來源", is_offshore=True)
    cloned = tmp_registry.clone_farm("src_offshore", "clone_a", "離岸 clone")
    assert cloned.is_offshore is True

    tmp_registry.create_farm(farm_id="src_onshore", name="陸上來源", is_offshore=False)
    cloned2 = tmp_registry.clone_farm("src_onshore", "clone_b", "陸上 clone")
    assert cloned2.is_offshore is False


# ─────────────────────────────────────────────────────────────────────────
# 4. to_dict / config.json
# ─────────────────────────────────────────────────────────────────────────


def test_to_dict_includes_is_offshore(tmp_registry):
    """API JSON 序列化 (to_dict) 必含 is_offshore 鍵 → 前端 TS type 才能依賴。"""
    farm = tmp_registry.create_farm(farm_id="t", name="T", is_offshore=True)
    d = farm.to_dict()
    assert "is_offshore" in d
    assert d["is_offshore"] is True


def test_config_json_persisted_with_is_offshore(tmp_registry, tmp_path):
    """create_farm 寫的 config.json 應含 is_offshore (便於離線 audit)。"""
    import json

    tmp_registry.create_farm(farm_id="t", name="T", is_offshore=True)
    config_path = tmp_path / "farms" / "t" / "config.json"
    assert config_path.exists()
    data = json.loads(config_path.read_text())
    assert data["is_offshore"] is True


# ─────────────────────────────────────────────────────────────────────────
# 5. Router 層正規化 (must-fix #2 regression test)
# ─────────────────────────────────────────────────────────────────────────


def test_router_post_normalizes_is_offshore(tmp_path, monkeypatch):
    """POST /api/farms — router 應把任何 truthy/falsy 值 coerce 成真 bool 再進 registry。"""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from server.farm_registry import FarmRegistry
    from server.routers import farms as farms_router

    reg = FarmRegistry(data_dir=tmp_path)
    monkeypatch.setattr(farms_router, "_get_registry", lambda: reg)

    app = FastAPI()
    app.include_router(farms_router.router)
    client = TestClient(app)

    # int 1 → True
    res = client.post("/api/farms", json={"name": "F1", "farm_id": "f1", "is_offshore": 1})
    assert res.status_code == 200
    assert res.json()["farm"]["is_offshore"] is True

    # int 0 → False
    res = client.post("/api/farms", json={"name": "F2", "farm_id": "f2", "is_offshore": 0})
    assert res.status_code == 200
    assert res.json()["farm"]["is_offshore"] is False

    # 不傳 is_offshore → default False
    res = client.post("/api/farms", json={"name": "F3", "farm_id": "f3"})
    assert res.status_code == 200
    assert res.json()["farm"]["is_offshore"] is False


def test_router_patch_normalizes_is_offshore(tmp_path, monkeypatch):
    """PATCH /api/farms/{id} — router 必須與 POST 對齊,先把 is_offshore 正規化成真 bool。

    這是 must-fix #2 的 regression test:之前 PATCH 直接 `**body` 展開,
    若 body 帶 truthy 字串 ("false") 會繞過 router 層 coerce 直接落地成 True。
    """
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from server.farm_registry import FarmRegistry
    from server.routers import farms as farms_router

    reg = FarmRegistry(data_dir=tmp_path)
    reg.create_farm(farm_id="t", name="T", is_offshore=False)
    monkeypatch.setattr(farms_router, "_get_registry", lambda: reg)

    app = FastAPI()
    app.include_router(farms_router.router)
    client = TestClient(app)

    # int 1 → True
    res = client.patch("/api/farms/t", json={"is_offshore": 1})
    assert res.status_code == 200
    assert res.json()["farm"]["is_offshore"] is True

    # int 0 → False
    res = client.patch("/api/farms/t", json={"is_offshore": 0})
    assert res.status_code == 200
    assert res.json()["farm"]["is_offshore"] is False

    # 不帶 is_offshore 的 PATCH 應該保持原值 + 改其他欄
    reg.update_farm("t", is_offshore=True)
    res = client.patch("/api/farms/t", json={"location": "彰化"})
    assert res.status_code == 200
    body = res.json()["farm"]
    assert body["is_offshore"] is True
    assert body["location"] == "彰化"
