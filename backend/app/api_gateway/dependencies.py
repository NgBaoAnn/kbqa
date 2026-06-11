"""FastAPI dependencies for Supabase-authenticated API routes."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import SUPABASE_JWT_SECRET

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    """Authenticated Supabase user extracted from a verified access token."""

    id: str
    email: str | None
    role: str
    claims: dict[str, Any]


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


def verify_supabase_access_token(token: str) -> CurrentUser:
    """Verify a Supabase JWT and return the current user.

    Supabase access tokens are signed with the project's JWT secret for the
    default Auth setup. The frontend obtains the token through supabase-js and
    sends it as `Authorization: Bearer <access_token>`.
    """
    if not SUPABASE_JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error_code": "SUPABASE_AUTH_NOT_CONFIGURED",
                "message": "Backend is missing SUPABASE_JWT_SECRET.",
            },
        )

    parts = token.split(".")
    if len(parts) != 3:
        raise _auth_error("Malformed Supabase access token.")

    header = _decode_base64url_json(parts[0])
    if header.get("alg") != "HS256":
        raise _auth_error("Unsupported Supabase access token algorithm.")

    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    expected_signature = hmac.new(
        SUPABASE_JWT_SECRET.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    expected_encoded = base64.urlsafe_b64encode(expected_signature).rstrip(b"=").decode("ascii")

    if not hmac.compare_digest(expected_encoded, parts[2]):
        raise _auth_error("Invalid Supabase access token signature.")

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
    """Require a valid Supabase Bearer token."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _auth_error("Missing Bearer token.")

    return verify_supabase_access_token(credentials.credentials)
