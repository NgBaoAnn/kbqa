"""QA Domain — Source Policy.

Pure functions to normalize raw pipeline metadata into SourceRecord
value objects.  No infrastructure dependencies (no Pydantic API models).

Policy:
- Every answer must have ≥1 source for provenance tracking.
- Metadata MUST NOT contain secrets/credentials.
- If engine provides no detail, degrade to a fallback source.
"""

from __future__ import annotations

import uuid
from typing import Any

from domain.qa.value_objects import SourceRecord

# ── Secret key stripping ──────────────────────────────────────────────────

_SECRET_KEYS = frozenset({
    "password", "token", "secret", "api_key", "apikey",
    "access_token", "service_role_key", "supabase_key",
    "supabase_service_role", "authorization", "auth",
})


def _safe_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of raw with any secret-looking keys removed."""
    return {k: v for k, v in raw.items() if k.lower() not in _SECRET_KEYS}


def _new_id() -> str:
    return str(uuid.uuid4())


# ── Source builders ───────────────────────────────────────────────────────

def build_cypher_source(
    cypher: str,
    engine: str = "cypher_direct",
    query_mode: str = "",
    extra: dict[str, Any] | None = None,
) -> SourceRecord:
    """Build a SourceRecord for a Cypher query result."""
    meta = {"engine": engine, "query_mode": query_mode}
    if extra:
        meta.update(extra)
    return SourceRecord(
        id=_new_id(),
        source_type="cypher",
        title="Neo4j VietMedKG",
        snippet=cypher.strip()[:500] if cypher else "",
        rank=1,
        metadata=_safe_metadata(meta),
    )


def build_lightrag_sources(
    entities: list[dict[str, Any]] | None = None,
    relationships: list[dict[str, Any]] | None = None,
    chunks: list[dict[str, Any]] | None = None,
    engine: str = "lightrag",
    query_mode: str = "",
) -> list[SourceRecord]:
    """Build SourceRecords from LightRAG retrieval context."""
    sources: list[SourceRecord] = []
    rank = 1

    for entity in (entities or []):
        name = entity.get("entity_name") or entity.get("name") or "Entity"
        desc = entity.get("description") or entity.get("desc") or ""
        sources.append(SourceRecord(
            id=_new_id(),
            source_type="lightrag_entity",
            title=str(name),
            snippet=str(desc)[:500],
            rank=rank,
            metadata=_safe_metadata({
                "engine": engine,
                "query_mode": query_mode,
                "entity_type": entity.get("type", ""),
            }),
        ))
        rank += 1

    for rel in (relationships or []):
        src = rel.get("src_id") or rel.get("source") or ""
        tgt = rel.get("tgt_id") or rel.get("target") or ""
        keywords = rel.get("keywords") or rel.get("relation_type") or ""
        desc = rel.get("description") or rel.get("desc") or ""
        sources.append(SourceRecord(
            id=_new_id(),
            source_type="lightrag_relationship",
            title=f"{src} → {tgt}",
            snippet=f"{keywords}: {desc}"[:500] if desc else f"{src} → {tgt}",
            rank=rank,
            metadata=_safe_metadata({
                "engine": engine,
                "query_mode": query_mode,
                "src": str(src),
                "tgt": str(tgt),
            }),
        ))
        rank += 1

    for chunk in (chunks or []):
        content = chunk.get("content") or chunk.get("text") or ""
        chunk_id = chunk.get("id") or chunk.get("chunk_id") or ""
        sources.append(SourceRecord(
            id=_new_id(),
            source_type="lightrag_chunk",
            title=f"Chunk {chunk_id}"[:80] if chunk_id else "LightRAG Chunk",
            snippet=str(content)[:500],
            rank=rank,
            metadata=_safe_metadata({
                "engine": engine,
                "query_mode": query_mode,
            }),
        ))
        rank += 1

    return sources


def build_fallback_source(engine: str, query_mode: str) -> SourceRecord:
    """Build a single fallback source when engine provides no detail."""
    return SourceRecord(
        id=_new_id(),
        source_type="other",
        title="AegisHealth Hybrid GraphRAG",
        snippet=f"Answer generated via {engine} engine (mode: {query_mode}).",
        rank=1,
        metadata=_safe_metadata({"engine": engine, "query_mode": query_mode}),
    )


def normalize_sources_from_pipeline(
    pipeline_metadata: dict[str, Any],
    pipeline_result: dict[str, Any] | None = None,
) -> list[SourceRecord]:
    """Normalize sources from raw pipeline output.

    Degradation strategy:
    1. Cypher path with cypher query → cypher source
    2. LightRAG path with entities/rels/chunks → lightrag sources
    3. Fallback → single generic source

    Returns:
        List of SourceRecord (at least one element).
    """
    if not isinstance(pipeline_metadata, dict):
        pipeline_metadata = {}

    engine = pipeline_metadata.get("engine", "unknown")
    query_mode = pipeline_metadata.get("query_mode", "unknown")

    try:
        # Cypher path
        if engine == "cypher_direct":
            cypher = pipeline_metadata.get("cypher") or ""
            if cypher:
                return [build_cypher_source(
                    cypher=cypher, engine=engine, query_mode=query_mode,
                )]

        # LightRAG path
        if engine == "lightrag" and pipeline_result:
            entities = pipeline_result.get("entities") or []
            relationships = pipeline_result.get("relationships") or []
            chunks = pipeline_result.get("chunks") or []
            if entities or relationships or chunks:
                sources = build_lightrag_sources(
                    entities=entities, relationships=relationships,
                    chunks=chunks, engine=engine, query_mode=query_mode,
                )
                if sources:
                    return sources

        # Fallback
        return [build_fallback_source(engine=engine, query_mode=query_mode)]

    except Exception:
        return [build_fallback_source(engine=engine, query_mode=query_mode)]
