"""Query Pipeline Orchestrator — Phương án C: Hybrid Architecture.

Dual-path pipeline:
    ┌─────────────────┐
    │   Câu hỏi NL    │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │  Query Router    │ — Phân tích câu hỏi
    └───┬─────────┬───┘
        │         │
   ┌────▼───┐ ┌──▼──────────┐
   │ CYPHER │ │  LIGHTRAG    │
   │ Path   │ │  Path        │
   │        │ │              │
   │ Build  │ │ Dual-level   │
   │ Cypher │ │ Retrieval    │
   │   ↓    │ │     ↓        │
   │ Neo4j  │ │ LLM Synth    │
   │   ↓    │ │     ↓        │
   │ Format │ │ Format       │
   └───┬────┘ └──┬──────────┘
       │         │
    ┌──▼─────────▼──┐
    │  API Response   │
    └────────────────┘
"""

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


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
    from ai_engine.services.query_router import QueryPath, route_query
    from ai_engine.utils.response_formatter import (
        format_error_response,
        format_lightrag_response,
    )

    start_time = time.time()

    # ── Step 1: Validate input ────────────────────────────────────────────
    if not question or not question.strip():
        elapsed_ms = (time.time() - start_time) * 1000
        return format_error_response(
            error_code="INVALID_QUESTION",
            error_message="Question is empty or whitespace-only.",
            user_message="Vui lòng nhập câu hỏi hợp lệ.",
            execution_time_ms=elapsed_ms,
        )

    # ── Step 2: Route the query ───────────────────────────────────────────
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

    # ── Step 3: Execute the chosen path ───────────────────────────────────
    try:
        if route["path"] == QueryPath.CYPHER:
            return await _execute_cypher_path(
                question=question,
                disease_name=route["disease_name"],
                query_type=route["query_type"],
                start_time=start_time,
            )
        else:
            return await _execute_lightrag_path(
                question=question,
                mode=mode,
                start_time=start_time,
            )

    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.exception("Pipeline: unexpected error: %s", e)

        return format_error_response(
            error_code="DATABASE_ERROR",
            error_message=str(e),
            user_message="Hệ thống đang gặp sự cố. Vui lòng thử lại sau.",
            execution_time_ms=elapsed_ms,
        )


# ── Cypher Path (Direct Neo4j VietMedKG) ─────────────────────────────────


async def _execute_cypher_path(
    question: str,
    disease_name: str | None,
    query_type: str,
    start_time: float,
) -> dict[str, Any]:
    """Execute the Cypher path — direct structured query on VietMedKG.

    Advantages: Deterministic, fast, precise for known entity lookups.
    """
    from ai_engine.services.cypher_query_builder import (
        build_cypher_query,
        format_cypher_result_as_text,
    )
    from ai_engine.utils.response_formatter import (
        format_error_response,
        format_lightrag_response,
    )

    logger.info(
        "Cypher path: type=%s, disease='%s'",
        query_type,
        disease_name,
    )

    # Build and execute Cypher query
    cypher, params = build_cypher_query(query_type, disease_name)

    try:
        from app.services.graph_service import execute_cypher

        records = await execute_cypher(cypher, params)
    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        logger.error("Cypher execution failed: %s", e)

        # Fallback to LightRAG if Cypher fails
        logger.info("Falling back to LightRAG...")
        return await _execute_lightrag_path(
            question=question,
            mode=None,
            start_time=start_time,
        )

    elapsed_ms = (time.time() - start_time) * 1000

    # No results → fallback to LightRAG for a semantic answer
    if not records:
        logger.info(
            "Cypher returned 0 records for '%s'. Falling back to LightRAG.",
            disease_name,
        )
        return await _execute_lightrag_path(
            question=question,
            mode=None,
            start_time=start_time,
        )

    # Format the Cypher results as text
    answer_text = format_cypher_result_as_text(query_type, disease_name, records)

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
    mode: str | None,
    start_time: float,
) -> dict[str, Any]:
    """Execute the LightRAG path — graph-enhanced semantic retrieval.

    Advantages: Handles vague queries, multi-hop reasoning, thematic questions.
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
                user_message="Dịch vụ AI tạm thời không khả dụng. Vui lòng thử lại sau.",
                execution_time_ms=elapsed_ms,
            )
        elif "invalid query mode" in error_msg.lower():
            return format_error_response(
                error_code="INVALID_QUESTION",
                error_message=error_msg,
                user_message="Chế độ truy vấn không hợp lệ.",
                execution_time_ms=elapsed_ms,
            )
        else:
            return format_error_response(
                error_code="CYPHER_GENERATION_FAILED",
                error_message=error_msg,
                user_message=(
                    "Xin lỗi, tôi chưa hiểu câu hỏi. "
                    "Bạn có thể diễn đạt lại được không?"
                ),
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
