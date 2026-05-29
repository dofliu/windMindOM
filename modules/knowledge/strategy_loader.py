"""RAG 策略檔載入器（M5-1 Knowledge module 第一塊）。

核心契約（見 docs/product/MVP_ARCHITECTURE.md §3.5）：

    RAG_Ultimate（research）  →  windMindOM（產品）
    1. strategy.yaml          →  本模組讀策略檔（chunking / embedding / retrieval 參數）
    2. *.parquet 向量檔        →  ingest/retrieve 模組載入（本模組不碰）
    3. 指定 embedding model    →  query 時用相同 model encode 問題

**windMindOM 只負責「載入 + 查詢」，不重新 embed。** 本模組是這條契約的入口：
把 RAG_Ultimate 交付的 ``strategy.yaml`` 解析成型別安全、已驗證的 :class:`RagStrategy`，
供 ingest.py / retrieve.py / alert_handler.py 共用，確保「embed 與 query 用同一組參數」。

設計原則：
- **嚴格 schema**（``extra="forbid"``）— 策略檔是部署契約，key 打錯要在啟動時就炸，
  而不是 retrieve 拿到怪結果才發現。新增欄位 = 本 loader 版本升級（刻意為之）。
- **清楚的例外階層** — 檔案不存在 / YAML 壞掉 / schema 不合，各自獨立例外，
  讓上層（service 啟動、settings 切換）能精準回報給劉老師 / 運維廠商。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# ─────────────────────────────────────────────────────────────────────────
# 例外階層
# ─────────────────────────────────────────────────────────────────────────


class StrategyLoadError(Exception):
    """載入 RAG 策略檔時的所有錯誤基底。

    上層只想「載入失敗」一把抓時 catch 這個；想分流處理時 catch 下面三個子類。
    """


class StrategyFileNotFoundError(StrategyLoadError):
    """指定的策略檔路徑不存在或不是檔案。"""


class StrategyParseError(StrategyLoadError):
    """策略檔 YAML 語法錯誤，或頂層不是 mapping（dict）。"""


class StrategyValidationError(StrategyLoadError):
    """策略檔語法正確但內容不符 schema（缺欄位 / 型別錯 / 違反約束）。"""


# ─────────────────────────────────────────────────────────────────────────
# 策略 schema（pydantic v2）
# ─────────────────────────────────────────────────────────────────────────

_STRICT = ConfigDict(extra="forbid")
"""所有子 model 共用：禁止未知 key，把策略檔 typo 在啟動時就擋下。"""


class ChunkingStrategy(BaseModel):
    """切塊策略 — RAG_Ultimate 怎麼把手冊切成 chunk，windMindOM 灌自有 SOP 時要用同一組。"""

    model_config = _STRICT

    method: Literal["semantic", "fixed", "recursive"] = Field(
        description="切塊方法。semantic=語意邊界切；fixed=固定長度；recursive=遞迴分隔符"
    )
    size: int = Field(gt=0, description="目標 chunk 大小（token 數），須 > 0")
    overlap: int = Field(default=0, ge=0, description="相鄰 chunk 重疊 token 數，須 >= 0 且 < size")

    @model_validator(mode="after")
    def _overlap_smaller_than_size(self) -> "ChunkingStrategy":
        """重疊量必須小於 chunk 大小，否則切塊會原地打轉。"""
        if self.overlap >= self.size:
            raise ValueError(
                f"chunking.overlap ({self.overlap}) 必須小於 chunking.size ({self.size})"
            )
        return self


class EmbeddingStrategy(BaseModel):
    """嵌入策略 — query 端必須用「與灌庫時完全相同」的 model + dimension，否則向量空間對不上。"""

    model_config = _STRICT

    model: str = Field(min_length=1, description="embedding model 名稱，例：BAAI/bge-large-zh-v1.5")
    dimension: int = Field(gt=0, description="向量維度，須 > 0，且須與 model 實際輸出一致")


class RetrievalStrategy(BaseModel):
    """檢索策略 — 警報 query 時 retrieve top-k 的演算法與參數，可在客戶端微調後重啟生效。"""

    model_config = _STRICT

    algorithm: Literal["vector", "bm25", "hybrid_bm25_vector"] = Field(
        description="檢索演算法。vector=純向量；bm25=純關鍵字；hybrid_bm25_vector=混合"
    )
    top_k: int = Field(gt=0, description="回傳前 k 個 chunk，須 >= 1")
    rerank: bool = Field(default=False, description="是否做二階段 rerank")
    rerank_model: str | None = Field(
        default=None, description="rerank model 名稱；rerank=True 時必填"
    )

    @model_validator(mode="after")
    def _rerank_needs_model(self) -> "RetrievalStrategy":
        """開了 rerank 卻沒給 rerank_model 是無效設定，提早擋下。"""
        if self.rerank and not self.rerank_model:
            raise ValueError("retrieval.rerank=True 時必須提供 retrieval.rerank_model")
        return self


class StrategyMeta(BaseModel):
    """策略檔的描述性 metadata（可選）。

    讓 windMindOM 前端 / settings 能顯示「現在載入的是哪份策略、對應哪個 OEM 機型、
    版本與向量檔」，也方便升級時比對。RAG_Ultimate 交付時建議帶上，但非必填以保留彈性。
    """

    model_config = _STRICT

    name: str | None = Field(default=None, description="策略檔人類可讀名稱")
    version: str | None = Field(default=None, description="策略版本，例：2026-05")
    oem_model: str | None = Field(default=None, description="對應 OEM 機型，例：Z72")
    vector_store_file: str | None = Field(
        default=None, description="對應的預計算向量檔名，例：z72_manual_v2026-05.parquet"
    )
    source: str | None = Field(default=None, description="產出來源，例：RAG_Ultimate Phase 3")


class RagStrategy(BaseModel):
    """完整 RAG 策略 — chunking / embedding / retrieval 三段必填，meta 可選。

    這是 ingest / retrieve / alert_handler 共用的單一真實來源，確保灌庫與查詢一致。
    """

    model_config = _STRICT

    chunking: ChunkingStrategy
    embedding: EmbeddingStrategy
    retrieval: RetrievalStrategy
    meta: StrategyMeta | None = Field(default=None, description="可選的描述性 metadata")

    @classmethod
    def from_dict(cls, data: object) -> "RagStrategy":
        """從已解析的 dict 建立並驗證策略。

        Args:
            data: 已從 YAML/JSON 解析出的物件，必須是 mapping。

        Returns:
            驗證通過的 :class:`RagStrategy`。

        Raises:
            StrategyParseError: ``data`` 不是 mapping（dict）。
            StrategyValidationError: 內容不符 schema。
        """
        if not isinstance(data, dict):
            raise StrategyParseError(
                f"策略內容頂層必須是 mapping（dict），實際得到 {type(data).__name__}"
            )
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            # 包成自家例外，對上層隱藏 pydantic 細節但保留可讀訊息
            raise StrategyValidationError(f"策略檔內容不符 schema：\n{exc}") from exc

    @classmethod
    def from_yaml_str(cls, text: str) -> "RagStrategy":
        """從 YAML 字串解析並驗證策略。

        Args:
            text: YAML 內容字串。

        Returns:
            驗證通過的 :class:`RagStrategy`。

        Raises:
            StrategyParseError: YAML 語法錯誤或頂層非 mapping。
            StrategyValidationError: 內容不符 schema。
        """
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise StrategyParseError(f"策略檔 YAML 語法錯誤：{exc}") from exc
        if data is None:
            raise StrategyParseError("策略檔為空（YAML 解析結果為 None）")
        return cls.from_dict(data)


# ─────────────────────────────────────────────────────────────────────────
# 載入入口
# ─────────────────────────────────────────────────────────────────────────


def load_strategy(path: str | Path) -> RagStrategy:
    """從檔案路徑載入並驗證 RAG 策略檔。

    這是 service 啟動 / settings 切換時的主入口。

    Args:
        path: 策略 YAML 檔路徑（str 或 Path）。

    Returns:
        驗證通過的 :class:`RagStrategy`。

    Raises:
        StrategyFileNotFoundError: 路徑不存在或不是檔案。
        StrategyParseError: YAML 語法錯誤或頂層非 mapping。
        StrategyValidationError: 內容不符 schema。
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise StrategyFileNotFoundError(f"找不到策略檔：{file_path}")
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:  # 權限 / IO 等讀檔失敗
        raise StrategyLoadError(f"讀取策略檔失敗（{file_path}）：{exc}") from exc
    return RagStrategy.from_yaml_str(text)
