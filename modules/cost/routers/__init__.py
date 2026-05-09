"""cost.routers — FastAPI routers for cost endpoints。

Endpoints：

| Method | Path                       | Body                | Response             | Issue |
|--------|----------------------------|---------------------|----------------------|-------|
| POST   | /api/cost/forecast         | CostForecastRequest | CostForecastResponse | -07   |
| POST   | /api/cost/lcoe             | LCOERequest         | LCOEResponse         | -07   |
| POST   | /api/cost/monte-carlo      | MonteCarloRequest   | MonteCarloResponse   | -07   |
| POST   | /api/cost/var-fluct        | VarFluctRequest     | VarFluctResponse     | -07   |
| GET    | /api/cost/ledger           | (query string)      | CostLedgerListResp   | -05   |
| GET    | /api/cost/ledger/summary   | (query string)      | CostLedgerSummary    | -05   |
"""

from modules.cost.routers.cost_ledger_router import router as ledger_router
from modules.cost.routers.cost_router import router

__all__ = ["router", "ledger_router"]
