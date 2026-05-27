"""Pinned ECN baseline 的容差比對工具。

ECN 移植 fidelity 用 pinned float64 數字守住（var_fluct / monte_carlo /
k13_equivalence / cost_api / adapter）。原本一律用 `==` 嚴格比對，但 float64
末位（~1 ULP）會隨平台 BLAS / numpy 版本不同而 drift：

- pin baseline 在 Windows 量測，CI / 雲端 sandbox 多為 Linux + OpenBLAS；
- numpy 1.x → 2.x 改了 pairwise summation，累加結果末位不同；
- 實測 numpy 1.26.4 與 2.4.x 在 Linux 下都與原 Windows pin 有最後一位差異。

結果是「程式碼零變動也紅燈」（見 work-logs 5/22 起反覆記為 pre-existing）。

修法：把嚴格 `==` 換成相對容差 `rel_tol=1e-9`。這仍守住 **9 位有效數字** —
任何真實的 ECN 計算 regression（漏項 / 公式錯 / 單位錯）量級都遠大於 1e-9，
攔截能力不變；只吸收平台 float 噪音（~1e-15）。`abs_tol` 處理近零 pinned
值（如 corrective_bop=0.0，此時 rel_tol 對 0 無效）。

設計取捨（容差是嚴格相等的 superset）：
容差比對對任何能通過嚴格 `==` 的值（整數 year/index、binary-exact 的
failure_multiplier 1.5/2.0、engine round() 後的確定性值如 summary npv）也必然
通過 —— 容差是 `==` 的 superset。因此：

- loop-accumulate 測試（var_fluct / monte_carlo / k13_equivalence）對整批欄位
  一律套 `pin_equal`，即使其中混有精確值也安全（不需逐欄位分流）。
- direct-assert 測試（cost_api / adapter）對「已知跨平台確定性」的圓整 / 整數值
  刻意保留嚴格 `==`，當成「此值精確、不靠容差」的可讀性訊號。兩種策略並存
  是刻意的，不是不一致。
"""

from __future__ import annotations

import math
from typing import Any

import pytest

# 相對容差：守住 9 位有效數字（真 regression 量級遠大於此）
PIN_REL_TOL: float = 1e-9
# 絕對容差：近零 pinned 值（rel_tol 對 0 無意義）；遠小於任何有意義的金額/比率
PIN_ABS_TOL: float = 1e-6


def pin_approx(expected: float) -> Any:
    """回傳容差版 expected，供 `assert actual == pin_approx(expected)` 使用。

    Args:
        expected: pinned ECN baseline 數值。

    Returns:
        pytest.approx 物件（rel=PIN_REL_TOL, abs=PIN_ABS_TOL）；
        型別標 `Any` 因 pytest 未正式 export ApproxBase 型別。
    """
    return pytest.approx(expected, rel=PIN_REL_TOL, abs=PIN_ABS_TOL)


def pin_equal(actual: Any, expected: Any) -> bool:
    """容差感知比對；數值用 math.isclose，非數值退回嚴格相等。

    供 loop-accumulate 風格的 pinned test（`if not pin_equal(a, b): failures.append(...)`）
    使用，保留原本一次回報所有 drift 欄位的行為。

    Args:
        actual: 實際計算值。
        expected: pinned ECN baseline 值。

    Returns:
        在容差內視為相等則 True。

    Notes:
        型別判斷邊界：
        - Python int（如 year=1、min_year_index=3）被 isinstance 捕捉，走
          math.isclose 路徑；因容差遠小於 1，對整數 identity 結果等同嚴格相等。
        - numpy.float64 是 Python float 子類 → 走 math.isclose；numpy.int64 在
          numpy 2.x 不是 Python int 子類 → 走 strict ==。兩條路徑對整數 identity
          結果皆正確。
        - bool 是 int 子類會走 math.isclose（結果正確），但語意上不該對 bool
          欄位（如 is_fallback）用本函式 —— 那類請用 strict ==。
    """
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(
            float(actual),
            float(expected),
            rel_tol=PIN_REL_TOL,
            abs_tol=PIN_ABS_TOL,
        )
    return actual == expected
