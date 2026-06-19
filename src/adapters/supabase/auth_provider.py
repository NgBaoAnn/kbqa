"""Supabase Auth Provider Adapter — implements IAuthProvider.

Verifies Supabase access tokens and resolves user roles from the profiles table.
Supabase projects can issue either HS256 JWTs signed by ``SUPABASE_JWT_SECRET``
or ES256 JWTs signed by rotating asymmetric keys exposed through JWKS.
"""

from __future__ import annotations

import base64
import json
import logging
import time
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
        jwt_secret: Supabase JWT secret for HS256 projects.
        db: An IDatabaseRepository instance for role lookups.
        supabase_url: Project URL used to fetch JWKS for ES256 projects.
    """

    def __init__(self, jwt_secret: str, db, supabase_url: str = "") -> None:
        self._jwt_secret = jwt_secret
        self._supabase_url = supabase_url.rstrip("/")
        self._db = db
        self._jwks_cache: dict[str, Any] | None = None
        self._jwks_cache_expires_at = 0.0

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
            payload = await self._decode_token(token)
            if not payload.get("sub"):
                from domain.shared.errors import AuthorizationError
                raise AuthorizationError("Token missing 'sub' claim")
            return self._get_or_create_profile(payload)
        except Exception as exc:
            from domain.shared.errors import AuthorizationError
            raise AuthorizationError(f"Invalid or expired token: {exc}") from exc

    async def _decode_token(self, token: str) -> dict[str, Any]:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Malformed Supabase access token.")

        header = _decode_base64url_json(parts[0])
        algorithm = header.get("alg")
        if algorithm == "HS256":
            return self._decode_hs256_token(token)
        if algorithm == "ES256":
            await self._verify_es256_signature(parts, header)
            claims = _decode_base64url_json(parts[1])
            self._validate_claims(claims)
            return claims
        raise ValueError("Unsupported Supabase access token algorithm.")

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

    async def _verify_es256_signature(self, parts: list[str], header: dict[str, Any]) -> None:
        jwk = await self._find_jwk(header)
        if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
            raise ValueError("Unsupported Supabase access token signing key.")

        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec, utils

        signature = _decode_base64url_bytes(parts[2])
        if len(signature) != 64:
            raise ValueError("Malformed Supabase access token signature.")

        x_bytes = _decode_base64url_bytes(jwk["x"])
        y_bytes = _decode_base64url_bytes(jwk["y"])
        public_numbers = ec.EllipticCurvePublicNumbers(
            int.from_bytes(x_bytes, "big"),
            int.from_bytes(y_bytes, "big"),
            ec.SECP256R1(),
        )
        public_key = public_numbers.public_key()
        der_signature = utils.encode_dss_signature(
            int.from_bytes(signature[:32], "big"),
            int.from_bytes(signature[32:], "big"),
        )
        signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")

        try:
            public_key.verify(der_signature, signing_input, ec.ECDSA(hashes.SHA256()))
        except InvalidSignature as exc:
            raise ValueError("Invalid Supabase access token signature.") from exc

    async def _find_jwk(self, header: dict[str, Any]) -> dict[str, Any]:
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise ValueError("Supabase access token is missing key id.")

        jwks = await self._fetch_supabase_jwks()
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return key
        raise ValueError("Supabase access token signing key was not found.")

    async def _fetch_supabase_jwks(self) -> dict[str, Any]:
        now = time.time()
        if self._jwks_cache is not None and now < self._jwks_cache_expires_at:
            return self._jwks_cache
        if not self._supabase_url:
            raise ValueError("SUPABASE_URL is required for ES256 token verification.")

        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{self._supabase_url}/auth/v1/.well-known/jwks.json")
            response.raise_for_status()
            jwks = response.json()

        if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
            raise ValueError("Supabase JWT signing keys response is invalid.")

        self._jwks_cache = jwks
        self._jwks_cache_expires_at = now + 300
        return jwks

    @staticmethod
    def _validate_claims(claims: dict[str, Any]) -> None:
        exp = claims.get("exp")
        if not isinstance(exp, int | float):
            raise ValueError("Supabase access token is missing expiration.")
        if exp <= time.time():
            raise ValueError("Supabase access token has expired.")

        audience = claims.get("aud")
        valid_audience = audience == "authenticated" or (
            isinstance(audience, list) and "authenticated" in audience
        )
        if not valid_audience:
            raise ValueError("Supabase access token has invalid audience.")

        if not isinstance(claims.get("sub"), str) or not claims["sub"]:
            raise ValueError("Supabase access token is missing subject.")

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


def _decode_base64url_json(value: str) -> dict[str, Any]:
    padded = value + "=" * (-len(value) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(decoded)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed Supabase access token.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Malformed Supabase access token.")
    return payload


def _decode_base64url_bytes(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except ValueError as exc:
        raise ValueError("Malformed Supabase access token.") from exc
