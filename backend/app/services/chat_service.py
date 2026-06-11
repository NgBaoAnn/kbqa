"""Conversation and chat service backed by Supabase Postgres."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import HTTPException, status

from app.database import SupabaseDatabase, get_database
from app.models.contracts import (
    ChatResponse,
    ConversationCreateRequest,
    ConversationDetail,
    ConversationSummary,
    MessageCreateRequest,
    MessageRecord,
)

logger = logging.getLogger(__name__)


CONVERSATION_COLUMNS = """
    id::text as id,
    title,
    language,
    created_at::text as created_at,
    updated_at::text as updated_at
"""

MESSAGE_COLUMNS = """
    id::text as id,
    role,
    content,
    response_type,
    data,
    safety,
    metadata,
    created_at::text as created_at
"""


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error_code": "CONVERSATION_NOT_FOUND",
            "message": "Conversation was not found.",
        },
    )


def _conversation_summary(row: dict[str, Any]) -> ConversationSummary:
    return ConversationSummary(**row)


def _message_record(row: dict[str, Any]) -> MessageRecord:
    return MessageRecord(**row)





async def create_conversation(
    *,
    user_id: str,
    payload: ConversationCreateRequest,
    database: SupabaseDatabase | None = None,
) -> ConversationSummary:
    db = database or get_database()
    title = payload.title or "Cuộc trò chuyện mới"
    row = db.fetch_one(
        f"""
        insert into public.conversations (user_id, title, language)
        values (%s, %s, %s)
        returning {CONVERSATION_COLUMNS}
        """,
        (user_id, title, payload.language),
    )
    if row is None:
        raise RuntimeError("Failed to create conversation.")
    return _conversation_summary(row)


async def list_conversations(
    *,
    user_id: str,
    database: SupabaseDatabase | None = None,
) -> list[ConversationSummary]:
    db = database or get_database()
    rows = db.fetch_all(
        f"""
        select {CONVERSATION_COLUMNS}
        from public.conversations
        where user_id = %s
        order by updated_at desc
        """,
        (user_id,),
    )
    return [_conversation_summary(row) for row in rows]


async def get_conversation(
    *,
    user_id: str,
    conversation_id: str,
    database: SupabaseDatabase | None = None,
) -> ConversationDetail:
    db = database or get_database()
    conversation = db.fetch_one(
        f"""
        select {CONVERSATION_COLUMNS}
        from public.conversations
        where id = %s
          and user_id = %s
        """,
        (conversation_id, user_id),
    )
    if conversation is None:
        raise _not_found()

    messages = db.fetch_all(
        f"""
        select {MESSAGE_COLUMNS}
        from public.messages
        where conversation_id = %s
        order by created_at asc
        """,
        (conversation_id,),
    )
    return ConversationDetail(
        conversation=_conversation_summary(conversation),
        messages=[_message_record(row) for row in messages],
    )


async def create_message(
    *,
    user_id: str,
    conversation_id: str,
    payload: MessageCreateRequest,
    database: SupabaseDatabase | None = None,
) -> ChatResponse:
    db = database or get_database()
    conversation = db.fetch_one(
        "select id::text as id from public.conversations where id = %s and user_id = %s",
        (conversation_id, user_id),
    )
    if conversation is None:
        raise _not_found()

    # ── Persist user message ───────────────────────────────────────────────
    db.fetch_one(
        f"""
        insert into public.messages (conversation_id, role, content, metadata)
        values (%s, 'user', %s, %s::jsonb)
        returning {MESSAGE_COLUMNS}
        """,
        (
            conversation_id,
            payload.question,
            json.dumps({"mode": payload.mode, "source": "api"}),
        ),
    )

    # ── Reserve assistant message row to get its id for ai_service ────────
    placeholder_row = db.fetch_one(
        f"""
        insert into public.messages (
            conversation_id, role, content, response_type, metadata
        )
        values (%s, 'assistant', '', 'text', '{{}}'::jsonb)
        returning {MESSAGE_COLUMNS}
        """,
        (conversation_id,),
    )
    if placeholder_row is None:
        raise RuntimeError("Failed to reserve assistant message row.")
    message_id: str = placeholder_row["id"]

    # ── Call real AI pipeline ──────────────────────────────────────────────
    from app.services import ai_service

    logger.info(
        "chat_service: invoking ai_service for conversation=%s message=%s",
        conversation_id,
        message_id,
    )
    chat_response = await ai_service.answer_question(
        conversation_id=conversation_id,
        message_id=message_id,
        question=payload.question,
        mode=payload.mode,
    )

    # ── Persist real answer into the reserved row ──────────────────────────
    safety_json = chat_response.safety.model_dump_json()
    metadata_json = chat_response.metadata.model_dump_json()

    db.execute(
        """
        update public.messages
        set
            content       = %s,
            response_type = %s,
            safety        = %s::jsonb,
            metadata      = %s::jsonb
        where id = %s
        """,
        (
            chat_response.answer,
            chat_response.response_type,
            safety_json,
            metadata_json,
            message_id,
        ),
    )

    # ── Update conversation timestamp ──────────────────────────────────────
    db.execute(
        "update public.conversations set updated_at = timezone('utc', now()) where id = %s",
        (conversation_id,),
    )

    # ── Write query log ────────────────────────────────────────────────────
    db.execute(
        """
        insert into public.query_logs (
            message_id,
            engine,
            query_mode,
            execution_time_ms,
            source_count,
            status,
            metadata
        )
        values (%s, %s, %s, %s, %s, 'success', %s::jsonb)
        """,
        (
            message_id,
            chat_response.metadata.engine,
            chat_response.metadata.query_mode,
            chat_response.metadata.execution_time_ms,
            chat_response.metadata.source_count,
            json.dumps({"ai_called": True}),
        ),
    )

    return chat_response
