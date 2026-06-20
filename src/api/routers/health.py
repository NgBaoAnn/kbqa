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

    Delegates dependency checks to SystemHealthUseCase.
    """
    container = getattr(request.app.state, "container", None)
    if container is None:
        services = ServiceStatus(api="running", ai_engine="not_initialized")
        services.ai_engine = "not_initialized"
        return HealthResponse(status="degraded", services=services, version=settings.pipeline_version)

    result = await container.system_health.execute()
    return HealthResponse(
        status=result.status,
        services=ServiceStatus(**result.services),
        version=result.version,
    )


@router.get("/api/v1/health/graph-schema", summary="Graph Schema")
@router.get("/health/graph-schema", summary="Graph Schema")
async def graph_schema(request: Request) -> dict:
    """Return the Neo4j knowledge graph schema."""
    container = getattr(request.app.state, "container", None)
    if container is None:
        return {"error": "container not initialized"}
    try:
        return await container.explore_knowledge.get_schema_info()
    except Exception as exc:
        logger.error("Schema fetch failed: %s", exc)
        return {"error": str(exc)}
