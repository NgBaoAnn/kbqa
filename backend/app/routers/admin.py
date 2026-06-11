"""Admin API contract stubs."""

from fastapi import APIRouter, Depends

from app.api_gateway.dependencies import CurrentUser, get_admin_user
from app.models.contracts import AdminMetricsResponse
from app.services import analytics_service

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get(
    "/metrics",
    response_model=AdminMetricsResponse,
    summary="Get Admin Metrics",
    responses={501: {"description": "Contract stub, not implemented yet"}},
)
async def get_metrics(current_user: CurrentUser = Depends(get_admin_user)):
    _ = current_user
    return await analytics_service.get_admin_metrics()
