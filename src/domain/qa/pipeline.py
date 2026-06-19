"""Domain QA Pipeline — Pure business logic orchestrator.

This module contains ONLY routing + decision logic. It has NO I/O:
- No database calls
- No HTTP calls
- All external operations come through injected Port interfaces

Architecture:
    ┌─────────────────────┐
    │   User Question     │
    └─────────┬───────────┘
              │
    ┌─────────▼───────────┐
    │  QAPipeline.run()   │ ← domain-level orchestration
    └───┬────────────┬────┘
        │            │
   ┌────▼────┐  ┌───▼──────────────┐
   │ CYPHER  │  │  LIGHTRAG        │
   │  Path   │  │  (semantic)      │
   └────┬────┘  └──┬───────────────┘
        │          │
    ┌───▼──────────▼───┐
    │  PipelineResult  │
    └──────────────────┘
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from domain.qa.intent_classifier import FIND_BY_TYPES, IntentClassifier
from domain.qa.response_formatter import format_lightrag_response
from domain.qa.value_objects import QueryType

logger = logging.getLogger(__name__)

# ── Engine constants ──────────────────────────────────────────────────────
ENGINE_CYPHER = "cypher_direct"
ENGINE_LIGHTRAG = "lightrag"

# ── User-facing error messages ────────────────────────────────────────────
MSG_INVALID_QUESTION = "Vui lòng nhập câu hỏi hợp lệ."
MSG_MODEL_UNAVAILABLE = "Dịch vụ AI tạm thời không khả dụng. Vui lòng thử lại sau."
MSG_INVALID_MODE = "Chế độ truy vấn không hợp lệ."
MSG_GENERATION_FAILED = "Xin lỗi, tôi chưa hiểu câu hỏi. Bạn có thể diễn đạt lại được không?"
MSG_SYSTEM_ERROR = "Hệ thống đang gặp sự cố. Vui lòng thử lại sau."
MSG_TIMEOUT = "Xử lý mất quá lâu. Vui lòng thử câu hỏi ngắn hơn."
MSG_NO_DATA = "Không tìm thấy thông tin về chủ đề này trong cơ sở dữ liệu."
MSG_EMPTY_ANSWER = "Không tìm thấy thông tin về chủ đề này trong cơ sở dữ liệu y tế."


@dataclass
class PipelineResult:
    """Structured result from QAPipeline — normalized before returning to use case."""

    status: str                                  # "success" | "error"
    answer: str
    response_type: str                           # "text" | "disambiguation" | "warning"
    data: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None

    @property
    def is_success(self) -> bool:
        return self.status == "success"


@dataclass(frozen=True)
class PipelineRouteDecision:
    """Public routing decision shared by normal and streaming QA use cases."""

    path: str
    mode: str | None = None
    query_type: str | None = None
    entity: str | None = None
    exact: bool = False
    variants: list[str] = field(default_factory=list)


class QAPipeline:
    """Hybrid GraphRAG pipeline: Cypher path + LightRAG semantic path.

    All ports are injected — QAPipeline has zero direct dependencies on
    infrastructure. It can be tested entirely with in-memory adapters.

    Args:
        graph: IGraphRepository for Cypher/Neo4j queries.
        vector: IVectorRepository for LightRAG/Qdrant queries.
        llm: ILlmProvider for intent extraction + answer synthesis.
        disable_cypher_path: If True, skip Cypher and always use LightRAG.
        default_lightrag_mode: LightRAG query mode (naive/local/hybrid).
    """

    def __init__(
        self,
        *,
        graph,           # IGraphRepository
        vector,          # IVectorRepository
        llm,             # ILlmProvider
        intent_extractor=None,  # IIntentExtractor | None
        cypher_engine=None,     # ICypherQaEngine | None
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

    async def run(
        self,
        question: str,
        mode: str | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> PipelineResult:
        """Execute the hybrid pipeline and return a PipelineResult.

        Decision flow:
        1. Validate question.
        2. If disable_cypher or explicit mode → LightRAG directly.
        3. LLM intent extraction → (query_type, entity).
        4. Regex fallback if LLM returns no entity.
        5. Entity disambiguation via KG.
        6. Route: entity found in KG → Cypher, else → LightRAG.
        """
        start = time.monotonic()

        # ── Step 1: Validate ──────────────────────────────────────────────
        if not question or not question.strip():
            return self._error(
                "INVALID_QUESTION",
                MSG_INVALID_QUESTION,
                start,
            )

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
            logger.info("Pipeline: %s → LightRAG bypass", reason)
            return PipelineRouteDecision(path="lightrag", mode=mode or self._default_mode)

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
            query_type, entity, routing_method,
        )

        if query_type in FIND_BY_TYPES:
            if not entity:
                logger.info("Reverse type=%s but no keyword → LightRAG", query_type)
                return PipelineRouteDecision(path="lightrag", mode=self._default_mode)
            logger.info("Route → CYPHER (reverse type=%s keyword='%s')", query_type, entity)
            return PipelineRouteDecision(
                path="cypher",
                query_type=query_type,
                entity=entity,
                exact=False,
            )

        if not entity:
            logger.info("No entity extracted → LightRAG (method=%s)", routing_method)
            return PipelineRouteDecision(path="lightrag", mode=self._default_mode)

        canonical, variants = await self._disambiguate(entity)

        if not variants:
            logger.info("Entity '%s' not in KG → LightRAG auto-fallback", entity)
            return PipelineRouteDecision(path="lightrag", mode=self._default_mode)

        if canonical is None:
            return PipelineRouteDecision(
                path="disambiguation",
                entity=entity,
                variants=variants,
            )

        logger.info("Route → CYPHER (type=%s entity='%s')", query_type, canonical)
        return PipelineRouteDecision(
            path="cypher",
            query_type=query_type,
            entity=canonical,
            exact=True,
        )

    async def execute_route(
        self,
        question: str,
        decision: PipelineRouteDecision,
        start: float,
    ) -> PipelineResult:
        """Execute a public route decision and return a normalized pipeline result."""
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

    # ── Intent Extraction ─────────────────────────────────────────────────

    async def _extract_intent_llm(
        self, question: str
    ) -> tuple[str | None, str | None]:
        """Use injected LLM-based intent extractor; regex fallback handles failures."""
        if self._intent_extractor is None:
            return None, None
        try:
            return await self._intent_extractor.extract_intent(question)
        except Exception as exc:
            logger.warning("LLM intent extraction failed: %s — falling back to regex", exc)
            return None, None

    # ── Entity Disambiguation ─────────────────────────────────────────────

    async def _disambiguate(self, entity: str) -> tuple[str | None, list[str]]:
        """Resolve entity to canonical disease name via graph repository.

        Returns (canonical, variants):
        - (None, [])     → not in KG
        - (name, [name]) → single match
        - (name, [...])  → multiple, canonical found
        - (None, [...])  → multiple, no clear canonical → disambiguation
        """
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

    # ── Cypher Path ───────────────────────────────────────────────────────

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
            logger.warning("Cypher engine is not configured → LightRAG fallback")
            return await self._lightrag_path(question, self._default_mode, start)

        logger.info("Cypher path: type=%s entity='%s' exact=%s", query_type, disease_name, exact)

        # The cypher_graph_service still needs an execute_fn injected.
        # We bridge it through our graph repository.
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
                logger.info("Cypher → LightRAG fallback: %s", result.get("reason"))
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

        # Legacy Cypher template results expose deterministic table records when present.
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

    # ── LightRAG Path ─────────────────────────────────────────────────────

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

    # ── Helpers ───────────────────────────────────────────────────────────

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
