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
    from use_cases.explore_knowledge import ExploreKnowledgeUseCase

    uc = ExploreKnowledgeUseCase(graph=request.app.state.container.graph)
    result = await uc.list_diseases(search=q, limit=limit, offset=offset)
    return result


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
    from use_cases.explore_knowledge import ExploreKnowledgeUseCase

    uc = ExploreKnowledgeUseCase(graph=request.app.state.container.graph)
    data = await uc.get_disease(disease_id=unquote(disease_id))
    if data is None:
        raise HTTPException(status_code=404, detail=f"Disease '{disease_id}' not found.")

    return DiseaseDetailResponse(
        id=data.get("disease_name", disease_id),
        disease_name=data.get("disease_name", ""),
        description=data.get("disease_description"),
        symptoms=[s["symptom_name"] for s in data.get("symptoms", []) if s.get("symptom_name")],
        treatments=[t["treatment_name"] for t in data.get("treatments", []) if t.get("treatment_name")],
        medicines=[m["medicine_name"] for m in data.get("medicines", []) if m.get("medicine_name")],
        advice=[a["advice_content"] for a in data.get("advice", []) if a.get("advice_content")],
        metadata={"source": "Neo4j VietMedKG", "category": data.get("disease_category")},
    )
