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


def _map_user_data(user_data: dict[str, Any]) -> CurrentUser:
    user_id = user_data.get("id") or user_data.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise _auth_error("Authenticated token is missing user id.")
    return CurrentUser(
        id=user_id,
        email=user_data.get("email"),
        role=user_data.get("role", "user"),
        claims=user_data.get("claims", user_data),
        display_name=user_data.get("display_name"),
        is_active=user_data.get("is_active", True),
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
        logger.error("Auth provider resolution failed: AppContainer is not initialized")
        raise _auth_error("Auth service unavailable.")
    auth = container.auth

    try:
        user_data = await auth.verify_token(token)
    except Exception as exc:
        logger.warning("Token verification failed: %s", exc)
        raise _auth_error(str(exc)) from exc

    if user_data is None:
        raise _auth_error("Invalid or expired token.")

    current_user = _map_user_data(user_data)
    if not current_user.is_active:
        raise _forbidden_error("User profile is inactive.")
    return current_user


async def get_optional_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser | None:
    """Return CurrentUser when a Bearer token is present, otherwise None."""
    if credentials is None:
        return None
    return await get_current_user(request, credentials)


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
