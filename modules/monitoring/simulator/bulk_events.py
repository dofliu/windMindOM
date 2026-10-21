"""批次生成路徑的可觀測事件（WMOM-20261021-04，EPIC-DS Phase 2）。

``WindFarmSimulator.generate_bulk`` 在每個物理子步收集兩類事件，以模擬時間戳交給呼叫端：

- **PLC 事件**：機組保護層（``plc_protection.py``）送出的 Z72 事件（警報 / 跳機 / 復位 / 資訊）。
- **狀態轉換**：``WTUR_TurSt`` 改變（含停機原因，例 ``plc:240``、``cut_out``）。

兩者都是**可觀測**事件：真實 SCADA 也看得到，不含任何故障根因（盲測，設計文件 §4）。
故障注入與根因只進標準答案（``simulator/ground_truth.py``）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .physics.plc_protection import PlcEvent

STATE_CHANGE = "state_change"


@dataclass(frozen=True)
class BulkEvent:
    """批次路徑的一筆可觀測事件。

    Attributes:
        timestamp: 事件發生的模擬時刻（tz-aware UTC）。
        turbine_id: 機組 ID。
        kind: PLC 事件種類（``alarm_raised`` / ``trip`` / ...，同 ``PlcEvent.kind``）或
            ``state_change``。
        plc_event: PLC 事件本體（``kind`` 為 PLC 種類時）。
        from_state: 轉換前的 ``WTUR_TurSt``（``state_change`` 時）。
        to_state: 轉換後的 ``WTUR_TurSt``（``state_change`` 時）。
        shutdown_cause: 轉換當下機組回報的停機原因（``state_change`` 時，可能為 None）。
    """

    timestamp: datetime
    turbine_id: str
    kind: str
    plc_event: Optional[PlcEvent] = None
    from_state: Optional[int] = None
    to_state: Optional[int] = None
    shutdown_cause: Optional[str] = None
