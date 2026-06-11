"""FastAPI dependencies for Supabase-authenticated API routes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import SUPABASE_JWT_SECRET, SUPABASE_URL

_bearer_scheme = HTTPBearer(auto_error=False)
_jwks_cache: dict[str, Any] | None = None
_jwks_cache_expires_at = 0.0


@dataclass(frozen=True)
class CurrentUser:
    """Authenticated Supabase user mapped to an application profile."""

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


def _decode_base64url_json(value: str) -> dict[str, Any]:
    padded = value + "=" * (-len(value) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(decoded)
    except (ValueError, json.JSONDecodeError) as exc:
        raise _auth_error("Malformed Supabase access token.") from exc

    if not isinstance(payload, dict):
        raise _auth_error("Malformed Supabase access token.")
    return payload


def _decode_base64url_bytes(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except ValueError as exc:
        raise _auth_error("Malformed Supabase access token.") from exc


def _fetch_supabase_jwks() -> dict[str, Any]:
    """Synchronous JWKS fetch — kept for internal/test use only.

    In production request paths use ``_fetch_supabase_jwks_async()`` instead
    so that the blocking HTTP call does not stall the FastAPI event loop.
    """
    global _jwks_cache, _jwks_cache_expires_at

    now = time.time()
    if _jwks_cache is not None and now < _jwks_cache_expires_at:
        return _jwks_cache

    if not SUPABASE_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "SUPABASE_AUTH_NOT_CONFIGURED",
                "message": "Backend is missing SUPABASE_URL.",
            },
        )

    try:
        response = httpx.get(
            f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json",
            timeout=5.0,
        )
        response.raise_for_status()
        jwks = response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "SUPABASE_JWKS_UNAVAILABLE",
                "message": "Unable to fetch Supabase JWT signing keys.",
            },
        ) from exc

    if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "SUPABASE_JWKS_INVALID",
                "message": "Supabase JWT signing keys response is invalid.",
            },
        )

    _jwks_cache = jwks
    _jwks_cache_expires_at = now + 300
    return jwks


async def _fetch_supabase_jwks_async() -> dict[str, Any]:
    """Async JWKS fetch — used by request-path dependencies.

    Uses ``httpx.AsyncClient`` to avoid blocking the event loop. Results are
    cached in the same module-level ``_jwks_cache`` dict as the sync variant,
    with a 5-minute TTL.
    """
    global _jwks_cache, _jwks_cache_expires_at

    now = time.time()
    if _jwks_cache is not None and now < _jwks_cache_expires_at:
        return _jwks_cache

    if not SUPABASE_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "SUPABASE_AUTH_NOT_CONFIGURED",
                "message": "Backend is missing SUPABASE_URL.",
            },
        )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
            )
            response.raise_for_status()
            jwks = response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "SUPABASE_JWKS_UNAVAILABLE",
                "message": "Unable to fetch Supabase JWT signing keys.",
            },
        ) from exc

    if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "SUPABASE_JWKS_INVALID",
                "message": "Supabase JWT signing keys response is invalid.",
            },
        )

    _jwks_cache = jwks
    _jwks_cache_expires_at = now + 300
    return jwks

def _find_jwk(header: dict[str, Any]) -> dict[str, Any]:
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise _auth_error("Supabase access token is missing key id.")

    for key in _fetch_supabase_jwks()["keys"]:
        if key.get("kid") == kid:
            return key

    raise _auth_error("Supabase access token signing key was not found.")


def _verify_hs256_signature(parts: list[str]) -> None:
    if not SUPABASE_JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "SUPABASE_AUTH_NOT_CONFIGURED",
                "message": "Backend is missing SUPABASE_JWT_SECRET.",
            },
        )

    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    expected_signature = hmac.new(
        SUPABASE_JWT_SECRET.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    expected_encoded = base64.urlsafe_b64encode(expected_signature).rstrip(b"=").decode("ascii")

    if not hmac.compare_digest(expected_encoded, parts[2]):
        raise _auth_error("Invalid Supabase access token signature.")


def _verify_es256_signature(parts: list[str], header: dict[str, Any]) -> None:
    jwk = _find_jwk(header)
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        raise _auth_error("Unsupported Supabase access token signing key.")

    signature = _decode_base64url_bytes(parts[2])
    if len(signature) != 64:
        raise _auth_error("Malformed Supabase access token signature.")

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
        raise _auth_error("Invalid Supabase access token signature.") from exc


def verify_supabase_access_token(token: str) -> CurrentUser:
    """Verify a Supabase JWT and return the current user.

    Supabase access tokens are signed with the project's JWT secret for the
    default Auth setup. The frontend obtains the token through supabase-js and
    sends it as `Authorization: Bearer <access_token>`.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise _auth_error("Malformed Supabase access token.")

    header = _decode_base64url_json(parts[0])
    algorithm = header.get("alg")
    if algorithm == "HS256":
        _verify_hs256_signature(parts)
    elif algorithm == "ES256":
        _verify_es256_signature(parts, header)
    else:
        raise _auth_error("Unsupported Supabase access token algorithm.")

    claims = _decode_base64url_json(parts[1])

    exp = claims.get("exp")
    if not isinstance(exp, int | float):
        raise _auth_error("Supabase access token is missing expiration.")
    if exp <= time.time():
        raise _auth_error("Supabase access token has expired.")

    audience = claims.get("aud")
    valid_audience = audience == "authenticated" or (
        isinstance(audience, list) and "authenticated" in audience
    )
    if not valid_audience:
        raise _auth_error("Supabase access token has invalid audience.")

    user_id = claims.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise _auth_error("Supabase access token is missing subject.")

    email = claims.get("email")
    role = claims.get("role") or "authenticated"

    return CurrentUser(
        id=user_id,
        email=email if isinstance(email, str) else None,
        role=role if isinstance(role, str) else "authenticated",
        claims=claims,
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    """Require a valid Supabase Bearer token and active app profile.

    JWKS keys are fetched via async HTTP client (``_fetch_supabase_jwks_async``)
    to avoid blocking the FastAPI event loop on I/O.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _auth_error("Missing Bearer token.")

    # Pre-warm the JWKS cache using the async client before entering the
    # sync verify path so that the network call is non-blocking.
    if _jwks_cache is None or time.time() >= _jwks_cache_expires_at:
        await _fetch_supabase_jwks_async()

    token_user = verify_supabase_access_token(credentials.credentials)

    from app.services import user_service

    profile = await user_service.get_or_create_profile(token_user)
    if not profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "USER_INACTIVE",
                "message": "User profile is inactive.",
            },
        )
    return profile


async def get_admin_user(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Require an active admin profile."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "ADMIN_REQUIRED",
                "message": "Admin role is required.",
            },
        )
    return current_user
