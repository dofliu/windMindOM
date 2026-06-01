"""知識庫載入 + 查詢輔助（M5-1）。

baseline 模式下，知識庫塊直接從 JSON（``data/baseline_corpus_z72.json``）載入，
無向量。M5-2 ChromaDB 整合後，正式向量檔（RAG_Ultimate 交付的 ``.parquet``）
會載進 ChromaDB，本 ``KnowledgeCorpus`` 仍可作為 metadata 同步層 / 純文字
fallback。

設計邊界：純資料容器 + filter，不接 ChromaDB / FastAPI。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from modules.knowledge.schemas import KnowledgeChunk

logger = logging.getLogger(__name__)

DEFAULT_CORPUS_PATH = (
    Path(__file__).resolve().parent / "data" / "baseline_corpus_z72.json"
)


def load_chunks(path: str | Path | None = None) -> list[KnowledgeChunk]:
    """從 JSON 載入知識庫塊清單。

    Args:
        path: 知識庫 JSON 路徑；``None`` 時用內建 baseline corpus。

    Returns:
        ``KnowledgeChunk`` 清單。檔案缺失回空 list（記 warning），讓平台
        仍能啟動（檢索會回空結果，前端標示 baseline 未就緒）。

    Note:
        JSON 結構：``{"chunks": [ {...}, ... ], "_meta": {...}}``；
        ``_meta`` 為說明用，載入時忽略。
    """
    target = Path(path) if path is not None else DEFAULT_CORPUS_PATH

    if not target.is_file():
        logger.warning("知識庫 JSON 不存在（%s），回空 corpus。", target)
        return []

    raw = json.loads(target.read_text(encoding="utf-8"))
    chunks_raw = raw.get("chunks", []) if isinstance(raw, dict) else raw

    # 單筆 chunk 損毀時 skip + warning，不讓整份知識庫載入中止（平台仍可啟動）。
    # M5-3 接 RAG_Ultimate 真向量檔後，個別格式異常風險升高，此 graceful
    # 處理避免一筆壞資料拖垮整個 knowledge module。
    valid_chunks: list[KnowledgeChunk] = []
    for i, chunk_raw in enumerate(chunks_raw):
        try:
            valid_chunks.append(KnowledgeChunk.model_validate(chunk_raw))
        except Exception as exc:  # noqa: BLE001 — 任何驗證錯誤都 skip 該筆
            logger.warning("知識庫第 %d 筆 chunk 驗證失敗（略過）：%s", i, exc)
    return valid_chunks


class KnowledgeCorpus:
    """記憶體內的知識庫（chunk 集合）+ 常用查詢輔助。"""

    def __init__(self, chunks: list[KnowledgeChunk]) -> None:
        """以 chunk 清單建立 corpus。"""
        self._chunks: list[KnowledgeChunk] = list(chunks)
        # 告警碼 → chunks 索引（一個碼可命中多塊；一塊可對多碼）。
        self._by_alarm: dict[int, list[KnowledgeChunk]] = {}
        for chunk in self._chunks:
            for code in chunk.alarm_codes:
                self._by_alarm.setdefault(code, []).append(chunk)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "KnowledgeCorpus":
        """從 JSON 載入並建立 corpus（便捷工廠）。"""
        return cls(load_chunks(path))

    @property
    def chunks(self) -> list[KnowledgeChunk]:
        """所有 chunk（回 copy 避免外部誤改內部 list）。"""
        return list(self._chunks)

    def __len__(self) -> int:
        """chunk 數量。"""
        return len(self._chunks)

    def is_empty(self) -> bool:
        """corpus 是否為空（baseline 未就緒時為 True）。"""
        return not self._chunks

    def by_alarm_code(self, code: int) -> list[KnowledgeChunk]:
        """回傳對應某告警碼的所有 chunk（無命中回空 list）。"""
        return list(self._by_alarm.get(code, []))

    def filter(
        self, oem: str | None = None, model: str | None = None
    ) -> "KnowledgeCorpus":
        """依 OEM / 機型過濾，回新的 ``KnowledgeCorpus``。

        ``None`` 表示該維度不限。比對為精確（大小寫敏感），對齊 chunk
        的 ``oem`` / ``model`` 欄位寫法。
        """
        selected = [
            c
            for c in self._chunks
            if (oem is None or c.oem == oem) and (model is None or c.model == model)
        ]
        return KnowledgeCorpus(selected)
