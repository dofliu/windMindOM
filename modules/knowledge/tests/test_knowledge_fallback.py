"""Knowledge RAG graceful fallback 測試（M5-2 / WMOM-20260608-01）。

**刻意不放 chromadb importorskip** —— fallback 行為（chroma 不可用 → 退回
baseline keyword）正是要在「依賴 / 向量檔 / 模型缺失」時被驗證，故這些測試
必跑（無論 chromadb 是否安裝、模型是否 ship）。對應 code review must-fix #2。
"""

from __future__ import annotations

from modules.knowledge import build_chroma_alert_handler
from modules.knowledge.schemas import AlertEvent


def test_fallback_on_bad_export_dir() -> None:
    """向量檔目錄不存在 → graceful fallback baseline keyword（不丟例外）。"""
    handler = build_chroma_alert_handler(export_dir="/no/such/vectors")
    assert handler.retriever.is_baseline is True
    assert handler.retriever.name == "baseline_keyword"
    # 仍可正常處理警報（走 baseline）。
    res = handler.on_alert(AlertEvent(alarm_code=21, turbine_id="WT001"))
    assert res.is_baseline is True


def test_fallback_on_missing_model_dir() -> None:
    """向量檔在、但嵌入模型目錄缺 → warmup 觸發 EmbedderUnavailable → fallback baseline。

    驗證 must-fix「啟動正常但首查炸 500」已修：build 後的 warmup retrieve 把
    lazy 模型載入失敗提前到建構期，一併退回 baseline。
    （chromadb 若未安裝，會更早在 import 階段 fallback，結果同樣是 baseline。）
    """
    handler = build_chroma_alert_handler(model_dir="/no/such/model/dir")
    assert handler.retriever.is_baseline is True
    assert handler.retriever.name == "baseline_keyword"
    res = handler.on_alert(AlertEvent(alarm_code=21, turbine_id="WT001"))
    assert res.is_baseline is True
