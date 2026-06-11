"""Conversation API contract stubs."""

from fastapi import APIRouter, Body, Depends, Path

from app.api_gateway.dependencies import CurrentUser, get_current_user
from app.models.contracts import (
    ChatResponse,
    ConversationCreateRequest,
    ConversationDetail,
    ConversationSummary,
    MessageCreateRequest,
)
from app.services import chat_service

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.post(
    "",
    response_model=ConversationSummary,
    status_code=201,
    summary="Create Conversation",
    responses={501: {"description": "Contract stub, not implemented yet"}},
)
async def create_conversation(
    payload: ConversationCreateRequest = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    return await chat_service.create_conversation(user_id=current_user.id, payload=payload)


@router.get(
    "",
    response_model=list[ConversationSummary],
    summary="List Conversations",
    responses={501: {"description": "Contract stub, not implemented yet"}},
)
async def list_conversations(current_user: CurrentUser = Depends(get_current_user)):
    return await chat_service.list_conversations(user_id=current_user.id)


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetail,
    summary="Get Conversation Detail",
    responses={501: {"description": "Contract stub, not implemented yet"}},
)
async def get_conversation(
    conversation_id: str = Path(..., description="Conversation UUID"),
    current_user: CurrentUser = Depends(get_current_user),
):
    return await chat_service.get_conversation(
        user_id=current_user.id,
        conversation_id=conversation_id,
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=ChatResponse,
    status_code=201,
    summary="Send Message To Conversation",
    responses={501: {"description": "Contract stub, not implemented yet"}},
)
async def create_message(
    conversation_id: str = Path(..., description="Conversation UUID"),
    payload: MessageCreateRequest = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    return await chat_service.create_message(
        user_id=current_user.id,
        conversation_id=conversation_id,
        payload=payload,
    )

