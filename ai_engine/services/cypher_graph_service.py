"""Cypher graph service facade — symmetric counterpart to lightrag_service.

Encapsulates the full Cypher path:
  to_cypher → validate → sanitize → execute → synthesize_answer

Returns a plain dict so callers (pipeline) need no knowledge of internal steps.
execute_fn is injected by the caller so this module stays independent of the
backend Neo4j driver (ai_engine must not import from backend/app).
"""

import logging
from collections.abc import Callable

from ai_engine.services.cypher_answer_synthesizer import synthesize_answer
from ai_engine.services.cypher_query_builder import to_cypher
from ai_engine.utils.cypher_validator import validate_cypher
from ai_engine.utils.sanitizer import sanitize_cypher

logger = logging.getLogger(__name__)


async def query(
    question: str,
    query_type: str | None,
    entity: str | None,
    exact: bool = False,
    *,
    execute_fn: Callable,
) -> dict:
    """Run the full Cypher path and return a structured result dict.

    Return shapes:
    - Success:
        {"success": True, "answer": str, "records": list[dict],
         "cypher": str, "used_template": bool}
    - LightRAG fallback warranted (caller should try LightRAG):
        {"success": False, "fallback": True, "reason": str}
    - Hard error (caller should surface an error response):
        {"success": False, "fallback": False, "error_code": "CYPHER_GENERATION_FAILED",
         "error_message": str}
    """
    # ── Step 1: Generate Cypher ────────────────────────────────────────────
    try:
        cypher, params, used_template = await to_cypher(query_type, entity, exact, question)
    except Exception as e:
        logger.error("Cypher generation failed: %s", e)
        return {"success": False, "fallback": True, "reason": f"generation_failed: {e}"}

    # ── Step 2: Validate ───────────────────────────────────────────────────
    is_valid, validation_error = validate_cypher(cypher)
    if not is_valid:
        logger.warning("Cypher validation failed: %s → fallback", validation_error)
        return {"success": False, "fallback": True, "reason": f"validation_failed: {validation_error}"}

    # ── Step 3: Sanitize ───────────────────────────────────────────────────
    try:
        cypher = sanitize_cypher(cypher)
    except ValueError as e:
        logger.error("Cypher sanitization blocked: %s", e)
        return {
            "success": False,
            "fallback": False,
            "error_code": "CYPHER_GENERATION_FAILED",
            "error_message": str(e),
        }

    # ── Step 4: Execute on Neo4j ───────────────────────────────────────────
    try:
        records = await execute_fn(cypher, params)
    except Exception as e:
        logger.error("Neo4j execution failed: %s → fallback", e)
        return {"success": False, "fallback": True, "reason": f"execution_failed: {e}"}

    if not records:
        logger.info("Cypher returned 0 records → fallback")
        return {"success": False, "fallback": True, "reason": "no_records"}

    # ── Step 5: Synthesize answer ──────────────────────────────────────────
    answer = await synthesize_answer(question, records)

    return {
        "success": True,
        "answer": answer,
        "records": records,
        "cypher": cypher,
        "used_template": used_template,
    }
