"""Messages router — per-message operations.

Routes:
    GET /api/v1/messages/{id}/trace — version + engine trace for an assistant message.

Authorization for /trace:
  - Owner of the conversation that contains the message.
  - Any user with role ``reviewer`` or ``admin``.
"""

from fastapi import APIRouter, Depends

from app.api_gateway.dependencies import CurrentUser, get_current_user
from app.models.contracts import MessageTraceResponse
from app.services import chat_service

router = APIRouter(prefix="/api/v1/messages", tags=["messages"])


@router.get(
    "/{message_id}/trace",
    response_model=MessageTraceResponse,
    summary="Get Message Trace",
    description=(
        "Return prompt/model/KG/pipeline version metadata and engine execution metadata "
        "for a specific assistant message. "
        "Accessible by the message owner, any reviewer, or any admin."
    ),
)
async def get_message_trace(
    message_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> MessageTraceResponse:
    """Fetch trace data for a single assistant message."""
    return await chat_service.get_message_trace(
        message_id=message_id,
        requester_user_id=current_user.id,
        requester_role=current_user.role,
    )
