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
        pytest.approx 物件（rel=PIN_REL_TOL, abs=PIN_ABS_TOL）。
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
    """
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(
            float(actual),
            float(expected),
            rel_tol=PIN_REL_TOL,
            abs_tol=PIN_ABS_TOL,
        )
    return actual == expected
