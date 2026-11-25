"""即時模擬的狀態存檔（WMOM-20261125-03-b，重啟續跑）。

把 ``WindFarmSimulator`` 會隨時間演變的狀態（各機組的物理模型與 PLC、故障引擎、風況 / 電網模型、亂數狀態、
模擬時鐘）存成一個檔案，伺服器重啟後還原，風場接著跑——重啟前鎖存的跳機還在、疲勞與結垢不歸零。

檔案格式：一行識別字串、4 個位元組的檔頭長度、JSON 檔頭（版本、程式指紋、機組、時區、模擬時鐘……）、
其後才是模擬器物件的 ``pickle``。讀檔時先看檔頭，版本或程式指紋對不上就**不解開**後面的內容——模擬器的
類別改過之後，舊物件缺新欄位，硬解開會在之後的某一步才出錯。對不上時視為沒有存檔，風場從頭開始。

安全：這是伺服器自己寫、自己讀的本機檔案（與風場 DB 同一個目錄）。``pickle`` 不能拿來讀不可信的來源；
能改這個目錄的人本來就能改 DB 與程式。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

from .time_utils import iso_utc, parse_iso

logger = logging.getLogger(__name__)

CHECKPOINT_VERSION = 1
CHECKPOINT_FILENAME = "live_checkpoint.pkl"
_MAGIC = b"WMOM-LIVE-CHECKPOINT\n"
_MAX_HEADER_BYTES = 1 << 20

_MONITORING_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _MONITORING_ROOT.parents[1]
# 狀態裡的物件來自這些程式與資料；任何一個改了，舊存檔就不還原
_FINGERPRINT_SOURCES = (
    _MONITORING_ROOT / "simulator",
    _MONITORING_ROOT / "wind_model.py",
    _REPO_ROOT / "shared" / "alarm_codes.py",
    _REPO_ROOT / "shared" / "data" / "z72_alarm_catalog.json",
)


@lru_cache(maxsize=1)
def code_fingerprint() -> str:
    """模擬器程式與警報目錄的指紋（sha256）；存檔與目前的程式對不上時不還原。

    Returns:
        16 進位字串。
    """
    digest = hashlib.sha256()
    for source in _FINGERPRINT_SOURCES:
        files = sorted(p for p in source.rglob("*.py")) if source.is_dir() else [source]
        for path in files:
            if not path.is_file():
                continue
            digest.update(str(path.relative_to(_REPO_ROOT)).encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


@dataclass(frozen=True)
class LiveCheckpoint:
    """一份即時模擬的存檔。

    Attributes:
        state: ``WindFarmSimulator.checkpoint_state()`` 的內容。
        sim_clock: 存檔當下的模擬時鐘。
        turbine_ids: 機組 ID（與目前的風場不同就不還原）。
        site_timezone: 風場時區。
        live_epoch: 這段即時資料的連續段編號（該狀態從頭開始的那個 session 的 id）。
        saved_at: 存檔的實際時間（UTC ISO）。
    """

    state: bytes
    sim_clock: Optional[datetime]
    turbine_ids: List[str]
    site_timezone: str
    live_epoch: int
    saved_at: str


def save_checkpoint(path: Path, checkpoint: LiveCheckpoint) -> None:
    """寫入存檔（先寫暫存檔再換名：寫到一半當機不會留下壞檔）。

    Args:
        path: 存檔路徑。
        checkpoint: 存檔內容。
    """
    header: Dict[str, object] = {
        "version": CHECKPOINT_VERSION,
        "fingerprint": code_fingerprint(),
        "saved_at": checkpoint.saved_at,
        "sim_clock": iso_utc(checkpoint.sim_clock) if checkpoint.sim_clock is not None else None,
        "turbine_ids": list(checkpoint.turbine_ids),
        "site_timezone": checkpoint.site_timezone,
        "live_epoch": int(checkpoint.live_epoch),
        "state_bytes": len(checkpoint.state),
    }
    encoded = json.dumps(header, ensure_ascii=False).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as handle:
        handle.write(_MAGIC)
        handle.write(len(encoded).to_bytes(4, "big"))
        handle.write(encoded)
        handle.write(checkpoint.state)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _read_file(path: Path) -> Optional[tuple]:
    """讀出（檔頭 dict、狀態 bytes）；格式不對回 None。"""
    with open(path, "rb") as handle:
        if handle.read(len(_MAGIC)) != _MAGIC:
            return None
        size = int.from_bytes(handle.read(4), "big")
        if not 0 < size <= _MAX_HEADER_BYTES:
            return None
        header = json.loads(handle.read(size).decode("utf-8"))
        state = handle.read()
    if not isinstance(header, dict) or len(state) != header.get("state_bytes") or not state:
        return None  # 檔案被截斷（寫到一半）或檔頭不是物件
    return header, state


def load_checkpoint(path: Path, turbine_ids: List[str], site_timezone: str) -> Optional[LiveCheckpoint]:
    """讀存檔；不存在、壞檔、版本 / 程式指紋 / 機組 / 時區對不上時回 None（風場從頭開始）。

    這個函式不丟例外：存檔有任何問題都只是「沒有存檔」，不能讓伺服器起不來。

    Args:
        path: 存檔路徑。
        turbine_ids: 目前風場的機組 ID。
        site_timezone: 目前風場的時區。

    Returns:
        可以還原的存檔，或 None。
    """
    if not path.is_file():
        return None
    try:
        parsed = _read_file(path)
    except Exception as exc:  # noqa: BLE001  壞檔（寫到一半、磁碟錯誤）就當沒有存檔
        logger.warning("即時模擬的存檔讀不出來，從頭開始：%s", exc)
        return None
    if parsed is None:
        logger.warning("即時模擬的存檔格式不對，從頭開始")
        return None
    header, state = parsed
    reasons = []
    if header.get("version") != CHECKPOINT_VERSION:
        reasons.append("存檔格式版本不同")
    if header.get("fingerprint") != code_fingerprint():
        reasons.append("模擬器程式或警報目錄改過")
    if header.get("turbine_ids") != list(turbine_ids):
        reasons.append("機組不同")
    if header.get("site_timezone") != site_timezone:
        reasons.append("風場時區不同")
    if reasons:
        logger.warning("即時模擬的存檔不還原（%s），從頭開始", "、".join(reasons))
        return None
    try:
        clock = header.get("sim_clock")
        return LiveCheckpoint(
            state=state,
            sim_clock=parse_iso(str(clock)) if clock else None,
            turbine_ids=list(turbine_ids),
            site_timezone=site_timezone,
            live_epoch=int(header.get("live_epoch") or 0),
            saved_at=str(header.get("saved_at") or ""),
        )
    except (TypeError, ValueError) as exc:
        logger.warning("即時模擬的存檔檔頭有讀不懂的欄位，從頭開始：%s", exc)
        return None
