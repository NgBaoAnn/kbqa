"""Feedback router — POST /api/v1/messages/{id}/feedback.

Thin handler: parse → ManageFeedbackUseCase → format response.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request, status

from api.middleware.auth import CurrentUser, get_current_user
from api.schemas.requests import FeedbackCreateRequest
from api.schemas.responses import FeedbackResponse, MessageTraceResponse
from domain.shared.errors import AuthorizationError, MessageNotFoundError
from use_cases.manage_feedback import FeedbackInput

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
    uc = request.app.state.container.manage_feedback
    try:
        row = uc.create_feedback(
            user_id=current_user.id,
            message_id=message_id,
            payload=FeedbackInput(
                rating=payload.rating,
                reason=payload.reason,
                comment=payload.comment,
            ),
        )
    except ValueError as exc:
        code = str(exc)
        status_code = (
            status.HTTP_404_NOT_FOUND
            if code == "MESSAGE_NOT_FOUND"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=status_code,
            detail={"error_code": code, "message": code.replace("_", " ").title()},
        ) from exc
    return FeedbackResponse(
        id=str(row.id),
        message_id=str(row.message_id),
        rating=row.rating,
        reason=row.reason,
        review_item_id=str(row.review_item_id) if row.review_item_id else None,
        created_at=str(row.created_at),
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
) -> MessageTraceResponse:
    """Fetch execution trace for an assistant message."""
    uc = request.app.state.container.manage_conversation
    try:
        trace = uc.get_message_trace(
            message_id=message_id,
            requester_user_id=current_user.id,
            requester_role=current_user.role,
        )
    except MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": exc.error_code, "message": str(exc)},
        ) from exc
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": "TRACE_ACCESS_DENIED", "message": str(exc)},
        ) from exc
    return MessageTraceResponse(**trace)
