"""個體差異 spread 排除故障機組測試 for #WMOM-20260505-24。

`modules/monitoring/examples/data_quality_analysis.py` 的「§7 風機個體差異」
原本直接對所有 `WTUR_TurSt==6.0`（發電中）列取每台機組平均功率算 spread，
但測試計畫（如 `basic_validation`）會對特定機組注入永久性故障（severity
超過 `auto_trip_severity` 後 `fault.tripped` 恆為 True，`WindFarmSimulator`
每步都對其呼叫 `cmd_emergency_stop`），該機組因此大部分時間停在
emergency/recovery 迴圈、產電時間暴跌，讓「平均產電功率」被故障期間的
低產出污染，使 spread 膨脹到與 individuality 參數無關的數字——實測 2 小時
`basic_validation` 跑法下 spread 曾錯誤地衝到 118%，錯誤地指向
「individuality 模型太誇張」。修法：`compute_healthy_individuality_spread`
先排除本次測試計畫中曾被注入故障（`has_fault` 曾為 True）的機組，只在
健康機組間比較。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "modules" / "monitoring"))
sys.path.insert(0, str(PROJECT_ROOT / "modules" / "monitoring" / "examples"))

from data_quality_analysis import compute_healthy_individuality_spread  # noqa: E402


def _producing_df(rows: list[dict]) -> pd.DataFrame:
    """建構最小可用的 `producing`（發電中）DataFrame，補齊必要欄位。"""
    df = pd.DataFrame(rows)
    for col, default in (("turbine_id", None), ("WTUR_TotPwrAt", None), ("has_fault", False)):
        if col not in df.columns:
            df[col] = default
    return df


def test_excludes_turbines_ever_faulted_during_run():
    """曾被注入故障的機組（即使當下這一列 has_fault 已消退）整台排除，不只排除故障當下那幾列。"""
    rows = []
    # 3 台健康機組：100 / 110 / 90 kW
    for tid, power in [("WT002", 100.0), ("WT004", 110.0), ("WT005", 90.0)]:
        for _ in range(5):
            rows.append({"turbine_id": tid, "WTUR_TotPwrAt": power, "has_fault": False})
    # WT001：全程故障（永久性 trip），產電時大部分是故障期間的低產出
    for _ in range(20):
        rows.append({"turbine_id": "WT001", "WTUR_TotPwrAt": 5.0, "has_fault": True})
    # WT003：先健康產電，之後才被注入故障（converter_cooling_fault 一類）——
    # 即使故障前那幾列 has_fault==False，整台仍需被排除，否則會用不對等的
    # 時間窗（只算故障前那段）跟其他機組比較，一樣是不公平比較。
    for _ in range(5):
        rows.append({"turbine_id": "WT003", "WTUR_TotPwrAt": 900.0, "has_fault": False})
    for _ in range(5):
        rows.append({"turbine_id": "WT003", "WTUR_TotPwrAt": 20.0, "has_fault": True})

    producing = _producing_df(rows)
    result = compute_healthy_individuality_spread(producing)

    assert result is not None
    assert result["turbine_ids"] == ["WT002", "WT004", "WT005"]
    # spread = (110-90)/100*100 = 20%，只在 3 台健康機組間比較
    assert result["spread_pct"] == pytest.approx(20.0)
    assert result["min_kw"] == pytest.approx(90.0)
    assert result["max_kw"] == pytest.approx(110.0)


def test_returns_none_when_fewer_than_two_healthy_turbines():
    """健康機組只剩 1 台（或 0 台）時無法比較 spread，回傳 None 而非誤導性單台"差異 0%"。"""
    rows = []
    for _ in range(5):
        rows.append({"turbine_id": "WT002", "WTUR_TotPwrAt": 100.0, "has_fault": False})
    for tid in ("WT001", "WT003", "WT004", "WT005"):
        for _ in range(5):
            rows.append({"turbine_id": tid, "WTUR_TotPwrAt": 5.0, "has_fault": True})

    producing = _producing_df(rows)
    assert compute_healthy_individuality_spread(producing) is None


def test_returns_none_when_required_columns_missing():
    """缺 `has_fault`/`turbine_id`/`WTUR_TotPwrAt` 任一必要欄位時安全回傳 None，不拋例外。"""
    df = pd.DataFrame({"turbine_id": ["WT001"], "WTUR_TotPwrAt": [100.0]})  # 缺 has_fault
    assert compute_healthy_individuality_spread(df) is None


def test_all_healthy_matches_naive_spread_formula():
    """全部機組皆無故障時，結果應與未過濾版本的 naive spread 公式一致（無回歸）。"""
    rows = []
    for tid, power in [("WT001", 200.0), ("WT002", 240.0), ("WT003", 220.0)]:
        for _ in range(4):
            rows.append({"turbine_id": tid, "WTUR_TotPwrAt": power, "has_fault": False})

    producing = _producing_df(rows)
    result = compute_healthy_individuality_spread(producing)

    assert result is not None
    assert set(result["turbine_ids"]) == {"WT001", "WT002", "WT003"}
    # naive: (240-200)/mean(200,240,220)*100 = 40/220*100
    assert result["spread_pct"] == pytest.approx(40.0 / 220.0 * 100.0)
