"""GET /api/v1/health — Health check endpoint."""

import logging

from fastapi import APIRouter

from app.config import API_VERSION
from app.models.response import HealthResponse, ServiceStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Kiểm tra trạng thái các dịch vụ: database, LLM, embedding, LightRAG.",
)
async def health_check() -> dict:
    """Check the health of all backend services.

    Returns:
        HealthResponse with status of each service component.
    """
    from ai_engine.services.lightrag_service import health_check as rag_health

    try:
        health = await rag_health()
    except Exception as e:
        logger.error("Health check failed: %s", e)
        health = {
            "llm_server": "unavailable",
            "embedding_server": "unavailable",
            "lightrag": f"error: {e}",
        }

    # Check Neo4j separately
    db_status = "unknown"
    try:
        from app.services.graph_service import check_connectivity

        db_status = "connected" if await check_connectivity() else "disconnected"
    except Exception:
        db_status = "disconnected"

    overall = "healthy"
    if health.get("llm_server") != "available":
        overall = "degraded"
    if db_status != "connected":
        overall = "degraded"
    if health.get("lightrag", "").startswith("error"):
        overall = "unhealthy"

    return {
        "status": overall,
        "services": {
            "database": db_status,
            "llm_server": health.get("llm_server", "unknown"),
            "embedding_server": health.get("embedding_server", "unknown"),
            "lightrag": health.get("lightrag", "unknown"),
            "api": "running",
        },
        "version": API_VERSION,
    }
