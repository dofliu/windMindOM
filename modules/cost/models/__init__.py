"""cost.models — windMindOM 自有的 cost-related ORM / domain models。

注意：**不**移植 ECN 的 SQLAlchemy models（13 個）。windMindOM 自己設計
schema 對齊 product flow（見 docs/product/MVP_ARCHITECTURE.md）。

預定模型（M2 後段補）：
- BudgetSnapshot — 每月預算快照
- CostLedger — 實際成本紀錄（與 modules/workflow 雙寫）
- LCOEResult — LCOE 計算結果（從 engine 包進來）
"""
