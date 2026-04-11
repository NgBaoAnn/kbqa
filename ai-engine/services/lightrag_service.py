"""LightRAG Service — Core integration with the LightRAG framework.

Provides initialization and querying capabilities using LightRAG's
graph-enhanced retrieval with Neo4j as the knowledge graph backend.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from ai_engine.config import (
    DEFAULT_QUERY_MODE,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    LIGHTRAG_DOC_STORAGE,
    LIGHTRAG_KG_STORAGE,
    LIGHTRAG_VECTOR_STORAGE,
    LIGHTRAG_WORKING_DIR,
    LLM_MODEL_NAME,
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USERNAME,
)

logger = logging.getLogger(__name__)

# ── Singleton instance ────────────────────────────────────────────────────
_lightrag_instance = None
_init_lock = asyncio.Lock()


async def get_lightrag_instance():
    """Get or create the LightRAG singleton instance.

    Uses double-checked locking to ensure thread-safe initialization.

    Returns:
        An initialized LightRAG instance.
    """
    global _lightrag_instance

    if _lightrag_instance is not None:
        return _lightrag_instance

    async with _init_lock:
        # Double-check after acquiring lock
        if _lightrag_instance is not None:
            return _lightrag_instance

        _lightrag_instance = await _create_lightrag_instance()
        return _lightrag_instance


async def _create_lightrag_instance():
    """Create and configure a new LightRAG instance.

    Returns:
        A configured LightRAG instance with Neo4j graph storage.
    """
    try:
        from lightrag import LightRAG, QueryParam
        from lightrag.llm.ollama import ollama_embed, ollama_model_complete
        from lightrag.kg.neo4j_impl import Neo4JStorage
    except ImportError as e:
        logger.error(
            "LightRAG is not installed. Run: pip install 'lightrag-hku[api]'\n"
            "Error: %s",
            e,
        )
        raise

    # Ensure working directory exists
    working_dir = Path(LIGHTRAG_WORKING_DIR)
    working_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Initializing LightRAG...")
    logger.info("  Working directory: %s", working_dir)
    logger.info("  KG Storage: %s", LIGHTRAG_KG_STORAGE)
    logger.info("  Vector Storage: %s", LIGHTRAG_VECTOR_STORAGE)
    logger.info("  LLM Model: %s", LLM_MODEL_NAME)
    logger.info("  Embedding Model: %s", EMBEDDING_MODEL)

    # Import the LLM/embedding wrapper functions from our service
    from ai_engine.services.llm_service import embedding_func, llm_model_func

    rag = LightRAG(
        working_dir=str(working_dir),
        llm_model_func=llm_model_func,
        embedding_func=EmbeddingFunc(
            embedding_dim=EMBEDDING_DIM,
            max_token_size=8192,
            func=embedding_func,
        ),
        graph_storage=LIGHTRAG_KG_STORAGE,
        vector_storage=LIGHTRAG_VECTOR_STORAGE,
        doc_storage=LIGHTRAG_DOC_STORAGE,
    )

    # Configure Neo4j connection if using Neo4J storage
    if LIGHTRAG_KG_STORAGE == "Neo4JStorage":
        os.environ.setdefault("NEO4J_URI", NEO4J_URI)
        os.environ.setdefault("NEO4J_USERNAME", NEO4J_USERNAME)
        os.environ.setdefault("NEO4J_PASSWORD", NEO4J_PASSWORD)
        logger.info("  Neo4j URI: %s", NEO4J_URI)

    logger.info("LightRAG initialized successfully.")
    return rag


# ── Import EmbeddingFunc helper ───────────────────────────────────────────
try:
    from lightrag import EmbeddingFunc
except ImportError:
    # Fallback: define a simple dataclass if LightRAG is not installed yet
    from dataclasses import dataclass
    from typing import Callable

    @dataclass
    class EmbeddingFunc:
        embedding_dim: int
        max_token_size: int
        func: Callable


# ── Query Interface ──────────────────────────────────────────────────────


async def query(
    question: str,
    mode: str | None = None,
    only_need_context: bool = False,
) -> dict[str, Any]:
    """Query LightRAG with a natural language question.

    Args:
        question: The user's question in natural language.
        mode: Query mode — one of: naive, local, global, hybrid, mix.
              Defaults to DEFAULT_QUERY_MODE from config.
        only_need_context: If True, returns only the retrieved context
                          without LLM synthesis.

    Returns:
        Dict with keys:
            - answer: The synthesized natural language answer.
            - mode: The query mode used.
            - success: Whether the query was successful.
            - error: Error message if unsuccessful (optional).
    """
    mode = mode or DEFAULT_QUERY_MODE

    # Validate mode
    valid_modes = {"naive", "local", "global", "hybrid", "mix"}
    if mode not in valid_modes:
        return {
            "answer": "",
            "mode": mode,
            "success": False,
            "error": f"Invalid query mode: '{mode}'. Must be one of: {valid_modes}",
        }

    try:
        from lightrag import QueryParam
    except ImportError:
        return {
            "answer": "",
            "mode": mode,
            "success": False,
            "error": "LightRAG is not installed.",
        }

    rag = await get_lightrag_instance()

    try:
        logger.info("Querying LightRAG (mode=%s): %s", mode, question[:100])

        param = QueryParam(mode=mode, only_need_context=only_need_context)
        result = await rag.aquery(question, param=param)

        logger.info("Query completed (mode=%s, answer_length=%d)", mode, len(str(result)))

        return {
            "answer": str(result),
            "mode": mode,
            "success": True,
        }

    except Exception as e:
        logger.error("LightRAG query failed (mode=%s): %s", mode, e)
        return {
            "answer": "",
            "mode": mode,
            "success": False,
            "error": str(e),
        }


async def health_check() -> dict[str, Any]:
    """Check the health status of the LightRAG service.

    Returns:
        Dict with status information for LightRAG, LLM, and storage.
    """
    health = {
        "lightrag": "unknown",
        "llm_server": "unknown",
        "embedding_server": "unknown",
        "graph_storage": LIGHTRAG_KG_STORAGE,
        "vector_storage": LIGHTRAG_VECTOR_STORAGE,
    }

    # Check LLM
    from ai_engine.services.llm_service import (
        check_embedding_availability,
        check_llm_availability,
    )

    try:
        llm_ok = await check_llm_availability()
        health["llm_server"] = "available" if llm_ok else "unavailable"
    except Exception:
        health["llm_server"] = "unavailable"

    # Check embedding
    try:
        emb_ok = await check_embedding_availability()
        health["embedding_server"] = "available" if emb_ok else "unavailable"
    except Exception:
        health["embedding_server"] = "unavailable"

    # Check LightRAG instance
    try:
        rag = await get_lightrag_instance()
        health["lightrag"] = "initialized" if rag else "not_initialized"
    except Exception as e:
        health["lightrag"] = f"error: {e}"

    return health
