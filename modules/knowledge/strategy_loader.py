"""RAG 策略載入器（WMOM-20260601-01）。

呼應 ROADMAP M5-3：『RAG_Ultimate strategy 對接 —— 拿 Phase 3 的
``strategy.yaml`` + ``z72_manual.parquet``；未 ready 用 baseline placeholder』。

本模組負責把研究端產出的策略檔（描述用哪種切塊 / embedding / 檢索參數 /
語料路徑）載入成型別化的 ``RagStrategy``。windMindOM **不重新 embed**，只依
策略檔載入既有語料並查詢。

未提供策略檔時，回退到內建 baseline placeholder（``default_strategy()``），
確保純 simulator 模式下也能跑通 demo。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

_logger = logging.getLogger(__name__)

# baseline 語料相對於本模組的位置
_BASELINE_DIR = Path(__file__).resolve().parent / "data" / "baseline"
BASELINE_STRATEGY_PATH = _BASELINE_DIR / "strategy.yaml"


class EmbeddingConfig(BaseModel):
    """Embedding / 向量化設定（baseline 不實際 embed）。"""

    model_config = ConfigDict(from_attributes=True)

    provider: str = Field(default="baseline-lexical", description="正式版可為 sentence-transformers 等")
    model: str = Field(default="none", description="模型名稱，baseline 為 none")


class RetrievalConfig(BaseModel):
    """檢索參數。"""

    model_config = ConfigDict(from_attributes=True)

    top_k: int = Field(default=3, ge=0, description="預設回傳前 k 筆")
    min_score: float = Field(default=0.0, description="低於此分數的候選不回傳")


class CorpusConfig(BaseModel):
    """語料來源設定。"""

    model_config = ConfigDict(from_attributes=True)

    source: str = Field(description="語料檔路徑（相對策略檔所在目錄或絕對路徑）")
    format: Literal["jsonl"] = Field(
        default="jsonl", description="目前 baseline 僅支援 jsonl（擴充 parquet 時加入 Literal）"
    )


class RagStrategy(BaseModel):
    """一份完整 RAG 策略 —— 載入語料 + 檢索的單一事實來源。"""

    model_config = ConfigDict(from_attributes=True)

    version: str = Field(description="策略版本，如 baseline-0.1 / z72-phase3-1.0")
    oem_model: str = Field(default="Z72", description="此策略適用機型")
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    corpus: CorpusConfig = Field(description="語料來源")

    def resolve_corpus_path(self, base_dir: Path) -> Path:
        """把 corpus.source 解析成絕對路徑。

        相對路徑以 ``base_dir``（策略檔所在目錄）為基準；絕對路徑原樣回傳。
        """
        source = Path(self.corpus.source)
        if source.is_absolute():
            return source
        return (base_dir / source).resolve()


def default_strategy() -> RagStrategy:
    """內建 baseline placeholder 策略（不讀檔，永遠可用）。

    指向 baseline Z72 手冊語料，供 RAG_Ultimate Phase 3 策略尚未 ready 時
    跑通整條 pipeline。
    """
    return RagStrategy(
        version="baseline-0.1",
        oem_model="Z72",
        embedding=EmbeddingConfig(provider="baseline-lexical", model="none"),
        retrieval=RetrievalConfig(top_k=3, min_score=0.0),
        corpus=CorpusConfig(source="z72_manual_baseline.jsonl", format="jsonl"),
    )


def load_strategy(path: Path) -> RagStrategy:
    """從 YAML 檔載入並驗證一份策略。

    Args:
        path: 策略 YAML 檔路徑。

    Returns:
        驗證過的 ``RagStrategy``。

    Raises:
        FileNotFoundError: 檔案不存在。
        ValueError: YAML 解析失敗或欄位不符 schema。
    """
    if not path.exists():
        raise FileNotFoundError(f"策略檔不存在：{path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - 防禦性
        raise ValueError(f"策略 YAML 解析失敗：{path}（{exc}）") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"策略檔內容須為 mapping，實得 {type(raw).__name__}：{path}")
    try:
        return RagStrategy.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"策略檔欄位不符 schema：{path}（{exc}）") from exc


def load_strategy_or_baseline(path: Path | None = None) -> RagStrategy:
    """載入策略，失敗 / 未提供時回退 baseline。

    供 autonomous / demo 路徑使用：``path`` 為 ``None`` 或檔案不存在時，
    回傳 ``default_strategy()`` 並記 warning，而非中斷流程。欄位 schema
    錯誤仍會往上拋（屬於策略檔本身的 bug，應顯性失敗）。

    Args:
        path: 策略 YAML 檔路徑；``None`` 表示直接用 baseline。

    Returns:
        ``RagStrategy``（正式策略或 baseline placeholder）。
    """
    if path is None:
        return default_strategy()
    if not path.exists():
        _logger.warning("策略檔不存在，回退 baseline：%s", path)
        return default_strategy()
    return load_strategy(path)
