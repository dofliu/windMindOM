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
PACK_IDS = ["z72-starter-01", "z72-starter-02", "z72-starter-03", "z72-starter-04"]


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


def test_kit_vocabulary_is_a_copy_of_the_shared_source() -> None:
    """詞彙的唯一來源在 shared/data（伺服器檢查 WS 預測用）；kit 的副本由 build_rag_starter_kit 同步。"""
    shared = PROJECT_ROOT / "shared" / "data" / "rag_assistant_vocabulary.json"
    assert (KIT / "vocabulary.json").read_bytes() == shared.read_bytes()


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
    answers = json.loads((KIT / "answers" / f"{pack_id}.ground_truth.json").read_text(encoding="utf-8"))
    secrets_ = set(FAULT_SCENARIOS) | {answers["scenario_name"]} | {
        c[k] for c in answers["cases"] for k in ("fault_name_en", "fault_name_zh", "component", "root_cause")}
    for name in (sp.FILE_MANIFEST, sp.FILE_EVENTS, sp.FILE_TAGS):
        text = (pack_dir / name).read_text(encoding="utf-8")
        assert not [x for x in secrets_ if x in text], f"{name} 透露了答案"


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
    # 反過來：最後改成錯的 → 元件錯、但群組對（同屬 pitch）；最後錯了就沒有延遲 / 早期預警
    report = _score([gt], [
        _pred("WT001", "2026-01-01T01:40:00Z", "pitch_system_blade_1"),
        _pred("WT001", "2026-01-01T02:10:00Z", "pitch_control_system"),
    ])
    case = report.case_results[0]
    assert not case.component_correct and case.component_group_correct
    assert not case.early_warning and case.latency_s is None and case.misdiagnosis_predictions == 1


def test_guessing_every_component_does_not_buy_an_early_warning() -> None:
    """警報前每 10 分鐘把 11 個元件都猜一遍、最後才答對：早期預警 0、誤診全部記下來。"""
    gt = _gt([_case("C001", "WT001", "main_bearing", "2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z")])
    lines = [_pred("WT001", f"2026-01-01T01:{m:02d}:00Z", comp) for m in range(10, 60, 10) for comp in COMPONENTS]
    lines.append(_pred("WT001", "2026-01-01T02:05:00Z", "main_bearing", refs=[262]))
    report = _score([gt], lines)
    case = report.case_results[0]
    assert case.component_correct and not case.early_warning and case.latency_s == 300.0
    assert case.misdiagnosis_predictions == 5 * (len(COMPONENTS) - 1) == report.misdiagnosis_predictions
    assert len(case.components_claimed) == len(COMPONENTS)


def test_time_to_diagnosis_starts_at_the_last_unbroken_correct_run() -> None:
    gt = _gt([_case("C001", "WT001", "main_bearing", "2026-01-01T01:00:00Z", "2026-01-01T02:00:00Z")])
    report = _score([gt], [
        _pred("WT001", "2026-01-01T01:30:00Z", "main_bearing"),
        _pred("WT001", "2026-01-01T01:40:00Z", "generator_stator"),
        _pred("WT001", "2026-01-01T01:50:00Z", "main_bearing"),
        _pred("WT001", "2026-01-01T02:30:00Z", "main_bearing"),
    ])
    case = report.case_results[0]
    assert case.first_correct_ts == "2026-01-01T01:50:00.000000Z" and case.latency_s == -600.0 and case.early_warning


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


def test_superseded_case_merges_into_its_replacement() -> None:
    """同機組同故障再注入：故障從第一次注入就在，時間窗與第一個警報都取最早那次。"""
    gt = _gt([
        _case("C001", "WT001", "main_bearing", "2026-01-01T01:00:00Z", "2026-01-01T01:30:00Z", superseded=True),
        _case("C002", "WT001", "main_bearing", "2026-01-01T03:00:00Z", None),
    ])
    report = _score([gt], [_pred("WT001", "2026-01-01T02:00:00Z", "main_bearing")])
    assert [r.case_id for r in report.case_results] == ["C002"]
    case = report.case_results[0]
    assert case.component_correct and report.false_alarm_predictions == 0, "再注入前的正確診斷不是誤報"
    assert case.latency_s == 1800.0 and not case.early_warning, "第一個警報取被取代那次的"


def test_pre_existing_case_has_no_timing_score() -> None:
    gt = _gt([_case("C001", "WT002", "transformer", None, None, codes=[417, 444], pre_existing=True)])
    report = _score([gt], [_pred("WT002", "2026-01-01T00:20:00Z", "transformer", refs=[417])])
    case = report.case_results[0]
    assert case.component_correct and not case.timing_scored
    assert not case.early_warning and case.latency_s is None, "開始時間不明：不算早期預警"


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


def test_manual_refs_hit_at_k_boundaries_and_cap() -> None:
    def result(refs: List[object]):  # type: ignore[no-untyped-def]
        gt = _gt([_case("C001", "WT001", "main_bearing", "2026-01-01T01:00:00Z", None, codes=[262])])
        line = json.dumps({"pack_id": "p1", "turbine_id": "WT001", "ts": "2026-01-01T02:00:00Z",
                           "category": "real_fault", "component": "main_bearing", "manual_refs": refs})
        return _score([gt], [line]).case_results[0]

    def rr(refs: List[object]) -> float:
        case = result(refs)
        return case.manual_reciprocal_rank if case.detected else -1.0

    assert rr([1, 2, 262]) == pytest.approx(1 / 3) and result([1, 2, 262]).manual_hit_at_3
    assert rr([1, 2, 3, 262]) == pytest.approx(0.25) and not result([1, 2, 3, 262]).manual_hit_at_3
    assert result([262]).manual_hit_at_1 and not result([1, 262]).manual_hit_at_1
    assert rr([1, 1, 1, 262]) == pytest.approx(0.5), "重複的碼先去重"
    assert rr(list(range(1, 11)) + [262]) == 0.0, "只看前 10 個（MRR@10）"
    assert rr([True, 262]) == -1.0, "bool 不是事件碼：整行無效"


def test_time_edges_ties_and_empty_inputs() -> None:
    gt = _gt([_case("C001", "WT001", "main_bearing", "2026-01-01T01:00:00Z", None)])
    report = _score([gt], [
        _pred("WT001", "2026-01-01T09:00:00+08:00", "main_bearing"),  # ＝01:00Z，窗的起點
        _pred("WT001", "2026-01-01T06:00:01Z", "generator_stator"),  # 晚於 sim_end
    ])
    assert report.case_results[0].component_correct and report.false_alarm_predictions == 1
    tie = _score([gt], [_pred("WT001", "2026-01-01T02:00:00Z", "generator_stator"),
                        _pred("WT001", "2026-01-01T02:00:00Z", "main_bearing")])
    assert tie.case_results[0].component_correct, "同一時刻依行號，後寫的是最後判斷"
    assert _score([gt], []).detected == 0
    empty = _score([_gt([])], [_pred("WT001", "2026-01-01T02:00:00Z", "main_bearing")])
    assert (empty.cases, empty.detection_rate, empty.false_alarm_predictions) == (0, 0.0, 1)


def test_false_alarm_episodes_do_not_depend_on_output_rate() -> None:
    gt = _gt([], healthy=["WT002"])
    lines = [_pred("WT002", f"2026-01-01T01:{m:02d}:00Z", "main_bearing") for m in range(0, 60, 5)]
    lines.append(_pred("WT002", "2026-01-01T03:00:00Z", "main_bearing"))
    lines.append(_pred("WT002", "2026-01-01T03:00:00Z", "transformer"))
    report = _score([gt], lines)
    assert (report.false_alarm_predictions, report.false_alarm_episodes, report.false_alarm_turbines) == (14, 3, 1)


def test_hostile_lines_are_reported_not_fatal() -> None:
    report = _score([_gt([])], [
        '{"pack_id": "p1", "turbine_id": "WT001", "ts": "0001-01-01T00:00:00+05:00", "category": "nuisance"}',
        "[" * 100_000,
        '{"pack_id": "p1", "turbine_id": "WT001", "ts": "2026-01-01T02:00:00Z", "category": "real_fault", '
        '"component": ["main_bearing"]}',
        '{"pack_id": "p1", "turbine_id": "WT001", "ts": "yesterday", "category": "nuisance"}',
    ])
    assert [i["line"] for i in report.invalid_predictions] == [1, 2, 3, 4]
    assert "vocabulary" in str(report.invalid_predictions[2]["reason"])


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
    # BOM（Windows 記事本）照讀；UTF-16（PowerShell 5 的 >）回 2，不是 traceback
    predictions.write_text(_pred("WT001", "2026-01-01T02:00:00Z", "main_bearing") + "\n", encoding="utf-8-sig")
    assert score.main(["--answers", str(answers), "--predictions", str(predictions)]) == 0
    assert "格式錯誤" not in capsys.readouterr().out
    assert score.main(["--answers", str(answers), str(answers), "--predictions", str(predictions)]) == 2, \
        "同一個資料包的答案給兩次"
    predictions.write_text(_pred("WT001", "2026-01-01T02:00:00Z", "main_bearing") + "\n", encoding="utf-16")
    assert score.main(["--answers", str(answers), "--predictions", str(predictions)]) == 2
    # JSON 字串裡的 U+2028 / U+0085 / \x0c 是合法字元（ensure_ascii=False 不跳脫），不是換行：照算一筆
    line = json.loads(_pred("WT001", "2026-01-01T02:00:00Z", "main_bearing"))
    line["root_cause"] = "軸承\u2028磨耗\u0085\x0c"
    predictions.write_text(json.dumps(line, ensure_ascii=False) + "\r\n", encoding="utf-8")
    capsys.readouterr()
    assert score.main(["--answers", str(answers), "--predictions", str(predictions)]) == 0
    assert "格式錯誤" not in capsys.readouterr().out


def test_answers_can_be_a_full_pack_directory(tmp_path: Path) -> None:
    """評分端版資料包（/pack/full、CLI --ground-truth）的答案檔叫 ground_truth.json。"""
    pack = tmp_path / "z72-scenario-00012"
    pack.mkdir()
    (pack / "ground_truth.json").write_text(json.dumps(_gt([])), encoding="utf-8")
    assert [a["pack_id"] for a in score.load_answers([tmp_path])] == ["p1"]
    assert [a["pack_id"] for a in score.load_answers([pack])] == ["p1"]


# ── 4. 基準助手 ──────────────────────────────────────────────────────────────


def test_baseline_scores_on_the_starter_packs(tmp_path: Path) -> None:
    """README 與合約 §8 引用的基準數字。"""
    output = tmp_path / "baseline.jsonl"
    assert baseline.main([str(KIT / "packs"), "-o", str(output)]) == 0
    predictions, invalid = score.read_predictions(output.read_text(encoding="utf-8").splitlines(), COMPONENTS)
    assert invalid == [] and predictions
    report = score.score(score.load_answers([KIT / "answers"]), predictions, COMPONENTS)
    assert (report.cases, report.detected) == (8, 8)
    assert (report.component_accuracy, report.component_group_accuracy, report.category_accuracy) == (0.875, 1.0, 0.75)
    # 讀值像真故障的感測器故障（風向標漂移、軸承溫度量測回路）判錯類別；有專屬碼的（229）判對
    wrong = {(r.pack_id, r.turbine_id) for r in report.case_results if not r.category_correct}
    assert wrong == {("z72-starter-03", "WT003"), ("z72-starter-04", "WT003")}
    assert (report.manual_hit_at_1, report.early_warnings, report.false_alarm_predictions) == (1.0, 0, 0)
    assert report.latency_median_s == 0.0


def test_baseline_only_uses_events_up_to_each_prediction() -> None:
    events = [
        {"ts": "2026-01-01T01:00:00Z", "turbine_id": "WT001", "event_type": "alarm_raised", "alarm_code": 262,
         "alarm_text": "Main bearing 1 temperature high"},
        {"ts": "2026-01-01T01:05:00Z", "turbine_id": "WT001", "event_type": "trip", "alarm_code": 240,
         "alarm_text": "Bearing 1 temperature very high"},
        {"ts": "2026-01-01T01:30:00Z", "turbine_id": "WT001", "event_type": "alarm_raised", "alarm_code": 262,
         "alarm_text": "Main bearing 1 temperature high"},
        {"ts": "2026-01-01T02:00:00Z", "turbine_id": "WT002", "event_type": "info", "alarm_code": 201,
         "alarm_text": "Windspeed too high"},
    ]
    out = baseline.diagnose("p1", events)
    assert [(p["ts"], p["manual_refs"]) for p in out[:2]] == [("2026-01-01T01:00:00Z", [262]),
                                                              ("2026-01-01T01:05:00Z", [240, 262])]
    assert len(out) == 3 and out[2]["category"] == "nuisance", "同一機組再出現的碼不重複輸出"


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


def test_pack_reader_stats_until_only_returns_finished_windows() -> None:
    pack = pack_reader.load_pack(KIT / "packs" / "z72-starter-01", verify=False)
    windows = pack.stats_until("2026-03-02T02:05:00", turbine_id="WT002")  # naive＝UTC
    assert windows["window_end"].max() == pack_reader._ts("2026-03-02T02:00:00Z")
    raw = pack.raw_until("2026-03-02T02:05:00", columns=["timestamp", "Z72PLC__UI_Loc_WTUR_Analogue_TotPwrAt"])
    assert list(raw.columns) == ["timestamp", "turbine_id", "Z72PLC__UI_Loc_WTUR_Analogue_TotPwrAt"]


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
    with builder._sim_clock(spec.start):
        import simulator.engine as engine_mod
        import wind_model as wind_model_mod

        assert engine_mod.utc_now() == wind_model_mod.utc_now() == spec.start, "兩處時鐘都要釘住才能重產"
    storage = Storage(db_path=str(tmp_path / "kit.db"))
    sid = builder.generate(storage, spec)
    manifest = sp.export_scenario_pack(storage, sid, tmp_path / "packs" / spec.pack_id, pack_id=spec.pack_id)
    answers = sp.export_ground_truth(storage, sid, tmp_path / "answers" / "a.json", pack_id=spec.pack_id)
    assert manifest["pack_id"] == answers["pack_id"] == "z72-test-01"
    assert manifest["sim_start"] == "2026-01-15T03:00:10.000000Z" and manifest["wind_profile"] == "rated"
    assert pack_reader.verify_pack(tmp_path / "packs" / spec.pack_id) == []
    assert [c["fault_id"] for c in answers["cases"]] == ["generator_overspeed"]
    for bad in ("Bad ID", "z72-abc\n", "-abc", "abc-", "ab"):
        with pytest.raises(ValueError, match="pack_id"):
            sp.export_scenario_pack(storage, sid, tmp_path / "bad", pack_id=bad)
    with pytest.raises(sp.ScenarioPackError) as exc:
        sp.export_ground_truth(storage, 99999, tmp_path / "none.json")
    assert exc.value.status_code == 404

    # 可重產：同一個設定再生成一次（全新 DB），資料檔逐位元相同（_sim_clock 釘住時鐘才成立）
    storage2 = Storage(db_path=str(tmp_path / "kit2.db"))
    manifest2 = sp.export_scenario_pack(storage2, builder.generate(storage2, spec), tmp_path / "again",
                                        pack_id=spec.pack_id)
    for name in (sp.FILE_RAW, sp.FILE_STATS, sp.FILE_EVENTS):
        assert manifest2["files"][name] == manifest["files"][name], name  # type: ignore[index]


def test_only_the_legacy_contract_label_is_relabelled() -> None:
    assert sp.ground_truth_for_pack({"contract_version": "0.1"}, "p")["contract_version"] == "1.0"
    assert sp.ground_truth_for_pack({"contract_version": "1.1"}, "p")["contract_version"] == "1.1"
