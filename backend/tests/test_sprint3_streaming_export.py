"""Sprint 3 — Streaming chat and conversation export tests."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api_gateway import dependencies
from app.main import app
from app.services import chat_service, export_service, feedback_service, streaming_service, user_service
from backend.tests.test_sprint2_be import FakeDatabase, _auth_headers, _make_ai_result


class FakeSprint3Database(FakeDatabase):
    def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        q = " ".join(query.lower().split())

        if "from public.message_sources" in q:
            message_ids = set(params[0])
            rows = []
            for index, source in enumerate(self.message_sources, start=1):
                if source["message_id"] in message_ids:
                    rows.append(
                        {
                            "id": f"source-{index}",
                            "message_id": source["message_id"],
                            "source_type": source["source_type"],
                            "title": source["title"],
                            "snippet": source["snippet"],
                            "metadata": source["metadata"],
                            "rank": source["rank"],
                        }
                    )
            return sorted(rows, key=lambda row: (row["message_id"], row["rank"]))

        return super().fetch_all(query, params)


@pytest.fixture
def sprint3_api(monkeypatch):
    fake_db = FakeSprint3Database()
    monkeypatch.setattr(dependencies, "SUPABASE_JWT_SECRET", "test-secret")
    monkeypatch.setattr(user_service, "get_database", lambda: fake_db)
    monkeypatch.setattr(chat_service, "get_database", lambda: fake_db)
    monkeypatch.setattr(streaming_service, "get_database", lambda: fake_db)
    monkeypatch.setattr(feedback_service, "get_database", lambda: fake_db)
    monkeypatch.setattr(export_service, "get_database", lambda: fake_db)
    return TestClient(app), fake_db


def _parse_sse(text: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in text.strip().split("\n\n"):
        event_name = ""
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line.removeprefix("event:").strip()
            if line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())
        if event_name:
            events.append((event_name, json.loads("\n".join(data_lines))))
    return events


def _stream_message(client: TestClient, conversation_id: str, question: str = "Question?"):
    with client.stream(
        "POST",
        f"/api/v1/conversations/{conversation_id}/messages/stream",
        headers=_auth_headers(),
        json={"question": question, "mode": None},
    ) as response:
        return response, _parse_sse(response.read().decode("utf-8"))


def _pipeline_result(answer: str = "Câu trả lời AI.", *, suggested_questions: list[str] | None = None) -> dict:
    return {
        "status": "success",
        "response_type": "text",
        "answer": answer,
        "data": None,
        "suggested_questions": suggested_questions or [],
        "metadata": {
            "engine": "cypher_direct",
            "query_mode": "cypher:template:symptoms",
            "execution_time_ms": 120.5,
            "source_count": 1,
            "cypher": "MATCH (d:Disease) RETURN d",
        },
    }


class TestSseStreaming:
    def test_sse_event_order(self, sprint3_api):
        client, fake_db = sprint3_api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")

        async def fake_stream(**_kwargs):
            return _pipeline_result("ABC")

        with patch("app.services.streaming_service.pipeline.run_pipeline_stream", new=fake_stream):
            response, events = _stream_message(client, cid)

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        names = [name for name, _ in events]
        assert names[:3] == ["stage", "stage", "stage"]
        assert "delta" in names
        assert names[-4:] == ["stage", "sources", "metadata", "final"]
        assert [data["stage"] for name, data in events if name == "stage"] == [
            "routing",
            "retrieving",
            "generating",
            "persisting",
        ]
        assert "".join(data["content"] for name, data in events if name == "delta") == "ABC"
        assert all(data["streaming_supported"] is False for name, data in events if name == "delta")

    def test_lightrag_native_deltas_are_forwarded(self, sprint3_api):
        client, fake_db = sprint3_api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")

        async def fake_stream(**kwargs):
            await kwargs["on_delta"]("Xin ")
            await kwargs["on_delta"]("chào")
            return _pipeline_result("Xin chào")

        with patch("app.services.streaming_service.pipeline.run_pipeline_stream", new=fake_stream):
            _, events = _stream_message(client, cid)

        deltas = [data for name, data in events if name == "delta"]
        assert [delta["content"] for delta in deltas] == ["Xin ", "chào"]
        assert all(delta["streaming_supported"] is True for delta in deltas)

    def test_final_response_is_persisted_chat_response(self, sprint3_api):
        client, fake_db = sprint3_api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")
        async def fake_stream(**_kwargs):
            return _pipeline_result(
                "Persisted answer.",
                suggested_questions=["Follow up?"],
            )

        with patch("app.services.streaming_service.pipeline.run_pipeline_stream", new=fake_stream):
            _, events = _stream_message(client, cid)

        final = events[-1][1]
        assistant = next(m for m in fake_db.messages if m["id"] == final["message_id"])
        assert assistant["role"] == "assistant"
        assert assistant["content"] == "Persisted answer."
        assert final["answer"] == assistant["content"]
        assert final["suggested_questions"] == ["Follow up?"]
        assert final["metadata"]["prompt_version"]

    def test_stream_error_is_normalized(self, sprint3_api):
        client, fake_db = sprint3_api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1")

        async def fake_stream(**_kwargs):
            raise RuntimeError("secret-stack-token")

        with patch("app.services.streaming_service.pipeline.run_pipeline_stream", new=fake_stream):
            response, events = _stream_message(client, cid)

        assert response.status_code == 200
        assert events[-1][0] == "error"
        assert events[-1][1]["error_code"] == "STREAM_MESSAGE_FAILED"
        assert "secret-stack-token" not in json.dumps(events[-1][1])


class TestConversationExport:
    def test_export_is_owner_only(self, sprint3_api):
        client, fake_db = sprint3_api
        fake_db.add_profile("user-1")
        fake_db.add_profile("user-2")
        cid = fake_db.add_conversation("user-1")

        own = client.get(
            f"/api/v1/conversations/{cid}/export?format=markdown",
            headers=_auth_headers("user-1"),
        )
        other = client.get(
            f"/api/v1/conversations/{cid}/export?format=markdown",
            headers=_auth_headers("user-2"),
        )

        assert own.status_code == 200
        assert other.status_code == 404

    def test_markdown_export_contains_messages_sources_disclaimer_and_versions(self, sprint3_api):
        client, fake_db = sprint3_api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1", title="Export Test")

        with patch("app.services.chat_service.ai_service") as mock_svc:
            mock_svc.answer_question = AsyncMock(return_value=_make_ai_result(answer="Assistant answer."))
            client.post(
                f"/api/v1/conversations/{cid}/messages",
                headers=_auth_headers(),
                json={"question": "User question?", "mode": None},
            )

        response = client.get(
            f"/api/v1/conversations/{cid}/export?format=markdown",
            headers=_auth_headers(),
        )

        body = response.text
        assert response.status_code == 200
        assert "Export Test" in body
        assert "User question?" in body
        assert "Assistant answer." in body
        assert "Safety Disclaimer" in body
        assert "AegisHealth Hybrid GraphRAG" in body
        assert "Version Trace" in body
        assert "Prompt Version" in body

    def test_pdf_export_download_contains_pdf_and_transcript_text(self, sprint3_api):
        client, fake_db = sprint3_api
        fake_db.add_profile("user-1")
        cid = fake_db.add_conversation("user-1", title="PDF Test")

        fake_db.add_message(cid, role="user", content="PDF user question?")
        assistant_id = fake_db.add_message(cid, role="assistant", content="PDF assistant answer.")
        fake_db.messages[-1]["metadata"].update(
            {
                "prompt_version": "prompt-v",
                "model_name": "model-v",
                "kg_version": "kg-v",
                "pipeline_version": "pipeline-v",
            }
        )
        fake_db.message_sources.append(
            {
                "message_id": assistant_id,
                "source_type": "document",
                "title": "PDF source",
                "snippet": "PDF snippet",
                "metadata": {"doc": "x"},
                "rank": 1,
            }
        )

        response = client.get(
            f"/api/v1/conversations/{cid}/export?format=pdf",
            headers=_auth_headers(),
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")
        assert b"PDF user question?" in response.content
        assert b"PDF assistant answer." in response.content
        assert b"PDF source" in response.content
