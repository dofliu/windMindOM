"""cost.routers — FastAPI routers for cost endpoints。

不移植 ECN routers — windMindOM 自己設計 API 對齊 product flow。

Endpoints（WMOM-20260504-07 已實作）：

| Method | Path                  | Body                | Response             |
|--------|-----------------------|---------------------|----------------------|
| POST   | /api/cost/forecast    | CostForecastRequest | CostForecastResponse |
| POST   | /api/cost/lcoe        | LCOERequest         | LCOEResponse         |
| POST   | /api/cost/monte-carlo | MonteCarloRequest   | MonteCarloResponse   |
| POST   | /api/cost/var-fluct   | VarFluctRequest     | VarFluctResponse     |

待補（M3+）：
- GET /api/cost/ledger — 查詢實際成本（與 workflow 雙寫的 ledger）
"""

from modules.cost.routers.cost_router import router

__all__ = ["router"]
