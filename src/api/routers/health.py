"""Health check router — GET /health.

No auth required. Used by load balancers and monitoring tools.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health", summary="Health Check")
async def health(request: Request) -> dict:
    """Return overall system health.

    Checks Neo4j and LightRAG connectivity if the AppContainer is available.
    """
    result: dict = {"status": "ok", "services": {}}

    container = getattr(request.app.state, "container", None)
    if container is None:
        result["services"]["container"] = "not initialized"
        return result

    # Neo4j / Graph
    try:
        ok = await container.graph.check_connectivity()
        result["services"]["neo4j"] = "ok" if ok else "degraded"
    except Exception as exc:
        result["services"]["neo4j"] = f"error: {exc}"
        result["status"] = "degraded"

    # LightRAG / Vector
    try:
        vector_health = await container.vector.health_check()
        result["services"]["lightrag"] = vector_health.get("lightrag", "unknown")
        result["services"]["llm_server"] = vector_health.get("llm_server", "unknown")
    except Exception as exc:
        result["services"]["lightrag"] = f"error: {exc}"
        result["status"] = "degraded"

    return result


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
