"""SSE streaming orchestration for conversation messages."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator

from fastapi import HTTPException

from app.models.contracts import (
    AIServiceResult,
    ChatResponse,
    MessageCreateRequest,
    StreamDeltaPayload,
    StreamErrorPayload,
    StreamStagePayload,
)
from app.services import chat_service
from app.services import ai_service
from app.services import pipeline
from app.services import preference_service
from app.database import get_database

logger = logging.getLogger(__name__)
FALLBACK_DELTA_CHUNK_SIZE = 16


def format_sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _normalise_error(exc: BaseException) -> StreamErrorPayload:
    if isinstance(exc, HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return StreamErrorPayload(
            error_code=str(detail.get("error_code") or "REQUEST_FAILED"),
            message=str(detail.get("message") or "Request failed."),
            status_code=exc.status_code,
        )

    logger.exception("Streaming message failed")
    return StreamErrorPayload(
        error_code="STREAM_MESSAGE_FAILED",
        message="Không thể xử lý câu hỏi lúc này. Vui lòng thử lại.",
        status_code=500,
    )


def _fallback_delta_chunks(answer: str) -> list[str]:
    return [
        answer[index : index + FALLBACK_DELTA_CHUNK_SIZE]
        for index in range(0, len(answer), FALLBACK_DELTA_CHUNK_SIZE)
    ]


async def stream_message_events(
    *,
    user_id: str,
    conversation_id: str,
    payload: MessageCreateRequest,
) -> AsyncIterator[str]:
    queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()

    async def publish_stage(stage: str, message: str) -> None:
        event = StreamStagePayload(stage=stage, message=message)
        await queue.put(("stage", event.model_dump(mode="json")))

    async def publish_delta(content: str, *, streaming_supported: bool) -> None:
        event = StreamDeltaPayload(
            content=content,
            streaming_supported=streaming_supported,
        )
        await queue.put(("delta", event.model_dump(mode="json")))

    async def run_streaming_chat() -> ChatResponse:
        db = get_database()
        await publish_stage("routing", "Đang kiểm tra hội thoại và quyền truy cập.")
        chat_service.ensure_conversation_owner(
            db=db,
            user_id=user_id,
            conversation_id=conversation_id,
        )
        chat_service.persist_user_message(
            db=db,
            conversation_id=conversation_id,
            payload=payload,
        )

        await publish_stage("retrieving", "Đang tải tuỳ chọn và truy xuất ngữ cảnh.")
        preferences = await preference_service.get_preferences(user_id, database=db)
        preference_context = {
            "language": preferences["language"],
            "explanation_level": preferences["explanation_level"],
            "answer_style": preferences["answer_style"],
        }

        emitted_delta = False

        async def on_pipeline_delta(chunk: str) -> None:
            nonlocal emitted_delta
            emitted_delta = True
            await publish_delta(chunk, streaming_supported=True)

        await publish_stage("generating", "Đang tạo câu trả lời.")
        start_time = time.time()
        pipeline_result = await pipeline.run_pipeline_stream(
            question=payload.question,
            mode=payload.mode,
            preferences=preference_context,
            on_delta=on_pipeline_delta,
        )
        ai_result: AIServiceResult = ai_service.build_result_from_pipeline(
            pipeline_result=pipeline_result,
            question=payload.question,
            execution_time_ms=(time.time() - start_time) * 1000,
            preferences=preference_context,
        )

        if not emitted_delta:
            for chunk in _fallback_delta_chunks(ai_result.answer):
                await publish_delta(chunk, streaming_supported=False)
                await asyncio.sleep(0)

        await publish_stage("persisting", "Đang lưu câu trả lời và nguồn trích dẫn.")
        return chat_service.persist_assistant_response(
            db=db,
            conversation_id=conversation_id,
            question=payload.question,
            ai_result=ai_result,
            ai_called=True,
        )

    task = asyncio.create_task(run_streaming_chat())

    while not task.done() or not queue.empty():
        try:
            event_name, event_data = await asyncio.wait_for(queue.get(), timeout=0.1)
        except TimeoutError:
            continue
        yield format_sse(event_name, event_data)

    try:
        response: ChatResponse = task.result()
    except Exception as exc:
        error = _normalise_error(exc)
        yield format_sse("error", error.model_dump(mode="json"))
        return

    yield format_sse(
        "sources",
        {"sources": [source.model_dump(mode="json") for source in response.sources]},
    )
    yield format_sse("metadata", response.metadata.model_dump(mode="json"))
    yield format_sse("final", response.model_dump(mode="json"))
