"""shared/alarm_codes.py 與 Z72 警報目錄單元測試（WMOM-20261021-02）。

涵蓋：
- 目錄完整性：xlsx「警告訊息列表」314 筆（各等級筆數一致）＋手冊獨有的 A039（WMOM-20261022-02）
- 等級與 PLC tag 對應：A → ActiveAlarm、T1 → ActiveTrip1、T2 → ActiveTrip2、I → 無 tag
- 查詢 API：get / find / is_known_code / all_alarms / event_id
- 手冊補充欄位：已知事件帶有原因、處置、每小時重啟上限與頁碼
- 來源漂移偵測：裝了 openpyxl + pdfplumber 時，重新從 xlsx / 手冊產生的目錄必須與
  commit 的 JSON 完全一致（CI 未裝這兩個 build-time 套件，自動 skip）
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from shared.alarm_codes import (
    CATALOG_PATH,
    all_alarms,
    find_alarm,
    get_alarm,
    is_known_code,
)

EXPECTED_TAG_BY_LEVEL = {
    "A": "Z72PLC__ActiveAlarm",
    "T1": "Z72PLC__ActiveTrip1",
    "T2": "Z72PLC__ActiveTrip2",
}


def test_catalog_has_all_314_xlsx_events_plus_manual_only_a039() -> None:
    alarms = all_alarms()
    assert len(alarms) == 315
    assert Counter(a.level for a in alarms) == {"T1": 207, "A": 63, "I": 24, "T2": 21}


def test_manual_only_auto_restart_blocked_a039() -> None:
    """自動重啟被封鎖：xlsx 沒列、手冊 Appendix C 有（p.106），PLC 以 A 級警報送出。"""
    a = get_alarm(39)
    assert a.level == "A"
    assert a.text == "Auto restart blocked"
    assert a.plc_tag == "Z72PLC__ActiveAlarm"
    assert a.cause is not None and "Max #/hr is exceeded" in a.cause
    assert a.max_per_hour is None
    assert a.manual_page == 106
    assert a.event_id == "A_039"


def test_all_alarms_sorted_and_unique() -> None:
    codes = [a.code for a in all_alarms()]
    assert codes == sorted(set(codes))


def test_plc_tag_matches_level() -> None:
    mismatched = [
        a.event_id for a in all_alarms() if a.plc_tag != EXPECTED_TAG_BY_LEVEL.get(a.level)
    ]
    assert mismatched == []


def test_get_alarm_returns_real_z72_definition() -> None:
    a = get_alarm(262)
    assert a.level == "A"
    assert a.text == "Main bearing 1 temperature high"
    assert a.plc_tag == "Z72PLC__ActiveAlarm"
    assert a.cause is not None and "might culminate into a trip" in a.cause
    assert a.rectification == "Check lubrication main bearing. Check cooling fan."
    assert a.max_per_hour is None
    assert a.manual_page == 111
    assert not a.is_trip
    assert a.event_id == "A_262"


def test_trip_event_has_restart_limit_and_trip_event_id() -> None:
    a = get_alarm(351)
    assert a.text == "Software overspeed"
    assert a.level == "T1"
    assert a.is_trip
    assert a.max_per_hour == 5
    assert a.event_id == "T_351"


def test_codes_previously_misused_by_simulator_have_real_meaning() -> None:
    """模擬器舊版把 350 當變壓器溫度高；真實 350 是 DC 電池維護開關，變壓器溫度高是 417。"""
    assert get_alarm(350).text == "DC battery maintenance switch active"
    assert get_alarm(417).text == "Transformer temperature high"


def test_information_event_has_no_plc_tag() -> None:
    a = get_alarm(2)
    assert a.level == "I"
    assert a.plc_tag is None
    assert a.event_id == "I_002"


def test_unknown_code_handling() -> None:
    for code in (41, 42, 43, 99999):
        assert not is_known_code(code)
        assert find_alarm(code) is None
    with pytest.raises(KeyError):
        get_alarm(41)


def test_empty_manual_fields_are_none_not_blank() -> None:
    """手冊沒寫的欄位一律是 None（不混用空字串），並修掉 PDF 斷字。"""
    for a in all_alarms():
        assert a.cause != "" and a.rectification != ""
    assert get_alarm(20).rectification == "Check parameter ranges, and re-configure"


def test_most_events_have_manual_entry() -> None:
    alarms = all_alarms()
    with_manual = [a for a in alarms if a.manual_page is not None]
    assert len(with_manual) == 307  # xlsx 306 + 手冊獨有 039
    assert all(104 <= a.manual_page <= 130 for a in with_manual)  # type: ignore[operator]  # 已過濾 None


def test_catalog_matches_sources_when_build_deps_available() -> None:
    """重新從 xlsx + 手冊產生的目錄必須與 commit 的 JSON 一致。"""
    pytest.importorskip("openpyxl")
    pytest.importorskip("pdfplumber")
    tools_dir = PROJECT_ROOT / "tools"
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    import build_z72_alarm_catalog as builder

    xlsx_events = builder.read_xlsx_events()
    manual_events = builder.read_manual_events()
    builder.validate_sources(xlsx_events, manual_events)
    catalog = builder.build_catalog(xlsx_events, manual_events)
    assert builder.render_catalog(catalog) == CATALOG_PATH.read_text(encoding="utf-8")
