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
_PROFILE_COLUMNS = """
    id::text as id,
    display_name,
    role,
    is_active,
    created_at::text as created_at,
    updated_at::text as updated_at
"""


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
            payload = self._decode_hs256_token(token)
            if not payload.get("sub"):
                from domain.shared.errors import AuthorizationError
                raise AuthorizationError("Token missing 'sub' claim")
            return self._get_or_create_profile(payload)
        except Exception as exc:
            from domain.shared.errors import AuthorizationError
            raise AuthorizationError(f"Invalid or expired token: {exc}") from exc

    def _decode_hs256_token(self, token: str) -> dict[str, Any]:
        """Decode a Supabase HS256 token with jose when available, else PyJWT."""
        try:
            from jose import jwt as jose_jwt

            return jose_jwt.decode(
                token,
                self._jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
                options={"verify_aud": True},
            )
        except ImportError:
            import jwt as pyjwt

            return pyjwt.decode(
                token,
                self._jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
                options={"verify_aud": True},
            )

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

    def _get_or_create_profile(self, claims: dict[str, Any]) -> dict[str, Any]:
        """Resolve the app profile for a verified Supabase JWT."""
        user_id = str(claims["sub"])
        row = self._db.fetch_one(
            f"""
            select {_PROFILE_COLUMNS}
            from public.profiles
            where id = %s
            """,
            (user_id,),
        )
        if row is None:
            row = self._db.fetch_one(
                f"""
                insert into public.profiles (id, display_name, role)
                values (%s, %s, 'user')
                on conflict (id) do update
                    set updated_at = public.profiles.updated_at
                returning {_PROFILE_COLUMNS}
                """,
                (user_id, self._default_display_name(claims.get("email"))),
            )
        if row is None:
            from domain.shared.errors import AuthorizationError
            raise AuthorizationError("Failed to create or load user profile.")

        return {
            "id": str(row["id"]),
            "email": claims.get("email") if isinstance(claims.get("email"), str) else None,
            "role": row.get("role") if row.get("role") in _VALID_ROLES else _DEFAULT_ROLE,
            "claims": claims,
            "display_name": row.get("display_name"),
            "is_active": bool(row.get("is_active", True)),
        }

    @staticmethod
    def _default_display_name(email: Any) -> str:
        if isinstance(email, str) and "@" in email:
            return email.split("@", 1)[0]
        return "User"
