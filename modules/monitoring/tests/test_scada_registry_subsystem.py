"""SCADA registry ``subsystem`` 欄位正確性測試（WMOM-20260927-07）。

驗證：
- ``WCOL_CoolantLvl``/``WCOL_CoolantAlm`` 的 ``subsystem`` 欄位為 ``"WCOL"``
  （曾誤植為 ``"WCNV"``，導致 ``by_subsystem("WCOL")`` 回傳空 list）
- ``ScadaRegistry.by_subsystem("WCOL")`` 能正確回傳這兩個 tag
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

from simulator.physics.scada_registry import SCADA_REGISTRY  # noqa: E402


def test_wcol_tags_have_wcol_subsystem() -> None:
    """WCOL_* tag 的 subsystem 欄位必須是 'WCOL'，不可誤植為其他 subsystem。"""
    assert SCADA_REGISTRY["WCOL_CoolantLvl"].subsystem == "WCOL"
    assert SCADA_REGISTRY["WCOL_CoolantAlm"].subsystem == "WCOL"


def test_by_subsystem_wcol_returns_both_tags() -> None:
    """by_subsystem('WCOL') 應回傳兩個 WCOL tag，且不誤入 WCNV 分組。"""
    wcol_tags = SCADA_REGISTRY.by_subsystem("WCOL")
    wcol_ids = {t.id for t in wcol_tags}
    assert wcol_ids == {"WCOL_CoolantLvl", "WCOL_CoolantAlm"}

    wcnv_ids = {t.id for t in SCADA_REGISTRY.by_subsystem("WCNV")}
    assert "WCOL_CoolantLvl" not in wcnv_ids
    assert "WCOL_CoolantAlm" not in wcnv_ids
