"""RAG 學生專題 starter kit（WMOM-20261021-09，EPIC-DS Phase 3d）。

守住：
1. 詞彙檔涵蓋故障庫的每個元件 / 類別（-08 加新故障時要同步更新合約詞彙）
2. commit 的範例資料包完整、盲測、格式與目前的匯出器一致；答案與資料包對得上
3. 評分規則（合約 §8）：對應、誤報、最後診斷 / 第一次正確、早期預警、手冊 hit@k / MRR、格式錯誤
4. 基準助手在範例上的成績（README / 合約引用的數字）
5. 讀取工具「只看當下以前」；產生工具能跑完一個小情境
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Dict, List, Optional

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for _p in (PROJECT_ROOT, PROJECT_ROOT / "modules" / "monitoring", PROJECT_ROOT / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from server import scenario_pack as sp  # noqa: E402
from simulator.ground_truth import CONTRACT_VERSION  # noqa: E402
from simulator.physics.fault_engine import FAULT_SCENARIOS  # noqa: E402

KIT = PROJECT_ROOT / "examples" / "rag_starter_kit"
PACK_IDS = ["z72-starter-01", "z72-starter-02", "z72-starter-03"]


def _load(name: str) -> ModuleType:
    """以獨立模組名載入 kit 的腳本（kit 是給學生複製走的，不是 package）。"""
    spec = importlib.util.spec_from_file_location(f"rag_kit_{name}", KIT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


score = _load("score")
baseline = _load("baseline_assistant")
pack_reader = _load("pack_reader")
VOCAB = json.loads((KIT / "vocabulary.json").read_text(encoding="utf-8"))
COMPONENTS = score.load_vocabulary()


# ── 1. 詞彙 ──────────────────────────────────────────────────────────────────


def test_vocabulary_covers_the_fault_library() -> None:
    groups = {g["id"] for g in VOCAB["component_groups"]}
    assert all(c["group"] in groups for c in VOCAB["components"])
    categories = {c["id"] for c in VOCAB["categories"]}
    for fault_id, scenario in FAULT_SCENARIOS.items():
        assert scenario.component in COMPONENTS, f"{fault_id}: 元件 {scenario.component} 不在 vocabulary.json"
        assert scenario.category in categories, fault_id
    assert VOCAB["contract_version"].split(".")[0] == CONTRACT_VERSION.split(".")[0]
    assert set(VOCAB["event_types"]) >= {"alarm_raised", "trip", "state_change"}


# ── 2. 範例資料包 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("pack_id", PACK_IDS)
def test_committed_pack_is_complete_blind_and_current(pack_id: str) -> None:
    pack_dir = KIT / "packs" / pack_id
    assert pack_reader.verify_pack(pack_dir) == []
    manifest = json.loads((pack_dir / sp.FILE_MANIFEST).read_text(encoding="utf-8"))
    assert manifest["pack_id"] == pack_id and manifest["contract_version"] == CONTRACT_VERSION
    assert manifest["ground_truth_included"] is False
    assert {p.name for p in pack_dir.iterdir()} == set(sp.pack_file_names(False))
    # 格式與目前的匯出器一致：tag 註冊表 / 排除清單改了就要重建範例（python tools/build_rag_starter_kit.py）
    tags = json.loads((pack_dir / sp.FILE_TAGS).read_text(encoding="utf-8"))["tags"]
    assert tags == sp.tag_dictionary(sp.pack_columns()), "範例資料包的 tag 與匯出器不一致：請重建 starter kit"
    events = [json.loads(line) for line in (pack_dir / sp.FILE_EVENTS).read_text(encoding="utf-8").splitlines()]
    assert events and all(list(e) == list(sp.EVENT_KEYS) for e in events)
    for name in (sp.FILE_MANIFEST, sp.FILE_EVENTS, sp.FILE_TAGS):
        text = (pack_dir / name).read_text(encoding="utf-8")
        assert not [fid for fid in FAULT_SCENARIOS if fid in text], f"{name} 透露了故障 ID"


@pytest.mark.parametrize("pack_id", PACK_IDS)
def test_answers_match_their_pack(pack_id: str) -> None:
    answers = json.loads((KIT / "answers" / f"{pack_id}.ground_truth.json").read_text(encoding="utf-8"))
    manifest = json.loads((KIT / "packs" / pack_id / sp.FILE_MANIFEST).read_text(encoding="utf-8"))
    assert answers["pack_id"] == pack_id and answers["contract_version"] == CONTRACT_VERSION
    assert answers["turbines"] == manifest["turbines"]
    assert answers["cases"] and all(c["component"] in COMPONENTS for c in answers["cases"])
    assert all(c["first_alarm_ts"] for c in answers["cases"]), "範例的每個故障都要在情境內出警報"


def test_build_tool_lists_exactly_the_committed_packs() -> None:
    import build_rag_starter_kit as builder

    assert [s.pack_id for s in builder.STARTER_PACKS] == PACK_IDS
    assert sorted(p.name for p in (KIT / "packs").iterdir()) == PACK_IDS
    assert sorted(p.name for p in (KIT / "answers").iterdir()) == [f"{p}.ground_truth.json" for p in PACK_IDS]


# ── 3. 評分規則 ──────────────────────────────────────────────────────────────


def _gt(cases: List[Dict[str, object]], healthy: Optional[List[str]] = None) -> Dict[str, object]:
    return {"pack_id": "p1", "sim_start": "2026-01-01T00:00:10Z", "sim_end": "2026-01-01T06:00:00Z",
            "healthy_turbines": healthy or [], "cases": cases}


def _case(case_id: str, turbine: str, component: str, onset: Optional[str], first_alarm: Optional[str],
          category: str = "real_fault", codes: Optional[List[int]] = None, **extra: object) -> Dict[str, object]:
    return {"case_id": case_id, "turbine_id": turbine, "component": component, "category": category,
            "expected_alarm_codes": codes or [262, 240], "onset_ts": onset, "first_alarm_ts": first_alarm,
            "fault_id": "x", "superseded": False, **extra}


def _pred(turbine: str, ts: str, component: Optional[str], category: str = "real_fault",
          refs: Optional[List[int]] = None, pack: str = "p1") -> str:
    return json.dumps({"pack_id": pack, "turbine_id": turbine, "ts": ts, "category": category,
                       "component": component, "manual_refs": refs or []})


def _score(gts: List[Dict[str, object]], lines: List[str]):  # type: ignore[no-untyped-def]
    predictions, invalid = score.read_predictions(lines, COMPONENTS)
    return score.score(gts, predictions, COMPONENTS, invalid)


def test_perfect_early_diagnosis_scores_full_marks() -> None:
    gt = _gt([_case("C001", "WT001", "main_bearing", "2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z")])
    report = _score([gt], [_pred("WT001", "2026-01-01T01:30:00Z", "main_bearing", refs=[262, 240])])
    assert (report.detection_rate, report.component_accuracy, report.category_accuracy) == (1.0, 1.0, 1.0)
    assert (report.manual_hit_at_1, report.manual_mrr, report.early_warnings) == (1.0, 1.0, 1)
    assert report.latency_median_s == -1800.0 and report.false_alarm_predictions == 0


def test_final_diagnosis_counts_and_latency_uses_the_first_correct_one() -> None:
    gt = _gt([_case("C001", "WT001", "pitch_system_blade_1", "2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z",
                    codes=[335, 336])])
    report = _score([gt], [
        _pred("WT001", "2026-01-01T01:40:00Z", "pitch_control_system", refs=[351]),
        _pred("WT001", "2026-01-01T02:10:00Z", "pitch_system_blade_1", refs=[351, 336]),
    ])
    case = report.case_results[0]
    assert case.component_correct and case.latency_s == 600.0 and not case.early_warning
    assert case.manual_reciprocal_rank == 0.5 and case.manual_hit_at_3 and not case.manual_hit_at_1
    # 反過來：最後改成錯的 → 元件錯、但群組對（同屬 pitch）
    report = _score([gt], [
        _pred("WT001", "2026-01-01T01:40:00Z", "pitch_system_blade_1"),
        _pred("WT001", "2026-01-01T02:10:00Z", "pitch_control_system"),
    ])
    case = report.case_results[0]
    assert not case.component_correct and case.component_group_correct and case.early_warning


def test_false_alarms_on_healthy_turbines_and_before_onset() -> None:
    gt = _gt([_case("C001", "WT001", "main_bearing", "2026-01-01T03:00:00Z", None)], healthy=["WT002"])
    report = _score([gt], [
        _pred("WT001", "2026-01-01T02:59:59Z", "main_bearing"),
        _pred("WT002", "2026-01-01T04:00:00Z", "main_bearing"),
        _pred("WT002", "2026-01-01T04:10:00Z", "main_bearing"),
    ])
    assert (report.false_alarm_predictions, report.false_alarm_turbines, report.detected) == (3, 2, 0)


def test_sensor_fault_category_and_alarm_free_case_is_an_early_warning() -> None:
    gt = _gt([_case("C001", "WT003", "wind_vane_1", "2026-01-01T01:00:00Z", None, category="sensor_fault",
                    codes=[233])])
    wrong = _score([gt], [_pred("WT003", "2026-01-01T03:00:00Z", "wind_vane_1", category="real_fault")])
    right = _score([gt], [_pred("WT003", "2026-01-01T03:00:00Z", "wind_vane_1", category="sensor_fault")])
    assert wrong.category_accuracy == 0.0 and right.category_accuracy == 1.0
    assert right.early_warnings == 1 and right.latency_median_s is None, "沒有預期警報的 case：診斷到就算早期預警"


def test_multiple_cases_on_one_turbine_match_by_component() -> None:
    gt = _gt([
        _case("C001", "WT001", "main_bearing", "2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z"),
        _case("C002", "WT001", "generator_stator", "2026-01-01T03:00:00Z", None, codes=[264, 244]),
    ])
    report = _score([gt], [_pred("WT001", "2026-01-01T04:00:00Z", "main_bearing"),
                           _pred("WT001", "2026-01-01T04:05:00Z", "nacelle_ventilation")])
    first, second = report.case_results
    assert first.component_correct, "與某個 case 元件相同 → 對到那個 case"
    assert second.detected and not second.component_correct, "都不同 → 對到最近開始的 case"


def test_superseded_cases_are_not_scored_and_pre_existing_starts_at_sim_start() -> None:
    gt = _gt([
        _case("C001", "WT001", "main_bearing", "2026-01-01T01:00:00Z", None, superseded=True),
        _case("C002", "WT001", "main_bearing", "2026-01-01T02:00:00Z", None),
        _case("C003", "WT002", "transformer", None, None, codes=[417, 444]),
    ])
    report = _score([gt], [_pred("WT002", "2026-01-01T00:20:00Z", "transformer")])
    assert [r.case_id for r in report.case_results] == ["C002", "C003"]
    assert report.case_results[1].component_correct


def test_nuisance_unknown_packs_and_invalid_lines() -> None:
    gt = _gt([_case("C001", "WT001", "main_bearing", "2026-01-01T01:00:00Z", None)])
    report = _score([gt], [
        _pred("WT001", "2026-01-01T02:00:00Z", None, category="nuisance"),
        _pred("WT002", "2026-01-01T02:00:00Z", None, category="nuisance"),
        _pred("WT001", "2026-01-01T02:00:00Z", "main_bearing", pack="other-pack"),
        '{"pack_id": "p1", "turbine_id": "WT001", "ts": "2026-01-01T02:00:00Z", "category": "real_fault", '
        '"component": "main_bearings"}',
        '{"pack_id": "p1", "turbine_id": "WT001", "ts": "2026-01-01T02:00:00Z", "category": "broken"}',
        '{"pack_id": "p1", "turbine_id": "WT001", "ts": "2026-01-01T02:00:00Z", "category": "real_fault", '
        '"component": "main_bearing", "manual_refs": ["262"]}',
        "not json",
        "",
    ])
    assert (report.nuisance_predictions, report.nuisance_during_fault, report.ignored_predictions) == (2, 1, 1)
    assert [i["line"] for i in report.invalid_predictions] == [4, 5, 6, 7]
    assert "vocabulary" in str(report.invalid_predictions[0]["reason"])
    assert report.detected == 0


def test_cli_writes_a_json_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    answers = tmp_path / "p1.ground_truth.json"
    answers.write_text(json.dumps(_gt([_case("C001", "WT001", "main_bearing", "2026-01-01T01:00:00Z", None)])),
                       encoding="utf-8")
    predictions = tmp_path / "p.jsonl"
    predictions.write_text(_pred("WT001", "2026-01-01T02:00:00Z", "main_bearing") + "\n", encoding="utf-8")
    assert score.main(["--answers", str(tmp_path), "--predictions", str(predictions),
                       "--json", str(tmp_path / "report.json")]) == 0
    assert "元件正確率" in capsys.readouterr().out
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["component_accuracy"] == 1.0 and report["case_results"][0]["case_id"] == "C001"
    assert score.main(["--answers", str(tmp_path / "nothing"), "--predictions", str(predictions)]) == 2
    empty = tmp_path / "empty"
    empty.mkdir()
    assert score.main(["--answers", str(empty), "--predictions", str(predictions)]) == 2
    assert score.main(["--answers", str(tmp_path), "--predictions", str(tmp_path / "missing.jsonl")]) == 2


# ── 4. 基準助手 ──────────────────────────────────────────────────────────────


def test_baseline_scores_on_the_starter_packs(tmp_path: Path) -> None:
    """README 與合約 §8 引用的基準數字。"""
    output = tmp_path / "baseline.jsonl"
    assert baseline.main([str(KIT / "packs"), "-o", str(output)]) == 0
    predictions, invalid = score.read_predictions(output.read_text(encoding="utf-8").splitlines(), COMPONENTS)
    assert invalid == [] and predictions
    report = score.score(score.load_answers([KIT / "answers"]), predictions, COMPONENTS)
    assert (report.cases, report.detected) == (5, 5)
    assert (report.component_accuracy, report.component_group_accuracy, report.category_accuracy) == (0.8, 1.0, 0.8)
    assert (report.manual_hit_at_1, report.early_warnings, report.false_alarm_predictions) == (1.0, 0, 0)
    assert report.latency_median_s == 0.0


def test_baseline_only_uses_events_up_to_each_prediction() -> None:
    events = [
        {"ts": "2026-01-01T01:00:00Z", "turbine_id": "WT001", "event_type": "alarm_raised", "alarm_code": 262,
         "alarm_text": "Main bearing 1 temperature high"},
        {"ts": "2026-01-01T01:05:00Z", "turbine_id": "WT001", "event_type": "trip", "alarm_code": 240,
         "alarm_text": "Bearing 1 temperature very high"},
        {"ts": "2026-01-01T02:00:00Z", "turbine_id": "WT002", "event_type": "info", "alarm_code": 201,
         "alarm_text": "Windspeed too high"},
    ]
    out = baseline.diagnose("p1", events)
    assert [(p["ts"], p["manual_refs"]) for p in out[:2]] == [("2026-01-01T01:00:00Z", [262]),
                                                              ("2026-01-01T01:05:00Z", [240, 262])]
    assert out[2]["category"] == "nuisance"


# ── 5. 讀取工具與產生工具 ─────────────────────────────────────────────────────


def test_pack_reader_never_returns_future_data() -> None:
    pack = pack_reader.load_pack(KIT / "packs" / "z72-starter-01")
    cutoff = "2026-03-02T02:00:10Z"
    raw = pack.raw_until(cutoff, turbine_id="WT002", window="30min",
                         columns=["Z72PLC__UI_Loc_WGEN_Analogue_GnBrgTmp1"])
    assert len(raw) == 180 and raw["timestamp"].max() == pack_reader._ts(cutoff)
    assert set(raw["turbine_id"]) == {"WT002"}
    seen = list(pack.events_until(cutoff, turbine_id="WT002"))
    assert seen and seen[-1]["alarm_code"] == 262, "截止時刻的事件算看得到"
    assert all(pack_reader._ts(str(e["ts"])) <= pack_reader._ts(cutoff) for e in seen)
    assert len(pack.stats("WT002")) == 25 and 262 in pack.alarm_catalog
    assert "z72-starter-01" in pack_reader.summary(pack)


def test_pack_reader_rejects_a_tampered_pack(tmp_path: Path) -> None:
    import shutil

    copy = tmp_path / "pack"
    shutil.copytree(KIT / "packs" / "z72-starter-01", copy)
    with (copy / sp.FILE_EVENTS).open("a", encoding="utf-8") as handle:
        handle.write("\n")
    with pytest.raises(ValueError, match="events.jsonl"):
        pack_reader.load_pack(copy)


def test_build_tool_generates_a_small_pack(tmp_path: Path) -> None:
    import build_rag_starter_kit as builder
    from datetime import datetime, timezone

    from server.storage import Storage

    spec = builder.StarterPack(
        pack_id="z72-test-01", title="tiny", start=datetime(2026, 1, 15, 3, 0, tzinfo=timezone.utc),
        turbines=2, hours=0.5, wind_profile="rated",
        faults=({"scenario_id": "generator_overspeed", "turbine_id": "WT002", "offset_seconds": 0,
                 "severity_rate": 0.02},),
    )
    storage = Storage(db_path=str(tmp_path / "kit.db"))
    sid = builder.generate(storage, spec)
    manifest = sp.export_scenario_pack(storage, sid, tmp_path / "packs" / spec.pack_id, pack_id=spec.pack_id)
    answers = sp.export_ground_truth(storage, sid, tmp_path / "answers" / "a.json", pack_id=spec.pack_id)
    assert manifest["pack_id"] == answers["pack_id"] == "z72-test-01"
    assert manifest["sim_start"] == "2026-01-15T03:00:10.000000Z" and manifest["wind_profile"] == "rated"
    assert pack_reader.verify_pack(tmp_path / "packs" / spec.pack_id) == []
    assert [c["fault_id"] for c in answers["cases"]] == ["generator_overspeed"]
    with pytest.raises(ValueError, match="pack_id"):
        sp.export_scenario_pack(storage, sid, tmp_path / "bad", pack_id="Bad ID")
