"""產生 RAG 學生專題 starter kit 的範例資料包（WMOM-20261021-09，EPIC-DS Phase 3d）。

每個範例是一個固定的批次情境：固定起點（UTC）、固定風況、固定故障排程，從全新的模擬器生成。
生成走與 ``POST /api/config/simulation/generate-bulk`` 相同的路徑（事件、標準答案都一樣），每個範例各用
一個新的暫存 DB（情境 session id 固定、與建置順序無關），不碰伺服器的 DB。

可重產：同一份程式碼、同版 numpy / pyarrow 重跑，資料檔逐位元相同（manifest 的 ``exported_at`` 與答案的
``generated_at`` 除外；Parquet 檔尾記有 pyarrow 版本，換版本只會差在那裡）。模擬器讀「現在時間」的地方
有三處：``simulator.engine``（批次起點）、``wind_model``（profile 從現在的自動風況過渡）都在 ``_sim_clock``
釘住；``fault_engine`` 的 ``started_at`` 與 ``grid_model`` 的 profile 起點目前不影響輸出（測試會擋）。

輸出（預設 ``examples/rag_starter_kit/``）：

```
packs/{pack_id}/                    盲測版資料包（同 GET /api/scenarios/{id}/pack）
answers/{pack_id}.ground_truth.json 標準答案（資料包之外；學生跑完自己的助手再拿來評分）
```

用法：
  python tools/build_rag_starter_kit.py              # 重建全部範例
  python tools/build_rag_starter_kit.py --probe      # 只生成、列出事件與答案摘要（挑情境用）
  python tools/build_rag_starter_kit.py --only z72-starter-02
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
MONITORING_ROOT = REPO_ROOT / "modules" / "monitoring"
for _path in (REPO_ROOT, MONITORING_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import simulator.engine as engine_mod  # noqa: E402
import wind_model as wind_model_mod  # noqa: E402
from server.data_broker import DataBroker  # noqa: E402
from server.routers import config as config_ep  # noqa: E402
from server.scenario_pack import export_ground_truth, export_scenario_pack  # noqa: E402
from server.storage import Storage  # noqa: E402
from simulator.engine import WindFarmSimulator  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "examples" / "rag_starter_kit"


@dataclass(frozen=True)
class StarterPack:
    """一個範例資料包的情境設定。

    Attributes:
        pack_id: 資料包 ID。
        title: 簡述（只寫進答案的 ``scenario_name``，不進資料包）。
        start: 模擬起點（UTC）。
        turbines: 機組數（WT001 起）。
        hours: 情境長度。
        wind_profile: 風況 profile（``wind_model.set_profile``）。
        faults: 故障排程（``generate-bulk`` 的 ``fault_schedule``）。
    """

    pack_id: str
    title: str
    start: datetime
    turbines: int
    hours: float
    wind_profile: str
    faults: Sequence[Dict[str, object]] = field(default_factory=tuple)


STARTER_PACKS: List[StarterPack] = [
    StarterPack(
        pack_id="z72-starter-01",
        title="入門：一台機組主軸承磨耗，額定風速",
        start=datetime(2026, 3, 2, 1, 0, tzinfo=timezone.utc),
        turbines=3, hours=4.0, wind_profile="rated",
        faults=(
            {"scenario_id": "bearing_wear", "turbine_id": "WT002", "offset_seconds": 1200, "severity_rate": 0.0004},
        ),
    ),
    StarterPack(
        pack_id="z72-starter-02",
        title="中等：偏航煞車液壓洩漏 + 變頻器冷卻故障（手冊只寫 See [ABB]），強風",
        start=datetime(2026, 3, 9, 4, 0, tzinfo=timezone.utc),
        turbines=4, hours=6.0, wind_profile="strong",
        faults=(
            {"scenario_id": "hydraulic_leak", "turbine_id": "WT001", "offset_seconds": 1800, "severity_rate": 0.001},
            {"scenario_id": "converter_cooling_fault", "turbine_id": "WT004", "offset_seconds": 3600,
             "severity_rate": 0.001},
        ),
    ),
    StarterPack(
        pack_id="z72-starter-03",
        title="干擾：風向標漂移（感測器故障）+ 葉片角不平衡，陣風、健康機組也有事件",
        start=datetime(2026, 3, 16, 7, 0, tzinfo=timezone.utc),
        turbines=5, hours=6.0, wind_profile="gusty",
        faults=(
            {"scenario_id": "yaw_sensor_drift", "turbine_id": "WT003", "offset_seconds": 900, "severity_rate": 0.001},
            {"scenario_id": "pitch_imbalance", "turbine_id": "WT005", "offset_seconds": 5400, "severity_rate": 0.001},
        ),
    ),
]


class _HeadlessBroker:
    """``generate_bulk`` 端點用到的 broker 表面：不起 Live、不開預設 DB（事件寫入沿用 DataBroker 的實作）。"""

    _PLC_EVENT_TITLES = DataBroker._PLC_EVENT_TITLES
    _plc_event_fields = DataBroker._plc_event_fields
    _state_transition_fields = DataBroker._state_transition_fields
    _state_name = DataBroker._state_name
    record_bulk_events = DataBroker.record_bulk_events

    def __init__(self, storage: Storage, simulator: WindFarmSimulator) -> None:
        self.storage = storage
        self.simulator = simulator
        self._session_id = storage.create_session(data_source="simulation", turbine_count=len(simulator.turbines))

    @contextmanager
    def pause_live_for_batch(self) -> Iterator[bool]:
        yield False

    def record_event(self, session_id: Optional[int] = None, **kwargs: object) -> None:
        self.storage.record_event(session_id=session_id if session_id is not None else self._session_id,
                                  **kwargs)  # type: ignore[arg-type]  # 轉交 record_event 的關鍵字參數


@contextmanager
def _sim_clock(start: datetime) -> Iterator[None]:
    """把時鐘釘在 ``start``：``generate_bulk`` 以 ``utc_now()`` 為起點，``set_profile`` / ``set_override``
    從「現在」的自動風況平滑過渡到設定風況——兩者都要釘住，資料才能重產。"""
    modules = (engine_mod, wind_model_mod)
    originals = [m.utc_now for m in modules]
    for module in modules:
        module.utc_now = lambda: start
    try:
        yield
    finally:
        for module, original in zip(modules, originals):
            module.utc_now = original


def generate(storage: Storage, spec: StarterPack) -> int:
    """生成一個範例情境。

    Args:
        storage: 暫存 DB。
        spec: 情境設定。

    Returns:
        情境 session id。
    """
    sim = WindFarmSimulator(turbine_count=spec.turbines)
    with _sim_clock(spec.start):
        sim.wind_model.set_profile(spec.wind_profile)
        broker = _HeadlessBroker(storage, sim)
        original = config_ep.get_broker
        config_ep.get_broker = lambda: broker
        try:
            result = asyncio.run(config_ep.generate_bulk({
                "duration_hours": spec.hours, "time_step": 10.0, "name": spec.title,
                "wind_profile": spec.wind_profile, "fault_schedule": [dict(f) for f in spec.faults],
            }))
        finally:
            config_ep.get_broker = original
    return int(result["scenario_id"])


def _probe(storage: Storage, scenario_id: int, spec: StarterPack) -> None:
    gt = storage.get_ground_truth(scenario_id) or {}
    events = storage.session_events(scenario_id)
    plc = [e for e in events if e.get("source") == "plc"]
    print(f"== {spec.pack_id}: {spec.title}")
    print(f"   events: {len(events)} total, {len(plc)} PLC, healthy={gt.get('healthy_turbines')}")
    for case in gt.get("cases", []):
        print(f"   {case['case_id']} {case['turbine_id']} {case['fault_id']}: first_alarm={case['first_alarm_ts']} "
              f"({case['first_alarm_code']}) trip={case['trip_ts']} ({case['trip_code']}) "
              f"observed={case['observed_alarm_codes']} other={case['other_observed_codes']}")
    for item in gt.get("unattributed_events", []):
        print(f"   unattributed {item['ts']} {item['turbine_id']} {item['kind']} {item['code']} {item['text']}")


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 進入點。

    Args:
        argv: 命令列參數（測試用）；None＝``sys.argv``。

    Returns:
        exit code。
    """
    parser = argparse.ArgumentParser(description="產生 RAG starter kit 範例資料包")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="starter kit 目錄")
    parser.add_argument("--only", action="append", help="只建指定 pack_id（可重複）")
    parser.add_argument("--probe", action="store_true", help="只生成並列出事件 / 答案摘要，不寫檔")
    args = parser.parse_args(argv)

    known = {s.pack_id for s in STARTER_PACKS}
    unknown = sorted(set(args.only or []) - known)
    if unknown:
        parser.error(f"不認得的 pack_id：{unknown}（可用：{sorted(known)}）")
    specs = [s for s in STARTER_PACKS if not args.only or s.pack_id in args.only]
    workdir = Path(tempfile.mkdtemp(prefix="wmom-starter-"))
    try:
        for spec in specs:
            storage = Storage(db_path=str(workdir / f"{spec.pack_id}.db"))
            scenario_id = generate(storage, spec)
            if args.probe:
                _probe(storage, scenario_id, spec)
                continue
            pack_dir = args.out / "packs" / spec.pack_id
            manifest = export_scenario_pack(storage, scenario_id, pack_dir, pack_id=spec.pack_id)
            export_ground_truth(storage, scenario_id, args.out / "answers" / f"{spec.pack_id}.ground_truth.json",
                                pack_id=spec.pack_id)
            counts = manifest["counts"]
            print(f"{spec.pack_id}: raw {counts['raw_rows']} 列、事件 {counts['events']} 筆 → {pack_dir}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
