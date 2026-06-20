"""SSE presentation for conversation message streaming."""

from __future__ import annotations

from collections.abc import AsyncIterator

from api.error_mapping import http_status_for_error
from api.schemas.streaming import (
    StreamFinalPayload,
    build_delta_event,
    build_error_event,
    build_final_event,
    build_metadata_event,
    build_sources_event,
    build_stage_event,
)


async def build_message_stream_events(
    events: AsyncIterator,
) -> AsyncIterator[str]:
    """Map transport-neutral stream events to Server-Sent Events."""
    async for event in events:
        payload = event.payload
        if event.type == "stage":
            yield build_stage_event(payload["stage"], payload["message"])
        elif event.type == "delta":
            yield build_delta_event(
                payload.get("content", ""),
                streaming_supported=payload.get("streaming_supported", True),
            )
        elif event.type == "sources":
            yield build_sources_event(payload.get("sources", []))
        elif event.type == "metadata":
            yield build_metadata_event(
                engine=payload.get("engine", "unknown"),
                query_mode=payload.get("query_mode", "auto"),
                execution_time_ms=payload.get("execution_time_ms", 0.0),
                source_count=payload.get("source_count", 0),
            )
        elif event.type == "final":
            yield build_final_event(StreamFinalPayload(**payload))
        elif event.type == "error":
            error_code = payload.get("error_code", "STREAM_ERROR")
            yield build_error_event(
                error_code=error_code,
                message=payload.get("message", ""),
                status_code=http_status_for_error(error_code),
            )
