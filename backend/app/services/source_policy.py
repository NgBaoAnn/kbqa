"""Source metadata policy — S2-ARCH-02.

Pure functions to normalize raw pipeline metadata into ``ChatSource`` objects.

Policy:
- Every source must have ``id``, ``source_type``, ``title``, ``snippet``,
  ``rank``, and ``metadata``.
- ``metadata`` MUST NOT contain secrets, tokens, or credentials.
- If the AI engine does not provide source details, degrade gracefully with a
  single fallback source rather than returning an empty list with no context.

Supported source_type values
-----------------------------
``cypher``              Raw Cypher query used against Neo4j VietMedKG.
``neo4j``               A Neo4j node/record returned by a Cypher query.
``lightrag_entity``     An entity retrieved from LightRAG vector store.
``lightrag_relationship`` A relationship retrieved from LightRAG vector store.
``lightrag_chunk``      A text chunk retrieved from LightRAG vector store.
``document``            A generic document / text source.
``other``               Fallback when type is unknown or not mapped.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.models.contracts import ChatSource

logger = logging.getLogger(__name__)

# ── Allowed source type values ────────────────────────────────────────────
VALID_SOURCE_TYPES = frozenset(
    {
        "cypher",
        "neo4j",
        "lightrag_entity",
        "lightrag_relationship",
        "lightrag_chunk",
        "document",
        "other",
    }
)

# ── Metadata keys that must never appear in persisted source metadata ──────
_SECRET_KEYS = frozenset(
    {
        "password",
        "token",
        "secret",
        "api_key",
        "apikey",
        "access_token",
        "service_role_key",
        "supabase_key",
        "supabase_service_role",
        "authorization",
        "auth",
    }
)


def _safe_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *raw* with any secret-looking keys removed.

    Performs a case-insensitive key check against ``_SECRET_KEYS``.
    """
    cleaned = {}
    for key, value in raw.items():
        if key.lower() in _SECRET_KEYS:
            logger.warning("source_policy: stripped secret-like key '%s' from source metadata", key)
            continue
        cleaned[key] = value
    return cleaned


def _new_source_id() -> str:
    return str(uuid.uuid4())


# ── Public API ─────────────────────────────────────────────────────────────


def normalize_cypher_source(
    cypher: str,
    engine: str = "cypher_direct",
    query_mode: str = "",
    extra_metadata: dict[str, Any] | None = None,
) -> ChatSource:
    """Build a ``ChatSource`` for a Cypher query path result.

    Args:
        cypher: The Cypher query string that was executed.
        engine: Engine name tag (default ``cypher_direct``).
        query_mode: The resolved query mode string.
        extra_metadata: Optional additional metadata to include (will be sanitized).

    Returns:
        A ``ChatSource`` with ``source_type="cypher"``.
    """
    raw_meta: dict[str, Any] = {
        "engine": engine,
        "query_mode": query_mode,
    }
    if extra_metadata:
        raw_meta.update(extra_metadata)

    return ChatSource(
        id=_new_source_id(),
        source_type="cypher",
        title="Neo4j VietMedKG",
        snippet=cypher.strip()[:500] if cypher else "",
        rank=1,
        metadata=_safe_metadata(raw_meta),
    )


def normalize_lightrag_sources(
    entities: list[dict[str, Any]] | None = None,
    relationships: list[dict[str, Any]] | None = None,
    chunks: list[dict[str, Any]] | None = None,
    engine: str = "lightrag",
    query_mode: str = "",
) -> list[ChatSource]:
    """Build ``ChatSource`` objects from LightRAG retrieval context.

    Args:
        entities: List of entity dicts from LightRAG vector search.
        relationships: List of relationship dicts from LightRAG.
        chunks: List of text chunk dicts from LightRAG.
        engine: Engine name tag.
        query_mode: The LightRAG query mode used.

    Returns:
        List of ``ChatSource`` objects, one per context item, ranked by order.
    """
    sources: list[ChatSource] = []
    rank = 1

    for entity in (entities or []):
        name = entity.get("entity_name") or entity.get("name") or "Entity"
        desc = entity.get("description") or entity.get("desc") or ""
        sources.append(
            ChatSource(
                id=_new_source_id(),
                source_type="lightrag_entity",
                title=str(name),
                snippet=str(desc)[:500],
                rank=rank,
                metadata=_safe_metadata(
                    {
                        "engine": engine,
                        "query_mode": query_mode,
                        "entity_type": entity.get("type", ""),
                    }
                ),
            )
        )
        rank += 1

    for rel in (relationships or []):
        src = rel.get("src_id") or rel.get("source") or ""
        tgt = rel.get("tgt_id") or rel.get("target") or ""
        keywords = rel.get("keywords") or rel.get("relation_type") or ""
        desc = rel.get("description") or rel.get("desc") or ""
        sources.append(
            ChatSource(
                id=_new_source_id(),
                source_type="lightrag_relationship",
                title=f"{src} → {tgt}",
                snippet=f"{keywords}: {desc}"[:500] if desc else f"{src} → {tgt}",
                rank=rank,
                metadata=_safe_metadata(
                    {
                        "engine": engine,
                        "query_mode": query_mode,
                        "src": str(src),
                        "tgt": str(tgt),
                    }
                ),
            )
        )
        rank += 1

    for chunk in (chunks or []):
        content = chunk.get("content") or chunk.get("text") or ""
        chunk_id = chunk.get("id") or chunk.get("chunk_id") or ""
        sources.append(
            ChatSource(
                id=_new_source_id(),
                source_type="lightrag_chunk",
                title=f"Chunk {chunk_id}"[:80] if chunk_id else "LightRAG Chunk",
                snippet=str(content)[:500],
                rank=rank,
                metadata=_safe_metadata(
                    {
                        "engine": engine,
                        "query_mode": query_mode,
                    }
                ),
            )
        )
        rank += 1

    return sources


def build_fallback_source(
    engine: str,
    query_mode: str,
) -> ChatSource:
    """Build a single fallback ``ChatSource`` when the engine provides no detail.

    This prevents ``sources=[]`` from reaching the API consumer, instead
    providing a minimal provenance record that links the answer to its engine.

    Args:
        engine: The engine that produced the answer (e.g. ``lightrag``).
        query_mode: The query mode used.

    Returns:
        A ``ChatSource`` with ``source_type="other"``.
    """
    return ChatSource(
        id=_new_source_id(),
        source_type="other",
        title="AegisHealth Hybrid GraphRAG",
        snippet=f"Answer generated via {engine} engine (mode: {query_mode}).",
        rank=1,
        metadata=_safe_metadata({"engine": engine, "query_mode": query_mode}),
    )


def normalize_sources_from_pipeline(
    pipeline_metadata: dict[str, Any],
    pipeline_result: dict[str, Any] | None = None,
) -> list[ChatSource]:
    """Normalize ``ChatSource[]`` from raw pipeline output.

    This is the main entry point used by ``ai_service``. It inspects
    ``pipeline_metadata`` and optionally the full ``pipeline_result`` dict
    to extract provenance information.

    Degradation strategy (in order):
    1. If engine is ``cypher_direct`` and ``metadata["cypher"]`` is present
       → create a ``cypher`` source.
    2. If engine is ``lightrag`` and retrieval context exists in result
       → map entities / relationships / chunks.
    3. If no structured source data is available
       → return a single ``fallback`` source so ``sources`` is never empty.

    Args:
        pipeline_metadata: The ``metadata`` dict from the pipeline response.
        pipeline_result: The full pipeline response dict (may have extra keys).

    Returns:
        List of ``ChatSource`` (at least one element).
    """
    if not isinstance(pipeline_metadata, dict):
        logger.warning("source_policy: non-dict pipeline_metadata, using fallback")
        pipeline_metadata = {}

    engine = pipeline_metadata.get("engine", "unknown")
    query_mode = pipeline_metadata.get("query_mode", "unknown")

    try:
        # ── Cypher path ───────────────────────────────────────────────────
        if engine == "cypher_direct":
            cypher = pipeline_metadata.get("cypher") or ""
            if cypher:
                return [
                    normalize_cypher_source(
                        cypher=cypher,
                        engine=engine,
                        query_mode=query_mode,
                    )
                ]

        # ── LightRAG path ─────────────────────────────────────────────────
        if engine == "lightrag" and pipeline_result:
            entities = pipeline_result.get("entities") or []
            relationships = pipeline_result.get("relationships") or []
            chunks = pipeline_result.get("chunks") or []
            if entities or relationships or chunks:
                sources = normalize_lightrag_sources(
                    entities=entities,
                    relationships=relationships,
                    chunks=chunks,
                    engine=engine,
                    query_mode=query_mode,
                )
                if sources:
                    return sources

        # ── Fallback ──────────────────────────────────────────────────────
        logger.info(
            "source_policy: no structured sources from engine='%s', using fallback",
            engine,
        )
        return [build_fallback_source(engine=engine, query_mode=query_mode)]

    except Exception:
        logger.exception("source_policy: unexpected error normalizing sources, using fallback")
        return [build_fallback_source(engine=engine, query_mode=query_mode)]
