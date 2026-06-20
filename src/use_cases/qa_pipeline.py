"""Application QA pipeline orchestration.

This module executes the pure domain routing policy through injected ports.
All graph/vector/LLM calls live here, not in ``domain``.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from domain.qa.intent_classifier import IntentClassifier
from domain.qa.pipeline import (
    ENGINE_CYPHER,
    ENGINE_LIGHTRAG,
    MSG_GENERATION_FAILED,
    MSG_INVALID_MODE,
    MSG_INVALID_QUESTION,
    MSG_MODEL_UNAVAILABLE,
    MSG_SYSTEM_ERROR,
    PipelineResult,
    PipelineRouteDecision,
    QAPipeline,
)
from domain.qa.response_formatter import format_lightrag_response

logger = logging.getLogger(__name__)


class ApplicationQAPipeline:
    """Hybrid GraphRAG pipeline executed in the application layer.

    Args:
        graph: IGraphRepository for Cypher/Neo4j queries.
        vector: IVectorRepository for LightRAG/Qdrant queries.
        llm: ILlmProvider for compatibility with existing constructor shape.
        intent_extractor: IIntentExtractor for LLM-backed intent extraction.
        cypher_engine: ICypherQaEngine for Cypher generation/execution synthesis.
        disable_cypher_path: If True, skip Cypher and always use LightRAG.
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
        self._classifier = IntentClassifier()
        self._routing = QAPipeline(
            disable_cypher_path=disable_cypher_path,
            default_lightrag_mode=default_lightrag_mode,
        )

    async def run(
        self,
        question: str,
        mode: str | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> PipelineResult:
        """Execute the hybrid pipeline and return a PipelineResult."""
        start = time.monotonic()

        if not question or not question.strip():
            return self._error("INVALID_QUESTION", MSG_INVALID_QUESTION, start)

        try:
            decision = await self.route_question(question, mode=mode)
            return await self.execute_route(question, decision, start)
        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.exception("Pipeline: unexpected error after %.0fms: %s", elapsed_ms, exc)
            return self._error("DATABASE_ERROR", MSG_SYSTEM_ERROR, start)

    async def route_question(
        self,
        question: str,
        mode: str | None = None,
    ) -> PipelineRouteDecision:
        """Return the Cypher/LightRAG/disambiguation decision for a question."""
        if self._disable_cypher or mode:
            reason = "disable_cypher_path" if self._disable_cypher else f"mode='{mode}'"
            logger.info("Pipeline: %s -> LightRAG bypass", reason)
            return self._routing.route_question(
                mode=mode,
                query_type=None,
                entity=None,
            )

        query_type, entity = await self._extract_intent_llm(question)
        routing_method = "llm"

        if entity is None:
            q_type_regex, entity_regex = self._classifier.classify(question)
            if q_type_regex:
                query_type = q_type_regex
            if entity_regex:
                entity = entity_regex
            routing_method = "regex_fallback"

        logger.info(
            "Pipeline: intent type=%s entity=%r method=%s",
            query_type,
            entity,
            routing_method,
        )

        canonical, variants = (None, [])
        if entity and query_type not in {
            "find_by_symptom",
            "find_by_medicine",
            "find_by_nutrition_avoid",
            "find_by_nutrition_eat",
            "find_by_prevention",
            "find_by_check_method",
        }:
            canonical, variants = await self._disambiguate(entity)

        decision = self._routing.route_question(
            mode=mode,
            query_type=query_type,
            entity=entity,
            canonical_entity=canonical,
            variants=variants,
        )
        logger.info("Pipeline route decided: %s", decision)
        return decision

    async def execute_route(
        self,
        question: str,
        decision: PipelineRouteDecision,
        start: float,
    ) -> PipelineResult:
        """Execute a route decision and return a normalized pipeline result."""
        if decision.path == "cypher":
            return await self._cypher_path(
                question,
                decision.entity,
                decision.query_type,
                start,
                exact=decision.exact,
            )
        if decision.path == "disambiguation":
            elapsed_ms = (time.monotonic() - start) * 1000
            return self._disambiguation_result(
                decision.entity or "",
                decision.variants,
                elapsed_ms,
            )
        return await self._lightrag_path(question, decision.mode or self._default_mode, start)

    async def _extract_intent_llm(
        self, question: str
    ) -> tuple[str | None, str | None]:
        """Use injected LLM-based intent extractor; regex fallback handles failures."""
        if self._intent_extractor is None:
            return None, None
        try:
            return await self._intent_extractor.extract_intent(question)
        except Exception as exc:
            logger.warning("LLM intent extraction failed: %s; falling back to regex", exc)
            return None, None

    async def _disambiguate(self, entity: str) -> tuple[str | None, list[str]]:
        """Resolve entity to canonical disease name via graph repository."""
        try:
            names = await self._graph.find_diseases_by_name(entity, limit=30)
        except Exception as exc:
            logger.warning("Disambiguation failed for %r: %s", entity, exc)
            return None, []

        if not names:
            return None, []
        if len(names) == 1:
            return names[0], names

        entity_lower = entity.lower().strip()
        exact = [n for n in names if n.lower() == entity_lower]
        if exact:
            return exact[0], names
        prefixed = [n for n in names if n.lower() == f"bệnh {entity_lower}"]
        if prefixed:
            return prefixed[0], names

        return None, names

    async def _cypher_path(
        self,
        question: str,
        disease_name: str | None,
        query_type: str | None,
        start: float,
        exact: bool = False,
    ) -> PipelineResult:
        """Execute Cypher path via injected QA engine."""
        if self._cypher_engine is None:
            logger.warning("Cypher engine is not configured -> LightRAG fallback")
            return await self._lightrag_path(question, self._default_mode, start)

        logger.info("Cypher path: type=%s entity='%s' exact=%s", query_type, disease_name, exact)

        async def _execute_fn(cypher: str, params: dict | None = None):
            return await self._graph.execute_cypher(cypher, params)

        result = await self._cypher_engine.query(
            question=question,
            query_type=query_type,
            entity=disease_name,
            exact=exact,
            execute_fn=_execute_fn,
        )
        elapsed_ms = (time.monotonic() - start) * 1000

        if not result["success"]:
            if result.get("fallback"):
                logger.info("Cypher -> LightRAG fallback: %s", result.get("reason"))
                return await self._lightrag_path(question, self._default_mode, start)
            return self._error(
                result.get("error_code", "CYPHER_GENERATION_FAILED"),
                MSG_GENERATION_FAILED,
                start,
            )

        answer_text = result["answer"]
        cypher = result["cypher"]
        use_template = result["used_template"]
        records = result["records"]

        query_mode = f"cypher:{'template' if use_template else 'llm'}:{query_type}"
        formatted = format_lightrag_response(
            raw_answer=answer_text,
            question=question,
            query_mode=query_mode,
            execution_time_ms=elapsed_ms,
        )

        data = self._extract_structured_data(query_type, records) if use_template else formatted.get("data")

        return PipelineResult(
            status="success",
            answer=formatted["answer"],
            response_type=formatted["response_type"],
            data=data,
            metadata={
                "engine": ENGINE_CYPHER,
                "query_mode": query_mode,
                "execution_time_ms": round(elapsed_ms, 1),
                "source_count": len(data) if data else formatted.get("metadata", {}).get("source_count", 1),
                "cypher": cypher.strip(),
            },
        )

    async def _lightrag_path(
        self, question: str, mode: str | None, start: float
    ) -> PipelineResult:
        """Execute LightRAG semantic retrieval path."""
        logger.info("LightRAG path: mode=%s", mode or "default")
        result = await self._vector.query(question, mode=mode or self._default_mode)
        elapsed_ms = (time.monotonic() - start) * 1000

        if not result.get("success"):
            error_msg = result.get("error", "Unknown error")
            logger.error(
                "LightRAG path failed in %.0fms (mode=%s): %s",
                elapsed_ms,
                mode or self._default_mode,
                error_msg,
            )
            if "not installed" in error_msg.lower():
                code, msg = "MODEL_UNAVAILABLE", MSG_MODEL_UNAVAILABLE
            elif "invalid query mode" in error_msg.lower():
                code, msg = "INVALID_QUESTION", MSG_INVALID_MODE
            else:
                code, msg = "LIGHTRAG_QUERY_FAILED", MSG_GENERATION_FAILED
            return self._error(code, msg, start)

        effective_mode = result.get("mode", mode or self._default_mode)
        formatted = format_lightrag_response(
            raw_answer=result.get("answer", ""),
            question=question,
            query_mode=effective_mode,
            execution_time_ms=elapsed_ms,
        )
        metadata = dict(formatted.get("metadata") or {})
        metadata.update({
            "engine": ENGINE_LIGHTRAG,
            "query_mode": effective_mode,
            "execution_time_ms": round(elapsed_ms, 1),
        })
        for key in ("entities", "relationships", "chunks"):
            if result.get(key):
                metadata[key] = result[key]

        logger.info(
            "LightRAG path completed in %.0fms (type=%s, mode=%s, answer_length=%d, data_count=%d)",
            elapsed_ms,
            formatted["response_type"],
            effective_mode,
            len(formatted["answer"]),
            len(formatted.get("data") or []),
        )

        return PipelineResult(
            status="success",
            answer=formatted["answer"],
            response_type=formatted["response_type"],
            data=formatted.get("data"),
            metadata=metadata,
        )

    def _error(
        self, error_code: str, user_message: str, start: float
    ) -> PipelineResult:
        elapsed_ms = (time.monotonic() - start) * 1000
        return PipelineResult(
            status="error",
            answer=user_message,
            response_type="text",
            error_code=error_code,
            metadata={
                "error_code": error_code,
                "execution_time_ms": round(elapsed_ms, 1),
                "engine": "unknown",
                "query_mode": "unknown",
            },
        )

    def _disambiguation_result(
        self, original_entity: str, variants: list[str], elapsed_ms: float
    ) -> PipelineResult:
        options = [
            {
                "id": "disease:" + re.sub(r"[^0-9A-Za-zÀ-ỹ]+", "-", label).strip("-").lower(),
                "label": label,
                "description": "Bệnh trong cơ sở tri thức VietMedKG.",
                "entity_type": "Disease",
                "confidence": round(max(0.5, 0.95 - idx * 0.03), 2),
            }
            for idx, label in enumerate(variants[:10])
        ]
        more = f" Hiển thị 10/{len(variants)} lựa chọn." if len(variants) > 10 else ""
        return PipelineResult(
            status="success",
            response_type="disambiguation",
            answer=(
                f'Tìm thấy {len(variants)} bệnh liên quan đến "{original_entity}". '
                f"Vui lòng chọn bệnh bạn muốn hỏi.{more}"
            ),
            data=options,
            metadata={
                "query_mode": "cypher:disambiguation",
                "execution_time_ms": round(elapsed_ms, 1),
                "source_count": len(options),
                "engine": ENGINE_CYPHER,
            },
        )

    @staticmethod
    def _extract_structured_data(
        query_type: str | None, records: list[dict]
    ) -> list[dict] | None:
        if not records:
            return None
        data = [{k: v for k, v in r.items() if v is not None and k != "disease"} for r in records]
        return [d for d in data if d] or None
