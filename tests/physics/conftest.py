"""Physics 自我驗證框架 — pytest 共用設定（WMOM-20260505-23）。

此 conftest 同時服務 Layer 1-6 所有 validator：

* `sys.path` 注入：把 `modules/monitoring` 放到 import path，讓
  `simulator.physics.*` 可以直接 import。
* Layer 7（測試紀錄保存）的 hook 預留位 — 完整實作會在後續 commit
  把 `pytest_sessionfinish` 接上自動報告產出（markdown + JSON）。
"""

from __future__ import annotations

import sys
from pathlib import Path

# ──────────────────────────────────────────────────────────────
# repo 結構：repo_root/tests/physics/conftest.py
# 三個 parents 上去就是 repo root；monitoring 物理模組在
# repo_root/modules/monitoring/ 之下。
# ──────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
MONITORING_ROOT = REPO_ROOT / "modules" / "monitoring"

if str(MONITORING_ROOT) not in sys.path:
    sys.path.insert(0, str(MONITORING_ROOT))


# ──────────────────────────────────────────────────────────────
# Layer 7 hook 預留位（WMOM-20260505-23 Layer 7 完整實作前的骨架）
#
# 規劃：每次 pytest run 結束會在 reports/{YYYY}/{MM}/ 下寫入：
#   {timestamp}-pytest.md   ← 人讀
#   {timestamp}-pytest.json ← 機讀（baseline diff 用）
#
# 詳細格式見 ISSUES.md WMOM-20260505-23 Layer 7 段；
# 這裡先留空 hook，避免 import 失敗時整個 test 卡住。
# ──────────────────────────────────────────────────────────────

REPORTS_DIR = Path(__file__).resolve().parent / "reports"


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    """Layer 7 placeholder — 之後在這裡寫入 markdown / JSON 報告。

    目前只確保 reports/ 資料夾存在；不做任何寫入動作。
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
