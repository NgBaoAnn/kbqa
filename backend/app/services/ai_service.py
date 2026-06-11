"""AI service adapter — bridges chat_service to the existing pipeline.

This is the ONLY module that calls `pipeline.run_pipeline` from the
conversation flow. Routers and chat_service must not call pipeline directly.
"""

from __future__ import annotations

import logging
from typing import Any

from app.models.contracts import (
    ChatMetadata,
    ChatResponse,
    SafetyPayload,
)

logger = logging.getLogger(__name__)


def _safety_from_response_type(response_type: str) -> SafetyPayload:
    """Derive a SafetyPayload from the pipeline response_type field."""
    if response_type == "warning":
        return SafetyPayload(
            level="caution",
            requires_emergency_notice=False,
            disclaimer=(
                "Thông tin chỉ mang tính chất tham khảo. "
                "Vui lòng tham khảo ý kiến bác sĩ."
            ),
        )
    return SafetyPayload()


def _map_pipeline_result(
    *,
    conversation_id: str,
    message_id: str,
    result: dict[str, Any],
    question: str,
) -> ChatResponse:
    """Map the legacy pipeline dict → ChatResponse contract.

    The pipeline returns a QueryResponse-shaped dict:
        {
            status, response_type, answer, data,
            metadata: { engine, query_mode, execution_time_ms,
                        source_count, cypher, ... }
        }
    """
    metadata_raw: dict[str, Any] = result.get("metadata", {})
    response_type: str = result.get("response_type", "text")
    answer: str = result.get("answer", "")

    chat_metadata = ChatMetadata(
        engine=metadata_raw.get("engine", "unknown"),
        query_mode=str(metadata_raw.get("query_mode", "unknown")),
        execution_time_ms=float(metadata_raw.get("execution_time_ms", 0)),
        source_count=int(metadata_raw.get("source_count", 0)),
        cypher=metadata_raw.get("cypher"),
    )

    safety = _safety_from_response_type(response_type)

    return ChatResponse(
        conversation_id=conversation_id,
        message_id=message_id,
        status="success",
        response_type=response_type,
        answer=answer,
        data=result.get("data"),
        sources=[],
        safety=safety,
        suggested_questions=[],
        metadata=chat_metadata,
    )


async def answer_question(
    *,
    conversation_id: str,
    message_id: str,
    question: str,
    mode: str | None = None,
) -> ChatResponse:
    """Run the Hybrid GraphRAG pipeline and return a ChatResponse.

    Falls back to an error ChatResponse if the pipeline fails, so
    chat_service always gets a usable response object.
    """
    from app.services.pipeline import run_pipeline

    logger.info(
        "ai_service: answering question for conversation=%s mode=%s",
        conversation_id,
        mode or "auto",
    )

    try:
        result = await run_pipeline(question=question, mode=mode)
    except Exception as exc:
        logger.exception("ai_service: pipeline raised unexpectedly: %s", exc)
        result = {
            "status": "error",
            "response_type": "text",
            "answer": "Hệ thống đang gặp sự cố. Vui lòng thử lại sau.",
            "data": None,
            "metadata": {
                "engine": "error",
                "query_mode": "error",
                "execution_time_ms": 0,
                "source_count": 0,
            },
        }

    return _map_pipeline_result(
        conversation_id=conversation_id,
        message_id=message_id,
        result=result,
        question=question,
    )
