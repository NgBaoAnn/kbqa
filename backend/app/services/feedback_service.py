"""Feedback service — S2-BE-03 & S2-BE-04.

Responsibilities:
- Persist feedback (rating, reason, comment) for an assistant message.
- Validate that the target message exists and belongs to the requesting user's conversation.
- Automatically create a ``review_items`` row when feedback is negative:
    - rating == "down"  OR
    - reason == "incorrect" OR reason == "unsafe"

NOT responsible for:
- Re-running the AI pipeline.
- Editing the knowledge graph.
- Authorization beyond ownership check.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import HTTPException, status

from app.database import SupabaseDatabase, get_database
from app.models.contracts import FeedbackCreateRequest, FeedbackResponse

logger = logging.getLogger(__name__)

# ── Review item creation policy ───────────────────────────────────────────
# A review_items row is inserted when ANY of these conditions is true.
_REVIEW_RATINGS = frozenset({"down"})
_REVIEW_REASONS = frozenset({"incorrect", "unsafe"})


def _should_create_review(payload: FeedbackCreateRequest) -> bool:
    """Return True when a pending review item should be created."""
    return payload.rating in _REVIEW_RATINGS or payload.reason in _REVIEW_REASONS


# ── Error factories ───────────────────────────────────────────────────────


def _message_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error_code": "MESSAGE_NOT_FOUND",
            "message": "Message was not found or does not belong to your conversation.",
        },
    )


def _message_not_assistant() -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "error_code": "FEEDBACK_ON_NON_ASSISTANT_MESSAGE",
            "message": "Feedback can only be given on assistant messages.",
        },
    )


# ── Internal helpers ──────────────────────────────────────────────────────


def _fetch_assistant_message(
    db: SupabaseDatabase,
    user_id: str,
    message_id: str,
) -> dict[str, Any]:
    """Return the message row if it is an assistant message in a conversation
    owned by ``user_id``, else raise an appropriate HTTPException.
    """
    row = db.fetch_one(
        """
        select
            m.id::text as id,
            m.role,
            m.conversation_id::text as conversation_id
        from public.messages m
        join public.conversations c on c.id = m.conversation_id
        where m.id = %s
          and c.user_id = %s
        """,
        (message_id, user_id),
    )
    if row is None:
        raise _message_not_found()
    if row["role"] != "assistant":
        raise _message_not_assistant()
    return row


def _insert_feedback(
    db: SupabaseDatabase,
    user_id: str,
    message_id: str,
    payload: FeedbackCreateRequest,
) -> dict[str, Any]:
    """Insert a feedback row and return it."""
    row = db.fetch_one(
        """
        insert into public.feedback (
            message_id,
            user_id,
            rating,
            reason,
            comment
        )
        values (%s, %s, %s, %s, %s)
        returning
            id::text as id,
            message_id::text as message_id,
            rating,
            reason,
            comment,
            created_at::text as created_at
        """,
        (
            message_id,
            user_id,
            payload.rating,
            payload.reason,
            payload.comment,
        ),
    )
    if row is None:
        raise RuntimeError("Failed to persist feedback.")
    return row


def _insert_review_item(
    db: SupabaseDatabase,
    feedback_id: str,
    reason: str | None,
) -> str | None:
    """Insert a review_items row for a negative/incorrect feedback.

    Category is derived from the feedback reason:
    - "incorrect"  → "incorrect_answer"
    - "unsafe"     → "safety_concern"
    - "down" (no explicit reason) → "negative_feedback"

    Returns the new review_item id as a string, or None if insert fails.
    """
    if reason == "incorrect":
        category = "answer_quality"
    elif reason == "unsafe":
        category = "safety"
    else:
        category = "other"

    row = db.fetch_one(
        """
        insert into public.review_items (
            feedback_id,
            status,
            category
        )
        values (%s, 'pending', %s)
        returning id::text as id
        """,
        (feedback_id, category),
    )
    if row is None:
        logger.warning("feedback_service: failed to create review item for feedback %s", feedback_id)
        return None
    logger.info(
        "feedback_service: review_item created id=%s category=%s feedback=%s",
        row["id"], category, feedback_id,
    )
    return row["id"]


# ── Public API ─────────────────────────────────────────────────────────────


async def create_feedback(
    *,
    user_id: str,
    message_id: str,
    payload: FeedbackCreateRequest,
    database: SupabaseDatabase | None = None,
) -> FeedbackResponse:
    """Persist user feedback for an assistant message.

    Steps:
    1. Verify the message exists, is an assistant message, and belongs to a
       conversation owned by ``user_id``.
    2. Insert the feedback row.
    3. If the feedback is negative (rating=down or reason=incorrect/unsafe),
       insert a pending review_items row.
    4. Return a FeedbackResponse with the feedback id and optional review_item_id.

    Args:
        user_id: Supabase auth user id (from JWT).
        message_id: The assistant message UUID the feedback targets.
        payload: Rating, reason, and optional comment.
        database: Optional injected SupabaseDatabase for testing.

    Returns:
        FeedbackResponse with id, message_id, rating, reason,
        review_item_id (if created), and created_at.
    """
    db = database or get_database()

    # ── Validate message ownership ────────────────────────────────────────
    _fetch_assistant_message(db, user_id, message_id)

    # ── Persist feedback ──────────────────────────────────────────────────
    feedback_row = _insert_feedback(db, user_id, message_id, payload)
    feedback_id = feedback_row["id"]

    # ── Create review item if needed ──────────────────────────────────────
    review_item_id: str | None = None
    if _should_create_review(payload):
        review_item_id = _insert_review_item(db, feedback_id, payload.reason)

    return FeedbackResponse(
        id=feedback_id,
        message_id=message_id,
        rating=payload.rating,
        reason=payload.reason,
        review_item_id=review_item_id,
        created_at=feedback_row["created_at"],
    )
