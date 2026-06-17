"""AnswerQuestionStreamUseCase — Streaming variant of the QA pipeline.

Streams LightRAG tokens via async generator while also returning the
full AIServiceResult at completion.

Architecture:
- Cypher path: runs normally (no streaming), delivers result in one shot.
- LightRAG path: streams tokens via on_delta callback, then finalizes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable, Awaitable
from typing import Any

from use_cases.answer_question import AIServiceResult, AnswerQuestionUseCase
from domain.qa.pipeline import (
    QAPipeline, MSG_TIMEOUT, MSG_SYSTEM_ERROR, ENGINE_LIGHTRAG,
)
from domain.qa.response_formatter import format_lightrag_response

logger = logging.getLogger(__name__)

_USE_CASE_TIMEOUT = 260


class AnswerQuestionStreamUseCase:
    """Stream a QA response with native LightRAG token streaming.

    The streaming path is:
    1. Run intent classification + disambiguation (same as non-streaming).
    2. If Cypher → run normally, return full result.
    3. If LightRAG → stream tokens via on_delta, accumulate, return result.

    Args:
        graph, vector, llm: Same ports as AnswerQuestionUseCase.
        disable_cypher_path: Skip Cypher.
        default_lightrag_mode: LightRAG query mode.
    """

    def __init__(
        self,
        *,
        graph,
        vector,
        llm,
        intent_extractor=None,
        cypher_engine=None,
        disable_cypher_path: bool = False,
        default_lightrag_mode: str = "naive",
    ) -> None:
        self._graph = graph
        self._vector = vector
        self._llm = llm
        self._intent_extractor = intent_extractor
        self._cypher_engine = cypher_engine
        self._disable_cypher = disable_cypher_path
        self._default_mode = default_lightrag_mode

    async def execute(
        self,
        *,
        question: str,
        mode: str | None = None,
        preferences: dict[str, Any] | None = None,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> AIServiceResult:
        """Run the streaming pipeline.

        Tokens are emitted via on_delta (if provided).
        Returns the complete AIServiceResult when done.
        """
        start = time.monotonic()

        try:
            result = await asyncio.wait_for(
                self._run_with_streaming(question, mode, preferences, on_delta, start),
                timeout=_USE_CASE_TIMEOUT,
            )
            return result
        except asyncio.TimeoutError:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.error("AnswerQuestionStreamUseCase: timeout after %.0fms", elapsed_ms)
            return self._timeout_result(elapsed_ms, mode)
        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.exception("AnswerQuestionStreamUseCase: unexpected error: %s", exc)
            return self._error_result(elapsed_ms, mode)

    async def _run_with_streaming(
        self,
        question: str,
        mode: str | None,
        preferences: dict[str, Any] | None,
        on_delta: Callable[[str], Awaitable[None]] | None,
        start: float,
    ) -> AIServiceResult:
        """Internal: run with LightRAG native streaming on the LightRAG path."""
        pipeline = QAPipeline(
            graph=self._graph,
            vector=self._vector,
            llm=self._llm,
            intent_extractor=self._intent_extractor,
            cypher_engine=self._cypher_engine,
            disable_cypher_path=self._disable_cypher,
            default_lightrag_mode=self._default_mode,
        )

        decision = await pipeline.route_question(question, mode=mode)
        if decision.path == "lightrag":
            return await self._stream_lightrag(
                question,
                decision.mode or mode or self._default_mode,
                on_delta,
                start,
                preferences,
            )

        result = await pipeline.execute_route(question, decision, start)
        return self._normalize(result, question, preferences, start)

    async def _stream_lightrag(
        self,
        question: str,
        mode: str,
        on_delta: Callable[[str], Awaitable[None]] | None,
        start: float,
        preferences: dict[str, Any] | None,
    ) -> AIServiceResult:
        """Execute the LightRAG streaming path, collect tokens, return result."""
        from domain.qa.safety_policy import safety_from_response_type
        from domain.qa.source_policy import normalize_sources_from_pipeline

        logger.info("LightRAG streaming path: mode=%s", mode)
        try:
            effective_mode, chunks = await self._vector.query_stream(question, mode=mode)
            retrieval_context = getattr(chunks, "retrieval_context", {}) or {}
            answer_parts: list[str] = []
            async for chunk in chunks:
                text = str(chunk)
                if not text:
                    continue
                answer_parts.append(text)
                if on_delta is not None:
                    await on_delta(text)
        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            error_msg = str(exc)
            logger.error("LightRAG streaming failed: %s", error_msg)
            if "not installed" in error_msg.lower():
                code = "MODEL_UNAVAILABLE"
            else:
                code = "LIGHTRAG_QUERY_FAILED"
            return self._error_result(elapsed_ms, mode, error_code=code)

        elapsed_ms = (time.monotonic() - start) * 1000
        raw_answer = "".join(answer_parts).strip()
        formatted = format_lightrag_response(
            raw_answer=raw_answer,
            question=question,
            query_mode=effective_mode,
            execution_time_ms=elapsed_ms,
        )
        answer = formatted["answer"]

        meta = {
            **(formatted.get("metadata") or {}),
            "engine": ENGINE_LIGHTRAG,
            "query_mode": effective_mode,
            "execution_time_ms": round(elapsed_ms, 1),
        }
        for key in ("entities", "relationships", "chunks"):
            if retrieval_context.get(key):
                meta[key] = retrieval_context[key]
        if preferences:
            meta.update({
                "language": preferences.get("language"),
                "explanation_level": preferences.get("explanation_level"),
                "answer_style": preferences.get("answer_style"),
            })

        safety_vo = safety_from_response_type(formatted["response_type"], question)
        safety = {
            "level": safety_vo.level,
            "requires_emergency_notice": safety_vo.requires_emergency_notice,
            "disclaimer": safety_vo.disclaimer,
        }
        source_records = normalize_sources_from_pipeline(
            pipeline_metadata=meta, pipeline_result={"answer": answer}
        )
        sources = [
            {
                "id": s.id,
                "source_type": s.source_type,
                "title": s.title,
                "snippet": s.snippet,
                "rank": s.rank,
                "metadata": s.metadata,
            }
            for s in source_records
        ]
        meta["source_count"] = len(sources)
        suggested_questions: list[str] = []
        if (
            formatted["response_type"] not in {"warning", "disambiguation"}
            and safety.get("level") != "emergency"
            and not safety.get("requires_emergency_notice", False)
        ):
            from domain.qa.suggestion_policy import generate_suggestions

            suggested_questions = generate_suggestions(
                question=question,
                answer=answer,
                sources=sources,
                safety=safety,
                status="success",
                response_type=formatted["response_type"],
            )

        return AIServiceResult(
            answer=answer or "Không tìm thấy thông tin về chủ đề này.",
            response_type=formatted["response_type"],
            data=formatted.get("data"),
            sources=sources,
            safety=safety,
            suggested_questions=suggested_questions,
            metadata=meta,
            raw_pipeline_metadata=meta,
        )

    def _normalize(self, result, question, preferences, start):
        """Reuse AnswerQuestionUseCase normalization logic."""
        uc = AnswerQuestionUseCase(
            graph=self._graph,
            vector=self._vector,
            llm=self._llm,
            intent_extractor=self._intent_extractor,
            cypher_engine=self._cypher_engine,
            disable_cypher_path=self._disable_cypher,
            default_lightrag_mode=self._default_mode,
        )
        return uc._normalize(result, question, preferences, start)

    def _timeout_result(self, elapsed_ms: float, mode: str | None) -> AIServiceResult:
        return AIServiceResult(
            answer=MSG_TIMEOUT,
            response_type="text",
            data=None,
            sources=[{"source_type": "other", "title": "Hệ thống", "snippet": "", "rank": 1, "metadata": {}}],
            safety={"level": "safe", "requires_emergency_notice": False, "disclaimer": "Thông tin chỉ mang tính chất tham khảo."},
            suggested_questions=[],
            metadata={"error_code": "TIMEOUT", "engine": "unknown", "query_mode": mode or "auto", "execution_time_ms": round(elapsed_ms, 1), "source_count": 0},
            raw_pipeline_metadata={"error_code": "TIMEOUT"},
        )

    def _error_result(self, elapsed_ms: float, mode: str | None, error_code: str = "ADAPTER_ERROR") -> AIServiceResult:
        return AIServiceResult(
            answer=MSG_SYSTEM_ERROR,
            response_type="text",
            data=None,
            sources=[{"source_type": "other", "title": "Hệ thống", "snippet": "", "rank": 1, "metadata": {}}],
            safety={"level": "safe", "requires_emergency_notice": False, "disclaimer": "Thông tin chỉ mang tính chất tham khảo."},
            suggested_questions=[],
            metadata={"error_code": error_code, "engine": "unknown", "query_mode": mode or "auto", "execution_time_ms": round(elapsed_ms, 1), "source_count": 0},
            raw_pipeline_metadata={"error_code": error_code},
        )
