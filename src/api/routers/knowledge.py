"""Knowledge router — GET /api/v1/knowledge/diseases.

No auth required for read-only knowledge browsing.
"""

from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query, Request

from api.schemas.responses import DiseaseDetailResponse, DiseaseListResponse, DiseaseSummary

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


@router.get(
    "/diseases",
    response_model=DiseaseListResponse,
    summary="List / Search Diseases",
    responses={404: {"description": "No diseases found"}},
)
async def list_diseases(
    request: Request,
    q: str | None = Query(default=None, description="Optional disease name search term"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DiseaseListResponse:
    """List diseases from the Knowledge Graph, optionally filtered by name."""
    uc = request.app.state.container.explore_knowledge
    try:
        result = await uc.list_diseases(q=q, limit=limit, offset=offset)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "KNOWLEDGE_GRAPH_UNAVAILABLE",
                "message": "Knowledge graph is temporarily unavailable.",
            },
        ) from exc
    return DiseaseListResponse(**result.__dict__)


@router.get(
    "/diseases/{disease_id:path}",
    response_model=DiseaseDetailResponse,
    summary="Get Disease Detail",
    responses={404: {"description": "Disease not found"}},
)
async def get_disease(
    disease_id: str,
    request: Request,
) -> DiseaseDetailResponse:
    """Return full disease profile from the Knowledge Graph."""
    uc = request.app.state.container.explore_knowledge
    try:
        data = await uc.get_disease(disease_id=unquote(disease_id))
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "KNOWLEDGE_GRAPH_UNAVAILABLE",
                "message": "Knowledge graph is temporarily unavailable.",
            },
        ) from exc
    if data is None:
        raise HTTPException(status_code=404, detail=f"Disease '{disease_id}' not found.")

    return DiseaseDetailResponse(
        id=data.get("disease_name", disease_id),
        disease_name=data.get("disease_name", ""),
        description=data.get("description"),
        symptoms=data.get("symptoms", []),
        treatments=data.get("treatments", []),
        medicines=data.get("medicines", []),
        advice=data.get("advice", []),
        metadata=data.get("metadata", {}),
    )
