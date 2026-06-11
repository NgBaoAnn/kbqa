"""Admin API — metrics and review queue.

Routes:
    GET  /api/v1/admin/metrics        — operational metrics (admin only)
    GET  /api/v1/admin/review-items   — pending review queue (admin only)
"""

from fastapi import APIRouter, Depends, Query

from app.api_gateway.dependencies import CurrentUser, get_admin_user
from app.models.contracts import AdminMetricsResponse, ReviewQueueResponse
from app.services import analytics_service

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get(
    "/metrics",
    response_model=AdminMetricsResponse,
    summary="Get Admin Metrics",
    description=(
        "Operational metrics aggregated from query_logs, feedback, and review_items. "
        "Requires admin role."
    ),
)
async def get_metrics(current_user: CurrentUser = Depends(get_admin_user)):
    _ = current_user
    return await analytics_service.get_admin_metrics()


@router.get(
    "/review-items",
    response_model=ReviewQueueResponse,
    summary="Get Review Queue",
    description=(
        "Paginated list of pending review items created from negative user feedback. "
        "Ordered newest-first. Requires admin role."
    ),
)
async def get_review_items(
    limit: int = Query(default=20, ge=1, le=100, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    current_user: CurrentUser = Depends(get_admin_user),
):
    _ = current_user
    return await analytics_service.get_review_queue(limit=limit, offset=offset)
