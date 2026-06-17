"""ManageConversationUseCase — CRUD for conversations and message persistence.

Responsibilities:
- Create / list / get conversations.
- Persist user message and AI response atomically.
- Insert message_sources and query_logs in the same transaction.

NOT responsible for:
- Running the AI pipeline (AnswerQuestionUseCase does that).
- Authorization beyond conversation ownership (router handles auth).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from domain.shared.errors import AuthorizationError, MessageNotFoundError

logger = logging.getLogger(__name__)

# ── Column projections (SQL string constants) ────────────────────────────
CONVERSATION_COLS = """
    id::text as id,
    title,
    language,
    created_at::text as created_at,
    updated_at::text as updated_at
"""

MESSAGE_COLS = """
    id::text as id,
    role,
    content,
    response_type,
    data,
    safety,
    metadata,
    created_at::text as created_at
"""


class ManageConversationUseCase:
    """Conversation and message persistence use case.

    Args:
        db: IDatabaseRepository
    """

    def __init__(self, *, db, version_metadata: dict[str, Any] | None = None) -> None:
        self._db = db
        self._version_metadata = version_metadata or {}

    # ── Conversation CRUD ─────────────────────────────────────────────────

    def create_conversation(
        self,
        *,
        user_id: str,
        title: str | None = None,
        language: str = "vi",
    ) -> dict[str, Any]:
        """Insert a new conversation row and return it."""
        title = title or "Cuộc trò chuyện mới"
        row = self._db.fetch_one(
            f"""
            insert into public.conversations (user_id, title, language)
            values (%s, %s, %s)
            returning {CONVERSATION_COLS}
            """,
            (user_id, title, language),
        )
        if row is None:
            raise RuntimeError("Failed to create conversation.")
        return dict(row)

    def list_conversations(self, *, user_id: str) -> list[dict[str, Any]]:
        rows = self._db.fetch_all(
            f"""
            select {CONVERSATION_COLS}
            from public.conversations
            where user_id = %s
            order by updated_at desc
            """,
            (user_id,),
        )
        return [dict(r) for r in rows]

    def get_conversation(
        self, *, user_id: str, conversation_id: str
    ) -> dict[str, Any] | None:
        """Return conversation + messages, or None if not found/not owned."""
        conv = self._db.fetch_one(
            f"""
            select {CONVERSATION_COLS}
            from public.conversations
            where id = %s and user_id = %s
            """,
            (conversation_id, user_id),
        )
        if conv is None:
            return None

        messages = self._db.fetch_all(
            f"""
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
        return {"conversation": dict(conv), "messages": [dict(m) for m in messages]}

    def ensure_owner(self, *, user_id: str, conversation_id: str) -> bool:
        """Return True if conversation belongs to user, False otherwise."""
        row = self._db.fetch_one(
            "select id::text as id from public.conversations where id = %s and user_id = %s",
            (conversation_id, user_id),
        )
        return row is not None

    # ── Message Persistence ───────────────────────────────────────────────

    def persist_user_message(
        self,
        *,
        conversation_id: str,
        question: str,
        mode: str | None = None,
    ) -> None:
        """Insert user message row (fire-and-forget, no return value needed)."""
        self._db.fetch_one(
            f"""
            insert into public.messages (conversation_id, role, content, metadata)
            values (%s, 'user', %s, %s::jsonb)
            returning {MESSAGE_COLS}
            """,
            (
                conversation_id,
                question,
                json.dumps({"mode": mode, "source": "api"}),
            ),
        )

    def persist_assistant_response(
        self,
        *,
        conversation_id: str,
        question: str,
        ai_result,  # AIServiceResult
        version_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Atomically persist assistant message + sources + query log.

        Returns the ChatResponse-equivalent dict.
        """
        version_meta = version_meta or self._version_metadata
        meta = ai_result.metadata if isinstance(ai_result.metadata, dict) else {}

        msg_metadata: dict[str, Any] = {
            **meta,
            **version_meta,
            "original_question": question,
            "suggested_questions": ai_result.suggested_questions,
            "persisted": True,
        }

        data_json = json.dumps(ai_result.data)
        safety_json = json.dumps(ai_result.safety)

        with self._db.transaction() as conn:
            assistant_row = self._db.fetch_one_in_tx(
                conn,
                f"""
                insert into public.messages (
                    conversation_id, role, content, response_type,
                    data, safety, metadata
                )
                values (%s, 'assistant', %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                returning {MESSAGE_COLS}
                """,
                (
                    conversation_id,
                    ai_result.answer,
                    ai_result.response_type,
                    data_json,
                    safety_json,
                    json.dumps(msg_metadata),
                ),
            )
            if assistant_row is None:
                raise RuntimeError("Failed to persist assistant message.")

            assistant_id = assistant_row["id"]

            # Insert sources
            if ai_result.sources:
                self._db.execute_many_in_tx(
                    conn,
                    """
                    insert into public.message_sources (
                        message_id, source_type, title, snippet, metadata, rank
                    )
                    values (%s, %s, %s, %s, %s::jsonb, %s)
                    """,
                    [
                        (
                            assistant_id,
                            s.get("source_type", "other"),
                            s.get("title", ""),
                            s.get("snippet", ""),
                            json.dumps({**(s.get("metadata", {}) or {}), "id": s.get("id")}),
                            s.get("rank", idx + 1),
                        )
                        for idx, s in enumerate(ai_result.sources)
                    ],
                )

            # Insert query log
            query_status = "error" if meta.get("error_code") else "success"
            log_meta: dict[str, Any] = {
                "ai_called": True,
                "query_mode": meta.get("query_mode", "unknown"),
                **version_meta,
            }
            if meta.get("error_code"):
                log_meta["error_code"] = meta["error_code"]

            self._db.execute_in_tx(
                conn,
                """
                insert into public.query_logs (
                    message_id, engine, query_mode, execution_time_ms,
                    source_count, status, metadata
                )
                values (%s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    assistant_id,
                    meta.get("engine", "unknown"),
                    meta.get("query_mode", "unknown"),
                    meta.get("execution_time_ms", 0.0),
                    meta.get("source_count", 0),
                    query_status,
                    json.dumps(log_meta),
                ),
            )

            # Update conversation timestamp
            self._db.execute_in_tx(
                conn,
                "update public.conversations set updated_at = timezone('utc', now()) where id = %s",
                (conversation_id,),
            )

        return {
            "conversation_id": conversation_id,
            "message_id": assistant_id,
            "status": "success",
            "response_type": ai_result.response_type,
            "answer": ai_result.answer,
            "data": ai_result.data,
            "sources": ai_result.sources,
            "safety": ai_result.safety,
            "suggested_questions": ai_result.suggested_questions,
            "metadata": msg_metadata,
        }

    def get_message_trace(
        self,
        *,
        message_id: str,
        requester_user_id: str,
        requester_role: str,
    ) -> dict[str, Any]:
        """Return version and engine metadata for one assistant message."""
        row = self._db.fetch_one(
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
            raise MessageNotFoundError(message_id)

        is_owner = row["owner_id"] == requester_user_id
        is_privileged = requester_role in ("reviewer", "admin")
        if not is_owner and not is_privileged:
            raise AuthorizationError("You do not have permission to view this message trace.")

        metadata = row.get("metadata") or {}
        version_keys = {"prompt_version", "model_name", "kg_version", "pipeline_version"}
        return {
            "message_id": message_id,
            "version_metadata": {
                "prompt_version": metadata.get("prompt_version", ""),
                "model_name": metadata.get("model_name", ""),
                "kg_version": metadata.get("kg_version", ""),
                "pipeline_version": metadata.get("pipeline_version", ""),
            },
            "engine_metadata": {
                key: value for key, value in metadata.items() if key not in version_keys
            },
        }
