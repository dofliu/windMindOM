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
``Objects/Z72/H01/WMET/...`` 瀏覽。只接受匿名登入、唯讀（變數不可寫、不能加刪節點；asyncua 內建的 admin
帳號關閉）、不加密：只開在教室 / 實驗室網路。

資料來源（DEC-20261022-03）：

- ``ReplayFeeder``：一個回放（``ScenarioReplay`` + ``ReplayClock``，由 ``tools/opcua_server.py`` 啟動）。
  server 建好節點、開始監聽後開播：正式評測寫入 ``replay_runs.started_at``、練習寫入同一欄當成本次播出的
  起點；WS 以 ``?stream=false`` 連線時加入同一個時鐘——受測端用 OPC UA 讀資料、用 WS 送判斷。
- ``LiveFeeder``：即時模擬（broker 的 simulator，每秒讀一次最新讀值與 PLC 狀態）；主程式以
  ``WMOM_OPCUA_ENABLE=true`` 開啟（``server/opcua_config.py``）。產生情境（批次）期間不更新。

OPC UA 是「目前值」介面（同真實 PLC）：每次更新只寫各機組最新的一筆讀值（``SourceTimestamp``＝該筆的
模擬時間）。要每一筆讀值與 10 分鐘統計，用 WS 回放或資料包。
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import (Awaitable, Callable, Deque, Dict, List, Mapping, Optional, Protocol, Sequence, Set, Tuple)

import numpy as np
from asyncua import Node, Server, ua
from asyncua.crypto.permission_rules import User, UserRole

try:
    from ..simulator.physics.plc_protection import ACTIVE_LIST_SLOTS, ActiveEventLists
    from ..simulator.time_utils import parse_iso, utc_now
    from . import opcua_config as oc
    from . import replay as rp
    from . import scenario_pack as sp
except ImportError:  # sys.path 注入模式（modules/monitoring 在 sys.path）
    from simulator.physics.plc_protection import ACTIVE_LIST_SLOTS, ActiveEventLists  # type: ignore[no-redef]
    from simulator.time_utils import parse_iso, utc_now  # type: ignore[no-redef]
    from server import opcua_config as oc  # type: ignore[no-redef]
    from server import replay as rp  # type: ignore[no-redef]
    from server import scenario_pack as sp  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

NAMESPACE_URI = "urn:windmindom:z72sim"
DEFAULT_PORT = oc.DEFAULT_PORT
ENDPOINT_PATH = "/windmindom/"
# 回放更新節點的間隔（實際秒）：一個取樣週期對應的實際時間，夾在 0.05–0.2 s（OPC UA 是目前值介面）
REPLAY_TICK_MAX_S = 0.2
REPLAY_TICK_MIN_S = 0.05
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
    """讀值節點的 item ID。

    Args:
        turbine_id: 機組 ID。
        column: 資料包欄位。

    Returns:
        例 ``Z72.H01.WMET.Z72PLC__UI_Loc_WMET_Analogue_WSpeedNac``。
    """
    return f"Z72.{plc_station(turbine_id)}.{column.tag.opc_tag}"


def list_item_id(turbine_id: str, level: str, index: int) -> str:
    """事件碼陣列元素的 item ID。

    Args:
        turbine_id: 機組 ID。
        level: ``A`` / ``T1`` / ``T2``。
        index: 陣列索引（0–20）。

    Returns:
        例 ``Z72.H01.Z72PLC__ActiveAlarm[0]``。
    """
    return f"Z72.{plc_station(turbine_id)}.{LIST_TAGS[level]}[{index}]"


def replay_tick_s(sample_period_s: Optional[float], speed: float) -> float:
    """回放更新節點的間隔：一個取樣週期對應的實際秒數，夾在 ``REPLAY_TICK_MIN_S``–``REPLAY_TICK_MAX_S``。

    Args:
        sample_period_s: 取樣週期（模擬秒；None＝未知）。
        speed: 回放速度。

    Returns:
        實際秒。
    """
    if not sample_period_s or speed <= 0:
        return REPLAY_TICK_MAX_S
    return min(REPLAY_TICK_MAX_S, max(REPLAY_TICK_MIN_S, sample_period_s / speed))


class RollingMean:
    """一台機組的移動平均（``(epoch 秒, 值)``，保留最近 ``AVG_WINDOW_S`` 秒；左開右閉）。"""

    def __init__(self, window_s: float = AVG_WINDOW_S) -> None:
        self._window_s = window_s
        self._samples: Deque[Tuple[float, float]] = deque()
        self._sum = 0.0
        self._last_epoch: Optional[float] = None

    def add(self, epoch_s: float, value: Optional[float]) -> Optional[float]:
        """加入一筆（缺值不加入）並回傳目前的平均（float32 精度；還沒有任何值時 None）。

        時間倒退（例：產生情境後即時模擬回到現在）時先清空，重新累積。

        Args:
            epoch_s: 這筆的時間（epoch 秒）。
            value: 值；None＝缺值。

        Returns:
            平均或 None。
        """
        if self._last_epoch is not None and epoch_s < self._last_epoch:
            self._samples.clear()
            self._sum = 0.0
        self._last_epoch = epoch_s
        if value is not None:
            self._samples.append((epoch_s, float(value)))
            self._sum += float(value)
        while self._samples and self._samples[0][0] <= epoch_s - self._window_s:
            self._sum -= self._samples.popleft()[1]
        if not self._samples:
            self._sum = 0.0
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


class _ReadOnlyUserManager:
    """每個 session 都是一般使用者（唯讀）：不認帳號密碼，也沒有 asyncua 內建的 admin。"""

    def get_user(self, iserver: object, username: Optional[str] = None, password: Optional[str] = None,
                 certificate: object = None) -> User:
        """回傳唯讀使用者（asyncua 的 UserManager 介面）。"""
        return User(role=UserRole.User)


@dataclass
class _TurbineNodes:
    values: Dict[str, ua.NodeId]
    lists: Dict[str, List[ua.NodeId]]
    last_lists: Optional[Dict[str, List[int]]]  # None＝還沒寫過（第一次全部寫）


class Z72OpcUaServer:
    """OPC UA server 與 Z72 的節點（資料由 ``ReplayFeeder`` / ``LiveFeeder`` 寫入）。

    Attributes:
        host: 監聽位址。
        port: 監聽埠。
        columns: 讀值欄位（同資料包）。
    """

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT,
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
        self._server = Server(user_manager=_ReadOnlyUserManager())  # type: ignore[arg-type]  # 鴨子型別的 UserManager
        self._idx = 0
        self._z72: Optional[Node] = None
        self._status: Dict[str, ua.NodeId] = {}
        self._turbines: Dict[str, _TurbineNodes] = {}
        self._stations: Dict[str, str] = {}
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

    @property
    def turbine_ids(self) -> List[str]:
        """已建節點的機組。"""
        return list(self._turbines)

    async def start(self, turbines: Sequence[str] = ()) -> None:
        """建立 namespace 與固定節點（與 ``turbines`` 的節點），開始監聽。

        只接受匿名登入、不加密；``allow_remote_admin`` 關閉，任何 session 都是唯讀的一般使用者。

        Args:
            turbines: 先建好節點的機組（回放：連上就看得到全部機組；之後也可以 ``ensure_turbine``）。
        """
        await self._server.init()
        self._server.set_endpoint(self.endpoint)
        self._server.set_server_name("windMindOM Z72 simulator")
        self._server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        self._server.set_identity_tokens([ua.AnonymousIdentityToken])
        self._server.allow_remote_admin(False)
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

        Raises:
            ValueError: 與已建的機組對到同一個站號（例 ``WT01`` 與 ``WT001``）。
        """
        async with self._lock:
            if turbine_id in self._turbines or self._z72 is None:
                return
            station = plc_station(turbine_id)
            if station in self._stations:
                raise ValueError(f"turbine {turbine_id!r} maps to {station}, already used by "
                                 f"{self._stations[station]!r}")
            folder = await self._z72.add_folder(
                self._node_id(f"Z72.{station}", self._idx), ua.QualifiedName(station, self._idx))
            groups: Dict[str, Node] = {}
            values: Dict[str, ua.NodeId] = {}
            for column in self.columns:
                group_name = column.tag.opc_tag.split(".", 1)[0]
                if group_name not in groups:
                    groups[group_name] = await folder.add_folder(
                        self._node_id(f"Z72.{station}.{group_name}", self._idx), ua.QualifiedName(group_name, self._idx))
                variant = _variant(column)
                node = await groups[group_name].add_variable(
                    self._node_id(value_item_id(turbine_id, column), self._idx), ua.QualifiedName(column.name, self._idx),
                    _INITIAL[variant], varianttype=variant)
                await self._describe_waiting(node, _description(column), ua.Variant(_INITIAL[variant], variant))
                values[column.name] = node.nodeid
            if "WMET" not in groups:
                groups["WMET"] = await folder.add_folder(
                    self._node_id(f"Z72.{station}.WMET", self._idx), ua.QualifiedName("WMET", self._idx))
            node = await groups["WMET"].add_variable(
                self._node_id(f"Z72.{station}.WMET.{WSPEED_AVG10M_TAG}", self._idx),
                ua.QualifiedName(WSPEED_AVG10M_TAG, self._idx), 0.0, varianttype=ua.VariantType.Float)
            await self._describe_waiting(node, WSPEED_AVG10M_DESCRIPTION, ua.Variant(0.0, ua.VariantType.Float))
            values[WSPEED_AVG10M_TAG] = node.nodeid
            lists: Dict[str, List[ua.NodeId]] = {}
            for level, tag in LIST_TAGS.items():
                lists[level] = []
                for index in range(ACTIVE_LIST_SLOTS):
                    node = await folder.add_variable(
                        self._node_id(list_item_id(turbine_id, level, index), self._idx),
                        ua.QualifiedName(f"{tag}[{index}]", self._idx), 0, varianttype=ua.VariantType.Int16)
                    await self._server.write_attribute_value(node.nodeid, _data_value(
                        ua.Variant(0, ua.VariantType.Int16), status=ua.StatusCodes.BadWaitingForInitialData))
                    lists[level].append(node.nodeid)
            self._turbines[turbine_id] = _TurbineNodes(values=values, lists=lists, last_lists=None)
            self._stations[station] = turbine_id

    async def _describe_waiting(self, node: Node, description: str, initial: ua.Variant) -> None:
        await self._server.write_attribute_value(
            node.nodeid, ua.DataValue(ua.Variant(ua.LocalizedText(description))), ua.AttributeIds.Description)
        await self._server.write_attribute_value(
            node.nodeid, _data_value(initial, status=ua.StatusCodes.BadWaitingForInitialData))

    async def write_values(self, turbine_id: str, values: Mapping[str, object], source_ts: datetime) -> None:
        """寫一台機組的讀值。

        Args:
            turbine_id: 機組 ID（先 ``ensure_turbine``）。
            values: ``{tag 名: 值}``（同資料包 / WS 回放的 ``values``，另加衍生的 ``WSPEED_AVG10M_TAG``；
                缺值 None → BadNoData）。
            source_ts: 這筆讀值的模擬時間。
        """
        nodes = self._turbines[turbine_id]
        server_ts = utc_now()
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
        """寫一台機組的事件碼陣列（第一次全部寫，之後只寫有變動的元素）。

        Args:
            turbine_id: 機組 ID（先 ``ensure_turbine``）。
            lists: ``{"A": [...], "T1": [...], "T2": [...]}``。
            source_ts: 模擬時間。
        """
        nodes = self._turbines[turbine_id]
        server_ts = utc_now()
        last = nodes.last_lists
        for level in LIST_TAGS:
            codes = list(lists.get(level, []))[:ACTIVE_LIST_SLOTS]
            padded = codes + [0] * (ACTIVE_LIST_SLOTS - len(codes))
            previous: List[Optional[int]] = [None] * ACTIVE_LIST_SLOTS
            if last is not None:
                previous = [*last[level], *([0] * (ACTIVE_LIST_SLOTS - len(last[level])))]
            for index, (code, old) in enumerate(zip(padded, previous, strict=True)):
                if code != old:
                    await self._server.write_attribute_value(nodes.lists[level][index], _data_value(
                        ua.Variant(code, ua.VariantType.Int16), source_ts=source_ts, server_ts=server_ts))
        nodes.last_lists = {level: list(lists.get(level, []))[:ACTIVE_LIST_SLOTS] for level in LIST_TAGS}

    async def clear_turbine(self, turbine_id: str) -> None:
        """一台機組不再有資料（例：即時模擬換了風場）：讀值與事件碼陣列都改成 BadNoData。

        Args:
            turbine_id: 機組 ID。
        """
        nodes = self._turbines.get(turbine_id)
        if nodes is None:
            return
        server_ts = utc_now()
        no_data = _data_value(status=ua.StatusCodes.BadNoData, server_ts=server_ts)
        for node_id in list(nodes.values.values()) + [n for level in nodes.lists.values() for n in level]:
            await self._server.write_attribute_value(node_id, no_data)
        nodes.last_lists = None

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
            clock: 回放時鐘（與 WS ``?stream=false`` 共用 ``replay_runs.started_at``）。
            mode: ``evaluation`` / ``practice``（寫進狀態節點）。
            speed: 回放速度（寫進狀態節點）。
            check_run: 定期呼叫；回傳非 None（停止原因：``revoked`` / ``expired`` / ``missing``）時停止更新。
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
        self._lists_written = False  # 第一次推進時寫入全部機組的事件碼陣列（開播後沒事件也要讀得到 0）
        self.done = False
        self.stop_reason: Optional[str] = None

    @property
    def tick_s(self) -> float:
        """依取樣週期與速度決定的更新間隔（實際秒）。"""
        return replay_tick_s(self._replay.sample_period_s, self._speed)

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
        if not self._lists_written:
            for turbine_id in self._lists:
                changed.setdefault(turbine_id, min(sim_ts, self._replay.sim_end))
            self._lists_written = True
        for turbine_id, due in changed.items():
            await self._server.write_lists(turbine_id, self._lists[turbine_id].snapshot(), due)
        if not self._buffer and self._replay.done:
            self.done = True
        await self._server.set_status(SimTime=min(sim_ts, self._replay.sim_end) if self.done else sim_ts,
                                      Status="finished" if self.done else "running")

    async def run(self, tick_s: Optional[float] = None) -> None:
        """依時鐘更新直到資料播完（或回放被撤銷 / 到期 / 刪除）。

        單次更新或回放狀態檢查失敗（例：DB 暫時鎖住）只記錄、下一輪再試：正式評測的時鐘不會停。

        Args:
            tick_s: 更新間隔（實際秒）；None＝``self.tick_s``。
        """
        interval = self.tick_s if tick_s is None else tick_s
        checked_at = rp.wall_time()
        while not self.done:
            if self._check_run is not None and rp.wall_time() - checked_at >= RUN_RECHECK_S:
                try:
                    reason = await self._check_run()
                except Exception:  # noqa: BLE001  查不到就下一輪再查（不更新 checked_at）
                    logger.exception("OPC UA replay run check failed")
                else:
                    checked_at = rp.wall_time()
                    if reason is not None:
                        self.stop_reason = reason
                        await self._server.set_status(Status=reason)
                        return
            try:
                await self.advance_to(self._clock.sim_now())
            except Exception:  # noqa: BLE001  單次失敗不中斷播出
                logger.exception("OPC UA replay update failed")
            if not self.done:
                await asyncio.sleep(interval)


class _PlcView(Protocol):
    @property
    def active_lists(self) -> ActiveEventLists: ...


class _ModelView(Protocol):
    @property
    def plc(self) -> _PlcView: ...


class LiveSimulator(Protocol):
    """``LiveFeeder`` 讀的 simulator 介面（``WindFarmSimulator``）。"""

    @property
    def turbines(self) -> Mapping[str, _ModelView]: ...

    @property
    def is_bulk_running(self) -> bool: ...

    @property
    def bulk_runs(self) -> int: ...

    def get_current_data(self) -> Dict[str, Dict]: ...


class LiveSource(Protocol):
    """``LiveFeeder`` 讀的 broker 介面（``DataBroker``）。"""

    @property
    def simulator(self) -> Optional[LiveSimulator]: ...

    @property
    def source_kind(self) -> Optional[str]: ...


class LiveFeeder:
    """把即時模擬（broker 的 simulator）的最新讀值與 PLC 狀態寫進 OPC UA 節點。

    不發布批次（產生情境）的資料：批次期間只標 ``idle``；批次結束後，先略過當下還留在 ``latest_data`` 的
    讀值（可能是批次最後一步），等即時模擬寫入新的讀值再發布。
    """

    def __init__(self, server: Z72OpcUaServer, broker: LiveSource) -> None:
        """建立。

        Args:
            server: 已 ``start`` 的 server。
            broker: ``DataBroker``（讀 ``source_kind`` 與 ``simulator``）。
        """
        self._server = server
        self._broker = broker
        self._tag_ids = [col.tag.id for col in server.columns]
        self._sim_key: Optional[Tuple[int, int]] = None  # (id(simulator), bulk_runs)
        self._skip_stamps: Dict[str, str] = {}
        self._last_ts: Dict[str, str] = {}
        self._wind_avg: Dict[str, RollingMean] = {}
        self._published: Set[str] = set()

    async def _idle(self) -> None:
        await self._server.set_status(Source="live", Status="idle", PackId="", Mode="live")

    async def update(self) -> None:
        """讀一次即時模擬：每台機組的最新讀值（有新的才寫）與 PLC 的事件碼清單。"""
        simulator = self._broker.simulator
        if simulator is None or self._broker.source_kind != "simulation" or simulator.is_bulk_running:
            await self._idle()
            return
        data = simulator.get_current_data()
        key = (id(simulator), simulator.bulk_runs)
        if key != self._sim_key:
            # 換了 simulator（換風場 / 來源）或跑過批次：重來，當下留著的讀值可能是批次的，先不發布
            fresh_sim = self._sim_key is None or self._sim_key[0] != key[0]
            self._sim_key = key
            self._last_ts.clear()
            self._wind_avg.clear()
            self._skip_stamps = {} if fresh_sim and key[1] == 0 else \
                {tid: str(r.get("timestamp")) for tid, r in data.items() if r}
        models = dict(simulator.turbines)
        for turbine_id in sorted(self._published - set(models)):
            await self._server.clear_turbine(turbine_id)
            self._published.discard(turbine_id)
        newest: Optional[datetime] = None
        for turbine_id, model in models.items():
            reading = data.get(turbine_id)
            if not reading or not isinstance(reading.get("scada"), dict):
                continue
            stamp = str(reading["timestamp"])
            if self._skip_stamps.get(turbine_id) == stamp:
                continue
            self._skip_stamps.pop(turbine_id, None)
            await self._server.ensure_turbine(turbine_id)
            self._published.add(turbine_id)
            ts = parse_iso(stamp)
            if self._last_ts.get(turbine_id) != stamp:
                self._last_ts[turbine_id] = stamp
                values = sp.json_values(sp.scada_dict_values(reading["scada"], self._tag_ids), self._server.columns)
                wind = values.get(WSPEED_TAG)
                values[WSPEED_AVG10M_TAG] = self._wind_avg.setdefault(turbine_id, RollingMean()).add(
                    ts.timestamp(), float(wind) if isinstance(wind, (int, float)) else None)
                await self._server.write_values(turbine_id, values, ts)
            # 模擬執行緒同時在改清單；snapshot 只複製三個 list（GIL 下逐一複製不會讀到壞掉的 list）
            await self._server.write_lists(turbine_id, model.plc.active_lists.snapshot(), ts)
            newest = ts if newest is None or ts > newest else newest
        if newest is None:
            await self._idle()
            return
        await self._server.set_status(Source="live", Status="running", PackId="", Mode="live", SimTime=newest)

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
        """停止更新與監聽（等更新的 task 結束，但不吞掉呼叫端自己被取消）。"""
        self.task.cancel()
        await asyncio.wait([self.task])
        await self.server.stop()


async def start_live_from_env(broker: LiveSource, env: Optional[Mapping[str, str]] = None) -> Optional[LiveOpcUa]:
    """``WMOM_OPCUA_ENABLE=true`` 時起即時模擬的 OPC UA server（``WMOM_OPCUA_HOST`` / ``WMOM_OPCUA_PORT``）。

    選配功能：起不來（埠被占用、設定錯誤等）只記警告，不擋主程式。預設只聽 ``127.0.0.1``。

    Args:
        broker: ``DataBroker``。
        env: 環境變數；None＝``os.environ``。

    Returns:
        執行中的 server，或 None（沒開啟 / 起不來）。
    """
    if not oc.opcua_enabled(env):
        return None
    try:
        host, port = oc.live_bind(env)
        server = Z72OpcUaServer(host=host, port=port)
        await server.start()
    except Exception as exc:  # noqa: BLE001
        logger.warning("OPC UA server not started: %s", exc)
        return None
    logger.info("OPC UA server (live simulation) at %s", server.endpoint)
    return LiveOpcUa(server=server, task=asyncio.create_task(LiveFeeder(server, broker).run()))
