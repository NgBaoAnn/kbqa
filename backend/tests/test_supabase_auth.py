"""Tests for Supabase JWT verification dependency."""

import base64
import hashlib
import hmac
import json
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils

from app.api_gateway import dependencies
from app.main import app


def _b64url(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _make_token(secret: str, claims: dict) -> str:
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


def test_verify_supabase_access_token_accepts_valid_token(monkeypatch):
    monkeypatch.setattr(dependencies, "SUPABASE_JWT_SECRET", "test-secret")
    token = _make_token(
        "test-secret",
        {
            "sub": "user-123",
            "email": "user@example.com",
            "role": "authenticated",
            "aud": "authenticated",
            "exp": int(time.time()) + 3600,
        },
    )

    current_user = dependencies.verify_supabase_access_token(token)

    assert current_user.id == "user-123"
    assert current_user.email == "user@example.com"
    assert current_user.role == "authenticated"


def test_verify_supabase_access_token_accepts_es256_jwks_token(monkeypatch):
    private_key = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(
        dependencies,
        "_fetch_supabase_jwks",
        lambda: {"keys": [_jwk_from_private_key(private_key, "test-key")]},
    )
    token = _make_es256_token(
        private_key,
        "test-key",
        {
            "sub": "user-123",
            "email": "user@example.com",
            "role": "authenticated",
            "aud": "authenticated",
            "exp": int(time.time()) + 3600,
        },
    )

    current_user = dependencies.verify_supabase_access_token(token)

    assert current_user.id == "user-123"
    assert current_user.email == "user@example.com"
    assert current_user.role == "authenticated"


def test_verify_supabase_access_token_rejects_bad_signature(monkeypatch):
    monkeypatch.setattr(dependencies, "SUPABASE_JWT_SECRET", "test-secret")
    token = _make_token(
        "wrong-secret",
        {
            "sub": "user-123",
            "aud": "authenticated",
            "exp": int(time.time()) + 3600,
        },
    )

    with pytest.raises(HTTPException) as exc:
        dependencies.verify_supabase_access_token(token)

    assert exc.value.status_code == 401


def test_verify_supabase_access_token_rejects_expired_token(monkeypatch):
    monkeypatch.setattr(dependencies, "SUPABASE_JWT_SECRET", "test-secret")
    token = _make_token(
        "test-secret",
        {
            "sub": "user-123",
            "aud": "authenticated",
            "exp": int(time.time()) - 1,
        },
    )

    with pytest.raises(HTTPException) as exc:
        dependencies.verify_supabase_access_token(token)

    assert exc.value.status_code == 401


def test_me_endpoint_returns_current_supabase_user(monkeypatch):
    monkeypatch.setattr(dependencies, "SUPABASE_JWT_SECRET", "test-secret")
    from app.services import user_service

    class FakeDatabase:
        def fetch_one(self, query, params=()):
            assert "from public.profiles" in query
            return {
                "id": params[0],
                "display_name": "Test User",
                "role": "user",
                "is_active": True,
                "created_at": "2026-06-11T00:00:00+00:00",
                "updated_at": "2026-06-11T00:00:00+00:00",
            }

    monkeypatch.setattr(user_service, "get_database", lambda: FakeDatabase())
    token = _make_token(
        "test-secret",
        {
            "sub": "user-123",
            "email": "user@example.com",
            "role": "authenticated",
            "aud": "authenticated",
            "exp": int(time.time()) + 3600,
        },
    )

    client = TestClient(app)
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "id": "user-123",
        "email": "user@example.com",
        "role": "user",
        "display_name": "Test User",
        "is_active": True,
        "auth_provider": "supabase",
    }
