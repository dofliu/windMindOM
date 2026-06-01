"""RAG 策略檔載入器（M5-1）。

「RAG_Ultimate 提供策略檔，windMindOM 只讀」—— 本模組把 yaml 策略檔
（chunking / embedding / retrieval）讀進 ``RagStrategy``。

baseline placeholder 契約（MVP_ARCHITECTURE §3.5 / EPIC-M5 M5-3）：
正式策略檔由 RAG_Ultimate Phase 3 交付前，檔案可能尚未存在 ——
``load_strategy`` 在路徑缺失時 **不丟例外**，而是回 ``default_strategy()``
（baseline），讓平台能在純 simulator 模式啟動 demo。
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from modules.knowledge.schemas import RagStrategy

logger = logging.getLogger(__name__)

# 內建 baseline 策略檔（與 RAG_Ultimate 正式檔同結構，參數保守）。
DEFAULT_STRATEGY_PATH = (
    Path(__file__).resolve().parent / "config" / "rag_strategy_z72_manual.yaml"
)


def default_strategy() -> RagStrategy:
    """回傳純程式內建的 baseline 策略（不讀檔）。

    當策略檔缺失 / 損毀時的 fallback；參數對齊 ``RagStrategy`` 各 sub-model
    的 default。
    """
    return RagStrategy(name="baseline")


def load_strategy(path: str | Path | None = None) -> RagStrategy:
    """從 yaml 載入 RAG 策略檔。

    Args:
        path: 策略檔路徑；``None`` 時用內建 ``DEFAULT_STRATEGY_PATH``。

    Returns:
        解析後的 ``RagStrategy``。檔案不存在或內容非 mapping 時記 warning
        並回 ``default_strategy()``（baseline placeholder 契約）。

    Note:
        yaml 解析失敗（語法錯誤）會原樣拋出 —— 那是設定錯誤，不該被
        靜默 fallback 掩蓋；只有「檔案缺失 / 空檔 / 非 mapping」走 baseline。
    """
    target = Path(path) if path is not None else DEFAULT_STRATEGY_PATH

    if not target.is_file():
        logger.warning(
            "RAG 策略檔不存在（%s），改用 baseline default 策略（純 simulator 模式）。",
            target,
        )
        return default_strategy()

    raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    if raw is None:
        logger.warning("RAG 策略檔為空檔（%s），改用 baseline default 策略。", target)
        return default_strategy()
    if not isinstance(raw, dict):
        logger.warning(
            "RAG 策略檔內容非 mapping（%s），改用 baseline default 策略。", target
        )
        return default_strategy()

    return RagStrategy.model_validate(raw)
