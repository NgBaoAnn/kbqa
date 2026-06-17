"""Health check router — GET /health.

No auth required. Used by load balancers and monitoring tools.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from api.config import settings
from api.schemas.responses import HealthResponse, ServiceStatus

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/api/v1/health", response_model=HealthResponse, summary="Health Check")
@router.get("/health", response_model=HealthResponse, summary="Health Check")
async def health(request: Request) -> HealthResponse:
    """Return overall system health.

    Checks Neo4j and LightRAG connectivity if the AppContainer is available.
    """
    services = ServiceStatus(api="running", ai_engine="ready")
    overall = "healthy"

    container = getattr(request.app.state, "container", None)
    if container is None:
        services.ai_engine = "not_initialized"
        return HealthResponse(status="degraded", services=services, version=settings.pipeline_version)

    # Neo4j / Graph
    try:
        ok = await container.graph.check_connectivity()
        services.neo4j = "connected" if ok else "unavailable"
        if not ok:
            overall = "degraded"
    except Exception as exc:
        logger.warning("Neo4j health check failed: %s", exc)
        services.neo4j = "unavailable"
        overall = "degraded"

    # Supabase/Postgres
    try:
        container.db.fetch_one("select 1 as ok")
        services.supabase_postgres = "connected"
    except Exception as exc:
        logger.warning("Postgres health check failed: %s", exc)
        services.supabase_postgres = "unavailable"
        overall = "degraded"

    # LightRAG / Vector
    try:
        vector_health = await container.vector.health_check()
        services.lightrag = vector_health.get("lightrag", "unknown")
        services.llm_server = vector_health.get("llm_server", "unknown")
        services.embedding_server = vector_health.get("embedding_server", "unknown")
        if services.lightrag in {"error", "unavailable"}:
            overall = "degraded"
    except Exception as exc:
        logger.warning("LightRAG health check failed: %s", exc)
        services.lightrag = "unavailable"
        services.llm_server = "unknown"
        services.embedding_server = "unknown"
        overall = "degraded"

    version_meta = getattr(container, "version_metadata", {}) or {}
    return HealthResponse(
        status=overall,
        services=services,
        version=version_meta.get("pipeline_version") or settings.pipeline_version,
    )


@router.get("/api/v1/health/graph-schema", summary="Graph Schema")
@router.get("/health/graph-schema", summary="Graph Schema")
async def graph_schema(request: Request) -> dict:
    """Return the Neo4j knowledge graph schema."""
    container = getattr(request.app.state, "container", None)
    if container is None:
        return {"error": "container not initialized"}
    try:
        return await container.graph.get_schema_info()
    except Exception as exc:
        logger.error("Schema fetch failed: %s", exc)
        return {"error": str(exc)}
