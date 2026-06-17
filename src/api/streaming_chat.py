"""SSE orchestration for conversation message streaming."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

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

logger = logging.getLogger(__name__)


def _source_dicts(result) -> list[dict[str, Any]]:
    return [
        {
            "id": s.get("id"),
            "source_type": s.get("source_type", "other"),
            "title": s.get("title", ""),
            "snippet": s.get("snippet"),
            "rank": s.get("rank", 1),
            "metadata": s.get("metadata", {}),
        }
        for s in (result.sources or [])
    ]


async def build_message_stream_events(
    *,
    conversation_id: str,
    question: str,
    mode: str | None,
    preferences: dict[str, Any] | None,
    answer_question_stream,
    manage_conversation,
) -> AsyncIterator[str]:
    """Yield SSE events for a streamed assistant answer.

    Persistence failure is fatal for this endpoint: the stream emits an error
    event and never emits a final success payload with a fabricated message id.
    """
    try:
        yield build_stage_event("routing", "Đang phân tích câu hỏi...")
        yield build_stage_event("retrieving", "Đang truy xuất tri thức...")
        yield build_stage_event("generating", "Đang tạo câu trả lời...")

        delta_queue: asyncio.Queue[str] = asyncio.Queue()
        emitted_delta = False

        async def _emit_delta(token: str) -> None:
            nonlocal emitted_delta
            emitted_delta = True
            await delta_queue.put(token)

        task = asyncio.create_task(
            answer_question_stream.execute(
                question=question,
                mode=mode,
                preferences=preferences,
                on_delta=_emit_delta,
            )
        )

        while not task.done():
            try:
                token = await asyncio.wait_for(delta_queue.get(), timeout=0.1)
                yield build_delta_event(token, streaming_supported=True)
            except asyncio.TimeoutError:
                continue

        while not delta_queue.empty():
            yield build_delta_event(delta_queue.get_nowait(), streaming_supported=True)

        result = await task
        error_code = (result.metadata or {}).get("error_code")
        if error_code:
            yield build_error_event(
                error_code=error_code,
                message=result.answer,
                status_code=http_status_for_error(error_code),
            )
            return

        if not emitted_delta:
            answer = result.answer or ""
            for idx in range(0, len(answer), 32):
                yield build_delta_event(answer[idx:idx + 32], streaming_supported=False)

        yield build_stage_event("persisting", "Đang lưu câu trả lời...")

        try:
            persisted = manage_conversation.persist_assistant_response(
                conversation_id=conversation_id,
                question=question,
                ai_result=result,
            )
        except Exception as exc:
            logger.warning("Failed to persist assistant message: %s", exc)
            yield build_error_event(
                error_code="PERSISTENCE_FAILED",
                message="Không thể lưu câu trả lời. Vui lòng thử lại.",
                status_code=http_status_for_error("PERSISTENCE_FAILED"),
            )
            return

        sources = _source_dicts(result)
        final_metadata = persisted["metadata"]

        yield build_sources_event(sources)
        yield build_metadata_event(
            engine=final_metadata.get("engine", "unknown"),
            query_mode=final_metadata.get("query_mode", "auto"),
            execution_time_ms=final_metadata.get("execution_time_ms", 0.0),
            source_count=final_metadata.get("source_count", len(sources)),
        )

        safety_raw = result.safety or {}
        final = StreamFinalPayload(
            conversation_id=conversation_id,
            message_id=persisted["message_id"],
            status="success",
            response_type=result.response_type,
            answer=result.answer,
            data=result.data,
            sources=sources,
            safety={
                "level": safety_raw.get("level", "normal"),
                "requires_emergency_notice": safety_raw.get("requires_emergency_notice", False),
                "disclaimer": safety_raw.get("disclaimer", "Thông tin chỉ mang tính chất tham khảo."),
            },
            suggested_questions=result.suggested_questions or [],
            metadata=final_metadata,
        )
        yield build_final_event(final)

    except Exception as exc:
        logger.exception("Streaming error: %s", exc)
        yield build_error_event(
            error_code="STREAM_ERROR",
            message="Đã xảy ra lỗi trong quá trình phát câu trả lời.",
            status_code=http_status_for_error("STREAM_ERROR"),
        )
