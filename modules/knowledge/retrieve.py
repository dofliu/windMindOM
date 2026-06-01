"""檢索層（M5-1）。

定義 ``Retriever`` 介面 + ``BaselineKeywordRetriever``（純 Python，無外部依賴）。

baseline retriever 讓 windMindOM 在「ChromaDB（M5-2）/ RAG_Ultimate 真向量檔
（M5-3 🟡）尚未就緒」時，純 simulator 模式即可 demo「警報 → 手冊處置段落」。
升級路徑（MVP_ARCHITECTURE §3.5 升級表）：之後新增 ``ChromaVectorRetriever``
實作同一 ``Retriever`` 介面，``AlertHandler`` / schema / 前端皆不需改動。

評分（baseline，可解釋且確定性）：
- 告警碼命中（query.alarm_codes ∩ chunk.alarm_codes）→ 主信號 0.6
- chunk 關鍵字在 query 文字出現的比例 → 至多 0.3
- query / chunk 文字 token 重疊（Jaccard）→ 至多 0.1
總分 clamp 0..1，丟棄零分，依分數降冪（同分以 chunk.id 穩定排序）取 top_k。
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from modules.knowledge.corpus import KnowledgeCorpus
from modules.knowledge.schemas import (
    KnowledgeChunk,
    RagStrategy,
    RetrievalQuery,
    RetrievedChunk,
)

# 評分權重（baseline）。
_CODE_WEIGHT = 0.6
_KEYWORD_WEIGHT = 0.3
_OVERLAP_WEIGHT = 0.1

# ASCII 詞 token（含底線，對齊 SCADA tag 如 WCNV_IGCTWtrTmp）。
_ASCII_TOKEN_RE = re.compile(r"[a-z0-9_]+")
# CJK 字元（U+4E00–U+9FFF，BMP 主塊；用於中文 bigram，無需斷詞器）。
# 刻意只涵蓋 BMP 主塊 —— baseline 語料字元全在此範圍；Ext-A / 補充平面
# 罕用繁體字不在內，待 M5-3 接真語料若有需要再擴。
_CJK_RE = re.compile(r"[一-鿿]")


def tokenize(text: str) -> set[str]:
    """把文字切成可比對 token 集合（公開工具，retriever / 未來實作可共用）。

    英數（含底線）取整詞；中文取相鄰二字 bigram —— 無需外部斷詞器即可
    在純 Python 下對中文做粗略重疊比對（baseline 夠用）。
    """
    lowered = text.lower()
    tokens: set[str] = set(_ASCII_TOKEN_RE.findall(lowered))
    cjk_chars = _CJK_RE.findall(text)
    for i in range(len(cjk_chars) - 1):
        tokens.add(cjk_chars[i] + cjk_chars[i + 1])
    return tokens


@runtime_checkable
class Retriever(Protocol):
    """檢索器介面。

    任何 retriever（baseline keyword / 未來 ChromaDB 向量）都實作此契約，
    讓 ``AlertHandler`` 與上層只依賴介面、不綁具體實作（MVP_ARCHITECTURE
    §3.5 升級契約：換 retriever 不需改 handler / schema）。

    契約屬性（實作必須提供）：
    - ``name``：retriever 識別名（寫進 ``AlertRagResult.retriever``）。
    - ``is_baseline``：True 表示 placeholder 檢索（非真向量），前端可標示。
    """

    name: str
    is_baseline: bool

    def retrieve(self, query: RetrievalQuery) -> list[RetrievedChunk]:
        """依 query 回傳已排序的命中 chunk（最相關在前）。"""
        ...


class BaselineKeywordRetriever:
    """純 Python 關鍵字 + 告警碼檢索器（baseline placeholder）。"""

    name = "baseline_keyword"
    # placeholder 檢索（非真向量）；M5-3 接 RAG_Ultimate 向量檔後改 False。
    is_baseline = True

    def __init__(self, corpus: KnowledgeCorpus, strategy: RagStrategy) -> None:
        """以知識庫 + 策略建立 retriever。

        Args:
            corpus: 知識庫（chunk 集合）。
            strategy: RAG 策略；本 retriever 取 ``retrieval.top_k`` 作為
                預設回傳筆數（query 可覆寫）。
        """
        self._corpus = corpus
        self._strategy = strategy

    def retrieve(self, query: RetrievalQuery) -> list[RetrievedChunk]:
        """執行檢索，回傳已排序的 ``RetrievedChunk`` 清單。"""
        # 1) 依 oem / model 過濾（query 未指定該維度則不限）。
        candidates = self._corpus.filter(oem=query.oem, model=query.model).chunks

        query_codes = set(query.alarm_codes)
        query_tokens = tokenize(query.text)
        query_text_lower = query.text.lower()

        scored: list[RetrievedChunk] = []
        for chunk in candidates:
            score, reason = self._score(
                chunk, query_codes, query_tokens, query_text_lower
            )
            if score > 0.0:
                scored.append(
                    RetrievedChunk(chunk=chunk, score=score, match_reason=reason)
                )

        # 2) 依分數降冪；同分以 chunk.id 穩定排序（確定性，方便測試）。
        scored.sort(key=lambda rc: (-rc.score, rc.chunk.id))

        # 3) top_k：query 明確指定（非 None）才覆寫，否則用策略值。
        #    用 `is not None` 而非 `or`，避免未來 top_k 約束放寬時 0 被誤 fallback。
        top_k = query.top_k if query.top_k is not None else self._strategy.retrieval.top_k
        return scored[:top_k]

    def _score(
        self,
        chunk: KnowledgeChunk,
        query_codes: set[int],
        query_tokens: set[str],
        query_text_lower: str,
    ) -> tuple[float, str]:
        """計算單一 chunk 的分數 + 繁中可解釋原因。"""
        reasons: list[str] = []
        score = 0.0

        # (a) 告警碼命中 —— 警報驅動檢索的主信號。
        matched_codes = query_codes & set(chunk.alarm_codes)
        if matched_codes:
            score += _CODE_WEIGHT
            codes_str = ", ".join(str(c) for c in sorted(matched_codes))
            reasons.append(f"命中告警碼 {codes_str}")

        # (b) 關鍵字命中比例（case-insensitive 子字串）。
        if chunk.keywords:
            hit_keywords = [
                kw for kw in chunk.keywords if kw.lower() in query_text_lower
            ]
            if hit_keywords:
                score += _KEYWORD_WEIGHT * (len(hit_keywords) / len(chunk.keywords))
                shown = ", ".join(hit_keywords[:5])
                reasons.append(f"關鍵字命中：{shown}")

        # (c) 文字 token 重疊（Jaccard）。有貢獻就記錄（前端透明度：
        #     分數變動須有對應說明，不論碼 / 關鍵字是否已命中）。
        chunk_tokens = tokenize(chunk.chunk_text)
        if chunk_tokens and query_tokens:
            overlap = query_tokens & chunk_tokens
            if overlap:
                jaccard = len(overlap) / len(query_tokens | chunk_tokens)
                score += _OVERLAP_WEIGHT * jaccard
                reasons.append(f"文字重疊（Jaccard {jaccard:.2f}）")

        return min(1.0, score), "；".join(reasons)
