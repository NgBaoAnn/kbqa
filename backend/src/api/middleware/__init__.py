"""Middleware package.

Exports:
    add_cors_middleware   — attach CORSMiddleware to a FastAPI app
    RateLimitMiddleware   — Starlette ASGI middleware class
    get_current_user      — FastAPI dependency for JWT auth
    require_role          — role-based access control dependency factory
    CurrentUser           — dataclass returned by get_current_user
"""

from api.middleware.auth import CurrentUser, get_current_user, require_admin, require_reviewer, require_role
from api.middleware.cors import add_cors_middleware
from api.middleware.rate_limit import RateLimitMiddleware

__all__ = [
    "add_cors_middleware",
    "RateLimitMiddleware",
    "get_current_user",
    "require_role",
    "require_admin",
    "require_reviewer",
    "CurrentUser",
]
