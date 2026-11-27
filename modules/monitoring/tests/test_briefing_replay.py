"""故障出勤卡的離線重播與自動評分（WMOM-20261127-08，出發前助理企劃的階段 A）。

1. 資料包換成卡片讀資料的兩個介面：事件與讀值和資料包逐筆相同；讀值晚到時看不到。
2. 出勤：每次停機一張；答案從標準答案取（故障、干擾、電網事件）。
3. 護欄：學生 starter kit 的 7 個範例資料包，用標準答案評分要過門檻；資料有問題時卡片要標出來。
"""

from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
MONITORING_ROOT = PROJECT_ROOT / "modules" / "monitoring"
if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))

import numpy as np
import pytest

from server import briefing
from server import briefing_replay as br
from server import scenario_pack as sp
from simulator.time_utils import iso_utc, parse_iso

KIT = PROJECT_ROOT / "examples" / "rag_starter_kit"


def _pack(name: str) -> br.PackData:
    return br.PackData.load(KIT / "packs" / name)


def _truth(name: str) -> dict:
    return json.loads((KIT / "answers" / f"{name}.ground_truth.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def replayed() -> dict:
    return br.replay_all(KIT / "packs", KIT / "answers")


# ── 1. 資料包當資料來源 ───────────────────────────────────────────────────


def test_pack_events_come_back_exactly_as_in_the_pack() -> None:
    pack = _pack("z72-starter-05")
    source = br.PackEvents(pack.events)
    start, end = parse_iso(str(pack.events[0]["ts"])), parse_iso(str(pack.events[-1]["ts"]))
    got, truncated = briefing._alarm_events(source, start, end, None)  # type: ignore[arg-type]
    expected = [e for e in pack.events if e["event_type"] in ("alarm_raised", "trip")]
    assert not truncated and len(got) == len(expected) > 0
    assert sorted(json.dumps(e, sort_keys=True) for e in got) == sorted(json.dumps(e, sort_keys=True) for e in expected)


def test_pack_readings_match_the_parquet_and_hide_late_data() -> None:
    pack = _pack("z72-starter-01")
    source = br.PackReadings(pack.raw)
    names = {c.tag.id: c.name for c in sp.pack_columns()}
    rows = source.readings("WT002", ["WGEN_GnBrgTmp1", "NO_SUCH_TAG"], start="2026-03-02T01:30:00Z",
                           end="2026-03-02T01:31:00Z")
    frame = pack.raw[pack.raw["turbine_id"] == "WT002"].sort_values("timestamp")
    window = frame[(frame["timestamp"] >= "2026-03-02T01:30:00Z") & (frame["timestamp"] < "2026-03-02T01:31:00Z")]
    assert [r.timestamp for r in rows] == [iso_utc(t.to_pydatetime()) for t in window["timestamp"]]
    assert np.allclose([r.values[0] for r in rows], window[names["WGEN_GnBrgTmp1"]].to_numpy(dtype=float))
    assert all(np.isnan(r.values[1]) for r in rows), "資料包沒有的欄位是 NaN"
    source.visible_until = "2026-03-02T01:30:30.000000+00:00"
    late = source.readings("WT002", ["WGEN_GnBrgTmp1"], start="2026-03-02T01:30:00Z", end="2026-03-02T01:31:00Z")
    assert late and all(r.timestamp < source.visible_until for r in late), "晚到的讀值看不到"


def test_ten_minute_rows_are_complete_windows_stamped_at_their_end() -> None:
    pack = _pack("z72-starter-01")
    frame = br.ten_minute_frame(pack.stats)
    whole = pack.stats[~pack.stats["is_partial"].astype(bool)]
    assert len(frame) == len(whole) and (frame["timestamp"].to_numpy() == whole["window_end"].to_numpy()).all()
    name = next(c.name for c in sp.pack_columns() if c.tag.id == "WGEN_GnBrgTmp1")
    assert np.allclose(frame[name].to_numpy(dtype=float), whole[f"{name}_avg"].to_numpy(dtype=float), equal_nan=True)


def test_degraders_are_reproducible() -> None:
    raw = _pack("z72-starter-01").raw
    gaps = br.degrade(raw, "gaps")
    assert 0.7 * len(raw) < len(gaps) < 0.9 * len(raw) and gaps.equals(br.degrade(raw, "gaps"))
    doubled = br.degrade(raw, "duplicates")
    assert 1.05 * len(raw) < len(doubled) < 1.15 * len(raw)
    assert br.degrade(raw, "raw") is raw


# ── 2. 出勤與答案 ─────────────────────────────────────────────────────────


def test_one_dispatch_per_stop_with_the_cutoff_one_sample_later() -> None:
    pack = _pack("z72-starter-05")
    found = br.dispatches(pack)
    per_turbine = {}
    for d in found:
        assert d.cutoff - d.trip_ts == timedelta(seconds=pack.sample_period_s)
        previous = per_turbine.get(d.turbine_id)
        assert previous is None or d.trip_ts - previous >= br.DISPATCH_GAP, "同一次停機只開一張"
        per_turbine[d.turbine_id] = d.trip_ts
    dips = [d for d in found if d.code == 482]
    assert len({d.turbine_id for d in dips}) >= 3, "電網事件讓多台同時跳機"


def test_answers_come_from_the_ground_truth() -> None:
    pack, truth = _pack("z72-starter-01"), _truth("z72-starter-01")
    (bearing,) = [d for d in br.dispatches(pack) if d.turbine_id == "WT002"]
    answer = br.answer_for(bearing, truth)
    assert answer["has_fault"] and [f["scenario_id"] for f in answer["faults"]] == ["bearing_wear"]
    names = {c.tag.id: c.name for c in sp.pack_columns()}
    assert names["WGEN_GnBrgTmp1"] in answer["faults"][0]["key_signals"], "重點訊號換成卡片用的欄位名"
    pack, truth = _pack("z72-starter-05"), _truth("z72-starter-05")
    dip = next(d for d in br.dispatches(pack) if d.code == 482)
    answer = br.answer_for(dip, truth)
    assert not answer["has_fault"] and answer["farm_events"][0]["kind"] == "grid_voltage_dip"


# ── 3. 護欄 ───────────────────────────────────────────────────────────────


def test_the_example_packs_pass_the_guardrails(replayed: dict) -> None:
    raw = replayed["modes"]["raw"]["summary"]
    assert raw["dispatches"] >= 20 and raw["with_fault"] >= 15
    assert raw["key_signal_flagged"] >= 0.6, "有故障的出勤，重點訊號要被標出來"
    assert raw["false_escalation"] <= 0.2, "沒有故障（干擾、電網事件）的出勤不要誤判"
    assert raw["farm_context_shown"] == 1.0, "電網事件的卡要列出同場同時同碼的機組"
    assert raw["manual_found"] == 1.0, "每個跳機碼都查得到手冊"
    for row in replayed["modes"]["raw"]["rows"]:
        assert "farm_event" not in json.dumps(row["flags"]), "卡片只標資料品質，不帶答案"


def test_bad_data_is_flagged_on_the_card(replayed: dict) -> None:
    stale = replayed["modes"]["stale"]
    assert all("stale_data" in row["flags"] for row in stale["rows"]), "讀值晚到：每張卡都標出來"
    assert stale["summary"]["degraded"] == 1.0
    ten = replayed["modes"]["ten_minute"]["summary"]
    assert ten["dispatches"] == replayed["modes"]["raw"]["summary"]["dispatches"], "只有 10 分鐘資料也做得出卡"
    duplicates = replayed["modes"]["duplicates"]["summary"]
    assert duplicates["key_signal_flagged"] == replayed["modes"]["raw"]["summary"]["key_signal_flagged"], \
        "重複的讀值不改變結果"


def test_the_cli_writes_a_report(tmp_path) -> None:
    sys.path.insert(0, str(PROJECT_ROOT / "tools"))
    import replay_fault_cards

    report, data = tmp_path / "report.md", tmp_path / "rows.json"
    assert replay_fault_cards.main(["--modes", "raw", "--markdown", str(report), "--json", str(data)]) == 0
    text = report.read_text(encoding="utf-8")
    assert text.startswith("# 故障出勤卡離線重播") and "原始 10 秒資料" in text
    assert json.loads(data.read_text(encoding="utf-8"))["modes"]["raw"]["rows"]
