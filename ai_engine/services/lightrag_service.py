"""LightRAG Service — Semantic retrieval via Qdrant vector search (naive mode).

Architecture:
  - Câu hỏi mơ hồ → vector search trên Qdrant (chế độ «naive»)
  - KHÔNG dùng LightRAG internal graph (graph đó trống, VietMedKG graph
    được phục vụ bởi Cypher path riêng biệt)
  - Embedding: bge-m3 (Ollama) → Qdrant Cloud (lightrag_vdb_chunks)
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
    FORCE_LIGHTRAG_NAIVE_MODE,
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

# Effective query mode used by this service.
# Always «naive» unless FORCE_LIGHTRAG_NAIVE_MODE is explicitly set to false.
EFFECTIVE_QUERY_MODE = "naive" if FORCE_LIGHTRAG_NAIVE_MODE else DEFAULT_QUERY_MODE


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
        A configured LightRAG instance wired to Qdrant for vector storage.
    """
    try:
        from lightrag import LightRAG
        from lightrag.utils import EmbeddingFunc
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
    logger.info("  Query Mode (enforced): %s", EFFECTIVE_QUERY_MODE)

    # Import the LLM/embedding wrapper functions from our service
    from ai_engine.services.llm_service import embedding_func, llm_model_func

    # model_name is required by QdrantVectorDBStorage to generate the
    # correct collection name suffix (e.g. lightrag_vdb_chunks_bge_m3_1024d).
    # Without it, the suffix is missing and Qdrant may not find the collection.
    emb_func = EmbeddingFunc(
        embedding_dim=EMBEDDING_DIM,
        max_token_size=8192,
        func=embedding_func,
        # NOTE: model_name is intentionally left absent here so the Qdrant
        # collection name stays «lightrag_vdb_chunks» (no suffix) — matching
        # the collection created during ingestion with the same setup.
        # If you want suffix isolation, set model_name=EMBEDDING_MODEL here
        # AND re-run the ingestion script to rebuild the collection.
    )

    # Configure Neo4j env vars before LightRAG reads them
    if LIGHTRAG_KG_STORAGE == "Neo4JStorage":
        os.environ.setdefault("NEO4J_URI", NEO4J_URI)
        os.environ.setdefault("NEO4J_USERNAME", NEO4J_USERNAME)
        os.environ.setdefault("NEO4J_PASSWORD", NEO4J_PASSWORD)
        logger.info("  Neo4j URI: %s", NEO4J_URI)

    rag = LightRAG(
        working_dir=str(working_dir),
        llm_model_func=llm_model_func,
        embedding_func=emb_func,
        graph_storage=LIGHTRAG_KG_STORAGE,
        vector_storage=LIGHTRAG_VECTOR_STORAGE,
        kv_storage=LIGHTRAG_DOC_STORAGE,
    )

    logger.info("Initializing LightRAG storages...")
    await rag.initialize_storages()
    logger.info("LightRAG initialized successfully.")
    return rag


# ── Query Interface ──────────────────────────────────────────────────────


async def query(
    question: str,
    mode: str | None = None,
    only_need_context: bool = False,
) -> dict[str, Any]:
    """Query LightRAG with a natural language question (naive / vector-only).

    This service ALWAYS uses «naive» mode (pure Qdrant vector search) because:
      1. LightRAG's internal entity graph is empty — only VietMedKG Neo4j graph
         contains real medical data, and it is served by the Cypher path.
      2. Qdrant Cloud holds all disease chunk embeddings ingested via
         ingest_vectors_direct.py — retrieval is fast and accurate.

    Args:
        question: The user's question in natural language.
        mode: Ignored when FORCE_LIGHTRAG_NAIVE_MODE=true (default).
              Respected only when FORCE_LIGHTRAG_NAIVE_MODE=false.
        only_need_context: If True, returns only the retrieved context
                          without LLM synthesis.

    Returns:
        Dict with keys:
            - answer: The synthesized natural language answer.
            - mode: The query mode actually used.
            - success: Whether the query was successful.
            - error: Error message if unsuccessful (optional).
    """
    # Enforce naive mode — override caller's mode if flag is set
    effective_mode = EFFECTIVE_QUERY_MODE if FORCE_LIGHTRAG_NAIVE_MODE else (mode or DEFAULT_QUERY_MODE)

    if mode and mode != effective_mode:
        logger.info(
            "Query mode override: '%s' → '%s' (FORCE_LIGHTRAG_NAIVE_MODE=true). "
            "To disable, set FORCE_LIGHTRAG_NAIVE_MODE=false in .env.",
            mode,
            effective_mode,
        )

    try:
        from lightrag import QueryParam
    except ImportError:
        return {
            "answer": "",
            "mode": effective_mode,
            "success": False,
            "error": "LightRAG is not installed.",
        }

    rag = await get_lightrag_instance()

    try:
        logger.info(
            "Querying LightRAG (mode=%s): %s", effective_mode, question[:100]
        )

        param = QueryParam(mode=effective_mode, only_need_context=only_need_context)
        result = await rag.aquery(question, param=param)

        logger.info(
            "Query completed (mode=%s, answer_length=%d)",
            effective_mode,
            len(str(result)),
        )

        return {
            "answer": str(result),
            "mode": effective_mode,
            "success": True,
        }

    except Exception as e:
        logger.error("LightRAG query failed (mode=%s): %s", effective_mode, e)
        return {
            "answer": "",
            "mode": effective_mode,
            "success": False,
            "error": str(e),
        }


async def health_check() -> dict[str, Any]:
    """Check the health status of the LightRAG service.

    Returns:
        Dict with status information for LightRAG, LLM, embedding, and storage.
    """
    qdrant_url = os.environ.get("QDRANT_URL", "(not set)")
    health = {
        "lightrag": "unknown",
        "query_mode": EFFECTIVE_QUERY_MODE,
        "force_naive": FORCE_LIGHTRAG_NAIVE_MODE,
        "llm_server": "unknown",
        "embedding_server": "unknown",
        "graph_storage": LIGHTRAG_KG_STORAGE,
        "vector_storage": LIGHTRAG_VECTOR_STORAGE,
        "qdrant_url": qdrant_url[:40] + "..." if len(qdrant_url) > 40 else qdrant_url,
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
