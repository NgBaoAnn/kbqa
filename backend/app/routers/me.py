"""Current-user and preferences endpoints backed by Supabase access-token verification.

Routes:
    GET   /api/v1/me                — current user profile
    GET   /api/v1/me/preferences    — user personalisation settings
    PATCH /api/v1/me/preferences    — update one or more preference fields
"""

from fastapi import APIRouter, Depends

from app.api_gateway.dependencies import CurrentUser, get_current_user
from app.models.contracts import CurrentUserResponse, UserPreferences, UserPreferencesResponse
from app.services import preference_service

router = APIRouter(prefix="/api/v1", tags=["me"])


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    summary="Get Current User",
    description="Return the active app profile mapped from the Supabase Bearer token.",
)
async def get_me(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    """Return the authenticated Supabase user profile visible to the backend."""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "display_name": current_user.display_name,
        "is_active": current_user.is_active,
        "auth_provider": "supabase",
    }


@router.get(
    "/me/preferences",
    response_model=UserPreferencesResponse,
    summary="Get User Preferences",
    description=(
        "Return personalisation preferences for the current user. "
        "Defaults (language=vi, explanation_level=general, answer_style=concise) "
        "are created automatically on first access."
    ),
)
async def get_preferences(
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Fetch (or auto-create default) preferences for the authenticated user."""
    return await preference_service.get_preferences(current_user.id)


@router.patch(
    "/me/preferences",
    response_model=UserPreferencesResponse,
    summary="Update User Preferences",
    description=(
        "Partially update one or more preference fields. "
        "Unknown fields are ignored. An empty body is a no-op."
    ),
)
async def patch_preferences(
    body: UserPreferences,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Apply a partial update to the current user's preferences."""
    patch = body.model_dump(exclude_unset=True)
    return await preference_service.update_preferences(current_user.id, patch)
