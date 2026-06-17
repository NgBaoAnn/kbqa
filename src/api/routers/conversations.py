"""Conversations router — create, list, retrieve conversations and send messages.

Pattern: parse → call ManageConversationUseCase / AnswerQuestionUseCase → format response.
No business logic here.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Request
from fastapi.responses import Response, StreamingResponse

from api.middleware.auth import CurrentUser, get_current_user
from api.schemas.requests import ConversationCreateRequest, MessageCreateRequest
from api.schemas.responses import (
    ChatMetadata,
    ChatResponse,
    ChatSource,
    ConversationDetail,
    ConversationSummary,
    MessageRecord,
    MessageFeedback,
    SafetyPayload,
)
from api.streaming_chat import build_message_stream_events

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


# ── Helpers ────────────────────────────────────────────────────────────────

def _row_to_summary(row: dict) -> ConversationSummary:
    return ConversationSummary(
        id=str(row["id"]),
        title=row.get("title") or "Untitled",
        language=row.get("language", "vi"),
        created_at=str(row.get("created_at", "")),
        updated_at=str(row.get("updated_at", "")),
    )


def _result_to_chat_response(
    result,
    *,
    conversation_id: str,
    message_id: str,
    metadata_override: dict | None = None,
) -> ChatResponse:
    safety_raw = result.safety or {}
    sources = [
        ChatSource(
            id=s.get("id"),
            source_type=s.get("source_type", "other"),
            title=s.get("title", ""),
            snippet=s.get("snippet"),
            rank=s.get("rank", 1),
            metadata=s.get("metadata", {}),
        )
        for s in (result.sources or [])
    ]
    meta = metadata_override or result.metadata or {}
    return ChatResponse(
        conversation_id=conversation_id,
        message_id=message_id,
        status="success",
        response_type=result.response_type,
        answer=result.answer,
        data=result.data,
        sources=sources,
        safety=SafetyPayload(
            level=safety_raw.get("level", "normal"),
            requires_emergency_notice=safety_raw.get("requires_emergency_notice", False),
            disclaimer=safety_raw.get("disclaimer", "Thông tin chỉ mang tính chất tham khảo."),
        ),
        suggested_questions=result.suggested_questions or [],
        metadata=ChatMetadata(
            engine=meta.get("engine", "unknown"),
            query_mode=meta.get("query_mode", "auto"),
            execution_time_ms=meta.get("execution_time_ms", 0.0),
            source_count=meta.get("source_count", len(sources)),
            cypher=meta.get("cypher"),
            prompt_version=meta.get("prompt_version"),
            model_name=meta.get("model_name"),
            kg_version=meta.get("kg_version"),
            pipeline_version=meta.get("pipeline_version"),
            language=meta.get("language"),
            explanation_level=meta.get("explanation_level"),
            answer_style=meta.get("answer_style"),
            original_question=meta.get("original_question"),
            suggested_questions=result.suggested_questions or [],
            persisted=meta.get("persisted", True),
        ),
    )


# ── Routes ─────────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=ConversationSummary,
    status_code=201,
    summary="Create Conversation",
)
async def create_conversation(
    payload: ConversationCreateRequest = Body(...),
    request: Request = None,
    current_user: CurrentUser = Depends(get_current_user),
) -> ConversationSummary:
    uc = request.app.state.container.manage_conversation
    row = uc.create_conversation(user_id=current_user.id, title=payload.title, language=payload.language)
    return _row_to_summary(row)


@router.get(
    "",
    response_model=list[ConversationSummary],
    summary="List Conversations",
)
async def list_conversations(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ConversationSummary]:
    uc = request.app.state.container.manage_conversation
    rows = uc.list_conversations(user_id=current_user.id)
    return [_row_to_summary(r) for r in rows]


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetail,
    summary="Get Conversation Detail",
    responses={404: {"description": "Conversation not found"}},
)
async def get_conversation(
    conversation_id: str = Path(..., description="Conversation UUID"),
    request: Request = None,
    current_user: CurrentUser = Depends(get_current_user),
) -> ConversationDetail:
    uc = request.app.state.container.manage_conversation
    data = uc.get_conversation(user_id=current_user.id, conversation_id=conversation_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    conv = _row_to_summary(data["conversation"])
    messages = [
        MessageRecord(
            id=str(m["id"]),
            role=m["role"],
            content=m["content"],
            response_type=m.get("response_type"),
            data=m.get("data"),
            safety=m.get("safety"),
            suggested_questions=m.get("suggested_questions", []),
            metadata=m.get("metadata", {}),
            feedback=MessageFeedback(
                rating=m["feedback_rating"],
                reason=m.get("feedback_reason"),
            ) if m.get("feedback_rating") else None,
            created_at=str(m.get("created_at", "")),
        )
        for m in data.get("messages", [])
    ]
    return ConversationDetail(conversation=conv, messages=messages)


@router.post(
    "/{conversation_id}/messages",
    response_model=ChatResponse,
    status_code=201,
    summary="Send Message",
    responses={404: {"description": "Conversation not found"}},
)
async def create_message(
    conversation_id: str = Path(..., description="Conversation UUID"),
    payload: MessageCreateRequest = Body(...),
    request: Request = None,
    current_user: CurrentUser = Depends(get_current_user),
) -> ChatResponse:
    container = request.app.state.container
    conv_uc = container.manage_conversation
    preferences = container.manage_preferences.get_preferences(user_id=current_user.id)

    # Verify ownership
    if not conv_uc.ensure_owner(user_id=current_user.id, conversation_id=conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")

    # Save user message
    conv_uc.persist_user_message(
        conversation_id=conversation_id,
        question=payload.question,
        mode=payload.mode,
    )

    # Execute QA
    result = await container.answer_question.execute(
        question=payload.question,
        mode=payload.mode,
        preferences=preferences,
    )

    # Persist assistant response (includes sources + query log in one transaction)
    persisted = conv_uc.persist_assistant_response(
        conversation_id=conversation_id,
        question=payload.question,
        ai_result=result,
    )

    return _result_to_chat_response(
        result,
        conversation_id=conversation_id,
        message_id=persisted["message_id"],
        metadata_override=persisted["metadata"],
    )


@router.post(
    "/{conversation_id}/messages/stream",
    summary="Stream Message",
    responses={404: {"description": "Conversation not found"}},
)
async def create_message_stream(
    conversation_id: str = Path(..., description="Conversation UUID"),
    payload: MessageCreateRequest = Body(...),
    request: Request = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Stream assistant response using Server-Sent Events."""
    container = request.app.state.container
    conv_uc = container.manage_conversation
    preferences = container.manage_preferences.get_preferences(user_id=current_user.id)

    if not conv_uc.ensure_owner(user_id=current_user.id, conversation_id=conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")

    # Save user message eagerly before streaming starts
    conv_uc.persist_user_message(
        conversation_id=conversation_id,
        question=payload.question,
        mode=payload.mode,
    )

    return StreamingResponse(
        build_message_stream_events(
            conversation_id=conversation_id,
            question=payload.question,
            mode=payload.mode,
            preferences=preferences,
            answer_question_stream=container.answer_question_stream,
            manage_conversation=conv_uc,
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
    request: Request = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Export a conversation as Markdown (default) or PDF."""
    uc = request.app.state.container.manage_conversation
    data = uc.get_conversation(user_id=current_user.id, conversation_id=conversation_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    if export_format == "markdown":
        conv = data["conversation"]
        lines = [f"# {conv.get('title', 'Conversation')}\n"]
        for m in data.get("messages", []):
            role = "**User**" if m["role"] == "user" else "**Assistant**"
            lines.append(f"{role}: {m['content']}\n")
        content = "\n".join(lines).encode("utf-8")
        filename = f"conversation-{conversation_id[:8]}.md"
        return Response(
            content=content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )
    else:
        raise HTTPException(status_code=501, detail="PDF export not yet implemented.")
