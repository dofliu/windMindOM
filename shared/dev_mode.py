"""WMOM_DEV_MODE 工具 — 跨 module 共用的 dev/demo bypass switch（WMOM-20260510-01 Part A）。

## 為什麼存在

windMindOM 的 workflow 設計帶若干「職責分離」(separation-of-duties) check，例如：

- ``_guard_dispatch``：dispatcher 的 ``actor_id`` 不可同時是 ``assignee_id``（派工人不可派給自己）
- ``signoff_repository._validate_step_decidable``：同 chain 內前面 step 的 ``decided_by`` 不可
  與當前 step 的 ``actor_id`` 相同（同一人不可連簽多階）

生產環境必要；但 client demo / 內部測試 / 教學情境下，**一個操作者** 想要 1 個人從建單跑到簽核
全 lifecycle 走完。此時把上述 check bypass 掉。透過環境變數 ``WMOM_DEV_MODE=true`` 啟用，
production 部署時 unset（預設關），絕無 silent default-on 風險。

## API

```python
from shared.dev_mode import is_dev_mode_enabled, log_dev_mode_warning_if_enabled

if not is_dev_mode_enabled():
    # 正式環境：執行 separation-of-duties check
    if actor_id == assignee_id:
        raise InvalidTransition("dispatcher cannot be the same person as assignee")
```

## 接受的「啟用」值（大小寫不敏感）

``"true"`` / ``"1"`` / ``"yes"`` / ``"on"`` 都算啟用。其餘（含未設、空字串、``"false"``）關閉。
"""

from __future__ import annotations

import logging
import os


_DEV_MODE_ENV_VAR = "WMOM_DEV_MODE"
_TRUTHY = frozenset({"true", "1", "yes", "on"})


def is_dev_mode_enabled() -> bool:
    """讀 ``WMOM_DEV_MODE`` env var；對 ``true`` / ``1`` / ``yes`` / ``on`` 回 True，其餘 False。

    每次呼叫都重新讀 env（test 友善 — 用 ``monkeypatch.setenv`` 可即時生效）。
    """
    raw = os.environ.get(_DEV_MODE_ENV_VAR, "")
    return raw.strip().lower() in _TRUTHY


def log_dev_mode_warning_if_enabled(logger: logging.Logger | None = None) -> bool:
    """若 dev mode 項目啟用 → log [WARNING] 並 return True；否則 return False。

    建議在 backend startup（``app.py`` lifespan）呼叫一次，讓任何啟動者都立刻看到
    auth check 被 bypass 的事實，避免誤把 dev_mode build 拿去做客戶 demo。

    Args:
        logger: optional logger；None 時用本模組預設 logger。
    """
    if not is_dev_mode_enabled():
        return False
    log = logger or logging.getLogger(__name__)
    log.warning(
        "[WARNING] WMOM_DEV_MODE active - separation-of-duties checks bypassed "
        "(dispatcher==assignee allowed, same actor may sign consecutive signoff levels). "
        "DO NOT use this build for production."
    )
    return True
