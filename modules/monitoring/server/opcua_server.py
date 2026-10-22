"""模仿 Bachmann Z72 tag 的 OPC UA server（WMOM-20261021-07，EPIC-DS Phase 3c ③）。

節點路徑對齊真實的讀取腳本（``shared/plc_clients/bachmann/opc_data_reader.py`` 的 OPC DA item ID）：

- ``Z72.H{nn}.{group}.Z72PLC__UI_Loc_*``：讀值。欄位與資料包 / WS 回放同一組（含標為 synthetic 的自創
  tag，節點說明會寫明），型別依 PLC：REAL32 → Float、SINT16 → Int16、UINT16 → UInt16、BOOL → Boolean。
  另加真實讀取腳本會讀的 ``WMET.Z72PLC__UI_Loc_WMET_Analogue_WSpeedNacAvg10m``：模擬器沒有這個 tag，由本
  server 以 ``WSpeedNac`` 的 10 分鐘移動平均算出（衍生量，節點說明寫明）。
- ``Z72.H{nn}.Z72PLC__ActiveAlarm[0..20]`` / ``ActiveTrip1[...]`` / ``ActiveTrip2[...]``：目前成立的事件碼
  （SINT16，依成立順序，空位為 0；規則見 ``plc_protection.ActiveEventLists``）。
- ``WindMindOM.*``：模擬器狀態（不是真實 PLC 的 tag）——``Source``、``Status``、``SimTime``、``PackId``、
  ``Mode``、``Speed``。

NodeId 是字串（namespace ``urn:windmindom:z72sim``、識別字＝DA 的 item ID），可以直接用 item ID 讀，也可以從
``Objects/Z72/H01/WMET/...`` 瀏覽。匿名、唯讀（變數不可寫）、不加密（教室 / 實驗室網路用）。

資料來源（DEC-20261022-03）：

- ``ReplayFeeder``：一個回放（``ScenarioReplay`` + ``ReplayClock``，由 ``tools/opcua_server.py`` 啟動）。
  正式評測在 server 啟動時開播（寫入 ``replay_runs.started_at``），之後的 WS 連線加入同一個時鐘：
  受測端用 OPC UA 讀資料、用 WS（``?stream=false``）送判斷。
- ``LiveFeeder``：即時模擬（broker 的 simulator，每秒讀一次最新讀值與 PLC 狀態）；主程式以
  ``WMOM_OPCUA_ENABLE=true`` 開啟。

OPC UA 是「目前值」介面（同真實 PLC）：每次更新只寫各機組最新的一筆讀值（``SourceTimestamp``＝該筆的
模擬時間）。要每一筆讀值與 10 分鐘統計，用 WS 回放或資料包。
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, Deque, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from asyncua import Server, ua

try:
    from ..simulator.physics.plc_protection import ACTIVE_LIST_SLOTS, ActiveEventLists
    from ..simulator.time_utils import parse_iso
    from . import replay as rp
    from . import scenario_pack as sp
except ImportError:  # sys.path 注入模式（modules/monitoring 在 sys.path）
    from simulator.physics.plc_protection import ACTIVE_LIST_SLOTS, ActiveEventLists  # type: ignore[no-redef]
    from simulator.time_utils import parse_iso  # type: ignore[no-redef]
    from server import replay as rp  # type: ignore[no-redef]
    from server import scenario_pack as sp  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

NAMESPACE_URI = "urn:windmindom:z72sim"
DEFAULT_PORT = 4840
ENDPOINT_PATH = "/windmindom/"
# 回放更新節點的間隔（實際秒）：OPC UA 是目前值介面，客戶端通常每秒讀一次
REPLAY_TICK_S = 0.2
LIVE_POLL_S = 1.0
# 每隔幾秒（實際時間）重讀回放狀態：撤銷 / 到期就停止更新
RUN_RECHECK_S = 5.0
LIST_TAGS: Dict[str, str] = {"A": "Z72PLC__ActiveAlarm", "T1": "Z72PLC__ActiveTrip1", "T2": "Z72PLC__ActiveTrip2"}
# 真實讀取腳本會讀、但模擬器沒有輸出的 tag：由 OPC UA server 從 WSpeedNac 算 10 分鐘移動平均（衍生量）
WSPEED_TAG = "Z72PLC__UI_Loc_WMET_Analogue_WSpeedNac"
WSPEED_AVG10M_TAG = "Z72PLC__UI_Loc_WMET_Analogue_WSpeedNacAvg10m"
WSPEED_AVG10M_DESCRIPTION = ("10-minute moving average of WSpeedNac [m/s] (derived by the windMindOM OPC UA server; "
                             "the simulator does not output this tag)")
AVG_WINDOW_S = 600.0

_VARIANTS: Dict[str, ua.VariantType] = {
    "REAL32": ua.VariantType.Float,
    "SINT16": ua.VariantType.Int16,
    "UINT16": ua.VariantType.UInt16,
    "BOOL": ua.VariantType.Boolean,
}
_INITIAL: Dict[ua.VariantType, object] = {
    ua.VariantType.Float: 0.0, ua.VariantType.Int16: 0, ua.VariantType.UInt16: 0, ua.VariantType.Boolean: False,
}


def plc_station(turbine_id: str) -> str:
    """機組 ID → 真實讀取腳本的站號（``WT001`` → ``H01``）。

    Args:
        turbine_id: 模擬器的機組 ID。

    Returns:
        ``H`` 加兩位數（超過 99 台時位數隨之增加）。

    Raises:
        ValueError: 機組 ID 沒有數字。
    """
    digits = "".join(ch for ch in turbine_id if ch.isdigit())
    if not digits:
        raise ValueError(f"turbine id {turbine_id!r} has no number")
    return f"H{int(digits):02d}"


def value_item_id(turbine_id: str, column: sp.PackColumn) -> str:
    """讀值節點的 item ID（例 ``Z72.H01.WMET.Z72PLC__UI_Loc_WMET_Analogue_WSpeedNac``）。"""
    return f"Z72.{plc_station(turbine_id)}.{column.tag.opc_tag}"


def list_item_id(turbine_id: str, level: str, index: int) -> str:
    """事件碼陣列元素的 item ID（例 ``Z72.H01.Z72PLC__ActiveAlarm[0]``）。"""
    return f"Z72.{plc_station(turbine_id)}.{LIST_TAGS[level]}[{index}]"


class RollingMean:
    """一台機組的移動平均（``(epoch 秒, 值)``，保留最近 ``AVG_WINDOW_S`` 秒；左開右閉）。"""

    def __init__(self, window_s: float = AVG_WINDOW_S) -> None:
        self._window_s = window_s
        self._samples: Deque[tuple] = deque()
        self._sum = 0.0

    def add(self, epoch_s: float, value: Optional[float]) -> Optional[float]:
        """加入一筆（缺值不加入）並回傳目前的平均（float32 精度；還沒有任何值時 None）。"""
        if value is not None:
            self._samples.append((epoch_s, float(value)))
            self._sum += float(value)
        while self._samples and self._samples[0][0] <= epoch_s - self._window_s:
            self._sum -= self._samples.popleft()[1]
        if not self._samples:
            return None
        # 同資料包 REAL32：float32 的最短十進位表示
        return float(str(np.float32(self._sum / len(self._samples))))


def _variant(column: sp.PackColumn) -> ua.VariantType:
    return _VARIANTS[column.tag.data_type]


def _description(column: sp.PackColumn) -> str:
    unit = f" [{column.tag.unit}]" if column.tag.unit else ""
    source = "" if sp.is_real_plc_tag(column.name) else " (synthetic: not a tag on a real Z72 PLC)"
    return f"{column.tag.label_en}{unit}{source}"


def _data_value(value: Optional[ua.Variant] = None, status: Optional[int] = None,
                source_ts: Optional[datetime] = None, server_ts: Optional[datetime] = None) -> ua.DataValue:
    """DataValue（asyncua 的型別標註要求自家的 UInt32 / DateTime NewType，實際接受 int / datetime）。"""
    return ua.DataValue(
        value, StatusCode=ua.StatusCode(status) if status is not None else ua.StatusCode(),  # type: ignore[arg-type]
        SourceTimestamp=source_ts, ServerTimestamp=server_ts,  # type: ignore[arg-type]  # asyncua NewType
    )


@dataclass
class _TurbineNodes:
    values: Dict[str, ua.NodeId]
    lists: Dict[str, List[ua.NodeId]]
    last_lists: Dict[str, List[int]]


class Z72OpcUaServer:
    """OPC UA server 與 Z72 的節點（資料由 ``ReplayFeeder`` / ``LiveFeeder`` 寫入）。

    Attributes:
        host: 監聽位址。
        port: 監聽埠。
        columns: 讀值欄位（同資料包）。
    """

    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_PORT,
                 columns: Optional[Sequence[sp.PackColumn]] = None) -> None:
        """建立（還沒開始監聽，見 ``start``）。

        Args:
            host: 監聽位址。
            port: 監聽埠。
            columns: 讀值欄位；None＝``scenario_pack.pack_columns()``。
        """
        self.host = host
        self.port = port
        self.columns = list(columns) if columns is not None else sp.pack_columns()
        self._server = Server()
        self._idx = 0
        self._z72: Optional[object] = None
        self._status: Dict[str, ua.NodeId] = {}
        self._turbines: Dict[str, _TurbineNodes] = {}
        self._lock = asyncio.Lock()

    def _node_id(self, identifier: str, namespace: Optional[int] = None) -> ua.NodeId:
        """字串 NodeId（asyncua 的型別標註要求自家的 String / Int16 NewType，實際接受 str / int）。"""
        return ua.NodeId(identifier, self._idx if namespace is None else namespace)  # type: ignore[arg-type]  # asyncua NewType

    @property
    def endpoint(self) -> str:
        """連線位址（``opc.tcp://host:port/windmindom/``）。"""
        return f"opc.tcp://{self.host}:{self.port}{ENDPOINT_PATH}"

    @property
    def namespace_index(self) -> int:
        """``urn:windmindom:z72sim`` 的 namespace index（``start`` 之後才有效）。"""
        return self._idx

    async def start(self, turbines: Sequence[str] = ()) -> None:
        """建立 namespace 與固定節點（與 ``turbines`` 的節點），開始監聽。

        Args:
            turbines: 先建好節點的機組（回放：連上就看得到全部機組；之後也可以 ``ensure_turbine``）。
        """
        await self._server.init()
        self._server.set_endpoint(self.endpoint)
        self._server.set_server_name("windMindOM Z72 simulator")
        self._server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        self._idx = await self._server.register_namespace(NAMESPACE_URI)
        objects = self._server.nodes.objects
        self._z72 = await objects.add_folder(self._node_id("Z72", self._idx), ua.QualifiedName("Z72", self._idx))
        status = await objects.add_folder(self._node_id("WindMindOM", self._idx),
                                          ua.QualifiedName("WindMindOM", self._idx))
        for name, value, variant in (
                ("Source", "idle", ua.VariantType.String), ("Status", "idle", ua.VariantType.String),
                ("SimTime", datetime(2000, 1, 1, tzinfo=timezone.utc), ua.VariantType.DateTime),
                ("PackId", "", ua.VariantType.String), ("Mode", "", ua.VariantType.String),
                ("Speed", 0.0, ua.VariantType.Double)):
            node = await status.add_variable(self._node_id(f"WindMindOM.{name}", self._idx),
                                             ua.QualifiedName(name, self._idx), value, varianttype=variant)
            self._status[name] = node.nodeid
        for turbine_id in turbines:
            await self.ensure_turbine(turbine_id)
        await self._server.start()

    async def stop(self) -> None:
        """停止監聽。"""
        await self._server.stop()

    async def ensure_turbine(self, turbine_id: str) -> None:
        """建立一台機組的節點（已存在就略過；即時模擬切換風場後機組數可能改變）。

        Args:
            turbine_id: 機組 ID。
        """
        async with self._lock:
            if turbine_id in self._turbines or self._z72 is None:
                return
            station = plc_station(turbine_id)
            folder = await self._z72.add_folder(  # type: ignore[attr-defined]  # asyncua Node
                self._node_id(f"Z72.{station}", self._idx), ua.QualifiedName(station, self._idx))
            groups: Dict[str, object] = {}
            values: Dict[str, ua.NodeId] = {}
            for column in self.columns:
                group_name = column.tag.opc_tag.split(".", 1)[0]
                group = groups.get(group_name)
                if group is None:
                    group = groups[group_name] = await folder.add_folder(
                        self._node_id(f"Z72.{station}.{group_name}", self._idx), ua.QualifiedName(group_name, self._idx))
                variant = _variant(column)
                node = await group.add_variable(  # type: ignore[attr-defined]  # asyncua Node
                    self._node_id(value_item_id(turbine_id, column), self._idx), ua.QualifiedName(column.name, self._idx),
                    _INITIAL[variant], varianttype=variant)
                await self._server.write_attribute_value(
                    node.nodeid, ua.DataValue(ua.Variant(ua.LocalizedText(_description(column)))),
                    ua.AttributeIds.Description)
                await self._server.write_attribute_value(node.nodeid, _data_value(
                    ua.Variant(_INITIAL[variant], variant), status=ua.StatusCodes.BadWaitingForInitialData))
                values[column.name] = node.nodeid
            wmet = groups.get("WMET")
            if wmet is None:
                wmet = await folder.add_folder(
                    self._node_id(f"Z72.{station}.WMET", self._idx), ua.QualifiedName("WMET", self._idx))
            node = await wmet.add_variable(  # type: ignore[attr-defined]  # asyncua Node
                self._node_id(f"Z72.{station}.WMET.{WSPEED_AVG10M_TAG}", self._idx),
                ua.QualifiedName(WSPEED_AVG10M_TAG, self._idx), 0.0, varianttype=ua.VariantType.Float)
            await self._server.write_attribute_value(
                node.nodeid, ua.DataValue(ua.Variant(ua.LocalizedText(WSPEED_AVG10M_DESCRIPTION))),
                ua.AttributeIds.Description)
            await self._server.write_attribute_value(node.nodeid, _data_value(
                ua.Variant(0.0, ua.VariantType.Float), status=ua.StatusCodes.BadWaitingForInitialData))
            values[WSPEED_AVG10M_TAG] = node.nodeid
            lists: Dict[str, List[ua.NodeId]] = {}
            for level, tag in LIST_TAGS.items():
                lists[level] = []
                for index in range(ACTIVE_LIST_SLOTS):
                    node = await folder.add_variable(
                        self._node_id(list_item_id(turbine_id, level, index), self._idx),
                        ua.QualifiedName(f"{tag}[{index}]", self._idx), 0, varianttype=ua.VariantType.Int16)
                    lists[level].append(node.nodeid)
            self._turbines[turbine_id] = _TurbineNodes(values=values, lists=lists,
                                                       last_lists={level: [] for level in LIST_TAGS})

    async def write_values(self, turbine_id: str, values: Mapping[str, object], source_ts: datetime) -> None:
        """寫一台機組的讀值。

        Args:
            turbine_id: 機組 ID（先 ``ensure_turbine``）。
            values: ``{tag 名: 值}``（同資料包 / WS 回放的 ``values``，另加衍生的 ``WSPEED_AVG10M_TAG``；
                缺值 None → BadNoData）。
            source_ts: 這筆讀值的模擬時間。
        """
        nodes = self._turbines[turbine_id]
        server_ts = datetime.now(timezone.utc)
        typed = [(column.name, _variant(column)) for column in self.columns]
        typed.append((WSPEED_AVG10M_TAG, ua.VariantType.Float))
        for name, variant in typed:
            value = values.get(name)
            if value is None:
                data = _data_value(status=ua.StatusCodes.BadNoData, source_ts=source_ts, server_ts=server_ts)
            else:
                data = _data_value(ua.Variant(value, variant), source_ts=source_ts, server_ts=server_ts)
            await self._server.write_attribute_value(nodes.values[name], data)

    async def write_lists(self, turbine_id: str, lists: Mapping[str, Sequence[int]], source_ts: datetime) -> None:
        """寫一台機組的事件碼陣列（只寫有變動的元素）。

        Args:
            turbine_id: 機組 ID（先 ``ensure_turbine``）。
            lists: ``{"A": [...], "T1": [...], "T2": [...]}``。
            source_ts: 模擬時間。
        """
        nodes = self._turbines[turbine_id]
        server_ts = datetime.now(timezone.utc)
        for level in LIST_TAGS:
            codes = list(lists.get(level, []))[:ACTIVE_LIST_SLOTS]
            padded = codes + [0] * (ACTIVE_LIST_SLOTS - len(codes))
            previous = nodes.last_lists[level] + [0] * (ACTIVE_LIST_SLOTS - len(nodes.last_lists[level]))
            for index, (code, old) in enumerate(zip(padded, previous, strict=True)):
                if code != old:
                    await self._server.write_attribute_value(nodes.lists[level][index], _data_value(
                        ua.Variant(code, ua.VariantType.Int16), source_ts=source_ts, server_ts=server_ts))
            nodes.last_lists[level] = codes

    async def set_status(self, **fields: object) -> None:
        """更新 ``WindMindOM.*`` 狀態節點（``Source`` / ``Status`` / ``SimTime`` / ``PackId`` / ``Mode`` / ``Speed``）。"""
        variants = {"SimTime": ua.VariantType.DateTime, "Speed": ua.VariantType.Double}
        for name, value in fields.items():
            await self._server.write_attribute_value(
                self._status[name], ua.DataValue(ua.Variant(value, variants.get(name, ua.VariantType.String))))


class ReplayFeeder:
    """把一個回放依時鐘寫進 OPC UA 節點（各機組最新一筆讀值 + 事件碼陣列）。"""

    def __init__(self, server: Z72OpcUaServer, replay: rp.ScenarioReplay, clock: rp.ReplayClock, mode: str,
                 speed: float, check_run: Optional[Callable[[], Awaitable[Optional[str]]]] = None) -> None:
        """建立。

        Args:
            server: 已 ``start`` 的 server。
            replay: 回放資料來源。
            clock: 回放時鐘（正式評測與 WS 共用 ``replay_runs.started_at``）。
            mode: ``evaluation`` / ``practice``（寫進狀態節點）。
            speed: 回放速度（寫進狀態節點）。
            check_run: 定期呼叫；回傳非 None（停止原因，例：``revoked``）時停止更新。
        """
        self._server = server
        self._replay = replay
        self._clock = clock
        self._mode = mode
        self._speed = speed
        self._check_run = check_run
        self._buffer: Deque[rp.ReplayFrame] = deque()
        self._lists = {tid: ActiveEventLists() for tid in replay.turbines}
        self._wind_avg = {tid: RollingMean() for tid in replay.turbines}
        self.done = False
        self.stop_reason: Optional[str] = None

    async def setup(self) -> None:
        """建立全部機組的節點、寫入回放說明。"""
        for turbine_id in self._replay.turbines:
            await self._server.ensure_turbine(turbine_id)
        await self._server.set_status(Source="replay", Status="running", PackId=self._replay.pack_id,
                                      Mode=self._mode, Speed=float(self._speed), SimTime=self._clock.sim_now())

    async def advance_to(self, sim_ts: datetime) -> None:
        """套用所有 ``due ≤ sim_ts`` 的訊息：每台機組只寫最新一筆讀值，事件依序更新事件碼陣列。

        Args:
            sim_ts: 目前的模擬時間。
        """
        latest: Dict[str, Tuple[Dict[str, object], datetime]] = {}
        changed: Dict[str, datetime] = {}
        while True:
            if not self._buffer:
                if self._replay.done:
                    break
                self._buffer.extend(await asyncio.to_thread(self._replay.next_frames))
                continue
            frame = self._buffer[0]
            if frame.due > sim_ts:
                break
            self._buffer.popleft()
            message = frame.message
            turbine_id = str(message.get("turbine_id"))
            raw = message.get("values")
            if message["type"] == "reading" and isinstance(raw, dict):
                values = dict(raw)
                wind = values.get(WSPEED_TAG)
                values[WSPEED_AVG10M_TAG] = self._wind_avg.setdefault(turbine_id, RollingMean()).add(
                    frame.due.timestamp(), float(wind) if isinstance(wind, (int, float)) else None)
                latest[turbine_id] = (values, parse_iso(str(message["ts"])))
            elif message["type"] == "event" and turbine_id in self._lists:
                code = message.get("alarm_code")
                level = message.get("alarm_level")
                if self._lists[turbine_id].apply(str(message["event_type"]), code if isinstance(code, int) else 0,
                                                 level if isinstance(level, str) else None):
                    changed[turbine_id] = frame.due
        for turbine_id, (values, ts) in latest.items():
            await self._server.write_values(turbine_id, values, ts)
        for turbine_id, due in changed.items():
            await self._server.write_lists(turbine_id, self._lists[turbine_id].snapshot(), due)
        if not self._buffer and self._replay.done:
            self.done = True
        await self._server.set_status(SimTime=min(sim_ts, self._replay.sim_end) if self.done else sim_ts,
                                      Status="finished" if self.done else "running")

    async def run(self, tick_s: float = REPLAY_TICK_S) -> None:
        """依時鐘更新直到資料播完（或回放被撤銷 / 到期）。

        Args:
            tick_s: 更新間隔（實際秒）。
        """
        checked_at = rp.wall_time()
        while not self.done:
            if self._check_run is not None and rp.wall_time() - checked_at >= RUN_RECHECK_S:
                checked_at = rp.wall_time()
                reason = await self._check_run()
                if reason is not None:
                    self.stop_reason = reason
                    await self._server.set_status(Status=reason)
                    return
            await self.advance_to(self._clock.sim_now())
            if not self.done:
                await asyncio.sleep(tick_s)


class LiveFeeder:
    """把即時模擬（broker 的 simulator）的最新讀值與 PLC 狀態寫進 OPC UA 節點。"""

    def __init__(self, server: Z72OpcUaServer, broker: object) -> None:
        """建立。

        Args:
            server: 已 ``start`` 的 server。
            broker: ``DataBroker``（讀 ``source_kind`` 與 ``simulator``）。
        """
        self._server = server
        self._broker = broker
        self._tag_ids = [col.tag.id for col in server.columns]
        self._last_ts: Dict[str, str] = {}
        self._wind_avg: Dict[str, RollingMean] = {}

    async def update(self) -> None:
        """讀一次即時模擬：每台機組的最新讀值（有新的才寫）與 PLC 的事件碼清單。"""
        simulator = getattr(self._broker, "simulator", None)
        if simulator is None or getattr(self._broker, "source_kind", None) != "simulation":
            await self._server.set_status(Source="live", Status="idle")
            return
        newest: Optional[datetime] = None
        for turbine_id, model in list(simulator.turbines.items()):
            reading = simulator.latest_data.get(turbine_id)
            if not reading or not isinstance(reading.get("scada"), dict):
                continue
            await self._server.ensure_turbine(turbine_id)
            stamp = str(reading["timestamp"])
            ts = parse_iso(stamp)
            if self._last_ts.get(turbine_id) != stamp:
                self._last_ts[turbine_id] = stamp
                values = sp.json_values(sp.scada_dict_values(reading["scada"], self._tag_ids), self._server.columns)
                wind = values.get(WSPEED_TAG)
                values[WSPEED_AVG10M_TAG] = self._wind_avg.setdefault(turbine_id, RollingMean()).add(
                    ts.timestamp(), float(wind) if isinstance(wind, (int, float)) else None)
                await self._server.write_values(turbine_id, values, ts)
            await self._server.write_lists(turbine_id, model.plc.active_lists.snapshot(), ts)
            newest = ts if newest is None or ts > newest else newest
        fields: Dict[str, object] = {"Source": "live", "Status": "running" if newest else "idle", "PackId": "",
                                     "Mode": "live"}
        if newest is not None:
            fields["SimTime"] = newest
        await self._server.set_status(**fields)

    async def run(self, poll_s: float = LIVE_POLL_S) -> None:
        """每 ``poll_s`` 秒更新一次，直到被取消。

        Args:
            poll_s: 更新間隔（實際秒）。
        """
        while True:
            try:
                await self.update()
            except Exception:  # noqa: BLE001  即時模擬換來源 / 換風場的瞬間讀到不一致的狀態，下一輪再試
                logger.exception("OPC UA live update failed")
            await asyncio.sleep(poll_s)


@dataclass
class LiveOpcUa:
    """主程式裡的即時模擬 OPC UA server（``start_live_from_env`` 回傳；``stop`` 收尾）。"""

    server: Z72OpcUaServer
    task: "asyncio.Task[None]"

    async def stop(self) -> None:
        """停止更新與監聽。"""
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass
        await self.server.stop()


def _truthy(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


async def start_live_from_env(broker: object) -> Optional[LiveOpcUa]:
    """``WMOM_OPCUA_ENABLE=true`` 時起即時模擬的 OPC UA server（``WMOM_OPCUA_HOST`` / ``WMOM_OPCUA_PORT``）。

    選配功能：起不來（埠被占用等）只記警告，不擋主程式。

    Args:
        broker: ``DataBroker``。

    Returns:
        執行中的 server，或 None（沒開啟 / 起不來）。
    """
    if not _truthy(os.environ.get("WMOM_OPCUA_ENABLE")):
        return None
    server = Z72OpcUaServer(host=os.environ.get("WMOM_OPCUA_HOST", "0.0.0.0"),
                            port=int(os.environ.get("WMOM_OPCUA_PORT", str(DEFAULT_PORT))))
    try:
        await server.start()
    except Exception as exc:  # noqa: BLE001
        logger.warning("OPC UA server not started: %s", exc)
        return None
    logger.info("OPC UA server (live simulation) at %s", server.endpoint)
    return LiveOpcUa(server=server, task=asyncio.create_task(LiveFeeder(server, broker).run()))
