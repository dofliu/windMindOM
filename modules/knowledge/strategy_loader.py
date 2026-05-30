"""RAG 策略檔載入器（knowledge module / M5-1 第一塊）。

核心模型（見 `docs/product/MVP_ARCHITECTURE.md` §3.5）：
    RAG_Ultimate（research）負責產出「策略檔 + 預計算向量檔」，
    windMindOM（產品）只負責**載入策略 + 用相同 embedding model query**，
    不在客戶端重新 chunk / embed。

本檔是 knowledge module 的最底層 contract：把 RAG_Ultimate 交付的
``config/rag_strategy_*.yaml`` 解析成 typed、validated、immutable 的
``RagStrategy``，供後續 ``ingest.py`` / ``retrieve.py`` / ``alert_handler.py``
共用。刻意**不依賴 ChromaDB / sentence-transformers**——只做純解析與驗證，
方便在無 GPU、無向量檔的 sandbox 下完整單元測試。

實作邊界（M5-1 Part 1）：
- 純 Python dataclass + PyYAML；不接 ChromaDB / FastAPI / SQLAlchemy
- 向量檔載入（``z72_manual_v*.parquet`` → ChromaDB）屬 M5-2，不在此檔
- query encode（embedding model 推論）屬 retrieve.py，不在此檔

placeholder 策略（DEC / MVP_ARCHITECTURE 風險表）：
    「RAG_Ultimate Phase 3 strategy 還沒 ready 就要交 artifact」→
    先用 baseline strategy（小參數小模型）做 placeholder，等 Phase 3 出來再升級。
    ``baseline_strategy()`` + ``load_strategy_or_baseline()`` 即為此而設。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# strategy 檔最外層三個必備區塊（缺一即視為非法策略檔）
_REQUIRED_SECTIONS: tuple[str, ...] = ("chunking", "embedding", "retrieval")

# 策略檔大小上限：策略檔理應僅幾 KB（chunking / embedding / retrieval 數十行）。
# M5 開放 /admin/settings 切換策略後，路徑可能由前端傳入 → 加上限避免誤指巨大檔案
# 一次讀進記憶體撐爆 worker（防禦性，非真正 untrusted input）。
_MAX_STRATEGY_FILE_BYTES = 65_536  # 64 KB


class StrategyError(ValueError):
    """策略檔解析 / 驗證失敗。

    繼承 ``ValueError`` 讓呼叫端可用既有 except 補捉；訊息一律繁中描述
    哪個欄位出錯，方便 RAG_Ultimate 對接時快速定位 yaml 問題。
    """


# ─────────────────────────────────────────────────────────────────────────
# Typed strategy dataclasses（frozen → 載入後不可變，避免 runtime 被改參數）
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChunkingStrategy:
    """切塊策略。

    Attributes:
        method: 切塊方法（如 ``semantic`` / ``fixed`` / ``recursive``）。
            不限制集合，交給 RAG_Ultimate 定義；只要求非空字串。
        size: 每塊目標 token / 字元數，必須 > 0。
        overlap: 相鄰塊重疊量，必須 >= 0 且 < ``size``（重疊不可吃掉整塊）。
    """

    method: str
    size: int
    overlap: int


@dataclass(frozen=True)
class EmbeddingStrategy:
    """嵌入模型策略。

    Attributes:
        model: embedding model 名稱（query 端必須用**相同** model encode，
            否則向量空間不一致——這是「客戶端只 query 不重 embed」的關鍵約束）。
        dimension: 向量維度，必須 > 0；需與預計算向量檔一致。
    """

    model: str
    dimension: int


@dataclass(frozen=True)
class RetrievalStrategy:
    """檢索策略。

    Attributes:
        algorithm: 檢索演算法（如 ``hybrid_bm25_vector`` / ``vector``）。
        top_k: 回傳前 k 個 chunk，必須 > 0。
        rerank: 是否啟用重排序。
        rerank_model: 重排序模型名稱；``rerank=True`` 時必填，否則可為 None。
    """

    algorithm: str
    top_k: int
    rerank: bool
    rerank_model: str | None


@dataclass(frozen=True)
class RagStrategy:
    """完整 RAG 策略（對應一份 ``rag_strategy_*.yaml``）。

    Attributes:
        chunking: 切塊策略。
        embedding: 嵌入模型策略。
        retrieval: 檢索策略。
        name: 策略識別名（選填，便於 log / UI 顯示與切換）。
        version: 策略版本（選填，對應 RAG_Ultimate Phase 版號）。
        source_path: 載入來源檔路徑；``baseline_strategy()`` 產生者為 None。
    """

    chunking: ChunkingStrategy
    embedding: EmbeddingStrategy
    retrieval: RetrievalStrategy
    name: str | None = None
    version: str | None = None
    source_path: str | None = None


# ─────────────────────────────────────────────────────────────────────────
# 型別收窄 helper（PyYAML safe_load 回傳 Any；在此一律收窄到精確型別）
# ─────────────────────────────────────────────────────────────────────────


def _require_mapping(value: object, where: str) -> dict[str, object]:
    """確保 ``value`` 是 dict（yaml mapping），否則拋 StrategyError。"""
    if not isinstance(value, dict):
        raise StrategyError(f"{where} 必須是 mapping（dict），實得 {type(value).__name__}")
    # yaml mapping 的 key 理論上可為非 str；策略檔約定一律 str key
    return {str(k): v for k, v in value.items()}


def _require_str(section: dict[str, object], key: str, where: str) -> str:
    """取出非空字串欄位。"""
    if key not in section:
        raise StrategyError(f"{where} 缺少必填欄位 '{key}'")
    value = section[key]
    if not isinstance(value, str) or not value.strip():
        raise StrategyError(f"{where}.{key} 必須是非空字串，實得 {value!r}")
    return value


def _require_int(section: dict[str, object], key: str, where: str) -> int:
    """取出整數欄位（拒絕 bool——Python 中 bool 是 int 子類，易誤判）。"""
    if key not in section:
        raise StrategyError(f"{where} 缺少必填欄位 '{key}'")
    value = section[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise StrategyError(f"{where}.{key} 必須是整數，實得 {value!r}")
    return value


def _require_bool(section: dict[str, object], key: str, where: str) -> bool:
    """取出布林欄位。"""
    if key not in section:
        raise StrategyError(f"{where} 缺少必填欄位 '{key}'")
    value = section[key]
    if not isinstance(value, bool):
        raise StrategyError(f"{where}.{key} 必須是布林值，實得 {value!r}")
    return value


def _optional_str(section: dict[str, object], key: str, where: str) -> str | None:
    """取出選填字串欄位；不存在或為 None 時回 None，存在則須為非空字串。

    用於語意敏感欄位（如 ``rerank_model``）——這類欄位是模型名稱，型別必須嚴格，
    數字 / 布林一律視為錯誤。純 metadata 欄位請改用 ``_optional_meta_str``。
    """
    if key not in section or section[key] is None:
        return None
    value = section[key]
    if not isinstance(value, str) or not value.strip():
        raise StrategyError(f"{where}.{key} 若提供則必須是非空字串，實得 {value!r}")
    return value


def _optional_meta_str(section: dict[str, object], key: str, where: str) -> str | None:
    """取出選填 metadata 字串欄位（如 ``name`` / ``version``），對 scalar 寬鬆。

    RAG_Ultimate 交付的策略檔常把 ``version: 2026`` / ``version: 3.0`` 寫成未加引號
    的數字，PyYAML 會解成 int / float。這些欄位純 informational（不參與檢索邏輯），
    為避免「一份其實合法的策略檔因 version 沒加引號就靜默退回 baseline」，此處對
    int / float scalar 寬鬆 coerce 成字串並 log warning 提醒 schema drift；
    對 list / dict 等容器型別仍視為錯誤。

    Args:
        section: 所在區塊 mapping。
        key: 欄位名。
        where: 錯誤訊息用的位置描述。

    Returns:
        欄位字串值；不存在 / None / 空字串一律回 None。
    """
    if key not in section or section[key] is None:
        return None
    value = section[key]
    if isinstance(value, str):
        return value if value.strip() else None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        coerced = str(value)
        logger.warning(
            "%s.%s 應為字串，實得 %r；已 coerce 成 %r（建議在 yaml 中加引號）",
            where,
            key,
            value,
            coerced,
        )
        return coerced
    raise StrategyError(f"{where}.{key} 若提供則必須是字串或數字，實得 {value!r}")


# ─────────────────────────────────────────────────────────────────────────
# 解析 + 驗證
# ─────────────────────────────────────────────────────────────────────────


def _parse_chunking(raw: object) -> ChunkingStrategy:
    section = _require_mapping(raw, "chunking")
    method = _require_str(section, "method", "chunking")
    size = _require_int(section, "size", "chunking")
    overlap = _require_int(section, "overlap", "chunking")
    if size <= 0:
        raise StrategyError(f"chunking.size 必須 > 0，實得 {size}")
    if overlap < 0:
        raise StrategyError(f"chunking.overlap 必須 >= 0，實得 {overlap}")
    if overlap >= size:
        raise StrategyError(f"chunking.overlap（{overlap}）必須小於 size（{size}），否則重疊吃掉整塊")
    return ChunkingStrategy(method=method, size=size, overlap=overlap)


def _parse_embedding(raw: object) -> EmbeddingStrategy:
    section = _require_mapping(raw, "embedding")
    model = _require_str(section, "model", "embedding")
    dimension = _require_int(section, "dimension", "embedding")
    if dimension <= 0:
        raise StrategyError(f"embedding.dimension 必須 > 0，實得 {dimension}")
    return EmbeddingStrategy(model=model, dimension=dimension)


def _parse_retrieval(raw: object) -> RetrievalStrategy:
    section = _require_mapping(raw, "retrieval")
    algorithm = _require_str(section, "algorithm", "retrieval")
    top_k = _require_int(section, "top_k", "retrieval")
    rerank = _require_bool(section, "rerank", "retrieval")
    if top_k <= 0:
        raise StrategyError(f"retrieval.top_k 必須 > 0，實得 {top_k}")
    rerank_model = _optional_str(section, "rerank_model", "retrieval")
    if rerank and rerank_model is None:
        raise StrategyError("retrieval.rerank=true 時必須提供 retrieval.rerank_model")
    if not rerank and rerank_model is not None:
        # rerank 關閉卻帶 rerank_model 是矛盾狀態，下游 retrieve.py 會混淆 → 丟棄 + 警示
        logger.warning(
            "retrieval.rerank=false 但提供了 rerank_model=%r，已忽略該欄位",
            rerank_model,
        )
        rerank_model = None
    return RetrievalStrategy(
        algorithm=algorithm,
        top_k=top_k,
        rerank=rerank,
        rerank_model=rerank_model,
    )


def parse_strategy(raw: object, *, source_path: str | None = None) -> RagStrategy:
    """把已解析的 yaml 物件（dict）驗證並轉成 ``RagStrategy``。

    與 ``load_strategy`` 分離，方便測試直接餵 dict、也供其他來源（如 DB）重用。

    Args:
        raw: yaml ``safe_load`` 的結果，應為最外層 mapping。
        source_path: 記錄到 ``RagStrategy.source_path`` 的來源檔路徑。

    Returns:
        驗證通過的不可變 ``RagStrategy``。

    Raises:
        StrategyError: 結構缺漏、型別錯誤或數值違反約束。
    """
    root = _require_mapping(raw, "策略檔最外層")
    missing = [s for s in _REQUIRED_SECTIONS if s not in root]
    if missing:
        raise StrategyError(f"策略檔缺少必備區塊：{', '.join(missing)}")
    return RagStrategy(
        chunking=_parse_chunking(root["chunking"]),
        embedding=_parse_embedding(root["embedding"]),
        retrieval=_parse_retrieval(root["retrieval"]),
        name=_optional_meta_str(root, "name", "策略檔"),
        version=_optional_meta_str(root, "version", "策略檔"),
        source_path=source_path,
    )


def load_strategy(path: str | Path) -> RagStrategy:
    """從 yaml 檔載入並驗證 RAG 策略。

    Args:
        path: 策略檔路徑（如 ``config/rag_strategy_z72_manual.yaml``）。

    Returns:
        驗證通過的 ``RagStrategy``，``source_path`` 設為傳入路徑。

    Raises:
        StrategyError: 檔案不存在、非合法 yaml、或內容驗證失敗。
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise StrategyError(f"策略檔不存在：{file_path}")
    try:
        size = file_path.stat().st_size
    except OSError as exc:
        raise StrategyError(f"策略檔無法存取：{file_path}（{exc}）") from exc
    if size > _MAX_STRATEGY_FILE_BYTES:
        raise StrategyError(
            f"策略檔過大（{size} bytes > {_MAX_STRATEGY_FILE_BYTES} 上限），拒絕載入：{file_path}"
        )
    # OS / 編碼層例外（權限不足、磁碟故障、非 UTF-8）統一轉成 StrategyError，
    # 才能兌現 docstring「Raises: StrategyError」契約、並讓 load_strategy_or_baseline
    # 的「永遠有 baseline 可開機」保證在磁碟異常時仍成立。
    try:
        text = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise StrategyError(f"策略檔讀取失敗：{file_path}（{exc}）") from exc
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise StrategyError(f"策略檔不是合法 yaml：{file_path}（{exc}）") from exc
    if raw is None:
        raise StrategyError(f"策略檔為空：{file_path}")
    return parse_strategy(raw, source_path=str(file_path))


def baseline_strategy() -> RagStrategy:
    """回傳 placeholder baseline 策略（RAG_Ultimate Phase 3 未 ready 時的退路）。

    刻意選**小、CPU 友善、多語**的設定，讓 sandbox / 客戶端在沒有正式向量檔時
    仍能跑通整條 pipeline（雖然檢索品質僅 baseline）。Phase 3 策略檔就位後，
    改用 ``load_strategy()`` 即可無痛升級。

    Returns:
        固定的 baseline ``RagStrategy``（``source_path`` 為 None 表示非檔案來源）。
    """
    return RagStrategy(
        chunking=ChunkingStrategy(method="fixed", size=512, overlap=50),
        embedding=EmbeddingStrategy(
            model="paraphrase-multilingual-MiniLM-L12-v2",
            dimension=384,
        ),
        retrieval=RetrievalStrategy(
            algorithm="vector",
            top_k=5,
            rerank=False,
            rerank_model=None,
        ),
        name="baseline-placeholder",
        version="0.0.0",
        source_path=None,
    )


def load_strategy_or_baseline(path: str | Path) -> RagStrategy:
    """嘗試載入策略檔；任何失敗則 log warning 後退回 ``baseline_strategy()``。

    給「artifact 可能還沒交付」的 M5 早期階段用——確保 knowledge module 永遠
    有一份可用策略可開機，不會因缺檔/壞檔讓整個服務起不來。

    Args:
        path: 策略檔路徑。

    Returns:
        成功則為檔案策略，否則為 baseline placeholder。
    """
    try:
        return load_strategy(path)
    except StrategyError as exc:
        logger.warning("載入策略檔失敗（%s），退回 baseline placeholder：%s", path, exc)
        return baseline_strategy()
