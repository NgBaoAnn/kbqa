"""Current-user endpoint backed by Supabase access-token verification."""

from fastapi import APIRouter, Depends

from app.api_gateway.dependencies import CurrentUser, get_current_user
from app.models.contracts import CurrentUserResponse

router = APIRouter(prefix="/api/v1", tags=["me"])


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    summary="Get Current User",
    description="Smoke endpoint for Supabase Bearer token verification. S1-BE-01 will extend it with profile data.",
)
async def get_me(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    """Return the authenticated Supabase user visible to the backend."""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "auth_provider": "supabase",
    }
