"""cost.routers — FastAPI routers for cost endpoints。

不移植 ECN routers — windMindOM 自己設計 API 對齊 product flow。

預定 endpoints（M2 後段，WMOM-20260504-07）：
- POST /api/cost/forecast       觸發 cost calculation
- GET  /api/cost/ledger         查詢實際成本（與 workflow 雙寫的 ledger）
- GET  /api/cost/lcoe           LCOE dashboard 用
- POST /api/cost/monte-carlo    Monte Carlo 風險分析
"""
