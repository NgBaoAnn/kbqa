"""Feedback router — POST /api/v1/messages/{id}/feedback.

Thin handler: parse → ManageFeedbackUseCase → format response.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Path, Request

from api.middleware.auth import CurrentUser, get_current_user
from api.schemas.requests import FeedbackCreateRequest
from api.schemas.responses import FeedbackResponse

router = APIRouter(prefix="/api/v1/messages", tags=["feedback"])


@router.post(
    "/{message_id}/feedback",
    response_model=FeedbackResponse,
    status_code=201,
    summary="Submit Message Feedback",
    responses={404: {"description": "Message not found"}},
)
async def create_feedback(
    message_id: str = Path(..., description="Assistant message UUID"),
    payload: FeedbackCreateRequest = Body(...),
    request: Request = None,
    current_user: CurrentUser = Depends(get_current_user),
) -> FeedbackResponse:
    """Submit thumbs-up / thumbs-down feedback for an assistant message."""
    from use_cases.manage_feedback import ManageFeedbackUseCase

    uc = ManageFeedbackUseCase(db=request.app.state.container.db)
    row = uc.create_feedback(
        user_id=current_user.id,
        message_id=message_id,
        rating=payload.rating,
        reason=payload.reason,
        comment=payload.comment,
    )
    return FeedbackResponse(
        id=str(row["id"]),
        message_id=str(row["message_id"]),
        rating=row["rating"],
        reason=row.get("reason"),
        review_item_id=str(row["review_item_id"]) if row.get("review_item_id") else None,
        created_at=str(row.get("created_at", "")),
    )


@router.get(
    "/{message_id}/trace",
    summary="Get Message Trace",
    description=(
        "Return prompt/model/KG/pipeline version metadata and engine execution metadata "
        "for a specific assistant message. "
        "Accessible by the message owner, any reviewer, or any admin."
    ),
)
async def get_message_trace(
    message_id: str = Path(..., description="Assistant message UUID"),
    request: Request = None,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Fetch execution trace for an assistant message."""
    from use_cases.manage_conversation import ManageConversationUseCase

    uc = ManageConversationUseCase(db=request.app.state.container.db)
    return uc.get_message_trace(
        message_id=message_id,
        requester_user_id=current_user.id,
        requester_role=current_user.role,
    )
