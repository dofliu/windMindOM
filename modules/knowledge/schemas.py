"""Knowledge / RAG module 的 pydantic v2 schema（M5-1）。

對應 [`docs/product/MVP_ARCHITECTURE.md`](../../docs/product/MVP_ARCHITECTURE.md) §3.5。

設計邊界（WMOM-20260601-01）：
- 純 pydantic 形狀 + enum；不接 ChromaDB / SQLAlchemy / FastAPI（那些在 M5-2 / M5-6）。
- 「RAG_Ultimate 提供策略檔 + 預計算向量檔，windMindOM 只載入 + query」：
  ``RagStrategy`` 描述策略檔結構；``KnowledgeChunk.embedding_vector_id`` 是
  ChromaDB 向量參照，baseline（純 simulator）模式下為 ``None``。
- ``AlertEvent`` 的告警碼語意對齊
  ``modules/monitoring/simulator/physics/fault_engine.py`` 的 Bachmann 告警碼。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# 告警等級：A=警示（alarm/warning）、T1=一級跳機、T2=二級跳機。
# 對齊 fault_engine.FaultScenario.alarm_codes 的 ``type`` 欄位。
AlarmLevel = Literal["A", "T1", "T2"]


# ─────────────────────────────────────────────────────────────────────────
# RAG 策略檔（由 RAG_Ultimate 提供；本 module 只讀）
# ─────────────────────────────────────────────────────────────────────────


class RagChunkingStrategy(BaseModel):
    """切塊策略（chunking）。對齊 MVP_ARCHITECTURE §3.5 yaml 範例。"""

    method: str = Field(default="semantic", description="切塊方法，例：semantic / fixed")
    size: int = Field(default=512, gt=0, description="每塊目標 token 數")
    overlap: int = Field(default=50, ge=0, description="相鄰塊重疊 token 數")


class RagEmbeddingStrategy(BaseModel):
    """嵌入策略（embedding）。query 端需用相同 model encode 問題。"""

    model: str = Field(default="BAAI/bge-large-zh-v1.5", description="嵌入模型名")
    dimension: int = Field(default=1024, gt=0, description="向量維度")


class RagRetrievalStrategy(BaseModel):
    """檢索策略（retrieval）。"""

    algorithm: str = Field(
        default="hybrid_bm25_vector", description="檢索演算法，例：hybrid_bm25_vector / vector"
    )
    top_k: int = Field(default=5, gt=0, description="回傳前 k 筆")
    rerank: bool = Field(default=True, description="是否做重排序")
    rerank_model: str | None = Field(default=None, description="重排序模型名（可選）")


class RagStrategy(BaseModel):
    """完整 RAG 策略檔。

    頂層的 ``name`` / ``oem`` / ``model`` 為 windMindOM 加的中繼資料，
    讓平台能依機型載入對應策略；缺失時用 default。
    """

    name: str = Field(default="baseline", description="策略檔識別名")
    oem: str = Field(default="Bachmann", description="適用控制系統 / OEM")
    model: str = Field(default="Z72", description="適用風機機型")
    chunking: RagChunkingStrategy = Field(default_factory=RagChunkingStrategy)
    embedding: RagEmbeddingStrategy = Field(default_factory=RagEmbeddingStrategy)
    retrieval: RagRetrievalStrategy = Field(default_factory=RagRetrievalStrategy)


# ─────────────────────────────────────────────────────────────────────────
# 知識庫塊 + 檢索 I/O
# ─────────────────────────────────────────────────────────────────────────


class KnowledgeChunk(BaseModel):
    """知識庫的一塊（手冊段落 / SOP）。

    對齊 MVP_ARCHITECTURE §6 ``KnowledgeChunk`` 資料模型。baseline 模式下
    chunk 直接從 JSON 載入（無向量）；M5-2 後 ``embedding_vector_id`` 指向
    ChromaDB 內的向量。
    """

    id: str = Field(description="塊唯一 ID")
    document_source: str = Field(description="來源文件，例：Z72UserManual.pdf")
    section: str | None = Field(default=None, description="章節，例：§4.3 變頻器冷卻")
    page: int | None = Field(default=None, description="頁碼")
    chunk_text: str = Field(description="段落正文")
    oem: str = Field(default="Bachmann", description="適用控制系統 / OEM")
    model: str = Field(default="Z72", description="適用風機機型")
    alarm_codes: list[int] = Field(
        default_factory=list, description="此塊對應的 Bachmann 告警碼（給警報→RAG 命中用）"
    )
    keywords: list[str] = Field(
        default_factory=list, description="關鍵字（baseline keyword retriever 用）"
    )
    embedding_vector_id: str | None = Field(
        default=None, description="ChromaDB 向量參照；baseline 模式為 None"
    )


class RetrievalQuery(BaseModel):
    """一次檢索請求。"""

    text: str = Field(description="查詢文字（問題 / 警報描述）")
    oem: str | None = Field(default=None, description="限定 OEM；None 表示不限")
    model: str | None = Field(default=None, description="限定機型；None 表示不限")
    alarm_codes: list[int] = Field(
        default_factory=list, description="加權命中的告警碼（警報→RAG 時帶入）"
    )
    top_k: int | None = Field(
        default=None, gt=0, description="覆寫策略 top_k；None 表示用策略值"
    )


class RetrievedChunk(BaseModel):
    """檢索結果單筆（chunk + 相關度 + 可解釋原因）。"""

    chunk: KnowledgeChunk
    score: float = Field(ge=0.0, le=1.0, description="相關度，0..1")
    match_reason: str = Field(description="繁中可解釋命中原因（前端透明度用）")


# ─────────────────────────────────────────────────────────────────────────
# 警報事件 → RAG
# ─────────────────────────────────────────────────────────────────────────


class AlertEvent(BaseModel):
    """SCADA 監控觸發的警報事件（送進 AlertHandler）。

    語意對齊 ``fault_engine.FaultScenario`` —— ``scenario_id`` 可回連
    ``FAULT_SCENARIOS`` 的 key，``abnormal_tags`` 對齊 ``affected_tags``。
    """

    alarm_code: int = Field(description="Bachmann 告警碼，例：21（變頻器跳機）")
    alarm_level: AlarmLevel = Field(default="A", description="告警等級 A / T1 / T2")
    turbine_id: str = Field(description="風機 ID")
    oem: str = Field(default="Bachmann", description="控制系統 / OEM")
    model: str = Field(default="Z72", description="風機機型")
    scenario_id: str | None = Field(
        default=None, description="對應 fault_engine FAULT_SCENARIOS key（可選）"
    )
    abnormal_tags: list[str] = Field(
        default_factory=list, description="異常 SCADA tag（例：WCNV_IGCTWtrTmp）"
    )
    description: str | None = Field(default=None, description="人類可讀警報描述")
    severity: float | None = Field(
        default=None, ge=0.0, le=1.0, description="嚴重度 0..1（可選）"
    )
    timestamp: datetime | None = Field(
        default=None, description="警報發生時間（UTC，須為 timezone-aware datetime）"
    )

    @field_validator("timestamp")
    @classmethod
    def _require_tz_aware(cls, v: datetime | None) -> datetime | None:
        """強制 timestamp 為 timezone-aware（CLAUDE.md §B：SCADA 事件一律 UTC）。

        baseline 階段先埋好防線 —— naive datetime 在串 SCADA 資料流後會
        靜默產生時區錯誤，比之後 debug 省力。
        """
        if v is not None and v.tzinfo is None:
            raise ValueError(
                "AlertEvent.timestamp 須為 timezone-aware datetime（UTC），收到 naive datetime"
            )
        return v


class AlertRagResult(BaseModel):
    """AlertHandler 回傳給 ``/field/alerts/{id}`` 的完整結果。"""

    alert: AlertEvent
    query: RetrievalQuery
    chunks: list[RetrievedChunk] = Field(
        default_factory=list, description="檢索到的手冊處置段落（依相關度排序）"
    )
    strategy_name: str = Field(description="使用的策略檔名")
    retriever: str = Field(description="使用的 retriever，例：baseline_keyword")
    is_baseline: bool = Field(
        default=True, description="True 表示 placeholder 檢索（非真向量），前端可標示"
    )


class KnowledgeStatus(BaseModel):
    """knowledge module 檢索層狀態（給前端顯示 baseline badge 用）。

    純 pydantic shape，與 FastAPI 無關（與本 module 其餘 schema 同層）；
    由 ``/api/knowledge/status`` 回傳。
    """

    retriever: str = Field(description="目前 retriever 名，例：baseline_keyword")
    is_baseline: bool = Field(
        description="True 表示 placeholder 檢索（非真向量），前端可標示「baseline 模式」"
    )
    strategy_name: str = Field(description="目前 RAG 策略檔名")
