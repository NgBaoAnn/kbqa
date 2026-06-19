"""ManageFeedbackUseCase — Feedback persistence and review item creation.

Extracted from backend/app/services/feedback_service.py.
Uses only IDatabaseRepository port — no direct DB imports.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Review trigger conditions
_REVIEW_RATINGS = frozenset({"down"})
_REVIEW_REASONS = frozenset({"incorrect", "unsafe"})


@dataclass
class FeedbackInput:
    rating: str         # "up" | "down"
    reason: str | None  # "incorrect" | "unsafe" | "irrelevant" | None
    comment: str | None


@dataclass
class FeedbackOutput:
    id: str
    message_id: str
    rating: str
    reason: str | None
    review_item_id: str | None
    created_at: str


class ManageFeedbackUseCase:
    """Create feedback for an assistant message and optionally flag for review.

    Args:
        db: IDatabaseRepository
    """

    def __init__(self, *, db) -> None:
        self._db = db

    def create_feedback(
        self,
        *,
        user_id: str,
        message_id: str,
        payload: FeedbackInput,
    ) -> FeedbackOutput:
        """Persist feedback. Raises ValueError if message not found or not owned.

        Steps:
        1. Verify message exists, is assistant, belongs to user.
        2. Upsert feedback row.
        3. If negative → insert review_items row.
        4. Return FeedbackOutput.
        """
        # Step 1: Verify ownership + role
        row = self._db.fetch_one(
            """
            select m.id::text as id, m.role, m.conversation_id::text as conversation_id
            from public.messages m
            join public.conversations c on c.id = m.conversation_id
            where m.id = %s and c.user_id = %s
            """,
            (message_id, user_id),
        )
        if row is None:
            raise ValueError("MESSAGE_NOT_FOUND")
        if row["role"] != "assistant":
            raise ValueError("FEEDBACK_ON_NON_ASSISTANT_MESSAGE")

        # Step 2: Upsert feedback
        fb_row = self._db.fetch_one(
            """
            insert into public.feedback (message_id, user_id, rating, reason, comment)
            values (%s, %s, %s, %s, %s)
            on conflict (message_id, user_id) do update set
                rating = excluded.rating,
                reason = excluded.reason,
                comment = excluded.comment,
                created_at = timezone('utc', now())
            returning
                id::text as id,
                message_id::text as message_id,
                rating,
                reason,
                comment,
                created_at::text as created_at
            """,
            (message_id, user_id, payload.rating, payload.reason, payload.comment),
        )
        if fb_row is None:
            raise RuntimeError("Failed to persist feedback.")

        feedback_id = fb_row["id"]

        # Step 3: Review item for negative feedback
        review_item_id: str | None = None
        if payload.rating in _REVIEW_RATINGS or payload.reason in _REVIEW_REASONS:
            review_item_id = self._create_review_item(feedback_id, payload.reason)

        return FeedbackOutput(
            id=feedback_id,
            message_id=message_id,
            rating=payload.rating,
            reason=payload.reason,
            review_item_id=review_item_id,
            created_at=fb_row["created_at"],
        )

    def _create_review_item(self, feedback_id: str, reason: str | None) -> str | None:
        if reason == "incorrect":
            category = "answer_quality"
        elif reason == "unsafe":
            category = "safety"
        else:
            category = "other"

        row = self._db.fetch_one(
            """
            insert into public.review_items (feedback_id, status, category)
            values (%s, 'pending', %s)
            returning id::text as id
            """,
            (feedback_id, category),
        )
        if row is None:
            logger.warning("Failed to create review item for feedback %s", feedback_id)
            return None
        logger.info("Review item created: id=%s category=%s", row["id"], category)
        return row["id"]
