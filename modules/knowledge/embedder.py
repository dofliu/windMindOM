"""Query 端嵌入器（M5-2）。

對應 DEC-20260608-01：預算向量是語料；使用者 query 是即時的，必須用
**同一個 ``Z72_WT_embed_small``**（RAG_Ultimate fine-tune 的 sentence-transformers
模型）把 query 也 encode 成 512 維 normalized 向量，才能跟語料向量做 cosine。

模型走 deploy artifact（~95MB，gitignore），路徑解析：
明確參數 > env ``WMOM_EMBED_MODEL_DIR`` > 預設 shipped 位置
``modules/knowledge/models/Z72_WT_embed_small``。

設計：lazy load（建構不載模型，首次 ``encode`` 才載），模型缺失 / 套件缺失
拋 ``EmbedderUnavailable`` 讓上層 graceful fallback baseline。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# 預設模型位置（shipped artifact，gitignore）。env 可覆寫指向 RAG_Ultimate 原始模型 / 客戶部署路徑。
DEFAULT_MODEL_DIR = (
    Path(__file__).resolve().parent / "models" / "Z72_WT_embed_small"
)
_ENV_MODEL_DIR = "WMOM_EMBED_MODEL_DIR"


class EmbedderUnavailable(RuntimeError):
    """模型目錄缺失 / sentence-transformers 未安裝 / 載入失敗時拋出。

    呼叫端攔此例外即可 fallback 回 baseline keyword retriever。
    """


def resolve_model_dir(model_dir: str | Path | None = None) -> Path:
    """決定模型目錄：明確參數 > env > 預設 shipped 位置。"""
    if model_dir is not None:
        return Path(model_dir)
    env = os.environ.get(_ENV_MODEL_DIR)
    if env:
        return Path(env)
    return DEFAULT_MODEL_DIR


class QueryEmbedder:
    """包 ``SentenceTransformer`` 的 query 嵌入器（lazy load）。"""

    def __init__(self, model_dir: str | Path | None = None) -> None:
        """記錄模型路徑（不立即載入）。

        Args:
            model_dir: 模型目錄；``None`` 時依 ``resolve_model_dir`` 解析。
        """
        self._model_dir = resolve_model_dir(model_dir)
        self._model: object | None = None  # 首次 encode 才實際載入

    @property
    def model_dir(self) -> Path:
        """目前模型目錄。"""
        return self._model_dir

    def _ensure_loaded(self) -> object:
        """首次使用時載入 ``SentenceTransformer``，缺套件 / 缺模型 → ``EmbedderUnavailable``。"""
        if self._model is not None:
            return self._model

        if not self._model_dir.is_dir():
            raise EmbedderUnavailable(
                f"嵌入模型目錄不存在：{self._model_dir}"
                f"（請放置 Z72_WT_embed_small 或設 {_ENV_MODEL_DIR}）"
            )

        try:
            # lazy import：未裝 sentence-transformers 時不阻擋 module import，
            # 只在真要做向量檢索時才要求依賴。
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover — 依賴缺失路徑
            raise EmbedderUnavailable(
                "未安裝 sentence-transformers，無法做語意檢索（pip install sentence-transformers）"
            ) from exc

        try:
            self._model = SentenceTransformer(str(self._model_dir))
        except Exception as exc:  # noqa: BLE001 — 模型載入各種底層錯誤統一轉 graceful
            raise EmbedderUnavailable(f"嵌入模型載入失敗：{exc}") from exc

        logger.info("已載入 query 嵌入模型：%s", self._model_dir)
        return self._model

    def encode(self, text: str) -> np.ndarray:
        """把單筆 query 文字編成 1D float32 向量（L2 normalized）。

        ``normalize_embeddings=True`` 確保與語料向量同為單位長度，cosine = dot。

        Raises:
            EmbedderUnavailable: 模型 / 套件缺失。
        """
        model = self._ensure_loaded()
        vec = model.encode(  # type: ignore[attr-defined]  # SentenceTransformer.encode
            text, normalize_embeddings=True, convert_to_numpy=True
        )
        return np.ascontiguousarray(vec, dtype=np.float32).reshape(-1)
