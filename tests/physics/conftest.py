"""Physics 自我驗證框架 — pytest 共用設定（WMOM-20260505-23）。

此 conftest 同時服務 Layer 1-7 所有 validator + 報告紀錄：

* `sys.path` 注入：把 `modules/monitoring` 放到 import path，讓
  `simulator.physics.*` 可以直接 import。
* Layer 7（測試紀錄保存）：`pytest_sessionfinish` hook 在 session 結束時
  自動產出 markdown + JSON 報告到 `tests/physics/reports/{YYYY}/{MM}/`，
  含 YAML metadata header（timestamp / git / python / pass-fail / duration）。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# ──────────────────────────────────────────────────────────────
# repo 結構：repo_root/tests/physics/conftest.py
# 三個 parents 上去就是 repo root；monitoring 物理模組在
# repo_root/modules/monitoring/ 之下。
# ──────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
MONITORING_ROOT = REPO_ROOT / "modules" / "monitoring"
REPORTS_DIR = Path(__file__).resolve().parent / "reports"
BASELINE_JSON = REPORTS_DIR / "_baseline" / "pytest_baseline.json"

if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))


# ══════════════════════════════════════════════════════════════
# Layer 7 — 測試紀錄保存（pytest hooks）
# ══════════════════════════════════════════════════════════════

# 透過 module-level 變數收集 session 資訊
_SESSION_START: float = 0.0
_TEST_RESULTS: List[Dict[str, Any]] = []  # 每筆 = {nodeid, outcome, duration}


def pytest_sessionstart(session):  # noqa: ARG001
    """記錄 session 起始時間。"""
    global _SESSION_START
    _SESSION_START = time.time()
    _TEST_RESULTS.clear()


def pytest_runtest_logreport(report):
    """收集每個 test 的結果（call phase 才算）。"""
    if report.when == "call":
        _TEST_RESULTS.append({
            "nodeid": report.nodeid,
            "outcome": report.outcome,  # "passed" / "failed" / "skipped"
            "duration": round(report.duration, 4),
        })


def pytest_sessionfinish(session, exitstatus):
    """Session 結束 → 寫入 markdown + JSON 報告。

    跳過寫入的條件：
    - WINDMINDOM_SKIP_REPORT 環境變數設為 1（CI debug 用）
    - 沒有任何 test 跑（collect-only / collection error）
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if os.environ.get("WINDMINDOM_SKIP_REPORT") == "1":
        return
    if not _TEST_RESULTS:
        return

    duration_sec = round(time.time() - _SESSION_START, 2)
    passed = sum(1 for r in _TEST_RESULTS if r["outcome"] == "passed")
    failed = sum(1 for r in _TEST_RESULTS if r["outcome"] == "failed")
    skipped = sum(1 for r in _TEST_RESULTS if r["outcome"] == "skipped")

    metadata = _build_metadata(
        exit_status=exitstatus,
        duration_sec=duration_sec,
        passed=passed, failed=failed, skipped=skipped,
    )

    drift = _compute_baseline_drift(metadata)
    metadata["baseline_drift"] = drift

    # output paths
    now = dt.datetime.now()
    month_dir = REPORTS_DIR / f"{now.year:04d}" / f"{now.month:02d}"
    month_dir.mkdir(parents=True, exist_ok=True)
    ts = now.strftime("%Y-%m-%d-%H%M")
    md_path = month_dir / f"{ts}-pytest.md"
    json_path = month_dir / f"{ts}-pytest.json"

    _write_markdown(md_path, metadata, _TEST_RESULTS, drift)
    _write_json(json_path, metadata, _TEST_RESULTS)


# ── Helpers ───────────────────────────────────────────────────

def _git_info() -> Dict[str, Any]:
    """取得 git commit / branch / dirty 狀態。"""
    def cmd(args: List[str]) -> str:
        try:
            r = subprocess.run(  # noqa: S603
                args, cwd=str(REPO_ROOT), capture_output=True, text=True,
                check=False, timeout=5.0,
            )
            return r.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""
    return {
        "git_commit": cmd(["git", "rev-parse", "--short", "HEAD"]) or "unknown",
        "git_branch": cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"]) or "unknown",
        "git_dirty": bool(cmd(["git", "status", "--porcelain"])),
    }


def _build_metadata(*, exit_status: int, duration_sec: float,
                    passed: int, failed: int, skipped: int) -> Dict[str, Any]:
    git = _git_info()
    return {
        "timestamp": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "git_commit": git["git_commit"],
        "git_branch": git["git_branch"],
        "git_dirty": git["git_dirty"],
        "python_version": sys.version.split()[0],
        "test_type": "pytest",
        "exit_status": int(exit_status),
        "duration_sec": duration_sec,
        "total_pass": passed,
        "total_fail": failed,
        "total_skip": skipped,
        "total_count": passed + failed + skipped,
    }


def _compute_baseline_drift(meta: Dict[str, Any]) -> Dict[str, Any]:
    """比對 baseline JSON，計算 drift 摘要。

    若 baseline 不存在 → 回傳 {"baseline_present": False}。
    """
    if not BASELINE_JSON.exists():
        return {"baseline_present": False}
    try:
        with BASELINE_JSON.open(encoding="utf-8") as f:
            base = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"baseline_present": False, "error": "baseline read failed"}

    base_meta = base.get("metadata", {})
    base_pass = base_meta.get("total_pass", 0)
    base_fail = base_meta.get("total_fail", 0)
    base_total = base_meta.get("total_count", 0)
    delta_pass = meta["total_pass"] - base_pass
    delta_fail = meta["total_fail"] - base_fail
    delta_total = meta["total_count"] - base_total

    # 失敗的 test 名稱集合（baseline 裡的 vs 當前）
    base_failures = {
        r["nodeid"] for r in base.get("results", [])
        if r.get("outcome") == "failed"
    }
    cur_failures = {
        r["nodeid"] for r in _TEST_RESULTS
        if r["outcome"] == "failed"
    }
    return {
        "baseline_present": True,
        "baseline_commit": base_meta.get("git_commit"),
        "baseline_timestamp": base_meta.get("timestamp"),
        "delta_pass": delta_pass,
        "delta_fail": delta_fail,
        "delta_total": delta_total,
        "new_failures": sorted(cur_failures - base_failures),
        "fixed_failures": sorted(base_failures - cur_failures),
    }


def _write_markdown(path: Path, meta: Dict[str, Any],
                    results: List[Dict[str, Any]],
                    drift: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("---")
    for k, v in meta.items():
        if isinstance(v, dict):
            lines.append(f"{k}:")
            for kk, vv in v.items():
                lines.append(f"  {kk}: {vv}")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append("# Pytest Report — windMindOM physics validation")
    lines.append("")
    lines.append(
        f"**Result：** {meta['total_pass']} pass / {meta['total_fail']} fail "
        f"/ {meta['total_skip']} skip   "
        f"(`exit={meta['exit_status']}`, {meta['duration_sec']} s)"
    )
    lines.append("")

    # baseline drift
    if drift.get("baseline_present"):
        lines.append("## Baseline drift")
        lines.append("")
        lines.append(
            f"- baseline commit: `{drift['baseline_commit']}` "
            f"({drift['baseline_timestamp']})"
        )
        lines.append(
            f"- delta_pass={drift['delta_pass']:+d}  "
            f"delta_fail={drift['delta_fail']:+d}  "
            f"delta_total={drift['delta_total']:+d}"
        )
        if drift["new_failures"]:
            lines.append("- **New failures**:")
            for nf in drift["new_failures"]:
                lines.append(f"  - `{nf}`")
        if drift["fixed_failures"]:
            lines.append("- Fixed failures:")
            for ff in drift["fixed_failures"]:
                lines.append(f"  - `{ff}`")
        if not drift["new_failures"] and not drift["fixed_failures"]:
            lines.append("- failure set unchanged vs baseline")
    else:
        lines.append("## Baseline drift")
        lines.append("")
        lines.append("No baseline yet — see `tests/physics/reports/_baseline/`.")
    lines.append("")

    # 失敗清單（人讀）
    failures = [r for r in results if r["outcome"] == "failed"]
    if failures:
        lines.append("## Failures")
        lines.append("")
        for r in failures:
            lines.append(f"- `{r['nodeid']}` ({r['duration']} s)")
        lines.append("")

    # 各 test file 統計
    by_file: Dict[str, Dict[str, int]] = {}
    for r in results:
        file_part = r["nodeid"].split("::")[0]
        d = by_file.setdefault(file_part, {"pass": 0, "fail": 0, "skip": 0})
        if r["outcome"] == "passed":
            d["pass"] += 1
        elif r["outcome"] == "failed":
            d["fail"] += 1
        else:
            d["skip"] += 1
    lines.append("## Per-file summary")
    lines.append("")
    lines.append("| File | Pass | Fail | Skip |")
    lines.append("|------|------|------|------|")
    for fp in sorted(by_file):
        d = by_file[fp]
        lines.append(f"| `{fp}` | {d['pass']} | {d['fail']} | {d['skip']} |")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def _write_json(path: Path, meta: Dict[str, Any],
                results: List[Dict[str, Any]]) -> None:
    payload = {
        "metadata": meta,
        "results": results,
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
