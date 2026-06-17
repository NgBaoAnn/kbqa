"""API contract tests for the refactored backend routers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from adapters.in_memory.database import InMemoryDatabaseRepository
from adapters.in_memory.graph_repository import InMemoryGraphRepository
from adapters.in_memory.vector_repository import InMemoryVectorRepository
from api.middleware.auth import CurrentUser, get_current_user
from api.routers.conversations import router as conversations_router
from api.routers.feedback import router as feedback_router
from api.routers.health import router as health_router
from api.routers.query import router as query_router
from api.streaming_chat import build_message_stream_events
from use_cases.answer_question import AIServiceResult
from use_cases.manage_conversation import ManageConversationUseCase
from use_cases.manage_feedback import ManageFeedbackUseCase
from use_cases.manage_preferences import ManagePreferencesUseCase


def _user() -> CurrentUser:
    return CurrentUser(id="user-1", email="u@example.test", role="user", claims={})


def _app_with_container(container: object, *routers) -> FastAPI:
    app = FastAPI()
    app.state.container = container
    app.dependency_overrides[get_current_user] = _user
    for router in routers:
        app.include_router(router)
    return app


class _QueryErrorUseCase:
    async def execute(self, *, question, mode=None, preferences=None):
        return AIServiceResult(
            answer="LightRAG failed",
            response_type="text",
            data=None,
            sources=[{"source_type": "other", "title": "Hệ thống", "snippet": "", "rank": 1, "metadata": {}}],
            safety={"level": "normal", "requires_emergency_notice": False, "disclaimer": "note"},
            suggested_questions=[],
            metadata={"error_code": "LIGHTRAG_QUERY_FAILED", "engine": "lightrag", "query_mode": mode or "naive"},
            raw_pipeline_metadata={"error_code": "LIGHTRAG_QUERY_FAILED"},
        )


class _QuerySuccessUseCase:
    async def execute(self, *, question, mode=None, preferences=None):
        return AIServiceResult(
            answer="Câu trả lời",
            response_type="text",
            data=None,
            sources=[{"source_type": "other", "title": "Nguồn", "snippet": "", "rank": 1, "metadata": {}}],
            safety={"level": "normal", "requires_emergency_notice": False, "disclaimer": "note"},
            suggested_questions=[],
            metadata={"engine": "lightrag", "query_mode": mode or "naive", "execution_time_ms": 1.0, "source_count": 1},
            raw_pipeline_metadata={},
        )


class _StreamingUseCase:
    async def execute(self, *, question, mode=None, preferences=None, on_delta=None):
        if on_delta is not None:
            await on_delta("Xin ")
            await asyncio.sleep(0)
            await on_delta("chào")
        return AIServiceResult(
            answer="Xin chào",
            response_type="text",
            data=None,
            sources=[{"id": "s1", "source_type": "other", "title": "Nguồn", "snippet": "", "rank": 1, "metadata": {}}],
            safety={"level": "normal", "requires_emergency_notice": False, "disclaimer": "note"},
            suggested_questions=[],
            metadata={"engine": "lightrag", "query_mode": "naive", "execution_time_ms": 1.0, "source_count": 1},
            raw_pipeline_metadata={},
        )


class _FailingPersistConversation:
    def persist_assistant_response(self, *, conversation_id, question, ai_result):
        raise RuntimeError("db down")


def test_query_lightrag_failure_maps_to_legacy_500() -> None:
    container = SimpleNamespace(
        db=InMemoryDatabaseRepository(),
        answer_question=_QueryErrorUseCase(),
        manage_preferences=ManagePreferencesUseCase(db=InMemoryDatabaseRepository()),
        version_metadata={},
    )
    client = TestClient(_app_with_container(container, query_router))

    response = client.post("/api/v1/query", json={"question": "test"})

    assert response.status_code == 500
    assert response.json()["detail"]["error_code"] == "LIGHTRAG_QUERY_FAILED"


def test_query_standalone_returns_explicit_unpersisted_contract() -> None:
    db = InMemoryDatabaseRepository()
    container = SimpleNamespace(
        db=db,
        answer_question=_QuerySuccessUseCase(),
        manage_preferences=ManagePreferencesUseCase(db=db),
        version_metadata={"pipeline_version": "pipe1"},
    )
    client = TestClient(_app_with_container(container, query_router))

    response = client.post("/api/v1/query", json={"question": "test"})

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] is None
    assert body["message_id"] is None
    assert body["metadata"]["persisted"] is False
    assert body["metadata"]["pipeline_version"] == "pipe1"


def test_health_uses_legacy_shape_and_service_keys() -> None:
    container = SimpleNamespace(
        graph=InMemoryGraphRepository(),
        vector=InMemoryVectorRepository(),
        db=InMemoryDatabaseRepository(),
        version_metadata={"pipeline_version": "test-pipeline"},
    )
    client = TestClient(_app_with_container(container, health_router))

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "services", "version"}
    assert body["version"] == "test-pipeline"
    assert set(body["services"]) == {
        "api",
        "supabase_postgres",
        "neo4j",
        "ai_engine",
        "llm_server",
        "embedding_server",
        "lightrag",
    }


def test_conversation_stream_event_sequence_contains_metadata_and_final_data() -> None:
    db = InMemoryDatabaseRepository()
    manage_conversation = ManageConversationUseCase(
        db=db,
        version_metadata={
            "prompt_version": "p1",
            "model_name": "m1",
            "kg_version": "kg1",
            "pipeline_version": "pipe1",
        },
    )
    conv = manage_conversation.create_conversation(user_id="user-1", title="Chat")
    container = SimpleNamespace(
        db=db,
        answer_question_stream=_StreamingUseCase(),
        manage_conversation=manage_conversation,
        manage_preferences=ManagePreferencesUseCase(db=db),
        version_metadata={
            "prompt_version": "p1",
            "model_name": "m1",
            "kg_version": "kg1",
            "pipeline_version": "pipe1",
        },
    )
    client = TestClient(_app_with_container(container, conversations_router))

    response = client.post(
        f"/api/v1/conversations/{conv['id']}/messages/stream",
        json={"question": "Xin chào"},
    )

    assert response.status_code == 200
    text = response.text
    assert text.index("event: stage\ndata: {\"stage\":\"routing\"") < text.index("event: stage\ndata: {\"stage\":\"retrieving\"")
    assert text.index("event: stage\ndata: {\"stage\":\"retrieving\"") < text.index("event: stage\ndata: {\"stage\":\"generating\"")
    assert "event: delta" in text
    assert text.index("event: stage\ndata: {\"stage\":\"persisting\"") < text.index("event: sources")
    assert text.index("event: sources") < text.index("event: metadata")
    assert text.index("event: metadata") < text.index("event: final")
    assert "\"data\":null" in text
    assert "\"prompt_version\":\"p1\"" in text
    assert "\"persisted\":true" in text


def test_stream_presenter_persist_failure_emits_error_without_final_success() -> None:
    async def _collect() -> str:
        events = []
        async for event in build_message_stream_events(
            conversation_id="conv-1",
            question="Xin chào",
            mode=None,
            preferences=None,
            answer_question_stream=_StreamingUseCase(),
            manage_conversation=_FailingPersistConversation(),
        ):
            events.append(event)
        return "".join(events)

    text = asyncio.run(_collect())

    assert "event: stage\ndata: {\"stage\":\"persisting\"" in text
    assert "event: error" in text
    assert "\"error_code\":\"PERSISTENCE_FAILED\"" in text
    assert "\"status_code\":500" in text
    assert "event: final" not in text


def test_feedback_endpoint_maps_request_to_use_case() -> None:
    db = InMemoryDatabaseRepository()
    manage_conversation = ManageConversationUseCase(db=db)
    conv = manage_conversation.create_conversation(user_id="user-1", title="Chat")
    result = AIServiceResult(
        answer="Câu trả lời",
        response_type="text",
        data=None,
        sources=[],
        safety={"level": "normal", "requires_emergency_notice": False, "disclaimer": "note"},
        suggested_questions=[],
        metadata={"engine": "lightrag", "query_mode": "naive", "execution_time_ms": 1.0, "source_count": 0},
        raw_pipeline_metadata={},
    )
    persisted = manage_conversation.persist_assistant_response(
        conversation_id=conv["id"],
        question="Câu hỏi",
        ai_result=result,
    )
    container = SimpleNamespace(
        db=db,
        manage_feedback=ManageFeedbackUseCase(db=db),
        manage_conversation=manage_conversation,
    )
    client = TestClient(_app_with_container(container, feedback_router))

    response = client.post(
        f"/api/v1/messages/{persisted['message_id']}/feedback",
        json={"rating": "down", "reason": "incorrect", "comment": "Sai"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["message_id"] == persisted["message_id"]
    assert body["rating"] == "down"
    assert body["review_item_id"]


def test_feedback_endpoint_maps_missing_message_to_404() -> None:
    db = InMemoryDatabaseRepository()
    container = SimpleNamespace(
        db=db,
        manage_feedback=ManageFeedbackUseCase(db=db),
        manage_conversation=ManageConversationUseCase(db=db),
    )
    client = TestClient(_app_with_container(container, feedback_router))

    response = client.post("/api/v1/messages/missing/feedback", json={"rating": "up"})

    assert response.status_code == 404
    assert response.json()["detail"]["error_code"] == "MESSAGE_NOT_FOUND"
