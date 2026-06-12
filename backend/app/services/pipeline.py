"""Query Pipeline Orchestrator — Hybrid Architecture (Phương án C).

Dual-path pipeline:
    ┌─────────────────┐
    │   Câu hỏi NL    │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │  Query Router    │ — Phân tích câu hỏi
    └───┬─────────┬───┘
        │         │
   ┌────▼───┐ ┌──▼──────────────────────┐
   │ CYPHER │ │  LIGHTRAG (local)          │
   │ Path   │ │  Entity + Rel search       │
   │        │ │                            │
   │ Text2  │ │  bge-m3 embed(question)    │
   │ Cypher │ │    → top-k entities        │
   │   ↓    │ │    → related rels          │
   │ Neo4j  │ │    → LLM synthesis         │
   │ (KBQA  │ │                            │
   │  graph)│ │  NOTE: local mode uses     │
   │   ↓    │ │  entity+rel search on      │
   │ Format │ │  Qdrant (3 collections).   │
   └───┬────┘ └──┬──────────────────────┘
       │         │
    ┌──▼─────────▼──┐
    │  API Response   │
    └────────────────┘
"""

import asyncio
import logging
import os
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.config import DISABLE_CYPHER_PATH

logger = logging.getLogger(__name__)

# Pipeline-level timeout (seconds).
# Worst case: intent extraction (~30s) + LightRAG mix synthesis (~78s) = ~110s.
# Set to 240s to accommodate cold Ollama model starts and mix mode queries.
PIPELINE_TIMEOUT_SECONDS = 240

# LightRAG default mode — đọc từ DEFAULT_QUERY_MODE trong .env để config một chỗ duy nhất.
_LIGHTRAG_MODE = os.getenv("DEFAULT_QUERY_MODE", "naive")

MSG_INVALID_QUESTION = "Vui lòng nhập câu hỏi hợp lệ."
MSG_MODEL_UNAVAILABLE = "Dịch vụ AI tạm thời không khả dụng. Vui lòng thử lại sau."
MSG_INVALID_MODE = "Chế độ truy vấn không hợp lệ."
MSG_GENERATION_FAILED = "Xin lỗi, tôi chưa hiểu câu hỏi. Bạn có thể diễn đạt lại được không?"
MSG_SYSTEM_ERROR = "Hệ thống đang gặp sự cố. Vui lòng thử lại sau."
MSG_TIMEOUT = "Xử lý mất quá lâu. Vui lòng thử câu hỏi ngắn hơn."
MSG_NO_DATA = "Không tìm thấy thông tin về chủ đề này trong cơ sở dữ liệu."

# ── Engine name constants ─────────────────────────────────────────────────
ENGINE_CYPHER = "cypher_direct"
ENGINE_LIGHTRAG = "lightrag"
LightRagExecutor = Callable[[str, str | None, float], Awaitable[dict[str, Any]]]


async def run_pipeline(
    question: str,
    mode: str | None = None,
    preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute the Hybrid Medical QA pipeline (Phương án C).

    Decision logic:
        1. Query Router analyzes the question
        2. If precise lookup → Cypher path (direct Neo4j query)
        3. If semantic/thematic → LightRAG path (graph-enhanced retrieval)
        4. Format response according to API contract

    Args:
        question: The user's natural language question.
        mode: LightRAG query mode override. If set, forces LightRAG path.

    Returns:
        Dict conforming to the QueryResponse schema.
    """
    from ai_engine.utils.response_formatter import format_error_response

    start_time = time.time()

    # ── Step 0: Wrap in timeout ────────────────────────────────────────────
    try:
        result = await asyncio.wait_for(
            _run_pipeline_inner(question, mode, start_time, _execute_lightrag_path),
            timeout=PIPELINE_TIMEOUT_SECONDS,
        )
        return _with_request_context(result, preferences)
    except asyncio.TimeoutError:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.error("Pipeline timeout after %.0fms", elapsed_ms)
        return _with_request_context(format_error_response(
            error_code="TIMEOUT",
            error_message=f"Pipeline exceeded {PIPELINE_TIMEOUT_SECONDS}s timeout",
            user_message=MSG_TIMEOUT,
            execution_time_ms=elapsed_ms,
        ), preferences)


async def run_pipeline_stream(
    question: str,
    mode: str | None = None,
    preferences: dict[str, Any] | None = None,
    on_delta: Callable[[str], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Execute the pipeline while streaming native LightRAG chunks when available."""
    from ai_engine.utils.response_formatter import format_error_response

    start_time = time.time()

    async def _streaming_lightrag_executor(
        q: str,
        m: str | None,
        s: float,
    ) -> dict[str, Any]:
        return await _execute_lightrag_path_stream(q, m, s, on_delta)

    try:
        result = await asyncio.wait_for(
            _run_pipeline_inner(question, mode, start_time, _streaming_lightrag_executor),
            timeout=PIPELINE_TIMEOUT_SECONDS,
        )
        return _with_request_context(result, preferences)
    except asyncio.TimeoutError:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.error("Pipeline stream timeout after %.0fms", elapsed_ms)
        return _with_request_context(format_error_response(
            error_code="TIMEOUT",
            error_message=f"Pipeline exceeded {PIPELINE_TIMEOUT_SECONDS}s timeout",
            user_message=MSG_TIMEOUT,
            execution_time_ms=elapsed_ms,
        ), preferences)


async def _run_pipeline_inner(
    question: str,
    mode: str | None,
    start_time: float,
    lightrag_executor: LightRagExecutor,
) -> dict[str, Any]:
    """Inner pipeline logic (wrapped by timeout in run_pipeline).

    Hybrid routing strategy:
      1. Regex fast path → (query_type, entity)
      2. LLM fallback when regex yields no valid entity
      3. Data-driven path selection: entity present in KG → CYPHER, else → LIGHTRAG
    """
    from ai_engine.services.query_router import classify_cypher_intent, extract_intent_with_llm
    from ai_engine.utils.response_formatter import format_error_response, format_lightrag_response

    # ── Step 1: Validate input ────────────────────────────────────────────
    if not question or not question.strip():
        elapsed_ms = (time.time() - start_time) * 1000
        return format_error_response(
            error_code="INVALID_QUESTION",
            error_message="Question is empty or whitespace-only.",
            user_message=MSG_INVALID_QUESTION,
            execution_time_ms=elapsed_ms,
        )

    try:
        # ── Step 2: Bypass Cypher khi flag bật toàn cục hoặc mode được set ──
        if DISABLE_CYPHER_PATH or mode:
            reason = "DISABLE_CYPHER_PATH" if DISABLE_CYPHER_PATH else f"mode='{mode}'"
            logger.info("Pipeline: %s → LightRAG (bypass Cypher)", reason)
            return await lightrag_executor(question, mode or _LIGHTRAG_MODE, start_time)

        # ── Step 3: LLM Intent Extraction (Accuracy First) ──────────────────
        query_type, entity = await extract_intent_with_llm(question)
        routing_method = "llm"

        # ── Step 4: Regex fallback when LLM fails or misses entity ──────────
        if entity is None:
            q_type_regex, entity_regex = classify_cypher_intent(question)
            if q_type_regex:
                query_type = q_type_regex
            if entity_regex:
                entity = entity_regex
            routing_method = "regex_fallback"

        logger.info(
            "Pipeline: intent type=%s entity=%r method=%s",
            query_type, entity, routing_method,
        )

        # ── Step 4b: Reverse-query types skip entity disambiguation ─────────
        # Entity here is a keyword/constraint, not a disease name.
        from ai_engine.services.query_router import _FIND_BY_TYPES
        if query_type in _FIND_BY_TYPES:
            if not entity:
                logger.info("Reverse type=%s but no keyword → LightRAG", query_type)
                return await lightrag_executor(question, _LIGHTRAG_MODE, start_time)
            logger.info(
                "Route → CYPHER (reverse type=%s keyword='%s' method=%s)",
                query_type, entity, routing_method,
            )
            return await _execute_cypher_path(
                question=question,
                disease_name=entity,
                query_type=query_type,
                start_time=start_time,
                exact=False,
                lightrag_executor=lightrag_executor,
            )

        # ── Step 5: No entity identified → LIGHTRAG ───────────────────────
        if not entity:
            logger.info("No entity extracted → LightRAG (method=%s)", routing_method)
            return await lightrag_executor(question, _LIGHTRAG_MODE, start_time)

        # ── Step 6: Data-driven check — is entity in KG? ──────────────────
        canonical, variants = await _disambiguate_entity(entity)

        if not variants:
            # KG has no record for this entity → auto-fallback to semantic path
            logger.info("Entity '%s' not in KG → LightRAG auto-fallback", entity)
            return await lightrag_executor(question, _LIGHTRAG_MODE, start_time)

        if canonical is None:
            # Multiple candidates, no clear winner → ask user to narrow down
            elapsed_ms = (time.time() - start_time) * 1000
            return _format_disambiguation_response(
                original_entity=entity,
                variants=variants,
                execution_time_ms=elapsed_ms,
            )

        # ── Step 7: Canonical found → CYPHER with exact match ─────────────
        logger.info(
            "Route → CYPHER (type=%s entity='%s' method=%s)",
            query_type, canonical, routing_method,
        )
        return await _execute_cypher_path(
            question=question,
            disease_name=canonical,
            query_type=query_type,
            start_time=start_time,
            exact=True,
            lightrag_executor=lightrag_executor,
        )

    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.exception("Pipeline: unexpected error: %s", e)

        return format_error_response(
            error_code="DATABASE_ERROR",
            error_message=str(e),
            user_message=MSG_SYSTEM_ERROR,
            execution_time_ms=elapsed_ms,
        )


# ── Entity Disambiguation ─────────────────────────────────────────────────


def _with_request_context(
    response: dict[str, Any],
    preferences: dict[str, Any] | None,
) -> dict[str, Any]:
    """Attach request preferences to pipeline metadata for traceability."""
    if not preferences:
        return response

    metadata = response.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
        response["metadata"] = metadata

    context = {
        "language": preferences.get("language"),
        "explanation_level": preferences.get("explanation_level"),
        "answer_style": preferences.get("answer_style"),
    }
    metadata.update(context)
    metadata["preferences"] = context
    return response


def _format_disambiguation_response(
    *,
    original_entity: str,
    variants: list[str],
    execution_time_ms: float,
) -> dict[str, Any]:
    options = [
        {
            "id": _disambiguation_option_id(label),
            "label": label,
            "description": "Bệnh trong cơ sở tri thức VietMedKG.",
            "entity_type": "Disease",
            "confidence": round(max(0.5, 0.95 - index * 0.03), 2),
        }
        for index, label in enumerate(variants[:10])
    ]
    more_text = f" Hiển thị 10/{len(variants)} lựa chọn phù hợp nhất." if len(variants) > 10 else ""
    return {
        "status": "success",
        "response_type": "disambiguation",
        "answer": (
            f'Tìm thấy {len(variants)} bệnh liên quan đến "{original_entity}". '
            f"Vui lòng chọn bệnh bạn muốn hỏi.{more_text}"
        ),
        "data": options,
        "metadata": {
            "query_mode": "cypher:disambiguation",
            "execution_time_ms": round(execution_time_ms, 1),
            "source_count": len(options),
            "engine": ENGINE_CYPHER,
        },
    }


def _disambiguation_option_id(label: str) -> str:
    return "disease:" + re.sub(r"[^0-9A-Za-zÀ-ỹ]+", "-", label).strip("-").lower()


async def _disambiguate_entity(entity: str) -> tuple[str | None, list[str]]:
    """Resolve entity to a canonical disease name.

    Returns (canonical, variants):
    - (None, [])        → entity not found in KG
    - (name, [name])    → single match, use directly
    - (name, [...])     → multiple, canonical found via exact / prefixed-exact match
    - (None, [...])     → multiple, no clear canonical → caller returns disambiguation list
    """
    from app.services.graph_service import execute_cypher as _neo4j_exec

    try:
        rows = await _neo4j_exec(
            "MATCH (d:Disease) WHERE toLower(d.disease_name) CONTAINS toLower($name) "
            "RETURN d.disease_name AS name ORDER BY name LIMIT 30",
            {"name": entity},
        )
    except Exception as exc:
        logger.warning("Disambiguation failed for %r: %s", entity, exc)
        return None, []

    names = [r["name"] for r in rows if r.get("name")]

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


# ── Cypher Path (Direct Neo4j VietMedKG) ─────────────────────────────────


async def _execute_cypher_path(
    question: str,
    disease_name: str | None,
    query_type: str | None,
    start_time: float,
    exact: bool = False,
    lightrag_executor: LightRagExecutor | None = None,
) -> dict[str, Any]:
    """Execute the Cypher path via cypher_graph_service facade.

    Caller is responsible for disambiguation; disease_name (when provided) is
    already the canonical KG name. exact=True generates a direct equality match.
    """
    from ai_engine.services.cypher_graph_service import query as _cypher_query
    from ai_engine.utils.response_formatter import format_error_response, format_lightrag_response
    from app.services.graph_service import execute_cypher as _neo4j_exec

    logger.info("Cypher path: type=%s entity='%s' exact=%s", query_type, disease_name, exact)

    result = await _cypher_query(
        question=question,
        query_type=query_type,
        entity=disease_name,
        exact=exact,
        execute_fn=_neo4j_exec,
    )

    elapsed_ms = (time.time() - start_time) * 1000

    if not result["success"]:
        if result.get("fallback"):
            logger.info("Cypher path → LightRAG fallback: %s", result.get("reason"))
            executor = lightrag_executor or _execute_lightrag_path
            return await executor(question, _LIGHTRAG_MODE, start_time)
        logger.error("Cypher hard error: %s", result.get("error_code"))
        return format_error_response(
            error_code=result["error_code"],
            error_message=result.get("error_message", ""),
            user_message=MSG_GENERATION_FAILED,
            execution_time_ms=elapsed_ms,
        )

    answer_text = result["answer"]
    cypher = result["cypher"]
    use_template = result["used_template"]
    records = result["records"]

    response = format_lightrag_response(
        raw_answer=answer_text,
        question=question,
        query_mode=f"cypher:{'template' if use_template else 'llm'}:{query_type}",
        execution_time_ms=elapsed_ms,
    )
    response["metadata"]["engine"] = ENGINE_CYPHER
    response["metadata"]["cypher"] = cypher.strip()

    if use_template:
        structured = _extract_structured_data(query_type, records)
        if structured:
            response["data"] = structured
            response["metadata"]["source_count"] = len(structured)

    logger.info(
        "Cypher path done in %.0fms (type=%s entity='%s' template=%s records=%d)",
        elapsed_ms, query_type, disease_name, use_template, len(records),
    )
    return response


def _extract_structured_data(query_type: str, records: list[dict]) -> list[dict] | None:
    """Extract structured data from Cypher results for table rendering."""
    if not records:
        return None

    # For other types, extract key fields
    data = []
    for r in records:
        # Filter out None values and internal fields
        item = {k: v for k, v in r.items() if v is not None and k != "disease"}
        if item:
            data.append(item)

    return data if data else None


# ── LightRAG Path (Semantic Retrieval) ────────────────────────────────────


async def _execute_lightrag_path(
    question: str,
    mode: str | None,
    start_time: float,
) -> dict[str, Any]:
    """Execute the LightRAG semantic path — local mode (entity + relationship vector search).

    Uses bge-m3 embeddings stored in Qdrant Cloud:
    - lightrag_vdb_entities: semantic search trên entities
    - lightrag_vdb_relationships: tìm relationships liên quan
    - lightrag_vdb_chunks: context bổ sung

    The VietMedKG graph (Neo4j) is NOT touched here — it is served by
    the Cypher path.  mode defaults to «local» for entity-aware retrieval.
    """
    from ai_engine.services import lightrag_service
    from ai_engine.utils.response_formatter import (
        format_error_response,
        format_lightrag_response,
    )

    logger.info("LightRAG path: mode=%s", mode or "default")

    result = await lightrag_service.query(
        question=question,
        mode=mode,
    )

    elapsed_ms = (time.time() - start_time) * 1000

    if not result.get("success"):
        error_msg = result.get("error", "Unknown error")
        logger.error("LightRAG query failed: %s", error_msg)

        if "not installed" in error_msg.lower():
            return format_error_response(
                error_code="MODEL_UNAVAILABLE",
                error_message=error_msg,
                user_message=MSG_MODEL_UNAVAILABLE,
                execution_time_ms=elapsed_ms,
            )
        elif "invalid query mode" in error_msg.lower():
            return format_error_response(
                error_code="INVALID_QUESTION",
                error_message=error_msg,
                user_message=MSG_INVALID_MODE,
                execution_time_ms=elapsed_ms,
            )
        else:
            return format_error_response(
                error_code="LIGHTRAG_QUERY_FAILED",
                error_message=error_msg,
                user_message=MSG_GENERATION_FAILED,
                execution_time_ms=elapsed_ms,
            )

    response = format_lightrag_response(
        raw_answer=result["answer"],
        question=question,
        query_mode=result.get("mode", mode or "hybrid"),
        execution_time_ms=elapsed_ms,
    )

    logger.info(
        "LightRAG path completed in %.0fms (type=%s, mode=%s)",
        elapsed_ms,
        response["response_type"],
        result.get("mode", "unknown"),
    )

    return response


async def _execute_lightrag_path_stream(
    question: str,
    mode: str | None,
    start_time: float,
    on_delta: Callable[[str], Awaitable[None]] | None,
) -> dict[str, Any]:
    """Execute LightRAG semantic path with native token/chunk streaming."""
    from ai_engine.services import lightrag_service
    from ai_engine.utils.response_formatter import (
        format_error_response,
        format_lightrag_response,
    )

    logger.info("LightRAG streaming path: mode=%s", mode or "default")

    try:
        effective_mode, chunks = await lightrag_service.stream_query(
            question=question,
            mode=mode,
        )
        answer_parts: list[str] = []
        async for chunk in chunks:
            text = str(chunk)
            if not text:
                continue
            answer_parts.append(text)
            if on_delta is not None:
                await on_delta(text)
    except Exception as exc:
        elapsed_ms = (time.time() - start_time) * 1000
        error_msg = str(exc)
        logger.error("LightRAG streaming query failed: %s", error_msg)
        if "not installed" in error_msg.lower():
            return format_error_response(
                error_code="MODEL_UNAVAILABLE",
                error_message=error_msg,
                user_message=MSG_MODEL_UNAVAILABLE,
                execution_time_ms=elapsed_ms,
            )
        if "invalid query mode" in error_msg.lower():
            return format_error_response(
                error_code="INVALID_QUESTION",
                error_message=error_msg,
                user_message=MSG_INVALID_MODE,
                execution_time_ms=elapsed_ms,
            )
        return format_error_response(
            error_code="LIGHTRAG_QUERY_FAILED",
            error_message=error_msg,
            user_message=MSG_GENERATION_FAILED,
            execution_time_ms=elapsed_ms,
        )

    elapsed_ms = (time.time() - start_time) * 1000
    response = format_lightrag_response(
        raw_answer="".join(answer_parts),
        question=question,
        query_mode=effective_mode,
        execution_time_ms=elapsed_ms,
    )

    logger.info(
        "LightRAG streaming path completed in %.0fms (type=%s, mode=%s)",
        elapsed_ms,
        response["response_type"],
        effective_mode,
    )
    return response
