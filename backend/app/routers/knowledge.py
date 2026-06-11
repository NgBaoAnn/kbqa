"""Knowledge explorer API contract stubs."""

from fastapi import APIRouter, Query

from app.models.contracts import DiseaseDetailResponse, DiseaseListResponse
from app.services import knowledge_service

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


@router.get(
    "/diseases",
    response_model=DiseaseListResponse,
    summary="List/Search Diseases",
    responses={501: {"description": "Contract stub, not implemented yet"}},
)
async def list_diseases(
    q: str | None = Query(default=None, description="Optional disease name search term"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await knowledge_service.list_diseases(q=q, limit=limit, offset=offset)


@router.get(
    "/diseases/{disease_id}",
    response_model=DiseaseDetailResponse,
    summary="Get Disease Detail",
    responses={501: {"description": "Contract stub, not implemented yet"}},
)
async def get_disease(disease_id: str):
    return await knowledge_service.get_disease(disease_id=disease_id)

