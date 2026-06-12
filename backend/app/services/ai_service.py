"""AI service adapter — S2-ARCH-01.

This module is the **only** backend service that may import ``ai_engine`` or
``app.services.pipeline`` directly.  All other services (chat_service, routers)
must call ``answer_question()`` from this module.

Responsibilities
----------------
- Call ``pipeline.run_pipeline()`` with the provided question and mode.
- Normalize the raw pipeline dict into an ``AIServiceResult``.
- Apply source normalization (``source_policy``) and safety classification
  (``safety_policy``).
- Handle all engine-level errors (timeout, exception, empty response, malformed
  metadata) and normalize them into a user-friendly ``AIServiceResult`` without
  leaking stack traces or credentials.

NOT responsible for
-------------------
- Persisting anything to Supabase (that is ``chat_service``'s job).
- Checking authorization (that is the router / ``api_gateway`` dependency).
- Rendering the response (that is the frontend / router's job).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.models.contracts import AIServiceResult, ChatMetadata, SafetyPayload
from app.services.safety_policy import safety_from_response_type
from app.services.source_policy import build_fallback_source, normalize_sources_from_pipeline
from app.services import suggestion_service

logger = logging.getLogger(__name__)

# ── Adapter-level timeout (seconds) ──────────────────────────────────────
# The pipeline already has its own internal timeout (PIPELINE_TIMEOUT_SECONDS).
# This outer guard is a safety net in case the pipeline hangs unexpectedly
# before reaching its own timeout.
_ADAPTER_TIMEOUT_SECONDS = 260

# ── Error answer strings ──────────────────────────────────────────────────
_MSG_SYSTEM_ERROR = (
    "Hệ thống đang gặp sự cố. Vui lòng thử lại sau ít phút."
)
_MSG_TIMEOUT = (
    "Xử lý mất quá lâu. Vui lòng thử câu hỏi ngắn hơn hoặc thử lại sau."
)
_MSG_EMPTY = (
    "Không tìm thấy thông tin về chủ đề này trong cơ sở dữ liệu y tế."
)


def _error_metadata(
    engine: str = "unknown",
    query_mode: str = "unknown",
    execution_time_ms: float = 0.0,
) -> ChatMetadata:
    return ChatMetadata(
        engine=engine,
        query_mode=query_mode,
        execution_time_ms=round(execution_time_ms, 1),
        source_count=0,
        cypher=None,
    )


def _build_result_from_pipeline(
    pipeline_result: dict[str, Any],
    question: str,
    execution_time_ms: float,
    preferences: dict[str, Any] | None = None,
) -> AIServiceResult:
    """Map a raw pipeline dict into an ``AIServiceResult``.

    Handles all field extraction defensively so malformed pipeline output
    never propagates as an unhandled exception.

    Args:
        pipeline_result: Raw dict from ``pipeline.run_pipeline()``.
        question: Original user question (for safety classification).
        execution_time_ms: Wall-clock time for the full call.

    Returns:
        A fully-populated ``AIServiceResult``.
    """
    if not isinstance(pipeline_result, dict):
        logger.warning("ai_service: pipeline returned non-dict result, using fallback")
        pipeline_result = {}

    # ── Extract core fields ───────────────────────────────────────────────
    status = pipeline_result.get("status", "error")
    response_type = pipeline_result.get("response_type", "text") or "text"
    answer = (pipeline_result.get("answer") or "").strip() or _MSG_EMPTY
    data = pipeline_result.get("data")

    # ── Extract metadata defensively ──────────────────────────────────────
    raw_meta: dict[str, Any] = pipeline_result.get("metadata") or {}
    if not isinstance(raw_meta, dict):
        logger.warning("ai_service: pipeline metadata is not a dict, using empty")
        raw_meta = {}
    if preferences:
        raw_meta = {
            **raw_meta,
            "language": preferences.get("language"),
            "explanation_level": preferences.get("explanation_level"),
            "answer_style": preferences.get("answer_style"),
            "preferences": {
                "language": preferences.get("language"),
                "explanation_level": preferences.get("explanation_level"),
                "answer_style": preferences.get("answer_style"),
            },
        }

    engine = str(raw_meta.get("engine", "unknown"))
    query_mode = str(raw_meta.get("query_mode", "unknown"))
    # Use the pipeline's measured time if available; our wall-clock is the
    # fallback when it is absent or zero.
    pipe_time = raw_meta.get("execution_time_ms")
    final_time = float(pipe_time) if pipe_time else execution_time_ms
    cypher = raw_meta.get("cypher")
    if cypher and not isinstance(cypher, str):
        cypher = str(cypher)

    # ── Safety ────────────────────────────────────────────────────────────
    # Combine pipeline response_type signal with question analysis.
    safety: SafetyPayload = safety_from_response_type(response_type, question)

    # ── Sources ───────────────────────────────────────────────────────────
    sources = normalize_sources_from_pipeline(
        pipeline_metadata=raw_meta,
        pipeline_result=pipeline_result,
    )

    # ── ChatMetadata ──────────────────────────────────────────────────────
    metadata = ChatMetadata(
        engine=engine,
        query_mode=query_mode,
        execution_time_ms=round(final_time, 1),
        source_count=len(sources),
        cypher=cypher,
        language=raw_meta.get("language"),
        explanation_level=raw_meta.get("explanation_level"),
        answer_style=raw_meta.get("answer_style"),
    )

    # ── Error status: override answer but keep metadata ───────────────────
    if status == "error":
        error_code = raw_meta.get("error_code", "UNKNOWN_ERROR")
        logger.info(
            "ai_service: pipeline returned error status (code=%s, mode=%s)",
            error_code,
            query_mode,
        )
        # The answer is already the user-friendly message from the pipeline.
        # Do not override unless it is empty.
        if not answer or answer == _MSG_EMPTY:
            answer = _MSG_SYSTEM_ERROR

    suggestions_allowed = (
        status == "success"
        and response_type not in {"warning", "disambiguation"}
        and safety.level != "emergency"
        and not safety.requires_emergency_notice
    )
    suggested_questions = []
    if suggestions_allowed:
        suggested_questions = suggestion_service.normalize_suggestions(
            pipeline_result.get("suggested_questions")
        )
        if not suggested_questions:
            suggested_questions = suggestion_service.generate_suggestions(
                question=question,
                answer=answer,
                sources=sources,
                safety=safety,
                status=status,
                response_type=response_type,
            )

    return AIServiceResult(
        answer=answer,
        response_type=response_type,
        data=data,
        sources=sources,
        safety=safety,
        suggested_questions=suggested_questions,
        metadata=metadata,
        raw_engine_metadata=raw_meta,
    )


def build_result_from_pipeline(
    *,
    pipeline_result: dict[str, Any],
    question: str,
    execution_time_ms: float,
    preferences: dict[str, Any] | None = None,
) -> AIServiceResult:
    """Public normalizer for streaming and non-streaming pipeline results."""
    return _build_result_from_pipeline(
        pipeline_result=pipeline_result,
        question=question,
        execution_time_ms=execution_time_ms,
        preferences=preferences,
    )


# ── Public API ─────────────────────────────────────────────────────────────


async def answer_question(
    *,
    question: str,
    mode: str | None = None,
    conversation_id: str | None = None,  # reserved for future context injection
    preferences: dict[str, Any] | None = None,
) -> AIServiceResult:
    """Execute the Hybrid GraphRAG pipeline and return a normalised result.

    This is the **single entry point** for all AI queries from the backend.
    It wraps ``pipeline.run_pipeline()`` and guarantees that:

    - Callers always receive an ``AIServiceResult`` (never a raw exception).
    - ``sources`` is never empty (fallback is used when engine provides none).
    - ``safety`` is always set.
    - No credentials, tokens, or stack traces leak into the result.

    Args:
        question: The user's natural language question.
        mode: Optional LightRAG query mode override (forces LightRAG path).
        conversation_id: Future use — conversation context for multi-turn Q&A.

    Returns:
        An ``AIServiceResult`` ready for ``chat_service`` to persist.

    Raises:
        Nothing.  All exceptions are caught and normalised.
    """
    from app.services.pipeline import run_pipeline  # local import to respect boundary

    start_time = time.time()

    try:
        pipeline_kwargs: dict[str, Any] = {"question": question, "mode": mode}
        if preferences is not None:
            pipeline_kwargs["preferences"] = preferences

        pipeline_result: dict[str, Any] = await asyncio.wait_for(
            run_pipeline(**pipeline_kwargs),
            timeout=_ADAPTER_TIMEOUT_SECONDS,
        )
        execution_time_ms = (time.time() - start_time) * 1000
        return build_result_from_pipeline(
            pipeline_result=pipeline_result,
            question=question,
            execution_time_ms=execution_time_ms,
            preferences=preferences,
        )

    except asyncio.TimeoutError:
        execution_time_ms = (time.time() - start_time) * 1000
        logger.error(
            "ai_service: adapter timeout after %.0fms for question: '%s'",
            execution_time_ms,
            question[:80],
        )
        fallback_source = build_fallback_source(engine="unknown", query_mode=mode or "auto")
        return AIServiceResult(
            answer=_MSG_TIMEOUT,
            response_type="text",
            data=None,
            sources=[fallback_source],
            safety=SafetyPayload(),
            suggested_questions=[],
            metadata=_error_metadata(
                engine="unknown",
                query_mode=mode or "auto",
                execution_time_ms=execution_time_ms,
            ),
            raw_engine_metadata={
                "error_code": "ADAPTER_TIMEOUT",
                "execution_time_ms": round(execution_time_ms, 1),
            },
        )

    except Exception:
        execution_time_ms = (time.time() - start_time) * 1000
        # Log with exc_info for internal debugging but do NOT include exception
        # message in the result (it may contain file paths, config values, etc.).
        logger.exception(
            "ai_service: unexpected error after %.0fms for question: '%s'",
            execution_time_ms,
            question[:80],
        )
        fallback_source = build_fallback_source(engine="unknown", query_mode=mode or "auto")
        return AIServiceResult(
            answer=_MSG_SYSTEM_ERROR,
            response_type="text",
            data=None,
            sources=[fallback_source],
            safety=SafetyPayload(),
            suggested_questions=[],
            metadata=_error_metadata(
                engine="unknown",
                query_mode=mode or "auto",
                execution_time_ms=execution_time_ms,
            ),
            raw_engine_metadata={
                "error_code": "ADAPTER_ERROR",
                "execution_time_ms": round(execution_time_ms, 1),
            },
        )
