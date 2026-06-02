"""knowledge.routers — FastAPI router for 警報 → RAG（M5-6）。

| Method | Path                  | Body / Query | Response        | Issue            |
|--------|-----------------------|--------------|-----------------|------------------|
| POST   | /api/knowledge/alert  | AlertEvent   | AlertRagResult  | WMOM-20260602-01 |
| GET    | /api/knowledge/status | —            | KnowledgeStatus | WMOM-20260602-01 |
"""

from __future__ import annotations

from modules.knowledge.routers.knowledge_router import router, set_alert_handler

# KnowledgeStatus 屬 schema（純 pydantic shape），消費者請從 modules.knowledge.schemas
# 取用，router 層不再 re-export，維持依賴方向（router 是 schema 的消費者）。

__all__ = ["router", "set_alert_handler"]
