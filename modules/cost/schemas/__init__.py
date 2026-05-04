"""cost.schemas — pydantic schemas for cost API + canonical input/output。

對 engine layer 是「翻譯層」：
- Engine 用 dataclass（從 ECN 移植，不動）
- Schemas 用 pydantic（windMindOM API 用）
- Adapter 在 cost/adapter.py（待補）做雙向轉換

這樣 engine 保持 ECN-compatible（能跟 ECN baseline 比對），對外則是
windMindOM canonical schema。
"""
