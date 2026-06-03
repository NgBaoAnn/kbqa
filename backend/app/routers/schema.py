"""GET /api/v1/schema — Graph schema info endpoint."""

import logging

from fastapi import APIRouter

from app.services.graph_service import get_schema_info

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["schema"])


@router.get(
    "/schema",
    summary="Graph Schema Info",
    description="Trả về thông tin schema của Knowledge Graph trên Neo4j: node labels, counts, properties, relationships.",
)
async def schema_info() -> dict:
    """Return graph schema information from Neo4j.

    Returns:
        Dict with nodes (label, count, properties) and relationships (type, count).
    """
    try:
        info = await get_schema_info()
        return info
    except Exception as e:
        logger.error("Schema endpoint error: %s", e)
        return {"nodes": [], "relationships": [], "error": str(e)}
