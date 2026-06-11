"""Sprint 1 backend API tests using an in-memory app-data fake."""

import base64
import hashlib
import hmac
import json
import time
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api_gateway import dependencies
from app.api_gateway.dependencies import CurrentUser
from app.main import app
from app.services import chat_service, user_service


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


class FakeDatabase:
    def __init__(self):
        self.profiles = {}
        self.conversations = {}
        self.messages = []
        self.executed = []
        self.now = "2026-06-11T00:00:00+00:00"

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
                {k: v for k, v in row.items() if k != "conversation_id"}
                for row in self.messages
                if row["conversation_id"] == conversation_id
            ]

        return []

    def execute(self, query, params=()):
        self.executed.append((query, params))

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
            # Sprint 2 signature: conv_id, content, response_type, data_json, safety_json, metadata_json
            # Sprint 1 would have passed 4 params; accept both via len check.
            if len(params) == 6:
                conversation_id, content, response_type, data_json, safety_json, metadata_json = params
            else:
                # Legacy 4-param fallback (kept for safety)
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
                "created_at": self.now,
            }
        self.messages.append(row)
        return {k: v for k, v in row.items() if k != "conversation_id"}


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


@pytest.mark.asyncio
async def test_admin_dependency_requires_profile_admin_role():
    user = CurrentUser(
        id="user-1",
        email="user@example.com",
        role="user",
        claims={},
    )

    with pytest.raises(HTTPException) as exc:
        await dependencies.get_admin_user(user)

    assert exc.value.status_code == 403


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
    import asyncio
    import types
    from unittest.mock import AsyncMock
    from uuid import uuid4 as _uuid4

    from app.models.contracts import (
        AIServiceResult, ChatMetadata, ChatSource, MessageCreateRequest, SafetyPayload
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
            ChatSource(id=str(_uuid4()), source_type="other", title="T",
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

    # Test the service function directly with injected mock AI (avoids HTTP pipeline)
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
    assert result.metadata.engine == "lightrag"  # real AI engine, not "mock"
    # Both user and assistant messages persisted (exactly 2, not 4)
    assert [m["role"] for m in fake_db.messages] == ["user", "assistant"]
    assert fake_db.messages[1]["safety"]["level"] == "normal"
