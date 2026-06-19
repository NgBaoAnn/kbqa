"""Unit tests for SupabaseAuthProvider JWT verification."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils


def _b64url(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _make_hs256_token(secret: str, claims: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _b64url(json.dumps(header, separators=(",", ":")).encode())
    encoded_claims = _b64url(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{encoded_header}.{encoded_claims}".encode("ascii")
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_claims}.{_b64url(signature)}"


def _make_es256_token(private_key, key_id: str, claims: dict) -> str:
    header = {"alg": "ES256", "kid": key_id, "typ": "JWT"}
    encoded_header = _b64url(json.dumps(header, separators=(",", ":")).encode())
    encoded_claims = _b64url(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{encoded_header}.{encoded_claims}".encode("ascii")
    der_signature = private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = utils.decode_dss_signature(der_signature)
    raw_signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return f"{encoded_header}.{encoded_claims}.{_b64url(raw_signature)}"


def _jwk_from_private_key(private_key, key_id: str) -> dict:
    numbers = private_key.public_key().public_numbers()
    return {
        "alg": "ES256",
        "crv": "P-256",
        "kid": key_id,
        "kty": "EC",
        "use": "sig",
        "x": _b64url(numbers.x.to_bytes(32, "big")),
        "y": _b64url(numbers.y.to_bytes(32, "big")),
    }


class FakeDb:
    def fetch_one(self, query, params=()):
        assert "public.profiles" in query or "profiles" in query
        return {
            "id": params[0],
            "display_name": "Test User",
            "role": "user",
            "is_active": True,
            "created_at": "2026-06-18T00:00:00+00:00",
            "updated_at": "2026-06-18T00:00:00+00:00",
        }


def _claims() -> dict:
    return {
        "sub": "user-123",
        "email": "user@example.com",
        "role": "authenticated",
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
    }


@pytest.mark.asyncio
async def test_verify_token_accepts_hs256_supabase_token():
    from adapters.supabase.auth_provider import SupabaseAuthProvider

    provider = SupabaseAuthProvider(jwt_secret="test-secret", db=FakeDb())
    user = await provider.verify_token(_make_hs256_token("test-secret", _claims()))

    assert user["id"] == "user-123"
    assert user["email"] == "user@example.com"
    assert user["role"] == "user"


@pytest.mark.asyncio
async def test_verify_token_accepts_es256_supabase_jwks_token():
    from adapters.supabase.auth_provider import SupabaseAuthProvider

    private_key = ec.generate_private_key(ec.SECP256R1())
    provider = SupabaseAuthProvider(jwt_secret="unused", db=FakeDb(), supabase_url="https://example.supabase.co")

    async def fetch_jwks():
        return {"keys": [_jwk_from_private_key(private_key, "test-key")]}

    provider._fetch_supabase_jwks = fetch_jwks

    user = await provider.verify_token(_make_es256_token(private_key, "test-key", _claims()))

    assert user["id"] == "user-123"
    assert user["email"] == "user@example.com"
    assert user["role"] == "user"


@pytest.mark.asyncio
async def test_verify_token_rejects_es256_bad_signature():
    from adapters.supabase.auth_provider import SupabaseAuthProvider
    from domain.shared.errors import AuthorizationError

    private_key = ec.generate_private_key(ec.SECP256R1())
    other_key = ec.generate_private_key(ec.SECP256R1())
    provider = SupabaseAuthProvider(jwt_secret="unused", db=FakeDb(), supabase_url="https://example.supabase.co")

    async def fetch_jwks():
        return {"keys": [_jwk_from_private_key(other_key, "test-key")]}

    provider._fetch_supabase_jwks = fetch_jwks

    with pytest.raises(AuthorizationError, match="Invalid or expired token"):
        await provider.verify_token(_make_es256_token(private_key, "test-key", _claims()))
