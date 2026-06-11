"""Conversation and chat service backed by Supabase Postgres.

Sprint 2 changes (S2-BE-01, S2-BE-02):
- create_message() now calls ai_service.answer_question() instead of the mock.
- Assistant message is persisted with full answer/response_type/safety/metadata.
- message_sources rows are inserted for each ChatSource from the AI result.
- query_logs row is inserted with engine/query_mode/latency/source_count.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import HTTPException, status

from app.database import SupabaseDatabase, get_database
from app.models.contracts import (
    AIServiceResult,
    ChatMetadata,
    ChatResponse,
    ConversationCreateRequest,
    ConversationDetail,
    ConversationSummary,
    MessageCreateRequest,
    MessageRecord,
    SafetyPayload,
)
from app.services import ai_service  # module-level so tests can patch it

logger = logging.getLogger(__name__)

# ── Column projections ─────────────────────────────────────────────────────

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


# ── Helpers ────────────────────────────────────────────────────────────────


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
    r = dict(row)
    rating = r.pop("feedback_rating", None)
    reason = r.pop("feedback_reason", None)
    if rating:
        r["feedback"] = {"rating": rating, "reason": reason}
    return MessageRecord(**r)


def _persist_message_sources(
    db: SupabaseDatabase,
    message_id: str,
    ai_result: AIServiceResult,
) -> None:
    """Insert one row into public.message_sources per ChatSource in ai_result.

    Each source's metadata dict is serialized to JSONB.  Secret keys are already
    stripped by source_policy before reaching here, so no additional sanitisation
    is needed.
    """
    for source in ai_result.sources:
        db.execute(
            """
            insert into public.message_sources (
                message_id,
                source_type,
                title,
                snippet,
                metadata,
                rank
            )
            values (%s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                message_id,
                source.source_type,
                source.title,
                source.snippet or "",
                json.dumps(source.metadata),
                source.rank,
            ),
        )


def _persist_query_log(
    db: SupabaseDatabase,
    message_id: str,
    ai_result: AIServiceResult,
    ai_called: bool,
) -> None:
    """Insert one row into public.query_logs for the AI call.

    raw_engine_metadata is used here so the log reflects what the pipeline
    actually returned, not the normalised ChatMetadata.  Crucially it must NOT
    contain secrets — that guarantee comes from ai_service which never puts
    credentials in raw_engine_metadata.
    """
    meta = ai_result.metadata
    # Determine status: if the pipeline returned an error, log it as 'error'
    raw = ai_result.raw_engine_metadata
    query_status = "error" if raw.get("error_code") else "success"

    # Build clean log metadata — exclude any key that looks like a secret
    log_meta: dict[str, Any] = {
        "sprint": 2,
        "ai_called": ai_called,
        "query_mode": meta.query_mode,
    }
    # Include error_code if present (helpful for debugging, not a secret)
    if raw.get("error_code"):
        log_meta["error_code"] = raw["error_code"]

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
        values (%s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        (
            message_id,
            meta.engine,
            meta.query_mode,
            meta.execution_time_ms,
            meta.source_count,
            query_status,
            json.dumps(log_meta),
        ),
    )


# ── Public service functions ───────────────────────────────────────────────


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
        """
        select 
            m.id::text as id,
            m.role,
            m.content,
            m.response_type,
            m.data,
            m.safety,
            m.metadata,
            m.created_at::text as created_at,
            f.rating as feedback_rating,
            f.reason as feedback_reason
        from public.messages m
        left join public.feedback f on f.message_id = m.id and f.user_id = %s
        where m.conversation_id = %s
        order by m.created_at asc
        """,
        (user_id, conversation_id),
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
    ai_service_module=None,  # injectable for testing
) -> ChatResponse:
    """Handle a user question: call AI, persist messages, sources and query log.

    Flow:
    1. Verify the conversation belongs to this user.
    2. Insert the user message.
    3. Call ai_service.answer_question() for the real AI response.
    4. Insert the assistant message with full response_type / safety / metadata.
    5. Insert message_sources rows (S2-BE-02).
    6. Insert query_logs row (S2-BE-02).
    7. Update conversation.updated_at.
    8. Return a ChatResponse mapping the persisted assistant message.

    The ``ai_service_module`` parameter allows tests to inject a mock without
    patching the global import.
    """
    db = database or get_database()

    # ── Step 1: Verify ownership ───────────────────────────────────────────
    conversation = db.fetch_one(
        "select id::text as id from public.conversations where id = %s and user_id = %s",
        (conversation_id, user_id),
    )
    if conversation is None:
        raise _not_found()

    # ── Step 2: Persist user message ──────────────────────────────────────
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

    # ── Step 3: Call AI service ───────────────────────────────────────────
    # ai_service_module allows tests to inject a mock without patching the global
    # import. Production code uses the module-level `ai_service` (patchable).
    _ai = ai_service_module if ai_service_module is not None else ai_service
    ai_result: AIServiceResult = await _ai.answer_question(
        question=payload.question,
        mode=payload.mode,
        conversation_id=conversation_id,
    )

    # ── Step 4: Persist assistant message ─────────────────────────────────
    # json.dumps(None) produces the string "null" which is valid JSONB.
    data_json = json.dumps(ai_result.data)
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
        values (%s, 'assistant', %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
        returning {MESSAGE_COLUMNS}
        """,
        (
            conversation_id,
            ai_result.answer,
            ai_result.response_type,
            data_json,
            ai_result.safety.model_dump_json(),
            ai_result.metadata.model_dump_json(),
        ),
    )
    if assistant_row is None:
        raise RuntimeError("Failed to persist assistant message.")

    assistant_message_id = assistant_row["id"]

    # ── Step 5: Persist message_sources ───────────────────────────────────
    _persist_message_sources(db, assistant_message_id, ai_result)

    # ── Step 6: Persist query_log ─────────────────────────────────────────
    _persist_query_log(db, assistant_message_id, ai_result, ai_called=True)

    # ── Step 7: Update conversation timestamp ─────────────────────────────
    db.execute(
        "update public.conversations set updated_at = timezone('utc', now()) where id = %s",
        (conversation_id,),
    )

    # ── Step 8: Build and return ChatResponse ─────────────────────────────
    return ChatResponse(
        conversation_id=conversation_id,
        message_id=assistant_message_id,
        status="success",
        response_type=ai_result.response_type,
        answer=ai_result.answer,
        data=ai_result.data,
        sources=ai_result.sources,
        safety=ai_result.safety,
        suggested_questions=ai_result.suggested_questions,
        metadata=ai_result.metadata,
    )
