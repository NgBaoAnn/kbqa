"""Sprint 1 backend API tests using an in-memory app-data fake.

Coverage:
  - Permission matrix: user / reviewer / admin for get_reviewer_user dependency.
  - Preferences: GET defaults, PATCH update, PATCH validation.
  - Trace endpoint: owner access, non-owner 403, reviewer access, admin access.
  - Version metadata: create_message merges version keys into assistant metadata.
  - Existing Sprint 1 contract tests (auth, conversations, messages).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
import types
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api_gateway import dependencies
from app.api_gateway.dependencies import CurrentUser
from app.main import app
from app.services import chat_service, user_service


# ── JWT helpers ────────────────────────────────────────────────────────────────


def _b64url(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _make_token(secret: str, user_id: str, email: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    claims = {
        "sub": user_id,
        "email": email,
        "role": "authenticated",
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
    }
    encoded_header = _b64url(json.dumps(header, separators=(",", ":")).encode())
    encoded_claims = _b64url(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{encoded_header}.{encoded_claims}".encode("ascii")
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_claims}.{_b64url(signature)}"


# ── Fake database ──────────────────────────────────────────────────────────────


class FakeDatabase:
    def __init__(self):
        self.profiles = {}
        self.conversations = {}
        self.messages = []
        self.preferences = {}  # user_id -> prefs dict (Sprint 1)
        self.executed = []
        self.now = "2026-06-12T00:00:00+00:00"

    # ── Profile helpers ─────────────────────────────────────────────────────

    def add_profile(self, user_id, *, role="user", is_active=True, display_name="Test User"):
        self.profiles[user_id] = {
            "id": user_id,
            "display_name": display_name,
            "role": role,
            "is_active": is_active,
            "created_at": self.now,
            "updated_at": self.now,
        }

    def add_conversation(self, user_id, *, conversation_id="conversation-1", title="Existing"):
        self.conversations[conversation_id] = {
            "id": conversation_id,
            "user_id": user_id,
            "title": title,
            "language": "vi",
            "created_at": self.now,
            "updated_at": self.now,
        }
        return conversation_id

    def add_assistant_message(self, conversation_id, *, metadata=None):
        """Add a pre-persisted assistant message for trace tests."""
        message_id = str(uuid4())
        self.messages.append({
            "id": message_id,
            "conversation_id": conversation_id,
            "role": "assistant",
            "content": "Test answer.",
            "response_type": "text",
            "data": None,
            "safety": {"level": "normal", "requires_emergency_notice": False, "disclaimer": "Ref."},
            "metadata": metadata or {},
            "owner_id": self.conversations[conversation_id]["user_id"],
            "created_at": self.now,
        })
        return message_id

    # ── Core DB interface ───────────────────────────────────────────────────

    def fetch_one(self, query, params=()):
        query_l = " ".join(query.lower().split())

        if "from public.profiles" in query_l and "insert into" not in query_l:
            return self.profiles.get(params[0])

        if "insert into public.profiles" in query_l:
            user_id, display_name = params
            self.add_profile(user_id, display_name=display_name)
            return self.profiles[user_id]

        if "insert into public.conversations" in query_l:
            user_id, title, language = params
            conversation_id = str(uuid4())
            row = {
                "id": conversation_id,
                "user_id": user_id,
                "title": title,
                "language": language,
                "created_at": self.now,
                "updated_at": self.now,
            }
            self.conversations[conversation_id] = row
            return self._conversation_row(row)

        if "from public.conversations" in query_l and "where id = %s and user_id = %s" in query_l:
            conversation_id, user_id = params
            row = self.conversations.get(conversation_id)
            if row and row["user_id"] == user_id:
                if "title" not in query_l:
                    return {"id": row["id"]}
                return self._conversation_row(row)
            return None

        if "insert into public.messages" in query_l:
            return self._insert_message(query_l, params)

        # Sprint 1: user_preferences
        if "from public.user_preferences" in query_l and "insert into" not in query_l and "update" not in query_l:
            user_id = params[0]
            return self.preferences.get(user_id)

        if "insert into public.user_preferences" in query_l:
            user_id, language, explanation_level, answer_style = params
            pref_id = str(uuid4())
            row = {
                "id": pref_id,
                "user_id": user_id,
                "language": language,
                "explanation_level": explanation_level,
                "answer_style": answer_style,
                "created_at": self.now,
                "updated_at": self.now,
            }
            self.preferences[user_id] = row
            return row

        if "update public.user_preferences" in query_l:
            # Dynamic SET clause: extract field values from params
            # Params: [field_values..., user_id]
            user_id = params[-1]
            row = self.preferences.get(user_id)
            if row is None:
                return None
            # Extract SET fields from the query
            import re
            field_matches = re.findall(r"(\w+) = %s", query_l)
            for i, field in enumerate(field_matches):
                if field in ("language", "explanation_level", "answer_style"):
                    row[field] = params[i]
            row["updated_at"] = self.now
            self.preferences[user_id] = row
            return row

        # Sprint 1: trace query — join messages + conversations
        if ("from public.messages" in query_l and "join public.conversations" in query_l
                and "role = 'assistant'" in query_l):
            message_id = params[0]
            for msg in self.messages:
                if msg["id"] == message_id and msg["role"] == "assistant":
                    conv = self.conversations.get(msg["conversation_id"], {})
                    return {
                        "id": msg["id"],
                        "metadata": msg.get("metadata", {}),
                        "owner_id": conv.get("user_id", ""),
                    }
            return None

        return None

    def fetch_all(self, query, params=()):
        query_l = " ".join(query.lower().split())
        if "from public.conversations" in query_l:
            user_id = params[0]
            return [
                self._conversation_row(row)
                for row in self.conversations.values()
                if row["user_id"] == user_id
            ]

        if "from public.messages" in query_l:
            conversation_id = params[0]
            return [
                {k: v for k, v in row.items() if k not in ("conversation_id", "owner_id")}
                for row in self.messages
                if row["conversation_id"] == conversation_id
            ]

        return []

    def execute(self, query, params=()):
        self.executed.append((query, params))

    # ── Transaction support ────────────────────────────────────────────────

    class _FakeTx:
        pass

    def transaction(self):
        from contextlib import contextmanager

        @contextmanager
        def _ctx():
            yield self._FakeTx()

        return _ctx()

    def fetch_one_in_tx(self, _conn, query, params=()):
        return self.fetch_one(query, params)

    def execute_in_tx(self, _conn, query, params=()):
        self.executed.append((query, params))

    def execute_many_in_tx(self, _conn, query, rows):
        for row in rows:
            self.executed.append((query, row))

    # ── Internal helpers ───────────────────────────────────────────────────

    def _conversation_row(self, row):
        return {
            "id": row["id"],
            "title": row["title"],
            "language": row["language"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _insert_message(self, query_l, params):
        message_id = str(uuid4())
        if "'assistant'" in query_l:
            if len(params) == 6:
                conversation_id, content, response_type, data_json, safety_json, metadata_json = params
            else:
                conversation_id, content, safety_json, metadata_json = params
                response_type = "text"
                data_json = "null"
            row = {
                "id": message_id,
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": content,
                "response_type": response_type,
                "data": json.loads(data_json),
                "safety": json.loads(safety_json),
                "metadata": json.loads(metadata_json),
                "owner_id": self.conversations.get(conversation_id, {}).get("user_id", ""),
                "created_at": self.now,
            }
        else:
            conversation_id, content, metadata = params
            row = {
                "id": message_id,
                "conversation_id": conversation_id,
                "role": "user",
                "content": content,
                "response_type": None,
                "data": None,
                "safety": None,
                "metadata": json.loads(metadata),
                "owner_id": self.conversations.get(conversation_id, {}).get("user_id", ""),
                "created_at": self.now,
            }
        self.messages.append(row)
        return {k: v for k, v in row.items() if k not in ("conversation_id", "owner_id")}


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def api(monkeypatch):
    fake_db = FakeDatabase()
    monkeypatch.setattr(dependencies, "SUPABASE_JWT_SECRET", "test-secret")
    monkeypatch.setattr(user_service, "get_database", lambda: fake_db)
    monkeypatch.setattr(chat_service, "get_database", lambda: fake_db)
    return TestClient(app), fake_db


def _auth_headers(user_id="user-1", email="user@example.com"):
    token = _make_token("test-secret", user_id, email)
    return {"Authorization": f"Bearer {token}"}


# ── Existing Sprint 1 auth tests ──────────────────────────────────────────────


def test_protected_endpoint_requires_bearer_token(api):
    client, _ = api

    response = client.get("/api/v1/me")

    assert response.status_code == 401


def test_inactive_user_cannot_access_protected_api(api):
    client, fake_db = api
    fake_db.add_profile("user-1", is_active=False)

    response = client.get("/api/v1/me", headers=_auth_headers())

    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "USER_INACTIVE"


# ── Sprint 1: Permission matrix ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reviewer_dependency_allows_reviewer_role():
    reviewer = CurrentUser(id="rev-1", email="r@example.com", role="reviewer", claims={})
    result = await dependencies.get_reviewer_user(reviewer)
    assert result.role == "reviewer"


@pytest.mark.asyncio
async def test_reviewer_dependency_allows_admin_role():
    admin = CurrentUser(id="admin-1", email="a@example.com", role="admin", claims={})
    result = await dependencies.get_reviewer_user(admin)
    assert result.role == "admin"


@pytest.mark.asyncio
async def test_reviewer_dependency_rejects_user_role():
    user = CurrentUser(id="user-1", email="u@example.com", role="user", claims={})
    with pytest.raises(HTTPException) as exc:
        await dependencies.get_reviewer_user(user)
    assert exc.value.status_code == 403
    assert exc.value.detail["error_code"] == "REVIEWER_REQUIRED"


@pytest.mark.asyncio
async def test_admin_dependency_requires_profile_admin_role():
    user = CurrentUser(id="user-1", email="user@example.com", role="user", claims={})
    with pytest.raises(HTTPException) as exc:
        await dependencies.get_admin_user(user)
    assert exc.value.status_code == 403


# ── Sprint 1: Preferences ─────────────────────────────────────────────────────


def test_get_preferences_returns_defaults(api, monkeypatch):
    from app.services import preference_service

    client, fake_db = api
    fake_db.add_profile("user-1")
    monkeypatch.setattr(preference_service, "get_database", lambda: fake_db)

    response = client.get("/api/v1/me/preferences", headers=_auth_headers())

    assert response.status_code == 200
    data = response.json()
    assert data["language"] == "vi"
    assert data["explanation_level"] == "general"
    assert data["answer_style"] == "concise"
    assert data["user_id"] == "user-1"


def test_patch_preferences_updates_fields(api, monkeypatch):
    from app.services import preference_service

    client, fake_db = api
    fake_db.add_profile("user-1")
    monkeypatch.setattr(preference_service, "get_database", lambda: fake_db)

    # First GET to seed defaults
    client.get("/api/v1/me/preferences", headers=_auth_headers())

    response = client.patch(
        "/api/v1/me/preferences",
        headers=_auth_headers(),
        json={"language": "en", "answer_style": "detailed"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["language"] == "en"
    assert data["answer_style"] == "detailed"
    assert data["explanation_level"] == "general"  # unchanged


def test_patch_preferences_ignores_unset_fields(api, monkeypatch):
    from app.services import preference_service

    client, fake_db = api
    fake_db.add_profile("user-1")
    monkeypatch.setattr(preference_service, "get_database", lambda: fake_db)

    # Seed defaults
    client.get("/api/v1/me/preferences", headers=_auth_headers())

    response = client.patch(
        "/api/v1/me/preferences",
        headers=_auth_headers(),
        json={"explanation_level": "expert"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["explanation_level"] == "expert"
    assert data["language"] == "vi"  # unchanged


# ── Sprint 1: Trace endpoint ──────────────────────────────────────────────────


def test_trace_endpoint_owner_can_access(api, monkeypatch):
    from app.services import preference_service

    client, fake_db = api
    fake_db.add_profile("user-1")
    conv_id = fake_db.add_conversation("user-1", conversation_id="conv-owner-1")
    msg_id = fake_db.add_assistant_message(
        conv_id,
        metadata={
            "prompt_version": "v1.0.0",
            "model_name": "llama3:8b",
            "kg_version": "v1.0.0",
            "pipeline_version": "v1.0.0",
            "engine": "cypher_direct",
        },
    )
    monkeypatch.setattr(preference_service, "get_database", lambda: fake_db)

    response = client.get(f"/api/v1/messages/{msg_id}/trace", headers=_auth_headers("user-1"))

    assert response.status_code == 200
    data = response.json()
    assert data["message_id"] == msg_id
    assert data["version_metadata"]["prompt_version"] == "v1.0.0"
    assert data["version_metadata"]["model_name"] == "llama3:8b"


def test_trace_endpoint_non_owner_user_gets_403(api, monkeypatch):
    from app.services import preference_service

    client, fake_db = api
    fake_db.add_profile("user-1")
    fake_db.add_profile("user-2")
    conv_id = fake_db.add_conversation("user-1", conversation_id="conv-owner-2")
    msg_id = fake_db.add_assistant_message(conv_id)
    monkeypatch.setattr(preference_service, "get_database", lambda: fake_db)

    # user-2 does not own this conversation
    response = client.get(
        f"/api/v1/messages/{msg_id}/trace",
        headers=_auth_headers("user-2", "two@example.com"),
    )

    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "TRACE_ACCESS_DENIED"


def test_trace_endpoint_reviewer_can_access(api, monkeypatch):
    from app.services import preference_service

    client, fake_db = api
    fake_db.add_profile("user-1")
    fake_db.add_profile("rev-1", role="reviewer")
    conv_id = fake_db.add_conversation("user-1", conversation_id="conv-rev-1")
    msg_id = fake_db.add_assistant_message(conv_id)
    monkeypatch.setattr(preference_service, "get_database", lambda: fake_db)

    response = client.get(
        f"/api/v1/messages/{msg_id}/trace",
        headers=_auth_headers("rev-1", "reviewer@example.com"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message_id"] == msg_id


def test_trace_endpoint_admin_can_access(api, monkeypatch):
    from app.services import preference_service

    client, fake_db = api
    fake_db.add_profile("user-1")
    fake_db.add_profile("admin-1", role="admin")
    conv_id = fake_db.add_conversation("user-1", conversation_id="conv-admin-1")
    msg_id = fake_db.add_assistant_message(conv_id)
    monkeypatch.setattr(preference_service, "get_database", lambda: fake_db)

    response = client.get(
        f"/api/v1/messages/{msg_id}/trace",
        headers=_auth_headers("admin-1", "admin@example.com"),
    )

    assert response.status_code == 200


def test_trace_endpoint_missing_message_returns_404(api, monkeypatch):
    from app.services import preference_service

    client, fake_db = api
    fake_db.add_profile("user-1")
    monkeypatch.setattr(preference_service, "get_database", lambda: fake_db)

    response = client.get(
        "/api/v1/messages/nonexistent-id/trace",
        headers=_auth_headers("user-1"),
    )

    assert response.status_code == 404


# ── Sprint 1: Version metadata in assistant message ────────────────────────────


def test_version_metadata_in_assistant_message(api, monkeypatch):
    """create_message should merge PROMPT_VERSION, MODEL_NAME, etc. into metadata."""
    from app.models.contracts import (
        AIServiceResult, ChatMetadata, ChatSource, MessageCreateRequest, SafetyPayload,
    )
    from app.services import chat_service as _cs
    from app.services import preference_service, versioning_service

    client, fake_db = api
    fake_db.add_profile("user-1")
    conversation_id = fake_db.add_conversation("user-1")
    monkeypatch.setattr(preference_service, "get_database", lambda: fake_db)

    # Patch version constants so we can assert specific values
    monkeypatch.setattr(versioning_service, "PROMPT_VERSION", "v2.0.0", raising=False)
    monkeypatch.setattr(versioning_service, "MODEL_NAME", "test-model", raising=False)
    monkeypatch.setattr(versioning_service, "KG_VERSION", "v3.0.0", raising=False)
    monkeypatch.setattr(versioning_service, "PIPELINE_VERSION", "v4.0.0", raising=False)

    ai_result = AIServiceResult(
        answer="Test answer.",
        response_type="text",
        data=None,
        sources=[],
        safety=SafetyPayload(level="normal", requires_emergency_notice=False, disclaimer="Ref."),
        suggested_questions=[],
        metadata=ChatMetadata(
            engine="lightrag", query_mode="mix", execution_time_ms=50.0, source_count=0, cypher=None
        ),
        raw_engine_metadata={"engine": "lightrag"},
    )
    mock_ai = types.SimpleNamespace(answer_question=AsyncMock(return_value=ai_result))

    result = asyncio.run(
        _cs.create_message(
            user_id="user-1",
            conversation_id=conversation_id,
            payload=MessageCreateRequest(question="test"),
            database=fake_db,
            ai_service_module=mock_ai,
        )
    )

    assert result.status == "success"
    assistant_msg = next(m for m in fake_db.messages if m["role"] == "assistant")
    assert assistant_msg["metadata"]["prompt_version"] == "v2.0.0"
    assert assistant_msg["metadata"]["model_name"] == "test-model"
    assert assistant_msg["metadata"]["kg_version"] == "v3.0.0"
    assert assistant_msg["metadata"]["pipeline_version"] == "v4.0.0"


# ── Existing conversation + message tests ─────────────────────────────────────


def test_create_list_get_conversation(api):
    client, fake_db = api
    fake_db.add_profile("user-1")

    create_response = client.post(
        "/api/v1/conversations",
        headers=_auth_headers(),
        json={"title": "Tư vấn đau đầu", "language": "vi"},
    )
    assert create_response.status_code == 201
    conversation_id = create_response.json()["id"]

    list_response = client.get("/api/v1/conversations", headers=_auth_headers())
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [conversation_id]

    detail_response = client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers=_auth_headers(),
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["conversation"]["id"] == conversation_id
    assert detail_response.json()["messages"] == []


def test_user_cannot_read_another_users_conversation(api):
    client, fake_db = api
    fake_db.add_profile("user-1")
    fake_db.add_profile("user-2")
    fake_db.add_conversation("user-2", conversation_id="conversation-2")

    response = client.get(
        "/api/v1/conversations/conversation-2",
        headers=_auth_headers("user-1", "one@example.com"),
    )

    assert response.status_code == 404


def test_create_message_persists_user_and_assistant_messages(api, monkeypatch):
    """Sprint 2: create_message calls real AI adapter and persists both message rows."""
    from app.models.contracts import (
        AIServiceResult, ChatMetadata, ChatSource, MessageCreateRequest, SafetyPayload,
    )
    from app.services import chat_service as _cs

    client, fake_db = api
    fake_db.add_profile("user-1")
    conversation_id = fake_db.add_conversation("user-1")

    ai_result = AIServiceResult(
        answer="AI trả lời test.",
        response_type="text",
        data=None,
        sources=[
            ChatSource(id=str(uuid4()), source_type="other", title="T",
                       snippet="s", rank=1, metadata={"engine": "lightrag"})
        ],
        safety=SafetyPayload(level="normal", requires_emergency_notice=False,
                             disclaimer="Tham khảo."),
        suggested_questions=[],
        metadata=ChatMetadata(engine="lightrag", query_mode="mix",
                              execution_time_ms=80.0, source_count=1, cypher=None),
        raw_engine_metadata={"engine": "lightrag"},
    )
    mock_ai_module = types.SimpleNamespace(answer_question=AsyncMock(return_value=ai_result))

    result = asyncio.run(
        _cs.create_message(
            user_id="user-1",
            conversation_id=conversation_id,
            payload=MessageCreateRequest(question="Đau đầu có nguy hiểm không?"),
            database=fake_db,
            ai_service_module=mock_ai_module,
        )
    )

    assert result.status == "success"
    assert result.response_type == "text"
    assert result.metadata.engine == "lightrag"
    # Both user and assistant messages persisted
    assert [m["role"] for m in fake_db.messages] == ["user", "assistant"]
    assert fake_db.messages[1]["safety"]["level"] == "normal"
