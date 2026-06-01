"""Baseline lexical 檢索器（WMOM-20260601-01）。

呼應 ROADMAP M5-1：『Knowledge module 後端 —— retrieve.py』，並落實
CLAUDE.md §15『平台只負責載入 + query，不重新 embed』與『Simulator-first』。

本檔提供一個**零重量級依賴、純 Python、決定性**的 baseline 檢索器：
- 不需 ChromaDB（M5-2）、不需 embedding 模型（M5-3），即可在純 simulator
  模式跑通『警報 → 手冊段落』檢索 demo。
- 對中英混合語料友善：英文 / 代碼走 alnum token，中文走 bigram。
- 警報碼（fault_code）精準命中給高權重，貼合現場『一個 alarm code 對一段
  處置』的使用情境。

正式版（M5-3 之後）會新增 embedding-based retriever；兩者共用
``ManualChunk`` / ``RetrievedChunk`` schema，可平滑替換。
"""

from __future__ import annotations

import re

from modules.knowledge.schemas.knowledge_schemas import (
    KnowledgeQuery,
    ManualChunk,
    RetrievedChunk,
)

# 命中權重：警報碼 > 關鍵詞 > 內文，反映精準度遞減
_WEIGHT_FAULT_CODE = 10.0
_WEIGHT_KEYWORD = 3.0
_WEIGHT_TEXT = 1.0

_ASCII_TOKEN = re.compile(r"[a-z0-9_]+")
_CJK_RUN = re.compile(r"[一-鿿]+")


def _extract_terms(text: str) -> set[str]:
    """把文字拆成可比對的 term 集合。

    策略：
    - 英文 / 數字 / 代碼 → 小寫 alnum token（保留底線，如 wgen_gnbrgtmp1）；
      長度 1 的 token 略過（如 ``A-262`` 拆出的 ``a`` 屬雜訊，會誤命中含該
      字母的任意 chunk，拉低精準度）。
    - 中文 → 連續 CJK 片段切 bigram（單字過於發散，bigram 精準度較佳）。

    Args:
        text: 原始文字。

    Returns:
        正規化後的 term 集合（去重）。
    """
    lowered = text.lower()
    terms: set[str] = {t for t in _ASCII_TOKEN.findall(lowered) if len(t) > 1}
    for run in _CJK_RUN.findall(text):
        if len(run) == 1:
            terms.add(run)
            continue
        for i in range(len(run) - 1):
            terms.add(run[i : i + 2])
    return terms


def _normalize_code(code: str) -> str:
    """正規化警報碼以利比對。

    去空白、轉小寫、移除常見分隔符（``A-262`` / ``A 262`` / ``a_262`` →
    ``a262``），讓 monitoring 端與手冊端格式差異不影響命中。
    """
    return re.sub(r"[\s\-_]+", "", code.strip().lower())


class BaselineLexicalRetriever:
    """純 lexical 的 baseline 檢索器。

    在建構時對語料建立輕量倒排索引（每個 chunk 的關鍵詞 term 集、內文 term
    集、正規化警報碼集），查詢時做加權命中計分。結果以 ``(-score, chunk_id)``
    排序確保**決定性**。
    """

    def __init__(self, chunks: list[ManualChunk]) -> None:
        """以一批 chunk 建構檢索器。

        Args:
            chunks: 語料（通常由 ``ingest.load_chunks_from_jsonl`` 載入）。
        """
        self._chunks: list[ManualChunk] = list(chunks)
        # 預先計算每個 chunk 的索引欄位，避免每次查詢重算
        self._keyword_terms: list[set[str]] = []
        self._text_terms: list[set[str]] = []
        self._codes: list[set[str]] = []
        for chunk in self._chunks:
            keyword_blob = " ".join(chunk.keywords)
            self._keyword_terms.append(_extract_terms(keyword_blob))
            self._text_terms.append(_extract_terms(chunk.text))
            self._codes.append({_normalize_code(c) for c in chunk.fault_codes})

    @property
    def size(self) -> int:
        """語料 chunk 總數。"""
        return len(self._chunks)

    def retrieve(self, query: KnowledgeQuery) -> list[RetrievedChunk]:
        """對語料執行 baseline 檢索。

        Args:
            query: 查詢（文字 + 可選 fault_code + top_k + oem_model 過濾）。

        Returns:
            依分數遞減排序的 ``RetrievedChunk`` list，長度 ≤ ``top_k``；
            分數須 > 0 才回傳（無命中不硬塞）。
        """
        if query.top_k <= 0:
            return []

        query_terms = _extract_terms(query.text)
        query_code = _normalize_code(query.fault_code) if query.fault_code else None

        scored: list[RetrievedChunk] = []
        for idx, chunk in enumerate(self._chunks):
            # 機型過濾：只比對同機型語料（baseline 大小寫不敏感）
            if chunk.oem_model.lower() != query.oem_model.lower():
                continue

            score = 0.0
            matched: set[str] = set()

            if query_code and query_code in self._codes[idx]:
                score += _WEIGHT_FAULT_CODE
                matched.add(query.fault_code or "")

            keyword_hits = query_terms & self._keyword_terms[idx]
            score += _WEIGHT_KEYWORD * len(keyword_hits)
            matched |= keyword_hits

            text_hits = query_terms & self._text_terms[idx]
            score += _WEIGHT_TEXT * len(text_hits)
            matched |= text_hits

            if score <= 0:
                continue

            scored.append(
                RetrievedChunk(
                    chunk=chunk,
                    score=score,
                    matched_terms=sorted(t for t in matched if t),
                )
            )

        # 決定性排序：分數高者先，分數相同以 chunk_id 字典序穩定排序
        scored.sort(key=lambda rc: (-rc.score, rc.chunk.chunk_id))
        return scored[: query.top_k]

    def candidate_count(self, oem_model: str) -> int:
        """回傳指定機型的候選 chunk 數（過濾後、計分前）。"""
        target = oem_model.lower()
        return sum(1 for c in self._chunks if c.oem_model.lower() == target)
