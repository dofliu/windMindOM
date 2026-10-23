"""Z72 真實 PLC tag 清單（WMOM-20261021-05，EPIC-DS Phase 3a）。

情境資料包的 tag 字典以 `shared/data/z72_plc_tags.json` 判定每個模擬 tag 是真實 Bachmann tag 還是
自創（synthetic）。這裡守住：清單與 xlsx 一致、判定規則、模擬器 118 個 tag 的真實 / 自創分布。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for _p in (PROJECT_ROOT, PROJECT_ROOT / "modules" / "monitoring"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.plc_tags import PLC_TAGS_PATH, is_real_plc_tag, real_plc_tags  # noqa: E402
from simulator.physics.scada_registry import SCADA_REGISTRY  # noqa: E402


def test_known_real_and_synthetic_tags() -> None:
    assert is_real_plc_tag("Z72PLC__UI_Loc_WTUR_Analogue_TotPwrAt")
    assert is_real_plc_tag("WTUR.Z72PLC__UI_Loc_WTUR_Analogue_TotPwrAt"), "OPC 分組前綴要先去掉"
    assert is_real_plc_tag("Z72PLC__ActiveTrip1")
    assert not is_real_plc_tag("Z72PLC__UI_Loc_WMET_Analogue_WakeDef"), "尾流虧損是模擬器自創的 tag"
    assert len(real_plc_tags()) >= 1500


def test_simulator_tags_split_into_50_real_and_71_synthetic() -> None:
    """121 個 tag：50 個真實 Bachmann tag（含 -03-a 補的 5 個、-08-a 補的軸承 / 定子溫度 2、-08-c 補的變槳馬達
    電流 3 個）、71 個依命名規則自創。"""
    real = [t.id for t in SCADA_REGISTRY.all_tags if is_real_plc_tag(t.opc_tag)]
    assert len(SCADA_REGISTRY.all_tags) == 121
    assert len(real) == 50
    for tag_id in ("WYAW_YwVn2AlgnAvg5s", "WCNV_VtgMsCnvGd1", "WYAW_YwBrkSealsLeak", "WGEN_GnBrgTmp1",
                   "WGEN_GnBrgTmp2", "WGEN_GnStaTmp2", "WROT_PtMotCurBl1", "WROT_PtMotCurBl2", "WROT_PtMotCurBl3"):
        assert tag_id in real


def test_tag_list_matches_the_xlsx_when_build_deps_available() -> None:
    """重新從 xlsx 擷取的 tag 清單必須與 commit 的 JSON 一致。"""
    pytest.importorskip("openpyxl")
    tools_dir = PROJECT_ROOT / "tools"
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    import build_z72_plc_tags as builder

    assert builder.render(builder.extract_tags(builder.XLSX_PATH)) == PLC_TAGS_PATH.read_text(encoding="utf-8")
