"""讀情境資料包（介面合約 v1 §3–§5，WMOM-20261021-09）。

需要 ``pandas`` 與 ``pyarrow``（``pip install -r requirements.txt``）。

當函式庫用::

    from pack_reader import load_pack
    pack = load_pack("packs/z72-starter-01")
    raw = pack.raw()                       # 每 10 s 一列，欄名＝Bachmann tag 名
    stats = pack.stats()                   # 10 分鐘 avg / min / max / std
    # 模擬「助手在 t 當下」：只看 t 以前的資料（合約 §6 時間因果）
    t = "2026-03-02T02:00:00Z"
    recent = pack.raw_until(t, turbine_id="WT002", window="1h")
    windows = pack.stats_until(t)          # 只有已經結束的 10 分鐘窗
    for event in pack.events_until(t):
        ...

時間參數可給 ISO 字串或 datetime；不帶時區者視為 UTC。

直接執行會檢查 sha256 並印出摘要::

    python pack_reader.py packs/z72-starter-01
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cached_property
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple, Union

import pandas as pd

PathLike = Union[str, Path]
SUPPORTED_MAJOR = 1


def _ts(value: Union[str, datetime, pd.Timestamp]) -> pd.Timestamp:
    """時間（字串 / datetime）→ UTC 的 ``pd.Timestamp``。"""
    ts = pd.Timestamp(value)
    return ts.tz_localize(timezone.utc) if ts.tzinfo is None else ts.tz_convert(timezone.utc)


@dataclass
class Pack:
    """一個資料包。

    Attributes:
        path: 資料包目錄。
        manifest: ``manifest.json``。
    """

    path: Path
    manifest: Dict[str, object]

    @property
    def pack_id(self) -> str:
        """資料包 ID。"""
        return str(self.manifest["pack_id"])

    @property
    def turbines(self) -> List[str]:
        """機組 ID 清單。"""
        turbines = self.manifest["turbines"]
        assert isinstance(turbines, list)
        return [str(t) for t in turbines]

    @cached_property
    def tags(self) -> pd.DataFrame:
        """tag 字典（每個欄位的單位、說明、``source``：``bachmann_real`` / ``synthetic``）。"""
        data = json.loads((self.path / "tag_dictionary.json").read_text(encoding="utf-8"))
        return pd.DataFrame(data["tags"]).set_index("tag")

    @cached_property
    def alarm_catalog(self) -> Dict[int, Dict[str, object]]:
        """Z72 警報目錄：事件碼 → 等級、文字、原因、處置、手冊頁碼。"""
        data = json.loads((self.path / "alarm_catalog.json").read_text(encoding="utf-8"))
        return {int(e["code"]): e for e in data["events"]}

    @cached_property
    def events(self) -> List[Dict[str, object]]:
        """可觀測事件（依時間排序；同一時刻依發生順序）。"""
        text = (self.path / "events.jsonl").read_text(encoding="utf-8")
        return [json.loads(line) for line in text.split("\n") if line.strip()]

    def raw(self, turbine_id: Optional[str] = None, columns: Optional[List[str]] = None) -> pd.DataFrame:
        """原始時序（``timestamp`` 為 UTC、欄名＝Bachmann tag 名、缺值為 NaN / <NA>）。

        Args:
            turbine_id: 只取一台機組。
            columns: 只取這些 tag 欄（``timestamp`` / ``turbine_id`` 會自動帶上）。

        Returns:
            DataFrame。
        """
        return self._read_raw(turbine_id, columns, [])

    def _read_raw(self, turbine_id: Optional[str], columns: Optional[List[str]],
                  filters: List[Tuple[str, str, object]]) -> pd.DataFrame:
        cols = None if columns is None else list(dict.fromkeys(["timestamp", "turbine_id", *columns]))
        if turbine_id is not None:
            filters = [*filters, ("turbine_id", "==", turbine_id)]
        return pd.read_parquet(self.path / "timeseries_raw.parquet", columns=cols, filters=filters or None)

    def stats(self, turbine_id: Optional[str] = None) -> pd.DataFrame:
        """10 分鐘統計（``window_start`` / ``window_end``、``n_samples``、``is_partial``、``<tag>_avg`` …）。

        注意：包含所有窗——在時間 t 只能用 ``window_end <= t`` 的窗（``stats_until``）。
        """
        filters = None if turbine_id is None else [("turbine_id", "==", turbine_id)]
        return pd.read_parquet(self.path / "stats_10min.parquet", filters=filters)

    def stats_until(self, ts: Union[str, datetime], turbine_id: Optional[str] = None) -> pd.DataFrame:
        """``ts`` 當下已經結束的 10 分鐘窗（``window_end <= ts``）——還沒結束的窗含有未來的讀值。

        Args:
            ts: 截止時間。
            turbine_id: 只取一台機組。

        Returns:
            DataFrame。
        """
        df = self.stats(turbine_id)
        return df[df["window_end"] <= _ts(ts)]

    def events_until(self, ts: Union[str, datetime], turbine_id: Optional[str] = None) -> Iterator[Dict[str, object]]:
        """``ts`` 之前（含）發生的事件——模擬「助手在 ts 當下看得到的事件」。

        Args:
            ts: 截止時間。
            turbine_id: 只取一台機組。

        Yields:
            事件。
        """
        cutoff = _ts(ts)
        for event in self.events:
            if _ts(str(event["ts"])) > cutoff:
                return
            if turbine_id is None or event["turbine_id"] == turbine_id:
                yield event

    def raw_until(self, ts: Union[str, datetime], turbine_id: Optional[str] = None,
                  window: str = "1h", columns: Optional[List[str]] = None) -> pd.DataFrame:
        """``ts`` 之前（含）、最近 ``window`` 的原始資料——助手在 ts 當下該看的範圍（不偷看未來）。

        Args:
            ts: 截止時間。
            turbine_id: 只取一台機組。
            window: 往回看多久（pandas 時間字串，例 ``"30min"``、``"2h"``）。
            columns: 只取這些 tag 欄。

        Returns:
            DataFrame。
        """
        end = _ts(ts)
        start = end - pd.Timedelta(window)
        # 時間條件推進 Parquet 讀取（只讀需要的 row group），不必每次讀整個檔
        return self._read_raw(turbine_id, columns, [("timestamp", ">", start), ("timestamp", "<=", end)])


def verify_pack(path: PathLike) -> List[str]:
    """核對 manifest 列的每個檔案（存在、大小、sha256）與合約主版本。

    Args:
        path: 資料包目錄。

    Returns:
        問題清單；空＝通過。
    """
    pack_dir = Path(path)
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    problems = []
    major = int(str(manifest.get("contract_version", "0")).split(".")[0])
    if major != SUPPORTED_MAJOR:
        problems.append(f"合約版本 {manifest.get('contract_version')} 不是本程式支援的 {SUPPORTED_MAJOR}.x")
    for name, info in manifest["files"].items():
        file = pack_dir / name
        if not file.exists():
            problems.append(f"{name}：檔案不見了")
            continue
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        if digest != info["sha256"] or file.stat().st_size != info["bytes"]:
            # 常見原因：Windows 的 git 設定 core.autocrlf 把 JSON 的換行改成 CRLF（repo 已用 .gitattributes 關掉）
            problems.append(f"{name}：sha256 / 大小與 manifest 不符（檔案被改過或換行被轉換）")
    return problems


def load_pack(path: PathLike, verify: bool = True) -> Pack:
    """開一個資料包。

    Args:
        path: 資料包目錄。
        verify: 先核對 sha256（大的資料包可關掉）。

    Returns:
        ``Pack``。

    Raises:
        ValueError: 核對不過。
    """
    pack_dir = Path(path)
    if verify:
        problems = verify_pack(pack_dir)
        if problems:
            raise ValueError(f"{pack_dir}: " + "; ".join(problems))
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    return Pack(path=pack_dir, manifest=manifest)


def summary(pack: Pack) -> str:
    """資料包摘要（給人看）。"""
    m = pack.manifest
    counts = m["counts"]
    assert isinstance(counts, dict)
    lines = [
        f"{pack.pack_id}（合約 v{m['contract_version']}）",
        f"  機組 {', '.join(pack.turbines)}；{m['sim_start']} → {m['sim_end']}；每 {m['sample_period_s']} s 一筆",
        f"  raw {counts['raw_rows']} 列 × {len(pack.tags)} 個 tag "
        f"（真實 Bachmann {int((pack.tags['source'] == 'bachmann_real').sum())}）；10 分鐘統計 {counts['stats_rows']} 列",
        f"  事件 {len(pack.events)} 筆：" + "、".join(f"{k} {v}" for k, v in Counter(
            str(e["event_type"]) for e in pack.events).most_common()),
    ]
    alarms = [e for e in pack.events if e["event_type"] in ("alarm_raised", "trip")]
    for event in alarms[:10]:
        entry = pack.alarm_catalog.get(int(str(event["alarm_code"])), {})
        lines.append(f"  {event['ts']} {event['turbine_id']} {event['event_type']:<12} "
                     f"{event['alarm_code']} {event['alarm_text']}（手冊 p.{entry.get('manual_page')}）")
    if len(alarms) > 10:
        lines.append(f"  …另 {len(alarms) - 10} 筆警報 / 跳機")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python pack_reader.py <資料包目錄> [...]", file=sys.stderr)
        sys.exit(2)
    for arg in sys.argv[1:]:
        print(summary(load_pack(arg)))
        print()
