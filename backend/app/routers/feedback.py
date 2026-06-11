"""Feedback API contract stubs."""

from fastapi import APIRouter, Body, Depends, Path

from app.api_gateway.dependencies import CurrentUser, get_current_user
from app.models.contracts import FeedbackCreateRequest, FeedbackResponse
from app.services import feedback_service

router = APIRouter(prefix="/api/v1/messages", tags=["feedback"])


@router.post(
    "/{message_id}/feedback",
    response_model=FeedbackResponse,
    status_code=201,
    summary="Create Message Feedback",
    responses={501: {"description": "Contract stub, not implemented yet"}},
)
async def create_feedback(
    message_id: str = Path(..., description="Assistant message UUID"),
    payload: FeedbackCreateRequest = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    return await feedback_service.create_feedback(
        user_id=current_user.id,
        message_id=message_id,
        payload=payload,
    )

