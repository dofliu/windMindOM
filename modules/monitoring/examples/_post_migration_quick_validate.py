"""Post-migration quick validation driver（WMOM-20260503-01 follow-up）。

呼叫既有的 ``generate_data`` + ``analyze_data``（ ``data_quality_analysis.py``
原 main 的兩個函式），但跑短版（duration_hours 可設）並把報告 / CSV 寫到
獨立檔案，不污染預先備份的 pre-migration baseline。

Usage::

    cd modules/monitoring/examples/
    python _post_migration_quick_validate.py            # 預設 0.17h ≈ 10 min wall
    python _post_migration_quick_validate.py 0.05       # 約 3 min wall

跑完 print 報告，並輸出：
- ``simulated_scada_post_migration.csv``
- ``data_quality_report_post_migration.txt``

之後人工跟 ``data_quality_report_pre_migration_baseline.txt`` diff 對照
key metric（power curve slope、temp range、vibration band、correlations）
是否在合理浮動範圍內，作為「搬遷後物理沒破」的證據。

完成驗證後本檔可保留作為下次 quick smoke 用的 driver；不必刪。
"""

import os
import sys
import time

# Windows cp950 console 對 utf-8 字元（≈/✓ 等）會 UnicodeEncodeError。
# 強制 stdout/stderr 走 utf-8，避免報告中的中文 + 數學符號 print 失敗。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from data_quality_analysis import generate_data, analyze_data  # noqa: E402


def main() -> int:
    duration_hours = float(sys.argv[1]) if len(sys.argv) > 1 else 0.17  # ~10 min wall
    print(f"[validate] duration_hours={duration_hours} (~{duration_hours*60:.1f} min wall, real-time sim)")

    t0 = time.perf_counter()
    df = generate_data(duration_hours=duration_hours, time_step=1.0, turbine_count=5)
    t_gen = time.perf_counter() - t0

    csv_path = os.path.join(_HERE, "simulated_scada_post_migration.csv")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n[validate] CSV saved → {csv_path}（{len(df)} rows，{t_gen:.1f}s wall）")

    print("\n[validate] Phase 2 分析中…\n")
    t1 = time.perf_counter()
    report = analyze_data(df)
    t_ana = time.perf_counter() - t1
    print(report)

    report_path = os.path.join(_HERE, "data_quality_report_post_migration.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n[validate] 報告寫入 → {report_path}（分析 {t_ana:.1f}s）")
    print(f"[validate] TOTAL wall-clock {time.perf_counter() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
