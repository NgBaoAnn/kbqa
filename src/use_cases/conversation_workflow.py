"""Conversation workflows that coordinate QA and conversation persistence."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConversationAnswerResult:
    """Result of sending a message in a persisted conversation."""

    ai_result: Any
    persisted: dict[str, Any]


@dataclass(frozen=True)
class ExportedConversation:
    """Rendered conversation export payload."""

    filename: str
    media_type: str
    content: bytes


@dataclass(frozen=True)
class StreamUseCaseEvent:
    """Transport-neutral event emitted by the streaming conversation use case."""

    type: Literal["stage", "delta", "sources", "metadata", "final", "error"]
    payload: dict[str, Any]


class SendConversationMessageUseCase:
    """Send a user message, run QA, and persist the assistant response."""

    def __init__(self, *, manage_conversation, manage_preferences, answer_question) -> None:
        self._manage_conversation = manage_conversation
        self._manage_preferences = manage_preferences
        self._answer_question = answer_question

    async def execute(
        self,
        *,
        user_id: str,
        conversation_id: str,
        question: str,
        mode: str | None = None,
    ) -> ConversationAnswerResult | None:
        if not self._manage_conversation.ensure_owner(
            user_id=user_id,
            conversation_id=conversation_id,
        ):
            return None

        preferences = self._manage_preferences.get_preferences(user_id=user_id)
        self._manage_conversation.persist_user_message(
            conversation_id=conversation_id,
            question=question,
            mode=mode,
        )
        result = await self._answer_question.execute(
            question=question,
            mode=mode,
            preferences=preferences,
        )
        persisted = self._manage_conversation.persist_assistant_response(
            conversation_id=conversation_id,
            question=question,
            ai_result=result,
        )
        return ConversationAnswerResult(ai_result=result, persisted=persisted)


class StreamConversationMessageUseCase:
    """Stream a user message answer and persist it when generation succeeds."""

    def __init__(
        self,
        *,
        manage_conversation,
        manage_preferences,
        answer_question_stream,
    ) -> None:
        self._manage_conversation = manage_conversation
        self._manage_preferences = manage_preferences
        self._answer_question_stream = answer_question_stream

    def start(
        self,
        *,
        user_id: str,
        conversation_id: str,
        question: str,
        mode: str | None = None,
    ) -> AsyncIterator[StreamUseCaseEvent] | None:
        if not self._manage_conversation.ensure_owner(
            user_id=user_id,
            conversation_id=conversation_id,
        ):
            return None

        preferences = self._manage_preferences.get_preferences(user_id=user_id)
        self._manage_conversation.persist_user_message(
            conversation_id=conversation_id,
            question=question,
            mode=mode,
        )
        return self._events(
            conversation_id=conversation_id,
            question=question,
            mode=mode,
            preferences=preferences,
        )

    async def _events(
        self,
        *,
        conversation_id: str,
        question: str,
        mode: str | None,
        preferences: dict[str, Any] | None,
    ) -> AsyncIterator[StreamUseCaseEvent]:
        try:
            yield StreamUseCaseEvent("stage", {"stage": "routing", "message": "Đang phân tích câu hỏi..."})
            yield StreamUseCaseEvent("stage", {"stage": "retrieving", "message": "Đang truy xuất tri thức..."})
            yield StreamUseCaseEvent("stage", {"stage": "generating", "message": "Đang tạo câu trả lời..."})

            delta_queue: asyncio.Queue[str] = asyncio.Queue()
            emitted_delta = False

            async def _emit_delta(token: str) -> None:
                nonlocal emitted_delta
                emitted_delta = True
                await delta_queue.put(token)

            task = asyncio.create_task(
                self._answer_question_stream.execute(
                    question=question,
                    mode=mode,
                    preferences=preferences,
                    on_delta=_emit_delta,
                )
            )

            while not task.done():
                try:
                    token = await asyncio.wait_for(delta_queue.get(), timeout=0.1)
                    yield StreamUseCaseEvent(
                        "delta",
                        {"content": token, "streaming_supported": True},
                    )
                except asyncio.TimeoutError:
                    continue

            while not delta_queue.empty():
                yield StreamUseCaseEvent(
                    "delta",
                    {"content": delta_queue.get_nowait(), "streaming_supported": True},
                )

            result = await task
            error_code = (result.metadata or {}).get("error_code")
            if error_code:
                yield StreamUseCaseEvent(
                    "error",
                    {"error_code": error_code, "message": result.answer},
                )
                return

            if not emitted_delta:
                answer = result.answer or ""
                for idx in range(0, len(answer), 32):
                    yield StreamUseCaseEvent(
                        "delta",
                        {"content": answer[idx:idx + 32], "streaming_supported": False},
                    )

            yield StreamUseCaseEvent("stage", {"stage": "persisting", "message": "Đang lưu câu trả lời..."})

            try:
                persisted = self._manage_conversation.persist_assistant_response(
                    conversation_id=conversation_id,
                    question=question,
                    ai_result=result,
                )
            except Exception as exc:
                logger.warning("Failed to persist assistant message: %s", exc)
                yield StreamUseCaseEvent(
                    "error",
                    {
                        "error_code": "PERSISTENCE_FAILED",
                        "message": "Không thể lưu câu trả lời. Vui lòng thử lại.",
                    },
                )
                return

            sources = _source_dicts(result)
            final_metadata = persisted["metadata"]
            yield StreamUseCaseEvent("sources", {"sources": sources})
            yield StreamUseCaseEvent(
                "metadata",
                {
                    "engine": final_metadata.get("engine", "unknown"),
                    "query_mode": final_metadata.get("query_mode", "auto"),
                    "execution_time_ms": final_metadata.get("execution_time_ms", 0.0),
                    "source_count": final_metadata.get("source_count", len(sources)),
                },
            )
            safety_raw = result.safety or {}
            yield StreamUseCaseEvent(
                "final",
                {
                    "conversation_id": conversation_id,
                    "message_id": persisted["message_id"],
                    "status": "success",
                    "response_type": result.response_type,
                    "answer": result.answer,
                    "data": result.data,
                    "sources": sources,
                    "safety": {
                        "level": safety_raw.get("level", "normal"),
                        "requires_emergency_notice": safety_raw.get("requires_emergency_notice", False),
                        "disclaimer": safety_raw.get("disclaimer", "Thông tin chỉ mang tính chất tham khảo."),
                    },
                    "suggested_questions": result.suggested_questions or [],
                    "metadata": final_metadata,
                },
            )
        except Exception as exc:
            logger.exception("Streaming error: %s", exc)
            yield StreamUseCaseEvent(
                "error",
                {
                    "error_code": "STREAM_ERROR",
                    "message": "Đã xảy ra lỗi trong quá trình phát câu trả lời.",
                },
            )


class ExportConversationUseCase:
    """Render a persisted conversation into an export artifact."""

    def __init__(self, *, manage_conversation) -> None:
        self._manage_conversation = manage_conversation

    def markdown(self, *, user_id: str, conversation_id: str) -> ExportedConversation | None:
        data = self._manage_conversation.get_conversation(
            user_id=user_id,
            conversation_id=conversation_id,
        )
        if data is None:
            return None

        conv = data["conversation"]
        lines = [f"# {conv.get('title', 'Conversation')}\n"]
        for message in data.get("messages", []):
            role = "**User**" if message["role"] == "user" else "**Assistant**"
            lines.append(f"{role}: {message['content']}\n")
        return ExportedConversation(
            filename=f"conversation-{conversation_id[:8]}.md",
            media_type="text/markdown",
            content="\n".join(lines).encode("utf-8"),
        )


def _source_dicts(result) -> list[dict[str, Any]]:
    return [
        {
            "id": source.get("id"),
            "source_type": source.get("source_type", "other"),
            "title": source.get("title", ""),
            "snippet": source.get("snippet"),
            "rank": source.get("rank", 1),
            "metadata": source.get("metadata", {}),
        }
        for source in (result.sources or [])
    ]
