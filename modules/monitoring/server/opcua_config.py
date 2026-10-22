"""即時模擬 OPC UA server 的環境變數設定（WMOM-20261021-07）。

獨立成小模組：主程式啟動時只需要判斷要不要開，沒開就不必載入 ``asyncua``。
"""

from __future__ import annotations

import os
from typing import Mapping, Optional, Tuple

ENABLE_ENV = "WMOM_OPCUA_ENABLE"
HOST_ENV = "WMOM_OPCUA_HOST"
PORT_ENV = "WMOM_OPCUA_PORT"
DEFAULT_PORT = 4840
# 即時模擬的 OPC UA 匿名、不加密：預設只聽本機，要給其他電腦連須明確設 WMOM_OPCUA_HOST（例 0.0.0.0）
DEFAULT_LIVE_HOST = "127.0.0.1"


def _truthy(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def opcua_enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    """``WMOM_OPCUA_ENABLE`` 是否開啟（``true`` / ``1`` / ``yes`` / ``on``）。

    Args:
        env: 環境變數；None＝``os.environ``。

    Returns:
        是否開啟即時模擬的 OPC UA server。
    """
    return _truthy((os.environ if env is None else env).get(ENABLE_ENV))


def live_bind(env: Optional[Mapping[str, str]] = None) -> Tuple[str, int]:
    """即時模擬 OPC UA server 的監聽位址與埠。

    Args:
        env: 環境變數；None＝``os.environ``。

    Returns:
        ``(host, port)``；預設 ``127.0.0.1:4840``。

    Raises:
        ValueError: ``WMOM_OPCUA_PORT`` 不是整數。
    """
    source = os.environ if env is None else env
    return source.get(HOST_ENV, DEFAULT_LIVE_HOST), int(source.get(PORT_ENV, str(DEFAULT_PORT)))
