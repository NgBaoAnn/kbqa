"""Me router — current user profile and preferences.

Routes:
    GET   /api/v1/me                — current user profile
    GET   /api/v1/me/preferences    — user personalisation settings
    PATCH /api/v1/me/preferences    — update one or more preference fields
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from api.middleware.auth import CurrentUser, get_current_user
from api.schemas.requests import UserPreferencesUpdateRequest
from api.schemas.responses import CurrentUserResponse, UserPreferencesResponse

router = APIRouter(prefix="/api/v1", tags=["me"])


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    summary="Get Current User",
    description="Return the active app profile mapped from the Supabase Bearer token.",
)
async def get_me(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,  # type: ignore[arg-type]
        display_name=current_user.display_name,
        is_active=current_user.is_active,
        auth_provider="supabase",
    )


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
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> UserPreferencesResponse:
    from use_cases.manage_preferences import ManagePreferencesUseCase

    uc = ManagePreferencesUseCase(db=request.app.state.container.db)
    row = uc.get_preferences(user_id=current_user.id)
    return UserPreferencesResponse(**row)


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
    body: UserPreferencesUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> UserPreferencesResponse:
    from use_cases.manage_preferences import ManagePreferencesUseCase

    uc = ManagePreferencesUseCase(db=request.app.state.container.db)
    patch = body.model_dump(exclude_unset=True, exclude_none=True)
    row = uc.update_preferences(user_id=current_user.id, patch=patch)
    return UserPreferencesResponse(**row)
