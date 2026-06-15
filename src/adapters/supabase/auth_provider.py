"""Supabase Auth Provider Adapter — implements IAuthProvider.

Verifies JWT tokens signed by Supabase and resolves user roles
from the profiles table.

JWT verification uses python-jose (HS256) — matching the Supabase
JWT configuration (secret from SUPABASE_JWT_SECRET).
"""

from __future__ import annotations

import logging
from typing import Any

from ports.auth import IAuthProvider

logger = logging.getLogger(__name__)

# Valid roles in this system
_VALID_ROLES = frozenset({"user", "reviewer", "admin"})
_DEFAULT_ROLE = "user"


class SupabaseAuthProvider(IAuthProvider):
    """Production auth adapter backed by Supabase JWT + profiles table.

    Args:
        jwt_secret: The Supabase JWT secret (SUPABASE_JWT_SECRET).
        db: An IDatabaseRepository instance for role lookups.
    """

    def __init__(self, jwt_secret: str, db) -> None:
        self._jwt_secret = jwt_secret
        self._db = db

    async def verify_token(self, token: str) -> dict[str, Any]:
        """Verify a Supabase JWT and return the decoded payload.

        Args:
            token: The bearer token string (without 'Bearer ' prefix).

        Returns:
            Dict with at least 'sub' (user UUID) and standard JWT claims.

        Raises:
            AuthorizationError: If the token is invalid, expired, or malformed.
        """
        try:
            from jose import JWTError, jwt
        except ImportError as exc:
            from domain.shared.errors import InfrastructureError
            raise InfrastructureError(
                "python-jose is not installed. Run: pip install python-jose[cryptography]"
            ) from exc

        try:
            payload = jwt.decode(
                token,
                self._jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False},  # Supabase does not require aud
            )
            if not payload.get("sub"):
                from domain.shared.errors import AuthorizationError
                raise AuthorizationError("Token missing 'sub' claim")
            return payload
        except JWTError as exc:
            from domain.shared.errors import AuthorizationError
            raise AuthorizationError(f"Invalid or expired token: {exc}") from exc

    async def get_user_role(self, user_id: str) -> str:
        """Resolve the role for a given user ID from the profiles table.

        Args:
            user_id: Supabase user UUID.

        Returns:
            Role string: 'user', 'reviewer', or 'admin'.
        """
        try:
            row = self._db.fetch_one(
                "SELECT role FROM profiles WHERE id = %s",
                (user_id,),
            )
            if row and row.get("role") in _VALID_ROLES:
                return row["role"]
            logger.debug(
                "get_user_role: user '%s' has no valid role in profiles, defaulting to '%s'",
                user_id,
                _DEFAULT_ROLE,
            )
            return _DEFAULT_ROLE
        except Exception as exc:
            logger.warning(
                "get_user_role: failed to fetch role for user '%s': %s. Defaulting to '%s'.",
                user_id,
                exc,
                _DEFAULT_ROLE,
            )
            return _DEFAULT_ROLE
