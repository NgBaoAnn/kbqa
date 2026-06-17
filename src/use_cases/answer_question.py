"""AnswerQuestionUseCase — Main QA use case.

Orchestrates the full question-answering flow:
1. Run QAPipeline (domain logic).
2. Apply safety policy.
3. Normalize sources.
4. Generate suggested questions.

NO persistence here — that is ManageConversationUseCase's job.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from domain.qa.pipeline import QAPipeline, PipelineResult, MSG_TIMEOUT, MSG_SYSTEM_ERROR

logger = logging.getLogger(__name__)

# Safety net timeout (seconds) — the pipeline has its own internal timeout.
_USE_CASE_TIMEOUT = 260


@dataclass
class AIServiceResult:
    """Normalized result from AnswerQuestionUseCase — ready for API serialization."""

    answer: str
    response_type: str                              # "text" | "disambiguation" | "warning"
    data: list[dict[str, Any]] | None
    sources: list[dict[str, Any]]
    safety: dict[str, Any]
    suggested_questions: list[str]
    metadata: dict[str, Any]
    raw_pipeline_metadata: dict[str, Any]


class AnswerQuestionUseCase:
    """Execute the Medical QA pipeline for a single question.

    Args:
        graph: IGraphRepository
        vector: IVectorRepository
        llm: ILlmProvider
        disable_cypher_path: Skip Cypher, always use LightRAG.
        default_lightrag_mode: LightRAG query mode.
    """

    def __init__(
        self,
        *,
        graph,
        vector,
        llm,
        disable_cypher_path: bool = False,
        default_lightrag_mode: str = "naive",
    ) -> None:
        self._pipeline = QAPipeline(
            graph=graph,
            vector=vector,
            llm=llm,
            disable_cypher_path=disable_cypher_path,
            default_lightrag_mode=default_lightrag_mode,
        )

    async def execute(
        self,
        *,
        question: str,
        mode: str | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> AIServiceResult:
        """Run the pipeline and normalize the result.

        Always returns an AIServiceResult — never raises.
        """
        start = time.monotonic()

        try:
            result: PipelineResult = await asyncio.wait_for(
                self._pipeline.run(question, mode=mode, preferences=preferences),
                timeout=_USE_CASE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.error("AnswerQuestionUseCase: timeout after %.0fms", elapsed_ms)
            return self._timeout_result(elapsed_ms, mode)
        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.exception("AnswerQuestionUseCase: unexpected error: %s", exc)
            return self._error_result(elapsed_ms, mode)

        return self._normalize(result, question, preferences, start)

    def _normalize(
        self,
        result: PipelineResult,
        question: str,
        preferences: dict[str, Any] | None,
        start: float,
    ) -> AIServiceResult:
        """Map PipelineResult → AIServiceResult with safety + sources + suggestions."""
        from domain.qa.safety_policy import safety_from_response_type
        from domain.qa.source_policy import normalize_sources_from_pipeline

        elapsed_ms = (time.monotonic() - start) * 1000
        meta = result.metadata.copy()

        # Attach preferences to metadata for traceability
        if preferences:
            meta.update({
                "language": preferences.get("language"),
                "explanation_level": preferences.get("explanation_level"),
                "answer_style": preferences.get("answer_style"),
                "preferences": {
                    "language": preferences.get("language"),
                    "explanation_level": preferences.get("explanation_level"),
                    "answer_style": preferences.get("answer_style"),
                },
            })

        # Safety classification — takes response_type + question
        safety_vo = safety_from_response_type(result.response_type, question)
        safety = {
            "level": safety_vo.level,
            "requires_emergency_notice": safety_vo.requires_emergency_notice,
            "disclaimer": safety_vo.disclaimer,
        }

        # Sources normalization — returns list[SourceRecord]
        source_records = normalize_sources_from_pipeline(
            pipeline_metadata=meta,
            pipeline_result=result.__dict__,
        )
        # Serialize to plain dicts for API layer
        sources = [
            {
                "source_type": s.source_type,
                "title": s.title,
                "snippet": s.snippet,
                "rank": s.rank,
                "metadata": s.metadata,
            }
            for s in source_records
        ]

        # Suggestion generation (only for successful non-warning responses)
        suggested_questions: list[str] = []
        allow_suggestions = (
            result.is_success
            and result.response_type not in {"warning", "disambiguation"}
            and safety.get("level") != "emergency"
            and not safety.get("requires_emergency_notice", False)
        )
        if allow_suggestions:
            suggested_questions = self._generate_suggestions(question, result.answer, sources, safety)

        # Final metadata
        final_meta = {
            **meta,
            "engine": meta.get("engine", "unknown"),
            "query_mode": meta.get("query_mode", "unknown"),
            "execution_time_ms": round(meta.get("execution_time_ms", elapsed_ms), 1),
            "source_count": len(sources),
            "cypher": meta.get("cypher"),
        }

        return AIServiceResult(
            answer=(result.answer or "Không tìm thấy thông tin về chủ đề này trong cơ sở dữ liệu y tế.").strip(),
            response_type=result.response_type,
            data=result.data,
            sources=sources,
            safety=safety,
            suggested_questions=suggested_questions,
            metadata=final_meta,
            raw_pipeline_metadata=meta,
        )

    def _generate_suggestions(
        self,
        question: str,
        answer: str,
        sources: list[dict],
        safety: dict,
    ) -> list[str]:
        """Generate follow-up question suggestions (delegates to legacy service for now)."""
        try:
            from app.services import suggestion_service
            return suggestion_service.generate_suggestions(
                question=question,
                answer=answer,
                sources=sources,
                safety=safety,
                status="success",
                response_type="text",
            )
        except Exception as exc:
            logger.debug("suggestion generation failed: %s", exc)
            return []

    def _timeout_result(self, elapsed_ms: float, mode: str | None) -> AIServiceResult:
        return AIServiceResult(
            answer=MSG_TIMEOUT,
            response_type="text",
            data=None,
            sources=[{"source_type": "knowledge_graph", "title": "Hệ thống", "snippet": "", "rank": 1, "metadata": {}}],
            safety={"level": "safe", "requires_emergency_notice": False},
            suggested_questions=[],
            metadata={"error_code": "TIMEOUT", "engine": "unknown", "query_mode": mode or "auto", "execution_time_ms": round(elapsed_ms, 1), "source_count": 0},
            raw_pipeline_metadata={"error_code": "TIMEOUT"},
        )

    def _error_result(self, elapsed_ms: float, mode: str | None) -> AIServiceResult:
        return AIServiceResult(
            answer=MSG_SYSTEM_ERROR,
            response_type="text",
            data=None,
            sources=[{"source_type": "knowledge_graph", "title": "Hệ thống", "snippet": "", "rank": 1, "metadata": {}}],
            safety={"level": "safe", "requires_emergency_notice": False},
            suggested_questions=[],
            metadata={"error_code": "ADAPTER_ERROR", "engine": "unknown", "query_mode": mode or "auto", "execution_time_ms": round(elapsed_ms, 1), "source_count": 0},
            raw_pipeline_metadata={"error_code": "ADAPTER_ERROR"},
        )
