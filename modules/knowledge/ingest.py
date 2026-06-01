"""語料載入（ingest）—— WMOM-20260601-01。

呼應 ROADMAP M5-1（``ingest.py``）+ M5-4（灌 Z72 手冊跑通 ingest pipeline）。

**重要邊界**（CLAUDE.md §15）：windMindOM 內的 ingest **不負責切塊與 embedding**
（那是研究端 RAG_Ultimate Phase 3 的工作）。本檔只負責把研究端產出的
結構化語料（jsonl，每行一個 ``ManualChunk``）載入記憶體，並依策略檔建出
可查詢的 baseline 檢索器。

未來接 ChromaDB（M5-2）/ parquet（M5-3）時，新增對應 loader 即可，
``ManualChunk`` schema 不變。
"""

from __future__ import annotations

import json
from pathlib import Path

from modules.knowledge.retrieve import BaselineLexicalRetriever
from modules.knowledge.schemas.knowledge_schemas import ManualChunk
from modules.knowledge.strategy_loader import RagStrategy
from pydantic import ValidationError


def load_chunks_from_jsonl(path: Path) -> list[ManualChunk]:
    """從 jsonl 載入手冊 chunk（每行一個 JSON object）。

    空行 / 純空白行會被略過（方便人手編輯語料）。任一行 JSON 或 schema
    解析失敗，會帶**行號**拋出 ``ValueError``，便於定位壞資料。

    Args:
        path: jsonl 語料檔路徑。

    Returns:
        ``ManualChunk`` list（保留檔案順序）。

    Raises:
        FileNotFoundError: 檔案不存在。
        ValueError: 某行 JSON 解析或 schema 驗證失敗。
    """
    if not path.exists():
        raise FileNotFoundError(f"語料檔不存在：{path}")

    chunks: list[ManualChunk] = []
    with path.open(encoding="utf-8") as fh:
        for lineno, raw_line in enumerate(fh, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"語料第 {lineno} 行 JSON 解析失敗：{path}（{exc}）"
                ) from exc
            try:
                chunks.append(ManualChunk.model_validate(payload))
            except ValidationError as exc:
                raise ValueError(
                    f"語料第 {lineno} 行欄位不符 schema：{path}（{exc}）"
                ) from exc
    return chunks


def build_retriever(
    strategy: RagStrategy, base_dir: Path
) -> BaselineLexicalRetriever:
    """依策略檔載入語料並建出 baseline 檢索器。

    Args:
        strategy: 已驗證的 ``RagStrategy``（決定語料路徑與格式）。
        base_dir: 解析相對 corpus 路徑的基準目錄（通常為策略檔所在目錄）。

    Returns:
        以策略指定語料建構的 ``BaselineLexicalRetriever``。

    Raises:
        ValueError: 不支援的語料格式。
        FileNotFoundError: 語料檔不存在。
    """
    fmt = strategy.corpus.format.lower()
    if fmt != "jsonl":
        raise ValueError(
            f"baseline ingest 目前僅支援 jsonl 語料，實得 format={strategy.corpus.format!r}"
        )
    corpus_path = strategy.resolve_corpus_path(base_dir)
    chunks = load_chunks_from_jsonl(corpus_path)
    return BaselineLexicalRetriever(chunks)
