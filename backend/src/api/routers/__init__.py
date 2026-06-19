"""Routers package.

All routers are imported here and exposed for registration in app.py.
"""

from api.routers.admin import router as admin_router
from api.routers.conversations import router as conversations_router
from api.routers.feedback import router as feedback_router
from api.routers.health import router as health_router
from api.routers.knowledge import router as knowledge_router
from api.routers.me import router as me_router
from api.routers.query import router as query_router
from api.routers.schema import router as schema_router

__all__ = [
    "admin_router",
    "conversations_router",
    "feedback_router",
    "health_router",
    "knowledge_router",
    "me_router",
    "query_router",
    "schema_router",
]
