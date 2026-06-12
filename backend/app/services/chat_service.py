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
    MessageTraceResponse,
    SafetyPayload,
    VersionMetadata,
)
from app.services import ai_service  # module-level so tests can patch it
from app.services import preference_service
from app.services import versioning_service

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
    metadata = r.get("metadata") or {}
    if isinstance(metadata, dict):
        suggestions = metadata.get("suggested_questions")
        if isinstance(suggestions, list):
            r["suggested_questions"] = [str(q) for q in suggestions if str(q).strip()]
    if rating:
        r["feedback"] = {"rating": rating, "reason": reason}
    return MessageRecord(**r)


def _persist_message_sources(
    db: SupabaseDatabase,
    conn: Any,
    message_id: str,
    ai_result: AIServiceResult,
) -> None:
    """Insert one row into public.message_sources per ChatSource in ai_result.

    Must be called within an active ``db.transaction()`` block so that source
    rows are committed or rolled back together with the assistant message.
    """
    db.execute_many_in_tx(
        conn,
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
        [
            (
                message_id,
                source.source_type,
                source.title,
                source.snippet or "",
                json.dumps(source.metadata),
                source.rank,
            )
            for source in ai_result.sources
        ],
    )


def _persist_query_log(
    db: SupabaseDatabase,
    conn: Any,
    message_id: str,
    ai_result: AIServiceResult,
    ai_called: bool,
) -> None:
    """Insert one row into public.query_logs for the AI call.

    Must be called within an active ``db.transaction()`` block so that the log
    row is committed or rolled back together with the assistant message.
    Now includes Sprint 1 version metadata in the log row's metadata JSONB.
    """
    meta = ai_result.metadata
    raw = ai_result.raw_engine_metadata
    query_status = "error" if raw.get("error_code") else "success"

    log_meta: dict[str, Any] = {
        "sprint": 2,
        "ai_called": ai_called,
        "query_mode": meta.query_mode,
    }
    if raw.get("error_code"):
        log_meta["error_code"] = raw["error_code"]
    if isinstance(raw.get("preferences"), dict):
        log_meta["preferences"] = raw["preferences"]

    # Sprint 1: merge version metadata into query log
    log_meta.update(versioning_service.get_version_metadata())

    db.execute_in_tx(
        conn,
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
    preferences = await preference_service.get_preferences(user_id, database=db)
    ai_result: AIServiceResult = await _ai.answer_question(
        question=payload.question,
        mode=payload.mode,
        conversation_id=conversation_id,
        preferences={
            "language": preferences["language"],
            "explanation_level": preferences["explanation_level"],
            "answer_style": preferences["answer_style"],
        },
    )

    # ── Step 4-7: Atomic persist of AI result ─────────────────────────────
    # All writes after AI call are wrapped in a single transaction so that
    # if any step fails, the DB is left in a consistent state (no orphaned
    # assistant messages without sources/query_logs).
    data_json = json.dumps(ai_result.data)  # json.dumps(None) → "null", valid JSONB
    with db.transaction() as conn:
        # Step 4: Persist assistant message
        # Sprint 1: merge version metadata into the message metadata JSONB
        version_meta = versioning_service.get_version_metadata()
        msg_metadata: dict[str, Any] = {
            **ai_result.metadata.model_dump(),
            **version_meta,
            "original_question": payload.question,
            "suggested_questions": ai_result.suggested_questions,
        }

        assistant_row = db.fetch_one_in_tx(
            conn,
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
                json.dumps(msg_metadata),
            ),
        )
        if assistant_row is None:
            raise RuntimeError("Failed to persist assistant message.")

        assistant_message_id = assistant_row["id"]

        # Step 5: Persist message_sources
        _persist_message_sources(db, conn, assistant_message_id, ai_result)

        # Step 6: Persist query_log
        _persist_query_log(db, conn, assistant_message_id, ai_result, ai_called=True)

        # Step 7: Update conversation timestamp
        db.execute_in_tx(
            conn,
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
        metadata=ChatMetadata(**msg_metadata),
    )


async def get_message_trace(
    *,
    message_id: str,
    requester_user_id: str,
    requester_role: str,
    database: SupabaseDatabase | None = None,
) -> MessageTraceResponse:
    """Return trace information for a single assistant message.

    Authorization rules:
    - The owner of the conversation that contains the message may access the trace.
    - Any user with role ``reviewer`` or ``admin`` may access any trace.

    Raises HTTP 404 if the message does not exist.
    Raises HTTP 403 if the requester is not the owner and not a reviewer/admin.
    """
    db = database or get_database()

    row = db.fetch_one(
        """
        select
            m.id::text as id,
            m.metadata,
            c.user_id::text as owner_id
        from public.messages m
        join public.conversations c on c.id = m.conversation_id
        where m.id = %s
          and m.role = 'assistant'
        """,
        (message_id,),
    )

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "MESSAGE_NOT_FOUND",
                "message": "Message was not found or is not an assistant message.",
            },
        )

    # Authorization: owner OR reviewer/admin
    is_owner = row["owner_id"] == requester_user_id
    is_privileged = requester_role in ("reviewer", "admin")
    if not is_owner and not is_privileged:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error_code": "TRACE_ACCESS_DENIED",
                "message": "You do not have permission to view this message trace.",
            },
        )

    metadata: dict[str, Any] = row.get("metadata") or {}

    # Extract version fields, falling back to empty strings if not persisted yet
    version_meta = VersionMetadata(
        prompt_version=metadata.get("prompt_version", ""),
        model_name=metadata.get("model_name", ""),
        kg_version=metadata.get("kg_version", ""),
        pipeline_version=metadata.get("pipeline_version", ""),
    )

    # Engine metadata: everything except the version keys
    version_keys = {"prompt_version", "model_name", "kg_version", "pipeline_version"}
    engine_meta = {k: v for k, v in metadata.items() if k not in version_keys}

    return MessageTraceResponse(
        message_id=message_id,
        version_metadata=version_meta,
        engine_metadata=engine_meta,
    )
