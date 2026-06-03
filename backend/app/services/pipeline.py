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

# LightRAG semantic path uses local mode (entity + relationship vector search).
# Requires lightrag_vdb_entities + lightrag_vdb_relationships to be populated in Qdrant.
# The VietMedKG graph is served exclusively by the Cypher path.
_LIGHTRAG_MODE = "local"

# User-facing messages per language
_USER_MESSAGES = {
    "vi": {
        "invalid_question": "Vui lòng nhập câu hỏi hợp lệ.",
        "model_unavailable": "Dịch vụ AI tạm thời không khả dụng. Vui lòng thử lại sau.",
        "invalid_mode": "Chế độ truy vấn không hợp lệ.",
        "generation_failed": "Xin lỗi, tôi chưa hiểu câu hỏi. Bạn có thể diễn đạt lại được không?",
        "system_error": "Hệ thống đang gặp sự cố. Vui lòng thử lại sau.",
        "timeout": "Xử lý mất quá lâu. Vui lòng thử câu hỏi ngắn hơn.",
        "no_data": "Không tìm thấy thông tin về chủ đề này trong cơ sở dữ liệu.",
    },
    "en": {
        "invalid_question": "Please enter a valid question.",
        "model_unavailable": "AI service is temporarily unavailable. Please try again later.",
        "invalid_mode": "Invalid query mode.",
        "generation_failed": "Sorry, I didn't understand the question. Could you rephrase it?",
        "system_error": "System is experiencing issues. Please try again later.",
        "timeout": "Processing took too long. Please try a shorter question.",
        "no_data": "No information found on this topic in the database.",
    },
}


def _msg(language: str, key: str) -> str:
    """Get user-facing message by language and key."""
    lang = language if language in _USER_MESSAGES else "vi"
    return _USER_MESSAGES[lang][key]


async def run_pipeline(
    question: str,
    language: str = "vi",
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
        language: Desired response language ('vi' or 'en').
        mode: LightRAG query mode override. If set, forces LightRAG path.

    Returns:
        Dict conforming to the QueryResponse schema.
    """
    from ai_engine.utils.response_formatter import format_error_response

    start_time = time.time()

    # ── Step 0: Wrap in timeout ────────────────────────────────────────────
    try:
        return await asyncio.wait_for(
            _run_pipeline_inner(question, language, mode, start_time),
            timeout=PIPELINE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.error("Pipeline timeout after %.0fms", elapsed_ms)
        return format_error_response(
            error_code="TIMEOUT",
            error_message=f"Pipeline exceeded {PIPELINE_TIMEOUT_SECONDS}s timeout",
            user_message=_msg(language, "timeout"),
            execution_time_ms=elapsed_ms,
        )


async def _run_pipeline_inner(
    question: str,
    language: str,
    mode: str | None,
    start_time: float,
) -> dict[str, Any]:
    """Inner pipeline logic (wrapped by timeout in run_pipeline)."""
    from ai_engine.services.query_router import QueryPath, route_query
    from ai_engine.utils.response_formatter import format_error_response

    # ── Step 1: Validate input ────────────────────────────────────────────
    if not question or not question.strip():
        elapsed_ms = (time.time() - start_time) * 1000
        return format_error_response(
            error_code="INVALID_QUESTION",
            error_message="Question is empty or whitespace-only.",
            user_message=_msg(language, "invalid_question"),
            execution_time_ms=elapsed_ms,
        )

    # ── Step 2: Route and execute ─────────────────────────────────────────
    try:
        # If mode is explicitly set → force LightRAG path
        if mode:
            route = {
                "path": QueryPath.LIGHTRAG,
                "disease_name": None,
                "query_type": None,
                "reason": f"Mode '{mode}' explicitly set → LightRAG",
            }
        else:
            route = route_query(question)

        logger.info(
            "Pipeline: route=%s (reason: %s)",
            route["path"],
            route["reason"],
        )

        # ── Step 3: Execute the chosen path ───────────────────────────────
        if route["path"] == QueryPath.CYPHER:
            return await _execute_cypher_path(
                question=question,
                disease_name=route["disease_name"],
                query_type=route["query_type"],
                language=language,
                start_time=start_time,
            )
        else:
            # Semantic path — always naive (Qdrant vector search)
            return await _execute_lightrag_path(
                question=question,
                language=language,
                mode=_LIGHTRAG_MODE,
                start_time=start_time,
            )

    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.exception("Pipeline: unexpected error: %s", e)

        return format_error_response(
            error_code="DATABASE_ERROR",
            error_message=str(e),
            user_message=_msg(language, "system_error"),
            execution_time_ms=elapsed_ms,
        )


# ── Cypher Path (Direct Neo4j VietMedKG) ─────────────────────────────────


async def _execute_cypher_path(
    question: str,
    disease_name: str | None,
    query_type: str | None,
    language: str,
    start_time: float,
) -> dict[str, Any]:
    """Execute the Cypher path — direct structured query on VietMedKG via LLM Text2Cypher.

    Advantages: Flexible for complex queries, uses LLM to understand context.
    """
    from ai_engine.services.text2cypher import generate_cypher, synthesize_answer
    from ai_engine.utils.cypher_validator import validate_cypher
    from ai_engine.utils.response_formatter import (
        format_error_response,
        format_lightrag_response,
    )
    from ai_engine.utils.sanitizer import sanitize_cypher

    logger.info("Cypher path via Text2Cypher for question: '%s'", question[:50])

    # Build Cypher query via LLM
    try:
        cypher = await generate_cypher(question)
    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.error("LLM failed to generate Cypher: %s", e)
        logger.info("Falling back to LightRAG (naive mode)...")
        return await _execute_lightrag_path(
            question=question,
            language=language,
            mode=_LIGHTRAG_MODE,
            start_time=start_time,
        )

    # Validate Cypher (defense-in-depth)
    is_valid, validation_error = validate_cypher(cypher)
    if not is_valid:
        logger.warning("Cypher validation failed: %s", validation_error)
        logger.info("Falling back to LightRAG (naive mode)...")
        return await _execute_lightrag_path(
            question=question,
            language=language,
            mode=_LIGHTRAG_MODE,
            start_time=start_time,
        )

    # Sanitize Cypher (block destructive commands)
    try:
        cypher = sanitize_cypher(cypher)
    except ValueError as e:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.error("Cypher sanitization blocked: %s", e)
        return format_error_response(
            error_code="CYPHER_GENERATION_FAILED",
            error_message=str(e),
            user_message=_msg(language, "generation_failed"),
            execution_time_ms=elapsed_ms,
        )

    # Execute on Neo4j
    try:
        from app.services.graph_service import execute_cypher

        records = await execute_cypher(cypher, {})
    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.error("Cypher execution failed: %s", e)

        # Fallback to LightRAG (naive mode) if Cypher fails
        logger.info("Falling back to LightRAG (naive mode)...")
        return await _execute_lightrag_path(
            question=question,
            language=language,
            mode=_LIGHTRAG_MODE,
            start_time=start_time,
        )

    elapsed_ms = (time.time() - start_time) * 1000

    # No results → fallback to LightRAG (naive mode) for a semantic answer
    if not records:
        logger.info(
            "Cypher returned 0 records for '%s'. Falling back to LightRAG (naive mode).",
            question[:50],
        )
        return await _execute_lightrag_path(
            question=question,
            language=language,
            mode=_LIGHTRAG_MODE,
            start_time=start_time,
        )

    # Synthesize the final answer using LLM
    try:
        answer_text = await synthesize_answer(question, records, language)
    except Exception as e:
        answer_text = str(records)

    # Use the regular formatter for consistency (response_type classification, disclaimer)
    response = format_lightrag_response(
        raw_answer=answer_text,
        question=question,
        query_mode=f"cypher:{query_type}",
        execution_time_ms=elapsed_ms,
    )

    # Override metadata to show this was the Cypher path
    response["metadata"]["engine"] = "cypher_direct"
    response["metadata"]["cypher"] = cypher.strip()

    # For table-type queries, extract structured data from records
    if query_type in ("symptoms", "medicine", "treatment", "count"):
        structured_data = _extract_structured_data(query_type, records)
        if structured_data and len(structured_data) >= 2:
            response["response_type"] = "table"
            response["data"] = structured_data
            response["metadata"]["source_count"] = len(structured_data)

    logger.info(
        "Cypher path completed in %.0fms (type=%s, records=%d)",
        elapsed_ms,
        query_type,
        len(records),
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
    language: str,
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

    logger.info("LightRAG path: mode=%s, lang=%s", mode or "default", language)

    # Prepend language instruction for English queries
    effective_question = question
    if language == "en":
        effective_question = f"Please answer in English: {question}"

    result = await lightrag_service.query(
        question=effective_question,
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
                user_message=_msg(language, "model_unavailable"),
                execution_time_ms=elapsed_ms,
            )
        elif "invalid query mode" in error_msg.lower():
            return format_error_response(
                error_code="INVALID_QUESTION",
                error_message=error_msg,
                user_message=_msg(language, "invalid_mode"),
                execution_time_ms=elapsed_ms,
            )
        else:
            return format_error_response(
                error_code="CYPHER_GENERATION_FAILED",
                error_message=error_msg,
                user_message=_msg(language, "generation_failed"),
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
