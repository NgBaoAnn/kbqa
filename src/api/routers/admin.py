"""Admin router — metrics and review queue.

Routes:
    GET  /api/v1/admin/metrics        — operational metrics (admin only)
    GET  /api/v1/admin/review-items   — pending review queue (admin only)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from api.middleware.auth import CurrentUser, require_admin
from api.schemas.responses import AdminMetricsResponse, ReviewQueueResponse

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
async def get_metrics(
    request: Request,
    current_user: CurrentUser = Depends(require_admin),
) -> AdminMetricsResponse:
    from use_cases.admin_analytics import AdminAnalyticsUseCase

    uc = AdminAnalyticsUseCase(db=request.app.state.container.db)
    metrics = await uc.get_metrics()
    return AdminMetricsResponse(**metrics)


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
    request: Request,
    limit: int = Query(default=20, ge=1, le=100, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    current_user: CurrentUser = Depends(require_admin),
) -> ReviewQueueResponse:
    from use_cases.admin_analytics import AdminAnalyticsUseCase

    uc = AdminAnalyticsUseCase(db=request.app.state.container.db)
    result = await uc.get_review_queue(limit=limit, offset=offset)
    return result
