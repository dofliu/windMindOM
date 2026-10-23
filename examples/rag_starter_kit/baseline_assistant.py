"""最陽春的「維修助手」：示範輸出格式，也是學生要超越的基準（介面合約 v1 §6，WMOM-20261021-09）。

只用 Python 標準函式庫。做法刻意簡單：

- 只看 ``events.jsonl``：每台機組出現新的警報 / 跳機碼時，用警報文字的關鍵字猜元件，輸出一筆診斷，
  手冊引用列出該機組至今出現過的碼（最新的在前）。
- 資訊類事件（I 級，例：201 風速過高停機）一律判成干擾（``nuisance``）。
- 同一個警報 / 跳機碼 60 秒內已在另一台機組出現（例：電網擾動全場一起跳）→ 判成干擾（v1.5）。第一台機組
  那時還看不出來，照樣當故障——這筆會算誤報。
- 警報文字點名感測器（sensor / encoder / temperature fault）時判成感測器故障，其餘判 ``real_fault``。

所以它**做不到**的正是學生專題該做的：
- 不看時序訊號 → 沒有早期預警（一定等警報出來才反應）。
- 只看警報文字判類別 → 讀值像真故障的感測器故障（例：溫度量測回路劣化，送出的是和真故障一樣的
  262 / 240）分不出來；要比對同元件的第二支感測器、振動與負載才看得出。
- 關鍵字對照取代檢索 → 換一組警報就猜不到，也不會讀手冊的原因 / 處置。
- 不看事件的模式 → 認不出單一機組的干擾（例：Pt100 接點鬆動反覆跳 242、跳完讀值立刻正常），一律當故障。

用法::

    python baseline_assistant.py packs/ -o predictions/baseline.jsonl
    python score.py --answers answers/ --predictions predictions/baseline.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# 警報文字關鍵字 → 元件（vocabulary.json 的 id）；依序比對，先中先贏
KEYWORDS: Sequence[Tuple[Tuple[str, ...], str]] = (
    (("bearing",), "main_bearing"),
    (("rotor speed",), "rotor_speed_sensor"),
    (("wind meter", "anemometer"), "nacelle_anemometer"),
    (("overspeed",), "pitch_control_system"),
    (("blade", "pitch"), "pitch_control_system"),
    (("yaw brake",), "yaw_brake_hydraulics"),
    (("wind vane",), "wind_vane_1"),
    (("cooling water", "static water", "converter"), "converter_cooling_system"),
    (("transformer",), "transformer"),
    (("stator",), "generator_stator"),
    (("undervoltage", "overvoltage", "grid"), "grid_connection"),
    (("nacelle",), "nacelle_ventilation"),
)


# 警報文字點名感測器 → 感測器故障（只認得有專屬故障碼的；讀值像真故障的漂移認不出來）
SENSOR_WORDS: Tuple[str, ...] = ("sensor", "encoder", "temperature fault", "signal fault")
# 同一個碼在另一台機組這麼多秒內也出現 → 全場一起發生，判成干擾
FARM_WIDE_WINDOW_S = 60.0


def guess_category(alarm_text: str) -> str:
    """警報文字 → 類別（``sensor_fault`` 或 ``real_fault``）。

    Args:
        alarm_text: 警報目錄的英文文字。

    Returns:
        類別。
    """
    text = alarm_text.lower()
    return "sensor_fault" if any(word in text for word in SENSOR_WORDS) else "real_fault"


def guess_component(alarm_text: str) -> Optional[str]:
    """警報文字 → 元件（猜不到回 None）。

    Args:
        alarm_text: 警報目錄的英文文字。

    Returns:
        元件 id。
    """
    text = alarm_text.lower()
    for words, component in KEYWORDS:
        if any(word in text for word in words):
            return component
    return None


def read_events(pack_dir: Path) -> Tuple[str, List[Dict[str, object]]]:
    """讀資料包的 pack_id 與事件。

    Args:
        pack_dir: 資料包目錄。

    Returns:
        ``(pack_id, 事件)``。
    """
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    lines = (pack_dir / "events.jsonl").read_text(encoding="utf-8").split("\n")
    return str(manifest["pack_id"]), [json.loads(line) for line in lines if line.strip()]


class BaselineAssistant:
    """基準助手的狀態：一次吃一則事件，需要時回傳一筆判斷（``diagnose`` 與 ``stream_client`` 共用）。"""

    def __init__(self) -> None:
        self._seen_codes: Dict[str, List[int]] = {}
        # 事件碼 → {機組: 最近一次出現的時間}
        self._last_seen: Dict[int, Dict[str, datetime]] = {}

    def on_event(self, event: Dict[str, object]) -> Optional[Dict[str, object]]:
        """處理一則事件。

        Args:
            event: 事件（欄位同 ``events.jsonl``）。

        Returns:
            判斷（合約 §6 欄位，不含 ``pack_id`` / ``ts``）或 None。
        """
        turbine = str(event["turbine_id"])
        if event["event_type"] == "info":
            return {"turbine_id": turbine, "category": "nuisance", "component": None,
                    "manual_refs": [event["alarm_code"]],
                    "root_cause": f"Informational event {event['alarm_code']}: {event['alarm_text']}"}
        if event["event_type"] not in ("alarm_raised", "trip"):
            return None
        code = int(str(event["alarm_code"]))
        ts = datetime.fromisoformat(str(event["ts"]).replace("Z", "+00:00"))
        seen = self._last_seen.setdefault(code, {})
        farm_wide = [t for t, last in seen.items()
                     if t != turbine and abs((ts - last).total_seconds()) <= FARM_WIDE_WINDOW_S]
        seen[turbine] = ts
        codes = self._seen_codes.setdefault(turbine, [])
        if code in codes:
            return None
        codes.insert(0, code)
        if farm_wide:
            return {"turbine_id": turbine, "category": "nuisance", "component": None, "manual_refs": [code],
                    "root_cause": f"Event {code} on {len(farm_wide) + 1} turbines within {FARM_WIDE_WINDOW_S:.0f} s: "
                                  "a farm-wide disturbance, not a turbine fault"}
        component = guess_component(str(event["alarm_text"]))
        if component is None:
            return None
        return {"turbine_id": turbine, "category": guess_category(str(event["alarm_text"])), "component": component,
                "manual_refs": list(codes),
                "root_cause": f"Alarm {code}: {event['alarm_text']}",
                "actions": ["Check the Z72 manual entries cited in manual_refs."]}


def diagnose(pack_id: str, events: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    """依事件逐筆產生診斷（只用到當下以前的事件）。

    Args:
        pack_id: 資料包 ID。
        events: 依時間排序的事件。

    Returns:
        預測（合約 §6 格式）。
    """
    assistant = BaselineAssistant()
    predictions: List[Dict[str, object]] = []
    for event in events:
        judgement = assistant.on_event(event)
        if judgement is not None:
            turbine = judgement.pop("turbine_id")
            predictions.append({"pack_id": pack_id, "turbine_id": turbine, "ts": event["ts"], **judgement})
    return predictions


def pack_dirs(paths: Sequence[Path]) -> List[Path]:
    """展開參數：資料包目錄，或內含多個資料包的目錄。

    Args:
        paths: 命令列給的路徑。

    Returns:
        資料包目錄。

    Raises:
        FileNotFoundError: 路徑不存在。
    """
    out: List[Path] = []
    for path in paths:
        if not path.is_dir():
            raise FileNotFoundError(path)
        if (path / "manifest.json").exists():
            out.append(path)
        else:
            out.extend(sorted(p for p in path.iterdir() if (p / "manifest.json").exists()))
    return out


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 進入點。

    Args:
        argv: 命令列參數（測試用）；None＝``sys.argv``。

    Returns:
        exit code。
    """
    parser = argparse.ArgumentParser(description="基準維修助手（關鍵字對照）")
    parser.add_argument("packs", type=Path, nargs="+", help="資料包目錄，或內含多個資料包的目錄")
    parser.add_argument("-o", "--output", type=Path, help="輸出 predictions.jsonl（預設印到 stdout）")
    args = parser.parse_args(argv)

    try:
        packs = pack_dirs(args.packs)
    except FileNotFoundError as exc:
        print(f"找不到資料包目錄：{exc}", file=sys.stderr)
        return 2
    if not packs:
        print("沒有找到資料包（含 manifest.json 的目錄）", file=sys.stderr)
        return 2
    lines = []
    for pack_dir in packs:
        pack_id, events = read_events(pack_dir)
        lines += [json.dumps(p, ensure_ascii=False) for p in diagnose(pack_id, events)]
    text = "".join(line + "\n" for line in lines)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
