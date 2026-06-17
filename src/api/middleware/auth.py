"""Auth FastAPI dependency — delegates to the IAuthProvider adapter.

This is a thin shim that resolves the auth adapter from the AppContainer
and exposes a ``get_current_user`` FastAPI dependency.

Design:
    - Routers import ``get_current_user`` and ``require_role``.
    - No JWT logic lives here — it's all in adapters/supabase/auth_provider.py.
    - In tests, swap the container's auth adapter with InMemoryAuthProvider.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)
_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    """Authenticated user passed through the request lifecycle."""

    id: str
    email: str | None
    role: str
    claims: dict[str, Any]
    display_name: str | None = None
    is_active: bool = True


def _auth_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error_code": "AUTHENTICATION_REQUIRED", "message": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error_code": "FORBIDDEN", "message": detail},
    )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    """FastAPI dependency: validate Bearer token and return CurrentUser.

    Resolves the IAuthProvider from the AppContainer stored in app.state.
    """
    if credentials is None:
        raise _auth_error("Missing Bearer token.")

    token = credentials.credentials

    # Resolve auth provider from app container
    container = getattr(request.app.state, "container", None)
    if container is None:
        # Fallback: try legacy SupabaseAuthProvider via adapter directly
        try:
            from adapters.supabase.auth_provider import SupabaseAuthProvider
            from api.config import settings
            from adapters.supabase.database_repository import SupabaseDatabaseRepository

            db = SupabaseDatabaseRepository(db_url=settings.supabase_db_url or None)
            auth = SupabaseAuthProvider(jwt_secret=settings.supabase_jwt_secret, db=db)
        except Exception as exc:
            logger.error("Auth provider resolution failed: %s", exc)
            raise _auth_error("Auth service unavailable.") from exc
    else:
        auth = container.auth

    try:
        user_data = await auth.verify_token(token)
    except Exception as exc:
        logger.warning("Token verification failed: %s", exc)
        raise _auth_error(str(exc)) from exc

    if user_data is None:
        raise _auth_error("Invalid or expired token.")

    return CurrentUser(
        id=user_data.get("id", ""),
        email=user_data.get("email"),
        role=user_data.get("role", "user"),
        claims=user_data.get("claims", {}),
        display_name=user_data.get("display_name"),
        is_active=user_data.get("is_active", True),
    )


def require_role(*roles: str):
    """FastAPI dependency factory: require the user to have one of the given roles.

    Usage::

        @router.get("/admin", dependencies=[Depends(require_role("admin", "reviewer"))])
        async def admin_endpoint(): ...
    """

    async def _dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in roles:
            raise _forbidden_error(
                f"Insufficient permissions. Required: {list(roles)}, got: {current_user.role}"
            )
        return current_user

    return _dependency


# Convenience aliases
require_admin = require_role("admin")
require_reviewer = require_role("admin", "reviewer")
