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
import time
from typing import Any

logger = logging.getLogger(__name__)

# Pipeline-level timeout (seconds).
# Naive Qdrant search + LLM synthesis can take up to ~90s on cold start.
PIPELINE_TIMEOUT_SECONDS = 120

# LightRAG semantic path uses mix mode (entity + relationship + raw chunks).
# mix = local (entities_vdb + Neo4j) + global (relationships_vdb + Neo4j)
#       + vector chunks (chunks_vdb) — most comprehensive context.
# The VietMedKG graph is served exclusively by the Cypher path.
_LIGHTRAG_MODE = "mix"

MSG_INVALID_QUESTION = "Vui lòng nhập câu hỏi hợp lệ."
MSG_MODEL_UNAVAILABLE = "Dịch vụ AI tạm thời không khả dụng. Vui lòng thử lại sau."
MSG_INVALID_MODE = "Chế độ truy vấn không hợp lệ."
MSG_GENERATION_FAILED = "Xin lỗi, tôi chưa hiểu câu hỏi. Bạn có thể diễn đạt lại được không?"
MSG_SYSTEM_ERROR = "Hệ thống đang gặp sự cố. Vui lòng thử lại sau."
MSG_TIMEOUT = "Xử lý mất quá lâu. Vui lòng thử câu hỏi ngắn hơn."
MSG_NO_DATA = "Không tìm thấy thông tin về chủ đề này trong cơ sở dữ liệu."


async def run_pipeline(
    question: str,
    mode: str | None = None,
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
        return await asyncio.wait_for(
            _run_pipeline_inner(question, mode, start_time),
            timeout=PIPELINE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.error("Pipeline timeout after %.0fms", elapsed_ms)
        return format_error_response(
            error_code="TIMEOUT",
            error_message=f"Pipeline exceeded {PIPELINE_TIMEOUT_SECONDS}s timeout",
            user_message=MSG_TIMEOUT,
            execution_time_ms=elapsed_ms,
        )


async def _run_pipeline_inner(
    question: str,
    mode: str | None,
    start_time: float,
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
        # ── Step 2: Force LightRAG when mode is explicitly set ────────────
        if mode:
            logger.info("Pipeline: mode='%s' explicitly set → LightRAG", mode)
            return await _execute_lightrag_path(question, _LIGHTRAG_MODE, start_time)

        # ── Step 3: LLM Intent Extraction (Accuracy First) ──────────────────
        query_type, entity = await extract_intent_with_llm(question)
        routing_method = "llm"

        # ── Step 4: Regex fallback when LLM fails or misses entity ──────────
        if entity is None and query_type != "count":
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
                return await _execute_lightrag_path(question, _LIGHTRAG_MODE, start_time)
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
            )

        # ── Step 5: Count/statistics → always CYPHER, no entity needed ────
        if query_type == "count":
            return await _execute_cypher_path(
                question=question,
                disease_name=None,
                query_type="count",
                start_time=start_time,
                exact=False,
            )

        # ── Step 6: No entity identified → LIGHTRAG ───────────────────────
        if not entity:
            logger.info("No entity extracted → LightRAG (method=%s)", routing_method)
            return await _execute_lightrag_path(question, _LIGHTRAG_MODE, start_time)

        # ── Step 7: Data-driven check — is entity in KG? ──────────────────
        canonical, variants = await _disambiguate_entity(entity)

        if not variants:
            # KG has no record for this entity → auto-fallback to semantic path
            logger.info("Entity '%s' not in KG → LightRAG auto-fallback", entity)
            return await _execute_lightrag_path(question, _LIGHTRAG_MODE, start_time)

        if canonical is None:
            # Multiple candidates, no clear winner → ask user to narrow down
            elapsed_ms = (time.time() - start_time) * 1000
            top = variants[:10]
            names_text = "\n".join(f"  {i+1}. {n}" for i, n in enumerate(top))
            more = f"\n  ... và {len(variants) - 10} bệnh khác" if len(variants) > 10 else ""
            answer = (
                f'Tìm thấy {len(variants)} bệnh liên quan đến "{entity}". '
                f"Bạn muốn hỏi về bệnh nào?\n\n{names_text}{more}"
            )
            return format_lightrag_response(
                raw_answer=answer,
                question=question,
                query_mode="cypher:disambiguation",
                execution_time_ms=elapsed_ms,
            )

        # ── Step 8: Canonical found → CYPHER with exact match ─────────────
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
) -> dict[str, Any]:
    """Execute the Cypher path — template-first, LLM Text2Cypher as fallback.

    Caller is responsible for disambiguation; disease_name (when provided) is
    already the canonical KG name. exact=True generates a direct equality match.

    Flow: Layer 1 (template) → Neo4j → Layer 3 (format)
    """
    from ai_engine.services.cypher_query_builder import build_cypher_query
    from ai_engine.services.text2cypher import generate_cypher, synthesize_answer
    from ai_engine.utils.cypher_validator import validate_cypher
    from ai_engine.utils.response_formatter import format_error_response, format_lightrag_response
    from ai_engine.utils.sanitizer import sanitize_cypher
    from app.services.graph_service import execute_cypher as _neo4j_exec

    logger.info("Cypher path: type=%s entity='%s' exact=%s", query_type, disease_name, exact)

    # ── Layer 1: Template-First ─────────────────────────────────────────────
    cypher, params = build_cypher_query(query_type, disease_name, exact=exact)
    use_template = cypher is not None

    if not use_template:
        logger.info("No template for type=%s → LLM Text2Cypher", query_type)
        try:
            cypher = await generate_cypher(question)
            params = {}
        except Exception as e:
            logger.error("LLM Cypher generation failed: %s", e)
            return await _execute_lightrag_path(question, _LIGHTRAG_MODE, start_time)

    # ── Validate + Sanitize ────────────────────────────────────────────────
    is_valid, validation_error = validate_cypher(cypher)
    if not is_valid:
        logger.warning("Cypher validation failed: %s → LightRAG fallback", validation_error)
        return await _execute_lightrag_path(question, _LIGHTRAG_MODE, start_time)

    try:
        cypher = sanitize_cypher(cypher)
    except ValueError as e:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.error("Cypher sanitization blocked: %s", e)
        return format_error_response(
            error_code="CYPHER_GENERATION_FAILED",
            error_message=str(e),
            user_message=MSG_GENERATION_FAILED,
            execution_time_ms=elapsed_ms,
        )

    # ── Execute on Neo4j ───────────────────────────────────────────────────
    try:
        records = await _neo4j_exec(cypher, params)
    except Exception as e:
        logger.error("Cypher execution failed: %s → LightRAG fallback", e)
        return await _execute_lightrag_path(question, _LIGHTRAG_MODE, start_time)

    elapsed_ms = (time.time() - start_time) * 1000

    if not records:
        logger.info("Cypher 0 records → LightRAG fallback")
        return await _execute_lightrag_path(question, _LIGHTRAG_MODE, start_time)

    # ── Layer 3: Format response (via LLM) ─────────────────────────────────
    try:
        answer_text = await synthesize_answer(question, records)
    except Exception as e:
        logger.error("Synthesize answer failed: %s", e)
        answer_text = str(records[:3])

    # (Disclaimer appending moved to format_lightrag_response)

    response = format_lightrag_response(
        raw_answer=answer_text,
        question=question,
        query_mode=f"cypher:{'template' if use_template else 'llm'}:{query_type}",
        execution_time_ms=elapsed_ms,
    )
    response["metadata"]["engine"] = "cypher_direct"
    response["metadata"]["cypher"] = cypher.strip()

    if use_template:
        structured = _extract_structured_data(query_type, records)
        if structured:
            # Always return structured data for frontend UI flexibility
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

    if query_type == "count":
        # Count results → already structured
        return [records[0]]

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
                error_code="CYPHER_GENERATION_FAILED",
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
