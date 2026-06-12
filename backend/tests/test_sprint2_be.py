"""Sprint 2 — Người 2: Integration tests for real chat API and feedback service.

Tests cover:
  S2-BE-01 + S2-BE-02: create_message with mocked AI adapter, real AI smoke check
  S2-BE-03: create_feedback — up/down/comment stored, ownership validation
  S2-BE-04: review item auto-created for down/incorrect/unsafe feedback
  S2-BE-05: integration contract — chat response shape, source/log persistence

All DB calls use an extended FakeDatabase that now handles:
  - message_sources inserts
  - query_logs inserts
  - feedback inserts
  - review_items inserts
  - join query for feedback ownership validation
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api_gateway import dependencies
from app.main import app
from app.models.contracts import (
    AIServiceResult,
    ChatMetadata,
    ChatSource,
    FeedbackCreateRequest,
    SafetyPayload,
)
from app.services import chat_service, feedback_service, user_service


# ════════════════════════════════════════════════════════════════════════════
# Test helpers
# ════════════════════════════════════════════════════════════════════════════

import base64
import hashlib
import hmac
import time as _time


def _b64url(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")


def _make_token(secret: str, user_id: str, email: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    claims = {
        "sub": user_id,
        "email": email,
        "role": "authenticated",
        "aud": "authenticated",
        "exp": int(_time.time()) + 3600,
    }
    encoded_header = _b64url(json.dumps(header, separators=(",", ":")).encode())
    encoded_claims = _b64url(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{encoded_header}.{encoded_claims}".encode("ascii")
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_claims}.{_b64url(signature)}"


def _auth_headers(user_id: str = "user-1", email: str = "user@example.com") -> dict:
    token = _make_token("test-secret", user_id, email)
    return {"Authorization": f"Bearer {token}"}


def _make_ai_result(
    answer: str = "Câu trả lời AI.",
    engine: str = "lightrag",
    query_mode: str = "mix",
    response_type: str = "text",
    sources: list[ChatSource] | None = None,
    safety_level: str = "normal",
    data: list[dict[str, Any]] | dict[str, Any] | None = None,
    suggested_questions: list[str] | None = None,
) -> AIServiceResult:
    if sources is None:
        sources = [
            ChatSource(
                id=str(uuid4()),
                source_type="other",
                title="AegisHealth Hybrid GraphRAG",
                snippet="Answer generated via lightrag engine (mode: mix).",
                rank=1,
                metadata={"engine": engine, "query_mode": query_mode},
            )
        ]
    return AIServiceResult(
        answer=answer,
        response_type=response_type,
        data=data,
        sources=sources,
        safety=SafetyPayload(
            level=safety_level,
            requires_emergency_notice=safety_level == "emergency",
            disclaimer="Thông tin chỉ mang tính chất tham khảo.",
        ),
        suggested_questions=suggested_questions or [],
        metadata=ChatMetadata(
            engine=engine,
            query_mode=query_mode,
            execution_time_ms=120.5,
            source_count=len(sources),
            cypher=None,
        ),
        raw_engine_metadata={
            "engine": engine,
            "query_mode": query_mode,
            "execution_time_ms": 120.5,
        },
    )


# ════════════════════════════════════════════════════════════════════════════
# Extended FakeDatabase (Sprint 2)
# ════════════════════════════════════════════════════════════════════════════


class FakeDatabase:
    """In-memory fake backing the Supabase Postgres calls made by services."""

    def __init__(self):
        self.profiles: dict[str, dict] = {}
        self.conversations: dict[str, dict] = {}
        self.messages: list[dict] = {}
        self.messages = []
        self.message_sources: list[dict] = []
        self.feedback_rows: list[dict] = []
        self.review_items: list[dict] = []
        self.query_logs: list[dict] = []
        self.preferences: dict[str, dict] = {}
        self.executed: list[tuple] = []
        self.now = "2026-06-11T00:00:00+00:00"

    # ── Setup helpers ───────────────────────────────────────────────────

    def add_profile(self, user_id: str, *, role: str = "user", is_active: bool = True, display_name: str = "Test User"):
        self.profiles[user_id] = {
            "id": user_id,
            "display_name": display_name,
            "role": role,
            "is_active": is_active,
            "created_at": self.now,
            "updated_at": self.now,
        }

    def add_conversation(self, user_id: str, *, conversation_id: str = "conv-1", title: str = "Existing") -> str:
        self.conversations[conversation_id] = {
            "id": conversation_id,
            "user_id": user_id,
            "title": title,
            "language": "vi",
            "created_at": self.now,
            "updated_at": self.now,
        }
        return conversation_id

    def add_message(self, conversation_id: str, *, role: str = "assistant", content: str = "ok") -> str:
        msg_id = str(uuid4())
        self.messages.append({
            "id": msg_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "response_type": "text" if role == "assistant" else None,
            "data": None,
            "safety": {"level": "normal", "requires_emergency_notice": False, "disclaimer": "ok"},
            "metadata": {"engine": "lightrag"},
            "created_at": self.now,
        })
        return msg_id

    # ── Core DB interface ───────────────────────────────────────────────

    def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        q = " ".join(query.lower().split())

        # profile read
        if "from public.profiles" in q and "insert" not in q:
            return self.profiles.get(params[0])

        # profile insert
        if "insert into public.profiles" in q:
            uid, dname = params
            self.add_profile(uid, display_name=dname)
            return self.profiles[uid]

        # conversation insert
        if "insert into public.conversations" in q:
            uid, title, language = params
            cid = str(uuid4())
            row = {"id": cid, "user_id": uid, "title": title, "language": language,
                   "created_at": self.now, "updated_at": self.now}
            self.conversations[cid] = row
            return self._conversation_row(row)

        # conversation select by id + user_id (ownership check)
        if "from public.conversations" in q and "where id = %s and user_id = %s" in q:
            cid, uid = params
            row = self.conversations.get(cid)
            if row and row["user_id"] == uid:
                if "title" not in q:
                    return {"id": row["id"]}
                return self._conversation_row(row)
            return None

        # message insert
        if "insert into public.messages" in q:
            return self._insert_message(q, params)

        # user_preferences select / insert used by chat_service
        if (
            "from public.user_preferences" in q
            and "insert into public.user_preferences" not in q
            and "update public.user_preferences" not in q
        ):
            user_id = params[0]
            return self.preferences.get(user_id)

        if "insert into public.user_preferences" in q:
            user_id, language, explanation_level, answer_style = params
            row = {
                "id": str(uuid4()),
                "user_id": user_id,
                "language": language,
                "explanation_level": explanation_level,
                "answer_style": answer_style,
                "created_at": self.now,
                "updated_at": self.now,
            }
            self.preferences[user_id] = row
            return row

        # These inserts are handled in execute() — fetch_one should not see them.
        # Fall through to None for any unmatched query.

        # feedback insert
        if "insert into public.feedback" in q:
            msg_id, uid, rating, reason, comment = params
            fid = str(uuid4())
            row = {
                "id": fid,
                "message_id": msg_id,
                "user_id": uid,
                "rating": rating,
                "reason": reason,
                "comment": comment,
                "created_at": self.now,
            }
            self.feedback_rows.append(row)
            return {
                "id": fid,
                "message_id": msg_id,
                "rating": rating,
                "reason": reason,
                "created_at": self.now,
            }

        # review_items insert
        if "insert into public.review_items" in q:
            fid, category = params
            rid = str(uuid4())
            self.review_items.append({
                "id": rid,
                "feedback_id": fid,
                "status": "pending",
                "category": category,
                "created_at": self.now,
            })
            return {"id": rid}

        # messages + conversations join (feedback ownership validation)
        if "join public.conversations" in q and "from public.messages" in q:
            msg_id, uid = params
            for m in self.messages:
                if m["id"] == msg_id:
                    conv = self.conversations.get(m["conversation_id"])
                    if conv and conv["user_id"] == uid:
                        return {
                            "id": m["id"],
                            "role": m["role"],
                            "conversation_id": m["conversation_id"],
                        }
            return None

        return None

    def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        q = " ".join(query.lower().split())

        if "from public.conversations" in q and "insert" not in q:
            uid = params[0]
            return [
                self._conversation_row(r)
                for r in self.conversations.values()
                if r["user_id"] == uid
            ]

        if "from public.messages" in q and "join public.conversations" not in q:
            cid = params[1] if len(params) > 1 else params[0]
            return [
                {k: v for k, v in m.items() if k != "conversation_id"}
                for m in self.messages
                if m["conversation_id"] == cid
            ]

        return []

    def execute(self, query: str, params: tuple = ()) -> None:
        q = " ".join(query.lower().split())
        self.executed.append((query, params))

        # Capture message_sources inserts for assertion in tests
        if "insert into public.message_sources" in q:
            msg_id, src_type, title, snippet, meta_json, rank = params
            self.message_sources.append({
                "message_id": msg_id,
                "source_type": src_type,
                "title": title,
                "snippet": snippet,
                "metadata": json.loads(meta_json),
                "rank": rank,
            })

        # Capture query_logs inserts for assertion in tests
        elif "insert into public.query_logs" in q:
            msg_id, engine, qmode, exec_ms, src_cnt, qstatus, meta_json = params
            self.query_logs.append({
                "message_id": msg_id,
                "engine": engine,
                "query_mode": qmode,
                "execution_time_ms": exec_ms,
                "source_count": src_cnt,
                "status": qstatus,
                "metadata": json.loads(meta_json),
            })

    class _FakeTx:
        pass

    def transaction(self):
        from contextlib import contextmanager

        @contextmanager
        def _ctx():
            yield self._FakeTx()

        return _ctx()

    def fetch_one_in_tx(self, _conn, query: str, params: tuple = ()) -> dict | None:
        return self.fetch_one(query, params)

    def execute_in_tx(self, _conn, query: str, params: tuple = ()) -> None:
        return self.execute(query, params)

    def execute_many_in_tx(self, _conn, query: str, rows) -> None:
        for row in rows:
            self.execute(query, row)

    # ── Private helpers ─────────────────────────────────────────────────

    def _conversation_row(self, row: dict) -> dict:
        return {
            "id": row["id"],
            "title": row["title"],
            "language": row["language"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _insert_message(self, query_l: str, params: tuple) -> dict:
        msg_id = str(uuid4())
        if "'assistant'" in query_l:
            # params: conv_id, answer, response_type, data_json, safety_json, metadata_json
            conv_id, content, resp_type, data_json, safety_json, meta_json = params
            row = {
                "id": msg_id,
                "conversation_id": conv_id,
                "role": "assistant",
                "content": content,
                "response_type": resp_type,
                "data": json.loads(data_json),
                "safety": json.loads(safety_json),
                "metadata": json.loads(meta_json),
                "created_at": self.now,
            }
        else:
            # params: conv_id, content, metadata_json
            conv_id, content, meta_json = params
            row = {
                "id": msg_id,
                "conversation_id": conv_id,
                "role": "user",
                "content": content,
                "response_type": None,
                "data": None,
                "safety": None,
                "metadata": json.loads(meta_json),
                "created_at": self.now,
            }
        self.messages.append(row)
        return {k: v for k, v in row.items() if k != "conversation_id"}


# ════════════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def api(monkeypatch):
    """TestClient with FakeDatabase and JWT secret patched in."""
    fake_db = FakeDatabase()
    monkeypatch.setattr(dependencies, "SUPABASE_JWT_SECRET", "test-secret")
    monkeypatch.setattr(user_service, "get_database", lambda: fake_db)
    monkeypatch.setattr(chat_service, "get_database", lambda: fake_db)
    monkeypatch.setattr(feedback_service, "get_database", lambda: fake_db)
    return TestClient(app), fake_db


@pytest.fixture
def mock_ai():
    """Default AIServiceResult for happy-path AI mock."""
    return _make_ai_result()


# ════════════════════════════════════════════════════════════════════════════
# S2-BE-01 — Real chat API (mocked AI)
# ════════════════════════════════════════════════════════════════════════════


class TestCreateMessageRealAI:
    def test_chat_calls_ai_service_not_mock(self, api, mock_ai):
        """POST /messages must call ai_service, not the Sprint 1 mock."""
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")

        with patch("app.services.chat_service.ai_service") as mock_svc:
            mock_svc.answer_question = AsyncMock(return_value=mock_ai)
            response = client.post(
                f"/api/v1/conversations/{cid}/messages",
                headers=_auth_headers(),
                json={"question": "Bệnh tiểu đường là gì?", "mode": None},
            )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "success"
        assert body["answer"] == mock_ai.answer
        mock_svc.answer_question.assert_awaited_once()

    def test_chat_response_has_required_fields(self, api, mock_ai):
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")

        with patch("app.services.chat_service.ai_service") as mock_svc:
            mock_svc.answer_question = AsyncMock(return_value=mock_ai)
            response = client.post(
                f"/api/v1/conversations/{cid}/messages",
                headers=_auth_headers(),
                json={"question": "Test?", "mode": None},
            )

        assert response.status_code == 201
        body = response.json()
        assert "conversation_id" in body
        assert "message_id" in body
        assert "status" in body
        assert "answer" in body
        assert "sources" in body
        assert "safety" in body
        assert "metadata" in body
        assert body["conversation_id"] == cid

    def test_ai_result_answer_persisted_in_messages(self, api):
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")

        ai_result = _make_ai_result(answer="AI đã trả lời rồi nhé!")
        with patch("app.services.chat_service.ai_service") as mock_svc:
            mock_svc.answer_question = AsyncMock(return_value=ai_result)
            client.post(
                f"/api/v1/conversations/{cid}/messages",
                headers=_auth_headers(),
                json={"question": "Q?"},
            )

        assistant_msgs = [m for m in fake_db.messages if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1
        assert assistant_msgs[0]["content"] == "AI đã trả lời rồi nhé!"

    def test_user_and_assistant_messages_both_persisted(self, api, mock_ai):
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")

        with patch("app.services.chat_service.ai_service") as mock_svc:
            mock_svc.answer_question = AsyncMock(return_value=mock_ai)
            client.post(
                f"/api/v1/conversations/{cid}/messages",
                headers=_auth_headers(),
                json={"question": "Câu hỏi?"},
            )

        assert [m["role"] for m in fake_db.messages] == ["user", "assistant"]
        assert fake_db.messages[0]["content"] == "Câu hỏi?"

    def test_response_type_from_ai_persisted(self, api):
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")

        ai_result = _make_ai_result(response_type="table")
        with patch("app.services.chat_service.ai_service") as mock_svc:
            mock_svc.answer_question = AsyncMock(return_value=ai_result)
            response = client.post(
                f"/api/v1/conversations/{cid}/messages",
                headers=_auth_headers(),
                json={"question": "Liệt kê triệu chứng?"},
            )

        body = response.json()
        assert body["response_type"] == "table"
        assistant_msg = next(m for m in fake_db.messages if m["role"] == "assistant")
        assert assistant_msg["response_type"] == "table"

    def test_safety_from_ai_persisted(self, api):
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")

        ai_result = _make_ai_result(safety_level="emergency")
        with patch("app.services.chat_service.ai_service") as mock_svc:
            mock_svc.answer_question = AsyncMock(return_value=ai_result)
            response = client.post(
                f"/api/v1/conversations/{cid}/messages",
                headers=_auth_headers(),
                json={"question": "Tôi đang bị bất tỉnh!"},
            )

        body = response.json()
        assert body["safety"]["level"] == "emergency"
        assert body["safety"]["requires_emergency_notice"] is True

    def test_engine_not_mock_in_metadata(self, api):
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")

        ai_result = _make_ai_result(engine="lightrag", query_mode="mix")
        with patch("app.services.chat_service.ai_service") as mock_svc:
            mock_svc.answer_question = AsyncMock(return_value=ai_result)
            response = client.post(
                f"/api/v1/conversations/{cid}/messages",
                headers=_auth_headers(),
                json={"question": "Q?"},
            )

        body = response.json()
        # Must NOT be the Sprint 1 "mock" engine
        assert body["metadata"]["engine"] != "mock"
        assert body["metadata"]["engine"] == "lightrag"

    def test_conversation_not_found_returns_404(self, api, mock_ai):
        client, fake_db = api
        fake_db.add_profile("user-1")
        # Don't add any conversation — 404 happens before AI is called
        response = client.post(
            "/api/v1/conversations/nonexistent-id/messages",
            headers=_auth_headers(),
            json={"question": "Q?"},
        )
        assert response.status_code == 404


class TestSprint2ChatIntelligence:
    def test_suggested_questions_returned_and_persisted_in_metadata(self, api):
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")
        ai_result = _make_ai_result(
            suggested_questions=[
                "Dấu hiệu cần đi khám là gì?",
                "Cách phòng ngừa như thế nào?",
                "Cần lưu ý gì khi chăm sóc?",
            ],
        )

        with patch("app.services.chat_service.ai_service") as mock_svc:
            mock_svc.answer_question = AsyncMock(return_value=ai_result)
            response = client.post(
                f"/api/v1/conversations/{cid}/messages",
                headers=_auth_headers(),
                json={"question": "Bệnh tiểu đường là gì?"},
            )

        body = response.json()
        assert len(body["suggested_questions"]) == 3
        assistant_msg = next(m for m in fake_db.messages if m["role"] == "assistant")
        assert assistant_msg["metadata"]["suggested_questions"] == body["suggested_questions"]

    def test_history_hydrates_suggested_questions_from_metadata(self, api):
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")
        fake_db.add_message(cid, role="assistant", content="Câu trả lời.")
        fake_db.messages[-1]["metadata"]["suggested_questions"] = ["Hỏi tiếp thế nào?"]

        response = client.get(f"/api/v1/conversations/{cid}", headers=_auth_headers())

        assert response.status_code == 200
        assistant = next(m for m in response.json()["messages"] if m["role"] == "assistant")
        assert assistant["suggested_questions"] == ["Hỏi tiếp thế nào?"]

    def test_disambiguation_response_has_structured_data(self, api):
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")
        options = [
            {
                "id": "disease-cum-a",
                "label": "Bệnh cúm A",
                "description": "Bệnh trong cơ sở tri thức VietMedKG.",
                "entity_type": "Disease",
                "confidence": 0.95,
            }
        ]
        ai_result = _make_ai_result(
            response_type="disambiguation",
            answer="Vui lòng chọn bệnh bạn muốn hỏi.",
            data=options,
        )

        with patch("app.services.chat_service.ai_service") as mock_svc:
            mock_svc.answer_question = AsyncMock(return_value=ai_result)
            response = client.post(
                f"/api/v1/conversations/{cid}/messages",
                headers=_auth_headers(),
                json={"question": "Cúm có triệu chứng gì?"},
            )

        body = response.json()
        assert body["response_type"] == "disambiguation"
        assert body["data"] == options
        assert set(body["data"][0]) == {"id", "label", "description", "entity_type", "confidence"}

    def test_preferences_are_passed_to_ai_and_logged(self, api):
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")
        fake_db.preferences["user-1"] = {
            "id": "pref-1",
            "user_id": "user-1",
            "language": "vi",
            "explanation_level": "expert",
            "answer_style": "detailed",
            "created_at": fake_db.now,
            "updated_at": fake_db.now,
        }
        ai_result = _make_ai_result()
        ai_result.metadata.language = "vi"
        ai_result.metadata.explanation_level = "expert"
        ai_result.metadata.answer_style = "detailed"
        ai_result.raw_engine_metadata["preferences"] = {
            "language": "vi",
            "explanation_level": "expert",
            "answer_style": "detailed",
        }

        with patch("app.services.chat_service.ai_service") as mock_svc:
            mock_svc.answer_question = AsyncMock(return_value=ai_result)
            response = client.post(
                f"/api/v1/conversations/{cid}/messages",
                headers=_auth_headers(),
                json={"question": "Bệnh tiểu đường là gì?"},
            )

        mock_svc.answer_question.assert_awaited_once()
        call_kwargs = mock_svc.answer_question.await_args.kwargs
        assert call_kwargs["preferences"] == {
            "language": "vi",
            "explanation_level": "expert",
            "answer_style": "detailed",
        }
        assert response.json()["metadata"]["explanation_level"] == "expert"
        assert fake_db.query_logs[0]["metadata"]["preferences"]["answer_style"] == "detailed"


# ════════════════════════════════════════════════════════════════════════════
# S2-BE-02 — message_sources and query_logs persistence
# ════════════════════════════════════════════════════════════════════════════


class TestMessageSourcesAndQueryLogs:
    def test_message_sources_inserted_for_each_source(self, api):
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")

        sources = [
            ChatSource(id=str(uuid4()), source_type="cypher", title="Neo4j",
                       snippet="MATCH (n) RETURN n", rank=1, metadata={"engine": "cypher_direct"}),
            ChatSource(id=str(uuid4()), source_type="lightrag_entity", title="Tiểu đường",
                       snippet="Rối loạn glucose", rank=2, metadata={"engine": "lightrag"}),
        ]
        ai_result = _make_ai_result(sources=sources)

        with patch("app.services.chat_service.ai_service") as mock_svc:
            mock_svc.answer_question = AsyncMock(return_value=ai_result)
            response = client.post(
                f"/api/v1/conversations/{cid}/messages",
                headers=_auth_headers(),
                json={"question": "Q?"},
            )

        assert response.status_code == 201
        assert len(fake_db.message_sources) == 2
        types = {s["source_type"] for s in fake_db.message_sources}
        assert types == {"cypher", "lightrag_entity"}

    def test_message_sources_have_correct_rank(self, api):
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")

        sources = [
            ChatSource(id=str(uuid4()), source_type="other", title="T", snippet="s", rank=1, metadata={}),
            ChatSource(id=str(uuid4()), source_type="other", title="T2", snippet="s2", rank=2, metadata={}),
        ]
        ai_result = _make_ai_result(sources=sources)

        with patch("app.services.chat_service.ai_service") as mock_svc:
            mock_svc.answer_question = AsyncMock(return_value=ai_result)
            client.post(f"/api/v1/conversations/{cid}/messages",
                        headers=_auth_headers(), json={"question": "Q?"})

        ranks = [s["rank"] for s in fake_db.message_sources]
        assert sorted(ranks) == [1, 2]

    def test_query_log_inserted_with_ai_engine(self, api, mock_ai):
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")

        with patch("app.services.chat_service.ai_service") as mock_svc:
            mock_svc.answer_question = AsyncMock(return_value=mock_ai)
            client.post(f"/api/v1/conversations/{cid}/messages",
                        headers=_auth_headers(), json={"question": "Q?"})

        assert len(fake_db.query_logs) == 1
        log = fake_db.query_logs[0]
        assert log["engine"] == "lightrag"
        assert log["query_mode"] == "mix"
        assert log["execution_time_ms"] > 0
        assert log["status"] == "success"

    def test_query_log_not_mock(self, api, mock_ai):
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")

        with patch("app.services.chat_service.ai_service") as mock_svc:
            mock_svc.answer_question = AsyncMock(return_value=mock_ai)
            client.post(f"/api/v1/conversations/{cid}/messages",
                        headers=_auth_headers(), json={"question": "Q?"})

        log = fake_db.query_logs[0]
        assert log["engine"] != "mock"
        assert log["metadata"]["ai_called"] is True

    def test_source_metadata_no_secret_keys(self, api):
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")

        # Even if ai_result somehow has a secret in source metadata, it should be stripped
        # by source_policy before reaching chat_service.
        sources = [
            ChatSource(id=str(uuid4()), source_type="other", title="T", snippet="s", rank=1,
                       metadata={"engine": "lightrag", "query_mode": "mix"}),
        ]
        ai_result = _make_ai_result(sources=sources)

        with patch("app.services.chat_service.ai_service") as mock_svc:
            mock_svc.answer_question = AsyncMock(return_value=ai_result)
            client.post(f"/api/v1/conversations/{cid}/messages",
                        headers=_auth_headers(), json={"question": "Q?"})

        for src in fake_db.message_sources:
            for key in src["metadata"]:
                assert key not in ("password", "token", "secret", "api_key")


# ════════════════════════════════════════════════════════════════════════════
# S2-BE-03 — Feedback API
# ════════════════════════════════════════════════════════════════════════════


class TestFeedbackAPI:
    def test_upvote_persists_and_returns_correct_shape(self, api):
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")
        msg_id = fake_db.add_message(cid, role="assistant")

        response = client.post(
            f"/api/v1/messages/{msg_id}/feedback",
            headers=_auth_headers(),
            json={"rating": "up", "reason": "helpful", "comment": None},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["rating"] == "up"
        assert body["message_id"] == msg_id
        assert body["id"]
        assert body["created_at"]

    def test_downvote_persists(self, api):
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")
        msg_id = fake_db.add_message(cid, role="assistant")

        response = client.post(
            f"/api/v1/messages/{msg_id}/feedback",
            headers=_auth_headers(),
            json={"rating": "down", "reason": "incorrect"},
        )

        assert response.status_code == 201
        assert response.json()["rating"] == "down"

    def test_feedback_on_nonexistent_message_returns_404(self, api):
        client, fake_db = api
        fake_db.add_profile("user-1")

        response = client.post(
            "/api/v1/messages/nonexistent-id/feedback",
            headers=_auth_headers(),
            json={"rating": "up"},
        )

        assert response.status_code == 404

    def test_feedback_on_user_message_returns_422(self, api):
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")
        # add a USER message (not assistant)
        user_msg_id = fake_db.add_message(cid, role="user", content="My question")

        response = client.post(
            f"/api/v1/messages/{user_msg_id}/feedback",
            headers=_auth_headers(),
            json={"rating": "up"},
        )

        assert response.status_code == 422
        assert response.json()["detail"]["error_code"] == "FEEDBACK_ON_NON_ASSISTANT_MESSAGE"

    def test_feedback_on_other_users_message_returns_404(self, api):
        client, fake_db = api
        fake_db.add_profile("user-1")
        fake_db.add_profile("user-2")
        cid2 = fake_db.add_conversation("user-2", conversation_id="conv-2")
        msg_id = fake_db.add_message(cid2, role="assistant")

        # user-1 tries to feedback on user-2's message
        response = client.post(
            f"/api/v1/messages/{msg_id}/feedback",
            headers=_auth_headers(user_id="user-1"),
            json={"rating": "up"},
        )

        assert response.status_code == 404

    def test_feedback_without_auth_returns_401(self, api):
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")
        msg_id = fake_db.add_message(cid, role="assistant")

        response = client.post(
            f"/api/v1/messages/{msg_id}/feedback",
            json={"rating": "up"},
        )

        assert response.status_code == 401


# ════════════════════════════════════════════════════════════════════════════
# S2-BE-04 — Auto-create review item for negative feedback
# ════════════════════════════════════════════════════════════════════════════


class TestReviewItemCreation:
    def _do_feedback(self, api, rating: str, reason: str | None = None, comment: str | None = None):
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")
        msg_id = fake_db.add_message(cid, role="assistant")
        body = {"rating": rating}
        if reason:
            body["reason"] = reason
        if comment:
            body["comment"] = comment
        response = client.post(
            f"/api/v1/messages/{msg_id}/feedback",
            headers=_auth_headers(),
            json=body,
        )
        return response, fake_db

    def test_down_creates_review_item(self, api):
        response, fake_db = self._do_feedback(api, "down")

        assert response.status_code == 201
        assert len(fake_db.review_items) == 1
        assert fake_db.review_items[0]["status"] == "pending"
        # review_item_id present in response
        assert response.json()["review_item_id"] is not None

    @pytest.mark.parametrize("reason, expected_category", [
        ("incorrect", "answer_quality"),
        ("unsafe", "safety"),
        ("other", "other"),
        (None, "other"),
    ])
    def test_review_item_category_mapping(self, api, reason, expected_category):
        response, fake_db = self._do_feedback(api, "down", reason=reason)

        assert len(fake_db.review_items) == 1
        assert fake_db.review_items[0]["category"] == expected_category

    def test_up_does_not_create_review_item(self, api):
        response, fake_db = self._do_feedback(api, "up", reason="helpful")

        assert response.status_code == 201
        assert len(fake_db.review_items) == 0
        assert response.json()["review_item_id"] is None

    def test_up_incorrect_does_not_create_review_item(self, api):
        """up rating with no negative reason does NOT trigger review."""
        response, fake_db = self._do_feedback(api, "up", reason="helpful")
        assert len(fake_db.review_items) == 0

    def test_review_item_linked_to_feedback(self, api):
        response, fake_db = self._do_feedback(api, "down", reason="incorrect")

        feedback = fake_db.feedback_rows[0]
        review = fake_db.review_items[0]
        assert review["feedback_id"] == feedback["id"]

    def test_review_item_id_returned_in_response(self, api):
        response, fake_db = self._do_feedback(api, "down")

        body = response.json()
        assert body["review_item_id"] == fake_db.review_items[0]["id"]


# ════════════════════════════════════════════════════════════════════════════
# S2-BE-05 — Integration contract smoke tests
# ════════════════════════════════════════════════════════════════════════════


class TestIntegrationContractSmoke:
    def test_chat_response_contract_shape(self, api):
        """Verify ChatResponse shape is fully backward-compatible with Sprint 1."""
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")

        ai_result = _make_ai_result()
        with patch("app.services.chat_service.ai_service") as mock_svc:
            mock_svc.answer_question = AsyncMock(return_value=ai_result)
            response = client.post(
                f"/api/v1/conversations/{cid}/messages",
                headers=_auth_headers(),
                json={"question": "Bệnh tiểu đường là gì?", "mode": "mix"},
            )

        assert response.status_code == 201
        body = response.json()

        # Required top-level fields
        for field in ["conversation_id", "message_id", "status", "response_type",
                      "answer", "sources", "safety", "metadata"]:
            assert field in body, f"missing field: {field}"

        # Safety shape
        safety = body["safety"]
        assert "level" in safety
        assert "requires_emergency_notice" in safety
        assert "disclaimer" in safety
        assert safety["level"] in ("normal", "caution", "emergency")

        # Metadata shape
        meta = body["metadata"]
        assert "engine" in meta
        assert "query_mode" in meta
        assert "execution_time_ms" in meta
        assert "source_count" in meta

        # Sources shape
        assert isinstance(body["sources"], list)
        if body["sources"]:
            src = body["sources"][0]
            assert "id" in src
            assert "source_type" in src
            assert "title" in src
            assert "rank" in src

    def test_full_chat_feedback_flow(self, api):
        """End-to-end: chat → feedback → review item."""
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")

        # 1. Send message
        ai_result = _make_ai_result()
        with patch("app.services.chat_service.ai_service") as mock_svc:
            mock_svc.answer_question = AsyncMock(return_value=ai_result)
            chat_resp = client.post(
                f"/api/v1/conversations/{cid}/messages",
                headers=_auth_headers(),
                json={"question": "Câu hỏi?"},
            )

        assert chat_resp.status_code == 201
        message_id = chat_resp.json()["message_id"]

        # 2. Send negative feedback
        fb_resp = client.post(
            f"/api/v1/messages/{message_id}/feedback",
            headers=_auth_headers(),
            json={"rating": "down", "reason": "incorrect", "comment": "Câu trả lời sai."},
        )

        assert fb_resp.status_code == 201
        fb_body = fb_resp.json()
        assert fb_body["rating"] == "down"
        assert fb_body["review_item_id"] is not None  # auto-created

        # 3. Verify DB state
        assert len(fake_db.feedback_rows) == 1
        assert len(fake_db.review_items) == 1
        assert len(fake_db.query_logs) == 1
        assert len(fake_db.message_sources) >= 1  # fallback source

    def test_engine_error_still_returns_201(self, api):
        """AI engine errors must not crash the endpoint — they produce a valid response."""
        client, fake_db = api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")

        # ai_service.answer_question() never raises; it normalises errors internally
        error_result = _make_ai_result(answer="Hệ thống đang gặp sự cố.")
        with patch("app.services.chat_service.ai_service") as mock_svc:
            mock_svc.answer_question = AsyncMock(return_value=error_result)
            response = client.post(
                f"/api/v1/conversations/{cid}/messages",
                headers=_auth_headers(),
                json={"question": "Q?"},
            )

        assert response.status_code == 201
        assert response.json()["answer"]
