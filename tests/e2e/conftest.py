"""E2E test 共用 path setup — repo root 加進 sys.path 讓 `modules.*` 可 import。

放在 ``tests/e2e/`` 下，讓 pytest auto-discovery 抓得到（rootdir 在 repo root）。
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
