"""AdminAnalyticsUseCase — Admin operational metrics and review queue.

Extracted from backend/app/services/analytics_service.py.
Uses only IDatabaseRepository port — no direct DB imports.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AdminMetrics:
    request_count: int
    average_latency_ms: float
    p95_latency_ms: float
    negative_feedback_rate: float
    engine_usage: dict[str, int]
    pending_review_count: int


@dataclass
class ReviewItemRecord:
    id: str
    status: str
    category: str
    feedback_id: str
    message_id: str
    conversation_id: str
    rating: str
    reason: str | None
    comment: str | None
    created_at: str
    question_content: str | None
    answer_content: str | None


@dataclass
class ReviewQueueResult:
    items: list[ReviewItemRecord]
    total: int
    limit: int
    offset: int


class AdminAnalyticsUseCase:
    """Compute operational metrics and review queue for admin dashboard.

    Args:
        db: IDatabaseRepository
    """

    def __init__(self, *, db) -> None:
        self._db = db

    def get_metrics(self) -> AdminMetrics:
        """Compute operational metrics from query_logs, feedback, review_items."""
        try:
            latency_row = self._db.fetch_one(
                """
                SELECT
                    COUNT(*)                                                          AS request_count,
                    COALESCE(AVG(execution_time_ms), 0.0)                             AS average_latency_ms,
                    COALESCE(
                        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY execution_time_ms),
                        0.0
                    )                                                                 AS p95_latency_ms
                FROM public.query_logs
                """
            )
            request_count = int(latency_row["request_count"]) if latency_row else 0
            average_latency_ms = float(latency_row["average_latency_ms"]) if latency_row else 0.0
            p95_latency_ms = float(latency_row["p95_latency_ms"]) if latency_row else 0.0

            feedback_row = self._db.fetch_one(
                """
                SELECT
                    COUNT(*) AS total_feedback,
                    COUNT(*) FILTER (WHERE rating = 'down') AS negative_count
                FROM public.feedback
                """
            )
            total_feedback = int(feedback_row["total_feedback"]) if feedback_row else 0
            negative_count = int(feedback_row["negative_count"]) if feedback_row else 0
            negative_feedback_rate = (
                round(negative_count / total_feedback, 4) if total_feedback > 0 else 0.0
            )

            engine_rows = self._db.fetch_all(
                "SELECT engine, COUNT(*) AS cnt FROM public.query_logs GROUP BY engine ORDER BY cnt DESC"
            )
            engine_usage = {row["engine"]: int(row["cnt"]) for row in engine_rows}

            review_row = self._db.fetch_one(
                "SELECT COUNT(*) AS pending_count FROM public.review_items WHERE status = 'pending'"
            )
            pending_review_count = int(review_row["pending_count"]) if review_row else 0

        except Exception as exc:
            logger.error("AdminAnalyticsUseCase.get_metrics failed: %s", exc)
            raise RuntimeError("ANALYTICS_UNAVAILABLE") from exc

        return AdminMetrics(
            request_count=request_count,
            average_latency_ms=round(average_latency_ms, 2),
            p95_latency_ms=round(p95_latency_ms, 2),
            negative_feedback_rate=negative_feedback_rate,
            engine_usage=engine_usage,
            pending_review_count=pending_review_count,
        )

    def get_review_queue(self, *, limit: int, offset: int) -> ReviewQueueResult:
        """Return paginated review items for admin review queue."""
        try:
            count_row = self._db.fetch_one("SELECT COUNT(*) AS total FROM public.review_items")
            total = int(count_row["total"]) if count_row else 0

            rows = self._db.fetch_all(
                """
                SELECT
                    ri.id               AS review_item_id,
                    ri.status           AS status,
                    ri.category         AS category,
                    ri.created_at       AS created_at,
                    f.id                AS feedback_id,
                    f.message_id        AS message_id,
                    f.rating            AS rating,
                    f.reason            AS reason,
                    f.comment           AS comment,
                    m.conversation_id   AS conversation_id,
                    m.content           AS answer_content,
                    prev_m.content      AS question_content
                FROM public.review_items ri
                JOIN public.feedback     f      ON f.id  = ri.feedback_id
                JOIN public.messages     m      ON m.id  = f.message_id
                LEFT JOIN public.messages prev_m ON (
                    prev_m.conversation_id = m.conversation_id
                    AND prev_m.role = 'user'
                    AND prev_m.created_at = (
                        SELECT MAX(u.created_at)
                        FROM public.messages u
                        WHERE u.conversation_id = m.conversation_id
                          AND u.role = 'user'
                          AND u.created_at < m.created_at
                    )
                )
                ORDER BY ri.created_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
        except Exception as exc:
            logger.error("AdminAnalyticsUseCase.get_review_queue failed: %s", exc)
            raise RuntimeError("ANALYTICS_UNAVAILABLE") from exc

        items = [
            ReviewItemRecord(
                id=str(row["review_item_id"]),
                status=row["status"],
                category=row["category"],
                feedback_id=str(row["feedback_id"]),
                message_id=str(row["message_id"]),
                conversation_id=str(row["conversation_id"]),
                rating=row["rating"],
                reason=row.get("reason"),
                comment=row.get("comment"),
                created_at=str(row["created_at"]),
                question_content=row.get("question_content"),
                answer_content=row.get("answer_content"),
            )
            for row in rows
        ]

        return ReviewQueueResult(items=items, total=total, limit=limit, offset=offset)
