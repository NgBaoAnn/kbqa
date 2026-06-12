"""Conversation API — create, list, retrieve conversations and send messages."""

from typing import Literal

from fastapi import APIRouter, Body, Depends, Path, Query
from fastapi.responses import Response, StreamingResponse

from app.api_gateway.dependencies import CurrentUser, get_current_user
from app.models.contracts import (
    ChatResponse,
    ConversationCreateRequest,
    ConversationDetail,
    ConversationSummary,
    MessageCreateRequest,
)
from app.services import chat_service
from app.services import export_service
from app.services import streaming_service

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.post(
    "",
    response_model=ConversationSummary,
    status_code=201,
    summary="Create Conversation",
    responses={404: {"description": "Conversation not found"}},
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
    responses={404: {"description": "Conversation not found"}},
)
async def list_conversations(current_user: CurrentUser = Depends(get_current_user)):
    return await chat_service.list_conversations(user_id=current_user.id)


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetail,
    summary="Get Conversation Detail",
    responses={404: {"description": "Conversation not found"}},
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
    responses={404: {"description": "Conversation not found"}},
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


@router.post(
    "/{conversation_id}/messages/stream",
    summary="Stream Message To Conversation",
    responses={404: {"description": "Conversation not found"}},
)
async def create_message_stream(
    conversation_id: str = Path(..., description="Conversation UUID"),
    payload: MessageCreateRequest = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    return StreamingResponse(
        streaming_service.stream_message_events(
            user_id=current_user.id,
            conversation_id=conversation_id,
            payload=payload,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/{conversation_id}/export",
    summary="Export Conversation",
    responses={404: {"description": "Conversation not found"}},
)
async def export_conversation(
    conversation_id: str = Path(..., description="Conversation UUID"),
    export_format: Literal["markdown", "pdf"] = Query("markdown", alias="format"),
    current_user: CurrentUser = Depends(get_current_user),
):
    exported = await export_service.export_conversation(
        user_id=current_user.id,
        conversation_id=conversation_id,
        export_format=export_format,
    )
    return Response(
        content=exported.content,
        media_type=exported.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{exported.filename}"',
            "Cache-Control": "no-store",
        },
    )
