"""Streaming SSE event schemas.

These are the Pydantic models used to construct Server-Sent Events
for the streaming chat endpoint.

Event flow:
    1. stage   — pipeline stage notification (routing, retrieving, generating, persisting)
    2. delta*  — one token at a time (LightRAG path only)
    3. sources — provenance records when retrieval is complete
    4. metadata — execution metadata
    5. final   — complete ChatResponse payload (client merges deltas)
    6. error   — on any fatal error

Usage (FastAPI SSE)::

    from api.schemas.streaming import StreamEvent, StreamDeltaPayload, build_delta_event
    from fastapi.responses import StreamingResponse
    import json

    async def event_generator():
        yield build_stage_event("routing", "분석 중...")
        async for token in token_stream:
            yield build_delta_event(token)
        yield build_final_event(chat_response)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


StreamEventType = Literal["stage", "delta", "sources", "metadata", "final", "error"]
StreamStage = Literal["routing", "retrieving", "generating", "persisting"]


class StreamStagePayload(BaseModel):
    stage: StreamStage
    message: str


class StreamDeltaPayload(BaseModel):
    content: str = ""
    streaming_supported: bool = False


class StreamSourcesPayload(BaseModel):
    sources: list[dict[str, Any]]


class StreamMetadataPayload(BaseModel):
    engine: str
    query_mode: str
    execution_time_ms: float
    source_count: int


class StreamFinalPayload(BaseModel):
    """Full ChatResponse JSON embedded in the final event."""

    conversation_id: str
    message_id: str
    status: Literal["success", "error"] = "success"
    response_type: str
    answer: str
    data: list[dict[str, Any]] | dict[str, Any] | None = None
    sources: list[dict[str, Any]]
    safety: dict[str, Any]
    suggested_questions: list[str]
    metadata: dict[str, Any]


class StreamErrorPayload(BaseModel):
    error_code: str
    message: str
    status_code: int | None = None


# ── SSE helpers ───────────────────────────────────────────────────────────

def _sse(event_type: str, payload: BaseModel | dict) -> str:
    """Format a single SSE line: ``event: <type>\\ndata: <json>\\n\\n``."""
    import json

    if isinstance(payload, BaseModel):
        data = payload.model_dump_json()
    else:
        data = json.dumps(payload)
    return f"event: {event_type}\ndata: {data}\n\n"


def build_stage_event(stage: StreamStage, message: str) -> str:
    return _sse("stage", StreamStagePayload(stage=stage, message=message))


def build_delta_event(content: str, streaming_supported: bool = True) -> str:
    return _sse("delta", StreamDeltaPayload(content=content, streaming_supported=streaming_supported))


def build_sources_event(sources: list[dict[str, Any]]) -> str:
    return _sse("sources", StreamSourcesPayload(sources=sources))


def build_metadata_event(
    engine: str,
    query_mode: str,
    execution_time_ms: float,
    source_count: int,
) -> str:
    return _sse(
        "metadata",
        StreamMetadataPayload(
            engine=engine,
            query_mode=query_mode,
            execution_time_ms=execution_time_ms,
            source_count=source_count,
        ),
    )


def build_final_event(payload: StreamFinalPayload) -> str:
    return _sse("final", payload)


def build_error_event(error_code: str, message: str, status_code: int | None = None) -> str:
    return _sse("error", StreamErrorPayload(error_code=error_code, message=message, status_code=status_code))
