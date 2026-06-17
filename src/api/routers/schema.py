"""Graph schema router — GET /api/v1/schema."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["schema"])


@router.get(
    "/schema",
    summary="Graph Schema Info",
    description=(
        "Trả về thông tin schema của Knowledge Graph trên Neo4j: "
        "node labels, counts, properties, relationships."
    ),
)
async def schema_info(request: Request) -> dict:
    """Return graph schema information from the configured graph adapter."""
    try:
        return await request.app.state.container.graph.get_schema_info()
    except Exception as exc:
        logger.error("Schema endpoint error: %s", exc)
        return {"nodes": [], "relationships": [], "error": str(exc)}
