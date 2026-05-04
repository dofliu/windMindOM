"""FastAPI cost router test — 用 TestClient 測 4 個 endpoint。

不挂主 app（會觸發 simulator startup），用最小 FastAPI(test_app) 只挂 cost router。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from modules.cost.routers import router as cost_router  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    """最小 FastAPI app 只挂 cost router，不啟動 monitoring。"""
    app = FastAPI(title="cost-api-test")
    app.include_router(cost_router)
    return TestClient(app)


# ─────────────────────────────────────────────────────────────────────────
# /api/cost/forecast
# ─────────────────────────────────────────────────────────────────────────


def test_forecast_k13_default(client: TestClient):
    r = client.post("/api/cost/forecast", json={"dataset": "k13"})
    assert r.status_code == 200, r.text
    data = r.json()
    # 6 top-level metric bit-perfect 等於 ECN baseline
    assert data["availability_time"] == 0.9401732630646628
    assert data["availability_energy"] == 0.9364235587596128
    assert data["total_revenue_loss"] == 15202721.720482074
    assert data["total_repair_cost"] == 52761689.17773973
    assert data["total_effort"] == 67964410.8982218
    assert data["cost_per_kwh"] == 0.036948752282382154
    # 4 季 breakdown 都在
    assert set(data["seasonal"].keys()) == {"winter", "spring", "summer", "autumn"}
    assert data["seasonal"]["winter"]["fixed_cost"] == 5550000.0


def test_forecast_default_dataset_is_k13(client: TestClient):
    """不傳 dataset → 應該用 default 'k13'。"""
    r = client.post("/api/cost/forecast", json={})
    assert r.status_code == 200, r.text
    assert r.json()["total_effort"] == 67964410.8982218


def test_forecast_unknown_dataset_404(client: TestClient):
    r = client.post("/api/cost/forecast", json={"dataset": "nonexistent"})
    # WMOM-10 後 dataset 改 str；router 在 _resolve_dataset 抛 404
    assert r.status_code == 404
    assert "Unknown dataset" in r.text


# ─────────────────────────────────────────────────────────────────────────
# Farm-aware dataset (WMOM-20260504-10)
# ─────────────────────────────────────────────────────────────────────────


def test_forecast_with_farm_overlay(client: TestClient):
    """dataset='farm:台中港曲風場' → 套用 14×2 MW overrides，meta.source==farm_overlay。"""
    r = client.post(
        "/api/cost/forecast",
        json={"dataset": "farm:台中港曲風場"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    meta = data["dataset_meta"]
    assert meta["dataset_used"] == "farm:台中港曲風場"
    assert meta["farm_id"] == "台中港曲風場"
    assert meta["is_fallback"] is False
    assert meta["source"] == "farm_overlay"
    # 14×2 MW 規模 → revenue_loss 應顯著小於 K13 的 1.52e7
    assert data["total_revenue_loss"] < 5e6


def test_forecast_dataset_meta_present_for_k13(client: TestClient):
    """k13 也要回 dataset_meta（source=k13_baseline, is_fallback=False）。"""
    r = client.post("/api/cost/forecast", json={"dataset": "k13"})
    assert r.status_code == 200, r.text
    meta = r.json()["dataset_meta"]
    assert meta["dataset_used"] == "k13"
    assert meta["farm_id"] is None
    assert meta["is_fallback"] is False
    assert meta["source"] == "k13_baseline"


def test_forecast_farm_unknown_falls_back_to_k13(client: TestClient):
    """dataset='farm:does_not_exist' → fallback K13 + is_fallback=True。"""
    r = client.post(
        "/api/cost/forecast",
        json={"dataset": "farm:totally_made_up_farm_xyz"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    meta = data["dataset_meta"]
    assert meta["is_fallback"] is True
    assert meta["source"] == "k13_fallback"
    assert meta["farm_id"] == "totally_made_up_farm_xyz"
    # 數字應該等於 K13 baseline
    assert data["total_effort"] == 67964410.8982218


def test_forecast_empty_farm_id_422(client: TestClient):
    """dataset='farm:' → 422 (router 防呆)。"""
    r = client.post("/api/cost/forecast", json={"dataset": "farm:"})
    assert r.status_code == 422
    assert "farm_id" in r.text or "farm:" in r.text


@pytest.mark.parametrize(
    "bad_dataset",
    [
        "farm:../etc/passwd",         # path traversal
        "farm:../../secrets",
        "farm:foo/bar",                # 含 /
        "farm:foo\\bar",               # 含 \
        "farm:has internal space",    # 內含空白（外圍 strip 不掉）
        "farm:tab\there",              # 含 tab
    ],
)
def test_forecast_rejects_invalid_farm_id(client: TestClient, bad_dataset: str):
    """非法 farm_id 字元 → 422，不可 silently fallback。"""
    r = client.post("/api/cost/forecast", json={"dataset": bad_dataset})
    assert r.status_code == 422, r.text
    assert "farm_id" in r.text


# ─────────────────────────────────────────────────────────────────────────
# /api/cost/lcoe
# ─────────────────────────────────────────────────────────────────────────


def test_lcoe_k13_default_params(client: TestClient):
    r = client.post(
        "/api/cost/lcoe",
        json={"dataset": "k13", "capex_per_kw": 1250.0, "discount_rate": 0.08},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # LCOE 黃金數字
    assert data["lcoe"] == 72.94042482488679
    assert data["capex_total"] == 650000000.0
    assert data["opex_total_npv"] == 667284604.6591944
    assert data["energy_total_npv"] == 18059733.101660598
    assert data["total_cost_npv"] == 1317284604.6591945


def test_lcoe_with_higher_capex(client: TestClient):
    """capex_per_kw 上調 → LCOE 應該變高（線性）。"""
    base = client.post(
        "/api/cost/lcoe",
        json={"capex_per_kw": 1250.0, "discount_rate": 0.08},
    ).json()
    higher = client.post(
        "/api/cost/lcoe",
        json={"capex_per_kw": 2500.0, "discount_rate": 0.08},
    ).json()
    assert higher["lcoe"] > base["lcoe"]
    assert higher["capex_total"] == base["capex_total"] * 2


# ─────────────────────────────────────────────────────────────────────────
# /api/cost/monte-carlo
# ─────────────────────────────────────────────────────────────────────────


def test_monte_carlo_k13_seed_42(client: TestClient):
    r = client.post(
        "/api/cost/monte-carlo",
        json={"dataset": "k13", "n_simulations": 100, "seed": 42},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["n_simulations"] == 100
    assert data["seed"] == 42
    # Deterministic == cost_cal baseline
    assert data["deterministic"]["availability_time"] == 0.9401732630646628
    # Percentiles bit-perfect (seed=42)
    assert data["percentiles"]["cost"]["p10"] == 64947395.4665548
    assert data["percentiles"]["cost"]["p50"] == 67461289.52520475
    assert data["percentiles"]["cost"]["p90"] == 70735646.24196146


def test_monte_carlo_validation_n_too_low(client: TestClient):
    """n_simulations < 10 → 422 validation error（schema constraint）。"""
    r = client.post(
        "/api/cost/monte-carlo",
        json={"n_simulations": 5, "seed": 42},
    )
    assert r.status_code == 422


def test_monte_carlo_default_n_and_seed(client: TestClient):
    """不傳 n_simulations / seed → 用 schema defaults (n=100, seed=42)。"""
    r = client.post("/api/cost/monte-carlo", json={})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["n_simulations"] == 100
    assert data["seed"] == 42


# ─────────────────────────────────────────────────────────────────────────
# /api/cost/var-fluct
# ─────────────────────────────────────────────────────────────────────────


def test_var_fluct_k13_default(client: TestClient):
    r = client.post("/api/cost/var-fluct", json={"dataset": "k13"})
    assert r.status_code == 200, r.text
    data = r.json()
    # 20 年 yearly
    assert len(data["yearly"]) == 20
    # Year 1 (early peak)
    y1 = data["yearly"][0]
    assert y1["year"] == 1
    assert y1["failure_multiplier"] == 1.5
    assert y1["total_effort"] == 88396679.81348723
    # Year 20 (late peak)
    y20 = data["yearly"][19]
    assert y20["year"] == 20
    assert y20["failure_multiplier"] == 2.0
    assert y20["total_effort"] == 131448595.88017026
    # Summary bit-perfect
    assert data["summary"]["npv_total_effort"] == 776626181.4
    assert data["summary"]["lifetime_availability_time"] == 0.932024
    assert data["summary"]["min_year_index"] == 3
    assert data["summary"]["max_year_index"] == 20


def test_var_fluct_custom_bathtub(client: TestClient):
    """自訂 bathtub params 應反映在 yearly multiplier 上。"""
    r = client.post(
        "/api/cost/var-fluct",
        json={
            "dataset": "k13",
            "failure_rate_model": "bathtub",
            "bathtub": {
                "early_peak": 3.0,  # 比 default 1.5 更高
                "late_peak": 2.0,
                "early_life_years": 2,
                "late_life_start": 15,
                "beta_early": 0.7,
                "beta_late": 1.5,
            },
        },
    )
    assert r.status_code == 200, r.text
    y1 = r.json()["yearly"][0]
    # early_peak 3.0 → year 1 multiplier 應該是 3.0
    assert y1["failure_multiplier"] == 3.0
    # total_effort 比 default 高（因為 failure rate 加倍）
    assert y1["total_effort"] > 88396679.81348723


def test_var_fluct_constant_failure_rate(client: TestClient):
    """failure_rate_model='constant' → 所有年 multiplier=1.0。"""
    r = client.post(
        "/api/cost/var-fluct",
        json={"dataset": "k13", "failure_rate_model": "constant"},
    )
    assert r.status_code == 200, r.text
    yearly = r.json()["yearly"]
    for y in yearly:
        assert y["failure_multiplier"] == 1.0
