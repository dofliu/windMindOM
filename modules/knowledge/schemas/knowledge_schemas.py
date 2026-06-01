"""Knowledge / RAG baseline 的 Pydantic schemas（WMOM-20260601-01）。

設計原則（呼應 CLAUDE.md §15）：
- **Simulator-first**：所有 model 不依賴 ChromaDB / embedding，純資料即可建構，
  讓 baseline 檢索能在無實場、無向量服務的情況下 demo。
- **平台只載入 + query**：``ManualChunk`` 假設手冊切塊與關鍵詞抽取已由研究端
  （RAG_Ultimate）完成，windMindOM 只負責載入與比對。

5 個 model：
- ``ManualChunk`` — 手冊切塊（語料的最小單位）
- ``RetrievedChunk`` — 一筆檢索命中（chunk + 分數 + 命中詞）
- ``AlertContext`` — 一筆警報事件（monitoring 告警 → 知識查詢的輸入）
- ``KnowledgeQuery`` — 一次檢索請求
- ``KnowledgeResponse`` — 一次檢索回應（top-k chunks + metadata）
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────────
# 語料：手冊切塊
# ─────────────────────────────────────────────────────────────────────────


class ManualChunk(BaseModel):
    """手冊切塊 —— baseline 語料的最小單位。

    對應研究端 ingest pipeline 產出的一行 jsonl。``keywords`` 與
    ``fault_codes`` 是預先抽取的結構化欄位，baseline lexical 檢索倚賴它們
    做高精準度比對（不重新 embed）。
    """

    model_config = ConfigDict(from_attributes=True)

    chunk_id: str = Field(description="全語料唯一 id，如 z72-bearing_wear-01")
    source: str = Field(description="來源文件，如 __Z72UserManual.pdf")
    section: str = Field(default="", description="章節 / 標題，給前端顯示用")
    page: Optional[int] = Field(default=None, description="原始頁碼（可選）")
    text: str = Field(description="切塊全文（現場工程師實際讀到的內容）")
    keywords: list[str] = Field(
        default_factory=list,
        description="預抽取關鍵詞，baseline 檢索高權重比對來源",
    )
    fault_codes: list[str] = Field(
        default_factory=list,
        description="對應的警報碼（如 A-262 / T1-21），供警報精準對齊",
    )
    oem_model: str = Field(default="Z72", description="適用機型，多 OEM 時用來分流語料")


# ─────────────────────────────────────────────────────────────────────────
# 檢索結果
# ─────────────────────────────────────────────────────────────────────────


class RetrievedChunk(BaseModel):
    """一筆檢索命中：chunk 本身 + 相關性分數 + 命中的查詢詞。"""

    model_config = ConfigDict(from_attributes=True)

    chunk: ManualChunk
    score: float = Field(description="baseline lexical 相關性分數（越高越相關）")
    matched_terms: list[str] = Field(
        default_factory=list,
        description="此 chunk 命中的查詢詞（debug / 高亮用），已排序",
    )


# ─────────────────────────────────────────────────────────────────────────
# 警報情境（monitoring → knowledge 的輸入）
# ─────────────────────────────────────────────────────────────────────────


class AlertContext(BaseModel):
    """一筆警報事件 —— alert_handler 的輸入。

    欄位刻意對齊 monitoring 的 fault scenario / alarm_codes 結構，讓 M5-6
    告警 → RAG 自動查詢能直接餵入。
    """

    model_config = ConfigDict(from_attributes=True)

    alert_code: str = Field(description="警報碼，如 A-262 / T1-21 / 262")
    severity: str = Field(default="warning", description="info / warning / alarm / critical")
    message: str = Field(default="", description="警報文字（中英皆可）")
    turbine_id: Optional[str] = Field(default=None, description="風機 id，如 WT003")
    subsystem: Optional[str] = Field(default=None, description="子系統，如 generator / pitch / yaw")
    oem_model: str = Field(default="Z72", description="機型，決定載入哪份語料")
    timestamp: Optional[datetime] = Field(default=None, description="警報發生時間")


# ─────────────────────────────────────────────────────────────────────────
# 查詢 / 回應
# ─────────────────────────────────────────────────────────────────────────


class KnowledgeQuery(BaseModel):
    """一次知識檢索請求。"""

    model_config = ConfigDict(from_attributes=True)

    text: str = Field(description="自由文字查詢（警報訊息 / 現場工程師提問）")
    top_k: int = Field(default=3, ge=0, description="回傳前 k 筆，0 表示不回傳")
    fault_code: Optional[str] = Field(
        default=None, description="若帶警報碼，命中的 chunk 會大幅加權"
    )
    oem_model: str = Field(default="Z72", description="機型過濾（多 OEM 語料時）")


class KnowledgeResponse(BaseModel):
    """一次知識檢索回應 —— 前端 alert detail 直接渲染。"""

    model_config = ConfigDict(from_attributes=True)

    query: str = Field(description="原始查詢文字（回顯）")
    oem_model: str = Field(description="實際使用的機型語料")
    strategy_version: str = Field(description="檢索策略版本，便於追溯 baseline / 正式策略")
    chunks: list[RetrievedChunk] = Field(
        default_factory=list, description="依分數排序的 top-k 命中"
    )
    total_candidates: int = Field(
        default=0, description="進入比對的候選 chunk 總數（過濾前）"
    )
    retrieved_at: datetime = Field(description="檢索時間戳（UTC）")
