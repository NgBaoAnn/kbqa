"""Conversation and chat service backed by Supabase Postgres."""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status

from app.database import SupabaseDatabase, get_database
from app.models.contracts import (
    ChatMetadata,
    ChatResponse,
    ConversationCreateRequest,
    ConversationDetail,
    ConversationSummary,
    MessageCreateRequest,
    MessageRecord,
    SafetyPayload,
)


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


def _mock_answer(question: str) -> str:
    return (
        "Đây là phản hồi thử nghiệm của AegisHealth trong Sprint 1. "
        "Hệ thống đã lưu câu hỏi của bạn và chưa gọi AI thật ở giai đoạn này. "
        f"Nội dung cần xử lý: {question}"
    )


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

    safety = SafetyPayload()
    metadata = ChatMetadata(
        engine="mock",
        query_mode=payload.mode or "mock:sprint1",
        execution_time_ms=0,
        source_count=0,
        cypher=None,
    )
    answer = _mock_answer(payload.question)
    assistant_row = db.fetch_one(
        f"""
        insert into public.messages (
            conversation_id,
            role,
            content,
            response_type,
            data,
            safety,
            metadata
        )
        values (%s, 'assistant', %s, 'text', null, %s::jsonb, %s::jsonb)
        returning {MESSAGE_COLUMNS}
        """,
        (
            conversation_id,
            answer,
            safety.model_dump_json(),
            metadata.model_dump_json(),
        ),
    )
    if assistant_row is None:
        raise RuntimeError("Failed to persist assistant message.")

    db.execute(
        "update public.conversations set updated_at = timezone('utc', now()) where id = %s",
        (conversation_id,),
    )
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
        values (%s, 'mock', %s, 0, 0, 'success', %s::jsonb)
        """,
        (
            assistant_row["id"],
            metadata.query_mode,
            json.dumps({"sprint": 1, "ai_called": False}),
        ),
    )

    return ChatResponse(
        conversation_id=conversation_id,
        message_id=assistant_row["id"],
        status="success",
        response_type="text",
        answer=answer,
        data=None,
        sources=[],
        safety=safety,
        suggested_questions=[],
        metadata=metadata,
    )
