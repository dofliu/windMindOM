"""Physics Health Check CLI（WMOM-20260505-23 Layer 6）。

一鍵體檢入口：跑全 Layer 1-5 validator + 30 分鐘 5 turbines short sim
（含 1 個 fault injection）+ 產出 markdown / JSON / 可選 matplotlib 圖表。

Usage:
    python tools/physics_health_check.py
    python tools/physics_health_check.py --no-save
    python tools/physics_health_check.py --no-plots
    python tools/physics_health_check.py --output-dir tests/physics/reports/manual

Exit code:
    0 — 全部 pass
    1 — 至少一項 fail / pytest 失敗

設計目標：
- 任何 physics 改動後跑一次 → 立刻知道 framework 是否仍 healthy
- 適合 CI（exit code）
- 產出可 commit 的紀錄（markdown + JSON），供日後 baseline diff
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
MONITORING_ROOT = REPO_ROOT / "modules" / "monitoring"
DEFAULT_REPORTS_BASE = REPO_ROOT / "tests" / "physics" / "reports"

if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))


# ════════════════════════════════════════════════════════════════════════
# Phase 1: pytest validators
# ════════════════════════════════════════════════════════════════════════

def run_pytest_validators() -> Dict[str, Any]:
    """跑 tests/physics/ 全 layer，回傳結果摘要。

    用 subprocess 而非直接 pytest.main，避免 conftest re-import / state 污染。
    """
    started = time.time()
    test_dir = str(REPO_ROOT / "tests" / "physics")
    cmd = [
        sys.executable, "-m", "pytest", test_dir, "--tb=short", "-q",
    ]
    proc = subprocess.run(  # noqa: S603 — 內部呼叫，受信任
        cmd, cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    duration = time.time() - started

    stdout = proc.stdout
    # 解析 pytest 結果摘要（最後一行如 "121 passed in 21.56s" 或 "X passed, Y failed"）
    last_lines = [ln for ln in stdout.strip().splitlines() if ln.strip()]
    summary_line = last_lines[-1] if last_lines else ""

    return {
        "exit_code": proc.returncode,
        "duration_sec": round(duration, 2),
        "summary_line": summary_line,
        "stdout_tail": "\n".join(last_lines[-12:]),
        "passed": proc.returncode == 0,
    }


# ════════════════════════════════════════════════════════════════════════
# Phase 2: 30-min short sim with 1 fault injection
# ════════════════════════════════════════════════════════════════════════

def run_short_sim(duration_sec: float = 1800.0,
                  turbine_count: int = 5,
                  V: float = 11.0,
                  fault_target_idx: int = 2,
                  fault_id: str = "bearing_wear",
                  fault_severity: float = 0.7) -> Dict[str, Any]:
    """跑短模擬：5 turbines × 30 min，第 3 台注入 bearing_wear。

    回傳 per-turbine 平均 metrics + 全 farm 統計。
    """
    from simulator.physics import TurbinePhysicsModel

    turbines = [TurbinePhysicsModel(seed=i + 1) for i in range(turbine_count)]
    # warm-up to production
    warm = 180
    for _ in range(warm):
        for m in turbines:
            m.step(wind_speed=V, wind_direction=180.0,
                   ambient_temp=15.0, dt=1.0)
    # inject fault on target
    turbines[fault_target_idx].active_faults = [
        {"scenario_id": fault_id, "severity": fault_severity},
    ]

    # collect samples（每 30 s 取 1 點，control overhead）
    sample_every = 30
    steps = int(duration_sec)
    samples: List[List[Dict[str, float]]] = [[] for _ in turbines]
    for s in range(steps):
        for i, m in enumerate(turbines):
            tags = m.step(wind_speed=V, wind_direction=180.0,
                          ambient_temp=15.0, dt=1.0)
            if s % sample_every == 0:
                samples[i].append(tags)

    # aggregate per turbine
    def avg(lst: List[Dict[str, float]], key: str) -> float:
        if not lst:
            return 0.0
        return float(sum(t.get(key, 0.0) for t in lst) / len(lst))

    per_turbine: List[Dict[str, Any]] = []
    for i, ts in enumerate(samples):
        is_faulty = (i == fault_target_idx)
        per_turbine.append({
            "turbine_id": f"WT{i + 1:03d}",
            "fault_injected": fault_id if is_faulty else None,
            "fault_severity": fault_severity if is_faulty else 0.0,
            "mean_power_kw": round(avg(ts, "WTUR_TotPwrAt"), 1),
            "mean_rotor_rpm": round(avg(ts, "WROT_RotSpd"), 3),
            "mean_gen_speed_rpm": round(avg(ts, "WGEN_GnSpd"), 3),
            "mean_stator_temp_c": round(avg(ts, "WGEN_GnStaTmp1"), 2),
            "mean_bearing_temp_c": round(avg(ts, "WGEN_GnBrgTmp1"), 2),
            "mean_vib_x_mm_s": round(avg(ts, "WNAC_VibMsNacXDir"), 3),
            "mean_vib_y_mm_s": round(avg(ts, "WNAC_VibMsNacYDir"), 3),
            "mean_cnv_water_temp_c": round(avg(ts, "WCNV_IGCTWtrTmp"), 2),
            "mean_coolant_level_pct": round(avg(ts, "WCOL_CoolantLvl"), 2),
        })

    # farm-level statistics
    powers = [t["mean_power_kw"] for t in per_turbine]
    n = len(powers)
    p_mean = sum(powers) / n
    p_var = sum((p - p_mean) ** 2 for p in powers) / n
    p_std = math.sqrt(p_var)

    healthy_powers = [
        t["mean_power_kw"] for t in per_turbine
        if t["fault_injected"] is None
    ]
    h_mean = sum(healthy_powers) / max(len(healthy_powers), 1)
    h_var = sum((p - h_mean) ** 2 for p in healthy_powers) / max(len(healthy_powers), 1)
    h_std = math.sqrt(h_var)

    return {
        "duration_sec": duration_sec,
        "turbine_count": turbine_count,
        "wind_mean_m_s": V,
        "fault_injected": fault_id,
        "fault_target": f"WT{fault_target_idx + 1:03d}",
        "fault_severity": fault_severity,
        "per_turbine": per_turbine,
        "farm_metrics": {
            "all_mean_power_kw": round(p_mean, 1),
            "all_power_std_kw": round(p_std, 1),
            "all_power_cv": round(p_std / max(p_mean, 1.0), 4),
            "healthy_mean_power_kw": round(h_mean, 1),
            "healthy_power_cv": round(h_std / max(h_mean, 1.0), 4),
            "spread_pct": round((max(powers) - min(powers)) / max(p_mean, 1.0), 4),
        },
    }


# ════════════════════════════════════════════════════════════════════════
# Phase 3: Health Assessment（per-category pass/warn/fail）
# ════════════════════════════════════════════════════════════════════════

def assess_health(sim: Dict[str, Any]) -> Dict[str, Any]:
    """根據 short sim 結果評估健康分級。

    Note：此函式 hardcode 假設 sim["fault_injected"] == "bearing_wear" 並用
    vibration X 作為 signature 門檻。若 run_short_sim 改用其他 fault scenario
    （e.g., converter_cooling_fault），需同步調整對應的 expected tag + 門檻，
    否則 fault signature check 會失去鑑別力。
    """
    farm = sim["farm_metrics"]
    fault_id = sim["fault_injected"]
    faulty = next(t for t in sim["per_turbine"] if t["fault_injected"] == fault_id)
    healthy = [t for t in sim["per_turbine"] if t["fault_injected"] is None]
    if not healthy:
        raise RuntimeError("No healthy turbines in short sim")
    h_avg_vib_x = sum(t["mean_vib_x_mm_s"] for t in healthy) / len(healthy)

    checks: List[Dict[str, Any]] = []

    # 1. Healthy spread sanity（individuality 機制有作用）
    spread = farm["spread_pct"]
    checks.append({
        "name": "healthy_spread",
        "value": spread,
        "ok_range": "[0.005, 0.50]",
        "pass": 0.005 < spread < 0.50,
    })

    # 2. Region 2-3 boundary mean power（V=11 → ~1700 kW lookup）
    h_mean_p = farm["healthy_mean_power_kw"]
    expected_p = 1700.0
    rel_err = abs(h_mean_p - expected_p) / expected_p
    checks.append({
        "name": "healthy_power_near_lookup",
        "value": round(rel_err, 4),
        "ok_range": "rel_err < 0.30",
        "pass": rel_err < 0.30,
    })

    # 3. Fault signature: bearing_wear 應推升 vibration
    fault_vib_delta = faulty["mean_vib_x_mm_s"] - h_avg_vib_x
    checks.append({
        "name": f"fault_signature_{fault_id}_vib_x",
        "value": round(fault_vib_delta, 3),
        "ok_range": "delta >= +0.4 mm/s",
        "pass": fault_vib_delta >= 0.4,
    })

    # 4. Healthy vibration overall RMS in ISO Zone A/B
    healthy_overall = math.sqrt(
        h_avg_vib_x ** 2
        + (sum(t["mean_vib_y_mm_s"] for t in healthy) / len(healthy)) ** 2
    )
    checks.append({
        "name": "healthy_vibration_iso_zone",
        "value": round(healthy_overall, 3),
        "ok_range": "<= 4.5 mm/s (ISO Zone B)",
        "pass": healthy_overall <= 4.5,
    })

    all_pass = all(c["pass"] for c in checks)
    return {
        "all_pass": all_pass,
        "checks": checks,
    }


# ════════════════════════════════════════════════════════════════════════
# Phase 4: Report writers
# ════════════════════════════════════════════════════════════════════════

def _git_info() -> Dict[str, str]:
    """取得當前 git commit / branch / dirty 狀態。"""
    def _cmd(args: List[str]) -> str:
        try:
            r = subprocess.run(  # noqa: S603
                args, cwd=str(REPO_ROOT), capture_output=True, text=True,
                check=False,
            )
            return r.stdout.strip()
        except OSError:
            return ""
    commit = _cmd(["git", "rev-parse", "--short", "HEAD"])
    branch = _cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    dirty = _cmd(["git", "status", "--porcelain"])
    return {
        "git_commit": commit or "unknown",
        "git_branch": branch or "unknown",
        "git_dirty": bool(dirty),
    }


def build_metadata(pytest_result: Dict[str, Any],
                   sim: Dict[str, Any],
                   assessment: Dict[str, Any]) -> Dict[str, Any]:
    """組合 YAML metadata header（也作為 JSON 的 metadata 區）。"""
    git = _git_info()
    return {
        "timestamp": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "git_commit": git["git_commit"],
        "git_branch": git["git_branch"],
        "git_dirty": git["git_dirty"],
        "python_version": sys.version.split()[0],
        "test_type": "health_check",
        "pytest_passed": pytest_result["passed"],
        "pytest_summary": pytest_result["summary_line"],
        "pytest_duration_sec": pytest_result["duration_sec"],
        "sim_duration_sec": sim["duration_sec"],
        "sim_turbine_count": sim["turbine_count"],
        "assessment_all_pass": assessment["all_pass"],
        "exit_code": (
            0 if (pytest_result["passed"] and assessment["all_pass"]) else 1
        ),
    }


def write_markdown(meta: Dict[str, Any],
                   pytest_result: Dict[str, Any],
                   sim: Dict[str, Any],
                   assessment: Dict[str, Any],
                   path: Path) -> None:
    """寫人讀的 markdown 報告。"""
    lines: List[str] = []
    lines.append("---")
    for k, v in meta.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append("# Physics Health Check Report")
    lines.append("")
    lines.append(f"**Status:** "
                 f"{'✅ ALL PASS' if meta['exit_code'] == 0 else '❌ FAIL'}")
    lines.append("")

    lines.append("## 1. Pytest Validators (Layer 1-5)")
    lines.append("")
    lines.append(f"- Summary: `{pytest_result['summary_line']}`")
    lines.append(f"- Duration: {pytest_result['duration_sec']} s")
    lines.append(f"- Exit code: {pytest_result['exit_code']}")
    lines.append("")

    lines.append("## 2. Short Simulation (Layer 6)")
    lines.append("")
    lines.append(
        f"- Duration: {sim['duration_sec']:.0f} s "
        f"({sim['duration_sec'] / 60:.1f} min)"
    )
    lines.append(f"- Turbines: {sim['turbine_count']}")
    lines.append(f"- Wind: {sim['wind_mean_m_s']} m/s")
    lines.append(
        f"- Fault injected on **{sim['fault_target']}**: "
        f"`{sim['fault_injected']}` (severity={sim['fault_severity']})"
    )
    lines.append("")

    lines.append("### Per-turbine snapshot (30-s mean of last sample)")
    lines.append("")
    lines.append(
        "| ID | Fault | P (kW) | rotor RPM | stator C | "
        "vib X mm/s | vib Y mm/s | coolant % |"
    )
    lines.append(
        "|----|-------|--------|-----------|-----------|"
        "------------|------------|------------|"
    )
    for t in sim["per_turbine"]:
        fault_label = t["fault_injected"] or "—"
        lines.append(
            f"| {t['turbine_id']} | {fault_label} | "
            f"{t['mean_power_kw']:.0f} | "
            f"{t['mean_rotor_rpm']:.2f} | "
            f"{t['mean_stator_temp_c']:.1f} | "
            f"{t['mean_vib_x_mm_s']:.2f} | "
            f"{t['mean_vib_y_mm_s']:.2f} | "
            f"{t['mean_coolant_level_pct']:.2f} |"
        )
    lines.append("")

    lines.append("### Farm-level metrics")
    lines.append("")
    for k, v in sim["farm_metrics"].items():
        lines.append(f"- `{k}`: {v}")
    lines.append("")

    lines.append("## 3. Health Assessment")
    lines.append("")
    lines.append("| Check | Value | OK range | Pass |")
    lines.append("|-------|-------|----------|------|")
    for c in assessment["checks"]:
        emoji = "✅" if c["pass"] else "❌"
        lines.append(
            f"| {c['name']} | {c['value']} | {c['ok_range']} | {emoji} |"
        )
    lines.append("")
    lines.append(
        f"**Assessment：{'ALL PASS' if assessment['all_pass'] else 'FAILED'}**"
    )
    lines.append("")

    lines.append("## 4. Pytest stdout (tail)")
    lines.append("")
    lines.append("```")
    lines.append(pytest_result["stdout_tail"])
    lines.append("```")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def write_json(meta: Dict[str, Any],
               pytest_result: Dict[str, Any],
               sim: Dict[str, Any],
               assessment: Dict[str, Any],
               path: Path) -> None:
    """寫機讀 JSON（baseline diff 用）。"""
    payload = {
        "metadata": meta,
        "pytest": pytest_result,
        "sim": sim,
        "assessment": assessment,
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def maybe_write_plots(sim: Dict[str, Any], output_dir: Path) -> List[str]:
    """畫關鍵圖（per-turbine power bar + vib bar）。matplotlib 缺席則 skip。"""
    try:
        import matplotlib  # type: ignore
        matplotlib.use("Agg")  # 避開 GUI backend
        import matplotlib.pyplot as plt  # type: ignore
    except ImportError:
        return []

    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    written: List[str] = []

    ids = [t["turbine_id"] for t in sim["per_turbine"]]
    powers = [t["mean_power_kw"] for t in sim["per_turbine"]]
    fault_target = sim["fault_target"]
    colors = ["#d9534f" if i == fault_target else "#5cb85c" for i in ids]

    fig1, ax1 = plt.subplots(figsize=(7, 3))
    ax1.bar(ids, powers, color=colors)
    ax1.set_ylabel("Mean Power (kW)")
    ax1.set_title("Per-turbine Power (red = fault target)")
    fig1.tight_layout()
    p1 = figures_dir / "per_turbine_power.png"
    fig1.savefig(p1, dpi=120)
    plt.close(fig1)
    written.append(str(p1.relative_to(output_dir)))

    vib_x = [t["mean_vib_x_mm_s"] for t in sim["per_turbine"]]
    vib_y = [t["mean_vib_y_mm_s"] for t in sim["per_turbine"]]
    fig2, ax2 = plt.subplots(figsize=(7, 3))
    x = list(range(len(ids)))
    width = 0.35
    ax2.bar([i - width / 2 for i in x], vib_x, width, color="#5bc0de", label="Vib X")
    ax2.bar([i + width / 2 for i in x], vib_y, width, color="#f0ad4e", label="Vib Y")
    ax2.set_xticks(x)
    ax2.set_xticklabels(ids)
    ax2.set_ylabel("Vibration RMS (mm/s)")
    ax2.axhline(2.3, color="gray", linestyle=":", label="ISO 10816 Zone A")
    ax2.axhline(4.5, color="black", linestyle="--", label="ISO Zone B")
    ax2.set_title("Per-turbine Vibration vs ISO 10816-3 zones")
    ax2.legend(loc="upper right", fontsize=8)
    fig2.tight_layout()
    p2 = figures_dir / "per_turbine_vibration.png"
    fig2.savefig(p2, dpi=120)
    plt.close(fig2)
    written.append(str(p2.relative_to(output_dir)))

    return written


# ════════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════════

def _output_dir(base: Path | None) -> Path:
    """產生 reports/{YYYY}/{MM}/health-{ts}/ 路徑。"""
    base = base or DEFAULT_REPORTS_BASE
    now = dt.datetime.now()
    ts = now.strftime("%Y-%m-%d-%H%M")
    return base / f"{now.year:04d}" / f"{now.month:02d}" / f"health-{ts}"


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-save", action="store_true",
        help="Do not write report files (just print summary).",
    )
    parser.add_argument(
        "--no-plots", action="store_true",
        help="Skip matplotlib figures (markdown / JSON still written).",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Override output dir (default: tests/physics/reports/YYYY/MM/health-TIMESTAMP/).",
    )
    parser.add_argument(
        "--skip-pytest", action="store_true",
        help="Skip Layer 1-5 pytest run（debug only — production 不要用）.",
    )
    parser.add_argument(
        "--sim-duration", type=float, default=1800.0,
        help="Short sim duration in seconds (default 1800 = 30 min).",
    )
    args = parser.parse_args(argv)

    print("=" * 70)
    print("Physics Health Check — windMindOM")
    print("=" * 70)

    # Phase 1: pytest
    if args.skip_pytest:
        print("\n[Phase 1] SKIPPED (--skip-pytest)")
        pytest_result = {
            "exit_code": 0, "duration_sec": 0.0,
            "summary_line": "skipped", "stdout_tail": "skipped",
            "passed": True,
        }
    else:
        print("\n[Phase 1] Running pytest tests/physics/ ...")
        pytest_result = run_pytest_validators()
        print(f"  → {pytest_result['summary_line']}")
        print(f"  → exit={pytest_result['exit_code']}, "
              f"duration={pytest_result['duration_sec']} s")

    # Phase 2: short sim
    print(f"\n[Phase 2] Running short sim "
          f"({args.sim_duration:.0f} s, 5 turbines, 1 fault)...")
    sim_started = time.time()
    sim = run_short_sim(duration_sec=args.sim_duration)
    print(f"  → done in {time.time() - sim_started:.1f} s")

    # Phase 3: assess
    print("\n[Phase 3] Health assessment ...")
    assessment = assess_health(sim)
    for c in assessment["checks"]:
        flag = "[PASS]" if c["pass"] else "[FAIL]"
        print(f"  {flag} {c['name']}: {c['value']} ({c['ok_range']})")

    # Phase 4: report
    meta = build_metadata(pytest_result, sim, assessment)
    written: List[str] = []
    if not args.no_save:
        out_dir = _output_dir(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        md_path = out_dir / "report.md"
        json_path = out_dir / "report.json"
        write_markdown(meta, pytest_result, sim, assessment, md_path)
        write_json(meta, pytest_result, sim, assessment, json_path)

        def _display(p: Path) -> str:
            try:
                return str(p.relative_to(REPO_ROOT))
            except ValueError:
                return str(p)

        written.append(_display(md_path))
        written.append(_display(json_path))
        if not args.no_plots:
            for p in maybe_write_plots(sim, out_dir):
                written.append(_display(out_dir / p))

        print(f"\n[Phase 4] Report written:")
        for w in written:
            print(f"  - {w}")
    else:
        print("\n[Phase 4] Report skipped (--no-save).")

    print("\n" + "=" * 70)
    print(
        f"Final: {'[ALL PASS]' if meta['exit_code'] == 0 else '[FAIL]'} "
        f"(exit_code={meta['exit_code']})"
    )
    print("=" * 70)
    return int(meta["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
